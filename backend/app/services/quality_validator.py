"""
Quality Validator Service

三层质量校验：基础校验、语义校验、格式校验。
以及基于原文上下文的重新生成功能。
"""
import asyncio
import re
from typing import List, Optional
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import logger, log_success, log_failure
from app.models.models import Chunk, ModelConfig, Question, Task
from app.services.llm_helpers import call_generation_model, LLM_SEMAPHORE


# ──────────────────────────────────────────────
# 第一层：基础校验（纯 Python）
# ──────────────────────────────────────────────

def _basic_validate(answer: Optional[str], source: str = "") -> tuple[str, str]:
    """基础校验：答案是否存在且长度足够。

    结构化数据（source 含 "structured"）阈值 2 字符，
    非结构化数据阈值 20 字符。

    Returns:
        (answer_status, answer_error)
    """
    if not answer or not answer.strip():
        return "failed", "缺少关联内容"
    min_len = 2 if "structured" in (source or "") else 20
    if len(answer.strip()) < min_len:
        return "failed", f"答案过短（{len(answer.strip())}字符，要求≥{min_len}）"
    return "completed", ""


# ──────────────────────────────────────────────
# 第二层：格式校验（正则 + 规则）
# ──────────────────────────────────────────────

def _format_validate(answer: str) -> tuple[bool, str]:
    """格式校验：检查答案是否存在格式异常。

    Returns:
        (is_valid, error_detail) — is_valid=True 表示格式正常
    """
    if not answer:
        return True, ""

    # 1. 乱码检测：连续非 ASCII 无意义字符占比 > 30%
    non_alpha_numeric = re.sub(r'[\w\s一-鿿　-〿＀-￯.,;:!?，。；：！？、""''（）()【】\[\]{}\-/\\@#$%^&*+=~`|<>]', '', answer)
    if len(answer) > 0 and len(non_alpha_numeric) / len(answer) > 0.3:
        return False, "格式异常: 包含大量乱码字符"

    # 2. 截断检测：末尾是省略号或未闭合的引号/括号
    stripped = answer.rstrip()
    if stripped.endswith(("...", "…", "。。。")):
        return False, "格式异常: 答案可能被截断（末尾省略号）"

    # 未闭合括号
    open_brackets = answer.count("(") + answer.count("（") + answer.count("[") + answer.count("【")
    close_brackets = answer.count(")") + answer.count("）") + answer.count("]") + answer.count("】")
    if open_brackets > close_brackets:
        return False, "格式异常: 存在未闭合的括号"

    # 未闭合引号（中英文引号计数）
    quote_pairs = [
        ("“", "”"),  # 中文左右双引号 ""
        ("‘", "’"),  # 中文左右单引号 ''
        ("「", "」"),  # 「」
        ("『", "』"),  # 『』
    ]
    for open_q, close_q in quote_pairs:
        if answer.count(open_q) != answer.count(close_q):
            return False, "格式异常: 存在未闭合的引号"

    # 3. 重复文本检测：检测 LLM 输出卡住导致的异常重复
    #    用正则检测连续重复：同一段文字紧挨着重复 ≥2 次
    #    例如 "风险管理的基本原则风险管理的基本原则风险管理的基本原则"
    if re.search(r'([一-鿿\w，。；：！？、]{6,})\1{2,}', answer):
        return False, "格式异常: 存在重复文本"

    # 非连续重复：中文长片段（≥20字）出现 ≥3 次
    #    含大量英文/数字的片段通常是术语名正常复用（如 PostgresSQL），不算异常
    for i in range(len(answer) - 20):
        fragment = answer[i:i + 20]
        if not fragment.strip():
            continue
        if answer.count(fragment) >= 3:
            # 计算片段中中文字符占比，> 60% 才算有意义的重复
            chinese_chars = len(re.findall(r'[一-鿿]', fragment))
            if chinese_chars / max(len(fragment), 1) > 0.6:
                return False, "格式异常: 存在重复文本"

    return True, ""


