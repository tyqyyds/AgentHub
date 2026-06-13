import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 默认嵌入向量维度（all-MiniLM-L6-v2 输出384维）
DEFAULT_EMBEDDING_DIMENSION = 384


class EmbeddingService:
    """嵌入服务：使用 sentence-transformers 生成文本嵌入向量。"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model: Optional[object] = None
        self._dimension = DEFAULT_EMBEDDING_DIMENSION
        self._initialized = False

    def _ensure_model(self) -> None:
        """懒加载模型，仅在首次调用时加载。"""
        if self._initialized:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
            self._dimension = self._model.get_sentence_embedding_dimension()
            self._initialized = True
            logger.info(
                "EmbeddingService 初始化成功，模型=%s，维度=%d",
                self._model_name,
                self._dimension,
            )
        except Exception as exc:
            logger.warning(
                "EmbeddingService 模型加载失败（model=%s）: %s。将返回空向量作为降级。",
                self._model_name,
                exc,
            )
            self._model = None
            self._initialized = True  # 标记已尝试初始化，避免重复加载

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, text: str) -> list[float]:
        """生成单文本嵌入向量。模型不可用时返回空向量。"""
        self._ensure_model()
        if self._model is None:
            logger.warning("EmbeddingService 不可用，返回空向量")
            return [0.0] * self._dimension

        try:
            embedding = await asyncio.to_thread(
                self._model.encode, text, {"show_progress_bar": False}
            )
            return embedding.tolist()
        except Exception as exc:
            logger.warning("embed_text 失败: %s", exc)
            return [0.0] * self._dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成嵌入向量。模型不可用时返回空向量列表。"""
        self._ensure_model()
        if self._model is None:
            logger.warning("EmbeddingService 不可用，返回空向量列表")
            return [[0.0] * self._dimension for _ in texts]

        try:
            embeddings = await asyncio.to_thread(
                self._model.encode, texts, {"show_progress_bar": False}
            )
            return [e.tolist() for e in embeddings]
        except Exception as exc:
            logger.warning("embed_texts 失败: %s", exc)
            return [[0.0] * self._dimension for _ in texts]
