"""Pure value-over-time series computation and date sampling.

Follows CONVENTIONS.md:
- O(T + D) single chronological sweep over ledger transactions and sampled dates.
- Prices resolved from union of:
  1. Official NAV history rows (is_official=True)
  2. Fund latest_nav at latest_nav_date (is_official=True)
  3. User ledger transaction NAVs (is_official=False)
  On identical dates, official NAV strictly wins.
- Quantization: units * price quantized to 0.01 per fund, then summed.
- Sampled steps per range capped at MAX_SERIES_POINTS (400), last date always included.
"""

import bisect
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from app.core.constants import MAX_SERIES_POINTS
from app.services.ledger import ledger_sort_key

AMOUNT_QUANT = Decimal("0.01")
NAV_QUANT = Decimal("0.00000001")


@dataclass(frozen=True)
class PricePoint:
    """Historical NAV price point for a fund."""

    fund_id: UUID
    nav_date: date
    nav: Decimal
    is_official: bool


@dataclass(frozen=True)
class SeriesPoint:
    """Single date point in the value series."""

    date: str
    value: str
    cost_basis: str


@dataclass(frozen=True)
class ValueSeriesResult:
    """Complete value-over-time series result."""

    range: str
    start_date: str
    end_date: str
    points: list[SeriesPoint]


def sample_dates(
    range_str: str,
    first_txn_date: date | None,
    today_ist: date,
) -> list[date]:
    """Generate sampled calendar dates for the specified range.

    Ranges:
    - 1m: 30 days back, daily step
    - 6m: 182 days back, 3-day step
    - 1y: 365 days back, weekly (7-day) step
    - 3y: 3*365 days back, weekly (7-day) step
    - 5y: 5*365 days back, 14-day step
    - max: back to first_txn_date, 30-day step

    The series starts at max(range start, first transaction date) and ends today (IST).
    Step is dynamically increased if needed to guarantee at most MAX_SERIES_POINTS.
    The last date (today_ist) is always included.
    Dates before first_txn_date produce no point.
    """
    if first_txn_date is None or first_txn_date > today_ist:
        return []

    r = range_str.lower()
    if r == "1m":
        range_start = today_ist - timedelta(days=30)
        default_step = 1
    elif r == "6m":
        range_start = today_ist - timedelta(days=182)
        default_step = 3
    elif r == "1y":
        range_start = today_ist - timedelta(days=365)
        default_step = 7
    elif r == "3y":
        range_start = today_ist - timedelta(days=3 * 365)
        default_step = 7
    elif r == "5y":
        range_start = today_ist - timedelta(days=5 * 365)
        default_step = 14
    elif r == "max":
        range_start = first_txn_date
        default_step = 30
    else:
        # Default fallback to 1y
        range_start = today_ist - timedelta(days=365)
        default_step = 7

    start_date = max(range_start, first_txn_date)
    total_days = (today_ist - start_date).days
    if total_days < 0:
        return []

    step = default_step
    estimated_points = (total_days // step) + 2
    if estimated_points > MAX_SERIES_POINTS:
        step = math.ceil(total_days / (MAX_SERIES_POINTS - 1))

    dates: list[date] = []
    curr = start_date
    while curr < today_ist:
        dates.append(curr)
        curr += timedelta(days=step)

    # Last date is always included
    if not dates or dates[-1] != today_ist:
        dates.append(today_ist)

    return dates


def value_series(
    transactions: list[Any],
    price_points: list[PricePoint],
    dates: list[date],
) -> list[SeriesPoint]:
    """Execute single O(T + D) chronological sweep to compute value and cost basis series."""
    if not dates or not transactions:
        return []

    # Filter out dates strictly before the very first transaction date
    sorted_txns = sorted(transactions, key=ledger_sort_key)
    first_txn_date = sorted_txns[0].txn_date
    valid_dates = [d for d in dates if d >= first_txn_date]
    if not valid_dates:
        return []

    # 1. Deduplicate price points per fund: official NAV wins on equal dates
    # Map: fund_id -> dict[date, (is_official, nav)]
    fund_price_dict: dict[UUID, dict[date, tuple[bool, Decimal]]] = defaultdict(dict)

    # Also incorporate user's ledger transaction NAVs (is_official=False)
    for t in sorted_txns:
        if t.nav is not None and t.nav > Decimal("0"):
            nav_val = t.nav.quantize(NAV_QUANT, rounding=ROUND_HALF_UP)
            fund_price_dict[t.fund_id][t.txn_date] = (False, nav_val)

    # Incorporate supplied price points (official NAV history and latest_nav)
    for p in price_points:
        existing = fund_price_dict[p.fund_id].get(p.nav_date)
        if existing is None:
            fund_price_dict[p.fund_id][p.nav_date] = (p.is_official, p.nav)
        else:
            existing_is_official, _ = existing
            # If current is official and existing was not, or both official, current wins
            if p.is_official or not existing_is_official:
                fund_price_dict[p.fund_id][p.nav_date] = (p.is_official, p.nav)

    # Pre-sort price history per fund into parallel lists for O(log P) bisect lookup
    fund_sorted_dates: dict[UUID, list[date]] = {}
    fund_sorted_navs: dict[UUID, list[Decimal]] = {}
    for fid, date_map in fund_price_dict.items():
        sorted_d = sorted(date_map.keys())
        fund_sorted_dates[fid] = sorted_d
        fund_sorted_navs[fid] = [date_map[d][1] for d in sorted_d]

    # 2. Sweep state
    running_units: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0.0000"))
    running_cost: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0.00"))

    points: list[SeriesPoint] = []
    txn_idx = 0
    num_txns = len(sorted_txns)

    for target_date in valid_dates:
        # Advance ledger transactions up to and including target_date
        while txn_idx < num_txns and sorted_txns[txn_idx].txn_date <= target_date:
            txn = sorted_txns[txn_idx]
            fid = txn.fund_id
            ttype = str(getattr(txn, "txn_type", "")).lower()

            if ttype in ("buy", "dividend_reinvest"):
                running_units[fid] += txn.units
                running_cost[fid] += txn.amount
            elif ttype == "sell":
                cur_u = running_units[fid]
                cur_c = running_cost[fid]
                avg_c = (cur_c / cur_u) if cur_u > Decimal("0") else Decimal("0")
                cost_sold = (txn.units * avg_c).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
                running_cost[fid] -= cost_sold
                running_units[fid] -= txn.units
                if running_units[fid] == Decimal("0"):
                    running_cost[fid] = Decimal("0.00")

            txn_idx += 1

        # Value all open positions at target_date
        date_total_value = Decimal("0.00")
        date_total_cost = Decimal("0.00")

        for fid, units in running_units.items():
            if units <= Decimal("0.0000"):
                continue

            cost_basis = max(
                Decimal("0.00"),
                running_cost[fid].quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP),
            )
            date_total_cost += cost_basis

            # Find latest price on or before target_date
            p_dates = fund_sorted_dates.get(fid, [])
            p_navs = fund_sorted_navs.get(fid, [])
            idx = bisect.bisect_right(p_dates, target_date) - 1

            if idx >= 0:
                price = p_navs[idx]
            else:
                # Fallback to average cost if no price point on or before date
                price = (cost_basis / units).quantize(NAV_QUANT, rounding=ROUND_HALF_UP)

            fund_val = (units * price).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
            date_total_value += fund_val

        points.append(
            SeriesPoint(
                date=target_date.isoformat(),
                value=str(date_total_value),
                cost_basis=str(date_total_cost),
            )
        )

    return points
