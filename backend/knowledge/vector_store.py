import asyncio
import logging
from typing import Optional

from .embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class VectorStore:
    """向量存储服务：使用 ChromaDB 进行文档的向量存储与语义搜索。"""

    def __init__(
        self,
        collection_name: str = "knowledge_base",
        chroma_host: str = "chromadb",
        chroma_port: int = 8000,
    ):
        self._collection_name = collection_name
        self._chroma_host = chroma_host
        self._chroma_port = chroma_port
        self._client = None
        self._collection = None
        self._embedding_service = EmbeddingService()
        self._initialized = False

    def _ensure_connection(self) -> None:
        """懒加载 ChromaDB 连接，仅在首次调用时建立。"""
        if self._initialized:
            return
        try:
            import chromadb

            self._client = chromadb.HttpClient(
                host=self._chroma_host,
                port=self._chroma_port,
            )
            # 健康检查
            self._client.heartbeat()
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
            )
            self._initialized = True
            logger.info(
                "VectorStore 连接成功，host=%s:%d，collection=%s",
                self._chroma_host,
                self._chroma_port,
                self._collection_name,
            )
        except Exception as exc:
            logger.warning(
                "VectorStore 连接 ChromaDB 失败（host=%s:%d）: %s。将返回空结果作为降级。",
                self._chroma_host,
                self._chroma_port,
                exc,
            )
            self._client = None
            self._collection = None
            self._initialized = True  # 标记已尝试，避免重复连接

    async def add_document(
        self, doc_id: str, text: str, metadata: Optional[dict] = None
    ) -> bool:
        """添加文档到向量库。返回是否成功。"""
        self._ensure_connection()
        if self._collection is None:
            logger.warning("VectorStore 不可用，跳过添加文档 doc_id=%s", doc_id)
            return False

        try:
            embedding = await self._embedding_service.embed_text(text)
            # 如果嵌入全为0（降级），仍然存储原文，但搜索质量会受影响
            await asyncio.to_thread(
                self._collection.upsert,
                ids=[doc_id],
                documents=[text],
                embeddings=[embedding],
                metadatas=[metadata or {}],
            )
            logger.info("文档已添加到向量库: doc_id=%s", doc_id)
            return True
        except Exception as exc:
            logger.warning("add_document 失败 doc_id=%s: %s", doc_id, exc)
            return False

    async def add_documents(self, documents: list[dict]) -> list[bool]:
        """批量添加文档。每个文档格式: {"doc_id": str, "text": str, "metadata": dict}。"""
        self._ensure_connection()
        if self._collection is None:
            logger.warning("VectorStore 不可用，跳过批量添加 %d 个文档", len(documents))
            return [False] * len(documents)

        try:
            ids = [d["doc_id"] for d in documents]
            texts = [d["text"] for d in documents]
            metadatas = [d.get("metadata", {}) for d in documents]

            embeddings = await self._embedding_service.embed_texts(texts)

            await asyncio.to_thread(
                self._collection.upsert,
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            logger.info("批量添加 %d 个文档到向量库", len(documents))
            return [True] * len(documents)
        except Exception as exc:
            logger.warning("add_documents 批量添加失败: %s", exc)
            return [False] * len(documents)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[dict] = None,
    ) -> list[dict]:
        """语义搜索，返回最相似的文档列表。"""
        self._ensure_connection()
        if self._collection is None:
            logger.warning("VectorStore 不可用，返回空搜索结果")
            return []

        try:
            query_embedding = await self._embedding_service.embed_text(query)

            query_kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
            }
            if filter_metadata:
                query_kwargs["where"] = filter_metadata

            results = await asyncio.to_thread(
                self._collection.query,
                **query_kwargs,
            )

            # 解析 ChromaDB 返回结果
            search_results: list[dict] = []
            if results and results.get("ids") and results["ids"][0]:
                ids = results["ids"][0]
                documents = results.get("documents", [[]])[0]
                distances = results.get("distances", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]

                for i, doc_id in enumerate(ids):
                    # ChromaDB 返回的是距离（越小越相似），转换为相似度分数
                    distance = distances[i] if i < len(distances) else 1.0
                    score = max(0.0, 1.0 - distance)

                    search_results.append(
                        {
                            "id": doc_id,
                            "text": documents[i] if i < len(documents) else "",
                            "score": round(score, 4),
                            "metadata": metadatas[i] if i < len(metadatas) else {},
                        }
                    )

            return search_results
        except Exception as exc:
            logger.warning("search 失败: %s", exc)
            return []

    async def delete_document(self, doc_id: str) -> bool:
        """删除文档。返回是否成功。"""
        self._ensure_connection()
        if self._collection is None:
            logger.warning("VectorStore 不可用，跳过删除文档 doc_id=%s", doc_id)
            return False

        try:
            await asyncio.to_thread(
                self._collection.delete,
                ids=[doc_id],
            )
            logger.info("文档已从向量库删除: doc_id=%s", doc_id)
            return True
        except Exception as exc:
            logger.warning("delete_document 失败 doc_id=%s: %s", doc_id, exc)
            return False

    async def get_document(self, doc_id: str) -> Optional[dict]:
        """获取单个文档。"""
        self._ensure_connection()
        if self._collection is None:
            logger.warning("VectorStore 不可用，无法获取文档 doc_id=%s", doc_id)
            return None

        try:
            results = await asyncio.to_thread(
                self._collection.get,
                ids=[doc_id],
            )

            if results and results.get("ids") and results["ids"]:
                documents = results.get("documents", [])
                metadatas = results.get("metadatas", [])
                return {
                    "id": results["ids"][0],
                    "text": documents[0] if documents else "",
                    "metadata": metadatas[0] if metadatas else {},
                }
            return None
        except Exception as exc:
            logger.warning("get_document 失败 doc_id=%s: %s", doc_id, exc)
            return None
