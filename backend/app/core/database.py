"""
Database Configuration and Session Management
支持 SQLite 和 PostgreSQL
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_engine_config():
    """根据数据库类型返回引擎配置"""
    if settings.DATABASE_URL.startswith("sqlite"):
        return {
            "echo": settings.DEBUG,
            "poolclass": NullPool,
            "connect_args": {"check_same_thread": False},
        }
    else:
        return {
            "echo": settings.DEBUG,
            "pool_pre_ping": True,
            "pool_size": 10,
            "max_overflow": 20,
            "pool_recycle": 3600,
            "pool_timeout": 30,
        }


# Async engine for FastAPI
async_engine = create_async_engine(
    settings.DATABASE_URL,
    **get_engine_config()
)


# SQLite: 在每个新连接上启用 WAL 模式，确保并发读写不阻塞
@event.listens_for(async_engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """在每个新 SQLite 连接上设置 WAL 模式和超时"""
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

# Sync engine for migrations (use NullPool for SQLite)
sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    poolclass=NullPool if settings.DATABASE_URL_SYNC.startswith("sqlite") else None,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


async def init_db():
    """Initialize database tables"""
    logger.info("Initializing database...")
    async with async_engine.begin() as conn:
        # 启用 SQLite WAL 模式，允许并发读写
        if settings.DATABASE_URL.startswith("sqlite"):
            await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_legacy_columns)
    logger.info("Database initialized successfully")


def _add_missing_column(sync_conn, table_name: str, column_name: str, definition: str):
    """Add a missing column using the current database dialect."""
    logger.info("Adding missing %s column to %s table", column_name, table_name)
    sync_conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))



def _ensure_legacy_columns(sync_conn):
    """Patch legacy tables with newly introduced columns."""
    inspector = inspect(sync_conn)
    table_names = inspector.get_table_names()

    if "model_configs" in table_names:
        model_columns = {column["name"] for column in inspector.get_columns("model_configs")}
        if "model_type" not in model_columns:
            _add_missing_column(sync_conn, "model_configs", "model_type", "VARCHAR(50) NOT NULL DEFAULT 'chat'")

    if "questions" in table_names:
        question_columns = {column["name"] for column in inspector.get_columns("questions")}
        missing_question_columns = {
            "generation_status": "VARCHAR(30) NOT NULL DEFAULT 'generated'",
            "answer_status": "VARCHAR(20) NOT NULL DEFAULT 'pending'",
            "answer_error": "TEXT",
            "quality_score": "FLOAT",
            "metadata": "JSON",
        }
        for column_name, definition in missing_question_columns.items():
            if column_name not in question_columns:
                _add_missing_column(sync_conn, "questions", column_name, definition)

    if "eval_datasets" in table_names:
        eval_columns = {column["name"] for column in inspector.get_columns("eval_datasets")}
        missing_eval_columns = {
            "status": "VARCHAR(20) DEFAULT 'pending'",
            "question_count": "INTEGER DEFAULT 0",
        }
        for column_name, definition in missing_eval_columns.items():
            if column_name not in eval_columns:
                _add_missing_column(sync_conn, "eval_datasets", column_name, definition)

    if "tasks" in table_names:
        task_columns = {column["name"] for column in inspector.get_columns("tasks")}
        missing_task_columns = {
            "model_info": "TEXT",
            "detail": "TEXT",
            "language": "VARCHAR(20) DEFAULT 'zh-CN'",
            "total_count": "INTEGER DEFAULT 0",
            "completed_count": "INTEGER DEFAULT 0",
            "end_time": "VARCHAR(50)",
            "note": "TEXT",
        }
        for column_name, definition in missing_task_columns.items():
            if column_name not in task_columns:
                _add_missing_column(sync_conn, "tasks", column_name, definition)

    if "files" in table_names:
        file_columns = {column["name"] for column in inspector.get_columns("files")}
        missing_file_columns = {
            "field_schema": "JSON DEFAULT '[]'",
            "row_count": "INTEGER",
        }
        for column_name, definition in missing_file_columns.items():
            if column_name not in file_columns:
                _add_missing_column(sync_conn, "files", column_name, definition)

    # Add batch_id column to questions table
    if "questions" in table_names:
        question_columns = {column["name"] for column in inspector.get_columns("questions")}
        if "batch_id" not in question_columns:
            _add_missing_column(sync_conn, "questions", "batch_id", "VARCHAR(36)")
            # Create index for batch_id
            try:
                sync_conn.execute(text("CREATE INDEX ix_questions_batch_id ON questions (batch_id)"))
            except Exception:
                pass  # Index may already exist

    # Add extra_data column to projects table
    if "projects" in table_names:
        project_columns = {column["name"] for column in inspector.get_columns("projects")}
        if "extra_data" not in project_columns:
            _add_missing_column(sync_conn, "projects", "extra_data", "JSON DEFAULT '{}'")


async def close_db():
    """Close database connections"""
    logger.info("Closing database connections...")
    await async_engine.dispose()
    logger.info("Database connections closed")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions with automatic cleanup"""
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db() -> AsyncSession:
    """Dependency for getting database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database error in dependency: {str(e)}")
            await session.rollback()
            raise
        finally:
            await session.close()


# Import all models to register them with Base.metadata
# This ensures all models are loaded before create_all is called
from app.models.models import *  # noqa: F401, F403, E402
