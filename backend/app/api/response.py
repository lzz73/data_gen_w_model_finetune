"""
API Response Wrapper
统一 API 响应格式
"""
from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应格式"""
    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    message: str = "Success"
    data: Optional[T] = None
    error: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def ok(cls, data: T = None, message: str = "Success") -> "ApiResponse[T]":
        """成功响应"""
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, message: str, error: dict = None) -> "ApiResponse[None]":
        """失败响应"""
        return cls(success=False, message=message, error=error)


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应格式"""
    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    message: str = "Success"
    data: List[T] = []
    pagination: dict = Field(default_factory=lambda: {
        "page": 1,
        "page_size": 20,
        "total": 0,
        "total_pages": 0
    })

    @classmethod
    def ok(
        cls,
        items: List[T],
        page: int = 1,
        page_size: int = 20,
        total: int = 0
    ) -> "PaginatedResponse[T]":
        """创建分页响应"""
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            success=True,
            data=items,
            pagination={
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages
            }
        )


class ErrorDetail(BaseModel):
    """错误详情"""
    code: str
    message: str
    details: Optional[dict] = None
    field: Optional[str] = None
