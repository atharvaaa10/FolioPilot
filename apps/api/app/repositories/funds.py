"""Repository for querying, searching, and upserting Fund master records."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, func, literal_column, or_, select, update
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fund import Fund
from app.services.search_query import escape_like_wildcards, parse_search_query


class FundRepository:
    """Thin repository handling all Fund database interactions."""

    @staticmethod
    async def get_by_id(session: AsyncSession, fund_id: UUID) -> Fund | None:
        """Fetch fund by primary key UUID."""
        stmt = select(Fund).where(Fund.id == fund_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_scheme_code(session: AsyncSession, scheme_code: int) -> Fund | None:
        """Fetch fund by unique AMFI scheme code."""
        stmt = select(Fund).where(Fund.scheme_code == scheme_code)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def count_active(session: AsyncSession) -> int:
        """Count all currently active funds."""
        stmt = select(func.count(Fund.id)).where(Fund.is_active.is_(True))
        result = await session.execute(stmt)
        return result.scalar_one() or 0

    @staticmethod
    async def get_tracked_funds(session: AsyncSession) -> list[Fund]:
        """Fetch all funds flagged as tracked."""
        stmt = select(Fund).where(Fund.is_tracked.is_(True))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def set_tracked(session: AsyncSession, scheme_code: int) -> Fund | None:
        """Set is_tracked=True on fund identified by scheme_code."""
        fund = await FundRepository.get_by_scheme_code(session, scheme_code)
        if fund is None:
            return None
        fund.is_tracked = True
        await session.flush()
        return fund

    @staticmethod
    async def deactivate_stale(session: AsyncSession, cutoff: datetime) -> int:
        """Deactivate funds whose last_seen_at is older than cutoff."""
        stmt = (
            update(Fund)
            .where(Fund.is_active.is_(True), Fund.last_seen_at < cutoff)
            .values(is_active=False)
        )
        result = await session.execute(stmt)
        return result.rowcount if isinstance(result, CursorResult) else 0

    @staticmethod
    async def search_funds(
        session: AsyncSession,
        query: str | None = None,
        asset_class: str | None = None,
        plan: str | None = None,
        option: str | None = None,
        active_only: bool = True,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Fund], bool]:
        """Search and filter funds with ranking, pagination, and trigram similarity."""
        limit = max(1, min(limit, 50))
        stmt = select(Fund)

        # Base filters
        if active_only:
            stmt = stmt.where(Fund.is_active.is_(True))
        if asset_class:
            stmt = stmt.where(Fund.asset_class == asset_class.lower())
        if plan:
            stmt = stmt.where(Fund.plan_type == plan.lower())
        if option:
            stmt = stmt.where(Fund.option_type == option.lower())

        # Search query matching and ranking
        if query and query.strip():
            parsed = parse_search_query(query)

            if parsed.is_scheme_code and parsed.scheme_code is not None:
                # Prioritize exact scheme code match
                exact_cond = Fund.scheme_code == parsed.scheme_code
                like_cond = Fund.name_normalized.ilike(
                    f"%{escape_like_wildcards(parsed.raw_query)}%"
                )
                stmt = stmt.where(or_(exact_cond, like_cond))
                stmt = stmt.order_by(
                    case((exact_cond, 0), else_=1),
                    Fund.name.asc(),
                )

            elif parsed.is_isin and parsed.isin is not None:
                # Prioritize exact ISIN match
                exact_isin = or_(
                    Fund.isin_growth == parsed.isin,
                    Fund.isin_reinvest == parsed.isin,
                )
                like_cond = Fund.name_normalized.ilike(
                    f"%{escape_like_wildcards(parsed.raw_query.lower())}%"
                )
                stmt = stmt.where(or_(exact_isin, like_cond))
                stmt = stmt.order_by(
                    case((exact_isin, 0), else_=1),
                    Fund.name.asc(),
                )

            elif parsed.tokens:
                # AND all normalized tokens with ILIKE
                token_filters = [
                    Fund.name_normalized.ilike(f"%{escape_like_wildcards(t)}%")
                    for t in parsed.tokens
                ]
                stmt = stmt.where(and_(*token_filters))
                # Order by trigram similarity then name
                norm_query = " ".join(parsed.tokens)
                stmt = stmt.order_by(
                    func.similarity(Fund.name_normalized, norm_query).desc(),
                    Fund.name.asc(),
                )
            else:
                stmt = stmt.order_by(Fund.name.asc())
        else:
            stmt = stmt.order_by(Fund.name.asc())

        # Fetch limit + 1 to determine has_more
        stmt = stmt.limit(limit + 1).offset(offset)
        result = await session.execute(stmt)
        items = list(result.scalars().all())

        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        return items, has_more

    @staticmethod
    async def upsert_funds_batch(
        session: AsyncSession,
        records: list[dict[str, Any]],
        batch_size: int = 1000,
    ) -> tuple[int, int]:
        """Batch upsert funds using ON CONFLICT (scheme_code) DO UPDATE.

        Returns (funds_created, funds_updated).
        """
        if not records:
            return 0, 0

        total_created = 0
        total_updated = 0

        for i in range(0, len(records), batch_size):
            chunk = records[i : i + batch_size]
            insert_stmt: Insert = insert(Fund).values(chunk)

            # Define conflict update mapping
            update_dict: dict[str, Any] = {
                "isin_growth": insert_stmt.excluded.isin_growth,
                "isin_reinvest": insert_stmt.excluded.isin_reinvest,
                "name": insert_stmt.excluded.name,
                "name_normalized": insert_stmt.excluded.name_normalized,
                "amc": insert_stmt.excluded.amc,
                "scheme_type_raw": insert_stmt.excluded.scheme_type_raw,
                "category_raw": insert_stmt.excluded.category_raw,
                "asset_class": insert_stmt.excluded.asset_class,
                "sub_category": insert_stmt.excluded.sub_category,
                "classification_source": insert_stmt.excluded.classification_source,
                "plan_type": insert_stmt.excluded.plan_type,
                "option_type": insert_stmt.excluded.option_type,
                # latest NAV never moves backwards
                "latest_nav": case(
                    (
                        or_(
                            Fund.latest_nav_date.is_(None),
                            insert_stmt.excluded.latest_nav_date >= Fund.latest_nav_date,
                        ),
                        insert_stmt.excluded.latest_nav,
                    ),
                    else_=Fund.latest_nav,
                ),
                "latest_nav_date": case(
                    (
                        or_(
                            Fund.latest_nav_date.is_(None),
                            insert_stmt.excluded.latest_nav_date >= Fund.latest_nav_date,
                        ),
                        insert_stmt.excluded.latest_nav_date,
                    ),
                    else_=Fund.latest_nav_date,
                ),
                "is_active": True,
                "last_seen_at": insert_stmt.excluded.last_seen_at,
                "updated_at": func.now(),
            }

            conflict_stmt: Any = insert_stmt.on_conflict_do_update(
                index_elements=["scheme_code"],
                set_=update_dict,
            ).returning(literal_column("xmax = 0").label("is_insert"))

            res = await session.execute(conflict_stmt)
            rows = res.all()
            chunk_created = sum(1 for r in rows if r[0] is True)
            chunk_updated = len(rows) - chunk_created

            total_created += chunk_created
            total_updated += chunk_updated

        return total_created, total_updated
