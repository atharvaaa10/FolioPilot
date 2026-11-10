"""Orchestration service for SIPs, pauses, and installments under portfolio locks."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    MAX_INSTALLMENTS_PER_GENERATION,
    MAX_PREVIEW_COUNT,
    MAX_SIPS_PER_PORTFOLIO,
    SIP_START_MAX_FUTURE_DAYS,
)
from app.core.errors import (
    FundInactiveError,
    FundNotFoundError,
    InstallmentNotFoundError,
    InstallmentNotSkippableError,
    PortfolioNotFoundError,
    SipAlreadyEndedError,
    SipAlreadyPausedError,
    SipInvalidScheduleError,
    SipLimitReachedError,
    SipNotFoundError,
    SipNotPausedError,
    ValidationError,
)
from app.core.logging import get_logger
from app.models.sip import Sip
from app.repositories.funds import FundRepository
from app.repositories.portfolios import PortfolioRepository
from app.repositories.sips import SipRepository
from app.repositories.transactions import TransactionRepository
from app.schemas.sip import (
    CreateSipRequest,
    PatchSipRequest,
    SipFundResponse,
    SipInstallmentResponse,
    SipInstallmentTransactionResponse,
    SipPauseResponse,
    SipPreviewItem,
    SipPreviewRequest,
    SipPreviewResponse,
    SipResponse,
    SipStatsResponse,
)
from app.services.ledger import validate_ledger
from app.services.nav_backfill import ensure_tracked
from app.services.sip_schedule import (
    compute_k,
    derive_status,
    first_due_date,
    iter_due_dates,
    next_due_date,
    planned_amount,
    validate_pauses,
)

logger = get_logger("services.sip")
KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


class SipService:
    """Service orchestrating SIP operations with pessimistic portfolio row locking."""

    @staticmethod
    def _to_sip_response(
        sip: Sip,
        stats: dict[str, Any] | None,
        today_kolkata: date,
    ) -> SipResponse:
        """Convert a Sip model and stats dict into a strongly-typed SipResponse."""
        fund = sip.fund
        fund_resp = SipFundResponse(
            scheme_code=fund.scheme_code,
            name=fund.name,
            amc=fund.amc,
            plan_type=fund.plan_type,
            option_type=fund.option_type,
            asset_class=fund.asset_class,
            sub_category=fund.sub_category,
        )

        derived_st = derive_status(sip.start_date, sip.end_date, sip.pauses, today_kolkata)
        next_due = next_due_date(
            sip.start_date, sip.day_of_month, sip.end_date, sip.pauses, today_kolkata
        )

        next_amt: Decimal | None = None
        if next_due is not None:
            origin_date = first_due_date(sip.start_date, sip.day_of_month)
            k = compute_k(origin_date, next_due)
            next_amt = planned_amount(sip.amount, sip.step_up_percent, k)

        pause_responses = [
            SipPauseResponse(
                id=p.id,
                paused_from=p.paused_from,
                resumed_on=p.resumed_on,
            )
            for p in sip.pauses
        ]

        st = stats or {
            "installments_total": 0,
            "executed": 0,
            "pending": 0,
            "skipped": 0,
            "total_invested": Decimal("0.00"),
            "units_acquired": Decimal("0.0000"),
        }
        stats_resp = SipStatsResponse(
            installments_total=st["installments_total"],
            executed=st["executed"],
            pending=st["pending"],
            skipped=st["skipped"],
            total_invested=st["total_invested"],
            units_acquired=st["units_acquired"],
        )

        return SipResponse(
            id=sip.id,
            portfolio_id=sip.portfolio_id,
            fund=fund_resp,
            amount=sip.amount,
            day_of_month=sip.day_of_month,
            start_date=sip.start_date,
            end_date=sip.end_date,
            step_up_percent=sip.step_up_percent,
            notes=sip.notes,
            status=derived_st,  # type: ignore[arg-type]
            next_due_date=next_due,
            next_installment_amount=next_amt,
            pauses=pause_responses,
            stats=stats_resp,
            created_at=sip.created_at,
        )

    @staticmethod
    async def create_sip(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        payload: CreateSipRequest,
        clock: Callable[[], datetime] | None = None,
    ) -> SipResponse:
        """Create a new SIP under portfolio row lock and lazily generate initial installments."""
        # 1. Acquire portfolio lock and verify ownership (404 rule)
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        # 2. Check maximum SIP limit
        count = await SipRepository.count_by_portfolio(session, portfolio_id)
        if count >= MAX_SIPS_PER_PORTFOLIO:
            raise SipLimitReachedError(
                f"Cannot create more than {MAX_SIPS_PER_PORTFOLIO} SIPs per portfolio"
            )

        # 3. Verify fund exists and is active
        if payload.fund_id is not None:
            fund = await FundRepository.get_by_id(session, payload.fund_id)
        elif payload.scheme_code is not None:
            fund = await FundRepository.get_by_scheme_code(session, payload.scheme_code)
        else:
            raise ValidationError("Either fund_id or scheme_code must be provided")

        if fund is None:
            ident = str(payload.fund_id or payload.scheme_code)
            raise FundNotFoundError(f"Fund {ident} not found")

        if not fund.is_active:
            raise FundInactiveError(
                f"Fund '{fund.name}' ({fund.scheme_code}) is inactive "
                "and cannot accept new investments"
            )

        # 4. Reference dates & bounds
        now_utc = clock() if clock else datetime.now(UTC)
        today_kolkata = now_utc.astimezone(KOLKATA_TZ).date()

        if (payload.start_date - today_kolkata).days > SIP_START_MAX_FUTURE_DAYS:
            raise ValidationError(
                f"Start date cannot exceed {SIP_START_MAX_FUTURE_DAYS} days in the future"
            )

        if payload.end_date is not None and payload.end_date < payload.start_date:
            raise ValidationError("End date cannot precede start date")

        # 5. Schedule validity check (must contain at least one valid due date)
        first_due = iter_due_dates(
            payload.start_date, payload.day_of_month, end_date=payload.end_date, max_count=1
        )
        if not first_due:
            raise SipInvalidScheduleError(
                "SIP schedule contains no valid due dates in the specified range",
                details={
                    "start_date": str(payload.start_date),
                    "day_of_month": payload.day_of_month,
                    "end_date": str(payload.end_date) if payload.end_date else None,
                },
            )

        # 6. Create SIP record
        sip = await SipRepository.create(
            session,
            portfolio_id=portfolio_id,
            fund_id=fund.id,
            amount=payload.amount,
            day_of_month=payload.day_of_month,
            start_date=payload.start_date,
            end_date=payload.end_date,
            step_up_percent=payload.step_up_percent,
            notes=payload.notes,
        )

        # 7. Generate lazy installments up to today (IST)
        due_dates = iter_due_dates(
            payload.start_date,
            payload.day_of_month,
            end_date=payload.end_date,
            until=today_kolkata,
            max_count=MAX_INSTALLMENTS_PER_GENERATION,
        )

        origin_date = first_due_date(payload.start_date, payload.day_of_month)
        installment_dicts = []
        for d in due_dates:
            k = compute_k(origin_date, d)
            amt = planned_amount(payload.amount, payload.step_up_percent, k)
            installment_dicts.append(
                {
                    "sip_id": sip.id,
                    "due_date": d,
                    "planned_amount": amt,
                    "status": "pending",
                }
            )

        if installment_dicts:
            await SipRepository.insert_installments_batch(session, installment_dicts)

        # 8. Ensure fund is flagged tracked
        await ensure_tracked(session, fund, enqueue_task=True)

        # Reload SIP with fund and pauses
        loaded_sip = await SipRepository.get_by_id(session, sip.id)
        assert loaded_sip is not None

        # 9. Trigger immediate execution enqueue after commit
        try:
            from app.workers.tasks import execute_pending_for_fund

            execute_pending_for_fund.delay(str(fund.id))
        except Exception as exc:
            logger.warning(
                "Could not enqueue execute_pending_for_fund on SIP creation",
                fund_id=str(fund.id),
                error=str(exc),
            )

        stats_map = await SipRepository.get_stats_for_sips(session, [sip.id])
        return SipService._to_sip_response(loaded_sip, stats_map.get(sip.id), today_kolkata)

    @staticmethod
    async def get_sip(
        session: AsyncSession,
        portfolio_id: UUID,
        sip_id: UUID,
        user_id: UUID,
        clock: Callable[[], datetime] | None = None,
    ) -> SipResponse:
        """Fetch a single SIP by ID enforcing portfolio ownership."""
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        sip = await SipRepository.get_by_id(session, sip_id)
        if sip is None or sip.portfolio_id != portfolio_id:
            raise SipNotFoundError("SIP not found")

        now_utc = clock() if clock else datetime.now(UTC)
        today_kolkata = now_utc.astimezone(KOLKATA_TZ).date()

        stats_map = await SipRepository.get_stats_for_sips(session, [sip.id])
        return SipService._to_sip_response(sip, stats_map.get(sip.id), today_kolkata)

    @staticmethod
    async def list_sips(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        status_filter: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> list[SipResponse]:
        """List all SIPs for a portfolio with optional status filter and no N+1 queries."""
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        sips = await SipRepository.list_by_portfolio(session, portfolio_id)
        if not sips:
            return []

        now_utc = clock() if clock else datetime.now(UTC)
        today_kolkata = now_utc.astimezone(KOLKATA_TZ).date()

        stats_map = await SipRepository.get_stats_for_sips(session, [s.id for s in sips])
        responses: list[SipResponse] = []

        for sip in sips:
            resp = SipService._to_sip_response(sip, stats_map.get(sip.id), today_kolkata)
            if status_filter:
                if resp.status.lower() == status_filter.lower():
                    responses.append(resp)
            else:
                responses.append(resp)

        return responses

    @staticmethod
    async def preview_schedule(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        payload: SipPreviewRequest,
        count: int = 12,
    ) -> SipPreviewResponse:
        """Generate projected schedule preview without database writes."""
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        preview_limit = min(max(1, count), MAX_PREVIEW_COUNT)
        due_dates = iter_due_dates(
            payload.start_date,
            payload.day_of_month,
            end_date=payload.end_date,
            max_count=preview_limit,
        )

        if not due_dates:
            raise SipInvalidScheduleError(
                "SIP schedule contains no valid due dates in the specified range",
                details={
                    "start_date": str(payload.start_date),
                    "day_of_month": payload.day_of_month,
                    "end_date": str(payload.end_date) if payload.end_date else None,
                },
            )

        origin_date = first_due_date(payload.start_date, payload.day_of_month)
        items = []
        for d in due_dates:
            k = compute_k(origin_date, d)
            amt = planned_amount(payload.amount, payload.step_up_percent, k)
            items.append(SipPreviewItem(due_date=d, planned_amount=amt))

        return SipPreviewResponse(items=items, count=len(items))

    @staticmethod
    async def pause_sip(
        session: AsyncSession,
        portfolio_id: UUID,
        sip_id: UUID,
        user_id: UUID,
        from_date: date | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> SipResponse:
        """Pause a SIP starting from from_date (defaults to today, must be >= today)."""
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        sip = await SipRepository.get_by_id_for_update(session, sip_id)
        if sip is None or sip.portfolio_id != portfolio_id:
            raise SipNotFoundError("SIP not found")

        now_utc = clock() if clock else datetime.now(UTC)
        today_kolkata = now_utc.astimezone(KOLKATA_TZ).date()

        current_status = derive_status(sip.start_date, sip.end_date, sip.pauses, today_kolkata)
        if current_status == "ended":
            raise SipAlreadyEndedError("Cannot pause a SIP that has already ended")

        open_pause = await SipRepository.get_open_pause(session, sip.id)
        if open_pause is not None:
            raise SipAlreadyPausedError("SIP already has an active open pause")

        p_from = from_date if from_date is not None else today_kolkata
        if p_from < today_kolkata:
            raise ValidationError("Pause start date cannot precede today")

        # Validate against existing pauses
        class TempPause:
            def __init__(self, f: date, r: date | None) -> None:
                self.paused_from = f
                self.resumed_on = r

        candidate_pauses = [TempPause(p.paused_from, p.resumed_on) for p in sip.pauses]
        candidate_pauses.append(TempPause(p_from, None))
        if not validate_pauses(candidate_pauses):
            raise ValidationError("Pause interval overlaps with existing pause intervals")

        await SipRepository.create_pause(session, sip_id=sip.id, paused_from=p_from)

        loaded_sip = await SipRepository.get_by_id(session, sip.id)
        assert loaded_sip is not None
        stats_map = await SipRepository.get_stats_for_sips(session, [sip.id])
        return SipService._to_sip_response(loaded_sip, stats_map.get(sip.id), today_kolkata)

    @staticmethod
    async def resume_sip(
        session: AsyncSession,
        portfolio_id: UUID,
        sip_id: UUID,
        user_id: UUID,
        on_date: date | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> SipResponse:
        """Resume a paused SIP on on_date (defaults to today, must be > paused_from)."""
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        sip = await SipRepository.get_by_id_for_update(session, sip_id)
        if sip is None or sip.portfolio_id != portfolio_id:
            raise SipNotFoundError("SIP not found")

        now_utc = clock() if clock else datetime.now(UTC)
        today_kolkata = now_utc.astimezone(KOLKATA_TZ).date()

        open_pause = await SipRepository.get_open_pause(session, sip.id)
        if open_pause is None:
            raise SipNotPausedError("SIP is not currently paused")

        p_on = on_date if on_date is not None else today_kolkata
        if p_on <= open_pause.paused_from:
            raise ValidationError("Resume date must be strictly after pause start date")

        open_pause.resumed_on = p_on
        await session.flush()

        loaded_sip = await SipRepository.get_by_id(session, sip.id)
        assert loaded_sip is not None
        stats_map = await SipRepository.get_stats_for_sips(session, [sip.id])
        return SipService._to_sip_response(loaded_sip, stats_map.get(sip.id), today_kolkata)

    @staticmethod
    async def end_sip(
        session: AsyncSession,
        portfolio_id: UUID,
        sip_id: UUID,
        user_id: UUID,
        end_date: date | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> SipResponse:
        """End a SIP on end_date (defaults to today).

        Must be >= start_date and >= last generated installment date.
        """
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        sip = await SipRepository.get_by_id_for_update(session, sip_id)
        if sip is None or sip.portfolio_id != portfolio_id:
            raise SipNotFoundError("SIP not found")

        now_utc = clock() if clock else datetime.now(UTC)
        today_kolkata = now_utc.astimezone(KOLKATA_TZ).date()

        new_end = end_date if end_date is not None else today_kolkata
        if new_end < sip.start_date:
            raise SipInvalidScheduleError(
                f"End date ({new_end}) cannot precede start date ({sip.start_date})"
            )

        last_inst = await SipRepository.get_last_generated_installment_date(session, sip.id)
        if last_inst is not None and new_end < last_inst:
            raise SipInvalidScheduleError(
                f"End date ({new_end}) cannot precede last generated installment date ({last_inst})"
            )

        sip.end_date = new_end
        await session.flush()

        loaded_sip = await SipRepository.get_by_id(session, sip.id)
        assert loaded_sip is not None
        stats_map = await SipRepository.get_stats_for_sips(session, [sip.id])
        return SipService._to_sip_response(loaded_sip, stats_map.get(sip.id), today_kolkata)

    @staticmethod
    async def patch_sip(
        session: AsyncSession,
        portfolio_id: UUID,
        sip_id: UUID,
        user_id: UUID,
        payload: PatchSipRequest,
        clock: Callable[[], datetime] | None = None,
    ) -> SipResponse:
        """Update mutable fields (notes, end_date) of a SIP."""
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        sip = await SipRepository.get_by_id_for_update(session, sip_id)
        if sip is None or sip.portfolio_id != portfolio_id:
            raise SipNotFoundError("SIP not found")

        now_utc = clock() if clock else datetime.now(UTC)
        today_kolkata = now_utc.astimezone(KOLKATA_TZ).date()

        if payload.end_date is not None:
            if payload.end_date < sip.start_date:
                raise SipInvalidScheduleError(
                    f"End date ({payload.end_date}) cannot precede start date ({sip.start_date})"
                )
            last_inst = await SipRepository.get_last_generated_installment_date(session, sip.id)
            if last_inst is not None and payload.end_date < last_inst:
                raise SipInvalidScheduleError(
                    f"End date ({payload.end_date}) cannot precede "
                    f"last generated installment date ({last_inst})"
                )
            sip.end_date = payload.end_date

        if payload.notes is not None:
            sip.notes = payload.notes.strip() if payload.notes else None

        await session.flush()

        loaded_sip = await SipRepository.get_by_id(session, sip.id)
        assert loaded_sip is not None
        stats_map = await SipRepository.get_stats_for_sips(session, [sip.id])
        return SipService._to_sip_response(loaded_sip, stats_map.get(sip.id), today_kolkata)

    @staticmethod
    async def delete_sip(
        session: AsyncSession,
        portfolio_id: UUID,
        sip_id: UUID,
        user_id: UUID,
    ) -> None:
        """Delete a SIP and its installments.

        Created transactions become ordinary (link set null).
        """
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        sip = await SipRepository.get_by_id_for_update(session, sip_id)
        if sip is None or sip.portfolio_id != portfolio_id:
            raise SipNotFoundError("SIP not found")

        await session.delete(sip)
        await session.flush()

    @staticmethod
    async def list_installments(
        session: AsyncSession,
        portfolio_id: UUID,
        sip_id: UUID,
        user_id: UUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SipInstallmentResponse], int, bool]:
        """List installments for a SIP with pagination and optional status filter."""
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        sip = await SipRepository.get_by_id(session, sip_id)
        if sip is None or sip.portfolio_id != portfolio_id:
            raise SipNotFoundError("SIP not found")

        limit_val = min(max(1, limit), 200)
        items, total = await SipRepository.list_installments_by_sip(
            session, sip_id=sip_id, status=status, limit=limit_val, offset=offset
        )

        has_more = (offset + len(items)) < total
        responses = []
        for inst, txn in items:
            txn_resp = None
            if txn is not None:
                txn_resp = SipInstallmentTransactionResponse(
                    id=txn.id,
                    txn_date=txn.txn_date,
                    units=txn.units,
                    nav=txn.nav,
                    amount=txn.amount,
                )
            responses.append(
                SipInstallmentResponse(
                    id=inst.id,
                    sip_id=inst.sip_id,
                    due_date=inst.due_date,
                    planned_amount=inst.planned_amount,
                    status=inst.status,  # type: ignore[arg-type]
                    nav_date=inst.nav_date,
                    transaction=txn_resp,
                )
            )

        return responses, total, has_more

    @staticmethod
    async def skip_installment(
        session: AsyncSession,
        portfolio_id: UUID,
        sip_id: UUID,
        installment_id: UUID,
        user_id: UUID,
    ) -> SipInstallmentResponse:
        """Skip an installment.

        If executed: deletes its transaction under portfolio lock with ledger validation.
        If pending: marks skipped.
        If already skipped: raises INSTALLMENT_NOT_SKIPPABLE.
        """
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        sip = await SipRepository.get_by_id(session, sip_id)
        if sip is None or sip.portfolio_id != portfolio_id:
            raise SipNotFoundError("SIP not found")

        # Re-select installment FOR UPDATE
        installment = await SipRepository.get_installment_for_update(session, installment_id)
        if installment is None or installment.sip_id != sip_id:
            raise InstallmentNotFoundError("Installment not found")

        if installment.status == "skipped":
            raise InstallmentNotSkippableError(
                "Installment is already skipped",
                details={"installment_id": str(installment.id)},
            )

        if installment.status == "pending":
            installment.status = "skipped"
            await session.flush()
            return SipInstallmentResponse(
                id=installment.id,
                sip_id=installment.sip_id,
                due_date=installment.due_date,
                planned_amount=installment.planned_amount,
                status="skipped",
                nav_date=installment.nav_date,
                transaction=None,
            )

        if installment.status == "executed":
            txn = await TransactionRepository.get_by_installment_id(session, installment.id)
            if txn is not None:
                all_txns = await TransactionRepository.list_by_portfolio(
                    session, portfolio_id, load_fund=False
                )
                remaining = [t for t in all_txns if t.id != txn.id]
                # Validate that removing this buy does not cause subsequent overdrafts
                validate_ledger(remaining, mutation_type="delete", target_txn_id=str(txn.id))
                await TransactionRepository.delete(session, txn)

            installment.status = "skipped"
            installment.nav_date = None
            await session.flush()
            return SipInstallmentResponse(
                id=installment.id,
                sip_id=installment.sip_id,
                due_date=installment.due_date,
                planned_amount=installment.planned_amount,
                status="skipped",
                nav_date=None,
                transaction=None,
            )

        raise InstallmentNotSkippableError("Invalid installment status")
