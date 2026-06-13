"""意图调度器：定时/周期意图执行调度

基于 IntentScheduleRecord 模型，支持 ONCE/DAILY/WEEKLY/MONTHLY 四种调度模式。
负责意图的定时触发、周期执行、调度状态管理和过期清理。
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import asyncio

from ..core.config import settings
from ..database.models import RecurrenceType

logger = logging.getLogger(__name__)


# ──────────────────────── 内部枚举与数据类 ────────────────────────


class ScheduleStatus(str, Enum):
    """调度状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class SchedulePriority(int, Enum):
    """调度优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class ScheduleEntry:
    """调度条目（内存映射）"""
    schedule_id: int
    intent_id: int
    scheduled_time: datetime
    recurrence: RecurrenceType
    is_active: bool = True
    last_executed_at: Optional[datetime] = None
    priority: SchedulePriority = SchedulePriority.NORMAL
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScheduleExecutionResult:
    """调度执行结果"""
    schedule_id: int
    intent_id: int
    status: ScheduleStatus
    executed_at: datetime
    next_scheduled_time: Optional[datetime] = None
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass
class IntentSchedulerConfig:
    """意图调度器配置"""
    check_interval_seconds: int = 30
    max_concurrent_executions: int = 10
    default_max_retries: int = 3
    retry_delay_seconds: int = 60
    expired_schedule_cleanup_hours: int = 72
    enable_priority_queue: bool = True
    timezone_offset_hours: int = 8  # UTC+8 中国标准时间


# ──────────────────────── 周期计算工具 ────────────────────────


def _calculate_next_occurrence(
    current_time: datetime,
    recurrence: RecurrenceType,
    base_time: datetime,
) -> Optional[datetime]:
    """根据周期类型计算下次执行时间

    Args:
        current_time: 当前时间
        recurrence: 周期类型
        base_time: 基准时间（首次调度时间）

    Returns:
        下次执行时间，ONCE 类型返回 None
    """
    if recurrence == RecurrenceType.ONCE:
        return None

    if recurrence == RecurrenceType.DAILY:
        next_time = current_time.replace(
            hour=base_time.hour,
            minute=base_time.minute,
            second=base_time.second,
            microsecond=0,
        ) + timedelta(days=1)
        # 如果当天的时间还没过，就返回当天
        candidate = current_time.replace(
            hour=base_time.hour,
            minute=base_time.minute,
            second=base_time.second,
            microsecond=0,
        )
        if candidate > current_time:
            return candidate
        return next_time

    if recurrence == RecurrenceType.WEEKLY:
        days_ahead = (base_time.weekday() - current_time.weekday()) % 7
        if days_ahead == 0:
            candidate = current_time.replace(
                hour=base_time.hour,
                minute=base_time.minute,
                second=base_time.second,
                microsecond=0,
            )
            if candidate > current_time:
                return candidate
            days_ahead = 7
        next_time = current_time + timedelta(days=days_ahead)
        return next_time.replace(
            hour=base_time.hour,
            minute=base_time.minute,
            second=base_time.second,
            microsecond=0,
        )

    if recurrence == RecurrenceType.MONTHLY:
        # 下个月同一天
        next_month = current_time.month % 12 + 1
        next_year = current_time.year + (1 if next_month == 1 else 0)
        try:
            candidate = datetime(
                next_year, next_month, base_time.day,
                base_time.hour, base_time.minute, base_time.second,
                tzinfo=current_time.tzinfo,
            )
        except ValueError:
            # 处理月末日期不存在的情况（如31号在2月不存在）
            import calendar
            last_day = calendar.monthrange(next_year, next_month)[1]
            day = min(base_time.day, last_day)
            candidate = datetime(
                next_year, next_month, day,
                base_time.hour, base_time.minute, base_time.second,
                tzinfo=current_time.tzinfo,
            )
        return candidate

    return None


# ──────────────────────── 意图调度器 ────────────────────────


class IntentScheduler:
    """意图调度器：定时/周期意图执行调度

    核心职责：
    1. 管理调度条目的注册/注销
    2. 按时间触发意图执行
    3. 支持四种周期模式（ONCE/DAILY/WEEKLY/MONTHLY）
    4. 优先级队列调度
    5. 执行失败重试
    6. 过期调度清理
    """

    def __init__(self, config: Optional[IntentSchedulerConfig] = None):
        self.config = config or IntentSchedulerConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._schedules: Dict[int, ScheduleEntry] = {}
        self._execution_results: List[ScheduleExecutionResult] = []
        self._running_tasks: Dict[int, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_executions)
        self._is_running = False
        self._check_task: Optional[asyncio.Task] = None

    # ──────────── 调度条目管理 ────────────

    def register_schedule(self, schedule_entry: ScheduleEntry) -> bool:
        """注册调度条目"""
        if schedule_entry.schedule_id in self._schedules:
            self.logger.warning(
                "调度条目已存在: schedule_id=%d", schedule_entry.schedule_id
            )
            return False

        self._schedules[schedule_entry.schedule_id] = schedule_entry
        self.logger.info(
            "注册调度条目: schedule_id=%d, intent_id=%d, recurrence=%s, scheduled_time=%s",
            schedule_entry.schedule_id,
            schedule_entry.intent_id,
            schedule_entry.recurrence.value,
            schedule_entry.scheduled_time.isoformat(),
        )
        return True

    def unregister_schedule(self, schedule_id: int) -> bool:
        """注销调度条目"""
        if schedule_id not in self._schedules:
            self.logger.warning("调度条目不存在: schedule_id=%d", schedule_id)
            return False

        entry = self._schedules.pop(schedule_id)
        entry.is_active = False
        self.logger.info("注销调度条目: schedule_id=%d", schedule_id)
        return True

    def pause_schedule(self, schedule_id: int) -> bool:
        """暂停调度"""
        entry = self._schedules.get(schedule_id)
        if not entry:
            return False
        entry.is_active = False
        self.logger.info("暂停调度: schedule_id=%d", schedule_id)
        return True

    def resume_schedule(self, schedule_id: int) -> bool:
        """恢复调度"""
        entry = self._schedules.get(schedule_id)
        if not entry:
            return False
        entry.is_active = True
        self.logger.info("恢复调度: schedule_id=%d", schedule_id)
        return True

    # ──────────── 调度检查与触发 ────────────

    def _get_due_schedules(self, now: datetime) -> List[ScheduleEntry]:
        """获取当前时间应触发的调度条目

        按优先级排序：URGENT > HIGH > NORMAL > LOW
        """
        due_entries = []
        for entry in self._schedules.values():
            if not entry.is_active:
                continue
            if entry.schedule_id in self._running_tasks:
                continue
            if entry.scheduled_time <= now:
                due_entries.append(entry)

        if self.config.enable_priority_queue:
            due_entries.sort(key=lambda e: e.priority.value, reverse=True)

        return due_entries

    async def _execute_intent(self, entry: ScheduleEntry) -> ScheduleExecutionResult:
        """执行意图（带并发控制）

        Args:
            entry: 调度条目

        Returns:
            执行结果
        """
        async with self._semaphore:
            start_time = datetime.now(timezone.utc)
            self.logger.info(
                "开始执行调度意图: schedule_id=%d, intent_id=%d",
                entry.schedule_id,
                entry.intent_id,
            )

            try:
                # 模拟意图执行：实际应调用意图处理管线
                result = await self._invoke_intent_pipeline(entry.intent_id, entry.metadata)

                duration_ms = int(
                    (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                )
                execution_result = ScheduleExecutionResult(
                    schedule_id=entry.schedule_id,
                    intent_id=entry.intent_id,
                    status=ScheduleStatus.COMPLETED,
                    executed_at=start_time,
                    duration_ms=duration_ms,
                )

                # 更新最后执行时间
                entry.last_executed_at = start_time

                # 计算下次执行时间
                if entry.recurrence != RecurrenceType.ONCE:
                    next_time = _calculate_next_occurrence(
                        start_time, entry.recurrence, entry.scheduled_time
                    )
                    execution_result.next_scheduled_time = next_time
                    if next_time:
                        entry.scheduled_time = next_time
                else:
                    # 一次性调度执行完毕后自动停用
                    entry.is_active = False

                self.logger.info(
                    "调度意图执行完成: schedule_id=%d, duration=%dms, next=%s",
                    entry.schedule_id,
                    duration_ms,
                    execution_result.next_scheduled_time.isoformat()
                    if execution_result.next_scheduled_time
                    else "N/A",
                )

            except Exception as e:
                duration_ms = int(
                    (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                )
                entry.retry_count += 1

                if entry.retry_count < entry.max_retries:
                    # 重试：延迟后重新调度
                    retry_time = start_time + timedelta(
                        seconds=self.config.retry_delay_seconds * entry.retry_count
                    )
                    entry.scheduled_time = retry_time
                    execution_result = ScheduleExecutionResult(
                        schedule_id=entry.schedule_id,
                        intent_id=entry.intent_id,
                        status=ScheduleStatus.FAILED,
                        executed_at=start_time,
                        next_scheduled_time=retry_time,
                        error=str(e),
                        duration_ms=duration_ms,
                    )
                    self.logger.warning(
                        "调度意图执行失败，将重试(%d/%d): schedule_id=%d, error=%s",
                        entry.retry_count,
                        entry.max_retries,
                        entry.schedule_id,
                        str(e),
                    )
                else:
                    # 超过最大重试次数，停用调度
                    entry.is_active = False
                    execution_result = ScheduleExecutionResult(
                        schedule_id=entry.schedule_id,
                        intent_id=entry.intent_id,
                        status=ScheduleStatus.FAILED,
                        executed_at=start_time,
                        error=f"超过最大重试次数({entry.max_retries}): {e}",
                        duration_ms=duration_ms,
                    )
                    self.logger.error(
                        "调度意图执行失败且超过重试上限，已停用: schedule_id=%d",
                        entry.schedule_id,
                    )

            self._execution_results.append(execution_result)
            return execution_result

    async def _invoke_intent_pipeline(
        self, intent_id: int, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """调用意图处理管线

        实际实现应调用意图解析→策略生成→执行→验证的完整管线。
        此处为模拟实现。
        """
        await asyncio.sleep(0.1)  # 模拟处理延迟

        # 模拟执行结果
        return {
            "intent_id": intent_id,
            "status": "completed",
            "message": f"意图 {intent_id} 调度执行成功",
            "metadata": metadata,
        }

    async def _check_and_execute(self) -> int:
        """检查并执行到期调度

        Returns:
            本次触发的调度数量
        """
        now = datetime.now(timezone.utc)
        due_entries = self._get_due_schedules(now)

        if not due_entries:
            return 0

        self.logger.info("发现 %d 个到期调度", len(due_entries))

        executed_count = 0
        for entry in due_entries[: self.config.max_concurrent_executions]:
            task = asyncio.create_task(self._execute_intent(entry))
            self._running_tasks[entry.schedule_id] = task
            task.add_done_callback(
                lambda t, sid=entry.schedule_id: self._running_tasks.pop(sid, None)
            )
            executed_count += 1

        return executed_count

    # ──────────── 过期清理 ────────────

    def _cleanup_expired_schedules(self) -> int:
        """清理过期的调度条目

        一次性调度超过 cleanup_hours 小时未执行的视为过期。
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=self.config.expired_schedule_cleanup_hours)
        expired_ids = []

        for schedule_id, entry in self._schedules.items():
            if entry.recurrence == RecurrenceType.ONCE and not entry.is_active:
                if entry.last_executed_at and entry.last_executed_at < cutoff:
                    expired_ids.append(schedule_id)
                elif entry.scheduled_time < cutoff:
                    expired_ids.append(schedule_id)

        for sid in expired_ids:
            del self._schedules[sid]

        if expired_ids:
            self.logger.info("清理 %d 个过期调度条目", len(expired_ids))

        return len(expired_ids)

    # ──────────── 调度器生命周期 ────────────

    async def start(self) -> None:
        """启动调度器"""
        if self._is_running:
            self.logger.warning("调度器已在运行")
            return

        self._is_running = True
        self.logger.info(
            "意图调度器启动: check_interval=%ds, max_concurrent=%d",
            self.config.check_interval_seconds,
            self.config.max_concurrent_executions,
        )

        async def _run_loop():
            while self._is_running:
                try:
                    await self._check_and_execute()
                    self._cleanup_expired_schedules()
                except Exception as e:
                    self.logger.error("调度循环异常: %s", str(e))
                await asyncio.sleep(self.config.check_interval_seconds)

        self._check_task = asyncio.create_task(_run_loop())

    async def stop(self) -> None:
        """停止调度器"""
        self._is_running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
            self._check_task = None

        # 等待运行中的任务完成
        if self._running_tasks:
            self.logger.info("等待 %d 个运行中任务完成...", len(self._running_tasks))
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)

        self.logger.info("意图调度器已停止")

    # ──────────── 查询接口 ────────────

    def get_schedule(self, schedule_id: int) -> Optional[ScheduleEntry]:
        """获取调度条目"""
        return self._schedules.get(schedule_id)

    def get_active_schedules(self) -> List[ScheduleEntry]:
        """获取所有活跃调度"""
        return [e for e in self._schedules.values() if e.is_active]

    def get_execution_history(
        self, schedule_id: Optional[int] = None, limit: int = 50
    ) -> List[ScheduleExecutionResult]:
        """获取执行历史"""
        results = self._execution_results
        if schedule_id is not None:
            results = [r for r in results if r.schedule_id == schedule_id]
        return results[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """获取调度统计信息"""
        total = len(self._schedules)
        active = sum(1 for e in self._schedules.values() if e.is_active)
        by_recurrence: Dict[str, int] = {}
        for entry in self._schedules.values():
            key = entry.recurrence.value
            by_recurrence[key] = by_recurrence.get(key, 0) + 1

        completed = sum(
            1 for r in self._execution_results if r.status == ScheduleStatus.COMPLETED
        )
        failed = sum(
            1 for r in self._execution_results if r.status == ScheduleStatus.FAILED
        )

        return {
            "total_schedules": total,
            "active_schedules": active,
            "inactive_schedules": total - active,
            "by_recurrence": by_recurrence,
            "total_executions": len(self._execution_results),
            "completed_executions": completed,
            "failed_executions": failed,
            "running_tasks": len(self._running_tasks),
        }

    # ──────────── Agent 标准接口 ────────────

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """处理调度任务

        支持的 action:
        - register: 注册调度条目
        - unregister: 注销调度条目
        - pause: 暂停调度
        - resume: 恢复调度
        - execute_now: 立即执行指定调度
        - list: 列出调度条目
        - stats: 获取统计信息
        - history: 获取执行历史
        """
        action = task.get("action", "list")

        if action == "register":
            entry_data = task.get("schedule_entry", {})
            entry = ScheduleEntry(
                schedule_id=entry_data.get("schedule_id", 0),
                intent_id=entry_data.get("intent_id", 0),
                scheduled_time=entry_data.get(
                    "scheduled_time", datetime.now(timezone.utc)
                ),
                recurrence=RecurrenceType(entry_data.get("recurrence", "once")),
                is_active=entry_data.get("is_active", True),
                priority=SchedulePriority(entry_data.get("priority", 1)),
                max_retries=entry_data.get("max_retries", self.config.default_max_retries),
                metadata=entry_data.get("metadata", {}),
            )
            success = self.register_schedule(entry)
            return {"action": "register", "success": success, "schedule_id": entry.schedule_id}

        if action == "unregister":
            schedule_id = task.get("schedule_id", 0)
            success = self.unregister_schedule(schedule_id)
            return {"action": "unregister", "success": success, "schedule_id": schedule_id}

        if action == "pause":
            schedule_id = task.get("schedule_id", 0)
            success = self.pause_schedule(schedule_id)
            return {"action": "pause", "success": success, "schedule_id": schedule_id}

        if action == "resume":
            schedule_id = task.get("schedule_id", 0)
            success = self.resume_schedule(schedule_id)
            return {"action": "resume", "success": success, "schedule_id": schedule_id}

        if action == "execute_now":
            schedule_id = task.get("schedule_id", 0)
            entry = self._schedules.get(schedule_id)
            if not entry:
                return {"action": "execute_now", "success": False, "error": "调度条目不存在"}
            result = await self._execute_intent(entry)
            return {
                "action": "execute_now",
                "success": result.status == ScheduleStatus.COMPLETED,
                "result": {
                    "schedule_id": result.schedule_id,
                    "status": result.status.value,
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                },
            }

        if action == "list":
            active_only = task.get("active_only", True)
            entries = self.get_active_schedules() if active_only else list(self._schedules.values())
            return {
                "action": "list",
                "count": len(entries),
                "schedules": [
                    {
                        "schedule_id": e.schedule_id,
                        "intent_id": e.intent_id,
                        "scheduled_time": e.scheduled_time.isoformat(),
                        "recurrence": e.recurrence.value,
                        "is_active": e.is_active,
                        "last_executed_at": e.last_executed_at.isoformat()
                        if e.last_executed_at
                        else None,
                        "priority": e.priority.value,
                    }
                    for e in entries
                ],
            }

        if action == "stats":
            return {"action": "stats", "statistics": self.get_statistics()}

        if action == "history":
            schedule_id = task.get("schedule_id")
            limit = task.get("limit", 50)
            results = self.get_execution_history(schedule_id=schedule_id, limit=limit)
            return {
                "action": "history",
                "count": len(results),
                "results": [
                    {
                        "schedule_id": r.schedule_id,
                        "intent_id": r.intent_id,
                        "status": r.status.value,
                        "executed_at": r.executed_at.isoformat(),
                        "next_scheduled_time": r.next_scheduled_time.isoformat()
                        if r.next_scheduled_time
                        else None,
                        "error": r.error,
                        "duration_ms": r.duration_ms,
                    }
                    for r in results
                ],
            }

        return {"error": f"未知 action: {action}"}

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        active_count = sum(1 for e in self._schedules.values() if e.is_active)
        running_count = len(self._running_tasks)
        recent_results = self._execution_results[-10:]
        recent_success_rate = 0.0
        if recent_results:
            success_count = sum(
                1 for r in recent_results if r.status == ScheduleStatus.COMPLETED
            )
            recent_success_rate = round(success_count / len(recent_results), 2)

        is_healthy = self._is_running and recent_success_rate >= 0.5

        return {
            "status": "healthy" if is_healthy else "degraded",
            "is_running": self._is_running,
            "active_schedules": active_count,
            "running_tasks": running_count,
            "total_executions": len(self._execution_results),
            "recent_success_rate": recent_success_rate,
            "check_interval_seconds": self.config.check_interval_seconds,
        }
