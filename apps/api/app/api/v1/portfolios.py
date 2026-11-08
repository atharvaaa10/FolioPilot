"""API router for Portfolios, Target Allocations, and the Transaction Ledger."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_clock, get_db_session
from app.core.errors import ValidationError
from app.models.transaction import Transaction
from app.repositories.funds import FundRepository
from app.repositories.transactions import TransactionRepository
from app.schemas.envelope import SuccessEnvelope
from app.schemas.portfolio import (
    PortfolioCreate,
    PortfolioResponse,
    PortfolioTargetsUpdate,
    PortfolioUpdate,
    TargetItem,
)
from app.schemas.transaction import (
    HoldingsListResponse,
    PortfolioDetailResponse,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)
from app.services.portfolio_service import PortfolioService
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


def _to_portfolio_response(p: Any) -> PortfolioResponse:
    targets_list = p.__dict__.get("targets")
    if targets_list is None:
        try:
            targets_list = getattr(p, "targets", [])
        except Exception:
            targets_list = []
    targets = [
        TargetItem(asset_class=t.asset_class, target_pct=t.target_pct) for t in (targets_list or [])
    ]
    return PortfolioResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        created_at=p.created_at,
        updated_at=p.updated_at,
        targets=targets,
    )


def _to_transaction_response(t: Transaction) -> TransactionResponse:
    return TransactionResponse(
        id=t.id,
        portfolio_id=t.portfolio_id,
        fund_id=t.fund_id,
        scheme_code=t.fund.scheme_code if t.fund else None,
        fund_name=t.fund.name if t.fund else None,
        txn_type=t.txn_type,
        txn_date=t.txn_date,
        units=t.units,
        nav=t.nav,
        amount=t.amount,
        notes=t.notes,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get(
    "",
    response_model=SuccessEnvelope[list[PortfolioResponse]],
    status_code=status.HTTP_200_OK,
)
async def list_portfolios(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[list[PortfolioResponse]]:
    """List all portfolios owned by the authenticated user."""
    portfolios = await PortfolioService.list_portfolios(session, current_user.id)
    return SuccessEnvelope(data=[_to_portfolio_response(p) for p in portfolios])


@router.post(
    "",
    response_model=SuccessEnvelope[PortfolioResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_portfolio(
    current_user: CurrentUser,
    payload: PortfolioCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[PortfolioResponse]:
    """Create a new portfolio."""
    portfolio = await PortfolioService.create_portfolio(
        session,
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    await session.commit()
    return SuccessEnvelope(data=_to_portfolio_response(portfolio))


@router.get(
    "/{portfolio_id}",
    response_model=SuccessEnvelope[PortfolioDetailResponse],
    status_code=status.HTTP_200_OK,
)
async def get_portfolio_detail(
    portfolio_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[PortfolioDetailResponse]:
    """Fetch complete portfolio view including metadata, targets, and summary metrics."""
    portfolio = await PortfolioService.get_portfolio(
        session, portfolio_id, user_id=current_user.id, load_targets=True
    )
    holdings = await TransactionService.get_holdings(session, portfolio_id, user_id=current_user.id)
    txns_count = await TransactionRepository.count_by_portfolio(session, portfolio_id)

    targets = [
        TargetItem(asset_class=t.asset_class, target_pct=t.target_pct)
        for t in getattr(portfolio, "targets", [])
    ]

    detail = PortfolioDetailResponse(
        id=portfolio.id,
        name=portfolio.name,
        description=portfolio.description,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
        targets=targets,
        total_cost_basis=holdings.totals.cost_basis,
        open_positions=holdings.totals.open_positions,
        total_transactions=txns_count,
    )
    return SuccessEnvelope(data=detail)


@router.patch(
    "/{portfolio_id}",
    response_model=SuccessEnvelope[PortfolioResponse],
    status_code=status.HTTP_200_OK,
)
async def update_portfolio(
    portfolio_id: UUID,
    payload: PortfolioUpdate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[PortfolioResponse]:
    """Update portfolio name or description."""
    portfolio = await PortfolioService.update_portfolio(
        session,
        portfolio_id,
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    await session.commit()
    # Reload with targets
    portfolio = await PortfolioService.get_portfolio(
        session, portfolio_id, user_id=current_user.id, load_targets=True
    )
    return SuccessEnvelope(data=_to_portfolio_response(portfolio))


@router.delete(
    "/{portfolio_id}",
    response_model=SuccessEnvelope[dict[str, bool]],
    status_code=status.HTTP_200_OK,
)
async def delete_portfolio(
    portfolio_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[dict[str, bool]]:
    """Delete a portfolio (cascades to targets and transactions)."""
    await PortfolioService.delete_portfolio(session, portfolio_id, user_id=current_user.id)
    await session.commit()
    return SuccessEnvelope(data={"deleted": True})


@router.put(
    "/{portfolio_id}/targets",
    response_model=SuccessEnvelope[list[TargetItem]],
    status_code=status.HTTP_200_OK,
)
async def set_portfolio_targets(
    portfolio_id: UUID,
    payload: PortfolioTargetsUpdate | list[TargetItem],
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[list[TargetItem]]:
    """Replace target allocations for portfolio (must sum to 100.00% if non-empty)."""
    raw_targets = payload.targets if isinstance(payload, PortfolioTargetsUpdate) else payload
    targets_input = [(t.asset_class, t.target_pct) for t in raw_targets]
    saved_targets = await PortfolioService.set_targets(
        session, portfolio_id, user_id=current_user.id, targets=targets_input
    )
    await session.commit()
    return SuccessEnvelope(
        data=[TargetItem(asset_class=t.asset_class, target_pct=t.target_pct) for t in saved_targets]
    )


@router.get(
    "/{portfolio_id}/transactions",
    response_model=SuccessEnvelope[list[TransactionResponse]],
    status_code=status.HTTP_200_OK,
)
async def list_transactions(
    portfolio_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    fund_id: UUID | None = Query(None, description="Filter transactions by fund ID"),
) -> SuccessEnvelope[list[TransactionResponse]]:
    """List transactions for portfolio in deterministic ledger order."""
    txns = await TransactionService.list_transactions(
        session, portfolio_id, user_id=current_user.id, fund_id=fund_id
    )
    return SuccessEnvelope(data=[_to_transaction_response(t) for t in txns])


@router.post(
    "/{portfolio_id}/transactions",
    response_model=SuccessEnvelope[TransactionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_transaction(
    portfolio_id: UUID,
    payload: TransactionCreate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    now: Annotated[datetime, Depends(get_clock)],
) -> SuccessEnvelope[TransactionResponse]:
    """Append a BUY or SELL transaction to the portfolio ledger."""
    target_fund_id = payload.fund_id
    if target_fund_id is None and payload.scheme_code is not None:
        fund = await FundRepository.get_by_scheme_code(session, payload.scheme_code)
        if not fund:
            raise ValidationError(f"Mutual fund scheme {payload.scheme_code} not found")
        target_fund_id = fund.id
    elif target_fund_id is None:
        raise ValidationError("Either fund_id or scheme_code is required")

    txn = await TransactionService.add_transaction(
        session,
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        fund_id=target_fund_id,
        txn_type=payload.txn_type,
        txn_date=payload.txn_date,
        units=payload.units,
        nav=payload.nav,
        amount=payload.amount,
        notes=payload.notes,
        clock=lambda: now,
    )
    await session.commit()

    # Re-fetch with fund relation loaded
    saved_txn = await TransactionService.get_transaction(
        session,
        portfolio_id=portfolio_id,
        transaction_id=txn.id,
        user_id=current_user.id,
    )
    return SuccessEnvelope(data=_to_transaction_response(saved_txn))


@router.get(
    "/{portfolio_id}/transactions/{transaction_id}",
    response_model=SuccessEnvelope[TransactionResponse],
    status_code=status.HTTP_200_OK,
)
async def get_transaction(
    portfolio_id: UUID,
    transaction_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[TransactionResponse]:
    """Fetch single transaction by ID."""
    txn = await TransactionService.get_transaction(
        session,
        portfolio_id=portfolio_id,
        transaction_id=transaction_id,
        user_id=current_user.id,
    )
    return SuccessEnvelope(data=_to_transaction_response(txn))


@router.patch(
    "/{portfolio_id}/transactions/{transaction_id}",
    response_model=SuccessEnvelope[TransactionResponse],
    status_code=status.HTTP_200_OK,
)
async def update_transaction(
    portfolio_id: UUID,
    transaction_id: UUID,
    payload: TransactionUpdate,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    now: Annotated[datetime, Depends(get_clock)],
) -> SuccessEnvelope[TransactionResponse]:
    """Update an existing transaction in portfolio ledger."""
    txn = await TransactionService.update_transaction(
        session,
        portfolio_id=portfolio_id,
        transaction_id=transaction_id,
        user_id=current_user.id,
        txn_date=payload.txn_date,
        units=payload.units,
        nav=payload.nav,
        amount=payload.amount,
        notes=payload.notes,
        clock=lambda: now,
    )
    await session.commit()

    saved_txn = await TransactionService.get_transaction(
        session,
        portfolio_id=portfolio_id,
        transaction_id=txn.id,
        user_id=current_user.id,
    )
    return SuccessEnvelope(data=_to_transaction_response(saved_txn))


@router.delete(
    "/{portfolio_id}/transactions/{transaction_id}",
    response_model=SuccessEnvelope[dict[str, bool]],
    status_code=status.HTTP_200_OK,
)
async def delete_transaction(
    portfolio_id: UUID,
    transaction_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[dict[str, bool]]:
    """Delete a transaction while validating that subsequent ledger integrity remains intact."""
    await TransactionService.delete_transaction(
        session,
        portfolio_id=portfolio_id,
        transaction_id=transaction_id,
        user_id=current_user.id,
    )
    await session.commit()
    return SuccessEnvelope(data={"deleted": True})


@router.get(
    "/{portfolio_id}/holdings",
    response_model=SuccessEnvelope[HoldingsListResponse],
    status_code=status.HTTP_200_OK,
)
async def get_portfolio_holdings(
    portfolio_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuccessEnvelope[HoldingsListResponse]:
    """Get calculated holdings for portfolio derived from ledger."""
    holdings = await TransactionService.get_holdings(session, portfolio_id, user_id=current_user.id)
    return SuccessEnvelope(data=holdings)
