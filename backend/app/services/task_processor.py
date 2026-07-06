"""
Task Processor Service
处理各种后台任务
"""
import asyncio
import json
import re
from typing import Tuple
from uuid import UUID
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Task, EvalDataset, EvalResult, Question, Chunk, ModelConfig


async def call_model(model: ModelConfig, system_prompt: str, user_prompt: str, temperature: float = 0.7,
                    max_retries: int = 3) -> str:
    """调用模型生成答案，带指数退避重试机制"""
    api_base = (model.api_base or "").rstrip("/")
    api_key = model.api_key or ""
    model_name = model.model_name

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature,
    }

    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                response = await client.post(
                    f"{api_base}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content.strip() if content else ""
        except httpx.HTTPStatusError as e:
            last_exception = e
            status_code = e.response.status_code
            if status_code == 429 or status_code >= 500:
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    print(f"[RETRY] 模型调用失败({status_code})，第{attempt+1}次重试，等待{wait_time}秒...")
                    await asyncio.sleep(wait_time)
                    continue
            raise
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = 2 ** attempt
                print(f"[RETRY] 模型调用异常，第{attempt+1}次重试，等待{wait_time}秒... 错误: {e}")
                await asyncio.sleep(wait_time)
                continue
            raise

    raise last_exception


def build_eval_prompt(chunk_content: str, question: str, answer: str, language: str = "zh-CN") -> Tuple[str, str]:
    """构建评估提示词 - 多维度评估"""

    system_prompt = """# Role: 数据集质量评估专家

## Profile:
- 你是一名专业的数据集质量评估专家，擅长从多个维度对问答数据集进行质量评估。

## 评估维度:
### 1. 问题质量 (25%)
- 5分：问题表述清晰准确，语法完美，具有明确的答案期望
- 3分：问题可理解，但存在一定歧义或表达不够精确
- 1分：问题表述严重不清，难以理解意图

### 2. 答案质量 (35%)
- 5分：答案完全准确，内容详尽，逻辑清晰，结构完整
- 3分：答案大致正确，但缺少部分细节
- 1分：答案大部分错误

### 3. 文本相关性 (25%)
- 5分：问题和答案与原始文本高度相关，文本完全支撑答案
- 3分：问题和答案与文本相关，但支撑度一般
- 1分：问题和答案与文本相关性很弱

### 4. 整体一致性 (15%)
- 5分：问题、答案、文本形成完美的逻辑闭环
- 3分：基本一致，可用于模型训练
- 1分：存在明显不一致

## 输出要求:
请按照以下JSON格式输出评估结果，评分范围为0-5分，精确到0.5分：

```json
{
    "score": 4.5,
    "evaluation": "评估结论，说明优点和不足"
}
```"""

    if not chunk_content or "Distilled Content" in chunk_content:
        chunk_content = "无原始文本参考（蒸馏数据集）"

    user_prompt = f"""## 原始文本块内容:
{chunk_content}

## 问题:
{question}

## 答案:
{answer}

## 评估说明:
请严格按照评分标准，对每个维度进行打分，最终评分为各维度加权平均。

请确保返回有效的JSON格式。"""

    return system_prompt, user_prompt


def parse_eval_result(content: str) -> dict:
    """解析评估结果"""
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()
        if content.startswith("```"):
            content = content[3:].split("```")[0]
        content = content.strip()

        result = json.loads(content)

        score = float(result.get("score", 0))
        score = max(0, min(5, score))
        score = round(score * 2) / 2

        return {
            "score": score,
            "is_correct": "true" if score >= 3 else "false",
            "feedback": str(result.get("evaluation", ""))
        }
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        score_match = re.search(r'"score"\s*:\s*(\d+\.?\d*)', content)
        eval_match = re.search(r'"evaluation"\s*:\s*"([^"]+)"', content)

        if score_match:
            score = float(score_match.group(1))
            score = max(0, min(5, score))
            score = round(score * 2) / 2
            return {
                "score": score,
                "is_correct": "true" if score >= 3 else "false",
                "feedback": eval_match.group(1) if eval_match else "评估完成"
            }

        return {
            "score": 0,
            "is_correct": "false",
            "feedback": f"解析失败: {str(e)[:100]}"
        }


async def process_evaluation_task(task_id: UUID):
    """
    处理评估任务
    1. 获取任务信息
    2. 从评估数据集中获取问题
    3. 获取问题关联的 chunk 内容
    4. 调用模型评估数据集质量
    5. 保存评估结果
    """
    from app.core.database import AsyncSessionLocal

    print(f"[EVAL TASK] 开始处理评估任务 {task_id}")
    async with AsyncSessionLocal() as db:
        dataset = None
        try:
            task = await db.get(Task, task_id)
            if not task:
                print(f"[EVAL TASK] 任务不存在: {task_id}")
                return

            detail = json.loads(task.detail) if task.detail else {}
            eval_dataset_ids = detail.get("eval_dataset_ids")
            if not eval_dataset_ids:
                eval_dataset_ids = [detail.get("eval_dataset_id")]

            if not eval_dataset_ids or not eval_dataset_ids[0]:
                raise ValueError("任务详情中缺少评估数据集ID")

            eval_dataset_id = eval_dataset_ids[0]

            dataset = await db.get(EvalDataset, UUID(eval_dataset_id))
            if not dataset:
                raise ValueError(f"找不到评估数据集: {eval_dataset_id}")
            print(f"[EVAL TASK] 获取评估数据集: {dataset.name}")

            extra_data = json.loads(dataset.extra_data) if isinstance(dataset.extra_data, str) else (dataset.extra_data or {})
            question_ids = extra_data.get("question_ids", [])
            selected_questions = extra_data.get("selected_questions")

            if not question_ids:
                raise ValueError("评估数据集中没有选择的问题")

            total_questions = len(question_ids)

            if selected_questions is not None and selected_questions > 0:
                if selected_questions <= len(question_ids):
                    total_questions = selected_questions
                else:
                    total_questions = len(question_ids)

            if len(question_ids) > total_questions:
                question_ids = question_ids[:total_questions]

            task.status = "running"
            task.total_count = total_questions
            task.completed_count = 0
            dataset.status = "running"
            await db.commit()
            print(f"[EVAL TASK] 任务状态更新为 running，总问题数: {total_questions}")

            # 查找评估模型
            model_config_id = detail.get("model_config_id")
            if model_config_id:
                model = await db.get(ModelConfig, UUID(model_config_id))
            else:
                result = await db.execute(
                    select(ModelConfig).where(
                        ModelConfig.project_id == task.project_id,
                        ModelConfig.model_type == "chat",
                        ModelConfig.is_default == "true"
                    )
                )
                model = result.scalar_one_or_none()

                if not model:
                    result = await db.execute(
                        select(ModelConfig).where(
                            ModelConfig.project_id == task.project_id,
                            ModelConfig.model_type == "chat"
                        ).limit(1)
                    )
                    model = result.scalar_one_or_none()

                if not model:
                    result = await db.execute(
                        select(ModelConfig).where(
                            ModelConfig.project_id == None,
                            ModelConfig.model_type == "chat",
                            ModelConfig.is_default == "true"
                        )
                    )
                    model = result.scalar_one_or_none()

                if not model:
                    result = await db.execute(
                        select(ModelConfig).where(
                            ModelConfig.project_id == None,
                            ModelConfig.model_type == "chat"
                        ).limit(1)
                    )
                    model = result.scalar_one_or_none()

            if not model:
                raise ValueError("未配置评估模型")
            print(f"[EVAL TASK] 使用模型: {model.model_name} (provider: {model.provider})")

            result = await db.execute(
                select(Question).where(Question.id.in_([UUID(qid) for qid in question_ids]))
            )
            questions = result.scalars().all()
            question_map = {str(q.id): q for q in questions}

            chunk_ids = [q.chunk_id for q in questions if q.chunk_id]
            if chunk_ids:
                chunk_result = await db.execute(
                    select(Chunk).where(Chunk.id.in_(chunk_ids))
                )
                chunks = chunk_result.scalars().all()
                chunk_map = {str(c.id): c.content for c in chunks}
            else:
                chunk_map = {}

            total_score = 0
            evaluated_count = 0
            language = task.language or "zh-CN"

            # 获取该数据集下已评估的问题 ID（用于继续评估时跳过）
            existing_eval_query = select(EvalResult.question_id).where(
                EvalResult.eval_dataset_id == dataset.id
            )
            existing_eval_result = await db.execute(existing_eval_query)
            existing_question_ids = set(str(qid) for qid in existing_eval_result.scalars().all() if qid)
            print(f"[EVAL TASK] 数据集 {dataset.id} 已评估的问题数：{len(existing_question_ids)}")

            for qid in question_ids:
                # 检查任务是否被停止
                await db.refresh(task)
                if task.status == "stopped":
                    print(f"[EVAL TASK] 任务被用户停止，已评估 {evaluated_count} 个问题")
                    # 更新任务的 completed_count 为实际评估的数量
                    task.completed_count = evaluated_count
                    task.progress = int(evaluated_count * 100 / task.total_count) if task.total_count > 0 else 0
                    await db.commit()
                    break
                if task.status == "failed":
                    print(f"[EVAL TASK] 任务失败，已评估 {evaluated_count} 个问题")
                    task.completed_count = evaluated_count
                    task.progress = int(evaluated_count * 100 / task.total_count) if task.total_count > 0 else 0
                    await db.commit()
                    break

                # 跳过已评估的问题（继续评估的场景）
                if str(qid) in existing_question_ids:
                    print(f"[EVAL TASK] 跳过已评估的问题：{qid}")
                    task.completed_count += 1
                    task.progress = int(task.completed_count * 100 / task.total_count)
                    await db.commit()
                    continue

                question = question_map.get(qid)
                if not question:
                    continue

                expected_answer = question.answer or ""
                question_text = question.content or ""
                question_type = question.question_type or "mixed"

                chunk_content = ""
                if question.chunk_id and str(question.chunk_id) in chunk_map:
                    chunk_content = chunk_map[str(question.chunk_id)]

                try:
                    system_prompt, user_prompt = build_eval_prompt(
                        chunk_content, question_text, expected_answer, language
                    )

                    eval_result_str = await call_model(model, system_prompt, user_prompt, temperature=0.3)
                    eval_result = parse_eval_result(eval_result_str)

                    eval_result_record = EvalResult(
                        task_id=task_id,
                        eval_dataset_id=dataset.id,
                        question_id=question.id,
                        model_answer=None,
                        expected_answer=expected_answer,
                        judge_score=eval_result["score"],
                        is_correct=eval_result["is_correct"],
                        feedback=eval_result["feedback"],
                        eval_metadata=json.dumps({
                            "question_type": question_type,
                            "model_name": model.model_name,
                            "question": question_text,
                            "chunk_content_length": len(chunk_content) if chunk_content else 0
                        })
                    )
                    db.add(eval_result_record)

                    total_score += eval_result["score"]
                    evaluated_count += 1

                except Exception as e:
                    print(f"评估问题 {qid} 失败: {e}")
                    import traceback
                    print(traceback.format_exc())

                    failed_record = EvalResult(
                        task_id=task_id,
                        eval_dataset_id=dataset.id,
                        question_id=question.id,
                        model_answer=None,
                        expected_answer=expected_answer,
                        judge_score=0,
                        is_correct="false",
                        feedback=f"评估失败: {str(e)[:200]}",
                        eval_metadata=json.dumps({
                            "question_type": question_type,
                            "model_name": model.model_name if model else "unknown",
                            "question": question_text,
                            "chunk_content_length": len(chunk_content) if chunk_content else 0,
                            "evaluation_status": "failed",
                            "error": str(e)[:500]
                        }, ensure_ascii=False)
                    )
                    db.add(failed_record)

                task.completed_count += 1
                task.progress = int(task.completed_count * 100 / task.total_count)
                await db.commit()
                print(f"[EVAL TASK] 进度更新: {task.completed_count}/{task.total_count} ({task.progress}%)")

            avg_score = (total_score / evaluated_count * 20) if evaluated_count > 0 else 0
            task.model_info = json.dumps({
                "avg_score": round(avg_score, 1),
                "avg_score_5": round(total_score / evaluated_count, 1) if evaluated_count > 0 else 0,
                "evaluated_count": evaluated_count,
                "model_name": model.model_name
            })

            # 如果是被停止的，保持 stopped 状态
            if task.status != "stopped":
                task.status = "completed"
                task.end_time = datetime.utcnow().isoformat()
                dataset.status = "completed"
            else:
                task.end_time = datetime.utcnow().isoformat()
                dataset.status = "stopped"
                print(f"[EVAL TASK] 任务已停止，保留已评估的 {evaluated_count} 个结果")

            await db.commit()
            if task.status == "completed":
                print(f"评估任务完成：平均分={avg_score:.2f}, 评估数量={evaluated_count}")

        except Exception as e:
            if task:
                task.status = "failed"
                task.error = str(e)
                if dataset:
                    dataset.status = "failed"
                await db.commit()
            raise
