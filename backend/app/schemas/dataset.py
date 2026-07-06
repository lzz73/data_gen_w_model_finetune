"""
Dataset Schemas
"""
from datetime import datetime
from typing import Optional, Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class DatasetBase(BaseModel):
    """Base dataset schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    dataset_type: Optional[str] = Field(None, max_length=50)
    extra_data: Optional[dict] = None


class DatasetCreate(DatasetBase):
    """Dataset create schema"""
    pass


class DatasetUpdate(BaseModel):
    """Dataset update schema"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    dataset_type: Optional[str] = Field(None, max_length=50)
    extra_data: Optional[dict] = None


class DatasetResponse(DatasetBase):
    """Dataset response schema"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime


# Alias for CRUD
DatasetCreateSchema = DatasetCreate
DatasetUpdateSchema = DatasetUpdate
