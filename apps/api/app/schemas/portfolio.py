"""Pydantic schemas for Portfolio and Target Allocation endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

DecimalStr = Annotated[
    Decimal,
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
