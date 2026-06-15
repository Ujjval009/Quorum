from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from supabase import Client as SupabaseClient

from app.core.logging import logger
from app.models.profile import Profile


def _get_anon_client() -> SupabaseClient:
    from app.config import settings

    return SupabaseClient(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_anon_key,
    )


def _get_admin_client() -> SupabaseClient:
    from app.config import settings

    return SupabaseClient(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_role_key,
    )


def signup(email: str, password: str) -> None:
    client = _get_admin_client()
    try:
        client.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
        })
        logger.info("User signed up (auto-confirmed)", email=email)
    except Exception as e:
        err_str = str(e)
        if "already been registered" in err_str:
            logger.info("User already exists, proceeding with login", email=email)
            return
        logger.error("Signup failed", email=email, error=err_str)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signup failed. Please check your credentials and try again.",
        )


def login(email: str, password: str) -> tuple[str, dict]:
    client = _get_anon_client()
    try:
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        session = getattr(response, "session", None)
        if session is None:
            logger.warning("Login requires email confirmation", email=email)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email confirmation required. Check your inbox.",
            )
        user_raw = getattr(session, "user", None) or getattr(response, "user", {})
        user_data = user_raw.model_dump() if hasattr(user_raw, "model_dump") else user_raw
        logger.info("User logged in", email=email, user_id=user_data.get("id"))
        return session.access_token, user_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login failed", email=email, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )


def verify_token(token: str) -> dict:
    client = _get_admin_client()
    try:
        response = client.auth.get_user(token)
        user = getattr(response, "user", response)
        if hasattr(user, "model_dump"):
            user_data = user.model_dump()
        else:
            user_data = dict(user)
        logger.debug("Token verified", user_id=user_data.get("id"))
        return user_data
    except Exception as e:
        logger.warning("Token verification failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def refresh_session(refresh_token: str) -> tuple[str, str, dict]:
    client = _get_anon_client()
    try:
        response = client.auth.refresh_session(refresh_token)
        session = getattr(response, "session", response)
        user_raw = getattr(session, "user", {})
        user_data = user_raw.model_dump() if hasattr(user_raw, "model_dump") else user_raw
        logger.info("Session refreshed", user_id=user_data.get("id"))
        return session.access_token, session.refresh_token, user_data
    except Exception as e:
        logger.warning("Session refresh failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )


def sync_profile(db: Session, supabase_user: dict) -> Profile:
    user_id = supabase_user["id"]
    email = supabase_user.get("email", "")

    profile = db.query(Profile).filter(Profile.id == user_id).first()
    if profile:
        logger.debug("Profile already exists", user_id=user_id)
        return profile

    profile = Profile(id=user_id, email=email)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    logger.info("Profile created", user_id=user_id, email=email)
    return profile


def get_profile_by_token(db: Session, token: str) -> Profile:
    supabase_user = verify_token(token)
    return sync_profile(db, supabase_user)
