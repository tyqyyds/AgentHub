from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from backend.core.security.rbac import get_current_user, requires_permission
from backend.agents.grayscale_healing import get_grayscale_healing_engine
from backend.api.response import success_response
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateGrayscaleTaskRequest(BaseModel):
    event_id: int = Field(..., description="关联的自愈事件ID")
    target_devices: List[str] = Field(..., min_length=1, description="所有目标设备ID列表")
    canary_device: str = Field(..., description="金丝雀设备ID（用于先行测试）")


class RollbackRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="回滚原因")


class EvaluateRequest(BaseModel):
    event_id: int = Field(..., description="自愈事件ID")
    task_id: Optional[str] = Field(None, description="关联的灰度任务ID")


@router.post("/tasks")
async def create_task(
    req: CreateGrayscaleTaskRequest,
    current_user=Depends(requires_permission("events:execute")),
):
    try:
        if req.canary_device not in req.target_devices:
            raise HTTPException(status_code=400, detail="canary_device must be in target_devices")
        engine = get_grayscale_healing_engine()
        task = await engine.create_task(
            event_id=req.event_id,
            target_devices=req.target_devices,
            canary_device=req.canary_device,
            created_by=current_user.username,
        )
        from backend.agents.grayscale_healing import _serialize_task
        return success_response(data=_serialize_task(task))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create grayscale healing task failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tasks/{task_id}/canary")
async def execute_canary(
    task_id: str,
    current_user=Depends(requires_permission("events:execute")),
):
    try:
        engine = get_grayscale_healing_engine()
        result = await engine.execute_canary(task_id)
        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execute canary failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tasks/{task_id}/batch")
async def execute_batch(
    task_id: str,
    current_user=Depends(requires_permission("events:execute")),
):
    try:
        engine = get_grayscale_healing_engine()
        result = await engine.execute_batch(task_id)
        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execute batch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tasks/{task_id}/rollback")
async def rollback_task(
    task_id: str,
    req: RollbackRequest,
    current_user=Depends(requires_permission("events:execute")),
):
    try:
        engine = get_grayscale_healing_engine()
        result = await engine.rollback_task(task_id, reason=req.reason)
        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rollback task failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tasks/{task_id}/analyze")
async def analyze_root_cause(
    task_id: str,
    current_user=Depends(get_current_user),
):
    try:
        engine = get_grayscale_healing_engine()
        result = await engine.analyze_root_cause(task_id)
        return success_response(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Root cause analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    current_user=Depends(get_current_user),
):
    try:
        engine = get_grayscale_healing_engine()
        tasks = await engine.list_tasks(status=status, limit=limit, offset=offset)
        return success_response(data={"items": tasks, "total": len(tasks)})
    except Exception as e:
        logger.error(f"List grayscale healing tasks failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    current_user=Depends(get_current_user),
):
    try:
        engine = get_grayscale_healing_engine()
        task = await engine.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
        return success_response(data=task)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get grayscale healing task failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/evaluate")
async def evaluate_healing(
    req: EvaluateRequest,
    current_user=Depends(get_current_user),
):
    try:
        engine = get_grayscale_healing_engine()
        result = await engine.evaluate_healing(event_id=req.event_id, task_id=req.task_id)
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Evaluate healing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/evaluations")
async def list_evaluations(
    event_id: Optional[int] = None,
    task_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    current_user=Depends(get_current_user),
):
    try:
        engine = get_grayscale_healing_engine()
        evaluations = await engine.list_evaluations(
            event_id=event_id, task_id=task_id, limit=limit, offset=offset
        )
        return success_response(data={"items": evaluations, "total": len(evaluations)})
    except Exception as e:
        logger.error(f"List evaluations failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/events/{event_id}/state-machine")
