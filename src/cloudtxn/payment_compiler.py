"""AI compiler for the payment failover demo."""

import os
from dataclasses import dataclass
from typing import Any, Literal, Optional
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cloudtxn.errors import ConfigurationError
from cloudtxn.models import Step, Transaction


class ScaleStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["kubernetes.scale_deployment"]
    deployment: Literal["payment-api"]
    replicas: Literal[3]


class ProviderStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["aws.ssm_put_parameter"]
    name: Literal["/payments/provider"]
    value: Literal["backup"]


class FlagStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["feature_flag.set"]
    flag: Literal["payment-fallback"]
    enabled: Literal[True]


class HealthStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["http.assert_payment_health"]
    expected_status: Literal[200]
    stabilization_seconds: Literal[3]


class PaymentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    explanation: list[str] = Field(min_length=1, max_length=6)
    steps: tuple[ScaleStep, ProviderStep, FlagStep, HealthStep]


@dataclass(frozen=True)
class PaymentSettings:
    ollama_url: str
    model: str
    kube_context: str
    ssm_endpoint: str
    feature_flag_url: str
    payment_health_url: str

    @classmethod
    def from_environment(cls) -> "PaymentSettings":
        names = {
            "ollama_url": "CLOUDTXN_OLLAMA_URL",
            "model": "CLOUDTXN_OLLAMA_MODEL",
            "kube_context": "CLOUDTXN_ALLOWED_KUBE_CONTEXT",
            "ssm_endpoint": "CLOUDTXN_ALLOWED_SSM_ENDPOINT",
            "feature_flag_url": "CLOUDTXN_FEATURE_FLAG_URL",
            "payment_health_url": "CLOUDTXN_PAYMENT_HEALTH_URL",
        }
        values: dict[str, str] = {}
        for field, variable in names.items():
            value = os.environ.get(variable)
            if not value:
                raise ConfigurationError(f"{variable} is required")
            values[field] = value
        return cls(**values)


PROMPT = """Compile the user's payment incident mitigation into exactly four ordered operations.
Return concise JSON only. Never emit URLs, credentials, contexts, shell commands, namespaces or
regions. The exact steps are: scale payment-api to 3; set /payments/provider to backup; enable the
payment-fallback flag; observe for 3 seconds and assert payment health is HTTP 200.
Explain briefly that a failed health gate triggers deterministic reverse compensation.
"""


class PaymentCompiler:
    def __init__(
        self,
        settings: PaymentSettings,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    def compile(self, user_prompt: str) -> PaymentPlan:
        if not user_prompt.strip():
            raise ConfigurationError("runbook prompt cannot be empty")
        messages = [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": user_prompt.strip()},
        ]
        last_error = "invalid model output"
        with httpx.Client(
            base_url=self.settings.ollama_url,
            timeout=180,
            transport=self.transport,
        ) as client:
            for _attempt in range(2):
                response = client.post(
                    "/api/chat",
                    json={
                        "model": self.settings.model,
                        "messages": messages,
                        "stream": False,
                        "format": PaymentPlan.model_json_schema(),
                        "keep_alive": "30m",
                        "options": {"temperature": 0, "num_ctx": 1536, "num_predict": 320},
                    },
                )
                response.raise_for_status()
                content = str(response.json()["message"]["content"])
                try:
                    return PaymentPlan.model_validate_json(content)
                except ValidationError as error:
                    last_error = str(error)
                    messages.extend(
                        [
                            {"role": "assistant", "content": content},
                            {"role": "user", "content": f"Correct the JSON: {last_error}"},
                        ]
                    )
        raise ConfigurationError(f"AI output failed validation twice: {last_error}")


def materialize(plan: PaymentPlan, settings: PaymentSettings) -> Transaction:
    steps: list[Step] = []
    for index, candidate in enumerate(plan.steps, start=1):
        config: dict[str, Any]
        operation: str
        if isinstance(candidate, ScaleStep):
            operation = candidate.operation
            config = {
                "context": settings.kube_context,
                "namespace": "default",
                "deployment": candidate.deployment,
                "replicas": candidate.replicas,
                "timeout_seconds": 12,
                "wait_for_ready": False,
                "observation_seconds": 3,
            }
        elif isinstance(candidate, ProviderStep):
            operation = candidate.operation
            config = {
                "endpoint_url": settings.ssm_endpoint,
                "region": "us-east-1",
                "name": candidate.name,
                "value": candidate.value,
            }
        elif isinstance(candidate, FlagStep):
            operation = candidate.operation
            config = {"url": settings.feature_flag_url, "enabled": candidate.enabled}
        elif isinstance(candidate, HealthStep):
            operation = candidate.operation
            config = {
                "url": settings.payment_health_url,
                "expected_status": candidate.expected_status,
                "stabilization_seconds": candidate.stabilization_seconds,
            }
        else:
            raise ConfigurationError("unsupported payment plan step")
        steps.append(
            Step(
                id=f"step-{index}-{operation.replace('.', '-')}",
                operation=operation,
                config=config,
            )
        )
    return Transaction(
        apiVersion="cloudtxn.io/v1",
        id=f"payment-failover-{uuid4().hex[:10]}",
        steps=steps,
    )


def preview(transaction: Transaction) -> list[str]:
    labels = {
        "http.assert_payment_health": "Health probe made no mutation",
        "feature_flag.set": "Restore payment-fallback feature flag",
        "aws.ssm_put_parameter": "Restore /payments/provider to primary",
        "kubernetes.scale_deployment": "Restore payment workers to 1 replica",
    }
    return [labels[step.operation] for step in reversed(transaction.steps)]
