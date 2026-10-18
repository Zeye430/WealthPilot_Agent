"""新品开售提醒：客户本人预约，开售后由客户本人买入。

规则（产品负责人确认，2026-10-18）：
- 只能预约「即将发售」且在客户风险等级范围内的产品；未测评不能预约（开售后也无法买入）。
- 提醒只由客户发起：界面按钮，或客户在对话中明确同意后由 AI 代为设置。
- 提醒不等于购买：开售后客户仍需本人确认买入，买入时照常校验。
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessment.scoring import rating_allows
from app.db.models import SaleReminder
from app.products import presenter
from app.products.catalog import Product, ProductStatus, load_catalog

BUTTON = "BUTTON"
CHAT = "CHAT"
DELIVERY_NOTE = "开售当天将通过短信和 App 推送提醒您（演示环境不发送）。"


class ReminderError(ValueError):
    pass


def check_remindable(product: Product, rating: str | None) -> None:
    if product.status is not ProductStatus.UPCOMING:
        raise ReminderError(f"{product.name}不是即将发售的新品，无需预约提醒。")
    if rating is None:
        raise ReminderError("请先完成风险承受能力测评，测评有效后才能预约和买入新品。")
    if not rating_allows(rating, product.effective_risk_level):
        raise ReminderError(
            f"{product.name}风险等级为 {product.effective_risk_level}，"
            "超出您的风险承受能力，无法预约。"
        )


def active_reminders(db: Session, customer_id: str) -> list[SaleReminder]:
    return list(
        db.scalars(
            select(SaleReminder)
            .where(SaleReminder.customer_id == customer_id, SaleReminder.cancelled_at.is_(None))
            .order_by(SaleReminder.created_at)
        )
    )


def reminded_codes(db: Session, customer_id: str) -> set[str]:
    return {r.product_code for r in active_reminders(db, customer_id)}


def create_reminder(
    db: Session, customer_id: str, product: Product, rating: str | None, source: str, now: datetime
) -> SaleReminder:
    """同一产品已有提醒时直接返回，不重复创建。"""
    check_remindable(product, rating)
    for r in active_reminders(db, customer_id):
        if r.product_code == product.code:
            return r
    reminder = SaleReminder(
        customer_id=customer_id, product_code=product.code, source=source, created_at=now
    )
    db.add(reminder)
    db.flush()
    return reminder


def cancel_reminder(db: Session, customer_id: str, reminder_id: str, now: datetime) -> None:
    reminder = db.get(SaleReminder, reminder_id)
    if reminder is None or reminder.customer_id != customer_id or reminder.cancelled_at:
        raise ReminderError("提醒不存在或已取消。")
    reminder.cancelled_at = now


def reminder_view(reminder: SaleReminder) -> dict:
    product = load_catalog().get(reminder.product_code)
    return {
        "id": reminder.id,
        "product": presenter.card(product) if product else {"code": reminder.product_code},
        "created_at": reminder.created_at,
        "delivery_note": DELIVERY_NOTE,
    }
