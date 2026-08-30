"""Read an allowlisted GitHub PR as a constrained GitOps incident change."""

import base64
import os
import re
from dataclasses import dataclass
from typing import Any, Literal, Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field

from cloudtxn.errors import ConfigurationError
from cloudtxn.models import Step, Transaction
from cloudtxn.payment_compiler import PaymentSettings

MANIFEST_PATH = "gitops/payment-incident.yaml"
PR_PATH = re.compile(r"^/([^/]+)/([^/]+)/pull/(\d+)/?$")


class PullRequestInput(BaseModel):
    """User-supplied GitHub pull-request URL."""

    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=20, max_length=500)


class IncidentSpec(BaseModel):
    """The only GitOps values a PR may propose in the demo."""

    model_config = ConfigDict(extra="forbid")
    payment_api_replicas: int = Field(alias="paymentApiReplicas", ge=1, le=3)
    payment_provider: Literal["primary", "backup"] = Field(alias="paymentProvider")
    payment_fallback: bool = Field(alias="paymentFallback")
    payment_reconciler_replicas: int = Field(
        alias="paymentReconcilerReplicas", ge=0, le=1
    )


class IncidentManifest(BaseModel):
    """Constrained declarative incident-change document."""

    model_config = ConfigDict(extra="forbid")
    api_version: Literal["cloudtxn.io/v1alpha1"] = Field(alias="apiVersion")
    kind: Literal["PaymentIncidentChange"]
    spec: IncidentSpec


@dataclass(frozen=True)
class PullRequestPlan:
    number: int
    url: str
    title: str
    author: str
    head_ref: str
    head_sha: str
    manifest: IncidentManifest
    transaction: Transaction


def _parse_url(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ConfigurationError("only https://github.com pull-request URLs are allowed")
    match = PR_PATH.fullmatch(parsed.path)
    if not match:
        raise ConfigurationError("expected a GitHub URL ending in /owner/repo/pull/NUMBER")
    owner, repository, number = match.groups()
    allowed = os.environ.get("CLOUDTXN_GITHUB_REPOSITORY", "alexzerg/cloudtxn")
    if f"{owner}/{repository}".lower() != allowed.lower():
        raise ConfigurationError(f"pull request must belong to {allowed}")
    return owner, repository, int(number)


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "cloudtxn-demo"}
    token = os.environ.get("CLOUDTXN_GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _transaction(
    number: int,
    manifest: IncidentManifest,
    settings: PaymentSettings,
) -> Transaction:
    spec = manifest.spec
    steps: list[Step] = []

    if spec.payment_api_replicas != 1:
        steps.append(
            Step(
                id="scale-payment-api",
                operation="kubernetes.scale_deployment",
                config={
                    "context": settings.kube_context,
                    "namespace": "default",
                    "deployment": "payment-api",
                    "replicas": spec.payment_api_replicas,
                    "timeout_seconds": 12,
                    "wait_for_ready": False,
                    "observation_seconds": 3,
                },
            )
        )
    if spec.payment_provider != "primary":
        steps.append(
            Step(
                id="switch-payment-provider",
                operation="aws.ssm_put_parameter",
                config={
                    "endpoint_url": settings.ssm_endpoint,
                    "region": "us-east-1",
                    "name": "/payments/provider",
                    "value": spec.payment_provider,
                },
            )
        )
    if spec.payment_fallback:
        steps.append(
            Step(
                id="enable-payment-fallback",
                operation="feature_flag.set",
                config={"url": settings.feature_flag_url, "enabled": True},
            )
        )
    if spec.payment_reconciler_replicas == 0:
        steps.append(
            Step(
                id="pause-payment-reconciler",
                operation="kubernetes.scale_deployment",
                config={
                    "context": settings.kube_context,
                    "namespace": "default",
                    "deployment": "payment-reconciler",
                    "replicas": 0,
                    "timeout_seconds": 12,
                    "wait_for_ready": True,
                    "observation_seconds": 0,
                },
            )
        )

    if not steps:
        raise ConfigurationError("PR does not change any allowlisted incident setting")
    steps.append(
        Step(
            id="verify-payment-health",
            operation="http.assert_payment_health",
            config={
                "url": settings.payment_health_url,
                "expected_status": 200,
                "stabilization_seconds": 5 if spec.payment_reconciler_replicas == 0 else 3,
            },
        )
    )
    return Transaction(
        apiVersion="cloudtxn.io/v1",
        id=f"pr-{number}-{uuid4().hex[:10]}",
        steps=steps,
    )


def inspect_pull_request(
    url: str,
    settings: PaymentSettings,
    transport: Optional[httpx.BaseTransport] = None,
) -> PullRequestPlan:
    """Fetch PR metadata and compile its allowlisted manifest into a transaction."""

    owner, repository, number = _parse_url(url)
    base = f"https://api.github.com/repos/{owner}/{repository}"
    with httpx.Client(timeout=15, headers=_headers(), transport=transport) as client:
        response = client.get(f"{base}/pulls/{number}")
        response.raise_for_status()
        pull = response.json()
        if pull.get("state") != "open":
            raise ConfigurationError("pull request must be open")
        head_sha = str(pull["head"]["sha"])
        content_response = client.get(
            f"{base}/contents/{MANIFEST_PATH}", params={"ref": head_sha}
        )
        content_response.raise_for_status()
        encoded = str(content_response.json()["content"]).replace("\n", "")
        document: Any = yaml.safe_load(base64.b64decode(encoded).decode("utf-8"))
        manifest = IncidentManifest.model_validate(document)

    transaction = _transaction(number, manifest, settings)
    return PullRequestPlan(
        number=number,
        url=str(pull["html_url"]),
        title=str(pull["title"]),
        author=str(pull["user"]["login"]),
        head_ref=str(pull["head"]["ref"]),
        head_sha=head_sha,
        manifest=manifest,
        transaction=transaction,
    )
