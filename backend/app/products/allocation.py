"""配置情景模拟：检查一组「产品 + 金额」的组合是否满足客户的硬约束。

刻意**不测算组合收益**：《银行保险机构资产管理产品信息披露管理办法》第八条禁止对实际投资业绩
进行预测。模拟只展示可确定的事实：构成比例、流动性、风险等级、固定费用，以及目标收益与
业绩比较基准上限的对比（事实对比，不是预测）。
"""

from decimal import Decimal

from pydantic import BaseModel

from app.compliance.suitability import CustomerContext, evaluate
from app.customers.needs import Needs
from app.products.catalog import Catalog, MetricType, Product
from app.products.presenter import format_money, format_rate, lockup_text

CASH_NAMES = {"活期存款", "活期", "现金", "存款", "CASH"}
CONCENTRATION_LIMIT = Decimal("0.5")
TOLERANCE = Decimal("1")  # 合计金额允许 1 元误差

OK, WARN, FAIL = "OK", "WARN", "FAIL"


class AllocationError(ValueError):
    pass


class Slice(BaseModel):
    code: str
    name: str
    amount: Decimal
    pct: Decimal
    risk_level: str | None
    lockup: str
    liquid: bool


class Check(BaseModel):
    status: str
    label: str
    message: str


class AllocationResult(BaseModel):
    slices: list[Slice]
    checks: list[Check]
    total: Decimal
    liquid_amount: Decimal
    annual_fee: Decimal | None

    @property
    def passed(self) -> bool:
        return all(c.status != FAIL for c in self.checks)


def simulate(
    items: list[tuple[str, Decimal]],
    catalog: Catalog,
    rating: str,
    needs: Needs,
    existing_liquid: Decimal | None = None,
) -> AllocationResult:
    if not 1 <= len(items) <= 8:
        raise AllocationError("请提供 1 到 8 个配置项")
    resolved: list[tuple[Product | None, Decimal]] = []
    for name, amount in items:
        if amount <= 0:
            raise AllocationError(f"「{name}」的金额必须大于 0")
        if name.strip() in CASH_NAMES:
            resolved.append((None, amount))
            continue
        product = catalog.find_by_name(name)
        if product is None:
            raise AllocationError(f"未找到产品「{name}」")
        resolved.append((product, amount))

    total = sum((a for _, a in resolved), Decimal(0))
    checks: list[Check] = []
    slices: list[Slice] = []
    horizon_days = round(needs.horizon_months * 365 / 12) if needs.horizon_months else None

    for product, amount in resolved:
        pct = amount / total
        if product is None:
            slices.append(
                Slice(
                    code="CASH",
                    name="活期存款",
                    amount=amount,
                    pct=pct,
                    risk_level=None,
                    lockup="随时支取",
                    liquid=True,
                )
            )
            continue
        slices.append(
            Slice(
                code=product.code,
                name=product.name,
                amount=amount,
                pct=pct,
                risk_level=product.effective_risk_level,
                lockup=lockup_text(product),
                liquid=product.lockup_days == 0,
            )
        )
        result = evaluate(
            product,
            CustomerContext(
                risk_rating=rating, investment_amount=amount, horizon_days=horizon_days
            ),
        )
        if not result.eligible:
            checks.append(
                Check(
                    status=FAIL, label=f"{product.name}不可配置", message="；".join(result.messages)
                )
            )

    if needs.investment_amount is not None and abs(total - needs.investment_amount) > TOLERANCE:
        checks.append(
            Check(
                status=FAIL,
                label="合计金额",
                message=f"组合合计 {format_money(total)}，与计划投资金额 "
                f"{format_money(needs.investment_amount)} 不一致",
            )
        )
    else:
        checks.append(
            Check(status=OK, label="合计金额", message=f"合计 {format_money(total)}，比例合计 100%")
        )

    liquid_amount = sum((s.amount for s in slices if s.liquid), Decimal(0))
    if needs.liquidity_reserve is not None:
        if liquid_amount >= needs.liquidity_reserve:
            checks.append(
                Check(
                    status=OK,
                    label="流动性",
                    message=f"可随时支取 {format_money(liquid_amount)}，满足随时可能动用的 "
                    f"{format_money(needs.liquidity_reserve)}",
                )
            )
        else:
            checks.append(
                Check(
                    status=FAIL,
                    label="流动性",
                    message=f"可随时支取仅 {format_money(liquid_amount)}，低于随时可能动用的 "
                    f"{format_money(needs.liquidity_reserve)}",
                )
            )

    for s in slices:
        if s.code != "CASH" and s.pct > CONCENTRATION_LIMIT:
            checks.append(
                Check(
                    status=WARN,
                    label="集中度",
                    message=f"{s.name}占比 {format_rate(s.pct)}，超过 50%，集中度较高",
                )
            )

    if needs.target_annual_return is not None:
        ceilings = [_yield_ceiling(p) for p, _ in resolved if p is not None]
        ceilings = [c for c in ceilings if c is not None]
        if ceilings and max(ceilings) < needs.target_annual_return:
            checks.append(
                Check(
                    status=WARN,
                    label="目标收益",
                    message=f"所选产品的收益指标上限最高为 {format_rate(max(ceilings))}，"
                    f"低于您的目标 {format_rate(needs.target_annual_return)}。"
                    "目标收益只是您的期望，不是承诺；业绩比较基准不是预期收益率，"
                    "在您的风险等级内，较低风险与较高收益通常难以兼得",
                )
            )

    fees = [(p.fees.annual_total, a) for p, a in resolved if p is not None]
    annual_fee = None
    if fees and all(f is not None for f, _ in fees):
        annual_fee = sum((f * a for f, a in fees), Decimal(0)).quantize(Decimal("0.01"))
        checks.append(
            Check(
                status=OK,
                label="固定费用",
                message=f"按年化固定费率估算，每年约 {format_money(annual_fee)}（已体现在净值中）",
            )
        )
    elif fees:
        checks.append(Check(status=WARN, label="固定费用", message="部分产品费用未核实，无法估算"))

    if existing_liquid:
        checks.append(
            Check(
                status=OK,
                label="在本行的其他资产",
                message=f"此外，您在本行还有可随时支取的资产约 {format_money(existing_liquid)}"
                "（来自银行系统记录，未计入本次配置）",
            )
        )

    return AllocationResult(
        slices=slices,
        checks=checks,
        total=total,
        liquid_amount=liquid_amount,
        annual_fee=annual_fee,
    )


def _yield_ceiling(product: Product) -> Decimal | None:
    """收益指标上限：业绩比较基准区间上限或七日年化；指数型基准无法给出数值，返回 None。"""
    if (m := product.metric(MetricType.PERFORMANCE_BENCHMARK)) and m.high is not None:
        return m.high
    if m := product.metric(MetricType.SEVEN_DAY_ANNUALIZED):
        return m.value
    return None
