"""
Model Schema
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID


class ModelBase(BaseModel):
    """Base model schema"""
    provider: str = Field(..., description="Model provider: minimax, glm, openai, ali")
    model_type: str = Field(default="chat", description="Model type: chat, vlm, embedding, rerank")
    model_name: str = Field(..., description="Model name")
    api_key: Optional[str] = Field(None, description="API key")
    api_base: Optional[str] = Field(None, description="API base URL")
    is_default: str = Field(default="false", description="Is default model: true/false")


class ModelCreate(ModelBase):
    """Model creation schema"""
    pass


class ModelUpdate(BaseModel):
    """Model update schema"""
    provider: Optional[str] = None
    model_type: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    is_default: Optional[str] = None


class ModelResponse(ModelBase):
    """Model response schema"""
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    project_id: Optional[UUID] = None
    connection_status: Optional[str] = Field(default="untested")

    model_config = ConfigDict(from_attributes=True)
