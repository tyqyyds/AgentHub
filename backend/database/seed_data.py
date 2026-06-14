"""
种子数据模块 - 为各模块初始化演示数据
仅在对应表为空时插入，不会重复插入
"""
import logging
import uuid
import random
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from backend.database.connection import async_session_maker
from backend.database.models import (
    IntentTemplate, GrayscaleHealingTask, HealingEvaluation,
    AgentCapabilityScore, WorkOrder, Playbook, WebhookSubscription,
    SelfHealingEvent, AgentRegistry, AgentHealthRecord, User,
    KnowledgeDocumentVersion, SLAPrediction, FailedIntentCase,
    ProactiveNotification, IntentScheduleRecord, TraceSpan,
    Intent, AuditLog,
)

logger = logging.getLogger(__name__)


def _ts(offset_hours: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=offset_hours)


async def _seed_default_users():
    """创建默认用户（仅当users表为空时）"""
    from backend.core.security.rbac import hash_password
    async with async_session_maker() as session:
        result = await session.execute(select(func.count()).select_from(User))
        count = result.scalar()
        if count and count > 0:
            return
        users = [
            User(username="admin", email="admin@agenthub.local", password_hash=hash_password("Admin@2024!"), role="admin"),
            User(username="operator", email="operator@agenthub.local", password_hash=hash_password("Operator@2024!"), role="operator"),
            User(username="viewer", email="viewer@agenthub.local", password_hash=hash_password("Viewer@2024!"), role="viewer"),
        ]
        session.add_all(users)
        await session.commit()
        logger.info("Seeded %d default users", len(users))


# ─── 知识文档版本 ──────────────────────────────────────────────
async def _seed_knowledge_document_versions():
    if not await _is_empty(KnowledgeDocumentVersion):
        return
    versions = [
        # Doc1: 华为交换机配置指南 (3 versions)
        {"version_id": str(uuid.uuid4()), "document_id": "doc_001", "title": "华为交换机配置指南", "content": "本文档涵盖华为S系列交换机的基础配置方法，包括VLAN划分、端口模式设置、STP配置等核心内容。适用于S5735/S6730等主流型号，提供从初始化到业务上线的完整配置流程。", "version_number": 1, "change_type": "create", "change_summary": "初始创建华为交换机配置指南", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["华为", "交换机", "配置"], "category": "设备配置"}},
        {"version_id": str(uuid.uuid4()), "document_id": "doc_001", "title": "华为交换机配置指南", "content": "本文档涵盖华为S系列交换机的基础配置方法，包括VLAN划分、端口模式设置、STP配置、堆叠配置等核心内容。新增iMaster NCE-Campus联动配置章节，适用于S5735/S6730等主流型号。", "version_number": 2, "change_type": "update", "change_summary": "新增堆叠配置和iMaster NCE联动章节", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["华为", "交换机", "配置", "堆叠"], "category": "设备配置"}},
        {"version_id": str(uuid.uuid4()), "document_id": "doc_001", "title": "华为交换机配置指南", "content": "本文档涵盖华为S系列交换机的基础配置方法，包括VLAN划分、端口模式设置、STP配置、堆叠配置、EVN虚拟化等核心内容。新增VXLAN EVPN配置章节和NetConf自动化配置示例，适用于S5735/S6730等主流型号。", "version_number": 3, "change_type": "minor_edit", "change_summary": "新增VXLAN EVPN配置和NetConf自动化示例", "contributor": "operator", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["华为", "交换机", "VXLAN", "自动化"], "category": "设备配置"}},
        # Doc2: BGP最佳实践 (2 versions)
        {"version_id": str(uuid.uuid4()), "document_id": "doc_002", "title": "BGP最佳实践", "content": "BGP边界网关协议最佳实践指南，涵盖邻居建立、路由策略、属性控制、路由反射器设计等内容。重点介绍企业网与运营商对接的BGP配置规范和常见问题排查方法。", "version_number": 1, "change_type": "create", "change_summary": "初始创建BGP最佳实践文档", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["BGP", "路由", "最佳实践"], "category": "路由协议"}},
        {"version_id": str(uuid.uuid4()), "document_id": "doc_002", "title": "BGP最佳实践", "content": "BGP边界网关协议最佳实践指南，涵盖邻居建立、路由策略、属性控制、路由反射器设计、BGP安全加固等内容。新增RPKI路由源验证和BGPsec配置章节，强化BGP安全防护能力。", "version_number": 2, "change_type": "update", "change_summary": "新增RPKI源验证和BGPsec安全加固章节", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["BGP", "安全", "RPKI", "BGPsec"], "category": "路由协议"}},
        # Doc3: 防火墙策略模板 (2 versions)
        {"version_id": str(uuid.uuid4()), "document_id": "doc_003", "title": "防火墙策略模板", "content": "防火墙安全策略模板集合，包含数据中心边界防护、内网隔离、DMZ区域策略等常见场景的ACL和安全策略模板。支持华为USG系列和山石网科Hillstone系列防火墙。", "version_number": 1, "change_type": "create", "change_summary": "初始创建防火墙策略模板", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["防火墙", "安全策略", "ACL"], "category": "安全防护"}},
        {"version_id": str(uuid.uuid4()), "document_id": "doc_003", "title": "防火墙策略模板", "content": "防火墙安全策略模板集合，包含数据中心边界防护、内网隔离、DMZ区域策略、零信任微隔离等常见场景的ACL和安全策略模板。新增零信任网络访问(ZTNA)策略模板和应用识别配置方法。", "version_number": 2, "change_type": "update", "change_summary": "新增零信任微隔离策略模板和应用识别配置", "contributor": "operator", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["防火墙", "零信任", "ZTNA"], "category": "安全防护"}},
        # Doc4: OSPF路由配置手册 (3 versions)
        {"version_id": str(uuid.uuid4()), "document_id": "doc_004", "title": "OSPF路由配置手册", "content": "OSPF开放最短路径优先协议配置手册，详细说明区域划分、接口配置、路由汇总、LSA类型及过滤等核心配置方法。适用于大规模企业网络的多区域OSPF部署场景。", "version_number": 1, "change_type": "create", "change_summary": "初始创建OSPF路由配置手册", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["OSPF", "路由", "配置手册"], "category": "路由协议"}},
        {"version_id": str(uuid.uuid4()), "document_id": "doc_004", "title": "OSPF路由配置手册", "content": "OSPF开放最短路径优先协议配置手册，详细说明区域划分、接口配置、路由汇总、LSA类型及过滤、OSPFv3 IPv6支持等核心配置方法。新增OSPF与BGP路由互引和路由泄露防护章节。", "version_number": 2, "change_type": "update", "change_summary": "新增OSPFv3 IPv6配置和路由互引章节", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["OSPF", "IPv6", "路由互引"], "category": "路由协议"}},
        {"version_id": str(uuid.uuid4()), "document_id": "doc_004", "title": "OSPF路由配置手册", "content": "OSPF开放最短路径优先协议配置手册，详细说明区域划分、接口配置、路由汇总、LSA类型及过滤、OSPFv3 IPv6支持、GR优雅重启等核心配置方法。新增OSPF GR优雅重启和NSR不间断路由配置，提升网络可靠性。", "version_number": 3, "change_type": "minor_edit", "change_summary": "新增GR优雅重启和NSR不间断路由配置", "contributor": "operator", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["OSPF", "高可用", "GR", "NSR"], "category": "路由协议"}},
        # Doc5: QoS策略参考 (2 versions)
        {"version_id": str(uuid.uuid4()), "document_id": "doc_005", "title": "QoS策略参考", "content": "QoS服务质量策略参考文档，涵盖流量分类、标记、队列调度、拥塞管理和流量整形等关键技术。提供语音、视频、数据业务的差分服务模型配置示例和SLA映射关系。", "version_number": 1, "change_type": "create", "change_summary": "初始创建QoS策略参考文档", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["QoS", "流量管理", "SLA"], "category": "网络保障"}},
        {"version_id": str(uuid.uuid4()), "document_id": "doc_005", "title": "QoS策略参考", "content": "QoS服务质量策略参考文档，涵盖流量分类、标记、队列调度、拥塞管理、流量整形和HQoS层次化QoS等关键技术。新增5G承载网QoS保障方案和SRv6 TE Policy QoS映射配置。", "version_number": 2, "change_type": "update", "change_summary": "新增HQoS层次化QoS和5G承载网QoS方案", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["QoS", "HQoS", "5G", "SRv6"], "category": "网络保障"}},
        # Doc6: 网络故障排查手册 (2 versions)
        {"version_id": str(uuid.uuid4()), "document_id": "doc_006", "title": "网络故障排查手册", "content": "网络故障排查手册，系统化介绍常见网络故障的诊断方法和处理流程。涵盖链路故障、路由异常、性能劣化、安全事件等故障类型的排查步骤和工具使用方法。", "version_number": 1, "change_type": "create", "change_summary": "初始创建网络故障排查手册", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["故障排查", "运维", "诊断"], "category": "故障处理"}},
        {"version_id": str(uuid.uuid4()), "document_id": "doc_006", "title": "网络故障排查手册", "content": "网络故障排查手册，系统化介绍常见网络故障的诊断方法和处理流程。涵盖链路故障、路由异常、性能劣化、安全事件等故障类型的排查步骤和工具使用方法。新增AI辅助故障定位和自动化巡检脚本章节。", "version_number": 2, "change_type": "update", "change_summary": "新增AI辅助故障定位和自动化巡检脚本", "contributor": "operator", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["故障排查", "AI", "自动化"], "category": "故障处理"}},
        # Doc7: SD-WAN部署指南 (2 versions)
        {"version_id": str(uuid.uuid4()), "document_id": "doc_007", "title": "SD-WAN部署指南", "content": "SD-WAN软件定义广域网部署指南，介绍SD-WAN架构设计、Underlay网络规划、Overlay隧道建立、智能选路策略和应用识别等核心部署流程。适用于华为CloudWAN和深信服SD-WAN方案。", "version_number": 1, "change_type": "create", "change_summary": "初始创建SD-WAN部署指南", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["SD-WAN", "广域网", "部署"], "category": "广域网"}},
        {"version_id": str(uuid.uuid4()), "document_id": "doc_007", "title": "SD-WAN部署指南", "content": "SD-WAN软件定义广域网部署指南，介绍SD-WAN架构设计、Underlay网络规划、Overlay隧道建立、智能选路策略、应用识别和安全加密等核心部署流程。新增SASE安全接入服务边缘集成和多云互联方案。", "version_number": 2, "change_type": "update", "change_summary": "新增SASE安全接入和多云互联方案", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["SD-WAN", "SASE", "多云互联"], "category": "广域网"}},
        # Doc8: 安全加固基线 (2 versions)
        {"version_id": str(uuid.uuid4()), "document_id": "doc_008", "title": "安全加固基线", "content": "网络设备安全加固基线标准，涵盖账号管理、访问控制、日志审计、协议安全、补丁管理等安全加固要求。依据等保2.0和CIS Benchmark制定，适用于路由器、交换机、防火墙等网络设备。", "version_number": 1, "change_type": "create", "change_summary": "初始创建安全加固基线文档", "contributor": "admin", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["安全加固", "等保", "基线"], "category": "安全防护"}},
        {"version_id": str(uuid.uuid4()), "document_id": "doc_008", "title": "安全加固基线", "content": "网络设备安全加固基线标准，涵盖账号管理、访问控制、日志审计、协议安全、补丁管理、密码算法等安全加固要求。依据等保2.0三级和CIS Benchmark制定，新增国密算法适配和量子安全准备章节。", "version_number": 2, "change_type": "update", "change_summary": "新增国密算法适配和量子安全准备章节", "contributor": "operator", "content_hash": uuid.uuid4().hex, "meta_data": {"tags": ["安全加固", "国密", "量子安全"], "category": "安全防护"}},
    ]
    async with async_session_maker() as session:
        for v in versions:
            session.add(KnowledgeDocumentVersion(**v))
        await session.commit()
    logger.info(f"Seeded {len(versions)} knowledge document versions")


