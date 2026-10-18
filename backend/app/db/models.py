import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import get_settings

EMBEDDING_DIM = get_settings().embedding_dim


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    ui_blocks: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ToolCallLog(Base):
    """工具调用审计：记录调用了什么、是否成功、耗时，不记录完整对话内容。"""

    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(64))
    input: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))  # success | error
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RiskAssessment(Base):
    """风险测评记录。每次测评新增一行，不覆盖历史；评级只能由计分代码写入。"""

    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    questionnaire_version: Mapped[str] = mapped_column(String(16))
    answers: Mapped[dict] = mapped_column(JSONB)
    score: Mapped[int] = mapped_column(Integer)
    rating: Mapped[str] = mapped_column(String(4))
    vetoed: Mapped[bool] = mapped_column(Boolean)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    # PENDING_CONFIRMATION（待客户确认）| CONFIRMED（已生效）| SUPERSEDED（被重新作答取代）
    status: Mapped[str] = mapped_column(String(24))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PolicyDecisionLog(Base):
    """合规决策审计：哪个检查点、什么结论、依据哪个规则版本。"""

    __tablename__ = "policy_decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    checkpoint: Mapped[str] = mapped_column(String(16))  # GATE | ROUTER | TOOL | OUTPUT
    decision: Mapped[str] = mapped_column(String(48))
    reason_codes: Mapped[list] = mapped_column(JSONB, default=list)
    rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DocumentChunk(Base):
    """检索语料的向量索引。语料本身来自知识库与说明书文件，本表只是可重建的派生索引。"""

    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # K17 / ZA-F03#四
    kind: Mapped[str] = mapped_column(String(16), index=True)
    product_code: Mapped[str | None] = mapped_column(String(16), index=True)
    content_hash: Mapped[str] = mapped_column(String(16))
    embedding_model: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CustomerNeeds(Base):
    """本次需求：客户在对话或页面中提供的投资需求，叠加在只读的基础画像之上。"""

    __tablename__ = "customer_needs"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # {字段: {"value": ..., "source": "CONVERSATION" | "CUSTOMER_EDIT", "updated_at": ISO 时间}}
    fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Handoff(Base):
    """人工交接。状态只能由真实操作推进：客户点击同意、理财经理接单 / 回复 / 结束。"""

    __tablename__ = "handoffs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(24), index=True)
    summary: Mapped[dict] = mapped_column(JSONB)
    consent_scope: Mapped[list] = mapped_column(JSONB, default=list)
    assigned_rm_id: Mapped[str] = mapped_column(String(32), index=True)
    assigned_rm_name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HandoffEvent(Base):
    """交接状态变更留痕：谁、何时、从什么状态到什么状态。"""

    __tablename__ = "handoff_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    handoff_id: Mapped[str] = mapped_column(ForeignKey("handoffs.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(64))  # 客户 / 理财经理 ID / AI
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SaleReminder(Base):
    """新品开售提醒：只能由客户本人发起（点击「开售提醒我」或在对话中明确同意）。"""

    __tablename__ = "sale_reminders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    product_code: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16))  # BUTTON 界面按钮 | CHAT 对话中客户同意
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(Base):
    """登录账号：客户（关联客户编号）或理财经理（关联员工编号）。真实系统中对接银行统一身份认证。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16))  # customer | rm
    customer_id: Mapped[str | None] = mapped_column(String(64))
    rm_id: Mapped[str | None] = mapped_column(String(32))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuthSession(Base):
    """服务端会话：只保存令牌的 SHA-256，数据库泄露也无法直接冒用会话；可随时吊销。"""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(token)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
