"""
Semantic Text Splitter using Online Embedding APIs
基于在线 Embedding API 的语义分割器
"""
import re
import asyncio
import httpx
import numpy as np
from typing import List, Dict, Optional
from abc import ABC, abstractmethod
from langchain_text_splitters import RecursiveCharacterTextSplitter


class EmbeddingProvider(ABC):
    """Embedding API 提供商基类"""

    @abstractmethod
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """获取文本的嵌入向量"""
        pass


class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI 兼容的 Embedding API"""

    def __init__(self, api_key: str, base_url: str, model: str = "text-embedding-3-small"):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """调用 OpenAI 兼容的 Embedding API"""
        import logging
        logger = logging.getLogger("yg_dataset")

        filtered = [t if t and t.strip() else "空" for t in texts]

        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "input": filtered,
                "model": self.model
            }

            logger.info(f"[OpenAIEmbedding] URL={self.base_url}/embeddings model={self.model} count={len(filtered)} key={self.api_key[:10]}...")

            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json=payload
            )

            if response.status_code != 200:
                logger.error(f"[OpenAIEmbedding] HTTP {response.status_code}: {response.text[:1000]}")
                raise Exception(f"Embedding API error {response.status_code}: {response.text[:500]}")

            data = response.json()
            return [item["embedding"] for item in data["data"]]


class AliEmbedding(EmbeddingProvider):
    """阿里云百炼 Embedding API (DashScope OpenAI 兼容模式)"""

    def __init__(self, api_key: str, base_url: str, model: str = "text-embedding-v4"):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """调用阿里云百炼 Embedding API (OpenAI 兼容模式)"""
        import logging
        logger = logging.getLogger("yg_dataset")

        filtered = [t if t and t.strip() else "空" for t in texts]

        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "input": filtered,
                "model": self.model
            }

            logger.info(f"[AliEmbedding] URL={self.base_url}/embeddings model={self.model} count={len(filtered)} key={self.api_key[:10]}...")

            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json=payload
            )

            if response.status_code != 200:
                logger.error(f"[AliEmbedding] HTTP {response.status_code}: {response.text[:1000]}")
                raise Exception(f"Embedding API error {response.status_code}: {response.text[:500]}")

            data = response.json()
            return [item["embedding"] for item in data["data"]]


class MiniMaxEmbedding(EmbeddingProvider):
    """MiniMax Embedding API"""

    def __init__(self, api_key: str, base_url: str = "https://api.minimax.chat/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """调用 MiniMax Embedding API"""
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            # MiniMax 格式
            payload = {
                "texts": texts,
                "model": "embo-01"
            }

            response = await client.post(
                f"{self.base_url}/text_embeddings",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            # MiniMax 返回格式可能不同，需要适配
            if "data" in data:
                return [item["embedding"] for item in data["data"]]
            return []


class EmbeddingSplitter:
    """基于 Embedding 的语义分割器基类"""

    def __init__(
        self,
        chunk_size: int = 500,
        overlap: int = 50,
        embedding_provider: Optional[EmbeddingProvider] = None,
        similarity_threshold: float = 0.3,
        min_chunk_size: int = 100,
        window_size: int = 3
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.embedding_provider = embedding_provider
        self.similarity_threshold = similarity_threshold
        self.min_chunk_size = min_chunk_size
        self.window_size = window_size

    def _tokenize_sentences(self, text: str) -> List[str]:
        """将文本切分为句子"""
        paragraphs = re.split(r'\n\s*\n+', text)
        sentences = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            parts = re.split(r'(?<=[。！？；.!?])\s+|(?<=[。！？；])', para)
            buffer = []

            for part in parts:
                part = part.strip()
                if not part:
                    continue

                # 过短的片段先暂存，尽量与后一句合并，避免 embedding 粒度过碎
                if len(part) < 8 and buffer:
                    buffer[-1] = f"{buffer[-1]} {part}".strip()
                else:
                    buffer.append(part)

            sentences.extend(buffer)

        return sentences

    def _compute_similarities(self, embeddings: List[List[float]]) -> List[float]:
        """计算相邻句子的余弦相似度"""
        similarities = []

        for i in range(len(embeddings) - 1):
            # 余弦相似度
            vec1 = np.array(embeddings[i])
            vec2 = np.array(embeddings[i + 1])

            # 归一化
            vec1 = vec1 / (np.linalg.norm(vec1) + 1e-8)
            vec2 = vec2 / (np.linalg.norm(vec2) + 1e-8)

            # 点积 = 余弦相似度（归一化后）
            sim = np.dot(vec1, vec2)
            similarities.append(float(sim))

        return similarities

    def _smooth_similarities(self, similarities: List[float]) -> List[float]:
        """滑动窗口平滑相似度"""
        if not similarities:
            return []

        window = max(1, self.window_size)
        smoothed = []

        for i in range(len(similarities)):
            start = max(0, i - window)
            end = min(len(similarities), i + window + 1)
            window_vals = similarities[start:end]
            smoothed.append(sum(window_vals) / len(window_vals))

        return smoothed

    def _detect_boundaries(self, similarities: List[float], sentence_lengths: List[int]) -> List[int]:
        """检测分割点（相似度显著下降的位置）

        纯语义驱动，不设切片大小上限，保证语义完整性。
        只要话题转变就切，无论累积长度。
        """
        if not similarities:
            return [0]

        smoothed = self._smooth_similarities(similarities)
        if len(smoothed) <= 1:
            return [0]

        mean_sim = float(np.mean(smoothed))
        std_sim = float(np.std(smoothed))
        dynamic_threshold = max(0.0, min(0.95, mean_sim - 0.5 * std_sim))
        effective_threshold = max(self.similarity_threshold, dynamic_threshold)

        boundaries = [0]  # 起始点
        accumulated_chars = 0

        for i, sim in enumerate(smoothed):
            accumulated_chars += sentence_lengths[i]

            left_sim = smoothed[i - 1] if i > 0 else 1.0
            right_sim = smoothed[i + 1] if i < len(smoothed) - 1 else 1.0
            is_local_min = sim <= left_sim and sim <= right_sim
            has_enough_context = accumulated_chars >= self.min_chunk_size

            # 纯语义断点：话题转变就切，不因长度强制截断
            if is_local_min and has_enough_context and sim <= effective_threshold:
                boundaries.append(i + 1)
                accumulated_chars = 0

        boundaries.append(len(sentence_lengths))

        return sorted(list(set(boundaries)))

    def _assemble_chunks(self, sentences: List[str], boundaries: List[int]) -> List[Dict]:
        """按分割点组装 chunks，保持语义完整性不做截断"""
        if not sentences:
            return []

        # 重新计算 boundaries（确保不超过句子数）
        if not boundaries or boundaries[0] != 0:
            boundaries = [0] + boundaries
        if boundaries[-1] != len(sentences):
            boundaries.append(len(sentences))

        chunks = []
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i + 1]
            if start >= end:
                continue

            chunk_text = ' '.join(sentences[start:end]).strip()
            if not chunk_text:
                continue

            chunks.append({
                "index": len(chunks),
                "content": chunk_text.strip(),
                "word_count": len(chunk_text.split()),
                "char_count": len(chunk_text)
            })

        # 合并过小的相邻 chunks
        chunks = self._merge_small_chunks(chunks)

        return chunks

    def _merge_small_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """合并过小的相邻 chunks，不设上限以保持语义完整性"""
        if len(chunks) <= 1:
            return chunks

        merged = [chunks[0]]

        for chunk in chunks[1:]:
            previous = merged[-1]
            should_merge = (
                previous["char_count"] < self.min_chunk_size or
                chunk["char_count"] < self.min_chunk_size
            )

            # 只要有一方过小就合并，不限制合并后大小
            if should_merge:
                previous["content"] += " " + chunk["content"]
                previous["word_count"] += chunk["word_count"]
                previous["char_count"] += chunk["char_count"]
            else:
                merged.append(chunk)

        for index, chunk in enumerate(merged):
            chunk["index"] = index

        return merged

    async def split_with_embedding(self, text: str) -> List[Dict]:
        """使用 Embedding 进行语义分割"""
        # 1. 句子切分
        sentences = self._tokenize_sentences(text)
        if not sentences:
            return []

        # 过滤纯噪音片段，但保留正常短句
        sentences = [s for s in sentences if len(s.strip()) >= 4]

        if not sentences:
            return []

        # 2. 如果只有一个句子，直接返回
        if len(sentences) == 1:
            return [{
                "index": 0,
                "content": sentences[0],
                "word_count": len(sentences[0].split()),
                "char_count": len(sentences[0])
            }]

        # 3. 调用 Embedding API
        try:
            if self.embedding_provider is None:
                raise ValueError("embedding provider is not configured")
            embeddings = await self.embedding_provider.get_embeddings(sentences)
        except Exception as e:
            # 如果 embedding 失败，降级到规则分割
            print(f"Embedding failed, falling back to rule-based: {e}")
            return self._fallback_split(text)

        if len(embeddings) != len(sentences):
            return self._fallback_split(text)

        # 4. 计算相似度
        similarities = self._compute_similarities(embeddings)

        # 5. 检测分割点
        boundaries = self._detect_boundaries(similarities, [len(sentence) for sentence in sentences])

        # 6. 组装 chunks
        chunks = self._assemble_chunks(sentences, boundaries)

        return chunks

    def _fallback_split(self, text: str) -> List[Dict]:
        """降级到规则分割"""
        # 使用 langchain 的 RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.overlap,
            separators=["\n\n", "\n", "。", "！", "？", ". ", "! ", "? "]
        )
        chunks = splitter.split_text(text)
        return [{
            "index": i,
            "content": c.strip(),
            "word_count": len(c.split()),
            "char_count": len(c)
        } for i, c in enumerate(chunks)]


class SemanticEmbeddingSplitter(EmbeddingSplitter):
    """基于在线 Embedding 的语义分割器"""

    def __init__(
        self,
        chunk_size: int = 500,
        overlap: int = 50,
        embedding_provider: Optional[EmbeddingProvider] = None,
        similarity_threshold: float = 0.3,
        min_chunk_size: int = 100,
        window_size: int = 3
    ):
        super().__init__(
            chunk_size=chunk_size,
            overlap=overlap,
            embedding_provider=embedding_provider,
            similarity_threshold=similarity_threshold,
            min_chunk_size=min_chunk_size,
            window_size=window_size
        )

    def split(self, text: str) -> List[Dict]:
        """同步接口，内部调用异步"""
        # 由于 split 是同步方法，需要创建新的事件循环
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果在异步环境中，创建新任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.split_with_embedding(text))
                    return future.result()
            else:
                return loop.run_until_complete(self.split_with_embedding(text))
        except RuntimeError:
            # 没有事件循环，直接创建
            return asyncio.run(self.split_with_embedding(text))


def create_embedding_provider(provider: str, api_key: str, base_url: str, model: str = None) -> EmbeddingProvider:
    """创建 Embedding 提供商"""
    if provider in ["openai", "compatible", "glm"]:
        return OpenAIEmbedding(api_key, base_url, model or "text-embedding-3-small")
    elif provider == "ali":
        return AliEmbedding(api_key, base_url, model or "text-embedding-v4")
    elif provider == "minimax":
        return MiniMaxEmbedding(api_key, base_url)
    else:
        raise ValueError(f"Unsupported embedding provider: {provider}")
