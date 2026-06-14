from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from pydantic import BaseModel, field_validator
from typing import Optional
from backend.database.connection import get_db_session
from backend.database.models import Intent, AuditLog, Device, DeviceLink
from datetime import datetime, timezone
from backend.agents.conflict_detector import ConflictDetectorAgent
from backend.agents.base import IntentContext, NetworkState, DeviceInfo
from backend.mcp.executor import get_tool_executor
from backend.core.security.rbac import get_current_user, requires_permission
from backend.core.config import settings
from backend.security.intent_scanner import intent_scanner
from backend.agents.proactive_notifier import ProactiveNotifier
from backend.api.fuse import check_fuse
import logging

logger = logging.getLogger(__name__)
_notifier = ProactiveNotifier()

router = APIRouter()

_conflict_detector = ConflictDetectorAgent()


async def _check_resource_conflicts(
    db: AsyncSession,
    structured_params: dict,
    sla_conditions: Optional[dict] = None,
) -> list[str]:
    """Pre-check for bandwidth and port conflicts with existing active intents.

    Returns a list of warning messages (empty if no conflicts).
    Does NOT block creation - only warns.
    """
    warnings = []
    intent_name = structured_params.get("intent_name", "")

    # Only check for bandwidth_guarantee and access_control intents
    if intent_name not in ("bandwidth_guarantee", "access_control", "qos_policy"):
        return warnings

    try:
        # Find active intents with same target device
        target_device = ""
        if isinstance(sla_conditions, dict):
            target_device = sla_conditions.get("target_device", "")

        if not target_device:
            return warnings

        # Query existing active intents for the same device
        result = await db.execute(
            Intent.__table__.select().where(
                Intent.approval_status.in_(["approved", "pending"]),
                Intent.execution_status.in_(["executed", "not_started", "running"]),
            )
        )
        active_intents = result.fetchall()

        for row in active_intents:
            existing_sla = row._mapping.get("sla_conditions", {})
            existing_params = row._mapping.get("structured_params", {})

            if not isinstance(existing_sla, dict):
                continue

            existing_device = existing_sla.get("target_device", "")

            # Check same target device
            if existing_device == target_device:
                existing_type = existing_params.get("intent_name", "")

                # Bandwidth conflict: two bandwidth_guarantee on same device
                if intent_name == "bandwidth_guarantee" and existing_type == "bandwidth_guarantee":
                    existing_bw = existing_params.get("bandwidth", "0")
                    new_bw = structured_params.get("bandwidth", "0")
                    try:
                        if int(existing_bw) + int(new_bw) > 10000:  # Assume 10G max
                            warnings.append(
                                f"带宽冲突风险: 设备'{target_device}'已有{existing_bw}Mbps带宽保障，"
                                f"新增{new_bw}Mbps可能超出链路容量"
                            )
                    except (ValueError, TypeError):
                        pass

                # Port conflict: overlapping access_control rules
                if intent_name == "access_control" and existing_type == "access_control":
                    existing_port = existing_params.get("port", "")
                    new_port = structured_params.get("port", "")
                    existing_action = existing_params.get("action", "")
                    new_action = structured_params.get("action", "")

                    if (existing_port and new_port and existing_port == new_port
                            and existing_action != new_action):
                        warnings.append(
                            f"端口冲突: 设备'{target_device}'端口{new_port}已有{existing_action}规则，"
                            f"与新增{new_action}规则冲突"
                        )

    except Exception as e:
        logger.debug(f"Conflict pre-check failed: {e}")

    return warnings


async def _build_network_state(db: AsyncSession) -> NetworkState:
    devices_result = await db.execute(Device.__table__.select())
    device_rows = devices_result.fetchall()
    devices = []
    qos_policies = []
    for row in device_rows:
        row_data = dict(row._mapping)
        devices.append(DeviceInfo(
            name=row_data.get("name", ""),
            ip=row_data.get("ip_address", ""),
            type=row_data.get("device_type", ""),
            status=row_data.get("status", "healthy")
        ))
        qos_data = row_data.get("qos_policies")
        if isinstance(qos_data, list):
            qos_policies.extend(qos_data)
    return NetworkState(devices=devices, qos_policies=qos_policies)

