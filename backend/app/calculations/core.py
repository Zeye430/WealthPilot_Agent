"""确定性金融计算。

约定：
- 输入输出均为 Decimal；中间过程保持全精度，只在对外输出时四舍五入到分（ROUND_HALF_UP）。
- 利率一律为小数形式（5% 写作 0.05），按年化给出。
- 本模块不依赖 LLM，也不做任何适当性判断。
"""

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

CENT = Decimal("0.01")
ZERO = Decimal("0")
ONE = Decimal("1")

MAX_YEARS = 100
MAX_ANNUAL_RATE = Decimal("1")  # 100%，超过视为输入错误（常见原因：把 5% 写成 5）
ALLOWED_PERIODS_PER_YEAR = {1, 2, 4, 12, 365}


class CalculationError(ValueError):
    """输入不合法。错误信息会原样返回给 LLM，用于修正参数，因此用中文写清原因。"""


class FeeMethod(StrEnum):
    EXTERNAL = "external"  # 外扣法：净申购金额 = 申购金额 / (1 + 费率)
    INTERNAL = "internal"  # 内扣法：申购费 = 申购金额 × 费率


def to_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


# ---------- 参数校验 ----------


def _check_amount(value: Decimal, name: str) -> None:
    if value < ZERO:
        raise CalculationError(f"{name}不能为负数，收到 {value}")


def _check_rate(rate: Decimal, name: str = "年化收益率") -> None:
    if rate <= -ONE:
        raise CalculationError(f"{name}必须大于 -100%，收到 {rate}")
    if rate > MAX_ANNUAL_RATE:
        raise CalculationError(
            f"{name}应为小数形式（5% 写作 0.05），收到 {rate}，超过 100% 视为输入错误"
        )


def _check_fee_rate(rate: Decimal, name: str) -> None:
    if rate < ZERO or rate >= ONE:
        raise CalculationError(f"{name}应在 0 到 1 之间（0.3% 写作 0.003），收到 {rate}")


def _check_years(years: int) -> None:
    if years < 0 or years > MAX_YEARS:
        raise CalculationError(f"年数应在 0 到 {MAX_YEARS} 之间，收到 {years}")


def _check_periods(periods_per_year: int) -> None:
    if periods_per_year not in ALLOWED_PERIODS_PER_YEAR:
        allowed = sorted(ALLOWED_PERIODS_PER_YEAR)
        raise CalculationError(f"每年计息次数只支持 {allowed}，收到 {periods_per_year}")


# ---------- 增长类 ----------


def compound_future_value(
    principal: Decimal, annual_rate: Decimal, years: int, periods_per_year: int = 1
) -> Decimal:
    """复利终值：FV = PV × (1 + r/m)^(m·n)。"""
    _check_amount(principal, "本金")
    _check_rate(annual_rate)
    _check_years(years)
    _check_periods(periods_per_year)
    m = Decimal(periods_per_year)
    return principal * (ONE + annual_rate / m) ** (periods_per_year * years)


def present_value(
    future_value: Decimal, annual_rate: Decimal, years: int, periods_per_year: int = 1
) -> Decimal:
    """复利现值：PV = FV / (1 + r/m)^(m·n)。"""
    _check_amount(future_value, "终值")
    _check_rate(annual_rate)
    _check_years(years)
    _check_periods(periods_per_year)
    m = Decimal(periods_per_year)
    return future_value / (ONE + annual_rate / m) ** (periods_per_year * years)


def simple_interest(principal: Decimal, annual_rate: Decimal, years: int) -> Decimal:
    """单利利息：I = PV × r × n。"""
    _check_amount(principal, "本金")
    _check_rate(annual_rate)
    _check_years(years)
    return principal * annual_rate * years


def periodic_investment_future_value(
    payment: Decimal,
    annual_rate: Decimal,
    years: int,
    periods_per_year: int = 12,
    at_period_start: bool = False,
) -> Decimal:
    """定期定额投资终值（年金终值）。

    期末投入：FV = P × [(1+i)^N − 1] / i；期初投入再乘 (1+i)。i = r/m，N = m·n。
    """
    _check_amount(payment, "每期投入")
    _check_rate(annual_rate)
    _check_years(years)
    _check_periods(periods_per_year)
    n = periods_per_year * years
    i = annual_rate / Decimal(periods_per_year)
    if i == ZERO:
        fv = payment * n
    else:
        fv = payment * ((ONE + i) ** n - ONE) / i
    if at_period_start:
        fv *= ONE + i
    return fv


