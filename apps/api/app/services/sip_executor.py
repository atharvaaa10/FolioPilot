"""Background execution engine for SIP installments."""

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import MAX_INSTALLMENTS_PER_GENERATION
from app.core.errors import TransactionLimitReachedError
from app.core.logging import get_logger
from app.models.nav_history import NavHistory
from app.models.sip import Sip, SipInstallment
from app.repositories.portfolios import PortfolioRepository
from app.repositories.sips import SipRepository
from app.services.sip_execution import pick_nav
from app.services.sip_schedule import (
    compute_k,
    first_due_date,
    iter_due_dates,
    planned_amount,
)
from app.services.transaction_service import TransactionService

logger = get_logger("services.sip_executor")
KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


class SipExecutor:
    """Orchestrator for recurring installment generation and execution."""

    @staticmethod
    async def generate_due_installments(
        session_or_factory: async_sessionmaker[AsyncSession] | AsyncSession,
        clock: Callable[[], datetime] | None = None,
        as_of: date | None = None,
    ) -> int:
        """Lazily generate installments up to today for active SIPs.

        Uses ON CONFLICT DO NOTHING to prevent duplicates.
        """
        if as_of is not None:
            today_kolkata = as_of
        else:
            now_utc = clock() if clock else datetime.now(UTC)
            today_kolkata = now_utc.astimezone(KOLKATA_TZ).date()

        if callable(session_or_factory):
            async with session_or_factory() as session:
                return await SipExecutor._generate_due_installments_session(
                    session, today_kolkata=today_kolkata
                )
        else:
            return await SipExecutor._generate_due_installments_session(
                session_or_factory, today_kolkata=today_kolkata
            )

    @staticmethod
    async def _generate_due_installments_session(
        session: AsyncSession,
        today_kolkata: date,
    ) -> int:
        # Query all SIPs that have not ended before today
        stmt = select(Sip).where((Sip.end_date.is_(None)) | (Sip.end_date >= today_kolkata))
        res = await session.execute(stmt)
        sips = list(res.scalars().all())

        total_generated = 0
        for sip in sips:
            due_dates = iter_due_dates(
                start_date=sip.start_date,
                day_of_month=sip.day_of_month,
                end_date=sip.end_date,
                pauses=sip.pauses,
                until=today_kolkata,
                max_count=MAX_INSTALLMENTS_PER_GENERATION,
            )
            if not due_dates:
                continue

            origin_date = first_due_date(sip.start_date, sip.day_of_month)
            batch = []
            for d in due_dates:
                k = compute_k(origin_date, d)
                amt = planned_amount(sip.amount, sip.step_up_percent, k)
                batch.append(
                    {
                        "sip_id": sip.id,
                        "due_date": d,
                        "planned_amount": amt,
                        "status": "pending",
                    }
                )

            if batch:
                await SipRepository.insert_installments_batch(session, batch)
                total_generated += len(batch)

        await session.commit()
        return total_generated

    @staticmethod
    async def _fetch_tasks_and_nav(
        session: AsyncSession,
        today_kolkata: date,
        fund_id: UUID | None,
    ) -> tuple[
        list[tuple[UUID, UUID, date, Decimal, UUID, UUID]],
        dict[UUID, list[tuple[date, Decimal]]],
    ]:
        pending_installments = await SipRepository.get_pending_installments_for_execution(
            session, today=today_kolkata, fund_id=fund_id
        )
        if not pending_installments:
            return [], {}

        fund_ids = {inst.sip.fund_id for inst in pending_installments}
        nav_stmt = (
            select(NavHistory.fund_id, NavHistory.nav_date, NavHistory.nav)
            .where(
                NavHistory.fund_id.in_(fund_ids),
                NavHistory.nav_date <= today_kolkata,
            )
            .order_by(NavHistory.nav_date.asc())
        )
        nav_res = await session.execute(nav_stmt)
        nav_points_by_fund: dict[UUID, list[tuple[date, Decimal]]] = defaultdict(list)
        for f_id, n_date, nav_val in nav_res.all():
            nav_points_by_fund[f_id].append((n_date, nav_val))

        tasks = [
            (
                inst.id,
                inst.sip_id,
                inst.due_date,
                inst.planned_amount,
                inst.sip.portfolio_id,
                inst.sip.fund_id,
            )
            for inst in pending_installments
        ]
        return tasks, nav_points_by_fund

    @staticmethod
    async def _execute_single_installment(
        session: AsyncSession,
        inst_id: UUID,
        portfolio_id: UUID,
        fund_id: UUID,
        planned_amt: Decimal,
        nav_date: date,
        nav: Decimal,
        clock: Callable[[], datetime] | None,
    ) -> str:
        # Lock portfolio row FOR UPDATE
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id)
        if portfolio is None:
            logger.error(
                "Portfolio not found during SIP execution",
                portfolio_id=str(portfolio_id),
            )
            return "failed"

        # Re-select installment FOR UPDATE
        installment = await SipRepository.get_installment_for_update(session, inst_id)
        if installment is None or installment.status != "pending":
            return "skipped"

        # Apply transaction through ledger service
        try:
            await TransactionService.add_transaction(
                session,
                portfolio_id=portfolio.id,
                user_id=portfolio.user_id,
                fund_id=fund_id,
                txn_type="buy",
                txn_date=nav_date,
                units=None,
                nav=nav,
                amount=planned_amt,
                notes=None,
                sip_installment_id=installment.id,
                clock=clock,
            )
        except TransactionLimitReachedError as exc:
            logger.warning(
                "Portfolio transaction limit reached; leaving installment pending",
                portfolio_id=str(portfolio_id),
                installment_id=str(installment.id),
                error=str(exc),
            )
            return "pending"

        installment.status = "executed"
        installment.nav_date = nav_date
        return "executed"

    @staticmethod
    async def execute_pending(
        session_or_factory: async_sessionmaker[AsyncSession] | AsyncSession,
        clock: Callable[[], datetime] | None = None,
        as_of: date | None = None,
        fund_id: UUID | None = None,
    ) -> dict[str, int]:
        """Execute pending installments due on or before today.

        Each installment executes in its own isolated database transaction with
        portfolio and installment row locks. NAV points are loaded ONCE per fund (no N+1).
        """
        if as_of is not None:
            today_kolkata = as_of
        else:
            now_utc = clock() if clock else datetime.now(UTC)
            today_kolkata = now_utc.astimezone(KOLKATA_TZ).date()

        if callable(session_or_factory):
            async with session_or_factory() as read_session:
                tasks, nav_points_by_fund = await SipExecutor._fetch_tasks_and_nav(
                    read_session, today_kolkata, fund_id
                )
        else:
            tasks, nav_points_by_fund = await SipExecutor._fetch_tasks_and_nav(
                session_or_factory, today_kolkata, fund_id
            )

        if not tasks:
            return {"processed": 0, "executed": 0, "pending": 0, "failed": 0}

        stats = {"processed": 0, "executed": 0, "pending": 0, "failed": 0}

        for inst_id, _sip_id, due_date, planned_amt, portfolio_id, f_id in tasks:
            stats["processed"] += 1
            fund_points = nav_points_by_fund.get(f_id, [])
            picked = pick_nav(due_date, today_kolkata, fund_points)
            if picked is None:
                stats["pending"] += 1
                continue

            nav_date, nav = picked

            if callable(session_or_factory):
                async with session_or_factory() as tx_session:
                    try:
                        res = await SipExecutor._execute_single_installment(
                            tx_session,
                            inst_id=inst_id,
                            portfolio_id=portfolio_id,
                            fund_id=f_id,
                            planned_amt=planned_amt,
                            nav_date=nav_date,
                            nav=nav,
                            clock=clock,
                        )
                        if res == "executed":
                            await tx_session.commit()
                            stats["executed"] += 1
                        elif res == "pending":
                            await tx_session.rollback()
                            stats["pending"] += 1
                        elif res == "failed":
                            await tx_session.rollback()
                            stats["failed"] += 1
                    except Exception as exc:
                        await tx_session.rollback()
                        logger.exception(
                            "Unexpected error executing installment",
                            installment_id=str(inst_id),
                            error=str(exc),
                        )
                        stats["failed"] += 1
            else:
                tx_session = session_or_factory
                try:
                    res = await SipExecutor._execute_single_installment(
                        tx_session,
                        inst_id=inst_id,
                        portfolio_id=portfolio_id,
                        fund_id=f_id,
                        planned_amt=planned_amt,
                        nav_date=nav_date,
                        nav=nav,
                        clock=clock,
                    )
                    if res == "executed":
                        await tx_session.commit()
                        stats["executed"] += 1
                    elif res == "pending":
                        await tx_session.rollback()
                        stats["pending"] += 1
                    elif res == "failed":
                        await tx_session.rollback()
                        stats["failed"] += 1
                except Exception as exc:
                    await tx_session.rollback()
                    logger.exception(
                        "Unexpected error executing installment",
                        installment_id=str(inst_id),
                        error=str(exc),
                    )
                    stats["failed"] += 1

        return stats
