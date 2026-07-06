"""
Files API Router
"""
import os
import asyncio
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, UploadFile, File, Query
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.response import ApiResponse, PaginatedResponse
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import ValidationException, NotFoundException
from app.core.crud import CRUDBase
from app.core.logging import log_success, log_failure
from app.models.models import File as FileModel
from app.models.models import Chunk, Question
from app.schemas.file import FileResponse, FileCreateSchema, FileUpdateSchema, UpdateFieldSchemaRequest
from app.services.field_analyzer import extract_field_schema_async, handle_missing_values

settings = get_settings()
router = APIRouter()

# Initialize CRUD
file_crud = CRUDBase(FileModel)


def get_project_raw_dir(project_id: str) -> Path:
    """获取项目的 raw 文件目录"""
    base_dir = Path("./YG-Datasets/data") / project_id / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def get_project_ready_dir(project_id: str) -> Path:
    """获取项目的 ready 文件目录（处理后的文件）"""
    base_dir = Path("./YG-Datasets/data") / project_id / "ready"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def get_file_type(filename: str) -> str:
    """Get file type from extension"""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    type_map = {
        'pdf': 'pdf',
        'docx': 'docx',
        'doc': 'docx',
        'xlsx': 'xlsx',
        'xls': 'xlsx',
        'csv': 'csv',
        'epub': 'epub',
        'md': 'md',
        'markdown': 'md',
        'txt': 'txt'
    }
    return type_map.get(ext, 'txt')


# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'xlsx', 'xls', 'csv', 'epub', 'md', 'txt'}


def validate_file(filename: str, file_size: int) -> None:
    """Validate file extension and size"""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationException(
            f"File type '{ext}' not allowed",
            field="file"
        )

    if file_size > settings.MAX_FILE_SIZE:
        raise ValidationException(
            f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE // (1024*1024)}MB",
            field="file"
        )


async def save_file_async(file: UploadFile, destination: Path) -> None:
    """Save uploaded file asynchronously"""
    content = await file.read()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: destination.write_bytes(content))


