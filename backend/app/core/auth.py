"""
API Key Authentication
API Key 认证中间件
"""
from typing import Optional
from fastapi import Header, HTTPException, Request
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

settings = get_settings()

# API Key header
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Header(None)) -> str:
    """Verify API key from header"""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key is required")

    # In production, you would validate against a database or cache
    # For development, we can use a simple validation
    if settings.DEBUG and api_key == "dev-api-key":
        return api_key

    # TODO: Implement proper API key validation
    # This is a placeholder - in production, validate against stored keys
    if len(api_key) < 32:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key


def create_api_key() -> str:
    """Generate a new API key"""
    import secrets
    return secrets.token_hex(32)
