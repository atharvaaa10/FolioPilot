"""Pure valuation, gain tracking, and XIRR flow assembly for portfolios.

Follows CONVENTIONS.md:
- Pure business logic (zero DB, zero network).
- Decimal arithmetic with 28-digit precision, ROUND_HALF_UP quantization.
- Totals are strictly SUMS of rounded per-position values.
- Price rule: amfi_latest with fallback to average cost (fallback_cost).
- Staleness threshold: nav_age_days > NAV_STALE_DAYS.
- Alignment check: nav_older_than_ledger flags latest_nav_date < last_txn_date.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from app.core.constants import (
    NAV_STALE_DAYS,
    TOP_HOLDINGS_LIMIT,
)
from app.services.ledger import compute_holdings
from app.services.xirr import CashFlow, XirrResult, solve_xirr

# Module-level constant tested by mutation testing
DIVIDEND_REINVEST_IS_CASH_FLOW: bool = False

AMOUNT_QUANT = Decimal("0.01")
PERCENT_QUANT = Decimal("0.01")
NAV_QUANT = Decimal("0.00000001")
UNITS_QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class FundInfo:
    """Minimal fund metadata required for pure valuation."""

    id: UUID
    scheme_code: int
    name: str
    amc: str
    asset_class: str
    sub_category: str | None
    plan_type: str
    option_type: str
    latest_nav: Decimal | None
    latest_nav_date: date | None


@dataclass(frozen=True)
class ValuationItem:
    """Valuation details for a single fund position."""

    scheme_code: int
    fund: FundInfo
    units: Decimal
    avg_cost: Decimal
    cost_basis: Decimal
    nav: Decimal
    nav_date: date | None
    nav_source: str  # "amfi_latest" | "fallback_cost"
    nav_age_days: int
    is_stale: bool
    nav_older_than_ledger: bool
    current_value: Decimal
    unrealized_gain: Decimal
    unrealized_gain_pct: Decimal | None
    realized_gain: Decimal
    xirr: XirrResult
    is_closed: bool


@dataclass(frozen=True)
class ValuationTotals:
    """Aggregated valuation totals for a portfolio or portfolio set."""

    cost_basis: Decimal
    current_value: Decimal
    unrealized_gain: Decimal
    unrealized_gain_pct: Decimal | None
    realized_gain: Decimal
    total_gain: Decimal
    open_positions: int
    fallback_positions: int
    stale_positions: int
    xirr: XirrResult


@dataclass(frozen=True)
class PortfolioValuationResult:
    """Complete portfolio valuation response object."""

    as_of: date | None
    items: list[ValuationItem]
    totals: ValuationTotals


@dataclass(frozen=True)
class AllocationSlice:
    """Allocation breakdown slice."""

    name: str  # asset_class or sub_category
    current_value: Decimal
    percent: Decimal


@dataclass(frozen=True)
class TopHoldingItem:
    """Top holding entry aggregated across portfolios."""

    scheme_code: int
    fund: FundInfo
    units: Decimal
    current_value: Decimal
    unrealized_gain: Decimal


@dataclass(frozen=True)
class ValuationSummaryResult:
    """Overall multi-portfolio valuation summary."""

    as_of: date | None
    totals: ValuationTotals
    portfolios: list[dict[str, Any]]
    allocation: dict[str, list[dict[str, Any]]]
    top_holdings: list[TopHoldingItem]
    counts: dict[str, int]


def assemble_fund_cash_flows(
    txns: list[Any],
    terminal_value: Decimal,
    terminal_date: date | None,
    is_closed: bool,
) -> list[CashFlow]:
    """Assemble cash flows for a single fund.

    buys are outflows (-amount), sells are inflows (+amount).
    dividend_reinvest is excluded unless DIVIDEND_REINVEST_IS_CASH_FLOW is True.
    open positions add terminal inflow (+current_value) on terminal_date.
    """
    flows: list[CashFlow] = []
    for txn in txns:
        txn_type = str(getattr(txn, "txn_type", "")).lower()
        txn_date = txn.txn_date
        amount = txn.amount

        if txn_type == "buy":
            flows.append(CashFlow(flow_date=txn_date, amount=-amount))
        elif txn_type == "sell":
            flows.append(CashFlow(flow_date=txn_date, amount=amount))
        elif txn_type == "dividend_reinvest" and DIVIDEND_REINVEST_IS_CASH_FLOW:
            flows.append(CashFlow(flow_date=txn_date, amount=-amount))

    # Add terminal inflow for open position
    if not is_closed and terminal_date is not None and terminal_value > Decimal("0.00"):
        flows.append(CashFlow(flow_date=terminal_date, amount=terminal_value))

    return flows


def compute_portfolio_valuation(
    transactions: list[Any],
    funds_by_id: dict[UUID, FundInfo],
    today_ist: date,
    include_closed: bool = False,
) -> PortfolioValuationResult:
    """Pure computation of valuation, realized/unrealized gains, and XIRR for a portfolio."""
    if not transactions:
        empty_xirr = XirrResult(
            rate=None,
            reason="NO_TRANSACTIONS",
            short_period=False,
            ambiguous=False,
            flows_count=0,
            first_flow_date=None,
            last_flow_date=None,
            excluded_funds=0,
        )
        empty_totals = ValuationTotals(
            cost_basis=Decimal("0.00"),
            current_value=Decimal("0.00"),
            unrealized_gain=Decimal("0.00"),
            unrealized_gain_pct=None,
            realized_gain=Decimal("0.00"),
            total_gain=Decimal("0.00"),
            open_positions=0,
            fallback_positions=0,
            stale_positions=0,
            xirr=empty_xirr,
        )
        return PortfolioValuationResult(as_of=None, items=[], totals=empty_totals)

    # 1. Derive holdings and realized gains from single ledger sweep
    holdings_map = compute_holdings(transactions)

    # Group transactions by fund_id for XIRR flow assembly
    txns_by_fund: dict[UUID, list[Any]] = defaultdict(list)
    for t in transactions:
        txns_by_fund[t.fund_id].append(t)

    items: list[ValuationItem] = []
    portfolio_xirr_flows: list[CashFlow] = []
    excluded_funds_count = 0
    as_of_dates: list[date] = []

    # Sort holdings deterministically by fund name
    sorted_fund_ids = sorted(
        holdings_map.keys(),
        key=lambda fid: funds_by_id[fid].name if fid in funds_by_id else str(fid),
    )

    for fund_id in sorted_fund_ids:
        holding = holdings_map[fund_id]
        fund = funds_by_id.get(fund_id)
        if fund is None:
            continue

        fund_txns = txns_by_fund.get(fund_id, [])

        # Price rule: amfi_latest vs fallback_cost
        if fund.latest_nav is not None and fund.latest_nav_date is not None:
            nav_source = "amfi_latest"
            nav = fund.latest_nav.quantize(NAV_QUANT, rounding=ROUND_HALF_UP)
            nav_date = fund.latest_nav_date
            nav_age_days = max(0, (today_ist - fund.latest_nav_date).days)
            is_stale = nav_age_days > NAV_STALE_DAYS
            nav_older_than_ledger = fund.latest_nav_date < holding.last_txn_date
            terminal_date = (
                max(fund.latest_nav_date, holding.last_txn_date)
                if nav_older_than_ledger
                else fund.latest_nav_date
            )
            if not holding.is_closed:
                as_of_dates.append(fund.latest_nav_date)
        else:
            nav_source = "fallback_cost"
            nav = holding.avg_cost.quantize(NAV_QUANT, rounding=ROUND_HALF_UP)
            nav_date = None
            nav_age_days = 0
            is_stale = False
            nav_older_than_ledger = False
            terminal_date = holding.last_txn_date

        # Per-position values
        current_value = (holding.units * nav).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
        cost_basis = holding.cost_basis.quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
        unrealized_gain = (current_value - cost_basis).quantize(
            AMOUNT_QUANT, rounding=ROUND_HALF_UP
        )

        if cost_basis > Decimal("0.00"):
            unrealized_gain_pct = (unrealized_gain / cost_basis * Decimal("100")).quantize(
                PERCENT_QUANT, rounding=ROUND_HALF_UP
            )
        else:
            unrealized_gain_pct = None

        realized_gain = holding.realized_gain.quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)

        # Assemble fund XIRR flows
        fund_flows = assemble_fund_cash_flows(
            txns=fund_txns,
            terminal_value=current_value,
            terminal_date=terminal_date,
            is_closed=holding.is_closed,
        )

        # Fund XIRR result
        if not holding.is_closed and nav_source == "fallback_cost":
            # Open position with fallback cost has no live NAV
            fund_xirr = solve_xirr(
                fund_flows,
                has_open_positions=True,
                has_live_nav=False,
                closed_flows_present=False,
            )
        else:
            fund_xirr = solve_xirr(
                fund_flows,
                has_open_positions=not holding.is_closed,
                has_live_nav=nav_source == "amfi_latest",
                closed_flows_present=holding.is_closed,
            )

        # Portfolio XIRR eligibility
        if holding.is_closed or nav_source == "amfi_latest":
            portfolio_xirr_flows.extend(fund_flows)
        else:
            excluded_funds_count += 1

        val_item = ValuationItem(
            scheme_code=fund.scheme_code,
            fund=fund,
            units=holding.units,
            avg_cost=holding.avg_cost,
            cost_basis=cost_basis,
            nav=nav,
            nav_date=nav_date,
            nav_source=nav_source,
            nav_age_days=nav_age_days,
            is_stale=is_stale,
            nav_older_than_ledger=nav_older_than_ledger,
            current_value=current_value,
            unrealized_gain=unrealized_gain,
            unrealized_gain_pct=unrealized_gain_pct,
            realized_gain=realized_gain,
            xirr=fund_xirr,
            is_closed=holding.is_closed,
        )

        if not holding.is_closed or include_closed:
            items.append(val_item)

    # Totals are strictly SUMS of the rounded per-position values
    live_items = [it for it in items if not it.is_closed]
    total_cost_basis = sum((it.cost_basis for it in live_items), Decimal("0.00"))
    total_current_value = sum((it.current_value for it in live_items), Decimal("0.00"))
    total_unrealized_gain = sum((it.unrealized_gain for it in live_items), Decimal("0.00"))

    if total_cost_basis > Decimal("0.00"):
        total_unrealized_gain_pct = (
            total_unrealized_gain / total_cost_basis * Decimal("100")
        ).quantize(PERCENT_QUANT, rounding=ROUND_HALF_UP)
    else:
        total_unrealized_gain_pct = None

    # Realized gain includes closed positions as well
    all_fund_holdings = list(holdings_map.values())
    total_realized_gain = sum(
        (h.realized_gain for h in all_fund_holdings), Decimal("0.00")
    ).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)

    total_gain = (total_unrealized_gain + total_realized_gain).quantize(
        AMOUNT_QUANT, rounding=ROUND_HALF_UP
    )

    open_positions = len(live_items)
    fallback_positions = sum(1 for it in live_items if it.nav_source == "fallback_cost")
    stale_positions = sum(1 for it in live_items if it.is_stale)

    # Compute overall portfolio XIRR
    has_live_nav_portfolio = any(it.nav_source == "amfi_latest" for it in live_items)
    closed_flows_present_portfolio = any(it.is_closed for it in items)

    portfolio_xirr = solve_xirr(
        portfolio_xirr_flows,
        excluded_funds=excluded_funds_count,
        has_open_positions=open_positions > 0,
        has_live_nav=has_live_nav_portfolio,
        closed_flows_present=closed_flows_present_portfolio,
    )

    as_of = max(as_of_dates) if as_of_dates else None

    totals = ValuationTotals(
        cost_basis=total_cost_basis,
        current_value=total_current_value,
        unrealized_gain=total_unrealized_gain,
        unrealized_gain_pct=total_unrealized_gain_pct,
        realized_gain=total_realized_gain,
        total_gain=total_gain,
        open_positions=open_positions,
        fallback_positions=fallback_positions,
        stale_positions=stale_positions,
        xirr=portfolio_xirr,
    )

    return PortfolioValuationResult(as_of=as_of, items=items, totals=totals)


def compute_valuation_summary(
    portfolios_data: list[tuple[UUID, str, PortfolioValuationResult, list[CashFlow]]],
) -> ValuationSummaryResult:
    """Compute overall valuation summary across all user portfolios.

    Totals are the SUM of per-portfolio totals.
    XIRR is solved across the union of all eligible portfolio flows.
    """
    if not portfolios_data:
        empty_xirr = XirrResult(
            rate=None,
            reason="NO_TRANSACTIONS",
            short_period=False,
            ambiguous=False,
            flows_count=0,
            first_flow_date=None,
            last_flow_date=None,
            excluded_funds=0,
        )
        empty_totals = ValuationTotals(
            cost_basis=Decimal("0.00"),
            current_value=Decimal("0.00"),
            unrealized_gain=Decimal("0.00"),
            unrealized_gain_pct=None,
            realized_gain=Decimal("0.00"),
            total_gain=Decimal("0.00"),
            open_positions=0,
            fallback_positions=0,
            stale_positions=0,
            xirr=empty_xirr,
        )
        return ValuationSummaryResult(
            as_of=None,
            totals=empty_totals,
            portfolios=[],
            allocation={"by_asset_class": [], "by_sub_category": []},
            top_holdings=[],
            counts={
                "portfolios": 0,
                "open_positions": 0,
                "fallback_positions": 0,
                "stale_positions": 0,
            },
        )

    as_of_dates: list[date] = []
    union_flows: list[CashFlow] = []
    total_excluded_funds = 0
    has_live_nav_overall = False
    has_closed_flows_overall = False

    portfolios_list: list[dict[str, Any]] = []

    # Aggregations for allocation and top holdings
    asset_class_values: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    sub_category_values: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    top_holdings_map: dict[int, dict[str, Any]] = {}

    for p_id, p_name, val_res, p_flows in portfolios_data:
        if val_res.as_of:
            as_of_dates.append(val_res.as_of)

        union_flows.extend(p_flows)
        total_excluded_funds += val_res.totals.xirr.excluded_funds

        if any(it.nav_source == "amfi_latest" for it in val_res.items if not it.is_closed):
            has_live_nav_overall = True
        if any(it.is_closed for it in val_res.items):
            has_closed_flows_overall = True

        portfolios_list.append(
            {
                "id": str(p_id),
                "name": p_name,
                "cost_basis": str(val_res.totals.cost_basis),
                "current_value": str(val_res.totals.current_value),
                "unrealized_gain": str(val_res.totals.unrealized_gain),
                "unrealized_gain_pct": (
                    str(val_res.totals.unrealized_gain_pct)
                    if val_res.totals.unrealized_gain_pct is not None
                    else None
                ),
                "realized_gain": str(val_res.totals.realized_gain),
                "total_gain": str(val_res.totals.total_gain),
                "open_positions": val_res.totals.open_positions,
                "fallback_positions": val_res.totals.fallback_positions,
                "stale_positions": val_res.totals.stale_positions,
                "xirr": {
                    "rate": val_res.totals.xirr.rate,
                    "reason": val_res.totals.xirr.reason,
                    "short_period": val_res.totals.xirr.short_period,
                    "ambiguous": val_res.totals.xirr.ambiguous,
                    "flows_count": val_res.totals.xirr.flows_count,
                    "first_flow_date": val_res.totals.xirr.first_flow_date,
                    "last_flow_date": val_res.totals.xirr.last_flow_date,
                    "excluded_funds": val_res.totals.xirr.excluded_funds,
                },
            }
        )

        for it in val_res.items:
            if it.is_closed:
                continue

            ac = it.fund.asset_class or "other"
            sc = it.fund.sub_category or "other"
            asset_class_values[ac] += it.current_value
            sub_category_values[sc] += it.current_value

            sc_code = it.scheme_code
            if sc_code not in top_holdings_map:
                top_holdings_map[sc_code] = {
                    "scheme_code": sc_code,
                    "fund": it.fund,
                    "units": Decimal("0.0000"),
                    "current_value": Decimal("0.00"),
                    "unrealized_gain": Decimal("0.00"),
                }
            top_holdings_map[sc_code]["units"] += it.units
            top_holdings_map[sc_code]["current_value"] += it.current_value
            top_holdings_map[sc_code]["unrealized_gain"] += it.unrealized_gain

    # Totals are strictly the SUM of per-portfolio totals
    sum_cost_basis = sum((p[2].totals.cost_basis for p in portfolios_data), Decimal("0.00"))
    sum_current_value = sum((p[2].totals.current_value for p in portfolios_data), Decimal("0.00"))
    sum_unrealized_gain = sum(
        (p[2].totals.unrealized_gain for p in portfolios_data), Decimal("0.00")
    )

    if sum_cost_basis > Decimal("0.00"):
        sum_unrealized_gain_pct = (sum_unrealized_gain / sum_cost_basis * Decimal("100")).quantize(
            PERCENT_QUANT, rounding=ROUND_HALF_UP
        )
    else:
        sum_unrealized_gain_pct = None

    sum_realized_gain = sum((p[2].totals.realized_gain for p in portfolios_data), Decimal("0.00"))
    sum_total_gain = (sum_unrealized_gain + sum_realized_gain).quantize(
        AMOUNT_QUANT, rounding=ROUND_HALF_UP
    )

    sum_open_positions = sum(p[2].totals.open_positions for p in portfolios_data)
    sum_fallback_positions = sum(p[2].totals.fallback_positions for p in portfolios_data)
    sum_stale_positions = sum(p[2].totals.stale_positions for p in portfolios_data)

    # Solve overall XIRR across all portfolios
    overall_xirr = solve_xirr(
        union_flows,
        excluded_funds=total_excluded_funds,
        has_open_positions=sum_open_positions > 0,
        has_live_nav=has_live_nav_overall,
        closed_flows_present=has_closed_flows_overall,
    )

    as_of = max(as_of_dates) if as_of_dates else None

    totals = ValuationTotals(
        cost_basis=sum_cost_basis,
        current_value=sum_current_value,
        unrealized_gain=sum_unrealized_gain,
        unrealized_gain_pct=sum_unrealized_gain_pct,
        realized_gain=sum_realized_gain,
        total_gain=sum_total_gain,
        open_positions=sum_open_positions,
        fallback_positions=sum_fallback_positions,
        stale_positions=sum_stale_positions,
        xirr=overall_xirr,
    )

    # Build allocation breakdown
    by_asset_class: list[dict[str, Any]] = []
    for ac, val in sorted(asset_class_values.items(), key=lambda x: x[1], reverse=True):
        pct = (
            (val / sum_current_value * Decimal("100")).quantize(
                PERCENT_QUANT, rounding=ROUND_HALF_UP
            )
            if sum_current_value > Decimal("0.00")
            else Decimal("0.00")
        )
        by_asset_class.append({"asset_class": ac, "current_value": str(val), "percent": str(pct)})

    by_sub_category: list[dict[str, Any]] = []
    for sc, val in sorted(sub_category_values.items(), key=lambda x: x[1], reverse=True):
        pct = (
            (val / sum_current_value * Decimal("100")).quantize(
                PERCENT_QUANT, rounding=ROUND_HALF_UP
            )
            if sum_current_value > Decimal("0.00")
            else Decimal("0.00")
        )
        by_sub_category.append({"sub_category": sc, "current_value": str(val), "percent": str(pct)})

    # Build top holdings
    sorted_top = sorted(top_holdings_map.values(), key=lambda x: x["current_value"], reverse=True)[
        :TOP_HOLDINGS_LIMIT
    ]

    top_holdings = [
        TopHoldingItem(
            scheme_code=h["scheme_code"],
            fund=h["fund"],
            units=h["units"].quantize(UNITS_QUANT, rounding=ROUND_HALF_UP),
            current_value=h["current_value"].quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP),
            unrealized_gain=h["unrealized_gain"].quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP),
        )
        for h in sorted_top
    ]

    return ValuationSummaryResult(
        as_of=as_of,
        totals=totals,
        portfolios=portfolios_list,
        allocation={"by_asset_class": by_asset_class, "by_sub_category": by_sub_category},
        top_holdings=top_holdings,
        counts={
            "portfolios": len(portfolios_data),
            "open_positions": sum_open_positions,
            "fallback_positions": sum_fallback_positions,
            "stale_positions": sum_stale_positions,
        },
    )
