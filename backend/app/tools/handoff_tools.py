"""人工交接工具：把咨询要点同步到理财经理看板，并在客户界面展示理财经理名片（企业微信 / 电话）。

工具不能宣称理财经理已接入或已联系客户：理财经理是否跟进由看板上的真实操作决定。
"""

import json
from datetime import UTC, datetime
from typing import Annotated, Literal

from langchain_core.tools import ToolException, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field
from sqlalchemy.orm import sessionmaker

from app.core.i18n import L
from app.db.session import get_engine
from app.handoff.service import (
    HandoffError,
    create_request,
    rm_contact_card,
    status_label,
)

Reason = Literal[
    "USER_REQUEST",
    "REGULATED_ADVISORY_REQUEST",
    "HIGH_COMPLEXITY",
    "SUITABILITY_CONFLICT",
    "MISSING_CRITICAL_INFORMATION",
    "LOW_RETRIEVAL_CONFIDENCE",
    "UNVERIFIED_PRODUCT_DATA",
    "TOOL_FAILURE",
    "HUMAN_AUTHORIZATION_REQUIRED",
]


@tool(response_format="content_and_artifact")
def request_handoff(
    state: Annotated[dict, InjectedState],
    reason: Annotated[
        Reason,
        Field(
            description="USER_REQUEST 客户要求人工；HIGH_COMPLEXITY 退休/税务/房产等综合规划；"
            "REGULATED_ADVISORY_REQUEST 要求正式投资方案或交易；"
            "SUITABILITY_CONFLICT 诉求与风险等级冲突；"
            "其余：MISSING_CRITICAL_INFORMATION、LOW_RETRIEVAL_CONFIDENCE、UNVERIFIED_PRODUCT_DATA、"
            "TOOL_FAILURE、HUMAN_AUTHORIZATION_REQUIRED"
        ),
    ],
    open_questions: Annotated[
        list[str], Field(description="需要理财经理跟进的问题，1–5 条，简短")
    ] = [],  # noqa: B006
) -> tuple[str, list[dict]]:
    """为客户联系专属理财经理：同步咨询要点，并在界面展示理财经理名片（企业微信、电话）。

    客户主动要求人工、需要综合规划或正式投资建议、诉求与风险等级冲突时使用。
    """
    customer_id, conversation_id = state.get("customer_id"), state.get("conversation_id")
    if not customer_id or not conversation_id:
        raise ToolException(L("无法识别客户或会话。", "Customer or conversation not identified."))
    with sessionmaker(bind=get_engine(), expire_on_commit=False)() as db:
        try:
            handoff = create_request(
                db, conversation_id, customer_id, reason, open_questions[:5], datetime.now(UTC)
            )
        except HandoffError as exc:
            raise ToolException(str(exc)) from exc
        db.commit()

    card = rm_contact_card(handoff)
    content = {
        "status": status_label(handoff.status),
        "rm": card["rm_name"],
        "next_step": "界面已展示理财经理名片，客户可通过企业微信或电话直接联系；"
        "咨询要点已同步给理财经理。不要说理财经理已接入、已联系客户或正在服务。",
    }
    return json.dumps(content, ensure_ascii=False), [card]


request_handoff.handle_tool_error = True
request_handoff.handle_validation_error = True
HANDOFF_TOOLS = [request_handoff]
