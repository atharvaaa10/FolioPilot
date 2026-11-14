"""Unit tests and Hypothesis property-based tests for pure XIRR solver."""

from datetime import date, timedelta
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.xirr import CashFlow, net_flows, solve_xirr


def test_example_a_closed_form_1() -> None:
    """-1000 on 2025-01-01, -1000 on 2026-01-01, +2310 on 2027-01-01 -> 0.100000 exactly."""
    flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2026, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2027, 1, 1), amount=Decimal("2310.00")),
    ]
    res = solve_xirr(flows)
    assert res.rate == "0.100000"
    assert res.reason is None
    assert res.ambiguous is False
    assert res.short_period is False


def test_example_a_closed_form_2() -> None:
    """-1000 on 2025-01-01 and +1100 on 2026-01-01 -> 0.100000."""
    flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2026, 1, 1), amount=Decimal("1100.00")),
    ]
    res = solve_xirr(flows)
    assert res.rate == "0.100000"
    assert res.reason is None
    assert res.ambiguous is False


def test_example_a_closed_form_3() -> None:
    """-1000 on 2025-01-01 and +900 on 2026-01-01 -> -0.100000."""
    flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2026, 1, 1), amount=Decimal("900.00")),
    ]
    res = solve_xirr(flows)
    assert res.rate == "-0.100000"
    assert res.reason is None
    assert res.ambiguous is False


def test_example_a_closed_form_leap_year() -> None:
    """-1000 on 2024-01-01 and +1210 on 2025-12-31 (730 days) -> 0.100000."""
    flows = [
        CashFlow(flow_date=date(2024, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2025, 12, 31), amount=Decimal("1210.00")),
    ]
    res = solve_xirr(flows)
    assert res.rate == "0.100000"
    assert res.reason is None
    assert res.ambiguous is False


def test_example_a_multiple_roots() -> None:
    """Multiple roots: -1000 on 2025-01-01, +2300 on 2026-01-01, -1320 on 2027-01-01.

    Roots are 10% and 20%; result selects smallest |r| -> 0.100000 with ambiguous = True.
    """
    flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2026, 1, 1), amount=Decimal("2300.00")),
        CashFlow(flow_date=date(2027, 1, 1), amount=Decimal("-1320.00")),
    ]
    res = solve_xirr(flows)
    assert res.rate == "0.100000"
    assert res.ambiguous is True
    assert res.reason is None


def test_reason_ordering_no_transactions() -> None:
    """Empty flows return NO_TRANSACTIONS."""
    res = solve_xirr([])
    assert res.reason == "NO_TRANSACTIONS"
    assert res.rate is None


def test_reason_ordering_no_nav_data() -> None:
    """Open positions exist but none has a live NAV and there are no closed flows -> NO_NAV_DATA."""
    flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
    ]
    res = solve_xirr(
        flows,
        has_open_positions=True,
        has_live_nav=False,
        closed_flows_present=False,
    )
    assert res.reason == "NO_NAV_DATA"
    assert res.rate is None


def test_reason_ordering_insufficient_flows_single_date() -> None:
    """Single date after netting -> INSUFFICIENT_FLOWS."""
    flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("500.00")),
    ]
    res = solve_xirr(flows)
    assert res.reason == "INSUFFICIENT_FLOWS"
    assert res.rate is None


def test_reason_ordering_insufficient_flows_all_outflows() -> None:
    """All negative flows -> INSUFFICIENT_FLOWS."""
    flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2026, 1, 1), amount=Decimal("-500.00")),
    ]
    res = solve_xirr(flows)
    assert res.reason == "INSUFFICIENT_FLOWS"
    assert res.rate is None


def test_reason_ordering_period_too_short() -> None:
    """Span < 30 days -> PERIOD_TOO_SHORT."""
    flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2025, 1, 20), amount=Decimal("1050.00")),
    ]
    res = solve_xirr(flows)
    assert res.reason == "PERIOD_TOO_SHORT"
    assert res.rate is None
    assert res.short_period is True


def test_short_period_flag_between_30_and_365_days() -> None:
    """Span between 30 and 365 days produces a rate with short_period = True."""
    flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2025, 7, 1), amount=Decimal("1050.00")),
    ]
    res = solve_xirr(flows)
    assert res.rate is not None
    assert res.reason is None
    assert res.short_period is True


def test_net_flows_combines_same_day() -> None:
    """net_flows aggregates amounts on identical dates and omits net zeros."""
    raw = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-500.00")),
        CashFlow(flow_date=date(2025, 1, 2), amount=Decimal("200.00")),
        CashFlow(flow_date=date(2025, 1, 2), amount=Decimal("-200.00")),  # Nets to zero
        CashFlow(flow_date=date(2025, 1, 3), amount=Decimal("1700.00")),
    ]
    netted = net_flows(raw)
    assert len(netted) == 2
    assert netted[0] == CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1500.00"))
    assert netted[1] == CashFlow(flow_date=date(2025, 1, 3), amount=Decimal("1700.00"))


# ==============================================================================
# Hypothesis Property-Based Tests
# ==============================================================================


@given(
    scale=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100.0"), places=2),
)
@settings(max_examples=30)
def test_hypothesis_scaling_invariance(scale: Decimal) -> None:
    """XIRR is unchanged when all cash flow amounts are multiplied by a positive constant."""
    base_flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2026, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2027, 1, 1), amount=Decimal("2310.00")),
    ]
    scaled_flows = [
        CashFlow(flow_date=f.flow_date, amount=(f.amount * scale).quantize(Decimal("0.01")))
        for f in base_flows
    ]
    base_res = solve_xirr(base_flows)
    scaled_res = solve_xirr(scaled_flows)
    assert base_res.rate == scaled_res.rate


@given(shift_days=st.integers(min_value=-365, max_value=365))
@settings(max_examples=30)
def test_hypothesis_time_shift_invariance(shift_days: int) -> None:
    """XIRR is unchanged when all flow dates shift by the same number of days."""
    delta = timedelta(days=shift_days)
    base_flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2026, 1, 1), amount=Decimal("1100.00")),
    ]
    shifted_flows = [CashFlow(flow_date=f.flow_date + delta, amount=f.amount) for f in base_flows]
    base_res = solve_xirr(base_flows)
    shifted_res = solve_xirr(shifted_flows)
    assert base_res.rate == shifted_res.rate


def test_hypothesis_zero_flows_invariance() -> None:
    """Adding zero cash flows does not change the XIRR result."""
    base_flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2026, 1, 1), amount=Decimal("1100.00")),
    ]
    with_zeros = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-1000.00")),
        CashFlow(flow_date=date(2025, 6, 1), amount=Decimal("0.00")),
        CashFlow(flow_date=date(2026, 1, 1), amount=Decimal("1100.00")),
    ]
    assert solve_xirr(base_flows).rate == solve_xirr(with_zeros).rate


def test_hypothesis_netting_invariance() -> None:
    """Netting flows on the same date produces the identical XIRR result."""
    split_flows = [
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-600.00")),
        CashFlow(flow_date=date(2025, 1, 1), amount=Decimal("-400.00")),
        CashFlow(flow_date=date(2026, 1, 1), amount=Decimal("700.00")),
        CashFlow(flow_date=date(2026, 1, 1), amount=Decimal("400.00")),
    ]
    netted_flows = net_flows(split_flows)
    assert solve_xirr(split_flows).rate == solve_xirr(netted_flows).rate
