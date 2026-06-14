import re
import uuid
import math
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np

try:
    import jieba
    _jieba_available = True
except ImportError:
    _jieba_available = False

from backend.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    doc_id: str
    title: str
    content: str
    score: float
    metadata: Optional[Dict[str, Any]] = None
    chunk_index: int = 0


class BM25Retriever:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self._k1 = k1
        self._b = b
        self._docs: Dict[str, str] = {}
        self._doc_tokens: Dict[str, List[str]] = {}
        self._df: Dict[str, int] = defaultdict(int)
        self._avg_dl: float = 0.0
        self._fitted = False

    def _tokenize(self, text: str) -> List[str]:
        if _jieba_available:
            return list(jieba.cut(text))
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', text.lower())
        result = []
        for token in tokens:
            if re.match(r'[\u4e00-\u9fff]+', token):
                for i in range(len(token)):
                    for j in range(i + 1, min(i + 4, len(token) + 1)):
                        result.append(token[i:j])
            else:
                result.append(token)
        return result

    def add_document(self, doc_id: str, text: str):
        self._docs[doc_id] = text
        self._fitted = False

    def _fit(self):
        self._doc_tokens = {}
        self._df = defaultdict(int)
        total_dl = 0
        for doc_id, text in self._docs.items():
            tokens = self._tokenize(text)
            self._doc_tokens[doc_id] = tokens
            total_dl += len(tokens)
            seen = set()
            for t in tokens:
                if t not in seen:
                    self._df[t] += 1
                    seen.add(t)
        n = len(self._docs)
        self._avg_dl = total_dl / n if n > 0 else 0
        self._fitted = True

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self._docs:
            return []
        if not self._fitted:
            self._fit()
        query_tokens = self._tokenize(query)
        n = len(self._docs)
        scores: Dict[str, float] = defaultdict(float)
        for doc_id, doc_tokens in self._doc_tokens.items():
            dl = len(doc_tokens)
            tf_map: Dict[str, int] = defaultdict(int)
            for t in doc_tokens:
                tf_map[t] += 1
            for qt in query_tokens:
                tf = tf_map.get(qt, 0)
                if tf == 0:
                    continue
                df = self._df.get(qt, 0)
                idf = math.log((n - df + 0.5) / (df + 0.5) + 1)
                numerator = tf * (self._k1 + 1)
                denominator = tf + self._k1 * (1 - self._b + self._b * dl / max(self._avg_dl, 1))
                scores[doc_id] += idf * numerator / denominator
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [{"doc_id": doc_id, "score": score} for doc_id, score in sorted_results]


class RRFFusion:
    def __init__(self, k: int = 60):
        self._k = k

    def fuse(self, result_lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        rrf_scores: Dict[str, float] = defaultdict(float)
        for results in result_lists:
            for rank, item in enumerate(results, start=1):
                doc_id = item.get("doc_id", "")
                rrf_scores[doc_id] += 1.0 / (self._k + rank)
        sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [{"doc_id": doc_id, "score": score} for doc_id, score in sorted_items]


class _EmbeddingBackend:
    def encode(self, texts: List[str]) -> np.ndarray:
        raise NotImplementedError

    def is_available(self) -> bool:
        return False


class _SentenceTransformerBackend(_EmbeddingBackend):
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name)
            self._dim = self._model.get_sentence_embedding_dimension()
            logger.info(f"SentenceTransformer backend loaded: {model_name}, dim={self._dim}")
        except Exception as e:
            logger.warning(f"Failed to load SentenceTransformer ({model_name}): {e}")
            self._model = None
            self._dim = 0

    def encode(self, texts: List[str]) -> np.ndarray:
        if self._model is None:
            return np.array([])
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return np.array(embeddings, dtype=np.float32)

    def is_available(self) -> bool:
        return self._model is not None

    @property
    def dim(self) -> int:
        return self._dim


class _TfidfBackend(_EmbeddingBackend):
    def __init__(self):
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self._vectorizer = TfidfVectorizer(max_features=512)
            self._fitted = False
            self._dim = 512
            logger.info("TF-IDF backend initialized as fallback")
        except ImportError:
            self._vectorizer = None
            self._dim = 0
            logger.warning("sklearn not available, TF-IDF backend disabled")

    def encode(self, texts: List[str]) -> np.ndarray:
        if self._vectorizer is None:
            return np.array([])
        if not self._fitted:
            tfidf_matrix = self._vectorizer.fit_transform(texts)
            self._fitted = True
        else:
            tfidf_matrix = self._vectorizer.transform(texts)
        dense = tfidf_matrix.toarray().astype(np.float32)
        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return dense / norms

    def is_available(self) -> bool:
        return self._vectorizer is not None

    @property
    def dim(self) -> int:
        return self._dim


