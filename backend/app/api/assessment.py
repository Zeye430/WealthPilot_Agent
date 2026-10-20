from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import CustomerState, customer_state, get_customer_id, get_now
from app.assessment import service
from app.assessment.scoring import AssessmentError, AssessmentResult, load_questionnaire
from app.core.config import get_settings
from app.customers.base import age_option, get_customer_info_system
from app.db.models import (
    Conversation,
    CustomerNeeds,
    Handoff,
    HandoffEvent,
    Message,
    PolicyDecisionLog,
    RiskAssessment,
    SaleReminder,
    ToolCallLog,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["assessment"])


class SubmitRequest(BaseModel):
    answers: dict[str, str]


class SubmitResponse(BaseModel):
    assessment_id: str
    result: AssessmentResult


@router.get("/me", response_model=CustomerState)
def me(
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    now: datetime = Depends(get_now),
):
    return customer_state(db, customer_id, now)


@router.get("/assessment/questionnaire")
def questionnaire(customer_id: str = Depends(get_customer_id)):
    """Questionnaire with preselected answers: the bank already knows the customer's age, so
    question 1 is preselected for the customer to confirm or change."""
    view = load_questionnaire().public_view()
    base = get_customer_info_system().get(customer_id)
    view["prefill"] = {"q1": age_option(base.age)} if base else {}
    return view


@router.post("/assessment", response_model=SubmitResponse)
def submit(
    req: SubmitRequest,
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    now: datetime = Depends(get_now),
):
    try:
        record, result = service.submit(db, customer_id, req.answers, now)
    except AssessmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except service.AssessmentFlowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return SubmitResponse(assessment_id=record.id, result=result)


@router.post("/assessment/{assessment_id}/confirm", response_model=CustomerState)
def confirm(
    assessment_id: str,
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    now: datetime = Depends(get_now),
):
    try:
        service.confirm(db, customer_id, assessment_id, now)
    except service.AssessmentFlowError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return customer_state(db, customer_id, now)


@router.post("/demo/reset", status_code=204)
def reset_demo(db: Session = Depends(get_session), customer_id: str = Depends(get_customer_id)):
    """Clear the current demo customer's assessments, conversations, current needs and sale
    reminders (the base profile comes from the bank system and is untouched)."""
    if not get_settings().demo_mode:
        raise HTTPException(status_code=404)
    conversation_ids = select(Conversation.id).where(Conversation.customer_id == customer_id)
    handoff_ids = select(Handoff.id).where(Handoff.customer_id == customer_id)
    db.execute(delete(HandoffEvent).where(HandoffEvent.handoff_id.in_(handoff_ids)))
    db.execute(delete(Handoff).where(Handoff.customer_id == customer_id))
    for model in (PolicyDecisionLog, ToolCallLog, Message):
        db.execute(delete(model).where(model.conversation_id.in_(conversation_ids)))
    db.execute(delete(Conversation).where(Conversation.customer_id == customer_id))
    db.execute(delete(RiskAssessment).where(RiskAssessment.customer_id == customer_id))
    db.execute(delete(CustomerNeeds).where(CustomerNeeds.customer_id == customer_id))
    db.execute(delete(SaleReminder).where(SaleReminder.customer_id == customer_id))
    db.commit()
