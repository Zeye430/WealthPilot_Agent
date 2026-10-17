from datetime import UTC, datetime
from typing import Annotated

from fastapi import Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.assessment.scoring import load_questionnaire
from app.assessment.service import latest_confirmed
from app.compliance.policy import evaluate_gate
from app.core.config import get_settings
from app.customers.context import customer_profile


def get_customer_id(
    x_demo_user: Annotated[str | None, Header()] = None,
) -> str:
    """演示鉴权：只接受配置中的虚构客户。真实系统应替换为登录鉴权。"""
    settings = get_settings()
    customer_id = x_demo_user or settings.demo_users[0]
    if customer_id not in settings.demo_users:
        raise HTTPException(status_code=403, detail="未知的演示用户")
    return customer_id


def get_now() -> datetime:
    """单独作为依赖，测试中可以替换为固定时间（如验证测评过期）。"""
    return datetime.now(UTC)


class AssessmentSummary(BaseModel):
    rating: str
    rating_name: str
    max_product_risk: str
    score: int
    confirmed_at: datetime
    expires_at: datetime


class CustomerState(BaseModel):
    customer_id: str
    permission: str
    gate_reasons: list[str]
    assessment: AssessmentSummary | None
    profile: dict  # {"base": 银行系统基础画像（只读）, "needs": 本次需求}


def customer_state(db: Session, customer_id: str, now: datetime) -> CustomerState:
    record = latest_confirmed(db, customer_id)
    gate = evaluate_gate(record, now)
    summary = None
    if record is not None and gate.risk_rating:
        band = load_questionnaire(record.questionnaire_version).band(record.rating)
        summary = AssessmentSummary(
            rating=record.rating,
            rating_name=band.name,
            max_product_risk=band.max_product_risk,
            score=record.score,
            confirmed_at=record.confirmed_at,
            expires_at=record.expires_at,
        )
    return CustomerState(
        customer_id=customer_id,
        permission=gate.permission,
        gate_reasons=gate.reason_codes,
        assessment=summary,
        profile=customer_profile(db, customer_id),
    )
