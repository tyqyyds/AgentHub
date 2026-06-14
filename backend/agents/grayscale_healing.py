from typing import List, Dict, Optional
from datetime import datetime, timezone
from sqlalchemy import select
from backend.database.connection import async_session_maker
from backend.database.models import GrayscaleHealingTask, HealingEvaluation, SelfHealingEvent
from backend.core.config import settings
import asyncio
import uuid
import logging
import json

logger = logging.getLogger(__name__)


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _serialize_task(task: GrayscaleHealingTask) -> dict:
    return {
        "id": task.id,
        "task_id": task.task_id,
        "event_id": task.event_id,
        "target_devices": task.target_devices,
        "canary_device": task.canary_device,
        "canary_status": task.canary_status,
        "canary_result": task.canary_result,
        "canary_started_at": task.canary_started_at.isoformat() if task.canary_started_at else None,
        "canary_completed_at": task.canary_completed_at.isoformat() if task.canary_completed_at else None,
        "batch_status": task.batch_status,
        "batch_progress": task.batch_progress,
        "batch_completed_devices": task.batch_completed_devices,
        "batch_failed_devices": task.batch_failed_devices,
        "batch_started_at": task.batch_started_at.isoformat() if task.batch_started_at else None,
        "batch_completed_at": task.batch_completed_at.isoformat() if task.batch_completed_at else None,
        "rollback_triggered": task.rollback_triggered,
        "rollback_reason": task.rollback_reason,
        "overall_status": task.overall_status,
        "created_by": task.created_by,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _serialize_evaluation(ev: HealingEvaluation) -> dict:
    return {
        "id": ev.id,
        "evaluation_id": ev.evaluation_id,
        "event_id": ev.event_id,
        "task_id": ev.task_id,
        "metrics_before": ev.metrics_before,
        "metrics_after": ev.metrics_after,
        "healing_action": ev.healing_action,
        "effectiveness_score": ev.effectiveness_score,
        "root_cause_analysis": ev.root_cause_analysis,
        "side_effects": ev.side_effects,
        "recommendation": ev.recommendation,
        "evaluated_at": ev.evaluated_at.isoformat() if ev.evaluated_at else None,
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


class GrayscaleHealingEngine:
    def __init__(self):
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def create_task(
        self,
        event_id: int,
        target_devices: list,
        canary_device: str,
        created_by: str,
    ) -> GrayscaleHealingTask:
        async with async_session_maker() as session:
            task_id = _generate_id("gs")
            task = GrayscaleHealingTask(
                task_id=task_id,
                event_id=event_id,
                target_devices=target_devices,
                canary_device=canary_device,
                created_by=created_by,
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            logger.info(f"Created grayscale healing task {task_id} for event {event_id}")
            return task

    async def execute_canary(self, task_id: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(GrayscaleHealingTask).where(GrayscaleHealingTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if task is None:
                raise ValueError(f"Task not found: {task_id}")

            task.canary_status = "running"
            task.overall_status = "canary_running"
            task.canary_started_at = datetime.now(timezone.utc)
            await session.commit()

            event_id = task.event_id
            canary_device = task.canary_device

        try:
            event_result = await self._get_event(event_id)
            healing_action = event_result.get("suggested_action", "") if event_result else ""

            canary_result = await self._execute_healing_on_device(
                canary_device, healing_action
            )

            await asyncio.sleep(settings.grayscale_canary_observation_seconds)

            device_healthy = await self._check_device_health(canary_device)

            async with async_session_maker() as session:
                result = await session.execute(
                    select(GrayscaleHealingTask).where(GrayscaleHealingTask.task_id == task_id)
                )
                task = result.scalar_one_or_none()
                if task is None:
                    raise ValueError(f"Task not found: {task_id}")

                task.canary_completed_at = datetime.now(timezone.utc)
                task.canary_result = canary_result

                if device_healthy:
                    task.canary_status = "success"
                    task.overall_status = "canary_success"
                    logger.info(f"Canary phase succeeded for task {task_id}")
                else:
                    task.canary_status = "failed"
                    task.overall_status = "batch_failed"
                    if settings.grayscale_auto_rollback:
                        task.rollback_triggered = True
                        task.rollback_reason = "Canary device unhealthy after healing"
                        task.overall_status = "rolled_back"
                        logger.warning(f"Canary phase failed for task {task_id}, auto-rollback triggered")
                    else:
                        logger.warning(f"Canary phase failed for task {task_id}")

                await session.commit()

                try:
                    from backend.core.websocket_manager import manager as ws_manager
                    await ws_manager.broadcast({
                        "type": "grayscale_progress",
                        "data": {"task_id": task_id, "phase": "canary", "status": task.canary_status, "device": task.canary_device}
                    })
                except Exception as e:
                    logger.warning(f"WebSocket broadcast failed: {e}")

                return _serialize_task(task)

        except Exception as e:
            logger.error(f"Canary execution failed for task {task_id}: {e}", exc_info=True)
            async with async_session_maker() as session:
                result = await session.execute(
                    select(GrayscaleHealingTask).where(GrayscaleHealingTask.task_id == task_id)
                )
                task = result.scalar_one_or_none()
                if task:
                    task.canary_status = "failed"
                    task.canary_completed_at = datetime.now(timezone.utc)
                    task.overall_status = "batch_failed"
                    task.canary_result = {"error": str(e)}
                    if settings.grayscale_auto_rollback:
                        task.rollback_triggered = True
                        task.rollback_reason = f"Canary execution error: {str(e)}"
                        task.overall_status = "rolled_back"
                    await session.commit()
            raise

    async def execute_batch(self, task_id: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(GrayscaleHealingTask).where(GrayscaleHealingTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if task is None:
                raise ValueError(f"Task not found: {task_id}")

            if task.canary_status != "success":
                raise ValueError(f"Cannot start batch: canary status is {task.canary_status}")

            remaining_devices = [
                d for d in task.target_devices
                if d != task.canary_device and d not in (task.batch_completed_devices or [])
            ]

            task.batch_status = "running"
            task.overall_status = "batch_running"
            task.batch_started_at = datetime.now(timezone.utc)
            await session.commit()

            event_id = task.event_id
            batch_completed_devices = list(task.batch_completed_devices or [])
            batch_failed_devices = list(task.batch_failed_devices or [])
            target_devices = list(task.target_devices or [])

        event_result = await self._get_event(event_id)
        healing_action = event_result.get("suggested_action", "") if event_result else ""

        completed_devices = batch_completed_devices
        failed_devices = batch_failed_devices
        total_remaining = len(remaining_devices)
        processed = 0

        try:
            batch_size = settings.grayscale_batch_size
            for i in range(0, total_remaining, batch_size):
                batch = remaining_devices[i:i + batch_size]

                for device_id in batch:
                    try:
                        await self._execute_healing_on_device(device_id, healing_action)
                        completed_devices.append(device_id)
                    except Exception as e:
                        logger.error(f"Failed to heal device {device_id}: {e}")
                        failed_devices.append(device_id)

                processed += len(batch)

                async with async_session_maker() as session:
                    result = await session.execute(
                        select(GrayscaleHealingTask).where(GrayscaleHealingTask.task_id == task_id)
                    )
                    task = result.scalar_one_or_none()
                    if task is None:
                        break

                    task.batch_completed_devices = completed_devices
                    task.batch_failed_devices = failed_devices
                    task.batch_progress = int((processed / len(target_devices)) * 100)
                    await session.commit()

                try:
                    from backend.core.websocket_manager import manager as ws_manager
                    await ws_manager.broadcast({
                        "type": "grayscale_progress",
                        "data": {"task_id": task_id, "phase": "batch", "status": "running", "progress": task.batch_progress}
                    })
                except Exception as e:
                    logger.warning(f"WebSocket broadcast failed: {e}")

                critical_failure = len(failed_devices) > len(target_devices) * 0.5
                if critical_failure and settings.grayscale_auto_rollback:
                    return await self.rollback_task(task_id, "Critical batch failure: too many devices failed")

                if i + batch_size < total_remaining:
                    await asyncio.sleep(settings.grayscale_batch_observation_seconds)

            async with async_session_maker() as session:
                result = await session.execute(
                    select(GrayscaleHealingTask).where(GrayscaleHealingTask.task_id == task_id)
                )
                task = result.scalar_one_or_none()
                if task is None:
                    raise ValueError(f"Task not found: {task_id}")

                task.batch_completed_at = datetime.now(timezone.utc)
                task.batch_progress = 100

                if failed_devices:
                    task.batch_status = "failed"
                    task.overall_status = "batch_failed"
                else:
                    task.batch_status = "success"
                    task.overall_status = "batch_success"

                await session.commit()
                return _serialize_task(task)

        except Exception as e:
            logger.error(f"Batch execution failed for task {task_id}: {e}", exc_info=True)
            async with async_session_maker() as session:
                result = await session.execute(
                    select(GrayscaleHealingTask).where(GrayscaleHealingTask.task_id == task_id)
                )
                task = result.scalar_one_or_none()
                if task:
                    task.batch_status = "failed"
                    task.batch_completed_at = datetime.now(timezone.utc)
                    task.overall_status = "batch_failed"
                    await session.commit()
            raise

    async def rollback_task(self, task_id: str, reason: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(GrayscaleHealingTask).where(GrayscaleHealingTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if task is None:
                raise ValueError(f"Task not found: {task_id}")

            task.rollback_triggered = True
            task.rollback_reason = reason
            task.overall_status = "rolled_back"
            await session.commit()

            try:
                from backend.core.websocket_manager import manager as ws_manager
                await ws_manager.broadcast({
                    "type": "grayscale_progress",
                    "data": {"task_id": task_id, "phase": "rollback", "status": "rolled_back", "reason": reason}
                })
            except Exception as e:
                logger.warning(f"WebSocket broadcast failed: {e}")

            batch_completed_devices = list(task.batch_completed_devices or [])
            canary_status = task.canary_status
            canary_device = task.canary_device

        all_healed = batch_completed_devices
        if canary_status == "success":
            all_healed.append(canary_device)

        rollback_results = {}
        for device_id in all_healed:
            try:
                rollback_result = await self._execute_rollback_on_device(device_id)
                rollback_results[device_id] = rollback_result
            except Exception as e:
                logger.error(f"Rollback failed for device {device_id}: {e}")
                rollback_results[device_id] = {"status": "failed", "error": str(e)}

        await self.analyze_root_cause(task_id)

        async with async_session_maker() as session:
            result = await session.execute(
                select(GrayscaleHealingTask).where(GrayscaleHealingTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            return _serialize_task(task) if task else {}

    async def analyze_root_cause(self, task_id: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(GrayscaleHealingTask).where(GrayscaleHealingTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if task is None:
                raise ValueError(f"Task not found: {task_id}")

            event_id = task.event_id
            canary_device = task.canary_device
            canary_status = task.canary_status
            canary_result = task.canary_result
            batch_failed_devices = task.batch_failed_devices
            rollback_reason = task.rollback_reason

        event_result = await self._get_event(event_id)
        healing_action = event_result.get("suggested_action", "") if event_result else ""
        event_description = event_result.get("description", "") if event_result else ""

        metrics_before = await self._collect_device_metrics(canary_device)
        metrics_after = await self._collect_device_metrics(canary_device)

        prompt = f"""你是智维AgentHub的根因分析引擎，负责分析灰度自愈失败的根本原因。

## 自愈事件信息:
- 事件描述: {event_description}
- 自愈动作: {healing_action}
- 金丝雀设备: {canary_device}
- 金丝雀状态: {canary_status}
- 金丝雀结果: {json.dumps(canary_result or {}, ensure_ascii=False)}
- 批次失败设备: {json.dumps(batch_failed_devices or [], ensure_ascii=False)}
- 回滚原因: {rollback_reason or 'N/A'}

## 设备指标(自愈前):
{json.dumps(metrics_before, ensure_ascii=False, indent=2)}

## 设备指标(自愈后):
{json.dumps(metrics_after, ensure_ascii=False, indent=2)}

## 任务:
1. 分析自愈失败的根本原因
2. 识别可能的副作用
3. 提供改进建议

## 输出格式（纯JSON，不要markdown代码块）:
{{
  "root_cause": "根本原因描述",
  "contributing_factors": ["因素1", "因素2"],
  "side_effects": ["副作用1", "副作用2"],
  "recommendation": "改进建议",
  "confidence": 0.0
}}

请只输出JSON，不要其他文字。"""

        rca_text = ""
        try:
            from backend.agents.llm_gateway import get_llm_gateway, TaskType
            gateway = get_llm_gateway()
            llm_result = await gateway.chat(
                messages=[
                    {"role": "system", "content": "你是网络运维根因分析专家，擅长分析自愈失败原因。"},
                    {"role": "user", "content": prompt},
                ],
                task_type=TaskType.FAULT_DIAGNOSE,
                temperature=0.3,
                max_tokens=1024,
            )
            rca_text = llm_result.get("content", "")
        except Exception as e:
            logger.error(f"LLM root cause analysis failed: {e}")
            rca_text = json.dumps({
                "root_cause": f"LLM分析不可用，手动分析: {rollback_reason or 'unknown'}",
                "contributing_factors": [],
                "side_effects": [],
                "recommendation": "请手动检查设备状态和自愈动作",
                "confidence": 0.0,
            })

        parsed_rca = {}
        try:
            json_str = rca_text.strip()
            if json_str.startswith("```"):
                json_str = json_str.split("\n", 1)[1] if "\n" in json_str else json_str[3:]
                json_str = json_str.rsplit("```", 1)[0]
            parsed_rca = json.loads(json_str.strip())
        except json.JSONDecodeError:
            parsed_rca = {"root_cause": rca_text, "raw_response": True}

        async with async_session_maker() as session:
            evaluation_id = _generate_id("eval")
            evaluation = HealingEvaluation(
                evaluation_id=evaluation_id,
                event_id=event_id,
                task_id=task_id,
                metrics_before=metrics_before,
                metrics_after=metrics_after,
                healing_action=healing_action,
                root_cause_analysis=parsed_rca.get("root_cause", ""),
                side_effects=parsed_rca.get("side_effects", []),
                recommendation=parsed_rca.get("recommendation", ""),
                evaluated_at=datetime.now(timezone.utc),
            )
            session.add(evaluation)
            await session.commit()
            await session.refresh(evaluation)
            logger.info(f"Root cause analysis completed for task {task_id}, evaluation {evaluation_id}")
            return _serialize_evaluation(evaluation)

    async def evaluate_healing(self, event_id: int, task_id: Optional[str] = None) -> dict:
        async with async_session_maker() as session:
            query = select(HealingEvaluation).where(HealingEvaluation.event_id == event_id)
            if task_id:
                query = query.where(HealingEvaluation.task_id == task_id)
            query = query.order_by(HealingEvaluation.created_at.desc())
            result = await session.execute(query)
            existing = result.scalar_one_or_none()

            if existing and existing.metrics_after is not None:
                return _serialize_evaluation(existing)

        event_result = await self._get_event(event_id)
        healing_action = event_result.get("suggested_action", "") if event_result else ""

        target_device = event_result.get("target_device", "") if event_result else ""
        metrics_before = await self._collect_device_metrics(target_device)
        metrics_after = await self._collect_device_metrics(target_device)

        effectiveness_score = self._calculate_effectiveness(metrics_before, metrics_after)
        side_effects = self._detect_side_effects(metrics_before, metrics_after)

        recommendation = ""
        if effectiveness_score >= 0.8:
            recommendation = "自愈效果良好，建议保持当前策略"
        elif effectiveness_score >= 0.5:
            recommendation = "自愈效果一般，建议优化自愈动作参数"
        else:
            recommendation = "自愈效果不佳，建议重新评估自愈策略或手动介入"

        async with async_session_maker() as session:
            evaluation_id = _generate_id("eval")
            evaluation = HealingEvaluation(
                evaluation_id=evaluation_id,
                event_id=event_id,
                task_id=task_id,
                metrics_before=metrics_before,
                metrics_after=metrics_after,
                healing_action=healing_action,
                effectiveness_score=effectiveness_score,
                side_effects=side_effects,
                recommendation=recommendation,
                evaluated_at=datetime.now(timezone.utc),
            )
            session.add(evaluation)
            await session.commit()
            await session.refresh(evaluation)
            logger.info(f"Healing evaluation completed for event {event_id}, score={effectiveness_score}")
            return _serialize_evaluation(evaluation)

    def _calculate_effectiveness(self, metrics_before: dict, metrics_after: dict) -> float:
        if not metrics_before or not metrics_after:
            return 0.0

        cpu_before = metrics_before.get("cpu_usage", 0)
        cpu_after = metrics_after.get("cpu_usage", 0)
        mem_before = metrics_before.get("memory_usage", 0)
        mem_after = metrics_after.get("memory_usage", 0)

        cpu_improved = max(0, cpu_before - cpu_after) / max(cpu_before, 1)
        mem_improved = max(0, mem_before - mem_after) / max(mem_before, 1)

        status_before = metrics_before.get("status", "unhealthy")
        status_after = metrics_after.get("status", "unhealthy")
        status_score = 1.0 if status_after == "healthy" and status_before != "healthy" else 0.0

        score = (cpu_improved * 0.3 + mem_improved * 0.3 + status_score * 0.4)
        return round(min(max(score, 0.0), 1.0), 2)

    def _detect_side_effects(self, metrics_before: dict, metrics_after: dict) -> list:
        side_effects = []
        if not metrics_before or not metrics_after:
            return side_effects

        if metrics_after.get("cpu_usage", 0) > metrics_before.get("cpu_usage", 0) + 20:
            side_effects.append("CPU使用率异常升高")
        if metrics_after.get("memory_usage", 0) > metrics_before.get("memory_usage", 0) + 20:
            side_effects.append("内存使用率异常升高")
        if metrics_before.get("status") == "healthy" and metrics_after.get("status") != "healthy":
            side_effects.append("设备状态从健康变为异常")

        return side_effects

    async def get_task(self, task_id: str) -> Optional[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(GrayscaleHealingTask).where(GrayscaleHealingTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if task is None:
                return None
            return _serialize_task(task)

    async def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[dict]:
        async with async_session_maker() as session:
            query = select(GrayscaleHealingTask)
            if status is not None:
                query = query.where(GrayscaleHealingTask.overall_status == status)
            query = query.order_by(GrayscaleHealingTask.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(query)
            tasks = result.scalars().all()
            return [_serialize_task(t) for t in tasks]

    async def list_evaluations(
        self,
        event_id: Optional[int] = None,
        task_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[dict]:
        async with async_session_maker() as session:
            query = select(HealingEvaluation)
            if event_id is not None:
                query = query.where(HealingEvaluation.event_id == event_id)
            if task_id is not None:
                query = query.where(HealingEvaluation.task_id == task_id)
            query = query.order_by(HealingEvaluation.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(query)
            evaluations = result.scalars().all()
            return [_serialize_evaluation(ev) for ev in evaluations]

    async def _get_event(self, event_id: int) -> Optional[dict]:
        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(SelfHealingEvent).where(SelfHealingEvent.id == event_id)
                )
                event = result.scalar_one_or_none()
                if event is None:
                    return None
                return {
                    "id": event.id,
                    "event_type": event.event_type,
                    "severity": event.severity,
                    "description": event.description,
                    "suggested_action": event.suggested_action,
                    "target_device": event.target_device,
                    "status": event.status,
                }
        except Exception as e:
            logger.error(f"Failed to get event {event_id}: {e}")
            return None

    async def _execute_healing_on_device(self, device_id: str, healing_action: str) -> dict:
        logger.info(f"Executing healing on device {device_id}: {healing_action}")
        return {
            "device_id": device_id,
            "action": healing_action,
            "status": "executed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _check_device_health(self, device_id: str) -> bool:
        try:
            async with async_session_maker() as session:
                from backend.database.models import Device
                result = await session.execute(
                    select(Device).where(Device.device_id == device_id)
                )
                device = result.scalar_one_or_none()
                if device and device.status == "healthy":
                    return True
        except Exception as e:
            logger.error(f"Device health check failed for {device_id}: {e}")
            return False
        return False

    async def _execute_rollback_on_device(self, device_id: str) -> dict:
        logger.info(f"Executing rollback on device {device_id}")
        return {
            "device_id": device_id,
            "status": "rolled_back",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _collect_device_metrics(self, device_id: str) -> dict:
        try:
            async with async_session_maker() as session:
                from backend.database.models import Device
                result = await session.execute(
                    select(Device).where(Device.device_id == device_id)
                )
                device = result.scalar_one_or_none()
                if device:
                    return {
                        "device_id": device_id,
                        "status": device.status,
                        "cpu_usage": device.cpu_usage,
                        "memory_usage": device.memory_usage,
                    }
        except Exception as e:
            logger.warning(f"Failed to collect metrics for {device_id}: {e}")
            return {"cpu_usage": 0, "memory_usage": 0, "interface_errors": 0, "link_utilization": 0}
        return {"device_id": device_id, "status": "unknown", "cpu_usage": 0, "memory_usage": 0}


_grayscale_healing_engine: Optional[GrayscaleHealingEngine] = None


def get_grayscale_healing_engine() -> GrayscaleHealingEngine:
    global _grayscale_healing_engine
    if _grayscale_healing_engine is None:
        _grayscale_healing_engine = GrayscaleHealingEngine()
    return _grayscale_healing_engine
