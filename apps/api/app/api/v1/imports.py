"""FastAPI routes for Excel transaction imports."""

import datetime as dt
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Response,
    UploadFile,
    status,
)
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_clock,
    get_current_user,
    get_db_session,
    get_redis_client,
)
from app.core.constants import IMPORT_ROWS_PAGE_MAX, IMPORT_UPLOADS_PER_MIN
from app.core.errors import RateLimitedError
from app.core.logging import get_logger
from app.models.import_batch import TransactionImport
from app.models.user import User
from app.schemas.envelope import SuccessEnvelope
from app.schemas.imports import (
    ImportCommitRequest,
    ImportDateRange,
    ImportFundSummary,
    ImportRowResponse,
    ImportRowsPageResponse,
    ImportSummaryResponse,
    ImportTotals,
    ImportUploadResponse,
    RowMessage,
)
from app.services.import_service import ImportService
from app.services.import_template import build_template
from app.services.rate_limit import check_rate_limit

router = APIRouter(tags=["imports"])
logger = get_logger("imports.api")


def _build_summary_response(import_rec: TransactionImport) -> ImportSummaryResponse:
    """Format TransactionImport model into canonical summary schema."""
    # Build totals and date_range defaults
    totals = ImportTotals(buy_amount="0.00", sell_amount="0.00")
    date_range: ImportDateRange | None = None

    return ImportSummaryResponse(
        id=import_rec.id,
        portfolio_id=import_rec.portfolio_id,
        filename=import_rec.filename,
        file_sha256=import_rec.file_sha256,
        status=import_rec.status,  # type: ignore[arg-type]
        rows_total=import_rec.rows_total,
        rows_ok=import_rec.rows_ok,
        rows_warning=import_rec.rows_warning,
        rows_duplicate=import_rec.rows_duplicate,
        rows_error=import_rec.rows_error,
        will_import=import_rec.will_import,
        plan_fingerprint=import_rec.plan_fingerprint,
        extra_columns=import_rec.extra_columns,
        funds_count=0,
        date_range=date_range,
        totals=totals,
        blocking_errors=[],
        previewed_at=import_rec.created_at,
        expires_at=import_rec.expires_at,
        committed_count=import_rec.committed_count,
        committed_at=import_rec.committed_at,
        undone_count=import_rec.undone_count,
        undone_at=import_rec.undone_at,
    )


@router.get(
    "/imports/template",
    summary="Download Excel transaction import template",
)
async def download_template() -> Response:
    """Return the official .xlsx template with Transactions and Instructions sheets."""
    content = build_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="foliopilot_transactions_template.xlsx"',
        },
    )


@router.post(
    "/portfolios/{portfolio_id}/imports",
    status_code=status.HTTP_201_CREATED,
    summary="Upload Excel spreadsheet to preview transactions",
)
async def upload_import(
    portfolio_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    redis_client: Redis = Depends(get_redis_client),
    clock: dt.datetime = Depends(get_clock),
) -> SuccessEnvelope[ImportUploadResponse]:
    """Upload workbook, run preview checks, and return import summary with initial page of rows."""
    now = dt.datetime.now(dt.UTC)

    # 1. User rate limiting (10 uploads/min)
    rl_result = await check_rate_limit(
        redis_client,
        prefix="rl_import_upload",
        identifier=str(current_user.id),
        limit=IMPORT_UPLOADS_PER_MIN,
        window_seconds=60,
        now_timestamp=int(now.timestamp()),
    )
    if not rl_result.allowed:
        raise RateLimitedError(
            "Upload rate limit exceeded. Please wait before uploading again.",
            retry_after=rl_result.retry_after,
        )

    # 2. Read file contents and ensure temp file cleanup
    try:
        file_bytes = await file.read()
    finally:
        await file.close()

    # 3. Preview and plan
    def clock_fn() -> dt.datetime:
        return clock

    import_rec, planned_rows, plan_res = await ImportService.preview(
        session=session,
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        file_bytes=file_bytes,
        filename=file.filename,
        clock=clock_fn,
    )
    await session.commit()

    logger.info(
        "import_preview_created",
        portfolio_id=str(portfolio_id),
        import_id=str(import_rec.id),
        file_sha256_prefix=import_rec.file_sha256[:8],
        rows_total=import_rec.rows_total,
        will_import=import_rec.will_import,
    )

    # Format initial page of rows (up to 100)
    initial_rows: list[ImportRowResponse] = []
    for r in planned_rows[:100]:
        fund_summary = None
        if r.fund is not None:
            fund_summary = ImportFundSummary(
                scheme_code=r.fund.scheme_code,
                name=r.fund.name,
                amc=getattr(r.fund, "amc", None),
                plan_type=getattr(r.fund, "plan_type", None),
                option_type=getattr(r.fund, "option_type", None),
                is_active=getattr(r.fund, "is_active", True),
            )

        row_msgs = [
            RowMessage(
                level=m["level"],
                code=m["code"],
                field=m.get("field"),
                message=m["message"],
                details=m.get("details"),
            )
            for m in r.messages
        ]

        initial_rows.append(
            ImportRowResponse(
                row_number=r.row_number,
                status=r.status,  # type: ignore[arg-type]
                fund=fund_summary,
                fund_name_in_file=r.fund_name_in_file,
                txn_type=r.txn_type,
                txn_date=r.txn_date,
                units=r.units,
                nav=r.nav,
                amount=r.amount,
                notes=r.notes,
                raw=r.raw,
                messages=row_msgs,
            )
        )

    # Enriched summary with planning totals and dates
    summary_resp = _build_summary_response(import_rec)
    summary_resp.funds_count = plan_res.funds_count
    if plan_res.date_range:
        summary_resp.date_range = ImportDateRange.model_validate(
            {
                "from": plan_res.date_range.get("from"),
                "to": plan_res.date_range.get("to"),
            }
        )
    summary_resp.totals = ImportTotals(
        buy_amount=plan_res.totals.get("buy_amount", "0.00"),
        sell_amount=plan_res.totals.get("sell_amount", "0.00"),
    )
    summary_resp.blocking_errors = plan_res.blocking_errors

    return SuccessEnvelope(
        data=ImportUploadResponse.model_validate(
            {
                "import": summary_resp,
                "rows": initial_rows,
            }
        )
    )


