"""Transaction ledger validation, ordering, and average-cost derived positions/holdings."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from app.core.errors import InsufficientUnitsError, LedgerInconsistentError

UNITS_QUANT = Decimal("0.0001")
NAV_QUANT = Decimal("0.00000001")
AMOUNT_QUANT = Decimal("0.01")


@dataclass(frozen=True)
class DerivedHolding:
    """Calculated holding for a fund derived from the append-only ledger."""

    fund_id: UUID
    units: Decimal
    avg_cost: Decimal
    cost_basis: Decimal
    total_bought: Decimal
    total_sold: Decimal
    first_txn_date: date
    last_txn_date: date
    txn_count: int
    is_closed: bool


def ledger_sort_key(txn: Any) -> tuple[date, int, datetime, str]:
    """Deterministic ordering key for transactions:

    1. txn_date ASC
    2. txn_type rank: buy/dividend_reinvest (0) before sell (1) on the same date
    3. created_at ASC (or min datetime if unpersisted)
    4. id ASC (or empty string if unpersisted)
    """
    txn_type = str(getattr(txn, "txn_type", "")).lower()
    type_rank = 0 if txn_type in ("buy", "dividend_reinvest") else 1
    created_at = getattr(txn, "created_at", None) or datetime.min.replace(tzinfo=UTC)
    txn_id = str(getattr(txn, "id", "") or "")
    return (txn.txn_date, type_rank, created_at, txn_id)


def validate_ledger(
    transactions: list[Any],
    mutation_type: str = "add",
    target_txn_id: str | None = None,
) -> None:
    """Validate that transactions never result in negative units for any fund.

    Applies deterministic tie-breaking sort order before evaluating.
    Raises:
    - InsufficientUnitsError (409) if a new sell exceeds available balance.
    - LedgerInconsistentError (409) if an edit or deletion breaks a downstream sell.
    """
    sorted_txns = sorted(transactions, key=ledger_sort_key)
    units_by_fund: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))

    for txn in sorted_txns:
        fund_id = txn.fund_id
        txn_type = str(getattr(txn, "txn_type", "")).lower()
        txn_id_str = str(getattr(txn, "id", "") or "")

        if txn_type in ("buy", "dividend_reinvest"):
            units_by_fund[fund_id] += txn.units
        elif txn_type == "sell":
            available = units_by_fund[fund_id]
            if available < txn.units:
                # If adding a new sell and this is that sell, raise INSUFFICIENT_UNITS
                if mutation_type == "add" and (
                    target_txn_id is None or txn_id_str == target_txn_id
                ):
                    raise InsufficientUnitsError(
                        f"Insufficient units: cannot sell {txn.units} units of fund {fund_id} "
                        f"on {txn.txn_date} (available balance is {available})",
                        details={"available_units": str(available), "date": str(txn.txn_date)},
                    )
                # Otherwise an edit or deletion caused a negative balance downstream
                raise LedgerInconsistentError(
                    f"Ledger inconsistent: fund {fund_id} balance becomes negative "
                    f"({available - txn.units}) on {txn.txn_date}",
                    details={
                        "fund": str(fund_id),
                        "fund_id": str(fund_id),
                        "date": str(txn.txn_date),
                    },
                )
            units_by_fund[fund_id] -= txn.units


def compute_holdings(transactions: list[Any]) -> dict[UUID, DerivedHolding]:
    """Derive holdings for all funds from ledger transactions using average cost method.

    Returns dict mapping fund_id to DerivedHolding.
    """
    validate_ledger(transactions)
    sorted_txns = sorted(transactions, key=ledger_sort_key)

    txns_by_fund: dict[UUID, list[Any]] = defaultdict(list)
    for txn in sorted_txns:
        txns_by_fund[txn.fund_id].append(txn)

    holdings: dict[UUID, DerivedHolding] = {}

    for fund_id, fund_txns in txns_by_fund.items():
        running_units = Decimal("0")
        running_cost = Decimal("0")
        total_bought = Decimal("0")
        total_sold = Decimal("0")

        first_txn_date = fund_txns[0].txn_date
        last_txn_date = fund_txns[-1].txn_date
        txn_count = len(fund_txns)

        for txn in fund_txns:
            txn_type = str(getattr(txn, "txn_type", "")).lower()
            if txn_type in ("buy", "dividend_reinvest"):
                running_units += txn.units
                running_cost += txn.amount
                total_bought += txn.amount
            elif txn_type == "sell":
                total_sold += txn.amount
                if running_units > Decimal("0"):
                    avg_cost_val = running_cost / running_units
                else:
                    avg_cost_val = Decimal("0")

                cost_of_sold = (txn.units * avg_cost_val).quantize(
                    AMOUNT_QUANT, rounding=ROUND_HALF_UP
                )
                running_cost -= cost_of_sold
                running_units -= txn.units

                if running_units == Decimal("0"):
                    running_cost = Decimal("0")

        # Quantize outputs
        units_out = running_units.quantize(UNITS_QUANT, rounding=ROUND_HALF_UP)
        cost_basis_out = max(
            Decimal("0.00"), running_cost.quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
        )
        if units_out > Decimal("0"):
            avg_cost_out = (running_cost / running_units).quantize(
                UNITS_QUANT, rounding=ROUND_HALF_UP
            )
        else:
            avg_cost_out = Decimal("0.0000")

        bought_out = total_bought.quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
        sold_out = total_sold.quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
        is_closed = units_out == Decimal("0")

        holdings[fund_id] = DerivedHolding(
            fund_id=fund_id,
            units=units_out,
            avg_cost=avg_cost_out,
            cost_basis=cost_basis_out,
            total_bought=bought_out,
            total_sold=sold_out,
            first_txn_date=first_txn_date,
            last_txn_date=last_txn_date,
            txn_count=txn_count,
            is_closed=is_closed,
        )

    return holdings


def compute_realized_gain(transactions: list[Any]) -> Decimal:
    """Internal helper to calculate realized gain using weighted average cost basis.

    Validated against worked example: sell of 30 units after 150 units costing 8000.00
    realizes 500.00 when proceeds are 2100.00.
    """
    sorted_txns = sorted(transactions, key=ledger_sort_key)
    running_units = Decimal("0")
    running_cost = Decimal("0")
    realized_gain = Decimal("0")

    for txn in sorted_txns:
        txn_type = getattr(txn, "txn_type", "").upper()
        if txn_type == "BUY":
            running_units += txn.units
            running_cost += txn.amount
        elif txn_type == "SELL":
            if running_units > Decimal("0"):
                current_avg_nav = running_cost / running_units
            else:
                current_avg_nav = Decimal("0")

            cost_basis_sold = (txn.units * current_avg_nav).quantize(
                AMOUNT_QUANT, rounding=ROUND_HALF_UP
            )
            gain = txn.amount - cost_basis_sold
            realized_gain += gain
            running_units -= txn.units
            running_cost -= cost_basis_sold

            if running_units == Decimal("0"):
                running_cost = Decimal("0")

    return realized_gain.quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
