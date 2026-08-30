"""Customer-facing payment API backed by a real PostgreSQL lock failure."""

import os
import time
from typing import Any

import psycopg  # type: ignore[import-not-found]
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="PayFlow Checkout")
DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://cloudtxn:cloudtxn@postgres:5432/cloudtxn",
)


def connect(application_name: str, timeout_ms: int) -> Any:
    connection = psycopg.connect(DSN, application_name=application_name)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(f"SET statement_timeout = {int(timeout_ms)}")
    return connection


def initialize() -> None:
    for _attempt in range(60):
        try:
            connection_context = connect("payment-api-init", 5000)
            with connection_context as connection, connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS payments ("
                    "id serial PRIMARY KEY, status text NOT NULL)"
                )
                cursor.execute("SELECT count(*) FROM payments")
                if int(cursor.fetchone()[0]) == 0:
                    cursor.execute("INSERT INTO payments(status) VALUES ('settled')")
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("PostgreSQL did not become ready")


initialize()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/lab/health")
def payment_health() -> Any:
    started = time.monotonic()
    try:
        connection_context = connect("payment-health", 900)
        with connection_context as connection, connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM payments WHERE status = 'settled'")
            settled = int(cursor.fetchone()[0])
        latency_ms = round((time.monotonic() - started) * 1000)
        return {
            "status": "healthy",
            "checkout_success": 100 if settled > 0 else 0,
            "latency_ms": latency_ms,
            "reason": "database responsive",
        }
    except Exception:
        latency_ms = round((time.monotonic() - started) * 1000)
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "checkout_success": 42,
                "latency_ms": latency_ms,
                "reason": "database lock timeout",
            },
        )


@app.get("/lab/diagnostics")
def diagnostics() -> dict[str, object]:
    connection_context = connect("payment-diagnostics", 3000)
    with connection_context as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT pid, application_name, state, wait_event_type, query "
            "FROM pg_stat_activity "
            "WHERE application_name = 'payment-reconciler' "
            "ORDER BY backend_start DESC LIMIT 1"
        )
        activity = cursor.fetchone()
        cursor.execute(
            "SELECT l.mode, l.granted FROM pg_locks l "
            "JOIN pg_class c ON c.oid = l.relation "
            "WHERE c.relname = 'payments' AND l.mode = 'AccessExclusiveLock'"
        )
        lock = cursor.fetchone()
    return {
        "backend_error": "database lock timeout",
        "blocked_table": "payments",
        "blocker": {
            "pid": activity[0] if activity else None,
            "application_name": activity[1] if activity else None,
            "state": activity[2] if activity else None,
            "wait_event_type": activity[3] if activity else None,
            "query": activity[4] if activity else None,
        },
        "database_lock": {
            "mode": lock[0] if lock else None,
            "granted": lock[1] if lock else False,
        },
        "kubernetes_owner": "deployment/payment-reconciler",
    }


@app.get("/customer", response_class=HTMLResponse)
def customer() -> str:
    return """<!doctype html>
<html><head><meta charset='utf-8'><title>PayFlow</title>
<style>
*{box-sizing:border-box}html,body{min-height:100%;overflow:hidden}
body{font-family:system-ui;background:#07111f;color:#edf5ff;display:grid;
place-items:center;margin:0;padding:16px}.card{width:min(520px,100%);padding:22px;
background:#10243c;border:1px solid #29415f;border-radius:18px}
.card h1{margin:0 0 8px;font-size:30px}.status{font-size:24px;font-weight:800}
.bad{color:#ff7383}.good{color:#64e49c}.bar{height:10px;background:#203653;
border-radius:8px;overflow:hidden}.fill{height:100%;background:#ff7383;width:42%}
</style></head><body><div class='card'><h1>PayFlow Checkout</h1>
<p>Live customer-facing payment service</p><div id='status' class='status'>Checking…</div>
<p id='reason'></p><div class='bar'><div id='fill' class='fill'></div></div>
<p id='metric'></p></div><script>
async function poll(){const r=await fetch('/lab/health'),d=await r.json(),ok=r.ok;
status.textContent=ok?'PAYMENTS HEALTHY':'PAYMENTS DEGRADED';
status.className='status '+(ok?'good':'bad');reason.textContent=ok?
'Database queries are completing normally.':d.reason;
fill.style.width=(d.checkout_success||100)+'%';fill.style.background=ok?'#64e49c':'#ff7383';
metric.textContent='Checkout success: '+(d.checkout_success||100)+'% · latency: '+
d.latency_ms+'ms'}setInterval(poll,1500);poll()</script></body></html>"""
