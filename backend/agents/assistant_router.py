from typing import Dict, Any, List, Optional
import re
import json
import logging
from datetime import datetime, timezone
from backend.agents.intent_classifier import IntentClassifier, IntentType, IntentResult
from backend.agents.dialogue_state import DialogueStateTracker, get_dst

logger = logging.getLogger(__name__)

try:
    from backend.agents.llm_gateway import get_llm_gateway, LLMGateway, TaskType, LLMProvider
    _llm_available = True
except ImportError:
    _llm_available = False
    logger.warning("LLMGateway不可用，将使用规则匹配模式")

NAVIGATION_PATTERNS = [
    (r'(?:去|打开|跳转|导航|我要去|我要看|前往).*(?:指挥舱|首页|仪表盘|dashboard)', '/', '指挥舱'),
    (r'(?:去|打开|跳转|导航|我要去|前往).*(?:意图中心|intent)', '/intent', '意图中心'),
    (r'(?:去|打开|跳转|导航|我要去|我要看|前往).*(?:拓扑|topology)', '/topology', '网络拓扑'),
    (r'(?:去|打开|跳转|导航|我要去|前往).*(?:自愈|故障|healing)', '/self-healing', '故障自愈'),
    (r'(?:去|打开|跳转|导航|我要去|前往).*(?:审计|日志|audit)', '/audit', '审计日志'),
    (r'(?:去|打开|跳转|导航|我要去|前往).*(?:mcp|工具)', '/mcp-tools', 'MCP工具'),
    (r'(?:去|打开|跳转|导航|我要去|我要看|前往).*(?:地图|agent.?map)', '/agent-map', '智能体地图'),
    (r'(?:去|打开|跳转|导航|我要去|前往).*(?:知识|问答|knowledge)', '/knowledge', '运维助手'),
    (r'(?:去|打开|跳转|导航|我要去|前往).*(?:工单|workflow)', '/workflow', '工单看板'),
    (r'(?:查看|看看).*(?:指挥舱|首页|仪表盘|dashboard)', '/', '指挥舱'),
    (r'(?:查看|看看).*(?:拓扑|topology)', '/topology', '网络拓扑'),
    (r'(?:查看|看看).*(?:地图|agent.?map)', '/agent-map', '智能体地图'),
]

QUERY_PATTERNS = [
    (r'(?:健康|状态|运行).*(?:如何|怎样|怎么样)', 'system_health'),
    (r'(?:有多少|有哪些|未处理).*(?:告警|报警|alert)|(?:告警|报警|alert).*(?:多少|有哪些|未处理)', 'pending_alerts'),
    (r'(?:查看|看看|当前|有哪些).*(?:告警|报警|alert|事件)', 'pending_alerts'),
    (r'(?:审批|待办|approve).*(?:多少|有哪些)', 'pending_approvals'),
    (r'(?:查看|看看|当前|有哪些).*(?:意图|intent|审批)', 'pending_approvals'),
    (r'(?:故障|fault).*(?:根因|原因|reason)', 'latest_fault_root_cause'),
    (r'(?:高危|危险).*(?:操作|变更)', 'high_risk_ops'),
    (r'(?:防火墙|firewall).*(?:修改|变更|策略)', 'firewall_policy_changes'),
    (r'(?:流量|traffic).*(?:趋势|统计)', 'traffic_stats'),
    (r'(?:智能体|agent).*(?:分布|状态|多少)', 'agent_distribution'),
    (r'(?:工单|order).*(?:待审批|有哪些|多少)', 'pending_work_orders'),
    (r'(?:工具|tool).*(?:可用|有哪些|列表)', 'available_config_tools'),
    (r'(?:查看|检查|查询|显示|看看).*(?:路由器|交换机|设备|节点|防火墙|服务器).*(?:状态|信息|详情)', 'device_status'),
    (r'(?:路由器|交换机|设备|节点|防火墙|服务器)\s*[A-Za-z0-9\-_]+\s*(?:的)?(?:状态|信息|详情)', 'device_status'),
    (r'(?:查看|看看|当前|有哪些).*(?:审计|日志|audit)', 'audit_logs'),
]

CONTROL_PATTERNS = [
    (r'(?:重启|restart).*(?:路由器|设备|switch|router)', 'restart_device'),
    (r'(?:隔离|isolate).*(?:节点|设备|node)', 'isolate_node'),
    (r'(?:创建|新建|提交).*(?:意图|intent)', 'create_intent'),
    (r'(?:优化|optimize).*(?:带宽|qos|网络)', 'optimize_bandwidth'),
    (r'(?:执行|run).*(?:ping|测试)', 'ping_test'),
    (r'(?:重试|retry).*(?:修复|healing)', 'retry_healing'),
    (r'(?:删除|delete|移除).*(?:意图|intent)', 'delete_intent'),
    (r'(?:关闭|shutdown).*(?:端口|接口|port|interface)', 'shutdown_port'),
    (r'(?:切断|断开).*(?:端口|接口|连接)', 'shutdown_port'),
]

SCENE_MODE_PATTERNS = [
    (r'(?:开启|切换|进入).*(?:应急|紧急|emergency).*(?:模式)?', 'emergency'),
    (r'(?:开启|切换|进入).*(?:日常|巡检|daily|normal).*(?:模式)?', 'daily'),
    (r'(?:开启|切换|进入).*(?:冻结|变更冻结|freeze).*(?:模式)?', 'freeze'),
]

