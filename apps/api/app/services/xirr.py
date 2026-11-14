"""Pure XIRR solver for irregular cash flows with terminal portfolio values.

Follows CONVENTIONS.md:
- Float64 is permitted strictly inside this solver module for numerical performance.
- Results are converted to Decimal, quantized to 6 decimal places, and serialized as string.
- Grid-scan sign change detection with bisection refinement for robust root-finding.
- Multiple root detection (ambiguous flag) selecting the root with minimum |r|.
- Verifies |NPV(rate)| <= 1e-6 * sum(|cf|), returning NO_SOLUTION if unverified.
"""

import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core.constants import (
    DAYS_PER_YEAR,
    XIRR_MIN_DAYS,
    XIRR_RATE_MAX,
    XIRR_RATE_MIN,
    XIRR_SHORT_PERIOD_DAYS,
)

RATE_QUANT = Decimal("0.000001")


@dataclass(frozen=True)
class CashFlow:
    """A cash flow on a specific date (negative for outflow, positive for inflow)."""

    flow_date: date
    amount: Decimal


@dataclass(frozen=True)
class XirrResult:
    """Standardized XIRR result object."""

    rate: str | None
    reason: str | None
    short_period: bool
    ambiguous: bool
    flows_count: int
    first_flow_date: str | None
    last_flow_date: str | None
    excluded_funds: int


