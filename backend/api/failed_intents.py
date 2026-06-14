from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from backend.core.security.rbac import get_current_user, requires_permission
from backend.agents.failed_intent_store import get_failed_intent_store
from backend.api.response import success_response
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class ResolveCaseRequest(BaseModel):
    user_clarification: str
    resolution_notes: str


@router.get("")
async def list_failed_intents(
    resolved: Optional[bool] = None,
    parse_method: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("intents:read")),
):
    try:
        store = get_failed_intent_store()
        cases = await store.list_cases(resolved=resolved, limit=limit, offset=offset)

        data = []
        for case in cases:
            if parse_method and case.parse_method != parse_method:
                continue
            # 根据failure_reason推断分类
            reason = case.failure_reason or ""
            if "模糊" in reason or "歧义" in reason or "宽泛" in reason:
                category = "ambiguous_input"
            elif "缺少" in reason or "参数" in reason:
                category = "entity_missing"
            elif "安全" in reason or "拦截" in reason:
                category = "unsupported_intent"
            elif "格式" in reason or "异常" in reason:
                category = "parse_error"
            elif "超时" in reason or "timeout" in reason.lower():
                category = "timeout"
            elif "不匹配" in reason or "超出" in reason:
                category = "unsupported_intent"
            else:
                category = "parse_error"
            data.append({
                "id": case.id,
                "user_input": case.user_input,
                "parse_method": case.parse_method,
                "failure_reason": case.failure_reason,
                "failure_reason_category": category,
                "raw_response": case.raw_response,
                "intent_type_attempted": case.intent_type_attempted,
                "clarification_question": case.clarification_question,
                "user_clarification": case.user_clarification,
                "resolved": case.resolved,
                "resolution_notes": case.resolution_notes,
                "metadata": case.meta_data,
                "created_at": case.created_at.isoformat() if case.created_at else None,
                "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            })

        # 获取总数用于分页
        stats = await store.get_failure_stats()
        total_count = stats.get("total", len(data))

        return success_response(data={"items": data, "total": total_count, "count": len(data)})
    except Exception as e:
        logger.error(f"List failed intents failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats")
async def get_failure_stats(current_user=Depends(get_current_user), _: None = Depends(requires_permission("intents:read"))):
    try:
        store = get_failed_intent_store()
        stats = await store.get_failure_stats()
        return success_response(data=stats)
    except Exception as e:
        logger.error(f"Get failure stats failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/finetuning-data")
async def get_finetuning_data(
    limit: int = Query(default=100, ge=1, le=500),
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("intents:read")),
):
    try:
        store = get_failed_intent_store()
        data = await store.get_cases_for_finetuning(limit=limit)
        return success_response(data={"items": data, "count": len(data)})
    except Exception as e:
        logger.error(f"Get finetuning data failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{case_id}")
async def get_failed_intent(case_id: int, current_user=Depends(get_current_user), _: None = Depends(requires_permission("intents:read"))):
    try:
        store = get_failed_intent_store()
        case = await store.get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Failed intent case not found")
        return success_response(data={
                "id": case.id,
                "user_input": case.user_input,
                "parse_method": case.parse_method,
                "failure_reason": case.failure_reason,
                "raw_response": case.raw_response,
                "intent_type_attempted": case.intent_type_attempted,
                "clarification_question": case.clarification_question,
                "user_clarification": case.user_clarification,
                "resolved": case.resolved,
                "resolution_notes": case.resolution_notes,
                "metadata": case.meta_data,
                "created_at": case.created_at.isoformat() if case.created_at else None,
                "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get failed intent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{case_id}/resolve")
async def resolve_failed_intent(
    case_id: int,
    req: ResolveCaseRequest,
    current_user=Depends(get_current_user),
    _: None = Depends(requires_permission("intents:approve"))
):
    try:
        store = get_failed_intent_store()
        success = await store.resolve_case(
            case_id=case_id,
            user_clarification=req.user_clarification,
            resolution_notes=req.resolution_notes
        )
        if not success:
            raise HTTPException(status_code=404, detail="Failed intent case not found")
        return success_response(data={"id": case_id, "resolved": True})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resolve failed intent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{case_id}")
async def delete_failed_intent(case_id: int, current_user=Depends(get_current_user), _: None = Depends(requires_permission("intents:delete"))):
    try:
        store = get_failed_intent_store()
        success = await store.delete_case(case_id)
        if not success:
            raise HTTPException(status_code=404, detail="Failed intent case not found")
        return success_response()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete failed intent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
