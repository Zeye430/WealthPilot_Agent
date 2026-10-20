"""Relationship-manager dashboard API: view the shared summary, mark follow-up, close.

Customers reach the RM via WeCom or phone on the contact card; there are no in-app endpoints for
customer confirmation or messaging.
Every status change is validated by the state machine (who, from which status, to which) and
recorded (handoff_events).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_now, get_rm_id
from app.core.i18n import L
from app.db.models import Handoff, HandoffEvent, Message
from app.db.session import get_session
from app.handoff.service import (
    ACCEPTED,
    RESOLVED,
    RM_VISIBLE,
    HandoffError,
    handoff_view,
    status_label,
    summary_view,
    sync_scope_view,
    transition,
)

router = APIRouter(prefix="/api/v1", tags=["handoffs"])


def _act(db: Session, handoff: Handoff, to: str, role: str, actor: str, now: datetime) -> dict:
    try:
        transition(db, handoff, to, role, actor, now)
    except HandoffError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return handoff_view(handoff)


# ---------- Relationship manager ----------


def _rm_handoff(db: Session, handoff_id: str, rm_id: str) -> Handoff:
    """An RM can only access handoffs assigned to them."""
    handoff = db.get(Handoff, handoff_id)
    if handoff is None or handoff.assigned_rm_id != rm_id or handoff.status not in RM_VISIBLE:
        raise HTTPException(
            status_code=404, detail=L("交接请求不存在", "Handoff request not found")
        )
    return handoff


@router.get("/rm/handoffs")
def rm_list(db: Session = Depends(get_session), rm_id: str = Depends(get_rm_id)):
    rows = db.scalars(
        select(Handoff)
        .where(Handoff.assigned_rm_id == rm_id, Handoff.status.in_(RM_VISIBLE))
        .order_by(Handoff.updated_at.desc())
    ).all()
    return [
        {
            **handoff_view(h),
            "customer_name": (summary_view(h.summary).get("customer") or {}).get(
                "display_name", h.customer_id
            ),
            "synced_at": h.created_at,
            "updated_at": h.updated_at,
        }
        for h in rows
    ]


@router.get("/rm/handoffs/{handoff_id}")
def rm_detail(handoff_id: str, db: Session = Depends(get_session), rm_id: str = Depends(get_rm_id)):
    handoff = _rm_handoff(db, handoff_id, rm_id)
    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == handoff.conversation_id)
        .order_by(Message.created_at)
    ).all()
    events = db.scalars(
        select(HandoffEvent).where(HandoffEvent.handoff_id == handoff.id).order_by(HandoffEvent.at)
    ).all()
    return {
        **handoff_view(handoff),
        "summary": summary_view(handoff.summary),
        "sync_scope": sync_scope_view(handoff.consent_scope),
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "events": [{"to": status_label(e.to_status), "actor": e.actor, "at": e.at} for e in events],
    }


@router.post("/rm/handoffs/{handoff_id}/accept")
def rm_accept(  # mark as "following up"
    handoff_id: str,
    db: Session = Depends(get_session),
    rm_id: str = Depends(get_rm_id),
    now: datetime = Depends(get_now),
):
    return _act(db, _rm_handoff(db, handoff_id, rm_id), ACCEPTED, "rm", rm_id, now)


@router.post("/rm/handoffs/{handoff_id}/resolve")
def rm_resolve(
    handoff_id: str,
    db: Session = Depends(get_session),
    rm_id: str = Depends(get_rm_id),
    now: datetime = Depends(get_now),
):
    """Close this follow-up."""
    return _act(db, _rm_handoff(db, handoff_id, rm_id), RESOLVED, "rm", rm_id, now)
