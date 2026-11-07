"""User profile endpoints."""

from fastapi import APIRouter, status

from app.api.deps import CurrentUser
from app.schemas.envelope import SuccessEnvelope
from app.schemas.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=SuccessEnvelope[UserResponse],
    status_code=status.HTTP_200_OK,
)
async def get_current_user_profile(
    current_user: CurrentUser,
) -> SuccessEnvelope[UserResponse]:
    """Retrieve the currently authenticated user's profile."""
    return SuccessEnvelope(data=UserResponse.model_validate(current_user))
