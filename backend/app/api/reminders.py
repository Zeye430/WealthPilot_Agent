"""Sale reminder API: customers tap "remind me" on a product card, and view or cancel reminders
under "My reminders"."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_customer_id, get_now
from app.api.products import customer_rating
from app.core.i18n import L
from app.db.session import get_session
from app.products.catalog import load_catalog
from app.reminders.service import (
    BUTTON,
    ReminderError,
    active_reminders,
    cancel_reminder,
    create_reminder,
    reminder_view,
)

router = APIRouter(prefix="/api/v1/reminders", tags=["reminders"])


class ReminderRequest(BaseModel):
    product_code: str


@router.get("")
def list_reminders(db: Session = Depends(get_session), customer_id: str = Depends(get_customer_id)):
    return [reminder_view(r) for r in active_reminders(db, customer_id)]


@router.post("")
def create(
    req: ReminderRequest,
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    rating: str | None = Depends(customer_rating),
    now: datetime = Depends(get_now),
):
    product = load_catalog().get(req.product_code)
    if product is None:
        raise HTTPException(status_code=404, detail=L("产品不存在", "Product not found"))
    try:
        reminder = create_reminder(db, customer_id, product, rating, BUTTON, now)
    except ReminderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return reminder_view(reminder)


@router.delete("/{reminder_id}", status_code=204)
def cancel(
    reminder_id: str,
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    now: datetime = Depends(get_now),
):
    try:
        cancel_reminder(db, customer_id, reminder_id, now)
    except ReminderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
