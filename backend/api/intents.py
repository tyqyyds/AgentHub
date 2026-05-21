from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from backend.database.connection import get_db_session
from backend.database.models import Intent, ApprovalStatus

router = APIRouter()


class IntentCreate(BaseModel):
    user_input: str
    structured_params: dict


class IntentUpdate(BaseModel):
    approval_status: str


@router.post("/")
async def create_intent(intent: IntentCreate, db: AsyncSession = Depends(get_db_session)):
    new_intent = Intent(
        intent_name=intent.structured_params.get("intent_name", "unknown"),
        user_input=intent.user_input,
        structured_params=intent.structured_params
    )
    db.add(new_intent)
    await db.commit()
    await db.refresh(new_intent)
    return {"status": "success", "data": {"id": new_intent.id}}


@router.get("/")
async def get_intents(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(Intent.__table__.select())
    intents = result.fetchall()
    return {"status": "success", "data": [dict(row._mapping) for row in intents]}


@router.get("/{intent_id}")
async def get_intent(intent_id: int, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(Intent.__table__.select().where(Intent.id == intent_id))
    intent = result.first()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")
    return {"status": "success", "data": dict(intent._mapping)}


@router.put("/{intent_id}")
async def update_intent(intent_id: int, update: IntentUpdate, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(Intent.__table__.select().where(Intent.id == intent_id))
    intent = result.first()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")
    
    try:
        status = ApprovalStatus(update.approval_status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid approval status")
    
    await db.execute(
        Intent.__table__.update()
        .where(Intent.id == intent_id)
        .values(approval_status=status)
    )
    await db.commit()
    return {"status": "success"}


@router.delete("/{intent_id}")
async def delete_intent(intent_id: int, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(Intent.__table__.select().where(Intent.id == intent_id))
    intent = result.first()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")
    
    await db.execute(Intent.__table__.delete().where(Intent.id == intent_id))
    await db.commit()
    return {"status": "success"}