import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
from ..database.connection import get_db_session
from ..database.models import KnowledgeDocumentVersion
from .deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


# ──────────────────────── 向量库懒加载实例 ────────────────────────

_vector_store = None


def _get_vector_store():
    """懒加载 VectorStore 实例，从环境变量读取连接参数。"""
    global _vector_store
    if _vector_store is None:
        from ..knowledge.vector_store import VectorStore

        chroma_host = os.getenv("CHROMA_HOST", "chromadb")
        chroma_port = int(os.getenv("CHROMA_PORT", "8000"))
        _vector_store = VectorStore(
            chroma_host=chroma_host,
            chroma_port=chroma_port,
        )
    return _vector_store


# ──────────────────────── 请求模型 ────────────────────────


class DocumentCreate(BaseModel):
    document_id: str
    content: str
    embedding_id: Optional[str] = None


class DocumentUpdate(BaseModel):
    content: Optional[str] = None
    embedding_id: Optional[str] = None


class DocumentSearchRequest(BaseModel):
    query: str
    top_k: int = 5


# ──────────────────────── 文档 CRUD ────────────────────────


@router.get("/documents")
async def list_documents(
    document_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(KnowledgeDocumentVersion)
    if document_id:
        query = query.where(KnowledgeDocumentVersion.document_id == document_id)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    docs = result.scalars().all()
    return {"status": "success", "data": [{"id": d.id, "document_id": d.document_id, "version": d.version, "embedding_id": d.embedding_id, "created_at": d.created_at.isoformat() if d.created_at else None} for d in docs]}


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "success", "data": {"id": doc.id, "document_id": doc.document_id, "version": doc.version, "content": doc.content, "embedding_id": doc.embedding_id}}


@router.post("/documents")
async def create_document(
    req: DocumentCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    version_result = await db.execute(
        select(func.max(KnowledgeDocumentVersion.version)).where(KnowledgeDocumentVersion.document_id == req.document_id)
    )
    max_version = version_result.scalar() or 0
    doc = KnowledgeDocumentVersion(document_id=req.document_id, version=max_version + 1, content=req.content, embedding_id=req.embedding_id)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # 同步到向量库（失败不影响主流程）
    try:
        vs = _get_vector_store()
        vector_doc_id = f"{req.document_id}_v{max_version + 1}"
        synced = await vs.add_document(
            doc_id=vector_doc_id,
            text=req.content,
            metadata={"document_id": req.document_id, "version": max_version + 1},
        )
        if synced:
            logger.info("文档 %s 已同步到向量库", vector_doc_id)
        else:
            logger.warning("文档 %s 同步到向量库失败（向量库可能不可用）", vector_doc_id)
    except Exception as exc:
        logger.warning("文档同步到向量库异常: %s", exc)

    return {"status": "success", "data": {"id": doc.id, "document_id": doc.document_id, "version": doc.version}}


@router.put("/documents/{doc_id}")
async def update_document(
    doc_id: int,
    req: DocumentUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # 如果更新了 content，创建新版本并同步向量库
    if req.content is not None and req.content != doc.content:
        # 1. 先从向量库删除旧版本向量
        try:
            vs = _get_vector_store()
            old_vector_id = f"{doc.document_id}_v{doc.version}"
            deleted = await vs.delete_document(doc_id=old_vector_id)
            if deleted:
                logger.info("文档 %s 旧版本向量已从向量库删除", old_vector_id)
            else:
                logger.warning("文档 %s 旧版本向量删除失败（向量库可能不可用）", old_vector_id)
        except Exception as exc:
            logger.warning("文档旧版本向量删除异常: %s", exc)

        # 2. 计算新版本号并创建新记录
        version_result = await db.execute(
            select(func.max(KnowledgeDocumentVersion.version)).where(KnowledgeDocumentVersion.document_id == doc.document_id)
        )
        max_version = version_result.scalar() or 0
        new_version = max_version + 1

        new_doc = KnowledgeDocumentVersion(
            document_id=doc.document_id,
            version=new_version,
            content=req.content,
            embedding_id=req.embedding_id or doc.embedding_id,
        )
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)

        # 3. 同步新版本到向量库
        try:
            vs = _get_vector_store()
            new_vector_id = f"{doc.document_id}_v{new_version}"
            synced = await vs.add_document(
                doc_id=new_vector_id,
                text=req.content,
                metadata={"document_id": doc.document_id, "version": new_version},
            )
            if synced:
                logger.info("文档 %s 新版本已同步到向量库", new_vector_id)
            else:
                logger.warning("文档 %s 新版本同步到向量库失败（向量库可能不可用）", new_vector_id)
        except Exception as exc:
            logger.warning("文档新版本同步到向量库异常: %s", exc)

        return {"status": "success", "data": {"id": new_doc.id, "document_id": new_doc.document_id, "version": new_doc.version}}

    # 仅更新 embedding_id（不涉及内容变更，不创建新版本）
    if req.embedding_id is not None:
        doc.embedding_id = req.embedding_id
        await db.commit()
        await db.refresh(doc)

    return {"status": "success", "data": {"id": doc.id, "document_id": doc.document_id, "version": doc.version}}


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(KnowledgeDocumentVersion).where(KnowledgeDocumentVersion.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # 先从向量库删除（失败不影响主流程）
    try:
        vs = _get_vector_store()
        vector_doc_id = f"{doc.document_id}_v{doc.version}"
        deleted = await vs.delete_document(doc_id=vector_doc_id)
        if deleted:
            logger.info("文档 %s 已从向量库删除", vector_doc_id)
        else:
            logger.warning("文档 %s 从向量库删除失败（向量库可能不可用）", vector_doc_id)
    except Exception as exc:
        logger.warning("文档从向量库删除异常: %s", exc)

    await db.delete(doc)
    await db.commit()
    return {"status": "success"}


# ──────────────────────── 语义搜索 ────────────────────────


@router.post("/search")
async def search_knowledge(
    req: DocumentSearchRequest,
    current_user=Depends(get_current_user),
):
    try:
        vs = _get_vector_store()
        results = await vs.search(
            query=req.query,
            top_k=req.top_k,
        )
        return {
            "status": "success",
            "data": {
                "query": req.query,
                "results": results,
                "total": len(results),
            },
        }
    except Exception as exc:
        logger.warning("语义搜索失败: %s", exc)
        return {
            "status": "success",
            "data": {
                "query": req.query,
                "results": [],
                "total": 0,
                "message": "向量搜索服务暂时不可用，请稍后重试",
            },
        }
