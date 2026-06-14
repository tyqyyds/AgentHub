import os
import uuid
import logging
import json
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

from backend.core.security.rbac import get_current_user, requires_permission
from backend.knowledge.qa_agent import qa_agent
from backend.core.config import settings
from backend.api.response import success_response
from backend.agents.assistant_router import AssistantRouterAgent
from backend.agents.react_engine import get_react_engine, ReActEngine
from backend.agents.proactive_notifier import get_proactive_notifier
from backend.agents.multimodal_processor import get_multimodal_processor
from backend.agents.quick_command_manager import get_quick_command_manager
from backend.database.connection import get_db_session, async_session_maker
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.models import Device, DeviceLink, AuditLog, Intent

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "knowledge")
os.makedirs(UPLOAD_DIR, exist_ok=True)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

assistant_agent = AssistantRouterAgent()

ASSISTANT_UPLOAD_DIR = "backend/data/uploads"
os.makedirs(ASSISTANT_UPLOAD_DIR, exist_ok=True)


async def _query_system_health(message: str, username: str) -> Dict[str, Any]:
    try:
        async with async_session_maker() as db:
            total_devices = await db.scalar(select(func.count(Device.id)))
            online_devices = await db.scalar(select(func.count(Device.id)).where(Device.status == 'online'))
            health_pct = round((online_devices / total_devices * 100), 1) if total_devices else 100
            status = '🟢 良好' if health_pct >= 90 else '🟡 一般' if health_pct >= 70 else '🔴 告警'
            return {
                'content': f'**系统健康度报告**\n\n'
                           f'状态：{status}\n'
                           f'健康度：**{health_pct}%**\n'
                           f'在线设备：{online_devices}/{total_devices}\n'
                           f'离线设备：{total_devices - online_devices}',
                'actions': [
                    {'type': 'navigate', 'label': '查看指挥舱', 'params': {'route': '/'}}
                ],
                'intent_type': 'query'
            }
    except Exception as e:
        logger.error(f"Query system health failed: {e}")
        return {"content": "系统健康状态查询暂时不可用", "actions": [], "intent_type": "query"}


async def _query_pending_alerts(message: str, username: str) -> Dict[str, Any]:
    try:
        async with async_session_maker() as db:
            # 从事件表获取告警数据
            from sqlalchemy import text
            result = await db.execute(
                text("SELECT * FROM events ORDER BY created_at DESC LIMIT 10")
            )
            events = result.fetchall()

            if not events:
                # 降级到审计日志
                critical_count = await db.scalar(
                    select(func.count(AuditLog.id)).where(AuditLog.security_type == 'critical')
                )
                warning_count = await db.scalar(
                    select(func.count(AuditLog.id)).where(AuditLog.security_type == 'warning')
                )
                return {
                    'content': f'**告警概览**\n\n'
                               f'🔴 严重告警：**{critical_count}** 条\n'
                               f'🟡 警告告警：**{warning_count}** 条\n'
                               f'总计：**{critical_count + warning_count}** 条未处理',
                    'actions': [
                        {'type': 'navigate', 'label': '查看自愈面板', 'params': {'route': '/self-healing'}},
                        {'type': 'navigate', 'label': '查看审计日志', 'params': {'route': '/audit'}}
                    ],
                    'intent_type': 'query'
                }

            # 构建告警表格
            rows = []
            critical = 0
            warning = 0
            for evt in events:
                row = dict(evt._mapping)
                severity = row.get('severity', 'info')
                title = row.get('title', row.get('action', '未知'))
                device = row.get('device_name', row.get('source', '未知'))
                status = row.get('status', '未知')
                time_str = str(row.get('created_at', ''))[:16] if row.get('created_at') else '未知'
                severity_icon = '🔴' if severity == 'critical' else '🟡' if severity == 'warning' else '🔵'
                rows.append(f'| {severity_icon} {severity} | {title[:20]} | {device} | {status} | {time_str} |')
                if severity == 'critical':
                    critical += 1
                elif severity == 'warning':
                    warning += 1

            content = f'**告警概览**\n\n'
            content += f'🔴 严重：**{critical}** | 🟡 警告：**{warning}** | 总计：**{len(events)}** 条\n\n'
            content += '| 级别 | 告警 | 设备 | 状态 | 时间 |\n'
            content += '|------|------|------|------|------|\n'
            content += '\n'.join(rows)

            return {
                'content': content,
                'actions': [
                    {'type': 'navigate', 'label': '查看自愈面板', 'params': {'route': '/self-healing'}},
                    {'type': 'navigate', 'label': '查看审计日志', 'params': {'route': '/audit'}}
                ],
                'intent_type': 'query'
            }
    except Exception as e:
        logger.error(f"Query pending alerts failed: {e}")
        return {"content": "告警查询暂时不可用", "actions": [], "intent_type": "query"}


async def _query_pending_approvals(message: str, username: str) -> Dict[str, Any]:
    try:
        async with async_session_maker() as db:
            from sqlalchemy import desc
            # 获取待审批意图
            pending_intents = await db.execute(
                select(Intent).where(Intent.approval_status == 'pending').order_by(desc(Intent.created_at)).limit(10)
            )
            pending_list = pending_intents.scalars().all()
            pending_count = len(pending_list)

            # 获取所有意图统计
            total_count = await db.scalar(select(func.count(Intent.id)))
            approved_count = await db.scalar(
                select(func.count(Intent.id)).where(Intent.approval_status == 'approved')
            )
            rejected_count = await db.scalar(
                select(func.count(Intent.id)).where(Intent.approval_status == 'rejected')
            )

            content = f'**意图审批概览**\n\n'
            content += f'待审批：**{pending_count}** | 已批准：**{approved_count}** | 已拒绝：**{rejected_count}** | 总计：**{total_count}**\n\n'

            if pending_list:
                content += '**待审批意图：**\n\n'
                content += '| 意图名称 | 类型 | 优先级 | 创建时间 |\n'
                content += '|----------|------|--------|----------|\n'
                for intent in pending_list:
                    name = getattr(intent, 'intent_name', '未知')[:20]
                    itype = getattr(intent, 'intent_type', '未知')
                    priority = getattr(intent, 'priority', '中')
                    time_str = intent.created_at.strftime('%m-%d %H:%M') if hasattr(intent, 'created_at') and intent.created_at else '未知'
                    content += f'| {name} | {itype} | {priority} | {time_str} |\n'

            return {
                'content': content,
                'actions': [
                    {'type': 'navigate', 'label': '前往意图中心', 'params': {'route': '/intent'}}
                ],
                'intent_type': 'query'
            }
    except Exception as e:
        logger.error(f"Query pending approvals failed: {e}")
        return {"content": "审批待办查询暂时不可用", "actions": [], "intent_type": "query"}


