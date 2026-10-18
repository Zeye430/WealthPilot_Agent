"""人工交接状态机与交接摘要。

客户通过理财经理名片（企业微信 / 电话）直接联系；系统同时把咨询要点同步到理财经理看板。
状态只能由真实操作推进，且每一步都校验「谁」有权推进：
    PENDING（已同步，待跟进）─理财经理跟进→ ACCEPTED ─结束→ RESOLVED；PENDING 也可直接结束
交接摘要由代码根据结构化数据生成（不由 LLM 撰写），避免摘要中出现与事实不符的内容。

产品负责人决定（2026-10-18）：客户界面不展示资料确认卡片，只展示理财经理名片并告知「咨询要点已同步」；
不再在应用内与理财经理文字沟通，因此 AI 始终可以回复。
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessment.scoring import load_questionnaire
from app.assessment.service import latest_confirmed
from app.compliance.policy import evaluate_gate
from app.customers.base import get_customer_info_system
from app.customers.needs import get_needs
from app.db.models import Handoff, HandoffEvent, Message
from app.products.catalog import load_catalog

PENDING = "PENDING"
ACCEPTED = "ACCEPTED"
RESOLVED = "RESOLVED"
CANCELLED = "CANCELLED"
# 旧流程的状态（客户确认、应用内服务），只为兼容历史数据保留标签
AWAITING_CONSENT = "AWAITING_CONSENT"
IN_PROGRESS = "IN_PROGRESS"
ACTIVE = (PENDING, ACCEPTED)
RM_VISIBLE = (PENDING, ACCEPTED, IN_PROGRESS, RESOLVED)

STATUS_LABELS = {
    PENDING: "咨询要点已同步，等待理财经理跟进",
    ACCEPTED: "理财经理跟进中",
    RESOLVED: "已结束",
    CANCELLED: "已取消",
    AWAITING_CONSENT: "待客户确认（旧流程）",
    IN_PROGRESS: "理财经理服务中（旧流程）",
}

# 角色 → 允许的状态变更
TRANSITIONS = {
    (PENDING, ACCEPTED): "rm",
    (PENDING, RESOLVED): "rm",
    (ACCEPTED, RESOLVED): "rm",
    (PENDING, CANCELLED): "customer",
}

REASON_LABELS = {
    "USER_REQUEST": "客户主动要求人工服务",
    "REGULATED_ADVISORY_REQUEST": "需要正式投资建议或交易等受监管服务",
    "HIGH_COMPLEXITY": "专业复杂度高（如退休、税务、跨类资产规划）",
    "SUITABILITY_CONFLICT": "客户诉求与风险等级存在冲突",
    "MISSING_CRITICAL_INFORMATION": "关键信息缺失，需人工核实",
    "LOW_RETRIEVAL_CONFIDENCE": "资料中未找到可靠依据",
    "UNVERIFIED_PRODUCT_DATA": "产品资料未核实",
    "TOOL_FAILURE": "系统工具异常",
    "HUMAN_AUTHORIZATION_REQUIRED": "需要人工授权或审批",
}

# 同步给理财经理的内容（看板展示；客户界面以一句话告知）
SYNC_SCOPE = [
    "基础资料（客户等级、在本行资产）",
    "本次需求（金额、期限、流动性、目标收益等）",
    "风险测评结果",
    "本次对话记录",
]


class HandoffError(ValueError):
    pass


def active_handoff(db: Session, conversation_id: str) -> Handoff | None:
    return db.scalars(
        select(Handoff)
        .where(Handoff.conversation_id == conversation_id, Handoff.status.in_(ACTIVE))
        .order_by(Handoff.created_at.desc())
        .limit(1)
    ).first()


def latest_handoff(db: Session, conversation_id: str) -> Handoff | None:
    return db.scalars(
        select(Handoff)
        .where(Handoff.conversation_id == conversation_id)
        .order_by(Handoff.created_at.desc())
        .limit(1)
    ).first()


def _record(db: Session, handoff: Handoff, from_status: str | None, actor: str, now: datetime):
    db.add(
        HandoffEvent(
            handoff_id=handoff.id,
            from_status=from_status,
            to_status=handoff.status,
            actor=actor,
            at=now,
        )
    )


def transition(db: Session, handoff: Handoff, to: str, role: str, actor: str, now: datetime):
    allowed = TRANSITIONS.get((handoff.status, to))
    if allowed is None:
        raise HandoffError(
            f"当前状态「{STATUS_LABELS[handoff.status]}」不能变更为「{STATUS_LABELS[to]}」"
        )
    if allowed != role:
        raise HandoffError("无权执行该操作")
    previous = handoff.status
    handoff.status = to
    handoff.updated_at = now
    _record(db, handoff, previous, actor, now)
    db.flush()
    return handoff


def build_summary(
    db: Session,
    conversation_id: str,
    customer_id: str,
    reason: str,
    open_questions: list[str],
    now: datetime,
) -> dict:
    """交接摘要：全部来自结构化数据。理财经理据此接手，无需重复询问客户。"""
    base = get_customer_info_system().get(customer_id)
    record = latest_confirmed(db, customer_id)
    gate = evaluate_gate(record, now)
    if gate.risk_rating:
        band = load_questionnaire().band(gate.risk_rating)
        assessment = (
            f"{band.rating} {band.name}（可购买 {band.max_product_risk} 及以下），"
            f"有效期至 {record.expires_at:%Y-%m-%d}"
        )
    else:
        assessment = (
            "测评已过期" if "ASSESSMENT_EXPIRED" in gate.reason_codes else "尚未完成风险测评"
        )

    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    ).all()
    catalog = load_catalog()
    discussed: dict[str, str] = {}
    for m in messages:
        for block in m.ui_blocks or []:
            for code in _product_codes(block):
                if (p := catalog.get(code)) is not None:
                    discussed[code] = f"{p.name}（{p.effective_risk_level}）"
    recent = [m.content[:120] for m in messages if m.role == "user"][-5:]

    return {
        "reason": REASON_LABELS.get(reason, reason),
        "customer": base.summary() if base else None,
        "assessment": assessment,
        "needs": [r for r in get_needs(db, customer_id).display() if r["value"]],
        "products_discussed": list(discussed.values()),
        "open_questions": open_questions,
        "recent_customer_messages": recent,
    }


def _product_codes(block: dict) -> list[str]:
    match block.get("type"):
        case "product_list":
            return [i["code"] for i in block["items"]]
        case "product_detail":
            return [block["code"]]
        case "comparison_table":
            return [c["code"] for c in block["columns"]]
        case "allocation":
            return [s["code"] for s in block["slices"]]
    return []


def create_request(
    db: Session,
    conversation_id: str,
    customer_id: str,
    reason: str,
    open_questions: list[str],
    now: datetime,
) -> Handoff:
    """生成交接请求并同步到理财经理看板。同一会话已有进行中的交接时直接返回，不重复创建。"""
    if existing := active_handoff(db, conversation_id):
        return existing
    if reason not in REASON_LABELS:
        raise HandoffError(f"未知的交接原因：{reason}")
    base = get_customer_info_system().get(customer_id)
    rm_id, rm_name = (
        (base.assigned_rm.id, base.assigned_rm.name) if base else ("RM001", "值班理财经理")
    )
    handoff = Handoff(
        conversation_id=conversation_id,
        customer_id=customer_id,
        reason=reason,
        status=PENDING,
        summary=build_summary(db, conversation_id, customer_id, reason, open_questions, now),
        consent_scope=SYNC_SCOPE,
        assigned_rm_id=rm_id,
        assigned_rm_name=rm_name,
        created_at=now,
        updated_at=now,
    )
    db.add(handoff)
    db.flush()
    _record(db, handoff, None, "AI", now)
    return handoff


def handoff_view(handoff: Handoff | None) -> dict | None:
    if handoff is None:
        return None
    return {
        "id": handoff.id,
        "status": handoff.status,
        "status_label": STATUS_LABELS[handoff.status],
        "rm_name": handoff.assigned_rm_name,
        "reason": REASON_LABELS.get(handoff.reason, handoff.reason),
    }


def rm_contact_card(handoff: Handoff) -> dict:
    """客户界面的理财经理名片：只含理财经理信息与联系方式，不展示客户资料。"""
    base = get_customer_info_system().get(handoff.customer_id)
    if base and base.assigned_rm.id == handoff.assigned_rm_id:
        contact = base.assigned_rm.contact_card()
    else:
        contact = {"rm_name": handoff.assigned_rm_name, "rm_title": "理财经理"}
        contact |= {"phone": None, "wecom_url": None}
    return {
        "type": "rm_contact",
        **contact,
        "handoff_id": handoff.id,
        "notice": f"您的咨询要点已同步给{handoff.assigned_rm_name}，联系时无需重复说明。",
    }
