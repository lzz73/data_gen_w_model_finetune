"""
Chunks API Router
"""
import asyncio
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.response import ApiResponse, PaginatedResponse
from app.core.database import get_db, AsyncSessionLocal
from app.core.exceptions import NotFoundException
from app.core.crud import CRUDBase
from app.core.logging import log_success, log_failure
from app.models.models import Chunk, File, ModelConfig, Project
from app.schemas.chunk import ChunkResponse
from app.schemas.chunk import ChunkCreateSchema, ChunkUpdateSchema
from app.services.text_splitter.splitter import get_splitter
from markitdown import MarkItDown
from .excel_pase import excel_parse

router = APIRouter()

# Initialize CRUD
chunk_crud = CRUDBase(Chunk)

# Initialize markitdown
markitdown = MarkItDown()


def get_project_ready_dir(project_id: str) -> Path:
    """获取项目的 ready 文件目录"""
    base_dir = Path("./YG-Datasets/data") / project_id / "ready"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


class SplitRequest(BaseModel):
    """Request model for splitting text"""
    file_id: UUID
    method: str = "recursive"
    chunk_size: int = Field(500, ge=50, le=5000)
    overlap: int = Field(50, ge=0, le=500)
    separator: Optional[str] = None
    # PDF 处理策略 (仅对 PDF 文件有效)
    pdf_strategy: Optional[str] = Field("default", description="PDF 处理策略：default, vision")
    # VLM 模型配置 (用于 vision 策略)
    vlm_model_name: Optional[str] = Field(None, description="VLM 模型名称")
    vlm_api_key: Optional[str] = Field(None, description="VLM API Key")
    vlm_api_base: Optional[str] = Field(None, description="VLM API Base URL")


async def get_default_embedding_config(db, project_id: UUID) -> Tuple[str, str, str, str]:
    """
    获取项目的默认embedding模型配置

    返回: (provider, api_key, api_base, model_name)
    """
    try:
        result = await db.execute(
            select(ModelConfig).where(
                ModelConfig.project_id == project_id,
                ModelConfig.model_type == "embedding",
                ModelConfig.is_default == "true"
            )
        )
        model_config = result.scalar_one_or_none()

        if not model_config:
            result = await db.execute(
                select(ModelConfig).where(
                    ModelConfig.project_id.is_(None),
                    ModelConfig.model_type == "embedding",
                    ModelConfig.is_default == "true"
                )
            )
            model_config = result.scalar_one_or_none()

        if model_config:
            return (
                model_config.provider,
                model_config.api_key or "",
                model_config.api_base or "",
                model_config.model_name or ""
            )
        else:
            return ("", "", "", "")
    except Exception as e:
        print(f"Error fetching default embedding config: {e}")
        return ("", "", "", "")


async def get_default_model_config(db, project_id: UUID, model_type: str) -> Optional[ModelConfig]:
    """
    获取指定类型的默认模型配置

    先查项目级别，再查全局（project_id 为 None）
    """
    try:
        # 先查项目级别
        result = await db.execute(
            select(ModelConfig).where(
                ModelConfig.project_id == project_id,
                ModelConfig.model_type == model_type,
                ModelConfig.is_default == "true"
            )
        )
        model_config = result.scalar_one_or_none()

        if not model_config:
            # 再查全局
            result = await db.execute(
                select(ModelConfig).where(
                    ModelConfig.project_id.is_(None),
                    ModelConfig.model_type == model_type,
                    ModelConfig.is_default == "true"
                )
            )
            model_config = result.scalar_one_or_none()

        return model_config
    except Exception as e:
        print(f"Error fetching default {model_type} model config: {e}")
        return None


