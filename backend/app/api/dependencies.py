"""
API Dependencies
API 依赖项
"""
from typing import Annotated, Optional
from fastapi import Depends
from app.core.auth import verify_api_key


# Type alias for API key dependency
ApiKey = Annotated[str, Depends(verify_api_key)]


# Optional API key (for endpoints that can work with or without auth)
async def get_optional_api_key(api_key: str = None) -> Optional[str]:
    """Get optional API key"""
    return api_key


OptionalApiKey = Annotated[Optional[str], Depends(get_optional_api_key)]
