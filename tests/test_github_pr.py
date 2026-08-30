"""GitHub PR to typed transaction boundary tests."""

import base64

import httpx

from cloudtxn.github_pr import inspect_pull_request
from cloudtxn.payment_compiler import PaymentSettings


def settings() -> PaymentSettings:
    return PaymentSettings(
        ollama_url="http://ollama:11434",
        model="demo",
        kube_context="k3d-cloudtxn-sandbox-demo",
        ssm_endpoint="http://localstack:4566",
        feature_flag_url="http://payment-control:8090/payments/flags/payment-fallback",
        payment_health_url="http://kong:8000/lab/health",
    )


def transport_for(manifest: str, branch: str) -> httpx.MockTransport:
    encoded = base64.b64encode(manifest.encode()).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pulls/1"):
            return httpx.Response(
                200,
                json={
                    "state": "open",
                    "html_url": "https://github.com/alexzerg/cloudtxn/pull/1",
                    "title": "Demo mitigation",
                    "user": {"login": "engineer"},
                    "head": {"sha": "abc123", "ref": branch},
                },
            )
        if request.url.path.endswith("/contents/gitops/payment-incident.yaml"):
            return httpx.Response(200, json={"content": encoded})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_bad_pr_compiles_all_engineer_hypothesis_steps(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDTXN_GITHUB_REPOSITORY", "alexzerg/cloudtxn")
    manifest = """apiVersion: cloudtxn.io/v1alpha1
kind: PaymentIncidentChange
spec:
  paymentApiReplicas: 3
  paymentProvider: backup
  paymentFallback: true
  paymentReconcilerReplicas: 1
"""

    plan = inspect_pull_request(
        "https://github.com/alexzerg/cloudtxn/pull/1",
        settings(),
        transport_for(manifest, "demo/bad-engineer-fix"),
    )

    assert [step.operation for step in plan.transaction.steps] == [
        "kubernetes.scale_deployment",
        "aws.ssm_put_parameter",
        "feature_flag.set",
        "http.assert_payment_health",
    ]
    assert plan.transaction.steps[0].config["wait_for_ready"] is False


def test_ai_pr_compiles_lock_owner_mitigation(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDTXN_GITHUB_REPOSITORY", "alexzerg/cloudtxn")
    manifest = """apiVersion: cloudtxn.io/v1alpha1
kind: PaymentIncidentChange
spec:
  paymentApiReplicas: 1
  paymentProvider: primary
  paymentFallback: false
  paymentReconcilerReplicas: 0
"""

    plan = inspect_pull_request(
        "https://github.com/alexzerg/cloudtxn/pull/1",
        settings(),
        transport_for(manifest, "demo/ai-lock-remediation"),
    )

    assert [step.operation for step in plan.transaction.steps] == [
        "kubernetes.scale_deployment",
        "http.assert_payment_health",
    ]
    assert plan.transaction.steps[0].config["deployment"] == "payment-reconciler"
