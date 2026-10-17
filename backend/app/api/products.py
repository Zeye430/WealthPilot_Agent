"""产品浏览 API。

与 LLM 工具共用同一套服务与适当性规则：绕过 Agent 直接调用接口，也绕不过过滤（S11）。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_customer_id, get_now
from app.assessment.scoring import load_questionnaire
from app.assessment.service import latest_confirmed
from app.compliance.policy import Permission, evaluate_gate
from app.compliance.suitability import REASON_LABELS, CustomerContext, evaluate
from app.db.session import get_session
from app.products import presenter
from app.products.catalog import ProductType, load_catalog
from app.products.service import SearchFilters, search

router = APIRouter(prefix="/api/v1/products", tags=["products"])


def assessed_context(
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    now: datetime = Depends(get_now),
) -> CustomerContext:
    gate = evaluate_gate(latest_confirmed(db, customer_id), now)
    if gate.permission is not Permission.ASSESSED:
        raise HTTPException(status_code=403, detail="请先完成风险承受能力测评，再查看产品。")
    return CustomerContext(risk_rating=gate.risk_rating)


@router.get("")
def list_products(
    product_type: list[ProductType] | None = Query(default=None),
    max_lockup_days: int | None = None,
    ctx: CustomerContext = Depends(assessed_context),
):
    catalog = load_catalog()
    result = search(
        catalog, ctx, SearchFilters(product_types=product_type, max_lockup_days=max_lockup_days)
    )
    band = load_questionnaire().band(ctx.risk_rating)
    return {
        "catalog_version": catalog.catalog_version,
        "rating": {
            "code": ctx.risk_rating,
            "name": band.name,
            "max_product_risk": band.max_product_risk,
        },
        "items": [
            {**presenter.card(r.product), "rank": i + 1, "rank_factors": r.explanation()}
            for i, r in enumerate(result.ranked)
        ]
        + [{**presenter.card(p), "rank": None, "warnings": e.messages} for p, e in result.unranked],
        "excluded": [{"reason": REASON_LABELS[c], "count": n} for c, n in result.excluded.items()],
        "ranking_note": "排序依据：期限匹配、流动性、费用；不按收益排序。",
    }


@router.get("/{code}")
def product_detail(code: str, ctx: CustomerContext = Depends(assessed_context)):
    product = load_catalog().get(code)
    if product is None:
        raise HTTPException(status_code=404, detail="产品不存在")
    eligibility = evaluate(product, ctx)
    return {
        **presenter.detail(product),
        "eligible": eligibility.eligible,
        "eligibility_messages": eligibility.messages,
    }
