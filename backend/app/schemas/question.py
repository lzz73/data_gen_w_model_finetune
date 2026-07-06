"""
Question Schemas
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class QuestionBase(BaseModel):
    """Base question schema"""
    content: str = Field(..., min_length=1)
    answer: Optional[str] = None
    question_type: Optional[str] = Field(None, max_length=50)
    source: Optional[str] = "manual"


class QuestionCreate(QuestionBase):
    """Question create schema"""
    chunk_id: Optional[UUID] = None


class QuestionUpdate(BaseModel):
    """Question update schema"""
    content: Optional[str] = Field(None, min_length=1)
    answer: Optional[str] = None
    question_type: Optional[str] = Field(None, max_length=50)


class QuestionResponse(QuestionBase):
    """Question response schema"""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    generation_status: Optional[str] = None
    answer_status: Optional[str] = None
    answer_error: Optional[str] = None
    quality_score: Optional[float] = None
    generation_metadata: Optional[dict] = Field(
        default=None,
        validation_alias=AliasChoices("generation_metadata", "metadata"),
        serialization_alias="metadata",
    )
    id: UUID
    project_id: UUID
    chunk_id: Optional[UUID]
    batch_id: Optional[UUID] = None  # 生成批次 ID
    file_id: Optional[UUID] = None  # 所属文件 ID
    file_name: Optional[str] = None  # 所属文件名
    created_at: datetime
    updated_at: datetime


# Alias for CRUD
QuestionCreateSchema = QuestionCreate
QuestionUpdateSchema = QuestionUpdate


class GenerateAnswersRequest(BaseModel):
    """Request schema for generating answers"""
    model_id: UUID
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    question_ids: Optional[List[UUID]] = None  # None means all questions without answers
    folder_ids: Optional[List[str]] = None  # 按文件夹选择（问题生成的输出文件夹）
    include_failed: bool = False
    include_answered: bool = False  # 是否包含已有答案的问题（重新生成）


class GenerateQARequest(BaseModel):
    """Request schema for one-step QA pair generation (question + answer together)"""
    model_id: UUID
    count: int = Field(3, ge=1, le=10, description="每块最大问题数")
    chunk_ids: Optional[List[UUID]] = None  # 指定块 ID；None 表示项目下所有块
    file_ids: Optional[List[UUID]] = None  # 指定文件 ID 过滤块
    dirty_data_filter: bool = True  # 默认开启 LLM 内容质量评估
    thinking_mode: bool = True
    preset_prompt: str = Field(
        default="你是一名高质量中文问答数据构建助手，负责基于给定文本块生成可用于训练和评测的问句。\n",
        min_length=1, max_length=4000,
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="问题生成温度")
    answer_model_id: Optional[UUID] = None  # 答案生成模型；None 表示与问题模型相同
    answer_temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="答案生成温度")
    generation_mode: str = Field(default="all", description="生成模式: local / context_enhanced / full_doc / all")
    context_window: int = Field(default=2, ge=0, le=5, description="邻域增强模式：前后各取几个 chunk 作为上下文")
    full_doc_max_chars: int = Field(default=80000, description="全文模式：最大字符数，超出则先摘要再生成")


class GenerateStructuredQARequest(BaseModel):
    """Request schema for structured data QA pair generation"""
    file_ids: List[UUID]  # 结构化文件 ID 列表
    strategy: str = Field(default="template", description="生成策略: template / llm")
    model_id: Optional[UUID] = None  # LLM 策略需要的模型 ID
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    questions_per_row: int = Field(default=1, ge=1, le=5, description="每行数据生成的问答对数量")
