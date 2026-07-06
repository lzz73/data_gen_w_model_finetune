"""
Evaluation Results Service
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

import json

from app.models.models import EvalResult, EvalDataset, Task, Question


async def get_eval_results_by_task_id(
    db: AsyncSession,
    task_id: UUID,
    page: int = 1,
    page_size: int = 10,
    type: Optional[str] = None,
    is_correct: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get evaluation results by task ID with pagination and filters.
    Ensures all expected questions are returned — fills missing (failed) evaluations with placeholders.
    """
    task_query = select(Task).where(Task.id == task_id)
    task_result = await db.execute(task_query)
    task = task_result.scalar_one_or_none()

    expected_total = 0
    if task:
        expected_total = task.total_count if task.total_count > 0 else 0

    query = select(EvalResult).where(EvalResult.task_id == task_id)
    count_query = select(func.count()).select_from(EvalResult).where(EvalResult.task_id == task_id)

    if is_correct is not None:
        query = query.where(EvalResult.is_correct == is_correct)
        count_query = count_query.where(EvalResult.is_correct == is_correct)

    if type:
        query = query.join(EvalDataset, EvalResult.eval_dataset_id == EvalDataset.id)
        query = query.where(EvalDataset.question_type == type)

        count_query = count_query.join(EvalDataset, EvalResult.eval_dataset_id == EvalDataset.id)
        count_query = count_query.where(EvalDataset.question_type == type)

    skip = (page - 1) * page_size
    query = query.offset(skip).limit(page_size)

    result = await db.execute(query)
    db_items = result.scalars().all()

    count_result = await db.execute(count_query)
    actual_total = count_result.scalar() or 0

    items_dict = []
    for item in db_items:
        items_dict.append({
            "id": str(item.id),
            "taskId": str(item.task_id),
            "evalDatasetId": str(item.eval_dataset_id),
            "questionId": str(item.question_id) if item.question_id else None,
            "modelAnswer": item.model_answer,
            "expectedAnswer": item.expected_answer,
            "judgeScore": item.judge_score,
            "isCorrect": item.is_correct,
            "feedback": item.feedback,
            "evalMetadata": item.eval_metadata,
            "createdAt": item.created_at.isoformat() if item.created_at else None,
            "updatedAt": item.updated_at.isoformat() if item.updated_at else None
        })

    try:
        # 只在任务失败时填充 placeholder，暂停时只显示已评估的结果
        task_status = task.status if task else ''
        if task_status != 'stopped' and not is_correct and not type and page == 1 and expected_total > len(items_dict):
            missing_count = expected_total - actual_total
            if missing_count > 0:
                detail = {}
                try:
                    detail = json.loads(task.detail) if task and task.detail else {}
                except:
                    pass

                raw_eval_dataset_ids = detail.get("eval_dataset_ids", [detail.get("eval_dataset_id")])
                eval_dataset_id = raw_eval_dataset_ids[0] if raw_eval_dataset_ids else None

                all_question_ids: List[str] = []
                existing_question_ids = set(str(item.get("questionId")) for item in items_dict if item.get("questionId"))

                if eval_dataset_id:
                    ds_query = select(EvalDataset).where(EvalDataset.id == UUID(eval_dataset_id))
                    ds_result = await db.execute(ds_query)
                    dataset = ds_result.scalar_one_or_none()

                    if dataset and dataset.extra_data:
                        try:
                            ds_extra = json.loads(dataset.extra_data) if isinstance(dataset.extra_data, str) else dataset.extra_data
                            all_question_ids = ds_extra.get("question_ids", [])
                        except:
                            pass

                missing_qids = [qid for qid in all_question_ids if qid not in existing_question_ids]

                if len(missing_qids) < missing_count:
                    missing_qids = [f"missing-{i}" for i in range(missing_count)]

                valid_uuid_qids = []
                for qid in missing_qids:
                    try:
                        valid_uuid_qids.append(UUID(qid))
                    except:
                        pass

                question_map: Dict[str, Dict[str, str]] = {}
                if valid_uuid_qids:
                    q_query = select(Question).where(Question.id.in_(valid_uuid_qids))
                    q_result = await db.execute(q_query)
                    for q in q_result.scalars().all():
                        question_map[str(q.id)] = {
                            "question": q.content or "",
                            "answer": q.answer or "",
                        }

                end_time_str = task.end_time if task and task.end_time else None
                for idx, qid in enumerate(missing_qids):
                    q_info = question_map.get(qid, {})
                    placeholder = {
                        "id": f"placeholder-{task_id}-{idx}",
                        "taskId": str(task_id),
                        "evalDatasetId": str(eval_dataset_id) if eval_dataset_id else None,
                        "questionId": qid if not qid.startswith("missing-") else None,
                        "modelAnswer": None,
                        "expectedAnswer": q_info.get("answer", ""),
                        "judgeScore": 0,
                        "isCorrect": "false",
                        "feedback": "评估失败：该问题的评估过程未完成或发生错误",
                        "evalMetadata": json.dumps({
                            "question_type": "unknown",
                            "question": q_info.get("question", ""),
                            "evaluation_status": "failed"
                        }, ensure_ascii=False),
                        "createdAt": end_time_str,
                        "updatedAt": end_time_str
                    }
                    items_dict.append(placeholder)
    except Exception as e:
        print(f"[WARNING] Failed to fill placeholder results (non-critical): {e}")
        import traceback
        print(traceback.format_exc())

    report_total = max(expected_total, actual_total)

    return {
        "items": items_dict,
        "total": report_total
    }


