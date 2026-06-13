import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'

interface ContextPage {
  name: string
  path: string
  description: string
  keywords: string[]
}

interface ContextSuggestion {
  type: 'action' | 'query' | 'info'
  text: string
  relevance: number
}

const PAGE_CONTEXT_MAP: Record<string, ContextPage> = {
  '/': {
    name: '仪表盘',
    path: '/',
    description: '系统总览仪表盘，展示关键指标和状态概览',
    keywords: ['仪表盘', '总览', '指标', '状态', 'dashboard']
  },
  '/intent': {
    name: '意图中心',
    path: '/intent',
    description: '自然语言意图识别与管理',
    keywords: ['意图', 'NLU', '自然语言', '识别', 'intent']
  },
  '/topology': {
    name: '网络拓扑',
    path: '/topology',
    description: '网络拓扑可视化与监控',
    keywords: ['拓扑', '网络', '节点', '链路', 'topology']
  },
  '/self-healing': {
    name: '自愈中心',
    path: '/self-healing',
    description: '自动化故障检测与自愈策略',
    keywords: ['自愈', '故障', '修复', '自动化', 'healing']
  },
  '/audit-logs': {
    name: '审计日志',
    path: '/audit-logs',
    description: '操作审计与日志查询',
    keywords: ['审计', '日志', '操作记录', 'audit']
  },
  '/mcp-tools': {
    name: 'MCP工具',
    path: '/mcp-tools',
    description: 'MCP工具管理与配置',
    keywords: ['MCP', '工具', '插件', 'tools']
  },
  '/agent-map': {
    name: 'Agent地图',
    path: '/agent-map',
    description: 'AI Agent协作拓扑与状态监控',
    keywords: ['Agent', '协作', '地图', '状态', 'agent']
  },
  '/work-orders': {
    name: '工单看板',
    path: '/work-orders',
    description: '运维工单管理与看板',
    keywords: ['工单', '看板', '运维', '任务', 'work-order']
  },
  '/playbooks': {
    name: '剧本库',
    path: '/playbooks',
    description: '自动化运维剧本管理',
    keywords: ['剧本', '自动化', '运维', 'playbook']
  },
  '/knowledge': {
    name: '知识库',
    path: '/knowledge',
    description: '运维知识库与文档管理',
    keywords: ['知识库', '文档', '搜索', 'knowledge']
  },
  '/sla-prediction': {
    name: 'SLA预测',
    path: '/sla-prediction',
    description: 'SLA指标预测与预警',
    keywords: ['SLA', '预测', '预警', '指标', 'prediction']
  },
  '/observability': {
    name: '可观测性',
    path: '/observability',
    description: '系统可观测性监控面板',
    keywords: ['监控', '可观测性', '指标', '链路', 'observability']
  },
  '/notifications': {
    name: '通知中心',
    path: '/notifications',
    description: '系统通知与告警管理',
    keywords: ['通知', '告警', '消息', 'notification']
  },
  '/webhooks': {
    name: 'Webhook管理',
    path: '/webhooks',
    description: 'Webhook配置与管理',
    keywords: ['Webhook', '回调', '集成', 'webhook']
  },
  '/scheduler': {
    name: '调度器',
    path: '/scheduler',
    description: '定时任务调度管理',
    keywords: ['调度', '定时任务', 'cron', 'scheduler']
  },
  '/failed-intents': {
    name: '失败意图',
    path: '/failed-intents',
    description: '失败意图分析与重试',
    keywords: ['失败', '意图', '重试', '错误', 'failed']
  },
  '/llm-router': {
    name: 'LLM路由',
    path: '/llm-router',
    description: '大模型路由配置与监控',
    keywords: ['LLM', '路由', '模型', '大模型', 'router']
  },
  '/user-management': {
    name: '用户管理',
    path: '/user-management',
    description: '系统用户与权限管理',
    keywords: ['用户', '权限', '角色', '管理', 'user']
  }
}

export function useAssistantContext() {
  const route = useRoute()
  const currentPage = ref<ContextPage | null>(null)
  const contextPages = ref<ContextPage[]>(
    Object.values(PAGE_CONTEXT_MAP)
  )

  // 根据当前路由自动识别页面上下文
  function updateContext(pageInfo?: Partial<ContextPage>): void {
    if (pageInfo) {
      currentPage.value = pageInfo as ContextPage
      return
    }

    const path = route.path
    // 精确匹配
    if (PAGE_CONTEXT_MAP[path]) {
      currentPage.value = PAGE_CONTEXT_MAP[path]
      return
    }

    // 前缀匹配（处理子路由）
    const matchedKey = Object.keys(PAGE_CONTEXT_MAP)
      .filter(key => path.startsWith(key))
      .sort((a, b) => b.length - a.length)[0]

    currentPage.value = matchedKey ? PAGE_CONTEXT_MAP[matchedKey] : null
  }

  function getContextSuggestions(): ContextSuggestion[] {
    if (!currentPage.value) return []

    const suggestions: ContextSuggestion[] = []
    const page = currentPage.value

    // 基于页面关键词生成建议
    suggestions.push({
      type: 'info',
      text: `当前页面：${page.name} - ${page.description}`,
      relevance: 1.0
    })

    // 根据不同页面类型生成操作建议
    if (page.path === '/topology') {
      suggestions.push(
        { type: 'query', text: '查看网络拓扑状态', relevance: 0.9 },
        { type: 'action', text: '刷新拓扑数据', relevance: 0.8 }
      )
    } else if (page.path === '/intent') {
      suggestions.push(
        { type: 'query', text: '查看最近意图执行情况', relevance: 0.9 },
        { type: 'action', text: '创建新意图', relevance: 0.7 }
      )
    } else if (page.path === '/self-healing') {
      suggestions.push(
        { type: 'query', text: '查看自愈策略执行历史', relevance: 0.9 },
        { type: 'action', text: '触发自愈检查', relevance: 0.8 }
      )
    } else if (page.path === '/observability') {
      suggestions.push(
        { type: 'query', text: '查看系统监控指标', relevance: 0.9 },
        { type: 'action', text: '检查告警状态', relevance: 0.8 }
      )
    }

    return suggestions.sort((a, b) => b.relevance - a.relevance)
  }

  // 监听路由变化自动更新上下文
  watch(() => route.path, () => {
    updateContext()
  }, { immediate: true })

  return {
    contextPages,
    currentPage,
    updateContext,
    getContextSuggestions
  }
}
