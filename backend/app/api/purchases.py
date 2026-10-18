"""买入确认 API（演示）：预览校验 → 客户阅读并确认文件 → 返回演示结果，不下单。

每一步都在服务端重新校验评级、在售状态、起购金额和可用余额，前端按钮状态只是提示。
"""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_customer_id
from app.api.products import customer_rating
from app.customers.base import get_customer_info_system
from app.products.catalog import Product, load_catalog
from app.purchases.service import DEMO_RESULT, DOCUMENTS, check_purchase, confirmation_view

router = APIRouter(prefix="/api/v1/purchases", tags=["purchases"])


class PurchaseRequest(BaseModel):
    product_code: str
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class ConfirmRequest(PurchaseRequest):
    acknowledged: list[str] = []  # 客户勾选「已阅读」的文件


def _product(code: str) -> Product:
    product = load_catalog().get(code)
    if product is None:
        raise HTTPException(status_code=404, detail="产品不存在")
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
        raise HTTPException(status_code=409, detail="；".join(check.errors))
    missing = [d["name"] for d in DOCUMENTS if d["id"] not in req.acknowledged]
    if missing:
        raise HTTPException(status_code=422, detail=f"请先阅读并确认：{'、'.join(missing)}")
    return {
        "status": "DEMO_NOT_PLACED",
        "message": DEMO_RESULT,
        **confirmation_view(check, product),
        "confirmed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
