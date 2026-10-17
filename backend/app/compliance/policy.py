"""Policy Engine：确定性的合规规则。规则见 docs/COMPLIANCE_DESIGN.md。

本模块不依赖 LLM。LLM 能用哪些工具、能看到哪些数据，由这里的结论决定。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.db.models import RiskAssessment

RULE_VERSION = "2026-10-17.1"

# 测评前允许 LLM 使用的工具。只放与具体产品无关的工具；收紧或放开只改这里。
# search_documents 测评前只检索知识库（工具内部按权限限定范围），不涉及产品信息
PRE_ASSESSMENT_ALLOWED_TOOLS = frozenset(
    {"start_risk_assessment", "calculate_growth", "search_documents"}
)


class Permission(StrEnum):
    ASSESSMENT_REQUIRED = "ASSESSMENT_REQUIRED"
    ASSESSED = "ASSESSED"


class GateDecision(BaseModel):
    permission: Permission
    risk_rating: str | None
    reason_codes: list[str]
    rule_version: str = RULE_VERSION


def evaluate_gate(assessment: RiskAssessment | None, now: datetime) -> GateDecision:
    """会话门禁：每条消息都重新计算，客户中途完成测评后立即生效。"""
    if assessment is None:
        return GateDecision(
            permission=Permission.ASSESSMENT_REQUIRED,
            risk_rating=None,
            reason_codes=["ASSESSMENT_MISSING"],
        )
    if assessment.expires_at is None or assessment.expires_at <= now:
        return GateDecision(
            permission=Permission.ASSESSMENT_REQUIRED,
            risk_rating=None,
            reason_codes=["ASSESSMENT_EXPIRED"],
        )
    return GateDecision(
        permission=Permission.ASSESSED, risk_rating=assessment.rating, reason_codes=[]
    )


def tool_allowed(permission: Permission, tool_name: str) -> bool:
    return permission is Permission.ASSESSED or tool_name in PRE_ASSESSMENT_ALLOWED_TOOLS
