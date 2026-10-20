from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.core.i18n import L


class StartAssessmentInput(BaseModel):
    pass


def assessment_prompt_block(variant: str = "invite") -> dict:
    """Assessment entry card (in the current language)."""
    return {
        "type": "assessment_prompt",
        "variant": variant,
        "title": L("风险承受能力测评", "Risk tolerance profile"),
        "message": L(
            "约 3 分钟，共 10 道题。完成后，我可以在您的风险等级范围内为您筛选产品。",
            "About 3 minutes, 10 questions. Afterwards I can match products "
            "within your risk level.",
        ),
    }


def _start_assessment():
    # The questionnaire is a fixed form in the UI; the LLM neither asks the questions nor scores
    # them, so it can't steer answers
    content = "界面已向客户展示风险测评入口。请用一两句话说明为什么需要先测评，不要替客户作答。"
    return content, [assessment_prompt_block()]


start_risk_assessment = StructuredTool.from_function(
    func=_start_assessment,
    name="start_risk_assessment",
    description="向客户展示风险承受能力测评入口。客户想了解适合自己的产品、要求推荐或配置，"
    "但尚未完成测评时调用；客户主动要求重新测评时也可调用。",
    args_schema=StartAssessmentInput,
    response_format="content_and_artifact",
)

ASSESSMENT_TOOLS = [start_risk_assessment]
