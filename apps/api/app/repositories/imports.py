"""Database queries and persistence for Excel transaction imports and preview rows."""

import datetime as dt
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fund import Fund
from app.models.import_batch import TransactionImport, TransactionImportRow
from app.models.sip import Sip
from app.models.transaction import Transaction
from app.services.import_planner import ExistingSip, ExistingTransactionItem, PlannedRow


class ImportRepository:
    """Thin repository handling database queries for transaction imports."""

    @staticmethod
    async def bulk_lookup_funds(
        session: AsyncSession,
        scheme_codes: set[int],
        isins: set[str],
    ) -> tuple[dict[int, Fund], dict[str, list[Fund]]]:
        """Bulk query funds by scheme codes and ISINs in one query per identifier kind."""
        funds_by_code: dict[int, Fund] = {}
        funds_by_isin: dict[str, list[Fund]] = {}

        if scheme_codes:
            stmt_codes = select(Fund).where(Fund.scheme_code.in_(scheme_codes))
            res_codes = await session.execute(stmt_codes)
            for fund in res_codes.scalars().all():
                funds_by_code[fund.scheme_code] = fund

        if isins:
            stmt_isins = select(Fund).where(
                (Fund.isin_growth.in_(isins)) | (Fund.isin_reinvest.in_(isins))
            )
            res_isins = await session.execute(stmt_isins)
            for fund in res_isins.scalars().all():
                if fund.isin_growth and fund.isin_growth in isins:
                    funds_by_isin.setdefault(fund.isin_growth, []).append(fund)
                if fund.isin_reinvest and fund.isin_reinvest in isins:
                    if fund not in funds_by_isin.get(fund.isin_reinvest, []):
                        funds_by_isin.setdefault(fund.isin_reinvest, []).append(fund)

        return funds_by_code, funds_by_isin

    @staticmethod
    async def get_existing_ledger_and_duplicate_counts(
        session: AsyncSession,
        portfolio_id: UUID,
        fund_ids: set[UUID],
    ) -> tuple[
        dict[UUID, list[ExistingTransactionItem]],
        dict[tuple[UUID, dt.date, str, Decimal, Decimal], int],
    ]:
        """Fetch existing transactions for affected funds and build ledger and duplicate counts."""
        ledger_by_fund: dict[UUID, list[ExistingTransactionItem]] = {}
        dup_counts: dict[tuple[UUID, dt.date, str, Decimal, Decimal], int] = {}

        if not fund_ids:
            return ledger_by_fund, dup_counts

        stmt = (
            select(Transaction)
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.fund_id.in_(fund_ids),
            )
            .order_by(Transaction.txn_date.asc(), Transaction.created_at.asc())
        )
        res = await session.execute(stmt)
        txns = res.scalars().all()

        for t in txns:
            item = ExistingTransactionItem(
                id=t.id,
                fund_id=t.fund_id,
                txn_type=t.txn_type.lower(),
                txn_date=t.txn_date,
                units=t.units,
                nav=t.nav,
                amount=t.amount,
                created_at=t.created_at,
            )
            ledger_by_fund.setdefault(t.fund_id, []).append(item)

            key = (
                t.fund_id,
                t.txn_date,
                t.txn_type.lower(),
                t.units.quantize(Decimal("0.0001")),
                t.amount.quantize(Decimal("0.01")),
            )
            dup_counts[key] = dup_counts.get(key, 0) + 1

        return ledger_by_fund, dup_counts

    @staticmethod
    async def get_active_sips_for_funds(
        session: AsyncSession,
        portfolio_id: UUID,
        fund_ids: set[UUID],
    ) -> list[ExistingSip]:
        """Fetch active or scheduled SIPs for affected funds in one query."""
        if not fund_ids:
            return []

        stmt = select(Sip).where(
            Sip.portfolio_id == portfolio_id,
            Sip.fund_id.in_(fund_ids),
        )
        res = await session.execute(stmt)
        sips = res.scalars().all()

        return [
            ExistingSip(
                fund_id=s.fund_id,
                start_date=s.start_date,
                end_date=s.end_date,
            )
            for s in sips
        ]

    @staticmethod
    async def delete_previewed_imports_for_portfolio(
        session: AsyncSession,
        portfolio_id: UUID,
    ) -> int:
        """Delete existing PREVIEWED imports for a portfolio (one active preview rule)."""
        stmt = delete(TransactionImport).where(
            TransactionImport.portfolio_id == portfolio_id,
            TransactionImport.status == "previewed",
        )
        result = await session.execute(stmt)
        cursor_res = cast(CursorResult[Any], result)
        return int(cursor_res.rowcount or 0)

    @staticmethod
    async def create_import(
        session: AsyncSession,
        portfolio_id: UUID,
        filename: str,
        file_sha256: str,
        file_size: int,
        rows_total: int,
        rows_ok: int,
        rows_warning: int,
        rows_duplicate: int,
        rows_error: int,
        will_import: int,
        plan_fingerprint: str,
        extra_columns: list[str] | None,
        expires_at: dt.datetime,
        planned_rows: list[PlannedRow],
    ) -> TransactionImport:
        """Create transaction import record and its prospective preview rows."""
        import_rec = TransactionImport(
            portfolio_id=portfolio_id,
            status="previewed",
            filename=filename,
            file_sha256=file_sha256,
            file_size=file_size,
            rows_total=rows_total,
            rows_ok=rows_ok,
            rows_warning=rows_warning,
            rows_duplicate=rows_duplicate,
            rows_error=rows_error,
            will_import=will_import,
            plan_fingerprint=plan_fingerprint,
            extra_columns=extra_columns,
            expires_at=expires_at,
        )
        session.add(import_rec)
        await session.flush()

        row_objects: list[TransactionImportRow] = []
        for r in planned_rows:
            row_rec = TransactionImportRow(
                import_id=import_rec.id,
                row_number=r.row_number,
                status=r.status,
                fund_id=r.fund_id,
                txn_type=r.txn_type,
                txn_date=r.txn_date,
                units=r.units,
                nav=r.nav,
                amount=r.amount,
                notes=r.notes,
                fund_name_in_file=r.fund_name_in_file,
                raw=r.raw,
                messages=r.messages,
            )
            row_objects.append(row_rec)

        session.add_all(row_objects)
        await session.flush()
        return import_rec

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        import_id: UUID,
        portfolio_id: UUID,
    ) -> TransactionImport | None:
        """Fetch import record by id scoped to portfolio."""
        stmt = select(TransactionImport).where(
            TransactionImport.id == import_id,
            TransactionImport.portfolio_id == portfolio_id,
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_for_update(
        session: AsyncSession,
        import_id: UUID,
        portfolio_id: UUID,
    ) -> TransactionImport | None:
        """Fetch import record under pessimistic row lock (FOR UPDATE)."""
        stmt = (
            select(TransactionImport)
            .where(
                TransactionImport.id == import_id,
                TransactionImport.portfolio_id == portfolio_id,
            )
            .with_for_update()
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def list_by_portfolio(
        session: AsyncSession,
        portfolio_id: UUID,
    ) -> list[TransactionImport]:
        """List all imports for a portfolio, newest first."""
        stmt = (
            select(TransactionImport)
            .where(TransactionImport.portfolio_id == portfolio_id)
            .order_by(TransactionImport.created_at.desc())
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_rows_paged(
        session: AsyncSession,
        import_id: UUID,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[TransactionImportRow], bool]:
        """Fetch paginated preview rows for an import with eager loaded fund metadata."""
        stmt = (
            select(TransactionImportRow)
            .options(selectinload(TransactionImportRow.fund))
            .where(TransactionImportRow.import_id == import_id)
        )
        if status:
            stmt = stmt.where(TransactionImportRow.status == status)

        stmt = stmt.order_by(TransactionImportRow.row_number.asc()).offset(offset).limit(limit + 1)
        res = await session.execute(stmt)
        rows = list(res.scalars().all())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        return rows, has_more

    @staticmethod
    async def delete_rows_for_import(
        session: AsyncSession,
        import_id: UUID,
    ) -> int:
        """Delete stored row records on commit (keeping summary)."""
        stmt = delete(TransactionImportRow).where(TransactionImportRow.import_id == import_id)
        res = await session.execute(stmt)
        cursor_res = cast(CursorResult[Any], res)
        return int(cursor_res.rowcount or 0)

    @staticmethod
    async def purge_expired_previews(
        session: AsyncSession,
        now_utc: dt.datetime,
    ) -> int:
        """Purge expired PREVIEWED imports older than TTL."""
        stmt = delete(TransactionImport).where(
            TransactionImport.status == "previewed",
            TransactionImport.expires_at < now_utc,
        )
        res = await session.execute(stmt)
        cursor_purge = cast(CursorResult[Any], res)
        return int(cursor_purge.rowcount or 0)
