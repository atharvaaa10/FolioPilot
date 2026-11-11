"""Application service orchestrating Excel transaction imports."""

import datetime as dt
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    IMPORT_MAX_ROWS,
    IMPORT_PREVIEW_TTL_HOURS,
    MAX_TRANSACTIONS_PER_PORTFOLIO,
)
from app.core.errors import (
    ConflictError,
    ImportAlreadyCommittedError,
    ImportHasErrorsError,
    ImportNotCommittedError,
    ImportNotFoundError,
    ImportNothingToImportError,
    ImportStaleError,
    LedgerInconsistentError,
    PortfolioNotFoundError,
    TransactionLimitReachedError,
)
from app.core.logging import get_logger
from app.models.import_batch import TransactionImport, TransactionImportRow
from app.models.transaction import Transaction
from app.repositories.imports import ImportRepository
from app.repositories.portfolios import PortfolioRepository
from app.repositories.transactions import TransactionRepository
from app.services.import_file import inspect_and_read_workbook
from app.services.import_planner import (
    PlannedRow,
    PlanResult,
    plan_import,
)
from app.services.import_rows import NormalizedRow, normalize_row
from app.services.ledger import validate_ledger
from app.services.transaction_service import TransactionService

logger = get_logger("services.import_service")


class ImportService:
    """Service orchestrating Excel import preview, commit, undo, discard, and purge."""

    @staticmethod
    async def preview(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        file_bytes: bytes,
        filename: str | None,
        clock: Any | None = None,
    ) -> tuple[TransactionImport, list[PlannedRow], PlanResult]:
        """Upload workbook, inspect, plan, persist preview rows, and return summary + rows."""
        # 1. Enforce portfolio ownership (404 rule)
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        # 2. In-memory parse & safety checks
        parsed_wb = inspect_and_read_workbook(file_bytes, filename)

        # 3. Pure row normalization
        normalized_rows = [normalize_row(r, clock=clock) for r in parsed_wb.raw_rows]

        # 4. Bulk fund lookup (no N+1)
        scheme_codes = {r.scheme_code for r in normalized_rows if r.scheme_code is not None}
        isins = {r.isin for r in normalized_rows if r.isin is not None}
        funds_by_code, funds_by_isin = await ImportRepository.bulk_lookup_funds(
            session, scheme_codes, isins
        )

        all_fund_ids = {f.id for f in funds_by_code.values()}
        for f_list in funds_by_isin.values():
            for f in f_list:
                all_fund_ids.add(f.id)

        # 5. Existing ledger and duplicate keys in one query
        (
            ledger_by_fund,
            dup_counts,
        ) = await ImportRepository.get_existing_ledger_and_duplicate_counts(
            session, portfolio_id, all_fund_ids
        )

        # 6. Active SIPs in one query
        active_sips = await ImportRepository.get_active_sips_for_funds(
            session, portfolio_id, all_fund_ids
        )

        # 7. Current transaction count
        current_txn_count = await TransactionRepository.count_by_portfolio(session, portfolio_id)

        # 8. Pure planning
        plan_res = plan_import(
            normalized_rows=normalized_rows,
            fund_lookup_by_code=funds_by_code,
            fund_lookup_by_isin=funds_by_isin,
            existing_ledger_by_fund=ledger_by_fund,
            existing_duplicate_counts=dup_counts,
            active_sips=active_sips,
            current_portfolio_txn_count=current_txn_count,
            max_transactions_limit=MAX_TRANSACTIONS_PER_PORTFOLIO,
        )

        # 9. One active preview per portfolio: delete user's previous PREVIEWED import
        await ImportRepository.delete_previewed_imports_for_portfolio(session, portfolio_id)

        # 10. Persist import and preview rows
        now_utc = clock() if clock else dt.datetime.now(dt.UTC)
        expires_at = now_utc + dt.timedelta(hours=IMPORT_PREVIEW_TTL_HOURS)

        import_rec = await ImportRepository.create_import(
            session=session,
            portfolio_id=portfolio_id,
            filename=parsed_wb.filename,
            file_sha256=parsed_wb.file_sha256,
            file_size=parsed_wb.file_size,
            rows_total=plan_res.rows_total,
            rows_ok=plan_res.rows_ok,
            rows_warning=plan_res.rows_warning,
            rows_duplicate=plan_res.rows_duplicate,
            rows_error=plan_res.rows_error,
            will_import=plan_res.will_import,
            plan_fingerprint=plan_res.plan_fingerprint,
            extra_columns=parsed_wb.extra_columns if parsed_wb.extra_columns else None,
            expires_at=expires_at,
            planned_rows=plan_res.rows,
        )

        return import_rec, plan_res.rows, plan_res

    @staticmethod
    async def commit(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        import_id: UUID,
        plan_fingerprint: str,
        skip_invalid: bool = False,
        clock: Any | None = None,
    ) -> TransactionImport:
        """Atomically commit a previewed import under portfolio lock with fingerprint check."""
        # 1. Acquire portfolio row lock and verify ownership
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        # 2. Re-select import FOR UPDATE
        import_rec = await ImportRepository.get_for_update(
            session, import_id, portfolio_id=portfolio_id
        )
        if import_rec is None:
            raise ImportNotFoundError("Import not found")

        if import_rec.status in ("committed", "undone"):
            raise ImportAlreadyCommittedError("Import has already been committed")
        if import_rec.status != "previewed":
            raise ImportNotFoundError("Import preview not found")

        # 3. Check request fingerprint matches stored fingerprint
        if import_rec.plan_fingerprint != plan_fingerprint:
            raise ImportStaleError("Import plan is stale. Please re-upload your file.")

        # 4. Re-load stored normalized rows and re-run planner under the lock
        stored_rows, _ = await ImportRepository.get_rows_paged(
            session, import_id, limit=IMPORT_MAX_ROWS
        )

        # Convert stored rows to NormalizedRow format for re-planning
        normalized_list: list[NormalizedRow] = []
        fund_ids: set[UUID] = set()
        for sr in stored_rows:
            if sr.fund_id:
                fund_ids.add(sr.fund_id)
            raw_dict = sr.raw or {}
            raw_scheme_code = None
            if sr.fund:
                raw_scheme_code = sr.fund.scheme_code
            elif raw_dict.get("scheme_code"):
                try:
                    raw_scheme_code = int(str(raw_dict["scheme_code"]).strip())
                except (ValueError, TypeError):
                    raw_scheme_code = None

            raw_isin = None
            if sr.fund:
                raw_isin = sr.fund.isin_growth or sr.fund.isin_reinvest
            elif raw_dict.get("isin"):
                raw_isin = str(raw_dict["isin"]).strip().upper()

            # Exclude only messages added dynamically by planner so they can be freshly re-evaluated
            codes_added_by_plan = {
                "DUPLICATE_IN_LEDGER",
                "DUPLICATE_IN_FILE",
                "POSSIBLE_SIP_OVERLAP",
                "INSUFFICIENT_UNITS",
                "UNKNOWN_FUND",
                "FUND_CODE_ISIN_MISMATCH",
                "ISIN_AMBIGUOUS",
                "FUND_INACTIVE",
            }
            initial_msgs = [
                m for m in (sr.messages or []) if m.get("code") not in codes_added_by_plan
            ]

            normalized_list.append(
                NormalizedRow(
                    row_number=sr.row_number,
                    txn_date=sr.txn_date,
                    txn_type=sr.txn_type,
                    scheme_code=raw_scheme_code,
                    isin=raw_isin,
                    units=sr.units,
                    nav=sr.nav,
                    amount=sr.amount,
                    notes=sr.notes,
                    fund_name_in_file=sr.fund_name_in_file,
                    raw=raw_dict,
                    messages=initial_msgs,
                )
            )

        # Funds lookup map from eager-loaded funds
        funds_by_code: dict[int, Any] = {}
        funds_by_isin: dict[str, list[Any]] = {}
        for sr in stored_rows:
            if sr.fund:
                funds_by_code[sr.fund.scheme_code] = sr.fund
                if sr.fund.isin_growth:
                    funds_by_isin.setdefault(sr.fund.isin_growth, []).append(sr.fund)
                if sr.fund.isin_reinvest:
                    funds_by_isin.setdefault(sr.fund.isin_reinvest, []).append(sr.fund)

        (
            ledger_by_fund,
            dup_counts,
        ) = await ImportRepository.get_existing_ledger_and_duplicate_counts(
            session, portfolio_id, fund_ids
        )
        active_sips = await ImportRepository.get_active_sips_for_funds(
            session, portfolio_id, fund_ids
        )
        current_txn_count = await TransactionRepository.count_by_portfolio(session, portfolio_id)

        replan_res = plan_import(
            normalized_rows=normalized_list,
            fund_lookup_by_code=funds_by_code,
            fund_lookup_by_isin=funds_by_isin,
            existing_ledger_by_fund=ledger_by_fund,
            existing_duplicate_counts=dup_counts,
            active_sips=active_sips,
            current_portfolio_txn_count=current_txn_count,
            max_transactions_limit=MAX_TRANSACTIONS_PER_PORTFOLIO,
        )

        # Fingerprint mismatch check
        if replan_res.plan_fingerprint != import_rec.plan_fingerprint:
            raise ImportStaleError(
                "Import preview is stale due to recent ledger changes. Please re-upload."
            )

        # 5. Check error rows
        if replan_res.rows_error > 0 and not skip_invalid:
            raise ImportHasErrorsError(
                f"Import contains {replan_res.rows_error} invalid rows. "
                f"Tick 'Skip invalid rows' to import the remaining {replan_res.will_import} rows.",
                details={
                    "rows_error": replan_res.rows_error,
                    "will_import": replan_res.will_import,
                },
            )

        # 6. Check will_import count
        if replan_res.will_import == 0:
            raise ImportNothingToImportError("No rows to import")

        # 7. Check transaction limit
        if current_txn_count + replan_res.will_import > MAX_TRANSACTIONS_PER_PORTFOLIO:
            raise TransactionLimitReachedError(
                f"Importing {replan_res.will_import} rows would exceed portfolio limit of "
                f"{MAX_TRANSACTIONS_PER_PORTFOLIO} transactions"
            )

        # 8. Prepare will_import rows for apply_transactions
        candidate_data: list[dict[str, Any]] = []
        for pr in replan_res.rows:
            if pr.status in ("ok", "warning"):
                candidate_data.append(
                    {
                        "fund_id": pr.fund_id,
                        "fund": pr.fund,
                        "txn_type": pr.txn_type,
                        "txn_date": pr.txn_date,
                        "units": pr.units,
                        "nav": pr.nav,
                        "amount": pr.amount,
                        "notes": pr.notes,
                    }
                )

        # 9. Apply transactions through common ledger service
        await TransactionService.apply_transactions(
            session=session,
            portfolio_id=portfolio_id,
            user_id=user_id,
            transactions_data=candidate_data,
            import_id=import_rec.id,
            already_planned=True,
            clock=clock,
        )

        # 10. Mark import committed
        now_utc = clock() if clock else dt.datetime.now(dt.UTC)
        import_rec.status = "committed"
        import_rec.committed_count = replan_res.will_import
        import_rec.committed_at = now_utc

        # 11. Delete stored row records (keep summary)
        await ImportRepository.delete_rows_for_import(session, import_id)
        await session.flush()

        return import_rec

    @staticmethod
    async def undo(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        import_id: UUID,
        clock: Any | None = None,
    ) -> TransactionImport:
        """Undo a committed import under portfolio lock, verifying ledger consistency."""
        # 1. Acquire portfolio row lock
        portfolio = await PortfolioRepository.get_for_update(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        # 2. Select import FOR UPDATE
        import_rec = await ImportRepository.get_for_update(
            session, import_id, portfolio_id=portfolio_id
        )
        if import_rec is None:
            raise ImportNotFoundError("Import not found")

        if import_rec.status != "committed":
            raise ImportNotCommittedError("Only committed imports can be undone")

        # 3. Find transactions carrying this import_id
        stmt = select(Transaction).where(
            Transaction.portfolio_id == portfolio_id,
            Transaction.import_id == import_id,
        )
        res = await session.execute(stmt)
        txns_to_undo = list(res.scalars().all())

        if not txns_to_undo:
            now_utc = clock() if clock else dt.datetime.now(dt.UTC)
            import_rec.status = "undone"
            import_rec.undone_count = 0
            import_rec.undone_at = now_utc
            await session.flush()
            return import_rec

        # 4. Check ledger consistency for each affected fund if these transactions are removed
        affected_fund_ids = {t.fund_id for t in txns_to_undo}
        undo_txn_ids = {t.id for t in txns_to_undo}

        for f_id in affected_fund_ids:
            all_fund_txns = await TransactionRepository.list_by_portfolio(
                session, portfolio_id, fund_id=f_id, load_fund=False
            )
            remaining_fund_txns = [t for t in all_fund_txns if t.id not in undo_txn_ids]
            try:
                validate_ledger(remaining_fund_txns, mutation_type="delete")
            except Exception as e:
                # Find first failing date / fund
                details = getattr(e, "details", {}) or {"fund": str(f_id)}
                raise LedgerInconsistentError(
                    f"Cannot undo import: subsequent transactions depend on imported units ({e})",
                    details=details,
                ) from e

        # 5. Delete transactions
        for t in txns_to_undo:
            await TransactionRepository.delete(session, t)

        # 6. Mark import undone
        now_utc = clock() if clock else dt.datetime.now(dt.UTC)
        import_rec.status = "undone"
        import_rec.undone_count = len(txns_to_undo)
        import_rec.undone_at = now_utc
        await session.flush()

        return import_rec

    @staticmethod
    async def discard(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        import_id: UUID,
    ) -> bool:
        """Discard an uncommitted previewed import (cascades to preview rows)."""
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        import_rec = await ImportRepository.get_by_id(session, import_id, portfolio_id=portfolio_id)
        if import_rec is None:
            raise ImportNotFoundError("Import not found")

        if import_rec.status != "previewed":
            raise ConflictError("Only previewed imports can be discarded", code="CONFLICT")

        await session.delete(import_rec)
        await session.flush()
        return True

    @staticmethod
    async def get_history(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
    ) -> list[TransactionImport]:
        """Fetch import history for a portfolio, newest first."""
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        return await ImportRepository.list_by_portfolio(session, portfolio_id)

    @staticmethod
    async def get_summary(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        import_id: UUID,
    ) -> TransactionImport:
        """Fetch single import summary enforcing ownership."""
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        import_rec = await ImportRepository.get_by_id(session, import_id, portfolio_id=portfolio_id)
        if import_rec is None:
            raise ImportNotFoundError("Import not found")

        return import_rec

    @staticmethod
    async def get_rows(
        session: AsyncSession,
        portfolio_id: UUID,
        user_id: UUID,
        import_id: UUID,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[TransactionImportRow], bool]:
        """Fetch preview rows for an active preview."""
        portfolio = await PortfolioRepository.get_by_id(session, portfolio_id, user_id=user_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")

        import_rec = await ImportRepository.get_by_id(session, import_id, portfolio_id=portfolio_id)
        if import_rec is None:
            raise ImportNotFoundError("Import not found")

        if import_rec.status != "previewed":
            return [], False

        return await ImportRepository.get_rows_paged(
            session, import_id, status=status, limit=limit, offset=offset
        )
