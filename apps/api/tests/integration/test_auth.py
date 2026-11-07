import asyncio
import io
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import redis.asyncio as redis_async
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_redis_client
from app.main import create_app
from app.models.refresh_token import RefreshToken
from app.models.user import User


@pytest.mark.asyncio
async def test_register_success_and_cookie_attributes(client: AsyncClient) -> None:
    """Verify registration creates user, returns access token, and sets secure HttpOnly cookie."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "investor1@example.com", "password": "Password123!"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert "access_token" in payload["data"]
    assert payload["data"]["token_type"] == "Bearer"
    assert payload["data"]["expires_in"] == 900
    assert "refresh_token" not in payload["data"]

    # Verify cookie attributes
    cookie_header = response.headers.get("set-cookie")
    assert cookie_header is not None
    assert "fp_refresh=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Path=/api/v1/auth" in cookie_header
    assert "samesite=lax" in cookie_header.lower()
    assert "secure" not in cookie_header.lower()


@pytest.mark.asyncio
async def test_cookie_secure_in_production(
    test_session: AsyncSession, test_redis: redis_async.Redis
) -> None:
    """Verify Secure flag is present on cookies when ENVIRONMENT=production."""
    from app.core.config import Settings, get_settings

    test_app = create_app()

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_session

    def override_redis() -> redis_async.Redis:
        return test_redis

    prod_settings = get_settings().model_copy(
        update={
            "ENVIRONMENT": "production",
            "JWT_SECRET": "a" * 64,
            "CORS_ORIGINS": ["https://app.foliopilot.in"],
        }
    )

    def override_settings() -> Settings:
        return prod_settings

    test_app.dependency_overrides[get_db_session] = override_db
    test_app.dependency_overrides[get_redis_client] = override_redis
    test_app.dependency_overrides[get_settings] = override_settings

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.post(
            "/api/v1/auth/register",
            json={"email": "prodcookie@example.com", "password": "Password123!"},
        )
        assert res.status_code == 201
        cookie_header = res.headers.get("set-cookie")
        assert cookie_header is not None
        assert "secure" in cookie_header.lower()


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    """Verify duplicate email registration returns 409 EMAIL_TAKEN."""
    res1 = await client.post(
        "/api/v1/auth/register",
        json={"email": "duplicate@example.com", "password": "Password123!"},
    )
    assert res1.status_code == 201

    res2 = await client.post(
        "/api/v1/auth/register",
        json={"email": "DUPLICATE@example.com", "password": "Password123!"},
    )
    assert res2.status_code == 409
    payload = res2.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "EMAIL_TAKEN"


@pytest.mark.asyncio
async def test_login_success_and_last_login(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Verify login updates last_login_at and returns tokens."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "investor2@example.com", "password": "Password123!"},
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "investor2@example.com", "password": "Password123!"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "access_token" in payload["data"]
    assert "fp_refresh=" in response.headers["set-cookie"]

    # Verify database record updated
    user = (
        await test_session.execute(select(User).where(User.email == "investor2@example.com"))
    ).scalar_one()
    assert user.last_login_at is not None


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient) -> None:
    """Verify unknown user or wrong password returns 401 INVALID_CREDENTIALS."""
    # Unknown user (executes dummy verify)
    res1 = await client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.com", "password": "AnyPassword123!"},
    )
    assert res1.status_code == 401
    assert res1.json()["error"]["code"] == "INVALID_CREDENTIALS"

    # Known user, wrong password
    await client.post(
        "/api/v1/auth/register",
        json={"email": "known@example.com", "password": "CorrectPassword123!"},
    )
    res2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "known@example.com", "password": "WrongPassword123!"},
    )
    assert res2.status_code == 401
    assert res2.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_login_identical_error_for_unknown_user_and_wrong_password(
    client: AsyncClient,
) -> None:
    """Verify wrong password and unknown email return identical status, code, and message."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "existing@example.com", "password": "Password123!"},
    )
    res_unknown = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Password123!"},
    )
    res_wrong = await client.post(
        "/api/v1/auth/login",
        json={"email": "existing@example.com", "password": "WrongPassword!"},
    )

    assert res_unknown.status_code == res_wrong.status_code == 401
    err_unknown = res_unknown.json()["error"]
    err_wrong = res_wrong.json()["error"]
    assert err_unknown["code"] == err_wrong["code"] == "INVALID_CREDENTIALS"
    assert err_unknown["message"] == err_wrong["message"]


