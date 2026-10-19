import logging
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
from app.core.config import get_settings
from app.core.i18n import L, LocaleMiddleware
from app.core.observability import METRICS, RequestContextMiddleware, configure_logging
from app.core.security import RedactingFilter, SecurityMiddleware
from app.db.session import get_engine

configure_logging(get_settings().log_format, [RedactingFilter()])
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        with sessionmaker(bind=get_engine())() as db:
            ensure_demo_accounts(db)
    except OperationalError:
        logger.warning("数据库不可用，跳过演示账号初始化")
    yield


app = FastAPI(title="WealthPilot AI", version=get_settings().app_version, lifespan=lifespan)


@app.exception_handler(PoolTimeoutError)
async def busy(_: Request, exc: PoolTimeoutError) -> JSONResponse:
    """数据库连接池耗尽（流量超出容量）：明确告知客户稍后再试，而不是笼统的 500。"""
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
# 最外层：请求编号与访问日志覆盖所有请求（包括被安全中间件拒绝的）
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
