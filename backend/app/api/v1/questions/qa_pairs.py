"""
QA Pair Generation API Router

一步式问答对生成接口（同时生成问题和答案）
"""
import asyncio
import json
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import ApiResponse
from app.core.crud import CRUDBase
from app.core.database import get_db
from app.core.exceptions import ValidationException, NotFoundException
from app.core.logging import logger
from app.models.models import Chunk, File, ModelConfig, Project, Question, Task, AuditLog
from app.schemas.eval import TaskResponse
from app.schemas.question import GenerateQARequest, GenerateStructuredQARequest
from app.services.qa_generation import process_generate_qa_async, process_structured_qa_async
from app.services.quality_validator import validate_questions_async, regenerate_answer_async

router = APIRouter()

task_crud = CRUDBase(Task)


# ──────────────────────────────────────────────
# 手动创建 QA 对
# ──────────────────────────────────────────────

class ManualQACreateRequest(BaseModel):
    """手动创建 QA 对请求"""
    content: str = Field(..., min_length=1, description="指令/问题内容")
    answer: str = Field(..., min_length=1, description="回复内容")
    source: str = Field(default="manual", description="来源标记")
    # DPO 字段
    rejected_answer: Optional[str] = Field(None, description="DPO 被拒绝的回答（仅 DPO 模板使用）")
    question_type: str = Field(default="manual", description="问题类型：manual / dpo")
    # 批次 ID（前端传入，同一次录入会话共享同一个 batch_id）
    batch_id: Optional[str] = Field(None, description="批次 ID，不传则自动生成")


class BatchImportRequest(BaseModel):
    """批量导入 QA 对请求"""
    items: List[ManualQACreateRequest] = Field(..., min_length=1, description="QA 对列表")


