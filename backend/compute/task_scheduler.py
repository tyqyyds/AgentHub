import uuid
import asyncio
import json
import os
import logging
from typing import Dict, List, Optional, Any, Callable, Awaitable
from datetime import datetime, timezone
import psutil
import aiosqlite
from backend.cross_domain.registry import AgentRegistryCenter

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_DB_PATH = os.path.join(_DB_DIR, "compute_tasks.db")

_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS compute_tasks (
        task_id TEXT PRIMARY KEY,
        task_type TEXT NOT NULL,
        params TEXT NOT NULL,
        priority TEXT NOT NULL DEFAULT 'medium',
        status TEXT NOT NULL DEFAULT 'pending',
        assigned_to TEXT NOT NULL,
        reasoning TEXT NOT NULL DEFAULT '',
        local_cpu_load_at_submit REAL NOT NULL DEFAULT 0,
        result TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
"""

_INSERT_SQL = """
    INSERT OR REPLACE INTO compute_tasks
    (task_id, task_type, params, priority, status, assigned_to, reasoning,
     local_cpu_load_at_submit, result, error, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_UPDATE_SQL = """
    UPDATE compute_tasks SET status=?, result=?, error=?, updated_at=?
    WHERE task_id=?
"""


class TaskScheduler:
    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._registry = AgentRegistryCenter()
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._db: Optional[aiosqlite.Connection] = None
        self._task_handlers: Dict[str, Callable[..., Awaitable[Any]]] = {}
        psutil.cpu_percent(interval=None)

    async def init_db(self):
        os.makedirs(_DB_DIR, exist_ok=True)
        self._db = await aiosqlite.connect(_DB_PATH)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(_CREATE_TABLE_SQL)
        await self._db.commit()
        await self._load_tasks_from_db()

    async def _load_tasks_from_db(self):
        async with self._db.execute("SELECT * FROM compute_tasks") as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            for row in rows:
                task = dict(zip(columns, row))
                task["params"] = json.loads(task["params"])
                if task.get("result") is not None:
                    task["result"] = json.loads(task["result"])
                task["created_at"] = datetime.fromisoformat(task["created_at"])
                task["updated_at"] = datetime.fromisoformat(task["updated_at"])
                self._tasks[task["task_id"]] = task

    async def close(self):
        for task_id, atask in list(self._running_tasks.items()):
            atask.cancel()
            try:
                await atask
            except asyncio.CancelledError:
                pass
        if self._db:
            await self._db.close()
            self._db = None

    def register_handler(self, task_type: str, handler: Callable[..., Awaitable[Any]]):
        self._task_handlers[task_type] = handler

    def get_system_stats(self) -> Dict[str, Any]:
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu_percent": cpu_percent,
            "cpu_count": psutil.cpu_count(),
            "memory_total": memory.total,
            "memory_used": memory.used,
            "memory_percent": memory.percent,
            "memory_available": memory.available,
            "disk_total": disk.total,
            "disk_used": disk.used,
            "disk_percent": disk.percent,
        }

    def _get_local_cpu_load(self) -> float:
        return psutil.cpu_percent(interval=None)

    async def submit_task(
        self,
        task_type: str,
        params: dict,
        priority: str = "medium",
    ) -> Dict[str, Any]:
        task_id = str(uuid.uuid4())
        local_cpu_load = self._get_local_cpu_load()

        assigned_to = ""
        reasoning = ""

        if local_cpu_load < 70:
            assigned_to = "agenthub-local"
            reasoning = f"Local node load is {local_cpu_load:.1f}% (< 70%), task assigned locally"
        else:
            remote_agent = self._registry.get_least_loaded(capability=task_type)
            if remote_agent:
                assigned_to = remote_agent.agent_id
                reasoning = f"Local node load is {local_cpu_load:.1f}% (>= 70%), task offloaded to remote agent '{remote_agent.agent_id}' (load: {remote_agent.cpu_load:.1f}%)"
            else:
                assigned_to = "agenthub-local"
                reasoning = f"Local node load is {local_cpu_load:.1f}% (>= 70%), no suitable remote agent available, task queued locally"

        now = datetime.now(timezone.utc)
        task = {
            "task_id": task_id,
            "task_type": task_type,
            "params": params,
            "priority": priority,
            "status": "pending",
            "assigned_to": assigned_to,
            "reasoning": reasoning,
            "local_cpu_load_at_submit": round(local_cpu_load, 2),
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        self._tasks[task_id] = task
        await self._persist_task(task)
        logger.info(f"Task submitted: {task_id}, type={task_type}, assigned_to={assigned_to}")

        if assigned_to == "agenthub-local" and task_type in self._task_handlers:
            asyncio.ensure_future(self._execute_task(task_id))

        return task

    async def _execute_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if not task or task["status"] != "pending":
            return

        task["status"] = "running"
        task["updated_at"] = datetime.now(timezone.utc)
        await self._update_task_in_db(task)

        handler = self._task_handlers.get(task["task_type"])
        if not handler:
            task["status"] = "failed"
            task["error"] = f"No handler registered for task type: {task['task_type']}"
            task["updated_at"] = datetime.now(timezone.utc)
            await self._update_task_in_db(task)
            logger.error(f"Task {task_id} failed: no handler for type {task['task_type']}")
            return

        atask = asyncio.create_task(self._run_handler(task_id, handler, task["params"]))
        self._running_tasks[task_id] = atask
        atask.add_done_callback(lambda t: self._running_tasks.pop(task_id, None))

    async def _run_handler(self, task_id: str, handler: Callable[..., Awaitable[Any]], params: dict) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        try:
            result = await handler(params)
            task["status"] = "completed"
            task["result"] = result
            task["updated_at"] = datetime.now(timezone.utc)
            await self._update_task_in_db(task)
            logger.info(f"Task {task_id} completed successfully")
        except asyncio.CancelledError:
            task["status"] = "cancelled"
            task["updated_at"] = datetime.now(timezone.utc)
            await self._update_task_in_db(task)
            logger.info(f"Task {task_id} was cancelled")
            raise
        except Exception as e:
            task["status"] = "failed"
            task["error"] = str(e)
            task["updated_at"] = datetime.now(timezone.utc)
            await self._update_task_in_db(task)
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)

    async def cancel_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        if task["status"] in ("completed", "failed", "cancelled"):
            return task

        atask = self._running_tasks.pop(task_id, None)
        if atask and not atask.done():
            atask.cancel()
            try:
                await atask
            except asyncio.CancelledError:
                pass

        task["status"] = "cancelled"
        task["updated_at"] = datetime.now(timezone.utc)
        await self._update_task_in_db(task)
        logger.info(f"Task {task_id} cancelled")
        return task

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[Dict[str, Any]]:
        return list(self._tasks.values())

    def get_compute_nodes(self) -> List[Dict[str, Any]]:
        agents = self._registry.list_all()
        nodes = []
        for agent in agents:
            nodes.append({
                "agent_id": agent.agent_id,
                "capabilities": agent.capabilities,
                "status": agent.status,
                "cpu_load": agent.cpu_load,
                "memory_free": agent.memory_free,
                "endpoint": agent.endpoint,
                "tags": agent.tags,
            })
        return nodes

    async def _persist_task(self, task: Dict[str, Any]) -> None:
        if not self._db:
            return
        await self._db.execute(
            _INSERT_SQL,
            (
                task["task_id"],
                task["task_type"],
                json.dumps(task["params"]),
                task["priority"],
                task["status"],
                task["assigned_to"],
                task["reasoning"],
                task["local_cpu_load_at_submit"],
                json.dumps(task["result"]) if task.get("result") is not None else None,
                task.get("error"),
                task["created_at"].isoformat(),
                task["updated_at"].isoformat(),
            ),
        )
        await self._db.commit()

    async def _update_task_in_db(self, task: Dict[str, Any]) -> None:
        if not self._db:
            return
        await self._db.execute(
            _UPDATE_SQL,
            (
                task["status"],
                json.dumps(task["result"]) if task.get("result") is not None else None,
                task.get("error"),
                task["updated_at"].isoformat(),
                task["task_id"],
            ),
        )
        await self._db.commit()


task_scheduler = TaskScheduler()
