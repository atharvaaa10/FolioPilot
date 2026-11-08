"""Pydantic schemas for Transaction ledger and derived holdings."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.schemas.portfolio import TargetItem

DecimalStr = Annotated[
    Decimal,
    PlainSerializer(lambda x: str(x) if x is not None else None, return_type=str),
]
OptionalDecimalStr = Annotated[
    Decimal | None,
    PlainSerializer(lambda x: str(x) if x is not None else None, return_type=str | None),
]


class TransactionCreate(BaseModel):
    """Payload to record a BUY or SELL transaction in portfolio ledger."""

    fund_id: UUID | None = None
    scheme_code: int | None = None
    txn_type: Literal["BUY", "SELL", "buy", "sell"]
    txn_date: date
    units: Decimal | None = None
    nav: Decimal | None = None
    amount: Decimal | None = None
    notes: str | None = None


class TransactionUpdate(BaseModel):
    """Payload to update an existing transaction in portfolio ledger.

    Note: txn_type and fund_id are strictly immutable.
    """

    txn_date: date | None = None
    units: Decimal | None = None
    nav: Decimal | None = None
    amount: Decimal | None = None
    notes: str | None = None


class TransactionResponse(BaseModel):
    """Transaction ledger entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    portfolio_id: UUID
    fund_id: UUID
    scheme_code: int | None = None
    fund_name: str | None = None
    txn_type: str
    txn_date: date
    units: DecimalStr
    nav: DecimalStr
    amount: DecimalStr
    notes: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


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