# ─── SLA预测 ──────────────────────────────────────────────────
async def _seed_sla_predictions():
    if not await _is_empty(SLAPrediction):
        return
    predictions = [
        # 5 predicted_violation=True
        {"intent_id": 1, "predicted_violation": True, "violation_probability": 0.92, "predicted_time": _ts(-2), "prediction_model": "statistical", "confidence": 0.88, "metrics_forecast": {"cpu_usage": {"current": 78, "predicted": 95, "trend": "rising"}, "memory_usage": {"current": 65, "predicted": 82, "trend": "rising"}, "bandwidth_utilization": {"current": 70, "predicted": 92, "trend": "rising"}}},
        {"intent_id": 3, "predicted_violation": True, "violation_probability": 0.85, "predicted_time": _ts(-4), "prediction_model": "ml", "confidence": 0.82, "metrics_forecast": {"cpu_usage": {"current": 82, "predicted": 93, "trend": "rising"}, "bandwidth_utilization": {"current": 88, "predicted": 97, "trend": "rising"}, "packet_loss": {"current": 0.02, "predicted": 0.08, "trend": "rising"}}},
        {"intent_id": 5, "predicted_violation": True, "violation_probability": 0.78, "predicted_time": _ts(-6), "prediction_model": "hybrid", "confidence": 0.75, "metrics_forecast": {"latency_ms": {"current": 15, "predicted": 45, "trend": "rising"}, "jitter_ms": {"current": 3, "predicted": 12, "trend": "rising"}, "bandwidth_utilization": {"current": 75, "predicted": 91, "trend": "rising"}}},
        {"intent_id": 7, "predicted_violation": True, "violation_probability": 0.65, "predicted_time": _ts(-8), "prediction_model": "statistical", "confidence": 0.70, "metrics_forecast": {"memory_usage": {"current": 72, "predicted": 89, "trend": "rising"}, "connection_count": {"current": 6500, "predicted": 9800, "trend": "rising"}}},
        {"intent_id": 9, "predicted_violation": True, "violation_probability": 0.60, "predicted_time": _ts(-10), "prediction_model": "ml", "confidence": 0.65, "metrics_forecast": {"cpu_usage": {"current": 68, "predicted": 88, "trend": "rising"}, "interface_errors": {"current": 50, "predicted": 280, "trend": "rising"}}},
        # 7 predicted_violation=False
        {"intent_id": 2, "predicted_violation": False, "violation_probability": 0.08, "predicted_time": _ts(-1), "prediction_model": "statistical", "confidence": 0.92, "metrics_forecast": {"cpu_usage": {"current": 35, "predicted": 38, "trend": "stable"}, "memory_usage": {"current": 42, "predicted": 45, "trend": "stable"}, "bandwidth_utilization": {"current": 40, "predicted": 43, "trend": "stable"}}},
        {"intent_id": 4, "predicted_violation": False, "violation_probability": 0.12, "predicted_time": _ts(-3), "prediction_model": "hybrid", "confidence": 0.90, "metrics_forecast": {"latency_ms": {"current": 8, "predicted": 9, "trend": "stable"}, "jitter_ms": {"current": 1, "predicted": 1.5, "trend": "stable"}, "packet_loss": {"current": 0.001, "predicted": 0.002, "trend": "stable"}}},
        {"intent_id": 6, "predicted_violation": False, "violation_probability": 0.05, "predicted_time": _ts(-5), "prediction_model": "ml", "confidence": 0.95, "metrics_forecast": {"cpu_usage": {"current": 28, "predicted": 30, "trend": "stable"}, "memory_usage": {"current": 38, "predicted": 40, "trend": "stable"}}},
        {"intent_id": 8, "predicted_violation": False, "violation_probability": 0.18, "predicted_time": _ts(-7), "prediction_model": "statistical", "confidence": 0.85, "metrics_forecast": {"bandwidth_utilization": {"current": 55, "predicted": 58, "trend": "stable"}, "interface_errors": {"current": 5, "predicted": 8, "trend": "stable"}}},
        {"intent_id": 10, "predicted_violation": False, "violation_probability": 0.22, "predicted_time": _ts(-9), "prediction_model": "hybrid", "confidence": 0.80, "metrics_forecast": {"cpu_usage": {"current": 45, "predicted": 50, "trend": "stable"}, "connection_count": {"current": 3200, "predicted": 3800, "trend": "rising"}}},
        {"intent_id": 11, "predicted_violation": False, "violation_probability": 0.35, "predicted_time": _ts(-11), "prediction_model": "ml", "confidence": 0.72, "metrics_forecast": {"memory_usage": {"current": 58, "predicted": 65, "trend": "rising"}, "bandwidth_utilization": {"current": 62, "predicted": 68, "trend": "rising"}}},
        {"intent_id": 12, "predicted_violation": False, "violation_probability": 0.10, "predicted_time": _ts(-12), "prediction_model": "statistical", "confidence": 0.91, "metrics_forecast": {"latency_ms": {"current": 5, "predicted": 6, "trend": "stable"}, "jitter_ms": {"current": 0.8, "predicted": 1.0, "trend": "stable"}}},
    ]
    async with async_session_maker() as session:
        for p in predictions:
            session.add(SLAPrediction(**p))
        await session.commit()
    logger.info(f"Seeded {len(predictions)} SLA predictions")


# ─── 失败意图案例 ──────────────────────────────────────────────
async def _seed_failed_intent_cases():
    if not await _is_empty(FailedIntentCase):
        return
    cases = [
        # 4 resolved
        {"user_input": "帮我处理一下那个网络问题", "parse_method": "llm", "failure_reason": "意图描述模糊无法识别", "raw_response": "{\"intent_type\": null, \"confidence\": 0.15, \"error\": \"无法确定具体意图\"}", "intent_type_attempted": "unknown", "clarification_question": "请问您需要处理哪类网络问题？例如：链路故障、设备配置、性能优化等", "user_clarification": "核心交换机BJ-01的链路中断了", "resolved": True, "resolution_notes": "用户补充信息后成功解析为fault_diagnosis意图", "meta_data": {"retry_count": 1, "original_session": "sess_001"}},
        {"user_input": "配置那个东西", "parse_method": "hybrid", "failure_reason": "缺少必要参数", "raw_response": "{\"intent_type\": \"device_config\", \"confidence\": 0.45, \"missing_params\": [\"device_name\", \"config_type\"]}", "intent_type_attempted": "device_config", "clarification_question": "请指定需要配置的设备名称和配置类型（接口/路由/VLAN/SNMP/NTP）", "user_clarification": "配置核心交换机SH-01的VLAN", "resolved": True, "resolution_notes": "补充设备名称和配置类型后成功执行", "meta_data": {"retry_count": 1, "original_session": "sess_002"}},
        {"user_input": "让网络自己修复所有故障", "parse_method": "llm", "failure_reason": "超出系统能力范围", "raw_response": "{\"intent_type\": \"auto_healing\", \"confidence\": 0.30, \"error\": \"范围过大，无法确定具体操作\"}", "intent_type_attempted": "auto_healing", "clarification_question": "自动修复功能需要指定具体故障类型和设备范围，请描述您遇到的特定故障", "user_clarification": "修复核心交换机BJ-01到SH-01的链路中断", "resolved": True, "resolution_notes": "缩小范围后成功触发自愈流程", "meta_data": {"retry_count": 1, "original_session": "sess_003"}},
        {"user_input": "把所有设备的密码都改成123456", "parse_method": "rule", "failure_reason": "安全策略拦截", "raw_response": "{\"intent_type\": \"device_config\", \"confidence\": 0.80, \"blocked\": true, \"reason\": \"弱密码策略违反安全基线\"}", "intent_type_attempted": "device_config", "clarification_question": "该操作违反安全策略，弱密码不符合安全加固基线要求。是否需要生成符合安全规范的强密码？", "user_clarification": "好的，请生成强密码", "resolved": True, "resolution_notes": "改为生成符合安全规范的随机强密码并批量配置", "meta_data": {"retry_count": 1, "security_intercept": True, "original_session": "sess_004"}},
        # 6 unresolved
        {"user_input": "优化一下网络", "parse_method": "llm", "failure_reason": "意图描述模糊无法识别", "raw_response": "{\"intent_type\": null, \"confidence\": 0.12, \"error\": \"意图过于宽泛，无法确定优化方向\"}", "intent_type_attempted": "unknown", "clarification_question": "请明确优化方向：带宽优化、路由优化、QoS策略优化、还是安全策略优化？", "user_clarification": None, "resolved": False, "resolution_notes": None, "meta_data": {"retry_count": 0, "original_session": "sess_005"}},
        {"user_input": "配置BGP邻居10.0.0.1的remote-as为", "parse_method": "hybrid", "failure_reason": "缺少必要参数", "raw_response": "{\"intent_type\": \"device_config\", \"confidence\": 0.55, \"missing_params\": [\"remote_as\"]}", "intent_type_attempted": "device_config", "clarification_question": "请提供BGP邻居的AS号码", "user_clarification": None, "resolved": False, "resolution_notes": None, "meta_data": {"retry_count": 0, "original_session": "sess_006"}},
        {"user_input": "预测明天的网络会不会出问题", "parse_method": "llm", "failure_reason": "LLM返回格式异常", "raw_response": "根据我的分析，明天网络可能会出现一些问题，建议关注...（非结构化输出）", "intent_type_attempted": "sla_prediction", "clarification_question": "请指定需要预测的具体设备和SLA指标，例如：预测核心路由器GZ-01的CPU使用率趋势", "user_clarification": None, "resolved": False, "resolution_notes": None, "meta_data": {"retry_count": 0, "llm_format_error": True, "original_session": "sess_007"}},
        {"user_input": "重启整个数据中心网络", "parse_method": "rule", "failure_reason": "意图类型不匹配", "raw_response": "{\"intent_type\": \"device_config\", \"confidence\": 0.35, \"error\": \"批量重启操作不属于配置类意图\"}", "intent_type_attempted": "device_config", "clarification_question": "批量重启操作风险极高，需要通过应急响应流程执行。是否需要启动应急响应剧本？", "user_clarification": None, "resolved": False, "resolution_notes": None, "meta_data": {"retry_count": 0, "original_session": "sess_008"}},
        {"user_input": "把防火墙所有规则都删掉重新配", "parse_method": "llm", "failure_reason": "安全策略拦截", "raw_response": "{\"intent_type\": \"device_config\", \"confidence\": 0.70, \"blocked\": true, \"reason\": \"批量删除防火墙规则属于高危操作\"}", "intent_type_attempted": "device_config", "clarification_question": "批量删除防火墙规则属于高危操作，可能导致网络中断。建议使用增量更新方式，是否需要协助制定安全策略更新方案？", "user_clarification": None, "resolved": False, "resolution_notes": None, "meta_data": {"retry_count": 0, "security_intercept": True, "original_session": "sess_009"}},
        {"user_input": "帮我看看交换机怎么回事", "parse_method": "hybrid", "failure_reason": "多意图歧义", "raw_response": "{\"possible_intents\": [\"fault_diagnosis\", \"performance_monitoring\", \"device_config\"], \"confidence\": [0.35, 0.30, 0.25]}", "intent_type_attempted": "fault_diagnosis", "clarification_question": "请明确您的需求：是诊断故障、查看性能、还是修改配置？同时请指定具体的交换机设备名称", "user_clarification": None, "resolved": False, "resolution_notes": None, "meta_data": {"retry_count": 0, "ambiguous_intents": 3, "original_session": "sess_010"}},
    ]
    async with async_session_maker() as session:
        for c in cases:
            session.add(FailedIntentCase(**c))
        await session.commit()
    logger.info(f"Seeded {len(cases)} failed intent cases")


# ─── 主动通知 ──────────────────────────────────────────────────
async def _seed_proactive_notifications():
    if not await _is_empty(ProactiveNotification):
        return
    notifications = [
        # 4 info
        {"notification_id": "ntf_001", "notification_type": "healing_completed", "severity": "info", "title": "自愈任务执行完成", "message": "核心交换机BJ-01链路切换自愈任务已成功执行，当前业务流量已切换到备用链路，链路状态正常", "suggested_action": "确认业务恢复情况，安排主用链路维修", "target_users": ["admin", "operator"], "source_data": {"event_id": 1, "task_id": "gs_a1b2c3d4", "healing_result": "success"}, "is_read": True, "read_by": ["admin"], "dismissed_by": []},
        {"notification_id": "ntf_002", "notification_type": "schedule_reminder", "severity": "info", "title": "定期巡检提醒", "message": "本周数据中心网络设备季度巡检计划已到执行时间，涉及12台核心设备的健康检查和配置审计", "suggested_action": "创建巡检工单并分配执行人员", "target_users": ["operator"], "source_data": {"schedule_type": "quarterly", "device_count": 12}, "is_read": True, "read_by": ["operator"], "dismissed_by": []},
        {"notification_id": "ntf_003", "notification_type": "topology_refresh", "severity": "info", "title": "网络拓扑更新完成", "message": "全网拓扑自动发现已完成，检测到3台新设备上线：SW-CD-06、RT-NJ-05、AP-BJ-20，拓扑数据已更新", "suggested_action": "审核新设备信息并更新资产台账", "target_users": ["admin", "operator"], "source_data": {"new_devices": 3, "updated_links": 8}, "is_read": False, "read_by": [], "dismissed_by": []},
        {"notification_id": "ntf_004", "notification_type": "intent_timeout", "severity": "info", "title": "意图执行超时", "message": "意图'QoS策略部署'(intent_id=15)执行超过预期时间，当前已运行180秒，可能需要人工介入", "suggested_action": "检查执行进度或手动终止意图", "target_users": ["operator"], "source_data": {"intent_id": 15, "elapsed_seconds": 180, "expected_seconds": 60}, "is_read": False, "read_by": [], "dismissed_by": []},
        # 4 warning
        {"notification_id": "ntf_005", "notification_type": "sla_warning", "severity": "warning", "title": "SLA偏离预警", "message": "北京到上海广域网链路延迟持续升高，当前延迟25ms，已偏离SLA目标(≤10ms)，违规概率78%", "suggested_action": "检查链路质量和流量负载，考虑启用备用路径", "target_users": ["admin", "operator"], "source_data": {"intent_id": 5, "current_latency": 25, "sla_target": 10, "violation_probability": 0.78}, "is_read": True, "read_by": ["admin", "operator"], "dismissed_by": []},
        {"notification_id": "ntf_006", "notification_type": "capacity_alert", "severity": "warning", "title": "容量预警", "message": "数据中心核心交换机SH-01端口利用率达到85%，预计2小时内将超过90%阈值", "suggested_action": "评估流量增长趋势，考虑链路扩容或流量调度", "target_users": ["admin"], "source_data": {"device": "SW-SH-01", "current_utilization": 85, "threshold": 90, "eta_hours": 2}, "is_read": False, "read_by": [], "dismissed_by": []},
        {"notification_id": "ntf_007", "notification_type": "agent_degraded", "severity": "warning", "title": "智能体性能降级", "message": "SLA预测智能体(agent_sla_predictor)当前状态为degraded，错误率15%，响应延迟升高", "suggested_action": "检查智能体运行状态和资源使用情况，必要时重启服务", "target_users": ["admin"], "source_data": {"agent_id": "agent_sla_predictor", "status": "degraded", "error_rate": 0.15}, "is_read": False, "read_by": [], "dismissed_by": []},
        {"notification_id": "ntf_008", "notification_type": "config_drift", "severity": "warning", "title": "配置偏移检测", "message": "检测到路由器RT-GZ-01的OSPF配置与基线不一致：区域1的cost值从100变更为200，可能影响路由选路", "suggested_action": "核实配置变更是否为授权操作，非授权变更需回滚", "target_users": ["admin", "operator"], "source_data": {"device": "RT-GZ-01", "config_type": "OSPF", "drift_details": "area 1 cost changed from 100 to 200"}, "is_read": True, "read_by": ["admin"], "dismissed_by": []},
        # 4 critical
        {"notification_id": "ntf_009", "notification_type": "device_anomaly", "severity": "critical", "title": "设备异常告警", "message": "防火墙FW-WH-01内存使用率异常增长至95%，存在内存泄漏风险，可能随时导致服务中断", "suggested_action": "立即启动自愈流程或手动重启防火墙进程", "target_users": ["admin", "operator"], "source_data": {"device": "FW-WH-01", "metric": "memory_usage", "value": 95, "threshold": 90}, "is_read": True, "read_by": ["admin", "operator"], "dismissed_by": []},
        {"notification_id": "ntf_010", "notification_type": "security_alert", "severity": "critical", "title": "安全威胁告警", "message": "检测到来自外网的异常扫描行为，源IP 203.0.113.50对数据中心网段进行端口扫描，已触发DDoS防护规则", "suggested_action": "确认防护规则生效，检查是否有入侵痕迹", "target_users": ["admin"], "source_data": {"source_ip": "203.0.113.50", "target_range": "10.0.0.0/8", "scan_type": "port_scan", "blocked": True}, "is_read": True, "read_by": ["admin"], "dismissed_by": ["operator"]},
        {"notification_id": "ntf_011", "notification_type": "link_degradation", "severity": "critical", "title": "链路质量严重劣化", "message": "北京到广州骨干链路丢包率升至5.2%，延迟波动剧烈，严重影响业务连续性", "suggested_action": "立即切换到备用链路，联系运营商排查线路故障", "target_users": ["admin", "operator"], "source_data": {"link": "BJ-GZ-骨干链路", "packet_loss": 0.052, "latency_ms": 85, "jitter_ms": 35}, "is_read": False, "read_by": [], "dismissed_by": []},
        {"notification_id": "ntf_012", "notification_type": "bgp_anomaly", "severity": "critical", "title": "BGP路由异常", "message": "路由器RT-NJ-02的BGP路由持续震荡，过去1小时内检测到45次路由翻动，影响网络稳定性", "suggested_action": "配置BGP路由阻尼，检查对等体状态和链路质量", "target_users": ["admin", "operator"], "source_data": {"device": "RT-NJ-02", "flap_count": 45, "window_minutes": 60, "affected_prefixes": 128}, "is_read": True, "read_by": ["admin"], "dismissed_by": ["operator"]},
    ]
    async with async_session_maker() as session:
        for n in notifications:
            session.add(ProactiveNotification(**n))
        await session.commit()
    logger.info(f"Seeded {len(notifications)} proactive notifications")