@router.post("/manual", response_model=ApiResponse)
async def create_manual_qa(
    project_id: UUID,
    request: ManualQACreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """手动创建单个 QA 对"""
    is_dpo = request.question_type == "dpo" or bool(request.rejected_answer)

    # 确定 batch_id：前端传入 > 自动生成
    import uuid as uuid_mod
    batch_id = uuid_mod.UUID(request.batch_id) if request.batch_id else uuid_mod.uuid4()

    question = Question(
        project_id=project_id,
        content=request.content,
        answer=request.answer,
        source=request.source,
        question_type="dpo" if is_dpo else "manual",
        batch_id=batch_id,
        generation_status="generated",
        answer_status="completed",
        generation_metadata={
            "rejected_answer": request.rejected_answer,
        } if is_dpo else None,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)

    return ApiResponse.ok(
        data={"id": str(question.id), "question_type": question.question_type, "batch_id": str(batch_id)},
        message="QA 对已创建",
    )


@router.post("/batch-import", response_model=ApiResponse)
async def batch_import_qa(
    project_id: UUID,
    request: BatchImportRequest,
    db: AsyncSession = Depends(get_db),
):
    """批量导入 QA 对"""
    import uuid as uuid_mod
    batch_id = uuid_mod.uuid4()
    created_ids = []
    for item in request.items:
        is_dpo = item.question_type == "dpo" or bool(item.rejected_answer)
        question = Question(
            project_id=project_id,
            content=item.content,
            answer=item.answer,
            source=item.source,
            question_type="dpo" if is_dpo else "manual",
            batch_id=batch_id,
            generation_status="generated",
            answer_status="completed",
            generation_metadata={
                "rejected_answer": item.rejected_answer,
            } if is_dpo else None,
        )
        db.add(question)
        created_ids.append(question)

    await db.commit()

    return ApiResponse.ok(
        data={
            "count": len(created_ids),
            "ids": [str(q.id) for q in created_ids],
        },
        message=f"成功导入 {len(created_ids)} 个 QA 对",
    )



@router.post("/generate-qa", response_model=ApiResponse)
async def generate_qa_pairs(
    project_id: UUID,
    request: GenerateQARequest,
    db: AsyncSession = Depends(get_db),
):
    """一步式生成问答对（问题 + 答案），后台执行，返回 task_id 用于进度查询。"""

    # --- 验证问题生成模型 ---
    model_result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == request.model_id,
            ModelConfig.project_id == None,  # noqa: E711
        )
    )
    model = model_result.scalar_one_or_none()
    if not model:
        raise ValidationException("问题生成模型未找到", field="model_id")
    if not model.api_key:
        raise ValidationException("问题生成模型缺少 API Key", field="model_id")

    # --- 验证答案生成模型（如指定）---
    if request.answer_model_id:
        answer_model_result = await db.execute(
            select(ModelConfig).where(
                ModelConfig.id == request.answer_model_id,
                ModelConfig.project_id == None,  # noqa: E711
            )
        )
        answer_model = answer_model_result.scalar_one_or_none()
        if not answer_model:
            raise ValidationException("答案生成模型未找到", field="answer_model_id")
        if not answer_model.api_key:
            raise ValidationException("答案生成模型缺少 API Key", field="answer_model_id")

    # --- 获取有效的 chunk IDs ---
    chunk_query = select(Chunk.id).where(Chunk.project_id == project_id)
    if request.chunk_ids:
        chunk_query = chunk_query.where(Chunk.id.in_(request.chunk_ids))
    elif request.file_ids:
        chunk_query = chunk_query.where(Chunk.file_id.in_(request.file_ids))

    chunk_result = await db.execute(chunk_query)
    valid_chunk_ids = [row[0] for row in chunk_result.all()]
    if not valid_chunk_ids:
        raise ValidationException(
            "没有可用的文本块",
            field="chunk_ids" if request.chunk_ids else "file_ids",
        )

    # 创建任务
    import uuid as uuid_mod
    batch_id = uuid_mod.uuid4()

    task = Task(
        project_id=project_id,
        task_type="generate_qa",
        status="pending",
        progress=0,
        result={
            "created_questions": 0,
            "created_answers": 0,
            "processed_chunks": 0,
            "skipped_chunks": 0,
            "total_chunks": len(valid_chunk_ids),
            "failed_answers": 0,
            "batch_id": str(batch_id),
        },
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # --- 启动后台任务 ---
    answer_model_id = request.answer_model_id or request.model_id

    async def run_task():
        try:
            await process_generate_qa_async(
                project_id=project_id,
                model_id=request.model_id,
                answer_model_id=answer_model_id,
                count=request.count,
                chunk_ids=valid_chunk_ids,
                file_ids=None,
                dirty_data_filter=request.dirty_data_filter,
                thinking_mode=request.thinking_mode,
                preset_prompt=request.preset_prompt,
                temperature=request.temperature,
                answer_temperature=request.answer_temperature,
                task_id=task.id,
                generation_mode=request.generation_mode,
                context_window=request.context_window,
                full_doc_max_chars=request.full_doc_max_chars,
                batch_id=batch_id,
            )
        except Exception as e:
            logger.error(f"问答对生成后台任务失败: task_id={task.id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    asyncio.create_task(run_task())

    # --- 预估问答对数量 ---
    chunk_result_for_stats = await db.execute(
        select(Chunk.content).where(Chunk.id.in_(valid_chunk_ids))
    )
    chunks_content = chunk_result_for_stats.scalars().all()
    total_chars = sum(len(c or "") for c in chunks_content)
    estimated_qa_pairs = max(1, min(request.count * len(valid_chunk_ids), total_chars // 240))

    return ApiResponse.ok(
        data={
            "chunk_count": len(valid_chunk_ids),
            "total_chars": total_chars,
            "estimated_qa_pairs": estimated_qa_pairs,
            "status": "processing",
            "task_id": str(task.id),
            "batch_id": str(batch_id),
        },
        message="问答对生成已在后台启动",
    )


@router.get("/qa-tasks/latest", response_model=ApiResponse)
async def get_latest_qa_task(
    project_id: UUID,
    task_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """获取项目最新的问答对生成任务状态（用于进度轮询）。

    支持通过 task_type 参数过滤特定类型的任务。
    不传 task_type 则返回所有 QA 类任务的最新一条。
    """
    # 查询最新的 QA 生成类任务（非结构化 + 结构化 + 校验）
    qa_task_types = ["generate_qa", "generate_structured_qa", "generate", "generate_answers", "validate_qa"]

    # 如果指定了 task_type，则只查该类型
    if task_type:
        qa_task_types = [task_type]

    task_query = (
        select(Task)
        .where(Task.project_id == project_id, Task.task_type.in_(qa_task_types))
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    result = await db.execute(task_query)
    task = result.scalar_one_or_none()

    if not task:
        return ApiResponse.ok(data=None)

    # 使用 TaskResponse 序列化（field_validator 会自动解析 JSON 字符串）
    try:
        task_data = TaskResponse.model_validate(task).model_dump()
    except Exception as e:
        # fallback：手动构建返回数据，确保 result 被正确解析
        logger.warning(f"[qa-tasks/latest] model_validate 失败: {e}")

        # 确保 result 是 dict 而非 JSON 字符串
        task_result = task.result
        if isinstance(task_result, str):
            try:
                task_result = json.loads(task_result)
            except (json.JSONDecodeError, ValueError):
                task_result = None

        task_data = {
            "id": str(task.id),
            "project_id": str(task.project_id) if task.project_id else None,
            "task_type": task.task_type,
            "status": task.status,
            "progress": task.progress or 0,
            "result": task_result,
            "error": task.error,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

    logger.info(f"[qa-tasks/latest] 返回: status={task.status}, progress={task.progress}, result_keys={list(task_data.get('result', {}).keys()) if isinstance(task_data.get('result'), dict) else 'N/A'}")

    return ApiResponse.ok(data=task_data)


@router.post("/generate-structured-qa", response_model=ApiResponse)
async def generate_structured_qa(
    project_id: UUID,
    request: GenerateStructuredQARequest,
    db: AsyncSession = Depends(get_db),
):
    """结构化数据问答对生成。支持模板模式和 LLM 增强模式。"""

    # 验证文件存在且有字段映射
    files_result = await db.execute(
        select(File).where(File.id.in_(request.file_ids), File.project_id == project_id)
    )
    files = files_result.scalars().all()
    if not files:
        raise ValidationException("未找到指定的文件", field="file_ids")

    for f in files:
        if not f.field_schema:
            raise ValidationException(
                f"文件 {f.filename} 尚未提取字段信息，请先在结构化数据处理页面完成字段标注",
                field="file_ids",
            )
        target_fields = [field for field in f.field_schema if field.get("role") == "target"]
        if not target_fields:
            raise ValidationException(
                f"文件 {f.filename} 没有标注输出字段，请至少将一个字段设为「输出字段」",
                field="file_ids",
            )

    # LLM 模式需要验证模型
    if request.strategy == "llm":
        if not request.model_id:
            raise ValidationException("LLM 增强模式需要指定生成模型", field="model_id")
        model_result = await db.execute(
            select(ModelConfig).where(ModelConfig.id == request.model_id)
        )
        model = model_result.scalar_one_or_none()
        if not model:
            raise ValidationException("生成模型未找到", field="model_id")
        if not model.api_key:
            raise ValidationException("生成模型缺少 API Key", field="model_id")

    # 创建任务
    import uuid as uuid_mod
    batch_id = uuid_mod.uuid4()

    # 创建任务（模板和 LLM 模式都走后台任务，支持渐进进度）
    task = Task(
        project_id=project_id,
        task_type="generate_structured_qa",
        status="pending",
        progress=0,
        result={"created_questions": 0, "processed_rows": 0, "total_rows": 0, "batch_id": str(batch_id)},
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # 启动后台任务
    async def run_task():
        try:
            await process_structured_qa_async(
                project_id=project_id,
                file_ids=request.file_ids,
                strategy=request.strategy,
                model_id=request.model_id,
                temperature=request.temperature,
                questions_per_row=request.questions_per_row,
                task_id=task.id,
                batch_id=batch_id,
            )
        except Exception as e:
            logger.error(f"结构化QA生成后台任务失败: task_id={task.id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    asyncio.create_task(run_task())

    return ApiResponse.ok(
        data={
            "status": "processing",
            "task_id": str(task.id),
            "batch_id": str(batch_id),
            "file_count": len(files),
            "strategy": request.strategy,
        },
        message="结构化数据问答对生成已启动",
    )


# ──────────────────────────────────────────────
# 数据质量校验
# ──────────────────────────────────────────────

class ValidateRequest(BaseModel):
    """质量校验请求"""
    question_ids: Optional[List[UUID]] = None  # 不传则校验全部
    batch_id: Optional[UUID] = None  # 按批次校验


@router.post("/validate", response_model=ApiResponse)
async def validate_questions(
    project_id: UUID,
    request: ValidateRequest = ValidateRequest(),
    db: AsyncSession = Depends(get_db),
):
    """执行三层质量校验（基础 + 语义 + 格式），后台运行。支持按批次校验。"""

    # 构建查询
    query = select(Question).where(Question.project_id == project_id)
    if request.question_ids:
        query = query.where(Question.id.in_(request.question_ids))
    elif request.batch_id:
        query = query.where(Question.batch_id == request.batch_id)

    result = await db.execute(query)
    questions = result.scalars().all()

    if not questions:
        raise ValidationException("项目下没有问答对数据", field="project_id")

    # 创建任务
    task = Task(
        project_id=project_id,
        task_type="validate_qa",
        status="pending",
        progress=0,
        result={"total": len(questions), "passed": 0, "hallucination": 0, "format_error": 0, "failed": 0},
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # 启动后台任务
    async def run_task():
        try:
            await validate_questions_async(
                project_id=project_id,
                question_ids=request.question_ids,
                task_id=task.id,
            )
        except Exception as e:
            logger.error(f"质量校验后台任务失败: task_id={task.id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    asyncio.create_task(run_task())

    return ApiResponse.ok(
        data={
            "status": "processing",
            "task_id": str(task.id),
            "total": len(questions),
        },
        message="质量校验已启动",
    )


@router.post("/{question_id}/regenerate", response_model=ApiResponse)
async def regenerate_question_answer(
    project_id: UUID,
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """重新生成单个问题的答案——基于原切片内容和失败原因重组提示词。"""

    # 验证问题存在
    question = await db.get(Question, question_id)
    if not question or question.project_id != project_id:
        raise NotFoundException("Question", question_id)

    # 在后台执行重新生成
    updated_question = await regenerate_answer_async(project_id, question_id)

    if not updated_question:
        raise ValidationException("重新生成失败，请检查是否配置了默认 Chat 模型", field="model")

    return ApiResponse.ok(
        data={
            "id": str(updated_question.id),
            "answer": updated_question.answer,
            "answer_status": updated_question.answer_status,
            "answer_error": updated_question.answer_error,
        },
        message="答案重新生成完成",
    )


# ──────────────────────────────────────────────
# 脱敏预览 & 审计日志
# ──────────────────────────────────────────────

class DesensitizePreviewRequest(BaseModel):
    """脱敏预览请求"""
    text: str = Field(..., min_length=1, description="待预览的文本内容")


@router.post("/desensitize-preview", response_model=ApiResponse)
async def desensitize_preview(
    project_id: UUID,
    request: DesensitizePreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """预览脱敏效果：对给定文本执行脱敏，返回原文和脱敏后文本及替换记录。"""
    from app.services.desensitize import build_engine_from_project_config

    project = await db.get(Project, project_id)
    if not project:
        raise NotFoundException("Project", project_id)

    extra_data = project.extra_data or {}
    sensitive_config = extra_data.get("sensitive_rules", {})
    if not sensitive_config.get("enabled", False):
        return ApiResponse.ok(data={
            "original": request.text,
            "desensitized": request.text,
            "records": [],
            "message": "脱敏未启用，原文不变",
        })

    engine, _ = build_engine_from_project_config(extra_data)
    desensitized, records = engine.desensitize(request.text)

    return ApiResponse.ok(data={
        "original": request.text,
        "desensitized": desensitized,
        "records": records,
    })


@router.get("/audit-logs", response_model=ApiResponse)
async def list_audit_logs(
    project_id: UUID,
    chunk_id: Optional[UUID] = None,
    file_id: Optional[UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """查询脱敏审计日志"""
    query = select(AuditLog).where(AuditLog.project_id == project_id)
    if chunk_id:
        query = query.where(AuditLog.chunk_id == chunk_id)
    if file_id:
        query = query.where(AuditLog.file_id == file_id)
    query = query.order_by(AuditLog.created_at.desc())

    # 简单分页
    total = await db.scalar(
        select(func.count(AuditLog.id)).where(AuditLog.project_id == project_id)
    )
    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    logs = result.scalars().all()

    log_list = []
    for log_entry in logs:
        log_list.append({
            "id": str(log_entry.id),
            "chunk_id": str(log_entry.chunk_id) if log_entry.chunk_id else None,
            "file_id": str(log_entry.file_id) if log_entry.file_id else None,
            "rule_id": log_entry.rule_id,
            "rule_type": log_entry.rule_type,
            "original_text": log_entry.original_text,
            "replacement": log_entry.replacement,
            "confidence": log_entry.confidence,
            "created_at": log_entry.created_at.isoformat() if log_entry.created_at else None,
        })

    return ApiResponse.ok(data={
        "items": log_list,
        "total": total or 0,
        "page": page,
        "page_size": page_size,
    })
