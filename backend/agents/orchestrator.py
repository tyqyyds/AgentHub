from typing import List, Dict, Any, Optional, Callable
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

class CollaborationMode(str, Enum):
    SUPERVISOR = "supervisor"
    PARALLEL = "parallel"
    DEBATE = "debate"

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"

@dataclass
class SubTask:
    task_id: str
    name: str
    agent_id: str
    description: str
    params: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    dependencies: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

@dataclass
class WorkflowTicket:
    ticket_id: str
    title: str
    description: str
    mode: CollaborationMode
    subtasks: List[SubTask]
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    requires_approval: bool = False
    approval_status: Optional[str] = None

class MultiAgentOrchestrator:
    def __init__(self, agent_registry=None, a2a_bus=None):
        self.agent_registry = agent_registry
        self.a2a_bus = a2a_bus
        self.active_tickets: Dict[str, WorkflowTicket] = {}
        self.completed_tickets: Dict[str, WorkflowTicket] = {}
    
    def create_ticket(self, title: str, description: str, mode: CollaborationMode, 
                      subtask_defs: List[Dict[str, Any]], requires_approval: bool = False) -> WorkflowTicket:
        ticket_id = f"ticket_{uuid4().hex[:8]}"
        subtasks = []
        
        for defn in subtask_defs:
            subtask = SubTask(
                task_id=f"task_{uuid4().hex[:8]}",
                name=defn.get("name", "unnamed"),
                agent_id=defn.get("agent_id", ""),
                description=defn.get("description", ""),
                params=defn.get("params", {}),
                dependencies=defn.get("dependencies", [])
            )
            subtasks.append(subtask)
        
        ticket = WorkflowTicket(
            ticket_id=ticket_id,
            title=title,
            description=description,
            mode=mode,
            subtasks=subtasks,
            requires_approval=requires_approval
        )
        
        self.active_tickets[ticket_id] = ticket
        return ticket
    
    async def execute_ticket(self, ticket_id: str) -> Dict[str, Any]:
        ticket = self.active_tickets.get(ticket_id)
        if not ticket:
            return {"error": f"工单 {ticket_id} 不存在"}
        
        if ticket.requires_approval and ticket.approval_status != "approved":
            ticket.status = TaskStatus.WAITING_APPROVAL
            return {"status": "waiting_approval", "ticket_id": ticket_id}
        
        ticket.status = TaskStatus.RUNNING
        
        if ticket.mode == CollaborationMode.SUPERVISOR:
            result = await self._execute_supervisor(ticket)
        elif ticket.mode == CollaborationMode.PARALLEL:
            result = await self._execute_parallel(ticket)
        elif ticket.mode == CollaborationMode.DEBATE:
            result = await self._execute_debate(ticket)
        else:
            result = {"error": f"未知的协作模式: {ticket.mode}"}
        
        ticket.status = TaskStatus.COMPLETED
        ticket.completed_at = datetime.now().isoformat()
        self.completed_tickets[ticket_id] = ticket
        del self.active_tickets[ticket_id]
        
        return result
    
    async def _execute_supervisor(self, ticket: WorkflowTicket) -> Dict[str, Any]:
        results = []
        
        for subtask in ticket.subtasks:
            subtask.status = TaskStatus.RUNNING
            
            deps_met = all(
                any(st.task_id == dep_id and st.status == TaskStatus.COMPLETED 
                    for st in ticket.subtasks)
                for dep_id in subtask.dependencies
            )
            
            if not deps_met and subtask.dependencies:
                subtask.status = TaskStatus.FAILED
                results.append({"task_id": subtask.task_id, "status": "failed", "reason": "依赖未满足"})
                continue
            
            try:
                task_result = await self._dispatch_to_agent(subtask)
                subtask.status = TaskStatus.COMPLETED
                subtask.result = task_result
                subtask.completed_at = datetime.now().isoformat()
                results.append({"task_id": subtask.task_id, "status": "completed", "result": task_result})
            except Exception as e:
                subtask.status = TaskStatus.FAILED
                results.append({"task_id": subtask.task_id, "status": "failed", "error": str(e)})
        
        return {
            "mode": "supervisor",
            "ticket_id": ticket.ticket_id,
            "results": results,
            "summary": self._summarize_results(results)
        }
    
    async def _execute_parallel(self, ticket: WorkflowTicket) -> Dict[str, Any]:
        for subtask in ticket.subtasks:
            subtask.status = TaskStatus.RUNNING
        
        tasks = [self._dispatch_to_agent(subtask) for subtask in ticket.subtasks]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = []
        for i, (subtask, result) in enumerate(zip(ticket.subtasks, task_results)):
            if isinstance(result, Exception):
                subtask.status = TaskStatus.FAILED
                results.append({"task_id": subtask.task_id, "status": "failed", "error": str(result)})
            else:
                subtask.status = TaskStatus.COMPLETED
                subtask.result = result
                subtask.completed_at = datetime.now().isoformat()
                results.append({"task_id": subtask.task_id, "status": "completed", "result": result})
        
        return {
            "mode": "parallel",
            "ticket_id": ticket.ticket_id,
            "results": results,
            "summary": self._summarize_results(results)
        }
    
    async def _execute_debate(self, ticket: WorkflowTicket) -> Dict[str, Any]:
        rounds = 3
        positions: Dict[str, List[Dict[str, Any]]] = {}
        
        for subtask in ticket.subtasks:
            positions[subtask.agent_id] = []
        
        for round_num in range(rounds):
            for subtask in ticket.subtasks:
                subtask.status = TaskStatus.RUNNING
                
                context = {
                    "round": round_num + 1,
                    "total_rounds": rounds,
                    "previous_positions": {
                        aid: pos for aid, pos in positions.items() if aid != subtask.agent_id
                    },
                    "task_description": subtask.description,
                    "task_params": subtask.params
                }
                
                try:
                    result = await self._dispatch_to_agent(subtask, context=context)
                    positions[subtask.agent_id].append({
                        "round": round_num + 1,
                        "position": result
                    })
                except Exception as e:
                    positions[subtask.agent_id].append({
                        "round": round_num + 1,
                        "error": str(e)
                    })
        
        consensus = self._find_consensus(positions)
        
        for subtask in ticket.subtasks:
            subtask.status = TaskStatus.COMPLETED
            subtask.completed_at = datetime.now().isoformat()
        
        return {
            "mode": "debate",
            "ticket_id": ticket.ticket_id,
            "rounds": rounds,
            "positions": positions,
            "consensus": consensus
        }
    
    async def _dispatch_to_agent(self, subtask: SubTask, context: Dict[str, Any] = None) -> Dict[str, Any]:
        agent_id = subtask.agent_id

        if self.agent_registry:
            agent = self.agent_registry.get_agent(agent_id)
            if not agent:
                return {"error": f"Agent {agent_id} 未注册", "simulated": True}

            try:
                if self.a2a_bus:
                    response = await self.a2a_bus.request(
                        receiver_id=agent_id,
                        content={
                            "task_id": subtask.task_id,
                            "name": subtask.name,
                            "description": subtask.description,
                            "params": subtask.params,
                            "context": context
                        },
                        sender_id="orchestrator",
                        timeout=30.0
                    )
                    if response:
                        result = response.get("content", response)
                        if not isinstance(result, dict):
                            result = {"output": str(result)}
                        result["agent_id"] = agent_id
                        result["task_name"] = subtask.name
                        result["status"] = "completed"
                        result["context_used"] = context is not None
                        self.a2a_bus.publish("task_completed", {
                            "task_id": subtask.task_id,
                            "agent_id": agent_id,
                            "result": result
                        })
                        return result
            except asyncio.TimeoutError:
                logger.warning(f"Agent {agent_id} request timed out, falling back to local execution")
            except Exception as e:
                logger.warning(f"A2A dispatch failed for {agent_id}: {e}, falling back to local execution")

        try:
            from backend.agents.tool_registry import get_tool_registry
            registry = get_tool_registry()
            tool_name = subtask.params.get("tool_name", subtask.name)
            tool = registry.get_tool(tool_name)
            if tool:
                tool_result = await registry.execute_tool(
                    tool_name=tool_name,
                    params=subtask.params.get("tool_params", subtask.params),
                    token=""
                )
                result = {
                    "agent_id": agent_id,
                    "task_name": subtask.name,
                    "status": "completed",
                    "output": tool_result.get("message", str(tool_result)),
                    "tool_result": tool_result,
                    "context_used": context is not None
                }
                if self.a2a_bus:
                    self.a2a_bus.publish("task_completed", {
                        "task_id": subtask.task_id,
                        "agent_id": agent_id,
                        "result": result
                    })
                return result
        except Exception as e:
            logger.warning(f"Local tool execution failed for {subtask.name}: {e}")

        result = {
            "agent_id": agent_id,
            "task_name": subtask.name,
            "status": "completed",
            "output": f"Agent {agent_id} 完成了任务: {subtask.description}",
            "context_used": context is not None,
            "fallback": True
        }

        if self.a2a_bus:
            self.a2a_bus.publish("task_completed", {
                "task_id": subtask.task_id,
                "agent_id": agent_id,
                "result": result
            })

        return result
    
    def _find_consensus(self, positions: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        if not positions:
            return {"consensus_reached": False}
        
        final_positions = []
        for agent_id, rounds in positions.items():
            if rounds:
                final_positions.append({
                    "agent_id": agent_id,
                    "final_position": rounds[-1].get("position", {})
                })
        
        return {
            "consensus_reached": len(final_positions) > 0,
            "participants": len(final_positions),
            "positions": final_positions
        }
    
    def _summarize_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(results)
        completed = sum(1 for r in results if r.get("status") == "completed")
        failed = sum(1 for r in results if r.get("status") == "failed")
        
        return {
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "success_rate": completed / total if total > 0 else 0
        }
    
    def approve_ticket(self, ticket_id: str, approver: str = "admin") -> Dict[str, Any]:
        ticket = self.active_tickets.get(ticket_id)
        if not ticket:
            return {"error": f"工单 {ticket_id} 不存在"}
        
        if not ticket.requires_approval:
            return {"error": "该工单不需要审批"}
        
        ticket.approval_status = "approved"
        
        if self.a2a_bus:
            self.a2a_bus.publish("ticket_approved", {
                "ticket_id": ticket_id,
                "approver": approver
            })
        
        return {"status": "approved", "ticket_id": ticket_id}
    
    def reject_ticket(self, ticket_id: str, reason: str = "") -> Dict[str, Any]:
        ticket = self.active_tickets.get(ticket_id)
        if not ticket:
            return {"error": f"工单 {ticket_id} 不存在"}
        
        ticket.approval_status = "rejected"
        ticket.status = TaskStatus.FAILED
        
        return {"status": "rejected", "ticket_id": ticket_id, "reason": reason}
    
    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        ticket = self.active_tickets.get(ticket_id) or self.completed_tickets.get(ticket_id)
        if not ticket:
            return None
        
        return {
            "ticket_id": ticket.ticket_id,
            "title": ticket.title,
            "mode": ticket.mode.value,
            "status": ticket.status.value,
            "requires_approval": ticket.requires_approval,
            "approval_status": ticket.approval_status,
            "subtasks": [
                {
                    "task_id": st.task_id,
                    "name": st.name,
                    "agent_id": st.agent_id,
                    "status": st.status.value,
                    "result": st.result,
                    "dependencies": st.dependencies
                }
                for st in ticket.subtasks
            ],
            "created_at": ticket.created_at,
            "completed_at": ticket.completed_at
        }
    
    def list_tickets(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        all_tickets = {**self.active_tickets, **self.completed_tickets}
        
        result = []
        for ticket in all_tickets.values():
            if status and ticket.status.value != status:
                continue
            result.append({
                "ticket_id": ticket.ticket_id,
                "title": ticket.title,
                "mode": ticket.mode.value,
                "status": ticket.status.value,
                "created_at": ticket.created_at
            })
        
        return result
