"""
Database Connection API Router — 数据库直连
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import ApiResponse
from app.core.database import get_db, AsyncSessionLocal
from app.core.crud import CRUDBase
from app.models.models import File as FileModel

router = APIRouter()
logger = logging.getLogger("yg_dataset.database")

file_crud = CRUDBase(FileModel)


class DBConnectRequest(BaseModel):
    """数据库连接请求"""
    db_type: str = Field(..., description="数据库类型: mysql, postgresql, sqlite")
    host: str = Field("", description="主机地址")
    port: Optional[int] = Field(None, description="端口号")
    user: str = Field("", description="用户名")
    password: str = Field("", description="密码")
    database: str = Field(..., description="数据库名（SQLite 为文件路径）")


class DBImportRequest(BaseModel):
    """数据库表导入请求"""
    db_type: str = Field(..., description="数据库类型")
    host: str = Field("", description="主机地址")
    port: Optional[int] = Field(None, description="端口号")
    user: str = Field("", description="用户名")
    password: str = Field("", description="密码")
    database: str = Field(..., description="数据库名")
    table_name: str = Field(..., description="要导入的表名")
    project_id: str = Field(..., description="目标项目 ID")


@router.post("/connect", response_model=ApiResponse)
async def connect_database(
    request: DBConnectRequest,
    db: AsyncSession = Depends(get_db),
):
    """测试数据库连接并获取表列表"""
    from app.services.db_connector import build_db_url, test_connection, list_tables

    try:
        db_url = build_db_url(
            db_type=request.db_type,
            host=request.host,
            port=request.port,
            user=request.user,
            password=request.password,
            database=request.database,
        )
    except ValueError as e:
        return ApiResponse.fail(message=str(e))

    # 测试连接
    conn_result = await asyncio.get_event_loop().run_in_executor(
        None, test_connection, db_url
    )
    if not conn_result["success"]:
        return ApiResponse.fail(message=f"连接失败: {conn_result['message']}")

    # 获取表列表
    try:
        tables = await asyncio.get_event_loop().run_in_executor(
            None, list_tables, db_url
        )
    except Exception as e:
        return ApiResponse.fail(message=f"获取表列表失败: {str(e)}")

    return ApiResponse.ok(data={
        "connected": True,
        "tables": tables,
    })


@router.post("/import", response_model=ApiResponse)
async def import_table(
    request: DBImportRequest,
    db: AsyncSession = Depends(get_db),
):
    """从数据库导入表到项目"""
    from app.services.db_connector import build_db_url, extract_table_to_csv

    try:
        project_id = UUID(request.project_id)
    except ValueError:
        return ApiResponse.fail(message=f"无效的项目 ID: {request.project_id}")

    try:
        db_url = build_db_url(
            db_type=request.db_type,
            host=request.host,
            port=request.port,
            user=request.user,
            password=request.password,
            database=request.database,
        )
    except ValueError as e:
        return ApiResponse.fail(message=str(e))

    # 提取数据到 CSV
    raw_dir = str(Path("./YG-Datasets/data") / str(project_id) / "raw")
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            extract_table_to_csv,
            db_url,
            request.table_name,
            raw_dir,
        )
    except Exception as e:
        return ApiResponse.fail(message=f"数据提取失败: {str(e)}")

    if not result["file_path"] or result["row_count"] == 0:
        return ApiResponse.fail(message="表为空或无法读取数据")

    # 创建 File 记录
    csv_path = Path(result["file_path"])
    db_file = FileModel(
        project_id=project_id,
        filename=f"{request.table_name}.csv",
        file_type="csv",
        file_path=str(csv_path),
        size=csv_path.stat().st_size if csv_path.exists() else 0,
        status="completed",
        field_schema=result.get("columns", []),
        row_count=result["row_count"],
    )
    db.add(db_file)
    await db.commit()
    await db.refresh(db_file)

    logger.info(f"数据库表导入成功: {request.table_name} -> {db_file.id}")
    return ApiResponse.ok(
        data={"file_id": str(db_file.id), "row_count": result["row_count"]},
        message=f"成功导入表 {request.table_name}（{result['row_count']} 行）",
    )
