import pytest
from backend.agents.wizard_templates import (
    WizardTemplate, WizardTemplateLibrary,
    FaultDiagnosisWizard, ChangeImplementationWizard,
    EmergencyResponseWizard, DailyInspectionWizard,
    BatchOperationWizard
)


class TestWizardTemplateLibrary:
    def test_list_all_templates(self):
        lib = WizardTemplateLibrary()
        templates = lib.list_templates()

        assert len(templates) >= 5
        types = {t.wizard_type for t in templates}
        assert "fault_diagnosis" in types
        assert "change_implementation" in types
        assert "emergency_response" in types
        assert "daily_inspection" in types
        assert "batch_operation" in types

    def test_get_template_by_type(self):
        lib = WizardTemplateLibrary()
        template = lib.get_template("fault_diagnosis")

        assert template is not None
        assert template.wizard_type == "fault_diagnosis"
        assert len(template.steps) >= 3

    def test_get_nonexistent_template(self):
        lib = WizardTemplateLibrary()
        template = lib.get_template("nonexistent")
        assert template is None

    def test_instantiate_template_with_params(self):
        lib = WizardTemplateLibrary()
        template = lib.get_template("fault_diagnosis")

        plan = template.instantiate(
            params={"device_name": "核心交换机SW-01", "alert_type": "链路中断"}
        )

        assert plan is not None
        assert "核心交换机SW-01" in plan.goal
        assert len(plan.steps) >= 3


class TestFaultDiagnosisWizard:
    def test_template_structure(self):
        wizard = FaultDiagnosisWizard()
        template = wizard.template

        assert template.wizard_type == "fault_diagnosis"
        assert template.name == "故障排查向导"
        assert len(template.param_schema) >= 1
        assert any(s.tool_name == "query_topology" for s in template.steps)
        assert any(s.tool_name == "query_device" for s in template.steps)


class TestChangeImplementationWizard:
    def test_template_structure(self):
        wizard = ChangeImplementationWizard()
        template = wizard.template

        assert template.wizard_type == "change_implementation"
        assert template.name == "变更实施向导"
        assert any(s.confirm_level.value == "high" for s in template.steps)


class TestEmergencyResponseWizard:
    def test_template_structure(self):
        wizard = EmergencyResponseWizard()
        template = wizard.template

        assert template.wizard_type == "emergency_response"
        assert template.name == "应急响应向导"


class TestDailyInspectionWizard:
    def test_template_structure(self):
        wizard = DailyInspectionWizard()
        template = wizard.template

        assert template.wizard_type == "daily_inspection"
        assert template.name == "日常巡检向导"
        assert any(s.parallel_group is not None for s in template.steps)


class TestBatchOperationWizard:
    def test_template_structure(self):
        wizard = BatchOperationWizard()
        template = wizard.template

        assert template.wizard_type == "batch_operation"
        assert template.name == "批量操作向导"
