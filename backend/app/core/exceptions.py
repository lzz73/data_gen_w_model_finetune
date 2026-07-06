"""
Custom Exceptions
自定义异常类
"""
from typing import Any, Optional


class AppException(Exception):
    """基础应用异常"""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[dict] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class NotFoundException(AppException):
    """资源未找到异常"""

    def __init__(self, resource: str, resource_id: Any = None):
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} with id '{resource_id}' not found"
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=404
        )


class ValidationException(AppException):
    """验证异常"""

    def __init__(self, message: str, field: str = None, details: dict = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=422,
            details={"field": field, **(details or {})}
        )


class DuplicateException(AppException):
    """重复资源异常"""

    def __init__(self, resource: str, field: str = None):
        resource_cn = {
            "Project": "项目",
        }.get(resource, resource)

        if field:
            field_cn = {
                "name": "名称",
            }.get(field, field)
            message = f"{resource_cn}{field_cn}已存在"
        else:
            message = f"{resource_cn}已存在"
        super().__init__(
            message=message,
            code="DUPLICATE",
            status_code=409
        )


class UnauthorizedException(AppException):
    """未授权异常"""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=401
        )


class ForbiddenException(AppException):
    """禁止访问异常"""

    def __init__(self, message: str = "Forbidden"):
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=403
        )


class RateLimitException(AppException):
    """速率限制异常"""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(
            message=message,
            code="RATE_LIMIT",
            status_code=429
        )


class FileProcessingException(AppException):
    """文件处理异常"""

    def __init__(self, message: str, file_name: str = None):
        details = {"file_name": file_name} if file_name else None
        super().__init__(
            message=message,
            code="FILE_PROCESSING_ERROR",
            status_code=422,
            details=details
        )


class DatabaseException(AppException):
    """数据库异常"""

    def __init__(self, message: str = "Database operation failed"):
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            status_code=500
        )
