"""
Authentication endpoints.

    POST /api/auth/register
    POST /api/auth/login
    GET  /api/auth/profile
    PUT  /api/auth/profile
    POST /api/auth/logout
"""

from fastapi import APIRouter, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.deps import CurrentUser
from app.core.security import create_access_token, hash_password, verify_password
from app.models.enums import AuditAction, AuditStatus, UserRole
from app.models.user import User, utcnow
from app.schemas.common import Message
from app.schemas.user import Token, UserLogin, UserOut, UserRegister, UserUpdate
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _issue_token(user: User) -> Token:
    token = create_access_token(subject=str(user.id), role=user.role.value)
    return Token(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.from_user(user),
    )


@router.post(
    "/register",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account",
)
async def register(payload: UserRegister):
    email = payload.email.lower().strip()

    # Bootstrap rule: the very first account created becomes the administrator,
    # because otherwise a fresh deployment would have no way to get one. Every
    # account after that is an analyst, and only an existing admin can promote
    # them via PATCH /api/users/{id}/role.
    is_first_user = await User.find_one() is None
    role = UserRole.ADMIN if is_first_user else UserRole.ANALYST

    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        role=role,
    )

    try:
        await user.insert()
    except DuplicateKeyError:
        # Relying on the unique index rather than a check-then-insert. A
        # separate "does this email exist?" query would leave a race window
        # where two concurrent registrations both pass the check.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    await log_action(
        AuditAction.USER_REGISTERED,
        user=user,
        remarks=f"Registered as {user.role.value}"
        + (" (first user - auto-admin)" if is_first_user else ""),
    )
    return _issue_token(user)


@router.post("/login", response_model=Token, summary="Exchange credentials for a JWT")
async def login(payload: UserLogin):
    email = payload.email.lower().strip()
    user = await User.find_one(User.email == email)

    # Same status and message for "no such user" and "wrong password".
    # Distinguishing them would let anyone enumerate which emails have accounts.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated",
        )

    await log_action(AuditAction.USER_LOGIN, user=user, status=AuditStatus.SUCCESS)
    return _issue_token(user)


@router.get("/profile", response_model=UserOut, summary="Current user's profile")
async def get_profile(user: CurrentUser):
    return UserOut.from_user(user)


@router.put("/profile", response_model=UserOut, summary="Update name or email")
async def update_profile(payload: UserUpdate, user: CurrentUser):
    if payload.email is not None:
        new_email = payload.email.lower().strip()
        if new_email != user.email:
            taken = await User.find_one(User.email == new_email)
            if taken:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="That email is already in use",
                )
            user.email = new_email

    if payload.name is not None:
        user.name = payload.name.strip()

    user.updated_at = utcnow()
    await user.save()
    return UserOut.from_user(user)


@router.post("/logout", response_model=Message, summary="Log out")
async def logout(user: CurrentUser):
    """
    JWTs are stateless, so there is nothing to invalidate server-side; the
    client discards the token. This endpoint exists so the action is audited.
    Real revocation needs a token blocklist in Redis - noted in the README as
    a known limitation.
    """
    await log_action(AuditAction.USER_LOGIN, user=user, remarks="Logged out")
    return Message(detail="Logged out successfully")
