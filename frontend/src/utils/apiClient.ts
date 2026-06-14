import { API_BASE_URL } from '@/config'
import { useAuthStore } from '@/stores/auth'

let isRefreshing = false
let refreshPromise: Promise<boolean> | null = null
let sessionExpired = false

const getAccessToken = (): string => localStorage.getItem('access_token') || ''

const getRefreshToken = (): string => localStorage.getItem('refresh_token') || ''

const refreshAccessToken = async (): Promise<boolean> => {
  if (sessionExpired) return false
  if (isRefreshing && refreshPromise) {
    return refreshPromise
  }
  isRefreshing = true
  refreshPromise = (async () => {
    const rt = getRefreshToken()
    if (!rt) return false
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
        credentials: 'include'
      })
      if (!response.ok) {
        sessionExpired = true
        return false
      }
      const refreshText = await response.text()
      const data = refreshText ? JSON.parse(refreshText) : {}
      const authStore = useAuthStore()
      authStore.setTokens({
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        user_info: data.user_info || authStore.userInfo,
        expires_in: data.expires_in || 0
      })
      return true
    } catch {
      sessionExpired = true
      return false
    } finally {
      isRefreshing = false
      refreshPromise = null
    }
  })()
  return refreshPromise
}

export const resetSessionExpired = () => { sessionExpired = false }

const handle401 = async (_token: string): Promise<boolean> => {
  if (sessionExpired) return false
  const refreshed = await refreshAccessToken()
  if (!refreshed) {
    sessionExpired = true
    const authStore = useAuthStore()
    authStore.logout()
    import('@/router').then(({ default: router }) => {
      const currentPath = router.currentRoute.value.fullPath
      if (currentPath !== '/login') {
        router.push({ name: 'Login', query: { redirect: currentPath } })
      }
    })
    return false
  }
  return true
}

