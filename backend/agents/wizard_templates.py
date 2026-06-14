import uuid
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from backend.agents.plan_executor_models import (
    ExecutionPlanModel, PlanStep, ConfirmLevel
)


class WizardParamField(BaseModel):
    name: str
    label: str
    field_type: str = "text"
    required: bool = True
    default: Any = None
    options: List[str] = Field(default_factory=list)


class WizardTemplate(BaseModel):
    wizard_type: str
    name: str
    description: str
    icon: str = "🔧"
    category: str = "general"
    param_schema: List[WizardParamField] = Field(default_factory=list)
    steps: List[PlanStep] = Field(default_factory=list)
    confirm_level: ConfirmLevel = ConfirmLevel.MEDIUM

    def instantiate(self, params: Dict[str, Any]) -> ExecutionPlanModel:
        resolved_steps = []
        for step_template in self.steps:
            resolved_params = {}
            for key, value in step_template.tool_params.items():
                if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                    param_name = value[2:-2].strip()
                    resolved_params[key] = params.get(param_name, value)
                else:
                    resolved_params[key] = value

            try:
                desc = step_template.description.format(**params)
            except (KeyError, IndexError):
                desc = step_template.description

            resolved_steps.append(PlanStep(
                step_index=step_template.step_index,
                description=desc,
                tool_name=step_template.tool_name,
                tool_params=resolved_params,
                confirm_level=step_template.confirm_level,
                condition=step_template.condition,
                parallel_group=step_template.parallel_group,
                fallback_tool=step_template.fallback_tool
            ))

        try:
            goal = self.description.format(**params)
        except (KeyError, IndexError):
            goal = self.description

        return ExecutionPlanModel(
            plan_id=f"plan_{self.wizard_type}_{uuid.uuid4().hex[:8]}",
            goal=goal,
            steps=resolved_steps,
            confirm_level=self.confirm_level
        )


class FaultDiagnosisWizard:
    @property
    def template(self) -> WizardTemplate:
        return WizardTemplate(
            wizard_type="fault_diagnosis",
            name="故障排查向导",
            description="排查 {device_name} 的 {alert_type} 故障",
            icon="🔍",
            category="fault",
            param_schema=[
                WizardParamField(name="device_name", label="设备名称", required=True),
                WizardParamField(name="alert_type", label="告警类型", required=True,
                    options=["链路中断", "CPU过载", "内存不足", "端口Down", "路由异常"]),
                WizardParamField(name="severity", label="严重程度", required=False, default="warning",
                    options=["critical", "warning", "info"])
            ],
            steps=[
                PlanStep(
                    step_index=0,
                    description="查询拓扑定位 {device_name}",
                    tool_name="query_topology",
                    tool_params={"filter": "alert"},
                    confirm_level=ConfirmLevel.LOW,
                    parallel_group=0
                ),
                PlanStep(
                    step_index=1,
                    description="查询 {device_name} 设备详情",
                    tool_name="query_device",
                    tool_params={"device_id": "{{device_name}}"},
                    confirm_level=ConfirmLevel.LOW,
                    parallel_group=0
                ),
                PlanStep(
                    step_index=2,
                    description="获取相关告警事件",
                    tool_name="get_events",
                    tool_params={"severity": "{{severity}}", "limit": 10},
                    confirm_level=ConfirmLevel.LOW
                ),
                PlanStep(
                    step_index=3,
                    description="执行自愈修复",
                    tool_name="execute_self_healing",
                    tool_params={"event_id": "$step2.data.events[0].id"},
                    confirm_level=ConfirmLevel.HIGH,
                    fallback_tool="system_health"
                ),
                PlanStep(
                    step_index=4,
                    description="验证修复结果",
                    tool_name="system_health",
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW
                )
            ],
            confirm_level=ConfirmLevel.HIGH
        )


class ChangeImplementationWizard:
    @property
    def template(self) -> WizardTemplate:
        return WizardTemplate(
            wizard_type="change_implementation",
            name="变更实施向导",
            description="对 {device_name} 实施 {change_type} 变更",
            icon="📝",
            category="change",
            param_schema=[
                WizardParamField(name="device_name", label="目标设备", required=True),
                WizardParamField(name="change_type", label="变更类型", required=True,
                    options=["配置修改", "版本升级", "策略调整", "端口变更"]),
                WizardParamField(name="change_content", label="变更内容", required=True),
                WizardParamField(name="rollback_plan", label="回滚方案", required=False)
            ],
            steps=[
                PlanStep(
                    step_index=0,
                    description="查询 {device_name} 当前状态",
                    tool_name="query_device",
                    tool_params={"device_id": "{{device_name}}"},
                    confirm_level=ConfirmLevel.LOW
                ),
                PlanStep(
                    step_index=1,
                    description="创建变更意图",
                    tool_name="create_intent",
                    tool_params={
                        "name": "{{change_type}}-{{device_name}}",
                        "intent_type": "config_change",
                        "target_devices": ["{{device_name}}"],
                        "parameters": {"change_content": "{{change_content}}"}
                    },
                    confirm_level=ConfirmLevel.MEDIUM
                ),
                PlanStep(
                    step_index=2,
                    description="执行变更",
                    tool_name="execute_intent",
                    tool_params={"intent_id": "$step1.data.intent_id"},
                    confirm_level=ConfirmLevel.HIGH,
                    fallback_tool="system_health"
                ),
                PlanStep(
                    step_index=3,
                    description="验证变更结果",
                    tool_name="system_health",
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW
                )
            ],
            confirm_level=ConfirmLevel.HIGH
        )


