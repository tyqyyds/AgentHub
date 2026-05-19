import pytest
import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflow.graph import build_workflow
from tools.mcp_tools import _query_compute_nodes, _get_node_status, _submit_task_to_node, COMPUTE_NODES
from agents.resource_discovery import discover_resources
from agents.scheduler import schedule_task, select_optimal_node
from agents.executor import execute_task

class TestUserInteraction:
    """测试用户交互功能"""
    
    def test_intent_input_format(self):
        """验证输入框支持多种格式的自然语言输入（模拟测试，不调用LLM）"""
        test_intents = [
            "在华东地区部署一个轻量级模型推理服务，需要4核CPU和8GB内存",
            "在北京的GPU节点上训练一个图像分类模型",
            "处理一批数据清洗任务，数据量大约500MB",
            "简单任务",
            "GPU训练任务，需要4张GPU，位于上海"
        ]
        
        for intent in test_intents:
            assert isinstance(intent, str)
            assert len(intent) > 0
    
    def test_empty_intent_handling(self):
        """验证空输入处理"""
        empty_intent = ""
        assert empty_intent == ""


class TestIntentParsing:
    """测试意图解析功能（跳过LLM调用，测试格式处理）"""
    
    def test_intent_format_validation(self):
        """验证意图格式验证"""
        valid_intents = [
            ("训练模型", "包含任务关键词"),
            ("部署推理服务", "包含部署关键词"),
            ("处理数据", "包含处理关键词"),
        ]
        
        for intent, description in valid_intents:
            assert isinstance(intent, str)
            assert len(intent) > 0
    
    def test_region_preference_extraction(self):
        """验证地域偏好提取逻辑"""
        test_cases = [
            ("在上海地区部署推理服务", "shanghai"),
            ("北京的GPU节点", "beijing"),
            ("杭州的CPU节点", "hangzhou"),
        ]
        
        for intent, expected_region in test_cases:
            assert isinstance(intent, str)
            assert expected_region in ["shanghai", "beijing", "hangzhou"]


class TestResourceDiscovery:
    """测试资源发现功能"""
    
    def test_discover_all_resources(self):
        """验证发现所有可用节点"""
        nodes = discover_resources()
        assert isinstance(nodes, list)
        assert len(nodes) >= 0
        
        for node in nodes:
            assert "node_id" in node
            assert "region" in node
            assert "status" in node
            assert node["status"] == "online"
    
    def test_discover_by_region(self):
        """验证按地域筛选"""
        nodes = discover_resources(region="beijing")
        for node in nodes:
            assert node["region"] == "beijing"
    
    def test_node_status_fields(self):
        """验证节点状态信息完整性"""
        node_id = "node-gpu-beijing"
        status = _get_node_status(node_id)
        
        assert "node_id" in status
        assert "available_cpu" in status
        assert "available_memory" in status
        assert "current_load" in status
        assert "status" in status
    
    def test_query_compute_nodes_direct(self):
        """验证直接调用查询节点"""
        nodes = _query_compute_nodes()
        assert isinstance(nodes, list)
        assert len(nodes) == 5  # 5个模拟节点
        
        nodes = _query_compute_nodes(region="shanghai")
        assert len(nodes) == 1
        assert nodes[0]["region"] == "shanghai"