async def get_event_state_machine(
    event_id: int,
    current_user=Depends(get_current_user),
):
    """Get the state machine data for a self-healing event, including real agent reasoning and results."""
    try:
        from backend.database.connection import async_session_maker
        from backend.database.models import SelfHealingEvent, HealingEvaluation
        from sqlalchemy import select

        async with async_session_maker() as session:
            result = await session.execute(
                select(SelfHealingEvent).where(SelfHealingEvent.id == event_id)
            )
            event = result.scalar_one_or_none()
            if not event:
                raise HTTPException(status_code=404, detail="Event not found")

            # Get evaluations for this event
            eval_result = await session.execute(
                select(HealingEvaluation).where(HealingEvaluation.event_id == event_id)
            )
            evaluations = eval_result.scalars().all()

            # Build state machine nodes from real data
            event_data = {
                "id": event.id,
                "event_type": event.event_type,
                "severity": event.severity,
                "description": event.description,
                "status": event.status,
                "target_device": event.target_device,
                "suggested_action": event.suggested_action,
                "executed_by": event.executed_by,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }

            nodes = [
                {
                    "id": "start", "label": "开始", "type": "start", "status": "completed",
                    "timestamp": event.created_at.isoformat() if event.created_at else None,
                },
                {
                    "id": "detection", "label": "故障检测", "type": "agent",
                    "status": "completed" if event.status != "pending" else "active",
                    "agentName": "TelemetryAgent",
                    "reasoning": f"检测到{event.event_type}类型故障，严重程度: {event.severity}",
                    "input": {"event_type": event.event_type, "device": event.target_device},
                    "output": {"description": event.description, "severity": event.severity},
                    "timestamp": event.created_at.isoformat() if event.created_at else None,
                },
                {
                    "id": "analysis", "label": "根因分析", "type": "agent",
                    "status": "completed" if event.status in ["healing", "completed", "approved"] else
                              "active" if event.status == "analyzing" else "pending",
                    "agentName": "AnalysisAgent",
                    "reasoning": event.suggested_action or "分析故障根因中...",
                    "input": {"event": event.description, "device": event.target_device},
                    "output": {"rootCause": event.suggested_action or "待分析", "confidence": 0.0},
                    "timestamp": None,
                },
                {
                    "id": "solution", "label": "方案生成", "type": "agent",
                    "status": "completed" if event.status in ["healing", "completed", "approved"] else "pending",
                    "agentName": "SolutionAgent",
                    "reasoning": event.suggested_action or "基于根因分析生成自愈方案",
                    "input": {"rootCause": event.suggested_action, "targetDevice": event.target_device},
                    "output": {"solution": event.suggested_action or "待生成"},
                    "timestamp": None,
                },
                {
                    "id": "approval", "label": "安全审批", "type": "approval",
                    "status": "completed" if event.status in ["approved", "healing", "completed"] else
                              "skipped" if event.status == "rejected" else "pending",
                    "agentName": "HumanApproval",
                    "reasoning": "管理员审批" if event.status in ["approved", "healing", "completed"] else "等待审批",
                    "input": {"solution": event.suggested_action},
                    "output": {"approved": event.status in ["approved", "healing", "completed"]},
                    "timestamp": None,
                },
                {
                    "id": "execution", "label": "执行自愈", "type": "agent",
                    "status": "completed" if event.status == "completed" else
                              "active" if event.status == "healing" else "pending",
                    "agentName": "ExecutionAgent",
                    "reasoning": "执行自愈方案并下发配置命令",
                    "input": {"commands": [event.suggested_action or "N/A"]},
                    "output": {"success": event.status == "completed", "device": event.target_device},
                    "timestamp": None,
                },
                {
                    "id": "verification", "label": "效果验证", "type": "agent",
                    "status": "completed" if event.status == "completed" and evaluations else "pending",
                    "agentName": "VerificationAgent",
                    "reasoning": "验证自愈效果是否达标" if evaluations else "待验证",
                    "input": {"device": event.target_device},
                    "output": {"verified": bool(evaluations), "score": evaluations[0].effectiveness_score if evaluations else None},
                    "timestamp": evaluations[0].evaluated_at.isoformat() if evaluations and evaluations[0].evaluated_at else None,
                },
                {
                    "id": "end", "label": "结束", "type": "end",
                    "status": "completed" if event.status == "completed" else "pending",
                }
            ]

            edges = [
                {"id": "e1", "source": "start", "target": "detection"},
                {"id": "e2", "source": "detection", "target": "analysis"},
                {"id": "e3", "source": "analysis", "target": "solution"},
                {"id": "e4", "source": "solution", "target": "approval", "condition": "方案已生成", "label": "提交审批"},
                {"id": "e5", "source": "approval", "target": "execution", "condition": "approved = true", "label": "通过"},
                {"id": "e6", "source": "approval", "target": "end", "condition": "approved = false", "label": "拒绝"},
                {"id": "e7", "source": "execution", "target": "verification"},
                {"id": "e8", "source": "verification", "target": "end"},
            ]

            return success_response(data={
                "event": event_data,
                "nodes": nodes,
                "edges": edges,
            })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get state machine failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
