"""
LLM Helper Functions

共享的 LLM 调用、prompt 构建、响应解析等工具函数。
供 API 层和 Service 层共同使用。
"""
import asyncio
import json
import re
import logging
from typing import List
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.models import Chunk, ModelConfig

# 并发控制信号量 - 限制同时进行的 LLM 调用数量，避免触发 429 频率限制
LLM_SEMAPHORE = asyncio.Semaphore(5)  # 最多同时 5 个 LLM 请求

VALID_MODEL_TYPES = {"chat", "vlm", "embedding", "rerank"}

# 任务取消标志存储（共享给 API 层和 Service 层）
cancelling_tasks: set[UUID] = set()

# 每 240 个字符生成 1 个问题（参考 easy-dataset）
CHARS_PER_QUESTION = 240


def normalize_model_type(model_type: str | None, model_name: str | None) -> str:
    """Normalize model type, with keyword fallback for legacy records."""
    if model_type in VALID_MODEL_TYPES and model_type != "chat":
        return model_type

    normalized_name = (model_name or "").strip().lower()
    rerank_keywords = ("rerank", "bce-reranker", "gte-rerank")
    embedding_keywords = (
        "embedding", "embed", "text-embedding", "bge-",
        "bge_m3", "gte-", "m3e", "e5-", "jina-embeddings",
    )
    vlm_keywords = ("vl", "vision", "visual", "multimodal", "qwen-vl", "gpt-4o")

    if any(keyword in normalized_name for keyword in rerank_keywords):
        return "rerank"
    if any(keyword in normalized_name for keyword in embedding_keywords):
        return "embedding"
    if any(keyword in normalized_name for keyword in vlm_keywords):
        return "vlm"
    return model_type if model_type in VALID_MODEL_TYPES else "chat"


def extract_text_from_response(data: dict) -> str:
    """Extract response text from provider response."""
    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [item.get("text", "") for item in content if isinstance(item, dict)]
            return "\n".join(part for part in parts if part)
        if isinstance(message.get("reasoning_content"), str):
            return message.get("reasoning_content", "")
    if isinstance(data.get("output_text"), str):
        return data.get("output_text", "")
    return ""


def parse_generated_questions(raw_text: str) -> List[dict]:
    """Parse JSON array from model output."""
    text = (raw_text or "").strip()
    if not text:
        return []

    text = re.sub(r"<Thinking>\s*.*?\s*</Thinking>", "", text, flags=re.S).strip()

    fenced_match = re.search(r"```json\s*(.*?)\s*```", text, flags=re.S)
    if fenced_match:
        text = fenced_match.group(1).strip()

    if not text.startswith("["):
        array_match = re.search(r"(\[\s*\{.*\}\s*\])", text, flags=re.S)
        if array_match:
            text = array_match.group(1)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []

    if isinstance(parsed, dict):
        for key in ("questions", "qa_pairs", "items", "data", "result"):
            value = parsed.get(key)
            if isinstance(value, list):
                parsed = value
                break

    if not isinstance(parsed, list):
        return []

    normalized = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        question_type = str(item.get("question_type", "fact")).strip() or "fact"
        if not question:
            continue
        normalized.append({
            "question": question,
            "answer": answer,
            "question_type": question_type
        })
    return normalized


DEFAULT_PRESET_PROMPT = (
    "你是一名高质量中文问答数据构建助手，负责基于给定文本块生成可用于训练和评测的问句。\n"
    "你的目标是产出准确、自然、覆盖关键信息、表达清晰的中文问句。\n\n"
    "生成原则：\n"
    "1. 问题必须紧扣文本内容，优先覆盖定义、流程、规则、职责、约束、条件、结论和关键细节。\n"
    "2. 问题应尽量具体，避免泛化提问。\n"
    "3. 若内容包含步骤、条款、角色分工、判断条件、注意事项，应优先围绕这些可验证信息出题。\n"
    "4. 若文本主要是目录、页眉页脚、版本号、页码、短标题、噪声片段或信息过少，应减少或放弃生成。\n"
    "5. 问题表达要自然，适合用于中文知识问答训练，不要出现机械措辞。\n"
    "6. 保持问题之间不重复，避免同义改写造成冗余样本。\n"
    "7. 问题长度尽量控制在 12 到 28 个中文字符之间。\n"
    "8. 问题表达要像真实用户会提出的问题，句式要有变化，不要连续生成结构高度相似的问题。"
)


