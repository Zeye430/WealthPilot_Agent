from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.assessment.scoring import load_questionnaire
from app.assessment.service import latest_confirmed
from app.auth.service import CUSTOMER, RM, CurrentUser, resolve_session
from app.compliance.policy import evaluate_gate
from app.customers.context import customer_profile
from app.db.session import get_session

SESSION_COOKIE = "wp_session"


def get_now() -> datetime:
    """单独作为依赖，测试中可以替换为固定时间（如验证测评过期）。"""
    return datetime.now(UTC)


def get_current_user(
    request: Request,
    db: Session = Depends(get_session),
    now: datetime = Depends(get_now),
) -> CurrentUser:
    """唯一的身份来源：httpOnly 会话 Cookie。请求头中的任何身份声明都不被信任。"""
    token = request.cookies.get(SESSION_COOKIE)
    user = resolve_session(db, token, now) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def get_customer_id(user: CurrentUser = Depends(get_current_user)) -> str:
    """客户接口：只允许客户角色，且只能访问自己的数据（客户编号来自会话，而非请求参数）。"""
    if user.role != CUSTOMER or not user.customer_id:
        raise HTTPException(status_code=403, detail="仅限客户访问")
    return user.customer_id


def get_rm_id(user: CurrentUser = Depends(get_current_user)) -> str:
    """理财经理接口：只允许理财经理角色，只能看到分配给自己的客户咨询。"""
    if user.role != RM or not user.rm_id:
        raise HTTPException(status_code=403, detail="仅限理财经理访问")
    return user.rm_id


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
