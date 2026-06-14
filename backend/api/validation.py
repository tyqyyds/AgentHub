from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from backend.database.connection import get_db_session
from backend.database.models import Device
from backend.core.security.rbac import get_current_user
import re
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

DANGEROUS_COMMANDS = [
    r'^undo\s+shutdown',
    r'^delete\s+config',
    r'^erase\s+startup-config',
    r'^reload\s+force',
    r'^access-list\s+\d+\s+deny\s+ip\s+any\s+any',
    r'^no\s+ip\s+route',
    r'^no\s+interface',
    r'^shutdown\s+interface',
    r'^clear\s+ip\s+route\s+.*',
    r'^write\s+erase',
    r'^format\s+\S+',
    r'^system-view\s+reset'
]

VENDOR_SYNTAX = {
    "huawei": {"prefix": "system-view", "save": "save", "rollback_prefix": "undo"},
    "cisco": {"prefix": "configure terminal", "save": "write memory", "rollback_prefix": "no"},
    "h3c": {"prefix": "system-view", "save": "save", "rollback_prefix": "undo"},
}


class ValidationRequest(BaseModel):
    intent_id: int
    commands: list[str]
    target_device: str
    device_type: str = 'router'


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    dry_run_result: Optional[str] = None
    whatif_analysis: Optional[dict] = None
    requires_approval: bool = False
    rollback_commands: list[str] = []
    dangerous_commands: list[str] = []


def validate_commands_syntax(commands: list[str]) -> tuple[bool, list[str]]:
    errors = []
    for cmd in commands:
        cmd = cmd.strip()
        if not cmd:
            errors.append("空命令不允许")
            continue
        if len(cmd) > 1024:
            errors.append(f"命令过长: {cmd[:50]}...")
            continue
        if cmd.count('"') % 2 != 0 or cmd.count("'") % 2 != 0:
            errors.append(f"引号不匹配: {cmd}")
    return len(errors) == 0, errors


def detect_dangerous_commands(commands: list[str]) -> tuple[bool, list[str]]:
    dangerous = []
    for cmd in commands:
        for pattern in DANGEROUS_COMMANDS:
            if re.match(pattern, cmd, re.IGNORECASE):
                dangerous.append(cmd)
                break
    return len(dangerous) == 0, dangerous


def generate_rollback_commands(commands: list[str], vendor: str = "huawei") -> list[str]:
    rollback = []
    prefix = VENDOR_SYNTAX.get(vendor, VENDOR_SYNTAX["huawei"])["rollback_prefix"]

    for cmd in commands:
        cmd = cmd.strip()
        if cmd.startswith(f'{prefix} '):
            rollback.append(cmd[len(prefix) + 1:])
        elif cmd.startswith('interface '):
            rollback.append(f'{prefix} {cmd}')
        elif cmd.startswith('ip route '):
            rollback.append(f'{prefix} {cmd}')
        elif cmd.startswith('access-list '):
            parts = cmd.split()
            if len(parts) >= 2:
                rollback.append(f'{prefix} {parts[0]} {parts[1]}')
        elif cmd.startswith('policy-map '):
            parts = cmd.split()
            if len(parts) >= 2:
                rollback.append(f'{prefix} {parts[0]} {parts[1]}')
        elif cmd.startswith('class-map '):
            parts = cmd.split()
            if len(parts) >= 2:
                rollback.append(f'{prefix} {parts[0]} {parts[1]}')
        elif 'shutdown' in cmd.lower():
            rollback.append(cmd.replace('shutdown', f'{prefix} shutdown'))
        elif cmd.startswith('traffic-policy '):
            parts = cmd.split()
            if len(parts) >= 2:
                rollback.append(f'{prefix} {parts[0]} {parts[1]}')
        elif cmd.startswith('qos car '):
            rollback.append(f'{prefix} {cmd}')
        elif cmd.startswith('bandwidth '):
            rollback.append(f'{prefix} {cmd}')
        elif cmd.startswith('car '):
            parts = cmd.split()
            if len(parts) >= 2:
                rollback.append(f'{prefix} {parts[0]} {parts[1]}')

        if rollback and rollback[-1] == cmd:
            rollback.pop()

    return rollback


