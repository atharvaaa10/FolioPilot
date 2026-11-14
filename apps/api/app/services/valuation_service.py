"""Application service orchestrating portfolio valuation, cross-portfolio summary, and series."""

from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PortfolioNotFoundError, ValidationError
from app.repositories.portfolios import PortfolioRepository
from app.repositories.valuation import ValuationRepository
from app.schemas.valuation import (
    AllocationSchema,
    AssetClassAllocationItem,
    FundBasicSummary,
    PortfolioSummaryItemSchema,
    SeriesPointSchema,
    SubCategoryAllocationItem,
    SummaryCountsSchema,
    TopHoldingSchema,
    ValuationItemSchema,
    ValuationResponse,
    ValuationSummaryResponse,
    ValuationTotalsSchema,
    ValueSeriesResponse,
    XirrResultSchema,
)
from app.services.valuation import (
    FundInfo,
    PortfolioValuationResult,
    ValuationTotals,
    assemble_fund_cash_flows,
    compute_portfolio_valuation,
    compute_valuation_summary,
)
from app.services.value_series import PricePoint, sample_dates, value_series
from app.services.xirr import CashFlow

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")
VALID_RANGES = {"1m", "6m", "1y", "3y", "5y", "max"}


def _build_fund_info(fund: Any) -> FundInfo:
    return FundInfo(
        id=fund.id,
        scheme_code=fund.scheme_code,
        name=fund.name,
        amc=fund.amc,
        asset_class=fund.asset_class,
        sub_category=fund.sub_category,
        plan_type=fund.plan_type,
        option_type=fund.option_type,
        latest_nav=fund.latest_nav,
        latest_nav_date=fund.latest_nav_date,
    )


def _serialize_xirr(xirr_obj: Any) -> XirrResultSchema:
    return XirrResultSchema(
        rate=xirr_obj.rate,
        reason=xirr_obj.reason,
        short_period=xirr_obj.short_period,
        ambiguous=xirr_obj.ambiguous,
        flows_count=xirr_obj.flows_count,
        first_flow_date=xirr_obj.first_flow_date,
        last_flow_date=xirr_obj.last_flow_date,
        excluded_funds=xirr_obj.excluded_funds,
    )


def _serialize_totals(totals: ValuationTotals) -> ValuationTotalsSchema:
    return ValuationTotalsSchema(
        cost_basis=str(totals.cost_basis),
        current_value=str(totals.current_value),
        unrealized_gain=str(totals.unrealized_gain),
        unrealized_gain_pct=str(totals.unrealized_gain_pct)
        if totals.unrealized_gain_pct is not None
        else None,
        realized_gain=str(totals.realized_gain),
        total_gain=str(totals.total_gain),
        open_positions=totals.open_positions,
        fallback_positions=totals.fallback_positions,
        stale_positions=totals.stale_positions,
        xirr=_serialize_xirr(totals.xirr),
    )


