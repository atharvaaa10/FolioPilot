"""Pure planning engine for Excel transaction imports.

Handles:
- Bulk fund resolution matching
- Multiset duplicate detection rule
- SIP overlap detection warning
- Pure iterative ledger conflict resolution
- Status assignment and deterministic plan_fingerprint generation
"""

import datetime as dt
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.constants import MAX_TRANSACTIONS_PER_PORTFOLIO
from app.services.import_rows import NormalizedRow


@dataclass(frozen=True)
class PlannedRow:
    """Fully planned row with resolved fund, final status, and audit messages."""

    row_number: int
    status: str  # ok, warning, duplicate, error
    fund_id: UUID | None
    fund: Any | None  # Fund master object or dict
    fund_name_in_file: str | None
    txn_type: str | None
    txn_date: dt.date | None
    units: Decimal | None
    nav: Decimal | None
    amount: Decimal | None
    notes: str | None
    raw: dict[str, str]
    messages: list[dict[str, Any]]


@dataclass(frozen=True)
class PlanResult:
    """Complete preview plan result."""

    rows: list[PlannedRow]
    rows_total: int
    rows_ok: int
    rows_warning: int
    rows_duplicate: int
    rows_error: int
    will_import: int
    plan_fingerprint: str
    funds_count: int
    date_range: dict[str, str] | None
    totals: dict[str, str]
    blocking_errors: list[str]


@dataclass(frozen=True)
class ExistingSip:
    """Active or scheduled SIP summary for overlap detection."""

    fund_id: UUID
    start_date: dt.date
    end_date: dt.date | None


@dataclass(frozen=True)
class ExistingTransactionItem:
    """Minimal representation of an existing ledger transaction."""

    id: UUID
    fund_id: UUID
    txn_type: str
    txn_date: dt.date
    units: Decimal
    nav: Decimal
    amount: Decimal
    created_at: dt.datetime


