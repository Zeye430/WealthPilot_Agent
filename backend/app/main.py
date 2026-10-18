import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.api import (
    assessment,
    auth,
    chat,
    customers,
    handoffs,
    health,
    products,
    purchases,
    reminders,
    speech,
)
from app.auth.service import ensure_demo_accounts
from app.core.config import get_settings
from app.core.security import RedactingFilter, SecurityMiddleware
from app.db.session import get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
for handler in logging.getLogger().handlers:
    handler.addFilter(RedactingFilter())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        with sessionmaker(bind=get_engine())() as db:
            ensure_demo_accounts(db)
    except OperationalError:
        logger.warning("数据库不可用，跳过演示账号初始化")
    yield


app = FastAPI(title="WealthPilot AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
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
