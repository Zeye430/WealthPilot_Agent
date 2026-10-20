import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import sessionmaker

from app.api import (
    assessment,
    auth,
    chat,
    customers,
    handoffs,
    health,
    ops,
    products,
    purchases,
    reminders,
    speech,
)
from app.auth.service import ensure_demo_accounts
from app.bank_sim import api as bank_sim_api
from app.core.config import get_settings
from app.core.i18n import L, LocaleMiddleware
from app.core.observability import METRICS, RequestContextMiddleware, configure_logging
from app.core.security import RedactingFilter, SecurityMiddleware
from app.db.session import get_engine

configure_logging(get_settings().log_format, [RedactingFilter()])
logger = logging.getLogger(__name__)


def _warmup() -> None:
    """Background warm-up: load the embedding model and sync the search index (tens of seconds on
    first deploy, then only changed content)."""
    from datetime import date

    from app.rag.service import get_retriever

    try:
        get_retriever(date.today())
        logger.info("warmup finished: retriever ready")
    except Exception:
        logger.warning("warmup failed; the retriever will initialize on first use", exc_info=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        with sessionmaker(bind=get_engine())() as db:
            ensure_demo_accounts(db)
    except OperationalError:
        logger.warning("数据库不可用，跳过演示账号初始化")
    if get_settings().warmup_on_start:
        threading.Thread(target=_warmup, name="warmup", daemon=True).start()
    yield


app = FastAPI(title="WealthPilot AI", version=get_settings().app_version, lifespan=lifespan)


@app.exception_handler(PoolTimeoutError)
async def busy(_: Request, exc: PoolTimeoutError) -> JSONResponse:
    """Database pool exhausted (traffic beyond capacity): tell the customer to try again shortly
    instead of a generic 500."""
    logger.error("database pool exhausted", exc_info=exc)
    METRICS.inc(
        "wealthpilot_http_requests_total",
        {"method": "-", "route": "pool_exhausted", "status": "503"},
    )
    return JSONResponse(
        {"detail": L("系统繁忙，请稍后再试。", "The system is busy. Please try again shortly.")},
        status_code=503,
        headers={"Retry-After": "5"},
    )


app.add_middleware(SecurityMiddleware)
app.add_middleware(LocaleMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
    expose_headers=["X-Request-ID"],
)
# Outermost: request IDs and access logs cover every request (including those rejected by the
# security middleware)
app.add_middleware(RequestContextMiddleware)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(assessment.router)
app.include_router(products.router)
app.include_router(customers.router)
app.include_router(handoffs.router)
app.include_router(purchases.router)
app.include_router(reminders.router)
app.include_router(speech.router)
app.include_router(ops.router)
app.include_router(
    bank_sim_api.router
)  # simulated mobile banking (demo); returns 404 when BANK_SIM_ENABLED=false
