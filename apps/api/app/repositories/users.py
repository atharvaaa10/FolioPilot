"""User data access repository."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Thin repository handling User database queries."""

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
        """Fetch active user by primary key."""
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(session: AsyncSession, email: str) -> User | None:
        """Fetch user by normalized lowercase email."""
        result = await session.execute(select(User).where(User.email == email.strip().lower()))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        email: str,
        password_hash: str,
    ) -> User:
        """Persist a new user entity."""
        user = User(
            email=email.strip().lower(),
            password_hash=password_hash,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        return user

    @staticmethod
    async def update_last_login(
        session: AsyncSession,
        user: User,
        last_login_at: datetime,
    ) -> None:
        """Update last_login_at timestamp on user."""
        user.last_login_at = last_login_at
        await session.flush()
