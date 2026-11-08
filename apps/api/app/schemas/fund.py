"""Pydantic schemas for Fund and NAV endpoints."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FundSearchItem(BaseModel):
    """Compact fund record for search results."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scheme_code: int
    name: str
    amc: str
    category_raw: str
    asset_class: str
    sub_category: str | None
    plan_type: str
    option_type: str
    latest_nav: Decimal | None
    latest_nav_date: date | None
    is_active: bool
    is_tracked: bool


class FundSearchResponse(BaseModel):
    """Search results response with pagination flag."""

    items: list[FundSearchItem]
    has_more: bool


class FundDetailResponse(BaseModel):
    """Comprehensive details for a single mutual fund scheme."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scheme_code: int
    isin_growth: str | None
    isin_reinvest: str | None
    name: str
    amc: str
    scheme_type_raw: str | None
    category_raw: str
    asset_class: str
    sub_category: str | None
    classification_source: str
    plan_type: str
    option_type: str
    latest_nav: Decimal | None
    latest_nav_date: date | None
    is_active: bool
    is_tracked: bool


class NavPoint(BaseModel):
    """Historical NAV point."""

    model_config = ConfigDict(from_attributes=True)

    date: date
    nav: Decimal


class FundNavHistoryResponse(BaseModel):
    """NAV history series for a fund."""

    scheme_code: int
    name: str
    history_available: bool
    points: list[NavPoint]


class TrackFundResponse(BaseModel):
    """Result of tracking a fund."""

    scheme_code: int
    status: str  # "queued" | "already_tracked"


class NavStatusResponse(BaseModel):
    """Health and freshness status of AMFI NAV data."""

    last_run_time: datetime | None
    last_run_status: str | None
    last_success_time: datetime | None
    schemes_parsed: int
    funds_created: int
    funds_updated: int
    nav_rows_written: int
    is_stale: bool