@pytest.mark.asyncio
async def test_refresh_grace_window_reuse(client: AsyncClient) -> None:
    """Verify reuse within grace window gives 200 with access token and no Set-Cookie header."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "grace@example.com", "password": "Password123!"},
    )
    first_cookie = client.cookies.get("fp_refresh")
    assert first_cookie is not None

    # Legitimate rotation
    rot = await client.post("/api/v1/auth/refresh")
    assert rot.status_code == 200
    assert "set-cookie" in rot.headers

    # Immediate reuse of first_cookie within grace window (< 10 seconds)
    client.cookies.set("fp_refresh", first_cookie)
    grace_res = await client.post("/api/v1/auth/refresh")
    assert grace_res.status_code == 200
    assert "access_token" in grace_res.json()["data"]
    assert "set-cookie" not in grace_res.headers


@pytest.mark.asyncio
async def test_refresh_rotation_and_successor_chain(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Verify clean rotation marks predecessor used and links successor."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "rotate@example.com", "password": "Password123!"},
    )
    assert reg.status_code == 201

    refresh_res = await client.post("/api/v1/auth/refresh")
    assert refresh_res.status_code == 200
    assert "access_token" in refresh_res.json()["data"]
    assert "fp_refresh=" in refresh_res.headers["set-cookie"]

    # Check database: 2 tokens exist in the same family
    tokens = (await test_session.execute(select(RefreshToken))).scalars().all()
    assert len(tokens) == 2
    root_token = next(t for t in tokens if t.used_at is not None)
    successor_token = next(t for t in tokens if t.used_at is None)

    assert root_token.replaced_by_id == successor_token.id
    assert root_token.family_id == successor_token.family_id


@pytest.mark.asyncio
async def test_concurrent_refreshes(
    test_session: AsyncSession, test_redis: redis_async.Redis
) -> None:
    """Verify concurrent refreshes with the same token yield two 200s and exactly 1 new row."""
    from tests.conftest import _test_session_factory

    assert _test_session_factory is not None
    test_app = create_app()

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with _test_session_factory() as s:
            yield s

    def override_redis() -> redis_async.Redis:
        return test_redis

    test_app.dependency_overrides[get_db_session] = override_db
    test_app.dependency_overrides[get_redis_client] = override_redis

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        reg = await c.post(
            "/api/v1/auth/register",
            json={"email": "concurrent@example.com", "password": "Password123!"},
        )
        assert reg.status_code == 201
        cookie_val = c.cookies.get("fp_refresh")
        assert cookie_val is not None

    # Launch two concurrent refreshes with identical cookie
    async def make_refresh_call() -> tuple[int, str | None]:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            cookies={"fp_refresh": cookie_val},
        ) as local_c:
            res = await local_c.post("/api/v1/auth/refresh")
            set_cookie = res.headers.get("set-cookie")
            return res.status_code, set_cookie

    res1, res2 = await asyncio.gather(make_refresh_call(), make_refresh_call())

    # Both requests must succeed with 200
    assert res1[0] == 200
    assert res2[0] == 200

    # Exactly one request rotated and set cookie; the second was handled via grace reuse (no cookie)
    cookies_set = [r[1] for r in (res1, res2) if r[1] is not None]
    assert len(cookies_set) == 1

    # Exactly 2 total token rows exist (1 root marked used, 1 successor created)
    tokens = (await test_session.execute(select(RefreshToken))).scalars().all()
    assert len(tokens) == 2


@pytest.mark.asyncio
async def test_refresh_token_reuse_revokes_entire_family(
    client: AsyncClient, test_session: AsyncSession
) -> None:
    """Verify token reuse outside grace window revokes the whole family with 401."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "reuse@example.com", "password": "Password123!"},
    )
    first_cookie = client.cookies.get("fp_refresh")

    # Rotate legitimately
    rot = await client.post("/api/v1/auth/refresh")
    assert rot.status_code == 200
    newest_cookie = client.cookies.get("fp_refresh")
    assert newest_cookie is not None
    assert newest_cookie != first_cookie

    # Backdate the used_at timestamp on the root token to 20 seconds ago (> 10s grace)
    tokens = (await test_session.execute(select(RefreshToken))).scalars().all()
    root_token = next(t for t in tokens if t.used_at is not None)
    root_token.used_at = datetime.now(UTC) - timedelta(seconds=20)
    await test_session.commit()

    # Attacker attempts replay of the stolen root token
    assert first_cookie is not None
    client.cookies.set("fp_refresh", first_cookie)
    reuse_res = await client.post("/api/v1/auth/refresh")
    assert reuse_res.status_code == 401
    assert reuse_res.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"

    # Entire family revoked in database
    await test_session.refresh(root_token)
    all_family_tokens = (
        (
            await test_session.execute(
                select(RefreshToken).where(RefreshToken.family_id == root_token.family_id)
            )
        )
        .scalars()
        .all()
    )
    assert all(t.revoked_at is not None for t in all_family_tokens)

    # Attempting to use newest token in that revoked family must also be rejected with 401
    client.cookies.set("fp_refresh", newest_cookie)
    subsequent_res = await client.post("/api/v1/auth/refresh")
    assert subsequent_res.status_code == 401
    assert subsequent_res.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_logout_revokes_family(client: AsyncClient, test_session: AsyncSession) -> None:
    """Verify logout revokes the family and clears cookie."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "logout@example.com", "password": "Password123!"},
    )

    res = await client.post("/api/v1/auth/logout")
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "logged_out"

    tokens = (await test_session.execute(select(RefreshToken))).scalars().all()
    assert all(t.revoked_at is not None for t in tokens)


@pytest.mark.asyncio
async def test_logout_is_idempotent(client: AsyncClient) -> None:
    """Verify calling logout twice in a row returns 200 on both calls."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "idempotent@example.com", "password": "Password123!"},
    )

    res1 = await client.post("/api/v1/auth/logout")
    assert res1.status_code == 200
    assert res1.json()["data"]["status"] == "logged_out"

    res2 = await client.post("/api/v1/auth/logout")
    assert res2.status_code == 200
    assert res2.json()["data"]["status"] == "logged_out"