INTENT_KEYWORDS = {
    'git_clone_bandwidth_guarantee': ['git', '克隆', '带宽'],
    'bandwidth_guarantee': ['带宽', '保障', '视频', '最小', '保证', '最低', '预留', '推流', '同步', '上报', '突发', '扩容', '临时'],
    'fault_diagnosis': ['故障', '诊断', '排查', '异常', '问题'],
    'performance_monitoring': ['监控', '性能', '指标', '延迟', '丢包', '抖动', '确保'],
    'qos_policy': ['qos', '优先级', '策略', '配置', '队列', '信令', '音频'],
    'traffic_shaping': ['流量', '整形', '限制', '上限', '峰值', '最大', '阻断', '禁止', '回传'],
    'access_control': ['访问', 'acl', '权限', '开放', '禁止', '端口', '安全', '防火墙', '防护', '允许', '阻止', '阻断', '限制', '黑名单', '绑定', '跳板', '隧道', 'ipsec', 'ssh', 'https', 'mysql', 'hdfs', '直连'],
    'link_management': ['链路', '路由', '切换', '负载', '备用', '专线', '主出口', '自动'],
    'device_config': ['配置', '设备', '接口']
}

INTENT_MIN_MATCHES = {
    'git_clone_bandwidth_guarantee': 2,
    'bandwidth_guarantee': 1,
    'fault_diagnosis': 1,
    'performance_monitoring': 1,
    'qos_policy': 1,
    'traffic_shaping': 1,
    'access_control': 1,
    'link_management': 1,
    'device_config': 1
}


def validate_semantic_consistency(user_input: str, intent_name: str) -> tuple[bool, str]:
    keywords = INTENT_KEYWORDS.get(intent_name, [])
    min_matches = INTENT_MIN_MATCHES.get(intent_name, 1)
    lower_input = user_input.lower()
    match_count = sum(1 for kw in keywords if kw.lower() in lower_input)

    if match_count < min_matches:
        matched = [kw for kw in keywords if kw.lower() in lower_input]
        missing = [kw for kw in keywords if kw.lower() not in lower_input]
        return False, (
            f'意图描述与识别类型"{intent_name}"不匹配。'
            f'命中的关键词: {matched or "无"}，'
            f'需要至少{min_matches}个关键词匹配（{missing}未命中）。'
            f'请提供更明确的描述，包含与操作相关的关键词。'
        )
    return True, ''


class IntentCreate(BaseModel):
    user_input: str
    structured_params: dict
    sla_conditions: Optional[dict] = None

    @field_validator('user_input')
    @classmethod
    def user_input_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('user_input cannot be empty')
        if len(v.strip()) < 4:
            raise ValueError('意图描述过短，请提供更详细的描述')
        if len(v.strip()) > 2000:
            raise ValueError('user_input cannot exceed 2000 characters')
        return v

    @field_validator('structured_params')
    @classmethod
    def structured_params_valid(cls, v):
        if not isinstance(v, dict):
            raise ValueError('structured_params must be a dictionary')
        if 'intent_name' not in v:
            raise ValueError('structured_params must contain intent_name')
        intent_name = v.get('intent_name', '')
        valid_intents = [
            'git_clone_bandwidth_guarantee', 'bandwidth_guarantee',
            'fault_diagnosis', 'performance_monitoring', 'qos_policy',
            'traffic_shaping', 'access_control', 'link_management',
            'device_config'
        ]
        if intent_name in ('unrecognized_intent', 'invalid_input', 'general_config'):
            raise ValueError(f'无法识别有效的网络运维意图，请提供更具体的描述')
        if intent_name not in valid_intents:
            raise ValueError(f'不支持的意图类型: {intent_name}，支持的类型: {", ".join(valid_intents)}')
        if 'confidence' in v:
            confidence = v['confidence']
            if isinstance(confidence, (int, float)) and confidence < 0.35:
                raise ValueError(f'意图识别置信度过低（{round(confidence * 100)}%），请提供更明确的描述')
        return v


class IntentUpdate(BaseModel):
    approval_status: str

    @field_validator('approval_status')
    @classmethod
    def approval_status_valid(cls, v):
        valid_statuses = ["pending", "approved", "rejected"]
        if v not in valid_statuses:
            raise ValueError(f'approval_status must be one of: {valid_statuses}')
        return v