PRONOUN_PATTERNS = [
    (r'^(?:它|他|她|那个|这个|其)$', 'entity_reference'),
    (r'(?:把它|将它|给它)(.+)', 'entity_action'),
    (r'^(?:重启|关闭|隔离|删除|查看|检查|优化|执行)(?:一下|下)?$', 'repeat_action'),
]

ENTITY_PATTERNS = [
    (r'((?:路由器|交换机|防火墙|服务器|设备)\s*[A-Za-z0-9\-_]+)', 'device'),
    (r'((?:节点|node)\s*[A-Za-z0-9\-_]+)', 'node'),
    (r'((?:端口|接口|port|interface)\s*[A-Za-z0-9\/\-_]+)', 'port'),
]

ROUTE_CONTEXT_MAP = {
    '/': {
        'title': '指挥舱', 'icon': '🖥️',
        'description': '实时监控网络健康与关键事件',
        'quick_actions': [
            {'label': '当前系统健康度如何？', 'type': 'query', 'params': {'query': 'system_health'}},
            {'label': '有哪些未处理告警？', 'type': 'query', 'params': {'query': 'pending_alerts'}},
        ]
    },
    '/intent': {
        'title': '意图中心', 'icon': '🎯',
        'description': '用自然语言描述需求，多智能体协同执行',
        'quick_actions': [
            {'label': '创建优化意图', 'type': 'fill_form', 'params': {'route': '/intent', 'field': 'inputText', 'value': '帮我优化网络带宽'}},
            {'label': '查看审批待办', 'type': 'query', 'params': {'query': 'pending_approvals'}},
        ]
    },
    '/topology': {
        'title': '网络拓扑', 'icon': '🔗',
        'description': '可视化展示设备连接与状态',
        'quick_actions': [
            {'label': '高亮故障链路', 'type': 'execute', 'params': {'command': 'highlight_fault_links'}},
            {'label': '查看核心路由器流量', 'type': 'query', 'params': {'query': 'core_router_traffic'}},
        ]
    },
    '/self-healing': {
        'title': '故障自愈', 'icon': '🛡️',
        'description': '自动诊断与修复，降低MTTR',
        'quick_actions': [
            {'label': '最新故障根因', 'type': 'query', 'params': {'query': 'latest_fault_root_cause'}},
            {'label': '重试失败修复任务', 'type': 'execute', 'params': {'command': 'retry_failed_healing'}},
        ]
    },
    '/audit': {
        'title': '审计日志', 'icon': '📋',
        'description': '追踪系统操作与安全事件',
        'quick_actions': [
            {'label': '查询过去1小时高危操作', 'type': 'query', 'params': {'query': 'high_risk_ops_last_hour'}},
            {'label': '谁修改了防火墙策略？', 'type': 'query', 'params': {'query': 'firewall_policy_changes'}},
        ]
    },
    '/mcp-tools': {
        'title': 'MCP工具', 'icon': '🔧',
        'description': '管理与调用底层运维工具',
        'quick_actions': [
            {'label': '执行Ping测试', 'type': 'execute', 'params': {'command': 'ping_test'}},
            {'label': '列出配置工具', 'type': 'query', 'params': {'query': 'available_config_tools'}},
        ]
    },
    '/agent-map': {
        'title': '智能体地图', 'icon': '🌐',
        'description': '全局视角查看智能体分布与路由',
        'quick_actions': [
            {'label': '查看智能体分布', 'type': 'query', 'params': {'query': 'agent_distribution'}},
        ]
    },
    '/knowledge': {
        'title': '运维助手', 'icon': '💡',
        'description': '运维知识问答与文档管理',
        'quick_actions': [
            {'label': '查询运维知识', 'type': 'query', 'params': {'query': 'ops_knowledge'}},
        ]
    },
    '/workflow': {
        'title': '工单看板', 'icon': '📌',
        'description': '管理运维工单与审批流程',
        'quick_actions': [
            {'label': '查看待审批工单', 'type': 'query', 'params': {'query': 'pending_work_orders'}},
        ]
    },
}

ROLE_ACCESS = {
    'admin': ['/', '/intent', '/topology', '/self-healing', '/audit', '/mcp-tools', '/agent-map', '/knowledge', '/workflow'],
    'operator': ['/', '/intent', '/topology', '/self-healing', '/mcp-tools', '/agent-map', '/knowledge', '/workflow'],
    'viewer': ['/', '/topology', '/knowledge'],
}

DANGER_COMMANDS = {'restart_device', 'isolate_node', 'shutdown_port', 'delete_intent'}


