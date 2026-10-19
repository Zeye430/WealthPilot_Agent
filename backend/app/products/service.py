"""产品查询服务：LLM 工具和 REST API 共用，保证两条路径的过滤规则完全一致。"""

import re
from collections import Counter

from pydantic import BaseModel

from app.compliance.suitability import (
    NOT_ON_SALE,
    UNVERIFIED,
    CustomerContext,
    Eligibility,
    evaluate,
)
from app.products.catalog import Catalog, DataQuality, Product, ProductStatus, ProductType
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
        haystack = (
            f"{product.name}{product.issuer}{product.type_label}{product.investment_scope}"
            f"{product.name_en}{product.investment_scope_en}"
        ).lower()
        keyword = filters.keyword.lower()
        # 英文关键词忽略空格与标点（「1 Year」与「1-Year」视为相同）
        loose = re.sub(r"[^0-9a-z]", "", keyword) if re.search(r"[a-z]", keyword) else ""
        if keyword not in haystack and not (loose and loose in re.sub(r"[^0-9a-z]", "", haystack)):
            return False
    return True


class BrowseResult(BaseModel):
    ranked: list[RankedProduct]  # 可买入：评级范围内、在售且已核实，按排序
    other: list[tuple[Product, list[str]]]  # 仅可查看：附原因（超出评级、未测评、未核实等）


def browse(catalog: Catalog, rating: str | None, filters: SearchFilters) -> BrowseResult:
    """产品浏览页：展示全部在售产品（产品负责人决定，2026-10-18）。

    评级范围内的产品排在前面并参与排序；超出评级或未测评时只能查看条款，不能买入。
    与对话中的 search_products 不同：对话推荐只在评级范围内进行。
    """
    candidates, other = [], []
    for product in catalog.products:
        if product.status is not ProductStatus.ON_SALE or not _matches(product, filters):
            continue
        if rating is None:
            other.append((product, ["完成风险承受能力测评后可买入。"]))
            continue
        result = evaluate(product, CustomerContext(risk_rating=rating))
        if result.rankable:
            candidates.append(product)
        else:
            other.append((product, result.messages))
    if rating is None:
        # 未测评：按流动性和费用排序展示，不区分能否买入
        verified = [p for p, _ in other if p.data_quality is DataQuality.VERIFIED]
        order = {r.product.code: i for i, r in enumerate(rank(verified))}
        other.sort(key=lambda item: order.get(item[0].code, len(order)))
    return BrowseResult(ranked=rank(candidates), other=other)


def upcoming(catalog: Catalog, ctx: CustomerContext | None) -> list[Product]:
    """即将发售的新品。传入客户条件时，只返回评级、期限、起购金额都符合的（与在售产品同一套规则）。"""
    products = [p for p in catalog.products if p.status is ProductStatus.UPCOMING]
    if ctx is None:
        return products
    allowed = {NOT_ON_SALE, UNVERIFIED}  # 「尚未开售」本身不是不合格
    return [p for p in products if set(evaluate(p, ctx).reason_codes) <= allowed]


def search(catalog: Catalog, ctx: CustomerContext, filters: SearchFilters) -> SearchResult:
    """先按客户的查询条件筛选，再做适当性硬过滤，最后只对合格产品排序。"""
    candidates, unranked, excluded = [], [], Counter()
    for product in catalog.products:
        # 即将发售的新品单独返回（upcoming），不算作被排除
        if product.status is ProductStatus.UPCOMING or not _matches(product, filters):
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