def _template_format_validate(answer: str, source: str = "") -> tuple[bool, str]:
    """模板格式校验：检查结构化数据生成的答案是否符合预设格式模板。

    文档 3.5 节要求：格式校验检查生成答案是否符合预设格式模板
    （例如 "{标识符}的{列名}为{值}"），不符合要求的结果标记为"格式异常"。

    仅对结构化数据生成的答案生效（source 包含 "structured"），
    非结构化数据答案不适用此校验。

    合法的模板格式示例：
        - "注册资本为5000万元。"
        - "注册资本为5000万元，成立日期为2020年。"
        - "根据记录，注册资本为5000万元，成立日期为2020年。"
        - "在职。"  (布尔型)
        - "未在职。" (布尔型否定)

    Returns:
        (is_valid, error_detail) — is_valid=True 表示格式正常
    """
    if not answer or not source:
        return True, ""

    # 仅对结构化数据来源的答案做模板格式校验
    if "structured" not in source:
        return True, ""

    stripped = answer.strip()

    # 合法模式 1：概括型 — "根据记录，XXX为YYY，ZZZ为WWW。"
    if re.match(r'^根据[记录数据，]+', stripped):
        # 概括型必须包含至少一个 "XX为YY" 或 "XX是YY" 的结构
        if re.search(r'[一-鿿\w]+[是为]\S+', stripped):
            return True, ""

    # 合法模式 2：多目标 — "XX为YY，ZZZ为WWW。" 或 "XX是YY，ZZZ是WWW。"
    # 至少包含一个 "字段名+连接词(为/是)+值" 的结构
    if re.search(r'[一-鿿\w]+[是为]\S+', stripped):
        return True, ""

    # 合法模式 3：布尔型 — "在职。" / "未在职。"
    if re.match(r'^(未)?[一-鿿]{2,10}[。.]?$', stripped):
        return True, ""

    # 合法模式 4：否定型 — "XX不为YY" / "XX不是YY"
    if re.search(r'[一-鿿\w]+不[是为]\S+', stripped):
        return True, ""

    # 不符合任何模板格式
    return False, "格式异常: 答案不符合预设格式模板（应为\"{字段名}为/是{值}\"格式）"


# ──────────────────────────────────────────────
# 第三层：语义校验（嵌入模型）
# ──────────────────────────────────────────────

async def _get_embedding_config(db: AsyncSession, project_id: UUID):
    """获取项目的默认 embedding 模型配置。"""
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

        if model_config and model_config.api_key:
            return model_config
        return None
    except Exception as e:
        logger.warning(f"[语义校验] 获取 embedding 配置失败: {e}")
        return None


async def _compute_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """计算两个向量的余弦相似度。"""
    a = np.array(vec1)
    b = np.array(vec2)
    norm_a = np.linalg.norm(a) + 1e-8
    norm_b = np.linalg.norm(b) + 1e-8
    return float(np.dot(a, b) / (norm_a * norm_b))


async def _semantic_validate(
    answer: str,
    chunk_content: str,
    embedding_model: ModelConfig,
) -> Optional[float]:
    """语义校验：计算答案与原切片的余弦相似度。

    Returns:
        相似度分数（0-1），如果调用失败返回 None
    """
    import httpx

    api_base = (embedding_model.api_base or "https://api.openai.com/v1").rstrip("/")
    api_key = embedding_model.api_key
    model_name = embedding_model.model_name or "text-embedding-3-small"

    # 构建请求
    payload = {
        "input": [answer, chunk_content[:2000]],  # 限制切片长度避免 token 过长
        "model": model_name,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{api_base}/embeddings",
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                logger.warning(f"[语义校验] Embedding API 错误: {response.status_code}")
                return None

            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]

            if len(embeddings) < 2:
                return None

            similarity = await _compute_cosine_similarity(embeddings[0], embeddings[1])
            return similarity

    except Exception as e:
        logger.warning(f"[语义校验] 计算相似度失败: {e}")
        return None


# ──────────────────────────────────────────────
# 主校验流程
# ──────────────────────────────────────────────

