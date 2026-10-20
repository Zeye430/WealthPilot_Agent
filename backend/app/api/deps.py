from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.assessment.scoring import load_questionnaire
from app.assessment.service import latest_confirmed
from app.auth.service import CUSTOMER, OPS, RM, CurrentUser, resolve_session
from app.compliance.policy import evaluate_gate
from app.core.i18n import L
from app.customers.context import customer_profile
from app.db.session import get_session

SESSION_COOKIE = "wp_session"


def get_now() -> datetime:
    """A separate dependency so tests can pin the time (e.g. to check assessment expiry)."""
    return datetime.now(UTC)


def get_current_user(
    request: Request,
    db: Session = Depends(get_session),
    now: datetime = Depends(get_now),
) -> CurrentUser:
    """The only identity source: the httpOnly session cookie. Identity claims in request headers
    are never trusted."""
    token = request.cookies.get(SESSION_COOKIE)
    user = resolve_session(db, token, now) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail=L("请先登录", "Please sign in"))
    return user


def get_customer_id(user: CurrentUser = Depends(get_current_user)) -> str:
    """Customer endpoints: customer role only, and only the customer's own data (the customer ID
    comes from the session, not request parameters)."""
    if user.role != CUSTOMER or not user.customer_id:
        raise HTTPException(status_code=403, detail=L("仅限客户访问", "Customers only"))
    return user.customer_id


def get_rm_id(user: CurrentUser = Depends(get_current_user)) -> str:
    """Relationship-manager endpoints: RM role only, and only requests assigned to that RM."""
    if user.role != RM or not user.rm_id:
        raise HTTPException(
            status_code=403, detail=L("仅限理财经理访问", "Relationship managers only")
        )
    return user.rm_id


def get_ops_user(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Ops dashboard: ops role only; aggregate metrics only, no conversation content or customer
    data."""
    if user.role != OPS:
        raise HTTPException(status_code=403, detail=L("仅限运维人员访问", "Operations staff only"))
    return user


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
    profile: dict  # {"base": base profile from the bank system (read-only), "needs": current needs}


def customer_state(db: Session, customer_id: str, now: datetime) -> CustomerState:
    record = latest_confirmed(db, customer_id)
    gate = evaluate_gate(record, now)
    summary = None
    if record is not None and gate.risk_rating:
        band = load_questionnaire(record.questionnaire_version).band(record.rating)
        summary = AssessmentSummary(
            rating=record.rating,
            rating_name=band.display_name,
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