def inflation_adjusted_value(nominal: Decimal, inflation_rate: Decimal, years: int) -> Decimal:
    """以今天的购买力衡量未来金额：Real = Nominal / (1 + π)^n。"""
    _check_amount(nominal, "名义金额")
    _check_rate(inflation_rate, "通胀率")
    _check_years(years)
    return nominal / (ONE + inflation_rate) ** years


def growth_path(
    principal: Decimal,
    annual_rate: Decimal,
    years: int,
    periods_per_year: int = 1,
    periodic_payment: Decimal = ZERO,
) -> list[Decimal]:
    """逐年期末余额（含第 0 年），用于画图。定投按期末投入。"""
    _check_amount(principal, "本金")
    _check_amount(periodic_payment, "每期投入")
    _check_rate(annual_rate)
    _check_years(years)
    _check_periods(periods_per_year)
    i = annual_rate / Decimal(periods_per_year)
    balance = principal
    path = [balance]
    for _ in range(years):
        for _ in range(periods_per_year):
            balance = balance * (ONE + i) + periodic_payment
        path.append(balance)
    return path


# ---------- 费用类 ----------


def subscription_fee(
    amount: Decimal, fee_rate: Decimal, method: FeeMethod = FeeMethod.EXTERNAL
) -> tuple[Decimal, Decimal]:
    """申购费。返回 (费用, 净申购金额)，均已四舍五入到分。"""
    _check_amount(amount, "申购金额")
    _check_fee_rate(fee_rate, "申购费率")
    if method is FeeMethod.EXTERNAL:
        net = to_cents(amount / (ONE + fee_rate))
    else:
        net = to_cents(amount - amount * fee_rate)
    return amount - net, net


def redemption_fee_rate(holding_days: int, tiers: list[tuple[int | None, Decimal]]) -> Decimal:
    """按持有天数选取赎回费率。

    tiers 形如 [(7, 0.015), (30, 0.005), (None, 0)]，含义：持有 <7 天 1.5%，
    7–29 天 0.5%，≥30 天 0。需按天数上限升序排列，最后一档上限为 None。
    """
    if holding_days < 0:
        raise CalculationError(f"持有天数不能为负数，收到 {holding_days}")
    if not tiers or tiers[-1][0] is not None:
        raise CalculationError("赎回费率分档的最后一档上限必须为 None（表示无上限）")
    for max_days, rate in tiers:
        _check_fee_rate(rate, "赎回费率")
        if max_days is None or holding_days < max_days:
            return rate
    raise AssertionError("unreachable")


def redemption_fee(redemption_amount: Decimal, fee_rate: Decimal) -> Decimal:
    _check_amount(redemption_amount, "赎回金额")
    _check_fee_rate(fee_rate, "赎回费率")
    return to_cents(redemption_amount * fee_rate)


def net_investment_proceeds(
    amount: Decimal,
    holding_period_return: Decimal,
    subscription_fee_rate: Decimal = ZERO,
    redemption_fee_rate: Decimal = ZERO,
    method: FeeMethod = FeeMethod.EXTERNAL,
) -> dict[str, Decimal]:
    """一次完整申购—持有—赎回的到手金额。

    holding_period_return 是**持有期间**（非年化）的净值涨幅。净值型产品的净值通常已扣除
    管理费、托管费等，因此这里只扣申购费和赎回费，避免重复扣费。
    """
    _check_rate(holding_period_return, "持有期收益率")
    sub_fee, net_sub = subscription_fee(amount, subscription_fee_rate, method)
    gross_value = to_cents(net_sub * (ONE + holding_period_return))
    red_fee = redemption_fee(gross_value, redemption_fee_rate)
    proceeds = gross_value - red_fee
    return {
        "subscription_fee": sub_fee,
        "net_subscription": net_sub,
        "gross_redemption_value": gross_value,
        "redemption_fee": red_fee,
        "net_proceeds": proceeds,
        "profit": proceeds - amount,
    }
