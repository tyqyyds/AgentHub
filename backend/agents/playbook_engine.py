from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import async_session_maker
from backend.database.models import Playbook, PlaybookExecution
import asyncio
import uuid
import logging

logger = logging.getLogger(__name__)


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _serialize_playbook(pb: Playbook) -> dict:
    return {
        "id": pb.id,
        "playbook_id": pb.playbook_id,
        "name": pb.name,
        "description": pb.description,
        "category": pb.category,
        "steps": pb.steps,
        "parameters_schema": pb.parameters_schema,
        "is_public": pb.is_public,
        "author": pb.author,
        "version": pb.version,
        "execution_count": pb.execution_count,
        "last_execution_status": pb.last_execution_status,
        "tags": pb.tags,
        "created_at": pb.created_at.isoformat() if pb.created_at else None,
        "updated_at": pb.updated_at.isoformat() if pb.updated_at else None,
    }


def _serialize_execution(ex: PlaybookExecution) -> dict:
    return {
        "id": ex.id,
        "execution_id": ex.execution_id,
        "playbook_id": ex.playbook_id,
        "status": ex.status,
        "current_step_index": ex.current_step_index,
        "parameter_values": ex.parameter_values,
        "step_results": ex.step_results,
        "triggered_by": ex.triggered_by,
        "started_at": ex.started_at.isoformat() if ex.started_at else None,
        "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
        "error_message": ex.error_message,
        "created_at": ex.created_at.isoformat() if ex.created_at else None,
    }


