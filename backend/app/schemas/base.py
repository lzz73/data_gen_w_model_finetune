"""
Base Pydantic schemas
"""
from datetime import datetime
from typing import Optional, Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class TimestampMixin(BaseModel):
    """Mixin for timestamps"""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UUIDMixin(BaseModel):
    """Mixin for UUID"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
