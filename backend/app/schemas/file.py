"""
File Schemas
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class FileBase(BaseModel):
    """Base file schema"""
    filename: str = Field(..., min_length=1, max_length=255)
    file_type: str = Field(..., max_length=50)
    size: Optional[int] = None


class FileCreate(FileBase):
    """File create schema"""
    project_id: UUID
    file_path: Optional[str] = None
    status: str = "pending"


class FieldSchemaItem(BaseModel):
    """Single field schema item"""
    name: str
    type: str = "string"  # string, integer, float, date, boolean
    sample: Optional[List[str]] = None
    missing_rate: float = 0.0
    role: str = "feature"  # feature, target, redundant
    desensitize: bool = False
    missing_strategy: str = "ignore"  # ignore, drop_row, fill_mode, fill_default
    fill_value: Optional[str] = None  # custom fill value when strategy is fill_default


class FileUpdate(BaseModel):
    """File update schema"""
    status: Optional[str] = None
    field_schema: Optional[List[Dict[str, Any]]] = None
    row_count: Optional[int] = None


class UpdateFieldSchemaRequest(BaseModel):
    """Request body for updating field role configuration"""
    fields: List[FieldSchemaItem]


class FileResponse(FileBase):
    """File response schema"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    file_path: Optional[str]
    status: str
    field_schema: Optional[List[Dict[str, Any]]] = None
    row_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# Alias for CRUD
FileCreateSchema = FileCreate
FileUpdateSchema = FileUpdate