def build_system_prompt(preset_prompt: str, count: int) -> str:
    """Build system prompt for question generation."""
    cleaned_prompt = re.sub(r"<\/?Thinking[^>]*>", "", preset_prompt).strip()

    return (
        f"你是问答数据构建助手，必须严格按照以下任务说明生成问句。\n\n"
        f"【核心任务说明】\n"
        f"{cleaned_prompt}\n\n"
        f"【问题类型定义】\n"
        f"- fact（事实型）: 询问可从文本直接提取的具体信息，如定义、数值、条款、角色、约束条件等\n"
        f"- summary（概括型）: 询问文本的主要内容、主题或核心观点\n"
        f"- reasoning（推理型）: 询问原因、目的、方法、步骤、逻辑推导等\n\n"
        f"【生成流程】（必须严格遵循）\n"
        f"1. 文本解析：通读全文，分段识别关键实体、事件、数值与结论\n"
        f"2. 问题设计：基于信息密度和重要性选择最佳提问切入点\n"
        f"3. 质量检查：确保问题可在原文中直接找到依据，问题之间主题不重复\n\n"
        f"【问题质量要求】\n"
        f"- 所有问题必须严格依据原文内容，不得添加外部信息或假设情境\n"
        f"- 问题需覆盖文本的不同主题、层级或视角，避免集中于单一片段\n"
        f"- 问题表述准确、无歧义且符合常规问句形式，不含\"请问\"、\"能否\"等前缀\n"
        f"- 问题不得包含\"报告/文章/文献/表格中提到\"等表述，需自然流畅\n"
        f"- 问题之间主题不重复，避免集中在同一主题连续提问\n\n"
        f"【输出要求】\n"
        f"1. 生成 {count} 个问题，优先选择 fact 和 reasoning 类型\n"
        f"2. 每个问题必须标注 question_type（fact/summary/reasoning）\n"
        f"3. 只输出 JSON 数组，不要输出任何 <Thinking> 标签、解释、标题或 Markdown\n"
        f"4. 格式: [{{\"question\":\"...\",\"question_type\":\"...\"}}]\n"
        f"5. 即使文本信息量较少，也要尽量生成 1-2 个基础问题（如询问文本主题、关键术语等）\n"
        f"6. 只有在文本完全是乱码、空白或纯符号时，才返回空数组 []"
    )


def build_user_prompt(chunk: Chunk, thinking_mode: bool) -> str:
    """Build user prompt with chunk context."""
    return (
        f"【Chunk 名称】{chunk.name or '未命名分片'}\n\n"
        f"【Chunk 内容】\n{chunk.content}"
    )


def build_user_prompt_with_context(
    chunk: Chunk,
    prev_chunks: list,
    next_chunks: list,
    thinking_mode: bool,
) -> str:
    """Build user prompt with neighboring chunk context for context-enhanced mode."""
    parts = [f"【Chunk 名称】{chunk.name or '未命名分片'}\n"]

    if prev_chunks:
        prev_content = "\n---\n".join(
            f"[{c.name or '未命名'}]: {c.content}" for c in prev_chunks
        )
        parts.append(f"【前文上下文（仅供参考，帮助理解当前文本的背景）】\n{prev_content}\n")

    parts.append(f"【当前 Chunk 内容（基于此生成问答）】\n{chunk.content}")

    if next_chunks:
        next_content = "\n---\n".join(
            f"[{c.name or '未命名'}]: {c.content}" for c in next_chunks
        )
        parts.append(f"【后文上下文（仅供参考，帮助理解当前文本的延续）】\n{next_content}")

    return "\n".join(parts)