# ─── 意图调度记录 ──────────────────────────────────────────────
async def _seed_intent_schedule_records():
    if not await _is_empty(IntentScheduleRecord):
        return
    records = [
        # 5 queued
        {"intent_id": 20, "priority": 5, "queue_position": 1, "resource_quota": {"cpu_limit": 50, "memory_mb": 512, "timeout_seconds": 120}, "status": "queued", "scheduled_at": _ts(0.5), "started_at": None, "completed_at": None, "preempted_by": None, "preempt_count": 0, "wait_time_ms": 0, "execution_time_ms": 0},
        {"intent_id": 21, "priority": 3, "queue_position": 2, "resource_quota": {"cpu_limit": 30, "memory_mb": 256, "timeout_seconds": 60}, "status": "queued", "scheduled_at": _ts(0.8), "started_at": None, "completed_at": None, "preempted_by": None, "preempt_count": 0, "wait_time_ms": 0, "execution_time_ms": 0},
        {"intent_id": 22, "priority": 7, "queue_position": 3, "resource_quota": {"cpu_limit": 80, "memory_mb": 1024, "timeout_seconds": 300}, "status": "queued", "scheduled_at": _ts(1.2), "started_at": None, "completed_at": None, "preempted_by": None, "preempt_count": 0, "wait_time_ms": 0, "execution_time_ms": 0},
        {"intent_id": 23, "priority": 4, "queue_position": 4, "resource_quota": {"cpu_limit": 40, "memory_mb": 384, "timeout_seconds": 90}, "status": "queued", "scheduled_at": _ts(1.5), "started_at": None, "completed_at": None, "preempted_by": None, "preempt_count": 0, "wait_time_ms": 0, "execution_time_ms": 0},
        {"intent_id": 24, "priority": 6, "queue_position": 5, "resource_quota": {"cpu_limit": 60, "memory_mb": 768, "timeout_seconds": 180}, "status": "queued", "scheduled_at": _ts(2.0), "started_at": None, "completed_at": None, "preempted_by": None, "preempt_count": 0, "wait_time_ms": 0, "execution_time_ms": 0},
        # 3 running
        {"intent_id": 15, "priority": 8, "queue_position": 0, "resource_quota": {"cpu_limit": 70, "memory_mb": 896, "timeout_seconds": 240}, "status": "running", "scheduled_at": _ts(1), "started_at": _ts(0.5), "completed_at": None, "preempted_by": None, "preempt_count": 0, "wait_time_ms": 500, "execution_time_ms": 0},
        {"intent_id": 16, "priority": 9, "queue_position": 0, "resource_quota": {"cpu_limit": 90, "memory_mb": 1280, "timeout_seconds": 600}, "status": "running", "scheduled_at": _ts(0.8), "started_at": _ts(0.3), "completed_at": None, "preempted_by": None, "preempt_count": 0, "wait_time_ms": 300, "execution_time_ms": 0},
        {"intent_id": 17, "priority": 6, "queue_position": 0, "resource_quota": {"cpu_limit": 50, "memory_mb": 512, "timeout_seconds": 120}, "status": "running", "scheduled_at": _ts(0.6), "started_at": _ts(0.2), "completed_at": None, "preempted_by": None, "preempt_count": 0, "wait_time_ms": 400, "execution_time_ms": 0},
        # 4 completed
        {"intent_id": 1, "priority": 10, "queue_position": 0, "resource_quota": {"cpu_limit": 100, "memory_mb": 2048, "timeout_seconds": 600}, "status": "completed", "scheduled_at": _ts(5), "started_at": _ts(4.8), "completed_at": _ts(4.2), "preempted_by": None, "preempt_count": 0, "wait_time_ms": 200, "execution_time_ms": 3600},
        {"intent_id": 3, "priority": 7, "queue_position": 0, "resource_quota": {"cpu_limit": 70, "memory_mb": 896, "timeout_seconds": 300}, "status": "completed", "scheduled_at": _ts(8), "started_at": _ts(7.5), "completed_at": _ts(6.8), "preempted_by": None, "preempt_count": 0, "wait_time_ms": 500, "execution_time_ms": 2520},
        {"intent_id": 5, "priority": 5, "queue_position": 0, "resource_quota": {"cpu_limit": 50, "memory_mb": 512, "timeout_seconds": 120}, "status": "completed", "scheduled_at": _ts(12), "started_at": _ts(11.5), "completed_at": _ts(11.0), "preempted_by": None, "preempt_count": 0, "wait_time_ms": 500, "execution_time_ms": 1800},
        {"intent_id": 8, "priority": 8, "queue_position": 0, "resource_quota": {"cpu_limit": 80, "memory_mb": 1024, "timeout_seconds": 240}, "status": "completed", "scheduled_at": _ts(15), "started_at": _ts(14.8), "completed_at": _ts(14.0), "preempted_by": None, "preempt_count": 0, "wait_time_ms": 200, "execution_time_ms": 2880},
        # 2 preempted
        {"intent_id": 10, "priority": 3, "queue_position": 0, "resource_quota": {"cpu_limit": 40, "memory_mb": 384, "timeout_seconds": 90}, "status": "preempted", "scheduled_at": _ts(3), "started_at": _ts(2.8), "completed_at": None, "preempted_by": 15, "preempt_count": 1, "wait_time_ms": 200, "execution_time_ms": 800},
        {"intent_id": 12, "priority": 2, "queue_position": 0, "resource_quota": {"cpu_limit": 30, "memory_mb": 256, "timeout_seconds": 60}, "status": "preempted", "scheduled_at": _ts(6), "started_at": _ts(5.5), "completed_at": None, "preempted_by": 16, "preempt_count": 2, "wait_time_ms": 500, "execution_time_ms": 1200},
        # 1 failed
        {"intent_id": 14, "priority": 6, "queue_position": 0, "resource_quota": {"cpu_limit": 60, "memory_mb": 768, "timeout_seconds": 180}, "status": "failed", "scheduled_at": _ts(10), "started_at": _ts(9.5), "completed_at": _ts(9.0), "preempted_by": None, "preempt_count": 0, "wait_time_ms": 500, "execution_time_ms": 1800},
    ]
    async with async_session_maker() as session:
        for r in records:
            session.add(IntentScheduleRecord(**r))
        await session.commit()
    logger.info(f"Seeded {len(records)} intent schedule records")