def simulate_whatif_analysis(commands: list[str], device_type: str,
                              device_info: dict = None) -> dict:
    conflicts = []
    affected_configs = []
    affected_interfaces = []
    affected_routes = []

    for cmd in commands:
        cmd_lower = cmd.lower()

        if 'access-list' in cmd_lower or 'acl' in cmd_lower:
            if 'deny' in cmd_lower and 'any any' in cmd_lower:
                conflicts.append({
                    'severity': 'high',
                    'message': '潜在危险：ACL规则可能阻断所有流量',
                    'command': cmd,
                    'recommendation': '建议使用更精确的源/目标地址范围'
                })
            affected_configs.append('ACL配置')

        if 'route' in cmd_lower or 'ospf' in cmd_lower or 'bgp' in cmd_lower:
            affected_configs.append('路由配置')
            route_match = re.search(r'ip\s+route\s+(\S+)\s+(\S+)\s+(\S+)', cmd_lower)
            if route_match:
                affected_routes.append({
                    'network': route_match.group(1),
                    'mask': route_match.group(2),
                    'next_hop': route_match.group(3)
                })

        if 'interface' in cmd_lower:
            affected_configs.append('接口配置')
            intf_match = re.search(r'interface\s+(\S+)', cmd, re.IGNORECASE)
            if intf_match:
                affected_interfaces.append(intf_match.group(1))

        if 'qos' in cmd_lower or 'policy-map' in cmd_lower or 'traffic-policy' in cmd_lower:
            affected_configs.append('QoS策略')

        if 'bandwidth' in cmd_lower or 'car' in cmd_lower:
            affected_configs.append('带宽策略')

        if 'vlan' in cmd_lower:
            affected_configs.append('VLAN配置')

    if device_info:
        cpu = device_info.get('cpu_usage', 0)
        memory = device_info.get('memory_usage', 0)
        if cpu > 80:
            warnings_item = {
                'severity': 'medium',
                'message': f"设备CPU使用率过高 ({cpu:.1f}%)，建议在低峰期执行",
                'command': 'system',
                'recommendation': '建议等待CPU使用率降至70%以下再执行'
            }
            conflicts.append(warnings_item)
        if memory > 80:
            conflicts.append({
                'severity': 'medium',
                'message': f"设备内存使用率过高 ({memory:.1f}%)，变更可能导致设备不稳定",
                'command': 'system',
                'recommendation': '建议等待内存使用率降至70%以下再执行'
            })

    impact_level = 'high' if any(c['severity'] == 'high' for c in conflicts) else \
                   'medium' if conflicts else 'low'

    return {
        'conflicts': conflicts,
        'affected_configs': list(set(affected_configs)),
        'affected_interfaces': affected_interfaces,
        'affected_routes': affected_routes,
        'impact_level': impact_level,
        'estimated_downtime': '0s' if impact_level == 'low' else
                              '<30s' if impact_level == 'medium' else '30s-5min',
        'recommendation': '可以安全执行' if impact_level == 'low' else
                          '建议在维护窗口执行' if impact_level == 'medium' else
                          '强烈建议人工审核后再执行'
    }


async def dry_run_commands(commands: list[str], device_type: str,
                            target_device: str, db: AsyncSession) -> dict:
    result = []
    result.append("=== Dry Run 模拟执行 ===")
    result.append(f"目标设备: {target_device}")
    result.append(f"设备类型: {device_type}")
    result.append(f"命令数量: {len(commands)}")
    result.append("")

    device_info = None
    try:
        db_result = await db.execute(select(Device).where(Device.device_id == target_device))
        device = db_result.scalars().first()
        if device:
            device_info = {
                'name': device.name,
                'vendor': device.vendor,
                'ip': device.ip_address,
                'status': device.status,
                'cpu_usage': device.cpu_usage,
                'memory_usage': device.memory_usage
            }
            result.append(f"设备信息: {device.name} ({device.ip_address}) [{device.vendor}]")
            result.append(f"设备状态: {device.status}")
            result.append(f"CPU: {device.cpu_usage:.1f}% | 内存: {device.memory_usage:.1f}%")
            result.append("")
    except Exception as e:
        logger.warning(f"Validation check failed: {e}")

    result.append("执行模拟:")
    syntax_errors = []
    for i, cmd in enumerate(commands, 1):
        result.append(f"  {i}. {cmd}")
        cmd_stripped = cmd.strip()
        if not cmd_stripped:
            result.append(f"     ✗ 空命令")
            syntax_errors.append(f"命令{i}: 空命令")
        elif len(cmd_stripped) > 1024:
            result.append(f"     ✗ 命令过长")
            syntax_errors.append(f"命令{i}: 命令过长")
        else:
            result.append(f"     ✓ 语法检查通过")

    result.append("")
    result.append("=== 模拟结果 ===")
    if syntax_errors:
        result.append(f"发现 {len(syntax_errors)} 个语法错误")
        for err in syntax_errors:
            result.append(f"  - {err}")
    else:
        result.append("所有命令语法验证通过")
        result.append("建议继续执行实际配置")

    rollback = generate_rollback_commands(commands,
                                           device_info.get('vendor', 'huawei') if device_info else 'huawei')
    result.append("")
    result.append("=== 回滚方案 ===")
    if rollback:
        result.append(f"已生成 {len(rollback)} 条回滚命令")
        for i, cmd in enumerate(rollback, 1):
            result.append(f"  {i}. {cmd}")
    else:
        result.append("警告：无法自动生成回滚命令，请手动准备回滚方案")

    return {
        "output": "\n".join(result),
        "syntax_errors": syntax_errors,
        "device_info": device_info,
        "rollback_available": len(rollback) > 0
    }


