"""Pure business logic for refresh token rotation, grace windows, and reuse detection.

Adheres strictly to CONVENTIONS.md: pure functions, no DB or framework dependencies.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

MAX_CLOCK_SKEW_SECONDS: float = 2.0


class RefreshDecision(StrEnum):
    """Outcomes of refresh token evaluation."""

    ROTATE = "ROTATE"
    GRACE_REUSE = "GRACE_REUSE"
    REVOKE_FAMILY = "REVOKE_FAMILY"
    REJECT_EXPIRED = "REJECT_EXPIRED"
    REJECT_UNKNOWN = "REJECT_UNKNOWN"
    REJECT_REVOKED = "REJECT_REVOKED"


@dataclass(frozen=True)
class TokenEvaluationState:
    """Snapshot of refresh token state for pure decision making."""

    token_exists: bool
    is_revoked: bool
    is_family_revoked: bool
    is_expired: bool
    used_at: datetime | None


def decide_refresh(
    state: TokenEvaluationState,
    *,
    now: datetime,
    grace_seconds: int = 10,
) -> RefreshDecision:
    """Pure policy engine determining the exact action for a refresh request.

    - ROTATE: Token is active, unexpired, and never used. Rotate cleanly.
    - GRACE_REUSE: Token was used recently within `grace_seconds` and within
      `MAX_CLOCK_SKEW_SECONDS` negative skew. Issue access token only.
    - REVOKE_FAMILY: Token was used outside `grace_seconds` or ahead of clock by
      more than `MAX_CLOCK_SKEW_SECONDS`. Potential token theft, revoke family.
    - REJECT_EXPIRED: Token expired.
    - REJECT_REVOKED: Token or family was already revoked.
    - REJECT_UNKNOWN: Token does not exist.
    """
    if not state.token_exists:
        return RefreshDecision.REJECT_UNKNOWN

    if state.is_revoked or state.is_family_revoked:
        return RefreshDecision.REJECT_REVOKED

    if state.is_expired:
        return RefreshDecision.REJECT_EXPIRED

    if state.used_at is None:
        return RefreshDecision.ROTATE

    # Token was already used. Check grace period.
    # Allow small negative delta up to MAX_CLOCK_SKEW_SECONDS (clock skew tolerance).
    time_since_use = (now - state.used_at).total_seconds()
    if -MAX_CLOCK_SKEW_SECONDS <= time_since_use <= grace_seconds:
        return RefreshDecision.GRACE_REUSE

    return RefreshDecision.REVOKE_FAMILY