def net_flows(flows: list[CashFlow]) -> list[CashFlow]:
    """Net multiple cash flows occurring on the same date into a single flow per date.

    Preserves chronological order by flow_date.
    """
    netted_map: dict[date, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for f in flows:
        netted_map[f.flow_date] += f.amount

    # Filter out zero net flows and sort chronologically
    result: list[CashFlow] = []
    for d in sorted(netted_map.keys()):
        amt = netted_map[d]
        if amt != Decimal("0.00"):
            result.append(CashFlow(flow_date=d, amount=amt))
    return result


def _bisection(
    f: Callable[[float], float],
    a: float,
    b: float,
    fa: float,
    max_iter: int = 80,
    tol_x: float = 1e-12,
    tol_f: float = 1e-14,
) -> float:
    """Pure bisection root refinement for bracket [a, b] where f(a) * f(b) <= 0."""
    left = a
    right = b
    f_left = fa

    for _ in range(max_iter):
        mid = 0.5 * (left + right)
        f_mid = f(mid)

        if abs(f_mid) <= tol_f or (right - left) <= tol_x:
            return mid

        if f_left * f_mid < 0.0:
            right = mid
        else:
            left = mid
            f_left = f_mid

    return 0.5 * (left + right)


def solve_xirr(
    flows: list[CashFlow],
    excluded_funds: int = 0,
    has_open_positions: bool = False,
    has_live_nav: bool = False,
    closed_flows_present: bool = False,
) -> XirrResult:
    """Calculate XIRR rate for a collection of dated cash flows and terminal value inflows.

    Reason codes in priority order:
    1. NO_TRANSACTIONS: no flows in scope
    2. NO_NAV_DATA: open positions exist but none has a live NAV and no closed flows
    3. INSUFFICIENT_FLOWS: fewer than 2 distinct dates after netting or no sign change
    4. PERIOD_TOO_SHORT: span between first and last flow date < XIRR_MIN_DAYS
    5. NO_SOLUTION: root cannot be bracketed/verified within tolerance
    """
    # 1. NO_TRANSACTIONS
    if not flows:
        return XirrResult(
            rate=None,
            reason="NO_TRANSACTIONS",
            short_period=False,
            ambiguous=False,
            flows_count=0,
            first_flow_date=None,
            last_flow_date=None,
            excluded_funds=excluded_funds,
        )

    # 2. NO_NAV_DATA
    if has_open_positions and not has_live_nav and not closed_flows_present:
        return XirrResult(
            rate=None,
            reason="NO_NAV_DATA",
            short_period=False,
            ambiguous=False,
            flows_count=len(flows),
            first_flow_date=min(f.flow_date for f in flows).isoformat(),
            last_flow_date=max(f.flow_date for f in flows).isoformat(),
            excluded_funds=excluded_funds,
        )

    # 3. INSUFFICIENT_FLOWS: Net flows by date
    netted = net_flows(flows)
    if len(netted) < 2:
        first_d = flows[0].flow_date if flows else None
        last_d = flows[-1].flow_date if flows else None
        return XirrResult(
            rate=None,
            reason="INSUFFICIENT_FLOWS",
            short_period=False,
            ambiguous=False,
            flows_count=len(flows),
            first_flow_date=first_d.isoformat() if first_d else None,
            last_flow_date=last_d.isoformat() if last_d else None,
            excluded_funds=excluded_funds,
        )

    first_date = netted[0].flow_date
    last_date = netted[-1].flow_date
    span_days = (last_date - first_date).days

    has_positive = any(f.amount > Decimal("0") for f in netted)
    has_negative = any(f.amount < Decimal("0") for f in netted)
    if not (has_positive and has_negative):
        return XirrResult(
            rate=None,
            reason="INSUFFICIENT_FLOWS",
            short_period=span_days < XIRR_SHORT_PERIOD_DAYS,
            ambiguous=False,
            flows_count=len(flows),
            first_flow_date=first_date.isoformat(),
            last_flow_date=last_date.isoformat(),
            excluded_funds=excluded_funds,
        )

    # 4. PERIOD_TOO_SHORT
    if span_days < XIRR_MIN_DAYS:
        return XirrResult(
            rate=None,
            reason="PERIOD_TOO_SHORT",
            short_period=True,
            ambiguous=False,
            flows_count=len(flows),
            first_flow_date=first_date.isoformat(),
            last_flow_date=last_date.isoformat(),
            excluded_funds=excluded_funds,
        )

    short_period = span_days < XIRR_SHORT_PERIOD_DAYS

    # Prepare float data for mathematical solver: t_i in years, cf_i
    t_vals: list[float] = [(f.flow_date - first_date).days / float(DAYS_PER_YEAR) for f in netted]
    cf_vals: list[float] = [float(f.amount) for f in netted]
    sum_abs_cf = sum(abs(c) for c in cf_vals)

    def f_eval(x: float) -> float:
        """f(x) = sum(cf_i * exp(-x * t_i)) where x = ln(1 + r)."""
        val = 0.0
        for cf, t in zip(cf_vals, t_vals, strict=True):
            # Guard against exp overflow/underflow
            exponent = -x * t
            if exponent > 700.0:
                val += cf * 1e300
            elif exponent < -700.0:
                pass
            else:
                val += cf * math.exp(exponent)
        return val

    # Grid search on [ln(1 + XIRR_RATE_MIN), ln(1 + XIRR_RATE_MAX)]
    x_min = math.log(1.0 + XIRR_RATE_MIN)
    x_max = math.log(1.0 + XIRR_RATE_MAX)
    grid_points = 1200
    step = (x_max - x_min) / float(grid_points)

    found_roots: list[float] = []
    x_prev = x_min
    f_prev = f_eval(x_prev)

    if abs(f_prev) < 1e-13:
        r_exact = math.exp(x_prev) - 1.0
        found_roots.append(r_exact)

    for step_idx in range(1, grid_points + 1):
        x_curr = x_min + step_idx * step
        f_curr = f_eval(x_curr)

        if abs(f_curr) < 1e-13:
            r_exact = math.exp(x_curr) - 1.0
            found_roots.append(r_exact)
        elif f_prev * f_curr < 0.0:
            root_x = _bisection(f_eval, x_prev, x_curr, f_prev)
            root_r = math.exp(root_x) - 1.0
            found_roots.append(root_r)

        x_prev = x_curr
        f_prev = f_curr

    # Deduplicate roots that are numerically identical
    unique_roots: list[float] = []
    for r in found_roots:
        if not any(abs(r - u) < 1e-4 for u in unique_roots):
            unique_roots.append(r)

    # 5. NO_SOLUTION check
    if not unique_roots:
        return XirrResult(
            rate=None,
            reason="NO_SOLUTION",
            short_period=short_period,
            ambiguous=False,
            flows_count=len(flows),
            first_flow_date=first_date.isoformat(),
            last_flow_date=last_date.isoformat(),
            excluded_funds=excluded_funds,
        )

    # Pick root with smallest |r|
    unique_roots.sort(key=lambda r: abs(r))
    best_root = unique_roots[0]
    ambiguous = len(unique_roots) > 1

    # Verify |NPV(rate)| <= 1e-6 * sum(|cf|)
    npv = 0.0
    for cf, t in zip(cf_vals, t_vals, strict=True):
        npv += cf * math.pow(1.0 + best_root, -t)

    if abs(npv) > (1e-6 * sum_abs_cf):
        return XirrResult(
            rate=None,
            reason="NO_SOLUTION",
            short_period=short_period,
            ambiguous=ambiguous,
            flows_count=len(flows),
            first_flow_date=first_date.isoformat(),
            last_flow_date=last_date.isoformat(),
            excluded_funds=excluded_funds,
        )

    # Quantize to Decimal fraction string (6 decimals)
    dec_val = Decimal(str(round(best_root, 8))).quantize(RATE_QUANT, rounding=ROUND_HALF_UP)
    rate_str = f"{dec_val:.6f}"

    return XirrResult(
        rate=rate_str,
        reason=None,
        short_period=short_period,
        ambiguous=ambiguous,
        flows_count=len(flows),
        first_flow_date=first_date.isoformat(),
        last_flow_date=last_date.isoformat(),
        excluded_funds=excluded_funds,
    )
