"""Output review in the English UI (P8-2b): the English version of each rule must block violations
without flagging compliant negations.

The Chinese UI uses only Chinese rules; the English UI applies both.
"""

import pytest

from app.compliance.output_guard import (
    check_output,
    mentioned_products,
    needs_no_guarantee_note,
    remove_steering,
)
from app.compliance.policy import Permission
from app.core.i18n import use_locale

ASSESSED = Permission.ASSESSED


@pytest.fixture(autouse=True)
def english():
    with use_locale("en"):
        yield


def violations(text: str, **kw) -> list[str]:
    return check_output(text, kw.pop("permission", ASSESSED), **kw)


@pytest.mark.parametrize(
    "text",
    [
        "This product offers guaranteed returns of about 3%.",
        "Your principal is guaranteed.",
        "It's essentially risk-free.",
        "There is no risk with this one.",
        "You can't lose money here.",
        "It's a safe bet for your savings.",
        "You will definitely earn more than a deposit.",
        "This is principal-protected.",
        "It carries virtually no risk.",
        "I can promise you guaranteed returns on this one.",
    ],
)
def test_prohibited_claims(text):
    assert "O-PROHIBITED_CLAIM" in violations(text)


@pytest.mark.parametrize(
    "text",
    [
        "Bank wealth products do not guarantee principal or returns.",
        "No wealth product is risk-free, including cash management products.",
        "Returns are not guaranteed, and you could lose money.",
        "There's no guaranteed return; a benchmark is not an expected return.",
        "Be wary if a salesperson says it's “risk-free”: that's a misleading claim.",
        "We can't promise you any guaranteed returns.",
        # Compliant replies wrongly blocked in English scenarios G02 / S02
        "Banks and other institutions are not allowed to promise principal protection or "
        "guaranteed returns.",
        "Regulations do not allow me to sell you a wealth management product with a "
        "guaranteed return.",
        "Wealth management products are **non-principal-protected**.",
        "Any product claiming guaranteed returns in the wealth management space would be "
        "non-compliant under current regulations.",
        "If your priority is capital preservation with no risk, your deposits are the closest "
        "match.",
        "Lower risk does not mean no risk.",
        "Principal-protected bank products no longer exist.",
        "By regulation, principal-protected products with guaranteed returns are no longer "
        "issued in the current market.",
    ],
)
def test_negated_or_quoted_claims_pass(text):
    assert violations(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "This is a limited-time offer.",
        "Act now before the quota runs out.",
        "Don't miss out on this one!",
        "It's selling out fast, so buy it today.",
        "Only 3 days left to subscribe.",
        "Hurry, it's your last chance.",
    ],
)
def test_pressure_sales(text):
    assert "O-PRESSURE_SALES" in violations(text)


def test_no_pressure_statement_passes():
    text = "There's no need to hurry; take your time and decide when you're ready."
    assert violations(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "Buy this product and you'll get 2,000 bonus points.",
        "You receive a gift when you purchase Zhian Ready Cash.",
    ],
)
def test_gift_for_purchase(text):
    assert "O-GIFT_FOR_PURCHASE" in violations(text, grounding="Zhian Ready Cash")


def test_tier_benefits_tied_to_assets_pass():
    text = "Adding ¥100,000 or more in total financial assets earns 2,000 points."
    benefits = "reward: 2,000 points for adding ¥100,000 or more"  # benefits tool result
    assert violations(text, facts=benefits) == []


def test_return_pitch():
    text = "I recommend Zhian Steady 1-Year Holding because it has the highest benchmark."
    assert "O-RETURN_PITCH" in violations(text, grounding="Zhian Steady 1-Year Holding")


def test_metric_mixing_sentence_and_paragraph():
    same = "Its benchmark is higher than the 7-day yield of Zhian Ready Cash."
    assert "O-METRIC_MIXING" in violations(same, grounding="Zhian Ready Cash")
    para = (
        "Zhian Ready Cash is a cash management product.\n"
        "The 30-day product's benchmark is higher, so it pays more."
    )
    assert "O-METRIC_MIXING" in violations(para, grounding="Zhian Ready Cash")
    caveat = "A benchmark and a 7-day yield are different measures and can't be compared."
    assert violations(caveat) == []


def test_ungrounded_figure_ignores_decimals_and_allocation_shares():
    grounding = "ZA-F02 PERFORMANCE_BENCHMARK 2.10%–2.70%"
    ok = "Its performance benchmark is 2.10%–2.70%. That is 22.22% of the mix."
    assert violations(ok, grounding=grounding) == []
    bad = "Its performance benchmark is 2.60% to 3.20%."
    assert "O-UNGROUNDED_FIGURE" in violations(bad, grounding=grounding)


