import logging

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.graph import build_graph, current_turn
from app.core.config import get_settings
from app.db.models import Conversation, Message, ToolCallLog
from app.db.session import get_session
from app.llm.client import LLMNotConfiguredError, get_chat_model

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])

HISTORY_LIMIT = 20
DEMO_CUSTOMER_ID = "demo_customer_1"  # Phase 2 改为按 X-Demo-User 识别


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)


class ChatReply(BaseModel):
    content: str
    ui_blocks: list[dict]


class ChatResponse(BaseModel):
    conversation_id: str
    reply: ChatReply


class MessageOut(BaseModel):
    role: str
    content: str
    ui_blocks: list[dict]


class ConversationOut(BaseModel):
    id: str
    title: str | None
    messages: list[MessageOut]


def get_agent():
    settings = get_settings()
    try:
        model = get_chat_model(settings)
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return build_graph(model, max_tool_calls=settings.agent_max_tool_calls)


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_session), agent=Depends(get_agent)):
    conversation = _get_or_create_conversation(db, req.conversation_id, req.message)
    history = _load_history(db, conversation.id)

    try:
        result = agent.invoke({"messages": [*history, HumanMessage(req.message)]})
    except Exception as exc:
        logger.exception("agent failed", extra={"conversation_id": conversation.id})
        raise HTTPException(status_code=502, detail="AI 服务暂时不可用，请稍后再试") from exc

    db.add(Message(conversation_id=conversation.id, role="user", content=req.message))
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=result["reply"],
            ui_blocks=result["ui_blocks"],
        )
    )
    _log_tool_calls(db, conversation.id, current_turn(result["messages"]))
    db.commit()

    return ChatResponse(
        conversation_id=conversation.id,
        reply=ChatReply(content=result["reply"], ui_blocks=result["ui_blocks"]),
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(conversation_id: str, db: Session = Depends(get_session)):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.customer_id != DEMO_CUSTOMER_ID:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        messages=[
            MessageOut(role=m.role, content=m.content, ui_blocks=m.ui_blocks)
            for m in conversation.messages
        ],
    )


def _get_or_create_conversation(db: Session, conversation_id: str | None, first_message: str):
    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None or conversation.customer_id != DEMO_CUSTOMER_ID:
            raise HTTPException(status_code=404, detail="会话不存在")
        return conversation
    conversation = Conversation(customer_id=DEMO_CUSTOMER_ID, title=first_message[:30])
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
        HumanMessage(m.content) if m.role == "user" else AIMessage(m.content)
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
