"""Product browsing API: every product on sale can be viewed; whether it can be bought is decided in
code.

Shares the suitability rules with the LLM tools: a product above the rating can't be bought from any
entry point (S11).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_customer_id, get_now
from app.assessment.scoring import load_questionnaire
from app.assessment.service import latest_confirmed
from app.compliance.policy import Permission, evaluate_gate
from app.compliance.suitability import CustomerContext, evaluate
from app.core.i18n import L
from app.db.session import get_session
from app.products import presenter
from app.products.catalog import ProductStatus, ProductType, load_catalog
from app.products.service import SearchFilters, browse, upcoming
from app.purchases.service import blocking_reasons
from app.reminders.service import ReminderError, check_remindable, reminded_codes

router = APIRouter(prefix="/api/v1/products", tags=["products"])


def customer_rating(
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    now: datetime = Depends(get_now),
) -> str | None:
    """Rating from a valid assessment; None if unassessed or expired (browsing still works,
    buying doesn't)."""
    gate = evaluate_gate(latest_confirmed(db, customer_id), now)
    return gate.risk_rating if gate.permission is Permission.ASSESSED else None


def _remind_state(product, rating: str | None, reminded: set[str]) -> dict:
    try:
        check_remindable(product, rating)
        return {
            "allowed": True,
            "reminded": product.code in reminded,
            "reason": None,
            "needs_assessment": False,
        }
    except ReminderError as exc:
        return {
            "allowed": False,
            "reminded": False,
            "reason": str(exc),
            "needs_assessment": rating is None and product.status is ProductStatus.UPCOMING,
        }


@router.get("")
def list_products(
    product_type: list[ProductType] | None = Query(default=None),
    max_lockup_days: int | None = None,
    rating: str | None = Depends(customer_rating),
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
):
    """All products on sale. Buyable ones first; those above the rating or blocked by a missing
    assessment are labeled and view-only. Upcoming products listed separately."""
    catalog = load_catalog()
    reminded = reminded_codes(db, customer_id)
    result = browse(
        catalog, rating, SearchFilters(product_types=product_type, max_lockup_days=max_lockup_days)
    )
    band = load_questionnaire().band(rating) if rating else None
    return {
        "catalog_version": catalog.catalog_version,
        "rating": {
            "code": band.rating,
            "name": band.display_name,
            "max_product_risk": band.max_product_risk,
        }
        if band
        else None,
        "items": [
            {
                **presenter.card(r.product),
                "purchasable": True,
                "rank": i + 1,
                "highlights": r.highlights(),
            }
            for i, r in enumerate(result.ranked)
        ]
        + [
            {
                **presenter.card(p),
                "purchasable": not blocking_reasons(p, rating),
                "rank": None,
                "warnings": messages,
            }
            for p, messages in result.other
        ],
        "upcoming": [
            {**presenter.card(p), "remind": _remind_state(p, rating, reminded)}
            for p in upcoming(catalog, None)
            if not product_type or p.product_type in product_type
        ],
        "ranking_note": L(
            "排序依据：流动性、费用；不按收益排序。",
            "Ranked by liquidity and fees, never by returns.",
        ),
    }


@router.get("/{code}")
def product_detail(
    code: str,
    rating: str | None = Depends(customer_rating),
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
):
    """Product details are open to every customer (objective terms); whether it can be bought is
    decided in code, with the reason."""
    product = load_catalog().get(code)
    if product is None:
        raise HTTPException(status_code=404, detail=L("产品不存在", "Product not found"))
    blocked = blocking_reasons(product, rating)
    eligibility = evaluate(product, CustomerContext(risk_rating=rating)) if rating else None
    return {
        **presenter.detail(product),
        "eligible": eligibility.eligible if eligibility else False,
        "eligibility_messages": eligibility.messages if eligibility else [],
        "purchase": {
            "allowed": not blocked,
            "reasons": blocked,
            "needs_assessment": rating is None,
        },
        "remind": _remind_state(product, rating, reminded_codes(db, customer_id))
        if product.status is ProductStatus.UPCOMING
        else None,
    }
