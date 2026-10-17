"""金融计算基准用例，对应 docs/EVALUATION_PLAN.md §2。"""

from decimal import Decimal as D

import pytest

from app.calculations.core import (
    CalculationError,
    FeeMethod,
    compound_future_value,
    growth_path,
    inflation_adjusted_value,
    net_investment_proceeds,
    periodic_investment_future_value,
    present_value,
    redemption_fee_rate,
    simple_interest,
    subscription_fee,
    to_cents,
)


def test_annual_compound():
    assert to_cents(compound_future_value(D("1000000"), D("0.05"), 10)) == D("1628894.63")


def test_monthly_compounding_exceeds_annual():
    monthly = to_cents(compound_future_value(D("1000000"), D("0.05"), 10, periods_per_year=12))
    assert monthly == D("1647009.50")
    assert monthly > D("1628894.63")


def test_present_value_inverts_future_value():
    fv = compound_future_value(D("1000000"), D("0.05"), 10)
    assert to_cents(present_value(fv, D("0.05"), 10)) == D("1000000.00")


def test_simple_interest():
    assert to_cents(simple_interest(D("1000000"), D("0.03"), 2)) == D("60000.00")


def test_monthly_periodic_investment():
    fv = periodic_investment_future_value(D("1000"), D("0.06"), 1, periods_per_year=12)
    assert to_cents(fv) == D("12335.56")


def test_periodic_investment_at_start_is_larger():
    end = periodic_investment_future_value(D("1000"), D("0.06"), 1)
    start = periodic_investment_future_value(D("1000"), D("0.06"), 1, at_period_start=True)
    assert to_cents(start) == to_cents(end * D("1.005"))


def test_periodic_investment_zero_rate():
    assert periodic_investment_future_value(D("1000"), D("0"), 2) == D("24000")


def test_inflation_adjusted():
    assert to_cents(inflation_adjusted_value(D("1000000"), D("0.02"), 10)) == D("820348.30")


def test_negative_return():
    assert to_cents(compound_future_value(D("1000000"), D("-0.05"), 1)) == D("950000.00")


def test_zero_rate_and_zero_years():
    assert compound_future_value(D("1000000"), D("0"), 5) == D("1000000")
    assert compound_future_value(D("1000000"), D("0.05"), 0) == D("1000000")


def test_growth_path_matches_closed_form():
    path = growth_path(D("1000000"), D("0.05"), 10)
    assert len(path) == 11
    assert path[0] == D("1000000")
    assert to_cents(path[-1]) == D("1628894.63")


def test_growth_path_with_contributions_matches_annuity():
    path = growth_path(D("0"), D("0.06"), 1, periods_per_year=12, periodic_payment=D("1000"))
    assert to_cents(path[-1]) == D("12335.56")


def test_subscription_fee_external():
    fee, net = subscription_fee(D("100000"), D("0.003"), FeeMethod.EXTERNAL)
    assert (fee, net) == (D("299.10"), D("99700.90"))


def test_subscription_fee_internal():
    fee, net = subscription_fee(D("100000"), D("0.003"), FeeMethod.INTERNAL)
    assert (fee, net) == (D("300.00"), D("99700.00"))


def test_redemption_fee_tiers():
    tiers = [(7, D("0.015")), (30, D("0.005")), (None, D("0"))]
    assert redemption_fee_rate(5, tiers) == D("0.015")
    assert redemption_fee_rate(7, tiers) == D("0.005")
    assert redemption_fee_rate(30, tiers) == D("0")


def test_net_proceeds_no_double_counting():
    result = net_investment_proceeds(
        D("100000"), holding_period_return=D("0.02"), subscription_fee_rate=D("0.003")
    )
    assert result["net_subscription"] == D("99700.90")
    assert result["gross_redemption_value"] == D("101694.92")
    assert result["net_proceeds"] == D("101694.92")
    assert result["profit"] == D("1694.92")


@pytest.mark.parametrize(
    "call",
    [
        lambda: compound_future_value(D("-1"), D("0.05"), 1),
        lambda: compound_future_value(D("1000"), D("5"), 1),  # 5% 误写成 5
        lambda: compound_future_value(D("1000"), D("-1"), 1),
        lambda: compound_future_value(D("1000"), D("0.05"), -1),
        lambda: compound_future_value(D("1000"), D("0.05"), 1, periods_per_year=3),
        lambda: subscription_fee(D("1000"), D("1.5")),
        lambda: redemption_fee_rate(-1, [(None, D("0"))]),
        lambda: redemption_fee_rate(3, [(7, D("0.01"))]),
    ],
)
def test_invalid_inputs_raise(call):
    with pytest.raises(CalculationError):
        call()