class ValuationService:
    """Service orchestrating valuation domain operations using an injectable clock."""

    @staticmethod
    async def get_portfolio_valuation(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        clock: datetime,
        include_closed: bool = False,
    ) -> ValuationResponse:
        """Calculate live valuation, gains, and XIRR for a specific user portfolio."""
        # 1. Ownership check
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        today_ist = clock.astimezone(KOLKATA_TZ).date()

        # 2. Load all transactions for portfolio with fund relation (single query)
        txns = await ValuationRepository.list_transactions_for_portfolios(session, [portfolio_id])
        funds_by_id = {t.fund_id: _build_fund_info(t.fund) for t in txns if t.fund is not None}

        # 3. Compute pure valuation
        val_res = compute_portfolio_valuation(
            transactions=txns,
            funds_by_id=funds_by_id,
            today_ist=today_ist,
            include_closed=include_closed,
        )

        items_schema: list[ValuationItemSchema] = []
        for it in val_res.items:
            items_schema.append(
                ValuationItemSchema(
                    scheme_code=it.scheme_code,
                    fund=FundBasicSummary(
                        name=it.fund.name,
                        amc=it.fund.amc,
                        asset_class=it.fund.asset_class,
                        sub_category=it.fund.sub_category,
                        plan_type=it.fund.plan_type,
                        option_type=it.fund.option_type,
                    ),
                    units=str(it.units),
                    avg_cost=str(it.avg_cost),
                    cost_basis=str(it.cost_basis),
                    nav=str(it.nav),
                    nav_date=it.nav_date.isoformat() if it.nav_date else None,
                    nav_source=it.nav_source,
                    nav_age_days=it.nav_age_days,
                    is_stale=it.is_stale,
                    nav_older_than_ledger=it.nav_older_than_ledger,
                    current_value=str(it.current_value),
                    unrealized_gain=str(it.unrealized_gain),
                    unrealized_gain_pct=str(it.unrealized_gain_pct)
                    if it.unrealized_gain_pct is not None
                    else None,
                    realized_gain=str(it.realized_gain),
                    xirr=_serialize_xirr(it.xirr),
                    is_closed=it.is_closed,
                )
            )

        return ValuationResponse(
            as_of=val_res.as_of.isoformat() if val_res.as_of else None,
            items=items_schema,
            totals=_serialize_totals(val_res.totals),
        )

    @staticmethod
    async def get_valuation_summary(
        session: AsyncSession,
        user_id: UUID,
        clock: datetime,
    ) -> ValuationSummaryResponse:
        """Compute aggregated valuation summary across all user portfolios in batch queries."""
        portfolios = await PortfolioRepository.list_by_user(session, user_id, load_targets=False)
        today_ist = clock.astimezone(KOLKATA_TZ).date()

        if not portfolios:
            empty_res = compute_valuation_summary([])
            return ValuationSummaryResponse(
                as_of=None,
                totals=_serialize_totals(empty_res.totals),
                portfolios=[],
                allocation=AllocationSchema(by_asset_class=[], by_sub_category=[]),
                top_holdings=[],
                counts=SummaryCountsSchema(
                    portfolios=0,
                    open_positions=0,
                    fallback_positions=0,
                    stale_positions=0,
                ),
            )

        portfolio_ids = [p.id for p in portfolios]
        # Single query for all user transactions across all portfolios
        all_txns = await ValuationRepository.list_transactions_for_portfolios(
            session, portfolio_ids
        )

        funds_by_id = {t.fund_id: _build_fund_info(t.fund) for t in all_txns if t.fund is not None}

        # Group transactions by portfolio_id
        txns_by_portfolio: dict[UUID, list[Any]] = {p.id: [] for p in portfolios}
        for t in all_txns:
            txns_by_portfolio[t.portfolio_id].append(t)

        portfolios_data: list[tuple[UUID, str, PortfolioValuationResult, list[CashFlow]]] = []

        for p in portfolios:
            p_txns = txns_by_portfolio[p.id]
            val_res = compute_portfolio_valuation(
                transactions=p_txns,
                funds_by_id=funds_by_id,
                today_ist=today_ist,
                include_closed=True,
            )

            # Assemble eligible portfolio cash flows for summary XIRR union
            p_flows: list[CashFlow] = []
            for it in val_res.items:
                if it.is_closed or it.nav_source == "amfi_latest":
                    f_txns = [t for t in p_txns if t.fund_id == it.fund.id]
                    t_date = (
                        max(it.fund.latest_nav_date, it.nav_date)
                        if it.nav_older_than_ledger and it.fund.latest_nav_date and it.nav_date
                        else (it.fund.latest_nav_date if it.fund.latest_nav_date else it.nav_date)
                    )
                    cfs = assemble_fund_cash_flows(
                        txns=f_txns,
                        terminal_value=it.current_value,
                        terminal_date=t_date,
                        is_closed=it.is_closed,
                    )
                    p_flows.extend(cfs)

            portfolios_data.append((p.id, p.name, val_res, p_flows))

        summary_res = compute_valuation_summary(portfolios_data)

        portfolios_schema = [
            PortfolioSummaryItemSchema(
                id=p["id"],
                name=p["name"],
                cost_basis=p["cost_basis"],
                current_value=p["current_value"],
                unrealized_gain=p["unrealized_gain"],
                unrealized_gain_pct=p["unrealized_gain_pct"],
                realized_gain=p["realized_gain"],
                total_gain=p["total_gain"],
                open_positions=p["open_positions"],
                fallback_positions=p["fallback_positions"],
                stale_positions=p["stale_positions"],
                xirr=XirrResultSchema(**p["xirr"]),
            )
            for p in summary_res.portfolios
        ]

        allocation_schema = AllocationSchema(
            by_asset_class=[
                AssetClassAllocationItem(
                    asset_class=a["asset_class"],
                    current_value=a["current_value"],
                    percent=a["percent"],
                )
                for a in summary_res.allocation["by_asset_class"]
            ],
            by_sub_category=[
                SubCategoryAllocationItem(
                    sub_category=s["sub_category"],
                    current_value=s["current_value"],
                    percent=s["percent"],
                )
                for s in summary_res.allocation["by_sub_category"]
            ],
        )

        top_holdings_schema = [
            TopHoldingSchema(
                scheme_code=th.scheme_code,
                fund=FundBasicSummary(
                    name=th.fund.name,
                    amc=th.fund.amc,
                    asset_class=th.fund.asset_class,
                    sub_category=th.fund.sub_category,
                    plan_type=th.fund.plan_type,
                    option_type=th.fund.option_type,
                ),
                units=str(th.units),
                current_value=str(th.current_value),
                unrealized_gain=str(th.unrealized_gain),
            )
            for th in summary_res.top_holdings
        ]

        return ValuationSummaryResponse(
            as_of=summary_res.as_of.isoformat() if summary_res.as_of else None,
            totals=_serialize_totals(summary_res.totals),
            portfolios=portfolios_schema,
            allocation=allocation_schema,
            top_holdings=top_holdings_schema,
            counts=SummaryCountsSchema(**summary_res.counts),
        )

    @staticmethod
    async def get_value_series(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        clock: datetime,
        range_str: str = "1y",
    ) -> ValueSeriesResponse:
        """Calculate historical value-over-time points for portfolio."""
        normalized_range = (range_str or "1y").lower()
        if normalized_range not in VALID_RANGES:
            raise ValidationError(
                f"Invalid range '{range_str}'. Allowed ranges: 1m, 6m, 1y, 3y, 5y, max"
            )

        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        today_ist = clock.astimezone(KOLKATA_TZ).date()

        txns = await ValuationRepository.list_transactions_for_portfolios(session, [portfolio_id])
        if not txns:
            return ValueSeriesResponse(
                range=normalized_range,
                start_date=today_ist.isoformat(),
                end_date=today_ist.isoformat(),
                points=[],
            )

        first_txn_date = min(t.txn_date for t in txns)
        dates = sample_dates(normalized_range, first_txn_date=first_txn_date, today_ist=today_ist)
        if not dates:
            return ValueSeriesResponse(
                range=normalized_range,
                start_date=today_ist.isoformat(),
                end_date=today_ist.isoformat(),
                points=[],
            )

        fund_ids = {t.fund_id for t in txns}
        start_date = dates[0]
        end_date = dates[-1]

        # In-range official NAV rows
        in_range_navs = await ValuationRepository.get_nav_points_in_range(
            session, fund_ids, start_date, end_date
        )

        # Last official NAV row before start_date per fund (DISTINCT ON)
        before_navs = await ValuationRepository.get_last_nav_before_date(
            session, fund_ids, start_date
        )

        price_points: list[PricePoint] = []
        for r in before_navs:
            price_points.append(
                PricePoint(
                    fund_id=r.fund_id,
                    nav_date=r.nav_date,
                    nav=r.nav,
                    is_official=True,
                )
            )

        for r in in_range_navs:
            price_points.append(
                PricePoint(
                    fund_id=r.fund_id,
                    nav_date=r.nav_date,
                    nav=r.nav,
                    is_official=True,
                )
            )

        # Also add fund latest_nav as official price point
        for t in txns:
            f = t.fund
            if f and f.latest_nav is not None and f.latest_nav_date is not None:
                price_points.append(
                    PricePoint(
                        fund_id=f.id,
                        nav_date=f.latest_nav_date,
                        nav=f.latest_nav,
                        is_official=True,
                    )
                )

        points = value_series(
            transactions=txns,
            price_points=price_points,
            dates=dates,
        )

        series_schemas = [
            SeriesPointSchema(date=p.date, value=p.value, cost_basis=p.cost_basis) for p in points
        ]

        return ValueSeriesResponse(
            range=normalized_range,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            points=series_schemas,
        )