@pytest.mark.asyncio
async def test_logout_all(client: AsyncClient, test_session: AsyncSession) -> None:
    """Verify logout-all revokes all sessions across all families for the user."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "logoutall@example.com", "password": "Password123!"},
    )
    access_token = reg.json()["data"]["access_token"]

    # Create a second independent session for same user via login
    await client.post(
        "/api/v1/auth/login",
        json={"email": "logoutall@example.com", "password": "Password123!"},
    )

    tokens_before = (await test_session.execute(select(RefreshToken))).scalars().all()
    assert len(tokens_before) == 2
    assert tokens_before[0].family_id != tokens_before[1].family_id

    # Call logout-all with access token
    res = await client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "all_sessions_revoked"

    tokens_after = (await test_session.execute(select(RefreshToken))).scalars().all()
    assert all(t.revoked_at is not None for t in tokens_after)


@pytest.mark.asyncio
async def test_rate_limiting_registration_and_login(client: AsyncClient) -> None:
    """Verify 429 RATE_LIMITED and Retry-After header on exceeding limits."""
    # Register 10 times with distinct emails from same IP
    for i in range(10):
        r = await client.post(
            "/api/v1/auth/register",
            json={"email": f"rate{i}@example.com", "password": "Password123!"},
        )
        assert r.status_code == 201

    # 11th registration from same IP must be rate limited
    blocked_reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "rate10@example.com", "password": "Password123!"},
    )
    assert blocked_reg.status_code == 429
    assert blocked_reg.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in blocked_reg.headers


@pytest.mark.asyncio
async def test_login_rate_limiting(client: AsyncClient) -> None:
    """Verify 5 failed attempts per (IP, email) returns 429 with Retry-After on 6th attempt."""
    email = "ratelimit_login@example.com"
    for _ in range(5):
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "WrongPassword123!"},
        )
        assert res.status_code == 401

    # 6th attempt must be rate-limited
    blocked = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword123!"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in blocked.headers


@pytest.mark.asyncio
async def test_csrf_foreign_origin_rejected(client: AsyncClient) -> None:
    """Verify cookie-authenticated endpoints reject unapproved foreign Origin headers."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "csrf@example.com", "password": "Password123!"},
    )

    bad_refresh = await client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": "https://evil-phishing-site.com"},
    )
    assert bad_refresh.status_code == 403
    assert bad_refresh.json()["error"]["code"] == "FORBIDDEN"

    bad_logout = await client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://evil-phishing-site.com"},
    )
    assert bad_logout.status_code == 403
    assert bad_logout.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_log_redaction_during_auth(client: AsyncClient) -> None:
    """Verify passwords and tokens are never printed or leaked in application logs."""
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    secret_password = "UltraSecretPassword999!"
    try:
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": "redact@example.com", "password": secret_password},
        )
        assert reg.status_code == 201
        token = reg.json()["data"]["access_token"]

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "redact@example.com", "password": secret_password},
        )
        assert login.status_code == 200

        logs = log_capture.getvalue()
        assert secret_password not in logs
        assert token not in logs
    finally:
        root_logger.removeHandler(handler)