@pytest.mark.parametrize(
    "text",
    [
        "To reach a 5% return, you could retake the risk profile.",
        "If you want higher returns, consider raising your risk rating with your RM.",
        "A 5% target needs PR3 products.\nIf things change, you can redo the questionnaire.",
    ],
)
def test_reassessment_steering(text):
    assert "O-REASSESSMENT_STEERING" in violations(text)


def test_complete_profile_reminder_is_not_steering():
    text = "Complete your risk tolerance profile first; then I can match products for you."
    assert violations(text, permission=Permission.ASSESSMENT_REQUIRED) == []


def test_remove_steering_keeps_rest_of_answer():
    text = (
        "Within your C2 rating, benchmarks top out around 3.2%. "
        "To reach 5%, you could retake the risk profile. "
        "Lower risk and higher returns rarely go together."
    )
    redacted = remove_steering(text)
    assert "retake" not in redacted
    assert "rarely go together" in redacted
    assert violations(redacted, grounding="3.2%") == []


def test_unsuitable_recommendation():
    text = "I recommend Zhian Equity Select for your goal."
    found = violations(text, grounding="Zhian Equity Select", risk_rating="C2")
    assert "O-UNSUITABLE_RECOMMENDATION" in found
    limited = "Zhian Equity Select is PR5, above your C2 rating, so you can't buy it."
    assert violations(limited, grounding="Zhian Equity Select", risk_rating="C2") == []


def test_permission_leak_before_assessment():
    text = "I recommend you buy Zhian Steady 30-Day Holding."
    assert violations(text, permission=Permission.ASSESSMENT_REQUIRED) == ["O-PERMISSION_LEAK"]


def test_profile_invitation_is_not_a_recommendation():  # English eval R03
    text = "Once you complete your risk profile, I can find suitable products for you."
    assert violations(text, permission=Permission.ASSESSMENT_REQUIRED) == []
    leak = "The best option for you is a fixed income product."
    assert violations(leak, permission=Permission.ASSESSMENT_REQUIRED) == ["O-PERMISSION_LEAK"]


def test_english_product_names_are_matched():
    assert mentioned_products("Zhian Ready Cash and zhian steady 1-year holding") == {
        "ZA-C01",
        "ZA-F03",
    }


@pytest.mark.parametrize(
    "text",
    [
        "I've connected you with RM Li.",
        "Your relationship manager is now online and handling your request.",
        "I have notified your relationship manager.",
    ],
)
def test_false_handoff_claim(text):
    assert "O-FALSE_HANDOFF_CLAIM" in violations(text)


def test_handoff_summary_shared_passes():
    text = "I've shared your request summary with RM Li. You can reach them on WeCom or by phone."
    assert violations(text) == []


def test_real_institution_english_name():
    assert "O-REAL_INSTITUTION" in violations("CMB Wealth has a similar product.")


def test_no_guarantee_note_trigger():
    assert needs_no_guarantee_note("Which product is risk-free?", "Zhian Ready Cash is PR1.")
    assert not needs_no_guarantee_note(
        "Which product is risk-free?", "None of them guarantee principal; all can lose money."
    )


def test_chinese_rules_still_apply_in_english_mode():
    assert "O-PROHIBITED_CLAIM" in violations("This one is 稳赚 for sure.")


def test_english_rules_off_in_chinese_mode():
    with use_locale("zh"):
        assert check_output("It's risk-free.", ASSESSED) == []


def test_reminder_claim_needs_evidence():
    reply = "Done! I've set a sale reminder for Zhian Fixed-Term 365-Day Series 15."
    grounding = "Zhian Fixed-Term 365-Day Series 15"
    assert "O-FALSE_ACTION_CLAIM" in violations(reply, grounding=grounding)
    assert violations(reply, grounding=grounding + ' "status": "Sale reminder set"') == []


def test_purchase_claim_is_always_false():
    reply = "I've placed the order for ¥10,000 of Zhian Ready Cash."
    assert "O-FALSE_ACTION_CLAIM" in violations(reply, grounding="Zhian Ready Cash")


def test_soft_return_pitch():
    reply = "Zhian Steady Daily Open is the highest-yielding daily-open option in your range."
    assert "O-RETURN_PITCH" in violations(reply, grounding="Zhian Steady Daily Open")
    s01 = (
        "I'll highlight a couple with longer holding periods that allow managers to pursue "
        "somewhat higher returns within the PR2 boundary."
    )
    assert "O-RETURN_PITCH" in violations(s01)
    p05 = "Put the rest in Zhian Steady Daily Open for a bit more return potential."
    assert "O-RETURN_PITCH" in violations(p05, grounding="Zhian Steady Daily Open")
    tradeoff = "Higher returns usually come with more risk and bigger swings."
    assert violations(tradeoff) == []
