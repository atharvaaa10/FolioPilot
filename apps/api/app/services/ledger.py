"""Transaction ledger validation, ordering, and average-cost derived positions."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from app.core.errors import InsufficientUnitsError

UNITS_QUANT = Decimal("0.0001")
NAV_QUANT = Decimal("0.00000001")
AMOUNT_QUANT = Decimal("0.01")


@dataclass(frozen=True)
class DerivedPosition:
    """Calculated position for a fund derived from the append-only ledger."""

    fund_id: UUID
    units: Decimal
    avg_nav: Decimal
    total_invested: Decimal
    realized_gain: Decimal


def ledger_sort_key(txn: Any) -> tuple[date, int, datetime, str]:
    """Deterministic ordering key for transactions:

    1. txn_date ASC
    2. txn_type rank: BUY (0) before SELL (1) on the same date
    3. created_at ASC (or min datetime if unpersisted)
    4. id ASC (or empty string if unpersisted)
    """
    type_rank = 0 if getattr(txn, "txn_type", "").upper() == "BUY" else 1
    created_at = getattr(txn, "created_at", None) or datetime.min.replace(tzinfo=UTC)
    txn_id = str(getattr(txn, "id", "") or "")
    return (txn.txn_date, type_rank, created_at, txn_id)


def validate_ledger(transactions: list[Any]) -> None:
    """Validate that transactions never result in negative units for any fund.

    Applies deterministic tie-breaking sort order before evaluating.
    Raises InsufficientUnitsError on violation.
    """
    sorted_txns = sorted(transactions, key=ledger_sort_key)
    units_by_fund: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))

    for txn in sorted_txns:
        fund_id = txn.fund_id
        txn_type = txn.txn_type.upper()

        if txn_type == "BUY":
            units_by_fund[fund_id] += txn.units
        elif txn_type == "SELL":
            available = units_by_fund[fund_id]
            if available < txn.units:
                raise InsufficientUnitsError(
                    f"Insufficient units: cannot sell {txn.units} units of fund {fund_id} "
                    f"on {txn.txn_date} (available balance at this point in ledger is {available})"
                )
            units_by_fund[fund_id] -= txn.units


def compute_positions(transactions: list[Any]) -> dict[UUID, DerivedPosition]:
    """Derive positions for all funds from ledger transactions using average cost method.

    Returns dict mapping fund_id to DerivedPosition.
    """
    validate_ledger(transactions)
    sorted_txns = sorted(transactions, key=ledger_sort_key)

    txns_by_fund: dict[UUID, list[Any]] = defaultdict(list)
    for txn in sorted_txns:
        txns_by_fund[txn.fund_id].append(txn)

    positions: dict[UUID, DerivedPosition] = {}

    for fund_id, fund_txns in txns_by_fund.items():
        running_units = Decimal("0")
        total_invested = Decimal("0")
        realized_gain = Decimal("0")

        for txn in fund_txns:
            txn_type = txn.txn_type.upper()
            if txn_type == "BUY":
                running_units += txn.units
                total_invested += txn.amount
            elif txn_type == "SELL":
                if running_units > Decimal("0"):
                    current_avg_nav = total_invested / running_units
                else:
                    current_avg_nav = Decimal("0")

                cost_basis_sold = (txn.units * current_avg_nav).quantize(
                    AMOUNT_QUANT, rounding=ROUND_HALF_UP
                )
                gain = txn.amount - cost_basis_sold
                realized_gain += gain
                running_units -= txn.units
                total_invested -= cost_basis_sold

                if running_units == Decimal("0"):
                    total_invested = Decimal("0")

        # Quantize results
        units_out = running_units.quantize(UNITS_QUANT, rounding=ROUND_HALF_UP)
        invested_out = max(
            Decimal("0.00"), total_invested.quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
        )
        if units_out > Decimal("0"):
            avg_nav_out = (total_invested / running_units).quantize(
                NAV_QUANT, rounding=ROUND_HALF_UP
            )
        else:
            avg_nav_out = Decimal("0.00000000")
        gain_out = realized_gain.quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)

        positions[fund_id] = DerivedPosition(
            fund_id=fund_id,
            units=units_out,
            avg_nav=avg_nav_out,
            total_invested=invested_out,
            realized_gain=gain_out,
        )

    return positions
