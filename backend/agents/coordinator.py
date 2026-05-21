from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional, List
from backend.agents.intent_parser import IntentParserAgent
from backend.agents.config_generator import ConfigGeneratorAgent
from backend.agents.config_executor import ConfigExecutorAgent
from backend.agents.validator import ValidatorAgent

class IntentState(TypedDict):
    user_input: str
    structured_intent: Optional[dict]
    config_commands: Optional[List[str]]
    execution_status: Optional[str]
    validation_result: Optional[dict]
    approval_required: bool
    current_step: str

class CoordinatorAgent:
    def __init__(self):
        self.graph = StateGraph(IntentState)
        self._build_graph()
    
    def _build_graph(self):
        self.graph.add_node("parse_intent", self._parse_intent)
        self.graph.add_node("generate_config", self._generate_config)
        self.graph.add_node("validate_config", self._validate_config)
        self.graph.add_node("execute_config", self._execute_config)
        self.graph.add_node("await_approval", self._await_approval)
        
        self.graph.add_edge("parse_intent", "generate_config")
        self.graph.add_edge("generate_config", "validate_config")
        self.graph.add_conditional_edges(
            "validate_config",
            self._should_approve,
            {
                "approve": "execute_config",
                "wait": "await_approval"
            }
        )
        self.graph.add_edge("await_approval", "execute_config")
        self.graph.add_edge("execute_config", END)
        
        self.graph.set_entry_point("parse_intent")
        
        self.app = self.graph.compile()
    
    async def _parse_intent(self, state: IntentState) -> IntentState:
        parser = IntentParserAgent()
        structured_intent = await parser.parse(state["user_input"])
        return {
            **state,
            "structured_intent": structured_intent,
            "current_step": "parse_intent"
        }
    
    async def _generate_config(self, state: IntentState) -> IntentState:
        generator = ConfigGeneratorAgent()
        commands = await generator.generate(state["structured_intent"])
        return {
            **state,
            "config_commands": commands,
            "current_step": "generate_config"
        }
    
    async def _validate_config(self, state: IntentState) -> IntentState:
        validator = ValidatorAgent()
        result = await validator.validate(state["config_commands"], state["structured_intent"])
        return {
            **state,
            "validation_result": result,
            "approval_required": result.get("requires_approval", True),
            "current_step": "validate_config"
        }
    
    def _should_approve(self, state: IntentState) -> str:
        if state["approval_required"] and state["validation_result"].get("status") != "auto_approve":
            return "wait"
        return "approve"
    
    async def _await_approval(self, state: IntentState) -> IntentState:
        return {**state, "current_step": "await_approval"}
    
    async def _execute_config(self, state: IntentState) -> IntentState:
        executor = ConfigExecutorAgent()
        status = await executor.execute(state["config_commands"])
        return {
            **state,
            "execution_status": status,
            "current_step": "execute_config"
        }
    
    async def run(self, user_input: str) -> dict:
        initial_state: IntentState = {
            "user_input": user_input,
            "structured_intent": None,
            "config_commands": None,
            "execution_status": None,
            "validation_result": None,
            "approval_required": False,
            "current_step": "start"
        }
        
        final_state = await self.app.ainvoke(initial_state)
        return dict(final_state)