export const api = {
  auth: {
    login: `${API_BASE_URL}/api/v1/auth/login`,
    register: `${API_BASE_URL}/api/v1/auth/register`,
    refresh: `${API_BASE_URL}/api/v1/auth/refresh`,
    me: `${API_BASE_URL}/api/v1/auth/me`,
    initAdmin: `${API_BASE_URL}/api/v1/auth/init-admin`,
    logout: `${API_BASE_URL}/api/v1/auth/logout`
  },
  intents: `${API_BASE_URL}/api/v1/intents`,
  intentCreate: `${API_BASE_URL}/api/v1/intents`,
  intentUpdate: (id: string) => `${API_BASE_URL}/api/v1/intents/${id}`,
  intentExecute: (id: string) => `${API_BASE_URL}/api/v1/intents/${id}/execute`,
  intentConflictCheck: (id: string) => `${API_BASE_URL}/api/v1/intents/${id}/conflict-check`,
  intentApprove: (id: string | number) => `${API_BASE_URL}/api/v1/intents/${id}/approve`,
  intentReject: (id: string | number) => `${API_BASE_URL}/api/v1/intents/${id}/reject`,

  mcpTools: `${API_BASE_URL}/api/v1/mcp-tools`,
  mcpToolsCheckName: `${API_BASE_URL}/api/v1/mcp-tools/check-name`,
  mcpToolsAdd: `${API_BASE_URL}/api/v1/mcp-tools/add`,
  mcpToolsDelete: (name: string) => `${API_BASE_URL}/api/v1/mcp-tools/delete/${encodeURIComponent(name)}`,
  mcpToolsExecute: `${API_BASE_URL}/api/v1/mcp-tools/execute`,
  mcpToolsHistory: `${API_BASE_URL}/api/v1/mcp-tools/execution-history`,

  events: `${API_BASE_URL}/api/v1/events`,
  eventsById: (id: number | string) => `${API_BASE_URL}/api/v1/events/${id}`,
  eventsExecute: (id: number | string) => `${API_BASE_URL}/api/v1/events/${id}/execute`,
  eventsReject: (id: number | string) => `${API_BASE_URL}/api/v1/events/${id}/reject`,
  eventsRollback: (id: number | string) => `${API_BASE_URL}/api/v1/events/${id}/rollback`,
  eventsGlobalRollback: `${API_BASE_URL}/api/v1/events/rollback`,

  rateLimit: {
    status: `${API_BASE_URL}/api/v1/rate-limit/status`,
    simulate: `${API_BASE_URL}/api/v1/rate-limit/simulate`,
    record: `${API_BASE_URL}/api/v1/rate-limit/record`,
    reset: `${API_BASE_URL}/api/v1/rate-limit/reset`
  },

  templates: `${API_BASE_URL}/api/v1/intent-templates`,
  templatesById: (id: string) => `${API_BASE_URL}/api/v1/intent-templates/${id}`,

  topology: `${API_BASE_URL}/api/v1/topology`,
  topologyDevices: `${API_BASE_URL}/api/v1/topology/devices`,
  topologyDeviceById: (id: string) => `${API_BASE_URL}/api/v1/topology/devices/${id}`,

  deepseek: {
    status: `${API_BASE_URL}/api/v2/deepseek/status`,
    parse: `${API_BASE_URL}/api/v2/deepseek/parse`
  },

  copilot: {
    chatStream: `${API_BASE_URL}/api/v2/copilot/chat/stream`,
    suggestions: `${API_BASE_URL}/api/v2/copilot/suggestions`
  },

  security: {
    scan: `${API_BASE_URL}/api/v2/security/scan`
  },

  knowledge: {
    query: `${API_BASE_URL}/api/v1/knowledge/query`,
    chatStream: `${API_BASE_URL}/api/v1/knowledge/chat/stream`,
    documents: `${API_BASE_URL}/api/v1/knowledge/documents`,
    addDocument: `${API_BASE_URL}/api/v1/knowledge/documents`,
    updateDocument: (id: string) => `${API_BASE_URL}/api/v1/knowledge/documents/${id}`,
    deleteDocument: (id: string) => `${API_BASE_URL}/api/v1/knowledge/documents/${id}`,
    searchDocuments: `${API_BASE_URL}/api/v1/knowledge/documents/search`,
    wizards: `${API_BASE_URL}/api/v1/knowledge/wizards`,
    wizardExecute: `${API_BASE_URL}/api/v1/knowledge/wizards/execute`,
    planExecute: `${API_BASE_URL}/api/v1/knowledge/plan-execute`,
    feedback: `${API_BASE_URL}/api/v1/knowledge/feedback`
  },

  workflow: {
    board: `${API_BASE_URL}/api/v1/workflow/board`,
    orders: `${API_BASE_URL}/api/v1/workflow/orders`,
    orderById: (id: string) => `${API_BASE_URL}/api/v1/workflow/orders/${id}`,
    approveOrder: (id: string) => `${API_BASE_URL}/api/v1/workflow/orders/${id}/approve`,
    rejectOrder: (id: string) => `${API_BASE_URL}/api/v1/workflow/orders/${id}/reject`,
    executeOrder: (id: string) => `${API_BASE_URL}/api/v1/workflow/orders/${id}/execute`,
    completeOrder: (id: string) => `${API_BASE_URL}/api/v1/workflow/orders/${id}/complete`
  },

  compute: {
    tasks: `${API_BASE_URL}/api/v1/compute/tasks`,
    taskById: (id: string) => `${API_BASE_URL}/api/v1/compute/tasks/${id}`,
    cancelTask: (id: string) => `${API_BASE_URL}/api/v1/compute/tasks/${id}`,
    retryTask: (id: string) => `${API_BASE_URL}/api/v1/compute/tasks/${id}/retry`,
    nodes: `${API_BASE_URL}/api/v1/compute/nodes`
  },

  map: {
    amapConfig: `${API_BASE_URL}/api/v1/map/amap/config`,
    agentsGeo: `${API_BASE_URL}/api/v1/map/agents/geo`,
    agentRegister: `${API_BASE_URL}/api/v1/map/agents/register`,
    markers: `${API_BASE_URL}/api/v1/map/markers`,
    markersBatch: `${API_BASE_URL}/api/v1/map/markers/batch`,
    markerById: (id: string) => `${API_BASE_URL}/api/v1/map/markers/${id}`,
    pathPlan: `${API_BASE_URL}/api/v1/map/path/plan`,
    poiSearch: `${API_BASE_URL}/api/v1/map/poi/search`
  },

  crossDomain: {
    route: `${API_BASE_URL}/api/v1/cross-domain/route`,
    topology: `${API_BASE_URL}/api/v1/cross-domain/topology`,
    discover: `${API_BASE_URL}/api/v1/cross-domain/discover`,
    register: `${API_BASE_URL}/api/v1/cross-domain/register`,
    deregister: (agentId: string) => `${API_BASE_URL}/api/v1/cross-domain/agents/${agentId}`,
  },

  system: {
    fuseStatus: `${API_BASE_URL}/api/v1/system/fuse/status`,
    fuse: `${API_BASE_URL}/api/v1/system/fuse`
  },

  assistant: {
    chat: `${API_BASE_URL}/api/v1/knowledge/chat`,
    context: (route: string) => `${API_BASE_URL}/api/v1/knowledge/context/${route}`,
    history: `${API_BASE_URL}/api/v1/knowledge/history`,
    conversation: (sessionId: string) => `${API_BASE_URL}/api/v1/knowledge/conversation/${sessionId}`,
    reactChat: `${API_BASE_URL}/api/v1/knowledge/react-chat`,
    reactApprove: `${API_BASE_URL}/api/v1/knowledge/react-approve`,
    llmStatus: `${API_BASE_URL}/api/v1/knowledge/llm-status`
  },

  observability: {
    overview: `${API_BASE_URL}/api/v1/observability/metrics/overview`,
    agentsHealth: `${API_BASE_URL}/api/v1/observability/agents/health`,
    agentHealth: (id: string) => `${API_BASE_URL}/api/v1/observability/agents/${id}/health`,
    traces: `${API_BASE_URL}/api/v1/observability/traces`,
    traceDetail: (id: string) => `${API_BASE_URL}/api/v1/observability/traces/${id}`,
    healthCheck: `${API_BASE_URL}/api/v1/observability/health-check`
  },

  failedIntents: {
    list: `${API_BASE_URL}/api/v1/failed-intents`,
    stats: `${API_BASE_URL}/api/v1/failed-intents/stats`,
    finetuningData: `${API_BASE_URL}/api/v1/failed-intents/finetuning-data`,
    byId: (id: string) => `${API_BASE_URL}/api/v1/failed-intents/${id}`,
    resolve: (id: string) => `${API_BASE_URL}/api/v1/failed-intents/${id}/resolve`
  },

  clarification: {
    analyze: `${API_BASE_URL}/api/v1/clarification/analyze`,
    respond: `${API_BASE_URL}/api/v1/clarification/respond`,
    session: (id: string) => `${API_BASE_URL}/api/v1/clarification/session/${id}`
  },

  intentTemplates: {
    list: `${API_BASE_URL}/api/v1/intent-templates`,
    categories: `${API_BASE_URL}/api/v1/intent-templates/categories`,
    popular: `${API_BASE_URL}/api/v1/intent-templates/popular`,
    byId: (id: string) => `${API_BASE_URL}/api/v1/intent-templates/${id}`,
    instantiate: (id: string) => `${API_BASE_URL}/api/v1/intent-templates/${id}/instantiate`,
    rate: (id: string) => `${API_BASE_URL}/api/v1/intent-templates/${id}/rate`,
    clone: (id: string) => `${API_BASE_URL}/api/v1/intent-templates/${id}/clone`
  },

  playbooks: {
    list: `${API_BASE_URL}/api/v1/playbooks`,
    byId: (id: string) => `${API_BASE_URL}/api/v1/playbooks/${id}`,
    execute: (id: string) => `${API_BASE_URL}/api/v1/playbooks/${id}/execute`,
    executions: `${API_BASE_URL}/api/v1/playbooks/executions`,
    executionById: (id: string) => `${API_BASE_URL}/api/v1/playbooks/executions/${id}`,
    approveExecution: (id: string) => `${API_BASE_URL}/api/v1/playbooks/executions/${id}/approve`,
    cancelExecution: (id: string) => `${API_BASE_URL}/api/v1/playbooks/executions/${id}/cancel`
  },

  sla: {
    predictions: `${API_BASE_URL}/api/v1/sla/predictions`,
    predictionById: (id: string) => `${API_BASE_URL}/api/v1/sla/predictions/${id}`,
    predict: (id: string) => `${API_BASE_URL}/api/v1/sla/predict/${id}`,
    alerts: `${API_BASE_URL}/api/v1/sla/alerts`,
    dynamicIntervals: `${API_BASE_URL}/api/v1/sla/dynamic-intervals`,
    dashboard: `${API_BASE_URL}/api/v1/sla/dashboard`
  },

  scheduler: {
    queue: `${API_BASE_URL}/api/v1/scheduler/queue`,
    enqueue: `${API_BASE_URL}/api/v1/scheduler/enqueue`,
    dequeue: `${API_BASE_URL}/api/v1/scheduler/dequeue`,
    position: (id: string) => `${API_BASE_URL}/api/v1/scheduler/position/${id}`,
    resources: `${API_BASE_URL}/api/v1/scheduler/resources`,
    rebalance: `${API_BASE_URL}/api/v1/scheduler/rebalance`
  },

  llmRouter: {
    providers: `${API_BASE_URL}/api/v1/llm-router/providers`,
    providerByName: (name: string) => `${API_BASE_URL}/api/v1/llm-router/providers/${name}`,
    toggleProvider: (name: string) => `${API_BASE_URL}/api/v1/llm-router/providers/${name}/toggle`,
    recommendations: (taskType: string) => `${API_BASE_URL}/api/v1/llm-router/recommendations/${taskType}`,
    metrics: `${API_BASE_URL}/api/v1/llm-router/metrics`
  },

  grayscaleHealing: {
    tasks: `${API_BASE_URL}/api/v1/grayscale-healing/tasks`,
    taskById: (id: string) => `${API_BASE_URL}/api/v1/grayscale-healing/tasks/${id}`,
    canary: (id: string) => `${API_BASE_URL}/api/v1/grayscale-healing/tasks/${id}/canary`,
    batch: (id: string) => `${API_BASE_URL}/api/v1/grayscale-healing/tasks/${id}/batch`,
    rollback: (id: string) => `${API_BASE_URL}/api/v1/grayscale-healing/tasks/${id}/rollback`,
    analyze: (id: string) => `${API_BASE_URL}/api/v1/grayscale-healing/tasks/${id}/analyze`,
    evaluate: `${API_BASE_URL}/api/v1/grayscale-healing/evaluate`,
    evaluations: `${API_BASE_URL}/api/v1/grayscale-healing/evaluations`
  },

  webhooks: {
    subscriptions: `${API_BASE_URL}/api/v1/webhooks/subscriptions`,
    subscriptionById: (id: string) => `${API_BASE_URL}/api/v1/webhooks/subscriptions/${id}`,
    toggle: (id: string) => `${API_BASE_URL}/api/v1/webhooks/subscriptions/${id}/toggle`,
    logs: (id: string) => `${API_BASE_URL}/api/v1/webhooks/subscriptions/${id}/logs`,
    test: `${API_BASE_URL}/api/v1/webhooks/test`,
    events: `${API_BASE_URL}/api/v1/webhooks/events`
  },

  agentManagement: {
    scores: `${API_BASE_URL}/api/v1/agent-management/scores`,
    scoreById: (id: string) => `${API_BASE_URL}/api/v1/agent-management/scores/${id}`,
    recalculate: `${API_BASE_URL}/api/v1/agent-management/scores/recalculate`,
    recommendations: (taskType: string) => `${API_BASE_URL}/api/v1/agent-management/recommendations/${taskType}`,
    upgrade: `${API_BASE_URL}/api/v1/agent-management/upgrade`,
    upgradeHistory: `${API_BASE_URL}/api/v1/agent-management/upgrade/history`,
    upgradeStatus: (id: string) => `${API_BASE_URL}/api/v1/agent-management/upgrade/${id}/status`,
    upgradeRollback: (id: string) => `${API_BASE_URL}/api/v1/agent-management/upgrade/${id}/rollback`
  },

  topologyMap: {
    devices: `${API_BASE_URL}/api/v1/topology/devices`,
    links: `${API_BASE_URL}/api/v1/topology/links`,
    view: `${API_BASE_URL}/api/v1/topology/view`,
    deviceById: (id: string) => `${API_BASE_URL}/api/v1/topology/devices/${id}`,
    health: `${API_BASE_URL}/api/v1/topology/health`,
    search: `${API_BASE_URL}/api/v1/topology/search`
  },

  terraform: {
    configure: `${API_BASE_URL}/api/v1/terraform/configure`,
    schema: `${API_BASE_URL}/api/v1/terraform/schema`,
    resources: (type: string) => `${API_BASE_URL}/api/v1/terraform/resources/${type}`,
    resourceById: (type: string, id: string) => `${API_BASE_URL}/api/v1/terraform/resources/${type}/${id}`,
    plan: `${API_BASE_URL}/api/v1/terraform/plan`,
    import: `${API_BASE_URL}/api/v1/terraform/import`
  },

  knowledgeVersions: {
    versions: (docId: string) => `${API_BASE_URL}/api/v1/knowledge/versions/${docId}`,
    versionDetail: (versionId: string) => `${API_BASE_URL}/api/v1/knowledge/versions/detail/${versionId}`,
    rollback: (docId: string) => `${API_BASE_URL}/api/v1/knowledge/versions/${docId}/rollback`,
    compare: (docId: string) => `${API_BASE_URL}/api/v1/knowledge/versions/${docId}/compare`,
    contributions: `${API_BASE_URL}/api/v1/knowledge/contributions`,
    stats: `${API_BASE_URL}/api/v1/knowledge/versions/stats`
  },

  notifications: {
    list: `${API_BASE_URL}/api/v1/knowledge/notifications`,
    unread: `${API_BASE_URL}/api/v1/knowledge/notifications/unread`,
    read: (id: string) => `${API_BASE_URL}/api/v1/knowledge/notifications/${id}/read`,
    dismiss: (id: string) => `${API_BASE_URL}/api/v1/knowledge/notifications/${id}/dismiss`
  },

  quickCommands: {
    list: `${API_BASE_URL}/api/v1/knowledge/quick-commands`,
    create: `${API_BASE_URL}/api/v1/knowledge/quick-commands`,
    execute: `${API_BASE_URL}/api/v1/knowledge/quick-commands/execute`,
    delete: (id: string) => `${API_BASE_URL}/api/v1/knowledge/quick-commands/${id}`
  },

  upload: `${API_BASE_URL}/api/v1/knowledge/assistant-upload`
}

