"""暴露给 LLM 的计算工具。

工具只做三件事：校验参数 → 调用 app.calculations → 组装结果。
返回值为 (content, artifact)：content 给 LLM 看（JSON 文本），artifact 是前端渲染用的 UI 块，
不经过 LLM 改写，保证图表数字与计算结果一致。
"""

import json
from decimal import Decimal
from typing import Literal

from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field

from app.calculations import core as calc

HYPOTHETICAL_NOTE = (
    "假设情景：按固定收益率测算，未考虑税费与市场波动，不代表任何产品的未来表现，亦非收益承诺。"
)


def _d(value: float) -> Decimal:
    # LLM 传来的是 JSON 数字；经 str 转换，避免二进制浮点误差（0.05 → Decimal("0.05")）
    return Decimal(str(value))


def _yuan(value: Decimal) -> str:
    return str(calc.to_cents(value))


def _pct(rate: Decimal) -> str:
    return f"{(rate * 100).normalize():f}%"


def _slip_assumptions(assumptions: list[str]) -> list[str]:
    # 凭证上的免责声明由印章（disclaimer 字段）承担，列表中不再重复
    return [a for a in assumptions if a != HYPOTHETICAL_NOTE]


def _run(fn):
    try:
        return fn()
    except calc.CalculationError as exc:
        raise ToolException(f"计算参数错误：{exc}") from exc


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
                raise calc.CalculationError("单利模式不支持每月追加投入，请改用按月复利")
            path = [pv + calc.simple_interest(pv, r, y) for y in range(years + 1)]
            formula = "FV = PV × (1 + r × n)"
        else:
            m = 12 if compounding == "monthly" or pmt else 1
            per_period = pmt if m == 12 else calc.ZERO
            path = calc.growth_path(pv, r, years, periods_per_year=m, periodic_payment=per_period)
            formula = "FV = PV × (1 + r/m)^(m·n)" + (" + 定投年金终值" if pmt else "")
        return path, formula

    path, formula = _run(compute)
    final = path[-1]
    invested = pv + pmt * 12 * years
    result = {
        "final_value": _yuan(final),
        "total_invested": _yuan(invested),
        "total_gain": _yuan(final - invested),
    }
    assumptions = [
        f"年化收益率固定为 {_pct(r)}",
        {"annual": "按年复利", "monthly": "按月复利", "simple": "单利，不再投资"}[compounding]
        if not pmt
        else "按月复利，每月末追加投入",
        HYPOTHETICAL_NOTE,
    ]
    items = [
        {"label": "期末金额", "value": result["final_value"], "unit": "元"},
        {"label": "累计投入", "value": result["total_invested"], "unit": "元"},
        {"label": "累计收益", "value": result["total_gain"], "unit": "元"},
    ]
    if inflation_rate is not None:
        real = _run(lambda: calc.inflation_adjusted_value(final, _d(inflation_rate), years))
        result["real_value_today"] = _yuan(real)
        items.append({"label": "折合今天购买力", "value": result["real_value_today"], "unit": "元"})
        assumptions.insert(1, f"年通胀率固定为 {_pct(_d(inflation_rate))}")

    content = json.dumps(
        {**result, "formula": formula, "assumptions": assumptions}, ensure_ascii=False
    )
    artifact = [
        {
            "type": "calculation_result",
            "title": f"{years} 年收益测算",
            "formula": formula,
            "items": items,
            "assumptions": _slip_assumptions(assumptions),
            "disclaimer": HYPOTHETICAL_NOTE,
        },
        {
            "type": "line_chart",
            "title": "逐年余额（假设情景）",
            "x_label": "年",
            "y_label": "元",
            "series": [
                {
                    "name": f"年化 {_pct(r)}",
                    "points": [{"x": i, "y": float(calc.to_cents(v))} for i, v in enumerate(path)],
                }
            ],
            "note": "按固定收益率测算，未考虑税费与市场波动",
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
        raise ToolException("计算参数错误：请提供 2 到 5 档收益率")
    pv = _d(principal)
    rates = sorted(_d(r) for r in annual_rates)
    paths = {r: _run(lambda r=r: calc.growth_path(pv, r, years)) for r in rates}
    finals = {_pct(r): _yuan(p[-1]) for r, p in paths.items()}
    content = json.dumps(
        {"final_values_by_rate": finals, "assumptions": ["按年复利", HYPOTHETICAL_NOTE]},
        ensure_ascii=False,
    )
    artifact = [
        {
            "type": "line_chart",
            "title": f"{years} 年多档收益假设对比",
            "x_label": "年",
            "y_label": "元",
            "series": [
                {
                    "name": f"年化 {_pct(r)}",
                    "points": [{"x": i, "y": float(calc.to_cents(v))} for i, v in enumerate(p)],
                }
                for r, p in paths.items()
            ],
            "note": "按年复利测算，未考虑税费与市场波动",
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
    """从产品要素读取费率：产品相关的费率不能由模型提供（可能编造）。"""
    from app.products.catalog import load_catalog
    from app.products.presenter import format_rate

    found = load_catalog().find_by_name(product)
    if found is None:
        raise ToolException(f"未找到产品「{product}」")
    if found.fees.subscription is None:
        raise ToolException(f"{found.name}的申购费未核实，无法测算")
    if holding_days is None:
        raise ToolException("按产品测算赎回费需要提供持有天数（holding_days）")
    redemption = _run(
        lambda: calc.redemption_fee_rate(
            holding_days, [(t.max_days, t.rate) for t in found.fees.redemption]
        )
    )
    note = (
        f"费率来自《{found.name}》说明书：申购费 {format_rate(found.fees.subscription)}，"
        f"持有 {holding_days} 天适用赎回费 {format_rate(redemption)}"
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
        "外扣法：净申购金额 = 申购金额 ÷ (1 + 费率)"
        if fee_method == "external"
        else "内扣法：申购费 = 申购金额 × 费率",
        "持有期收益按净值涨幅计；净值通常已扣除管理费、托管费，此处不重复扣除",
        HYPOTHETICAL_NOTE,
    ]
    if source_note:
        assumptions.insert(0, source_note)
    labels = {
        "subscription_fee": "申购费",
        "net_subscription": "净申购金额",
        "gross_redemption_value": "赎回前市值",
        "redemption_fee": "赎回费",
        "net_proceeds": "到手金额",
        "profit": "净收益",
    }
    content = json.dumps({**as_text, "assumptions": assumptions}, ensure_ascii=False)
    artifact = [
        {
            "type": "calculation_result",
            "title": "费用与到手金额测算",
            "formula": None,
            "items": [{"label": labels[k], "value": v, "unit": "元"} for k, v in as_text.items()],
            "assumptions": _slip_assumptions(assumptions),
            "disclaimer": HYPOTHETICAL_NOTE,
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