@router.get(
    "/portfolios/{portfolio_id}/imports",
    summary="List portfolio import history",
)
async def list_imports(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessEnvelope[list[ImportSummaryResponse]]:
    """Return historical import batches for portfolio, newest first."""
    imports = await ImportService.get_history(
        session=session,
        portfolio_id=portfolio_id,
        user_id=current_user.id,
    )
    items = [_build_summary_response(rec) for rec in imports]
    return SuccessEnvelope(data=items)


@router.get(
    "/portfolios/{portfolio_id}/imports/{import_id}",
    summary="Get import batch summary",
)
async def get_import_summary(
    portfolio_id: UUID,
    import_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessEnvelope[ImportSummaryResponse]:
    """Return summary metadata for a single import batch."""
    import_rec = await ImportService.get_summary(
        session=session,
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        import_id=import_id,
    )
    return SuccessEnvelope(data=_build_summary_response(import_rec))


@router.get(
    "/portfolios/{portfolio_id}/imports/{import_id}/rows",
    summary="Get paginated preview rows for active preview",
)
async def get_import_rows(
    portfolio_id: UUID,
    import_id: UUID,
    status: str | None = Query(
        None, description="Filter rows by status (ok, warning, duplicate, error)"
    ),
    limit: int = Query(100, ge=1, le=IMPORT_ROWS_PAGE_MAX, description="Page limit (max 500)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessEnvelope[ImportRowsPageResponse]:
    """Return paginated prospective rows for previewed import."""
    rows, has_more = await ImportService.get_rows(
        session=session,
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        import_id=import_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    items: list[ImportRowResponse] = []
    for r in rows:
        fund_summary = None
        if r.fund is not None:
            fund_summary = ImportFundSummary(
                scheme_code=r.fund.scheme_code,
                name=r.fund.name,
                amc=getattr(r.fund, "amc", None),
                plan_type=getattr(r.fund, "plan_type", None),
                option_type=getattr(r.fund, "option_type", None),
                is_active=getattr(r.fund, "is_active", True),
            )

        row_msgs = [
            RowMessage(
                level=m["level"],
                code=m["code"],
                field=m.get("field"),
                message=m["message"],
                details=m.get("details"),
            )
            for m in (r.messages or [])
        ]

        items.append(
            ImportRowResponse(
                row_number=r.row_number,
                status=r.status,  # type: ignore[arg-type]
                fund=fund_summary,
                fund_name_in_file=r.fund_name_in_file,
                txn_type=r.txn_type,
                txn_date=r.txn_date,
                units=r.units,
                nav=r.nav,
                amount=r.amount,
                notes=r.notes,
                raw=r.raw or {},
                messages=row_msgs,
            )
        )

    return SuccessEnvelope(
        data=ImportRowsPageResponse(
            items=items,
            has_more=has_more,
        )
    )


@router.post(
    "/portfolios/{portfolio_id}/imports/{import_id}/commit",
    summary="Commit previewed import to portfolio ledger",
)
async def commit_import(
    portfolio_id: UUID,
    import_id: UUID,
    payload: ImportCommitRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    clock: dt.datetime = Depends(get_clock),
) -> SuccessEnvelope[ImportSummaryResponse]:
    """Atomically commit candidate transactions under row lock."""
    import_rec = await ImportService.commit(
        session=session,
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        import_id=import_id,
        plan_fingerprint=payload.plan_fingerprint,
        skip_invalid=payload.skip_invalid,
        clock=lambda: clock,
    )
    await session.commit()

    logger.info(
        "import_committed",
        portfolio_id=str(portfolio_id),
        import_id=str(import_id),
        committed_count=import_rec.committed_count,
    )
    return SuccessEnvelope(data=_build_summary_response(import_rec))


@router.post(
    "/portfolios/{portfolio_id}/imports/{import_id}/undo",
    summary="Undo a committed transaction import",
)
async def undo_import(
    portfolio_id: UUID,
    import_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    clock: dt.datetime = Depends(get_clock),
) -> SuccessEnvelope[ImportSummaryResponse]:
    """Delete imported transactions and verify ledger consistency."""
    import_rec = await ImportService.undo(
        session=session,
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        import_id=import_id,
        clock=lambda: clock,
    )
    await session.commit()

    logger.info(
        "import_undone",
        portfolio_id=str(portfolio_id),
        import_id=str(import_id),
        undone_count=import_rec.undone_count,
    )
    return SuccessEnvelope(data=_build_summary_response(import_rec))


@router.delete(
    "/portfolios/{portfolio_id}/imports/{import_id}",
    summary="Discard an uncommitted previewed import",
)
async def discard_import(
    portfolio_id: UUID,
    import_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessEnvelope[dict[str, bool]]:
    """Delete an active preview without affecting ledger."""
    await ImportService.discard(
        session=session,
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        import_id=import_id,
    )
    await session.commit()

    logger.info(
        "import_discarded",
        portfolio_id=str(portfolio_id),
        import_id=str(import_id),
    )
    return SuccessEnvelope(data={"discarded": True})