# ─── 链路追踪Span ──────────────────────────────────────────────
async def _seed_trace_spans():
    if not await _is_empty(TraceSpan):
        return
    now = datetime.now(timezone.utc)
    spans = [
        # Trace 1: intent_execute (5 spans)
        {"trace_id": "tr_intent_001", "span_id": "sp_001_1", "parent_span_id": None, "agent_id": "agent_intent_parser", "operation": "intent_execute", "start_time": now - timedelta(seconds=100), "end_time": now - timedelta(seconds=95), "duration_ms": 5000, "status": "ok", "attributes": {"user_input": "为核心交换机BJ-01配置VLAN 100", "intent_type": "device_config", "parse_method": "hybrid"}},
        {"trace_id": "tr_intent_001", "span_id": "sp_001_2", "parent_span_id": "sp_001_1", "agent_id": "agent_intent_parser", "operation": "intent_parse", "start_time": now - timedelta(seconds=99), "end_time": now - timedelta(seconds=97), "duration_ms": 2000, "status": "ok", "attributes": {"model": "deepseek-v3", "tokens_used": 256, "confidence": 0.95}},
        {"trace_id": "tr_intent_001", "span_id": "sp_001_3", "parent_span_id": "sp_001_1", "agent_id": "agent_config_generator", "operation": "config_generate", "start_time": now - timedelta(seconds=96), "end_time": now - timedelta(seconds=94), "duration_ms": 2000, "status": "ok", "attributes": {"device": "SW-BJ-01", "config_type": "VLAN", "template": "vlan_config"}},
        {"trace_id": "tr_intent_001", "span_id": "sp_001_4", "parent_span_id": "sp_001_1", "agent_id": "agent_security_scanner", "operation": "security_check", "start_time": now - timedelta(seconds=94), "end_time": now - timedelta(seconds=93), "duration_ms": 1000, "status": "ok", "attributes": {"check_type": "config_safety", "violations": 0}},
        {"trace_id": "tr_intent_001", "span_id": "sp_001_5", "parent_span_id": "sp_001_1", "agent_id": "agent_healing_executor", "operation": "config_deploy", "start_time": now - timedelta(seconds=93), "end_time": now - timedelta(seconds=90), "duration_ms": 3000, "status": "ok", "attributes": {"device": "SW-BJ-01", "deploy_method": "netconf", "rollback_ready": True}},

        # Trace 2: agent_discover (4 spans)
        {"trace_id": "tr_discover_002", "span_id": "sp_002_1", "parent_span_id": None, "agent_id": "agent_topology_analyzer", "operation": "agent_discover", "start_time": now - timedelta(seconds=80), "end_time": now - timedelta(seconds=70), "duration_ms": 10000, "status": "ok", "attributes": {"scope": "datacenter_bj", "protocol": "lldp+snmp"}},
        {"trace_id": "tr_discover_002", "span_id": "sp_002_2", "parent_span_id": "sp_002_1", "agent_id": "agent_topology_analyzer", "operation": "topology_scan", "start_time": now - timedelta(seconds=79), "end_time": now - timedelta(seconds=74), "duration_ms": 5000, "status": "ok", "attributes": {"devices_found": 28, "links_found": 45}},
        {"trace_id": "tr_discover_002", "span_id": "sp_002_3", "parent_span_id": "sp_002_1", "agent_id": "agent_topology_analyzer", "operation": "topology_analyze", "start_time": now - timedelta(seconds=74), "end_time": now - timedelta(seconds=72), "duration_ms": 2000, "status": "ok", "attributes": {"topology_type": "spine-leaf", "redundancy_level": "full"}},
        {"trace_id": "tr_discover_002", "span_id": "sp_002_4", "parent_span_id": "sp_002_1", "agent_id": "agent_performance_monitor", "operation": "health_collect", "start_time": now - timedelta(seconds=72), "end_time": now - timedelta(seconds=70), "duration_ms": 2000, "status": "ok", "attributes": {"metrics_collected": ["cpu", "memory", "interface"], "device_count": 28}},

        # Trace 3: tool_route (3 spans)
        {"trace_id": "tr_route_003", "span_id": "sp_003_1", "parent_span_id": None, "agent_id": "agent_intent_parser", "operation": "tool_route", "start_time": now - timedelta(seconds=60), "end_time": now - timedelta(seconds=55), "duration_ms": 5000, "status": "ok", "attributes": {"intent_type": "fault_diagnosis", "routing_strategy": "capability_based"}},
        {"trace_id": "tr_route_003", "span_id": "sp_003_2", "parent_span_id": "sp_003_1", "agent_id": "agent_fault_diagnostician", "operation": "fault_diagnose", "start_time": now - timedelta(seconds=59), "end_time": now - timedelta(seconds=56), "duration_ms": 3000, "status": "ok", "attributes": {"device": "RT-GZ-01", "fault_type": "cpu_overload", "root_cause_found": True}},
        {"trace_id": "tr_route_003", "span_id": "sp_003_3", "parent_span_id": "sp_003_1", "agent_id": "agent_healing_executor", "operation": "healing_execute", "start_time": now - timedelta(seconds=56), "end_time": now - timedelta(seconds=55), "duration_ms": 1000, "status": "ok", "attributes": {"action": "route_optimize", "auto_approved": True}},

        # Trace 4: security_scan (6 spans)
        {"trace_id": "tr_sec_004", "span_id": "sp_004_1", "parent_span_id": None, "agent_id": "agent_security_scanner", "operation": "security_scan", "start_time": now - timedelta(seconds=50), "end_time": now - timedelta(seconds=35), "duration_ms": 15000, "status": "ok", "attributes": {"scan_scope": "full_network", "scan_type": "compliance"}},
        {"trace_id": "tr_sec_004", "span_id": "sp_004_2", "parent_span_id": "sp_004_1", "agent_id": "agent_security_scanner", "operation": "port_scan", "start_time": now - timedelta(seconds=49), "end_time": now - timedelta(seconds=45), "duration_ms": 4000, "status": "ok", "attributes": {"devices_scanned": 35, "open_ports_found": 128}},
        {"trace_id": "tr_sec_004", "span_id": "sp_004_3", "parent_span_id": "sp_004_1", "agent_id": "agent_security_scanner", "operation": "vulnerability_detect", "start_time": now - timedelta(seconds=45), "end_time": now - timedelta(seconds=40), "duration_ms": 5000, "status": "ok", "attributes": {"vulnerabilities_found": 3, "severity": ["high", "medium", "low"]}},
        {"trace_id": "tr_sec_004", "span_id": "sp_004_4", "parent_span_id": "sp_004_1", "agent_id": "agent_access_controller", "operation": "acl_audit", "start_time": now - timedelta(seconds=40), "end_time": now - timedelta(seconds=38), "duration_ms": 2000, "status": "ok", "attributes": {"rules_audited": 256, "redundant_rules": 12}},
        {"trace_id": "tr_sec_004", "span_id": "sp_004_5", "parent_span_id": "sp_004_1", "agent_id": "agent_security_scanner", "operation": "baseline_check", "start_time": now - timedelta(seconds=38), "end_time": now - timedelta(seconds=36), "duration_ms": 2000, "status": "error", "attributes": {"error": "设备FW-WH-01无响应，基线检查跳过", "devices_checked": 34, "devices_skipped": 1}},
        {"trace_id": "tr_sec_004", "span_id": "sp_004_6", "parent_span_id": "sp_004_1", "agent_id": "agent_security_scanner", "operation": "report_generate", "start_time": now - timedelta(seconds=36), "end_time": now - timedelta(seconds=35), "duration_ms": 1000, "status": "ok", "attributes": {"report_format": "pdf", "compliance_score": 82}},

        # Trace 5: healing_execute (5 spans)
        {"trace_id": "tr_heal_005", "span_id": "sp_005_1", "parent_span_id": None, "agent_id": "agent_healing_executor", "operation": "healing_execute", "start_time": now - timedelta(seconds=30), "end_time": now - timedelta(seconds=15), "duration_ms": 15000, "status": "ok", "attributes": {"event_type": "link_down", "severity": "critical", "target_device": "SW-BJ-01"}},
        {"trace_id": "tr_heal_005", "span_id": "sp_005_2", "parent_span_id": "sp_005_1", "agent_id": "agent_fault_diagnostician", "operation": "fault_confirm", "start_time": now - timedelta(seconds=29), "end_time": now - timedelta(seconds=27), "duration_ms": 2000, "status": "ok", "attributes": {"fault_confirmed": True, "fault_type": "link_down", "affected_link": "BJ-SH-骨干链路"}},
        {"trace_id": "tr_heal_005", "span_id": "sp_005_3", "parent_span_id": "sp_005_1", "agent_id": "agent_healing_executor", "operation": "canary_healing", "start_time": now - timedelta(seconds=27), "end_time": now - timedelta(seconds=23), "duration_ms": 4000, "status": "ok", "attributes": {"canary_device": "SW-GZ-01", "action": "link_switchover", "result": "success"}},
        {"trace_id": "tr_heal_005", "span_id": "sp_005_4", "parent_span_id": "sp_005_1", "agent_id": "agent_healing_executor", "operation": "batch_healing", "start_time": now - timedelta(seconds=23), "end_time": now - timedelta(seconds=17), "duration_ms": 6000, "status": "ok", "attributes": {"batch_devices": ["SW-BJ-01", "SW-SH-01"], "completed": 2, "failed": 0}},
        {"trace_id": "tr_heal_005", "span_id": "sp_005_5", "parent_span_id": "sp_005_1", "agent_id": "agent_performance_monitor", "operation": "post_healing_verify", "start_time": now - timedelta(seconds=17), "end_time": now - timedelta(seconds=15), "duration_ms": 2000, "status": "ok", "attributes": {"verification_result": "healthy", "metrics_recovered": True}},

        # Trace 6: topology_refresh (7 spans)
        {"trace_id": "tr_topo_006", "span_id": "sp_006_1", "parent_span_id": None, "agent_id": "agent_topology_analyzer", "operation": "topology_refresh", "start_time": now - timedelta(seconds=12), "end_time": now - timedelta(seconds=2), "duration_ms": 10000, "status": "ok", "attributes": {"trigger": "scheduled", "scope": "all_sites"}},
        {"trace_id": "tr_topo_006", "span_id": "sp_006_2", "parent_span_id": "sp_006_1", "agent_id": "agent_topology_analyzer", "operation": "lldp_discover", "start_time": now - timedelta(seconds=11), "end_time": now - timedelta(seconds=8), "duration_ms": 3000, "status": "ok", "attributes": {"neighbors_found": 156, "new_neighbors": 3}},
        {"trace_id": "tr_topo_006", "span_id": "sp_006_3", "parent_span_id": "sp_006_1", "agent_id": "agent_topology_analyzer", "operation": "snmp_collect", "start_time": now - timedelta(seconds=8), "end_time": now - timedelta(seconds=6), "duration_ms": 2000, "status": "ok", "attributes": {"devices_queried": 42, "interfaces_collected": 380}},
        {"trace_id": "tr_topo_006", "span_id": "sp_006_4", "parent_span_id": "sp_006_1", "agent_id": "agent_topology_analyzer", "operation": "topology_merge", "start_time": now - timedelta(seconds=6), "end_time": now - timedelta(seconds=5), "duration_ms": 1000, "status": "ok", "attributes": {"nodes_merged": 45, "links_merged": 78, "conflicts_resolved": 2}},
        {"trace_id": "tr_topo_006", "span_id": "sp_006_5", "parent_span_id": "sp_006_1", "agent_id": "agent_topology_analyzer", "operation": "path_compute", "start_time": now - timedelta(seconds=5), "end_time": now - timedelta(seconds=4), "duration_ms": 1000, "status": "ok", "attributes": {"paths_computed": 120, "redundant_paths": 85}},
        {"trace_id": "tr_topo_006", "span_id": "sp_006_6", "parent_span_id": "sp_006_1", "agent_id": "agent_bandwidth_guarantor", "operation": "sla_validate", "start_time": now - timedelta(seconds=4), "end_time": now - timedelta(seconds=3), "duration_ms": 1000, "status": "ok", "attributes": {"sla_checked": 15, "violations_found": 1}},
        {"trace_id": "tr_topo_006", "span_id": "sp_006_7", "parent_span_id": "sp_006_1", "agent_id": "agent_topology_analyzer", "operation": "topology_persist", "start_time": now - timedelta(seconds=3), "end_time": now - timedelta(seconds=2), "duration_ms": 1000, "status": "ok", "attributes": {"persist_method": "incremental", "records_updated": 123}},
    ]
    async with async_session_maker() as session:
        for s in spans:
            session.add(TraceSpan(**s))
        await session.commit()
    logger.info(f"Seeded {len(spans)} trace spans")


async def seed_all():
    """执行所有种子数据初始化"""
    await _seed_default_users()
    await _seed_intents()
    await _seed_audit_logs()
    await _seed_intent_templates()
    await _seed_self_healing_events()
    await _seed_grayscale_tasks()
    await _seed_agent_scores()
    await _seed_work_orders()
    await _seed_playbooks()
    await _seed_webhooks()
    await _seed_agent_registry()
    await _seed_agent_health_records()
    await _seed_knowledge_document_versions()
    await _seed_sla_predictions()
    await _seed_failed_intent_cases()
    await _seed_proactive_notifications()
    await _seed_intent_schedule_records()
    await _seed_trace_spans()
    logger.info("Seed data initialization complete")


async def _is_empty(model_class) -> bool:
    async with async_session_maker() as session:
        result = await session.execute(select(func.count()).select_from(model_class))
        return result.scalar() == 0


# ─── 意图实例 ────────────────────────────────────────────────
async def _seed_intents():
    if not await _is_empty(Intent):
        return
    intents = [
        {
            "intent_name": "bandwidth_guarantee",
            "user_input": "保障北京到上海骨干链路最小500M带宽",
            "structured_params": {"source": "BJ", "destination": "SH", "bandwidth_mbps": 500, "sla_level": "gold"},
            "approval_status": "approved",
            "execution_status": "completed",
            "sla_conditions": {"availability": 99.99, "latency_ms": 10},
            "sla_status": "achieving",
        },
        {
            "intent_name": "fault_diagnosis",
            "user_input": "诊断核心交换机GZ-01的CPU过载问题",
            "structured_params": {"device_name": "RT-GZ-01", "fault_type": "cpu_overload"},
            "approval_status": "approved",
            "execution_status": "completed",
            "sla_conditions": {"response_time_min": 5},
            "sla_status": "achieving",
        },
        {
            "intent_name": "access_control",
            "user_input": "拒绝192.168.100.0/24到10.0.0.5的TCP访问",
            "structured_params": {"action": "deny", "source": "192.168.100.0/24", "destination": "10.0.0.5", "protocol": "TCP"},
            "approval_status": "pending",
            "execution_status": "pending",
            "sla_conditions": {"deployment_time_min": 10},
            "sla_status": "pending",
        },
        {
            "intent_name": "qos_policy",
            "user_input": "在汇聚交换机SH-03上部署流量整形QoS策略",
            "structured_params": {"device_name": "SW-SH-03", "policy_type": "traffic_shaping", "priority": "high"},
            "approval_status": "approved",
            "execution_status": "running",
            "sla_conditions": {"deployment_time_min": 15},
            "sla_status": "achieving",
        },
        {
            "intent_name": "link_management",
            "user_input": "启用BJ-SH备用链路并配置ECMP负载均衡",
            "structured_params": {"operation": "enable", "link_name": "BJ-SH-backup", "strategy": "ECMP"},
            "approval_status": "rejected",
            "execution_status": "pending",
            "sla_conditions": {"deployment_time_min": 20},
            "sla_status": "pending",
        },
        {
            "intent_name": "performance_monitoring",
            "user_input": "监控核心路由器GZ-01的CPU、内存和接口流量指标",
            "structured_params": {"target": "RT-GZ-01", "metrics": ["CPU", "memory", "interface_traffic"], "interval": 30},
            "approval_status": "approved",
            "execution_status": "completed",
            "sla_conditions": {"response_time_min": 2},
            "sla_status": "achieving",
        },
        {
            "intent_name": "traffic_shaping",
            "user_input": "对BJ-SH骨干链路限速1000Mbps，突发128KB",
            "structured_params": {"link_name": "BJ-SH-backbone", "max_bandwidth": 1000, "burst_size": 128},
            "approval_status": "pending",
            "execution_status": "pending",
            "sla_conditions": {"deployment_time_min": 10},
            "sla_status": "pending",
        },
        {
            "intent_name": "device_config",
            "user_input": "批量配置边缘交换机组VLAN 100 name MGMT",
            "structured_params": {"device_group": "edge-switches", "config_type": "VLAN", "config_content": "VLAN 100 name MGMT"},
            "approval_status": "approved",
            "execution_status": "completed",
            "sla_conditions": {"deployment_time_min": 30},
            "sla_status": "violating",
        },
    ]
    async with async_session_maker() as session:
        for i in intents:
            session.add(Intent(**i))
        await session.commit()
    logger.info(f"Seeded {len(intents)} intents")


# ─── 审计日志 ────────────────────────────────────────────────
async def _seed_audit_logs():
    if not await _is_empty(AuditLog):
        return
    logs = [
        {
            "user_id": "1",
            "action": "提交意图",
            "target_device": "SW-BJ-01",
            "commands": ["configure terminal", "interface GigabitEthernet0/0/1", "bandwidth 500000"],
            "security_type": "normal",
            "status": "success",
            "prompt_tokens": 256,
            "completion_tokens": 128,
            "latency_ms": 1200,
        },
        {
            "user_id": "1",
            "action": "审批意图",
            "target_device": "RT-GZ-01",
            "commands": ["show cpu-usage", "diagnose fault cpu_overload"],
            "security_type": "normal",
            "status": "success",
            "prompt_tokens": 180,
            "completion_tokens": 95,
            "latency_ms": 850,
        },
        {
            "user_id": "2",
            "action": "执行意图",
            "target_device": "FW-WH-01",
            "commands": ["configure terminal", "ip access-list extended BLOCK_TCP", "deny tcp 192.168.100.0 0.0.0.255 host 10.0.0.5"],
            "security_type": "warning",
            "status": "success",
            "prompt_tokens": 320,
            "completion_tokens": 200,
            "latency_ms": 2100,
        },
        {
            "user_id": "2",
            "action": "配置下发",
            "target_device": "SW-SH-03",
            "commands": ["configure terminal", "class-map TRAFFIC_SHAPING", "policy-map QOS_POLICY"],
            "security_type": "normal",
            "status": "success",
            "prompt_tokens": 280,
            "completion_tokens": 150,
            "latency_ms": 1500,
        },
        {
            "user_id": "1",
            "action": "拒绝意图",
            "target_device": "RT-BJ-01",
            "commands": [],
            "security_type": "normal",
            "status": "success",
            "prompt_tokens": 120,
            "completion_tokens": 60,
            "latency_ms": 300,
        },
        {
            "user_id": "1",
            "action": "安全告警",
            "target_device": "SW-CD-03",
            "commands": ["configure terminal", "vlan 100", "name MGMT"],
            "security_type": "critical",
            "status": "failed",
            "prompt_tokens": 200,
            "completion_tokens": 80,
            "latency_ms": 3500,
        },
        {
            "user_id": "2",
            "action": "自愈执行",
            "target_device": "SW-BJ-01",
            "commands": ["configure terminal", "interface GigabitEthernet0/0/2", "no shutdown"],
            "security_type": "normal",
            "status": "success",
            "prompt_tokens": 300,
            "completion_tokens": 180,
            "latency_ms": 2800,
        },
        {
            "user_id": "1",
            "action": "配置回滚",
            "target_device": "FW-WH-01",
            "commands": ["configure replace flash:backup.cfg force"],
            "security_type": "warning",
            "status": "success",
            "prompt_tokens": 250,
            "completion_tokens": 120,
            "latency_ms": 4200,
        },
        {
            "user_id": "1",
            "action": "审批意图(冲突检查)",
            "target_device": "SW-BJ-01",
            "commands": ["show running-config interface Gi0/0/1"],
            "security_type": "normal",
            "status": "success",
            "prompt_tokens": 350,
            "completion_tokens": 200,
            "latency_ms": 1800,
        },
        {
            "user_id": "2",
            "action": "提交意图",
            "target_device": "RT-GZ-01",
            "commands": ["monitor cpu", "monitor memory", "monitor interface traffic interval 30"],
            "security_type": "normal",
            "status": "success",
            "prompt_tokens": 220,
            "completion_tokens": 110,
            "latency_ms": 950,
        },
    ]
    async with async_session_maker() as session:
        for l in logs:
            session.add(AuditLog(**l))
        await session.commit()
    logger.info(f"Seeded {len(logs)} audit logs")


