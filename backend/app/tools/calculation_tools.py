"""Calculation tools exposed to the LLM.

Tools do three things only: validate arguments → call app.calculations → assemble the result.
They return (content, artifact): content is for the LLM (JSON text); artifact is the UI block the
frontend renders,
never rewritten by the LLM, so chart numbers always match the calculation.
"""

import json
from decimal import Decimal
from typing import Literal

from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field

from app.calculations import core as calc
from app.core.i18n import L, all_versions, localized, register

HYPOTHETICAL_NOTE = register(
    "假设情景：按固定收益率测算，未考虑税费与市场波动，不代表任何产品的未来表现，亦非收益承诺。",
    "Hypothetical: assumes a fixed rate and ignores taxes, fees and market swings. It does not "
    "represent any product's future performance and is not a promise of returns.",
)


def _d(value: float) -> Decimal:
    # The LLM sends JSON numbers; going through str avoids binary floating-point error (0.05 →
    # Decimal("0.05"))
    return Decimal(str(value))


def _yuan(value: Decimal) -> str:
    return str(calc.to_cents(value))


def _pct(rate: Decimal) -> str:
    return f"{(rate * 100).normalize():f}%"


def _slip_assumptions(assumptions: list[str]) -> list[str]:
    # The disclaimer on the slip is carried by the stamp (disclaimer field), so it isn't repeated in
    # the list
    return [a for a in assumptions if a not in all_versions(HYPOTHETICAL_NOTE)]


def _unit() -> str:
    return L("元", "CNY")


def _run(fn):
    try:
        return fn()
    except calc.CalculationError as exc:
        raise ToolException(L(f"计算参数错误：{exc}", f"Invalid calculation input: {exc}")) from exc


# ---------- calculate_growth ----------


class GrowthInput(BaseModel):
    principal: float = Field(description="初始本金（元），如 100 万填 1000000")
    annual_rate: float = Field(description="假设年化收益率，小数形式，5% 填 0.05")
    years: int = Field(description="投资年数，整数")
    compounding: Literal["annual", "monthly", "simple"] = Field(
        default="annual", description="annual=按年复利，monthly=按月复利，simple=单利"
    )
    monthly_contribution: float = Field(default=0, description="每月追加投入（元），没有填 0")
    inflation_rate: float | None = Field(
        default=None, description="假设年通胀率，小数形式；用户关心购买力时填写，如 0.02"
    )


def _growth(
    principal: float,
    annual_rate: float,
    years: int,
    compounding: str = "annual",
    monthly_contribution: float = 0,
    inflation_rate: float | None = None,
):
    pv, r, pmt = _d(principal), _d(annual_rate), _d(monthly_contribution)

    def compute():
        if compounding == "simple":
            if pmt:
                raise calc.CalculationError(
                    L(
                        "单利模式不支持每月追加投入，请改用按月复利",
                        "Simple interest doesn't support monthly contributions; use monthly "
                        "compounding instead",
                    )
                )
            path = [pv + calc.simple_interest(pv, r, y) for y in range(years + 1)]
            formula = "FV = PV × (1 + r × n)"
        else:
            m = 12 if compounding == "monthly" or pmt else 1
            per_period = pmt if m == 12 else calc.ZERO
            path = calc.growth_path(pv, r, years, periods_per_year=m, periodic_payment=per_period)
            formula = "FV = PV × (1 + r/m)^(m·n)" + (
                L(" + 定投年金终值", " + FV of monthly contributions") if pmt else ""
            )
        return path, formula

    path, formula = _run(compute)
    final = path[-1]
    invested = pv + pmt * 12 * years
    result = {
        "final_value": _yuan(final),
        "total_invested": _yuan(invested),
        "total_gain": _yuan(final - invested),
    }
    compounding_text = {
        "annual": L("按年复利", "Compounded annually"),
        "monthly": L("按月复利", "Compounded monthly"),
        "simple": L("单利，不再投资", "Simple interest, no reinvestment"),
    }
    assumptions = [
        L(f"年化收益率固定为 {_pct(r)}", f"Fixed annual rate of {_pct(r)}"),
        compounding_text[compounding]
        if not pmt
        else L("按月复利，每月末追加投入", "Compounded monthly, contributions at month-end"),
        localized(HYPOTHETICAL_NOTE),
    ]
    items = [
        {"label": L("期末金额", "Ending balance"), "value": result["final_value"], "unit": _unit()},
        {
            "label": L("累计投入", "Total invested"),
            "value": result["total_invested"],
            "unit": _unit(),
        },
        {"label": L("累计收益", "Total gain"), "value": result["total_gain"], "unit": _unit()},
    ]
    if inflation_rate is not None:
        real = _run(lambda: calc.inflation_adjusted_value(final, _d(inflation_rate), years))
        result["real_value_today"] = _yuan(real)
        items.append(
            {
                "label": L("折合今天购买力", "In today's money"),
                "value": result["real_value_today"],
                "unit": _unit(),
            }
        )
        rate_text = _pct(_d(inflation_rate))
        assumptions.insert(
            1, L(f"年通胀率固定为 {rate_text}", f"Fixed annual inflation of {rate_text}")
        )

    content = json.dumps(
        {**result, "formula": formula, "assumptions": assumptions}, ensure_ascii=False
    )
    artifact = [
        {
            "type": "calculation_result",
            "title": L(f"{years} 年收益测算", f"{years}-year growth estimate"),
            "formula": formula,
            "items": items,
            "assumptions": _slip_assumptions(assumptions),
            "disclaimer": localized(HYPOTHETICAL_NOTE),
        },
        {
            "type": "line_chart",
            "title": L("逐年余额（假设情景）", "Balance by year (hypothetical)"),
            "x_label": L("年", "Year"),
            "y_label": _unit(),
            "series": [
                {
                    "name": L(f"年化 {_pct(r)}", f"{_pct(r)} a year"),
                    "points": [{"x": i, "y": float(calc.to_cents(v))} for i, v in enumerate(path)],
                }
            ],
            "note": L(
                "按固定收益率测算，未考虑税费与市场波动",
                "Assumes a fixed rate; ignores taxes, fees and market swings",
            ),
        },
    ]
    return content, artifact


