"""REST API router for portfolio valuation, XIRR, and historical value series."""

import datetime as dt
from uuid import UUID

import redis.asyncio as redis_async
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_clock, get_current_user, get_db_session, get_redis_client
from app.core.constants import VALUATION_REQUESTS_PER_MIN
from app.core.errors import RateLimitedError
from app.models.user import User
from app.schemas.envelope import SuccessEnvelope
from app.schemas.valuation import (
    ValuationResponse,
    ValuationSummaryResponse,
    ValueSeriesResponse,
)
from app.services.rate_limit import check_rate_limit
from app.services.valuation_service import ValuationService

router = APIRouter(tags=["valuation"])


async def _enforce_valuation_rate_limit(
    redis_client: redis_async.Redis,
    user_id: UUID,
    now: dt.datetime,
) -> None:
    """Enforce per-user rate limit covering valuation endpoints."""
    rl_result = await check_rate_limit(
        redis_client,
        prefix="rl_valuation",
        identifier=str(user_id),
        limit=VALUATION_REQUESTS_PER_MIN,
        window_seconds=60,
        now_timestamp=int(now.timestamp()),
    )
    if not rl_result.allowed:
        raise RateLimitedError(
            "Valuation rate limit exceeded. Please wait.",
            retry_after=rl_result.retry_after,
        )


@router.get(
    "/portfolios/{portfolio_id}/valuation",
    summary="Get live portfolio valuation, gains, and XIRR",
)
async def get_portfolio_valuation(
    portfolio_id: UUID,
    response: Response,
    include_closed: bool = Query(False, description="Include fully closed positions"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    redis_client: redis_async.Redis = Depends(get_redis_client),
    clock: dt.datetime = Depends(get_clock),
) -> SuccessEnvelope[ValuationResponse]:
    """Return live portfolio valuation, per-fund gains, XIRR, and totals."""
    await _enforce_valuation_rate_limit(redis_client, current_user.id, clock)
    response.headers["Cache-Control"] = "no-store"

    data = await ValuationService.get_portfolio_valuation(
        session=session,
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        clock=clock,
        include_closed=include_closed,
    )
    return SuccessEnvelope(data=data)


@router.get(
    "/valuation/summary",
    summary="Get overall multi-portfolio valuation summary and allocation",
)
async def get_valuation_summary(
    response: Response,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    redis_client: redis_async.Redis = Depends(get_redis_client),
    clock: dt.datetime = Depends(get_clock),
) -> SuccessEnvelope[ValuationSummaryResponse]:
    """Return aggregated totals, per-portfolio summaries, allocation, and top holdings."""
    await _enforce_valuation_rate_limit(redis_client, current_user.id, clock)
    response.headers["Cache-Control"] = "no-store"

    data = await ValuationService.get_valuation_summary(
        session=session,
        user_id=current_user.id,
        clock=clock,
    )
    return SuccessEnvelope(data=data)


@router.get(
    "/portfolios/{portfolio_id}/value-series",
    summary="Get historical value-over-time series for portfolio",
)
async def get_value_series(
    portfolio_id: UUID,
    response: Response,
    range: str = Query("1y", description="Series range: 1m, 6m, 1y, 3y, 5y, max"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    redis_client: redis_async.Redis = Depends(get_redis_client),
    clock: dt.datetime = Depends(get_clock),
) -> SuccessEnvelope[ValueSeriesResponse]:
    """Return historical value and cost basis time series."""
    await _enforce_valuation_rate_limit(redis_client, current_user.id, clock)
    response.headers["Cache-Control"] = "no-store"

    data = await ValuationService.get_value_series(
        session=session,
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        clock=clock,
        range_str=range,
    )
    return SuccessEnvelope(data=data)
