"""CloudTxn hackathon Business Web App."""

import json
import os
import time
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from cloudtxn import __version__
from cloudtxn.adapters.base import AdapterRegistry
from cloudtxn.adapters.feature_flag import FeatureFlagAdapter
from cloudtxn.adapters.health import HealthAssertionAdapter
from cloudtxn.adapters.kubernetes import KubernetesScaleAdapter
from cloudtxn.adapters.ssm import SsmPutParameterAdapter
from cloudtxn.diagnosis_compiler import DiagnosisCompiler, materialize_diagnosis
from cloudtxn.engine import TransactionEngine
from cloudtxn.errors import CloudTxnError
from cloudtxn.github_pr import PullRequestInput, inspect_pull_request
from cloudtxn.journal import Journal
from cloudtxn.models import Transaction
from cloudtxn.payment_compiler import PaymentCompiler, PaymentSettings, materialize, preview
from cloudtxn.safety import demo_mode_enabled

STATIC_ROOT = Path(__file__).parent / "web" / "static"
app = FastAPI(title="CloudTxn", version=__version__)
_executed_runs: set[str] = set()
_executed_lock = Lock()
_operation_lock = Lock()


class CompileRequest(BaseModel):
    """Natural-language runbook request."""

    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=10, max_length=2000)


class RunRequest(BaseModel):
    """Approved typed transaction."""

    model_config = ConfigDict(extra="forbid")
    transaction: Transaction


def _sandbox_root() -> Path:
    if not demo_mode_enabled():
        raise HTTPException(status_code=503, detail="CloudTxn web demo requires sandbox mode")
    value = os.environ.get("CLOUDTXN_SANDBOX_ROOT")
    if not value:
        raise HTTPException(status_code=503, detail="sandbox root is not configured")
    return Path(value).resolve()


def _registry() -> AdapterRegistry:
    return AdapterRegistry(
        [
            KubernetesScaleAdapter(),
            SsmPutParameterAdapter(),
            FeatureFlagAdapter(),
            HealthAssertionAdapter(),
        ]
    )


