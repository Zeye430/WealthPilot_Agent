"""Purchase confirmation API (demo): preview checks → customer reads and confirms documents → demo
result; no order is placed.

Every step re-checks the rating, sale status, minimum amount and available balance on the server;
frontend button states are only hints.
"""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_customer_id
from app.api.products import customer_rating
from app.core.i18n import L
from app.customers.base import get_customer_info_system
from app.products.catalog import Product, load_catalog
from app.purchases.service import check_purchase, confirmation_view, demo_result, documents

router = APIRouter(prefix="/api/v1/purchases", tags=["purchases"])


class PurchaseRequest(BaseModel):
    product_code: str
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class ConfirmRequest(PurchaseRequest):
    acknowledged: list[str] = []  # documents the customer ticked as read


def _product(code: str) -> Product:
    product = load_catalog().get(code)
    if product is None:
        raise HTTPException(status_code=404, detail=L("产品不存在", "Product not found"))
    return product


def _available_balance(customer_id: str) -> Decimal:
    base = get_customer_info_system().get(customer_id)
    return base.assets_at_bank.demand_deposit if base else Decimal(0)


@router.post("/preview")
def preview(
    req: PurchaseRequest,
    customer_id: str = Depends(get_customer_id),
    rating: str | None = Depends(customer_rating),
):
    product = _product(req.product_code)
    check = check_purchase(product, req.amount, rating, _available_balance(customer_id))
    return confirmation_view(check, product)


@router.post("/confirm")
def confirm(
    req: ConfirmRequest,
    customer_id: str = Depends(get_customer_id),
    rating: str | None = Depends(customer_rating),
):
    product = _product(req.product_code)
    check = check_purchase(product, req.amount, rating, _available_balance(customer_id))
    if not check.allowed:
        raise HTTPException(status_code=409, detail=L("；", " ").join(check.errors))
    missing = [d["name"] for d in documents() if d["id"] not in req.acknowledged]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=L("请先阅读并确认：", "Please read and confirm: ") + L("、", ", ").join(missing),
        )
    return {
        "status": "DEMO_NOT_PLACED",
        "message": demo_result(),
        **confirmation_view(check, product),
        "confirmed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