class ConversationMemory:
    def __init__(self, max_turns: int = 20):
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._entities: Dict[str, Dict[str, Any]] = {}
        self._last_mentioned: Dict[str, str] = {}
        self._last_intent: Dict[str, Dict[str, Any]] = {}
        self._max_turns = max_turns

    def add_turn(self, username: str, role: str, content: str, intent_type: str = None, entities: Dict[str, Any] = None, session_id: str = None):
        if username not in self._history:
            self._history[username] = []
        self._history[username].append({
            'role': role,
            'content': content,
            'intent_type': intent_type,
            'entities': entities or {},
            'session_id': session_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        if len(self._history[username]) > self._max_turns:
            self._history[username] = self._history[username][-self._max_turns:]

    def set_entity(self, username: str, entity_type: str, entity_value: str):
        if username not in self._entities:
            self._entities[username] = {}
        self._entities[username][entity_type] = entity_value
        self._last_mentioned[username] = entity_value

    def get_entities(self, username: str) -> Dict[str, Any]:
        return self._entities.get(username, {})

    def get_last_mentioned(self, username: str) -> Optional[str]:
        return self._last_mentioned.get(username)

    def set_last_intent(self, username: str, intent: Dict[str, Any]):
        self._last_intent[username] = intent

    def get_last_intent(self, username: str) -> Optional[Dict[str, Any]]:
        return self._last_intent.get(username)

    def get_recent_messages(self, username: str, count: int = 10) -> List[Dict[str, Any]]:
        history = self._history.get(username, [])
        return history[-count:] if history else []

    def resolve_pronoun(self, username: str, message: str) -> str:
        last_mentioned = self.get_last_mentioned(username)
        last_intent = self.get_last_intent(username)
        resolved = message

        for pattern, ptype in PRONOUN_PATTERNS:
            match = re.search(pattern, message)
            if match:
                if ptype == 'entity_reference' and last_mentioned:
                    resolved = f"查看{last_mentioned}的状态"
                elif ptype == 'entity_action' and last_mentioned:
                    action = match.group(1)
                    action = re.sub(r'(一下|下|了)$', '', action)
                    resolved = f"{action}{last_mentioned}"
                elif ptype == 'repeat_action' and last_intent:
                    command = last_intent.get('command', '')
                    target = last_mentioned or ''
                    if command and target:
                        resolved = f"{command}{target}"
                break

        return resolved

    def extract_entities(self, message: str) -> Dict[str, str]:
        entities = {}
        for pattern, etype in ENTITY_PATTERNS:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                entities[etype] = match.group(1)
        return entities


class AssistantRouterAgent:
    def __init__(self):
        self._memory = ConversationMemory()
        self._query_handlers: Dict[str, Any] = {}
        self._control_handlers: Dict[str, Any] = {}
        self._fallback_query_handlers: Dict[str, Any] = {
            'latest_fault_root_cause': self._query_fault_root_cause,
            'high_risk_ops_last_hour': self._query_high_risk_ops,
            'firewall_policy_changes': self._query_firewall_changes,
            'traffic_stats': self._query_traffic_stats,
            'pending_work_orders': self._query_pending_work_orders,
            'available_config_tools': self._query_config_tools,
            'ops_knowledge': self._query_ops_knowledge,
        }
        self._scene_mode: str = 'daily'
        self._intent_classifier = IntentClassifier()
        self._dst = get_dst()
        self._llm: Optional[LLMGateway] = None
        if _llm_available:
            try:
                self._llm = get_llm_gateway()
                if self._llm.zhipu.available:
                    logger.info("AssistantRouterAgent已接入智谱LLM，智能回复模式已启用")
                else:
                    logger.info("智谱LLM不可用，降级为规则匹配模式")
            except Exception as e:
                logger.warning(f"LLMGateway初始化失败: {e}，降级为规则匹配模式")
                self._llm = None

    def register_query_handler(self, query_type: str, handler):
        self._query_handlers[query_type] = handler

    def register_control_handler(self, command: str, handler):
        self._control_handlers[command] = handler

    def set_scene_mode(self, mode: str):
        if mode in ('daily', 'emergency', 'freeze'):
            self._scene_mode = mode

    def get_scene_mode(self) -> str:
        return self._scene_mode

    async def route(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        role = context.get('role', 'viewer')
        username = context.get('username', 'unknown')
        route = context.get('route', '/')
        # 优先使用内部场景模式状态（由场景切换命令设置），context仅作为初始值
        scene_mode = self._scene_mode if self._scene_mode != 'daily' else context.get('scene_mode', self._scene_mode)

        resolved_message = self._memory.resolve_pronoun(username, message)
        session_id = context.get('session_id', f'{username}_default')
        self._dst.update(session_id, message, '', intent_type=None, username=username)
        entities = self._memory.extract_entities(resolved_message)
        for etype, evalue in entities.items():
            self._memory.set_entity(username, etype, evalue)

        self._memory.add_turn(username, 'user', resolved_message, entities=entities)

        scene_result = self._check_scene_mode(resolved_message)
        if scene_result:
            self._dst.update(session_id, '', scene_result.get('content', ''), intent_type=scene_result.get('intent_type'), username=username)
            self._memory.add_turn(username, 'assistant', scene_result['content'], intent_type=scene_result.get('intent_type'))
            return scene_result

        plan_result = self._check_plan_execute(resolved_message)
        if plan_result:
            self._dst.update(session_id, '', plan_result.get('content', ''), intent_type=plan_result.get('intent_type'), username=username)
            self._memory.add_turn(username, 'assistant', plan_result['content'], intent_type=plan_result.get('intent_type'))
            return plan_result

        proactive_result = self._check_proactive_query(resolved_message)
        if proactive_result:
            self._dst.update(session_id, '', proactive_result.get('content', ''), intent_type=proactive_result.get('intent_type'), username=username)
            self._memory.add_turn(username, 'assistant', proactive_result['content'], intent_type=proactive_result.get('intent_type'))
            return proactive_result

        wizard_result = self._check_wizard(resolved_message)
        if wizard_result:
            self._dst.update(session_id, '', wizard_result.get('content', ''), intent_type=wizard_result.get('intent_type'), username=username)
            self._memory.add_turn(username, 'assistant', wizard_result['content'], intent_type=wizard_result.get('intent_type'))
            return wizard_result

        feedback_result = self._check_feedback(resolved_message)
        if feedback_result:
            self._dst.update(session_id, '', feedback_result.get('content', ''), intent_type=feedback_result.get('intent_type'), username=username)
            self._memory.add_turn(username, 'assistant', feedback_result['content'], intent_type=feedback_result.get('intent_type'))
            return feedback_result

        multimodal_result = self._check_multimodal(resolved_message)
        if multimodal_result:
            self._dst.update(session_id, '', multimodal_result.get('content', ''), intent_type=multimodal_result.get('intent_type'), username=username)
            self._memory.add_turn(username, 'assistant', multimodal_result['content'], intent_type=multimodal_result.get('intent_type'))
            return multimodal_result

        # 查询检查优先于导航检查，避免"查看告警"被误识别为导航
        query_result = await self._check_query(resolved_message, role, username)
        if query_result:
            if self._llm and self._llm.zhipu.available:
                try:
                    enhanced = await self._llm_enhance_query_result(
                        query_result.get('content', ''), resolved_message, username
                    )
                    query_result['content'] = enhanced
                except Exception as e:
                    logger.warning(f"LLM query enhancement failed: {e}")
            self._memory.add_turn(username, 'assistant', query_result['content'], intent_type=query_result.get('intent_type'))
            self._dst.update(session_id, '', query_result.get('content', ''), intent_type=query_result.get('intent_type'), username=username)
            return query_result

        nav_result = self._check_navigation(resolved_message, role)
        if nav_result:
            self._dst.update(session_id, '', nav_result.get('content', ''), intent_type=nav_result.get('intent_type'), username=username)
            self._memory.add_turn(username, 'assistant', nav_result['content'], intent_type=nav_result.get('intent_type'))
            return nav_result

        control_result = await self._check_control(resolved_message, role, username, scene_mode)
        if control_result:
            self._dst.update(session_id, '', control_result.get('content', ''), intent_type=control_result.get('intent_type'), username=username)
            self._memory.add_turn(username, 'assistant', control_result['content'], intent_type=control_result.get('intent_type'))
            return control_result

        general = await self._llm_general_response(resolved_message, context, username)
        self._dst.update(session_id, '', general.get('content', ''), intent_type=general.get('intent_type'), username=username)
        self._memory.add_turn(username, 'assistant', general['content'], intent_type='general')
        return general

    def _check_scene_mode(self, message: str) -> Optional[Dict[str, Any]]:
        msg_lower = message.lower()
        for pattern, mode in SCENE_MODE_PATTERNS:
            if re.search(pattern, msg_lower):
                self._scene_mode = mode
                mode_names = {'daily': '日常巡检', 'emergency': '应急响应', 'freeze': '变更冻结'}
                mode_icons = {'daily': '🟢', 'emergency': '🔴', 'freeze': '🟡'}
                return {
                    'content': f'{mode_icons[mode]} 已切换至**{mode_names[mode]}模式**。',
                    'actions': [
                        {'type': 'scene_mode', 'label': f'{mode_names[mode]}模式', 'params': {'mode': mode}}
                    ],
                    'intent_type': 'scene_mode',
                    'scene_mode': mode
                }
        return None

    def _check_plan_execute(self, message: str) -> Optional[Dict[str, Any]]:
        intent_result = self._intent_classifier.classify_regex(message)
        if intent_result and intent_result.intent_type == IntentType.PLAN_EXECUTE:
            return {
                'content': f'我理解您需要进行**规划执行**。让我为您制定分步方案…',
                'actions': [
                    {'type': 'plan_execute', 'label': '开始规划', 'params': {'query': message}},
                    {'type': 'navigate', 'label': '前往意图中心', 'params': {'route': '/intent'}},
                ],
                'intent_type': 'plan_execute',
                'entities': intent_result.entities,
            }
        return None

    def _check_proactive_query(self, message: str) -> Optional[Dict[str, Any]]:
        intent_result = self._intent_classifier.classify_regex(message)
        if intent_result and intent_result.intent_type == IntentType.PROACTIVE_QUERY:
            return {
                'content': f'正在为您**主动巡检**，检查网络异常…',
                'actions': [
                    {'type': 'query', 'label': '查看巡检结果', 'params': {'query': 'proactive_check'}},
                ],
                'intent_type': 'proactive_query',
                'entities': intent_result.entities,
            }
        return None

    def _check_wizard(self, message: str) -> Optional[Dict[str, Any]]:
        intent_result = self._intent_classifier.classify_regex(message)
        if intent_result and intent_result.intent_type == IntentType.WIZARD:
            return {
                'content': f'好的，我来**引导您完成配置**。让我们一步步来…',
                'actions': [
                    {'type': 'wizard', 'label': '开始向导', 'params': {'query': message}},
                ],
                'intent_type': 'wizard',
                'entities': intent_result.entities,
            }
        return None

    def _check_feedback(self, message: str) -> Optional[Dict[str, Any]]:
        intent_result = self._intent_classifier.classify_regex(message)
        if intent_result and intent_result.intent_type == IntentType.FEEDBACK:
            return {
                'content': '感谢您的反馈！我会尝试提供更好的回答。请问您希望我如何改进？',
                'actions': [
                    {'type': 'feedback', 'label': '重新回答', 'params': {'action': 'retry'}},
                    {'type': 'feedback', 'label': '换一种方式', 'params': {'action': 'rephrase'}},
                ],
                'intent_type': 'feedback',
                'entities': intent_result.entities,
            }
        return None

    def _check_multimodal(self, message: str) -> Optional[Dict[str, Any]]:
        intent_result = self._intent_classifier.classify_regex(message)
        if intent_result and intent_result.intent_type == IntentType.MULTIMODAL:
            return {
                'content': '我检测到您想分析图片或文件。请上传相关文件，我会为您解读。',
                'actions': [
                    {'type': 'upload', 'label': '上传文件', 'params': {}},
                ],
                'intent_type': 'multimodal',
                'entities': intent_result.entities,
            }
        return None

    def _check_navigation(self, message: str, role: str) -> Optional[Dict[str, Any]]:
        msg_lower = message.lower()
        for pattern, route, title in NAVIGATION_PATTERNS:
            if re.search(pattern, msg_lower):
                allowed = ROLE_ACCESS.get(role, ROLE_ACCESS['viewer'])
                if route not in allowed:
                    return {
                        'content': f'抱歉，您当前的{role}角色无权访问{title}页面。',
                        'actions': [],
                        'intent_type': 'navigation_denied'
                    }
                return {
                    'content': f'好的，正在为您导航到**{title}**。',
                    'actions': [
                        {'type': 'navigate', 'label': f'前往{title}', 'params': {'route': route}}
                    ],
                    'intent_type': 'navigation'
                }
        return None

    async def _check_control(self, message: str, role: str, username: str, scene_mode: str = 'daily') -> Optional[Dict[str, Any]]:
        msg_lower = message.lower()
        for pattern, command in CONTROL_PATTERNS:
            if re.search(pattern, msg_lower):
                if role == 'viewer':
                    return {
                        'content': '抱歉，您当前的观察者角色无权执行操作类指令。如需执行操作，请联系管理员提升权限。',
                        'actions': [],
                        'intent_type': 'control_denied'
                    }

                if scene_mode == 'freeze' and command in ('create_intent', 'restart_device', 'isolate_node', 'shutdown_port', 'optimize_bandwidth'):
                    return {
                        'content': '🟡 当前为**变更冻结期**，所有写操作已被拦截，仅允许查看和审批。\n\n如需执行操作，请先切换为日常或应急模式。',
                        'actions': [
                            {'type': 'scene_mode', 'label': '切换日常模式', 'params': {'mode': 'daily'}}
                        ],
                        'intent_type': 'control_frozen'
                    }

                entities = self._memory.get_entities(username)
                entity_desc = ''
                if entities:
                    entity_desc = '，目标：' + '、'.join(f'{k} **{v}**' for k, v in entities.items())

                self._memory.set_last_intent(username, {'command': command, 'entities': entities})

                is_danger = command in DANGER_COMMANDS

                handler = self._control_handlers.get(command)
                if handler:
                    try:
                        result = await handler(message, entities, username)
                        if result:
                            result['is_danger'] = is_danger
                            result['entities'] = entities
                            return result
                    except Exception as e:
                        logger.error(f"Control handler error for {command}: {e}")

                workflow_steps = self._build_workflow_steps(command, entities)

                llm_confirm = await self._llm_enhance_control_response(command, entities, username)
                confirm_text = llm_confirm or f'我理解您的意图是**{command}**{entity_desc}，正在进入意图执行管线…'

                return {
                    'content': confirm_text,
                    'actions': [
                        {'type': 'execute', 'label': f'执行{command}', 'params': {'command': command, **entities}},
                        {'type': 'navigate', 'label': '前往意图中心查看', 'params': {'route': '/intent'}}
                    ],
                    'intent_type': 'control',
                    'is_danger': is_danger,
                    'entities': entities,
                    'progress': [
                        '⏳ 意图解析中：Intent Parser Agent 工作',
                        '🔍 冲突检测中：Conflict Detector Agent 工作',
                        '📋 生成执行计划：Policy Planner Agent 工作',
                        '🚀 调用工具执行：Execution Agent 调用 MCP 工具',
                    ],
                    'workflow': workflow_steps
                }
        return None

    def _build_workflow_steps(self, command: str, entities: Dict[str, Any]) -> List[Dict[str, Any]]:
        entity_str = '、'.join(entities.values()) if entities else '目标设备'
        return [
            {
                'id': 'step_parse',
                'agent': 'IntentParser',
                'status': 'completed',
                'title': f'意图解析：识别为{command}操作，目标{entity_str}',
                'detail': f'已提取实体：{entities}'
            },
            {
                'id': 'step_conflict',
                'agent': 'ConflictDetector',
                'status': 'running',
                'title': '冲突检测：检查操作是否与现有意图冲突',
                'detail': '正在扫描活跃意图列表…'
            },
            {
                'id': 'step_plan',
                'agent': 'PolicyPlanner',
                'status': 'pending',
                'title': '策略规划：生成执行步骤',
                'detail': '等待冲突检测完成'
            },
            {
                'id': 'step_execute',
                'agent': 'ExecutionAgent',
                'status': 'pending',
                'title': '执行操作：调用MCP工具下发配置',
                'detail': '等待策略规划完成'
            }
        ]

    async def _check_query(self, message: str, role: str, username: str) -> Optional[Dict[str, Any]]:
        msg_lower = message.lower()
        for pattern, query_type in QUERY_PATTERNS:
            if re.search(pattern, msg_lower):
                handler = self._query_handlers.get(query_type)
                if handler:
                    try:
                        result = await handler(message, username)
                        if result:
                            return result
                    except Exception as e:
                        logger.error(f"Query handler error for {query_type}: {e}")

                fallback_handler = self._fallback_query_handlers.get(query_type)
                if fallback_handler:
                    try:
                        return await fallback_handler(username)
                    except Exception as e:
                        logger.error(f"Fallback query handler error for {query_type}: {e}")

                return {
                    'content': f'正在为您查询**{query_type}**相关信息…',
                    'actions': [
                        {'type': 'query', 'label': '查看详情', 'params': {'query': query_type}}
                    ],
                    'intent_type': 'query'
                }
        return None

    def _general_response(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        route = context.get('route', '/')
        route_ctx = ROUTE_CONTEXT_MAP.get(route, {})
        page_name = route_ctx.get('title', '当前页面')
        fallback = {
            'content': f'我理解您的问题。作为智维运维助手，我可以帮您：\n\n'
                       f'1. **导航** — 告诉我"去拓扑"即可跳转页面\n'
                       f'2. **查询** — 询问"系统健康度如何"获取实时数据\n'
                       f'3. **操控** — 说"重启路由器A"触发意图执行\n\n'
                       f'当前您在**{page_name}**，有什么具体需要吗？',
            'actions': route_ctx.get('quick_actions', [])[:2],
            'intent_type': 'general'
        }
        return fallback

    async def _llm_general_response(self, message: str, context: Dict[str, Any], username: str) -> Dict[str, Any]:
        if not self._llm:
            return self._general_response(message, context)

        route = context.get('route', '/')
        route_ctx = ROUTE_CONTEXT_MAP.get(route, {})
        page_name = route_ctx.get('title', '当前页面')
        role = context.get('role', 'viewer')
        scene_mode = context.get('scene_mode', self._scene_mode)
        recent = self._memory.get_recent_messages(username, 6)

        # 时间感知：判断是否为非工作时间
        now = datetime.now(timezone.utc)
        cn_hour = (now.hour + 8) % 24  # UTC+8
        is_weekday = now.weekday() < 5  # 周一至周五
        is_off_hours = False
        time_greeting = ""
        if is_weekday and (cn_hour >= 18 or cn_hour < 9):
            is_off_hours = True
            if cn_hour >= 22 or cn_hour < 6:
                time_greeting = "当前为深夜时段，请注意休息。"
            else:
                time_greeting = "当前为非工作时间。"
        elif not is_weekday:
            is_off_hours = True
            time_greeting = "当前为休息日。"

        scene_desc = '日常巡检' if scene_mode == 'daily' else '应急响应' if scene_mode == 'emergency' else '变更冻结'

        system_prompt = f"""你是智维AgentHub的专业智能运维助手，专注于协助运维人员高效完成日常运维工作。

## 角色定义
你是智维运维平台的专业智能助手，回答必须保持高度的准确性、专业性和严谨性，同时维持礼貌自然的交互语气。

## 核心职责
1. **运维查询响应**：对服务器状态、监控告警、日志分析、故障排查等运维相关查询提供快速、精准的响应
2. **运维操作协助**：支持重启服务、修改配置、创建工单等运维操作的执行，确保操作指令清晰可执行
3. **运维知识支持**：基于平台知识库内容，提供专业的运维知识解答
4. **非运维问题处理**：对非运维类问题可提供简洁回答，但不得偏离运维主题

## 输出规范
1. **结构化输出**：优先采用表格、列表等结构化形式，提升可读性
2. **关键信息强调**：使用**加粗**格式突出告警级别、操作风险、重要参数
3. **操作步骤规范**：采用编号形式（1. 2. 3.）分步骤说明，确保可按步骤执行
4. **内容简洁**：直击问题核心，避免冗余

## 行为规则
1. **操作确认机制**：执行任何运维操作前，必须确认用户意图，获得明确授权后方可继续
2. **风险提示要求**：涉及系统重启、配置修改等高风险操作时，必须醒目提醒注意事项、潜在风险及回滚方案
3. **故障处理规范**：工具调用失败时，需告知具体失败原因、影响范围及建议解决措施
4. **不编造数据**：如果不确定，告诉用户你可以帮他们查询

当前上下文：
- 用户角色：{role}
- 当前页面：{page_name}（路由：{route}）
- 场景模式：{scene_desc}
- 当前时间：北京时间{cn_hour:02d}:{now.minute:02d}
{f"- {time_greeting}" if time_greeting else ""}

你的核心能力：
1. **导航** — 帮用户跳转到系统页面（指挥舱、意图中心、网络拓扑、故障自愈、审计日志等）
2. **查询** — 查询系统健康度、告警、设备状态、审批待办等实时数据
3. **操控** — 执行重启设备、隔离节点、优化带宽等运维操作
4. **场景切换** — 切换日常巡检/应急响应/变更冻结模式

回复使用Markdown格式，适当使用加粗和列表。{"非工作时间可适当使用更轻松的语气，但专业术语和解答专业度不得降低。" if is_off_hours else ""}"""

        messages = [{"role": "system", "content": system_prompt}]
        for msg in recent:
            if msg.get('role') in ('user', 'assistant'):
                messages.append({"role": msg['role'], "content": msg['content']})
        messages.append({"role": "user", "content": message})

        try:
            result = await self._llm.chat(
                messages,
                task_type=TaskType.COPILOT_CHAT,
                temperature=0.7,
                max_tokens=1024,
                preferred=LLMProvider.ZHIPU
            )
            content = result.get("content", "")
            if not content or len(content.strip()) < 5:
                return self._general_response(message, context)
            return {
                'content': content,
                'actions': route_ctx.get('quick_actions', [])[:2],
                'intent_type': 'general'
            }
        except Exception as e:
            logger.warning(f"LLM通用回复失败，降级为规则匹配: {e}")
            return self._general_response(message, context)

    async def _llm_enhance_query_result(self, raw_content: str, user_message: str, username: str) -> str:
        if not self._llm:
            return raw_content

        recent = self._memory.get_recent_messages(username, 4)
        messages = [
            {"role": "system", "content": "你是智维运维平台的专业数据分析师。请将查询结果用更专业、易读的方式重新组织，保持数据准确性。输出规范：1.优先使用表格或列表展示数据；2.使用**加粗**突出关键指标和异常值；3.内容简洁直击核心；4.使用Markdown格式。不要添加不存在的数据。"},
            {"role": "user", "content": f"用户问题：{user_message}\n\n原始查询结果：\n{raw_content}"}
        ]

        try:
            result = await self._llm.chat(
                messages,
                task_type=TaskType.COPILOT_CHAT,
                temperature=0.3,
                max_tokens=800,
                preferred=LLMProvider.ZHIPU
            )
            enhanced = result.get("content", "")
            return enhanced if len(enhanced.strip()) > 10 else raw_content
        except Exception as e:
            logger.warning(f"LLM查询增强失败，使用原始结果: {e}")
            return raw_content

    async def _llm_enhance_control_response(self, command: str, entities: Dict[str, Any], username: str) -> Optional[str]:
        if not self._llm:
            return None

        entity_str = '、'.join(f'{k}**{v}**' for k, v in entities.items()) if entities else '目标设备'
        is_danger = command in DANGER_COMMANDS
        risk_instruction = ""
        if is_danger:
            risk_instruction = "\n由于这是高风险操作，必须在确认语后附上：**风险提示**和**回滚方案**。"

        messages = [
            {"role": "system", "content": f"你是智维运维平台的专业操作确认助手。用简洁专业的语言确认用户意图，使用Markdown加粗关键信息。只输出确认语，不要其他内容。{risk_instruction}"},
            {"role": "user", "content": f"用户要执行{command}操作，涉及{entity_str}。请生成确认语。"}
        ]

        try:
            result = await self._llm.chat(
                messages,
                task_type=TaskType.INTENT_PARSE,
                temperature=0.3,
                max_tokens=200,
                preferred=LLMProvider.ZHIPU
            )
            content = result.get("content", "").strip()
            return content if len(content) > 5 else None
        except Exception as e:
            logger.warning(f"LLM操控增强失败: {e}")
            return None

    def get_context_for_route(self, route: str, role: str) -> Dict[str, Any]:
        ctx = ROUTE_CONTEXT_MAP.get(route)
        if not ctx:
            return {'title': '未知页面', 'icon': '❓', 'description': '', 'quick_actions': []}
        allowed = ROLE_ACCESS.get(role, ROLE_ACCESS['viewer'])
        if route not in allowed:
            return {'title': ctx['title'], 'icon': ctx['icon'], 'description': '无权访问', 'quick_actions': []}
        return ctx

    def get_conversation_history(self, username: str, count: int = 10) -> List[Dict[str, Any]]:
        return self._memory.get_recent_messages(username, count)

    async def _query_fault_root_cause(self, username: str) -> Dict[str, Any]:
        try:
            from backend.database.connection import get_db_session
            from backend.database.models import SelfHealingEvent
            async for db in get_db_session():
                from sqlalchemy import select, desc
                stmt = select(SelfHealingEvent).where(
                    SelfHealingEvent.status.in_(["detected", "analyzing", "healing"])
                ).order_by(desc(SelfHealingEvent.id)).limit(5)
                result = await db.execute(stmt)
                events = result.scalars().all()
                if events:
                    lines = []
                    for e in events:
                        lines.append(f"- **{e.event_type}** ({e.severity}): {e.description}")
                    return {
                        'content': f'最近故障事件：\n' + '\n'.join(lines),
                        'actions': [{'type': 'navigate', 'label': '查看故障自愈', 'params': {'route': '/self-healing'}}],
                        'intent_type': 'query'
                    }
                break
        except Exception as e:
            logger.warning(f"Query fault root cause failed: {e}")
        return {
            'content': '当前没有活跃的故障事件，系统运行正常。',
            'actions': [{'type': 'navigate', 'label': '查看故障自愈', 'params': {'route': '/self-healing'}}],
            'intent_type': 'query'
        }

    async def _query_high_risk_ops(self, username: str) -> Dict[str, Any]:
        try:
            from backend.database.connection import get_db_session
            from backend.database.models import AuditLog
            from datetime import datetime, timedelta
            async for db in get_db_session():
                from sqlalchemy import select, desc
                one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                stmt = select(AuditLog).where(
                    AuditLog.security_type.in_(["high", "critical"]),
                    AuditLog.created_at >= one_hour_ago
                ).order_by(desc(AuditLog.id)).limit(10)
                result = await db.execute(stmt)
                logs = result.scalars().all()
                if logs:
                    lines = [f"- **{l.action}** by {l.user_id}: {l.status}" for l in logs]
                    return {
                        'content': f'过去1小时高危操作（{len(logs)}条）：\n' + '\n'.join(lines),
                        'actions': [{'type': 'navigate', 'label': '查看审计日志', 'params': {'route': '/audit'}}],
                        'intent_type': 'query'
                    }
                break
        except Exception as e:
            logger.warning(f"Query high risk ops failed: {e}")
        return {
            'content': '过去1小时没有高危操作记录。',
            'actions': [{'type': 'navigate', 'label': '查看审计日志', 'params': {'route': '/audit'}}],
            'intent_type': 'query'
        }

    async def _query_firewall_changes(self, username: str) -> Dict[str, Any]:
        try:
            from backend.database.connection import get_db_session
            from backend.database.models import AuditLog
            async for db in get_db_session():
                from sqlalchemy import select, desc
                stmt = select(AuditLog).where(
                    AuditLog.action.ilike("%acl%")
                ).order_by(desc(AuditLog.id)).limit(5)
                result = await db.execute(stmt)
                logs = result.scalars().all()
                if logs:
                    lines = [f"- **{l.action}** by {l.user_id} at {l.created_at}" for l in logs]
                    return {
                        'content': f'防火墙策略变更记录：\n' + '\n'.join(lines),
                        'actions': [{'type': 'navigate', 'label': '查看审计日志', 'params': {'route': '/audit'}}],
                        'intent_type': 'query'
                    }
                break
        except Exception as e:
            logger.warning(f"Query firewall changes failed: {e}")
        return {
            'content': '没有找到防火墙策略变更记录。',
            'actions': [{'type': 'navigate', 'label': '查看审计日志', 'params': {'route': '/audit'}}],
            'intent_type': 'query'
        }

    async def _query_traffic_stats(self, username: str) -> Dict[str, Any]:
        try:
            from backend.telemetry.collector import get_telemetry_collector
            collector = get_telemetry_collector()
            all_metrics = collector.collect_all_devices()
            bandwidth_data = [m for m in all_metrics if m.get("metric_type") == "bandwidth_mbps"]
            if bandwidth_data:
                lines = [f"- **{m['device']}**: {m['value']:.1f} Mbps" for m in bandwidth_data[:5]]
                return {
                    'content': f'当前带宽使用情况：\n' + '\n'.join(lines),
                    'intent_type': 'query'
                }
        except Exception as e:
            logger.warning(f"Query traffic stats failed: {e}")
        return {
            'content': '暂无流量统计数据，请稍后再试。',
            'intent_type': 'query'
        }

    async def _query_pending_work_orders(self, username: str) -> Dict[str, Any]:
        try:
            from backend.workflow.work_order import work_order_manager
            manager = work_order_manager
            summary = manager.get_board_summary()
            pending = summary.get("pending", 0)
            return {
                'content': f'当前待审批工单：**{pending}**个。',
                'actions': [{'type': 'navigate', 'label': '查看工单看板', 'params': {'route': '/workflow'}}],
                'intent_type': 'query'
            }
        except Exception as e:
            logger.warning(f"Query pending work orders failed: {e}")
        return {
            'content': '暂无法获取工单信息。',
            'actions': [{'type': 'navigate', 'label': '查看工单看板', 'params': {'route': '/workflow'}}],
            'intent_type': 'query'
        }

    async def _query_config_tools(self, username: str) -> Dict[str, Any]:
        try:
            from backend.mcp.tools import get_mcp_tools
            tools = get_mcp_tools()
            config_tools = [t for t in tools if "config" in t.get("name", "").lower() or "config" in t.get("description", "").lower()]
            if config_tools:
                lines = [f"- **{t['name']}**: {t.get('description', '无描述')}" for t in config_tools[:5]]
                return {
                    'content': f'可用配置工具：\n' + '\n'.join(lines),
                    'actions': [{'type': 'navigate', 'label': '查看MCP工具', 'params': {'route': '/mcp-tools'}}],
                    'intent_type': 'query'
                }
        except Exception as e:
            logger.warning(f"Query config tools failed: {e}")
        return {
            'content': '暂无法获取工具列表。',
            'actions': [{'type': 'navigate', 'label': '查看MCP工具', 'params': {'route': '/mcp-tools'}}],
            'intent_type': 'query'
        }

    async def _query_ops_knowledge(self, username: str) -> Dict[str, Any]:
        return {
            'content': '运维知识库支持以下主题查询：\n- QoS配置\n- OSPF路由\n- BGP排查\n- VLAN配置\n- 防火墙策略\n- 设备巡检\n- 网络自愈\n- 流量工程\n\n请告诉我您想了解哪个主题？',
            'actions': [{'type': 'navigate', 'label': '打开知识助手', 'params': {'route': '/knowledge'}}],
            'intent_type': 'query'
        }
