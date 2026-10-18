from typing import Optional
from fastapi import Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.core.security import decode_access_token
from backend.app.db.db_service import get_user_by_email

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

import os

def _get_limiter_storage_uri() -> str:
    if os.getenv("ENVIRONMENT") == "test":
        return "memory://"
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis
        client = redis.from_url(redis_url, socket_connect_timeout=1.0)
        client.ping()
        return redis_url
    except Exception:
        return "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_get_limiter_storage_uri(),
    enabled=os.getenv("ENVIRONMENT") != "test"
)

async def get_current_user(
    header_token: Optional[str] = Depends(oauth2_scheme)
):
    if not header_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(header_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub")
    user = await get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def get_current_user_optional(
    header_token: Optional[str] = Depends(oauth2_scheme)
) -> Optional[dict]:
    if not header_token:
        return None
    payload = decode_access_token(header_token)
    if not payload:
        return None
    email = payload.get("sub")
    return await get_user_by_email(email)

