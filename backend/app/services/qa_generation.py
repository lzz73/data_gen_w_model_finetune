"""
QA Pair Generation Service

一步式问答对生成：对每个 chunk 同时生成问题和答案，输出到文件夹管理。
"""
import asyncio
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.exceptions import ValidationException
from app.core.logging import log_failure, log_success, logger
from app.models.models import Chunk, File, ModelConfig, Question, Task
from app.services.template_qa_engine import generate_template_qa_pairs, parse_chunk_content, reset_desensitize_state
from app.services.llm_helpers import (
    CHARS_PER_QUESTION,
    LLM_SEMAPHORE,
    build_answer_prompt,
    build_full_doc_prompt,
    build_full_doc_system_prompt,
    build_system_prompt,
    build_user_prompt,
    build_user_prompt_with_context,
    call_generation_model,
    cancelling_tasks,
    evaluate_chunk_quality,
    normalize_model_type,
    parse_generated_questions,
)

# 并发控制：每个 chunk 需要 2+ 次 LLM 调用，限制同时处理的 chunk 数
PROCESS_SEMAPHORE = asyncio.Semaphore(10)


async def process_generate_qa_async(
    project_id: UUID,
    model_id: UUID,
    answer_model_id: UUID | None,
    count: int,
    chunk_ids: List[UUID] | None,
    file_ids: List[UUID] | None,
    dirty_data_filter: bool,
    thinking_mode: bool,
    preset_prompt: str,
    temperature: float,
    answer_temperature: float,
    task_id: UUID,
    generation_mode: str = "all",
    context_window: int = 2,
    full_doc_max_chars: int = 80000,
    batch_id: UUID | None = None,
):
    """一步式问答对生成后台任务。

    generation_mode 决定生成方式：
    - "local": 仅基于当前 chunk 生成（事实型）
    - "context_enhanced": 带前后 chunk 上下文生成（减少片面性）
    - "full_doc": 按文件全文生成全局性问答（总结型、推理型）
    - "all": 三种模式都跑，source 区分来源
    """
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        try:
            if task:
                task.status = "running"
                task.progress = 0
                # 保留已有 result 中的 batch_id 和 total 数据（API 端点已设置 total_chunks）
                existing_result = task.result or {}
                existing_batch_id = existing_result.get("batch_id")
                task.result = {
                    "created_questions": 0,
                    "created_answers": 0,
                    "processed_chunks": 0,
                    "skipped_chunks": 0,
                    "total_chunks": existing_result.get("total_chunks", 0),
                    "total_steps": existing_result.get("total_steps", 0),
                    "failed_answers": 0,
                }
                if existing_batch_id:
                    task.result["batch_id"] = existing_batch_id
                task.error = None
                await db.commit()

            # --- 加载问题生成模型 ---
            model_result = await db.execute(
                select(ModelConfig).where(
                    ModelConfig.id == model_id,
                    ModelConfig.project_id == None,  # noqa: E711
                )
            )
            question_model = model_result.scalar_one_or_none()
            if not question_model:
                raise ValidationException("问题生成模型未找到", field="model_id")

            model_type = normalize_model_type(question_model.model_type, question_model.model_name)
            if model_type not in {"chat", "vlm"}:
                raise ValidationException("问题生成模型必须是 chat/vlm 类型", field="model_id")

            # --- 加载答案生成模型（如未指定则与问题模型相同）---
            if answer_model_id and answer_model_id != model_id:
                answer_model_result = await db.execute(
                    select(ModelConfig).where(
                        ModelConfig.id == answer_model_id,
                        ModelConfig.project_id == None,  # noqa: E711
                    )
                )
                answer_model = answer_model_result.scalar_one_or_none()
                if not answer_model:
                    raise ValidationException("答案生成模型未找到", field="answer_model_id")
            else:
                answer_model = question_model

            # --- 加载 chunks ---
            chunk_query = select(Chunk).where(Chunk.project_id == project_id)
            if chunk_ids:
                chunk_query = chunk_query.where(Chunk.id.in_(chunk_ids))
            elif file_ids:
                chunk_query = chunk_query.where(Chunk.file_id.in_(file_ids))

            chunk_result = await db.execute(chunk_query)
            chunks = chunk_result.scalars().all()
            if not chunks:
                if task:
                    task.status = "failed"
                    task.error = "没有可用的文本块"
                    task.progress = 0
                    await db.commit()
                return

            total_chunks = len(chunks)
            created_questions = 0
            created_answers = 0
            skipped_chunks = 0
            failed_answers = 0
            processed_count = 0

            if task:
                task.result = {
                    "created_questions": 0,
                    "created_answers": 0,
                    "processed_chunks": 0,
                    "skipped_chunks": 0,
                    "total_chunks": total_chunks,
                    "total_steps": total_chunks,
                    "failed_answers": 0,
                }
                await db.commit()

            # --- 创建输出目录 ---
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            output_base = Path(f"data/{project_id}/generated-qa/{timestamp}")
            output_base.mkdir(parents=True, exist_ok=True)
            logger.info(f"[问答对生成] 输出目录: {output_base.absolute()}")

            # --- 按文件分组 chunks ---
            file_chunks_map: dict[UUID, List[Chunk]] = defaultdict(list)
            for chunk in chunks:
                if chunk.file_id:
                    file_chunks_map[chunk.file_id].append(chunk)

            # --- 对每个文件的 chunks 按索引排序，以便邻域增强查找前后 chunk ---
            for file_id in file_chunks_map:
                file_chunks_map[file_id].sort(key=lambda c: c.name or "")

            # --- 构建按文件查找的 chunk 序列索引用于邻域增强 ---
            def get_neighbor_chunks(chunk: Chunk, window: int):
                """获取同文件中前后 window 个 chunk"""
                if not chunk.file_id or chunk.file_id not in file_chunks_map:
                    return [], []
                file_chunks = file_chunks_map[chunk.file_id]
                try:
                    idx = file_chunks.index(chunk)
                except ValueError:
                    return [], []
                prev_chunks = file_chunks[max(0, idx - window):idx]
                next_chunks = file_chunks[idx + 1:idx + 1 + window]
                return prev_chunks, next_chunks

            # --- 确定需要运行的模式 ---
            modes_to_run = []
            if generation_mode == "all":
                modes_to_run = ["local", "context_enhanced", "full_doc"]
            else:
                modes_to_run = [generation_mode]

            # --- 所有生成的 QA 数据（用于批量保存到 DB） ---
            all_qa_items_with_chunk: list[tuple[dict, Chunk, str]] = []  # (qa_item, chunk, mode)

            # --- 阶段 A: 局部模式 + 邻域增强模式（按 chunk 并发） ---
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
                for file_id, file_chunks in file_chunks_map.items():
                    file_result = await db.execute(select(File).where(File.id == file_id))
                    file_obj = file_result.scalar_one_or_none()
                    filename = file_obj.filename if file_obj else "unknown"
                    full_content = "\n\n".join(c.content for c in file_chunks if c.content)
                    if not full_content.strip():
                        file_full_contents[file_id] = ""
                        continue
                    full_len = len(full_content)
                    if full_len > full_doc_max_chars:
                        logger.info(f"[问答对生成-full_doc] 文件 {filename} 超过 {full_doc_max_chars} 字符，先生成摘要")
                        try:
                            summary_prompt = (
                                f"请对以下文档内容生成一份结构化摘要，包含：\n"
                                f"1. 文档主题和目的\n2. 各章节/段落的核心要点\n"
                                f"3. 关键事实、定义、结论\n4. 各部分之间的逻辑关系\n\n"
                                f"【文档内容】\n{full_content[:full_doc_max_chars]}"
                            )
                            full_content = await call_generation_model(
                                question_model, "", summary_prompt, temperature, json_output=False
                            )
                            logger.info(f"[问答对生成-full_doc] 摘要生成完成: {len(full_content)} 字符")
                        except Exception as e:
                            logger.error(f"[问答对生成-full_doc] 摘要生成失败: {str(e)}")
                    file_full_contents[file_id] = full_content

            # 计算实际总步骤数
            total_steps = len(chunk_modes)

            if task:
                task.result = {
                    "created_questions": 0,
                    "created_answers": 0,
                    "processed_chunks": 0,
                    "skipped_chunks": 0,
                    "total_chunks": total_chunks,
                    "total_steps": total_steps,
                    "failed_answers": 0,
                }
                await db.commit()

            async def process_single_chunk_mode(chunk: Chunk, mode: str, chunk_idx: int) -> tuple:
                """处理单个 chunk 的某种模式"""
                # 检查取消
                if task_id in cancelling_tasks:
                    logger.info(f"[问答对生成-{mode}] 任务被取消，跳过 chunk #{chunk_idx}")
                    return 0, 0, 0, 0, [], chunk_idx, mode

                chunk_len = len(chunk.content) if chunk.content else 0
                source_tag = f"generated_qa_{mode}" if generation_mode == "all" else "generated_qa"
                logger.info(f"[问答对生成-{mode}] 开始处理 chunk #{chunk_idx}: id={chunk.id}, name={chunk.name}, length={chunk_len}")

                # 阶段 1: 内容质量评估
                if dirty_data_filter:
                    # 检查取消
                    if task_id in cancelling_tasks:
                        return 0, 0, 0, 0, [], chunk_idx, mode
                    can_generate, skip_reason = await evaluate_chunk_quality(
                        question_model, chunk.content, temperature
                    )
                    if not can_generate:
                        logger.info(f"[问答对生成-{mode}] 跳过 chunk #{chunk_idx}: {skip_reason}")
                        return 0, 0, 1, 0, [], chunk_idx, mode

                # 阶段 2: 生成问题
                try:
                    # 检查取消
                    if task_id in cancelling_tasks:
                        return 0, 0, 0, 0, [], chunk_idx, mode

                    dynamic_count = max(1, min(count, chunk_len // CHARS_PER_QUESTION))

                    if mode == "full_doc":
                        # 全文模式：当前 chunk + 全文上下文
                        system_prompt = build_full_doc_system_prompt(preset_prompt, dynamic_count)
                        full_content = file_full_contents.get(chunk.file_id, "")
                        user_prompt = build_full_doc_prompt(full_content, chunk.name or "未命名", thinking_mode)
                    elif mode == "context_enhanced":
                        prev_chunks, next_chunks = get_neighbor_chunks(chunk, context_window)
                        user_prompt = build_user_prompt_with_context(
                            chunk, prev_chunks, next_chunks, thinking_mode
                        )
                        system_prompt = build_system_prompt(preset_prompt, dynamic_count)
                    else:
                        system_prompt = build_system_prompt(preset_prompt, dynamic_count)
                        user_prompt = build_user_prompt(chunk, thinking_mode)

                    raw_text = await call_generation_model(
                        question_model, system_prompt, user_prompt, temperature
                    )
                    qa_pairs = parse_generated_questions(raw_text)[:dynamic_count]

                    if not qa_pairs:
                        logger.warning(f"[问答对生成-{mode}] LLM 返回空数组, chunk_id={chunk.id}")
                        qa_pairs = [{
                            "question": "这段文本的主要内容是什么？",
                            "answer": "",
                            "question_type": "summary"
                        }]
                except Exception as e:
                    logger.error(f"[问答对生成-{mode}] 问题生成失败: chunk_id={chunk.id}, error={str(e)}")
                    return 0, 0, 1, 0, [], chunk_idx, mode

                # 阶段 3: 为每个问题生成答案
                chunk_failed_answers = 0
                for item in qa_pairs:
                    # 检查取消
                    if task_id in cancelling_tasks:
                        item["answer"] = ""
                        chunk_failed_answers += 1
                        continue
                    try:
                        if mode == "full_doc":
                            # 全文模式用全文作为答案上下文
                            answer_context = file_full_contents.get(chunk.file_id, chunk.content or "")
                        elif mode == "context_enhanced":
                            prev_chunks, next_chunks = get_neighbor_chunks(chunk, context_window)
                            context_parts = []
                            for c in prev_chunks:
                                context_parts.append(c.content)
                            context_parts.append(chunk.content)
                            for c in next_chunks:
                                context_parts.append(c.content)
                            answer_context = "\n".join(context_parts)
                        else:
                            answer_context = chunk.content

                        answer_prompt = build_answer_prompt(item["question"], answer_context)
                        answer = await call_generation_model(
                            answer_model, "", answer_prompt, answer_temperature, json_output=False
                        )
                        answer = answer.strip()
                        if len(answer) < 20:
                            logger.warning(f"[问答对生成-{mode}] 答案过短 ({len(answer)} 字符)")
                            item["answer"] = ""
                            chunk_failed_answers += 1
                        else:
                            item["answer"] = answer
                    except Exception as e:
                        logger.error(f"[问答对生成-{mode}] 答案生成失败: question={item['question'][:50]}, error={str(e)}")
                        item["answer"] = ""
                        chunk_failed_answers += 1

                # 标记来源
                for item in qa_pairs:
                    item["_source"] = source_tag

                questions_count = len(qa_pairs)
                answers_count = questions_count - chunk_failed_answers
                logger.info(
                    f"[问答对生成-{mode}] chunk #{chunk_idx} 完成: questions={questions_count}, "
                    f"answers={answers_count}, failed={chunk_failed_answers}"
                )
                return questions_count, answers_count, 0, chunk_failed_answers, qa_pairs, chunk_idx, mode

            async def process_with_semaphore(chunk: Chunk, mode: str, chunk_idx: int) -> tuple:
                async with PROCESS_SEMAPHORE:
                    return await process_single_chunk_mode(chunk, mode, chunk_idx)

            # --- 并发处理局部 + 邻域增强模式 ---
            # 使用 asyncio.Task 而非 as_completed，以便能真正取消任务
            pending_tasks: set[asyncio.Task] = set()
            for i, (chunk, mode) in enumerate(chunk_modes):
                t = asyncio.create_task(process_with_semaphore(chunk, mode, i))
                pending_tasks.add(t)

            # 按文件整理结果
            file_results: dict[UUID, dict] = {
                file_id: {"qa_pairs": [], "chunks_processed": 0, "chunks_skipped": 0}
                for file_id in file_chunks_map.keys()
            }

            completed = 0
            was_cancelled = False
            while pending_tasks:
                # 检查取消
                if task_id in cancelling_tasks:
                    logger.info(f"[问答对生成] 任务被取消: task_id={task_id}, processed={completed}")
                    cancelling_tasks.discard(task_id)
                    was_cancelled = True
                    # 取消所有未完成的 asyncio.Task
                    for t in pending_tasks:
                        t.cancel()
                    # 等待被取消的任务完成（忽略 CancelledError）
                    await asyncio.gather(*pending_tasks, return_exceptions=True)
                    pending_tasks.clear()
                    break

                # 等待至少一个任务完成，超时 2 秒后重新检查取消标志
                done, pending_tasks = await asyncio.wait(pending_tasks, timeout=2.0, return_when=asyncio.FIRST_COMPLETED)

                for t in done:
                    if t.cancelled():
                        continue
                    try:
                        result = t.result()
                    except Exception as e:
                        logger.error(f"[问答对生成] chunk 处理异常: {str(e)}")
                        continue

                    q_count, a_count, skipped, f_answers, qa_items, chunk_idx, mode = result

                    chunk = chunks[chunk_idx] if chunk_idx < len(chunks) else chunks[0]
                    processed_count = completed + 1
                    created_questions += q_count
                    created_answers += a_count
                    skipped_chunks += skipped
                    failed_answers += f_answers

                    # 按文件分组
                    if chunk.file_id and chunk.file_id in file_results:
                        file_results[chunk.file_id]["chunks_processed"] += 1
                        file_results[chunk.file_id]["chunks_skipped"] += skipped
                        if qa_items:
                            file_results[chunk.file_id]["qa_pairs"].extend(qa_items)

                    # 收集用于保存到 DB
                    for item in qa_items:
                        source_tag = item.pop("_source", "generated_qa")
                        all_qa_items_with_chunk.append((item, chunk, source_tag))

                    # 更新进度
                    if task:
                        task.progress = int(processed_count * 100 / max(total_steps, 1))
                        existing_bid = (task.result or {}).get("batch_id")
                        task.result = {
                            "created_questions": created_questions,
                            "created_answers": created_answers,
                            "processed_chunks": processed_count,
                            "skipped_chunks": skipped_chunks,
                            "total_chunks": total_chunks,
                            "total_steps": total_steps,
                            "failed_answers": failed_answers,
                        }
                        if existing_bid:
                            task.result["batch_id"] = existing_bid
                        await db.commit()

                    completed += 1

            # --- 保存到数据库 ---
            for item, chunk, source_tag in all_qa_items_with_chunk:
                answer_value = item.get("answer", "")
                answer_status = "completed" if answer_value and len(answer_value) >= 20 else "failed"
                generation_status = "answered" if answer_status == "completed" else "answer_failed"

                question_obj = Question(
                    project_id=project_id,
                    chunk_id=chunk.id,
                    batch_id=batch_id,
                    content=item["question"],
                    answer=answer_value if answer_status == "completed" else None,
                    question_type=item.get("question_type", "fact"),
                    source=source_tag,
                    generation_status=generation_status,
                    answer_status=answer_status,
                )
                db.add(question_obj)

            await db.commit()

            # 回写 question_id 到 qa_pairs 数据中，供输出文件使用
            # 查询刚插入的记录获取 ID
            for item, chunk, source_tag in all_qa_items_with_chunk:
                q_result = await db.execute(
                    select(Question).where(
                        Question.project_id == project_id,
                        Question.chunk_id == chunk.id,
                        Question.content == item["question"],
                        Question.source == source_tag,
                    ).order_by(Question.created_at.desc()).limit(1)
                )
                q_obj = q_result.scalar_one_or_none()
                if q_obj:
                    item["question_id"] = str(q_obj.id)

            # --- 保存输出文件 ---
            logger.info(f"[问答对生成] 开始保存输出文件...")
            summary = {
                "task_id": str(task_id),
                "project_id": str(project_id),
                "total_chunks": total_chunks,
                "processed_chunks": processed_count,
                "skipped_chunks": skipped_chunks,
                "created_questions": created_questions,
                "created_answers": created_answers,
                "failed_answers": failed_answers,
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

                # 保存 qa_pairs.json
                if result["qa_pairs"]:
                    qa_file = file_output_dir / "qa_pairs.json"
                    with open(qa_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "file_id": str(file_id),
                            "filename": filename,
                            "qa_count": len(result["qa_pairs"]),
                            "qa_pairs": result["qa_pairs"]
                        }, f, ensure_ascii=False, indent=2)
                    logger.info(f"[问答对生成] ✓ {filename}: {len(result['qa_pairs'])} 个问答对")

                # 保存 metadata.json
                metadata_file = file_output_dir / "metadata.json"
                with open(metadata_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "file_id": str(file_id),
                        "filename": filename,
                        "total_chunks": result["chunks_processed"] + result["chunks_skipped"],
                        "chunks_processed": result["chunks_processed"],
                        "chunks_skipped": result["chunks_skipped"],
                        "qa_count": len(result["qa_pairs"]),
                    }, f, ensure_ascii=False, indent=2)

                summary["files"][str(file_id)] = {
                    "filename": filename,
                    "qa_count": len(result["qa_pairs"]),
                    "chunks_processed": result["chunks_processed"],
                    "chunks_skipped": result["chunks_skipped"],
                }

            # 保存 summary.json
            summary_file = output_base / "summary.json"
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            logger.info(f"[问答对生成] ✓ 保存 summary.json: {len(summary['files'])} 个文件")

            # --- 完成任务 ---
            if task:
                task.status = "cancelled" if was_cancelled else "completed"
                task.progress = 100
                task.result = {
                    "created_questions": created_questions,
                    "created_answers": created_answers,
                    "processed_chunks": processed_count,
                    "skipped_chunks": skipped_chunks,
                    "total_chunks": total_chunks,
                    "total_steps": total_steps,
                    "failed_answers": failed_answers,
                    "output_dir": str(output_base),
                }
                task.error = None
                await db.commit()

            status_label = "已取消（部分完成）" if was_cancelled else "完成"
            log_success(
                f"问答对批量生成{status_label}",
                project_id=str(project_id),
                model_id=str(question_model.id),
                chunk_count=total_chunks,
                created_questions=created_questions,
                created_answers=created_answers,
                failed_answers=failed_answers,
                skipped_chunks=skipped_chunks,
                output_dir=str(output_base)
            )
            logger.info(
                f"[问答对生成{status_label}] "
                f"处理 {processed_count}/{total_chunks} 个 chunk, "
                f"生成 {created_questions} 个问题, {created_answers} 个答案, "
                f"跳过 {skipped_chunks} 个, 答案失败 {failed_answers} 个"
            )

        except Exception as e:
            if task:
                task.status = "failed"
                task.error = str(e)
                await db.commit()
            log_failure(
                "问答对批量生成失败",
                project_id=str(project_id),
                model_id=str(model_id),
                error=str(e)
            )
            logger.error(f"[问答对生成] 任务失败: {str(e)}")


async def process_structured_qa_async(
    project_id: UUID,
    file_ids: List[UUID],
    strategy: str,  # "template" or "llm"
    model_id: Optional[UUID] = None,
    temperature: float = 0.7,
    questions_per_row: int = 1,
    task_id: Optional[UUID] = None,
    batch_id: Optional[UUID] = None,
):
    """结构化数据问答对生成后台任务。

    strategy:
    - "template": 基于字段映射关系，每行数据自动组装为指令-回复对，无需调用 LLM
    - "llm": 调用大模型基于行切片 + 字段映射信息生成更自然的问答对

    batch_id: 本次生成的批次 ID，同一次生成的问答对共享同一 batch_id
    """
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id) if task_id else None
        try:
            if task:
                task.status = "running"
                task.progress = 0
                # 保留已有 result 中的 batch_id，只覆盖统计字段
                existing_batch_id = (task.result or {}).get("batch_id")
                task.result = {
                    "created_questions": 0,
                    "processed_rows": 0,
                    "total_rows": (task.result or {}).get("total_rows", 0),
                }
                if existing_batch_id:
                    task.result["batch_id"] = existing_batch_id
                await db.commit()

            # 加载文件及其字段映射
            files_result = await db.execute(
                select(File).where(File.id.in_(file_ids), File.project_id == project_id)
            )
            files = files_result.scalars().all()
            if not files:
                if task:
                    task.status = "failed"
                    task.error = "没有找到指定的结构化文件"
                    await db.commit()
                return

            # 重置脱敏占位符状态（新批次）
            reset_desensitize_state()

            total_created = 0
            total_rows = 0
            processed_rows = 0  # 已处理的行数（用于进度更新）

            # 先统计总行数，确保进度计算准确
            for file_obj in files:
                field_schema = file_obj.field_schema or []
                if not field_schema:
                    continue
                feature_fields = [f for f in field_schema if f.get("role") == "feature"]
                if not feature_fields:
                    continue
                count_result = await db.execute(
                    select(func.count(Chunk.id)).where(Chunk.file_id == file_obj.id)
                )
                total_rows += count_result.scalar() or 0

            if task:
                task.result = {"created_questions": 0, "processed_rows": 0, "total_rows": total_rows}
                await db.commit()

            for file_obj in files:
                field_schema = file_obj.field_schema or []
                if not field_schema:
                    logger.warning(f"[结构化QA] 文件 {file_obj.filename} 没有字段映射配置，跳过")
                    continue

                # 分类字段
                feature_fields = [f for f in field_schema if f.get("role") == "feature"]
                target_fields = [f for f in field_schema if f.get("role") == "target"]
                redundant_fields = [f for f in field_schema if f.get("role") == "redundant"]

                if not feature_fields:
                    logger.warning(f"[结构化QA] 文件 {file_obj.filename} 没有业务属性字段，跳过")
                    continue

                # 加载该文件的 chunks（结构化切片）
                chunks_result = await db.execute(
                    select(Chunk).where(Chunk.file_id == file_obj.id)
                )
                chunks = chunks_result.scalars().all()

                if not chunks:
                    logger.warning(f"[结构化QA] 文件 {file_obj.filename} 没有切片，跳过")
                    continue

                if strategy == "template":
                    # 模板模式：使用模板引擎生成多样化的问答对
                    for row_idx, chunk in enumerate(chunks):
                        content = chunk.content or ""
                        if not content.strip():
                            continue

                        # 解析切片内容并调用模板引擎
                        row_data = parse_chunk_content(content)
                        qa_pairs = generate_template_qa_pairs(
                            row_data=row_data,
                            field_schema=field_schema,
                            questions_per_row=questions_per_row,
                            row_index=row_idx,
                        )

                        for qa in qa_pairs:
                            answer_value = qa.get("answer", "")
                            if answer_value:
                                answer_status = "completed"
                                generation_status = "answered"
                                answer_error = None
                            else:
                                answer_status = "failed"
                                generation_status = "answer_failed"
                                answer_error = "模板引擎未生成答案（可能是该行数据缺少必要字段）"

                            q = Question(
                                project_id=project_id,
                                chunk_id=chunk.id,
                                batch_id=batch_id,
                                content=qa["question"],
                                answer=answer_value or None,
                                question_type=qa.get("question_type", "fact"),
                                source="structured_template",
                                generation_status=generation_status,
                                answer_status=answer_status,
                                answer_error=answer_error,
                                generation_metadata={
                                    "file_id": str(file_obj.id),
                                    "filename": file_obj.filename,
                                    "strategy": "template",
                                    "template_type": qa.get("template_type", "forward"),
                                    "row_data_keys": list(row_data.keys()),
                                },
                            )
                            db.add(q)
                            total_created += 1

                        # 逐行更新进度
                        processed_rows += 1
                        if task:
                            task.progress = min(99, int(processed_rows * 100 / max(total_rows, 1)))
                            existing_bid = (task.result or {}).get("batch_id")
                            task.result = {
                                "created_questions": total_created,
                                "processed_rows": processed_rows,
                                "total_rows": total_rows,
                            }
                            if existing_bid:
                                task.result["batch_id"] = existing_bid
                            await db.commit()

                elif strategy == "llm":
                    # LLM 增强模式：基于切片 + 字段映射构建 prompt
                    if not model_id:
                        logger.error("[结构化QA-LLM] 未指定模型 ID")
                        continue

                    model_result = await db.execute(
                        select(ModelConfig).where(
                            ModelConfig.id == model_id,
                        )
                    )
                    model_config = model_result.scalar_one_or_none()
                    if not model_config:
                        logger.error("[结构化QA-LLM] 模型未找到")
                        continue

                    # 构建字段映射信息文本
                    mapping_text = "字段映射配置：\n"
                    for f in field_schema:
                        role_label = {"feature": "业务属性（输入）", "target": "输出字段（预测目标）", "redundant": "冗余字段（忽略）"}
                        mapping_text += f"- {f['name']}: {role_label.get(f['role'], f['role'])}"
                        if f.get("desensitize"):
                            mapping_text += "，需脱敏"
                        mapping_text += "\n"

                    feature_names = [f["name"] for f in feature_fields]
                    target_names = [f["name"] for f in target_fields]

                    for chunk in chunks:
                        content = chunk.content or ""
                        if not content.strip():
                            continue

                        processed_rows += 1

                        # 构建 prompt
                        json_format_example = '[{"question": "...", "answer": "..."}]'
                        system_prompt = (
                            "你是一名专业的问答数据构建助手。以下是结构化数据的一行记录，"
                            f"以及字段映射配置。请根据映射关系，基于这行数据生成 {questions_per_row} 个问答对。\n"
                            "业务属性字段作为问题的已知条件，输出字段作为需要预测的答案目标。\n"
                            f"{mapping_text}\n"
                            "要求：\n"
                            "1. 问题应该自然流畅，不要机械地罗列条件\n"
                            "2. 答案必须准确，直接引用数据中的值\n"
                            "3. 如果字段标记需要脱敏，答案中用语义化占位符替换（如 **姓名值A**、**薪资值A**）\n"
                            f"4. 返回 JSON 数组格式：{json_format_example}"
                        )
                        user_prompt = f"数据行内容：\n{content}"

                        try:
                            raw_text = await call_generation_model(
                                model_config, system_prompt, user_prompt, temperature
                            )
                            qa_pairs = parse_generated_questions(raw_text)[:questions_per_row]

                            for item in qa_pairs:
                                answer_value = item.get("answer", "")
                                if answer_value and len(answer_value) >= 2:
                                    answer_status = "completed"
                                    generation_status = "answered"
                                    answer_error = None
                                else:
                                    answer_status = "failed"
                                    generation_status = "answer_failed"
                                    if not answer_value:
                                        answer_error = "LLM 未返回答案"
                                    else:
                                        answer_error = f"答案为空或异常：{answer_value[:100]}"

                                q = Question(
                                    project_id=project_id,
                                    chunk_id=chunk.id,
                                    batch_id=batch_id,
                                    content=item.get("question", ""),
                                    answer=answer_value if answer_status == "completed" else None,
                                    question_type="fact",
                                    source="structured_llm",
                                    generation_status=generation_status,
                                    answer_status=answer_status,
                                    answer_error=answer_error,
                                    generation_metadata={
                                        "file_id": str(file_obj.id),
                                        "filename": file_obj.filename,
                                        "strategy": "llm",
                                        "feature_fields": feature_names,
                                        "target_fields": target_names,
                                    },
                                )
                                db.add(q)
                                total_created += 1
                        except Exception as e:
                            logger.error(f"[结构化QA-LLM] 生成失败: {str(e)}")
                            # 创建一条失败记录，让用户能看到问题
                            q = Question(
                                project_id=project_id,
                                chunk_id=chunk.id,
                                batch_id=batch_id,
                                content=f"[LLM生成失败] 数据行：{(chunk.content or '')[:200]}",
                                answer=None,
                                question_type="fact",
                                source="structured_llm",
                                generation_status="answer_failed",
                                answer_status="failed",
                                answer_error=f"LLM 调用异常：{str(e)[:500]}",
                                generation_metadata={
                                    "file_id": str(file_obj.id),
                                    "filename": file_obj.filename,
                                    "strategy": "llm",
                                    "feature_fields": feature_names,
                                    "target_fields": target_names,
                                },
                            )
                            db.add(q)
                            total_created += 1

                        # 每行更新进度
                        if task:
                            task.progress = min(99, int(processed_rows * 100 / max(total_rows, 1)))
                            existing_bid = (task.result or {}).get("batch_id")
                            task.result = {
                                "created_questions": total_created,
                                "processed_rows": processed_rows,
                                "total_rows": total_rows,
                            }
                            if existing_bid:
                                task.result["batch_id"] = existing_bid
                            await db.commit()

            await db.commit()

            if task:
                task.status = "completed"
                task.progress = 100
                task.result = {
                    "created_questions": total_created,
                    "processed_rows": processed_rows,
                    "total_rows": total_rows,
                }
                await db.commit()

            log_success(
                "结构化数据问答对生成完成",
                project_id=str(project_id),
                strategy=strategy,
                file_count=len(files),
                created_questions=total_created,
                total_rows=total_rows,
            )

        except Exception as e:
            if task:
                task.status = "failed"
                task.error = str(e)
                await db.commit()
            log_failure(
                "结构化数据问答对生成失败",
                project_id=str(project_id),
                error=str(e)
            )
            logger.error(f"[结构化QA] 任务失败: {str(e)}")