calculate_growth = StructuredTool.from_function(
    func=_growth,
    name="calculate_growth",
    description="计算本金在假设年化收益率下的增长：单利、复利、每月定投、通胀调整。"
    "凡是涉及金额增长的计算都必须调用本工具，不要自己心算。",
    args_schema=GrowthInput,
    response_format="content_and_artifact",
    handle_tool_error=True,
    handle_validation_error=True,
)


# ---------- generate_return_scenarios ----------


class ScenarioInput(BaseModel):
    principal: float = Field(description="初始本金（元）")
    years: int = Field(description="投资年数")
    annual_rates: list[float] = Field(
        description="2–5 档假设年化收益率，小数形式，如 [0.02, 0.03, 0.05]；可含负数表示亏损情景"
    )


def _scenarios(principal: float, years: int, annual_rates: list[float]):
    if not 2 <= len(annual_rates) <= 5:
        raise ToolException(
            L(
                "计算参数错误：请提供 2 到 5 档收益率",
                "Invalid calculation input: give 2 to 5 rates",
            )
        )
    pv = _d(principal)
    rates = sorted(_d(r) for r in annual_rates)
    paths = {r: _run(lambda r=r: calc.growth_path(pv, r, years)) for r in rates}
    finals = {_pct(r): _yuan(p[-1]) for r, p in paths.items()}
    content = json.dumps(
        {
            "final_values_by_rate": finals,
            "assumptions": [L("按年复利", "Compounded annually"), localized(HYPOTHETICAL_NOTE)],
        },
        ensure_ascii=False,
    )
    artifact = [
        {
            "type": "line_chart",
            "title": L(f"{years} 年多档收益假设对比", f"{years}-year rate scenarios"),
            "x_label": L("年", "Year"),
            "y_label": _unit(),
            "series": [
                {
                    "name": L(f"年化 {_pct(r)}", f"{_pct(r)} a year"),
                    "points": [{"x": i, "y": float(calc.to_cents(v))} for i, v in enumerate(p)],
                }
                for r, p in paths.items()
            ],
            "note": L(
                "按年复利测算，未考虑税费与市场波动",
                "Compounded annually; ignores taxes, fees and market swings",
            ),
        }
    ]
    return content, artifact


generate_return_scenarios = StructuredTool.from_function(
    func=_scenarios,
    name="generate_return_scenarios",
    description="对同一笔本金，比较多档假设年化收益率下的增长路径，用于说明收益假设的影响。",
    args_schema=ScenarioInput,
    response_format="content_and_artifact",
    handle_tool_error=True,
    handle_validation_error=True,
)


# ---------- calculate_fees ----------


class FeeInput(BaseModel):
    amount: float = Field(description="申购金额（元）")
    product: str | None = Field(
        default=None,
        description="产品代码或名称。填写后申购费、赎回费按该产品说明书的费率计算，不需要也不应自行填写费率",
    )
    holding_days: int | None = Field(
        default=None, description="持有天数；填写 product 时用于确定赎回费档位"
    )
    subscription_fee_rate: float = Field(default=0, description="申购费率，小数形式，0.3% 填 0.003")
    fee_method: Literal["external", "internal"] = Field(
        default="external", description="申购费计算方式：external=外扣法，internal=内扣法"
    )
    holding_period_return: float = Field(
        default=0, description="持有期间净值涨幅（非年化），小数形式，如持有期涨 2% 填 0.02"
    )
    redemption_fee_rate: float = Field(default=0, description="赎回费率，小数形式")


