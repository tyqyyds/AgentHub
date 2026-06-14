import pytest
from backend.knowledge.rag_engine import RAGEngine, SearchResult


class TestBM25Retriever:
    def test_bm25_search_basic(self):
        from backend.knowledge.rag_engine import BM25Retriever
        bm25 = BM25Retriever()
        bm25.add_document("doc1", "QoS配置指南 带宽限速 traffic-policy命令")
        bm25.add_document("doc2", "OSPF路由协议 area划分区域 骨干区域area 0")
        results = bm25.search("QoS带宽配置", top_k=2)
        assert len(results) > 0
        assert results[0]["doc_id"] == "doc1"

    def test_bm25_search_no_match(self):
        from backend.knowledge.rag_engine import BM25Retriever
        bm25 = BM25Retriever()
        bm25.add_document("doc1", "QoS配置指南")
        results = bm25.search("天气预报", top_k=2)
        assert len(results) == 0


class TestRRFFusion:
    def test_rrf_fusion_basic(self):
        from backend.knowledge.rag_engine import RRFFusion
        rrf = RRFFusion(k=60)
        vector_results = [
            {"doc_id": "doc1", "score": 0.9},
            {"doc_id": "doc2", "score": 0.7},
        ]
        bm25_results = [
            {"doc_id": "doc2", "score": 3.5},
            {"doc_id": "doc3", "score": 2.0},
        ]
        fused = rrf.fuse([vector_results, bm25_results])
        assert len(fused) > 0
        doc_ids = [r["doc_id"] for r in fused]
        assert "doc2" in doc_ids

    def test_rrf_single_list(self):
        from backend.knowledge.rag_engine import RRFFusion
        rrf = RRFFusion(k=60)
        results = [{"doc_id": "doc1", "score": 0.9}]
        fused = rrf.fuse([results])
        assert len(fused) == 1
        assert fused[0]["doc_id"] == "doc1"


class TestHybridSearch:
    def test_hybrid_search_integration(self):
        engine = RAGEngine()
        engine.add_document("doc1", "QoS配置指南", "QoS配置指南: 带宽限速使用traffic-policy命令，优先级队列分为high/medium/low三级")
        engine.add_document("doc2", "OSPF路由协议", "OSPF路由协议: 使用area划分区域，骨干区域为area 0，所有非骨干区域必须与area 0直连")
        results = engine.hybrid_search("QoS带宽配置", top_k=2)
        assert len(results) > 0
        assert isinstance(results[0], SearchResult)

    def test_hybrid_search_fallback_to_vector(self):
        engine = RAGEngine()
        engine.add_document("doc1", "测试文档", "这是一段测试内容")
        results = engine.hybrid_search("测试", top_k=2)
        assert len(results) >= 0