async def get_eval_results_stats(
    db: AsyncSession,
    task_id: UUID
) -> Dict[str, Any]:
    """
    Get statistics for evaluation results
    """
    try:
        task_query = select(Task).where(Task.id == task_id)
        task_result = await db.execute(task_query)
        task = task_result.scalar_one_or_none()

        total = task.total_count if task and task.total_count > 0 else 0

        eval_total_query = select(func.count()).select_from(EvalResult).where(
            EvalResult.task_id == task_id
        )
        eval_total_result = await db.execute(eval_total_query)
        eval_total = eval_total_result.scalar() or 0

        correct_query = select(func.count()).select_from(EvalResult).where(
            EvalResult.task_id == task_id
        ).where(EvalResult.is_correct == "true")
        correct_result = await db.execute(correct_query)
        correct = correct_result.scalar() or 0

        partial_query = select(func.count()).select_from(EvalResult).where(
            EvalResult.task_id == task_id
        ).where(EvalResult.is_correct == "partial")
        partial_result = await db.execute(partial_query)
        partial = partial_result.scalar() or 0

        failed_count = total - eval_total if total > eval_total else 0
        actual_incorrect = eval_total - correct - partial
        incorrect = actual_incorrect + failed_count

        accuracy = correct / total if total > 0 else 0
        correct_rate = (correct + partial * 0.5) / total if total > 0 else 0

        avg_score_query = select(func.avg(EvalResult.judge_score)).select_from(EvalResult).where(
            EvalResult.task_id == task_id
        ).where(EvalResult.judge_score.isnot(None))
        avg_score_result = await db.execute(avg_score_query)
        avg_score = avg_score_result.scalar() or 0.0

        stats = {
            "total": total,
            "correct": correct,
            "partial": partial,
            "incorrect": incorrect,
            "accuracy": round(accuracy, 4),
            "correctRate": round(correct_rate, 4),
            "averageScore": round(float(avg_score), 2) if avg_score else 0.0
        }
        return stats
    except Exception as e:
        print(f"[ERROR] Exception in get_eval_results_stats: {e}")
        import traceback
        print(traceback.format_exc())
        return {
            "total": 0,
            "correct": 0,
            "partial": 0,
            "incorrect": 0,
            "accuracy": 0.0,
            "correctRate": 0.0,
            "averageScore": 0.0
        }
