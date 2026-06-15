from __future__ import annotations


from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from supabase import Client as SupabaseClient

from app.config import settings
from app.core.logging import logger
from app.domain.auth import get_profile_by_token
from app.models.base import get_db
from app.models.profile import Profile

security = HTTPBearer(auto_error=False)


def get_supabase_client() -> SupabaseClient:
    return SupabaseClient(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_role_key,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )
    client = get_supabase_client()
    try:
        user = client.auth.get_user(credentials.credentials)
        return user.model_dump()
    except Exception:
        logger.warning("Token verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def get_current_profile(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> Profile:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )
    return get_profile_by_token(db, credentials.credentials)
