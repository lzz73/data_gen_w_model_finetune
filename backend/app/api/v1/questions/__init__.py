"""
Questions API Router
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from app.core.logging import logger

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import ApiResponse, PaginatedResponse
from app.api.v1.questions.folders import router as folders_router
from app.api.v1.questions.answer_folders import router as answer_folders_router
from app.api.v1.questions.qa_pairs import router as qa_pairs_router
from app.api.v1.questions.qa_folders import router as qa_folders_router
from app.api.v1.questions.qa_batches import router as qa_batches_router
from app.core.crud import CRUDBase
from app.core.database import AsyncSessionLocal, get_db
from app.core.exceptions import NotFoundException, ValidationException
from app.core.logging import log_failure, log_success
from app.models.models import Chunk, File, ModelConfig, Question, Task
from app.schemas.eval import TaskResponse
from app.schemas.question import GenerateAnswersRequest, QuestionCreateSchema, QuestionResponse

router = APIRouter()
router.include_router(folders_router, tags=["输出文件夹管理"])
router.include_router(answer_folders_router, tags=["答案输出文件夹管理"])
router.include_router(qa_pairs_router, tags=["问答对生成"])
router.include_router(qa_folders_router, tags=["问答对文件夹管理"])
router.include_router(qa_batches_router, tags=["问答对批次管理"])

# Initialize CRUD
question_crud = CRUDBase(Question)
task_crud = CRUDBase(Task)

# 从 Service 层导入共享的 LLM 辅助函数和常量
from app.services.llm_helpers import (  # noqa: E402
    DEFAULT_PRESET_PROMPT,
    LLM_SEMAPHORE,
    VALID_MODEL_TYPES,
    build_answer_prompt,
    build_full_doc_prompt,
    build_full_doc_system_prompt,
    build_system_prompt,
    build_user_prompt,
    build_user_prompt_with_context,
    call_generation_model,
    cancelling_tasks,
    evaluate_chunk_quality,
    extract_text_from_response,
    normalize_model_type,
    parse_generated_questions,
)


# 以下函数已移至 app.services.llm_helpers，通过上方 import 导入：
# evaluate_chunk_quality, build_system_prompt, build_user_prompt,
# build_answer_prompt, normalize_model_type, extract_text_from_response,
# parse_generated_questions, call_generation_model, LLM_SEMAPHORE


class GenerateRequest(BaseModel):
    """Request model for generating questions"""
    chunk_ids: Optional[List[UUID]] = Field(default=None, description="Optional subset of chunk ids; omitted means all project chunks")
    file_ids: Optional[List[UUID]] = Field(default=None, description="Optional subset of file ids to filter chunks by source file")
    model_id: UUID
    count: int = Field(3, ge=1, le=10)
    dirty_data_filter: bool = True  # 默认开启，使用 LLM 评估内容质量
    thinking_mode: bool = True
    preset_prompt: str = Field(default=DEFAULT_PRESET_PROMPT, min_length=1, max_length=4000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="LLM temperature for generation, higher = more creative")
    generation_mode: str = Field(default="all", description="生成模式: local / context_enhanced / full_doc / all")
    context_window: int = Field(default=2, ge=0, le=5, description="邻域增强模式：前后各取几个 chunk 作为上下文")
    full_doc_max_chars: int = Field(default=80000, description="全文模式：最大字符数，超出则先摘要再生成")


@dataclass(frozen=True)
class GenerateAnswersPreflightResult:
    task_id: UUID
    question_count: int
    original_question_count: int  # 原始问题数量（去重前）
    skipped_duplicates: int  # 跳过的重复问题数量
    request_payload: GenerateAnswersRequest


@dataclass(frozen=True)
class GenerateAnswersWorkerContext:
    model: ModelConfig
    questions: List[Question]
    question_chunk_map: dict[UUID, Chunk | None]


ANSWER_PROCESSING_STATUS = "processing"
ANSWER_PROCESSING_STALE_AFTER = timedelta(minutes=10)



async def process_generate_async(project_id: UUID, request: GenerateRequest, task_id: UUID):
    """Generate QA pairs in background."""
    async with AsyncSessionLocal() as db:
        task = await task_crud.get(db, task_id)
        try:
            if task:
                task.status = "running"
                task.progress = 0
                task.result = {"created_questions": 0, "processed_chunks": 0, "skipped_chunks": 0, "total_chunks": 0, "total_steps": 0}
                task.error = None
                await db.commit()

            model_result = await db.execute(
                select(ModelConfig).where(ModelConfig.id == request.model_id, ModelConfig.project_id == None)  # noqa: E711
            )
            model = model_result.scalar_one_or_none()
            if not model:
                return

            model_type = normalize_model_type(model.model_type, model.model_name)
            if model_type not in {"chat", "vlm"}:
                raise ValidationException("Selected model must be chat/vlm type", field="model_id")

            chunk_query = select(Chunk).where(Chunk.project_id == project_id)
            if request.chunk_ids:
                chunk_query = chunk_query.where(Chunk.id.in_(request.chunk_ids))

            chunk_result = await db.execute(chunk_query)
            chunks = chunk_result.scalars().all()
            if not chunks:
                if task:
                    task.status = "failed"
                    task.error = "No chunks available for generation"
                    task.progress = 0
                    task.result = {"created_questions": 0, "processed_chunks": 0, "skipped_chunks": 0, "total_chunks": 0, "total_steps": 0}
                    await db.commit()
                return

            created_count = 0
            skipped_count = 0
            processed_count = 0
            total_chunks = len(chunks)

            if task:
                task.result = {
                    "created_questions": 0,
                    "processed_chunks": 0,
                    "skipped_chunks": 0,
                    "total_chunks": total_chunks,
                    "total_steps": total_chunks,
                }
                await db.commit()

            # 每240个字符生成1个问题（参考easy-dataset）
            CHARS_PER_QUESTION = 240

            # --- 确定需要运行的模式 ---
            gen_mode = getattr(request, 'generation_mode', 'all')
            modes_to_run = []
            if gen_mode == "all":
                modes_to_run = ["local", "context_enhanced", "full_doc"]
            else:
                modes_to_run = [gen_mode]

            # --- 按文件分组 chunks ---
            from collections import defaultdict
            file_chunks_map: dict[UUID, List[Chunk]] = defaultdict(list)
            for chunk in chunks:
                file_chunks_map[chunk.file_id].append(chunk)

            # 对每个文件的 chunks 排序
            for file_id in file_chunks_map:
                file_chunks_map[file_id].sort(key=lambda c: c.name or "")

            def get_neighbor_chunks(chunk: Chunk, window: int):
                if not chunk.file_id or chunk.file_id not in file_chunks_map:
                    return [], []
                file_chunks = file_chunks_map[chunk.file_id]
                try:
                    idx = file_chunks.index(chunk)
                except ValueError:
                    return [], []
                return file_chunks[max(0, idx - window):idx], file_chunks[idx + 1:idx + 1 + window]

            async def process_single_chunk(chunk: Chunk, mode: str = "local") -> tuple[int, int, list, str]:
                """Process a single chunk and return (created_count, skipped, qa_items, source_tag)."""
                chunk_len = len(chunk.content) if chunk.content else 0
                source_tag = f"generated_{mode}" if gen_mode == "all" else "generated"

                logger.info(f"========== [Chunk 处理开始-{mode}] chunk_id={chunk.id}, chunk_name={chunk.name}, length={chunk_len} ==========")

                # LLM 质量评估
                logger.info(f"[步骤 1/2] 开始 LLM 质量评估...")
                can_generate, skip_reason = await evaluate_chunk_quality(model, chunk.content, request.temperature)
                if not can_generate:
                    logger.info(f"[步骤 1/2] LLM 评估结果：✗ 跳过 - {skip_reason}")
                    return 0, 1, [], source_tag

                logger.info(f"[步骤 1/2] LLM 评估结果：✓ 可以生成问题")
                logger.info(f"[步骤 2/2] 开始生成问题...")
                try:
                    chunk_len = len(chunk.content) if chunk.content else 0
                    dynamic_count = max(1, min(request.count, chunk_len // CHARS_PER_QUESTION))

                    if mode == "full_doc":
                        # 全文模式：当前 chunk + 全文上下文
                        system_prompt = build_full_doc_system_prompt(request.preset_prompt, dynamic_count)
                        full_content = file_full_contents.get(chunk.file_id, "")
                        user_prompt = build_full_doc_prompt(full_content, chunk.name or "未命名", request.thinking_mode)
                    elif mode == "context_enhanced":
                        ctx_window = getattr(request, 'context_window', 2)
                        prev_chunks, next_chunks = get_neighbor_chunks(chunk, ctx_window)
                        user_prompt = build_user_prompt_with_context(
                            chunk, prev_chunks, next_chunks, request.thinking_mode
                        )
                        system_prompt = build_system_prompt(request.preset_prompt, dynamic_count)
                    else:
                        system_prompt = build_system_prompt(request.preset_prompt, dynamic_count)
                        user_prompt = build_user_prompt(chunk, request.thinking_mode)

                    raw_text = await call_generation_model(model, system_prompt, user_prompt, request.temperature)
                    qa_pairs = parse_generated_questions(raw_text)[:dynamic_count]
                    if not qa_pairs:
                        logger.warning(f"LLM 返回空数组，尝试 fallback：chunk_id={chunk.id}")
                        qa_pairs = [{
                            "question": "这段文本的主要内容是什么？",
                            "answer": "",
                            "question_type": "summary"
                        }]

                    logger.info(f"[步骤 2/2] 问题生成结果：✓ 生成 {len(qa_pairs)} 个问题")
                    return len(qa_pairs), 0, qa_pairs, source_tag
                except Exception as e:
                    logger.error(f"处理异常：chunk_id={chunk.id}, error={str(e)}")
                    return 0, 1, [], source_tag

            # --- 构建 chunk-mode 任务列表 ---
            chunk_modes = []
            for chunk in chunks:
                if "local" in modes_to_run:
                    chunk_modes.append((chunk, "local"))
                if "context_enhanced" in modes_to_run:
                    chunk_modes.append((chunk, "context_enhanced"))
                if "full_doc" in modes_to_run:
                    chunk_modes.append((chunk, "full_doc"))

            # 预先为全文模式准备每个文件的全文内容（含摘要）
            file_full_contents: dict[UUID, str] = {}
            if "full_doc" in modes_to_run:
                full_doc_max_chars = getattr(request, 'full_doc_max_chars', 80000)
                for file_id, file_chunks_list in file_chunks_map.items():
                    file_result = await db.execute(select(File).where(File.id == file_id))
                    file_obj = file_result.scalar_one_or_none()
                    filename = file_obj.filename if file_obj else "unknown"
                    full_content = "\n\n".join(c.content for c in file_chunks_list if c.content)
                    if not full_content.strip():
                        file_full_contents[file_id] = ""
                        continue
                    full_len = len(full_content)
                    if full_len > full_doc_max_chars:
                        try:
                            summary_prompt = (
                                f"请对以下文档内容生成一份结构化摘要，包含：\n"
                                f"1. 文档主题和目的\n2. 各章节核心要点\n"
                                f"3. 关键事实、定义、结论\n4. 各部分逻辑关系\n\n"
                                f"【文档内容】\n{full_content[:full_doc_max_chars]}"
                            )
                            full_content = await call_generation_model(model, "", summary_prompt, request.temperature, json_output=False)
                        except Exception as e:
                            logger.error(f"[全文模式] 摘要生成失败: {str(e)}")
                    file_full_contents[file_id] = full_content

            # 计算实际总步骤数
            total_steps = len(chunk_modes)

            # 更新任务的总数
            if task:
                task.result = {
                    "created_questions": 0,
                    "processed_chunks": 0,
                    "skipped_chunks": 0,
                    "total_chunks": total_chunks,
                    "total_steps": total_steps,
                }
                await db.commit()

            # 并发控制
            process_semaphore = asyncio.Semaphore(5)

            async def process_with_semaphore(chunk: Chunk, mode: str, index: int) -> tuple[int, int, list, str, int]:
                async with process_semaphore:
                    result = await process_single_chunk(chunk, mode)
                    return (*result, index)

            # 创建输出目录
            import os
            from pathlib import Path
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            output_base = Path(f"data/{project_id}/generated-questions/{timestamp}")
            output_base.mkdir(parents=True, exist_ok=True)
            logger.info(f"[输出目录] 创建于 {output_base.absolute()}")

            # 并发处理局部 + 邻域增强
            tasks = [process_with_semaphore(chunk, mode, i) for i, (chunk, mode) in enumerate(chunk_modes)]

            # 按文件整理结果
            file_results: dict[UUID, dict] = {
                file_id: {"questions": [], "chunks_processed": 0, "chunks_skipped": 0}
                for file_id in file_chunks_map.keys()
            }

            completed = 0
            was_cancelled = False
            for coro in asyncio.as_completed(tasks):
                if task_id in cancelling_tasks:
                    logger.info(f"任务被取消：task_id={task_id}, processed={completed}")
                    cancelling_tasks.discard(task_id)
                    was_cancelled = True
                    break

                result = await coro
                batch_created, batch_skipped, qa_items, source_tag, chunk_index = result

                processed_count = completed + 1
                skipped_count += batch_skipped
                created_count += batch_created

                chunk = chunk_modes[chunk_index][0] if chunk_index < len(chunk_modes) else chunks[0]

                if chunk.file_id:
                    file_results[chunk.file_id]["chunks_processed"] += 1
                    file_results[chunk.file_id]["chunks_skipped"] += batch_skipped
                    if qa_items:
                        file_results[chunk.file_id]["questions"].extend(qa_items)

                for item in qa_items:
                    db.add(Question(
                        project_id=project_id,
                        chunk_id=chunk.id,
                        content=item["question"],
                        answer=None,
                        question_type=item["question_type"],
                        source=source_tag
                    ))

                if task:
                    task.progress = int(processed_count * 100 / max(total_steps, 1))
                    task.result = {
                        "created_questions": created_count,
                        "processed_chunks": processed_count,
                        "skipped_chunks": skipped_count,
                        "total_chunks": total_chunks,
                        "total_steps": total_steps,
                    }
                    await db.commit()

                completed += 1

            # 按文件保存问题到 JSON（取消时也保存已生成的部分）
            logger.info(f"[文件输出] 开始保存 {len(file_results)} 个文件的问题...")
            summary = {
                "task_id": str(task_id),
                "project_id": str(project_id),
                "total_chunks": total_chunks,
                "processed_chunks": processed_count,
                "skipped_chunks": skipped_count,
                "created_questions": created_count,
                "files": {}
            }

            for file_id, result in file_results.items():
                if not file_id:
                    continue

                # 获取文件信息
                file_result = await db.execute(select(File).where(File.id == file_id))
                file = file_result.scalar_one_or_none()
                filename = file.filename if file else "unknown"

                # 创建文件输出目录
                file_output_dir = output_base / str(file_id)
                file_output_dir.mkdir(parents=True, exist_ok=True)

                # 保存该文件的问题
                if result["questions"]:
                    questions_file = file_output_dir / "questions.json"
                    with open(questions_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "file_id": str(file_id),
                            "filename": filename,
                            "question_count": len(result["questions"]),
                            "questions": result["questions"]
                        }, f, ensure_ascii=False, indent=2)
                    logger.info(f"[文件输出] ✓ {filename}: {len(result['questions'])} 个问题")

                # 保存该文件的元数据
                metadata_file = file_output_dir / "metadata.json"
                with open(metadata_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "file_id": str(file_id),
                        "filename": filename,
                        "total_chunks": result["chunks_processed"] + result["chunks_skipped"],
                        "chunks_processed": result["chunks_processed"],
                        "chunks_skipped": result["chunks_skipped"],
                        "question_count": len(result["questions"])
                    }, f, ensure_ascii=False, indent=2)

                summary["files"][str(file_id)] = {
                    "filename": filename,
                    "question_count": len(result["questions"]),
                    "chunks_processed": result["chunks_processed"],
                    "chunks_skipped": result["chunks_skipped"]
                }

            # 保存总览
            summary_file = output_base / "summary.json"
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            logger.info(f"[文件输出] ✓ 保存 summary.json: {len(summary['files'])} 个文件，共 {created_count} 个问题")

            await db.commit()

            if task:
                task.status = "cancelled" if was_cancelled else "completed"
                task.progress = 100
                task.result = {
                    "created_questions": created_count,
                    "processed_chunks": processed_count,
                    "skipped_chunks": skipped_count,
                    "total_chunks": total_chunks,
                    "total_steps": total_steps,
                    "output_dir": str(output_base),
                }
                task.error = None
                await db.commit()

            status_label = "已取消（部分完成）" if was_cancelled else "完成"
            log_success(
                f"问答批量生成{status_label}",
                project_id=str(project_id),
                model_id=str(model.id),
                chunk_count=total_chunks,
                created_questions=created_count,
                skipped_chunks=skipped_count,
                output_dir=str(output_base)
            )
            logger.info(f"========== [任务{status_label}] 共处理 {processed_count}/{total_chunks} 个 chunk，生成 {created_count} 个问题，跳过 {skipped_count} 个 ==========")
        except Exception as e:
            if task:
                task.status = "failed"
                task.error = str(e)
                await db.commit()
            log_failure(
                "问答批量生成失败",
                project_id=str(project_id),
                model_id=str(request.model_id),
                error=str(e)
            )


async def prepare_generate_answers_worker_context(
    db: AsyncSession,
    project_id: UUID,
    request: GenerateAnswersRequest,
    task: Task | None,
) -> GenerateAnswersWorkerContext | None:
    model_result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == request.model_id, ModelConfig.project_id == None)  # noqa: E711
    )
    model = model_result.scalar_one_or_none()
    if not model:
        if task:
            task.status = "failed"
            task.error = "Selected model not found"
            await db.commit()
        return None

    model_type = normalize_model_type(model.model_type, model.model_name)
    if model_type not in {"chat", "vlm"}:
        raise ValidationException("Selected model must be chat/vlm type", field="model_id")

    stale_processing_cutoff = datetime.now(timezone.utc) - ANSWER_PROCESSING_STALE_AFTER

    # 构建问题查询 - 通过 Chunk -> File 关联
    # 如果 include_answered=True，则包含所有问题（不管 answer_status 和 answer 是什么）
    # 否则只包含 answer_status 为 pending/NULL 且 answer 为空的问题
    if request.include_answered:
        # 重新生成模式：包含所有问题，不管有没有答案
        eligible_answer_status = or_(
            Question.answer_status == "pending",
            Question.answer_status == "completed",  # 已有答案的问题也可以重新生成
            Question.answer_status == "failed",
            Question.answer_status.is_(None),
        )
    else:
        # 仅生成没有答案的问题
        eligible_answer_status = (
            or_(
                Question.answer_status == "pending",
                Question.answer_status == "failed",
                Question.answer_status.is_(None),
                (Question.answer_status == ANSWER_PROCESSING_STATUS) & (Question.updated_at < stale_processing_cutoff),
            )
            if request.include_failed
            else or_(
                Question.answer_status == "pending",
                Question.answer_status.is_(None),
            )
        )

    question_query = select(Question).join(Chunk, Question.chunk_id == Chunk.id).outerjoin(
        File, Chunk.file_id == File.id
    ).where(
        Question.project_id == project_id,
        eligible_answer_status,
    )

    # 只有在 not include_answered 时才过滤空答案
    if not request.include_answered:
        question_query = question_query.where(
            or_(
                Question.answer.is_(None),
                Question.answer == '',
            )
        )
    if request.question_ids:
        question_query = question_query.where(Question.id.in_(request.question_ids))

    # 按 folder_ids 过滤（问题生成的输出文件夹）
    # 从问题生成 output folder 的 summary.json 中读取该文件夹包含的 file_id 列表
    if request.folder_ids and len(request.folder_ids) > 0:
        from pathlib import Path
        import json
        from uuid import UUID

        valid_file_ids = []
        for folder_name in request.folder_ids:
            # 问题生成文件夹路径：data/{project_id}/generated-questions/{folder_name}
            summary_path = Path(f"data/{project_id}/generated-questions/{folder_name}/summary.json")
            if summary_path.exists():
                try:
                    with open(summary_path, "r", encoding="utf-8") as f:
                        summary = json.load(f)
                    file_ids_in_folder = [UUID(fid) for fid in summary.get("files", {}).keys()]
                    valid_file_ids.extend(file_ids_in_folder)
                except Exception as e:
                    logger.warning(f"Failed to read summary for folder {folder_name}: {e}")

        if valid_file_ids:
            valid_file_ids = list(set(valid_file_ids))
            question_query = question_query.where(File.id.in_(valid_file_ids))
        else:
            if task:
                task.status = "completed"
                task.progress = 100
                # 保留原有的 total_questions
                task.result = {
                    "created_answers": 0,
                    "processed_questions": 0,
                    "total_questions": task.result.get("total_questions", 0) if task.result else 0
                }
                task.error = None
                await db.commit()
            return None

    question_result = await db.execute(question_query)
    questions = question_result.scalars().all()
    logger.info(f"[prepare_worker_context] 查询到 {len(questions)} 个问题, request.question_ids={len(request.question_ids) if request.question_ids else 0}")
    if not questions:
        if task:
            task.status = "completed"
            task.progress = 100
            # 保留原有的 total_questions
            task.result = {
                "created_answers": 0,
                "processed_questions": 0,
                "total_questions": task.result.get("total_questions", 0) if task.result else 0
            }
            task.error = None
            await db.commit()
        return None

    question_chunk_map: dict[UUID, Chunk | None] = {}
    chunk_ids = [q.chunk_id for q in questions if q.chunk_id]
    if chunk_ids:
        chunk_result = await db.execute(select(Chunk).where(Chunk.id.in_(chunk_ids)))
        chunks = {chunk.id: chunk for chunk in chunk_result.scalars().all()}
        question_chunk_map = {q.id: chunks.get(q.chunk_id) for q in questions}

    return GenerateAnswersWorkerContext(
        model=model,
        questions=questions,
        question_chunk_map=question_chunk_map,
    )


async def process_generate_answers_async(project_id: UUID, request: GenerateAnswersRequest, task_id: UUID):
    """Generate answers in background for questions without answers."""
    logger.info(f"答案生成任务开始：task_id={task_id}, project_id={project_id}")

    async with AsyncSessionLocal() as db:
        task = await task_crud.get(db, task_id)
        try:
            # 保存初始的 total_questions 和跳过信息，后续不要覆盖
            initial_total_questions = task.result.get("total_questions", 0) if task and task.result else 0
            initial_skipped_duplicates = task.result.get("skipped_duplicates", 0) if task and task.result else 0
            initial_original_questions = task.result.get("original_questions", initial_total_questions) if task and task.result else initial_total_questions

            if task:
                task.status = "running"
                task.progress = 0
                # 保留 total_questions 和跳过信息，不要重置为 0
                if task.result:
                    task.result = {
                        "created_answers": 0,
                        "processed_questions": 0,
                        "total_questions": initial_total_questions,
                        "original_questions": initial_original_questions,
                        "skipped_duplicates": initial_skipped_duplicates
                    }
                else:
                    task.result = {
                        "created_answers": 0,
                        "processed_questions": 0,
                        "total_questions": initial_total_questions,
                        "original_questions": initial_original_questions,
                        "skipped_duplicates": initial_skipped_duplicates
                    }
                task.error = None
                await db.commit()

            worker_context = await prepare_generate_answers_worker_context(db, project_id, request, task)
            if worker_context is None:
                logger.warning(f"答案生成任务无问题可处理：task_id={task_id}")
                return

            model = worker_context.model
            questions = worker_context.questions
            question_chunk_map = worker_context.question_chunk_map

            created_count = 0
            processed_count = 0
            claimed_question_count = 0
            # 失败原因统计
            failed_reasons = {
                "missing_chunk": 0,
                "too_short": 0,
                "generation_error": 0
            }

            async def generate_answer_for_question(question: Question) -> tuple[bool, str, str | None, UUID]:
                logger.info(f"[答案生成] 开始处理问题: question_id={question.id}")
                try:
                    chunk = question_chunk_map.get(question.id)
                    chunk_content = chunk.content if chunk else ""

                    if not chunk_content or not chunk_content.strip():
                        logger.warning(f"答案生成跳过: 问题 {question.id} 没有关联的chunk内容")
                        return False, "", "missing_chunk", question.id

                    user_prompt = build_answer_prompt(question.content, chunk_content)
                    answer = await call_generation_model(model, "", user_prompt, request.temperature, json_output=False)
                    answer = answer.strip()

                    if len(answer) < 20:
                        logger.warning(f"答案生成跳过: 问题 {question.id} 生成的答案太短 ({len(answer)} 字符)")
                        return False, "", "too_short", question.id

                    logger.info(f"[答案生成] 问题处理成功: question_id={question.id}, answer_length={len(answer)}")
                    return True, answer, None, question.id
                except Exception as e:
                    logger.error(f"答案生成异常: 问题 {question.id}, 错误: {str(e)}")
                    return False, "", "generation_error", question.id

            BATCH_SIZE = 8
            semaphore = asyncio.Semaphore(BATCH_SIZE)
            stale_processing_cutoff = datetime.now(timezone.utc) - ANSWER_PROCESSING_STALE_AFTER

            async def process_with_semaphore(question: Question) -> tuple[bool, str, str | None, UUID]:
                async with semaphore:
                    return await generate_answer_for_question(question)

            # 预先抢占所有问题（而不是分批抢占）
            claimed_questions = []
            skipped_claim_reasons = {"already_processing": 0, "condition_not_met": 0}
            for question in questions:
                if request.include_answered:
                    claim_condition = or_(
                        Question.answer_status.in_(["pending", "failed", "completed"]),
                        Question.answer_status.is_(None),
                        (Question.answer_status == ANSWER_PROCESSING_STATUS) & (Question.updated_at < stale_processing_cutoff),
                    )
                else:
                    claim_condition = and_(
                        or_(
                            Question.answer.is_(None),
                            Question.answer == '',
                        ),
                        or_(
                            Question.answer_status.in_(["pending", "failed"]),
                            Question.answer_status.is_(None),
                            (Question.answer_status == ANSWER_PROCESSING_STATUS) & (Question.updated_at < stale_processing_cutoff),
                        )
                    )

                claim_result = await db.execute(
                    update(Question)
                    .where(
                        Question.id == question.id,
                        claim_condition,
                    )
                    .values(answer_status=ANSWER_PROCESSING_STATUS)
                )
                if claim_result.rowcount == 1:
                    claimed_questions.append(question)
                else:
                    # 记录未能抢占的原因
                    logger.debug(f"[答案生成] 未能抢占问题 {question.id}, answer_status={question.answer_status}")
                    if question.answer_status == ANSWER_PROCESSING_STATUS:
                        skipped_claim_reasons["already_processing"] += 1
                    else:
                        skipped_claim_reasons["condition_not_met"] += 1
            await db.commit()
            claimed_question_count += len(claimed_questions)

            if skipped_claim_reasons["already_processing"] > 0 or skipped_claim_reasons["condition_not_met"] > 0:
                logger.info(f"[答案生成] 抢占统计: 成功={len(claimed_questions)}, 已处理中={skipped_claim_reasons['already_processing']}, 条件不满足={skipped_claim_reasons['condition_not_met']}")

            # 使用实际抢占的问题数量作为总数（而不是 preflight 时的数量）
            actual_total_questions = len(claimed_questions)
            logger.info(f"[答案生成] 实际抢占 {actual_total_questions} 个问题，preflight 预估 {initial_total_questions} 个")

            # 创建任务列表（提前创建所有任务）
            tasks = [process_with_semaphore(q) for q in claimed_questions]

            # 使用 as_completed 实现进度逐个更新
            completed = 0
            was_cancelled = False
            for coro in asyncio.as_completed(tasks):
                # 检查任务是否被取消
                if task_id in cancelling_tasks:
                    logger.info(f"答案任务被取消：task_id={task_id}, processed={completed}")
                    cancelling_tasks.discard(task_id)
                    was_cancelled = True
                    break

                logger.debug(f"[答案生成] 等待下一个结果... completed={completed}/{actual_total_questions}")
                result = await coro
                success, answer, error_reason, question_id = result
                logger.info(f"[答案生成] 收到结果: question_id={question_id}, success={success}, error_reason={error_reason}")

                # 通过 question_id 找到对应的问题对象
                question = next((q for q in claimed_questions if q.id == question_id), None)
                if not question:
                    continue

                completed += 1
                processed_count = completed
                if success and answer:
                    question.answer = answer
                    question.generation_status = "answered"
                    question.answer_status = "completed"
                    question.answer_error = None
                    created_count += 1
                else:
                    question.generation_status = "answer_failed"
                    question.answer_status = "failed"
                    question.answer_error = error_reason
                    # 统计失败原因
                    if error_reason and error_reason in failed_reasons:
                        failed_reasons[error_reason] += 1

                await db.commit()

                # 每个问题完成后立即更新进度（使用实际抢占的数量）
                if task:
                    task.progress = int(processed_count * 100 / max(actual_total_questions, 1))
                    task.result = {
                        "created_answers": created_count,
                        "processed_questions": processed_count,
                        "total_questions": actual_total_questions,
                        "original_questions": initial_original_questions,
                        "skipped_duplicates": initial_skipped_duplicates,
                        "failed_reasons": failed_reasons.copy(),
                    }
                    await db.commit()

            await db.commit()

            logger.info(f"[答案生成完成] created_count={created_count}, processed_count={processed_count}")

            # 保存答案输出到文件夹（参考问题生成的输出结构）
            output_dir = None
            if created_count > 0:
                try:
                    from pathlib import Path
                    from collections import defaultdict

                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    output_base = Path(f"data/{project_id}/generated-answers/{timestamp}")
                    output_base.mkdir(parents=True, exist_ok=True)
                    logger.info(f"[答案输出目录] 创建于 {output_base.absolute()}")

                    # 按文件分组问题
                    file_questions_map: dict[UUID, list] = defaultdict(list)
                    for question in questions:
                        if question.answer and question.answer.strip():
                            chunk = question_chunk_map.get(question.id)
                            if chunk and chunk.file_id:
                                file_questions_map[chunk.file_id].append(question)
                                logger.debug(f"[答案分组] 问题 {question.id} 添加到文件 {chunk.file_id}")

                    logger.info(f"[答案文件分组] 共 {len(questions)} 个问题，{created_count} 个有答案，来自 {len(file_questions_map)} 个文件")
                    logger.info(f"[答案文件分组] file_questions_map keys: {list(file_questions_map.keys())}")

                    # 保存 summary
                    summary = {
                        "task_id": str(task_id),
                        "project_id": str(project_id),
                        "total_questions": len(questions),
                        "processed_questions": processed_count,
                        "created_answers": created_count,
                        "files": {}
                    }

                    for file_id, file_questions in file_questions_map.items():
                        if not file_id:
                            continue

                        # 获取文件信息
                        file_result = await db.execute(select(File).where(File.id == file_id))
                        file = file_result.scalar_one_or_none()
                        filename = file.filename if file else "unknown"

                        # 创建文件输出目录
                        file_output_dir = output_base / str(file_id)
                        file_output_dir.mkdir(parents=True, exist_ok=True)

                        # 保存该文件的问题和答案
                        qa_data = []
                        for q in file_questions:
                            if q.answer:
                                qa_data.append({
                                    "question_id": str(q.id),
                                    "question": q.content,
                                    "answer": q.answer,
                                    "question_type": q.question_type
                                })

                        if qa_data:
                            answers_file = file_output_dir / "answers.json"
                            with open(answers_file, "w", encoding="utf-8") as f:
                                json.dump({
                                    "file_id": str(file_id),
                                    "filename": filename,
                                    "answer_count": len(qa_data),
                                    "answers": qa_data
                                }, f, ensure_ascii=False, indent=2)
                            logger.info(f"[答案输出] ✓ {filename}: {len(qa_data)} 个答案")

                        # 保存元数据
                        metadata_file = file_output_dir / "metadata.json"
                        with open(metadata_file, "w", encoding="utf-8") as f:
                            json.dump({
                                "file_id": str(file_id),
                                "filename": filename,
                                "answer_count": len(qa_data)
                            }, f, ensure_ascii=False, indent=2)

                        summary["files"][str(file_id)] = {
                            "filename": filename,
                            "answer_count": len(qa_data)
                        }

                    # 保存总览
                    summary_file = output_base / "summary.json"
                    with open(summary_file, "w", encoding="utf-8") as f:
                        json.dump(summary, f, ensure_ascii=False, indent=2)
                    logger.info(f"[答案输出] ✓ 保存 summary.json: {len(summary['files'])} 个文件，共 {created_count} 个答案")

                    output_dir = str(output_base)

                except Exception as e:
                    logger.error(f"保存答案输出文件夹失败：{e}")
                    import traceback
                    logger.error(traceback.format_exc())

            if task:
                task.status = "cancelled" if was_cancelled else "completed"
                task.progress = 100
                task.result = {
                    "created_answers": created_count,
                    "processed_questions": processed_count,
                    "total_questions": actual_total_questions,
                    "original_questions": initial_original_questions,
                    "skipped_duplicates": initial_skipped_duplicates,
                    "failed_reasons": failed_reasons,
                }
                if output_dir:
                    task.result["output_dir"] = output_dir
                task.error = None
                await db.commit()

            # 计算失败总数
            failed_count = sum(failed_reasons.values())
            status_label = "已取消（部分完成）" if was_cancelled else "完成"
            log_success(
                f"答案批量生成{status_label}",
                project_id=str(project_id),
                model_id=str(model.id),
                question_count=claimed_question_count,
                created_answers=created_count,
                failed_answers=failed_count,
                failed_reasons=failed_reasons,
                output_dir=output_dir
            )
        except Exception as e:
            if task:
                task.status = "failed"
                task.error = str(e)
                await db.commit()
            log_failure(
                "答案批量生成失败",
                project_id=str(project_id),
                model_id=str(request.model_id),
                error=str(e)
            )


@router.post("/generate", response_model=ApiResponse)
async def generate_questions(
    project_id: UUID,
    request: GenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Generate questions from chunks using LLM in background."""
    model_result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == request.model_id, ModelConfig.project_id == None)  # noqa: E711
    )
    model = model_result.scalar_one_or_none()
    if not model:
        raise ValidationException("Selected model not found", field="model_id")

    model_type = normalize_model_type(model.model_type, model.model_name)
    if model_type not in {"chat", "vlm"}:
        raise ValidationException("Selected model must be chat/vlm type", field="model_id")
    if not model.api_key:
        raise ValidationException("Selected model is missing API Key", field="model_id")

    # chunk_ids 优先级最高，file_ids 次之，否则取项目下所有 chunk
    chunk_query = select(Chunk.id).where(Chunk.project_id == project_id)
    if request.chunk_ids:
        chunk_query = chunk_query.where(Chunk.id.in_(request.chunk_ids))
    elif request.file_ids:
        chunk_query = chunk_query.where(Chunk.file_id.in_(request.file_ids))

    chunk_result = await db.execute(chunk_query)
    valid_chunk_ids = [row[0] for row in chunk_result.all()]
    if not valid_chunk_ids:
        raise ValidationException("No valid chunks found", field="chunk_ids" if request.chunk_ids else "file_ids")

    # 计算实际总步骤数（考虑多模式）
    gen_mode = getattr(request, 'generation_mode', 'all')
    modes_count = 3 if gen_mode == "all" else 1
    total_steps = len(valid_chunk_ids) * modes_count

    task = Task(
        project_id=project_id,
        task_type="generate",
        status="pending",
        progress=0,
        result={"created_questions": 0, "processed_chunks": 0, "skipped_chunks": 0, "total_chunks": len(valid_chunk_ids), "total_steps": total_steps},
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    request_payload = request.model_copy(update={"chunk_ids": valid_chunk_ids, "file_ids": None})
    asyncio.create_task(process_generate_async(project_id, request_payload, task.id))

    # 计算问题数预估（每 240 字符 1 个问题）
    chunk_result_for_stats = await db.execute(
        select(Chunk.content).where(Chunk.id.in_(valid_chunk_ids))
    )
    chunks_content = chunk_result_for_stats.scalars().all()
    total_chars = sum(len(c or "") for c in chunks_content)
    estimated_questions = max(1, min(request.count * len(valid_chunk_ids), total_chars // 240))

    return ApiResponse.ok(
        data={
            "chunk_count": len(valid_chunk_ids),
            "total_chars": total_chars,
            "estimated_questions": estimated_questions,
            "total_chunks": len(valid_chunk_ids),
            "total_steps": total_steps,
            "status": "processing",
            "task_id": str(task.id)
        },
        message="Question generation started in background"
    )


async def prepare_generate_answers_preflight(
    db: AsyncSession,
    project_id: UUID,
    request: GenerateAnswersRequest,
) -> GenerateAnswersPreflightResult:
    if request.question_ids is not None and len(request.question_ids) == 0:
        raise ValidationException("question_ids cannot be empty", field="question_ids")

    model_result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == request.model_id, ModelConfig.project_id == None)  # noqa: E711
    )
    model = model_result.scalar_one_or_none()
    if not model:
        raise ValidationException("Selected model not found", field="model_id")

    model_type = normalize_model_type(model.model_type, model.model_name)
    if model_type not in {"chat", "vlm"}:
        raise ValidationException("Selected model must be chat/vlm type", field="model_id")
    if not model.api_key:
        raise ValidationException("Selected model is missing API Key", field="model_id")

    stale_processing_cutoff = datetime.now(timezone.utc) - ANSWER_PROCESSING_STALE_AFTER

    # 用于跟踪原始问题数量和跳过的重复问题
    original_question_count = 0
    skipped_duplicates = 0

    # 按 folder_ids 过滤（问题生成的输出文件夹）
    # 按 folder_ids 过滤（问题生成的输出文件夹）
    # 直接从文件夹的 questions.json 读取问题内容，然后查询数据库匹配的问题 ID
    valid_question_ids = []
    if request.folder_ids and len(request.folder_ids) > 0:
        from pathlib import Path
        import json
        from uuid import UUID

        # 从文件夹中读取问题内容（以文件夹为准）
        folder_question_contents = set()
        # 同时统计原始问题数量（不去重）
        original_folder_question_count = 0
        for folder_name in request.folder_ids:
            summary_path = Path(f"data/{project_id}/generated-questions/{folder_name}/summary.json")
            if summary_path.exists():
                try:
                    with open(summary_path, "r", encoding="utf-8") as f:
                        summary = json.load(f)
                    folder_path = summary_path.parent
                    for file_id in summary.get("files", {}).keys():
                        questions_file = folder_path / file_id / "questions.json"
                        if questions_file.exists():
                            with open(questions_file, "r", encoding="utf-8") as f:
                                q_data = json.load(f)
                            questions_list = q_data.get("questions", [])
                            original_folder_question_count += len(questions_list)
                            for q in questions_list:
                                q_content = q.get("question")
                                if q_content:
                                    folder_question_contents.add(q_content)
                except Exception as e:
                    logger.warning(f"Failed to read questions from folder {folder_name}: {e}")

        if not folder_question_contents:
            raise ValidationException("No questions found in selected folders", field="folder_ids")

        original_question_count = original_folder_question_count

        # 从数据库查询匹配的问题 ID（每个问题内容只取第一个 ID）
        question_result = await db.execute(
            select(Question.id, Question.content)
            .where(Question.project_id == project_id)
        )

        # 按问题内容去重，只保留文件夹中存在的问题
        seen_contents = set()
        for row in question_result.all():
            q_id, q_content = row
            if q_content in folder_question_contents and q_content not in seen_contents:
                valid_question_ids.append(q_id)
                seen_contents.add(q_content)

        skipped_duplicates = original_question_count - len(valid_question_ids)
        logger.info(f"[preflight] folder_ids={request.folder_ids}, original_questions={original_question_count}, unique_questions={len(folder_question_contents)}, valid_question_ids={len(valid_question_ids)}, skipped_duplicates={skipped_duplicates}, include_answered={request.include_answered}")

        if not valid_question_ids:
            raise ValidationException("No questions found in selected folders", field="folder_ids")
    else:
        # 没有指定 folder_ids，查询数据库
        # 构建问题查询 - 通过 Chunk -> File 关联
        # 如果 include_answered=True，则包含所有问题（不管 answer_status 和 answer 是什么）
        # 否则只包含 answer_status 为 pending/NULL 且 answer 为空的问题
        if request.include_answered:
            # 重新生成模式：包含所有问题，不管有没有答案
            eligible_answer_status = or_(
                Question.answer_status == "pending",
                Question.answer_status == "completed",  # 已有答案的问题也可以重新生成
                Question.answer_status == "failed",
                Question.answer_status.is_(None),
            )
        else:
            # 仅生成没有答案的问题
            eligible_answer_status = (
                or_(
                    Question.answer_status == "pending",
                    Question.answer_status == "failed",
                    Question.answer_status.is_(None),
                    (Question.answer_status == ANSWER_PROCESSING_STATUS) & (Question.updated_at < stale_processing_cutoff),
                )
                if request.include_failed
                else or_(
                    Question.answer_status == "pending",
                    Question.answer_status.is_(None),
                )
            )

        question_query = select(Question.id).join(Chunk, Question.chunk_id == Chunk.id).outerjoin(
            File, Chunk.file_id == File.id
        ).where(
            Question.project_id == project_id,
            eligible_answer_status,
        )

        # 只有在 not include_answered 时才过滤空答案
        if not request.include_answered:
            question_query = question_query.where(
                or_(
                    Question.answer.is_(None),
                    Question.answer == '',
                )
            )

        # 按 question_ids 过滤
        if request.question_ids:
            question_query = question_query.where(Question.id.in_(request.question_ids))

        question_result = await db.execute(question_query)
        valid_question_ids = [row[0] for row in question_result.all()]
        # 没有指定 folder_ids 时，原始问题数等于有效问题数
        original_question_count = len(valid_question_ids)
        skipped_duplicates = 0

    logger.info(f"[preflight] project_id={project_id}, folder_ids={request.folder_ids}, valid_question_ids count={len(valid_question_ids)}, original_count={original_question_count}, skipped_duplicates={skipped_duplicates}")

    if not valid_question_ids:
        raise ValidationException("No questions found", field="question_ids")

    task = Task(
        project_id=project_id,
        task_type="generate_answers",
        status="pending",
        progress=0,
        result={
            "created_answers": 0,
            "processed_questions": 0,
            "total_questions": len(valid_question_ids),
            "original_questions": original_question_count,
            "skipped_duplicates": skipped_duplicates
        },
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    return GenerateAnswersPreflightResult(
        task_id=task.id,
        question_count=len(valid_question_ids),
        original_question_count=original_question_count,
        skipped_duplicates=skipped_duplicates,
        request_payload=request.model_copy(update={"question_ids": valid_question_ids, "folder_ids": None}),
    )


@router.post("/generate-answers", response_model=ApiResponse)
async def generate_answers(
    project_id: UUID,
    request: GenerateAnswersRequest,
    db: AsyncSession = Depends(get_db)
):
    """Generate answers for questions without answers using LLM in background."""
    preflight = await prepare_generate_answers_preflight(db, project_id, request)

    # 创建后台任务，添加日志
    task_id = preflight.task_id
    logger.info(f"创建答案生成后台任务：task_id={task_id}, question_count={preflight.question_count}")

    async def run_task():
        try:
            await process_generate_answers_async(project_id, preflight.request_payload, task_id)
        except Exception as e:
            logger.error(f"答案生成后台任务失败：task_id={task_id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    asyncio.create_task(run_task())

    return ApiResponse.ok(
        data={
            "question_count": preflight.question_count,
            "original_question_count": preflight.original_question_count,
            "skipped_duplicates": preflight.skipped_duplicates,
            "status": "processing",
            "task_id": str(preflight.task_id)
        },
        message="Answer generation started in background"
    )


@router.get("/answer-tasks/latest", response_model=ApiResponse)
async def get_latest_answer_task(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get latest answer generation task for a project."""
    tasks, _ = await task_crud.get_multi(
        db,
        skip=0,
        limit=1,
        filters={"project_id": project_id, "task_type": "generate_answers"},
        order_by="created_at",
        descending=True
    )

    task = tasks[0] if tasks else None
    return ApiResponse.ok(data=TaskResponse.model_validate(task) if task else None)


@router.post("/tasks/{task_id}/cancel", response_model=ApiResponse)
async def cancel_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    """Cancel a running generation task."""
    task = await task_crud.get(db, task_id)
    if not task:
        raise NotFoundException("Task not found")

    if task.status not in ["running", "pending"]:
        return ApiResponse.ok(message=f"Task already completed with status: {task.status}")

    # 立即更新数据库状态为 cancelling，让前端能立刻看到
    task.status = "cancelling"
    await db.commit()

    # 设置取消标志（后台任务会在下一轮迭代检测到并保存已生成内容）
    cancelling_tasks.add(task_id)

    return ApiResponse.ok(message="Task cancellation requested")


@router.get("/tasks/latest", response_model=ApiResponse)
async def get_latest_generate_task(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get latest question generation task for a project."""
    tasks, _ = await task_crud.get_multi(
        db,
        skip=0,
        limit=1,
        filters={"project_id": project_id, "task_type": "generate"},
        order_by="created_at",
        descending=True
    )

    task = tasks[0] if tasks else None
    return ApiResponse.ok(data=TaskResponse.model_validate(task) if task else None)


@router.get("", response_model=PaginatedResponse)
async def list_questions(
    project_id: UUID,
    chunk_id: Optional[UUID] = Query(None),
    batch_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """List questions for a project with file info"""
    filters = {"project_id": project_id}
    if chunk_id:
        filters["chunk_id"] = chunk_id
    if batch_id:
        filters["batch_id"] = batch_id

    skip = (page - 1) * page_size

    questions, total = await question_crud.get_multi(
        db,
        skip=skip,
        limit=page_size,
        filters=filters,
        order_by="created_at",
        descending=True
    )

    # 批量获取 chunk 和 file 信息
    chunk_ids = [q.chunk_id for q in questions if q.chunk_id]
    chunk_file_map = {}
    if chunk_ids:
        chunk_result = await db.execute(
            select(Chunk.id, Chunk.file_id, File.filename)
            .join(File, Chunk.file_id == File.id, isouter=True)
            .where(Chunk.id.in_(chunk_ids))
        )
        chunk_file_map = {row.id: {"file_id": row.file_id, "file_name": row.filename} for row in chunk_result.fetchall()}

    # 构建响应数据，添加 file_id 和 file_name
    question_responses = []
    for q in questions:
        q_dict = QuestionResponse.model_validate(q).model_dump()
        if q.chunk_id and q.chunk_id in chunk_file_map:
            q_dict["file_id"] = chunk_file_map[q.chunk_id]["file_id"]
            q_dict["file_name"] = chunk_file_map[q.chunk_id]["file_name"]
        question_responses.append(q_dict)

    return PaginatedResponse.ok(
        items=question_responses,
        page=page,
        page_size=page_size,
        total=total
    )


@router.put("/{question_id}", response_model=ApiResponse)
async def update_question(
    project_id: UUID,
    question_id: UUID,
    question: QuestionCreateSchema,
    db: AsyncSession = Depends(get_db)
):
    """Update question"""
    db_question = await question_crud.get(db, question_id)
    if not db_question or db_question.project_id != project_id:
        raise NotFoundException("Question", question_id)

    updated_question = await question_crud.update(db, db_question, question)
    return ApiResponse.ok(
        data=QuestionResponse.model_validate(updated_question),
        message="Question updated successfully"
    )


@router.delete("/{question_id}", response_model=ApiResponse)
async def delete_question(
    project_id: UUID,
    question_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete question"""
    question = await question_crud.get(db, question_id)
    if not question or question.project_id != project_id:
        raise NotFoundException("Question", question_id)

    await question_crud.delete(db, question_id)
    return ApiResponse.ok(message="Question deleted successfully")