def compute_plan_fingerprint(will_import_rows: list[PlannedRow]) -> str:
    """Compute deterministic SHA-256 fingerprint over sorted will_import rows."""
    sorted_rows = sorted(will_import_rows, key=lambda r: r.row_number)
    items: list[str] = []
    for r in sorted_rows:
        notes_str = r.notes if r.notes is not None else ""
        units_str = f"{r.units:.4f}" if r.units is not None else ""
        nav_str = f"{r.nav:.8f}" if r.nav is not None else ""
        amount_str = f"{r.amount:.2f}" if r.amount is not None else ""
        item_str = (
            f"{r.row_number}|{r.fund_id}|{r.txn_type}|{r.txn_date}|"
            f"{units_str}|{nav_str}|{amount_str}|{notes_str}"
        )
        items.append(item_str)
    payload = "\n".join(items).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def plan_import(
    normalized_rows: list[NormalizedRow],
    fund_lookup_by_code: dict[int, Any],
    fund_lookup_by_isin: dict[str, list[Any]],
    existing_ledger_by_fund: dict[UUID, list[ExistingTransactionItem]],
    existing_duplicate_counts: dict[tuple[UUID, dt.date, str, Decimal, Decimal], int],
    active_sips: list[ExistingSip],
    current_portfolio_txn_count: int = 0,
    max_transactions_limit: int = MAX_TRANSACTIONS_PER_PORTFOLIO,
) -> PlanResult:
    """Plan prospective import rows purely without DB side effects."""
    # Step 1: Fund resolution
    resolved_rows: list[tuple[NormalizedRow, Any | None, list[dict[str, Any]]]] = []

    for r in normalized_rows:
        msgs = list(r.messages)
        matched_fund: Any | None = None

        if r.scheme_code is not None and r.isin is not None:
            fund_by_code = fund_lookup_by_code.get(r.scheme_code)
            funds_by_isin = fund_lookup_by_isin.get(r.isin, [])

            if fund_by_code is None:
                msgs.append(
                    {
                        "level": "error",
                        "code": "UNKNOWN_FUND",
                        "field": "scheme_code",
                        "message": f"Fund with scheme code {r.scheme_code} not found in master",
                    }
                )
            elif not any(f.id == fund_by_code.id for f in funds_by_isin):
                msgs.append(
                    {
                        "level": "error",
                        "code": "FUND_CODE_ISIN_MISMATCH",
                        "field": "isin",
                        "message": f"ISIN {r.isin} does not belong to scheme code {r.scheme_code}",
                    }
                )
            else:
                matched_fund = fund_by_code
        elif r.scheme_code is not None:
            fund_by_code = fund_lookup_by_code.get(r.scheme_code)
            if fund_by_code is None:
                msgs.append(
                    {
                        "level": "error",
                        "code": "UNKNOWN_FUND",
                        "field": "scheme_code",
                        "message": f"Fund with scheme code {r.scheme_code} not found in master",
                    }
                )
            else:
                matched_fund = fund_by_code
        elif r.isin is not None:
            funds_by_isin = fund_lookup_by_isin.get(r.isin, [])
            if not funds_by_isin:
                msgs.append(
                    {
                        "level": "error",
                        "code": "UNKNOWN_FUND",
                        "field": "isin",
                        "message": f"Fund with ISIN {r.isin} not found in master",
                    }
                )
            elif len(funds_by_isin) > 1:
                msgs.append(
                    {
                        "level": "error",
                        "code": "ISIN_AMBIGUOUS",
                        "field": "isin",
                        "message": f"ISIN {r.isin} matches multiple schemes in master",
                    }
                )
            else:
                matched_fund = funds_by_isin[0]

        if matched_fund is not None and not getattr(matched_fund, "is_active", True):
            msgs.append(
                {
                    "level": "warning",
                    "code": "FUND_INACTIVE",
                    "field": "scheme_code",
                    "message": "Fund is inactive in AMFI master",
                }
            )

        resolved_rows.append((r, matched_fund, msgs))

    # Step 2: Multiset Duplicate Detection
    # Duplicate key: (fund_id, txn_date, txn_type, units_4dp, amount_2dp)
    file_key_indices: dict[tuple[UUID, dt.date, str, Decimal, Decimal], list[int]] = {}
    for idx, (r, fund, msgs) in enumerate(resolved_rows):
        has_blocking = any(m["level"] == "error" for m in msgs)
        if (
            not has_blocking
            and fund is not None
            and r.txn_date is not None
            and r.txn_type is not None
            and r.units is not None
            and r.amount is not None
        ):
            key = (
                fund.id,
                r.txn_date,
                r.txn_type.lower(),
                r.units.quantize(Decimal("0.0001")),
                r.amount.quantize(Decimal("0.01")),
            )
            file_key_indices.setdefault(key, []).append(idx)

    duplicate_indices: set[int] = set()
    for key, indices in file_key_indices.items():
        n = len(indices)
        m = existing_duplicate_counts.get(key, 0)
        num_dups = min(n, m)
        for i in range(num_dups):
            dup_idx = indices[i]
            duplicate_indices.add(dup_idx)
            resolved_rows[dup_idx][2].append(
                {
                    "level": "info",
                    "code": "DUPLICATE_IN_LEDGER",
                    "field": None,
                    "message": "Transaction already exists in portfolio ledger",
                }
            )

        # In-file duplicate warning if n > 1
        if n > 1:
            for idx in indices:
                resolved_rows[idx][2].append(
                    {
                        "level": "warning",
                        "code": "DUPLICATE_IN_FILE",
                        "field": None,
                        "message": "Identical transaction occurs multiple times in this file",
                    }
                )

    # Step 3: SIP Overlap Warning
    for idx, (r, fund, msgs) in enumerate(resolved_rows):
        if idx in duplicate_indices or any(m["level"] == "error" for m in msgs):
            continue
        if fund is not None and r.txn_date is not None and r.txn_type == "buy":
            for sip in active_sips:
                if sip.fund_id == fund.id and sip.start_date <= r.txn_date:
                    if sip.end_date is None or sip.end_date >= r.txn_date:
                        msgs.append(
                            {
                                "level": "warning",
                                "code": "POSSIBLE_SIP_OVERLAP",
                                "field": "txn_date",
                                "message": "The app may already generate a buy for this date",
                            }
                        )
                        break

    # Step 4: Iterative Ledger Conflict Resolution
    # Group candidate rows by fund_id
    candidate_indices_by_fund: dict[UUID, list[int]] = {}
    for idx, (r, fund, msgs) in enumerate(resolved_rows):
        if idx in duplicate_indices or any(m["level"] == "error" for m in msgs):
            continue
        if (
            fund is not None
            and r.units is not None
            and r.txn_date is not None
            and r.txn_type is not None
        ):
            candidate_indices_by_fund.setdefault(fund.id, []).append(idx)

    for fund_id, cand_indices in candidate_indices_by_fund.items():
        existing_txns = existing_ledger_by_fund.get(fund_id, [])
        active_candidates = set(cand_indices)

        while True:
            # Build merged chronological timeline
            timeline: list[dict[str, Any]] = []
            for ex in existing_txns:
                timeline.append(
                    {
                        "is_candidate": False,
                        "index": -1,
                        "txn_date": ex.txn_date,
                        "txn_type": ex.txn_type,
                        "units": ex.units,
                        "created_at": ex.created_at,
                        "id": str(ex.id),
                    }
                )
            for c_idx in active_candidates:
                r_cand, _, _ = resolved_rows[c_idx]
                timeline.append(
                    {
                        "is_candidate": True,
                        "index": c_idx,
                        "txn_date": r_cand.txn_date,
                        "txn_type": r_cand.txn_type,
                        "units": r_cand.units,
                        "created_at": dt.datetime.min.replace(tzinfo=dt.UTC),
                        "id": f"row_{r_cand.row_number}",
                    }
                )

            # Sort using standard ledger sorting criteria: (txn_date, type_rank, created_at, id)
            timeline.sort(
                key=lambda item: (
                    item["txn_date"],
                    0 if item["txn_type"] in ("buy", "dividend_reinvest") else 1,
                    item["created_at"],
                    item["id"],
                )
            )

            # Simulate running balance
            running_balance = Decimal("0")
            violation_found = False
            violation_date: dt.date | None = None
            available_at_violation = Decimal("0")

            for item in timeline:
                t_type = item["txn_type"]
                units_val = item["units"]
                if t_type in ("buy", "dividend_reinvest"):
                    running_balance += units_val
                elif t_type == "sell":
                    if running_balance < units_val:
                        violation_found = True
                        violation_date = item["txn_date"]
                        available_at_violation = running_balance
                        break
                    running_balance -= units_val

            if not violation_found or violation_date is None:
                # Valid ledger achieved
                break

            # Find latest candidate sell at or before violation_date
            candidate_sells: list[int] = []
            for idx in active_candidates:
                r_norm = resolved_rows[idx][0]
                if (
                    r_norm.txn_type == "sell"
                    and r_norm.txn_date is not None
                    and r_norm.txn_date <= violation_date
                ):
                    candidate_sells.append(idx)

            if not candidate_sells:
                # No candidate sells can be removed to resolve (existing ledger alone is violated)
                break

            # Pick the latest candidate sell (highest date or highest timeline index)
            candidate_sells.sort(
                key=lambda idx: (
                    resolved_rows[idx][0].txn_date or dt.date.min,
                    resolved_rows[idx][0].row_number,
                )
            )
            failing_candidate_idx = candidate_sells[-1]

            # Mark failing candidate sell as error INSUFFICIENT_UNITS
            resolved_rows[failing_candidate_idx][2].append(
                {
                    "level": "error",
                    "code": "INSUFFICIENT_UNITS",
                    "field": "units",
                    "message": (
                        f"Insufficient units: available balance is {available_at_violation} units "
                        f"on {violation_date}"
                    ),
                    "details": {
                        "available_units": f"{available_at_violation:.4f}",
                        "date": str(violation_date),
                    },
                }
            )
            active_candidates.remove(failing_candidate_idx)

    # Step 5: Assign final status per row and compute metrics
    planned_rows: list[PlannedRow] = []
    rows_ok = 0
    rows_warning = 0
    rows_duplicate = 0
    rows_error = 0
    will_import_rows: list[PlannedRow] = []

    distinct_funds: set[UUID] = set()
    dates: list[dt.date] = []
    buy_amount_total = Decimal("0.00")
    sell_amount_total = Decimal("0.00")

    for idx, (r, fund, msgs) in enumerate(resolved_rows):
        has_error = any(m["level"] == "error" for m in msgs)
        has_warning = any(m["level"] == "warning" for m in msgs)

        if idx in duplicate_indices:
            status = "duplicate"
            rows_duplicate += 1
        elif has_error:
            status = "error"
            rows_error += 1
        elif has_warning:
            status = "warning"
            rows_warning += 1
        else:
            status = "ok"
            rows_ok += 1

        p_row = PlannedRow(
            row_number=r.row_number,
            status=status,
            fund_id=fund.id if fund is not None else None,
            fund=fund,
            fund_name_in_file=r.fund_name_in_file,
            txn_type=r.txn_type,
            txn_date=r.txn_date,
            units=r.units,
            nav=r.nav,
            amount=r.amount,
            notes=r.notes,
            raw=r.raw,
            messages=msgs,
        )
        planned_rows.append(p_row)

        if status in ("ok", "warning"):
            will_import_rows.append(p_row)
            if fund is not None:
                distinct_funds.add(fund.id)
            if r.txn_date is not None:
                dates.append(r.txn_date)
            if r.amount is not None:
                if r.txn_type in ("buy", "dividend_reinvest"):
                    buy_amount_total += r.amount
                elif r.txn_type == "sell":
                    sell_amount_total += r.amount

    will_import_count = len(will_import_rows)
    fingerprint = compute_plan_fingerprint(will_import_rows)

    date_range: dict[str, str] | None = None
    if dates:
        date_range = {
            "from": min(dates).isoformat(),
            "to": max(dates).isoformat(),
        }

    blocking_errors: list[str] = []
    if current_portfolio_txn_count + will_import_count > max_transactions_limit:
        blocking_errors.append("TRANSACTION_LIMIT_REACHED")

    return PlanResult(
        rows=planned_rows,
        rows_total=len(planned_rows),
        rows_ok=rows_ok,
        rows_warning=rows_warning,
        rows_duplicate=rows_duplicate,
        rows_error=rows_error,
        will_import=will_import_count,
        plan_fingerprint=fingerprint,
        funds_count=len(distinct_funds),
        date_range=date_range,
        totals={
            "buy_amount": f"{buy_amount_total:.2f}",
            "sell_amount": f"{sell_amount_total:.2f}",
        },
        blocking_errors=blocking_errors,
    )