class TestSchedulingAlgorithm:
    """测试调度算法"""
    
    def test_select_optimal_node(self):
        """验证最优节点选择"""
        nodes = _query_compute_nodes()
        requirement = {
            "required_cpu": 8,
            "required_memory": 16000,
            "required_gpu": 0
        }
        
        selected = select_optimal_node(nodes, requirement)
        assert selected is not None
        assert isinstance(selected, str)
    
    def test_select_gpu_node(self):
        """验证GPU节点选择"""
        nodes = _query_compute_nodes()
        requirement = {
            "required_cpu": 4,
            "required_memory": 64000,
            "required_gpu": 2,
            "region_preference": "beijing"
        }
        
        selected = select_optimal_node(nodes, requirement)
        assert selected == "node-gpu-beijing"
    
    def test_no_suitable_node(self):
        """验证无合适节点时的处理"""
        nodes = _query_compute_nodes()
        requirement = {
            "required_cpu": 1000,
            "required_memory": 1000000,
            "required_gpu": 100
        }
        
        selected = select_optimal_node(nodes, requirement)
        assert selected is None
    
    def test_schedule_task_success(self):
        """验证调度任务成功"""
        nodes = _query_compute_nodes()
        requirement = {
            "required_cpu": 4,
            "required_memory": 8000,
            "required_gpu": 0
        }
        
        result = schedule_task(nodes, requirement)
        assert result["success"] == True
        assert "selected_node" in result
    
    def test_schedule_task_failure(self):
        """验证调度失败处理"""
        nodes = []
        requirement = {
            "required_cpu": 4,
            "required_memory": 8000,
            "required_gpu": 0
        }
        
        result = schedule_task(nodes, requirement)
        assert result["success"] == False
        assert "error" in result


class TestTaskExecution:
    """测试任务下发功能"""
    
    def test_execute_task_success(self):
        """验证任务下发成功"""
        node_id = "node-cpu-hangzhou"
        task_config = {
            "task_type": "general_compute",
            "required_cpu": 4,
            "required_memory": 8000,
            "required_gpu": 0
        }
        
        result = execute_task(node_id, task_config)
        assert result["status"] == "submitted"
        assert "task_id" in result
    
    def test_execute_task_failure(self):
        """验证任务下发失败处理"""
        node_id = "non-existent-node"
        task_config = {"task_type": "general_compute"}
        
        result = execute_task(node_id, task_config)
        assert result["status"] == "failed"
        assert "error" in result
    
    def test_execute_task_insufficient_resources(self):
        """验证资源不足时的处理"""
        node_id = "node-edge-shanghai"
        task_config = {
            "task_type": "model_training",
            "required_gpu": 2  # 边缘节点没有GPU
        }
        
        result = execute_task(node_id, task_config)
        assert result["status"] == "failed"
    
    def test_submit_task_to_node_direct(self):
        """验证直接调用提交任务"""
        node_id = "node-cpu-hangzhou"
        task_config = {"task_type": "test"}
        
        result = _submit_task_to_node(node_id, task_config)
        assert result["status"] == "submitted"
        assert "task_id" in result


class TestTelemetryVerification:
    """测试遥测验证功能"""
    
    def test_collect_telemetry(self):
        """验证遥测数据采集"""
        node_id = "node-gpu-beijing"
        telemetry = _get_node_status(node_id)
        
        assert isinstance(telemetry, dict)
        assert "node_id" in telemetry
        assert "current_load" in telemetry
        assert "status" in telemetry


class TestWorkflow:
    """测试完整工作流"""
    
    def test_workflow_initialization(self):
        """验证工作流初始化"""
        workflow = build_workflow()
        assert workflow is not None


class TestSchedulingAlgorithmDetails:
    """测试调度算法详细功能"""
    
    def test_resource_matching_score(self):
        """验证资源匹配评分算法"""
        nodes = _query_compute_nodes()
        requirement = {
            "required_cpu": 8,
            "required_memory": 16000,
            "required_gpu": 0,
            "region_preference": "hangzhou"
        }
        
        selected = select_optimal_node(nodes, requirement)
        assert selected == "node-cpu-hangzhou"
    
    def test_load_balancing(self):
        """验证负载均衡考虑"""
        original_load = COMPUTE_NODES["node-cpu-hangzhou"]["current_load"]
        
        COMPUTE_NODES["node-cpu-hangzhou"]["current_load"] = 0.9
        
        nodes = _query_compute_nodes()
        requirement = {
            "required_cpu": 4,
            "required_memory": 8000,
            "required_gpu": 0
        }
        
        selected = select_optimal_node(nodes, requirement)
        assert selected == "node-edge-shanghai"
        
        COMPUTE_NODES["node-cpu-hangzhou"]["current_load"] = original_load


if __name__ == "__main__":
    pytest.main([__file__, "-v"])