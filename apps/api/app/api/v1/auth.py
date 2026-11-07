"""Authentication endpoints: register, login, refresh, logout, and logout-all."""

import uuid
from datetime import datetime, timedelta
from typing import Annotated

import redis.asyncio as redis_async
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentUser,
    get_client_ip,
    get_clock,
    get_db_session,
    get_redis_client,
    verify_csrf_origin,
)
from app.core.config import Settings, get_settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    RateLimitedError,
    UnauthorizedError,
)
from app.core.logging import get_logger
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository
from app.schemas.auth import AuthTokenResponse, LoginRequest, RegisterRequest
from app.schemas.envelope import SuccessEnvelope
from app.services.rate_limit import check_rate_limit
from app.services.refresh_policy import RefreshDecision, TokenEvaluationState, decide_refresh
from app.services.security import (
    DUMMY_HASH,
    check_needs_rehash,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)

logger = get_logger("auth")

router = APIRouter(prefix="/auth", tags=["auth"])


def set_refresh_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    """Set the HttpOnly refresh token cookie with strict security flags."""
    is_prod = settings.ENVIRONMENT == "production"
    max_age = settings.REFRESH_TOKEN_TTL_DAYS * 86400
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=max_age,
        expires=max_age,
        path="/api/v1/auth",
        httponly=True,
        samesite="lax",
        secure=is_prod,
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    """Clear the refresh token cookie."""
    is_prod = settings.ENVIRONMENT == "production"
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path="/api/v1/auth",
        httponly=True,
        samesite="lax",
        secure=is_prod,
    )


@router.post(
    "/register",
    response_model=SuccessEnvelope[AuthTokenResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: Request,
    response: Response,
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis_client: Annotated[redis_async.Redis, Depends(get_redis_client)],
    now: Annotated[datetime, Depends(get_clock)],
    client_ip: Annotated[str, Depends(get_client_ip)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SuccessEnvelope[AuthTokenResponse]:
    """Register a new user account with rate limiting, Argon2id hashing, and refresh cookies."""
    # Rate limit: 10 registrations per hour per IP
    rl_result = await check_rate_limit(
        redis_client,
        prefix="reg_ip",
        identifier=client_ip,
        limit=10,
        window_seconds=3600,
        now_timestamp=int(now.timestamp()),
    )
    if not rl_result.allowed:
        raise RateLimitedError(
            "Too many registration attempts. Please try again later.",
            retry_after=rl_result.retry_after,
        )

    # Check for existing email (case-insensitive)
    existing_user = await UserRepository.get_by_email(session, payload.email)
    if existing_user is not None:
        raise ConflictError("Email is already registered", code="EMAIL_TAKEN")

    # Hash password with Argon2id
    pw_hash = hash_password(payload.password)
    user = await UserRepository.create(session, email=payload.email, password_hash=pw_hash)

    # Create refresh token and root family
    raw_refresh = generate_refresh_token()
    token_hash = hash_token(raw_refresh)
    family_id = uuid.uuid4()
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)

    await RefreshTokenRepository.create(
        session,
        user_id=user.id,
        family_id=family_id,
        token_hash=token_hash,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
    )

    await session.commit()

    # Set secure cookie
    set_refresh_cookie(response, raw_refresh, settings)

    # Issue access token
    access_token = create_access_token(
        user_id=user.id,
        secret=settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES),
        now=now,
    )

    return SuccessEnvelope(
        data=AuthTokenResponse(
            access_token=access_token,
            token_type="Bearer",
            expires_in=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
        )
    )


@router.post(
    "/login",
    response_model=SuccessEnvelope[AuthTokenResponse],
    status_code=status.HTTP_200_OK,
)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis_client: Annotated[redis_async.Redis, Depends(get_redis_client)],
    now: Annotated[datetime, Depends(get_clock)],
    client_ip: Annotated[str, Depends(get_client_ip)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SuccessEnvelope[AuthTokenResponse]:
    """Authenticate existing user with dual rate limiting and side-channel timing protection."""
    current_ts = int(now.timestamp())
    normalized_email = payload.email.strip().lower()

    # Rate limit 1: 5 attempts per minute per (IP, email)
    rl_pair = await check_rate_limit(
        redis_client,
        prefix="login_ip_email",
        identifier=f"{client_ip}:{normalized_email}",
        limit=5,
        window_seconds=60,
        now_timestamp=current_ts,
    )
    if not rl_pair.allowed:
        raise RateLimitedError(
            "Too many failed login attempts for this account. Please wait before retrying.",
            retry_after=rl_pair.retry_after,
        )

    # Rate limit 2: 30 attempts per minute per IP
    rl_ip = await check_rate_limit(
        redis_client,
        prefix="login_ip",
        identifier=client_ip,
        limit=30,
        window_seconds=60,
        now_timestamp=current_ts,
    )
    if not rl_ip.allowed:
        raise RateLimitedError(
            "Too many requests from this network. Please wait before retrying.",
            retry_after=rl_ip.retry_after,
        )

    user = await UserRepository.get_by_email(session, normalized_email)
    if user is None:
        # Mitigate timing side-channels via constant-time dummy verification
        verify_password(payload.password, DUMMY_HASH)
        raise UnauthorizedError("Invalid email or password", code="INVALID_CREDENTIALS")

    if not user.is_active:
        raise ForbiddenError("User account is inactive", code="FORBIDDEN")

    if not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password", code="INVALID_CREDENTIALS")

    # Upgrade password hash if Argon2 parameters were updated
    if check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    await UserRepository.update_last_login(session, user, now)

    # Create fresh refresh token family
    raw_refresh = generate_refresh_token()
    token_hash = hash_token(raw_refresh)
    family_id = uuid.uuid4()
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)

    await RefreshTokenRepository.create(
        session,
        user_id=user.id,
        family_id=family_id,
        token_hash=token_hash,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
    )

    await session.commit()

    set_refresh_cookie(response, raw_refresh, settings)

    access_token = create_access_token(
        user_id=user.id,
        secret=settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES),
        now=now,
    )

    return SuccessEnvelope(
        data=AuthTokenResponse(
            access_token=access_token,
            token_type="Bearer",
            expires_in=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
        )
    )