@router.post("/validate", response_model=ValidationResult)
async def validate_intent(request: ValidationRequest, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user)):
    errors = []
    warnings = []
    requires_approval = False
    dangerous_commands = []

    syntax_valid, syntax_errors = validate_commands_syntax(request.commands)
    if not syntax_valid:
        errors.extend(syntax_errors)

    safe, dangerous_cmds = detect_dangerous_commands(request.commands)
    if dangerous_cmds:
        dangerous_commands = dangerous_cmds
        errors.extend([f"检测到危险命令: {cmd}" for cmd in dangerous_cmds])
        requires_approval = True

    device_info = None
    try:
        db_result = await db.execute(select(Device).where(Device.device_id == request.target_device))
        device = db_result.scalars().first()
        if device:
            device_info = {
                'cpu_usage': device.cpu_usage,
                'memory_usage': device.memory_usage,
                'status': device.status,
                'vendor': device.vendor
            }
    except Exception as e:
        logger.warning(f"Validation check failed: {e}")

    whatif_result = simulate_whatif_analysis(request.commands, request.device_type, device_info)
    if whatif_result['conflicts']:
        for conflict in whatif_result['conflicts']:
            if conflict['severity'] == 'high':
                errors.append(conflict['message'])
            else:
                warnings.append(conflict['message'])

    dry_run = await dry_run_commands(request.commands, request.device_type, request.target_device, db)

    vendor = device_info.get('vendor', 'huawei') if device_info else 'huawei'
    rollback_cmds = generate_rollback_commands(request.commands, vendor)

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        dry_run_result=dry_run["output"],
        whatif_analysis=whatif_result,
        requires_approval=requires_approval,
        rollback_commands=rollback_cmds,
        dangerous_commands=dangerous_commands
    )


@router.post("/dry-run")
async def execute_dry_run(request: ValidationRequest, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user)):
    dry_run = await dry_run_commands(request.commands, request.device_type, request.target_device, db)
    return {
        "status": "success",
        "data": {
            "dry_run_result": dry_run["output"],
            "syntax_errors": dry_run["syntax_errors"],
            "device_info": dry_run["device_info"],
            "rollback_available": dry_run["rollback_available"],
            "command_count": len(request.commands)
        }
    }


@router.post("/whatif")
async def analyze_whatif(request: ValidationRequest, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user)):
    device_info = None
    try:
        db_result = await db.execute(select(Device).where(Device.device_id == request.target_device))
        device = db_result.scalars().first()
        if device:
            device_info = {
                'cpu_usage': device.cpu_usage,
                'memory_usage': device.memory_usage,
                'status': device.status,
                'vendor': device.vendor
            }
    except Exception as e:
        logger.warning(f"Validation check failed: {e}")

    analysis = simulate_whatif_analysis(request.commands, request.device_type, device_info)
    return {
        "status": "success",
        "data": analysis
    }


@router.post("/generate-rollback")
async def generate_rollback(request: ValidationRequest, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user)):
    vendor = "huawei"
    try:
        db_result = await db.execute(select(Device).where(Device.device_id == request.target_device))
        device = db_result.scalars().first()
        if device:
            vendor = device.vendor
    except Exception as e:
        logger.warning(f"Validation check failed: {e}")

    rollback_cmds = generate_rollback_commands(request.commands, vendor)
    return {
        "status": "success",
        "data": {
            "rollback_commands": rollback_cmds,
            "original_count": len(request.commands),
            "rollback_count": len(rollback_cmds),
            "vendor": vendor
        }
    }
