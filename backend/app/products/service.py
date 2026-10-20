"""Product query service shared by the LLM tools and the REST API, so both paths apply exactly
the same filters."""

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
    ranked: list[RankedProduct]  # eligible and verified, in rank order
    unranked: list[tuple[Product, Eligibility]]  # eligible but unverified: shown, not ranked
    excluded: dict[str, int]  # how many were excluded by suitability rules, by primary reason


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
        # English keywords ignore spaces and punctuation ("1 Year" and "1-Year" are the same)
        loose = re.sub(r"[^0-9a-z]", "", keyword) if re.search(r"[a-z]", keyword) else ""
        if keyword not in haystack and not (loose and loose in re.sub(r"[^0-9a-z]", "", haystack)):
            return False
    return True


class BrowseResult(BaseModel):
    ranked: list[RankedProduct]  # buyable: within the rating, on sale and verified, in rank order
    # view only, with reasons (above the rating, unassessed, unverified, etc.)
    other: list[tuple[Product, list[str]]]


def browse(catalog: Catalog, rating: str | None, filters: SearchFilters) -> BrowseResult:
    """Product browsing page: shows every product on sale (product-owner decision, 2026-10-18).

    Products within the rating come first and are ranked; above the rating or without an assessment,
    terms can be viewed but not bought.
    Unlike search_products in chat, where recommendations stay within the rating.
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
        # Unassessed: sort by liquidity and fees without separating buyable products
        verified = [p for p, _ in other if p.data_quality is DataQuality.VERIFIED]
        order = {r.product.code: i for i, r in enumerate(rank(verified))}
        other.sort(key=lambda item: order.get(item[0].code, len(order)))
    return BrowseResult(ranked=rank(candidates), other=other)


def upcoming(catalog: Catalog, ctx: CustomerContext | None) -> list[Product]:
    """Upcoming products. With customer criteria, only those matching rating, horizon and minimum
    amount (same rules as products on sale)."""
    products = [p for p in catalog.products if p.status is ProductStatus.UPCOMING]
    if ctx is None:
        return products
    allowed = {NOT_ON_SALE, UNVERIFIED}  # "not yet on sale" alone doesn't make it ineligible
    return [p for p in products if set(evaluate(p, ctx).reason_codes) <= allowed]


def search(catalog: Catalog, ctx: CustomerContext, filters: SearchFilters) -> SearchResult:
    """Filter by the customer's query first, then apply the suitability hard filter, then rank
    only eligible products."""
    candidates, unranked, excluded = [], [], Counter()
    for product in catalog.products:
        # Upcoming products are returned separately (upcoming), not counted as excluded
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
