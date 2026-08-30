"""Isolated payment control-plane simulator."""

from threading import Lock
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

app = FastAPI(title="CloudTxn Payment Control")
_lock = Lock()
_fallback_enabled = False


class FlagUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


@app.get("/payments/flags/payment-fallback")
def get_flag() -> dict[str, bool]:
    with _lock:
        return {"enabled": _fallback_enabled}


@app.put("/payments/flags/payment-fallback")
def set_flag(update: FlagUpdate) -> dict[str, bool]:
    global _fallback_enabled
    with _lock:
        _fallback_enabled = update.enabled
        return {"enabled": _fallback_enabled}


@app.post("/payments/reset")
def reset() -> dict[str, bool]:
    global _fallback_enabled
    with _lock:
        _fallback_enabled = False
        return {"enabled": _fallback_enabled}


@app.get("/payments/health")
def payment_health() -> Any:
    with _lock:
        if _fallback_enabled:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "provider": "backup",
                    "reason": "backup provider unavailable",
                },
            )
    return {"status": "healthy", "provider": "primary"}
