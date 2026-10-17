"""本次需求：客户在对话中提供的投资需求（金额、期限、流动性储备、目标收益等）。

与基础画像分开存放：基础画像来自银行系统、只读；本次需求可由客户随时补充或修改，
每个字段记录来源与更新时间。
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import CustomerNeeds
from app.products.presenter import format_money, format_rate

CONVERSATION = "CONVERSATION"  # 对话中提供
CUSTOMER_EDIT = "CUSTOMER_EDIT"  # 客户在页面修改
SOURCE_LABELS = {CONVERSATION: "对话中提供", CUSTOMER_EDIT: "客户修改"}

FIELD_LABELS = {
    "investment_amount": "计划投资金额",
    "horizon_months": "投资期限",
    "liquidity_reserve": "随时可能动用的金额",
    "target_annual_return": "目标年化收益",
    "max_acceptable_loss": "可接受的最大亏损",
    "goal": "投资目的",
}


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
    """当前需求的类型化视图；未提供的字段为 None。"""

    investment_amount: Decimal | None = None
    horizon_months: int | None = None
    liquidity_reserve: Decimal | None = None
    target_annual_return: Decimal | None = None
    max_acceptable_loss: Decimal | None = None
    goal: str | None = None
    sources: dict[str, str] = {}

    def display(self) -> list[dict]:
        rows = []
        for name, label in FIELD_LABELS.items():
            value = getattr(self, name)
            rows.append(
                {
                    "field": name,
                    "label": label,
                    "value": _format(name, value),
                    "source": SOURCE_LABELS.get(self.sources.get(name, "")),
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
        return f"{value} 个月"
    return str(value)


def get_needs(db: Session, customer_id: str) -> Needs:
    row = db.get(CustomerNeeds, customer_id)
    return get_needs_from_fields(row.fields) if row else Needs()


def update_needs(
    db: Session, customer_id: str, update: NeedsUpdate, source: str, now: datetime
) -> Needs:
    provided = update.provided()
    if not provided:
        raise NeedsError("没有提供需要记录的需求信息。")
    for name in ("investment_amount", "liquidity_reserve"):
        if name in provided and provided[name] < 0:
            raise NeedsError(f"{FIELD_LABELS[name]}不能为负数")
    for name in ("target_annual_return", "max_acceptable_loss"):
        if name in provided and not Decimal(0) <= provided[name] <= Decimal(1):
            raise NeedsError(f"{FIELD_LABELS[name]}应为小数形式（5% 写作 0.05）")
    if "horizon_months" in provided and not 0 < provided["horizon_months"] <= 600:
        raise NeedsError("投资期限应在 1 到 600 个月之间")

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
        raise NeedsError("随时可能动用的金额不能超过计划投资金额")
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
