"""Pydantic schemas for Transaction ledger and derived positions."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

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


class PositionResponse(BaseModel):
    """Derived holding position for a fund calculated using average cost."""

    fund_id: UUID
    scheme_code: int
    fund_name: str
    asset_class: str
    sub_category: str | None
    units: DecimalStr
    avg_nav: DecimalStr
    total_invested: DecimalStr
    realized_gain: DecimalStr
    latest_nav: OptionalDecimalStr = None
    latest_nav_date: date | None = None
    current_value: OptionalDecimalStr = None
    unrealized_gain: OptionalDecimalStr = None


class PortfolioDetailResponse(BaseModel):
    """Complete portfolio view containing metadata, targets, positions, and summary metrics."""

    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    targets: list[dict[str, str]] = Field(default_factory=list)
    positions: list[PositionResponse] = Field(default_factory=list)
    total_invested: DecimalStr = Decimal("0.00")
    current_value: DecimalStr = Decimal("0.00")
    unrealized_gain: DecimalStr = Decimal("0.00")
    realized_gain: DecimalStr = Decimal("0.00")