async def process_file_by_type(
    file: File,
    pdf_strategy: str = 'default',
    vlm_model_info: Optional[dict] = None,
    embedding_config: Optional[dict] = None,
    split_method: str = None,
    preprocessing_config: Optional[dict] = None,
) -> str:
    """
    Process file based on its type, convert to markdown

    参考 easy-dataset-main 的文件处理流程:
    1. PDF: 支持多种策略 (default, vision)
    2. DOCX: mammoth + markdownify
    3. XLSX: 自定义 Excel 解析（合并单元格 + embedding 边界检测）
    4. MD/TXT: 直接读取
    5. 其他：MarkItDown

    Args:
        file: File 对象
        pdf_strategy: PDF 处理策略 ('default', 'vision')
        vlm_model_info: VLM 模型配置 (用于 vision 策略)
        embedding_config: Embedding 配置 (用于 Excel 解析)
        split_method: 分割方法 (用于决定 Excel 输出格式)
        preprocessing_config: 预处理配置 (header_threshold, footer_threshold, custom_header_patterns 等)
    """
    if not file.file_path:
        raise NotFoundException("File", file.id)

    file_path_obj = Path(file.file_path) if isinstance(file.file_path, str) else file.file_path

    file_type = file.file_type.lower()
    output_path = file_path_obj.with_suffix('.md')

    # Excel 处理：根据分割方法决定输出格式
    if file_type in ['xlsx', 'xls']:
        loop = asyncio.get_event_loop()
        # markdown_structure 使用 Markdown 表格输出（每个工作表一个切片，返回列表）
        # 其他使用结构化文本（返回字符串）
        output_format = 'markdown' if split_method == 'markdown_structure' else 'structured'
        content = await loop.run_in_executor(
            None,
            lambda: excel_parse(str(file_path_obj), embedding_config, output_format)
        )
        return content

    # PDF 处理
    if file_type == 'pdf':
        from app.services.file_processor import process_file
        from app.services.file_processor.pdf.default import convert_pdf_to_markdown

        # 如果有预处理配置中的页眉页脚阈值，直接调用带阈值的转换
        header_threshold = (preprocessing_config or {}).get('header_threshold', 0)
        footer_threshold = (preprocessing_config or {}).get('footer_threshold', 100)

        if header_threshold > 0 or footer_threshold < 100:
            # 有坐标过滤需求，使用带阈值的 pdfplumber 路径
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None,
                lambda: convert_pdf_to_markdown(
                    str(file_path_obj),
                    header_threshold=header_threshold,
                    footer_threshold=footer_threshold,
                )
            )
            # 写入输出文件
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(content, encoding='utf-8')
            return content

        # 无坐标过滤，走标准流程
        result = await process_file(
            str(file_path_obj),
            str(output_path),
            file_type='pdf',
            strategy=pdf_strategy,
            model_info=vlm_model_info
        )

        if result['success']:
            return Path(output_path).read_text(encoding='utf-8')
        else:
            raise Exception(f"PDF 转换失败：{result.get('error', 'Unknown error')}")

    # DOCX 处理
    elif file_type in ['docx', 'doc']:
        from app.services.file_processor import process_file

        result = await process_file(
            str(file_path_obj),
            str(output_path),
            file_type='docx'
        )

        if result['success']:
            return Path(output_path).read_text(encoding='utf-8')
        else:
            raise Exception(f"DOCX 转换失败：{result.get('error', 'Unknown error')}")

    # MD/TXT 直接读取
    elif file_type in ['md', 'txt']:
        ready_dir = Path("./YG-Datasets/data") / str(file.project_id) / "ready"
        ready_md_path = ready_dir / f"{file.id}.md"

        if ready_md_path.exists():
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None,
                lambda: open(ready_md_path, 'r', encoding='utf-8').read()
            )
            return content

        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(
            None,
            lambda: open(file_path_obj, 'r', encoding='utf-8').read()
        )
        return content

    # 其他类型使用 MarkItDown
    else:
        markitdown = MarkItDown()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: markitdown.convert(str(file_path_obj))
        )
        return result.text_content


