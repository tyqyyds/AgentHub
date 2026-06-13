from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from ..database.connection import get_db_session
from ..database.models import Intent, WizardSession
from .deps import get_current_user

router = APIRouter()


class ClarificationRequest(BaseModel):
    intent_id: int
    question: str
    options: Optional[List[str]] = None


class ClarificationResponse(BaseModel):
    intent_id: int
    answer: str
    selected_option: Optional[str] = None


@router.post("/ask")
async def ask_clarification(
    req: ClarificationRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Intent).where(Intent.id == req.intent_id))
    intent = result.scalar_one_or_none()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    return {"status": "success", "data": {"intent_id": req.intent_id, "question": req.question, "options": req.options, "session_active": True}}


@router.post("/answer")
async def submit_clarification(
    req: ClarificationResponse,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Intent).where(Intent.id == req.intent_id))
    intent = result.scalar_one_or_none()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    return {"status": "success", "data": {"intent_id": req.intent_id, "answer_received": True, "clarification_complete": True}}


@router.get("/wizard/{session_id}")
async def get_wizard_session(
    session_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(WizardSession).where(WizardSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Wizard session not found")
    return {"status": "success", "data": {"id": session.id, "current_step": session.current_step, "total_steps": session.total_steps, "wizard_data": session.wizard_data}}


@router.post("/wizard/{session_id}/next")
async def wizard_next_step(
    session_id: int,
    step_data: dict,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(WizardSession).where(WizardSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Wizard session not found")
    session.current_step = min(session.current_step + 1, session.total_steps)
    if session.wizard_data:
        session.wizard_data.update(step_data)
    else:
        session.wizard_data = step_data
    await db.commit()
    return {"status": "success", "data": {"current_step": session.current_step, "total_steps": session.total_steps}}
