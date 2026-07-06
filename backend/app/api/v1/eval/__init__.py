"""
Evaluation API Router - 评估系统主路由
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
import json
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, and_

from app.api.response import ApiResponse, PaginatedResponse
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.crud import CRUDBase
from app.models.models import EvalDataset, Task, ModelConfig, Question
from app.schemas.eval import EvalDatasetResponse, TaskResponse, format_task_response, validate_task_status
from app.api.v1.eval.eval_results_service import get_eval_results_by_task_id, get_eval_results_stats

router = APIRouter()

# Initialize CRUD
eval_crud = CRUDBase(EvalDataset)
task_crud = CRUDBase(Task)

DATASETS_ROOT = Path("data")


# ============ Request Models ============

class FolderRef(BaseModel):
    """文件夹引用 — 支持答案文件夹和问答对文件夹"""
    folder_name: str = Field(..., min_length=1)
    folder_type: str = Field("answer", pattern="^(answer|qa)$")


class GenerateEvalRequest(BaseModel):
    """创建评估数据集 — 从文件夹选取问答对（支持答案文件夹和问答对文件夹）"""
    name: str = Field(..., min_length=1, max_length=255)
    question_type: str = Field("mixed", pattern="^(mixed|fact|reasoning|summary)$")
    folders: List[FolderRef] = Field(..., min_length=1)
    # 兼容旧版前端，如果传了 answer_folder_names 则自动转为 folders
    answer_folder_names: Optional[List[str]] = None


class RunEvalRequest(BaseModel):
    """运行评估"""
    model_config_id: Optional[UUID] = None


class CreateEvalTaskRequest(BaseModel):
    """创建评估任务（盲测）"""
    models: list = Field(..., min_length=1)
    eval_dataset_ids: list = Field(..., min_length=1)
    judge_model_id: Optional[UUID] = None
    judge_provider_id: Optional[UUID] = None
    language: str = "zh-CN"


class StartTaskRequest(BaseModel):
    """启动任务"""
    note: Optional[str] = None


# ============ Helper Functions ============

async def process_task_async(task_id: UUID):
    """后台任务处理"""
    from app.services.task_processor import process_evaluation_task
    try:
        await process_evaluation_task(task_id)
    except Exception as e:
        print(f"Failed to process task {task_id}: {e}")
        raise


# ============ Eval Dataset Endpoints ============

@router.get("", response_model=ApiResponse)
async def list_eval_datasets(
    project_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """列表评估数据集"""
    skip = (page - 1) * page_size

    datasets, total = await eval_crud.get_multi(
        db, skip=skip, limit=page_size,
        filters={"project_id": project_id},
        order_by="created_at", descending=True
    )

    items = []
    for d in datasets:
        items.append({
            "id": str(d.id),
            "project_id": str(d.project_id),
            "name": d.name,
            "question_type": d.question_type,
            "status": d.status,
            "question_count": d.question_count,
            "created_at": d.created_at.isoformat() if d.created_at else None
        })

    return PaginatedResponse.ok(items=items, page=page, page_size=page_size, total=total)


@router.post("", response_model=ApiResponse)
async def create_eval_dataset(
    project_id: UUID,
    request: GenerateEvalRequest,
    db: AsyncSession = Depends(get_db)
):
    """创建评估数据集 — 从文件夹中选取问答对（支持答案文件夹和问答对文件夹）"""
    try:
        all_question_ids = []
        all_qa_items = []  # 兼容旧数据：没有 question_id 的 QA 对

        # 兼容旧版前端：如果没有 folders 但有 answer_folder_names，自动转换
        folders = request.folders
        if not folders and request.answer_folder_names:
            folders = [FolderRef(folder_name=name, folder_type="answer") for name in request.answer_folder_names]

        for folder_ref in folders:
            folder_name = folder_ref.folder_name
            folder_type = folder_ref.folder_type

            # 根据文件夹类型确定目录
            if folder_type == "qa":
                folder_path = DATASETS_ROOT / str(project_id) / "generated-qa" / folder_name
                if not folder_path.exists():
                    return ApiResponse.fail(message=f"问答对文件夹不存在: {folder_name}")
            else:
                folder_path = DATASETS_ROOT / str(project_id) / "generated-answers" / folder_name
                if not folder_path.exists():
                    return ApiResponse.fail(message=f"答案文件夹不存在: {folder_name}")

            summary_file = folder_path / "summary.json"
            if not summary_file.exists():
                continue

            with open(summary_file, "r", encoding="utf-8") as f:
                summary = json.load(f)

            for file_id in summary.get("files", {}).keys():
                if folder_type == "qa":
                    # QA 文件夹：从 qa_pairs.json 读取
                    qa_file = folder_path / file_id / "qa_pairs.json"
                    if qa_file.exists():
                        with open(qa_file, "r", encoding="utf-8") as f:
                            qa_data = json.load(f)
                        for qa_item in qa_data.get("qa_pairs", []):
                            q_id = qa_item.get("question_id")
                            if q_id and q_id not in all_question_ids:
                                all_question_ids.append(q_id)
                            elif not q_id:
                                # 兼容旧数据：没有 question_id，通过内容匹配
                                all_qa_items.append(qa_item)
                else:
                    # 答案文件夹：从 answers.json 读取
                    answers_file = folder_path / file_id / "answers.json"
                    if answers_file.exists():
                        with open(answers_file, "r", encoding="utf-8") as f:
                            answers_data = json.load(f)
                        for answer_item in answers_data.get("answers", []):
                            q_id = answer_item.get("question_id")
                            if q_id and q_id not in all_question_ids:
                                all_question_ids.append(q_id)

        # 兼容旧数据：没有 question_id 的 QA 对，通过内容匹配数据库
        if not all_question_ids and all_qa_items:
            for qa_item in all_qa_items:
                question_text = qa_item.get("question", "").strip()
                if not question_text:
                    continue
                q_result = await db.execute(
                    select(Question).where(
                        Question.project_id == project_id,
                        Question.content == question_text,
                        Question.answer.isnot(None),
                        Question.answer != "",
                    ).limit(1)
                )
                q_obj = q_result.scalar_one_or_none()
                if q_obj and str(q_obj.id) not in all_question_ids:
                    all_question_ids.append(str(q_obj.id))

        if not all_question_ids:
            return ApiResponse.fail(message="所选文件夹中没有可用的问答数据")

        # 验证这些问题在数据库中存在且有答案
        valid_ids = []
        for qid in all_question_ids:
            try:
                UUID(qid)
                valid_ids.append(qid)
            except ValueError:
                pass

        query = select(Question).where(
            Question.project_id == project_id,
            Question.id.in_([UUID(qid) for qid in valid_ids]),
            Question.answer.isnot(None),
            Question.answer != ""
        )
        result = await db.execute(query)
        questions = result.scalars().all()

        if not questions:
            return ApiResponse.fail(message="所选文件夹中没有有效的问答数据")

        question_ids = [str(q.id) for q in questions]
        extra_data = {
            "question_ids": question_ids,
            "folders": [{"folder_name": f.folder_name, "folder_type": f.folder_type} for f in folders],
            "answer_folder_names": [f.folder_name for f in folders],
            "selected_questions": len(question_ids)
        }

        db_dataset = EvalDataset(
            project_id=project_id,
            name=request.name,
            question_type=request.question_type,
            question_count=len(questions),
            status="pending",
            extra_data=json.dumps(extra_data)
        )
        db.add(db_dataset)
        await db.commit()
        await db.refresh(db_dataset)

        return ApiResponse.ok(
            data={"id": str(db_dataset.id), "question_count": len(questions)},
            message="评估数据集创建成功"
        )
    except Exception as e:
        import traceback
        print(f"[CREATE EVAL DATASET] 创建评估数据集时发生异常: {e}")
        print(traceback.format_exc())
        return ApiResponse.fail(message=f"创建评估数据集失败: {str(e)}")


# ============ Eval Tasks Endpoints ============

@router.get("/tasks", response_model=ApiResponse)
async def list_eval_tasks(
    project_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """列表评估任务"""
    skip = (page - 1) * page_size

    query = select(Task).where(
        and_(Task.project_id == project_id, Task.task_type == "model-evaluation")
    ).order_by(Task.created_at.desc()).offset(skip).limit(page_size)

    count_query = select(func.count()).select_from(Task).where(
        and_(Task.project_id == project_id, Task.task_type == "model-evaluation")
    )

    result = await db.execute(query)
    tasks = result.scalars().all()
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    items = []
    for t in tasks:
        model_info = {}
        try:
            model_info = json.loads(t.model_info) if t.model_info else {}
        except:
            pass

        detail = {}
        try:
            detail = json.loads(t.detail) if t.detail else {}
        except:
            pass

        items.append({
            "id": str(t.id),
            "name": model_info.get("modelName", "未知模型"),
            "status": validate_task_status(t.status),
            "progress": int((t.completed_count / t.total_count * 100)) if t.total_count > 0 else 0,
            "total": t.total_count,
            "completed": t.completed_count,
            "task_type": t.task_type,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "detail": detail
        })

    return PaginatedResponse.ok(items=items, page=page, page_size=page_size, total=total)


@router.post("/tasks", response_model=ApiResponse)
async def create_eval_task(
    project_id: UUID,
    request: CreateEvalTaskRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """创建评估任务"""
    created_tasks = []

    for model in request.models:
        model_config = await db.execute(
            select(ModelConfig).where(
                and_(
                    ModelConfig.project_id == project_id,
                    ModelConfig.id == model.get("modelId")
                )
            )
        )
        config = model_config.scalar_one_or_none()

        model_info = {
            "modelId": str(model.get("modelId")),
            "modelName": config.model_name if config else "未知",
            "providerId": str(model.get("providerId", "")),
            "providerName": config.provider if config else "未知"
        }

        task = Task(
            project_id=project_id,
            task_type="model-evaluation",
            status="pending",
            model_info=json.dumps(model_info),
            detail=json.dumps({
                "eval_dataset_ids": [str(id) for id in request.eval_dataset_ids],
                "judge_model_id": str(request.judge_model_id) if request.judge_model_id else None
            }),
            language=request.language,
            total_count=len(request.eval_dataset_ids),
            completed_count=0
        )
        db.add(task)
        await db.flush()
        created_tasks.append(task)

        background_tasks.add_task(process_task_async, task.id)

    await db.commit()

    return ApiResponse.ok(
        data=[{"id": str(t.id), "name": json.loads(t.model_info).get("modelName", "未知")} for t in created_tasks],
        message=f"创建了 {len(created_tasks)} 个评估任务"
    )


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_eval_task(
    project_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取任务详情"""
    task = await db.execute(
        select(Task).where(and_(Task.id == task_id, Task.project_id == project_id))
    )
    t = task.scalar_one_or_none()
    if not t:
        raise NotFoundException("Task", task_id)

    return ApiResponse.ok(data={
        "id": str(t.id),
        "status": validate_task_status(t.status),
        "progress": int((t.completed_count / t.total_count * 100)) if t.total_count > 0 else 0,
        "total": t.total_count,
        "completed": t.completed_count,
        "error": t.error
    })