# ─── 意图模板 ────────────────────────────────────────────────
async def _seed_intent_templates():
    if not await _is_empty(IntentTemplate):
        return
    templates = [
        {
            "template_id": "tpl_bandwidth_guarantee",
            "name": "带宽保障",
            "description": "为指定业务流提供端到端带宽保障，支持SLA级别配置",
            "category": "网络保障",
            "intent_type": "bandwidth_guarantee",
            "template_content": "为{source}到{destination}的业务流提供{bandwidth}Mbps带宽保障，SLA级别为{sla_level}",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "源地址"},
                    "destination": {"type": "string", "description": "目的地址"},
                    "bandwidth": {"type": "integer", "description": "带宽(Mbps)", "default": 100},
                    "sla_level": {"type": "string", "enum": ["gold", "silver", "bronze"], "default": "silver"}
                },
                "required": ["source", "destination"]
            },
            "example_values": {"source": "192.168.1.0/24", "destination": "10.0.0.0/8", "bandwidth": 200, "sla_level": "gold"},
            "sla_template": {"availability": 99.99, "latency_ms": 10, "jitter_ms": 2},
            "priority": "high",
            "author": "system",
            "usage_count": 156,
            "rating": 4.8,
            "rating_count": 42,
            "tags": ["带宽", "QoS", "SLA"],
        },
        {
            "template_id": "tpl_fault_diagnosis",
            "name": "故障诊断",
            "description": "自动诊断网络设备故障，定位根因并推荐修复方案",
            "category": "故障处理",
            "intent_type": "fault_diagnosis",
            "template_content": "诊断{device_name}的{fault_type}故障，分析根因并推荐修复方案",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "device_name": {"type": "string", "description": "设备名称"},
                    "fault_type": {"type": "string", "enum": ["链路中断", "CPU过载", "内存溢出", "接口故障", "路由异常"], "description": "故障类型"}
                },
                "required": ["device_name", "fault_type"]
            },
            "example_values": {"device_name": "核心交换机BJ-01", "fault_type": "链路中断"},
            "sla_template": {"response_time_min": 5, "resolution_time_min": 30},
            "priority": "high",
            "author": "system",
            "usage_count": 230,
            "rating": 4.6,
            "rating_count": 58,
            "tags": ["故障", "诊断", "自愈"],
        },
        {
            "template_id": "tpl_qos_policy",
            "name": "QoS策略部署",
            "description": "在指定设备上部署QoS策略，支持流量整形和优先级标记",
            "category": "网络保障",
            "intent_type": "qos_policy",
            "template_content": "在{device_name}上部署QoS策略：{policy_type}，优先级{priority}",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "device_name": {"type": "string", "description": "设备名称"},
                    "policy_type": {"type": "string", "enum": ["流量整形", "优先级标记", "队列调度", "拥塞控制"]},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"], "default": "medium"}
                },
                "required": ["device_name", "policy_type"]
            },
            "example_values": {"device_name": "汇聚交换机SH-03", "policy_type": "流量整形", "priority": "high"},
            "sla_template": {"deployment_time_min": 10},
            "priority": "medium",
            "author": "system",
            "usage_count": 89,
            "rating": 4.3,
            "rating_count": 21,
            "tags": ["QoS", "策略", "流量控制"],
        },
        {
            "template_id": "tpl_traffic_shaping",
            "name": "流量整形",
            "description": "对指定链路进行流量整形，控制带宽使用和突发流量",
            "category": "流量管理",
            "intent_type": "traffic_shaping",
            "template_content": "对{link_name}进行流量整形，限制带宽为{max_bandwidth}Mbps，突发{burst_size}KB",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "link_name": {"type": "string", "description": "链路名称"},
                    "max_bandwidth": {"type": "integer", "description": "最大带宽(Mbps)"},
                    "burst_size": {"type": "integer", "description": "突发大小(KB)", "default": 64}
                },
                "required": ["link_name", "max_bandwidth"]
            },
            "example_values": {"link_name": "BJ-SH-骨干链路", "max_bandwidth": 1000, "burst_size": 128},
            "priority": "medium",
            "author": "system",
            "usage_count": 67,
            "rating": 4.1,
            "rating_count": 15,
            "tags": ["流量", "整形", "带宽控制"],
        },
        {
            "template_id": "tpl_access_control",
            "name": "访问控制",
            "description": "配置ACL访问控制策略，管理网络访问权限",
            "category": "安全管理",
            "intent_type": "access_control",
            "template_content": "配置ACL：{action} {source}到{destination}的{protocol}访问",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["允许", "拒绝"]},
                    "source": {"type": "string", "description": "源地址/网段"},
                    "destination": {"type": "string", "description": "目的地址/网段"},
                    "protocol": {"type": "string", "enum": ["TCP", "UDP", "ICMP", "全部"], "default": "全部"}
                },
                "required": ["action", "source", "destination"]
            },
            "example_values": {"action": "允许", "source": "192.168.1.0/24", "destination": "10.0.0.5", "protocol": "TCP"},
            "priority": "high",
            "author": "system",
            "usage_count": 112,
            "rating": 4.5,
            "rating_count": 33,
            "tags": ["ACL", "安全", "访问控制"],
        },
        {
            "template_id": "tpl_perf_monitor",
            "name": "性能监控",
            "description": "对指定设备或链路设置性能监控任务，持续采集关键指标",
            "category": "监控管理",
            "intent_type": "performance_monitoring",
            "template_content": "对{target}设置性能监控，采集指标：{metrics}，采集间隔{interval}秒",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "监控目标(设备/链路)"},
                    "metrics": {"type": "array", "items": {"type": "string"}, "description": "监控指标列表"},
                    "interval": {"type": "integer", "description": "采集间隔(秒)", "default": 60}
                },
                "required": ["target", "metrics"]
            },
            "example_values": {"target": "核心路由器GZ-01", "metrics": ["CPU", "内存", "接口流量", "丢包率"], "interval": 30},
            "priority": "medium",
            "author": "system",
            "usage_count": 198,
            "rating": 4.7,
            "rating_count": 47,
            "tags": ["监控", "性能", "指标"],
        },
        {
            "template_id": "tpl_link_management",
            "name": "链路管理",
            "description": "管理网络链路状态，支持链路启停和负载均衡配置",
            "category": "网络管理",
            "intent_type": "link_management",
            "template_content": "{operation}链路{link_name}，{details}",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["启用", "禁用", "切换", "负载均衡"]},
                    "link_name": {"type": "string", "description": "链路名称"},
                    "details": {"type": "string", "description": "操作详情"}
                },
                "required": ["operation", "link_name"]
            },
            "example_values": {"operation": "负载均衡", "link_name": "BJ-SH-双链路", "details": "配置ECMP负载均衡"},
            "priority": "medium",
            "author": "system",
            "usage_count": 45,
            "rating": 4.0,
            "rating_count": 12,
            "tags": ["链路", "负载均衡"],
        },
        {
            "template_id": "tpl_device_config",
            "name": "设备配置",
            "description": "批量配置网络设备参数，支持模板化配置下发",
            "category": "配置管理",
            "intent_type": "device_config",
            "template_content": "配置{device_group}的{config_type}参数：{config_content}",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "device_group": {"type": "string", "description": "设备组/名称"},
                    "config_type": {"type": "string", "enum": ["接口", "路由", "VLAN", "SNMP", "NTP"]},
                    "config_content": {"type": "string", "description": "配置内容"}
                },
                "required": ["device_group", "config_type", "config_content"]
            },
            "example_values": {"device_group": "边缘交换机组", "config_type": "VLAN", "config_content": "VLAN 100 name MGMT"},
            "priority": "medium",
            "author": "system",
            "usage_count": 76,
            "rating": 4.2,
            "rating_count": 18,
            "tags": ["配置", "批量", "设备管理"],
        },
    ]
    async with async_session_maker() as session:
        for t in templates:
            session.add(IntentTemplate(**t))
        await session.commit()
    logger.info(f"Seeded {len(templates)} intent templates")


# ─── 自愈事件 (灰度自愈依赖) ──────────────────────────────────
async def _seed_self_healing_events():
    if not await _is_empty(SelfHealingEvent):
        return
    events = [
        {"event_type": "link_down", "severity": "critical", "description": "核心交换机BJ-01到SH-01的骨干链路中断", "suggested_action": "切换到备用链路并重新路由流量", "healing_mode": "auto", "requires_approval": False, "status": "executed", "target_device": "SW-BJ-01", "executed_by": "system"},
        {"event_type": "cpu_overload", "severity": "warning", "description": "路由器GZ-01 CPU使用率持续超过90%", "suggested_action": "优化路由表并清理无效ARP条目", "healing_mode": "suggested", "requires_approval": True, "status": "pending", "target_device": "RT-GZ-01", "executed_by": None},
        {"event_type": "interface_error", "severity": "warning", "description": "交换机CD-03千兆接口GE0/0/1误码率升高", "suggested_action": "重置接口并检查光纤连接", "healing_mode": "suggested", "requires_approval": True, "status": "approved", "target_device": "SW-CD-03", "executed_by": None},
        {"event_type": "memory_leak", "severity": "critical", "description": "防火墙WH-01内存使用率异常增长至95%", "suggested_action": "重启防火墙进程并清理缓存", "healing_mode": "auto", "requires_approval": False, "status": "executed", "target_device": "FW-WH-01", "executed_by": "system"},
        {"event_type": "route_flap", "severity": "medium", "description": "路由器NJ-02 BGP路由持续震荡", "suggested_action": "配置路由阻尼并检查对等体状态", "healing_mode": "suggested", "requires_approval": True, "status": "rejected", "target_device": "RT-NJ-02", "executed_by": None},
    ]
    async with async_session_maker() as session:
        for e in events:
            session.add(SelfHealingEvent(**e))
        await session.commit()
    logger.info(f"Seeded {len(events)} self-healing events")


