"""Pydantic schemas for Excel transaction imports and preview rows."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
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


class ImportFundSummary(BaseModel):
    """Fund details embedded in import row response."""

    model_config = ConfigDict(from_attributes=True)

    scheme_code: int
    name: str
    amc: str | None = None
    plan_type: str | None = None
    option_type: str | None = None
    is_active: bool = True


class RowMessage(BaseModel):
    """Validation or informative message attached to an import row."""

    level: Literal["error", "warning", "info"]
    code: str
    field: str | None = None
    message: str
    details: Any | None = None


class ImportRowResponse(BaseModel):
    """Single row in an import preview."""

    model_config = ConfigDict(from_attributes=True)

    row_number: int
    status: Literal["ok", "warning", "duplicate", "error"]
    fund: ImportFundSummary | None = None
    fund_name_in_file: str | None = None
    txn_type: str | None = None
    txn_date: date | None = None
    units: OptionalDecimalStr = None
    nav: OptionalDecimalStr = None
    amount: OptionalDecimalStr = None
    notes: str | None = None
    raw: dict[str, str] = Field(default_factory=dict)
    messages: list[RowMessage] = Field(default_factory=list)


class ImportDateRange(BaseModel):
    """Date span of candidate transactions to import."""

    from_: str | None = Field(None, alias="from")
    to: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class ImportTotals(BaseModel):
    """Aggregated financial totals of will_import candidate transactions."""

    buy_amount: str = "0.00"
    sell_amount: str = "0.00"


class ImportSummaryResponse(BaseModel):
    """Summary representation of an Excel import batch."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    portfolio_id: UUID
    filename: str
    file_sha256: str
    status: Literal["previewed", "committed", "undone"]
    rows_total: int
    rows_ok: int
    rows_warning: int
    rows_duplicate: int
    rows_error: int
    will_import: int
    plan_fingerprint: str
    extra_columns: list[str] | None = None
    funds_count: int = 0
    date_range: ImportDateRange | None = None
    totals: ImportTotals = Field(default_factory=ImportTotals)
    blocking_errors: list[str] = Field(default_factory=list)
    previewed_at: datetime
    expires_at: datetime
    committed_count: int | None = None
    committed_at: datetime | None = None
    undone_count: int | None = None
    undone_at: datetime | None = None


class ImportUploadResponse(BaseModel):
    """Response returned immediately upon file upload and preview creation."""

    import_: ImportSummaryResponse = Field(..., alias="import")
    rows: list[ImportRowResponse]

    model_config = ConfigDict(populate_by_name=True)


class ImportRowsPageResponse(BaseModel):
    """Paginated preview rows response."""

    items: list[ImportRowResponse]
    has_more: bool = False


class ImportCommitRequest(BaseModel):
    """Request payload to commit a previewed import batch."""

    plan_fingerprint: str
    skip_invalid: bool = False
