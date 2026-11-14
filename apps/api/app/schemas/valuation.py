"""Pydantic response models for Portfolio Valuation, Valuation Summary, and Value Series."""

from pydantic import BaseModel, ConfigDict


class XirrResultSchema(BaseModel):
    """Standardized XIRR result representation."""

    model_config = ConfigDict(from_attributes=True)

    rate: str | None = None
    reason: str | None = None
    short_period: bool
    ambiguous: bool
    flows_count: int
    first_flow_date: str | None = None
    last_flow_date: str | None = None
    excluded_funds: int


class FundBasicSummary(BaseModel):
    """Fund metadata embedded in valuation and holdings responses."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    amc: str
    asset_class: str
    sub_category: str | None
    plan_type: str
    option_type: str


class ValuationItemSchema(BaseModel):
    """Valuation item representing a single fund position."""

    model_config = ConfigDict(from_attributes=True)

    scheme_code: int
    fund: FundBasicSummary
    units: str
    avg_cost: str
    cost_basis: str
    nav: str
    nav_date: str | None = None
    nav_source: str
    nav_age_days: int
    is_stale: bool
    nav_older_than_ledger: bool
    current_value: str
    unrealized_gain: str
    unrealized_gain_pct: str | None = None
    realized_gain: str
    xirr: XirrResultSchema
    is_closed: bool


class ValuationTotalsSchema(BaseModel):
    """Aggregated portfolio valuation totals."""

    model_config = ConfigDict(from_attributes=True)

    cost_basis: str
    current_value: str
    unrealized_gain: str
    unrealized_gain_pct: str | None = None
    realized_gain: str
    total_gain: str
    open_positions: int
    fallback_positions: int
    stale_positions: int
    xirr: XirrResultSchema


class ValuationResponse(BaseModel):
    """Response data for GET /portfolios/{id}/valuation."""

    model_config = ConfigDict(from_attributes=True)

    as_of: str | None = None
    items: list[ValuationItemSchema]
    totals: ValuationTotalsSchema


class PortfolioSummaryItemSchema(BaseModel):
    """Summary of a single portfolio embedded within GET /valuation/summary."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    cost_basis: str
    current_value: str
    unrealized_gain: str
    unrealized_gain_pct: str | None = None
    realized_gain: str
    total_gain: str
    open_positions: int
    fallback_positions: int
    stale_positions: int
    xirr: XirrResultSchema


class AssetClassAllocationItem(BaseModel):
    """Asset class allocation slice."""

    model_config = ConfigDict(from_attributes=True)

    asset_class: str
    current_value: str
    percent: str


class SubCategoryAllocationItem(BaseModel):
    """Sub-category allocation slice."""

    model_config = ConfigDict(from_attributes=True)

    sub_category: str
    current_value: str
    percent: str


class AllocationSchema(BaseModel):
    """Allocation breakdown by asset class and sub-category."""

    model_config = ConfigDict(from_attributes=True)

    by_asset_class: list[AssetClassAllocationItem]
    by_sub_category: list[SubCategoryAllocationItem]


class TopHoldingSchema(BaseModel):
    """Top fund holding aggregated across portfolios."""

    model_config = ConfigDict(from_attributes=True)

    scheme_code: int
    fund: FundBasicSummary
    units: str
    current_value: str
    unrealized_gain: str


class SummaryCountsSchema(BaseModel):
    """Global counts across user portfolios."""

    model_config = ConfigDict(from_attributes=True)

    portfolios: int
    open_positions: int
    fallback_positions: int
    stale_positions: int


class ValuationSummaryResponse(BaseModel):
    """Response data for GET /valuation/summary."""

    model_config = ConfigDict(from_attributes=True)

    as_of: str | None = None
    totals: ValuationTotalsSchema
    portfolios: list[PortfolioSummaryItemSchema]
    allocation: AllocationSchema
    top_holdings: list[TopHoldingSchema]
    counts: SummaryCountsSchema


class SeriesPointSchema(BaseModel):
    """Single date point in the value-over-time series."""

    model_config = ConfigDict(from_attributes=True)

    date: str
    value: str
    cost_basis: str


class ValueSeriesResponse(BaseModel):
    """Response data for GET /portfolios/{id}/value-series."""

    model_config = ConfigDict(from_attributes=True)

    range: str
    start_date: str
    end_date: str
    points: list[SeriesPointSchema]
