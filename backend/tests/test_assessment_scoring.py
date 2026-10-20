"""问卷计分测试：校准画像的计分结果保持稳定。"""

import pytest

from app.assessment.scoring import (
    AssessmentError,
    load_questionnaire,
    rating_allows,
    score_answers,
)

Q = load_questionnaire("v1")


def answers(letters: str) -> dict[str, str]:
    return {f"q{i + 1}": letter for i, letter in enumerate(letters.replace(" ", ""))}


@pytest.mark.parametrize(
    ("letters", "score", "rating", "vetoed"),
    [
        ("E C B A A A A A A A", 17, "C1", True),
        ("E C B B B A A B C B", 37, "C2", False),
        ("C C C B B B B B C B", 51, "C2", False),  # 主场景
        ("A C C B B B B B C B", 52, "C2", False),
        ("B C C C B B B B C C", 59, "C3", False),
        ("B C C C C C C C C C", 72, "C3", False),
        ("B D D D C C C C C D", 83, "C4", False),
        ("B D D E D D D D C E", 100, "C5", False),
        ("B D D E D D D D C A", 90, "C1", True),  # 否决题
    ],
)
def test_calibration_personas(letters, score, rating, vetoed):
    result = score_answers(Q, answers(letters))
    assert (result.score, result.rating, result.vetoed) == (score, rating, vetoed)


def test_result_carries_band_details():
    result = score_answers(Q, answers("C C C B B B B B C B"))
    assert result.rating_name == "稳健型"
    assert result.max_product_risk == "PR2"
    assert result.questionnaire_version == "v1"


def test_band_boundaries():
    # 25 → C1，26 → C2：用最低分答案逐步加分不便构造，直接检查分档配置
    assert [(r.rating, r.max_score) for r in Q.ratings] == [
        ("C1", 25),
        ("C2", 55),
        ("C3", 72),
        ("C4", 88),
        ("C5", 100),
    ]


def test_missing_answer_rejected():
    partial = answers("C C C B B B B B C B")
    del partial["q10"]
    with pytest.raises(AssessmentError, match="q10"):
        score_answers(Q, partial)


def test_invalid_option_rejected():
    bad = answers("C C C B B B B B C B")
    bad["q1"] = "Z"
    with pytest.raises(AssessmentError):
        score_answers(Q, bad)


def test_unknown_question_rejected():
    bad = answers("C C C B B B B B C B") | {"q99": "A"}
    with pytest.raises(AssessmentError, match="q99"):
        score_answers(Q, bad)


def test_liquidity_contradiction_warns_but_does_not_change_score():
    plain = score_answers(Q, answers("B D D E C D D C C E"))
    contradictory = score_answers(Q, answers("B D D E A D D D C E"))
    assert plain.warnings == []
    assert len(contradictory.warnings) == 1
    assert "1 年内" in contradictory.warnings[0]


def test_knowledge_contradiction_warns():
    result = score_answers(Q, answers("B D D E D D D D A E"))
    assert any("保本" in w for w in result.warnings)


def test_elderly_note():
    assert score_answers(Q, answers("E C B B B A A B C B")).notes
    assert not score_answers(Q, answers("C C C B B B B B C B")).notes


def test_public_view_hides_scores_and_veto():
    view = Q.public_view()
    assert len(view["questions"]) == 10
    flat = str(view)
    assert "score" not in flat
    assert "veto" not in flat


@pytest.mark.parametrize(
    ("rating", "product", "allowed"),
    [
        ("C1", "PR1", True),
        ("C1", "PR2", False),
        ("C2", "PR2", True),
        ("C2", "PR3", False),
        ("C5", "PR5", True),
    ],
)
def test_rating_allows(rating, product, allowed):
    assert rating_allows(rating, product) is allowed
