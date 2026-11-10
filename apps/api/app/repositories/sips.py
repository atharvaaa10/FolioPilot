"""Repository for SIPs, pauses, and installments."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sip import Sip, SipInstallment, SipPause
from app.models.transaction import Transaction


class SipRepository:
    """Thin repository layer for SIP entities."""

    @staticmethod
    async def count_by_portfolio(session: AsyncSession, portfolio_id: UUID) -> int:
        """Count active or all SIPs for a portfolio to enforce MAX_SIPS_PER_PORTFOLIO."""
        stmt = select(func.count(Sip.id)).where(Sip.portfolio_id == portfolio_id)
        res = await session.execute(stmt)
        return int(res.scalar_one() or 0)

    @staticmethod
    async def get_by_id(session: AsyncSession, sip_id: UUID) -> Sip | None:
        """Fetch SIP by ID with pauses eagerly loaded."""
        stmt = select(Sip).where(Sip.id == sip_id).options(selectinload(Sip.pauses))
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_id_for_update(session: AsyncSession, sip_id: UUID) -> Sip | None:
        """Fetch SIP by ID with pessimistic row-level lock."""
        stmt = (
            select(Sip).where(Sip.id == sip_id).with_for_update().options(selectinload(Sip.pauses))
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def list_by_portfolio(session: AsyncSession, portfolio_id: UUID) -> list[Sip]:
        """List all SIPs for a portfolio ordered by created_at DESC."""
        stmt = (
            select(Sip)
            .where(Sip.portfolio_id == portfolio_id)
            .order_by(Sip.created_at.desc())
            .options(selectinload(Sip.pauses))
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        portfolio_id: UUID,
        fund_id: UUID,
        amount: Decimal,
        day_of_month: int,
        start_date: date,
        end_date: date | None = None,
        step_up_percent: Decimal = Decimal("0.00"),
        notes: str | None = None,
    ) -> Sip:
        """Create a new SIP."""
        sip = Sip(
            portfolio_id=portfolio_id,
            fund_id=fund_id,
            amount=amount,
            day_of_month=day_of_month,
            start_date=start_date,
            end_date=end_date,
            step_up_percent=step_up_percent,
            notes=notes,
        )
        session.add(sip)
        await session.flush()
        return sip

    @staticmethod
    async def create_pause(
        session: AsyncSession,
        *,
        sip_id: UUID,
        paused_from: date,
        resumed_on: date | None = None,
    ) -> SipPause:
        """Create a new pause interval."""
        pause = SipPause(
            sip_id=sip_id,
            paused_from=paused_from,
            resumed_on=resumed_on,
        )
        session.add(pause)
        await session.flush()
        return pause

    @staticmethod
    async def get_open_pause(session: AsyncSession, sip_id: UUID) -> SipPause | None:
        """Fetch the active open pause for a SIP if any exists."""
        stmt = select(SipPause).where(
            SipPause.sip_id == sip_id,
            SipPause.resumed_on.is_(None),
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def insert_installments_batch(
        session: AsyncSession,
        installments: list[dict[str, Any]],
    ) -> None:
        """Insert installments with ON CONFLICT (sip_id, due_date) DO NOTHING."""
        if not installments:
            return

        stmt = pg_insert(SipInstallment).values(installments)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_sip_installments_sip_due_date")
        await session.execute(stmt)

    @staticmethod
    async def get_installment_by_id(
        session: AsyncSession, installment_id: UUID
    ) -> SipInstallment | None:
        """Fetch installment by ID."""
        stmt = select(SipInstallment).where(SipInstallment.id == installment_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_installment_for_update(
        session: AsyncSession, installment_id: UUID
    ) -> SipInstallment | None:
        """Fetch installment by ID with row lock."""
        stmt = select(SipInstallment).where(SipInstallment.id == installment_id).with_for_update()
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def list_installments_by_sip(
        session: AsyncSession,
        sip_id: UUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[tuple[SipInstallment, Transaction | None]], int]:
        """List installments for a SIP with optional status filter, newest due_date first."""
        base_filter = [SipInstallment.sip_id == sip_id]
        if status:
            base_filter.append(SipInstallment.status == status.lower())

        count_stmt = select(func.count(SipInstallment.id)).where(*base_filter)
        total_res = await session.execute(count_stmt)
        total = int(total_res.scalar_one() or 0)

        query = (
            select(SipInstallment, Transaction)
            .outerjoin(Transaction, Transaction.sip_installment_id == SipInstallment.id)
            .where(*base_filter)
            .order_by(SipInstallment.due_date.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await session.execute(query)
        items: list[tuple[SipInstallment, Transaction | None]] = [
            (row[0], row[1]) for row in res.all()
        ]
        return items, total

    @staticmethod
    async def get_last_generated_installment_date(
        session: AsyncSession, sip_id: UUID
    ) -> date | None:
        """Find the latest due_date among existing installments for a SIP."""
        stmt = select(func.max(SipInstallment.due_date)).where(SipInstallment.sip_id == sip_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_stats_for_sips(
        session: AsyncSession,
        sip_ids: list[UUID],
    ) -> dict[UUID, dict[str, Any]]:
        """Compute aggregated statistics for a list of SIPs in a single SQL query (no N+1)."""
        if not sip_ids:
            return {}

        # 1. Aggregation across installments and linked transactions
        stmt = (
            select(
                SipInstallment.sip_id,
                func.count(SipInstallment.id).label("total_count"),
                func.count().filter(SipInstallment.status == "executed").label("executed_count"),
                func.count().filter(SipInstallment.status == "pending").label("pending_count"),
                func.count().filter(SipInstallment.status == "skipped").label("skipped_count"),
                func.coalesce(
                    func.sum(Transaction.amount).filter(SipInstallment.status == "executed"),
                    Decimal("0.00"),
                ).label("total_invested"),
                func.coalesce(
                    func.sum(Transaction.units).filter(SipInstallment.status == "executed"),
                    Decimal("0.0000"),
                ).label("units_acquired"),
            )
            .outerjoin(Transaction, Transaction.sip_installment_id == SipInstallment.id)
            .where(SipInstallment.sip_id.in_(sip_ids))
            .group_by(SipInstallment.sip_id)
        )
        res = await session.execute(stmt)
        stats_map: dict[UUID, dict[str, Any]] = defaultdict(
            lambda: {
                "installments_total": 0,
                "executed": 0,
                "pending": 0,
                "skipped": 0,
                "total_invested": Decimal("0.00"),
                "units_acquired": Decimal("0.0000"),
            }
        )

        for row in res.all():
            sip_id, total, exec_c, pend_c, skip_c, inv, units = row
            stats_map[sip_id] = {
                "installments_total": total,
                "executed": exec_c,
                "pending": pend_c,
                "skipped": skip_c,
                "total_invested": Decimal(str(inv)).quantize(Decimal("0.01")),
                "units_acquired": Decimal(str(units)).quantize(Decimal("0.0001")),
            }

        return stats_map

    @staticmethod
    async def get_pending_installments_for_execution(
        session: AsyncSession,
        today: date,
        fund_id: UUID | None = None,
    ) -> list[SipInstallment]:
        """Fetch pending installments due on or before today.

        Joined with SIP for fund/portfolio info.
        """
        stmt = (
            select(SipInstallment)
            .join(Sip, Sip.id == SipInstallment.sip_id)
            .where(
                SipInstallment.status == "pending",
                SipInstallment.due_date <= today,
            )
            .options(selectinload(SipInstallment.sip))
        )
        if fund_id:
            stmt = stmt.where(Sip.fund_id == fund_id)

        stmt = stmt.order_by(SipInstallment.due_date.asc())
        res = await session.execute(stmt)
        return list(res.scalars().all())