def _product_rates(product: str, holding_days: int | None) -> tuple[float, float, str]:
    """Read fee rates from product terms: product-specific rates can't come from the model (it
    might invent them)."""
    from app.products.catalog import load_catalog
    from app.products.presenter import format_rate

    found = load_catalog().find_by_name(product)
    if found is None:
        raise ToolException(L(f"未找到产品「{product}」", f'Product "{product}" not found'))
    if found.fees.subscription is None:
        raise ToolException(
            L(
                f"{found.name}的申购费未核实，无法测算",
                f"{found.name_en}'s subscription fee is unverified, so it can't be estimated",
            )
        )
    if holding_days is None:
        raise ToolException(
            L(
                "按产品测算赎回费需要提供持有天数（holding_days）",
                "Product-based redemption fees need holding_days",
            )
        )
    redemption = _run(
        lambda: calc.redemption_fee_rate(
            holding_days, [(t.max_days, t.rate) for t in found.fees.redemption]
        )
    )
    note = L(
        f"费率来自《{found.name}》说明书：申购费 {format_rate(found.fees.subscription)}，"
        f"持有 {holding_days} 天适用赎回费 {format_rate(redemption)}",
        f"Rates from the {found.name_en} prospectus: subscription fee "
        f"{format_rate(found.fees.subscription)}; redemption fee for {holding_days} days held "
        f"{format_rate(redemption)}",
    )
    return float(found.fees.subscription), float(redemption), note


def _fees(
    amount: float,
    product: str | None = None,
    holding_days: int | None = None,
    subscription_fee_rate: float = 0,
    fee_method: str = "external",
    holding_period_return: float = 0,
    redemption_fee_rate: float = 0,
):
    source_note = None
    if product:
        subscription_fee_rate, redemption_fee_rate, source_note = _product_rates(
            product, holding_days
        )
    result = _run(
        lambda: calc.net_investment_proceeds(
            _d(amount),
            holding_period_return=_d(holding_period_return),
            subscription_fee_rate=_d(subscription_fee_rate),
            redemption_fee_rate=_d(redemption_fee_rate),
            method=calc.FeeMethod(fee_method),
        )
    )
    as_text = {k: _yuan(v) for k, v in result.items()}
    assumptions = [
        L(
            "外扣法：净申购金额 = 申购金额 ÷ (1 + 费率)",
            "External method: net subscription = amount ÷ (1 + fee rate)",
        )
        if fee_method == "external"
        else L(
            "内扣法：申购费 = 申购金额 × 费率", "Internal method: subscription fee = amount × rate"
        ),
        L(
            "持有期收益按净值涨幅计；净值通常已扣除管理费、托管费，此处不重复扣除",
            "Return is based on NAV change; NAV is usually already net of management and "
            "custody fees, so they aren't deducted again",
        ),
        localized(HYPOTHETICAL_NOTE),
    ]
    if source_note:
        assumptions.insert(0, source_note)
    labels = {
        "subscription_fee": L("申购费", "Subscription fee"),
        "net_subscription": L("净申购金额", "Net subscription"),
        "gross_redemption_value": L("赎回前市值", "Value before redemption"),
        "redemption_fee": L("赎回费", "Redemption fee"),
        "net_proceeds": L("到手金额", "Net proceeds"),
        "profit": L("净收益", "Net gain"),
    }
    content = json.dumps({**as_text, "assumptions": assumptions}, ensure_ascii=False)
    artifact = [
        {
            "type": "calculation_result",
            "title": L("费用与到手金额测算", "Fees and net proceeds"),
            "formula": None,
            "items": [
                {"label": labels[k], "value": v, "unit": _unit()} for k, v in as_text.items()
            ],
            "assumptions": _slip_assumptions(assumptions),
            "disclaimer": localized(HYPOTHETICAL_NOTE),
        }
    ]
    return content, artifact


calculate_fees = StructuredTool.from_function(
    func=_fees,
    name="calculate_fees",
    description="计算申购费、赎回费以及一次申购—持有—赎回后的到手金额和净收益。"
    "涉及具体产品时填写 product 与 holding_days，费率自动取自产品说明书。",
    args_schema=FeeInput,
    response_format="content_and_artifact",
    handle_tool_error=True,
    handle_validation_error=True,
)

CALCULATION_TOOLS = [calculate_growth, generate_return_scenarios, calculate_fees]
