import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
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
    """Tool-call audit: what was called, whether it succeeded and how long it took; no full
    conversation content."""

    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(64))
    input: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))  # success | error
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RiskAssessment(Base):
    """Risk assessment records. Each assessment adds a row and never overwrites history; ratings
    are written only by the scoring code."""

    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    questionnaire_version: Mapped[str] = mapped_column(String(16))
    answers: Mapped[dict] = mapped_column(JSONB)
    score: Mapped[int] = mapped_column(Integer)
    rating: Mapped[str] = mapped_column(String(4))
    vetoed: Mapped[bool] = mapped_column(Boolean)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    # PENDING_CONFIRMATION (awaiting customer confirmation) | CONFIRMED (in effect) | SUPERSEDED
    # (replaced by a new submission)
    status: Mapped[str] = mapped_column(String(24))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PolicyDecisionLog(Base):
    """Compliance decision audit: which checkpoint, what decision, under which rule version."""

    __tablename__ = "policy_decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    checkpoint: Mapped[str] = mapped_column(String(16))  # GATE | ROUTER | TOOL | OUTPUT
    decision: Mapped[str] = mapped_column(String(48))
    reason_codes: Mapped[list] = mapped_column(JSONB, default=list)
    rule_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DocumentChunk(Base):
    """Vector index for the search corpus. The corpus itself comes from knowledge-base and
    prospectus files; this table is a rebuildable derived index."""

    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # K17 / ZA-F03#<section>
    kind: Mapped[str] = mapped_column(String(16), index=True)
    product_code: Mapped[str | None] = mapped_column(String(16), index=True)
    content_hash: Mapped[str] = mapped_column(String(16))
    embedding_model: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CustomerNeeds(Base):
    """Current needs: investment needs the customer gives in chat or on a page, layered on top of
    the read-only base profile."""

    __tablename__ = "customer_needs"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # {field: {"value": ..., "source": "CONVERSATION" | "CUSTOMER_EDIT", "updated_at": ISO time}}
    fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Handoff(Base):
    """Handoff to a human. Status only advances through real actions: the customer agrees; the
    relationship manager accepts / replies / closes."""

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
    """Handoff status history: who changed it, when, and from which status to which."""

    __tablename__ = "handoff_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    handoff_id: Mapped[str] = mapped_column(ForeignKey("handoffs.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(64))  # customer / relationship manager ID / AI
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SaleReminder(Base):
    """New-product sale reminders: only the customer can create one (the "remind me" button or
    explicit agreement in chat)."""

    __tablename__ = "sale_reminders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    product_code: Mapped[str] = mapped_column(String(16))
    # BUTTON: UI button | CHAT: customer agreed in chat
    source: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(Base):
    """Sign-in accounts: customers (linked to a customer ID) or relationship managers (linked to
    an employee ID). A real system would use the bank's single sign-on."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16))  # customer | rm | ops
    customer_id: Mapped[str | None] = mapped_column(String(64))
    rm_id: Mapped[str | None] = mapped_column(String(32))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuthSession(Base):
    """Server-side sessions: only the token's SHA-256 is stored, so a database leak can't be used
    to hijack sessions; revocable at any time."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(token)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TurnMetric(Base):
    """Per-turn runtime metrics (P8-3): latency, model calls, token and cost estimates, tools,
    review outcome.

    Deliberately stores no conversation content or customer IDs: the ops dashboard shows aggregates
    only; to trace a specific issue, use request_id / conversation_id
    to join the access-controlled audit tables (policy_decisions, tool_calls).
    """

    __tablename__ = "turn_metrics"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    locale: Mapped[str] = mapped_column(String(4))
    permission: Mapped[str | None] = mapped_column(String(32))
    intent: Mapped[str | None] = mapped_column(String(32))
    # ANSWERED | OUT_OF_SCOPE | ASSESSMENT_REQUIRED | FALLBACK | TOOL_LIMIT | TIMEOUT
    # | ERROR (model or system error) | BREAKER_OPEN (circuit open, model not called)
    outcome: Mapped[str] = mapped_column(String(24), index=True)
    guard_decision: Mapped[str | None] = mapped_column(
        String(16)
    )  # PASS | REWRITE | REDACT | FALLBACK
    violation_codes: Mapped[list] = mapped_column(JSONB, default=list)
    latency_ms: Mapped[int] = mapped_column(Integer)
    llm_ms: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    llm_errors: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_errors: Mapped[int] = mapped_column(Integer, default=0)
    tools: Mapped[list] = mapped_column(JSONB, default=list)  # [{"name", "status"}]
    model: Mapped[str] = mapped_column(String(64), default="")


class UsedAppTicket(Base):
    """Used mobile banking entry tickets (one-time): reusing a ticket hits a primary-key conflict
    and counts as a replay.

    Expired records can be purged periodically (the tickets themselves already fail the expiry
    check).
    """

    __tablename__ = "used_app_tickets"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
