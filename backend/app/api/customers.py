"""View and edit current needs. The base profile comes from the bank system and is read-only;
there is no endpoint to change it."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.deps import CustomerState, customer_state, get_customer_id, get_now
from app.customers.needs import CUSTOMER_EDIT, NeedsError, NeedsUpdate, update_needs
from app.db.models import CustomerNeeds
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/needs", tags=["customers"])


@router.patch("", response_model=CustomerState)
def edit_needs(
    update: NeedsUpdate,
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    now: datetime = Depends(get_now),
):
    try:
        update_needs(db, customer_id, update, CUSTOMER_EDIT, now)
    except NeedsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return customer_state(db, customer_id, now)


@router.delete("", response_model=CustomerState)
def clear_needs(
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    now: datetime = Depends(get_now),
):
    """Clear current needs when starting a new wealth goal."""
    db.execute(delete(CustomerNeeds).where(CustomerNeeds.customer_id == customer_id))
    db.commit()
    return customer_state(db, customer_id, now)