async def validate_questions_async(
    project_id: UUID,
    question_ids: Optional[List[UUID]] = None,
    task_id: Optional[UUID] = None,
):
    """后台执行三层质量校验。"""
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id) if task_id else None
        try:
            if task:
                task.status = "running"
                task.progress = 0
                task.result = {"total": 0, "passed": 0, "hallucination": 0, "format_error": 0, "failed": 0}
                await db.commit()

            # 加载问题
            query = select(Question).where(Question.project_id == project_id)
            if question_ids:
                query = query.where(Question.id.in_(question_ids))
            result = await db.execute(query)
            questions = result.scalars().all()

            if not questions:
                if task:
                    task.status = "completed"
                    task.progress = 100
                    task.result = {"total": 0, "passed": 0, "hallucination": 0, "format_error": 0, "failed": 0}
                    await db.commit()
                return

            total = len(questions)
            passed = 0
            hallucination = 0
            format_error = 0
            failed = 0

            # 获取 embedding 配置
            embedding_model = await _get_embedding_config(db, project_id)
            has_embedding = embedding_model is not None
            if not has_embedding:
                logger.info("[语义校验] 无 embedding 模型配置，跳过语义校验")

            # 批量加载 chunks（按 question.chunk_id 查询）
            chunk_ids = list(set(q.chunk_id for q in questions if q.chunk_id))
            chunk_map = {}
            if chunk_ids:
                chunk_result = await db.execute(
                    select(Chunk).where(Chunk.id.in_(chunk_ids))
                )
                for chunk in chunk_result.scalars().all():
                    chunk_map[chunk.id] = chunk

            for idx, question in enumerate(questions):
                answer = question.answer
                chunk = chunk_map.get(question.chunk_id) if question.chunk_id else None
                chunk_content = chunk.content if chunk else ""

                # ── 第一层：基础校验 ──
                source = question.source or ""
                basic_status, basic_error = _basic_validate(answer, source)

                # ── 第二层 a：通用格式校验 ──
                format_ok = True
                format_detail = ""
                if answer:
                    format_ok, format_detail = _format_validate(answer)

                # ── 第二层 b：模板格式校验（仅结构化数据） ──
                template_ok = True
                template_detail = ""
                if answer and format_ok:
                    template_ok, template_detail = _template_format_validate(answer, source)

                # ── 第三层：语义校验 ──
                quality_score = None
                is_hallucination = False
                semantic_min_len = 2 if "structured" in source else 20
                if has_embedding and answer and len(answer.strip()) >= semantic_min_len and chunk_content:
                    similarity = await _semantic_validate(answer, chunk_content, embedding_model)
                    if similarity is not None:
                        quality_score = round(similarity, 4)
                        if similarity < 0.5:
                            is_hallucination = True

                # ── 汇总结果 ──
                if not format_ok:
                    answer_status = "failed"
                    answer_error = format_detail
                    format_error += 1
                elif not template_ok:
                    answer_status = "failed"
                    answer_error = template_detail
                    format_error += 1
                elif is_hallucination:
                    # 幻觉不算 failed，但标记警告
                    answer_status = question.answer_status or "completed"
                    answer_error = f"疑似幻觉（相似度 {quality_score}）"
                    hallucination += 1
                elif basic_status == "failed":
                    answer_status = "failed"
                    answer_error = basic_error
                    failed += 1
                else:
                    answer_status = "completed"
                    answer_error = ""
                    passed += 1

                # 更新 question 记录
                question.answer_status = answer_status
                question.answer_error = answer_error or None
                question.quality_score = quality_score

                # 幻觉标记写入 metadata
                if is_hallucination:
                    metadata = question.generation_metadata or {}
                    metadata["hallucination"] = True
                    question.generation_metadata = metadata
                elif question.generation_metadata and question.generation_metadata.get("hallucination"):
                    # 清除旧标记
                    metadata = question.generation_metadata
                    metadata.pop("hallucination", None)
                    question.generation_metadata = metadata

                # 进度更新（每 20 条或最后一条）
                if task and (idx % 20 == 0 or idx == total - 1):
                    task.progress = min(99, int((idx + 1) * 100 / total))
                    task.result = {
                        "total": total,
                        "passed": passed,
                        "hallucination": hallucination,
                        "format_error": format_error,
                        "failed": failed,
                    }
                    await db.commit()

            await db.commit()

            if task:
                task.status = "completed"
                task.progress = 100
                task.result = {
                    "total": total,
                    "passed": passed,
                    "hallucination": hallucination,
                    "format_error": format_error,
                    "failed": failed,
                }
                await db.commit()

            log_success(
                "质量校验完成",
                project_id=str(project_id),
                total=total,
                passed=passed,
                hallucination=hallucination,
                format_error=format_error,
                failed=failed,
            )

        except Exception as e:
            if task:
                task.status = "failed"
                task.error = str(e)
                await db.commit()
            log_failure("质量校验失败", project_id=str(project_id), error=str(e))
            logger.error(f"[质量校验] 失败: {e}")


