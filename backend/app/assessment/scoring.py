"""风险测评计分。纯函数，不依赖 LLM 和数据库；评级只能由这里产生。"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

from app.core.i18n import L

QUESTIONNAIRE_DIR = Path(__file__).parent
RATING_ORDER = ["C1", "C2", "C3", "C4", "C5"]
PRODUCT_RISK_ORDER = ["PR1", "PR2", "PR3", "PR4", "PR5"]


class AssessmentError(ValueError):
    pass


class Option(BaseModel):
    id: str
    text: str
    text_en: str
    score: int


class Question(BaseModel):
    id: str
    dimension: str
    dimension_en: str
    text: str
    text_en: str
    options: list[Option]
    veto_option: str | None = None

    def option(self, option_id: str) -> Option | None:
        return next((o for o in self.options if o.id == option_id), None)


class RatingBand(BaseModel):
    rating: str
    name: str
    name_en: str
    max_score: int
    max_product_risk: str
    description: str
    description_en: str

    @property
    def display_name(self) -> str:
        return L(self.name, self.name_en)

    @property
    def display_description(self) -> str:
        return L(self.description, self.description_en)


class Questionnaire(BaseModel):
    version: str
    title: str
    title_en: str
    disclaimer: str
    disclaimer_en: str
    validity_months: int
    reassessment_cooldown_hours: int
    questions: list[Question]
    ratings: list[RatingBand]

    @model_validator(mode="after")
    def _check(self):
        # 配置错误应在启动时暴露，而不是在客户测评时
        total = sum(max(o.score for o in q.options) for q in self.questions)
        if total != 100:
            raise ValueError(f"问卷满分应为 100，实际为 {total}")
        if [r.rating for r in self.ratings] != RATING_ORDER:
            raise ValueError("评级分档必须依次为 C1–C5")
        limits = [r.max_score for r in self.ratings]
        if limits != sorted(limits) or limits[-1] != 100:
            raise ValueError("分档上限必须递增且最后一档为 100")
        for q in self.questions:
            if q.veto_option and q.option(q.veto_option) is None:
                raise ValueError(f"{q.id} 的否决选项 {q.veto_option} 不存在")
        return self

    def band(self, rating: str) -> RatingBand:
        return next(r for r in self.ratings if r.rating == rating)

    def public_view(self) -> dict:
        """给前端的版本：不含分值和否决规则，避免客户「按分作答」。"""
        return {
            "version": self.version,
            "title": L(self.title, self.title_en),
            "disclaimer": L(self.disclaimer, self.disclaimer_en),
            "questions": [
                {
                    "id": q.id,
                    "dimension": L(q.dimension, q.dimension_en),
                    "text": L(q.text, q.text_en),
                    "options": [{"id": o.id, "text": L(o.text, o.text_en)} for o in q.options],
                }
                for q in self.questions
            ],
        }


class AssessmentResult(BaseModel):
    questionnaire_version: str
    score: int
    rating: str
    rating_name: str
    description: str
    max_product_risk: str
    vetoed: bool
    warnings: list[str]  # 矛盾作答提示：提醒客户核对，不改分
    notes: list[str]  # 其他提示（如高龄客户）


@lru_cache
def load_questionnaire(version: str = "v1") -> Questionnaire:
    path = QUESTIONNAIRE_DIR / f"questionnaire_{version}.yaml"
    return Questionnaire.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def score_answers(questionnaire: Questionnaire, answers: dict[str, str]) -> AssessmentResult:
    expected = {q.id for q in questionnaire.questions}
    if missing := sorted(expected - answers.keys()):
        raise AssessmentError(
            L(
                f"以下题目未作答：{', '.join(missing)}",
                f"Unanswered questions: {', '.join(missing)}",
            )
        )
    if extra := sorted(answers.keys() - expected):
        raise AssessmentError(
            L(f"未知题目：{', '.join(extra)}", f"Unknown questions: {', '.join(extra)}")
        )

    score = 0
    vetoed = False
    for q in questionnaire.questions:
        option = q.option(answers[q.id])
        if option is None:
            raise AssessmentError(
                L(
                    f"{q.id} 的选项 {answers[q.id]} 不存在",
                    f"Option {answers[q.id]} doesn't exist for {q.id}",
                )
            )
        score += option.score
        if q.veto_option and option.id == q.veto_option:
            vetoed = True

    score_rating = next(r.rating for r in questionnaire.ratings if score <= r.max_score)
    rating = "C1" if vetoed else score_rating
    band = questionnaire.band(rating)
    return AssessmentResult(
        questionnaire_version=questionnaire.version,
        score=score,
        rating=rating,
        rating_name=band.display_name,
        description=band.display_description,
        max_product_risk=band.max_product_risk,
        vetoed=vetoed,
        warnings=_consistency_warnings(answers, score_rating),
        notes=_notes(answers),
    )


def _consistency_warnings(answers: dict[str, str], score_rating: str) -> list[str]:
    warnings = []
    if answers.get("q5") == "A" and (answers.get("q7") == "D" or answers.get("q8") == "D"):
        warnings.append(
            L(
                "您表示这笔资金 1 年内可能使用，但又选择了高波动的投资倾向，请核对答案。",
                "You said you may need this money within a year, but chose a high-volatility "
                "preference. Please check your answers.",
            )
        )
    if answers.get("q9") in {"A", "D"} and RATING_ORDER.index(score_rating) >= 2:
        warnings.append(
            L(
                "您认为理财产品保本或不清楚其风险，但评估结果为中高风险承受能力，请核对答案。",
                "You think wealth products are principal-protected or aren't sure of their risk, "
                "yet your result shows medium-to-high risk tolerance. Please check your answers.",
            )
        )
    return warnings


def _notes(answers: dict[str, str]) -> list[str]:
    if answers.get("q1") == "E":
        return [
            L(
                "建议您在购买任何理财产品前，与家人或理财经理充分沟通。",
                "Before buying any wealth product, we suggest talking it through with family "
                "or your relationship manager.",
            )
        ]
    return []


def rating_allows(rating: str, product_risk: str) -> bool:
    """客户评级不低于产品风险等级才可购买：C2 可购买 PR1–PR2。"""
    return PRODUCT_RISK_ORDER.index(product_risk) <= RATING_ORDER.index(rating)
