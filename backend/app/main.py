"""
YG-Dataset Backend Application
FastAPI-based API server for dataset generation platform
"""

import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.exc import SQLAlchemyError
import os

# 将项目根目录加入 sys.path，使后端能导入 llamafactory
# __file__ = backend/app/main.py → .parent.parent.parent = platform_demo/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.api.v1 import api_router
from app.api.response import ApiResponse
from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.exceptions import AppException
from app.core.logging import logger

# Import all models to register them with Base.metadata
from app.models.models import *  # noqa: F401, F403


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to each request"""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Add request ID to response headers
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """Middleware to measure request processing time"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Log request
        logger.info(f"→ {request.method} {request.url.path}")

        response = await call_next(request)

        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)

        # Log response
        logger.info(f"← {request.method} {request.url.path} | Status: {response.status_code} | Time: {process_time:.3f}s")

        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting 远光微调平台 application...")
    await init_db()
    logger.info("Database initialized successfully")

    # 预加载模型列表（用于训练模块）
    try:
        from app.api.v1.training import init_model_cache
        init_model_cache()
        logger.info("Model cache initialized")
    except Exception as e:
        logger.warning(f"Model cache initialization failed: {e}")

    # 重置重启时残留的活跃任务（running/pending/cancelling → cancelled）
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.models import Task
        from sqlalchemy import update
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(Task)
                .where(Task.status.in_(["running", "pending", "cancelling"]))
                .values(status="cancelled", error="服务重启，任务已自动取消")
            )
            await db.commit()
            if result.rowcount > 0:
                logger.info(f"已重置 {result.rowcount} 个残留任务为 cancelled")
    except Exception as e:
        logger.warning(f"重置残留任务失败（非致命）: {e}")

    yield
    # Shutdown
    logger.info("Shutting down YG-Dataset application...")
    await close_db()
    logger.info("Database connections closed")


app = FastAPI(
    title="远光微调平台 API",
    description="远光大模型微调平台 - 数据治理与微调训练 API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


# 禁用 /docs、/redoc、/openapi.json，访问时返回 404
@app.get("/docs", include_in_schema=False)
@app.get("/redoc", include_in_schema=False)
@app.get("/openapi.json", include_in_schema=False)
async def block_api_docs():
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404, content={"detail": "Not Found"})

# Add custom middleware (order matters: last added = first executed)
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestIDMiddleware)

# CORS - Configure properly for production
# For development, you can use ["*"] but for production, specify exact origins
ALLOWED_ORIGINS = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle custom application exceptions"""
    logger.warning(f"App exception: {exc.message} | Code: {exc.code}")
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse.fail(
            message=exc.message,
            error={"code": exc.code, "details": exc.details}
        ).model_dump(mode='json')
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation exceptions"""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    logger.warning(f"Validation error: {errors}")
    return JSONResponse(
        status_code=422,
        content=ApiResponse.fail(
            message="Validation error",
            error={"code": "VALIDATION_ERROR", "details": {"errors": errors}}
        ).model_dump(mode='json')
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    """Handle database exceptions"""
    logger.error(f"Database error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ApiResponse.fail(
            message="Database operation failed",
            error={"code": "DATABASE_ERROR"}
        ).model_dump(mode='json')
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unhandled exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ApiResponse.fail(
            message="Internal server error",
            error={"code": "INTERNAL_ERROR"}
        ).model_dump(mode='json')
    )


# Include API routes
app.include_router(api_router, prefix="/api/v1")

# Serve frontend static files (point to ../../frontend/dist)
FRONTEND_DIST = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))

if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/")
    async def serve_root():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # SPA fallback: return index.html for client-side routing
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return ApiResponse.ok(
        data={"status": "healthy", "version": "1.0.0"},
        message="Service is running"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
    )
