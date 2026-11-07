import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.security import hash_password, hash_token
from app.workers.tasks import purge_expired_refresh_tokens


@pytest.mark.asyncio
async def test_purge_expired_refresh_tokens_task(test_session: AsyncSession) -> None:
    """Verify Celery task purges tokens expired more than 7 days ago and keeps recent tokens."""
    # Create test user
    user = User(
        email="purge_task@example.com",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    test_session.add(user)
    await test_session.flush()

    now = datetime.now(UTC)

    # 1. Old expired token (> 7 days ago) -> MUST BE PURGED
    old_token = RefreshToken(
        user_id=user.id,
        family_id=uuid.uuid4(),
        token_hash=hash_token("old-token-value-1"),
        expires_at=now - timedelta(days=10),
    )

    # 2. Recently expired token (< 7 days ago) -> MUST BE RETAINED for detection
    recent_token = RefreshToken(
        user_id=user.id,
        family_id=uuid.uuid4(),
        token_hash=hash_token("recent-token-value-2"),
        expires_at=now - timedelta(days=2),
    )

    # 3. Active unexpired token -> MUST BE RETAINED
    active_token = RefreshToken(
        user_id=user.id,
        family_id=uuid.uuid4(),
        token_hash=hash_token("active-token-value-3"),
        expires_at=now + timedelta(days=7),
    )

    test_session.add_all([old_token, recent_token, active_token])
    await test_session.commit()

    # Execute purge task via thread helper since test runner runs an active event loop
    purged_count = await asyncio.to_thread(purge_expired_refresh_tokens)
    assert purged_count == 1

    # Verify database state
    remaining = (await test_session.execute(select(RefreshToken))).scalars().all()
    assert len(remaining) == 2
    hashes = {t.token_hash for t in remaining}
    assert hash_token("old-token-value-1") not in hashes
    assert hash_token("recent-token-value-2") in hashes
    assert hash_token("active-token-value-3") in hashes