async def process_split_async(
    project_id: UUID,
    request: SplitRequest,
):
    """Run chunk splitting in background."""
    async with AsyncSessionLocal() as db:
        file = None
        try:
            log_success(
                "[DEBUG] process_split_async 开始执行",
                project_id=str(project_id),
                file_id=str(request.file_id),
                method=request.method
            )

            result = await db.execute(
                select(File).where(File.id == request.file_id, File.project_id == project_id)
            )
            file = result.scalar_one_or_none()
            if not file:
                log_failure(
                    "[DEBUG] 文件未找到",
                    project_id=str(project_id),
                    file_id=str(request.file_id)
                )
                return

            log_success(
                "[DEBUG] 文件查询成功",
                file_id=str(file.id),
                filename=file.filename,
                file_type=file.file_type
            )

            # 准备 VLM 模型配置 (用于 PDF vision 策略)
            vlm_model_info = None
            if request.pdf_strategy == 'vision':
                if request.vlm_model_name and request.vlm_api_key:
                    vlm_model_info = {
                        'model_name': request.vlm_model_name,
                        'api_key': request.vlm_api_key,
                        'api_base': request.vlm_api_base or 'https://api.openai.com/v1'
                    }
                else:
                    raise Exception("使用 vision 策略需要配置 VLM 模型 (model_name, api_key)")

            # 获取默认embedding配置（用于Excel解析等）
            provider, api_key, api_base, model_name = await get_default_embedding_config(db, project_id)
            embedding_config = None
            if api_key:
                embedding_config = {
                    "provider": provider or "openai",
                    "api_key": api_key,
                    "base_url": api_base or "https://api.minimax.chat/v1",
                    "model": model_name or "text-embedding-3-small"
                }

            # 获取默认 chat 模型配置（用于 LLM 摘要生成）
            llm_config = None
            chat_model = await get_default_model_config(db, project_id, "chat")
            if chat_model and chat_model.api_key:
                llm_config = {
                    "api_key": chat_model.api_key,
                    "api_base": chat_model.api_base,
                    "model_name": chat_model.model_name,
                }

            # 获取项目预处理配置
            project_result = await db.execute(select(Project).where(Project.id == project_id))
            project = project_result.scalar_one_or_none()
            preprocessing_config = (project.extra_data or {}).get('preprocessing_config') if project else None

            # 转换文件为 Markdown
            log_success(
                "[DEBUG] 开始转换文件为 Markdown",
                file_type=file.file_type,
                pdf_strategy=request.pdf_strategy or 'default'
            )

            text = await process_file_by_type(
                file,
                pdf_strategy=request.pdf_strategy or 'default',
                vlm_model_info=vlm_model_info,
                embedding_config=embedding_config,
                split_method=request.method,
                preprocessing_config=preprocessing_config,
            )

            log_success(
                "[DEBUG] 文件转换成功",
                text_length=len(text) if isinstance(text, str) else len(str(text))
            )

            # Excel markdown 模式：每个工作表作为一个完整的切片，跳过分割器
            if file.file_type in ['xlsx', 'xls'] and request.method == 'markdown_structure' and isinstance(text, list):
                # 直接使用预切分的切片列表
                split_results = []
                for i, sheet_content in enumerate(text):
                    split_results.append({
                        "index": i,
                        "content": sheet_content,
                        "word_count": len(sheet_content.split()),
                        "name": f"Sheet {i + 1}"
                    })
                log_success(
                    "[DEBUG] Excel Markdown 模式 - 按工作表切分",
                    sheet_count=len(split_results)
                )
            else:
                # 准备分割器参数
                kwargs = {"chunk_size": request.chunk_size, "overlap": request.overlap}
                if request.method == "custom" and request.separator:
                    kwargs["separator"] = request.separator

                # Excel 文件使用特殊处理：已经是结构化文本（每行一条数据）
                # 但仅当用户明确选择 excel_structured 方法时才使用
                if file.file_type in ['xlsx', 'xls'] and file.file_path and request.method == 'excel_structured':
                    # 使用 excel_structured 分割器，按行分割，每条结构化数据保持完整
                    # 传递文件路径，让分割器直接从 Excel 读取并按行切分
                    splitter = get_splitter(
                        "excel_structured",
                        chunk_size=request.chunk_size,
                        overlap=request.overlap,
                        file_path=file.file_path
                    )
                else:
                    # markdown_structure 纯按标题结构切分，不接受 chunk_size/overlap
                    if request.method == "markdown_structure":
                        kwargs = {}
                        # 传递自定义页眉页脚关键词
                        if preprocessing_config:
                            if preprocessing_config.get("custom_header_patterns"):
                                kwargs["custom_header_patterns"] = preprocessing_config["custom_header_patterns"]
                            if preprocessing_config.get("custom_footer_patterns"):
                                kwargs["custom_footer_patterns"] = preprocessing_config["custom_footer_patterns"]
                    # semantic_embedding 纯语义驱动，不需要 chunk_size/overlap
                    if request.method == "semantic_embedding":
                        kwargs = {}
                    # 传递 LLM 配置给分割器（用于摘要生成）
                    if llm_config:
                        kwargs["llm_config"] = llm_config
                    # 语义嵌入分割需要 embedding 配置
                    if request.method == "semantic_embedding" and embedding_config:
                        kwargs["embedding_provider_type"] = embedding_config.get("provider", "openai")
                        kwargs["embedding_api_key"] = embedding_config.get("api_key", "")
                        kwargs["embedding_base_url"] = embedding_config.get("base_url", "")
                        kwargs["embedding_model"] = embedding_config.get("model", "")
                    elif request.method == "semantic_embedding" and not embedding_config:
                        raise Exception("语义嵌入分割需要先配置 Embedding 模型，请在「模型配置」中添加 embedding 类型模型并设为默认")

                    log_success(
                        "[DEBUG] 准备创建分割器",
                        method=request.method,
                        kwargs=kwargs
                    )

                    try:
                        splitter = get_splitter(request.method, **kwargs)
                        log_success(
                            "[DEBUG] 分割器创建成功",
                            splitter_type=type(splitter).__name__
                        )
                    except Exception as splitter_error:
                        log_failure(
                            "[DEBUG] 分割器创建失败",
                            error=str(splitter_error),
                            method=request.method
                        )
                        # 重新抛出异常，让前端能看到错误信息
                        raise Exception(f"分割器创建失败：{str(splitter_error)}")

                try:
                    split_results = splitter.split(text)
                    log_success(
                        "[DEBUG] 分割完成",
                        chunk_count=len(split_results)
                    )
                except Exception as split_error:
                    log_failure(
                        "[DEBUG] 分割执行失败",
                        error=str(split_error),
                        text_length=len(text) if isinstance(text, str) else len(str(text)),
                        method=request.method
                    )
                    # 重新抛出异常，让前端能看到错误信息
                    raise Exception(f"分割执行失败：{str(split_error)}")

            await db.execute(
                Chunk.__table__.delete().where(
                    Chunk.project_id == project_id,
                    Chunk.file_id == file.id
                )
            )

            chunks = []
            # 脱敏引擎：如果项目配置了敏感信息脱敏，在切片入库前执行
            from app.services.desensitize import desensitize_chunk
            project_extra = project.extra_data if project else {}
            sensitive_config = (project_extra or {}).get('sensitive_rules', {})
            desensitize_enabled = sensitive_config.get('enabled', False) if sensitive_config else False

            # 获取 chat 模型配置（NER 可能需要）
            ner_model = None
            if desensitize_enabled and sensitive_config.get('ner_enabled', False):
                model_result = await db.execute(
                    select(ModelConfig).where(
                        ModelConfig.project_id.is_(None),
                        ModelConfig.model_type.in_(["chat", "vlm"]),
                        ModelConfig.is_default == "true",
                    )
                )
                ner_model = model_result.scalar_one_or_none()
                if not ner_model:
                    model_result = await db.execute(
                        select(ModelConfig).where(
                            ModelConfig.project_id == project_id,
                            ModelConfig.model_type.in_(["chat", "vlm"]),
                            ModelConfig.is_default == "true",
                        )
                    )
                    ner_model = model_result.scalar_one_or_none()

            for chunk_data in split_results:
                content = chunk_data["content"]

                # 应用脱敏（正则 + 关键词 + 可选 NER）
                audit_records = []
                if desensitize_enabled:
                    content, audit_records = await desensitize_chunk(
                        content,
                        project_extra,
                        model_config=ner_model,
                        file_id=str(file.id),
                    )
                    # 写入审计日志
                    if audit_records:
                        from app.models.models import AuditLog
                        for record in audit_records:
                            db.add(AuditLog(
                                project_id=project_id,
                                chunk_id=None,  # chunk 还未 flush，后续更新
                                file_id=file.id,
                                rule_id=record.get("rule_id", ""),
                                rule_type=record.get("rule_type", ""),
                                original_text=record.get("original_text", ""),
                                replacement=record.get("replacement", ""),
                                confidence=record.get("confidence", 1.0),
                            ))

                db_chunk = Chunk(
                    project_id=project_id,
                    file_id=file.id,
                    name=chunk_data.get("name", f"Chunk {chunk_data['index'] + 1}"),  # 标题路径
                    content=content,
                    summary=chunk_data.get("summary", chunk_data.get("name")),  # 内容摘要
                    word_count=chunk_data.get("word_count", len(content.split()))
                )
                db.add(db_chunk)
                chunks.append(db_chunk)

            await db.commit()

            ready_dir = get_project_ready_dir(str(project_id))

            # 删除旧的 markdown 文件（可能有两种命名格式）
            old_md_files = list(ready_dir.glob(f"{file.id}*.md"))
            for old_file in old_md_files:
                try:
                    old_file.unlink()
                except Exception:
                    pass

            md_filename = f"{file.id}.md"
            md_path = ready_dir / md_filename

            # 写入 markdown 文件（Excel markdown 模式时 text 是列表，需要合并）
            md_content = "\n\n".join(text) if isinstance(text, list) else text
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: md_path.write_text(md_content, encoding='utf-8')
            )

            file.status = "completed"
            await db.commit()

            log_success(
                "文件分割完成",
                project_id=str(project_id),
                file_id=str(file.id),
                filename=file.filename,
                method=request.method,
                chunk_count=len(chunks),
                text_length=len(md_content),
                ready_path=str(md_path)
            )
        except Exception as e:
            if file:
                file.status = "failed"
                await db.commit()

            log_failure(
                "文件分割失败",
                project_id=str(project_id),
                file_id=str(request.file_id),
                method=request.method,
                error=str(e),
                exc_info=True
            )


