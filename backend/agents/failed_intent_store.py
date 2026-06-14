from typing import Dict, List, Optional
from datetime import datetime, timezone
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import async_session_maker
from backend.database.models import FailedIntentCase
import logging

logger = logging.getLogger(__name__)


class FailedIntentStore:
    async def record_failure(
        self,
        user_input: str,
        parse_method: str,
        failure_reason: str,
        raw_response: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> FailedIntentCase:
        async with async_session_maker() as session:
            case = FailedIntentCase(
                user_input=user_input,
                parse_method=parse_method,
                failure_reason=failure_reason,
                raw_response=raw_response,
                metadata=metadata
            )
            session.add(case)
            try:
                await session.commit()
                await session.refresh(case)
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to record failed intent case: {e}")
                raise
            logger.info(f"Recorded failed intent case {case.id}: method={parse_method}")
            return case

    async def resolve_case(
        self,
        case_id: int,
        user_clarification: str,
        resolution_notes: str
    ) -> bool:
        async with async_session_maker() as session:
            result = await session.execute(
                select(FailedIntentCase).where(FailedIntentCase.id == case_id)
            )
            case = result.scalar_one_or_none()
            if not case:
                return False
            case.resolved = True
            case.user_clarification = user_clarification
            case.resolution_notes = resolution_notes
            case.updated_at = datetime.now(timezone.utc)
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to resolve case {case_id}: {e}")
                raise
            logger.info(f"Resolved failed intent case {case_id}")
            return True

    async def list_cases(
        self,
        resolved: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[FailedIntentCase]:
        async with async_session_maker() as session:
            query = select(FailedIntentCase).order_by(FailedIntentCase.created_at.desc())
            if resolved is not None:
                query = query.where(FailedIntentCase.resolved == resolved)
            query = query.offset(offset).limit(limit)
            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_case(self, case_id: int) -> Optional[FailedIntentCase]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(FailedIntentCase).where(FailedIntentCase.id == case_id)
            )
            return result.scalar_one_or_none()

    async def get_failure_stats(self) -> Dict:
        async with async_session_maker() as session:
            total_result = await session.execute(
                select(func.count(FailedIntentCase.id))
            )
            total = total_result.scalar() or 0

            resolved_result = await session.execute(
                select(func.count(FailedIntentCase.id)).where(FailedIntentCase.resolved == True)
            )
            resolved = resolved_result.scalar() or 0

            by_method_result = await session.execute(
                select(FailedIntentCase.parse_method, func.count(FailedIntentCase.id))
                .group_by(FailedIntentCase.parse_method)
            )
            by_method = {row[0]: row[1] for row in by_method_result.all()}

            by_reason_result = await session.execute(
                select(FailedIntentCase.failure_reason, func.count(FailedIntentCase.id))
                .group_by(FailedIntentCase.failure_reason)
            )
            by_reason = {row[0]: row[1] for row in by_reason_result.all()}

            recent_result = await session.execute(
                select(func.count(FailedIntentCase.id))
                .where(
                    FailedIntentCase.created_at >= datetime.now(timezone.utc).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                )
            )
            today_count = recent_result.scalar() or 0

            # 找出最高频失败原因
            top_failure_reason = "--"
            if by_reason:
                top_failure_reason = max(by_reason, key=by_reason.get)

            return {
                "total_failures": total,
                "today_failures": today_count,
                "unresolved_cases": total - resolved,
                "resolution_rate": round((resolved / total * 100) if total > 0 else 0, 1),
                "total": total,
                "resolved": resolved,
                "unresolved": total - resolved,
                "today_count": today_count,
                "top_failure_reason": top_failure_reason,
                "by_method": by_method,
                "by_reason": by_reason
            }

    async def get_cases_for_finetuning(self, limit: int = 100) -> List[Dict]:
        async with async_session_maker() as session:
            query = (
                select(FailedIntentCase)
                .where(FailedIntentCase.resolved == True)
                .order_by(FailedIntentCase.updated_at.desc())
                .limit(limit)
            )
            result = await session.execute(query)
            cases = result.scalars().all()

            finetuning_data = []
            for case in cases:
                finetuning_data.append({
                    "messages": [
                        {"role": "system", "content": "你是一个专业的网络运维意图解析专家。请将用户的自然语言运维需求解析为结构化的JSON数据。"},
                        {"role": "user", "content": case.user_input},
                        {"role": "assistant", "content": case.user_clarification or ""}
                    ],
                    "metadata": {
                        "case_id": case.id,
                        "original_method": case.parse_method,
                        "failure_reason": case.failure_reason,
                        "resolution_notes": case.resolution_notes
                    }
                })
            return finetuning_data

    async def auto_resolve_with_clarification(
        self,
        case_id: int,
        clarification_response: str
    ) -> bool:
        async with async_session_maker() as session:
            result = await session.execute(
                select(FailedIntentCase).where(FailedIntentCase.id == case_id)
            )
            case = result.scalar_one_or_none()
            if not case:
                return False
            case.resolved = True
            case.user_clarification = clarification_response
            case.resolution_notes = f"Auto-resolved with clarification: {clarification_response}"
            case.updated_at = datetime.now(timezone.utc)
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to auto-resolve case {case_id}: {e}")
                raise
            logger.info(f"Auto-resolved failed intent case {case_id}")
            return True

    async def delete_case(self, case_id: int) -> bool:
        async with async_session_maker() as session:
            result = await session.execute(
                select(FailedIntentCase).where(FailedIntentCase.id == case_id)
            )
            case = result.scalar_one_or_none()
            if not case:
                return False
            await session.execute(
                delete(FailedIntentCase).where(FailedIntentCase.id == case_id)
            )
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to delete case {case_id}: {e}")
                raise
            logger.info(f"Deleted failed intent case {case_id}")
            return True


_failed_intent_store: Optional[FailedIntentStore] = None


def get_failed_intent_store() -> FailedIntentStore:
    global _failed_intent_store
    if _failed_intent_store is None:
        _failed_intent_store = FailedIntentStore()
    return _failed_intent_store
