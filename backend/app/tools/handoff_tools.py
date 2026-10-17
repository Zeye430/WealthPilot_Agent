"""人工交接工具：生成交接草稿，由客户在界面上确认后才会提交给理财经理。

工具本身不能提交交接，也不能宣称已接入：状态只能由客户点击同意、理财经理接单等真实操作推进。
"""

import json
from datetime import UTC, datetime
from typing import Annotated, Literal

from langchain_core.tools import ToolException, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field
from sqlalchemy.orm import sessionmaker

from app.db.session import get_engine
from app.handoff.service import (
    AWAITING_CONSENT,
    STATUS_LABELS,
    HandoffError,
    create_draft,
    handoff_view,
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
    """为客户生成转人工（理财经理）请求。

    客户主动要求人工、需要综合规划或正式投资建议、诉求与风险等级冲突时使用。
    生成后需要客户在界面确认分享的信息，才会提交给理财经理；在此之前不得说已转接。
    """
    customer_id, conversation_id = state.get("customer_id"), state.get("conversation_id")
    if not customer_id or not conversation_id:
        raise ToolException("无法识别客户或会话。")
    with sessionmaker(bind=get_engine(), expire_on_commit=False)() as db:
        try:
            handoff = create_draft(
                db, conversation_id, customer_id, reason, open_questions[:5], datetime.now(UTC)
            )
        except HandoffError as exc:
            raise ToolException(str(exc)) from exc
        db.commit()

    view = handoff_view(handoff)
    if handoff.status == AWAITING_CONSENT:
        content = {
            "status": STATUS_LABELS[handoff.status],
            "rm": handoff.assigned_rm_name,
            "next_step": "请客户在下方卡片中确认分享的信息范围；"
            "确认前不会提交，也不能说已转接或理财经理已接入。",
        }
        summary = handoff.summary
        artifact = {
            "type": "handoff_consent",
            **view,
            "scope": handoff.consent_scope,
            "preview": {
                "assessment": summary["assessment"],
                "needs": [f"{n['label']} {n['value']}" for n in summary["needs"]],
                "products_discussed": summary["products_discussed"],
                "open_questions": summary["open_questions"],
            },
        }
    else:
        content = {
            "status": STATUS_LABELS[handoff.status],
            "rm": handoff.assigned_rm_name,
            "next_step": "该会话已有进行中的人工服务请求，如实告知当前状态，不要重复提交。",
        }
        artifact = {"type": "handoff_status", **view}
    return json.dumps(content, ensure_ascii=False), [artifact]


request_handoff.handle_tool_error = True
request_handoff.handle_validation_error = True
HANDOFF_TOOLS = [request_handoff]
