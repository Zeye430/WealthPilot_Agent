import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import assessment, chat, customers, handoffs, health, products, purchases
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="WealthPilot AI", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(assessment.router)
app.include_router(products.router)
app.include_router(customers.router)
app.include_router(handoffs.router)
app.include_router(purchases.router)
