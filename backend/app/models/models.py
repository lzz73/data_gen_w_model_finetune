"""
Database Models for YG-Dataset
"""
from sqlalchemy import Column, String, Text, Integer, BigInteger, ForeignKey, JSON, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import UUIDMixin, TimestampMixin


class Project(Base, UUIDMixin, TimestampMixin):
    """Project model"""
    __tablename__ = "projects"

    name = Column(String(255), nullable=False)
    description = Column(Text)
    type = Column(String(50), default="qa")  # qa, table, database
    extra_data = Column(JSON, default=dict)  # project-level config: preprocessing, desensitize rules, etc.

    # Relationships
    files = relationship("File", back_populates="project", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="project", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="project", cascade="all, delete-orphan")
    datasets = relationship("Dataset", back_populates="project", cascade="all, delete-orphan")
    eval_datasets = relationship("EvalDataset", back_populates="project", cascade="all, delete-orphan")
    model_configs = relationship("ModelConfig", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")


class File(Base, UUIDMixin, TimestampMixin):
    """File model for uploaded documents"""
    __tablename__ = "files"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf, docx, xlsx, csv, epub, md, txt
    file_path = Column(String(500))
    size = Column(BigInteger)  # file size in bytes
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    field_schema = Column(JSON, default=list)  # auto-extracted field metadata with user annotations
    row_count = Column(Integer)  # number of data rows (for structured files)

    # Relationships
    project = relationship("Project", back_populates="files")
    chunks = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")


class Chunk(Base, UUIDMixin, TimestampMixin):
    """Text chunk model after splitting"""
    __tablename__ = "chunks"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"))
    name = Column(String(255))
    content = Column(Text, nullable=False)
    summary = Column(Text)
    word_count = Column(Integer)
    extra_data = Column(JSON)  # store additional info like headings, page numbers

    # Relationships
    project = relationship("Project", back_populates="chunks")
    file = relationship("File", back_populates="chunks")
    questions = relationship("Question", back_populates="chunk", cascade="all, delete-orphan")
    chunk_tags = relationship("ChunkTag", back_populates="chunk", cascade="all, delete-orphan")


class Tag(Base, UUIDMixin, TimestampMixin):
    """Tag/Label model for categorizing content"""
    __tablename__ = "tags"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    label = Column(String(255), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"))
    color = Column(String(20))  # hex color code

    # Relationships
    project = relationship("Project", back_populates="tags")
    parent = relationship("Tag", remote_side="Tag.id", back_populates="children")
    children = relationship("Tag", back_populates="parent")
    chunk_tags = relationship("ChunkTag", back_populates="tag")


class ChunkTag(Base, UUIDMixin):
    """Many-to-many relationship between chunks and tags"""
    __tablename__ = "chunk_tags"

    chunk_id = Column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)

    # Relationships
    chunk = relationship("Chunk", back_populates="chunk_tags")
    tag = relationship("Tag", back_populates="chunk_tags")


class Question(Base, UUIDMixin, TimestampMixin):
    """Question/QA pair model"""
    __tablename__ = "questions"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chunk_id = Column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"))
    batch_id = Column(UUID(as_uuid=True), index=True)  # 生成批次 ID，同一次生成的问答对共享同一 batch_id
    content = Column(Text, nullable=False)  # question content
    answer = Column(Text)  # answer content
    question_type = Column(String(50))  # fact, summary, reasoning, etc.
    source = Column(String(50), default="manual")  # manual, generated
    generation_status = Column(String(30), nullable=False, default="generated")
    answer_status = Column(String(20), nullable=False, default="pending")
    answer_error = Column(Text)
    quality_score = Column(Float)
    generation_metadata = Column("metadata", JSON)

    # Relationships
    project = relationship("Project")
    chunk = relationship("Chunk", back_populates="questions")


class Dataset(Base, UUIDMixin, TimestampMixin):
    """Dataset model"""
    __tablename__ = "datasets"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    dataset_type = Column(String(50))  # qa, conversation, instruction
    extra_data = Column(JSON)

    # Relationships
    project = relationship("Project", back_populates="datasets")


class EvalDataset(Base, UUIDMixin, TimestampMixin):
    """Evaluation dataset model"""
    __tablename__ = "eval_datasets"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    question_type = Column(String(50))  # mixed, fact, reasoning
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    question_count = Column(Integer, default=0)
    extra_data = Column(JSON)

    # Relationships
    project = relationship("Project", back_populates="eval_datasets")
    eval_results = relationship("EvalResult", back_populates="eval_dataset", cascade="all, delete-orphan")


class EvalResult(Base, UUIDMixin, TimestampMixin):
    """Evaluation result model"""
    __tablename__ = "eval_results"

    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    eval_dataset_id = Column(UUID(as_uuid=True), ForeignKey("eval_datasets.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"))
    model_answer = Column(Text)
    expected_answer = Column(Text)
    judge_score = Column(Float)
    is_correct = Column(String(10))  # true, false, partial
    feedback = Column(Text)
    eval_metadata = Column(JSON)

    # Relationships
    task = relationship("Task", back_populates="eval_results")
    eval_dataset = relationship("EvalDataset", back_populates="eval_results")
    question = relationship("Question")


class ModelConfig(Base, UUIDMixin, TimestampMixin):
    """Model configuration for LLM providers"""
    __tablename__ = "model_configs"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    provider = Column(String(50), nullable=False)  # minimax, glm, openai, ali
    model_type = Column(String(50), nullable=False, default="chat")  # chat, vlm, embedding, rerank
    model_name = Column(String(100))
    api_key = Column(String(500))
    api_base = Column(String(500))
    is_default = Column(String(10), default="false")
    connection_status = Column(String(20), default="untested")  # untested, connected, disconnected

    # Relationships
    project = relationship("Project", back_populates="model_configs")


class Task(Base, UUIDMixin, TimestampMixin):
    """Task model for background jobs"""
    __tablename__ = "tasks"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    task_type = Column(String(50))  # split, generate, eval, export, model-evaluation
    status = Column(String(20), default="pending")  # pending, running, completed, failed, stopped
    progress = Column(Integer, default=0)  # 0-100
    result = Column(JSON)
    error = Column(Text)
    model_info = Column(Text)  # JSON string
    detail = Column(Text)  # JSON string
    language = Column(String(20), default="zh-CN")
    total_count = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    end_time = Column(String(50))
    note = Column(Text)

    # Relationships
    project = relationship("Project", back_populates="tasks")
    eval_results = relationship("EvalResult", back_populates="task", cascade="all, delete-orphan")


class AuditLog(Base, UUIDMixin, TimestampMixin):
    """Audit log for desensitization operations"""
    __tablename__ = "audit_logs"

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chunk_id = Column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"))
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"))
    rule_id = Column(String(100))  # which rule triggered (e.g., "phone", "id_card", "keyword:薪资")
    rule_type = Column(String(20))  # regex, keyword, ner
    original_text = Column(String(50))  # first 10 chars of original for audit
    replacement = Column(String(100))  # what it was replaced with
    confidence = Column(Float, default=1.0)  # 1.0 for regex, 0.0-1.0 for NER
