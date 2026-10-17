"""产品查询服务：LLM 工具和 REST API 共用，保证两条路径的过滤规则完全一致。"""

from collections import Counter

from pydantic import BaseModel

from app.compliance.suitability import CustomerContext, Eligibility, evaluate
from app.products.catalog import Catalog, Product, ProductType
from app.products.ranking import RankedProduct, rank


class SearchFilters(BaseModel):
    product_types: list[ProductType] | None = None
    max_lockup_days: int | None = None
    keyword: str | None = None


class SearchResult(BaseModel):
    ranked: list[RankedProduct]  # 合格且已核实，按排序
    unranked: list[tuple[Product, Eligibility]]  # 合格但数据未核实，展示但不排序
    excluded: dict[str, int]  # 被适当性规则排除的数量，按首要原因统计


def _matches(product: Product, filters: SearchFilters) -> bool:
    if filters.product_types and product.product_type not in filters.product_types:
        return False
    if filters.max_lockup_days is not None and product.lockup_days > filters.max_lockup_days:
        return False
    if filters.keyword:
        haystack = f"{product.name}{product.issuer}{product.type_label}{product.investment_scope}"
        if filters.keyword not in haystack:
            return False
    return True


def search(catalog: Catalog, ctx: CustomerContext, filters: SearchFilters) -> SearchResult:
    """先按客户的查询条件筛选，再做适当性硬过滤，最后只对合格产品排序。"""
    candidates, unranked, excluded = [], [], Counter()
    for product in catalog.products:
        if not _matches(product, filters):
            continue
        result = evaluate(product, ctx)
        if not result.eligible:
            excluded[result.reason_codes[0]] += 1
        elif result.rankable:
            candidates.append(product)
        else:
            unranked.append((product, result))
    return SearchResult(
        ranked=rank(candidates, ctx.horizon_days),
        unranked=unranked,
        excluded=dict(excluded),
    )