@router.post("/upload", response_model=ApiResponse)
async def upload_file(
    project_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Upload a file"""
    try:
        # Read file content for validation
        content = await file.read()
        file_size = len(content)

        # Validate file
        validate_file(file.filename, file_size)

        # Save file to disk - 使用项目 raw 目录
        safe_filename = f"{uuid4().hex[:8]}_{file.filename}"
        project_dir = get_project_raw_dir(str(project_id))
        file_path = project_dir / safe_filename

        # Write file asynchronously
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: file_path.write_bytes(content)
        )

        # Create file record
        db_file = FileModel(
            project_id=project_id,
            filename=file.filename,
            file_type=get_file_type(file.filename),
            file_path=str(file_path),
            size=file_size,
            status="pending"
        )
        db.add(db_file)
        await db.commit()
        await db.refresh(db_file)

        log_success(
            "文件上传成功",
            project_id=str(project_id),
            file_id=str(db_file.id),
            filename=file.filename,
            file_path=str(file_path)
        )

        return ApiResponse.ok(
            data={"id": str(db_file.id), "filename": db_file.filename, "status": db_file.status},
            message="File uploaded successfully"
        )
    except Exception as e:
        # 记录失败日志
        log_failure(
            "文件上传失败",
            project_id=str(project_id),
            filename=file.filename if 'file' in locals() else "unknown",
            error=str(e)
        )
        raise


@router.get("", response_model=ApiResponse)
async def list_files(
    project_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List files for a project"""
    skip = (page - 1) * page_size
    files, total = await file_crud.get_multi(
        db,
        skip=skip,
        limit=page_size,
        filters={"project_id": project_id},
        order_by="created_at",
        descending=True
    )

    file_responses = [FileResponse.model_validate(f) for f in files]
    return PaginatedResponse.ok(
        items=file_responses,
        page=page,
        page_size=page_size,
        total=total
    )


@router.get("/{file_id}", response_model=ApiResponse)
async def get_file(
    project_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get file by ID"""
    file = await file_crud.get(db, file_id)
    if not file or file.project_id != project_id:
        raise NotFoundException("File", file_id)

    return ApiResponse.ok(data=FileResponse.model_validate(file))


@router.get("/{file_id}/raw")
async def get_file_raw(
    project_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get raw file content for preview"""
    file = await file_crud.get(db, file_id)
    if not file or file.project_id != project_id:
        raise NotFoundException("File", file_id)

    # 读取 raw 目录中的原始文件
    raw_path = Path(file.file_path)

    if not raw_path.exists():
        raise NotFoundException("File not found on disk", file_id)

    # 根据文件类型返回不同的内容
    if file.file_type in ['txt', 'md', 'markdown', 'csv']:
        content = raw_path.read_text(encoding='utf-8')
        return PlainTextResponse(content=content, media_type="text/plain; charset=utf-8")
    elif file.file_type == 'pdf':
        # 返回PDF文件，浏览器可以内嵌显示
        import base64
        content = raw_path.read_bytes()
        b64 = base64.b64encode(content).decode('utf-8')
        return PlainTextResponse(
            content=f"data:application/pdf;base64,{b64}",
            media_type="text/plain"
        )
    else:
        # 其他二进制文件，返回文件信息
        size_mb = file.size / (1024 * 1024)
        content = f"""[二进制文件]

文件名: {file.filename}
文件类型: {file.file_type.upper()}
文件大小: {size_mb:.2f} MB

此文件为二进制格式，请下载后查看。
"""
        return PlainTextResponse(content=content, media_type="text/plain; charset=utf-8")


@router.get("/{file_id}/content")
async def get_file_content(
    project_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db)
) -> PlainTextResponse:
    """Get file content (markdown)"""
    file = await file_crud.get(db, file_id)
    if not file or file.project_id != project_id:
        raise NotFoundException("File", file_id)

    # 读取 ready 目录中的 markdown 文件
    ready_path = Path("./YG-Datasets/data") / str(project_id) / "ready" / f"{file_id}.md"

    if ready_path.exists():
        content = ready_path.read_text(encoding='utf-8')
        return PlainTextResponse(content=content, media_type="text/plain; charset=utf-8")
    else:
        raise NotFoundException("File content", file_id)


@router.delete("/{file_id}", response_model=ApiResponse)
async def delete_file(
    project_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete file and all related data (markdown, chunks, questions)"""
    file = await file_crud.get(db, file_id)
    if not file or file.project_id != project_id:
        raise NotFoundException("File", file_id)

    # Delete related chunks and their questions (explicit deletion for safety)
    chunks_result = await db.execute(
        select(Chunk).where(Chunk.file_id == file_id)
    )
    chunks = chunks_result.scalars().all()
    for chunk in chunks:
        # Delete questions related to this chunk
        questions_result = await db.execute(
            select(Question).where(Question.chunk_id == chunk.id)
        )
        questions = questions_result.scalars().all()
        for question in questions:
            await db.delete(question)
        # Delete chunk
        await db.delete(chunk)

    loop = asyncio.get_event_loop()

    async def remove_path(path: Path) -> None:
        if path.exists() and path.is_file():
            await loop.run_in_executor(None, os.remove, str(path))

    # Delete source file from raw directory.
    # Legacy records may have file.file_path incorrectly overwritten to the ready markdown path,
    # so we delete both the recorded path (when it points to raw) and raw-dir filename matches.
    if file.file_path:
        file_path = Path(file.file_path)
        if file_path.exists() and file_path.is_file() and file_path.parent.name == "raw":
            await remove_path(file_path)

    raw_dir = Path("./YG-Datasets/data") / str(project_id) / "raw"
    if raw_dir.exists():
        raw_candidates = list(raw_dir.glob(f"*_{file.filename}"))
        for raw_file in raw_candidates:
            await remove_path(raw_file)

    # Delete file from ready directory (processed markdown) - try both naming conventions
    ready_dir = Path("./YG-Datasets/data") / str(project_id) / "ready"
    if ready_dir.exists():
        # Try file_id.md (from upload process)
        ready_path = ready_dir / f"{file_id}.md"
        if ready_path.exists():
            await remove_path(ready_path)
        # Try file_id_filename.md (from split process)
        for md_file in ready_dir.glob(f"{file_id}_*.md"):
            await remove_path(md_file)

    await file_crud.delete(db, file_id)
    await db.commit()
    return ApiResponse.ok(message="File deleted successfully")


@router.get("/{file_id}/download")
async def download_file(
    project_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db)
) -> FileResponse:
    """Download file"""
    file = await file_crud.get(db, file_id)
    if not file or file.project_id != project_id:
        raise NotFoundException("File", file_id)

    if not file.file_path or not os.path.exists(file.file_path):
        raise ValidationException("File not found on disk", field="file")

    return FileResponse(
        path=file.file_path,
        filename=file.filename,
        media_type=f"application/{file.file_type}"
    )


async def _auto_create_structured_chunks(db: AsyncSession, file: FileModel) -> None:
    """结构化文件提取字段后，自动按行创建 chunks。

    每行数据格式为 "字段名: 值"，与 QA 生成模板模式的解析逻辑兼容。
    """
    import pandas as pd

    if file.file_type not in ("xlsx", "xls", "csv") or not file.file_path:
        return

    file_path = Path(file.file_path)
    if not file_path.exists():
        return

    try:
        # 读取数据
        if file.file_type == "csv":
            df = None
            for encoding in ["utf-8", "gbk", "gb2312", "utf-8-sig", "latin1"]:
                try:
                    df = pd.read_csv(str(file_path), encoding=encoding)
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            if df is None:
                df = pd.read_csv(str(file_path), encoding="utf-8", errors="ignore")
        else:
            # Excel：读取第一个 sheet
            df = pd.read_excel(str(file_path), sheet_name=0)

        if df is None or df.empty:
            return

        # 应用缺失值处理策略（根据 field_schema 中的 missing_strategy）
        if file.field_schema:
            df = handle_missing_values(df, file.field_schema)

        # 删除旧 chunks（如果存在）
        from sqlalchemy import delete
        await db.execute(
            delete(Chunk).where(Chunk.file_id == file.id)
        )

        # 按行创建 chunk
        col_names = [str(c).strip() for c in df.columns]
        for idx, (_, row) in enumerate(df.iterrows()):
            lines = []
            for col_name in col_names:
                val = row.get(col_name)
                if pd.notna(val):
                    lines.append(f"{col_name}: {str(val).strip()}")
            if not lines:
                continue

            chunk_content = "\n".join(lines)
            db_chunk = Chunk(
                project_id=file.project_id,
                file_id=file.id,
                name=f"行 {idx + 1}",
                content=chunk_content,
                summary=f"数据行 {idx + 1}",
                word_count=len(chunk_content.split()),
            )
            db.add(db_chunk)

        await db.flush()

        log_success(
            "结构化文件自动切片完成",
            file_id=str(file.id),
            filename=file.filename,
            chunk_count=len(df),
        )
    except Exception as e:
        log_failure(
            "结构化文件自动切片失败",
            file_id=str(file.id),
            filename=file.filename,
            error=str(e),
        )


@router.post("/{file_id}/extract-fields", response_model=ApiResponse)
async def extract_fields(
    project_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Auto-extract field metadata from a structured file (xlsx/xls/csv)"""
    file = await file_crud.get(db, file_id)
    if not file or file.project_id != project_id:
        raise NotFoundException("File", file_id)

    if file.file_type not in ("xlsx", "xls", "csv"):
        raise ValidationException("仅支持 Excel/CSV 文件的字段提取", field="file_type")

    if not file.file_path or not os.path.exists(file.file_path):
        raise ValidationException("文件不存在于磁盘", field="file")

    try:
        result = await extract_field_schema_async(file.file_path, file.file_type)

        # 存储到 file 记录
        file.field_schema = result.get("fields", [])
        file.row_count = result.get("total_rows", 0)

        # 结构化文件：提取字段后自动按行创建 chunks，设为已处理
        await _auto_create_structured_chunks(db, file)

        file.status = "completed"
        await db.commit()
        await db.refresh(file)

        log_success(
            "字段提取成功",
            project_id=str(project_id),
            file_id=str(file_id),
            field_count=len(result.get("fields", [])),
            total_rows=result.get("total_rows", 0)
        )

        return ApiResponse.ok(
            data=result,
            message="字段提取成功"
        )
    except Exception as e:
        log_failure(
            "字段提取失败",
            project_id=str(project_id),
            file_id=str(file_id),
            error=str(e)
        )
        raise


@router.put("/{file_id}/field-schema", response_model=ApiResponse)
async def update_field_schema(
    project_id: UUID,
    file_id: UUID,
    request: UpdateFieldSchemaRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update field role configuration for a structured file"""
    file = await file_crud.get(db, file_id)
    if not file or file.project_id != project_id:
        raise NotFoundException("File", file_id)

    # 合并用户配置到现有 field_schema
    current_schema = file.field_schema or []

    # 构建 name -> 新配置 的映射
    update_map = {}
    for field in request.fields:
        update_map[field.name] = {
            "role": field.role,
            "desensitize": field.desensitize,
            "missing_strategy": getattr(field, "missing_strategy", "ignore"),
            "fill_value": getattr(field, "fill_value", None),
        }

    # 更新已有字段
    updated_schema = []
    for existing in current_schema:
        name = existing.get("name", "")
        if name in update_map:
            updated = {**existing}
            updated["role"] = update_map[name]["role"]
            updated["desensitize"] = update_map[name]["desensitize"]
            updated["missing_strategy"] = update_map[name]["missing_strategy"]
            if update_map[name]["fill_value"] is not None:
                updated["fill_value"] = update_map[name]["fill_value"]
            updated_schema.append(updated)
        else:
            updated_schema.append(existing)

    # 添加新字段（如果 request 中有 current_schema 没有的）
    existing_names = {f.get("name", "") for f in current_schema}
    for field in request.fields:
        if field.name not in existing_names:
            updated_schema.append({
                "name": field.name,
                "type": field.type,
                "sample": field.sample,
                "missing_rate": field.missing_rate,
                "role": field.role,
                "desensitize": field.desensitize,
                "missing_strategy": getattr(field, "missing_strategy", "ignore"),
                "fill_value": getattr(field, "fill_value", None),
            })

    file.field_schema = updated_schema

    # 结构化文件：字段配置更新后重新生成 chunks（应用缺失值处理策略）
    chunks_regenerated = False
    if file.file_type in ("xlsx", "xls", "csv"):
        # 检查是否已有 chunks
        from sqlalchemy import func as sa_func
        existing_chunks_count = await db.scalar(
            select(sa_func.count(Chunk.id)).where(Chunk.file_id == file.id)
        )
        # 检查是否有非 ignore 的缺失值策略
        has_active_strategy = any(
            f.get("missing_strategy", "ignore") != "ignore"
            for f in updated_schema
        )
        # 有活跃策略时，始终重新生成 chunks；否则仅在没有 chunks 时创建
        if has_active_strategy or not existing_chunks_count:
            await _auto_create_structured_chunks(db, file)
            chunks_regenerated = True
        file.status = "completed"

    await db.commit()
    await db.refresh(file)

    log_success(
        "字段配置更新成功",
        project_id=str(project_id),
        file_id=str(file_id),
        field_count=len(updated_schema)
    )

    return ApiResponse.ok(
        data={
            "field_schema": updated_schema,
            "chunks_regenerated": chunks_regenerated,
        },
        message="字段配置已更新" + ("，分片已重建" if chunks_regenerated else "")
    )