@router.post(
    "/refresh",
    response_model=SuccessEnvelope[AuthTokenResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_csrf_origin)],
)
async def refresh_tokens(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    now: Annotated[datetime, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SuccessEnvelope[AuthTokenResponse]:
    """Rotate refresh token or reuse within grace period under pessimistic lock."""
    cookie_value = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not cookie_value:
        clear_refresh_cookie(response, settings)
        raise UnauthorizedError("Refresh token missing", code="INVALID_TOKEN")

    token_hash = hash_token(cookie_value)

    # Pessimistic row-level lock on the refresh token
    token = await RefreshTokenRepository.get_by_token_hash_for_update(session, token_hash)
    if token is None:
        clear_refresh_cookie(response, settings)
        raise UnauthorizedError("Refresh token invalid", code="INVALID_TOKEN")

    # Check if this token's family was already revoked
    is_family_revoked = await RefreshTokenRepository.is_family_revoked(session, token.family_id)

    state = TokenEvaluationState(
        token_exists=True,
        is_revoked=token.revoked_at is not None,
        is_family_revoked=is_family_revoked,
        is_expired=token.expires_at <= now,
        used_at=token.used_at,
    )

    decision = decide_refresh(state, now=now, grace_seconds=settings.REFRESH_GRACE_SECONDS)

    if decision == RefreshDecision.ROTATE:
        # Create successor in same family
        new_raw_refresh = generate_refresh_token()
        new_token_hash = hash_token(new_raw_refresh)
        new_expires_at = now + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)

        successor = await RefreshTokenRepository.create(
            session,
            user_id=token.user_id,
            family_id=token.family_id,
            token_hash=new_token_hash,
            expires_at=new_expires_at,
            user_agent=request.headers.get("user-agent"),
        )
        await RefreshTokenRepository.mark_used_and_rotate(
            session,
            current_token=token,
            successor_token=successor,
            used_at=now,
        )
        await session.commit()

        set_refresh_cookie(response, new_raw_refresh, settings)

        access_token = create_access_token(
            user_id=token.user_id,
            secret=settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES),
            now=now,
        )
        return SuccessEnvelope(
            data=AuthTokenResponse(
                access_token=access_token,
                token_type="Bearer",
                expires_in=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
            )
        )

    if decision == RefreshDecision.GRACE_REUSE:
        # Concurrent request within grace window: issue new access token without rotating cookie
        await session.commit()
        access_token = create_access_token(
            user_id=token.user_id,
            secret=settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES),
            now=now,
        )
        return SuccessEnvelope(
            data=AuthTokenResponse(
                access_token=access_token,
                token_type="Bearer",
                expires_in=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
            )
        )

    if decision == RefreshDecision.REVOKE_FAMILY:
        # Token reused outside grace window: breach detected, revoke all tokens in family
        await RefreshTokenRepository.revoke_family(session, token.family_id, now)
        await session.commit()
        clear_refresh_cookie(response, settings)
        logger.warning(
            "refresh_token_reuse_detected",
            user_id=str(token.user_id),
            family_id=str(token.family_id),
            now=now.isoformat(),
            used_at=token.used_at.isoformat() if token.used_at else None,
            diff_seconds=(now - token.used_at).total_seconds() if token.used_at else None,
        )
        raise UnauthorizedError(
            "Refresh token reuse detected. Family revoked.",
            code="REFRESH_TOKEN_REUSED",
        )

    if decision == RefreshDecision.REJECT_EXPIRED:
        clear_refresh_cookie(response, settings)
        raise UnauthorizedError("Refresh token expired", code="TOKEN_EXPIRED")

    # REJECT_REVOKED or REJECT_UNKNOWN
    clear_refresh_cookie(response, settings)
    raise UnauthorizedError("Refresh token revoked or invalid", code="INVALID_TOKEN")


@router.post(
    "/logout",
    response_model=SuccessEnvelope[dict[str, str]],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_csrf_origin)],
)
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    now: Annotated[datetime, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SuccessEnvelope[dict[str, str]]:
    """Log out current session by revoking the token family and clearing the cookie."""
    cookie_value = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if cookie_value:
        token_hash = hash_token(cookie_value)
        token = await RefreshTokenRepository.get_by_token_hash_for_update(session, token_hash)
        if token is not None:
            await RefreshTokenRepository.revoke_family(session, token.family_id, now)
            await session.commit()

    clear_refresh_cookie(response, settings)
    return SuccessEnvelope(data={"status": "logged_out"})


@router.post(
    "/logout-all",
    response_model=SuccessEnvelope[dict[str, str]],
    status_code=status.HTTP_200_OK,
)
async def logout_all(
    response: Response,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    now: Annotated[datetime, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SuccessEnvelope[dict[str, str]]:
    """Revoke all active refresh token families for the authenticated user across all devices."""
    await RefreshTokenRepository.revoke_all_for_user(session, current_user.id, now)
    await session.commit()

    clear_refresh_cookie(response, settings)
    return SuccessEnvelope(data={"status": "all_sessions_revoked"})
