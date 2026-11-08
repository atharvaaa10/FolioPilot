"""Pydantic schemas for Portfolio and Target Allocation endpoints."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

DecimalStr = Annotated[
    Decimal,
    PlainSerializer(lambda x: str(x) if x is not None else None, return_type=str),
]
OptionalDecimalStr = Annotated[
    Decimal | None,
    PlainSerializer(lambda x: str(x) if x is not None else None, return_type=str),
]


class TargetItem(BaseModel):
    """Target percentage for an asset class."""

    asset_class: str
    target_pct: DecimalStr


class PortfolioTargetsUpdate(BaseModel):
    """Payload to replace target allocations for a portfolio."""

    targets: list[TargetItem]


class PortfolioCreate(BaseModel):
    """Payload to create a new portfolio."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None


class PortfolioUpdate(BaseModel):
    """Payload to update portfolio metadata."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None


class PortfolioResponse(BaseModel):
    """Portfolio representation with embedded targets."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    targets: list[TargetItem] = Field(default_factory=list)


class FundSummary(BaseModel):
    """Summary of fund master data embedded in holdings."""

    name: str
    amc: str
    asset_class: str
    sub_category: str | None
    plan_type: str
    option_type: str
    latest_nav: OptionalDecimalStr = None
    latest_nav_date: date | None = None


class HoldingResponse(BaseModel):
    """Derived holding position for a fund calculated using average cost."""

    scheme_code: int
    fund: FundSummary
    units: DecimalStr
    avg_cost: DecimalStr
    cost_basis: DecimalStr
    total_bought: DecimalStr
    total_sold: DecimalStr
    first_txn_date: date
    last_txn_date: date
    txn_count: int
    is_closed: bool


class HoldingsTotals(BaseModel):
    """Aggregated portfolio totals for holdings."""

    cost_basis: DecimalStr
    open_positions: int


class HoldingsListResponse(BaseModel):
    """Holdings list endpoint envelope data."""

    items: list[HoldingResponse]
    totals: HoldingsTotals


class PortfolioDetailResponse(BaseModel):
    """Complete portfolio view containing metadata, targets, and summary metrics."""

    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    targets: list[TargetItem] = Field(default_factory=list)
    total_cost_basis: DecimalStr = Decimal("0.00")
    open_positions: int = 0
    total_transactions: int = 0
