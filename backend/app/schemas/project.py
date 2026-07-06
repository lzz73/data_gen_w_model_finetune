"""
Project Schemas
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    """Base project schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    type: str = Field(default="qa")  # qa, table, database


class ProjectCreate(ProjectBase):
    """Project create schema"""
    pass


class ProjectUpdate(BaseModel):
    """Project update schema"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    type: Optional[str] = Field(None)
    extra_data: Optional[dict] = Field(None, description="项目级配置（预处理、脱敏规则等）")


class ProjectResponse(ProjectBase):
    """Project response schema"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    extra_data: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class ProjectStats(BaseModel):
    """Project pipeline statistics"""
    file_count: int = 0
    chunk_count: int = 0
    question_count: int = 0
    dataset_count: int = 0
    eval_count: int = 0


# Alias for CRUD
ProjectCreateSchema = ProjectCreate
ProjectUpdateSchema = ProjectUpdate
