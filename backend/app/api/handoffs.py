"""理财经理看板 API：查看同步过来的咨询要点，标记跟进、结束。

客户通过名片上的企业微信 / 电话联系理财经理，应用内不再有客户确认或文字沟通的接口。
所有状态变更都经过状态机校验「谁、从什么状态、到什么状态」，并留痕（handoff_events）。
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_now
from app.core.config import get_settings
from app.db.models import Handoff, HandoffEvent, Message
from app.db.session import get_session
from app.handoff.service import (
    ACCEPTED,
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


# ---------- 理财经理 ----------


def get_rm_id(x_demo_user: Annotated[str | None, Header()] = None) -> str:
    """演示鉴权：只接受配置中的理财经理账号。真实系统应替换为员工登录与权限体系。"""
    rm_id = get_settings().demo_rms.get(x_demo_user or "")
    if rm_id is None:
        raise HTTPException(status_code=403, detail="仅限理财经理访问")
    return rm_id


def _rm_handoff(db: Session, handoff_id: str, rm_id: str) -> Handoff:
    """理财经理只能访问分配给自己的交接。"""
    handoff = db.get(Handoff, handoff_id)
    if handoff is None or handoff.assigned_rm_id != rm_id or handoff.status not in RM_VISIBLE:
        raise HTTPException(status_code=404, detail="交接请求不存在")
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
            "customer_name": (h.summary.get("customer") or {}).get("display_name", h.customer_id),
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
        "summary": handoff.summary,
        "sync_scope": handoff.consent_scope,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "events": [
            {"to": STATUS_LABELS[e.to_status], "actor": e.actor, "at": e.at} for e in events
        ],
    }


@router.post("/rm/handoffs/{handoff_id}/accept")
def rm_accept(  # 标记「跟进中」
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
    """结束本次跟进。"""
    return _act(db, _rm_handoff(db, handoff_id, rm_id), RESOLVED, "rm", rm_id, now)
