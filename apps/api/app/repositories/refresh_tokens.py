"""Refresh token data access repository."""

import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    """Thin repository handling RefreshToken database transactions."""

    @staticmethod
    async def get_by_token_hash_for_update(
        session: AsyncSession,
        token_hash: str,
    ) -> RefreshToken | None:
        """Fetch refresh token by SHA-256 hash using pessimistic row lock (SELECT FOR UPDATE)."""
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def is_family_revoked(
        session: AsyncSession,
        family_id: uuid.UUID,
    ) -> bool:
        """Check if any token in this family has been revoked."""
        stmt = (
            select(RefreshToken.id)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.isnot(None),
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None = None,
    ) -> RefreshToken:
        """Persist a new refresh token entity."""
        token = RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent[:255] if user_agent else None,
        )
        session.add(token)
        await session.flush()
        return token

    @staticmethod
    async def mark_used_and_rotate(
        session: AsyncSession,
        *,
        current_token: RefreshToken,
        successor_token: RefreshToken,
        used_at: datetime,
    ) -> None:
        """Mark current token used and link to its successor."""
        current_token.used_at = used_at
        current_token.replaced_by_id = successor_token.id
        await session.flush()

    @staticmethod
    async def revoke_family(
        session: AsyncSession,
        family_id: uuid.UUID,
        revoked_at: datetime,
    ) -> None:
        """Revoke all tokens belonging to a family."""
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id)
            .values(revoked_at=revoked_at)
        )
        await session.execute(stmt)
        await session.flush()

    @staticmethod
    async def revoke_all_for_user(
        session: AsyncSession,
        user_id: uuid.UUID,
        revoked_at: datetime,
    ) -> None:
        """Revoke all refresh tokens for a user across all families (logout-all)."""
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .values(revoked_at=revoked_at)
        )
        await session.execute(stmt)
        await session.flush()

    @staticmethod
    async def delete_expired_before(
        session: AsyncSession,
        cutoff: datetime,
    ) -> int:
        """Purge refresh tokens expired before the cutoff timestamp."""
        stmt = delete(RefreshToken).where(RefreshToken.expires_at < cutoff)
        result = await session.execute(stmt)
        await session.flush()
        return int(result.rowcount)  # type: ignore[attr-defined]
