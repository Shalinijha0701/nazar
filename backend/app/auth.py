from functools import lru_cache

from fastapi import HTTPException
from supabase import Client, create_client

from app.config import Settings, get_settings


@lru_cache
def supabase_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase credentials are not configured")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def authenticated_user(authorization: str | None, settings: Settings) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    if settings.mode == "replay":
        return "demo-user"

    token = authorization.removeprefix("Bearer ").strip()
    try:
        response = supabase_client().auth.get_user(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc
    if not response.user:
        raise HTTPException(status_code=401, detail="Invalid session")
    return str(response.user.id)
