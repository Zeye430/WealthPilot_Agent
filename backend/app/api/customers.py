"""本次需求的查看与修改。基础画像来自银行系统、只读，这里没有修改它的接口。"""

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
    """开始一个新的理财目标时清空本次需求。"""
    db.execute(delete(CustomerNeeds).where(CustomerNeeds.customer_id == customer_id))
    db.commit()
    return customer_state(db, customer_id, now)
