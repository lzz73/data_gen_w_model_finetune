"""
Chunk Schemas
"""
from datetime import datetime
from typing import Optional, Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ChunkBase(BaseModel):
    """Base chunk schema"""
    name: Optional[str] = Field(None, max_length=255)
    content: str = Field(..., min_length=1)
    summary: Optional[str] = None
    word_count: Optional[int] = None
    extra_data: Optional[dict] = None


class ChunkCreate(ChunkBase):
    """Chunk create schema"""
    project_id: Optional[UUID] = None
    file_id: Optional[UUID] = None


class ChunkUpdate(BaseModel):
    """Chunk update schema"""
    name: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = None
    extra_data: Optional[dict] = None


class ChunkResponse(ChunkBase):
    """Chunk response schema"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    file_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime


# Alias for CRUD
ChunkCreateSchema = ChunkCreate
ChunkUpdateSchema = ChunkUpdate
