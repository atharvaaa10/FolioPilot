from datetime import UTC, datetime, timedelta

from app.services.refresh_policy import (
    MAX_CLOCK_SKEW_SECONDS,
    RefreshDecision,
    TokenEvaluationState,
    decide_refresh,
)


def test_decide_refresh_unknown() -> None:
    state = TokenEvaluationState(
        token_exists=False,
        is_revoked=False,
        is_family_revoked=False,
        is_expired=False,
        used_at=None,
    )
    decision = decide_refresh(state, now=datetime.now(UTC), grace_seconds=10)
    assert decision == RefreshDecision.REJECT_UNKNOWN


def test_decide_refresh_revoked() -> None:
    # Token directly revoked
    state1 = TokenEvaluationState(
        token_exists=True,
        is_revoked=True,
        is_family_revoked=False,
        is_expired=False,
        used_at=None,
    )
    decision1 = decide_refresh(state1, now=datetime.now(UTC), grace_seconds=10)
    assert decision1 == RefreshDecision.REJECT_REVOKED

    # Family revoked
    state2 = TokenEvaluationState(
        token_exists=True,
        is_revoked=False,
        is_family_revoked=True,
        is_expired=False,
        used_at=None,
    )
    decision2 = decide_refresh(state2, now=datetime.now(UTC), grace_seconds=10)
    assert decision2 == RefreshDecision.REJECT_REVOKED


def test_decide_refresh_expired() -> None:
    state = TokenEvaluationState(
        token_exists=True,
        is_revoked=False,
        is_family_revoked=False,
        is_expired=True,
        used_at=None,
    )
    decision = decide_refresh(state, now=datetime.now(UTC), grace_seconds=10)
    assert decision == RefreshDecision.REJECT_EXPIRED


def test_decide_refresh_rotate() -> None:
    state = TokenEvaluationState(
        token_exists=True,
        is_revoked=False,
        is_family_revoked=False,
        is_expired=False,
        used_at=None,
    )
    decision = decide_refresh(state, now=datetime.now(UTC), grace_seconds=10)
    assert decision == RefreshDecision.ROTATE


def test_decide_refresh_grace_reuse() -> None:
    now = datetime(2026, 11, 6, 12, 0, 10, tzinfo=UTC)
    used_at = now - timedelta(seconds=4)  # 4 seconds ago <= 10s grace
    state = TokenEvaluationState(
        token_exists=True,
        is_revoked=False,
        is_family_revoked=False,
        is_expired=False,
        used_at=used_at,
    )
    decision = decide_refresh(state, now=now, grace_seconds=10)
    assert decision == RefreshDecision.GRACE_REUSE


def test_decide_refresh_clock_skew_at_tolerance() -> None:
    """Verify used_at exactly at MAX_CLOCK_SKEW_SECONDS (2.0s) in future is GRACE_REUSE."""
    now = datetime(2026, 11, 6, 12, 0, 10, tzinfo=UTC)
    used_at = now + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS)  # Exactly -2.0s delta
    state = TokenEvaluationState(
        token_exists=True,
        is_revoked=False,
        is_family_revoked=False,
        is_expired=False,
        used_at=used_at,
    )
    decision = decide_refresh(state, now=now, grace_seconds=10)
    assert decision == RefreshDecision.GRACE_REUSE


def test_decide_refresh_clock_skew_beyond_tolerance_revokes_family() -> None:
    """Verify used_at past MAX_CLOCK_SKEW_SECONDS in future fails safe to REVOKE_FAMILY."""
    now = datetime(2026, 11, 6, 12, 0, 10, tzinfo=UTC)
    used_at = now + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS, milliseconds=1)  # -2.001s delta
    state = TokenEvaluationState(
        token_exists=True,
        is_revoked=False,
        is_family_revoked=False,
        is_expired=False,
        used_at=used_at,
    )
    decision = decide_refresh(state, now=now, grace_seconds=10)
    assert decision == RefreshDecision.REVOKE_FAMILY


def test_decide_refresh_grace_boundary_at_limit() -> None:
    """Verify used_at exactly at grace_seconds limit (10.0s ago) is permitted as GRACE_REUSE."""
    now = datetime(2026, 11, 6, 12, 0, 10, tzinfo=UTC)
    used_at = now - timedelta(seconds=10)
    state = TokenEvaluationState(
        token_exists=True,
        is_revoked=False,
        is_family_revoked=False,
        is_expired=False,
        used_at=used_at,
    )
    decision = decide_refresh(state, now=now, grace_seconds=10)
    assert decision == RefreshDecision.GRACE_REUSE


def test_decide_refresh_revoke_family_on_reuse_past_grace() -> None:
    """Verify used_at beyond grace_seconds triggers REVOKE_FAMILY."""
    now = datetime(2026, 11, 6, 12, 0, 10, tzinfo=UTC)
    used_at = now - timedelta(seconds=10, milliseconds=1)  # 10.001s ago > 10s grace
    state = TokenEvaluationState(
        token_exists=True,
        is_revoked=False,
        is_family_revoked=False,
        is_expired=False,
        used_at=used_at,
    )
    decision = decide_refresh(state, now=now, grace_seconds=10)
    assert decision == RefreshDecision.REVOKE_FAMILY