# ─── 灰度自愈任务 + 评估 ─────────────────────────────────────
async def _seed_grayscale_tasks():
    if not await _is_empty(GrayscaleHealingTask):
        return
    tasks = [
        {
            "task_id": "gs_a1b2c3d4",
            "event_id": 1,
            "target_devices": ["SW-BJ-01", "SW-SH-01", "SW-GZ-01"],
            "canary_device": "SW-GZ-01",
            "canary_status": "success",
            "canary_result": {"device_id": "SW-GZ-01", "action": "切换到备用链路", "status": "executed"},
            "canary_started_at": _ts(5),
            "canary_completed_at": _ts(4.9),
            "batch_status": "success",
            "batch_progress": 100,
            "batch_completed_devices": ["SW-BJ-01", "SW-SH-01"],
            "batch_failed_devices": [],
            "batch_started_at": _ts(4.8),
            "batch_completed_at": _ts(4.5),
            "rollback_triggered": False,
            "overall_status": "batch_success",
            "created_by": "system",
        },
        {
            "task_id": "gs_e5f6g7h8",
            "event_id": 2,
            "target_devices": ["RT-GZ-01", "RT-CD-01"],
            "canary_device": "RT-CD-01",
            "canary_status": "failed",
            "canary_result": {"device_id": "RT-CD-01", "action": "优化路由表", "status": "failed", "error": "设备无响应"},
            "canary_started_at": _ts(2),
            "canary_completed_at": _ts(1.9),
            "batch_status": "pending",
            "batch_progress": 0,
            "rollback_triggered": True,
            "rollback_reason": "Canary device unhealthy after healing",
            "overall_status": "rolled_back",
            "created_by": "admin",
        },
        {
            "task_id": "gs_i9j0k1l2",
            "event_id": 4,
            "target_devices": ["FW-WH-01", "FW-NJ-01"],
            "canary_device": "FW-WH-01",
            "canary_status": "success",
            "canary_result": {"device_id": "FW-WH-01", "action": "重启防火墙进程", "status": "executed"},
            "canary_started_at": _ts(1),
            "canary_completed_at": _ts(0.9),
            "batch_status": "running",
            "batch_progress": 50,
            "batch_completed_devices": ["FW-WH-01"],
            "batch_failed_devices": [],
            "batch_started_at": _ts(0.8),
            "overall_status": "batch_running",
            "created_by": "system",
        },
        {
            "task_id": "gs_m3n4o5p6",
            "event_id": 3,
            "target_devices": ["SW-CD-03", "SW-CD-04", "SW-CD-05"],
            "canary_device": "SW-CD-03",
            "canary_status": "success",
            "canary_result": {"device_id": "SW-CD-03", "action": "重置接口GE0/0/1", "status": "executed"},
            "canary_started_at": _ts(8),
            "canary_completed_at": _ts(7.8),
            "batch_status": "success",
            "batch_progress": 100,
            "batch_completed_devices": ["SW-CD-04", "SW-CD-05"],
            "batch_failed_devices": [],
            "batch_started_at": _ts(7.6),
            "batch_completed_at": _ts(7),
            "rollback_triggered": False,
            "overall_status": "batch_success",
            "created_by": "admin",
        },
        {
            "task_id": "gs_q7r8s9t0",
            "event_id": 5,
            "target_devices": ["RT-NJ-02", "RT-NJ-03"],
            "canary_device": "RT-NJ-02",
            "canary_status": "failed",
            "canary_result": {"device_id": "RT-NJ-02", "action": "配置路由阻尼", "status": "failed", "error": "BGP会话建立失败"},
            "canary_started_at": _ts(3),
            "canary_completed_at": _ts(2.8),
            "batch_status": "pending",
            "batch_progress": 0,
            "rollback_triggered": True,
            "rollback_reason": "BGP对等体状态异常，阻尼配置未生效",
            "overall_status": "rolled_back",
            "created_by": "operator",
        },
        {
            "task_id": "gs_u1v2w3x4",
            "event_id": 1,
            "target_devices": ["SW-BJ-02", "SW-BJ-03", "SW-BJ-04"],
            "canary_device": "SW-BJ-02",
            "canary_status": "success",
            "canary_result": {"device_id": "SW-BJ-02", "action": "切换到备用链路", "status": "executed"},
            "canary_started_at": _ts(12),
            "canary_completed_at": _ts(11.8),
            "batch_status": "success",
            "batch_progress": 100,
            "batch_completed_devices": ["SW-BJ-03", "SW-BJ-04"],
            "batch_failed_devices": [],
            "batch_started_at": _ts(11.5),
            "batch_completed_at": _ts(10.5),
            "rollback_triggered": False,
            "overall_status": "batch_success",
            "created_by": "system",
        },
        {
            "task_id": "gs_y5z6a7b8",
            "event_id": 2,
            "target_devices": ["RT-GZ-01", "RT-GZ-02", "RT-GZ-03"],
            "canary_device": "RT-GZ-02",
            "canary_status": "running",
            "canary_result": None,
            "canary_started_at": _ts(0.3),
            "batch_status": "pending",
            "batch_progress": 0,
            "batch_completed_devices": [],
            "batch_failed_devices": [],
            "rollback_triggered": False,
            "overall_status": "canary_running",
            "created_by": "operator",
        },
        {
            "task_id": "gs_c9d0e1f2",
            "event_id": 4,
            "target_devices": ["FW-WH-01", "FW-CS-01"],
            "canary_device": "FW-CS-01",
            "canary_status": "success",
            "canary_result": {"device_id": "FW-CS-01", "action": "重启防火墙进程并清理缓存", "status": "executed"},
            "canary_started_at": _ts(6),
            "canary_completed_at": _ts(5.7),
            "batch_status": "failed",
            "batch_progress": 50,
            "batch_completed_devices": ["FW-CS-01"],
            "batch_failed_devices": ["FW-WH-01"],
            "batch_started_at": _ts(5.5),
            "batch_completed_at": _ts(5),
            "rollback_triggered": True,
            "rollback_reason": "批量阶段FW-WH-01执行失败，触发自动回滚",
            "overall_status": "rolled_back",
            "created_by": "admin",
        },
        {
            "task_id": "gs_g3h4i5j6",
            "event_id": 3,
            "target_devices": ["SW-CD-03"],
            "canary_device": "SW-CD-03",
            "canary_status": "pending",
            "canary_result": None,
            "batch_status": "pending",
            "batch_progress": 0,
            "batch_completed_devices": [],
            "batch_failed_devices": [],
            "rollback_triggered": False,
            "overall_status": "canary_pending",
            "created_by": "operator",
        },
        {
            "task_id": "gs_k7l8m9n0",
            "event_id": 5,
            "target_devices": ["RT-NJ-02", "RT-NJ-03", "RT-NJ-04"],
            "canary_device": "RT-NJ-03",
            "canary_status": "success",
            "canary_result": {"device_id": "RT-NJ-03", "action": "配置路由阻尼并检查对等体", "status": "executed"},
            "canary_started_at": _ts(15),
            "canary_completed_at": _ts(14.7),
            "batch_status": "running",
            "batch_progress": 33,
            "batch_completed_devices": ["RT-NJ-04"],
            "batch_failed_devices": [],
            "batch_started_at": _ts(14.5),
            "overall_status": "batch_running",
            "created_by": "system",
        },
    ]
    async with async_session_maker() as session:
        for t in tasks:
            session.add(GrayscaleHealingTask(**t))
        await session.commit()
    logger.info(f"Seeded {len(tasks)} grayscale healing tasks")

    # 评估数据
    if not await _is_empty(HealingEvaluation):
        return
    evaluations = [
        {
            "evaluation_id": "eval_m3n4o5p6",
            "event_id": 1,
            "task_id": "gs_a1b2c3d4",
            "metrics_before": {"cpu_usage": 85, "memory_usage": 72, "interface_errors": 150, "status": "unhealthy"},
            "metrics_after": {"cpu_usage": 35, "memory_usage": 48, "interface_errors": 2, "status": "healthy"},
            "healing_action": "切换到备用链路并重新路由流量",
            "effectiveness_score": 0.92,
            "root_cause_analysis": "主用链路光纤衰减过大导致信号丢失，备用链路状态正常",
            "side_effects": [],
            "recommendation": "自愈效果良好，建议保持当前策略并安排主用链路维修",
            "evaluated_at": _ts(4.4),
        },
        {
            "evaluation_id": "eval_q7r8s9t0",
            "event_id": 2,
            "task_id": "gs_e5f6g7h8",
            "metrics_before": {"cpu_usage": 92, "memory_usage": 68, "status": "degraded"},
            "metrics_after": {"cpu_usage": 90, "memory_usage": 70, "status": "degraded"},
            "healing_action": "优化路由表并清理无效ARP条目",
            "effectiveness_score": 0.15,
            "root_cause_analysis": "路由优化未能降低CPU负载，根因可能是BGP邻居过多导致的处理开销",
            "side_effects": ["CPU使用率短暂升高", "部分路由表项丢失"],
            "recommendation": "自愈效果不佳，建议重新评估自愈策略或手动介入，考虑减少BGP邻居数量",
            "evaluated_at": _ts(1.8),
        },
        {
            "evaluation_id": "eval_u1v2w3x4",
            "event_id": 4,
            "task_id": "gs_i9j0k1l2",
            "metrics_before": {"cpu_usage": 45, "memory_usage": 95, "status": "unhealthy"},
            "metrics_after": {"cpu_usage": 30, "memory_usage": 42, "status": "healthy"},
            "healing_action": "重启防火墙进程并清理缓存",
            "effectiveness_score": 0.88,
            "root_cause_analysis": "内存泄漏由特定规则匹配引擎引起，重启后恢复正常",
            "side_effects": [],
            "recommendation": "自愈效果良好，建议升级防火墙固件修复内存泄漏问题",
            "evaluated_at": _ts(0.7),
        },
        {
            "evaluation_id": "eval_a1b2c3d4",
            "event_id": 3,
            "task_id": "gs_m3n4o5p6",
            "metrics_before": {"interface_errors": 230, "packet_loss": 0.12, "link_utilization": 85, "status": "degraded"},
            "metrics_after": {"interface_errors": 5, "packet_loss": 0.001, "link_utilization": 35, "status": "healthy"},
            "healing_action": "重置接口GE0/0/1并检查光纤连接",
            "effectiveness_score": 0.95,
            "root_cause_analysis": "光纤连接器松动导致误码率升高，重置接口后恢复正常",
            "side_effects": ["接口短暂中断约3秒"],
            "recommendation": "自愈效果优秀，建议定期检查光纤连接器紧固状态",
            "evaluated_at": _ts(6.9),
        },
        {
            "evaluation_id": "eval_e5f6g7h8",
            "event_id": 5,
            "task_id": "gs_q7r8s9t0",
            "metrics_before": {"route_flaps": 45, "bgp_peers_down": 3, "convergence_time": 120, "status": "unhealthy"},
            "metrics_after": {"route_flaps": 42, "bgp_peers_down": 3, "convergence_time": 115, "status": "unhealthy"},
            "healing_action": "配置路由阻尼并检查对等体状态",
            "effectiveness_score": 0.08,
            "root_cause_analysis": "BGP对等体持续异常导致阻尼配置无法生效，需要先修复对等体连接",
            "side_effects": ["路由表短暂抖动", "部分前缀撤销"],
            "recommendation": "自愈效果极差，建议先手动修复BGP对等体连接后再尝试阻尼策略",
            "evaluated_at": _ts(2.7),
        },
        {
            "evaluation_id": "eval_i9j0k1l2",
            "event_id": 1,
            "task_id": "gs_u1v2w3x4",
            "metrics_before": {"cpu_usage": 78, "memory_usage": 65, "interface_errors": 80, "status": "degraded"},
            "metrics_after": {"cpu_usage": 28, "memory_usage": 42, "interface_errors": 1, "status": "healthy"},
            "healing_action": "切换到备用链路并重新路由流量",
            "effectiveness_score": 0.90,
            "root_cause_analysis": "链路故障由光模块老化引起，备用链路切换后流量正常",
            "side_effects": [],
            "recommendation": "自愈效果良好，建议更换老化光模块",
            "evaluated_at": _ts(10.4),
        },
        {
            "evaluation_id": "eval_m3n4o5p7",
            "event_id": 4,
            "task_id": "gs_c9d0e1f2",
            "metrics_before": {"cpu_usage": 50, "memory_usage": 93, "connection_count": 8500, "status": "unhealthy"},
            "metrics_after": {"cpu_usage": 48, "memory_usage": 91, "connection_count": 8200, "status": "degraded"},
            "healing_action": "重启防火墙进程并清理缓存",
            "effectiveness_score": 0.25,
            "root_cause_analysis": "FW-WH-01重启后内存未完全释放，可能存在深层内存泄漏，需固件升级",
            "side_effects": ["FW-WH-01重启期间连接中断", "会话表丢失"],
            "recommendation": "自愈效果不佳且产生副作用，建议联系厂商获取固件补丁",
            "evaluated_at": _ts(4.9),
        },
        {
            "evaluation_id": "eval_q7r8s9t1",
            "event_id": 3,
            "task_id": "gs_g3h4i5j6",
            "metrics_before": {"interface_errors": 180, "crc_errors": 45, "status": "degraded"},
            "metrics_after": None,
            "healing_action": "重置接口并检查光纤连接",
            "effectiveness_score": None,
            "root_cause_analysis": None,
            "side_effects": [],
            "recommendation": "任务尚未执行，等待金丝雀阶段完成后评估",
            "evaluated_at": _ts(0.1),
        },
        {
            "evaluation_id": "eval_u1v2w3x5",
            "event_id": 5,
            "task_id": "gs_k7l8m9n0",
            "metrics_before": {"route_flaps": 38, "bgp_peers_down": 2, "convergence_time": 95, "status": "degraded"},
            "metrics_after": {"route_flaps": 12, "bgp_peers_down": 0, "convergence_time": 25, "status": "healthy"},
            "healing_action": "配置路由阻尼并检查对等体状态",
            "effectiveness_score": 0.82,
            "root_cause_analysis": "路由阻尼配置有效抑制了路由震荡，BGP对等体恢复正常",
            "side_effects": ["部分路由暂时被抑制"],
            "recommendation": "自愈效果良好，建议持续监控BGP对等体状态并调整阻尼参数",
            "evaluated_at": _ts(14.2),
        },
        {
            "evaluation_id": "eval_y5z6a7b9",
            "event_id": 2,
            "task_id": "gs_y5z6a7b8",
            "metrics_before": {"cpu_usage": 91, "memory_usage": 70, "arp_entries": 12000, "status": "unhealthy"},
            "metrics_after": None,
            "healing_action": "优化路由表并清理无效ARP条目",
            "effectiveness_score": None,
            "root_cause_analysis": None,
            "side_effects": [],
            "recommendation": "金丝雀阶段执行中，等待完成后评估",
            "evaluated_at": _ts(0.2),
        },
    ]
    async with async_session_maker() as session:
        for ev in evaluations:
            session.add(HealingEvaluation(**ev))
        await session.commit()
    logger.info(f"Seeded {len(evaluations)} healing evaluations")


