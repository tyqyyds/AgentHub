import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { getUserRole, type UserRole } from '@/utils/userRole'

export interface PageContext {
  route: string
  title: string
  icon: string
  description: string
  quickActions: QuickAction[]
}

export interface QuickAction {
  label: string
  type: string
  params?: Record<string, unknown>
}

interface RoleScene {
  title: string
  description: string
  quickActions: QuickAction[]
}

const ROUTE_ICONS: Record<string, string> = {
  '/': '🖥️',
  '/intent': '🎯',
  '/topology': '🔗',
  '/self-healing': '🛡️',
  '/mcp-tools': '🔧',
  '/agent-map': '🌐',
  '/knowledge': '💡',
  '/workflow': '📌',
  '/observability': '📊',
  '/grayscale-healing': '🔬',
  '/webhooks': '🪝',
  '/agent-management': '🤖',
  '/playbooks': '📖'
}

const SCENE_ROLE_MAP: Record<string, Record<UserRole, RoleScene>> = {
  '/': {
    admin: {
      title: '指挥舱',
      description: '全局视角，掌控系统健康与高危事件',
      quickActions: [
        { label: '查看全系统健康度', type: 'query', params: { query: 'system_health_full' } },
        { label: '有哪些待审批的高危意图？', type: 'query', params: { query: 'pending_high_risk_intents' } }
      ]
    },
    operator: {
      title: '指挥舱',
      description: '实时监控系统健康与关键告警',
      quickActions: [
        { label: '当前系统健康度如何？', type: 'query', params: { query: 'system_health' } },
        { label: '有哪些未处理告警？', type: 'query', params: { query: 'pending_alerts' } }
      ]
    },
    viewer: {
      title: '指挥舱',
      description: '监控中心，实时掌握网络动态',
      quickActions: [
        { label: '查看今日告警趋势', type: 'query', params: { query: 'daily_alert_trend' } },
        { label: '当前网络是否正常？', type: 'query', params: { query: 'network_status' } }
      ]
    }
  },
  '/intent': {
    admin: {
      title: '意图中心',
      description: '管理意图创建、审批与执行全流程',
      quickActions: [
        { label: '保障带宽', type: 'fill_form', params: { route: '/intent', field: 'inputText', value: '我需要为 [IP地址/端口/应用] 保障带宽，当前网络环境是 [设备型号/操作系统]，带宽上限是 [X Mbps]，请给出详细的QoS配置步骤。' } },
        { label: '开放访问', type: 'fill_form', params: { route: '/intent', field: 'inputText', value: '我需要开放 [端口号] 给 [指定IP段/所有IP]，用于 [服务名称]，当前使用的防火墙是 [设备型号/软件]，请给出详细的配置步骤和安全注意事项。' } },
        { label: '故障诊断', type: 'fill_form', params: { route: '/intent', field: 'inputText', value: '我遇到了 [具体故障现象]，发生时间是 [X]，影响范围是 [X]，已经尝试过 [X] 操作，设备型号/系统版本是 [X]，请帮我排查故障原因并给出解决方案。' } },
        { label: '链路切换', type: 'fill_form', params: { route: '/intent', field: 'inputText', value: '我需要将流量从 [主链路] 切换到 [备用链路]，当前使用的路由协议是 [静态/OSPF/BGP]，请给出详细的切换步骤和回滚方案。' } }
      ]
    },
    operator: {
      title: '意图中心',
      description: '用自然语言描述需求，快速下发运维指令',
      quickActions: [
        { label: '保障带宽', type: 'fill_form', params: { route: '/intent', field: 'inputText', value: '我需要为 [IP地址/端口/应用] 保障带宽，当前网络环境是 [设备型号/操作系统]，带宽上限是 [X Mbps]，请给出详细的QoS配置步骤。' } },
        { label: '开放访问', type: 'fill_form', params: { route: '/intent', field: 'inputText', value: '我需要开放 [端口号] 给 [指定IP段/所有IP]，用于 [服务名称]，当前使用的防火墙是 [设备型号/软件]，请给出详细的配置步骤和安全注意事项。' } },
        { label: '故障诊断', type: 'fill_form', params: { route: '/intent', field: 'inputText', value: '我遇到了 [具体故障现象]，发生时间是 [X]，影响范围是 [X]，已经尝试过 [X] 操作，设备型号/系统版本是 [X]，请帮我排查故障原因并给出解决方案。' } },
        { label: '链路切换', type: 'fill_form', params: { route: '/intent', field: 'inputText', value: '我需要将流量从 [主链路] 切换到 [备用链路]，当前使用的路由协议是 [静态/OSPF/BGP]，请给出详细的切换步骤和回滚方案。' } }
      ]
    },
    viewer: {
      title: '意图中心',
      description: '观测意图执行轨迹，了解系统自动化过程',
      quickActions: [
        { label: '查看最近的意图记录', type: 'query', params: { query: 'recent_intent_records' } },
        { label: '当前有冲突的意图吗？', type: 'query', params: { query: 'conflicting_intents' } }
      ]
    }
  },
  '/topology': {
    admin: {
      title: '网络拓扑',
      description: '可视化网络结构，支持对话式定位与配置',
      quickActions: [
        { label: '定位核心交换机', type: 'query', params: { query: 'locate_core_switch' } },
        { label: '高亮显示故障链路', type: 'execute', params: { command: 'highlight_fault_links' } }
      ]
    },
    operator: {
      title: '网络拓扑',
      description: '可视化网络结构，支持对话式定位与配置',
      quickActions: [
        { label: '定位核心交换机', type: 'query', params: { query: 'locate_core_switch' } },
        { label: '高亮显示故障链路', type: 'execute', params: { command: 'highlight_fault_links' } }
      ]
    },
    viewer: {
      title: '网络拓扑',
      description: '可视化网络结构，查看设备状态与链路信息',
      quickActions: [
        { label: '定位核心交换机', type: 'query', params: { query: 'locate_core_switch' } },
        { label: '查看故障链路状态', type: 'query', params: { query: 'fault_link_status' } }
      ]
    }
  },
  '/self-healing': {
    admin: {
      title: '故障自愈',
      description: 'AI自动诊断与修复，降低MTTR',
      quickActions: [
        { label: '最新故障的根因是什么？', type: 'query', params: { query: 'latest_fault_root_cause' } },
        { label: '重试失败的修复任务', type: 'execute', params: { command: 'retry_failed_healing' } }
      ]
    },
    operator: {
      title: '故障自愈',
      description: 'AI自动诊断与修复，降低MTTR',
      quickActions: [
        { label: '最新故障的根因是什么？', type: 'query', params: { query: 'latest_fault_root_cause' } },
        { label: '重试失败的修复任务', type: 'execute', params: { command: 'retry_failed_healing' } }
      ]
    },
    viewer: {
      title: '故障自愈',
      description: '查看故障自愈过程与诊断结果',
      quickActions: [
        { label: '查看最近的修复记录', type: 'query', params: { query: 'recent_healing_records' } },
        { label: '当前有哪些活跃故障？', type: 'query', params: { query: 'active_faults' } }
      ]
    }
  },
  '/mcp-tools': {
    admin: {
      title: 'MCP工具',
      description: '管理与调用底层运维工具',
      quickActions: [
        { label: '执行Ping测试', type: 'execute', params: { command: 'ping_test' } },
        { label: '列出配置工具', type: 'query', params: { query: 'available_config_tools' } }
      ]
    },
    operator: {
      title: 'MCP工具',
      description: '管理与调用底层运维工具',
      quickActions: [
        { label: '执行Ping测试', type: 'execute', params: { command: 'ping_test' } },
        { label: '列出配置工具', type: 'query', params: { query: 'available_config_tools' } }
      ]
    },
    viewer: {
      title: 'MCP工具',
      description: '管理与调用底层运维工具',
      quickActions: [
        { label: '列出配置工具', type: 'query', params: { query: 'available_config_tools' } }
      ]
    }
  },
  '/agent-map': {
    admin: {
      title: '智能体地图',
      description: '全局视角查看智能体分布与路由',
      quickActions: [
        { label: '查看智能体分布', type: 'query', params: { query: 'agent_distribution' } },
        { label: '规划跨域路由', type: 'fill_form', params: { route: '/agent-map', field: 'pathStart', value: '' } }
      ]
    },
    operator: {
      title: '智能体地图',
      description: '全局视角查看智能体分布与路由',
      quickActions: [
        { label: '查看智能体分布', type: 'query', params: { query: 'agent_distribution' } },
        { label: '规划跨域路由', type: 'fill_form', params: { route: '/agent-map', field: 'pathStart', value: '' } }
      ]
    },
    viewer: {
      title: '智能体地图',
      description: '全局视角查看智能体分布与路由',
      quickActions: [
        { label: '查看智能体分布', type: 'query', params: { query: 'agent_distribution' } }
      ]
    }
  },
  '/knowledge': {
    admin: {
      title: '运维助手',
      description: '运维知识问答与文档管理',
      quickActions: [
        { label: '查询运维知识', type: 'query', params: { query: 'ops_knowledge' } },
        { label: '上传运维文档', type: 'execute', params: { command: 'upload_document' } }
      ]
    },
    operator: {
      title: '运维助手',
      description: '运维知识问答与文档管理',
      quickActions: [
        { label: '查询运维知识', type: 'query', params: { query: 'ops_knowledge' } },
        { label: '上传运维文档', type: 'execute', params: { command: 'upload_document' } }
      ]
    },
    viewer: {
      title: '运维助手',
      description: '运维知识问答与文档管理',
      quickActions: [
        { label: '查询运维知识', type: 'query', params: { query: 'ops_knowledge' } }
      ]
    }
  },
  '/workflow': {
    admin: {
      title: '工单看板',
      description: '管理运维工单与审批流程',
      quickActions: [
        { label: '创建运维工单', type: 'fill_form', params: { route: '/workflow', field: 'newOrder.title', value: '' } },
        { label: '查看待审批工单', type: 'query', params: { query: 'pending_work_orders' } }
      ]
    },
    operator: {
      title: '工单看板',
      description: '管理运维工单与审批流程',
      quickActions: [
        { label: '创建运维工单', type: 'fill_form', params: { route: '/workflow', field: 'newOrder.title', value: '' } },
        { label: '查看待审批工单', type: 'query', params: { query: 'pending_work_orders' } }
      ]
    },
    viewer: {
      title: '工单看板',
      description: '管理运维工单与审批流程',
      quickActions: [
        { label: '查看待审批工单', type: 'query', params: { query: 'pending_work_orders' } }
      ]
    }
  },
  '/observability': {
    admin: {
      title: '可观测性',
      description: '监控Agent健康状态、链路追踪与系统指标',
      quickActions: [
        { label: '查看系统指标概览', type: 'query', params: { query: 'system_metrics_overview' } },
        { label: '触发全局健康检查', type: 'execute', params: { command: 'trigger_health_check' } }
      ]
    },
    operator: {
      title: '可观测性',
      description: '监控Agent健康状态、链路追踪与系统指标',
      quickActions: [
        { label: '查看系统指标概览', type: 'query', params: { query: 'system_metrics_overview' } },
        { label: '查看异常链路', type: 'query', params: { query: 'error_traces' } }
      ]
    },
    viewer: {
      title: '可观测性',
      description: '查看Agent健康状态与链路追踪',
      quickActions: [
        { label: '查看系统指标概览', type: 'query', params: { query: 'system_metrics_overview' } }
      ]
    }
  },
  '/grayscale-healing': {
    admin: {
      title: '灰度自愈',
      description: '金丝雀发布式自愈，安全渐进修复故障',
      quickActions: [
        { label: '查看灰度自愈任务', type: 'query', params: { query: 'grayscale_healing_tasks' } },
        { label: '查看自愈评估报告', type: 'query', params: { query: 'healing_evaluations' } }
      ]
    },
    operator: {
      title: '灰度自愈',
      description: '金丝雀发布式自愈，安全渐进修复故障',
      quickActions: [
        { label: '查看灰度自愈任务', type: 'query', params: { query: 'grayscale_healing_tasks' } },
        { label: '查看自愈评估报告', type: 'query', params: { query: 'healing_evaluations' } }
      ]
    },
    viewer: {
      title: '灰度自愈',
      description: '查看灰度自愈任务与评估结果',
      quickActions: [
        { label: '查看灰度自愈任务', type: 'query', params: { query: 'grayscale_healing_tasks' } }
      ]
    }
  },
  '/webhooks': {
    admin: {
      title: 'Webhook管理',
      description: '配置事件订阅与Webhook投递',
      quickActions: [
        { label: '查看活跃订阅', type: 'query', params: { query: 'active_webhook_subscriptions' } },
        { label: '创建新订阅', type: 'fill_form', params: { route: '/webhooks', field: 'subscriptionName', value: '' } }
      ]
    },
    operator: {
      title: 'Webhook管理',
      description: '查看事件订阅与投递状态',
      quickActions: [
        { label: '查看活跃订阅', type: 'query', params: { query: 'active_webhook_subscriptions' } }
      ]
    },
    viewer: {
      title: 'Webhook管理',
      description: '查看事件订阅状态',
      quickActions: [
        { label: '查看活跃订阅', type: 'query', params: { query: 'active_webhook_subscriptions' } }
      ]
    }
  },
  '/agent-management': {
    admin: {
      title: 'Agent管理',
      description: 'Agent评分排名、热升级与能力管理',
      quickActions: [
        { label: '查看Agent评分排名', type: 'query', params: { query: 'agent_score_ranking' } },
        { label: '查看升级历史', type: 'query', params: { query: 'agent_upgrade_history' } }
      ]
    },
    operator: {
      title: 'Agent管理',
      description: '查看Agent评分与能力信息',
      quickActions: [
        { label: '查看Agent评分排名', type: 'query', params: { query: 'agent_score_ranking' } },
        { label: '获取任务推荐Agent', type: 'query', params: { query: 'recommended_agents' } }
      ]
    },
    viewer: {
      title: 'Agent管理',
      description: '查看Agent状态与评分',
      quickActions: [
        { label: '查看Agent评分排名', type: 'query', params: { query: 'agent_score_ranking' } }
      ]
    }
  },
  '/playbooks': {
    admin: {
      title: '运维剧本',
      description: '编排与执行自动化运维流程',
      quickActions: [
        { label: '查看所有剧本', type: 'query', params: { query: 'all_playbooks' } },
        { label: '创建新剧本', type: 'fill_form', params: { route: '/playbooks', field: 'playbookName', value: '' } }
      ]
    },
    operator: {
      title: '运维剧本',
      description: '执行与管理自动化运维流程',
      quickActions: [
        { label: '查看所有剧本', type: 'query', params: { query: 'all_playbooks' } },
        { label: '查看执行记录', type: 'query', params: { query: 'playbook_executions' } }
      ]
    },
    viewer: {
      title: '运维剧本',
      description: '查看运维剧本与执行状态',
      quickActions: [
        { label: '查看所有剧本', type: 'query', params: { query: 'all_playbooks' } }
      ]
    }
  }
}

const RBAC_FORBIDDEN_KEYWORDS = ['创建', '删除', '执行']
const RBAC_FORBIDDEN_TYPES = ['execute']

function applyRbacFilter(role: UserRole, actions: QuickAction[]): QuickAction[] {
  if (role !== 'viewer') return actions
  return actions.filter(a => !RBAC_FORBIDDEN_KEYWORDS.some(kw => a.label.includes(kw)) && !RBAC_FORBIDDEN_TYPES.includes(a.type))
}

export function useAssistantContext() {
  const router = useRouter()

  const currentContext = computed<PageContext | null>(() => {
    const path = router.currentRoute.value.path
    const role = getUserRole()
    const roleMap = SCENE_ROLE_MAP[path]
    if (!roleMap) return null
    const scene = roleMap[role]
    if (!scene) return null
    const icon = ROUTE_ICONS[path] || '📄'
    const quickActions = applyRbacFilter(role, scene.quickActions)
    return {
      route: path,
      title: scene.title,
      icon,
      description: scene.description,
      quickActions
    }
  })

  const hasContext = computed(() => currentContext.value !== null)

  return { currentContext, hasContext }
}