async def _query_agent_distribution(message: str, username: str) -> Dict[str, Any]:
    try:
        async with async_session_maker() as db:
            total = await db.scalar(select(func.count(Device.id)))
            online = await db.scalar(select(func.count(Device.id)).where(Device.status == 'online'))
            return {
                'content': f'**智能体分布概览**\n\n'
                           f'总设备数：**{total}**\n'
                           f'在线：**{online}** | 离线：**{total - online}**',
                'actions': [
                    {'type': 'navigate', 'label': '查看智能体地图', 'params': {'route': '/agent-map'}},
                    {'type': 'navigate', 'label': '查看网络拓扑', 'params': {'route': '/topology'}}
                ],
                'intent_type': 'query'
            }
    except Exception as e:
        logger.error(f"Query agent distribution failed: {e}")
        return {"content": "智能体分布查询暂时不可用", "actions": [], "intent_type": "query"}


async def _query_device_status(message: str, username: str) -> Dict[str, Any]:
    try:
        device_name = None
        for pattern, etype in [
            (r'((?:路由器|交换机|防火墙|服务器|设备)\s*[A-Za-z0-9\-_]+)', 'device'),
        ]:
            import re
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                device_name = match.group(1).strip()
                break

        async with async_session_maker() as db:
            if device_name:
                escaped_name = device_name.replace('%', '\\%').replace('_', '\\_')
                device = await db.scalar(
                    select(Device).where(Device.name.ilike(f'%{escaped_name}%', escape='\\'))
                )
                if device:
                    status_emoji = '🟢' if device.status == 'online' else '🔴'
                    return {
                        'content': f'**{device.name} 状态报告**\n\n'
                                   f'状态：{status_emoji} {device.status}\n'
                                   f'类型：{getattr(device, "device_type", "未知")}\n'
                                   f'IP地址：{getattr(device, "ip_address", "未知")}',
                        'actions': [
                            {'type': 'navigate', 'label': '查看网络拓扑', 'params': {'route': '/topology'}},
                            {'type': 'highlight', 'label': f'在拓扑中高亮{device.name}', 'params': {'node': device.name}}
                        ],
                        'intent_type': 'query'
                    }
                else:
                    return {
                        'content': f'未找到设备 **{device_name}**。请检查设备名称是否正确。',
                        'actions': [
                            {'type': 'navigate', 'label': '查看网络拓扑', 'params': {'route': '/topology'}}
                        ],
                        'intent_type': 'query'
                    }
            else:
                total = await db.scalar(select(func.count(Device.id)))
                online = await db.scalar(select(func.count(Device.id)).where(Device.status == 'online'))
                return {
                    'content': f'**设备状态概览**\n\n'
                               f'总设备：**{total}**\n'
                               f'在线：**🟢 {online}** | 离线：**🔴 {total - online}**',
                    'actions': [
                        {'type': 'navigate', 'label': '查看网络拓扑', 'params': {'route': '/topology'}}
                    ],
                    'intent_type': 'query'
                }
    except Exception as e:
        logger.error(f"Query device status failed: {e}")
        return {"content": "设备状态查询暂时不可用", "actions": [], "intent_type": "query"}


assistant_agent.register_query_handler('system_health', _query_system_health)
assistant_agent.register_query_handler('pending_alerts', _query_pending_alerts)
assistant_agent.register_query_handler('pending_approvals', _query_pending_approvals)
assistant_agent.register_query_handler('agent_distribution', _query_agent_distribution)
assistant_agent.register_query_handler('device_status', _query_device_status)


async def _query_audit_logs(message: str, username: str) -> Optional[Dict[str, Any]]:
    """查询审计日志"""
    try:
        async with async_session_maker() as db:
            from sqlalchemy import select, func, desc
            # 获取最近10条审计日志
            result = await db.execute(
                select(AuditLog).order_by(desc(AuditLog.created_at)).limit(10)
            )
            logs = result.scalars().all()
            if not logs:
                return {
                    'content': '当前没有审计日志记录。',
                    'actions': [],
                    'intent_type': 'query'
                }
            # 构建表格
            rows = []
            for log in logs:
                action = getattr(log, 'action', '未知')
                user = getattr(log, 'username', '未知')
                target = getattr(log, 'target_type', '') or ''
                detail = getattr(log, 'detail', '') or ''
                time_str = log.created_at.strftime('%m-%d %H:%M') if hasattr(log, 'created_at') and log.created_at else '未知'
                rows.append(f'| {time_str} | {user} | {action} | {target} |')

            content = '**审计日志（最近10条）**\n\n'
            content += '| 时间 | 用户 | 操作 | 目标 |\n'
            content += '|------|------|------|------|\n'
            content += '\n'.join(rows)

            return {
                'content': content,
                'actions': [
                    {'type': 'navigate', 'label': '查看完整审计日志', 'params': {'route': '/audit'}}
                ],
                'intent_type': 'query'
            }
    except Exception as e:
        logger.error(f"Query audit logs failed: {e}")
        return {"content": "审计日志查询暂时不可用", "actions": [], "intent_type": "query"}


assistant_agent.register_query_handler('audit_logs', _query_audit_logs)


class QueryRequest(BaseModel):
    question: str


class AddDocumentRequest(BaseModel):
    title: str
    content: str


class UpdateDocumentRequest(BaseModel):
    title: str = None
    content: str = None


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class SemanticSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    threshold: float = 0.3


class RollbackRequest(BaseModel):
    version_id: str
    contributor: str


class ChatContext(BaseModel):
    route: str = Field(default="/", max_length=200)
    entity: str = Field(default="", max_length=200)
    role: str = Field(default="viewer", max_length=50)
    scene_mode: str = Field(default="daily", max_length=20)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    context: ChatContext = Field(default_factory=ChatContext)


class AssistantAction(BaseModel):
    type: str = Field(default="query", max_length=50)
    label: str = Field(default="", max_length=200)
    params: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    content: str = Field(default="")
    actions: List[AssistantAction] = Field(default_factory=list)
    intent_type: Optional[str] = None
    progress: List[str] = Field(default_factory=list)
    scene_mode: Optional[str] = None
    workflow: List[Dict[str, Any]] = Field(default_factory=list)
    is_danger: bool = False
    entities: Dict[str, Any] = Field(default_factory=dict)