# ──────────────────────────────────────────────
# 重新生成
# ──────────────────────────────────────────────

async def regenerate_answer_async(
    project_id: UUID,
    question_id: UUID,
) -> Optional[Question]:
    """基于原文上下文重新生成答案。"""
    async with AsyncSessionLocal() as db:
        try:
            # 加载问题和对应 chunk
            question = await db.get(Question, question_id)
            if not question or question.project_id != project_id:
                return None

            chunk = None
            if question.chunk_id:
                chunk = await db.get(Chunk, question.chunk_id)

            chunk_content = chunk.content if chunk else ""
            if not chunk_content:
                logger.warning(f"[重新生成] 问题 {question_id} 没有关联的文本切片")
                return question

            # 获取默认 chat 模型
            model_result = await db.execute(
                select(ModelConfig).where(
                    ModelConfig.project_id.is_(None),
                    ModelConfig.model_type.in_(["chat", "vlm"]),
                    ModelConfig.is_default == "true",
                )
            )
            model = model_result.scalar_one_or_none()
            if not model:
                # 再试项目级别
                model_result = await db.execute(
                    select(ModelConfig).where(
                        ModelConfig.project_id == project_id,
                        ModelConfig.model_type.in_(["chat", "vlm"]),
                        ModelConfig.is_default == "true",
                    )
                )
                model = model_result.scalar_one_or_none()

            if not model or not model.api_key:
                logger.error("[重新生成] 未找到可用的 chat 模型")
                return question

            # 重组提示词
            failure_hint = ""
            if question.answer_error:
                failure_hint = f"\n注意：上次生成失败，失败原因为「{question.answer_error}」，请避免同样的问题。"

            system_prompt = (
                "你是一名专业的问答数据构建助手。请根据给定的文本内容，"
                "对问题生成准确、完整的答案。答案必须直接引用文本中的信息，"
                "不得编造文本中不存在的内容。答案长度应不少于 50 字。"
                f"{failure_hint}"
            )

            user_prompt = (
                f"【文本内容】\n{chunk_content[:4000]}\n\n"
                f"【问题】\n{question.content}\n\n"
                "请根据文本内容生成问题的答案："
            )

            async with LLM_SEMAPHORE:
                new_answer = await call_generation_model(
                    model, system_prompt, user_prompt, temperature=0.7, json_output=False
                )

            new_answer = new_answer.strip()

            # 更新答案
            source = question.source or ""
            min_len = 2 if "structured" in source else 20
            if new_answer and len(new_answer) >= min_len:
                question.answer = new_answer
                question.answer_status = "completed"
                question.answer_error = None
                question.generation_status = "answered"
                # 清除旧的幻觉标记
                if question.generation_metadata and question.generation_metadata.get("hallucination"):
                    metadata = question.generation_metadata
                    metadata.pop("hallucination", None)
                    question.generation_metadata = metadata
            else:
                question.answer = new_answer or ""
                question.answer_status = "failed"
                question.answer_error = "重新生成失败：答案过短"
                question.generation_status = "answer_failed"

            await db.commit()
            await db.refresh(question)

            log_success(
                "答案重新生成完成",
                project_id=str(project_id),
                question_id=str(question_id),
                answer_status=question.answer_status,
            )

            return question

        except Exception as e:
            log_failure("答案重新生成失败", project_id=str(project_id), question_id=str(question_id), error=str(e))
            logger.error(f"[重新生成] 失败: {e}")
            return None