@app.get("/")
def index() -> FileResponse:
    """Serve the single-page demo UI."""

    return FileResponse(STATIC_ROOT / "incident-chart.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Report only non-sensitive sandbox metadata."""

    return {
        "status": "ready",
        "mode": "isolated-sandbox",
        "timing_profile": (
            "fast-demo" if os.environ.get("CLOUDTXN_DEMO_FAST") == "1" else "normal"
        ),
        "ai": {
            "provider": "local-ollama",
            "model": os.environ.get("CLOUDTXN_OLLAMA_MODEL", "unknown"),
        },
        "kubernetes_context": os.environ.get("CLOUDTXN_ALLOWED_KUBE_CONTEXT"),
        "ssm_endpoint": os.environ.get("CLOUDTXN_ALLOWED_SSM_ENDPOINT"),
        "production_access": False,
    }


def _reset_step(
    journal: Journal,
    operation: str,
    config: dict[str, Any],
) -> None:
    adapter = _registry().get(operation)
    journal.append("reset_step_started", operation=operation, config=config)
    adapter.validate(config)
    adapter.apply(config)
    adapter.verify(config)
    journal.append("reset_step_verified", operation=operation)


@app.post("/api/demo/reset")
def reset_demo() -> dict[str, Any]:
    """Restore and prove the canonical degraded incident state."""

    root = _sandbox_root()
    reset_id = f"demo-reset-{uuid4().hex[:10]}"
    journal = Journal(root / "journals", reset_id)
    try:
        with _operation_lock:
            settings = PaymentSettings.from_environment()
            journal.append("demo_reset_started", reset_id=reset_id)
            kube_base = {
                "context": settings.kube_context,
                "namespace": "default",
                "timeout_seconds": 20,
                "wait_for_ready": True,
                "observation_seconds": 0,
            }
            _reset_step(
                journal,
                "kubernetes.scale_deployment",
                {**kube_base, "deployment": "payment-reconciler", "replicas": 0},
            )
            _reset_step(
                journal,
                "kubernetes.scale_deployment",
                {**kube_base, "deployment": "payment-api", "replicas": 1},
            )
            _reset_step(
                journal,
                "aws.ssm_put_parameter",
                {
                    "endpoint_url": settings.ssm_endpoint,
                    "region": "us-east-1",
                    "name": "/payments/provider",
                    "value": "primary",
                },
            )
            _reset_step(
                journal,
                "feature_flag.set",
                {"url": settings.feature_flag_url, "enabled": False},
            )
            _reset_step(
                journal,
                "kubernetes.scale_deployment",
                {**kube_base, "deployment": "payment-reconciler", "replicas": 1},
            )

            diagnostics_url = os.environ.get("CLOUDTXN_DIAGNOSTICS_URL")
            if not diagnostics_url:
                raise CloudTxnError("CLOUDTXN_DIAGNOSTICS_URL is required")
            deadline = time.monotonic() + 15
            evidence: dict[str, Any] = {}
            while time.monotonic() < deadline:
                response = httpx.get(diagnostics_url, timeout=3)
                response.raise_for_status()
                evidence = response.json()
                blocker = evidence.get("blocker") or {}
                lock = evidence.get("database_lock") or {}
                if (
                    blocker.get("application_name") == "payment-reconciler"
                    and lock.get("mode") == "AccessExclusiveLock"
                    and lock.get("granted") is True
                ):
                    break
                time.sleep(0.25)
            else:
                raise CloudTxnError("payment-reconciler lock was not restored")

            health_response = httpx.get(settings.payment_health_url, timeout=3)
            if health_response.status_code != 503:
                raise CloudTxnError(
                    "reset expected checkout HTTP 503, received "
                    f"HTTP {health_response.status_code}"
                )
            with _executed_lock:
                _executed_runs.clear()
            journal.append(
                "demo_reset_verified",
                status="DEGRADED_READY",
                checkout_http=503,
                blocker="payment-reconciler",
                lock_mode="AccessExclusiveLock",
            )
            return {
                "status": "DEGRADED_READY",
                "payment_api_replicas": 1,
                "payment_reconciler_replicas": 1,
                "provider": "primary",
                "payment_fallback": False,
                "checkout_http": 503,
                "evidence": evidence,
                "journal_path": str(journal.path),
            }
    except Exception as error:
        journal.append("demo_reset_failed", error=str(error))
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/pr/inspect")
def inspect_pr(request: PullRequestInput) -> dict[str, Any]:
    """Compile an allowlisted GitHub PR into an unexecuted typed transaction."""

    try:
        settings = PaymentSettings.from_environment()
        plan = inspect_pull_request(request.url, settings)
        return {
            "pull_request": {
                "number": plan.number,
                "url": plan.url,
                "title": plan.title,
                "author": plan.author,
                "head_ref": plan.head_ref,
                "head_sha": plan.head_sha,
            },
            "manifest": plan.manifest.model_dump(by_alias=True),
            "transaction": plan.transaction.model_dump(by_alias=True),
            "executed": False,
        }
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/compile")
def compile_runbook(request: CompileRequest) -> dict[str, Any]:
    """Compile natural language into an unexecuted typed plan."""

    try:
        settings = PaymentSettings.from_environment()
        plan = PaymentCompiler(settings).compile(request.prompt)
        transaction = materialize(plan, settings)
        return {
            "summary": plan.summary,
            "explanation": plan.explanation,
            "transaction": transaction.model_dump(by_alias=True),
            "compensation_preview": preview(transaction),
            "executed": False,
        }
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/diagnose")
def diagnose_incident() -> dict[str, Any]:
    """Collect real lock evidence and ask local AI for a constrained mitigation."""

    try:
        settings = PaymentSettings.from_environment()
        diagnostics_url = os.environ.get("CLOUDTXN_DIAGNOSTICS_URL")
        if not diagnostics_url:
            raise CloudTxnError("CLOUDTXN_DIAGNOSTICS_URL is required")
        response = httpx.get(diagnostics_url, timeout=10)
        response.raise_for_status()
        evidence = response.json()
        plan = DiagnosisCompiler(settings).compile(evidence)
        transaction = materialize_diagnosis(plan, settings)
        return {
            "root_cause": plan.root_cause,
            "explanation": plan.explanation,
            "evidence": evidence,
            "transaction": transaction.model_dump(by_alias=True),
            "compensation_preview": [
                "Health probe made no mutation",
                "Restore payment-reconciler to 1 replica if recovery fails",
            ],
            "executed": False,
        }
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _execute_transaction(
    transaction: Transaction,
    *,
    mode: str,
) -> dict[str, Any]:
    root = _sandbox_root()
    execution_key = f"{mode}:{transaction.id}"
    with _executed_lock:
        if execution_key in _executed_runs:
            raise HTTPException(status_code=409, detail=f"transaction already {mode}ed")
        _executed_runs.add(execution_key)
    try:
        with _operation_lock:
            engine = TransactionEngine(_registry(), root / "journals")
            result = engine.test(transaction) if mode == "test" else engine.run(transaction)
        journal_path = Path(result.journal_path).resolve()
        if root not in journal_path.parents:
            raise CloudTxnError("journal escaped the sandbox root")
        lines = journal_path.read_text(encoding="utf-8").splitlines()
        events = [json.loads(line) for line in lines]
        return {"result": result.model_dump(), "events": events, "mode": mode}
    except CloudTxnError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/test")
def test_transaction(request: RunRequest) -> dict[str, Any]:
    """Apply and verify a plan, then restore every captured snapshot."""

    return _execute_transaction(request.transaction, mode="test")


@app.post("/api/apply")
def apply_tested_transaction(request: RunRequest) -> dict[str, Any]:
    """Promote a tested plan to a fresh transaction and commit it."""

    promoted = request.transaction.model_copy(
        update={"id": f"{request.transaction.id}-apply-{uuid4().hex[:8]}"}
    )
    return _execute_transaction(promoted, mode="apply")


@app.post("/api/run")
def run_transaction(request: RunRequest) -> dict[str, Any]:
    """Execute an approved transaction and return its full journal timeline."""

    return _execute_transaction(request.transaction, mode="apply")
