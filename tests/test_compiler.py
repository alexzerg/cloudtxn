"""Tests for constrained AI compilation and trusted materialization."""

import json

import httpx
import pytest

from cloudtxn.compiler import CompilerSettings, OllamaCompiler, materialize_transaction
from cloudtxn.errors import ConfigurationError

SETTINGS = CompilerSettings(
    ollama_url="http://ollama.test",
    model="demo-model",
    kube_context="k3d-cloudtxn-sandbox-demo",
    ssm_endpoint="http://127.0.0.1:14566",
)


def response_for(plan: dict[str, object]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": json.dumps(plan)}},
        )

    return httpx.MockTransport(handler)


def test_compiles_and_injects_only_trusted_targets() -> None:
    transport = response_for(
        {
            "id": "demo-run",
            "summary": "Scale, update, and fail",
            "steps": [
                {
                    "operation": "kubernetes.scale_deployment",
                    "deployment": "cloudtxn-demo",
                    "replicas": 3,
                },
                {
                    "operation": "aws.ssm_put_parameter",
                    "name": "/cloudtxn/demo",
                    "value": "after",
                },
                {"operation": "test.fail", "message": "planned failure"},
            ],
            "explanation": ["The final step demonstrates compensation."],
        }
    )

    plan = OllamaCompiler(SETTINGS, transport=transport).compile("Scale and then fail safely")
    transaction = materialize_transaction(plan, SETTINGS)

    assert transaction.id.startswith("demo-")
    assert transaction.id != plan.id
    assert transaction.steps[0].config["context"] == "k3d-cloudtxn-sandbox-demo"
    assert transaction.steps[1].config["endpoint_url"] == "http://127.0.0.1:14566"
    assert all("profile" not in step.config for step in transaction.steps)


def test_rejects_model_selected_non_demo_resource() -> None:
    transport = response_for(
        {
            "id": "unsafe-run",
            "summary": "Unsafe target",
            "steps": [
                {
                    "operation": "kubernetes.scale_deployment",
                    "deployment": "production-api",
                    "replicas": 3,
                }
            ],
            "explanation": ["Unsafe"],
        }
    )

    with pytest.raises(ConfigurationError, match="AI output failed validation twice"):
        OllamaCompiler(SETTINGS, transport=transport).compile("Scale production please")
