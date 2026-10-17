from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    settings = get_settings()
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "unavailable"
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
        "llm_configured": bool(settings.llm_api_key.get_secret_value()),
        "llm_model": settings.llm_model,
    }
