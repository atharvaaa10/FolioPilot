"""Pure SIP installment execution helpers.

Adheres strictly to CONVENTIONS.md:
- Pure functions only (no DB, no network, no side-effects).
- Deterministic NAV lookup and unit derivation.
"""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.services.transaction_math import resolve_transaction_amounts


def pick_nav(
    due_date: date,
    today: date,
    nav_points: list[tuple[date, Decimal]],
) -> tuple[date, Decimal] | None:
    """Pick the earliest available historical NAV on or after due_date, with nav_date <= today.

    nav_points is a list of (nav_date, nav) tuples.
    Returns (nav_date, nav) or None if no qualifying NAV exists.
    """
    qualifying = [(d, nav) for d, nav in nav_points if due_date <= d <= today]
    if not qualifying:
        return None

    # Earliest date on or after due_date
    return min(qualifying, key=lambda item: item[0])


def build_installment_buy_params(
    installment_id: UUID,
    portfolio_id: UUID,
    fund_id: UUID,
    planned_amount: Decimal,
    nav_date: date,
    nav: Decimal,
) -> dict[str, Any]:
    """Derive BUY transaction fields for an executed SIP installment.

    Uses resolve_transaction_amounts to compute:
    units = round(planned_amount / nav, 4) ROUND_HALF_UP.
    """
    units, resolved_nav, resolved_amount = resolve_transaction_amounts(
        units=None,
        nav=nav,
        amount=planned_amount,
    )

    return {
        "portfolio_id": portfolio_id,
        "fund_id": fund_id,
        "txn_type": "buy",
        "txn_date": nav_date,
        "units": units,
        "nav": resolved_nav,
        "amount": resolved_amount,
        "sip_installment_id": installment_id,
        "notes": None,
    }
