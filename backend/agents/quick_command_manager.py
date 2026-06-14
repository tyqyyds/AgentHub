from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import async_session_maker
from backend.database.models import QuickCommand
import uuid
import re
import logging

logger = logging.getLogger(__name__)


def _generate_command_id() -> str:
    return f"qc_{uuid.uuid4().hex[:4]}"


def _command_to_dict(c: QuickCommand) -> dict:
    return {
        "id": c.id,
        "command_id": c.command_id,
        "name": c.name,
        "shortcut": c.shortcut,
        "template": c.template,
        "parameters": c.parameters or [],
        "category": c.category,
        "is_public": c.is_public,
        "created_by": c.created_by,
        "usage_count": c.usage_count,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


BUILT_IN_COMMANDS = [
    {
        "name": "带宽保障",
        "shortcut": "/bw",
        "template": "保障{bandwidth}M带宽给{application}",
        "parameters": [
            {"name": "bandwidth", "type": "number", "description": "带宽大小(M)", "required": True},
            {"name": "application", "type": "string", "description": "应用名称", "required": True},
        ],
        "category": "network",
    },
    {
        "name": "访问控制",
        "shortcut": "/acl",
        "template": "{action}访问控制从{source}到{dest}",
        "parameters": [
            {"name": "action", "type": "string", "description": "动作(允许/拒绝)", "required": True},
            {"name": "source", "type": "string", "description": "源地址", "required": True},
            {"name": "dest", "type": "string", "description": "目的地址", "required": True},
        ],
        "category": "security",
    },
    {
        "name": "故障诊断",
        "shortcut": "/diag",
        "template": "诊断{device}故障",
        "parameters": [
            {"name": "device", "type": "string", "description": "设备名称", "required": True},
        ],
        "category": "diagnosis",
    },
    {
        "name": "QoS配置",
        "shortcut": "/qos",
        "template": "配置QoS优先级{priority}给{device}",
        "parameters": [
            {"name": "priority", "type": "string", "description": "优先级(高/中/低)", "required": True},
            {"name": "device", "type": "string", "description": "设备名称", "required": True},
        ],
        "category": "network",
    },
]


class QuickCommandManager:
    async def create_command(
        self,
        name: str,
        shortcut: str,
        template: str,
        parameters: list,
        created_by: str,
        **kwargs,
    ) -> QuickCommand:
        command_id = _generate_command_id()
        async with async_session_maker() as session:
            command = QuickCommand(
                command_id=command_id,
                name=name,
                shortcut=shortcut,
                template=template,
                parameters=parameters,
                category=kwargs.get("category", "custom"),
                is_public=kwargs.get("is_public", False),
                created_by=created_by,
            )
            session.add(command)
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
            await session.refresh(command)
            logger.info(f"Created quick command {command_id}: {shortcut}")
            return command

    async def execute_command(
        self,
        shortcut: str,
        parameter_values: list,
        created_by: str,
    ) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(QuickCommand).where(QuickCommand.shortcut == shortcut)
            )
            command = result.scalar_one_or_none()
            if not command:
                built_in = None
                for bic in BUILT_IN_COMMANDS:
                    if bic["shortcut"] == shortcut:
                        built_in = bic
                        break
                if not built_in:
                    return {"error": f"快捷指令不存在: {shortcut}"}
                template = built_in["template"]
                params = built_in["parameters"]
            else:
                template = command.template
                params = command.parameters or []
                command.usage_count = (command.usage_count or 0) + 1
                await session.commit()

            placeholders = re.findall(r"\{(\w+)\}", template)
            filled_template = template
            missing = []

            for i, ph in enumerate(placeholders):
                if i < len(parameter_values):
                    filled_template = filled_template.replace(f"{{{ph}}}", str(parameter_values[i]), 1)
                else:
                    missing.append(ph)

            if missing:
                return {
                    "error": f"缺少必要参数: {', '.join(missing)}",
                    "missing_parameters": missing,
                    "template": template,
                    "parameters": params,
                }

            return {
                "shortcut": shortcut,
                "filled_template": filled_template,
                "parameter_values": parameter_values,
                "executed_by": created_by,
            }

    async def list_commands(
        self,
        created_by: Optional[str] = None,
        is_public: Optional[bool] = None,
        category: Optional[str] = None,
    ) -> List[dict]:
        async with async_session_maker() as session:
            query = select(QuickCommand)
            conditions = []
            if created_by is not None:
                conditions.append(
                    or_(
                        QuickCommand.created_by == created_by,
                        QuickCommand.is_public == True,
                    )
                )
            if is_public is not None:
                conditions.append(QuickCommand.is_public == is_public)
            if category is not None:
                conditions.append(QuickCommand.category == category)
            if conditions:
                query = query.where(*conditions)
            query = query.order_by(QuickCommand.usage_count.desc(), QuickCommand.created_at.desc())
            result = await session.execute(query)
            commands = result.scalars().all()
            return [_command_to_dict(c) for c in commands]

    async def get_command(self, command_id: str) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(QuickCommand).where(QuickCommand.command_id == command_id)
            )
            command = result.scalar_one_or_none()
            if not command:
                return None
            return _command_to_dict(command)

    async def delete_command(self, command_id: str) -> bool:
        async with async_session_maker() as session:
            result = await session.execute(
                select(QuickCommand).where(QuickCommand.command_id == command_id)
            )
            command = result.scalar_one_or_none()
            if not command:
                return False
            await session.delete(command)
            await session.commit()
            logger.info(f"Deleted quick command {command_id}")
            return True

    def parse_shortcut(self, input_text: str) -> dict:
        match = re.match(r"^(/\w+)\s*(.*)", input_text.strip())
        if not match:
            return {"is_shortcut": False, "shortcut": None, "params": []}
        shortcut = match.group(1)
        params_str = match.group(2).strip()
        params = [p for p in re.split(r"\s+", params_str) if p] if params_str else []
        return {"is_shortcut": True, "shortcut": shortcut, "params": params}

    def get_built_in_commands(self) -> List[dict]:
        return BUILT_IN_COMMANDS.copy()


_quick_command_manager: Optional[QuickCommandManager] = None


def get_quick_command_manager() -> QuickCommandManager:
    global _quick_command_manager
    if _quick_command_manager is None:
        _quick_command_manager = QuickCommandManager()
    return _quick_command_manager