class PlaybookEngine:
    def __init__(self):
        self._running_executions: Dict[str, asyncio.Task] = {}

    async def create_playbook(
        self,
        name: str,
        description: str,
        category: str,
        steps: list,
        author: str,
        **kwargs,
    ) -> Playbook:
        async with async_session_maker() as session:
            playbook_id = _generate_id("pb")
            pb = Playbook(
                playbook_id=playbook_id,
                name=name,
                description=description,
                category=category,
                steps=steps,
                author=author,
                parameters_schema=kwargs.get("parameters_schema"),
                is_public=kwargs.get("is_public", True),
                tags=kwargs.get("tags", []),
            )
            session.add(pb)
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
            await session.refresh(pb)
            logger.info(f"Created playbook {playbook_id}: {name}")
            return pb

    async def list_playbooks(
        self,
        category: Optional[str] = None,
        is_public: Optional[bool] = None,
        author: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[dict]:
        async with async_session_maker() as session:
            query = select(Playbook)
            if category is not None:
                query = query.where(Playbook.category == category)
            if is_public is not None:
                query = query.where(Playbook.is_public == is_public)
            if author is not None:
                query = query.where(Playbook.author == author)
            if search is not None:
                query = query.where(
                    or_(
                        Playbook.name.contains(search),
                        Playbook.description.contains(search),
                    )
                )
            query = query.order_by(Playbook.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(query)
            playbooks = result.scalars().all()
            return [_serialize_playbook(pb) for pb in playbooks]

    async def get_playbook(self, playbook_id: str) -> Optional[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Playbook).where(Playbook.playbook_id == playbook_id)
            )
            pb = result.scalar_one_or_none()
            if pb is None:
                return None
            return _serialize_playbook(pb)

    async def update_playbook(self, playbook_id: str, **kwargs) -> Optional[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Playbook).where(Playbook.playbook_id == playbook_id)
            )
            pb = result.scalar_one_or_none()
            if pb is None:
                return None
            for key, value in kwargs.items():
                if hasattr(pb, key) and value is not None:
                    setattr(pb, key, value)
            pb.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(pb)
            logger.info(f"Updated playbook {playbook_id}")
            return _serialize_playbook(pb)

    async def delete_playbook(self, playbook_id: str) -> bool:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Playbook).where(Playbook.playbook_id == playbook_id)
            )
            pb = result.scalar_one_or_none()
            if pb is None:
                return False
            await session.delete(pb)
            await session.commit()
            logger.info(f"Deleted playbook {playbook_id}")
            return True

    async def execute_playbook(
        self,
        playbook_id: str,
        parameter_values: dict,
        triggered_by: str,
    ) -> PlaybookExecution:
        async with async_session_maker() as session:
            result = await session.execute(
                select(Playbook).where(Playbook.playbook_id == playbook_id)
            )
            pb = result.scalar_one_or_none()
            if pb is None:
                raise ValueError(f"Playbook not found: {playbook_id}")

            execution_id = _generate_id("pbe")
            execution = PlaybookExecution(
                execution_id=execution_id,
                playbook_id=playbook_id,
                status="pending",
                current_step_index=0,
                parameter_values=parameter_values,
                step_results=[],
                triggered_by=triggered_by,
            )
            session.add(execution)

            pb.execution_count += 1
            await session.commit()
            await session.refresh(execution)

            logger.info(f"Started execution {execution_id} for playbook {playbook_id}")

        task = asyncio.create_task(self._run_execution(execution_id))
        self._running_executions[execution_id] = task

        return execution

    async def _run_execution(self, execution_id: str):
        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(PlaybookExecution).where(
                        PlaybookExecution.execution_id == execution_id
                    )
                )
                execution = result.scalar_one_or_none()
                if execution is None:
                    return

                execution.status = "running"
                execution.started_at = datetime.now(timezone.utc)
                await session.commit()

            while True:
                step_result = await self.execute_step(execution_id)
                if step_result is None:
                    break
                if step_result.get("status") == "waiting_approval":
                    break
                if step_result.get("status") == "completed":
                    break
                if step_result.get("status") == "failed":
                    break
                if step_result.get("status") == "cancelled":
                    break

        except Exception as e:
            logger.error(f"Execution {execution_id} failed: {e}", exc_info=True)
            async with async_session_maker() as session:
                result = await session.execute(
                    select(PlaybookExecution).where(
                        PlaybookExecution.execution_id == execution_id
                    )
                )
                execution = result.scalar_one_or_none()
                if execution:
                    execution.status = "failed"
                    execution.error_message = str(e)
                    execution.completed_at = datetime.now(timezone.utc)
                    await session.commit()
                    await self._update_playbook_status(execution.playbook_id, "failed")
        finally:
            self._running_executions.pop(execution_id, None)

    async def _update_playbook_status(self, playbook_id: str, status: str):
        async with async_session_maker() as session:
            result = await session.execute(
                select(Playbook).where(Playbook.playbook_id == playbook_id)
            )
            pb = result.scalar_one_or_none()
            if pb:
                pb.last_execution_status = status
                await session.commit()

    async def execute_step(self, execution_id: str) -> Optional[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PlaybookExecution).where(
                    PlaybookExecution.execution_id == execution_id
                )
            )
            execution = result.scalar_one_or_none()
            if execution is None:
                return None

            if execution.status in ("completed", "failed", "cancelled"):
                return {"status": execution.status}

            pb_result = await session.execute(
                select(Playbook).where(Playbook.playbook_id == execution.playbook_id)
            )
            pb = pb_result.scalar_one_or_none()
            if pb is None:
                return None

            steps = pb.steps or []
            step_index = execution.current_step_index

            if step_index >= len(steps):
                execution.status = "completed"
                execution.completed_at = datetime.now(timezone.utc)
                await session.commit()
                await self._update_playbook_status(execution.playbook_id, "completed")
                return {"status": "completed", "step_index": step_index}

            step = steps[step_index]
            step_type = step.get("type", "")
            step_params = step.get("params", {})
            parameter_values = execution.parameter_values or {}

            try:
                if step_type == "intent":
                    step_result_data = await self._execute_intent_step(step_params, parameter_values)
                elif step_type == "approval":
                    execution.status = "running"
                    await session.commit()
                    step_results = list(execution.step_results or [])
                    step_results.append({
                        "step_index": step_index,
                        "step_id": step.get("id"),
                        "step_name": step.get("name"),
                        "type": "approval",
                        "status": "waiting_approval",
                        "started_at": datetime.now(timezone.utc).isoformat(),
                    })
                    execution.step_results = step_results
                    await session.commit()
                    return {"status": "waiting_approval", "step_index": step_index}
                elif step_type == "tool_call":
                    step_result_data = await self._execute_tool_call_step(step_params, parameter_values)
                elif step_type == "wait":
                    step_result_data = await self._execute_wait_step(step_params)
                elif step_type == "condition":
                    step_result_data = await self._execute_condition_step(step_params, parameter_values, step)
                elif step_type == "notification":
                    step_result_data = await self._execute_notification_step(step_params, execution)
                else:
                    step_result_data = {"status": "skipped", "reason": f"Unknown step type: {step_type}"}

                step_results = list(execution.step_results or [])
                step_results.append({
                    "step_index": step_index,
                    "step_id": step.get("id"),
                    "step_name": step.get("name"),
                    "type": step_type,
                    "result": step_result_data,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                execution.step_results = step_results

                if step_type == "condition" and step_result_data.get("branch_next_step") is not None:
                    next_step_id = step_result_data["branch_next_step"]
                    next_index = self._find_step_index(steps, next_step_id)
                    if next_index is not None:
                        execution.current_step_index = next_index
                    else:
                        execution.current_step_index = step_index + 1
                else:
                    next_step = step.get("next_step")
                    if next_step:
                        next_index = self._find_step_index(steps, next_step)
                        if next_index is not None:
                            execution.current_step_index = next_index
                        else:
                            execution.current_step_index = step_index + 1
                    else:
                        execution.current_step_index = step_index + 1

                await session.commit()

                if execution.current_step_index >= len(steps):
                    execution.status = "completed"
                    execution.completed_at = datetime.now(timezone.utc)
                    await session.commit()
                    await self._update_playbook_status(execution.playbook_id, "completed")
                    return {"status": "completed", "step_index": step_index}

                return {"status": "step_completed", "step_index": step_index, "result": step_result_data}

            except Exception as e:
                logger.error(f"Step execution failed for {execution_id} step {step_index}: {e}", exc_info=True)
                execution.status = "failed"
                execution.error_message = f"Step {step_index} ({step_type}) failed: {str(e)}"
                execution.completed_at = datetime.now(timezone.utc)
                step_results = list(execution.step_results or [])
                step_results.append({
                    "step_index": step_index,
                    "step_id": step.get("id"),
                    "step_name": step.get("name"),
                    "type": step_type,
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                execution.step_results = step_results
                await session.commit()
                await self._update_playbook_status(execution.playbook_id, "failed")
                return {"status": "failed", "step_index": step_index, "error": str(e)}

    def _find_step_index(self, steps: list, step_id: str) -> Optional[int]:
        for i, s in enumerate(steps):
            if s.get("id") == step_id:
                return i
        return None

    async def _execute_intent_step(self, params: dict, parameter_values: dict) -> dict:
        from backend.agents.intent_parser import IntentParserAgent
        user_input = params.get("user_input", "")
        for key, value in parameter_values.items():
            user_input = user_input.replace(f"{{{{{key}}}}}", str(value))
        parser = IntentParserAgent()
        parsed = parser.parse(user_input)
        return {
            "status": "success",
            "intent_type": parsed.intent_type,
            "actions": parsed.actions,
            "entities": parsed.entities,
        }

    async def _execute_tool_call_step(self, params: dict, parameter_values: dict) -> dict:
        from backend.agents.tool_registry import get_tool_registry
        tool_name = params.get("tool_name", "")
        tool_params = dict(params.get("tool_params", {}))
        for key, value in parameter_values.items():
            for pk, pv in tool_params.items():
                if isinstance(pv, str) and f"{{{{{key}}}}}" in pv:
                    tool_params[pk] = pv.replace(f"{{{{{key}}}}}", str(value))
        registry = get_tool_registry()
        result = await registry.execute_tool(tool_name, tool_params, "")
        return {"status": "success", "tool_name": tool_name, "result": result}

    async def _execute_wait_step(self, params: dict) -> dict:
        duration_seconds = params.get("duration_seconds", 0)
        await asyncio.sleep(duration_seconds)
        return {"status": "success", "waited_seconds": duration_seconds}

    async def _execute_condition_step(self, params: dict, parameter_values: dict, step: dict) -> dict:
        condition_field = params.get("field", "")
        condition_operator = params.get("operator", "==")
        condition_value = params.get("value", "")

        actual_value = parameter_values.get(condition_field, "")

        condition_met = False
        if condition_operator == "==":
            condition_met = str(actual_value) == str(condition_value)
        elif condition_operator == "!=":
            condition_met = str(actual_value) != str(condition_value)
        elif condition_operator == ">":
            try:
                condition_met = float(actual_value) > float(condition_value)
            except (ValueError, TypeError):
                condition_met = False
        elif condition_operator == "<":
            try:
                condition_met = float(actual_value) < float(condition_value)
            except (ValueError, TypeError):
                condition_met = False
        elif condition_operator == "in":
            condition_met = str(actual_value) in str(condition_value)
        elif condition_operator == "contains":
            condition_met = str(condition_value) in str(actual_value)

        branch_next_step = params.get("next_step_if_true") if condition_met else params.get("next_step_if_false")

        return {
            "status": "success",
            "condition_met": condition_met,
            "branch_next_step": branch_next_step,
        }

    async def _execute_notification_step(self, params: dict, execution: PlaybookExecution) -> dict:
        from backend.core.websocket_manager import manager
        message = params.get("message", "")
        target_user = params.get("target_user", "")
        notification = {
            "type": "playbook_notification",
            "data": {
                "execution_id": execution.execution_id,
                "playbook_id": execution.playbook_id,
                "message": message,
                "step_index": execution.current_step_index,
            },
        }
        if target_user:
            await manager.send_to_user(target_user, notification)
        else:
            await manager.broadcast(notification)
        return {"status": "success", "notification_sent": True, "target_user": target_user or "all"}

    async def approve_step(self, execution_id: str, approver: str) -> Optional[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PlaybookExecution).where(
                    PlaybookExecution.execution_id == execution_id
                )
            )
            execution = result.scalar_one_or_none()
            if execution is None:
                return None

            step_results = list(execution.step_results or [])
            current_step_result = None
            current_step_idx = None
            for i, sr in enumerate(step_results):
                if sr.get("status") == "waiting_approval":
                    current_step_result = sr
                    current_step_idx = i
                    break

            if current_step_result is None:
                raise ValueError("No step awaiting approval")

            step_results[current_step_idx]["status"] = "approved"
            step_results[current_step_idx]["approved_by"] = approver
            step_results[current_step_idx]["approved_at"] = datetime.now(timezone.utc).isoformat()
            execution.step_results = step_results

            pb_result = await session.execute(
                select(Playbook).where(Playbook.playbook_id == execution.playbook_id)
            )
            pb = pb_result.scalar_one_or_none()
            steps = pb.steps if pb else []
            step_index = execution.current_step_index
            if step_index < len(steps):
                step = steps[step_index]
                next_step = step.get("next_step")
                if next_step:
                    next_index = self._find_step_index(steps, next_step)
                    if next_index is not None:
                        execution.current_step_index = next_index
                    else:
                        execution.current_step_index = step_index + 1
                else:
                    execution.current_step_index = step_index + 1

            await session.commit()
            logger.info(f"Step approved for execution {execution_id} by {approver}")

        task = asyncio.create_task(self._run_execution(execution_id))
        self._running_executions[execution_id] = task

        async with async_session_maker() as session:
            result = await session.execute(
                select(PlaybookExecution).where(
                    PlaybookExecution.execution_id == execution_id
                )
            )
            execution = result.scalar_one_or_none()
            if execution:
                return _serialize_execution(execution)
        return None

    async def cancel_execution(self, execution_id: str) -> bool:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PlaybookExecution).where(
                    PlaybookExecution.execution_id == execution_id
                )
            )
            execution = result.scalar_one_or_none()
            if execution is None:
                return False
            if execution.status in ("completed", "failed", "cancelled"):
                return False
            execution.status = "cancelled"
            execution.completed_at = datetime.now(timezone.utc)
            await session.commit()
            await self._update_playbook_status(execution.playbook_id, "cancelled")

        task = self._running_executions.pop(execution_id, None)
        if task and not task.done():
            task.cancel()

        logger.info(f"Cancelled execution {execution_id}")
        return True

    async def get_execution(self, execution_id: str) -> Optional[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PlaybookExecution).where(
                    PlaybookExecution.execution_id == execution_id
                )
            )
            execution = result.scalar_one_or_none()
            if execution is None:
                return None
            return _serialize_execution(execution)

    async def list_executions(
        self,
        playbook_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[dict]:
        async with async_session_maker() as session:
            query = select(PlaybookExecution)
            if playbook_id is not None:
                query = query.where(PlaybookExecution.playbook_id == playbook_id)
            if status is not None:
                query = query.where(PlaybookExecution.status == status)
            query = query.order_by(PlaybookExecution.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(query)
            executions = result.scalars().all()
            return [_serialize_execution(ex) for ex in executions]

    async def get_execution_status(self, execution_id: str) -> Optional[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(PlaybookExecution).where(
                    PlaybookExecution.execution_id == execution_id
                )
            )
            execution = result.scalar_one_or_none()
            if execution is None:
                return None

            pb_result = await session.execute(
                select(Playbook).where(Playbook.playbook_id == execution.playbook_id)
            )
            pb = pb_result.scalar_one_or_none()
            steps = pb.steps if pb else []
            total_steps = len(steps)
            completed_steps = len([sr for sr in (execution.step_results or []) if sr.get("status") != "waiting_approval"])

            return {
                **_serialize_execution(execution),
                "total_steps": total_steps,
                "completed_steps": completed_steps,
                "progress": completed_steps / total_steps if total_steps > 0 else 0.0,
                "current_step": steps[execution.current_step_index] if execution.current_step_index < total_steps else None,
            }


_playbook_engine: Optional[PlaybookEngine] = None


def get_playbook_engine() -> PlaybookEngine:
    global _playbook_engine
    if _playbook_engine is None:
        _playbook_engine = PlaybookEngine()
    return _playbook_engine