class ReActChatResponse(BaseModel):
    content: str = Field(default="")
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    tools_called: List[str] = Field(default_factory=list)
    requires_approval: bool = False
    approval_data: Optional[Dict[str, Any]] = None
    frontend_actions: List[Dict[str, Any]] = Field(default_factory=list)
    intent_type: Optional[str] = "react"
    workflow: List[Dict[str, Any]] = Field(default_factory=list)
    is_danger: bool = False
    entities: Dict[str, Any] = Field(default_factory=dict)


class ReActApproveRequest(BaseModel):
    approval_id: str = Field(..., min_length=1)
    approved: bool = Field(...)
    user_code: Optional[str] = None


class CreateQuickCommandRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    shortcut: str = Field(..., min_length=1, max_length=20)
    template: str = Field(..., min_length=1, max_length=500)
    parameters: List[Dict[str, Any]] = Field(default_factory=list)
    category: str = Field(default="custom", max_length=50)
    is_public: bool = Field(default=False)


class ExecuteQuickCommandRequest(BaseModel):
    shortcut: str = Field(..., min_length=1, max_length=20)
    parameter_values: List[str] = Field(default_factory=list)


_pending_approvals: Dict[str, Dict[str, Any]] = {}


# ---- 知识库查询与文档管理 ----


@router.post("/query")
async def query_knowledge(req: QueryRequest, current_user=Depends(get_current_user)):
    try:
        result = qa_agent.query(req.question)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Knowledge query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/documents")
async def list_documents(current_user=Depends(get_current_user)):
    try:
        documents = qa_agent.list_documents()
        return {"status": "success", "data": documents, "total": len(documents)}
    except Exception as e:
        logger.error(f"List documents failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/documents")
