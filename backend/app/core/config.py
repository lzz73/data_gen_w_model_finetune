"""
Application Configuration
"""

from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application settings"""

    # App
    APP_NAME: str = "远光微调平台"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins"
    )

    # Database - 使用 SQLite 进行开发/测试
    # 生产环境可切换为 PostgreSQL
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./ygdataset.db",
        description="Database connection URL (sqlite+aiosqlite:// or postgresql+asyncpg://)"
    )
    DATABASE_URL_SYNC: str = Field(
        default="sqlite:///./ygdataset.db",
        description="Synchronous database connection URL"
    )

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB

    # Crawler
    CRAWL_TIMEOUT: int = Field(
        default=30,
        description="HTTP request timeout for web crawler (seconds)"
    )
    CRAWL_MAX_PAGES: int = Field(
        default=50,
        description="Maximum number of pages the crawler can fetch"
    )

    # LLM Settings
    DEFAULT_MODEL_PROVIDER: str = "openai"
    DEFAULT_MODEL_NAME: str = "gpt-4o-mini"

    # Security
    SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for JWT and other security operations"
    )
    API_KEY_HEADER: str = "X-API-Key"

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Logging
    LOG_LEVEL: str = "INFO"

    @field_validator("MAX_FILE_SIZE")
    @classmethod
    def validate_max_file_size(cls, v: int) -> int:
        """Validate max file size (max 500MB)"""
        if v > 500 * 1024 * 1024:
            return 500 * 1024 * 1024
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings"""
    return Settings()


# Create global settings instance
settings = get_settings()
