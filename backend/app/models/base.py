"""
Base Model with UUID support
"""
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

# 使用北京时间（UTC+8）
_BEIJING_TZ = timezone(timedelta(hours=8))


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps"""
    created_at = Column(DateTime, default=lambda: datetime.now(_BEIJING_TZ), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(_BEIJING_TZ), onupdate=lambda: datetime.now(_BEIJING_TZ), nullable=False)


class UUIDMixin:
    """Mixin for UUID primary key"""
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