async def add_document(req: AddDocumentRequest, current_user=Depends(get_current_user), _: None = Depends(requires_permission("knowledge:manage"))):
    try:
        doc = qa_agent.add_document(title=req.title, content=req.content)
        return {"status": "success", "data": doc}
    except Exception as e:
        logger.error(f"Add document failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, current_user=Depends(get_current_user), _: None = Depends(requires_permission("knowledge:manage"))):
    try:
        deleted = qa_agent.delete_document(doc_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"status": "success", "message": "Document deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete document failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/documents/{doc_id}")
async def update_document(doc_id: str, req: UpdateDocumentRequest, current_user=Depends(get_current_user), _: None = Depends(requires_permission("knowledge:manage"))):
    try:
        documents = qa_agent.list_documents()
        target = None
        for doc in documents:
            if doc.get("id") == doc_id:
                target = doc
                break
        if not target:
            raise HTTPException(status_code=404, detail="Document not found")
        if req.title:
            target["title"] = req.title
        if req.content:
            target["content"] = req.content
        qa_agent.delete_document(doc_id)
        updated = qa_agent.add_document(title=target["title"], content=target["content"])
        return {"status": "success", "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update document failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/documents/search")
async def search_documents(req: SearchRequest, current_user=Depends(get_current_user)):
    try:
        documents = qa_agent.list_documents()
        query_lower = req.query.lower()
        scored = []
        for doc in documents:
            title_lower = doc.get("title", "").lower()
            content_lower = doc.get("content", "").lower()
            score = 0
            for word in query_lower.split():
                if len(word) >= 2:
                    score += title_lower.count(word) * 3
                    score += content_lower.count(word)
            if score > 0:
                scored.append({**doc, "relevance_score": score})
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        return {"status": "success", "data": scored[:req.limit], "total": len(scored)}
    except Exception as e:
        logger.error(f"Search documents failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("knowledge:manage")),
):
    try:
        allowed_extensions = {".txt", ".md", ".markdown", ".pdf", ".json", ".yaml", ".yml", ".xml", ".csv", ".cfg", ".conf", ".log"}
        file_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""

        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()[:8]}_{file.filename}")
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        result = qa_agent.upload_document(file_path=file_path, title=title or file.filename)

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/search")
async def semantic_search(req: SemanticSearchRequest, current_user=Depends(get_current_user)):
    try:
        from backend.knowledge.rag_engine import get_rag_engine
        engine = get_rag_engine()

        if not engine.available:
            raise HTTPException(status_code=503, detail="RAG engine not available")

        results = engine.search(
            query=req.query,
            top_k=req.top_k,
            threshold=req.threshold,
        )

        data = [
            {
                "doc_id": r.doc_id,
                "title": r.title,
                "content": r.content,
                "score": round(r.score, 4),
                "metadata": r.metadata,
                "chunk_index": r.chunk_index,
            }
            for r in results
        ]

        return {"status": "success", "data": data, "total": len(data)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Semantic search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats")
async def get_knowledge_stats(current_user=Depends(get_current_user)):
    try:
        from backend.knowledge.rag_engine import get_rag_engine
        engine = get_rag_engine()

        rag_stats = engine.get_stats()
        documents = qa_agent.list_documents()

        return {
            "status": "success",
            "data": {
                "total_docs": len(documents),
                "total_chunks": rag_stats.get("total_chunks", 0),
                "index_size": rag_stats.get("index_size", 0),
                "rag_available": rag_stats.get("available", False),
                "backend": rag_stats.get("backend", "none"),
                "embedding_model": rag_stats.get("embedding_model", "none"),
            },
        }
    except Exception as e:
        logger.error(f"Get knowledge stats failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/rebuild-index")
async def rebuild_index(current_user=Depends(get_current_user), _: None = Depends(requires_permission("knowledge:manage"))):
    try:
        from backend.knowledge.rag_engine import get_rag_engine
        engine = get_rag_engine()

        if not engine.available:
            raise HTTPException(status_code=503, detail="RAG engine not available")

        engine.rebuild_index()
        stats = engine.get_stats()

        return {
            "status": "success",
            "message": "Index rebuilt successfully",
            "data": stats,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rebuild index failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---- 版本控制 ----


@router.get("/versions/{document_id}")
async def get_document_versions(
    document_id: str,
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    try:
        from backend.knowledge.version_control import get_knowledge_version_control
        vc = get_knowledge_version_control()
        versions = await vc.get_document_versions(document_id, limit=limit)
        return success_response(data={"items": versions, "total": len(versions)})
    except Exception as e:
        logger.error(f"Get document versions failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/versions/detail/{version_id}")
async def get_version_detail(
    version_id: str,
    current_user=Depends(get_current_user),
):
    try:
        from backend.knowledge.version_control import get_knowledge_version_control
        vc = get_knowledge_version_control()
        version = await vc.get_version(version_id)
        return success_response(data=version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Get version detail failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/versions/{document_id}/rollback")
async def rollback_to_version(
    document_id: str,
    req: RollbackRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("knowledge:version")),
):
    try:
        from backend.knowledge.version_control import get_knowledge_version_control
        vc = get_knowledge_version_control()
        version = await vc.rollback_to_version(document_id, req.version_id, req.contributor)
        return success_response(data=version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Rollback version failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/versions/{document_id}/compare")
async def compare_versions(
    document_id: str,
    version_a: str = Query(..., alias="version_a"),
    version_b: str = Query(..., alias="version_b"),
    current_user=Depends(get_current_user),
):
    try:
        from backend.knowledge.version_control import get_knowledge_version_control
        vc = get_knowledge_version_control()
        comparison = await vc.compare_versions(document_id, version_a, version_b)
        return success_response(data=comparison)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Compare versions failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/contributions")
async def get_contributor_history(
    contributor: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user),
):
    try:
        from backend.knowledge.version_control import get_knowledge_version_control
        vc = get_knowledge_version_control()
        history = await vc.get_contributor_history(contributor, limit=limit)
        return success_response(data={"items": history, "total": len(history)})
    except Exception as e:
        logger.error(f"Get contributor history failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/versions/stats")
async def get_version_stats(
    current_user=Depends(get_current_user),
):
    try:
        from backend.knowledge.version_control import get_knowledge_version_control
        vc = get_knowledge_version_control()
        stats = await vc.get_version_stats()
        return success_response(data=stats)
    except Exception as e:
        logger.error(f"Get version stats failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---- AI 助手聊天功能 ----


@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(request: ChatRequest, current_user=Depends(get_current_user)):
    try:
        result = await assistant_agent.route(
            message=request.message,
            context={
                "route": request.context.route,
                "entity": request.context.entity,
                "role": current_user.role if hasattr(current_user, 'role') else request.context.role,
                "username": current_user.username,
                "scene_mode": request.context.scene_mode
            }
        )

        intent_type = result.get("intent_type")
        if intent_type in ('control', 'scene_mode'):
            try:
                async with async_session_maker() as db:
                    audit_entry = AuditLog(
                        user_id=f"AI-Assistant:{current_user.username}",
                        action=result.get("intent_type", "assistant_action"),
                        target_device=str(result.get("entities", {})),
                        commands=[{
                            "source": "AI-Assistant",
                            "original_user": current_user.username,
                            "message": request.message
                        }],
                        status="success",
                        security_type="critical" if result.get("is_danger") else "info"
                    )
                    db.add(audit_entry)
                    await db.commit()
            except Exception as audit_err:
                logger.error(f"Audit log write error: {audit_err}")

        return ChatResponse(
            content=result.get("content", ""),
            actions=[AssistantAction(**a) for a in result.get("actions", [])],
            intent_type=result.get("intent_type"),
            progress=result.get("progress", []),
            scene_mode=result.get("scene_mode"),
            workflow=result.get("workflow", []),
            is_danger=result.get("is_danger", False),
            entities=result.get("entities", {})
        )
    except Exception as e:
        logger.error(f"Assistant chat error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.get("/context/{route:path}")
async def get_route_context(route: str, current_user=Depends(get_current_user)):
    context = assistant_agent.get_context_for_route(
        route=f"/{route}",
        role=current_user.role if hasattr(current_user, 'role') else 'viewer'
    )
    return context


@router.get("/history")
async def get_conversation_history(
    count: int = 20,
    current_user=Depends(get_current_user)
):
    history = assistant_agent.get_conversation_history(
        username=current_user.username,
        count=min(count, 50)
    )
    return {"history": history}


@router.get("/conversation/{session_id}")
async def get_conversation_by_session(
    session_id: str,
    current_user=Depends(get_current_user)
):
    try:
        memory = assistant_agent._memory
        all_history = memory._history.get(current_user.username, [])
        matched = [
            msg for msg in all_history
            if msg.get("session_id") == session_id
        ]
        if not matched:
            matched = all_history[-20:] if all_history else []
        return {"session_id": session_id, "messages": matched}
    except Exception as e:
        logger.error(f"Get conversation by session error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.post("/chat/stream")
async def chat_stream_with_assistant(request: ChatRequest, current_user=Depends(get_current_user)):
    try:
        from backend.agents.llm_gateway import get_llm_gateway, TaskType, LLMProvider
        gateway = get_llm_gateway()

        if not gateway.zhipu.available:
            result = await assistant_agent.route(
                message=request.message,
                context={
                    "route": request.context.route,
                    "entity": request.context.entity,
                    "role": current_user.role if hasattr(current_user, 'role') else request.context.role,
                    "username": current_user.username,
                    "scene_mode": request.context.scene_mode
                }
            )
            async def single_response():
                yield f"data: {json.dumps({'content': result.get('content', ''), 'done': True}, ensure_ascii=False)}\n\n"
            return StreamingResponse(single_response(), media_type="text/event-stream")

        route = request.context.route
        role = current_user.role if hasattr(current_user, 'role') else request.context.role
        scene_mode = request.context.scene_mode
        route_ctx = assistant_agent.get_context_for_route(route, role)
        page_name = route_ctx.get('title', '当前页面')
        recent = assistant_agent.get_conversation_history(current_user.username, 6)

        system_prompt = f"""你是智维AgentHub的专业智能运维助手，专注于协助运维人员高效完成日常运维工作。

## 角色定义
你是智维运维平台的专业智能助手，回答必须保持高度的准确性、专业性和严谨性，同时维持礼貌自然的交互语气。

## 核心职责
1. **运维查询响应**：对服务器状态、监控告警、日志分析、故障排查等运维相关查询提供快速、精准的响应
2. **运维操作协助**：支持重启服务、修改配置、创建工单等运维操作的执行，确保操作指令清晰可执行
3. **运维知识支持**：基于平台知识库内容，提供专业的运维知识解答
4. **非运维问题处理**：对非运维类问题可提供简洁回答，但不得偏离运维主题

## 输出规范
1. **结构化输出**：优先采用表格、列表等结构化形式，提升可读性
2. **关键信息强调**：使用**加粗**格式突出告警级别、操作风险、重要参数
3. **操作步骤规范**：采用编号形式（1. 2. 3.）分步骤说明，确保可按步骤执行
4. **内容简洁**：直击问题核心，避免冗余

## 行为规则
1. **操作确认机制**：执行任何运维操作前，必须确认用户意图，获得明确授权后方可继续
2. **风险提示要求**：涉及系统重启、配置修改等高风险操作时，必须醒目提醒注意事项、潜在风险及回滚方案
3. **故障处理规范**：工具调用失败时，需告知具体失败原因、影响范围及建议解决措施
4. **不编造数据**：如果不确定，告诉用户你可以帮他们查询

当前上下文：
- 用户角色：{role}
- 当前页面：{page_name}（路由：{route}）
- 场景模式：{'日常巡检' if scene_mode == 'daily' else '应急响应' if scene_mode == 'emergency' else '变更冻结'}

你的核心能力：
1. **导航** — 帮用户跳转到系统页面（指挥舱、意图中心、网络拓扑、故障自愈、审计日志等）
2. **查询** — 查询系统健康度、告警、设备状态、审批待办等实时数据
3. **操控** — 执行重启设备、隔离节点、优化带宽等运维操作
4. **场景切换** — 切换日常巡检/应急响应/变更冻结模式

回复使用Markdown格式，适当使用加粗和列表。"""

        messages = [{"role": "system", "content": system_prompt}]
        for msg in recent:
            if msg.get('role') in ('user', 'assistant'):
                messages.append({"role": msg['role'], "content": msg['content']})
        messages.append({"role": "user", "content": request.message})

        async def stream_generator():
            full_content = ""
            try:
                async for chunk in gateway.chat_stream(
                    messages,
                    task_type=TaskType.COPILOT_STREAM,
                    temperature=0.7,
                    max_tokens=2048,
                    preferred=LLMProvider.ZHIPU
                ):
                    if "content" in chunk:
                        full_content += chunk["content"]
                        yield f"data: {json.dumps({'content': chunk['content'], 'done': False}, ensure_ascii=False)}\n\n"
                    elif "error" in chunk:
                        yield f"data: {json.dumps({'error': chunk['error'], 'done': True}, ensure_ascii=False)}\n\n"
                        return
            except Exception as e:
                logger.error(f"Stream error: {e}")
                yield f"data: {json.dumps({'error': 'Internal server error', 'done': True}, ensure_ascii=False)}\n\n"
                return

            assistant_agent._memory.add_turn(current_user.username, 'user', request.message)
            assistant_agent._memory.add_turn(current_user.username, 'assistant', full_content, intent_type='general')
            yield f"data: {json.dumps({'content': '', 'done': True}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as e:
        logger.error(f"Stream chat error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.get("/llm-status")
async def get_llm_status(current_user=Depends(get_current_user)):
    try:
        from backend.agents.llm_gateway import get_llm_gateway
        gateway = get_llm_gateway()
        return gateway.get_status()
    except Exception as e:
        return {"zhipu": {"available": False, "error": "Service unavailable"}, "deepseek": {"available": False}}


@router.post("/react-chat", response_model=ReActChatResponse)
async def react_chat(
    request: ChatRequest,
    current_user=Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
):
    try:
        from backend.core.websocket_manager import manager as ws_manager

        react_engine: ReActEngine = get_react_engine()
        username: str = current_user.username

        context: Dict[str, Any] = {
            "role": current_user.role if hasattr(current_user, 'role') else request.context.role,
            "page": request.context.route,
            "scene_mode": request.context.scene_mode,
            "username": username
        }

        async def step_callback(step_dict: Dict[str, Any]) -> None:
            try:
                await ws_manager.send_to_user(username, {
                    "type": "react_step",
                    "data": step_dict
                })
            except Exception as cb_err:
                logger.warning(f"WebSocket步骤回调发送失败: {cb_err}")

        result = await react_engine.run(
            user_message=request.message,
            context=context,
            token=token,
            on_step_callback=step_callback
        )

        steps_dicts: List[Dict[str, Any]] = [s.__dict__ for s in result.steps]
        workflow: List[Dict[str, Any]] = [
            {
                "id": f"react_step_{s['step_number']}",
                "agent": s.get("action", "Reasoning"),
                "status": s.get("status", "thinking"),
                "title": s.get("thought", ""),
                "detail": s.get("observation")
            }
            for s in steps_dicts
        ]

        is_danger: bool = result.requires_approval

        approval_data: Optional[Dict[str, Any]] = None
        if result.requires_approval and result.approval_data:
            approval_id: str = str(uuid.uuid4())
            approval_data = {
                "approval_id": approval_id,
                **result.approval_data
            }
            _pending_approvals[approval_id] = {
                "username": username,
                "token": token,
                "context": context,
                "steps": steps_dicts,
                "tools_called": list(result.tools_called),
                "frontend_actions": list(result.frontend_actions),
                "approval_data": result.approval_data,
                "message": request.message
            }
            logger.info(f"ReAct推理暂停等待审批，approval_id={approval_id}, 用户={username}")

        if result.tools_called:
            try:
                async with async_session_maker() as db:
                    audit_entry = AuditLog(
                        user_id=f"ReAct:{username}",
                        action="react_execution",
                        target_device=str(result.approval_data or {}),
                        commands=[{
                            "source": "ReAct-Engine",
                            "original_user": username,
                            "message": request.message,
                            "tools_called": result.tools_called
                        }],
                        status="pending" if result.requires_approval else "success",
                        security_type="critical" if is_danger else "info"
                    )
                    db.add(audit_entry)
                    await db.commit()
            except Exception as audit_err:
                logger.error(f"ReAct审计日志写入失败: {audit_err}")

        return ReActChatResponse(
            content=result.final_answer,
            steps=steps_dicts,
            tools_called=result.tools_called,
            requires_approval=result.requires_approval,
            approval_data=approval_data,
            frontend_actions=result.frontend_actions,
            intent_type="react",
            workflow=workflow,
            is_danger=is_danger,
            entities={}
        )
    except Exception as e:
        logger.error(f"ReAct聊天处理失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.post("/react-approve", response_model=ReActChatResponse)
async def react_approve(
    request: ReActApproveRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("intents:approve"))
):
    try:
        from backend.core.websocket_manager import manager as ws_manager

        approval_id: str = request.approval_id
        username: str = current_user.username

        pending: Optional[Dict[str, Any]] = _pending_approvals.get(approval_id)
        if not pending:
            raise HTTPException(status_code=404, detail=f"审批记录不存在或已过期: {approval_id}")

        if pending["username"] != username:
            raise HTTPException(status_code=403, detail="无权审批此请求")

        if not request.approved:
            _pending_approvals.pop(approval_id, None)

            existing_steps: List[Dict[str, Any]] = pending["steps"]
            workflow: List[Dict[str, Any]] = [
                {
                    "id": f"react_step_{s['step_number']}",
                    "agent": s.get("action", "Reasoning"),
                    "status": "cancelled",
                    "title": s.get("thought", ""),
                    "detail": "用户已拒绝执行此高危操作"
                }
                for s in existing_steps
            ]

            try:
                await ws_manager.send_to_user(username, {
                    "type": "react_step",
                    "data": {
                        "step_number": len(existing_steps) + 1,
                        "thought": "用户已拒绝执行此高危操作",
                        "status": "cancelled"
                    }
                })
            except Exception as ws_err:
                logger.warning(f"WebSocket审批拒绝通知发送失败: {ws_err}")

            return ReActChatResponse(
                content="操作已被拒绝，高危操作未执行。",
                steps=existing_steps,
                tools_called=pending["tools_called"],
                requires_approval=False,
                approval_data=None,
                frontend_actions=pending["frontend_actions"],
                intent_type="react",
                workflow=workflow,
                is_danger=False,
                entities={}
            )

        token: str = pending["token"]
        context: Dict[str, Any] = pending["context"]
        original_message: str = pending["message"]
        approval_data_raw: Dict[str, Any] = pending["approval_data"]

        _pending_approvals.pop(approval_id, None)

        approved_message: str = (
            f"{original_message}\n\n"
            f"[系统提示] 用户已批准执行高危操作: {approval_data_raw.get('tool_name', '未知工具')}。"
            f"请继续执行。"
        )

        async def step_callback(step_dict: Dict[str, Any]) -> None:
            try:
                await ws_manager.send_to_user(username, {
                    "type": "react_step",
                    "data": step_dict
                })
            except Exception as cb_err:
                logger.warning(f"WebSocket步骤回调发送失败: {cb_err}")

        react_engine: ReActEngine = get_react_engine()
        result = await react_engine.run(
            user_message=approved_message,
            context=context,
            token=token,
            on_step_callback=step_callback
        )

        all_steps: List[Dict[str, Any]] = pending["steps"] + [s.__dict__ for s in result.steps]
        all_tools_called: List[str] = list(set(pending["tools_called"] + result.tools_called))
        all_frontend_actions: List[Dict[str, Any]] = pending["frontend_actions"] + result.frontend_actions

        workflow: List[Dict[str, Any]] = [
            {
                "id": f"react_step_{s['step_number']}",
                "agent": s.get("action", "Reasoning"),
                "status": s.get("status", "thinking"),
                "title": s.get("thought", ""),
                "detail": s.get("observation")
            }
            for s in all_steps
        ]

        try:
            async with async_session_maker() as db:
                audit_entry = AuditLog(
                    user_id=f"ReAct-Approve:{username}",
                    action="react_approved_execution",
                    target_device=str(approval_data_raw),
                    commands=[{
                        "source": "ReAct-Engine-Approved",
                        "original_user": username,
                        "message": original_message,
                        "tools_called": all_tools_called,
                        "user_code": request.user_code
                    }],
                    status="success",
                    security_type="critical"
                )
                db.add(audit_entry)
                await db.commit()
        except Exception as audit_err:
            logger.error(f"ReAct审批审计日志写入失败: {audit_err}")

        return ReActChatResponse(
            content=result.final_answer,
            steps=all_steps,
            tools_called=all_tools_called,
            requires_approval=result.requires_approval,
            approval_data=None,
            frontend_actions=all_frontend_actions,
            intent_type="react",
            workflow=workflow,
            is_danger=result.requires_approval,
            entities={}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ReAct审批处理失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


# ---- 助手文件上传 ----

@router.post("/assistant-upload")
async def upload_assistant_file(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("knowledge:manage")),
):
    try:
        file_name = file.filename or "unknown"
        ext = os.path.splitext(file_name)[1].lower()
        allowed_extensions = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".log", ".txt", ".csv", ".pdf"}
        if ext not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

        file_id = uuid.uuid4().hex[:8]
        save_path = os.path.join(ASSISTANT_UPLOAD_DIR, f"{file_id}_{file_name}")
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)

        processor = get_multimodal_processor()
        result = await processor.process_file_upload(save_path, file_name)
        result["file_name"] = file_name
        result["uploaded_by"] = current_user.username
        return success_response(data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


# ---- 通知管理 ----

@router.get("/notifications")
async def list_notifications(
    notification_type: Optional[str] = Query(None),
    is_read: Optional[bool] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    try:
        notifier = get_proactive_notifier()
        notifications = await notifier.list_notifications(
            username=current_user.username,
            notification_type=notification_type,
            is_read=is_read,
            limit=limit,
        )
        return success_response(data={"notifications": notifications})
    except Exception as e:
        logger.error(f"List notifications error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.get("/notifications/unread")
async def get_unread_notifications(
    current_user=Depends(get_current_user),
):
    try:
        notifier = get_proactive_notifier()
        notifications = await notifier.get_unread_notifications(current_user.username)
        return success_response(data={"notifications": notifications, "count": len(notifications)})
    except Exception as e:
        logger.error(f"Get unread notifications error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user=Depends(get_current_user),
):
    try:
        notifier = get_proactive_notifier()
        await notifier.mark_as_read(notification_id, current_user.username)
        return success_response()
    except Exception as e:
        logger.error(f"Mark notification read error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("notification:manage")),
):
    try:
        notifier = get_proactive_notifier()
        count = await notifier.mark_all_as_read(current_user.username)
        return success_response(data={"count": count})
    except Exception as e:
        logger.error(f"Mark all notifications read error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.post("/notifications/{notification_id}/dismiss")
async def dismiss_notification(
    notification_id: str,
    current_user=Depends(get_current_user),
):
    try:
        notifier = get_proactive_notifier()
        await notifier.dismiss_notification(notification_id, current_user.username)
        return success_response()
    except Exception as e:
        logger.error(f"Dismiss notification error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


# ---- 快捷指令 ----

@router.get("/quick-commands")
async def list_quick_commands(
    category: Optional[str] = Query(None),
    is_public: Optional[bool] = Query(None),
    current_user=Depends(get_current_user),
):
    try:
        manager = get_quick_command_manager()
        commands = await manager.list_commands(
            created_by=current_user.username,
            is_public=is_public,
            category=category,
        )
        built_in = manager.get_built_in_commands()
        return success_response(data={"commands": commands, "built_in": built_in})
    except Exception as e:
        logger.error(f"List quick commands error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.post("/quick-commands")
async def create_quick_command(
    request: CreateQuickCommandRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("quick-command:manage")),
):
    try:
        manager = get_quick_command_manager()
        command = await manager.create_command(
            name=request.name,
            shortcut=request.shortcut,
            template=request.template,
            parameters=request.parameters,
            created_by=current_user.username,
            category=request.category,
            is_public=request.is_public,
        )
        return success_response(data={
            "command_id": command.command_id,
            "name": command.name,
            "shortcut": command.shortcut,
            "template": command.template,
            "parameters": command.parameters,
            "category": command.category,
            "is_public": command.is_public,
            "created_by": command.created_by,
        })
    except Exception as e:
        logger.error(f"Create quick command error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.post("/quick-commands/execute")
async def execute_quick_command(
    request: ExecuteQuickCommandRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("quick-command:manage")),
):
    try:
        manager = get_quick_command_manager()
        result = await manager.execute_command(
            shortcut=request.shortcut,
            parameter_values=request.parameter_values,
            created_by=current_user.username,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return success_response(data=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execute quick command error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.delete("/quick-commands/{command_id}")
async def delete_quick_command(
    command_id: str,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("quick-command:manage")),
):
    try:
        manager = get_quick_command_manager()
        command = await manager.get_command(command_id)
        if not command:
            raise HTTPException(status_code=404, detail="快捷指令不存在")
        if command["created_by"] != current_user.username and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="无权删除此快捷指令")
        deleted = await manager.delete_command(command_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="快捷指令不存在")
        return success_response()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete quick command error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


class FeedbackRequest(BaseModel):
    query: str
    answer: str
    feedback_type: str
    comment: str = ""
    correction: str = ""


@router.post("/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    current_user=Depends(get_current_user),
):
    try:
        from backend.knowledge.feedback_loop import get_feedback_loop
        loop = get_feedback_loop()
        entry = loop.record_feedback(
            query=req.query,
            answer=req.answer,
            feedback_type=req.feedback_type,
            user_id=current_user.username,
            comment=req.comment,
            correction=req.correction,
        )
        return success_response(data={
            "entry_id": entry.entry_id,
            "feedback_type": entry.feedback_type,
            "score": entry.score,
        })
    except Exception as e:
        logger.error(f"Submit feedback failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/feedback")
async def list_feedback(
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    try:
        from backend.knowledge.feedback_loop import get_feedback_loop
        loop = get_feedback_loop()
        feedback = loop.get_recent_feedback(limit=limit)
        stats = loop.get_stats()
        return success_response(data={"items": feedback, "stats": stats})
    except Exception as e:
        logger.error(f"List feedback failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/realtime-knowledge")
async def get_realtime_knowledge(
    source: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    try:
        from backend.knowledge.realtime_injector import get_realtime_injector
        injector = get_realtime_injector()
        items = injector.get_recent_items(limit=limit, source=source, severity=severity)
        stats = injector.get_stats()
        return success_response(data={
            "items": [
                {
                    "item_id": i.item_id,
                    "source": i.source,
                    "title": i.title,
                    "content": i.content,
                    "severity": i.severity,
                    "created_at": i.created_at,
                }
                for i in items
            ],
            "stats": stats,
        })
    except Exception as e:
        logger.error(f"Get realtime knowledge failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


class PlanExecuteRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    context: ChatContext = Field(default_factory=ChatContext)


class PlanStep(BaseModel):
    step_id: str = Field(default="")
    title: str = Field(default="")
    description: str = Field(default="")
    status: str = Field(default="pending")
    agent: str = Field(default="")


class PlanExecuteResponse(BaseModel):
    plan_id: str = Field(default="")
    content: str = Field(default="")
    steps: List[PlanStep] = Field(default_factory=list)
    intent_type: str = Field(default="plan_execute")


@router.post("/plan-execute", response_model=PlanExecuteResponse)
async def plan_execute(
    request: PlanExecuteRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("intents:execute")),
):
    try:
        import uuid as _uuid
        plan_id = _uuid.uuid4().hex[:8]

        steps = [
            PlanStep(step_id=f"plan_{plan_id}_1", title="需求分析", description="分析用户需求，确定优化目标", status="running", agent="IntentParser"),
            PlanStep(step_id=f"plan_{plan_id}_2", title="现状评估", description="收集当前网络状态数据", status="pending", agent="QueryAgent"),
            PlanStep(step_id=f"plan_{plan_id}_3", title="方案生成", description="生成优化方案并评估风险", status="pending", agent="PolicyPlanner"),
            PlanStep(step_id=f"plan_{plan_id}_4", title="执行确认", description="等待用户确认后执行", status="pending", agent="ExecutionAgent"),
        ]

        return PlanExecuteResponse(
            plan_id=plan_id,
            content=f'已为您创建**规划执行方案**（ID: {plan_id}），共 {len(steps)} 个步骤。',
            steps=steps,
            intent_type="plan_execute",
        )
    except Exception as e:
        logger.error(f"Plan execute error: {e}")
        raise HTTPException(status_code=500, detail="规划执行请求处理失败")


@router.get("/dialogue-state/{session_id}")
async def get_dialogue_state(
    session_id: str,
    current_user=Depends(get_current_user),
):
    try:
        from backend.agents.dialogue_state import get_dst
        dst = get_dst()
        state = dst.get_state(session_id)
        if state is None:
            return success_response(data={"session_id": session_id, "turn_count": 0, "entities": {}})
        return success_response(data=state)
    except Exception as e:
        logger.error(f"Get dialogue state error: {e}")
        raise HTTPException(status_code=500, detail="获取对话状态失败")


@router.get("/behavior-stats")
async def get_behavior_stats(
    current_user=Depends(get_current_user),
):
    try:
        from backend.agents.dialogue_state import get_dst
        dst = get_dst()
        stats = dst.get_behavior_stats(current_user.username)
        return success_response(data=stats)
    except Exception as e:
        logger.error(f"Get behavior stats error: {e}")
        raise HTTPException(status_code=500, detail="获取行为统计失败")


@router.get("/wizards")
async def list_wizards(
    current_user=Depends(get_current_user),
):
    try:
        from backend.agents.wizard_templates import WizardTemplateLibrary
        lib = WizardTemplateLibrary()
        templates = lib.list_templates()

        return success_response(data={
            "wizards": [
                {
                    "wizard_type": t.wizard_type,
                    "name": t.name,
                    "description": t.description,
                    "icon": t.icon,
                    "category": t.category,
                    "param_schema": [p.model_dump() for p in t.param_schema],
                    "confirm_level": t.confirm_level.value
                }
                for t in templates
            ]
        })
    except Exception as e:
        logger.error(f"List wizards error: {e}")
        raise HTTPException(status_code=500, detail="获取向导列表失败")


class WizardExecuteRequest(BaseModel):
    wizard_type: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/wizards/execute")
async def execute_wizard(
    request: WizardExecuteRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("intents:execute")),
):
    try:
        from backend.agents.wizard_templates import WizardTemplateLibrary

        lib = WizardTemplateLibrary()
        template = lib.get_template(request.wizard_type)
        if not template:
            raise HTTPException(status_code=404, detail=f"向导类型不存在: {request.wizard_type}")

        plan = template.instantiate(request.params)

        return success_response(data={
            "plan_id": plan.plan_id,
            "goal": plan.goal,
            "steps": [
                {
                    "step_index": s.step_index,
                    "description": s.description,
                    "tool_name": s.tool_name,
                    "confirm_level": s.confirm_level.value,
                    "status": s.status.value
                }
                for s in plan.steps
            ],
            "confirm_level": plan.confirm_level.value,
            "risk_summary": plan.risk_summary
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Wizard execute error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="向导执行失败")


@router.get("/tool-chains")
async def list_tool_chains(
    current_user=Depends(get_current_user),
):
    try:
        from backend.agents.tool_chains import ToolChainRegistry
        registry = ToolChainRegistry()
        chains = registry.list_chains()

        return success_response(data={
            "chains": [
                {
                    "chain_id": c.chain_id,
                    "name": c.name,
                    "description": c.description,
                    "steps_count": len(c.steps),
                    "auto_degradation": c.auto_degradation,
                    "parallel_groups": c.parallel_groups
                }
                for c in chains
            ]
        })
    except Exception as e:
        logger.error(f"List tool chains error: {e}")
        raise HTTPException(status_code=500, detail="获取工具链列表失败")


class ToolChainExecuteRequest(BaseModel):
    chain_id: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/tool-chains/execute")
async def execute_tool_chain(
    request: ToolChainExecuteRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("intents:execute")),
):
    try:
        from backend.agents.tool_chains import ToolChainRegistry
        from backend.agents.tool_orchestrator import ToolOrchestrationEngine

        registry = ToolChainRegistry()
        chain = registry.get_chain(request.chain_id)
        if not chain:
            raise HTTPException(status_code=404, detail=f"工具链不存在: {request.chain_id}")

        for key, value in request.params.items():
            for step in chain.steps:
                for param_key, param_value in step.params.items():
                    if isinstance(param_value, str) and f"{{{{{key}}}}}" in param_value:
                        step.params[param_key] = param_value.replace(f"{{{{{key}}}}}", str(value))

        from backend.agents.react_engine import get_react_engine
        react_engine = get_react_engine()
        engine = ToolOrchestrationEngine(react_engine.tool_registry)

        result = await engine.execute(chain, token="")

        return success_response(data={
            "chain_id": result.chain_id,
            "status": result.status,
            "steps_results": result.steps_results,
            "total_duration_seconds": result.total_duration_seconds,
            "success_count": result.success_count,
            "degraded_count": result.degraded_count,
            "failed_count": result.failed_count
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tool chain execute error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="工具链执行失败")


@router.get("/proactive/suggestions")
async def get_proactive_suggestions(
    current_user=Depends(get_current_user),
):
    try:
        from backend.agents.environment_awareness import get_environment_awareness_engine
        engine = get_environment_awareness_engine()
        snapshot = await engine.get_environment_snapshot()
        suggestions = []

        health = snapshot.get("health_percentage", 100)
        critical = snapshot.get("alert_summary", {}).get("critical", 0)
        warning = snapshot.get("alert_summary", {}).get("warning", 0)

        if critical > 0:
            suggestions.append({
                "type": "alert_diagnosis",
                "priority": "high",
                "message": f"当前有 {critical} 条严重告警需要处理",
                "action": {"label": "查看告警", "type": "navigate", "params": {"route": "/self-healing"}},
            })

        if health < 80:
            suggestions.append({
                "type": "operation_suggestion",
                "priority": "medium",
                "message": f"系统健康度 {health}%，建议检查离线设备",
                "action": {"label": "查看拓扑", "type": "navigate", "params": {"route": "/topology"}},
            })

        if warning > 5:
            suggestions.append({
                "type": "trend_warning",
                "priority": "low",
                "message": f"警告告警 {warning} 条，可能存在趋势性风险",
                "action": {"label": "查看详情", "type": "query", "params": {"query": "pending_alerts"}},
            })

        return success_response(data={"suggestions": suggestions, "snapshot": snapshot})
    except Exception as e:
        logger.error(f"Get proactive suggestions error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")


@router.get("/proactive/insights")
async def get_proactive_insights(
    current_user=Depends(get_current_user),
):
    try:
        from backend.agents.environment_awareness import get_environment_awareness_engine
        engine = get_environment_awareness_engine()

        snapshot = await engine.get_environment_snapshot()
        is_storm = engine.is_alert_storm()

        insights = {
            "system_health": snapshot.get("health_percentage", 100),
            "alert_storm": is_storm,
            "alert_summary": snapshot.get("alert_summary", {}),
            "active_intents": snapshot.get("active_intents", 0),
            "recommended_mode": "emergency" if is_storm or snapshot.get("alert_summary", {}).get("critical", 0) > 3 else "daily",
        }

        return success_response(data=insights)
    except Exception as e:
        logger.error(f"Get proactive insights error: {e}")
        raise HTTPException(status_code=500, detail="处理请求失败，请稍后重试")
