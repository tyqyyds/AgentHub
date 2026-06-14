from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class ToolStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEGRADED = "degraded"
    SKIPPED = "skipped"


class ToolStep(BaseModel):
    step_index: int = Field(..., ge=0)
    tool_name: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[int] = Field(default_factory=list)
    parallel_group: Optional[int] = None
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=2, ge=0)
    fallback_tool: Optional[str] = None
    timeout_seconds: int = Field(default=30, ge=5)
    status: ToolStepStatus = Field(default=ToolStepStatus.PENDING)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ToolChain(BaseModel):
    chain_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(default="")
    steps: List[ToolStep] = Field(..., min_length=1)
    parallel_groups: List[List[int]] = Field(default_factory=list)
    auto_degradation: bool = Field(default=True)


class DAGNode(BaseModel):
    step_index: int
    dependencies: List[int] = Field(default_factory=list)
    dependents: List[int] = Field(default_factory=list)


class DAGAnalysisResult(BaseModel):
    is_valid: bool = True
    has_cycles: bool = False
    parallel_groups: List[List[int]] = Field(default_factory=list)
    execution_order: List[int] = Field(default_factory=list)
    critical_path: List[int] = Field(default_factory=list)


class ToolChainExecutionResult(BaseModel):
    chain_id: str
    status: str
    steps_results: List[Dict[str, Any]] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    success_count: int = 0
    degraded_count: int = 0
    failed_count: int = 0


class PredefinedToolChains:
    @staticmethod
    def fault_auto_healing_chain() -> ToolChain:
        return ToolChain(
            chain_id="fault_auto_healing",
            name="故障自愈链",
            description="自动检测故障并执行自愈恢复",
            auto_degradation=True,
            steps=[
                ToolStep(
                    step_index=0,
                    tool_name="query_topology",
                    params={"filter": "alert"},
                    depends_on=[],
                    parallel_group=0
                ),
                ToolStep(
                    step_index=1,
                    tool_name="get_events",
                    params={"severity": "critical", "limit": 10},
                    depends_on=[],
                    parallel_group=0
                ),
                ToolStep(
                    step_index=2,
                    tool_name="query_device",
                    params={"device_id": "$step0.devices[0].id"},
                    depends_on=[0],
                    fallback_tool="system_health"
                ),
                ToolStep(
                    step_index=3,
                    tool_name="execute_self_healing",
                    params={"event_id": "$step1.events[0].id"},
                    depends_on=[1, 2],
                    max_retries=2,
                    fallback_tool="system_health"
                ),
                ToolStep(
                    step_index=4,
                    tool_name="system_health",
                    params={},
                    depends_on=[3]
                )
            ],
            parallel_groups=[[0, 1]]
        )

    @staticmethod
    def batch_inspection_chain() -> ToolChain:
        return ToolChain(
            chain_id="batch_inspection",
            name="批量巡检链",
            description="并行执行多维度巡检",
            auto_degradation=True,
            steps=[
                ToolStep(
                    step_index=0,
                    tool_name="query_topology",
                    params={},
                    depends_on=[],
                    parallel_group=0
                ),
                ToolStep(
                    step_index=1,
                    tool_name="system_health",
                    params={},
                    depends_on=[],
                    parallel_group=0
                ),
                ToolStep(
                    step_index=2,
                    tool_name="get_events",
                    params={"limit": 50},
                    depends_on=[],
                    parallel_group=0
                ),
                ToolStep(
                    step_index=3,
                    tool_name="get_audit_logs",
                    params={"limit": 20},
                    depends_on=[0, 1, 2]
                )
            ],
            parallel_groups=[[0, 1, 2]]
        )

    @staticmethod
    def change_verification_chain() -> ToolChain:
        return ToolChain(
            chain_id="change_verification",
            name="变更验证链",
            description="执行变更并验证结果",
            auto_degradation=True,
            steps=[
                ToolStep(
                    step_index=0,
                    tool_name="query_device",
                    params={"device_id": "{{target_device}}"},
                    depends_on=[]
                ),
                ToolStep(
                    step_index=1,
                    tool_name="create_intent",
                    params={
                        "name": "config_change",
                        "intent_type": "config_change",
                        "target_devices": ["{{target_device}}"]
                    },
                    depends_on=[0]
                ),
                ToolStep(
                    step_index=2,
                    tool_name="execute_intent",
                    params={"intent_id": "$step1.data.intent_id"},
                    depends_on=[1],
                    max_retries=1,
                    fallback_tool="system_health"
                ),
                ToolStep(
                    step_index=3,
                    tool_name="query_device",
                    params={"device_id": "{{target_device}}"},
                    depends_on=[2]
                ),
                ToolStep(
                    step_index=4,
                    tool_name="system_health",
                    params={},
                    depends_on=[3]
                )
            ]
        )


class ToolChainRegistry:
    def __init__(self):
        self._chains: Dict[str, ToolChain] = {}
        self._register_builtin_chains()

    def _register_builtin_chains(self):
        predefined = PredefinedToolChains()
        self._chains["fault_auto_healing"] = predefined.fault_auto_healing_chain()
        self._chains["batch_inspection"] = predefined.batch_inspection_chain()
        self._chains["change_verification"] = predefined.change_verification_chain()

    def list_chains(self) -> List[ToolChain]:
        return list(self._chains.values())

    def get_chain(self, chain_id: str) -> Optional[ToolChain]:
        return self._chains.get(chain_id)

    def register_chain(self, chain: ToolChain) -> None:
        self._chains[chain.chain_id] = chain