def build_full_doc_system_prompt(preset_prompt: str, count: int) -> str:
    """Build system prompt for full-document generation mode."""
    cleaned_prompt = re.sub(r"<\/?Thinking[^>]*>", "", preset_prompt).strip()

    return (
        f"你是问答数据构建助手，必须严格按照以下任务说明生成问句。\n\n"
        f"【核心任务说明】\n"
        f"{cleaned_prompt}\n\n"
        f"【重要：这是全文模式】\n"
        f"你将看到一份文档的完整内容。请基于全文视角生成问题，重点关注：\n"
        f"- 文档的整体主题、核心观点和结构脉络（summary 型）\n"
        f"- 跨章节/跨段落的关系、对比、因果推理（reasoning 型）\n"
        f"- 全文中的关键定义、重要结论、核心约束条件（fact 型）\n"
        f"- 避免只关注局部细节，优先生成需要全局理解才能回答的问题\n\n"
        f"【问题类型定义】\n"
        f"- fact（事实型）: 询问可从文本直接提取的具体信息\n"
        f"- summary（概括型）: 询问文本的主要内容、主题或核心观点\n"
        f"- reasoning（推理型）: 询问原因、目的、方法、步骤、逻辑推导、跨章节关系等\n\n"
        f"【生成流程】\n"
        f"1. 全文通读：理解文档整体结构、各章节主题和逻辑关系\n"
        f"2. 问题设计：优先选择需要全局视角的问题切入点\n"
        f"3. 质量检查：确保问题可在原文中找到依据，问题之间主题不重复\n\n"
        f"【输出要求】\n"
        f"1. 生成 {count} 个问题，优先选择 summary 和 reasoning 类型\n"
        f"2. 每个问题必须标注 question_type（fact/summary/reasoning）\n"
        f"3. 只输出 JSON 数组，不要输出任何 <Thinking> 标签、解释、标题或 Markdown\n"
        f"4. 格式: [{{\"question\":\"...\",\"question_type\":\"...\"}}]\n"
        f"5. 只有在文本完全是乱码、空白或纯符号时，才返回空数组 []"
    )


def build_full_doc_prompt(
    file_content: str,
    filename: str,
    thinking_mode: bool,
) -> str:
    """Build user prompt for full-document generation mode."""
    return (
        f"【文件名称】{filename}\n\n"
        f"【文件完整内容】\n{file_content}"
    )


def build_answer_prompt(question_content: str, chunk_content: str) -> str:
    """Build prompt for generating answer based on question and chunk content."""
    return f"""# Role: 微调数据集生成专家

## Profile:
- Description: 你是一名微调数据集生成专家，擅长从给定的内容中生成准确的问题答案，确保答案的准确性和相关性，你要直接回答用户问题，所有信息已内化为你的专业知识。

## Skills:
1. 答案必须基于给定的内容
2. 答案必须准确，不能胡编乱造
3. 答案必须与问题相关
4. 答案必须符合逻辑
5. 基于给定参考内容，用自然流畅的语言整合成一个完整答案，不需要提及文献来源或引用标记

## Workflow:
1. Take a deep breath and work on this problem step-by-step.
2. 首先，分析给定的文件内容，理解其核心含义
3. 然后，从内容中提取与问题相关的所有关键信息
4. 接着，整合关键信息，用自然语言生成完整、详细的答案
5. 最后，确保答案充分详尽，包含所有必要信息

## 参考内容：

------ 参考内容 Start ------
{chunk_content}
------ 参考内容 End ------

## 问题
{question_content}

## Constrains:
1. 答案必须基于给定的参考内容，从内容中提取和整合信息
2. 答案必须准确、详尽、完整，包含所有必要的信息点
3. 答案长度不能少于50个中文字符，越详尽越好
4. 答案中不得出现"参考"、"依据"、"文献中提到"、"如图所示"等任何引用性表述
5. 用自然流畅的语言整合成完整答案，不要分点列举（除非问题要求）
6. 直接给出最终答案即可，不需要任何思考过程、解释或铺垫"""


