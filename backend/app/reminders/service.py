"""New-product sale reminders: set by the customer; after launch, the customer buys.

Rules (confirmed by the product owner, 2026-10-18):
- Only upcoming products within the customer's risk level can be reserved; not without an assessment
(they couldn't be bought at launch either).
- Only the customer creates reminders: the UI button, or the AI sets one after the customer
explicitly agrees in chat.
- A reminder isn't a purchase: at launch the customer must still confirm the purchase, with the
usual checks.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessment.scoring import rating_allows
from app.core.i18n import L
from app.db.models import SaleReminder
from app.products import presenter
from app.products.catalog import Product, ProductStatus, load_catalog

BUTTON = "BUTTON"
CHAT = "CHAT"


def delivery_note() -> str:
    return L(
        "开售当天将通过短信和 App 推送提醒您（演示环境不发送）。",
        "We'll remind you by SMS and app notification on the opening day (not sent in this demo).",
    )


class ReminderError(ValueError):
    pass


def check_remindable(product: Product, rating: str | None) -> None:
    if product.status is not ProductStatus.UPCOMING:
        raise ReminderError(
            L(
                f"{product.name}不是即将发售的新品，无需预约提醒。",
                f"{product.name_en} isn't an upcoming product, so no reminder is needed.",
            )
        )
    if rating is None:
        raise ReminderError(
            L(
                "请先完成风险承受能力测评，测评有效后才能预约和买入新品。",
                "Complete your risk tolerance profile first. Once it's valid you can set "
                "reminders and buy new products.",
            )
        )
    if not rating_allows(rating, product.effective_risk_level):
        raise ReminderError(
            L(
                f"{product.name}风险等级为 {product.effective_risk_level}，"
                "超出您的风险承受能力，无法预约。",
                f"{product.name_en} is rated {product.effective_risk_level}, above your risk "
                "tolerance, so you can't set a reminder.",
            )
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
    """If the product already has a reminder, return it instead of creating another."""
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
        raise ReminderError(
            L("提醒不存在或已取消。", "This reminder doesn't exist or was already cancelled.")
        )
    reminder.cancelled_at = now


def reminder_view(reminder: SaleReminder) -> dict:
    product = load_catalog().get(reminder.product_code)
    return {
        "id": reminder.id,
        "product": presenter.card(product) if product else {"code": reminder.product_code},
        "created_at": reminder.created_at,
        "delivery_note": delivery_note(),
    }
