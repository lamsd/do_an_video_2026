from fastapi import Header, HTTPException

from .config import get_settings


def owner(x_app_user_id: str | None = Header(default=None)) -> str:
    """Temporary development identity; replace with JWT/session middleware before production."""
    settings = get_settings()
    if x_app_user_id:
        return x_app_user_id
    if settings.app_env == "development":
        return "local-dev"
    raise HTTPException(401, "missing application identity")
