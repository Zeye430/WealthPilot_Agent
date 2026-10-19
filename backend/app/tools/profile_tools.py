"""需求记录与配置模拟工具。客户身份与评级均来自流程状态（InjectedState），LLM 不可见。"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from langchain_core.tools import ToolException, tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from app.core.i18n import L, localized, register
from app.customers.base import get_customer_info_system
from app.customers.needs import CONVERSATION, FIELD_LABELS, NeedsError, NeedsUpdate, get_needs
from app.customers.needs import update_needs as save_needs
from app.db.session import get_engine
from app.products.allocation import AllocationError, simulate
from app.products.catalog import load_catalog
from app.products.presenter import format_money, format_rate

ALLOCATION_NOTE = register(
    "配置模拟仅用于理解组合的比例、流动性与费用，不测算收益，不构成投资建议。",
    "This simulation only shows the mix's shares, liquidity and fees. It does not estimate "
    "returns and is not investment advice.",
)


def _session():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)()


def _customer_id(state: dict) -> str:
    customer_id = state.get("customer_id")
    if not customer_id:
        raise ToolException(L("无法识别客户身份。", "Customer not identified."))
    return customer_id


def _d(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


@tool(response_format="content_and_artifact")
def update_needs(
    state: Annotated[dict, InjectedState],
    investment_amount: Annotated[
        float | None, Field(description="计划投资金额（元），如 100 万填 1000000")
    ] = None,
    horizon_months: Annotated[int | None, Field(description="投资期限（月），如 2 年填 24")] = None,
    liquidity_reserve: Annotated[
        float | None, Field(description="计划投资金额中随时可能动用的部分（元）")
    ] = None,
    target_annual_return: Annotated[
        float | None, Field(description="客户期望的年化收益，小数形式，5% 填 0.05")
    ] = None,
    max_acceptable_loss: Annotated[
        float | None, Field(description="客户说明的可接受最大亏损，小数形式，5% 填 0.05")
    ] = None,
    goal: Annotated[str | None, Field(description="投资目的，简短描述，如「子女教育」")] = None,
) -> tuple[str, list[dict]]:
    """记录客户在对话中提供的投资需求。只记录客户明确说出的信息，不要推测。

    这些信息叠加在银行系统已有的客户资料之上，不会改写基础资料。
    """
    update = NeedsUpdate(
        investment_amount=_d(investment_amount),
        horizon_months=horizon_months,
        liquidity_reserve=_d(liquidity_reserve),
        target_annual_return=_d(target_annual_return),
        max_acceptable_loss=_d(max_acceptable_loss),
        goal=goal,
    )
    with _session() as db:
        try:
            needs = save_needs(db, _customer_id(state), update, CONVERSATION, datetime.now(UTC))
        except NeedsError as exc:
            raise ToolException(L(f"需求信息有误：{exc}", f"Invalid goal details: {exc}")) from exc
        db.commit()
    updated = [r for r in needs.display() if r["field"] in update.provided()]
    content = json.dumps(
        {"recorded": {r["label"]: r["value"] for r in updated}}, ensure_ascii=False
    )
    return content, [{"type": "needs_update", "items": updated}]


class AllocationItem(BaseModel):
    product: str = Field(description="产品代码或名称；活期存款写「活期存款」")
    amount: float = Field(description="配置金额（元）")


MAX_SIMULATIONS_PER_TURN = 2  # 首次模拟 + 按检查结果调整一次


def _simulations_this_turn(state: dict) -> int:
    """本轮（最后一条客户消息之后）模型发起的配置模拟次数，含正在执行的这次。"""
    from langchain_core.messages import AIMessage, HumanMessage

    messages = state.get("messages", [])
    start = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1)
    return sum(
        1
        for m in messages[start + 1 :]
        if isinstance(m, AIMessage)
        for c in m.tool_calls
        if c["name"] == "simulate_allocation"
    )


@tool(response_format="content_and_artifact")
def simulate_allocation(
    state: Annotated[dict, InjectedState],
    allocations: Annotated[list[AllocationItem], Field(description="1–8 个配置项")],
) -> tuple[str, list[dict]]:
    """模拟一个配置组合，检查是否满足客户的风险等级、合计金额、流动性、集中度等约束，并估算固定费用。

    只用于帮助客户理解不同组合的取舍，不测算收益。产品应来自 search_products 的结果。
    """
    rating = state.get("risk_rating")
    if not rating:
        raise ToolException(
            L(
                "客户尚未完成有效的风险测评，无法模拟配置。",
                "The customer has no valid risk profile, so a mix can't be simulated.",
            )
        )
    if _simulations_this_turn(state) > MAX_SIMULATIONS_PER_TURN:
        # 场景评估 V02：模型反复调整组合，耗尽本轮工具调用次数
        raise ToolException(
            L(
                f"本轮已模拟 {MAX_SIMULATIONS_PER_TURN} 次配置，"
                "请根据最后一次的检查结果回答客户，不要再模拟。",
                f"Already simulated {MAX_SIMULATIONS_PER_TURN} times this turn. Answer from the "
                "last check results; don't simulate again.",
            )
        )
    customer_id = _customer_id(state)
    with _session() as db:
        needs = get_needs(db, customer_id)
    base = get_customer_info_system().get(customer_id)
    try:
        result = simulate(
            [(a.product, Decimal(str(a.amount))) for a in allocations],
            load_catalog(),
            rating,
            needs,
            existing_liquid=base.assets_at_bank.liquid_total() if base else None,
        )
    except AllocationError as exc:
        raise ToolException(L(f"配置参数有误：{exc}", f"Invalid mix: {exc}")) from exc

    slices = [
        {
            "code": s.code,
            "name": s.name,
            "amount": float(s.amount),
            "amount_text": format_money(s.amount),
            "pct": float(s.pct),
            "pct_text": format_rate(s.pct),
            "risk_level": s.risk_level,
            "lockup": s.lockup,
        }
        for s in result.slices
    ]
    checks = [c.model_dump() for c in result.checks]
    content = json.dumps(
        {
            "passed": result.passed,
            "slices": [f"{s['name']} {s['amount_text']} ({s['pct_text']})" for s in slices],
            "checks": [f"[{c['status']}] {c['label']}: {c['message']}" for c in checks],
            "rules": "如实说明检查结果；未通过的项必须说明原因；不要测算或承诺组合收益。",
        },
        ensure_ascii=False,
    )
    artifact = {
        "type": "allocation",
        "title": L("配置情景模拟", "Allocation simulation"),
        "passed": result.passed,
        "slices": slices,
        "checks": checks,
        "disclaimer": localized(ALLOCATION_NOTE),
    }
    return content, [artifact]


PROFILE_TOOLS = [update_needs, simulate_allocation]
for _t in PROFILE_TOOLS:
    _t.handle_tool_error = True
    _t.handle_validation_error = True

__all__ = ["PROFILE_TOOLS", "FIELD_LABELS"]
