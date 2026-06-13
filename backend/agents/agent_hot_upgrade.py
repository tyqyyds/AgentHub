import logging
import importlib
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum as PyEnum

from ..core.config import settings
from ..database.models import AgentHealthStatus

logger = logging.getLogger(__name__)


class UpgradeStatus(PyEnum):
    """升级状态"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    VALIDATING = "validating"
    STAGING = "staging"
    SWITCHING = "switching"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class UpgradeStrategy(PyEnum):
    """升级策略"""
    IMMEDIATE = "immediate"
    GRACEFUL = "graceful"
    BLUE_GREEN = "blue_green"


@dataclass
class AgentVersion:
    """Agent版本信息"""
    agent_id: str = ""
    current_version: str = "0.0.0"
    target_version: str = ""
    module_path: str = ""
    class_name: str = ""


@dataclass
class UpgradeRecord:
    """升级记录"""
    agent_id: str = ""
    from_version: str = ""
    to_version: str = ""
    status: UpgradeStatus = UpgradeStatus.PENDING
    strategy: UpgradeStrategy = UpgradeStrategy.GRACEFUL
    started_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    health_check_passed: bool = False


@dataclass
class AgentHotUpgradeConfig:
    """Agent热升级配置"""
    max_concurrent_upgrades: int = 3
    health_check_timeout_seconds: int = 30
    health_check_retries: int = 3
    rollback_on_failure: bool = True
    graceful_drain_timeout_seconds: int = 60
    default_strategy: UpgradeStrategy = UpgradeStrategy.GRACEFUL
    version_validation_enabled: bool = True


class AgentHotUpgrade:
    """Agent热升级：运行时Agent版本更新

    支持三种升级策略：
    - immediate: 立即替换，中断当前任务
    - graceful: 优雅替换，等待当前任务完成后切换
    - blue_green: 蓝绿部署，新旧版本并行验证后切换
    """

    def __init__(self, config: Optional[AgentHotUpgradeConfig] = None):
        self.config = config or AgentHotUpgradeConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._agent_instances: Dict[str, Any] = {}
        self._agent_versions: Dict[str, AgentVersion] = {}
        self._upgrade_history: List[UpgradeRecord] = []
        self._locked_agents: set = set()

    def register_agent(
        self,
        agent_id: str,
        instance: Any,
        module_path: str = "",
        class_name: str = "",
        version: str = "0.0.0",
    ) -> None:
        """注册Agent实例"""
        self._agent_instances[agent_id] = instance
        self._agent_versions[agent_id] = AgentVersion(
            agent_id=agent_id,
            current_version=version,
            module_path=module_path,
            class_name=class_name or instance.__class__.__name__,
        )
        self.logger.info(f"Agent {agent_id} v{version} 已注册")

    def _validate_version(self, from_ver: str, to_ver: str) -> bool:
        """验证版本兼容性"""
        if not self.config.version_validation_enabled:
            return True

        try:
            from_parts = [int(p) for p in from_ver.split(".")]
            to_parts = [int(p) for p in to_ver.split(".")]

            if len(from_parts) < 3 or len(to_parts) < 3:
                self.logger.warning(f"版本号格式异常: {from_ver} → {to_ver}")
                return True

            major_diff = to_parts[0] - from_parts[0]
            if major_diff > 1:
                self.logger.error(
                    f"主版本跨度过大: {from_ver} → {to_ver}，建议逐步升级"
                )
                return False
            return True
        except (ValueError, IndexError):
            self.logger.warning(f"版本号解析失败，跳过验证: {from_ver} → {to_ver}")
            return True

    async def _health_check_agent(self, agent_id: str) -> bool:
        """对新版本Agent执行健康检查"""
        instance = self._agent_instances.get(agent_id)
        if not instance or not hasattr(instance, "health_check"):
            return False

        for attempt in range(self.config.health_check_retries):
            try:
                result = await instance.health_check()
                status = result.get("status", "unhealthy")
                if status in ("healthy", "ok"):
                    return True
                self.logger.warning(
                    f"Agent {agent_id} 健康检查未通过 "
                    f"(尝试 {attempt + 1}/{self.config.health_check_retries}): "
                    f"status={status}"
                )
            except Exception as e:
                self.logger.error(
                    f"Agent {agent_id} 健康检查异常 "
                    f"(尝试 {attempt + 1}/{self.config.health_check_retries}): {e}"
                )
        return False

    def _create_upgrade_record(
        self,
        agent_id: str,
        from_version: str,
        to_version: str,
        strategy: UpgradeStrategy,
    ) -> UpgradeRecord:
        """创建升级记录"""
        record = UpgradeRecord(
            agent_id=agent_id,
            from_version=from_version,
            to_version=to_version,
            status=UpgradeStatus.PENDING,
            strategy=strategy,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._upgrade_history.append(record)
        return record

    async def _load_new_version(
        self, module_path: str, class_name: str
    ) -> Optional[Any]:
        """加载新版本Agent模块"""
        try:
            if module_path:
                module = importlib.import_module(module_path)
                importlib.reload(module)
                cls = getattr(module, class_name, None)
                if cls:
                    return cls()
            return None
        except Exception as e:
            self.logger.error(f"加载新版本模块失败: {module_path}.{class_name}: {e}")
            return None

    async def _upgrade_immediate(
        self, agent_id: str, new_instance: Any, record: UpgradeRecord
    ) -> UpgradeRecord:
        """立即升级策略"""
        old_instance = self._agent_instances.get(agent_id)

        record.status = UpgradeStatus.SWITCHING
        self._agent_instances[agent_id] = new_instance

        health_ok = await self._health_check_agent(agent_id)
        if health_ok:
            record.status = UpgradeStatus.COMPLETED
            record.health_check_passed = True
            self.logger.info(f"Agent {agent_id} 立即升级成功")
        else:
            record.status = UpgradeStatus.FAILED
            record.error = "健康检查未通过"
            if self.config.rollback_on_failure and old_instance:
                self._agent_instances[agent_id] = old_instance
                record.status = UpgradeStatus.ROLLED_BACK
                self.logger.warning(f"Agent {agent_id} 升级失败，已回滚")

        record.completed_at = datetime.now(timezone.utc).isoformat()
        return record

    async def _upgrade_graceful(
        self, agent_id: str, new_instance: Any, record: UpgradeRecord
    ) -> UpgradeRecord:
        """优雅升级策略"""
        old_instance = self._agent_instances.get(agent_id)

        record.status = UpgradeStatus.STAGING
        staging_id = f"{agent_id}_staging"
        self._agent_instances[staging_id] = new_instance

        health_ok = await self._health_check_agent(staging_id)
        if not health_ok:
            record.status = UpgradeStatus.FAILED
            record.error = "新版本健康检查未通过"
            del self._agent_instances[staging_id]
            record.completed_at = datetime.now(timezone.utc).isoformat()
            return record

        record.status = UpgradeStatus.SWITCHING
        self._agent_instances[agent_id] = new_instance
        del self._agent_instances[staging_id]

        final_health = await self._health_check_agent(agent_id)
        if final_health:
            record.status = UpgradeStatus.COMPLETED
            record.health_check_passed = True
            self.logger.info(f"Agent {agent_id} 优雅升级成功")
        else:
            record.status = UpgradeStatus.FAILED
            record.error = "切换后健康检查未通过"
            if self.config.rollback_on_failure and old_instance:
                self._agent_instances[agent_id] = old_instance
                record.status = UpgradeStatus.ROLLED_BACK

        record.completed_at = datetime.now(timezone.utc).isoformat()
        return record

    async def _upgrade_blue_green(
        self, agent_id: str, new_instance: Any, record: UpgradeRecord
    ) -> UpgradeRecord:
        """蓝绿升级策略"""
        old_instance = self._agent_instances.get(agent_id)

        blue_id = f"{agent_id}_blue"
        green_id = f"{agent_id}_green"

        record.status = UpgradeStatus.STAGING
        self._agent_instances[blue_id] = old_instance
        self._agent_instances[green_id] = new_instance

        green_health = await self._health_check_agent(green_id)
        if not green_health:
            record.status = UpgradeStatus.FAILED
            record.error = "绿版本健康检查未通过"
            del self._agent_instances[blue_id]
            del self._agent_instances[green_id]
            record.completed_at = datetime.now(timezone.utc).isoformat()
            return record

        record.status = UpgradeStatus.SWITCHING
        self._agent_instances[agent_id] = new_instance
        del self._agent_instances[blue_id]
        del self._agent_instances[green_id]

        final_health = await self._health_check_agent(agent_id)
        if final_health:
            record.status = UpgradeStatus.COMPLETED
            record.health_check_passed = True
            self.logger.info(f"Agent {agent_id} 蓝绿升级成功")
        else:
            record.status = UpgradeStatus.FAILED
            record.error = "切换后健康检查未通过"
            if self.config.rollback_on_failure and old_instance:
                self._agent_instances[agent_id] = old_instance
                record.status = UpgradeStatus.ROLLED_BACK

        record.completed_at = datetime.now(timezone.utc).isoformat()
        return record

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行Agent热升级

        输入:
            agent_id: 目标Agent ID
            target_version: 目标版本号
            module_path: 新版本模块路径（可选）
            class_name: 新版本类名（可选）
            new_instance: 新实例（内部使用，可选）
            strategy: 升级策略 immediate/graceful/blue_green
        """
        agent_id = input_data.get("agent_id", "")
        target_version = input_data.get("target_version", "")
        strategy_name = input_data.get("strategy", self.config.default_strategy.value)

        if not agent_id:
            return {"status": "failed", "error": "缺少agent_id"}

        if agent_id in self._locked_agents:
            return {"status": "failed", "error": f"Agent {agent_id} 正在升级中"}

        version_info = self._agent_versions.get(agent_id)
        if not version_info:
            return {"status": "failed", "error": f"Agent {agent_id} 未注册"}

        current_version = version_info.current_version
        if not target_version:
            return {"status": "failed", "error": "缺少target_version"}

        if current_version == target_version:
            return {
                "status": "skipped",
                "reason": "目标版本与当前版本相同",
                "current_version": current_version,
            }

        if not self._validate_version(current_version, target_version):
            return {
                "status": "failed",
                "error": f"版本兼容性验证失败: {current_version} → {target_version}",
            }

        try:
            strategy = UpgradeStrategy(strategy_name)
        except ValueError:
            strategy = self.config.default_strategy

        self._locked_agents.add(agent_id)
        record = self._create_upgrade_record(
            agent_id, current_version, target_version, strategy
        )

        try:
            module_path = input_data.get("module_path", version_info.module_path)
            class_name = input_data.get("class_name", version_info.class_name)
            new_instance = input_data.get("new_instance")

            if not new_instance and module_path and class_name:
                record.status = UpgradeStatus.DOWNLOADING
                new_instance = await self._load_new_version(module_path, class_name)

            if not new_instance:
                record.status = UpgradeStatus.FAILED
                record.error = "无法加载新版本Agent实例"
                record.completed_at = datetime.now(timezone.utc).isoformat()
                return {
                    "status": "failed",
                    "error": "无法加载新版本Agent实例",
                    "agent_id": agent_id,
                }

            record.status = UpgradeStatus.VALIDATING

            if strategy == UpgradeStrategy.IMMEDIATE:
                record = await self._upgrade_immediate(agent_id, new_instance, record)
            elif strategy == UpgradeStrategy.GRACEFUL:
                record = await self._upgrade_graceful(agent_id, new_instance, record)
            elif strategy == UpgradeStrategy.BLUE_GREEN:
                record = await self._upgrade_blue_green(agent_id, new_instance, record)

            if record.status in (UpgradeStatus.COMPLETED, UpgradeStatus.ROLLED_BACK):
                if record.status == UpgradeStatus.COMPLETED:
                    version_info.current_version = target_version
                    version_info.target_version = target_version

            return {
                "status": record.status.value,
                "agent_id": agent_id,
                "from_version": current_version,
                "to_version": target_version if record.health_check_passed else current_version,
                "strategy": strategy.value,
                "health_check_passed": record.health_check_passed,
                "error": record.error,
                "started_at": record.started_at,
                "completed_at": record.completed_at,
            }

        except Exception as e:
            self.logger.error(f"Agent {agent_id} 热升级异常: {e}")
            record.status = UpgradeStatus.FAILED
            record.error = str(e)
            record.completed_at = datetime.now(timezone.utc).isoformat()
            return {
                "status": "failed",
                "agent_id": agent_id,
                "error": str(e),
            }
        finally:
            self._locked_agents.discard(agent_id)

    def get_upgrade_history(
        self, agent_id: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """获取升级历史"""
        records = self._upgrade_history
        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]
        return [
            {
                "agent_id": r.agent_id,
                "from_version": r.from_version,
                "to_version": r.to_version,
                "status": r.status.value,
                "strategy": r.strategy.value,
                "health_check_passed": r.health_check_passed,
                "error": r.error,
                "started_at": r.started_at,
                "completed_at": r.completed_at,
            }
            for r in records[-limit:]
        ]

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "status": "healthy",
            "agent": self.__class__.__name__,
            "registered_agents": len(self._agent_versions),
            "active_instances": len(self._agent_instances),
            "locked_agents": list(self._locked_agents),
            "upgrade_history_count": len(self._upgrade_history),
            "config": {
                "max_concurrent_upgrades": self.config.max_concurrent_upgrades,
                "default_strategy": self.config.default_strategy.value,
                "rollback_on_failure": self.config.rollback_on_failure,
            },
        }