@router.post("/split", response_model=ApiResponse)
async def split_text(
    project_id: UUID,
    request: SplitRequest,
    db: AsyncSession = Depends(get_db)
):
    """Split text into chunks"""
    try:
        result = await db.execute(
            select(File).where(File.id == request.file_id, File.project_id == project_id)
        )
        file = result.scalar_one_or_none()
        if not file:
            raise NotFoundException("File", request.file_id)

        # 记录开始处理
        log_success(
            "开始处理文件",
            project_id=str(project_id),
            file_id=str(file.id),
            filename=file.filename,
            method=request.method,
            chunk_size=request.chunk_size,
            overlap=request.overlap
        )

        file.status = "processing"
        await db.commit()

        asyncio.create_task(
            process_split_async(
                project_id=project_id,
                request=request,
            )
        )

        return ApiResponse.ok(
            data={"file_id": str(file.id), "status": file.status},
            message="Split task started, processing in background"
        )
    except Exception as e:
        if 'file' in locals() and file:
            file.status = "failed"
            await db.commit()

        log_failure(
            "分割任务启动失败",
            project_id=str(project_id),
            file_id=str(request.file_id),
            error=str(e)
        )
        raise


@router.get("", response_model=ApiResponse)
async def list_chunks(
    project_id: UUID,
    file_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List chunks for a project"""
    filters = {"project_id": project_id}
    if file_id:
        filters["file_id"] = file_id

    skip = (page - 1) * page_size
    chunks, total = await chunk_crud.get_multi(
        db,
        skip=skip,
        limit=page_size,
        filters=filters,
        order_by="created_at",
        descending=False
    )

    chunk_responses = [ChunkResponse.model_validate(c) for c in chunks]
    return PaginatedResponse.ok(
        items=chunk_responses,
        page=page,
        page_size=page_size,
        total=total
    )


@router.get("/{chunk_id}", response_model=ApiResponse)
async def get_chunk(
    project_id: UUID,
    chunk_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get chunk by ID"""
    chunk = await chunk_crud.get(db, chunk_id)
    if not chunk or chunk.project_id != project_id:
        raise NotFoundException("Chunk", chunk_id)

    return ApiResponse.ok(data=ChunkResponse.model_validate(chunk))


@router.put("/{chunk_id}", response_model=ApiResponse)
async def update_chunk(
    project_id: UUID,
    chunk_id: UUID,
    chunk: ChunkUpdateSchema,
    db: AsyncSession = Depends(get_db)
):
    """Update chunk"""
    db_chunk = await chunk_crud.get(db, chunk_id)
    if not db_chunk or db_chunk.project_id != project_id:
        raise NotFoundException("Chunk", chunk_id)

    updated_chunk = await chunk_crud.update(db, db_chunk, chunk)
    return ApiResponse.ok(
        data=ChunkResponse.model_validate(updated_chunk),
        message="Chunk updated successfully"
    )


@router.delete("/{chunk_id}", response_model=ApiResponse)
async def delete_chunk(
    project_id: UUID,
    chunk_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete chunk"""
    chunk = await chunk_crud.get(db, chunk_id)
    if not chunk or chunk.project_id != project_id:
        raise NotFoundException("Chunk", chunk_id)

    await chunk_crud.delete(db, chunk_id)
    return ApiResponse.ok(message="Chunk deleted successfully")
