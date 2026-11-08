"""API router for NAV operational status and health metrics."""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_clock, get_db_session
from app.repositories.sync_runs import SyncRunRepository
from app.schemas.envelope import SuccessEnvelope
from app.schemas.fund import NavStatusResponse

router = APIRouter(prefix="/nav", tags=["nav"])


@router.get(
    "/status",
    response_model=SuccessEnvelope[NavStatusResponse],
    status_code=status.HTTP_200_OK,
)
async def get_nav_status(
    _current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    now: Annotated[datetime, Depends(get_clock)],
) -> SuccessEnvelope[NavStatusResponse]:
    """Retrieve operational status, last run counts, and freshness of AMFI NAV data."""
    latest_run, latest_success = await SyncRunRepository.get_last_amfi_run_status(session)

    is_stale = True
    if latest_success and latest_success.started_at:
        age = now - latest_success.started_at
        is_stale = age > timedelta(hours=36)

    schemes_parsed = latest_success.schemes_parsed if latest_success else 0
    funds_created = latest_success.funds_created if latest_success else 0
    funds_updated = latest_success.funds_updated if latest_success else 0
    nav_rows_written = latest_success.nav_rows_written if latest_success else 0

    return SuccessEnvelope(
        data=NavStatusResponse(
            last_run_time=latest_run.started_at if latest_run else None,
            last_run_status=latest_run.status if latest_run else None,
            last_success_time=latest_success.started_at if latest_success else None,
            schemes_parsed=schemes_parsed,
            funds_created=funds_created,
            funds_updated=funds_updated,
            nav_rows_written=nav_rows_written,
            is_stale=is_stale,
        )
    )