class EmergencyResponseWizard:
    @property
    def template(self) -> WizardTemplate:
        return WizardTemplate(
            wizard_type="emergency_response",
            name="应急响应向导",
            description="处理 {device_name} 的 {emergency_type} 紧急事件",
            icon="🚨",
            category="emergency",
            param_schema=[
                WizardParamField(name="device_name", label="故障设备", required=True),
                WizardParamField(name="emergency_type", label="紧急类型", required=True,
                    options=["设备宕机", "链路中断", "安全事件", "性能崩溃"]),
                WizardParamField(name="isolation_required", label="是否需要隔离", required=False, default="false",
                    options=["true", "false"])
            ],
            steps=[
                PlanStep(
                    step_index=0,
                    description="获取全局拓扑和告警",
                    tool_name="query_topology",
                    tool_params={"filter": "alert"},
                    confirm_level=ConfirmLevel.LOW,
                    parallel_group=0
                ),
                PlanStep(
                    step_index=1,
                    description="获取紧急告警列表",
                    tool_name="get_events",
                    tool_params={"severity": "critical", "limit": 20},
                    confirm_level=ConfirmLevel.LOW,
                    parallel_group=0
                ),
                PlanStep(
                    step_index=2,
                    description="查询故障设备详情",
                    tool_name="query_device",
                    tool_params={"device_id": "{{device_name}}"},
                    confirm_level=ConfirmLevel.LOW
                ),
                PlanStep(
                    step_index=3,
                    description="执行自愈恢复",
                    tool_name="execute_self_healing",
                    tool_params={"event_id": "$step1.data.events[0].id"},
                    confirm_level=ConfirmLevel.HIGH,
                    fallback_tool="system_health"
                ),
                PlanStep(
                    step_index=4,
                    description="验证恢复状态",
                    tool_name="system_health",
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW
                )
            ],
            confirm_level=ConfirmLevel.HIGH
        )


class DailyInspectionWizard:
    @property
    def template(self) -> WizardTemplate:
        return WizardTemplate(
            wizard_type="daily_inspection",
            name="日常巡检向导",
            description="执行 {scope} 日常巡检",
            icon="📋",
            category="inspection",
            param_schema=[
                WizardParamField(name="scope", label="巡检范围", required=True,
                    options=["全网", "核心层", "汇聚层", "接入层"]),
                WizardParamField(name="focus", label="关注指标", required=False, default="all",
                    options=["all", "cpu_memory", "link_status", "config_drift"])
            ],
            steps=[
                PlanStep(
                    step_index=0,
                    description="查询全网拓扑状态",
                    tool_name="query_topology",
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW,
                    parallel_group=0
                ),
                PlanStep(
                    step_index=1,
                    description="查询系统健康度",
                    tool_name="system_health",
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW,
                    parallel_group=0
                ),
                PlanStep(
                    step_index=2,
                    description="获取告警概览",
                    tool_name="get_events",
                    tool_params={"limit": 50},
                    confirm_level=ConfirmLevel.LOW
                ),
                PlanStep(
                    step_index=3,
                    description="获取审计日志",
                    tool_name="get_audit_logs",
                    tool_params={"limit": 20},
                    confirm_level=ConfirmLevel.LOW
                )
            ],
            confirm_level=ConfirmLevel.LOW
        )


class BatchOperationWizard:
    @property
    def template(self) -> WizardTemplate:
        return WizardTemplate(
            wizard_type="batch_operation",
            name="批量操作向导",
            description="对 {target_group} 执行 {operation_type} 批量操作",
            icon="⚡",
            category="batch",
            param_schema=[
                WizardParamField(name="target_group", label="目标设备组", required=True),
                WizardParamField(name="operation_type", label="操作类型", required=True,
                    options=["批量巡检", "批量配置", "批量重启", "批量升级"]),
                WizardParamField(name="batch_size", label="批次大小", required=False, default="5")
            ],
            steps=[
                PlanStep(
                    step_index=0,
                    description="查询目标设备组拓扑",
                    tool_name="query_topology",
                    tool_params={"filter": "{{target_group}}"},
                    confirm_level=ConfirmLevel.LOW
                ),
                PlanStep(
                    step_index=1,
                    description="创建批量操作意图",
                    tool_name="create_intent",
                    tool_params={
                        "name": "batch_{{operation_type}}-{{target_group}}",
                        "intent_type": "batch_operation",
                        "target_devices": "$step0.data.devices",
                        "parameters": {
                            "operation": "{{operation_type}}",
                            "batch_size": "{{batch_size}}"
                        }
                    },
                    confirm_level=ConfirmLevel.MEDIUM
                ),
                PlanStep(
                    step_index=2,
                    description="执行批量操作",
                    tool_name="execute_intent",
                    tool_params={"intent_id": "$step1.data.intent_id"},
                    confirm_level=ConfirmLevel.HIGH,
                    fallback_tool="system_health"
                ),
                PlanStep(
                    step_index=3,
                    description="验证批量操作结果",
                    tool_name="system_health",
                    tool_params={},
                    confirm_level=ConfirmLevel.LOW
                )
            ],
            confirm_level=ConfirmLevel.HIGH
        )


class WizardTemplateLibrary:
    def __init__(self):
        self._templates: Dict[str, WizardTemplate] = {}
        self._register_builtin_templates()

    def _register_builtin_templates(self):
        wizards = [
            FaultDiagnosisWizard(),
            ChangeImplementationWizard(),
            EmergencyResponseWizard(),
            DailyInspectionWizard(),
            BatchOperationWizard(),
        ]
        for wizard in wizards:
            template = wizard.template
            self._templates[template.wizard_type] = template

    def list_templates(self) -> List[WizardTemplate]:
        return list(self._templates.values())

    def get_template(self, wizard_type: str) -> Optional[WizardTemplate]:
        return self._templates.get(wizard_type)

    def register_template(self, template: WizardTemplate) -> None:
        self._templates[template.wizard_type] = template
