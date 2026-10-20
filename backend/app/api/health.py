"""Health checks and metrics.

- /health: liveness (the process is up and responding), for the load balancer; independent of
external services,
  so database hiccups don't cause containers to be restarted repeatedly.
- /health/ready: readiness, checking each dependency (database, model config, breaker, knowledge
index, speech model);
  returns 503 if any required one is unavailable, so the platform stops routing traffic to this
  instance.
- /metrics: Prometheus text format; requires METRICS_TOKEN and a Bearer token; disabled when unset.
"""

import hmac
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.observability import METRICS
from app.db.models import DocumentChunk
from app.db.session import get_engine
from app.llm.breaker import get_breaker
from app.products.catalog import load_catalog
from app.speech.recognizer import model_installed

router = APIRouter(tags=["health"])
STARTED = time.time()


@router.get("/health")
def health():
    return {"status": "ok"}


def readiness() -> dict:
    """Status of each dependency. When an item with required=True is down, the instance shouldn't
    receive traffic."""
    settings = get_settings()
    checks: dict[str, dict] = {}
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            chunks = conn.execute(select(func.count()).select_from(DocumentChunk)).scalar_one()
        checks["database"] = {"ok": True, "required": True}
        checks["knowledge_index"] = {"ok": chunks > 0, "required": False, "chunks": chunks}
    except Exception as exc:
        checks["database"] = {"ok": False, "required": True, "error": type(exc).__name__}
        checks["knowledge_index"] = {"ok": False, "required": False, "chunks": None}
    fake = settings.llm_provider == "fake"
    checks["llm"] = {
        "ok": fake or bool(settings.llm_api_key.get_secret_value()),
        "required": True,
        "provider": settings.llm_provider,
        "model": "fake" if fake else settings.llm_model,
    }
    breaker = get_breaker().state
    # An open breaker doesn't make the instance unhealthy (it's an upstream fault); browsing
    # products and contacting the RM still work, so it isn't required
    checks["llm_circuit"] = {"ok": breaker == "CLOSED", "required": False, "state": breaker}
    checks["speech_model"] = {"ok": model_installed(), "required": False}
    ready = all(c["ok"] for c in checks.values() if c["required"])
    return {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
        "version": settings.app_version,
        "git_sha": settings.git_sha,
        "catalog_version": load_catalog().catalog_version,
        "uptime_seconds": round(time.time() - STARTED),
    }


@router.get("/health/ready")
def ready():
    result = readiness()
    return JSONResponse(result, status_code=200 if result["status"] == "ready" else 503)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(request: Request):
    token = get_settings().metrics_token
    if token is None:
        raise HTTPException(status_code=404)
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, token.get_secret_value()):
        raise HTTPException(status_code=401)
    return PlainTextResponse(METRICS.render(), media_type="text/plain; version=0.0.4")
