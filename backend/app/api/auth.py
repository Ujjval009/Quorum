from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_profile
from app.core.logging import logger
from app.core.rate_limiter import RateLimiter, RateLimitExceeded
from app.domain.auth import (
    get_profile_by_token,
    login,
    refresh_session,
    signup,
)
from app.models.base import get_db
from app.models.profile import Profile
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    SignUpRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Shared rate limiter for auth endpoints ──
_auth_limiter = RateLimiter(window=60, max_requests=10)


def _check_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    try:
        _auth_limiter.check(f"auth:{client_ip}")
    except RateLimitExceeded:
        logger.warning("Rate limit exceeded", client_ip=client_ip, endpoint="auth")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )


@router.post("/signup", status_code=201)
def register(
    body: SignUpRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthResponse:
    _check_rate_limit(request)
    logger.info("Signup request", email=body.email)
    from app.domain.auth import sync_profile
    signup(email=body.email, password=body.password)
    token_data = login(email=body.email, password=body.password)
    access_token, user_data = token_data
    profile = sync_profile(db, user_data)
    return AuthResponse(
        access_token=access_token,
        user=UserResponse(
            id=profile.id,
            email=profile.email,
            display_name=profile.display_name,
            created_at=profile.created_at,
        ),
    )


@router.post("/login")
def sign_in(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthResponse:
    _check_rate_limit(request)
    logger.info("Login request", email=body.email)
    access_token, user_data = login(email=body.email, password=body.password)
    profile = get_profile_by_token(db, access_token)

    return AuthResponse(
        access_token=access_token,
        user=UserResponse(
            id=profile.id,
            email=profile.email,
            display_name=profile.display_name,
            created_at=profile.created_at,
        ),
    )


@router.post("/refresh")
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> AuthResponse:
    logger.info("Token refresh request")
    access_token, _refresh_token, user_data = refresh_session(body.refresh_token)
    profile = get_profile_by_token(db, access_token)

    return AuthResponse(
        access_token=access_token,
        user=UserResponse(
            id=profile.id,
            email=profile.email,
            display_name=profile.display_name,
            created_at=profile.created_at,
        ),
    )


@router.get("/me")
def me(profile: Profile = Depends(get_current_profile)) -> UserResponse:
    logger.info("Profile fetch", user_id=profile.id)
    return UserResponse(
        id=profile.id,
        email=profile.email,
        display_name=profile.display_name,
        created_at=profile.created_at,
    )
