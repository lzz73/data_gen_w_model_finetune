"""
LLM-based Text Summarization Service
基于 LLM 的文本摘要服务
"""
import httpx
import asyncio
import logging
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 线程池：在同步方法中运行异步 HTTP 调用
_executor = ThreadPoolExecutor(max_workers=4)


class SummarizationService:
    """
    基于 LLM 的文本摘要服务

    使用智谱 GLM 对文本 chunk 生成简洁的摘要
    """

    # 摘要生成提示词
    DEFAULT_SUMMARIZATION_PROMPT = """你是一名专业的文本摘要助手。请基于给定的文本内容，生成一段简洁、准确的摘要。

要求：
1. 摘要长度控制在 50-150 字之间
2. 必须准确反映原文的核心内容和关键信息
3. 语言简洁、通顺，适合中文读者阅读
4. 不要添加原文中没有的信息
5. 如果文本是技术文档，要保留关键术语和核心概念
6. 如果文本包含多个主题，要涵盖主要主题

只输出摘要内容，不要输出任何解释、前缀或后缀。

文本内容：
{content}

摘要："""

    def __init__(self, api_key: str, api_base: str, model_name: str):
        self.api_key = api_key
        self.api_base = api_base
        self.model_name = model_name

    def summarize(self, content: str, max_length: int = 150) -> str:
        """
        对给定内容生成摘要

        Args:
            content: 需要摘要的文本内容
            max_length: 摘要最大长度（字）

        Returns:
            生成的摘要文本
        """
        if not content or len(content.strip()) < 50:
            # 内容太短，直接返回
            return content.strip() if content else "空内容"

        # 如果内容本身就不长，直接截取
        if len(content) <= max_length:
            return content.strip()

        # 构建提示词（限制输入长度，避免超出 token 限制）
        prompt = self.DEFAULT_SUMMARIZATION_PROMPT.format(content=content[:4000])

        try:
            # 在独立线程中运行异步 HTTP 调用
            # 避免同步 httpx.Client 在容器/Docker 环境中的网络问题
            future = _executor.submit(asyncio.run, self._call_llm(prompt))
            summary = future.result(timeout=65)

            if summary:
                # 确保摘要不超过最大长度
                if len(summary) > max_length:
                    summary = summary[:max_length]
                    # 尝试在句子边界处切断
                    for sep in ['。', '！', '？', '.', '!', '?']:
                        last_sep = summary.rfind(sep)
                        if last_sep > max_length * 0.7:
                            summary = summary[:last_sep + 1]
                            break

                return summary

            return "生成摘要超时"

        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            return "生成摘要超时"
        except Exception as e:
            logger.warning(f"生成摘要失败: {e}")
            return f"生成摘要失败"

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM API（异步，与生成问题使用相同的 httpx.AsyncClient）"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,  # 较低温度，确保摘要准确
            "max_tokens": 200
        }

        url = f"{self.api_base}/chat/completions"

        logger.info(f"正在调用 LLM API: url={url}, model={self.model_name}")

        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            response = await client.post(url, headers=headers, json=payload)

            logger.info(f"API 响应状态码：{response.status_code}")

            response.raise_for_status()
            data = response.json()

            # 提取响应内容 - 尝试多种可能的格式
            content = None

            # 格式 1: 标准 OpenAI 格式
            if "choices" in data and len(data["choices"]) > 0:
                message = data["choices"][0].get("message", {})
                content = message.get("content")
                # 有些模型返回 reasoning_content
                if not content:
                    content = message.get("reasoning_content")

            # 格式 2: 直接 output_text
            if not content:
                content = data.get("output_text")

            # 格式 3: data 数组
            if not content and "data" in data:
                data_list = data.get("data", [])
                if data_list and len(data_list) > 0:
                    content = data_list[0].get("text") or data_list[0].get("content")

            if content:
                content = content.strip()
                logger.info(f"LLM 返回摘要：{content[:100]}...")
                return content

            logger.error(f"LLM 响应中无法提取内容：{data}")
            return ""

    def _fallback_summarize(self, content: str, max_length: int) -> str:
        """
        降级到规则式摘要（当 LLM 不可用时）

        策略：
        1. 提取第一段和最后一段的关键句子
        2. 尝试在句子边界处切断
        """
        paragraphs = content.split('\n\n')

        # 取第一段和最后一段（通常包含核心信息）
        key_paragraphs = []
        if paragraphs:
            key_paragraphs.append(paragraphs[0].strip())
        if len(paragraphs) > 1:
            key_paragraphs.append(paragraphs[-1].strip())

        preview = ' '.join(key_paragraphs)

        if len(preview) <= max_length:
            return preview

        # 截取并在句子边界处切断
        truncated = preview[:max_length]
        for sep in ['。', '！', '？', '.', '!', '?']:
            last_sep = truncated.rfind(sep)
            if last_sep > max_length * 0.5:
                return truncated[:last_sep + 1]

        return truncated.rstrip() + '...'


# 全局单例
_summarizer: Optional[SummarizationService] = None


def get_summarizer(api_key: str = None, api_base: str = None, model_name: str = None) -> SummarizationService:
    """
    获取摘要服务单例

    首次调用时必须传入配置参数，后续调用可省略（复用已有实例）。
    如果传入新的配置参数，会重新创建实例。
    """
    global _summarizer
    if _summarizer is None:
        if not api_key or not api_base or not model_name:
            raise ValueError("首次获取 SummarizationService 必须提供 api_key, api_base, model_name 参数")
        _summarizer = SummarizationService(api_key=api_key, api_base=api_base, model_name=model_name)
    return _summarizer


def summarize_text(content: str, max_length: int = 150) -> str:
    """便捷方法：生成文本摘要"""
    summarizer = get_summarizer()
    return summarizer.summarize(content, max_length)
