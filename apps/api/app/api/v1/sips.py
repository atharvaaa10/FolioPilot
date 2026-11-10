"""API router for Systematic Investment Plans (SIPs) and installments."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_clock, get_db_session
from app.schemas.envelope import SuccessEnvelope
from app.schemas.sip import (
    CreateSipRequest,
    EndSipRequest,
    InstallmentsListResponse,
    PatchSipRequest,
    PauseSipRequest,
    ResumeSipRequest,
    SipInstallmentResponse,
    SipListResponse,
    SipPreviewRequest,
    SipPreviewResponse,
    SipResponse,
)
from app.services.sip_service import SipService

router = APIRouter(prefix="/portfolios", tags=["sips"])


@router.post(
    "/{id}/sips",
    response_model=SuccessEnvelope[SipResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_sip(
    id: UUID,
    payload: CreateSipRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[datetime, Depends(get_clock)],
) -> SuccessEnvelope[SipResponse]:
    """Create a new recurring investment plan (SIP) for a portfolio."""
    res = await SipService.create_sip(
        session,
        portfolio_id=id,
        user_id=current_user.id,
        payload=payload,
        clock=lambda: clock,
    )
    await session.commit()
    return SuccessEnvelope(data=res)


@router.post(
    "/{id}/sips/preview",
    response_model=SuccessEnvelope[SipPreviewResponse],
    status_code=status.HTTP_200_OK,
)
async def preview_sip_schedule(
    id: UUID,
    payload: SipPreviewRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    count: int = Query(default=12, ge=1, le=60),
) -> SuccessEnvelope[SipPreviewResponse]:
    """Generate projected schedule preview without database writes."""
    res = await SipService.preview_schedule(
        session,
        portfolio_id=id,
        user_id=current_user.id,
        payload=payload,
        count=count,
    )
    return SuccessEnvelope(data=res)


@router.get(
    "/{id}/sips",
    response_model=SuccessEnvelope[SipListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_sips(
    id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[datetime, Depends(get_clock)],
    status: str | None = Query(default=None),
) -> SuccessEnvelope[SipListResponse]:
    """List all SIPs for a portfolio with optional status filtering."""
    items = await SipService.list_sips(
        session,
        portfolio_id=id,
        user_id=current_user.id,
        status_filter=status,
        clock=lambda: clock,
    )
    return SuccessEnvelope(data=SipListResponse(items=items, total=len(items)))


@router.get(
    "/{id}/sips/{sip_id}",
    response_model=SuccessEnvelope[SipResponse],
    status_code=status.HTTP_200_OK,
)
async def get_sip(
    id: UUID,
    sip_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[datetime, Depends(get_clock)],
) -> SuccessEnvelope[SipResponse]:
    """Fetch details and current derived status of a single SIP."""
    res = await SipService.get_sip(
        session,
        portfolio_id=id,
        sip_id=sip_id,
        user_id=current_user.id,
        clock=lambda: clock,
    )
    return SuccessEnvelope(data=res)


@router.patch(
    "/{id}/sips/{sip_id}",
    response_model=SuccessEnvelope[SipResponse],
    status_code=status.HTTP_200_OK,
)
async def patch_sip(
    id: UUID,
    sip_id: UUID,
    payload: PatchSipRequest,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[datetime, Depends(get_clock)],
) -> SuccessEnvelope[SipResponse]:
    """Update mutable fields (notes, end_date) of a SIP."""
    res = await SipService.patch_sip(
        session,
        portfolio_id=id,
        sip_id=sip_id,
        user_id=current_user.id,
        payload=payload,
        clock=lambda: clock,
    )
    await session.commit()
    return SuccessEnvelope(data=res)


@router.post(
    "/{id}/sips/{sip_id}/pause",
    response_model=SuccessEnvelope[SipResponse],
    status_code=status.HTTP_200_OK,
)
async def pause_sip(
    id: UUID,
    sip_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[datetime, Depends(get_clock)],
    payload: PauseSipRequest = PauseSipRequest(),
) -> SuccessEnvelope[SipResponse]:
    """Pause a SIP starting from from_date (defaults to today)."""
    res = await SipService.pause_sip(
        session,
        portfolio_id=id,
        sip_id=sip_id,
        user_id=current_user.id,
        from_date=payload.from_date,
        clock=lambda: clock,
    )
    await session.commit()
    return SuccessEnvelope(data=res)


@router.post(
    "/{id}/sips/{sip_id}/resume",
    response_model=SuccessEnvelope[SipResponse],
    status_code=status.HTTP_200_OK,
)
async def resume_sip(
    id: UUID,
    sip_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[datetime, Depends(get_clock)],
    payload: ResumeSipRequest = ResumeSipRequest(),
) -> SuccessEnvelope[SipResponse]:
    """Resume a paused SIP on on_date (defaults to today)."""
    res = await SipService.resume_sip(
        session,
        portfolio_id=id,
        sip_id=sip_id,
        user_id=current_user.id,
        on_date=payload.on_date,
        clock=lambda: clock,
    )
    await session.commit()
    return SuccessEnvelope(data=res)


@router.post(
    "/{id}/sips/{sip_id}/end",
    response_model=SuccessEnvelope[SipResponse],
    status_code=status.HTTP_200_OK,
)
async def end_sip(
    id: UUID,
    sip_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[datetime, Depends(get_clock)],
    payload: EndSipRequest = EndSipRequest(),
) -> SuccessEnvelope[SipResponse]:
    """End a SIP on end_date (defaults to today)."""
    res = await SipService.end_sip(
        session,
        portfolio_id=id,
        sip_id=sip_id,
        user_id=current_user.id,
        end_date=payload.end_date,
        clock=lambda: clock,
    )
    await session.commit()
    return SuccessEnvelope(data=res)


@router.delete(
    "/{id}/sips/{sip_id}",
    response_model=SuccessEnvelope[dict[str, bool]],
    status_code=status.HTTP_200_OK,
)
async def delete_sip(
    id: UUID,
    sip_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[dict[str, bool]]:
    """Delete a SIP and its installments; created transactions become ordinary."""
    await SipService.delete_sip(
        session,
        portfolio_id=id,
        sip_id=sip_id,
        user_id=current_user.id,
    )
    await session.commit()
    return SuccessEnvelope(data={"deleted": True})


@router.get(
    "/{id}/sips/{sip_id}/installments",
    response_model=SuccessEnvelope[InstallmentsListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_sip_installments(
    id: UUID,
    sip_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SuccessEnvelope[InstallmentsListResponse]:
    """List installments for a SIP with pagination and optional status filter."""
    items, total, has_more = await SipService.list_installments(
        session,
        portfolio_id=id,
        sip_id=sip_id,
        user_id=current_user.id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return SuccessEnvelope(
        data=InstallmentsListResponse(
            items=items,
            total=total,
            has_more=has_more,
            limit=limit,
            offset=offset,
        )
    )


@router.post(
    "/{id}/sips/{sip_id}/installments/{installment_id}/skip",
    response_model=SuccessEnvelope[SipInstallmentResponse],
    status_code=status.HTTP_200_OK,
)
async def skip_sip_installment(
    id: UUID,
    sip_id: UUID,
    installment_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[SipInstallmentResponse]:
    """Skip an installment. If executed, removes its transaction under ledger validation."""
    res = await SipService.skip_installment(
        session,
        portfolio_id=id,
        sip_id=sip_id,
        installment_id=installment_id,
        user_id=current_user.id,
    )
    await session.commit()
    return SuccessEnvelope(data=res)