# ─── Agent评分 ────────────────────────────────────────────────
async def _seed_agent_scores():
    if not await _is_empty(AgentCapabilityScore):
        return
    agents_data = [
        {"agent_id": "agent_bandwidth_guarantor", "success_rate": 0.95, "avg_execution_time_ms": 1200, "resource_efficiency": 0.88, "total_tasks": 156, "successful_tasks": 148, "failed_tasks": 8, "capability_tags": ["bandwidth", "qos", "sla"], "performance_trend": "improving"},
        {"agent_id": "agent_fault_diagnostician", "success_rate": 0.92, "avg_execution_time_ms": 3500, "resource_efficiency": 0.82, "total_tasks": 230, "successful_tasks": 212, "failed_tasks": 18, "capability_tags": ["fault", "diagnosis", "root_cause"], "performance_trend": "stable"},
        {"agent_id": "agent_config_generator", "success_rate": 0.89, "avg_execution_time_ms": 2800, "resource_efficiency": 0.75, "total_tasks": 89, "successful_tasks": 79, "failed_tasks": 10, "capability_tags": ["config", "template", "device"], "performance_trend": "stable"},
        {"agent_id": "agent_security_scanner", "success_rate": 0.97, "avg_execution_time_ms": 800, "resource_efficiency": 0.91, "total_tasks": 312, "successful_tasks": 303, "failed_tasks": 9, "capability_tags": ["security", "scan", "acl"], "performance_trend": "improving"},
        {"agent_id": "agent_healing_executor", "success_rate": 0.85, "avg_execution_time_ms": 4500, "resource_efficiency": 0.70, "total_tasks": 67, "successful_tasks": 57, "failed_tasks": 10, "capability_tags": ["healing", "rollback", "recovery"], "performance_trend": "declining"},
        {"agent_id": "agent_topology_analyzer", "success_rate": 0.93, "avg_execution_time_ms": 1800, "resource_efficiency": 0.85, "total_tasks": 198, "successful_tasks": 184, "failed_tasks": 14, "capability_tags": ["topology", "path", "routing"], "performance_trend": "stable"},
        {"agent_id": "agent_sla_predictor", "success_rate": 0.88, "avg_execution_time_ms": 2200, "resource_efficiency": 0.78, "total_tasks": 145, "successful_tasks": 128, "failed_tasks": 17, "capability_tags": ["sla", "prediction", "monitoring"], "performance_trend": "improving"},
        {"agent_id": "agent_intent_parser", "success_rate": 0.91, "avg_execution_time_ms": 1500, "resource_efficiency": 0.83, "total_tasks": 420, "successful_tasks": 382, "failed_tasks": 38, "capability_tags": ["intent", "nlp", "parse"], "performance_trend": "stable"},
        {"agent_id": "agent_traffic_shaper", "success_rate": 0.94, "avg_execution_time_ms": 900, "resource_efficiency": 0.87, "total_tasks": 178, "successful_tasks": 167, "failed_tasks": 11, "capability_tags": ["traffic", "shaping", "rate_limiting"], "performance_trend": "improving"},
        {"agent_id": "agent_link_manager", "success_rate": 0.90, "avg_execution_time_ms": 2100, "resource_efficiency": 0.80, "total_tasks": 112, "successful_tasks": 101, "failed_tasks": 11, "capability_tags": ["link", "failover", "load_balancing"], "performance_trend": "stable"},
        {"agent_id": "agent_performance_monitor", "success_rate": 0.96, "avg_execution_time_ms": 600, "resource_efficiency": 0.92, "total_tasks": 540, "successful_tasks": 518, "failed_tasks": 22, "capability_tags": ["monitoring", "anomaly", "capacity"], "performance_trend": "improving"},
        {"agent_id": "agent_access_controller", "success_rate": 0.87, "avg_execution_time_ms": 3200, "resource_efficiency": 0.72, "total_tasks": 56, "successful_tasks": 49, "failed_tasks": 7, "capability_tags": ["access", "auth", "policy"], "performance_trend": "declining"},
    ]
    async with async_session_maker() as session:
        for a in agents_data:
            a["last_scored_at"] = _ts(random.randint(0, 24))
            a["score_version"] = random.randint(1, 5)
            session.add(AgentCapabilityScore(**a))
        await session.commit()
    logger.info(f"Seeded {len(agents_data)} agent capability scores")


# ─── 工单 ─────────────────────────────────────────────────────
async def _seed_work_orders():
    if not await _is_empty(WorkOrder):
        return
    orders = [
        {"id": "wo_001", "title": "核心交换机固件升级", "description": "对核心交换机BJ-01和SH-01进行固件升级，修复已知安全漏洞", "status": "pending", "priority": "high", "created_by": "admin", "assigned_to": "operator1", "approval_chain": [{"role": "operator", "status": "pending"}, {"role": "admin", "status": "pending"}], "current_step": 0, "intent_id": None},
        {"id": "wo_002", "title": "新增办公网ACL策略", "description": "为新建办公区域配置网络访问控制策略，限制非授权访问", "status": "approved", "priority": "medium", "created_by": "operator1", "assigned_to": "operator2", "approval_chain": [{"role": "operator", "status": "approved"}, {"role": "admin", "status": "approved"}], "current_step": 2, "intent_id": None},
        {"id": "wo_003", "title": "广域网链路扩容", "description": "北京到上海广域网链路从10G扩容至40G，满足业务增长需求", "status": "executing", "priority": "high", "created_by": "admin", "assigned_to": "operator1", "approval_chain": [{"role": "operator", "status": "approved"}, {"role": "admin", "status": "approved"}], "current_step": 2, "intent_id": None},
        {"id": "wo_004", "title": "数据中心网络设备巡检", "description": "对贵阳数据中心全部网络设备进行季度巡检", "status": "completed", "priority": "low", "created_by": "operator2", "assigned_to": "operator1", "approval_chain": [{"role": "operator", "status": "approved"}, {"role": "admin", "status": "approved"}], "current_step": 2, "intent_id": None, "result": "巡检完成，发现2台设备CPU偏高，已创建自愈事件"},
        {"id": "wo_005", "title": "VPN隧道配置更新", "description": "更新与合作伙伴的IPSec VPN隧道配置，启用新的加密算法", "status": "rejected", "priority": "medium", "created_by": "operator1", "assigned_to": "", "approval_chain": [{"role": "operator", "status": "approved"}, {"role": "admin", "status": "rejected"}], "current_step": 1, "intent_id": None, "reject_reason": "加密算法兼容性未验证，需先在测试环境验证"},
        {"id": "wo_006", "title": "防火墙规则批量更新", "description": "根据安全审计建议，批量更新数据中心防火墙入站规则，封禁高危端口", "status": "pending", "priority": "critical", "created_by": "admin", "assigned_to": "operator1", "approval_chain": [{"role": "operator", "status": "pending"}, {"role": "admin", "status": "pending"}], "current_step": 0, "intent_id": None},
        {"id": "wo_007", "title": "SD-WAN策略优化", "description": "优化全国SD-WAN链路选择策略，提升视频会议业务优先级", "status": "pending", "priority": "medium", "created_by": "operator1", "assigned_to": "operator2", "approval_chain": [{"role": "operator", "status": "pending"}, {"role": "admin", "status": "pending"}], "current_step": 0, "intent_id": None},
        {"id": "wo_008", "title": "核心路由器OSPF重配置", "description": "重新配置核心路由器OSPF区域划分，解决路由环路问题", "status": "approved", "priority": "high", "created_by": "admin", "assigned_to": "operator1", "approval_chain": [{"role": "operator", "status": "approved"}, {"role": "admin", "status": "approved"}], "current_step": 2, "intent_id": "intent_001"},
        {"id": "wo_009", "title": "无线AP固件批量升级", "description": "对园区200+无线AP进行固件批量升级，修复连接稳定性问题", "status": "executing", "priority": "medium", "created_by": "operator2", "assigned_to": "operator1", "approval_chain": [{"role": "operator", "status": "approved"}, {"role": "admin", "status": "approved"}], "current_step": 2, "intent_id": None},
        {"id": "wo_010", "title": "QoS策略调整", "description": "调整生产网QoS策略，保障ERP系统带宽优先级", "status": "completed", "priority": "medium", "created_by": "admin", "assigned_to": "operator2", "approval_chain": [{"role": "operator", "status": "approved"}, {"role": "admin", "status": "approved"}], "current_step": 2, "intent_id": "intent_002", "result": "QoS策略已生效，ERP系统延迟降低40%"},
        {"id": "wo_011", "title": "DDoS防护规则更新", "description": "更新DDoS防护设备清洗规则，应对新型攻击手法", "status": "completed", "priority": "high", "created_by": "admin", "assigned_to": "operator1", "approval_chain": [{"role": "operator", "status": "approved"}, {"role": "admin", "status": "approved"}], "current_step": 2, "intent_id": None, "result": "防护规则已更新，已验证拦截效果"},
        {"id": "wo_012", "title": "网络监控探针部署", "description": "在5个分支机构部署网络性能监控探针，实现端到端可观测性", "status": "rejected", "priority": "low", "created_by": "operator2", "assigned_to": "", "approval_chain": [{"role": "operator", "status": "approved"}, {"role": "admin", "status": "rejected"}], "current_step": 1, "intent_id": None, "reject_reason": "预算未审批，暂缓执行"},
        {"id": "wo_013", "title": "BGP路由策略优化", "description": "优化与3家运营商的BGP路由策略，实现流量智能调度", "status": "pending", "priority": "high", "created_by": "admin", "assigned_to": "operator1", "approval_chain": [{"role": "operator", "status": "pending"}, {"role": "admin", "status": "pending"}], "current_step": 0, "intent_id": None},
        {"id": "wo_014", "title": "容灾切换演练", "description": "组织数据中心容灾切换演练，验证RTO/RPO达标", "status": "approved", "priority": "critical", "created_by": "admin", "assigned_to": "operator2", "approval_chain": [{"role": "operator", "status": "approved"}, {"role": "admin", "status": "approved"}], "current_step": 2, "intent_id": None},
        {"id": "wo_015", "title": "SSL证书批量续期", "description": "对即将到期的15张SSL证书进行批量续期部署", "status": "executing", "priority": "medium", "created_by": "operator1", "assigned_to": "operator1", "approval_chain": [{"role": "operator", "status": "approved"}, {"role": "admin", "status": "approved"}], "current_step": 2, "intent_id": None},
    ]
    async with async_session_maker() as session:
        for o in orders:
            session.add(WorkOrder(**o))
        await session.commit()
    logger.info(f"Seeded {len(orders)} work orders")


# ─── 运维剧本 ─────────────────────────────────────────────────
async def _seed_playbooks():
    if not await _is_empty(Playbook):
        return
    playbooks = [
        {
            "playbook_id": "pb_link_failover",
            "name": "链路故障切换",
            "description": "当主用链路故障时，自动切换到备用链路并验证连通性",
            "category": "故障处理",
            "steps": [
                {"type": "intent", "name": "检测链路状态", "params": {"intent_type": "performance_monitoring", "target": "{{link_name}}"}},
                {"type": "tool_call", "name": "切换备用链路", "params": {"tool": "link_switchover", "device": "{{primary_device}}", "backup_link": "{{backup_link}}"}},
                {"type": "wait", "name": "等待链路稳定", "params": {"duration_seconds": 30}},
                {"type": "intent", "name": "验证连通性", "params": {"intent_type": "fault_diagnosis", "target": "{{backup_link}}"}},
                {"type": "notification", "name": "通知运维团队", "params": {"channel": "webhook", "message": "链路{{link_name}}已切换到{{backup_link}}"}}
            ],
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "link_name": {"type": "string", "description": "故障链路名称"},
                    "primary_device": {"type": "string", "description": "主用设备"},
                    "backup_link": {"type": "string", "description": "备用链路"}
                },
                "required": ["link_name", "primary_device", "backup_link"]
            },
            "is_public": True,
            "author": "system",
            "execution_count": 23,
            "last_execution_status": "success",
            "tags": ["链路", "故障切换", "自愈"],
        },
        {
            "playbook_id": "pb_device_upgrade",
            "name": "设备滚动升级",
            "description": "对一组设备执行滚动升级，确保业务不中断",
            "category": "变更管理",
            "steps": [
                {"type": "approval", "name": "变更审批", "params": {"approvers": ["admin"], "description": "设备升级变更审批"}},
                {"type": "tool_call", "name": "备份当前配置", "params": {"tool": "config_backup", "device": "{{device_group}}"}},
                {"type": "condition", "name": "检查备份状态", "params": {"condition": "backup_status == 'success'", "on_false": "abort"}},
                {"type": "tool_call", "name": "上传固件", "params": {"tool": "firmware_upload", "device": "{{device_group}}", "version": "{{target_version}}"}},
                {"type": "tool_call", "name": "执行升级", "params": {"tool": "firmware_upgrade", "device": "{{device_group}}", "strategy": "rolling"}},
                {"type": "wait", "name": "等待设备重启", "params": {"duration_seconds": 120}},
                {"type": "intent", "name": "验证设备状态", "params": {"intent_type": "performance_monitoring", "target": "{{device_group}}"}},
                {"type": "notification", "name": "通知升级完成", "params": {"channel": "webhook", "message": "设备{{device_group}}已升级到{{target_version}}"}}
            ],
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "device_group": {"type": "string", "description": "设备组名称"},
                    "target_version": {"type": "string", "description": "目标固件版本"}
                },
                "required": ["device_group", "target_version"]
            },
            "is_public": True,
            "author": "system",
            "execution_count": 8,
            "last_execution_status": "success",
            "tags": ["升级", "变更", "滚动"],
        },
        {
            "playbook_id": "pb_security_hardening",
            "name": "安全加固",
            "description": "对网络设备执行安全加固，关闭不必要的服务和端口",
            "category": "安全管理",
            "steps": [
                {"type": "approval", "name": "安全变更审批", "params": {"approvers": ["admin", "security_lead"], "description": "安全加固变更审批"}},
                {"type": "tool_call", "name": "扫描开放端口", "params": {"tool": "port_scan", "device": "{{device_name}}"}},
                {"type": "tool_call", "name": "关闭不必要服务", "params": {"tool": "service_disable", "device": "{{device_name}}", "services": ["telnet", "ftp", "http"]}},
                {"type": "tool_call", "name": "配置SSH访问", "params": {"tool": "ssh_config", "device": "{{device_name}}", "version": "v2"}},
                {"type": "intent", "name": "验证安全状态", "params": {"intent_type": "access_control", "target": "{{device_name}}"}},
                {"type": "notification", "name": "通知安全团队", "params": {"channel": "webhook", "message": "设备{{device_name}}安全加固完成"}}
            ],
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "device_name": {"type": "string", "description": "目标设备名称"}
                },
                "required": ["device_name"]
            },
            "is_public": True,
            "author": "system",
            "execution_count": 15,
            "last_execution_status": "success",
            "tags": ["安全", "加固", "合规"],
        },
        {
            "playbook_id": "pb_emergency_response",
            "name": "应急响应",
            "description": "网络攻击或严重故障时的应急响应流程",
            "category": "应急处理",
            "steps": [
                {"type": "intent", "name": "故障诊断", "params": {"intent_type": "fault_diagnosis", "target": "{{affected_scope}}"}},
                {"type": "tool_call", "name": "隔离受影响区域", "params": {"tool": "network_isolate", "scope": "{{affected_scope}}"}},
                {"type": "approval", "name": "应急操作审批", "params": {"approvers": ["admin"], "description": "紧急隔离操作审批", "timeout_seconds": 300}},
                {"type": "tool_call", "name": "采集取证数据", "params": {"tool": "forensic_collect", "scope": "{{affected_scope}}"}},
                {"type": "notification", "name": "通知安全团队", "params": {"channel": "webhook", "message": "应急响应已启动：{{affected_scope}}"}},
                {"type": "wait", "name": "等待分析结果", "params": {"duration_seconds": 300}},
                {"type": "intent", "name": "恢复验证", "params": {"intent_type": "performance_monitoring", "target": "{{affected_scope}}"}}
            ],
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "affected_scope": {"type": "string", "description": "受影响范围"}
                },
                "required": ["affected_scope"]
            },
            "is_public": True,
            "author": "system",
            "execution_count": 3,
            "last_execution_status": "partial",
            "tags": ["应急", "安全", "响应"],
        },
    ]
    async with async_session_maker() as session:
        for p in playbooks:
            session.add(Playbook(**p))
        await session.commit()
    logger.info(f"Seeded {len(playbooks)} playbooks")


