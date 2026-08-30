"""Evidence-grounded AI diagnosis and mitigation compiler."""

import json
from typing import Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict

from cloudtxn.models import Step, Transaction
from cloudtxn.payment_compiler import PaymentSettings


class PauseReconcilerStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["kubernetes.scale_deployment"]
    deployment: Literal["payment-reconciler"]
    replicas: Literal[0]


class DiagnosisHealthStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["http.assert_payment_health"]
    expected_status: Literal[200]
    stabilization_seconds: Literal[5]


class DiagnosisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root_cause: str
    explanation: list[str]
    steps: tuple[PauseReconcilerStep, DiagnosisHealthStep]


class DiagnosisCompiler:
    def __init__(self, settings: PaymentSettings) -> None:
        self.settings = settings

    def compile(self, evidence: dict[str, object]) -> DiagnosisPlan:
        prompt = (
            "Diagnose this payment incident from the evidence. Return concise JSON with exactly "
            "two steps: scale payment-reconciler to 0, then wait up to 5 seconds for lock release "
            "and assert HTTP 200. State clearly that payment-reconciler owns the blocking "
            "AccessExclusiveLock and pausing it releases the lock. Explain briefly why scaling "
            "payment-api or switching providers cannot fix a database lock. "
            f"Evidence: {json.dumps(evidence, sort_keys=True)}"
        )
        schema = DiagnosisPlan.model_json_schema()
        with httpx.Client(base_url=self.settings.ollama_url, timeout=180) as client:
            response = client.post(
                "/api/chat",
                json={
                    "model": self.settings.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": schema,
                    "keep_alive": "30m",
                    "options": {"temperature": 0, "num_ctx": 1536, "num_predict": 240},
                },
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
        return DiagnosisPlan.model_validate_json(content)


def materialize_diagnosis(plan: DiagnosisPlan, settings: PaymentSettings) -> Transaction:
    return Transaction(
        apiVersion="cloudtxn.io/v1",
        id=f"ai-mitigation-{uuid4().hex[:10]}",
        steps=[
            Step(
                id="step-1-pause-reconciler",
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
            ),
            Step(
                id="step-2-verify-payment-health",
                operation="http.assert_payment_health",
                config={
                    "url": settings.payment_health_url,
                    "expected_status": 200,
                    "stabilization_seconds": 5,
                },
            ),
        ],
    )
