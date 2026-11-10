"""Pydantic schemas for SIPs, installments, schedules, and preview."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator

from app.core.constants import (
    LEDGER_DATE_FLOOR,
    SIP_DAY_MAX,
    SIP_MAX_AMOUNT,
    SIP_MIN_AMOUNT,
)

DecimalStr = Annotated[
    Decimal,
    PlainSerializer(lambda x: str(x) if x is not None else None, return_type=str),
]
OptionalDecimalStr = Annotated[
    Decimal | None,
    PlainSerializer(lambda x: str(x) if x is not None else None, return_type=str | None),
]


class CreateSipRequest(BaseModel):
    """Payload to create a new SIP."""

    fund_id: UUID | None = None
    scheme_code: int | None = None
    amount: Decimal
    day_of_month: int = Field(ge=1, le=SIP_DAY_MAX)
    start_date: date
    end_date: date | None = None
    step_up_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    notes: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_fund_target(self) -> Self:
        if self.fund_id is None and self.scheme_code is None:
            raise ValueError("Either fund_id or scheme_code must be provided")
        return self

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if not v.is_finite():
            raise ValueError("Amount must be a finite number")
        if v < SIP_MIN_AMOUNT or v > SIP_MAX_AMOUNT:
            raise ValueError(f"Amount must be between ₹{SIP_MIN_AMOUNT} and ₹{SIP_MAX_AMOUNT}")
        exp = v.as_tuple().exponent
        if not isinstance(exp, int) or exp < -2:
            raise ValueError("Amount cannot exceed 2 decimal places")
        return v

    @field_validator("step_up_percent")
    @classmethod
    def validate_step_up_percent(cls, v: Decimal) -> Decimal:
        if not v.is_finite():
            raise ValueError("Step-up percent must be a finite number")
        exp = v.as_tuple().exponent
        if not isinstance(exp, int) or exp < -2:
            raise ValueError("Step-up percent cannot exceed 2 decimal places")
        return v

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, v: date) -> date:
        if v < LEDGER_DATE_FLOOR:
            raise ValueError(f"Start date cannot precede {LEDGER_DATE_FLOOR}")
        # Note: future bound validation against clock today will also be checked in service
        return v


class SipPreviewRequest(BaseModel):
    """Payload to preview schedule installments for given SIP parameters."""

    fund_id: UUID | None = None
    scheme_code: int | None = None
    amount: Decimal
    day_of_month: int = Field(ge=1, le=SIP_DAY_MAX)
    start_date: date
    end_date: date | None = None
    step_up_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    notes: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_fund_target(self) -> Self:
        if self.fund_id is None and self.scheme_code is None:
            raise ValueError("Either fund_id or scheme_code must be provided")
        return self

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if not v.is_finite():
            raise ValueError("Amount must be a finite number")
        if v < SIP_MIN_AMOUNT or v > SIP_MAX_AMOUNT:
            raise ValueError(f"Amount must be between ₹{SIP_MIN_AMOUNT} and ₹{SIP_MAX_AMOUNT}")
        exp = v.as_tuple().exponent
        if not isinstance(exp, int) or exp < -2:
            raise ValueError("Amount cannot exceed 2 decimal places")
        return v

    @field_validator("step_up_percent")
    @classmethod
    def validate_step_up_percent(cls, v: Decimal) -> Decimal:
        if not v.is_finite():
            raise ValueError("Step-up percent must be a finite number")
        exp = v.as_tuple().exponent
        if not isinstance(exp, int) or exp < -2:
            raise ValueError("Step-up percent cannot exceed 2 decimal places")
        return v


class SipPreviewItem(BaseModel):
    """Single projected installment in schedule preview."""

    due_date: date
    planned_amount: DecimalStr


class SipPreviewResponse(BaseModel):
    """List of preview installments."""

    items: list[SipPreviewItem]
    count: int


class PatchSipRequest(BaseModel):
    """Payload to update mutable SIP parameters."""

    notes: str | None = Field(default=None, max_length=200)
    end_date: date | None = None


class PauseSipRequest(BaseModel):
    """Payload to pause a SIP."""

    from_date: date | None = None


class ResumeSipRequest(BaseModel):
    """Payload to resume a paused SIP."""

    on_date: date | None = None


class EndSipRequest(BaseModel):
    """Payload to end a SIP."""

    end_date: date | None = None


class SipPauseResponse(BaseModel):
    """Record of a pause interval."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paused_from: date
    resumed_on: date | None = None


class SipStatsResponse(BaseModel):
    """Aggregated statistics for a SIP across its installments."""

    installments_total: int = 0
    executed: int = 0
    pending: int = 0
    skipped: int = 0
    total_invested: DecimalStr = Decimal("0.00")
    units_acquired: DecimalStr = Decimal("0.0000")


class SipFundResponse(BaseModel):
    """Summary of fund master data for SIP responses."""

    scheme_code: int
    name: str
    amc: str
    plan_type: str
    option_type: str
    asset_class: str
    sub_category: str | None = None


class SipResponse(BaseModel):
    """Full detail of a SIP."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    portfolio_id: UUID
    fund: SipFundResponse
    amount: DecimalStr
    day_of_month: int
    start_date: date
    end_date: date | None = None
    step_up_percent: DecimalStr
    notes: str | None = None
    status: Literal["scheduled", "active", "paused", "ended"]
    next_due_date: date | None = None
    next_installment_amount: OptionalDecimalStr = None
    pauses: list[SipPauseResponse] = Field(default_factory=list)
    stats: SipStatsResponse = Field(default_factory=SipStatsResponse)
    created_at: datetime


class SipListResponse(BaseModel):
    """List of SIPs for a portfolio."""

    items: list[SipResponse]
    total: int


class SipInstallmentTransactionResponse(BaseModel):
    """Transaction created by an executed installment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    txn_date: date
    units: DecimalStr
    nav: DecimalStr
    amount: DecimalStr


class SipInstallmentResponse(BaseModel):
    """SIP installment detail."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sip_id: UUID
    due_date: date
    planned_amount: DecimalStr
    status: Literal["pending", "executed", "skipped"]
    nav_date: date | None = None
    transaction: SipInstallmentTransactionResponse | None = None


class InstallmentsListResponse(BaseModel):
    """Paginated list of installments for a SIP."""

    items: list[SipInstallmentResponse]
    total: int
    has_more: bool
    limit: int
    offset: int