class _KeywordBackend(_EmbeddingBackend):
    def __init__(self):
        self._vocab: Dict[str, int] = {}
        self._dim = 256
        logger.info("Keyword matching backend initialized as last resort")

    def _tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+', text.lower())
        result = []
        for token in tokens:
            if re.match(r'[\u4e00-\u9fff]+', token):
                for i in range(len(token)):
                    for j in range(i + 1, min(i + 4, len(token) + 1)):
                        result.append(token[i:j])
            else:
                result.append(token)
        return list(set(result))

    def encode(self, texts: List[str]) -> np.ndarray:
        all_tokens = set()
        tokenized = []
        for text in texts:
            tokens = self._tokenize(text)
            tokenized.append(tokens)
            all_tokens.update(tokens)

        for token in all_tokens:
            if token not in self._vocab:
                self._vocab[token] = len(self._vocab) % self._dim

        embeddings = []
        for tokens in tokenized:
            vec = np.zeros(self._dim, dtype=np.float32)
            for token in tokens:
                if token in self._vocab:
                    vec[self._vocab[token]] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            embeddings.append(vec)
        return np.array(embeddings, dtype=np.float32)

    def is_available(self) -> bool:
        return True

    @property
    def dim(self) -> int:
        return self._dim


class VectorStore:
    def __init__(self, dim: int):
        self._dim = dim
        self._vectors: np.ndarray = np.empty((0, dim), dtype=np.float32)
        self._chunk_ids: List[str] = []
        self._chunk_doc_ids: List[str] = []
        self._chunk_indices: List[int] = []

    def add(self, chunk_id: str, doc_id: str, chunk_index: int, vector: np.ndarray):
        vec = vector.reshape(1, -1).astype(np.float32)
        if self._vectors.shape[0] == 0:
            self._vectors = vec
        else:
            self._vectors = np.vstack([self._vectors, vec])
        self._chunk_ids.append(chunk_id)
        self._chunk_doc_ids.append(doc_id)
        self._chunk_indices.append(chunk_index)

    def remove_by_doc(self, doc_id: str):
        keep_mask = [did != doc_id for did in self._chunk_doc_ids]
        if not any(keep_mask):
            self._vectors = np.empty((0, self._dim), dtype=np.float32)
            self._chunk_ids = []
            self._chunk_doc_ids = []
            self._chunk_indices = []
            return
        keep_indices = [i for i, k in enumerate(keep_mask) if k]
        self._vectors = self._vectors[keep_indices]
        self._chunk_ids = [self._chunk_ids[i] for i in keep_indices]
        self._chunk_doc_ids = [self._chunk_doc_ids[i] for i in keep_indices]
        self._chunk_indices = [self._chunk_indices[i] for i in keep_indices]

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> List[Dict[str, Any]]:
        if self._vectors.shape[0] == 0:
            return []
        q = query_vector.reshape(1, -1).astype(np.float32)
        scores = np.dot(self._vectors, q.T).flatten()
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            results.append({
                "chunk_id": self._chunk_ids[idx],
                "doc_id": self._chunk_doc_ids[idx],
                "chunk_index": self._chunk_indices[idx],
                "score": float(scores[idx]),
            })
        return results

    def clear(self):
        self._vectors = np.empty((0, self._dim), dtype=np.float32)
        self._chunk_ids = []
        self._chunk_doc_ids = []
        self._chunk_indices = []

    @property
    def size(self) -> int:
        return self._vectors.shape[0]


