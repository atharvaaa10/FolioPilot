"""API router for mutual fund search, scheme details, historical NAV, and tracking."""

from datetime import date, datetime
from typing import Annotated

import redis.asyncio as redis_async
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    get_clock,
    get_db_session,
    get_redis_client,
)
from app.core.config import Settings, get_settings
from app.core.errors import FundNotFoundError, RateLimitedError
from app.repositories.funds import FundRepository
from app.repositories.nav_history import NavHistoryRepository
from app.schemas.envelope import SuccessEnvelope
from app.schemas.fund import (
    FundDetailResponse,
    FundNavHistoryResponse,
    FundSearchItem,
    FundSearchResponse,
    NavPoint,
    TrackFundResponse,
)
from app.services.nav_backfill import ensure_tracked
from app.services.rate_limit import check_rate_limit

router = APIRouter(prefix="/funds", tags=["funds"])


@router.get(
    "/search",
    response_model=SuccessEnvelope[FundSearchResponse],
    status_code=status.HTTP_200_OK,
)
async def search_funds(
    _current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis_client: Annotated[redis_async.Redis, Depends(get_redis_client)],
    now: Annotated[datetime, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
    q: str | None = Query(None, description="Search query (name, scheme code, or ISIN)"),
    asset_class: str | None = Query(None, description="Filter by asset class"),
    plan: str | None = Query(None, description="Filter by plan type (direct/regular)"),
    option: str | None = Query(None, description="Filter by option type (growth/idcw)"),
    active_only: bool = Query(True, description="Filter active funds only"),
    limit: int = Query(20, ge=1, le=50, description="Page limit (max 50)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> SuccessEnvelope[FundSearchResponse]:
    """Search and filter mutual funds with ranking and rate limiting."""
    # Rate limit: 60 queries/min per authenticated user
    rl_result = await check_rate_limit(
        redis_client,
        prefix="rl_fund_search",
        identifier=str(_current_user.id),
        limit=settings.FUND_SEARCH_RATE_LIMIT_PER_MIN,
        window_seconds=60,
        now_timestamp=int(now.timestamp()),
    )
    if not rl_result.allowed:
        raise RateLimitedError(
            "Search rate limit exceeded. Please slow down.",
            retry_after=rl_result.retry_after,
        )

    funds, has_more = await FundRepository.search_funds(
        session,
        query=q,
        asset_class=asset_class,
        plan=plan,
        option=option,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )

    items = [FundSearchItem.model_validate(f) for f in funds]
    return SuccessEnvelope(data=FundSearchResponse(items=items, has_more=has_more))


@router.get(
    "/{scheme_code}",
    response_model=SuccessEnvelope[FundDetailResponse],
    status_code=status.HTTP_200_OK,
)
async def get_fund_detail(
    scheme_code: int,
    _current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[FundDetailResponse]:
    """Retrieve complete metadata and classification details for a fund scheme."""
    fund = await FundRepository.get_by_scheme_code(session, scheme_code)
    if fund is None:
        raise FundNotFoundError(f"Fund with scheme code {scheme_code} not found")

    return SuccessEnvelope(data=FundDetailResponse.model_validate(fund))


@router.get(
    "/{scheme_code}/nav",
    response_model=SuccessEnvelope[FundNavHistoryResponse],
    status_code=status.HTTP_200_OK,
)
async def get_fund_nav_history(
    scheme_code: int,
    _current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    from_date: date | None = Query(None, alias="from", description="Start date (inclusive)"),
    to_date: date | None = Query(None, alias="to", description="End date (inclusive)"),
    limit: int | None = Query(None, ge=1, description="Max history points"),
) -> SuccessEnvelope[FundNavHistoryResponse]:
    """Retrieve chronological NAV points for a fund."""
    fund = await FundRepository.get_by_scheme_code(session, scheme_code)
    if fund is None:
        raise FundNotFoundError(f"Fund with scheme code {scheme_code} not found")

    has_hist = await NavHistoryRepository.has_history(session, fund.id)
    history_records = await NavHistoryRepository.get_history(
        session,
        fund_id=fund.id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )

    points = [NavPoint(date=r.nav_date, nav=r.nav) for r in history_records]

    return SuccessEnvelope(
        data=FundNavHistoryResponse(
            scheme_code=fund.scheme_code,
            name=fund.name,
            history_available=has_hist,
            points=points,
        )
    )


@router.post(
    "/{scheme_code}/track",
    response_model=SuccessEnvelope[TrackFundResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def track_fund(
    scheme_code: int,
    _current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[TrackFundResponse]:
    """Flag fund as tracked and enqueue historical NAV backfill if needed."""
    fund = await FundRepository.get_by_scheme_code(session, scheme_code)
    if fund is None:
        raise FundNotFoundError(f"Fund with scheme code {scheme_code} not found")

    _is_tracked, queued = await ensure_tracked(session, fund, enqueue_task=True)
    await session.commit()

    status_str = "queued" if queued else "already_tracked"
    return SuccessEnvelope(
        data=TrackFundResponse(
            scheme_code=fund.scheme_code,
            status=status_str,
        )
    )
