"""Current needs: investment needs the customer gives in chat (amount, horizon, liquidity reserve,
target return, etc.).

Stored separately from the base profile: the base profile comes from the bank system and is
read-only; current needs can be added or changed by the customer at any time,
with the source and update time recorded for each field.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.i18n import L
from app.db.models import CustomerNeeds
from app.products.presenter import format_money, format_rate

CONVERSATION = "CONVERSATION"  # given in chat
CUSTOMER_EDIT = "CUSTOMER_EDIT"  # edited by the customer on a page
SOURCE_LABELS = {CONVERSATION: "对话中提供", CUSTOMER_EDIT: "客户修改"}
SOURCE_LABELS_EN = {CONVERSATION: "From chat", CUSTOMER_EDIT: "Edited by you"}

FIELD_LABELS = {
    "investment_amount": "计划投资金额",
    "horizon_months": "投资期限",
    "liquidity_reserve": "随时可能动用的金额",
    "target_annual_return": "目标年化收益",
    "max_acceptable_loss": "可接受的最大亏损",
    "goal": "投资目的",
}
FIELD_LABELS_EN = {
    "investment_amount": "Amount to invest",
    "horizon_months": "Time horizon",
    "liquidity_reserve": "Cash you may need anytime",
    "target_annual_return": "Target annual return",
    "max_acceptable_loss": "Largest acceptable loss",
    "goal": "Goal",
}


def field_label(name: str) -> str:
    return L(FIELD_LABELS[name], FIELD_LABELS_EN[name])


class NeedsError(ValueError):
    pass


class NeedsUpdate(BaseModel):
    investment_amount: Decimal | None = None
    horizon_months: int | None = None
    liquidity_reserve: Decimal | None = None
    target_annual_return: Decimal | None = None
    max_acceptable_loss: Decimal | None = None
    goal: str | None = None

    def provided(self) -> dict:
        return self.model_dump(exclude_none=True)


class Needs(BaseModel):
    """Typed view of current needs; fields not provided are None."""

    investment_amount: Decimal | None = None
    horizon_months: int | None = None
    liquidity_reserve: Decimal | None = None
    target_annual_return: Decimal | None = None
    max_acceptable_loss: Decimal | None = None
    goal: str | None = None
    sources: dict[str, str] = {}

    def display(self) -> list[dict]:
        rows = []
        for name in FIELD_LABELS:
            value = getattr(self, name)
            source = self.sources.get(name, "")
            rows.append(
                {
                    "field": name,
                    "label": field_label(name),
                    "value": _format(name, value),
                    "source": L(SOURCE_LABELS.get(source), SOURCE_LABELS_EN.get(source)),
                }
            )
        return rows


def _format(name: str, value) -> str | None:
    if value is None:
        return None
    if name in ("investment_amount", "liquidity_reserve"):
        return format_money(Decimal(value))
    if name in ("target_annual_return", "max_acceptable_loss"):
        return format_rate(Decimal(value))
    if name == "horizon_months":
        return L(f"{value} 个月", f"{value} months")
    return str(value)


def get_needs(db: Session, customer_id: str) -> Needs:
    row = db.get(CustomerNeeds, customer_id)
    return get_needs_from_fields(row.fields) if row else Needs()


def update_needs(
    db: Session, customer_id: str, update: NeedsUpdate, source: str, now: datetime
) -> Needs:
    provided = update.provided()
    if not provided:
        raise NeedsError(L("没有提供需要记录的需求信息。", "No goal details were provided."))
    for name in ("investment_amount", "liquidity_reserve"):
        if name in provided and provided[name] < 0:
            raise NeedsError(
                L(f"{FIELD_LABELS[name]}不能为负数", f"{FIELD_LABELS_EN[name]} can't be negative")
            )
    for name in ("target_annual_return", "max_acceptable_loss"):
        if name in provided and not Decimal(0) <= provided[name] <= Decimal(1):
            raise NeedsError(
                L(
                    f"{FIELD_LABELS[name]}应为小数形式（5% 写作 0.05）",
                    f"{FIELD_LABELS_EN[name]} must be a decimal (5% is 0.05)",
                )
            )
    if "horizon_months" in provided and not 0 < provided["horizon_months"] <= 600:
        raise NeedsError(
            L("投资期限应在 1 到 600 个月之间", "Time horizon must be 1 to 600 months")
        )

    row = db.get(CustomerNeeds, customer_id) or CustomerNeeds(customer_id=customer_id, fields={})
    fields = dict(row.fields)
    for name, value in provided.items():
        fields[name] = {
            "value": str(value) if isinstance(value, Decimal) else value,
            "source": source,
            "updated_at": now.isoformat(),
        }
    merged = get_needs_from_fields(fields)
    if (
        merged.investment_amount is not None
        and merged.liquidity_reserve is not None
        and merged.liquidity_reserve > merged.investment_amount
    ):
        raise NeedsError(
            L(
                "随时可能动用的金额不能超过计划投资金额",
                "Cash you may need anytime can't exceed the amount to invest",
            )
        )
    row.fields = fields
    row.updated_at = now
    db.merge(row)
    db.flush()
    return merged


def get_needs_from_fields(fields: dict) -> Needs:
    return Needs(
        **{k: v["value"] for k, v in fields.items()},
        sources={k: v["source"] for k, v in fields.items()},
    )