export const createApiClient = () => {
  const request = async <T = any>(
    url: string,
    options: RequestInit = {}
  ): Promise<{ data: T; status: string; message?: string }> => {
    const defaultHeaders: HeadersInit = {
      'Content-Type': 'application/json'
    }
    const token = getAccessToken()
    if (token) {
      (defaultHeaders as Record<string, string>)['Authorization'] = `Bearer ${token}`
    }

    let response = await fetch(url, {
      ...options,
      credentials: 'include',
      headers: {
        ...defaultHeaders,
        ...options.headers
      }
    })

    if (response.status === 401 && token) {
      const handled = await handle401(token)
      if (handled) {
        const newToken = getAccessToken()
        response = await fetch(url, {
          ...options,
          headers: {
            ...defaultHeaders,
            ...options.headers,
            'Authorization': `Bearer ${newToken}`
          }
        })
      } else {
        throw new Error('Session expired')
      }
    }

    if (!response.ok) {
      let errorMsg = `HTTP error! status: ${response.status}`
      try {
        const errText = await response.text()
        const errData = errText ? JSON.parse(errText) : {}
        errorMsg = errData.detail || errData.message || errorMsg

        // Auto-detect fuse state from 503 response
        if (response.status === 503 && errData.triggered_by) {
          const { useAppStore } = await import('@/stores/app')
          const appStore = useAppStore()
          if (!appStore.fuseEnabled) {
            appStore.fuseEnabled = true
            appStore.fuseReason = errData.message || '系统紧急熔断'
          }
        }
      } catch {}
      throw new Error(errorMsg)
    }

    if (response.status === 204) {
      return { data: null as T, status: 'success' }
    }

    let result: any
    try {
      const responseText = await response.text()
      result = responseText ? JSON.parse(responseText) : {}
    } catch {
      throw new Error('Invalid response format')
    }

    if (result.status === 'error') {
      throw new Error(result.message || 'API request failed')
    }

    if (result.status === 'success') {
      const { status: _, ...rest } = result
      // 如果有 data 字段则解包 data，否则保留整个 rest 作为数据
      const data = rest.data !== undefined ? rest.data : rest
      return { data: data as T, status: 'success', message: result.message }
    }

    return { data: result as T, status: 'success' }
  }

  const get = <T = any>(url: string, options?: RequestInit) => {
    return request<T>(url, { ...options, method: 'GET' })
  }

  const post = <T = any>(url: string, data?: any, options?: RequestInit) => {
    return request<T>(url, {
      ...options,
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined
    })
  }

  const put = <T = any>(url: string, data?: any, options?: RequestInit) => {
    return request<T>(url, {
      ...options,
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined
    })
  }

  const del = <T = any>(url: string, options?: RequestInit) => {
    return request<T>(url, { ...options, method: 'DELETE' })
  }

  return {
    get,
    post,
    put,
    delete: del
  }
}

export const apiClient = createApiClient()

export const authFetch = async (url: string, options: RequestInit = {}): Promise<Response> => {
  const headers = new Headers(options.headers || {})
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getAccessToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  let response = await fetch(url, { ...options, headers, credentials: 'include' })

  if (response.status === 401 && token) {
    const handled = await handle401(token)
    if (handled) {
      const newToken = getAccessToken()
      headers.set('Authorization', `Bearer ${newToken}`)
      response = await fetch(url, { ...options, headers })
    } else {
      throw new Error('Session expired')
    }
  }

  return response
}
