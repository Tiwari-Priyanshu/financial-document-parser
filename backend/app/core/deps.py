"""
Reusable FastAPI dependencies.

This is where "Authentication & Authorization" actually happens. Rather than
repeating token checks in every endpoint, a route declares what it needs in its
signature and FastAPI resolves it:

    async def list_docs(user: CurrentUser): ...       # any logged-in user
    async def delete_doc(user: AdminUser): ...        # admins only
"""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.models.enums import UserRole
from app.models.user import User

# auto_error=False so we raise our own 401 with a consistent body shape.
bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> User:
    if credentials is None or not credentials.credentials:
        raise CREDENTIALS_EXCEPTION

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise CREDENTIALS_EXCEPTION

    user_id = payload.get("sub")
    if not user_id:
        raise CREDENTIALS_EXCEPTION

    try:
        object_id = PydanticObjectId(user_id)
    except Exception:
        raise CREDENTIALS_EXCEPTION

    # We still load the user rather than trusting the token blindly. A token
    # issued before an account was deactivated must stop working immediately,
    # not at expiry.
    user = await User.get(object_id)
    if user is None or not user.is_active:
        raise CREDENTIALS_EXCEPTION

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires administrator privileges",
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]
