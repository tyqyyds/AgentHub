import time
from typing import List, Dict, Any, Optional
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from backend.agents.base import AgentState, IntentContext, NetworkState
from backend.agents.intent_parser import IntentParserAgent
from backend.agents.conflict_detector import ConflictDetectorAgent
from backend.agents.policy_planner import PolicyPlannerAgent
from backend.agents.execution_agent import ExecutionAgent, VerificationAgent
from backend.agents.a2a_bus import A2ABus

class IntentWorkflow:
    def __init__(self):
        self.intent_parser = IntentParserAgent()
        self.conflict_detector = ConflictDetectorAgent()
        self.policy_planner = PolicyPlannerAgent()
        self.execution_agent = ExecutionAgent()
        self.verification_agent = VerificationAgent()
        self.a2a_bus = A2ABus()
        self.workflow = self._build_workflow()
    
    def _reject_intent(self, state: AgentState) -> AgentState:
        state["execution_result"] = ExecutionResult(
            status="rejected",
            device="",
            command="",
            output="意图因严重冲突被自动拒绝",
            error=state["intent_context"].conflict_details if hasattr(state["intent_context"], "conflict_details") else None
        )
        return state

    def _build_workflow(self):
        workflow = StateGraph(AgentState)
        
        workflow.add_node("parse_intent", self._parse_intent)
        workflow.add_node("detect_conflict", self._detect_conflict)
        workflow.add_node("plan_policy", self._plan_policy)
        workflow.add_node("execute", self._execute)
        workflow.add_node("verify", self._verify)
        workflow.add_node("reconstruct", self._reconstruct)
        
        workflow.add_edge("parse_intent", "detect_conflict")
        workflow.add_node("reject", self._reject_intent)
        workflow.add_edge("reject", END)
        workflow.add_conditional_edges(
            "detect_conflict",
            self._should_continue,
            {
                "continue": "plan_policy",
                "conflict": END,
                "reject": "reject"
            }
        )
        workflow.add_edge("plan_policy", "execute")
        workflow.add_edge("execute", "verify")
        workflow.add_conditional_edges(
            "verify",
            self._verify_result,
            {
                "completed": END,
                "reconstruct": "reconstruct",
                "rollback": END
            }
        )
        workflow.add_edge("reconstruct", "plan_policy")
        
        workflow.set_entry_point("parse_intent")
        
        return workflow.compile()
    
    def _parse_intent(self, state: AgentState) -> dict:
        user_input = next((m.content for m in state["messages"] if isinstance(m, HumanMessage)), "")
        
        parsed = self.intent_parser.parse(user_input)
        
        self.a2a_bus.publish("intent_parsed", {
            "intent_id": parsed.intent_id,
            "user_input": user_input,
            "parsed": parsed.model_dump()
        })
        
        return {
            **state,
            "intent_context": parsed,
            "current_step": "parse_intent",
            "next_steps": ["detect_conflict"]
        }
    
    def _detect_conflict(self, state: AgentState) -> dict:
        result = self.conflict_detector.detect(
            state["intent_context"],
            state["network_state"]
        )
        
        updated_context = state["intent_context"].model_copy(update={
            "conflict_detected": result["conflict"],
            "conflict_details": result["details"]
        })
        
        return {
            **state,
            "intent_context": updated_context,
            "current_step": "detect_conflict"
        }
    
    def _should_continue(self, state: AgentState) -> str:
        if state["intent_context"].conflict_detected:
            conflict_details = state["intent_context"].conflict_details
            if conflict_details and isinstance(conflict_details, dict):
                severity = conflict_details.get("severity", "high")
                if severity == "critical":
                    return "reject"
            return "conflict"
        return "continue"
    
    def _plan_policy(self, state: AgentState) -> dict:
        plan = self.policy_planner.generate(
            state["intent_context"],
            state["network_state"]
        )
        
        updated_context = state["intent_context"].model_copy(update={
            "actions": plan["actions"]
        })
        
        return {
            **state,
            "intent_context": updated_context,
            "current_step": "plan_policy",
            "next_steps": ["execute"]
        }
    
    def _execute(self, state: AgentState) -> dict:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    results = pool.submit(
                        asyncio.run,
                        self.execution_agent.execute(
                            state["intent_context"].actions,
                            state["network_state"]
                        )
                    ).result()
            else:
                results = loop.run_until_complete(
                    self.execution_agent.execute(
                        state["intent_context"].actions,
                        state["network_state"]
                    )
                )
        except RuntimeError:
            results = asyncio.run(
                self.execution_agent.execute(
                    state["intent_context"].actions,
                    state["network_state"]
                )
            )
        
        self.a2a_bus.publish("intent_executed", {
            "intent_id": state["intent_context"].intent_id,
            "results": [r.model_dump() for r in results]
        })
        
        return {
            **state,
            "execution_results": results,
            "current_step": "execute",
            "next_steps": ["verify"]
        }
    
    def _verify(self, state: AgentState) -> dict:
        result = self.verification_agent.verify(
            state["intent_context"],
            state["execution_results"]
        )
        
        return {
            **state,
            "current_step": "verify",
            "telemetry_data": result.get("telemetry", []),
            "next_steps": result.get("next_steps", [])
        }
    
    def _verify_result(self, state: AgentState) -> str:
        results = state["execution_results"]
        if not results:
            return "rollback"
        reconstruct_count = state.get("reconstruct_count", 0)
        if all(r.status == "success" for r in results):
            return "completed"
        elif any(r.status == "failed" for r in results) and reconstruct_count < 2:
            return "reconstruct"
        else:
            return "rollback"
    
    def _reconstruct(self, state: AgentState) -> dict:
        reconstruct_count = state.get("reconstruct_count", 0) + 1
        updated_plan = self.policy_planner.adjust(
            state["intent_context"],
            [r.model_dump() for r in state["execution_results"]],
            state["network_state"]
        )
        
        updated_context = state["intent_context"].model_copy(update={
            "actions": updated_plan["actions"]
        })
        
        return {
            **state,
            "intent_context": updated_context,
            "current_step": "reconstruct",
            "reconstruct_count": reconstruct_count,
            "next_steps": ["plan_policy"]
        }
    
    async def run(self, user_input: str, network_state: NetworkState) -> dict:
        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "intent_context": IntentContext(
                intent_id=f"intent_{int(time.time())}",
                user_input=user_input
            ),
            "network_state": network_state,
            "execution_results": [],
            "telemetry_data": [],
            "current_step": "start",
            "next_steps": ["parse_intent"],
            "is_completed": False,
            "error": None,
            "reconstruct_count": 0
        }
        
        result = await self.workflow.ainvoke(initial_state, config={"recursion_limit": 25})
        return result
    
    def run_sync(self, user_input: str, network_state: NetworkState) -> dict:
        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "intent_context": IntentContext(
                intent_id=f"intent_{int(time.time())}",
                user_input=user_input
            ),
            "network_state": network_state,
            "execution_results": [],
            "telemetry_data": [],
            "current_step": "start",
            "next_steps": ["parse_intent"],
            "is_completed": False,
            "error": None,
            "reconstruct_count": 0
        }
        
        result = self.workflow.invoke(initial_state, config={"recursion_limit": 25})
        return result
