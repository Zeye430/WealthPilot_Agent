"""Customer tier and campaign tool: unrelated to specific products, so it is available before an
assessment.

Tiers, gaps and campaigns are all computed in code from asset data; the AI only relays them and must
not invent benefits or promise upgrades. Tool docstrings are the tool descriptions sent to the
model, so they stay in Chinese like the prompts.
"""

import json
from datetime import date
from decimal import Decimal
from typing import Annotated

from langchain_core.tools import ToolException, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field

from app.benefits.service import benefits_block, tier_status
from app.core.i18n import L
from app.customers.base import get_customer_info_system
from app.tools.product_tools import _recorded_needs

RULES = (
    "只转述列出的等级、权益和活动，不要编造；权益与金融资产总额挂钩（存款也计入），"
    "不要说「购买某款产品送礼品 / 返现」；等级以银行评定为准，不要承诺一定能升级；"
    "projection 是假设计划资金为新转入本行的资金，提及时说明这一前提。"
)


@tool(response_format="content_and_artifact")
def get_customer_benefits(
    state: Annotated[dict, InjectedState],
    planned_amount: Annotated[
        float | None,
        Field(description="客户计划新转入本行的资金（元）；未提及不填，系统会参考已记录的投资金额"),
    ] = None,
) -> tuple[str, list[dict]]:
    """查询客户的贵宾等级、当前权益、距下一等级的差距，以及可参与的营销活动。

    客户询问奖励、礼品、活动、权益、贵宾卡、客户等级，或计划资金转入后可能达到更高等级时使用。
    """
    customer_id = state.get("customer_id")
    base = get_customer_info_system().get(customer_id) if customer_id else None
    if base is None:
        raise ToolException(
            L(
                "未找到客户资料，无法查询等级与权益。",
                "Customer records not found, so tier and benefits can't be checked.",
            )
        )
    if planned_amount is None and (needs := _recorded_needs(customer_id)):
        planned_amount = float(needs.investment_amount) if needs.investment_amount else None
    status = tier_status(base, Decimal(str(planned_amount)) if planned_amount else None)
    block = benefits_block(status, date.today())
    content = {k: v for k, v in block.items() if k != "type"} | {"rules": RULES}
    return json.dumps(content, ensure_ascii=False), [block]


get_customer_benefits.handle_tool_error = True
get_customer_benefits.handle_validation_error = True
BENEFIT_TOOLS = [get_customer_benefits]