@router.post("")
async def create_intent(intent: IntentCreate, db: AsyncSession = Depends(get_db_session), current_user=Depends(requires_permission("intents:create")), _fuse=Depends(check_fuse)):
    scan_result = intent_scanner.scan(intent.user_input)
    params_scan_result = intent_scanner.scan_structured_params(intent.structured_params)
    all_threats = scan_result["threats"] + params_scan_result["threats"]
    combined_risk = scan_result["risk_level"]
    if params_scan_result["risk_level"] == "high":
        combined_risk = "high"
    elif params_scan_result["risk_level"] == "medium" and combined_risk != "high":
        combined_risk = "medium"

    if combined_risk in ("high", "medium"):
        audit_log = AuditLog(
            user_id=current_user.username,
            action="malicious_intent_blocked",
            target_device="system",
            commands=[intent.user_input],
            status="blocked",
            security_type=combined_risk,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.commit()
        logger.warning(f"Malicious intent blocked for user {current_user.username}: {all_threats}")
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Intent rejected: malicious content detected",
                "risk_level": combined_risk,
                "threats": all_threats
            }
        )

    intent_name = intent.structured_params.get("intent_name", "")
    # Only validate semantic consistency when confidence is provided (from DeepSeek parsing)
    # Skip for direct API creation which may not have keyword matching
    if intent.structured_params.get("confidence") is not None:
        is_consistent, error_msg = validate_semantic_consistency(intent.user_input, intent_name)
        if not is_consistent:
            raise HTTPException(status_code=422, detail=[
                {"loc": ["structured_params", "intent_name"], "msg": error_msg, "type": "value_error.semantic_inconsistency"}
            ])

    # Pre-check for bandwidth/port conflicts with existing active intents
    conflict_warnings = await _check_resource_conflicts(db, intent.structured_params, intent.sla_conditions)

    try:
        new_intent = Intent(
            intent_name=intent.structured_params.get("intent_name", "unknown"),
            user_input=intent.user_input,
            structured_params=intent.structured_params,
            sla_conditions=intent.sla_conditions,
        )
        db.add(new_intent)
        await db.flush()
        
        audit_log = AuditLog(
            user_id=current_user.username,
            action="create_intent",
            target_device="system",
            commands=[intent.user_input],
            status="success",
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.commit()
        await db.refresh(new_intent)
        
        return {"status": "success", "data": {"id": new_intent.id}, "warnings": conflict_warnings if conflict_warnings else None}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Create intent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("")
async def get_intents(
    approval_status: str = None,
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user)
):
    # Column pruning: only select needed columns for list view (skip large JSON fields)
    list_columns = [
        Intent.id, Intent.intent_name, Intent.user_input,
        Intent.approval_status, Intent.execution_status,
        Intent.conflict_detected, Intent.sla_status,
        Intent.sla_conditions, Intent.created_at, Intent.updated_at
    ]
    query = select(*list_columns).order_by(Intent.created_at.desc())
    if approval_status:
        query = query.where(Intent.approval_status == approval_status)

    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    intents = result.fetchall()

    count_query = select(func.count(Intent.id))
    if approval_status:
        count_query = count_query.where(Intent.approval_status == approval_status)
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return {
        "status": "success",
        "data": [dict(row._mapping) for row in intents],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }


@router.get("/{intent_id}")
async def get_intent(intent_id: int, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user)):
    result = await db.execute(Intent.__table__.select().where(Intent.id == intent_id))
    intent = result.first()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")
    return {"status": "success", "data": dict(intent._mapping)}


