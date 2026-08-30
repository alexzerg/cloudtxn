"""Constrained local-AI runbook compiler."""

import os
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Optional, Union
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cloudtxn.errors import ConfigurationError
from cloudtxn.models import Step, Transaction


class KubernetesScalePlanStep(BaseModel):
    """AI-selected scale operation with no authority to choose a context."""

    model_config = ConfigDict(extra="forbid")
    operation: Literal["kubernetes.scale_deployment"]
    deployment: Literal["cloudtxn-demo"]
    replicas: int = Field(ge=0, le=20)


class SsmPutPlanStep(BaseModel):
    """AI-selected SSM operation with no authority to choose an endpoint."""

    model_config = ConfigDict(extra="forbid")
    operation: Literal["aws.ssm_put_parameter"]
    name: Literal["/cloudtxn/demo"]
    value: str


class FailPlanStep(BaseModel):
    """Explicitly requested deterministic failure."""

    model_config = ConfigDict(extra="forbid")
    operation: Literal["test.fail"]
    message: str = Field(min_length=1)


AIPlanStep = Annotated[
    Union[KubernetesScalePlanStep, SsmPutPlanStep, FailPlanStep],
    Field(discriminator="operation"),
]


class AIPlan(BaseModel):
    """Structured AI output before trusted sandbox settings are injected."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9._-]+$")
    summary: str = Field(min_length=1)
    steps: list[AIPlanStep] = Field(min_length=1, max_length=8)
    explanation: list[str] = Field(min_length=1, max_length=8)


@dataclass(frozen=True)
class CompilerSettings:
    """Trusted values that the AI is never allowed to choose."""

    ollama_url: str
    model: str
    kube_context: str
    ssm_endpoint: str

    @classmethod
    def from_environment(cls) -> "CompilerSettings":
        required = {
            "ollama_url": "CLOUDTXN_OLLAMA_URL",
            "model": "CLOUDTXN_OLLAMA_MODEL",
            "kube_context": "CLOUDTXN_ALLOWED_KUBE_CONTEXT",
            "ssm_endpoint": "CLOUDTXN_ALLOWED_SSM_ENDPOINT",
        }
        values: dict[str, str] = {}
        for field_name, variable in required.items():
            value = os.environ.get(variable)
            if not value:
                raise ConfigurationError(f"{variable} is required")
            values[field_name] = value
        return cls(**values)


SYSTEM_PROMPT = """You compile incident runbooks into a tiny allowlisted CloudTxn plan.
Return only JSON matching the provided schema. Never emit shell commands, URLs, credentials,
Kubernetes contexts, namespaces, regions, or cloud account identifiers.

Allowed operations and fields:
1. kubernetes.scale_deployment: deployment, replicas (0-20)
2. aws.ssm_put_parameter: name, value; name must start with /cloudtxn/
3. test.fail: message; include only when the user explicitly asks to simulate a failure

The demo contains exactly one Kubernetes Deployment named cloudtxn-demo and one SSM parameter
named /cloudtxn/demo. Reject ambiguity by using only those resources. Keep the original step order.

Example shape:
{"id":"demo-run","summary":"Safe demo","steps":[
{"operation":"kubernetes.scale_deployment","deployment":"cloudtxn-demo","replicas":3},
{"operation":"aws.ssm_put_parameter","name":"/cloudtxn/demo","value":"after"},
{"operation":"test.fail","message":"planned failure"}],
"explanation":["The final step demonstrates compensation."]}
"""


class OllamaCompiler:
    """Compile natural language through local Ollama structured output."""

    def __init__(
        self,
        settings: CompilerSettings,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    def compile(self, prompt: str) -> AIPlan:
        """Compile and validate, retrying once with schema feedback."""

        if not prompt.strip():
            raise ConfigurationError("runbook prompt cannot be empty")
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt.strip()},
        ]
        last_error = "unknown validation error"
        with httpx.Client(
            base_url=self.settings.ollama_url,
            timeout=180.0,
            transport=self.transport,
        ) as client:
            for _attempt in range(2):
                response = client.post(
                    "/api/chat",
                    json={
                        "model": self.settings.model,
                        "messages": messages,
                        "stream": False,
                        "format": AIPlan.model_json_schema(),
                        "keep_alive": "10m",
                        "options": {
                            "temperature": 0,
                            "num_ctx": 2048,
                            "num_predict": 512,
                        },
                    },
                )
                response.raise_for_status()
                content = str(response.json()["message"]["content"])
                try:
                    return AIPlan.model_validate_json(content)
                except ValidationError as error:
                    last_error = str(error)
                    messages.extend(
                        [
                            {"role": "assistant", "content": content},
                            {
                                "role": "user",
                                "content": (
                                    "Correct the JSON so it matches the schema. "
                                    f"Validation error: {last_error}"
                                ),
                            },
                        ]
                    )
        raise ConfigurationError(f"AI output failed validation twice: {last_error}")


def materialize_transaction(plan: AIPlan, settings: CompilerSettings) -> Transaction:
    """Inject trusted sandbox targets and reject model-selected resources."""

    steps: list[Step] = []
    for index, candidate in enumerate(plan.steps, start=1):
        config: dict[str, Any]
        if candidate.operation == "kubernetes.scale_deployment":
            if candidate.deployment != "cloudtxn-demo":
                raise ConfigurationError("AI selected a non-demo Kubernetes deployment")
            config = {
                "context": settings.kube_context,
                "namespace": "default",
                "deployment": candidate.deployment,
                "replicas": candidate.replicas,
            }
        elif candidate.operation == "aws.ssm_put_parameter":
            if candidate.name != "/cloudtxn/demo":
                raise ConfigurationError("AI selected a non-demo SSM parameter")
            config = {
                "endpoint_url": settings.ssm_endpoint,
                "region": "us-east-1",
                "name": candidate.name,
                "value": candidate.value,
            }
        else:
            config = {"message": candidate.message}
        steps.append(
            Step(
                id=f"step-{index}-{candidate.operation.replace('.', '-')}",
                operation=candidate.operation,
                config=config,
            )
        )
    transaction_id = f"demo-{uuid4().hex[:12]}"
    return Transaction(apiVersion="cloudtxn.io/v1", id=transaction_id, steps=steps)


def compensation_preview(transaction: Transaction) -> list[str]:
    """Describe deterministic reverse compensation without asking the model."""

    descriptions: list[str] = []
    for step in reversed(transaction.steps):
        if step.operation == "kubernetes.scale_deployment":
            description = f"Restore replica count for {step.config['deployment']}"
        elif step.operation == "aws.ssm_put_parameter":
            description = f"Restore previous value for {step.config['name']}"
        else:
            description = "Verify intentional failure made no external mutation"
        descriptions.append(description)
    return descriptions
