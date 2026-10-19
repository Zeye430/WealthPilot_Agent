"""健康检查与指标。

- /health：存活检查（进程在、能响应），给负载均衡用，不依赖外部服务，
  避免数据库抖动导致容器被反复重启。
- /health/ready：就绪检查，逐项检查依赖（数据库、模型配置、熔断状态、知识库索引、语音模型），
  任一必需项不可用返回 503，部署平台据此暂停向该实例转发流量。
- /metrics：Prometheus 文本格式指标，需配置 METRICS_TOKEN 并以 Bearer 令牌访问；未配置时关闭。
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
    """各依赖的状态。required=True 的项不可用时，实例不应接收流量。"""
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
    # 熔断打开不代表实例不健康（上游故障），仍可浏览产品、联系理财经理，因此不是必需项
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