@router.post("/tasks/{task_id}/start", response_model=ApiResponse)
async def start_eval_task(
    project_id: UUID,
    task_id: UUID,
    request: StartTaskRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """启动任务"""
    task = await db.execute(
        select(Task).where(and_(Task.id == task_id, Task.project_id == project_id))
    )
    t = task.scalar_one_or_none()
    if not t:
        raise NotFoundException("Task", task_id)

    if validate_task_status(t.status) == "completed":
        raise HTTPException(status_code=400, detail="任务已完成")

    t.status = "running"
    if request.note:
        t.note = request.note
    await db.commit()

    background_tasks.add_task(process_task_async, t.id)

    return ApiResponse.ok(message="任务已启动")


@router.post("/tasks/{task_id}/stop", response_model=ApiResponse)
async def stop_eval_task(
    project_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """停止任务"""
    task = await db.execute(
        select(Task).where(and_(Task.id == task_id, Task.project_id == project_id))
    )
    t = task.scalar_one_or_none()
    if not t:
        raise NotFoundException("Task", task_id)

    t.status = "stopped"
    t.end_time = datetime.utcnow().isoformat()

    # 同时更新关联的评估数据集状态
    detail = json.loads(t.detail) if t.detail else {}
    eval_dataset_ids = detail.get("eval_dataset_ids", [])
    if not eval_dataset_ids:
        eval_dataset_id = detail.get("eval_dataset_id")
        if eval_dataset_id:
            eval_dataset_ids = [eval_dataset_id]

    for ds_id in eval_dataset_ids:
        try:
            dataset = await db.get(EvalDataset, UUID(ds_id))
            if dataset:
                dataset.status = "stopped"
        except Exception:
            pass

    await db.commit()

    return ApiResponse.ok(message="任务已停止")


@router.delete("/tasks/{task_id}", response_model=ApiResponse)
async def delete_eval_task(
    project_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """删除任务"""
    task = await db.execute(
        select(Task).where(and_(Task.id == task_id, Task.project_id == project_id))
    )
    t = task.scalar_one_or_none()
    if not t:
        raise NotFoundException("Task", task_id)

    status = validate_task_status(t.status)
    if status in ["running"]:
        raise HTTPException(status_code=400, detail="运行中的任务无法删除")

    await db.delete(t)
    await db.commit()

    return ApiResponse.ok(message="任务已删除")


# ============ Eval Dataset Detail Endpoints ============

@router.get("/{eval_id}", response_model=ApiResponse)
async def get_eval_dataset(
    project_id: UUID,
    eval_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取评估数据集"""
    dataset = await eval_crud.get(db, eval_id)
    if not dataset or dataset.project_id != project_id:
        raise NotFoundException("Evaluation Dataset", eval_id)

    return ApiResponse.ok(data={
        "id": str(dataset.id),
        "name": dataset.name,
        "question_type": dataset.question_type,
        "status": dataset.status,
        "question_count": dataset.question_count
    })


@router.delete("/{eval_id}", response_model=ApiResponse)
async def delete_eval_dataset(
    project_id: UUID,
    eval_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """删除评估数据集"""
    dataset = await eval_crud.get(db, eval_id)
    if not dataset or dataset.project_id != project_id:
        raise NotFoundException("Evaluation Dataset", eval_id)

    await db.delete(dataset)
    await db.commit()

    return ApiResponse.ok(message="删除成功")


@router.post("/{eval_id}/evaluate", response_model=ApiResponse)
async def run_evaluation(
    project_id: UUID,
    eval_id: UUID,
    background_tasks: BackgroundTasks,
    request: Optional[RunEvalRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """运行评估"""
    dataset = await eval_crud.get(db, eval_id)
    if not dataset or dataset.project_id != project_id:
        raise NotFoundException("Evaluation Dataset", eval_id)

    dataset.status = "running"
    await db.commit()

    extra_data = json.loads(dataset.extra_data) if isinstance(dataset.extra_data, str) else (dataset.extra_data or {})
    selected_questions = extra_data.get("selected_questions")

    if selected_questions is not None and selected_questions > 0:
        total = min(selected_questions, dataset.question_count)
    else:
        total = dataset.question_count

    task = Task(
        project_id=project_id,
        task_type="model-evaluation",
        status="pending",
        detail=json.dumps({"eval_dataset_id": str(eval_id)}),
        total_count=total,
        completed_count=0
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    background_tasks.add_task(process_task_async, task.id)

    return ApiResponse.ok(
        data={"task_id": str(task.id)},
        message="评估任务已启动"
    )


# ============ Evaluation Results Endpoints ============

@router.get("/tasks/{task_id}/results", response_model=ApiResponse)
async def get_eval_results(
    project_id: UUID,
    task_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    type: Optional[str] = Query(None),
    is_correct: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """获取评估任务结果列表"""
    task = await db.execute(
        select(Task).where(and_(Task.id == task_id, Task.project_id == project_id))
    )
    t = task.scalar_one_or_none()
    if not t:
        raise NotFoundException("Task", task_id)

    results = await get_eval_results_by_task_id(
        db, task_id, page, page_size, type, is_correct
    )

    return PaginatedResponse.ok(
        items=results["items"],
        page=page,
        page_size=page_size,
        total=results["total"]
    )


@router.get("/tasks/{task_id}/results/stats", response_model=ApiResponse)
async def get_eval_results_stats_endpoint(
    project_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取评估任务结果统计"""
    task = await db.execute(
        select(Task).where(and_(Task.id == task_id, Task.project_id == project_id))
    )
    t = task.scalar_one_or_none()
    if not t:
        raise NotFoundException("Task", task_id)

    stats = await get_eval_results_stats(db, task_id)

    return ApiResponse.ok(data=stats)