class RAGEngine:
    def __init__(self):
        self._documents: Dict[str, Dict[str, Any]] = {}
        self._chunks: Dict[str, Dict[str, Any]] = {}
        self._backend: Optional[_EmbeddingBackend] = None
        self._vector_store: Optional[VectorStore] = None
        self._chunk_size = settings.rag_chunk_size
        self._chunk_overlap = settings.rag_chunk_overlap
        self._init_backend()
        self._bm25 = BM25Retriever()
        self._rrf = RRFFusion()

    def _init_backend(self):
        if not settings.rag_enabled:
            logger.info("RAG engine disabled by configuration")
            return

        st_backend = _SentenceTransformerBackend(settings.rag_embedding_model)
        if st_backend.is_available():
            self._backend = st_backend
            self._vector_store = VectorStore(st_backend.dim)
            return

        tfidf_backend = _TfidfBackend()
        if tfidf_backend.is_available():
            self._backend = tfidf_backend
            self._vector_store = VectorStore(tfidf_backend.dim)
            return

        kw_backend = _KeywordBackend()
        self._backend = kw_backend
        self._vector_store = VectorStore(kw_backend.dim)
        logger.info("Using keyword matching backend as last resort")

    @property
    def available(self) -> bool:
        return self._backend is not None and self._backend.is_available()

    def _chunk_text(self, text: str) -> List[str]:
        paragraphs = re.split(r'\n+', text)
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) <= self._chunk_size:
                current_chunk += ("\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append(current_chunk)

                if len(para) <= self._chunk_size:
                    if self._chunk_overlap > 0 and chunks:
                        overlap_text = chunks[-1][-self._chunk_overlap:]
                        current_chunk = overlap_text + "\n" + para
                    else:
                        current_chunk = para
                else:
                    for i in range(0, len(para), self._chunk_size - self._chunk_overlap):
                        chunk = para[i:i + self._chunk_size]
                        if chunk.strip():
                            chunks.append(chunk)
                    current_chunk = ""

        if current_chunk.strip():
            chunks.append(current_chunk)

        return chunks if chunks else [text[:self._chunk_size]]

    def add_document(self, doc_id: str, title: str, content: str, metadata: dict = None):
        self._documents[doc_id] = {
            "id": doc_id,
            "title": title,
            "content": content,
            "metadata": metadata or {},
            "chunk_count": 0,
        }

        if not self.available:
            logger.warning(f"RAG engine not available, document {doc_id} stored without indexing")
            return

        text_chunks = self._chunk_text(content)
        self._vector_store.remove_by_doc(doc_id)

        texts_to_encode = [f"{title}: {chunk}" if title else chunk for chunk in text_chunks]
        embeddings = self._backend.encode(texts_to_encode)

        if embeddings.size == 0:
            logger.warning(f"Failed to encode chunks for document {doc_id}")
            return

        for i, (chunk_text, embedding) in enumerate(zip(text_chunks, embeddings)):
            chunk_id = f"{doc_id}_chunk_{i}"
            self._chunks[chunk_id] = {
                "id": chunk_id,
                "doc_id": doc_id,
                "chunk_index": i,
                "content": chunk_text,
            }
            self._vector_store.add(chunk_id, doc_id, i, embedding)

        self._documents[doc_id]["chunk_count"] = len(text_chunks)
        self._bm25.add_document(doc_id, f"{title} {content}")
        logger.info(f"Added document {doc_id} with {len(text_chunks)} chunks")

    def add_documents(self, docs: List[dict]):
        for doc in docs:
            doc_id = doc.get("id", str(uuid.uuid4())[:8])
            self.add_document(
                doc_id=doc_id,
                title=doc.get("title", ""),
                content=doc.get("content", ""),
                metadata=doc.get("metadata"),
            )

    def search(self, query: str, top_k: int = 5, threshold: float = 0.3) -> List[SearchResult]:
        if not self.available:
            return []

        query_embedding = self._backend.encode([query])
        if query_embedding.size == 0:
            return []

        raw_results = self._vector_store.search(query_embedding[0], top_k=top_k)

        search_results = []
        for raw in raw_results:
            if raw["score"] < threshold:
                continue
            chunk = self._chunks.get(raw["chunk_id"], {})
            doc = self._documents.get(raw["doc_id"], {})
            search_results.append(SearchResult(
                doc_id=raw["doc_id"],
                title=doc.get("title", ""),
                content=chunk.get("content", ""),
                score=raw["score"],
                metadata=doc.get("metadata"),
                chunk_index=raw["chunk_index"],
            ))

        return search_results

    def hybrid_search(self, query: str, top_k: int = 5, threshold: float = 0.3, vector_weight: float = 0.6, bm25_weight: float = 0.4) -> List[SearchResult]:
        vector_results = []
        if self.available:
            query_embedding = self._backend.encode([query])
            if query_embedding.size > 0:
                raw_results = self._vector_store.search(query_embedding[0], top_k=top_k * 2)
                vector_results = [
                    {"doc_id": r["doc_id"], "score": r["score"] * vector_weight}
                    for r in raw_results if r["score"] >= threshold
                ]

        bm25_results = []
        try:
            raw_bm25 = self._bm25.search(query, top_k=top_k * 2)
            max_bm25 = max((r["score"] for r in raw_bm25), default=1.0)
            bm25_results = [
                {"doc_id": r["doc_id"], "score": (r["score"] / max_bm25) * bm25_weight}
                for r in raw_bm25
            ]
        except Exception as e:
            logger.warning(f"BM25 search failed: {e}")

        if not vector_results and not bm25_results:
            return self.search(query, top_k=top_k, threshold=threshold)

        fused = self._rrf.fuse([vector_results, bm25_results])
        search_results = []
        for item in fused[:top_k]:
            doc = self._documents.get(item["doc_id"], {})
            best_chunk = None
            for cid, chunk in self._chunks.items():
                if chunk.get("doc_id") == item["doc_id"]:
                    if best_chunk is None:
                        best_chunk = chunk
            search_results.append(SearchResult(
                doc_id=item["doc_id"],
                title=doc.get("title", ""),
                content=best_chunk.get("content", doc.get("content", "")) if best_chunk else doc.get("content", ""),
                score=item["score"],
                metadata=doc.get("metadata"),
                chunk_index=best_chunk.get("chunk_index", 0) if best_chunk else 0,
            ))
        return search_results

    def delete_document(self, doc_id: str) -> bool:
        if doc_id not in self._documents:
            return False

        if self._vector_store:
            self._vector_store.remove_by_doc(doc_id)

        chunks_to_remove = [
            cid for cid, chunk in self._chunks.items()
            if chunk.get("doc_id") == doc_id
        ]
        for cid in chunks_to_remove:
            del self._chunks[cid]

        del self._documents[doc_id]
        logger.info(f"Deleted document {doc_id} and {len(chunks_to_remove)} chunks")
        return True

    def get_document(self, doc_id: str) -> dict:
        doc = self._documents.get(doc_id)
        if doc is None:
            return None
        return dict(doc)

    def list_documents(self) -> List[dict]:
        return [dict(doc) for doc in self._documents.values()]

    async def answer_question(self, question: str, top_k: int = 3) -> Dict[str, Any]:
        search_results = self.search(question, top_k=top_k, threshold=settings.rag_similarity_threshold)

        if not search_results:
            return {
                "answer": "未找到与您问题相关的知识条目，建议联系运维专家或查阅更多文档。",
                "sources": [],
                "confidence": 0.1,
            }

        context_parts = []
        sources = []
        for i, result in enumerate(search_results):
            context_parts.append(f"[{i + 1}] {result.title}: {result.content}")
            sources.append({
                "title": result.title,
                "score": round(result.score, 4),
                "chunk_index": result.chunk_index,
            })

        context_text = "\n\n".join(context_parts)
        confidence = min(search_results[0].score, 0.95)

        try:
            from backend.agents.llm_gateway import get_llm_gateway, TaskType
            gateway = get_llm_gateway()

            system_prompt = """你是智维AgentHub的知识问答助手。请根据提供的参考资料回答用户问题。

要求：
1. 优先基于参考资料中的信息回答
2. 如果参考资料不足以回答问题，请如实说明
3. 回答使用中文
4. 引用资料时标注来源编号"""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"参考资料：\n{context_text}\n\n问题：{question}"},
            ]

            result = await gateway.chat(
                messages,
                task_type=TaskType.COPILOT_CHAT,
                temperature=0.3,
                max_tokens=1024,
            )

            return {
                "answer": result["content"],
                "sources": sources,
                "confidence": round(confidence, 4),
                "provider": result.get("provider"),
                "model": result.get("model"),
            }
        except Exception as e:
            logger.warning(f"LLM generation failed, falling back to direct retrieval: {e}")
            return {
                "answer": search_results[0].content,
                "sources": sources,
                "confidence": round(confidence, 4),
            }

    def rebuild_index(self):
        if not self.available:
            logger.warning("RAG engine not available, cannot rebuild index")
            return

        docs = dict(self._documents)
        self._chunks.clear()
        self._vector_store.clear()

        for doc_id, doc in docs.items():
            text_chunks = self._chunk_text(doc["content"])
            texts_to_encode = [f"{doc['title']}: {chunk}" if doc.get("title") else chunk for chunk in text_chunks]
            embeddings = self._backend.encode(texts_to_encode)

            if embeddings.size == 0:
                continue

            for i, (chunk_text, embedding) in enumerate(zip(text_chunks, embeddings)):
                chunk_id = f"{doc_id}_chunk_{i}"
                self._chunks[chunk_id] = {
                    "id": chunk_id,
                    "doc_id": doc_id,
                    "chunk_index": i,
                    "content": chunk_text,
                }
                self._vector_store.add(chunk_id, doc_id, i, embedding)

            docs[doc_id]["chunk_count"] = len(text_chunks)

        self._documents = docs
        logger.info(f"Rebuilt index with {len(self._documents)} documents, {self._vector_store.size} chunks")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_documents": len(self._documents),
            "total_chunks": len(self._chunks),
            "index_size": self._vector_store.size if self._vector_store else 0,
            "backend": type(self._backend).__name__ if self._backend else "none",
            "available": self.available,
            "embedding_model": settings.rag_embedding_model if self.available else "none",
        }


_rag_engine: Optional[RAGEngine] = None


def get_rag_engine() -> RAGEngine:
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine()
    return _rag_engine