@router.put("/{intent_id}")
async def update_intent(intent_id: int, update: IntentUpdate, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user), _fuse=Depends(check_fuse)):
    result = await db.execute(Intent.__table__.select().where(Intent.id == intent_id))
    intent = result.first()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    if update.approval_status == "approved" and intent.approval_status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot approve intent in '{intent.approval_status}' status")

    try:
        update_values: dict = {"approval_status": update.approval_status}

        if update.approval_status == "approved":
            intent_data = dict(intent._mapping)
            structured_params = intent_data.get("structured_params", {}) or {}
            parsed_intent = structured_params if isinstance(structured_params, dict) else {}

            network_state = await _build_network_state(db)

            intent_context = IntentContext(
                intent_id=str(intent_id),
                user_input=intent_data.get("user_input", ""),
                parsed_intent=parsed_intent,
                target_devices=parsed_intent.get("target_devices", []),
                actions=parsed_intent.get("actions", [])
            )

            conflict_result = _conflict_detector.detect(intent_context, network_state)
            update_values["conflict_detected"] = conflict_result.get("conflict", False)
            update_values["conflict_details"] = conflict_result.get("details")

            if conflict_result.get("conflict"):
                update_values["execution_status"] = "conflict_blocked"
            else:
                update_values["execution_status"] = "approved_pending_execution"

            audit_log = AuditLog(
                user_id=current_user.username,
                action="approve_intent_with_conflict_check",
                target_device=parsed_intent.get("device", "system"),
                commands=[f"Intent {intent_id} approved, conflict={conflict_result.get('conflict', False)}"],
                status="success",
                timestamp=datetime.now(timezone.utc)
            )
            db.add(audit_log)

        await db.execute(
            Intent.__table__.update()
            .where(Intent.id == intent_id)
            .values(**update_values)
        )
        await db.commit()

        response: dict = {"status": "success"}
        if update.approval_status == "approved" and "conflict_detected" in update_values:
            response["conflict_check"] = {
                "conflict_detected": update_values["conflict_detected"],
                "conflict_details": update_values.get("conflict_details"),
                "execution_status": update_values.get("execution_status")
            }
        return response
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Update intent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{intent_id}")
async def delete_intent(intent_id: int, db: AsyncSession = Depends(get_db_session), current_user=Depends(requires_permission("intents:delete")), _fuse=Depends(check_fuse)):
    result = await db.execute(Intent.__table__.select().where(Intent.id == intent_id))
    intent = result.first()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    try:
        # 从Row对象安全提取字段
        intent_mapping = intent._mapping if hasattr(intent, '_mapping') else {}
        target_device = intent_mapping.get("target_device", "system") or "system"
        user_input = intent_mapping.get("user_input", "")
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.username,
            action="delete_intent",
            target_device=target_device,
            commands=[f"Delete intent #{intent_id}: {user_input}"],
            status="success",
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.execute(Intent.__table__.delete().where(Intent.id == intent_id))
        await db.commit()
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Delete intent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{intent_id}/approve")
async def approve_intent(intent_id: int, db: AsyncSession = Depends(get_db_session), current_user=Depends(requires_permission("intents:approve")), _fuse=Depends(check_fuse)):
    result = await db.execute(Intent.__table__.select().where(Intent.id == intent_id))
    intent = result.first()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    intent_data = dict(intent._mapping)
    if intent_data.get("approval_status") == "approved":
        raise HTTPException(status_code=400, detail="Intent is already approved")

    try:
        await db.execute(
            Intent.__table__.update()
            .where(Intent.id == intent_id)
            .values(approval_status="approved")
        )
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.username,
            action="approve_intent",
            target_device=intent_data.get("structured_params", {}).get("device", "system"),
            commands=[f"Approve intent #{intent_id}: {intent_data.get('user_input', '')}"],
            status="success",
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.commit()
        # 发送通知
        try:
            await _notifier.notify_intent_status_change(
                intent_id=intent_id,
                old_status=intent_data.get("approval_status", "pending"),
                new_status="approved",
            )
        except Exception as e:
            logger.warning(f"Failed to send approval notification: {e}")
        return {"status": "success", "data": {"id": intent_id, "approval_status": "approved"}}
    except Exception as e:
        await db.rollback()
        logger.error(f"Approve intent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{intent_id}/reject")
