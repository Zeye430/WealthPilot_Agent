"""Policy engine: deterministic compliance rules.

This module doesn't depend on the LLM. These decisions control which tools the LLM may use and which
data it can see.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.db.models import RiskAssessment

RULE_VERSION = "2026-10-19.1"

# Tools the LLM may use before a risk assessment. Only tools unrelated to specific products; tighten
# or loosen here only.
# search_documents only searches the knowledge base before an assessment (the tool limits its scope
# by permission);
# update_needs only records needs; request_handoff works without an assessment (a person can help
# with it);
# get_customer_benefits looks up the customer's tier and campaigns, unrelated to specific products
PRE_ASSESSMENT_ALLOWED_TOOLS = frozenset(
    {
        "start_risk_assessment",
        "calculate_growth",
        "search_documents",
        "update_needs",
        "request_handoff",
        "get_customer_benefits",
    }
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
    """Conversation gate: recomputed for every message, so an assessment completed
    mid-conversation takes effect immediately."""
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
