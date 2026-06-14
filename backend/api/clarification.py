from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from backend.core.security.rbac import get_current_user
from backend.agents.clarification import get_clarification_agent
from backend.agents.intent_parser import IntentParserAgent
from backend.api.response import success_response
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

_intent_parser = IntentParserAgent()


class AnalyzeRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=2000)


class RespondRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    user_response: str = Field(..., min_length=1, max_length=2000)


@router.post("/analyze")
async def analyze_input(request: AnalyzeRequest, current_user=Depends(get_current_user)):
    try:
        result = await _intent_parser.parse_with_clarification(request.user_input)

        from backend.agents.clarification import ClarificationResult
        from backend.agents.base import IntentContext

        if isinstance(result, IntentContext):
            return success_response(data={
                "needs_clarification": False,
                "confidence": 1.0,
                "questions": [],
                "session_id": None,
                "parsed_intent": result.parsed_intent
            })

        if isinstance(result, ClarificationResult):
            return success_response(data={
                "needs_clarification": result.needs_clarification,
                "confidence": result.confidence,
                "questions": result.questions,
                "session_id": result.session_id,
                "missing_fields": result.missing_fields
            })

        return success_response(data={
            "needs_clarification": True,
            "confidence": 0.0,
            "questions": ["无法解析您的意图，请更详细地描述您的需求"],
            "session_id": None
        })
    except Exception as e:
        logger.error(f"Clarification analyze error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="意图分析失败，请稍后重试")


@router.post("/respond")
async def respond_clarification(request: RespondRequest, current_user=Depends(get_current_user)):
    try:
        result = await _intent_parser.resolve_and_parse(request.session_id, request.user_response)

        from backend.agents.clarification import ClarificationResult
        from backend.agents.base import IntentContext

        if isinstance(result, IntentContext):
            return success_response(data={
                "resolved": True,
                "parsed_intent": result.parsed_intent,
                "needs_more_clarification": False,
                "questions": []
            })

        if isinstance(result, ClarificationResult):
            return success_response(data={
                "resolved": False,
                "parsed_intent": None,
                "needs_more_clarification": result.needs_clarification,
                "questions": result.questions,
                "missing_fields": result.missing_fields,
                "session_id": result.session_id
            })

        return success_response(data={
            "resolved": False,
            "parsed_intent": None,
            "needs_more_clarification": True,
            "questions": ["请继续提供更多信息"]
        })
    except Exception as e:
        logger.error(f"Clarification respond error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"澄清响应处理失败: {str(e)}")


@router.get("/session/{session_id}")
async def get_session_status(session_id: str, current_user=Depends(get_current_user)):
    clarification_agent = get_clarification_agent()
    session = clarification_agent.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="澄清会话不存在或已过期")
    return success_response(data=session)


@router.delete("/session/{session_id}")
async def cancel_clarification_session(session_id: str, current_user=Depends(get_current_user)):
    clarification_agent = get_clarification_agent()
    cancelled = clarification_agent.cancel_session(session_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="澄清会话不存在或已过期")
    return success_response(message="澄清会话已取消")