async def reject_intent(intent_id: int, db: AsyncSession = Depends(get_db_session), current_user=Depends(requires_permission("intents:approve")), _fuse=Depends(check_fuse)):
    result = await db.execute(Intent.__table__.select().where(Intent.id == intent_id))
    intent = result.first()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    intent_data = dict(intent._mapping)
    if intent_data.get("approval_status") == "rejected":
        raise HTTPException(status_code=400, detail="Intent is already rejected")

    try:
        await db.execute(
            Intent.__table__.update()
            .where(Intent.id == intent_id)
            .values(approval_status="rejected")
        )
        # 记录审计日志
        audit_log = AuditLog(
            user_id=current_user.username,
            action="reject_intent",
            target_device=intent_data.get("structured_params", {}).get("device", "system"),
            commands=[f"Reject intent #{intent_id}: {intent_data.get('user_input', '')}"],
            status="success",
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.commit()
        # 发送通知
        try:
            await _notifier.notify_intent_status_change(
                intent_id=intent_id,
                old_status=intent_data.get("approval_status", "pending"),
                new_status="rejected",
            )
        except Exception as e:
            logger.warning(f"Failed to send rejection notification: {e}")
        return {"status": "success", "data": {"id": intent_id, "approval_status": "rejected"}}
    except Exception as e:
        await db.rollback()
        logger.error(f"Reject intent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{intent_id}/execute")
async def execute_intent(intent_id: int, db: AsyncSession = Depends(get_db_session), current_user=Depends(requires_permission("intents:execute")), _fuse=Depends(check_fuse)):
    result = await db.execute(Intent.__table__.select().where(Intent.id == intent_id))
    intent = result.first()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    intent_data = dict(intent._mapping)
    if intent_data.get("approval_status") != "approved":
        raise HTTPException(status_code=400, detail=f"Cannot execute intent in '{intent_data.get('approval_status')}' status, must be 'approved'")

    if intent_data.get("execution_status") == "conflict_blocked":
        raise HTTPException(status_code=409, detail="意图存在冲突，请先解决冲突")

    structured_params = intent_data.get("structured_params", {}) or {}
    intent_name = structured_params.get("intent_name", "")

    tool_mapping = {
        "bandwidth_guarantee": "config_qos",
        "qos_policy": "config_qos",
        "traffic_shaping": "config_qos",
        "access_control": "config_acl",
        "fault_diagnosis": "show_interface",
        "performance_monitoring": "get_device_status",
        "link_management": "show_interface",
        "device_config": "show_interface",
        "git_clone_bandwidth_guarantee": "config_qos",
    }

    tool_name = tool_mapping.get(intent_name)
    if not tool_name:
        raise HTTPException(status_code=400, detail=f"意图类型 '{intent_name}' 没有对应的工具映射")

    executor = get_tool_executor()
    tool_params = {}
    if "device" in structured_params:
        tool_params["device"] = structured_params["device"]
    if "target" in structured_params:
        tool_params["target"] = structured_params["target"]
    if "bandwidth_percent" in structured_params:
        tool_params["bandwidth_percent"] = structured_params["bandwidth_percent"]
    if "class_name" in structured_params:
        tool_params["class_name"] = structured_params["class_name"]
    if "acl_name" in structured_params:
        tool_params["acl_name"] = structured_params["acl_name"]
    if "action" in structured_params:
        tool_params["action"] = structured_params["action"]
    if "protocol" in structured_params:
        tool_params["protocol"] = structured_params["protocol"]
    if "source" in structured_params:
        tool_params["source"] = structured_params["source"]
    if "destination" in structured_params:
        tool_params["destination"] = structured_params["destination"]
    if "interface" in structured_params:
        tool_params["interface"] = structured_params["interface"]

    execution_result = await executor.execute_tool(tool_name, tool_params)

    try:
        await db.execute(
            Intent.__table__.update()
            .where(Intent.id == intent_id)
            .values(
                execution_status="executed" if execution_result.get("status") == "success" else "execution_failed",
                execution_result=execution_result
            )
        )
        audit_log = AuditLog(
            user_id=current_user.username,
            action="execute_intent",
            target_device=structured_params.get("device", "system"),
            commands=[f"Intent {intent_id}: tool={tool_name}, params={tool_params}"],
            status=execution_result.get("status", "unknown"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.commit()
        # 发送通知
        try:
            new_status = "executed" if execution_result.get("status") == "success" else "execution_failed"
            await _notifier.notify_intent_status_change(
                intent_id=intent_id,
                old_status=intent_data.get("execution_status", "pending"),
                new_status=new_status,
            )
        except Exception as e:
            logger.warning(f"Failed to send execution notification: {e}")
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Execute intent audit log failed: {e}", exc_info=True)

    return {
        "status": "success",
        "data": {
            "intent_id": intent_id,
            "tool_name": tool_name,
            "execution_result": execution_result
        }
    }


@router.post("/{intent_id}/conflict-check")
async def check_intent_conflicts(intent_id: int, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user)):
    result = await db.execute(Intent.__table__.select().where(Intent.id == intent_id))
    intent = result.first()
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    intent_data = dict(intent._mapping)
    structured_params = intent_data.get("structured_params", {}) or {}

    intent_context = IntentContext(
        intent_id=str(intent_id),
        user_input=intent_data.get("user_input", ""),
        parsed_intent=structured_params,
        target_devices=structured_params.get("target_devices", []),
        actions=structured_params.get("actions", [])
    )

    network_state = await _build_network_state(db)
    conflict_result = _conflict_detector.detect(intent_context, network_state)

    return {"status": "success", "data": conflict_result}


@router.post("/test/create")
async def create_test_intent(
    intent_name: str = None,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user)
):
    """创建测试意图的便捷接口"""
    if settings.environment != "development":
        raise HTTPException(status_code=404, detail="Not found in production")
    import random
    
    intent_names = [
        "restart_device", "isolate_node", "unisolate_node", 
        "update_config", "check_status", "backup_data",
        "restore_backup", "clear_cache", "refresh_connection"
    ]
    
    selected_name = intent_name or random.choice(intent_names)
    
    try:
        new_intent = Intent(
            intent_name=selected_name,
            user_input=f"测试意图: {selected_name}",
            structured_params={"intent_name": selected_name}
        )
        db.add(new_intent)
        await db.flush()
        
        audit_log = AuditLog(
            user_id=current_user.username,
            action="create_test_intent",
            target_device="system",
            commands=[f"测试 {selected_name}"],
            status="success",
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        await db.commit()
        await db.refresh(new_intent)
        
        return {"status": "success", "data": {"id": new_intent.id, "name": selected_name}}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Create test intent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")