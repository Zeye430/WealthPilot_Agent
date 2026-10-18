import logging
from datetime import datetime
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.graph import build_graph, current_turn
from app.api.deps import CustomerState, customer_state, get_customer_id, get_now
from app.assessment.service import latest_confirmed
from app.compliance.policy import evaluate_gate
from app.core.config import get_settings
from app.customers.base import get_customer_info_system
from app.customers.context import age_conflict_note, assessed_loss_tolerance, prompt_section
from app.customers.needs import get_needs
from app.db.models import Conversation, Message, PolicyDecisionLog, ToolCallLog
from app.db.session import get_session
from app.handoff.service import (
    STATUS_LABELS,
    active_handoff,
    handoff_view,
    latest_handoff,
)
from app.llm.client import LLMNotConfiguredError, get_chat_model

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])

HISTORY_LIMIT = 20
ROUTER_MAX_TOKENS = 16


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)


class ChatReply(BaseModel):
    content: str
    ui_blocks: list[dict]


class ChatResponse(BaseModel):
    conversation_id: str
    reply: ChatReply
    state: CustomerState
    handoff: dict | None = None


class MessageOut(BaseModel):
    role: str
    content: str
    ui_blocks: list[dict]


class ConversationOut(BaseModel):
    id: str
    title: str | None
    messages: list[MessageOut]
    handoff: dict | None = None


class ConversationSummary(BaseModel):
    id: str
    title: str | None
    updated_at: datetime
    message_count: int


@lru_cache
def _build_agent():
    settings = get_settings()
    return build_graph(
        get_chat_model(settings),
        # 话题路由是简单分类：关闭思考、限制输出长度，约 0.7 秒、几个 token
        get_chat_model(settings, thinking=False, max_tokens=ROUTER_MAX_TOKENS),
        max_tool_calls=settings.agent_max_tool_calls,
    )


def get_agent():
    try:
        return _build_agent()
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    now: datetime = Depends(get_now),
    agent=Depends(get_agent),
):
    conversation = _get_or_create_conversation(db, customer_id, req.conversation_id, req.message)
    # 先提交会话：工具（如生成交接请求）在独立事务中写入，需要会话已存在
    db.commit()

    handoff = active_handoff(db, conversation.id)
    history = _load_history(db, conversation.id)
    base = get_customer_info_system().get(customer_id)
    customer_context = prompt_section(
        base,
        get_needs(db, customer_id),
        assessed_loss_tolerance(db, customer_id),
    )
    if handoff is not None:
        customer_context += (
            f"\n\n## 当前人工服务状态\n- {STATUS_LABELS[handoff.status]}"
            f"（{handoff.assigned_rm_name}）。如实描述该状态，不要重复生成请求。"
        )
    # 门禁：每条消息都从数据库重新判断，LLM 无法修改
    gate = evaluate_gate(latest_confirmed(db, customer_id), now)

    try:
        result = agent.invoke(
            {
                "messages": [*history, HumanMessage(req.message)],
                "customer_id": customer_id,
                "conversation_id": conversation.id,
                # 基础画像（银行系统，只读）+ 本次需求 + 人工服务状态：每条消息重新组装
                "customer_context": customer_context,
                "permission": gate.permission,
                "risk_rating": gate.risk_rating,
                "gate_reasons": gate.reason_codes,
                "policy_decisions": [
                    {
                        "checkpoint": "GATE",
                        "decision": gate.permission.value,
                        "reason_codes": gate.reason_codes,
                        "rule_version": gate.rule_version,
                    }
                ],
            }
        )
    except Exception as exc:
        logger.exception("agent failed", extra={"conversation_id": conversation.id})
        raise HTTPException(status_code=502, detail="AI 服务暂时不可用，请稍后再试") from exc
    if note := age_conflict_note(req.message, result["reply"], base):
        # 放在回答开头：年龄影响适当性判断，客户应先看到以登记为准
        result["reply"] = f"> {note}\n\n{result['reply']}"

    db.add(Message(conversation_id=conversation.id, role="user", content=req.message))
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=result["reply"],
            ui_blocks=result["ui_blocks"],
        )
    )
    conversation.updated_at = now
    _log_tool_calls(db, conversation.id, current_turn(result["messages"]))
    for d in result["policy_decisions"]:
        db.add(PolicyDecisionLog(conversation_id=conversation.id, **d))
    db.commit()

    return ChatResponse(
        conversation_id=conversation.id,
        reply=ChatReply(content=result["reply"], ui_blocks=result["ui_blocks"]),
        state=customer_state(db, customer_id, now),
        handoff=handoff_view(latest_handoff(db, conversation.id)),
    )


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    db: Session = Depends(get_session), customer_id: str = Depends(get_customer_id)
):
    """历史会话（最近 30 个），按最近活动时间倒序。"""
    rows = db.scalars(
        select(Conversation)
        .where(Conversation.customer_id == customer_id)
        .order_by(Conversation.updated_at.desc())
        .limit(30)
    ).all()
    return [
        ConversationSummary(
            id=c.id, title=c.title, updated_at=c.updated_at, message_count=len(c.messages)
        )
        for c in rows
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
):
    conversation = _owned_conversation(db, conversation_id, customer_id)
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        messages=[_message_out(m) for m in conversation.messages],
        handoff=handoff_view(latest_handoff(db, conversation.id)),
    )


def _owned_conversation(db: Session, conversation_id: str, customer_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conversation


def _message_out(m: Message) -> MessageOut:
    return MessageOut(role=m.role, content=m.content, ui_blocks=m.ui_blocks or [])


def _get_or_create_conversation(
    db: Session, customer_id: str, conversation_id: str | None, first_message: str
) -> Conversation:
    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None or conversation.customer_id != customer_id:
            raise HTTPException(status_code=404, detail="会话不存在")
        return conversation
    conversation = Conversation(customer_id=customer_id, title=first_message[:30])
    db.add(conversation)
    db.flush()
    return conversation


def _load_history(db: Session, conversation_id: str) -> list[BaseMessage]:
    """只把用户与助手的文字回放给 LLM；工具中间过程不回放，控制 token 消耗。"""
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    return [
        HumanMessage(m.content)
        if m.role == "user"
        else AIMessage(f"（理财经理回复）{m.content}" if m.role == "rm" else m.content)
        for m in reversed(rows)
    ]


def _log_tool_calls(db: Session, conversation_id: str, turn: list[BaseMessage]) -> None:
    statuses = {m.tool_call_id: m.status for m in turn if isinstance(m, ToolMessage)}
    for m in turn:
        if isinstance(m, AIMessage):
            for call in m.tool_calls:
                db.add(
                    ToolCallLog(
                        conversation_id=conversation_id,
                        tool_name=call["name"],
                        input=call["args"],
                        status=statuses.get(call["id"], "skipped"),
                    )
                )