async def evaluate_chunk_quality(
    model: ModelConfig,
    chunk_content: str,
    temperature: float = 0.3,
) -> tuple[bool, str]:
    """
    使用 LLM 评估 chunk 内容质量，判断是否适合生成问答对。

    返回：(是否可生成问题，跳过原因)
    - (True, ""): 可以生成问题
    - (False, "reason"): 跳过，reason 是跳过原因
    """
    eval_system_prompt = """你是问答数据质量评估助手，负责判断给定文本是否适合生成问答对。

评估标准（满足任一即判定为不适合）：
1. 空白内容或纯符号乱码
2. 纯目录/索引/章节列表（没有实质内容）
3. 纯页眉页脚/页码/版本信息
4. 纯图表标题/表格标题（没有实际图表内容）
5. 信息量过少（少于 50 字有效内容）
6. 内容不完整/截断严重

输出要求：
- 只输出 JSON 格式：{"can_generate": true/false, "reason": "跳过原因（如果不能生成）"}
- 如果 can_generate 为 true，reason 可以为空字符串
"""

    eval_user_prompt = f"""请评估以下文本是否适合生成问答对：

【文本内容】
{chunk_content[:2000]}"""

    try:
        async with LLM_SEMAPHORE:
            raw_text = await call_generation_model(
                model,
                eval_system_prompt,
                eval_user_prompt,
                temperature=temperature,
                json_output=True,
            )

        logger.info(f"[LLM 质量评估] 原始响应：{raw_text[:500]}")

        try:
            result = json.loads(raw_text)
            can_generate = result.get("can_generate", True)
            reason = result.get("reason", "")

            if can_generate:
                logger.info("[LLM 质量评估] 结果：✓ 可以生成问题")
            else:
                logger.info(f"[LLM 质量评估] 结果：✗ 跳过 - {reason}")

            return (bool(can_generate), reason)
        except json.JSONDecodeError as e:
            logger.warning(f"[LLM 质量评估] JSON 解析失败，默认可以生成：{raw_text[:200]}")
            return (True, "")
    except Exception as e:
        logger.warning(f"[LLM 质量评估] 调用失败，默认可以生成：chunk_error={str(e)}")
        return (True, "")


async def call_generation_model(
    model: ModelConfig,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    json_output: bool = True,
    max_retries: int = 3,
) -> str:
    """
    Call configured chat model for generation.

    带重试机制：遇到 429 频率限制时自动重试（指数退避）
    """
    api_key = model.api_key
    api_base = model.api_base or "https://api.openai.com/v1"
    # 兜底补全协议，防止用户漏填 https://
    if api_base and not api_base.startswith(("http://", "https://")):
        api_base = f"https://{api_base}"
    model_name = model.model_name

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    messages = []
    if system_prompt and system_prompt.strip():
        messages.append({
            "role": "system",
            "content": system_prompt,
        })
    messages.append({
        "role": "user",
        "content": user_prompt,
    })

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
    }

    last_exception = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                response = await client.post(
                    f"{api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                )

                response.raise_for_status()
                data = response.json()
                content = extract_text_from_response(data)
                if not content:
                    raise ValueError(f"Model returned empty content: response_keys={list(data.keys())}")

                if json_output and content.lstrip().startswith("{"):
                    obj = json.loads(content)
                    if isinstance(obj, dict) and isinstance(obj.get("questions"), list):
                        return json.dumps(obj["questions"], ensure_ascii=False)
                return content

        except httpx.HTTPStatusError as e:
            last_exception = e
            status_code = e.response.status_code
            if (status_code == 429 or status_code >= 500) and attempt < max_retries - 1:
                wait_time = 1.0 * (2 ** attempt)
                error_type = "429 频率限制" if status_code == 429 else f"{status_code} 服务器错误"
                logger.warning(f"LLM 调用触发 {error_type}，等待 {wait_time}s 后重试 (attempt={attempt + 1}/{max_retries}), url={api_base}")
                await asyncio.sleep(wait_time)
            else:
                try:
                    error_body = e.response.text[:500]
                except Exception:
                    error_body = "无法读取错误详情"
                logger.error(f"LLM 调用失败: status={status_code}, url={api_base}, model={model_name}, error={error_body}")
                raise
        except httpx.TimeoutException as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = 1.0 * (2 ** attempt)
                logger.warning(f"LLM 调用超时，等待 {wait_time}s 后重试 (attempt={attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
            else:
                raise
        except Exception as e:
            last_exception = e
            logger.error(f"LLM 调用异常: {str(e)}")
            raise

    raise last_exception or Exception("LLM 调用失败")
