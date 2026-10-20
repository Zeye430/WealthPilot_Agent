import logging
import time
from datetime import datetime
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.graph import build_graph, current_turn
from app.agent.prompts import (
    ASSESSMENT_REQUIRED_REPLY,
    BREAKER_OPEN_REPLY,
    OUT_OF_SCOPE_REPLY,
    SAFE_FALLBACK_REPLY,
    TOOL_LIMIT_REPLY,
    TURN_TIMEOUT_REPLY,
)
from app.api.deps import (
    CustomerState,
    customer_state,
    get_current_user,
    get_customer_id,
    get_now,
)
from app.assessment.service import latest_confirmed
from app.auth.service import CurrentUser
from app.compliance.policy import evaluate_gate
from app.core.config import get_settings
from app.core.i18n import L, all_versions, current, localized
from app.core.ratelimit import chat_limit
from app.customers.base import get_customer_info_system
from app.customers.context import (
    age_conflict_note,
    assessed_loss_tolerance,
    prompt_section,
    tier_upgrade_note,
)
from app.customers.needs import get_needs
from app.db.models import Conversation, Message, PolicyDecisionLog, ToolCallLog
from app.db.session import get_session
from app.handoff.service import (
    STATUS_LABELS,
    active_handoff,
    handoff_view,
    latest_handoff,
)
from app.llm.breaker import get_breaker
from app.llm.client import (
    LLMNotConfiguredError,
    describe,
    get_chat_model,
    get_router_model,
    prices_are_defaults,
    provider_name,
)
from app.llm.fake import FakeChatModel
from app.llm.telemetry import TurnTelemetry
from app.ops.turns import TurnRecord, record_turn
from app.products.catalog import load_catalog
from app.reminders.service import reminded_codes

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
    if provider_name(settings) == "fake":
        logger.warning("LLM_PROVIDER=fake：使用压测用假模型，回答为固定内容")
        return build_graph(
            FakeChatModel(latency_seconds=settings.fake_llm_latency_seconds),
            FakeChatModel(reply="FINANCE_KNOWLEDGE", latency_seconds=0.2, completion_tokens=3),
            max_tool_calls=settings.agent_max_tool_calls,
        )
    logger.info("LLM: %s", describe(settings))
    if prices_are_defaults(settings):
        logger.warning(
            "费用估算仍使用默认（Kimi）单价：请在 .env 中设置 "
            "LLM_PRICE_INPUT_PER_MTOK / LLM_PRICE_OUTPUT_PER_MTOK"
        )
    return build_graph(
        get_chat_model(settings),
        # Topic routing is a simple classification: thinking off and a short output limit, about 0.7
        # s and a few tokens
        get_router_model(settings, max_tokens=ROUTER_MAX_TOKENS),
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
    user: CurrentUser = Depends(get_current_user),
    now: datetime = Depends(get_now),
    agent=Depends(get_agent),
):
    chat_limit(user)  # every call costs model credits: rate-limit per user
    started = time.perf_counter()
    breaker = get_breaker()
    if not breaker.allow():
        # Circuit open: don't call the model; tell the customer right away (no waiting for a
        # timeout); everything else still works
        record_turn(TurnRecord("BREAKER_OPEN", time.perf_counter() - started, current()))
        raise HTTPException(
            status_code=503,
            detail=localized(BREAKER_OPEN_REPLY),
            headers={"Retry-After": str(breaker.retry_after())},
        )
    conversation = _get_or_create_conversation(db, customer_id, req.conversation_id, req.message)
    # Commit the conversation first: tools (e.g. creating a handoff) write in their own transactions
    # and need it to exist
    db.commit()

    handoff = active_handoff(db, conversation.id)
    history = _load_history(db, conversation.id)
    base = get_customer_info_system().get(customer_id)
    catalog = load_catalog()
    reminders = [
        f"{p.name}（{p.code}）" if (p := catalog.get(code)) else code
        for code in sorted(reminded_codes(db, customer_id))
    ]
    customer_context = prompt_section(
        base,
        get_needs(db, customer_id),
        assessed_loss_tolerance(db, customer_id),
        reminders,
    )
    if handoff is not None:
        customer_context += (
            f"\n\n## 当前人工服务状态\n- {STATUS_LABELS[handoff.status]}"
            f"（{handoff.assigned_rm_name}）。如实描述该状态，不要重复生成请求。"
        )
    # Gate: recomputed from the database for every message; the LLM can't change it
    gate = evaluate_gate(latest_confirmed(db, customer_id), now)

    telemetry = TurnTelemetry()
    settings = get_settings()
    # End the read-only transaction before calling the model, returning the connection to the pool
    # while waiting for the reply.
    # Found in P8-4 load testing: every in-flight conversation used to hold a connection, so beyond
    # the pool size (5+10)
    # requests queued for connections and throughput stalled at about 7 req/s. Tools read and write
    # in their own sessions, not this transaction.
    db.commit()
    try:
        result = agent.invoke(
            {
                "messages": [*history, HumanMessage(req.message)],
                "customer_id": customer_id,
                "conversation_id": conversation.id,
                # Base profile (bank system, read-only) + current needs + human-service status:
                # rebuilt for every message
                "customer_context": customer_context,
                "permission": gate.permission,
                "risk_rating": gate.risk_rating,
                "gate_reasons": gate.reason_codes,
                "deadline": time.monotonic() + settings.chat_turn_budget_seconds,
                "policy_decisions": [
                    {
                        "checkpoint": "GATE",
                        "decision": gate.permission.value,
                        "reason_codes": gate.reason_codes,
                        "rule_version": gate.rule_version,
                    }
                ],
            },
            # Telemetry callback: latency and tokens of every model call in the graph are aggregated
            # into telemetry
            config={"callbacks": [telemetry]},
        )
    except Exception as exc:
        logger.exception("agent failed", extra={"conversation_id": conversation.id})
        # only failures of the model service count toward the breaker, not tool or business-code
        # exceptions
        if telemetry.errors:
            breaker.record_failure()
        record_turn(
            TurnRecord(
                "ERROR",
                time.perf_counter() - started,
                current(),
                conversation_id=conversation.id,
                permission=gate.permission.value,
            ),
            telemetry,
        )
        raise HTTPException(
            status_code=502,
            detail=L(
                "AI 服务暂时不可用，请稍后再试",
                "The AI service is temporarily unavailable. Please try again later.",
            ),
        ) from exc
    if telemetry.successes:
        breaker.record_success()
    # No notes are appended after fixed replies (fallback, tool limit, timeout)
    fixed = (SAFE_FALLBACK_REPLY, TOOL_LIMIT_REPLY, OUT_OF_SCOPE_REPLY, TURN_TIMEOUT_REPLY)
    fixed_reply = result["reply"] in {v for f in fixed for v in all_versions(f)}
    if not fixed_reply and (note := age_conflict_note(req.message, result["reply"], base)):
        # Put it at the start: age affects suitability, so the customer should first see that bank
        # records take precedence
        result["reply"] = f"> {note}\n\n{result['reply']}"
    # This turn may have just recorded an investment amount; re-read needs to decide on a
    # tier-upgrade note (at most once per conversation)
    history_text = "\n".join(str(m.content) for m in history)
    upgrade = tier_upgrade_note(base, get_needs(db, customer_id), result["reply"], history_text)
    if not fixed_reply and (note := upgrade):
        result["reply"] = f"{result['reply']}\n\n> {note}"

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
    record_turn(_turn_record(result, time.perf_counter() - started, conversation.id), telemetry)

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
    """Past conversations (latest 30), most recently active first."""
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
        raise HTTPException(status_code=404, detail=L("会话不存在", "Conversation not found"))
    return conversation


