"""Unit tests for NAV update policy and sync sanity guard."""

from datetime import date

from app.services.nav_rules import evaluate_sanity_guard, should_update_latest


def test_should_update_latest() -> None:
    d1 = date(2026, 11, 5)
    d2 = date(2026, 11, 6)

    # Stored is None, incoming present -> True
    assert should_update_latest(None, d1) is True

    # Incoming is None -> False
    assert should_update_latest(d1, None) is False
    assert should_update_latest(None, None) is False

    # Incoming newer -> True
    assert should_update_latest(d1, d2) is True

    # Incoming same date -> True (updates NAV for same day if refreshed)
    assert should_update_latest(d2, d2) is True

    # Incoming older -> False (latest NAV never moves backwards)
    assert should_update_latest(d2, d1) is False


def test_evaluate_sanity_guard() -> None:
    # Passing normal case
    is_sane, reason = evaluate_sanity_guard(
        parsed_count=14000,
        active_count=13500,
        min_schemes=5000,
        is_valid_format=True,
    )
    assert is_sane is True
    assert reason is None

    # Invalid format or HTML
    is_sane, reason = evaluate_sanity_guard(
        parsed_count=14000,
        active_count=13500,
        min_schemes=5000,
        is_valid_format=False,
    )
    assert is_sane is False
    assert "Invalid format" in str(reason) or "HTML" in str(reason)

    # Below minimum schemes threshold (5000)
    is_sane, reason = evaluate_sanity_guard(
        parsed_count=4999,
        active_count=0,
        min_schemes=5000,
        is_valid_format=True,
    )
    assert is_sane is False
    assert "below minimum threshold" in str(reason)

    # Below 70% of active funds
    # Active: 10,000, 70% = 7,000; parsed: 6,999
    is_sane, reason = evaluate_sanity_guard(
        parsed_count=6999,
        active_count=10000,
        min_schemes=5000,
        is_valid_format=True,
    )
    assert is_sane is False
    assert "below 70%" in str(reason)

    # Exactly 70% of active funds
    is_sane, reason = evaluate_sanity_guard(
        parsed_count=7000,
        active_count=10000,
        min_schemes=5000,
        is_valid_format=True,
    )
    assert is_sane is True
    assert reason is None