# ─── Webhook订阅 ──────────────────────────────────────────────
async def _seed_webhooks():
    if not await _is_empty(WebhookSubscription):
        return
    subscriptions = [
        {
            "subscription_id": "wh_monitor",
            "name": "监控告警通知",
            "url": "https://monitor.example.com/webhook/alerts",
            "secret": "whsec_monitor_xxx",
            "event_types": ["device.alert", "device.status_changed", "agent.health_changed"],
            "headers": {"X-Source": "AgentHub", "Authorization": "Bearer token_monitor"},
            "is_active": True,
            "retry_policy": {"max_retries": 3, "backoff_seconds": [5, 30, 120]},
            "last_triggered_at": _ts(1),
            "last_status": "success",
            "failure_count": 0,
            "created_by": "admin",
        },
        {
            "subscription_id": "wh_sla",
            "name": "SLA违规告警",
            "url": "https://sla.example.com/webhook/violations",
            "secret": "whsec_sla_xxx",
            "event_types": ["sla.violated", "sla.violation_predicted", "sla.deviating"],
            "headers": {"X-Source": "AgentHub"},
            "is_active": True,
            "retry_policy": {"max_retries": 5, "backoff_seconds": [10, 60, 300, 600, 1800]},
            "last_triggered_at": _ts(6),
            "last_status": "success",
            "failure_count": 1,
            "created_by": "admin",
        },
        {
            "subscription_id": "wh_ci_cd",
            "name": "CI/CD集成",
            "url": "https://cicd.example.com/webhook/deploy",
            "secret": "whsec_cicd_xxx",
            "event_types": ["intent.completed", "intent.failed"],
            "headers": {"X-Source": "AgentHub", "X-Pipeline": "network-ops"},
            "is_active": True,
            "retry_policy": {"max_retries": 2, "backoff_seconds": [5, 30]},
            "last_triggered_at": _ts(12),
            "last_status": "success",
            "failure_count": 0,
            "created_by": "operator1",
        },
        {
            "subscription_id": "wh_healing",
            "name": "自愈事件通知",
            "url": "https://ops.example.com/webhook/healing",
            "secret": "whsec_healing_xxx",
            "event_types": ["healing.started", "healing.completed", "healing.failed"],
            "headers": {"X-Source": "AgentHub"},
            "is_active": False,
            "retry_policy": {"max_retries": 3, "backoff_seconds": [5, 30, 120]},
            "last_triggered_at": _ts(48),
            "last_status": "failed",
            "failure_count": 5,
            "created_by": "admin",
        },
        {
            "subscription_id": "wh_intent_track",
            "name": "意图全生命周期追踪",
            "url": "https://intent.example.com/webhook/lifecycle",
            "secret": "whsec_intent_xxx",
            "event_types": ["intent.created", "intent.completed", "intent.failed"],
            "headers": {"X-Source": "AgentHub", "X-Service": "intent-tracker"},
            "is_active": True,
            "retry_policy": {"max_retries": 3, "backoff_seconds": [5, 30, 120]},
            "last_triggered_at": _ts(2),
            "last_status": "success",
            "failure_count": 0,
            "created_by": "admin",
        },
        {
            "subscription_id": "wh_sla_predict",
            "name": "SLA预测预警",
            "url": "https://sla-predict.example.com/webhook/forecast",
            "secret": "whsec_slapred_xxx",
            "event_types": ["sla.violation_predicted", "sla.deviating", "sla.achieving"],
            "headers": {"X-Source": "AgentHub", "X-Alert-Level": "early-warning"},
            "is_active": True,
            "retry_policy": {"max_retries": 3, "backoff_seconds": [10, 60, 300]},
            "last_triggered_at": _ts(8),
            "last_status": "success",
            "failure_count": 0,
            "created_by": "operator1",
        },
        {
            "subscription_id": "wh_workflow",
            "name": "工单流程联动",
            "url": "https://workflow.example.com/webhook/steps",
            "secret": "whsec_wf_xxx",
            "event_types": ["workflow.step_completed", "workflow.completed"],
            "headers": {"X-Source": "AgentHub", "X-System": "work-order"},
            "is_active": True,
            "retry_policy": {"max_retries": 2, "backoff_seconds": [5, 30]},
            "last_triggered_at": _ts(4),
            "last_status": "success",
            "failure_count": 0,
            "created_by": "admin",
        },
        {
            "subscription_id": "wh_device_alert",
            "name": "设备异常实时告警",
            "url": "https://alert.example.com/webhook/device",
            "secret": "whsec_devalert_xxx",
            "event_types": ["device.alert", "device.status_changed"],
            "headers": {"X-Source": "AgentHub", "X-Priority": "high"},
            "is_active": True,
            "retry_policy": {"max_retries": 5, "backoff_seconds": [5, 15, 60, 180, 600]},
            "last_triggered_at": _ts(3),
            "last_status": "failed",
            "failure_count": 3,
            "created_by": "operator1",
        },
        {
            "subscription_id": "wh_healing_audit",
            "name": "自愈审计归档",
            "url": "https://audit.example.com/webhook/healing-log",
            "secret": "whsec_haudit_xxx",
            "event_types": ["healing.completed", "healing.failed"],
            "headers": {"X-Source": "AgentHub", "X-Archive": "true"},
            "is_active": False,
            "retry_policy": {"max_retries": 1, "backoff_seconds": [30]},
            "last_triggered_at": _ts(72),
            "last_status": "success",
            "failure_count": 0,
            "created_by": "admin",
        },
        {
            "subscription_id": "wh_agent_health",
            "name": "智能体健康监控",
            "url": "https://agent-monitor.example.com/webhook/health",
            "secret": "whsec_aghealth_xxx",
            "event_types": ["agent.health_changed", "device.status_changed"],
            "headers": {"X-Source": "AgentHub"},
            "is_active": True,
            "retry_policy": {"max_retries": 3, "backoff_seconds": [5, 30, 120]},
            "last_triggered_at": _ts(1),
            "last_status": "success",
            "failure_count": 1,
            "created_by": "admin",
        },
    ]
    async with async_session_maker() as session:
        for s in subscriptions:
            session.add(WebhookSubscription(**s))
        await session.commit()
    logger.info(f"Seeded {len(subscriptions)} webhook subscriptions")


# ─── Agent注册表 ──────────────────────────────────────────────
async def _seed_agent_registry():
    if not await _is_empty(AgentRegistry):
        return
    agents = [
        {"agent_id": "agent_bandwidth_guarantor", "domain": "网络保障", "ip": "10.0.1.10", "a2a_endpoint": "http://10.0.1.10:8080/a2a", "capabilities": ["bandwidth_guarantee", "qos_config", "sla_monitoring"], "status": "online"},
        {"agent_id": "agent_fault_diagnostician", "domain": "故障处理", "ip": "10.0.1.11", "a2a_endpoint": "http://10.0.1.11:8080/a2a", "capabilities": ["fault_diagnosis", "root_cause_analysis", "healing_execution"], "status": "online"},
        {"agent_id": "agent_config_generator", "domain": "配置管理", "ip": "10.0.1.12", "a2a_endpoint": "http://10.0.1.12:8080/a2a", "capabilities": ["config_generation", "template_rendering", "device_config"], "status": "online"},
        {"agent_id": "agent_security_scanner", "domain": "安全管理", "ip": "10.0.1.13", "a2a_endpoint": "http://10.0.1.13:8080/a2a", "capabilities": ["security_scan", "acl_management", "vulnerability_detection"], "status": "online"},
        {"agent_id": "agent_healing_executor", "domain": "自愈执行", "ip": "10.0.1.14", "a2a_endpoint": "http://10.0.1.14:8080/a2a", "capabilities": ["healing_execution", "rollback", "grayscale_healing"], "status": "online"},
        {"agent_id": "agent_topology_analyzer", "domain": "拓扑分析", "ip": "10.0.1.15", "a2a_endpoint": "http://10.0.1.15:8080/a2a", "capabilities": ["topology_discovery", "path_analysis", "routing_optimization"], "status": "online"},
        {"agent_id": "agent_sla_predictor", "domain": "SLA预测", "ip": "10.0.1.16", "a2a_endpoint": "http://10.0.1.16:8080/a2a", "capabilities": ["sla_prediction", "violation_forecast", "metric_analysis"], "status": "degraded"},
        {"agent_id": "agent_intent_parser", "domain": "意图解析", "ip": "10.0.1.17", "a2a_endpoint": "http://10.0.1.17:8080/a2a", "capabilities": ["intent_parsing", "nlu", "entity_extraction"], "status": "online"},
        {"agent_id": "agent_traffic_shaper", "domain": "流量整形", "ip": "10.0.1.18", "a2a_endpoint": "http://10.0.1.18:8080/a2a", "capabilities": ["traffic_shaping", "rate_limiting", "congestion_control"], "status": "online"},
        {"agent_id": "agent_link_manager", "domain": "链路管理", "ip": "10.0.1.19", "a2a_endpoint": "http://10.0.1.19:8080/a2a", "capabilities": ["link_management", "failover", "load_balancing"], "status": "online"},
        {"agent_id": "agent_performance_monitor", "domain": "性能监控", "ip": "10.0.1.20", "a2a_endpoint": "http://10.0.1.20:8080/a2a", "capabilities": ["performance_monitoring", "anomaly_detection", "capacity_planning"], "status": "online"},
        {"agent_id": "agent_access_controller", "domain": "访问控制", "ip": "10.0.1.21", "a2a_endpoint": "http://10.0.1.21:8080/a2a", "capabilities": ["access_control", "authentication", "policy_enforcement"], "status": "offline"},
    ]
    async with async_session_maker() as session:
        for a in agents:
            session.add(AgentRegistry(**a))
        await session.commit()
    logger.info(f"Seeded {len(agents)} agent registry entries")


# ─── Agent健康记录 ──────────────────────────────────────────────
async def _seed_agent_health_records():
    if not await _is_empty(AgentHealthRecord):
        return
    records = [
        {"agent_id": "agent_bandwidth_guarantor", "status": "healthy", "latency_p50": 45, "latency_p95": 120, "latency_p99": 250, "error_rate": 0.02, "qps": 35.2, "reasoning_rounds_avg": 1.8, "last_check_time": _ts(0)},
        {"agent_id": "agent_fault_diagnostician", "status": "healthy", "latency_p50": 85, "latency_p95": 320, "latency_p99": 680, "error_rate": 0.05, "qps": 12.8, "reasoning_rounds_avg": 2.4, "last_check_time": _ts(0)},
        {"agent_id": "agent_config_generator", "status": "healthy", "latency_p50": 62, "latency_p95": 180, "latency_p99": 420, "error_rate": 0.08, "qps": 8.5, "reasoning_rounds_avg": 2.1, "last_check_time": _ts(0)},
        {"agent_id": "agent_security_scanner", "status": "healthy", "latency_p50": 28, "latency_p95": 75, "latency_p99": 150, "error_rate": 0.01, "qps": 48.6, "reasoning_rounds_avg": 1.3, "last_check_time": _ts(0)},
        {"agent_id": "agent_healing_executor", "status": "warning", "latency_p50": 120, "latency_p95": 450, "latency_p99": 920, "error_rate": 0.12, "qps": 5.3, "reasoning_rounds_avg": 3.1, "last_check_time": _ts(0)},
        {"agent_id": "agent_topology_analyzer", "status": "healthy", "latency_p50": 55, "latency_p95": 160, "latency_p99": 350, "error_rate": 0.04, "qps": 22.1, "reasoning_rounds_avg": 1.9, "last_check_time": _ts(0)},
        {"agent_id": "agent_sla_predictor", "status": "degraded", "latency_p50": 95, "latency_p95": 380, "latency_p99": 850, "error_rate": 0.15, "qps": 9.7, "reasoning_rounds_avg": 2.8, "last_check_time": _ts(0)},
        {"agent_id": "agent_intent_parser", "status": "healthy", "latency_p50": 38, "latency_p95": 110, "latency_p99": 280, "error_rate": 0.03, "qps": 56.4, "reasoning_rounds_avg": 1.5, "last_check_time": _ts(0)},
        {"agent_id": "agent_traffic_shaper", "status": "healthy", "latency_p50": 32, "latency_p95": 88, "latency_p99": 180, "error_rate": 0.02, "qps": 42.3, "reasoning_rounds_avg": 1.4, "last_check_time": _ts(0)},
        {"agent_id": "agent_link_manager", "status": "healthy", "latency_p50": 72, "latency_p95": 210, "latency_p99": 480, "error_rate": 0.06, "qps": 15.6, "reasoning_rounds_avg": 2.2, "last_check_time": _ts(0)},
        {"agent_id": "agent_performance_monitor", "status": "healthy", "latency_p50": 22, "latency_p95": 58, "latency_p99": 120, "error_rate": 0.01, "qps": 68.9, "reasoning_rounds_avg": 1.2, "last_check_time": _ts(0)},
        {"agent_id": "agent_access_controller", "status": "unhealthy", "latency_p50": 180, "latency_p95": 520, "latency_p99": 1100, "error_rate": 0.22, "qps": 3.1, "reasoning_rounds_avg": 3.5, "last_check_time": _ts(0)},
    ]
    async with async_session_maker() as session:
        for r in records:
            session.add(AgentHealthRecord(**r))
        await session.commit()
    logger.info(f"Seeded {len(records)} agent health records")
