"""
QA Batch Management API

问答对批次管理：列出批次、查看详情、删除批次、重命名。
每个生成任务对应一个 batch_id，同一次生成的问答对共享同一 batch_id。
批次名称存储在 Project.extra_data.batch_names 中。
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import ApiResponse
from app.core.database import get_db
from app.models.models import ModelConfig, Project, Question, Task

router = APIRouter()


# ──────────────────────────────────────────────
# 注意：静态路径必须放在动态路径 {batch_id} 之前
# ──────────────────────────────────────────────


@router.get("/batches/check-embedding", response_model=ApiResponse)
async def check_embedding_model(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """检查项目是否配置了可用的 embedding 模型（语义校验需要）。"""
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.project_id == project_id,
            ModelConfig.model_type == "embedding",
            ModelConfig.is_default == "true",
        )
    )
    model_config = result.scalar_one_or_none()

    if not model_config:
        result = await db.execute(
            select(ModelConfig).where(
                ModelConfig.project_id.is_(None),
                ModelConfig.model_type == "embedding",
                ModelConfig.is_default == "true",
            )
        )
        model_config = result.scalar_one_or_none()

    has_embedding = model_config is not None and bool(model_config.api_key)

    return ApiResponse.ok(data={
        "has_embedding": has_embedding,
        "model_name": model_config.model_name if model_config else None,
        "model_id": str(model_config.id) if model_config else None,
    })


def _get_batch_names(project: Project) -> dict:
    """从 Project.extra_data 中获取批次名称映射。"""
    extra = project.extra_data or {}
    return extra.get("batch_names", {})


async def _set_batch_name(project: Project, batch_id_str: str, name: str, db: AsyncSession):
    """设置批次名称到 Project.extra_data.batch_names。"""
    from sqlalchemy.orm.attributes import flag_modified

    extra = project.extra_data or {}
    batch_names = extra.get("batch_names", {})
    batch_names[batch_id_str] = name
    extra["batch_names"] = batch_names
    project.extra_data = extra
    flag_modified(project, "extra_data")
    await db.commit()


@router.get("/batches", response_model=ApiResponse)
async def list_batches(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """列出项目所有问答对生成批次。"""
    # 获取项目（用于读取 batch_names）
    project = await db.get(Project, project_id)
    batch_names_map = _get_batch_names(project) if project else {}

    # 查询所有有 batch_id 的问答对，按 batch_id 分组统计
    query = (
        select(
            Question.batch_id,
            func.count(Question.id).label("total_count"),
            func.count(Question.id).filter(Question.answer_status == "completed").label("completed_count"),
            func.count(Question.id).filter(Question.answer_status == "failed").label("failed_count"),
            func.count(Question.id).filter(Question.answer_status == "pending").label("pending_count"),
            func.min(Question.created_at).label("created_at"),
            func.max(Question.source).label("source"),
        )
        .where(
            Question.project_id == project_id,
            Question.batch_id.isnot(None),
        )
        .group_by(Question.batch_id)
        .order_by(func.min(Question.created_at).desc())
    )
    result = await db.execute(query)
    rows = result.all()

    # 一次性查询所有项目的 Task（用于匹配 task_status）
    task_result = await db.execute(
        select(Task).where(Task.project_id == project_id)
    )
    tasks_list = task_result.scalars().all()
    # 建立 batch_id_str → Task 映射
    task_map = {}
    for t in tasks_list:
        if t.result and isinstance(t.result, dict) and t.result.get("batch_id"):
            task_map[t.result["batch_id"]] = t

    # source → 中文标签映射
    label_map = {
        "manual": "手动录入",
        "structured_template": "结构化-模板",
        "structured_llm": "结构化-LLM",
        "generated_qa": "非结构化QA",
        "generated_qa_local": "非结构化-局部",
        "generated_qa_context_enhanced": "非结构化-增强",
        "generated_qa_full_doc": "非结构化-全文",
        "generated": "问题生成",
        "generated_local": "问题-局部",
        "generated_context_enhanced": "问题-增强",
        "generated_full_doc": "问题-全文",
    }

    batches = []
    for row in rows:
        batch_id_str = str(row.batch_id)
        task = task_map.get(batch_id_str)

        # 获取文件名列表（从 generation_metadata 提取）
        file_names_query = (
            select(Question.generation_metadata)
            .where(
                Question.project_id == project_id,
                Question.batch_id == row.batch_id,
                Question.generation_metadata.isnot(None),
            )
            .limit(50)
        )
        file_names_result = await db.execute(file_names_query)
        file_names = set()
        for meta_row in file_names_result.all():
            meta = meta_row[0] or {}
            filename = meta.get("filename", "")
            if filename:
                file_names.add(filename)

        # 优先用用户自定义名称，否则用类型标签
        custom_name = batch_names_map.get(batch_id_str, "")
        source = row.source or "unknown"
        auto_label = label_map.get(source, source)

        batch_info = {
            "batch_id": batch_id_str,
            "total_count": row.total_count,
            "completed_count": row.completed_count,
            "failed_count": row.failed_count,
            "pending_count": row.pending_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "source": source,
            "task_status": task.status if task else None,
            "task_progress": task.progress if task else None,
            "file_names": list(file_names),
            "name": custom_name,
            "label": custom_name or auto_label,
        }

        batches.append(batch_info)

    return ApiResponse.ok(data={"batches": batches})


@router.get("/batches/{batch_id}", response_model=ApiResponse)
async def get_batch_details(
    project_id: UUID,
    batch_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取批次详情，包含该批次的问答对列表。"""
    stats_query = (
        select(
            func.count(Question.id).label("total"),
            func.count(Question.id).filter(Question.answer_status == "completed").label("completed"),
            func.count(Question.id).filter(Question.answer_status == "failed").label("failed"),
            func.count(Question.id).filter(Question.quality_score < 0.5).label("hallucination"),
        )
        .where(
            Question.project_id == project_id,
            Question.batch_id == batch_id,
        )
    )
    stats_result = await db.execute(stats_query)
    stats_row = stats_result.one()

    skip = (page - 1) * page_size
    questions_query = (
        select(Question)
        .where(
            Question.project_id == project_id,
            Question.batch_id == batch_id,
        )
        .order_by(Question.created_at.desc())
        .offset(skip)
        .limit(page_size)
    )
    questions_result = await db.execute(questions_query)
    questions = questions_result.scalars().all()

    from app.schemas.question import QuestionResponse
    from app.models.models import Chunk, File

    chunk_ids = [q.chunk_id for q in questions if q.chunk_id]
    chunk_file_map = {}
    if chunk_ids:
        chunk_result = await db.execute(
            select(Chunk.id, Chunk.file_id, File.filename)
            .join(File, Chunk.file_id == File.id, isouter=True)
            .where(Chunk.id.in_(chunk_ids))
        )
        chunk_file_map = {
            row.id: {"file_id": row.file_id, "file_name": row.filename}
            for row in chunk_result.fetchall()
        }

    question_responses = []
    for q in questions:
        q_dict = QuestionResponse.model_validate(q).model_dump()
        if q.chunk_id and q.chunk_id in chunk_file_map:
            q_dict["file_id"] = chunk_file_map[q.chunk_id]["file_id"]
            q_dict["file_name"] = chunk_file_map[q.chunk_id]["file_name"]
        question_responses.append(q_dict)

    return ApiResponse.ok(data={
        "batch_id": str(batch_id),
        "stats": {
            "total": stats_row.total,
            "completed": stats_row.completed,
            "failed": stats_row.failed,
            "hallucination": stats_row.hallucination,
        },
        "questions": question_responses,
        "page": page,
        "page_size": page_size,
        "total": stats_row.total,
    })


class RenameBatchRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="新名称")


@router.put("/batches/{batch_id}/rename", response_model=ApiResponse)
async def rename_batch(
    project_id: UUID,
    batch_id: UUID,
    request: RenameBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """重命名批次（存储到 Project.extra_data.batch_names）。"""
    project = await db.get(Project, project_id)
    if not project:
        return ApiResponse.fail(message="项目不存在")

    # 验证批次存在
    count = await db.scalar(
        select(func.count(Question.id)).where(
            Question.project_id == project_id,
            Question.batch_id == batch_id,
        )
    )
    if not count:
        return ApiResponse.fail(message="批次不存在")

    await _set_batch_name(project, str(batch_id), request.name, db)

    return ApiResponse.ok(message="批次名称已更新", data={"batch_id": str(batch_id), "name": request.name})


@router.delete("/batches/{batch_id}", response_model=ApiResponse)
async def delete_batch(
    project_id: UUID,
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除一个批次及其所有问答对。"""
    count_result = await db.execute(
        select(func.count(Question.id))
        .where(
            Question.project_id == project_id,
            Question.batch_id == batch_id,
        )
    )
    count = count_result.scalar()

    if count == 0:
        return ApiResponse.fail(message="批次不存在或已删除")

    await db.execute(
        delete(Question)
        .where(
            Question.project_id == project_id,
            Question.batch_id == batch_id,
        )
    )

    # 同时清理批次名称
    project = await db.get(Project, project_id)
    if project:
        batch_names_map = _get_batch_names(project)
        batch_id_str = str(batch_id)
        if batch_id_str in batch_names_map:
            del batch_names_map[batch_id_str]
            extra = project.extra_data or {}
            extra["batch_names"] = batch_names_map
            project.extra_data = extra
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(project, "extra_data")

    await db.commit()

    return ApiResponse.ok(
        message=f"批次已删除，共清理 {count} 条问答对",
        data={"deleted_count": count},
    )
