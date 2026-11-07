"""Authentication request and response schemas."""

from pydantic import BaseModel, EmailStr, Field

from app.core.constants import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


class RegisterRequest(BaseModel):
    """Payload for user registration."""

    email: EmailStr
    password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description="Plaintext password to be securely hashed with Argon2id",
    )


class LoginRequest(BaseModel):
    """Payload for user authentication."""

    email: EmailStr
    password: str = Field(
        ...,
        min_length=1,
        max_length=PASSWORD_MAX_LENGTH,
        description="User password",
    )


class AuthTokenResponse(BaseModel):
    """Token response returned upon successful authentication or rotation."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int
