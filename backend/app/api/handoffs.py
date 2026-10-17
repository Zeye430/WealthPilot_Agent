"""人工交接 API：客户确认 / 取消，理财经理接单 / 回复 / 结束。

所有状态变更都经过状态机校验「谁、从什么状态、到什么状态」，并留痕（handoff_events）。
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_customer_id, get_now
from app.core.config import get_settings
from app.db.models import Handoff, HandoffEvent, Message
from app.db.session import get_session
from app.handoff.service import (
    ACCEPTED,
    CANCELLED,
    IN_PROGRESS,
    PENDING,
    RESOLVED,
    RM_VISIBLE,
    STATUS_LABELS,
    HandoffError,
    handoff_view,
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


# ---------- 客户 ----------


def _customer_handoff(db: Session, handoff_id: str, customer_id: str) -> Handoff:
    handoff = db.get(Handoff, handoff_id)
    if handoff is None or handoff.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="交接请求不存在")
    return handoff


@router.post("/handoffs/{handoff_id}/consent")
def consent(
    handoff_id: str,
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    now: datetime = Depends(get_now),
):
    """客户同意分享卡片中列出的信息，交接请求提交给理财经理（此后理财经理才能看到）。"""
    return _act(
        db, _customer_handoff(db, handoff_id, customer_id), PENDING, "customer", "客户", now
    )


@router.post("/handoffs/{handoff_id}/cancel")
def cancel(
    handoff_id: str,
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    now: datetime = Depends(get_now),
):
    return _act(
        db, _customer_handoff(db, handoff_id, customer_id), CANCELLED, "customer", "客户", now
    )


# ---------- 理财经理 ----------


def get_rm_id(x_demo_user: Annotated[str | None, Header()] = None) -> str:
    """演示鉴权：只接受配置中的理财经理账号。真实系统应替换为员工登录与权限体系。"""
    rm_id = get_settings().demo_rms.get(x_demo_user or "")
    if rm_id is None:
        raise HTTPException(status_code=403, detail="仅限理财经理访问")
    return rm_id


def _rm_handoff(db: Session, handoff_id: str, rm_id: str) -> Handoff:
    """理财经理只能访问分配给自己、且客户已同意分享的交接。"""
    handoff = db.get(Handoff, handoff_id)
    if handoff is None or handoff.assigned_rm_id != rm_id or handoff.status not in RM_VISIBLE:
        raise HTTPException(status_code=404, detail="交接请求不存在")
    return handoff


class RMMessage(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


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
            "customer_name": (h.summary.get("customer") or {}).get("display_name", h.customer_id),
            "consented_at": h.consented_at,
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
        "summary": handoff.summary,
        "consent_scope": handoff.consent_scope,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "events": [
            {"to": STATUS_LABELS[e.to_status], "actor": e.actor, "at": e.at} for e in events
        ],
    }


@router.post("/rm/handoffs/{handoff_id}/accept")
def rm_accept(
    handoff_id: str,
    db: Session = Depends(get_session),
    rm_id: str = Depends(get_rm_id),
    now: datetime = Depends(get_now),
):
    return _act(db, _rm_handoff(db, handoff_id, rm_id), ACCEPTED, "rm", rm_id, now)


@router.post("/rm/handoffs/{handoff_id}/messages")
def rm_reply(
    handoff_id: str,
    body: RMMessage,
    db: Session = Depends(get_session),
    rm_id: str = Depends(get_rm_id),
    now: datetime = Depends(get_now),
):
    """理财经理回复客户；首次回复时状态由「已接单」变为「服务中」。"""
    handoff = _rm_handoff(db, handoff_id, rm_id)
    if handoff.status not in (ACCEPTED, IN_PROGRESS):
        raise HTTPException(status_code=409, detail="请先接单再回复")
    if handoff.status == ACCEPTED:
        transition(db, handoff, IN_PROGRESS, "rm", rm_id, now)
    db.add(Message(conversation_id=handoff.conversation_id, role="rm", content=body.text))
    db.commit()
    return handoff_view(handoff)


@router.post("/rm/handoffs/{handoff_id}/resolve")
def rm_resolve(
    handoff_id: str,
    db: Session = Depends(get_session),
    rm_id: str = Depends(get_rm_id),
    now: datetime = Depends(get_now),
):
    """结束人工服务，AI 恢复回复。"""
    return _act(db, _rm_handoff(db, handoff_id, rm_id), RESOLVED, "rm", rm_id, now)