def _message_out(m: Message) -> MessageOut:
    return MessageOut(role=m.role, content=m.content, ui_blocks=m.ui_blocks or [])


def _get_or_create_conversation(
    db: Session, customer_id: str, conversation_id: str | None, first_message: str
) -> Conversation:
    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None or conversation.customer_id != customer_id:
            raise HTTPException(status_code=404, detail=L("会话不存在", "Conversation not found"))
        return conversation
    conversation = Conversation(customer_id=customer_id, title=first_message[:30])
    db.add(conversation)
    db.flush()
    return conversation


def _load_history(db: Session, conversation_id: str) -> list[BaseMessage]:
    """Replay only user and assistant text to the LLM; intermediate tool steps are not replayed,
    to limit tokens."""
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


REPLY_OUTCOMES = [
    (SAFE_FALLBACK_REPLY, "FALLBACK"),
    (TOOL_LIMIT_REPLY, "TOOL_LIMIT"),
    (TURN_TIMEOUT_REPLY, "TIMEOUT"),
    (OUT_OF_SCOPE_REPLY, "OUT_OF_SCOPE"),
    (ASSESSMENT_REQUIRED_REPLY, "ASSESSMENT_REQUIRED"),
]


def _turn_record(result: dict, latency_s: float, conversation_id: str) -> TurnRecord:
    """Summarize this turn's metrics: outcome, review decision and rules hit, tool success (no
    conversation content)."""
    reply = result["reply"]
    outcome = next(
        (o for text, o in REPLY_OUTCOMES if any(reply.startswith(v) for v in all_versions(text))),
        "ANSWERED",
    )
    output = [d for d in result["policy_decisions"] if d["checkpoint"] == "OUTPUT"]
    agent_ran = any(isinstance(m, AIMessage) for m in current_turn(result["messages"]))
    turn = current_turn(result["messages"])
    tools = [{"name": m.name, "status": m.status} for m in turn if isinstance(m, ToolMessage)]
    return TurnRecord(
        outcome=outcome,
        latency_s=latency_s,
        locale=current(),
        conversation_id=conversation_id,
        permission=result["permission"].value,
        intent=result.get("intent"),
        guard_decision=output[-1]["decision"] if output else ("PASS" if agent_ran else None),
        violation_codes=sorted(
            {c for d in output for c in d["reason_codes"] if not c.startswith("片段:")}
        ),
        tools=tools,
    )


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
