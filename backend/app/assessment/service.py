"""Reading and writing assessment records: submit, confirm, get the current valid one. Scoring
lives in scoring.py."""

import calendar
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.assessment.scoring import AssessmentResult, load_questionnaire, score_answers
from app.db.models import RiskAssessment

PENDING = "PENDING_CONFIRMATION"
CONFIRMED = "CONFIRMED"
SUPERSEDED = "SUPERSEDED"


class AssessmentFlowError(ValueError):
    """An action the flow doesn't allow (retaking during the cooldown, confirming a missing
    assessment, etc.); the message is shown to the customer."""


def add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year, month = dt.year + month_index // 12, month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])  # Feb 29 + 12 months → Feb 28
    return dt.replace(year=year, month=month, day=day)


def latest_confirmed(db: Session, customer_id: str) -> RiskAssessment | None:
    """The latest confirmed assessment (it may have expired; the policy engine decides)."""
    return db.scalars(
        select(RiskAssessment)
        .where(RiskAssessment.customer_id == customer_id, RiskAssessment.status == CONFIRMED)
        .order_by(RiskAssessment.confirmed_at.desc())
        .limit(1)
    ).first()


def _check_cooldown(db: Session, customer_id: str, now: datetime) -> None:
    hours = load_questionnaire().reassessment_cooldown_hours
    last = latest_confirmed(db, customer_id)
    if last is None or last.expires_at <= now:
        return
    available_at = last.confirmed_at + timedelta(hours=hours)
    if now < available_at:
        raise AssessmentFlowError(
            f"您在 {hours} 小时内已完成过测评，请于 {available_at:%Y-%m-%d %H:%M} 之后再重新测评。"
        )


def submit(
    db: Session, customer_id: str, answers: dict[str, str], now: datetime
) -> tuple[RiskAssessment, AssessmentResult]:
    """Score and save as pending confirmation. Re-answering before confirming isn't subject to
    the cooldown; the old pending record is voided."""
    _check_cooldown(db, customer_id, now)
    result = score_answers(load_questionnaire(), answers)
    db.execute(
        update(RiskAssessment)
        .where(RiskAssessment.customer_id == customer_id, RiskAssessment.status == PENDING)
        .values(status=SUPERSEDED)
    )
    record = RiskAssessment(
        customer_id=customer_id,
        questionnaire_version=result.questionnaire_version,
        answers=answers,
        score=result.score,
        rating=result.rating,
        vetoed=result.vetoed,
        warnings=result.warnings,
        status=PENDING,
        created_at=now,
    )
    db.add(record)
    db.flush()
    return record, result


def confirm(db: Session, customer_id: str, assessment_id: str, now: datetime) -> RiskAssessment:
    record = db.get(RiskAssessment, assessment_id)
    if record is None or record.customer_id != customer_id or record.status != PENDING:
        raise AssessmentFlowError("该测评结果不存在或已失效，请重新作答。")
    _check_cooldown(db, customer_id, now)
    record.status = CONFIRMED
    record.confirmed_at = now
    record.expires_at = add_months(now, load_questionnaire().validity_months)
    db.flush()
    return record
