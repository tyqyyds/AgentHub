<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useLogger } from '@/utils/logger'
import { DEBOUNCE, VALIDATION } from '@/config'
import { api, authFetch } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'
import { useAuthStore } from '@/stores/auth'

const { info, warn } = useLogger()
const authStore = useAuthStore()
const canWrite = computed(() => authStore.userRole !== 'viewer')

interface MCPToolParam {
  type: string
  description: string
  default?: unknown
}

interface MCPTool {
  name: string
  description: string
  category: string
  tags: string[]
  version: string
  author: string
  rating: number
  ratingCount: number
  downloads: number
  lastUpdated: string
  args_schema: {
    type: string
    properties: Record<string, MCPToolParam>
    required: string[]
  }
  is_custom?: boolean
}

interface NewToolParam {
  name: string
  description: string
  required: boolean
}

interface ToolReview {
  id: string
  user: string
  rating: number
  comment: string
  timestamp: string
}

interface MetricCard {
  label: string
  value: number
  displayValue: number
  unit: string
  icon: string
  color: string
  animFrameId: number | null
}

const TOOL_CATEGORIES = [
  { key: 'all', label: '全部', icon: '🔧' },
  { key: 'network_config', label: '网络配置', icon: '⚙️' },
  { key: 'network_diagnosis', label: '网络诊断', icon: '🔍' },
  { key: 'security', label: '安全策略', icon: '🔒' },
  { key: 'device_management', label: '设备管理', icon: '🖥️' },
  { key: 'custom', label: '自定义', icon: '✨' }
]

const SORT_OPTIONS = [
  { key: 'name', label: '按名称' },
  { key: 'rating', label: '按评分' },
  { key: 'downloads', label: '按下载量' },
  { key: 'lastUpdated', label: '按更新时间' }
]

const tools = ref<MCPTool[]>([])
const isMockData = ref(false)
const loadingState = ref<'initial' | 'refreshing' | 'idle'>('initial')
const searchQuery = ref('')
const selectedTool = ref<MCPTool | null>(null)
const showDetailModal = ref(false)
const showTryItModal = ref(false)
const showAddToolModal = ref(false)
const showDeleteConfirmModal = ref(false)
const toolToDelete = ref<MCPTool | null>(null)
const deleteToolLoading = ref(false)
const deleteToolMessage = ref('')
const deleteToolSuccess = ref(false)
const tryItParams = ref<Record<string, string>>({})
const tryItResult = ref('')
const tryItLoading = ref(false)

const executionHistory = ref<any[]>([])
const showExecutionHistory = ref(false)

const fetchExecutionHistory = async () => {
  try {
    const response = await authFetch(api.mcpToolsHistory)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    executionHistory.value = Array.isArray(data.data) ? data.data : (Array.isArray(data) ? data : [])
  } catch {
    executionHistory.value = []
  }
}

const newToolName = ref('')
const newToolDescription = ref('')
const newToolParams = ref<NewToolParam[]>([
  { name: '', description: '', required: false }
])
const addToolLoading = ref(false)
const addToolMessage = ref('')
const addToolSuccess = ref(false)
const nameError = ref('')
const descError = ref('')
const paramErrors = ref<Record<number, { name?: string; description?: string }>>({})
const nameCheckLoading = ref(false)

const nameInput = ref<HTMLInputElement>()
const descInput = ref<HTMLInputElement>()

const activeCategory = ref('all')
const activeTag = ref('')
const sortBy = ref('name')
const dataFreshness = ref('实时')
const lastRefreshTime = ref('')
const showExportMenu = ref(false)
const toolReviews = ref<Record<string, ToolReview[]>>({})
const newReviewRating = ref(0)
const newReviewComment = ref('')

const metrics = ref<MetricCard[]>([
  { label: '工具总数', value: 0, displayValue: 0, unit: '个', icon: '🔧', color: '#165DFF', animFrameId: null },
  { label: '自定义工具', value: 0, displayValue: 0, unit: '个', icon: '✨', color: '#8B5CF6', animFrameId: null },
  { label: '内置工具', value: 0, displayValue: 0, unit: '个', icon: '⚙️', color: '#52C41A', animFrameId: null },
  { label: '平均评分', value: 0, displayValue: 0, unit: '分', icon: '⭐', color: '#FAAD14', animFrameId: null }
])

let fetchAbortController: AbortController | null = null
let isFetching = false
let searchDebounceTimer: number | null = null
let addToolSuccessTimer: number | null = null
let deleteToolSuccessTimer: number | null = null
let visibilityDebounceTimer: number | null = null
let handleDataUpdate: (() => void) | null = null

const animateValue = (metric: MetricCard, from: number, to: number, duration: number = 600) => {
  if (metric.animFrameId) cancelAnimationFrame(metric.animFrameId)
  const startTime = performance.now()
  const animate = (currentTime: number) => {
    const elapsed = currentTime - startTime
    const progress = Math.min(elapsed / duration, 1)
    const eased = 1 - Math.pow(1 - progress, 3)
    metric.displayValue = Math.round(from + (to - from) * eased)
    if (progress < 1) {
      metric.animFrameId = requestAnimationFrame(animate)
    } else {
      metric.animFrameId = null
    }
  }
  metric.animFrameId = requestAnimationFrame(animate)
}

watch(() => metrics.value.map(m => m.value), (newVals, oldVals) => {
  newVals.forEach((val, i) => {
    const oldVal = oldVals?.[i] ?? 0
    if (val !== oldVal) {
      animateValue(metrics.value[i], oldVal, val)
    }
  })
}, { deep: true })

const updateMetrics = () => {
  const all = tools.value
  const custom = all.filter(t => t.is_custom)
  const builtin = all.filter(t => !t.is_custom)
  const avgRating = all.length > 0 ? Math.round(all.reduce((sum, t) => sum + t.rating, 0) / all.length * 10) / 10 : 0

  metrics.value[0].value = all.length
  metrics.value[1].value = custom.length
  metrics.value[2].value = builtin.length
  metrics.value[3].value = avgRating
}

const allTags = computed(() => {
  const tagSet = new Set<string>()
  tools.value.forEach(t => t.tags.forEach(tag => tagSet.add(tag)))
  return Array.from(tagSet)
})

const filteredTools = computed(() => {
  let result = tools.value

  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(tool =>
      tool.name.toLowerCase().includes(query) ||
      tool.description.toLowerCase().includes(query) ||
      tool.tags.some(tag => tag.toLowerCase().includes(query))
    )
  }

  if (activeCategory.value !== 'all') {
    if (activeCategory.value === 'custom') {
      result = result.filter(tool => tool.is_custom)
    } else {
      result = result.filter(tool => tool.category === activeCategory.value)
    }
  }

  if (activeTag.value) {
    result = result.filter(tool => tool.tags.includes(activeTag.value))
  }

  result = [...result].sort((a, b) => {
    switch (sortBy.value) {
      case 'rating': return b.rating - a.rating
      case 'downloads': return b.downloads - a.downloads
      case 'lastUpdated': return new Date(b.lastUpdated).getTime() - new Date(a.lastUpdated).getTime()
      case 'name': default: return a.name.localeCompare(b.name)
    }
  })

  return result
})

const getCategoryIcon = (category: string): string => {
  const found = TOOL_CATEGORIES.find(c => c.key === category)
  return found ? found.icon : '🔧'
}

const getCategoryLabel = (category: string): string => {
  const found = TOOL_CATEGORIES.find(c => c.key === category)
  return found ? found.label : category
}

const filterToolName = () => {
  newToolName.value = newToolName.value
    .replace(/[^a-zA-Z0-9_]/g, '')
    .replace(/^[0-9]+/, '')
    .slice(0, VALIDATION.TOOL_NAME.MAX_LENGTH)
  nameError.value = ''
}

const validateToolNameFormat = (name: string): { valid: boolean; error: string } => {
  if (!name.trim()) {
    return { valid: false, error: '工具名称不能为空' }
  }
  if (name.length < VALIDATION.TOOL_NAME.MIN_LENGTH) {
    return { valid: false, error: `工具名称至少需要${VALIDATION.TOOL_NAME.MIN_LENGTH}个字符` }
  }
  if (!VALIDATION.TOOL_NAME.PATTERN.test(name)) {
    return { valid: false, error: '只能以字母开头，包含字母、数字和下划线' }
  }
  return { valid: true, error: '' }
}

const validateToolDescription = (desc: string): { valid: boolean; error: string } => {
  if (!desc.trim()) {
    return { valid: false, error: '工具描述不能为空' }
  }
  if (desc.trim().length < VALIDATION.TOOL_DESCRIPTION.MIN_LENGTH) {
    return { valid: false, error: `描述至少需要${VALIDATION.TOOL_DESCRIPTION.MIN_LENGTH}个字符` }
  }
  if (desc.trim().length > VALIDATION.TOOL_DESCRIPTION.MAX_LENGTH) {
    return { valid: false, error: `描述不能超过${VALIDATION.TOOL_DESCRIPTION.MAX_LENGTH}个字符` }
  }
  const invalidPatterns = ['随便填', '123', '测试', 'test']
  const trimmed = desc.trim()
  if (invalidPatterns.some(p => trimmed.toLowerCase() === p.toLowerCase())) {
    return { valid: false, error: '请填写有效的工具描述' }
  }
  return { valid: true, error: '' }
}

const validateParams = (params: NewToolParam[]): { valid: boolean; errors: Record<number, { name?: string; description?: string }> } => {
  const errors: Record<number, { name?: string; description?: string }> = {}
  const usedNames = new Set<string>()
  let hasError = false

  for (let i = 0; i < params.length; i++) {
    const param = params[i]
    errors[i] = {}

    if (!param.name.trim() && !param.description.trim()) {
      if (params.length > 1 && i < params.length - 1) {
        errors[i].name = '请完善或删除此参数'
        hasError = true
      }
      continue
    }

    if (param.name.trim()) {
      if (!VALIDATION.PARAM_NAME.PATTERN.test(param.name)) {
        errors[i].name = `字母开头，${VALIDATION.PARAM_NAME.MIN_LENGTH}-${VALIDATION.PARAM_NAME.MAX_LENGTH}字符，仅字母/数字/下划线`
        hasError = true
      } else if (usedNames.has(param.name.toLowerCase())) {
        errors[i].name = '参数名重复'
        hasError = true
      } else {
        usedNames.add(param.name.toLowerCase())
      }
    } else {
      errors[i].name = '请填写参数名'
      hasError = true
    }

    if (param.description.trim()) {
      if (param.description.trim().length < VALIDATION.PARAM_DESCRIPTION.MIN_LENGTH) {
        errors[i].description = `描述至少需要${VALIDATION.PARAM_DESCRIPTION.MIN_LENGTH}个字符`
        hasError = true
      } else if (param.description.trim().length > VALIDATION.PARAM_DESCRIPTION.MAX_LENGTH) {
        errors[i].description = `描述不能超过${VALIDATION.PARAM_DESCRIPTION.MAX_LENGTH}个字符`
        hasError = true
      }
    } else {
      errors[i].description = '请填写参数描述'
      hasError = true
    }
  }

  return { valid: !hasError, errors }
}

const checkToolNameUnique = async (name: string): Promise<boolean> => {
  if (!name.trim()) return false

  nameCheckLoading.value = true
  try {
    const response = await authFetch(`${api.mcpToolsCheckName}?name=${encodeURIComponent(name)}`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    return data.available
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    warn('检查工具名称失败', { error: message })
    nameError.value = '无法验证名称唯一性，请检查网络后重试'
    return false
  } finally {
    nameCheckLoading.value = false
  }
}

const fetchTools = async (showLoading = false) => {
  if (isFetching) return
  isFetching = true

  if (fetchAbortController) {
    fetchAbortController.abort()
  }
  fetchAbortController = new AbortController()
  const signal = fetchAbortController.signal

  lastRefreshTime.value = new Date().toLocaleTimeString()
  if (showLoading) loadingState.value = 'refreshing'

  try {
    const url = searchQuery.value
      ? `${api.mcpTools}?q=${encodeURIComponent(searchQuery.value)}`
      : `${api.mcpTools}`
    const response = await authFetch(url, { signal })
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    const data = await response.json()
    if (data.status === 'success') {
      tools.value = (data.data || []).map((tool: Record<string, unknown>) => {
        const rawSchema = tool.args_schema as Record<string, unknown> || {}
        const isSimpleSchema = Object.values(rawSchema).every(v => typeof v === 'string')
        let properties: Record<string, MCPToolParam>
        let required: string[] = []

        if (isSimpleSchema && !rawSchema.type) {
          properties = Object.entries(rawSchema).reduce((acc, [key, value]) => {
            acc[key] = {
              type: 'string',
              description: typeof value === 'string' ? value : '参数'
            }
            return acc
          }, {} as Record<string, MCPToolParam>)
        } else {
          properties = (rawSchema.properties as Record<string, MCPToolParam>) || {}
          required = (rawSchema.required as string[]) || []
        }

        return {
          name: tool.name as string,
          description: tool.description as string,
          category: (tool.category as string) || guessCategory(tool.name as string),
          tags: (tool.tags as string[]) || guessTags(tool.name as string, tool.description as string),
          version: (tool.version as string) || '1.0.0',
          author: (tool.author as string) || '系统',
          rating: typeof tool.rating === 'number' ? tool.rating : 0,
          ratingCount: typeof tool.ratingCount === 'number' ? tool.ratingCount : 0,
          downloads: typeof tool.downloads === 'number' ? tool.downloads : 0,
          lastUpdated: (tool.lastUpdated as string) || new Date().toISOString().split('T')[0],
          args_schema: {
            type: 'object',
            properties,
            required
          },
          is_custom: tool.is_custom as boolean | undefined
        }
      })
      updateMetrics()
      dataFreshness.value = '实时'
      isMockData.value = false
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    const message = err instanceof Error ? err.message : String(err)
    warn('获取MCP工具失败', { error: message })
    loadMockData()
    isMockData.value = true
    dataFreshness.value = '降级'
  } finally {
    loadingState.value = 'idle'
    isFetching = false
    fetchAbortController = null
  }
}

const guessCategory = (name: string): string => {
  if (/config|qos|acl|policy|bandwidth/i.test(name)) return 'network_config'
  if (/ping|traceroute|diagnos|show|check|test/i.test(name)) return 'network_diagnosis'
  if (/security|firewall|encrypt|auth/i.test(name)) return 'security'
  if (/device|interface|status|version/i.test(name)) return 'device_management'
  return 'network_config'
}

const guessTags = (name: string, description: string): string[] => {
  const tags: string[] = []
  const combined = `${name} ${description}`.toLowerCase()
  if (/qos|带宽|bandwidth/i.test(combined)) tags.push('QoS')
  if (/acl|访问|access/i.test(combined)) tags.push('ACL')
  if (/接口|interface/i.test(combined)) tags.push('接口')
  if (/路由|route/i.test(combined)) tags.push('路由')
  if (/ping|连通/i.test(combined)) tags.push('连通性')
  if (/安全|security/i.test(combined)) tags.push('安全')
  if (tags.length === 0) tags.push('通用')
  return tags
}

const debouncedFetchTools = () => {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
  searchDebounceTimer = window.setTimeout(() => {
    fetchTools()
  }, DEBOUNCE.SEARCH)
}

const loadMockData = () => {
  tools.value = [
    {
      name: 'show_interface',
      description: '显示网络设备接口状态',
      category: 'device_management',
      tags: ['接口', '连通性'],
      version: '1.2.0',
      author: '系统',
      rating: 4.5,
      ratingCount: 32,
      downloads: 456,
      lastUpdated: '2025-05-20',
      args_schema: {
        type: 'object',
        properties: {
          device: { type: 'string', description: '目标设备名称' },
          interface: { type: 'string', description: '接口名称' }
        },
        required: ['device', 'interface']
      },
      is_custom: false
    },
    {
      name: 'config_qos',
      description: '配置QoS策略',
      category: 'network_config',
      tags: ['QoS', '带宽'],
      version: '2.1.0',
      author: '系统',
      rating: 4.2,
      ratingCount: 28,
      downloads: 312,
      lastUpdated: '2025-05-18',
      args_schema: {
        type: 'object',
        properties: {
          device: { type: 'string', description: '目标设备名称' },
          class_name: { type: 'string', description: 'QoS类名' },
          bandwidth_percent: { type: 'integer', description: '带宽百分比' }
        },
        required: ['device', 'class_name', 'bandwidth_percent']
      },
      is_custom: false
    },
    {
      name: 'ping',
      description: '执行网络连通性测试',
      category: 'network_diagnosis',
      tags: ['连通性'],
      version: '1.0.0',
      author: '系统',
      rating: 4.8,
      ratingCount: 56,
      downloads: 892,
      lastUpdated: '2025-05-22',
      args_schema: {
        type: 'object',
        properties: {
          target: { type: 'string', description: '目标IP地址或主机名' },
          count: { type: 'integer', description: 'ping次数', default: 4 }
        },
        required: ['target']
      },
      is_custom: false
    },
    {
      name: 'config_acl',
      description: '配置ACL规则',
      category: 'security',
      tags: ['ACL', '安全'],
      version: '3.0.1',
      author: '系统',
      rating: 4.0,
      ratingCount: 19,
      downloads: 178,
      lastUpdated: '2025-05-15',
      args_schema: {
        type: 'object',
        properties: {
          device: { type: 'string', description: '目标设备名称' },
          acl_name: { type: 'string', description: 'ACL名称' },
          action: { type: 'string', description: '动作: permit或deny' },
          protocol: { type: 'string', description: '协议' },
          source: { type: 'string', description: '源地址' },
          destination: { type: 'string', description: '目标地址' }
        },
        required: ['device', 'acl_name', 'action', 'protocol', 'source', 'destination']
      },
      is_custom: false
    },
    {
      name: 'get_device_status',
      description: '获取设备状态',
      category: 'device_management',
      tags: ['接口'],
      version: '1.1.0',
      author: '系统',
      rating: 4.3,
      ratingCount: 24,
      downloads: 267,
      lastUpdated: '2025-05-19',
      args_schema: {
        type: 'object',
        properties: {
          device: { type: 'string', description: '目标设备名称' }
        },
        required: ['device']
      },
      is_custom: false
    },
    {
      name: 'traceroute',
      description: '追踪网络数据包路径',
      category: 'network_diagnosis',
      tags: ['连通性', '路由'],
      version: '1.0.0',
      author: '系统',
      rating: 4.6,
      ratingCount: 41,
      downloads: 534,
      lastUpdated: '2025-05-21',
      args_schema: {
        type: 'object',
        properties: {
          target: { type: 'string', description: '目标IP地址或主机名' },
          max_hops: { type: 'integer', description: '最大跳数', default: 30 }
        },
        required: ['target']
      },
      is_custom: false
    }
  ]
  updateMetrics()
}

const showToolDetail = (tool: MCPTool) => {
  selectedTool.value = tool
  newReviewRating.value = 0
  newReviewComment.value = ''
  showDetailModal.value = true
  loadToolReviews(tool.name)
}

const closeDetailModal = () => {
  showDetailModal.value = false
  selectedTool.value = null
}

const openTryItModal = (tool: MCPTool, event?: Event) => {
  if (event) {
    event.stopPropagation()
  }
  selectedTool.value = tool
  tryItParams.value = {}
  tryItResult.value = ''
  showTryItModal.value = true
}

const closeTryItModal = () => {
  showTryItModal.value = false
  selectedTool.value = null
  tryItParams.value = {}
  tryItResult.value = ''
}

const executeTryIt = async () => {
  if (!selectedTool.value) return

  tryItLoading.value = true
  tryItResult.value = ''
  try {
    const params: Record<string, string> = {}
    for (const [key, val] of Object.entries(tryItParams.value)) {
      if (val && val.trim()) params[key] = val.trim()
    }
    const response = await authFetch(api.mcpToolsExecute, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tool_name: selectedTool.value.name,
        parameters: params
      })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    tryItResult.value = JSON.stringify({
      status: data.status || 'success',
      output: data.result || data.output || JSON.stringify(data, null, 2),
      execution_time: data.execution_time || 0,
      tool_name: selectedTool.value.name
    }, null, 2)
    showToast('工具执行完成', 'success')
    fetchExecutionHistory()
  } catch (e: unknown) {
    tryItResult.value = JSON.stringify({
      status: 'error',
      output: e instanceof Error ? e.message : '执行失败',
      execution_time: 0,
      tool_name: selectedTool.value?.name || ''
    }, null, 2)
    showToast('工具执行失败', 'error')
  } finally {
    tryItLoading.value = false
  }
}

const openAddToolModal = () => {
  newToolName.value = ''
  newToolDescription.value = ''
  newToolParams.value = [{ name: '', description: '', required: false }]
  addToolMessage.value = ''
  addToolSuccess.value = false
  nameError.value = ''
  descError.value = ''
  paramErrors.value = {}
  showAddToolModal.value = true
}

const closeAddToolModal = () => {
  showAddToolModal.value = false
}

const addNewParam = () => {
  if (newToolParams.value.length < VALIDATION.MAX_PARAMS) {
    newToolParams.value.push({ name: '', description: '', required: false })
  }
}

const removeParam = (index: number) => {
  if (newToolParams.value.length > 1) {
    newToolParams.value.splice(index, 1)
    const newErrors: Record<number, { name?: string; description?: string }> = {}
    const entries = Object.entries(paramErrors.value).filter(([key]) => Number(key) !== index)
    for (const [key, val] of entries) {
      const newKey = Number(key) > index ? Number(key) - 1 : Number(key)
      newErrors[newKey] = val
    }
    paramErrors.value = newErrors
  }
}

const filterParamName = (index: number) => {
  newToolParams.value[index].name = newToolParams.value[index].name
    .replace(/[^a-zA-Z0-9_]/g, '')
    .replace(/^[0-9]+/, '')
    .slice(0, VALIDATION.PARAM_NAME.MAX_LENGTH)
  if (paramErrors.value[index]) {
    delete paramErrors.value[index].name
  }
}

const submitNewTool = async () => {
  const nameValidation = validateToolNameFormat(newToolName.value)
  if (!nameValidation.valid) {
    nameError.value = nameValidation.error
    nextTick(() => nameInput.value?.focus())
    addToolMessage.value = '内容错误请重新输入'
    addToolSuccess.value = false
    return
  }

  const descValidation = validateToolDescription(newToolDescription.value)
  if (!descValidation.valid) {
    descError.value = descValidation.error
    nextTick(() => descInput.value?.focus())
    addToolMessage.value = '内容错误请重新输入'
    addToolSuccess.value = false
    return
  }

  const paramValidation = validateParams(newToolParams.value)
  if (!paramValidation.valid) {
    paramErrors.value = paramValidation.errors
    addToolMessage.value = '内容错误请重新输入'
    addToolSuccess.value = false
    return
  }

  const isNameUnique = await checkToolNameUnique(newToolName.value)
  if (!isNameUnique) {
    nameError.value = '工具名称已存在'
    nextTick(() => nameInput.value?.focus())
    addToolMessage.value = '内容错误请重新输入'
    addToolSuccess.value = false
    return
  }

  const validParams = newToolParams.value.filter(p => p.name.trim())
  const argsSchema: Record<string, string> = {}
  const requiredParams: string[] = []
  for (const param of validParams) {
    argsSchema[param.name.trim()] = param.description.trim()
    if (param.required) {
      requiredParams.push(param.name.trim())
    }
  }

  const toolConfig = {
    name: newToolName.value.trim(),
    description: newToolDescription.value.trim(),
    args_schema: argsSchema,
    required: requiredParams
  }

  addToolLoading.value = true
  addToolMessage.value = '正在验证并添加工具...'

  try {
    const response = await authFetch(api.mcpToolsAdd, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(toolConfig)
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    const data = await response.json()

    if (data.status === 'success') {
      addToolSuccess.value = true
      addToolMessage.value = '工具添加成功！'
      showToast('工具添加成功', 'success')
      await fetchTools()
      addToolSuccessTimer = window.setTimeout(() => {
        addToolSuccessTimer = null
        closeAddToolModal()
      }, 1500)
    } else {
      addToolSuccess.value = false
      addToolMessage.value = data.message || '内容错误请重新输入'
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    addToolSuccess.value = false
    addToolMessage.value = '内容错误请重新输入'
    warn('添加工具失败', { error: message })
  } finally {
    addToolLoading.value = false
  }
}

const openDeleteConfirmModal = (tool: MCPTool, event?: Event) => {
  if (event) {
    event.stopPropagation()
  }
  toolToDelete.value = tool
  deleteToolMessage.value = ''
  deleteToolSuccess.value = false
  showDeleteConfirmModal.value = true
}

const closeDeleteConfirmModal = () => {
  showDeleteConfirmModal.value = false
  toolToDelete.value = null
}

const deleteTool = async () => {
  if (!toolToDelete.value) return

  deleteToolLoading.value = true
  deleteToolMessage.value = '正在删除工具...'

  try {
    const response = await authFetch(api.mcpToolsDelete(toolToDelete.value.name), {
      method: 'DELETE'
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    const data = await response.json()

    if (data.status === 'success') {
      deleteToolSuccess.value = true
      deleteToolMessage.value = '工具删除成功！'
      showToast('工具删除成功', 'success')
      await fetchTools()
      deleteToolSuccessTimer = window.setTimeout(() => {
        deleteToolSuccessTimer = null
        closeDeleteConfirmModal()
      }, 1500)
    } else {
      deleteToolSuccess.value = false
      deleteToolMessage.value = data.message || '删除工具失败'
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    deleteToolSuccess.value = false
    deleteToolMessage.value = '网络错误，请稍后重试'
    warn('删除工具失败', { error: message })
  } finally {
    deleteToolLoading.value = false
  }
}

const submitReview = async () => {
  if (!selectedTool.value || newReviewRating.value === 0) return
  const toolName = selectedTool.value.name
  try {
    const resp = await apiClient.post(api.mcpTools + `/${encodeURIComponent(toolName)}/reviews`, {
      rating: newReviewRating.value,
      comment: newReviewComment.value
    })
    const reviewData = resp.data || resp
    if (!toolReviews.value[toolName]) {
      toolReviews.value[toolName] = []
    }
    toolReviews.value[toolName].push({
      id: reviewData.id || `review-${Date.now()}`,
      user: reviewData.user || '当前用户',
      rating: reviewData.rating || newReviewRating.value,
      comment: reviewData.comment || newReviewComment.value,
      timestamp: reviewData.timestamp || new Date().toLocaleString('zh-CN')
    })
    const reviews = toolReviews.value[toolName]
    const tool = tools.value.find(t => t.name === toolName)
    if (tool) {
      const totalRating = reviews.reduce((sum, r) => sum + r.rating, 0)
      tool.rating = Math.round((totalRating / reviews.length) * 10) / 10
      tool.ratingCount = reviews.length
    }
    newReviewRating.value = 0
    newReviewComment.value = ''
    showToast('评论提交成功', 'success')
  } catch {
    showToast('评论提交失败，请稍后重试', 'error')
  }
}

const getToolReviews = (toolName: string): ToolReview[] => {
  return toolReviews.value[toolName] || []
}

const loadToolReviews = async (toolName: string) => {
  try {
    const resp = await apiClient.get(api.mcpTools + `/${encodeURIComponent(toolName)}/reviews`)
    const data = resp.data || resp
    if (Array.isArray(data)) {
      toolReviews.value[toolName] = data
    } else if (data && Array.isArray(data.data)) {
      toolReviews.value[toolName] = data.data
    }
  } catch {
    // Reviews not available, keep local
  }
}

const renderStars = (rating: number): string => {
  const full = Math.floor(rating)
  const half = rating % 1 >= 0.5 ? 1 : 0
  const empty = 5 - full - half
  return '★'.repeat(full) + (half ? '☆' : '') + '☆'.repeat(empty)
}

const exportData = (format: 'json' | 'csv') => {
  const payload = {
    exportTime: new Date().toISOString(),
    totalTools: tools.value.length,
    tools: tools.value.map(t => ({
      name: t.name,
      description: t.description,
      category: t.category,
      tags: t.tags,
      version: t.version,
      author: t.author,
      rating: t.rating,
      ratingCount: t.ratingCount,
      downloads: t.downloads,
      lastUpdated: t.lastUpdated,
      isCustom: t.is_custom || false,
      paramCount: Object.keys(t.args_schema?.properties || {}).length
    }))
  }

  if (format === 'json') {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `mcp-tools_${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 100)
  } else {
    const escCsv = (v: string | number | boolean): string => { const s = String(v).replace(/[\r\n]+/g, ' '); return /[",=+\-@]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s }
    const headers = '工具名称,描述,分类,版本,评分,下载量,是否自定义,参数数量\n'
    const rows = tools.value.map(t =>
      [t.name, t.description, getCategoryLabel(t.category), t.version, t.rating, t.downloads, t.is_custom ? '是' : '否', Object.keys(t.args_schema?.properties || {}).length].map(escCsv).join(',')
    ).join('\n')
    const blob = new Blob(['\uFEFF' + headers + rows], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `mcp-tools_${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 100)
  }

  showExportMenu.value = false
  showToast(`数据已导出为 ${format.toUpperCase()} 格式`, 'success')
}

const manualRefresh = async () => {
  loadingState.value = 'refreshing'
  try {
    await fetchTools(true)
    showToast('工具列表已刷新', 'success')
  } catch (_err: unknown) {
    showToast('刷新失败', 'error')
  }
}

const clearFilters = () => {
  searchQuery.value = ''
  activeCategory.value = 'all'
  activeTag.value = ''
  sortBy.value = 'name'
}

const handleVisibilityChange = () => {
  if (!document.hidden) {
    if (visibilityDebounceTimer) clearTimeout(visibilityDebounceTimer)
    visibilityDebounceTimer = window.setTimeout(() => {
      if (!isFetching) {
        fetchTools(false)
      }
      visibilityDebounceTimer = null
    }, 300)
  }
}

const handleKeydown = (e: KeyboardEvent) => {
  const target = e.target as HTMLElement
  const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable
  if ((e.ctrlKey || e.metaKey) && e.key === 'r' && !isInput) {
    e.preventDefault()
    manualRefresh()
  }
  if (e.key === 'Escape') {
    if (showDeleteConfirmModal.value) closeDeleteConfirmModal()
    else if (showAddToolModal.value) closeAddToolModal()
    else if (showTryItModal.value) closeTryItModal()
    else if (showDetailModal.value) closeDetailModal()
  }
}

const handleClickOutside = (e: MouseEvent) => {
  if (showExportMenu.value) {
    const target = e.target as HTMLElement
    if (!target.closest('.export-wrapper')) {
      showExportMenu.value = false
    }
  }
}

onMounted(() => {
  info('MCPTools mounted, initializing...')
  fetchTools(true)
  fetchExecutionHistory()

  handleDataUpdate = () => {
    fetchTools(false)
  }

  window.addEventListener('dashboardDataUpdated', handleDataUpdate)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('click', handleClickOutside)

  info('MCPTools 初始化完成')
})

onUnmounted(() => {
  if (searchDebounceTimer !== null) clearTimeout(searchDebounceTimer)
  if (addToolSuccessTimer !== null) clearTimeout(addToolSuccessTimer)
  if (deleteToolSuccessTimer !== null) clearTimeout(deleteToolSuccessTimer)
  if (visibilityDebounceTimer !== null) clearTimeout(visibilityDebounceTimer)
  if (fetchAbortController) fetchAbortController.abort()
  metrics.value.forEach(m => {
    if (m.animFrameId) cancelAnimationFrame(m.animFrameId)
  })
  if (handleDataUpdate) {
    window.removeEventListener('dashboardDataUpdated', handleDataUpdate)
  }
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <div class="mcp-tools" :class="{ loading: loadingState === 'initial' }">
    <div class="mcp-bg">
      <div class="bg-grid"></div>
      <div class="bg-glow glow-1"></div>
      <div class="bg-glow glow-2"></div>
    </div>

    <div class="mcp-header">
      <div class="header-left">
        <h1 class="page-title">MCP 工具市场</h1>
        <p class="page-subtitle">网络运维工具管理与配置中心</p>
      </div>
      <div class="header-actions">
        <span class="data-freshness" :class="{ degraded: dataFreshness === '降级' }">
          <span class="freshness-dot"></span>
          {{ dataFreshness }}
        </span>
        <span class="last-refresh" v-if="lastRefreshTime">{{ lastRefreshTime }}</span>
        <div class="export-wrapper">
          <button type="button" class="action-btn" @click.stop="showExportMenu = !showExportMenu" title="导出数据" aria-label="导出数据">
            📥 导出
          </button>
          <div v-if="showExportMenu" class="export-dropdown">
            <button type="button" @click="exportData('json')" aria-label="导出JSON">导出 JSON</button>
            <button type="button" @click="exportData('csv')" aria-label="导出CSV">导出 CSV</button>
          </div>
        </div>
        <button
          type="button"
          class="action-btn refresh-btn"
          :class="{ refreshing: loadingState === 'refreshing' }"
          @click="manualRefresh"
          :disabled="loadingState === 'refreshing'"
          title="刷新数据 (Alt+R)"
          aria-label="刷新数据"
        >
          <span class="refresh-icon" :class="{ spinning: loadingState === 'refreshing' }">🔄</span>
          {{ loadingState === 'refreshing' ? '刷新中...' : '刷新' }}
        </button>
        <button type="button" v-if="canWrite" class="add-tool-btn" @click="openAddToolModal" aria-label="添加工具">
          <span class="btn-icon">+</span>
          添加工具
        </button>
      </div>
    </div>

    <div v-if="loadingState === 'initial'" class="metrics-grid">
      <div v-for="i in 4" :key="i" class="metric-card skeleton">
        <div class="skeleton-line wide"></div>
        <div class="skeleton-line narrow"></div>
      </div>
    </div>

    <div v-else class="metrics-grid">
      <div
        v-for="(metric, idx) in metrics"
        :key="metric.label"
        class="metric-card"
        :style="{ '--accent': metric.color, '--delay': `${idx * 0.08}s` }"
      >
        <div class="metric-icon" :style="{ background: `${metric.color}18`, color: metric.color, boxShadow: `0 0 20px ${metric.color}15` }">
          {{ metric.icon }}
        </div>
        <div class="metric-content">
          <div class="metric-value" :style="{ textShadow: `0 0 24px ${metric.color}40` }">
            {{ metric.displayValue }}
            <span class="metric-unit">{{ metric.unit }}</span>
          </div>
          <div class="metric-label">{{ metric.label }}</div>
        </div>
        <div class="metric-bottom-bar">
          <div class="metric-bottom-fill" :style="{ background: `linear-gradient(90deg, ${metric.color}, ${metric.color}66)`, width: `${Math.min(100, metric.value)}%` }"></div>
        </div>
      </div>
    </div>

    <div class="filter-bar">
      <div class="filter-left">
        <div class="search-wrapper">
          <span class="search-icon">🔍</span>
          <input
            v-model="searchQuery"
            type="text"
            class="search-input"
            placeholder="搜索工具名称、描述、标签..."
            aria-label="搜索MCP工具"
            @input="debouncedFetchTools"
          />
          <button type="button" v-if="searchQuery" class="search-clear" @click="searchQuery = ''; debouncedFetchTools()" aria-label="清除搜索">✕</button>
        </div>
        <div class="category-tabs">
          <button
            type="button"
            v-for="cat in TOOL_CATEGORIES"
            :key="cat.key"
            :class="['category-btn', { active: activeCategory === cat.key }]"
            @click="activeCategory = cat.key"
            :aria-label="cat.label"
          >
            <span class="cat-icon">{{ cat.icon }}</span>
            {{ cat.label }}
          </button>
        </div>
      </div>
      <div class="filter-right">
        <div v-if="allTags.length > 0" class="tag-filter">
          <select v-model="activeTag" class="filter-select" aria-label="按标签筛选">
            <option value="">全部标签</option>
            <option v-for="tag in allTags" :key="tag" :value="tag">{{ tag }}</option>
          </select>
        </div>
        <select v-model="sortBy" class="filter-select" aria-label="排序方式">
          <option v-for="opt in SORT_OPTIONS" :key="opt.key" :value="opt.key">{{ opt.label }}</option>
        </select>
        <button
          type="button"
          v-if="searchQuery || activeCategory !== 'all' || activeTag || sortBy !== 'name'"
          class="clear-filter-btn"
          @click="clearFilters"
          aria-label="清除筛选"
        >
          清除筛选
        </button>
      </div>
    </div>

    <div v-if="loadingState !== 'idle' && !tools.length" class="loading-container">
      <div class="loading-spinner"></div>
      <p class="loading-text">加载工具中...</p>
    </div>

    <div v-else-if="filteredTools.length === 0" class="empty-state">
      <div class="empty-icon">🔍</div>
      <div class="empty-text">
        {{ searchQuery || activeCategory !== 'all' || activeTag ? '没有找到匹配的工具，请调整筛选条件' : '暂无工具数据' }}
      </div>
      <button
        type="button"
        v-if="searchQuery || activeCategory !== 'all' || activeTag"
        class="clear-filter-btn"
        @click="clearFilters"
        aria-label="清除筛选"
      >
        清除筛选
      </button>
    </div>

    <div v-else class="tools-grid">
      <div
        v-for="(tool, idx) in filteredTools"
        :key="tool.name"
        class="tool-card"
        :style="{ '--delay': `${idx * 0.04}s` }"
        @click="showToolDetail(tool)"
      >
        <div class="tool-header">
          <div class="tool-icon-badge" :class="tool.category">
            {{ getCategoryIcon(tool.category) }}
          </div>
          <div class="tool-title-wrapper">
            <h3 class="tool-name">{{ tool.name }}</h3>
            <span v-if="tool.is_custom" class="custom-badge">自定义</span>
          </div>
        </div>
        <p class="tool-description">{{ tool.description }}</p>
        <div class="tool-tags">
          <span v-for="tag in tool.tags" :key="tag" class="tool-tag" @click.stop="activeTag = tag">{{ tag }}</span>
        </div>
        <div class="tool-meta-row">
          <div class="tool-rating">
            <span class="stars">{{ renderStars(tool.rating) }}</span>
            <span class="rating-num">{{ tool.rating.toFixed(1) }}</span>
            <span class="rating-count">({{ tool.ratingCount }})</span>
          </div>
          <span class="tool-downloads">📥 {{ tool.downloads }}</span>
        </div>
        <div class="tool-footer">
          <div class="tool-info">
            <span class="tool-params">{{ Object.keys(tool.args_schema?.properties || {}).length }} 个参数</span>
            <span class="tool-version">v{{ tool.version }}</span>
          </div>
          <div class="tool-actions">
            <button type="button" v-if="canWrite" class="try-it-btn" @click.stop="openTryItModal(tool, $event)" aria-label="试用工具">
              🧪 Try it
            </button>
            <button
              type="button"
              v-if="canWrite && tool.is_custom"
              class="delete-tool-btn"
              @click.stop="openDeleteConfirmModal(tool, $event)"
              aria-label="删除工具"
            >
              🗑️
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="executionHistory.length > 0" class="execution-history-section">
      <div class="section-header">
        <h3>执行历史</h3>
        <button type="button" class="btn-text" @click="showExecutionHistory = !showExecutionHistory" aria-label="收起/展开">
          {{ showExecutionHistory ? '收起' : '展开' }}
        </button>
      </div>
      <div v-if="showExecutionHistory" class="history-list">
        <div v-for="record in executionHistory.slice(0, 20)" :key="record.execution_id || record.timestamp" class="history-item">
          <div class="history-header">
            <span class="tool-name">{{ record.tool_name }}</span>
            <span :class="['status-badge', record.status === 'success' ? 'success' : 'error']">
              {{ record.status === 'success' ? '成功' : '失败' }}
            </span>
            <span class="history-time">{{ record.timestamp || record.executed_at }}</span>
          </div>
          <div class="history-params">{{ JSON.stringify(record.parameters) }}</div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showDetailModal && selectedTool" class="modal-overlay" @click.self="closeDetailModal" role="dialog" aria-modal="true" aria-labelledby="detail-modal-title">
        <div class="modal-content detail-modal">
          <div class="modal-header">
            <h2 id="detail-modal-title" class="modal-title">
              <span class="tool-icon-large">{{ getCategoryIcon(selectedTool.category) }}</span>
              {{ selectedTool.name }}
              <span v-if="selectedTool.is_custom" class="custom-badge-large">自定义</span>
            </h2>
            <button type="button" class="modal-close" @click="closeDetailModal" aria-label="关闭">✕</button>
          </div>

          <div class="modal-body">
            <div class="detail-section">
              <h4 class="section-title">描述</h4>
              <p class="section-content">{{ selectedTool.description }}</p>
            </div>

            <div class="detail-meta-grid">
              <div class="detail-meta-item">
                <span class="meta-label">分类</span>
                <span class="meta-value">{{ getCategoryIcon(selectedTool.category) }} {{ getCategoryLabel(selectedTool.category) }}</span>
              </div>
              <div class="detail-meta-item">
                <span class="meta-label">版本</span>
                <span class="meta-value">v{{ selectedTool.version }}</span>
              </div>
              <div class="detail-meta-item">
                <span class="meta-label">作者</span>
                <span class="meta-value">{{ selectedTool.author }}</span>
              </div>
              <div class="detail-meta-item">
                <span class="meta-label">更新时间</span>
                <span class="meta-value">{{ selectedTool.lastUpdated }}</span>
              </div>
            </div>

            <div class="detail-section">
              <h4 class="section-title">评分</h4>
              <div class="rating-section">
                <div class="rating-display">
                  <span class="stars large">{{ renderStars(selectedTool.rating) }}</span>
                  <span class="rating-num large">{{ selectedTool.rating.toFixed(1) }}</span>
                  <span class="rating-count">({{ selectedTool.ratingCount }} 评分)</span>
                </div>
                <div class="rating-input">
                  <span class="rating-label">提交评分：</span>
                  <div class="star-input">
                    <span
                      v-for="star in 5"
                      :key="star"
                      :class="['star-btn', { active: star <= newReviewRating }]"
                      @click="newReviewRating = star"
                    >★</span>
                  </div>
                  <input
                    v-model="newReviewComment"
                    type="text"
                    class="review-input"
                    placeholder="写下你的评论..."
                    aria-label="评论内容"
                  />
                  <button type="button" class="review-submit-btn" @click="submitReview" :disabled="newReviewRating === 0" aria-label="提交评价">提交</button>
                </div>
              </div>
            </div>

            <div v-if="getToolReviews(selectedTool.name).length > 0" class="detail-section">
              <h4 class="section-title">评论 ({{ getToolReviews(selectedTool.name).length }})</h4>
              <div class="reviews-list">
                <div v-for="review in getToolReviews(selectedTool.name)" :key="review.id" class="review-item">
                  <div class="review-header">
                    <span class="review-user">{{ review.user }}</span>
                    <span class="stars small">{{ renderStars(review.rating) }}</span>
                    <span class="review-time">{{ review.timestamp }}</span>
                  </div>
                  <p v-if="review.comment" class="review-comment">{{ review.comment }}</p>
                </div>
              </div>
            </div>

            <div v-if="selectedTool.tags.length > 0" class="detail-section">
              <h4 class="section-title">标签</h4>
              <div class="detail-tags">
                <span v-for="tag in selectedTool.tags" :key="tag" class="detail-tag">{{ tag }}</span>
              </div>
            </div>

            <div class="detail-section">
              <h4 class="section-title">参数定义</h4>
              <div class="parameters-list">
                <div
                  v-for="(schema, paramName) in (selectedTool.args_schema?.properties || {})"
                  :key="paramName"
                  class="parameter-item"
                >
                  <div class="parameter-header">
                    <span class="param-name">{{ paramName }}</span>
                    <span
                      v-if="(selectedTool.args_schema?.required || []).includes(paramName)"
                      class="param-badge required"
                    >必填</span>
                    <span
                      v-else
                      class="param-badge optional"
                    >可选</span>
                  </div>
                  <p class="param-description">{{ schema?.description || '暂无描述' }}</p>
                  <span class="param-type">类型: {{ schema?.type || 'string' }}</span>
                  <span
                    v-if="schema?.default !== undefined"
                    class="param-default"
                  >默认值: {{ schema.default }}</span>
                </div>
              </div>
            </div>

            <div class="detail-section">
              <h4 class="section-title">JSON Schema</h4>
              <pre class="schema-json">{{ JSON.stringify(selectedTool.args_schema, null, 2) }}</pre>
            </div>
          </div>

          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="closeDetailModal" aria-label="关闭">关闭</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showTryItModal && selectedTool" class="modal-overlay" @click.self="closeTryItModal" role="dialog" aria-modal="true" aria-labelledby="tryit-modal-title">
        <div class="modal-content try-it-modal">
          <div class="modal-header">
            <h2 id="tryit-modal-title" class="modal-title">
              <span class="tool-icon-large">🧪</span>
              Try it - {{ selectedTool.name }}
            </h2>
            <button type="button" class="modal-close" @click="closeTryItModal" aria-label="关闭">✕</button>
          </div>

          <div class="modal-body">
            <div class="try-it-section">
              <h4 class="section-title">参数配置</h4>
              <div class="parameters-form">
                <div
                  v-for="(schema, paramName) in (selectedTool.args_schema?.properties || {})"
                  :key="paramName"
                  class="form-item"
                >
                  <label class="form-label">
                    {{ paramName }}
                    <span
                      v-if="(selectedTool.args_schema?.required || []).includes(paramName)"
                      class="required-star"
                    >*</span>
                  </label>
                  <input
                    v-model="tryItParams[paramName]"
                    type="text"
                    :placeholder="`请输入 ${schema?.description || '参数值'}`"
                    class="form-input"
                    :aria-label="`${paramName} 参数输入`"
                  />
                  <span class="form-hint">{{ schema?.description }}</span>
                </div>
              </div>
            </div>

            <div class="try-it-section">
              <div class="try-it-header">
                <h4 class="section-title">执行结果</h4>
                <span v-if="tryItResult" class="preview-badge">预览</span>
              </div>
              <div v-if="tryItLoading" class="loading-container small">
                <div class="loading-spinner small"></div>
                <span class="loading-text">正在生成预览...</span>
              </div>
              <pre v-else-if="tryItResult" class="result-json">{{ tryItResult }}</pre>
              <div v-else class="empty-state small">
                <span class="empty-icon">📝</span>
                <p>点击下方按钮查看执行预览</p>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="closeTryItModal" aria-label="关闭">关闭</button>
            <button type="button" v-if="canWrite" class="btn btn-primary" @click="executeTryIt" :disabled="tryItLoading" aria-label="查看预览">
              {{ tryItLoading ? '执行中...' : '🔍 查看预览' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showAddToolModal" class="modal-overlay" @click.self="closeAddToolModal" role="dialog" aria-modal="true" aria-labelledby="add-tool-modal-title">
        <div class="modal-content add-tool-modal">
          <div class="modal-header">
            <h2 id="add-tool-modal-title" class="modal-title">
              <span class="tool-icon-large">➕</span>
              添加自定义工具
            </h2>
            <button type="button" class="modal-close" @click="closeAddToolModal" aria-label="关闭">✕</button>
          </div>

          <div class="modal-body">
            <div v-if="addToolMessage" :class="['message-box', addToolSuccess ? 'success' : 'error']">
              {{ addToolMessage }}
            </div>

            <div class="form-section">
              <h4 class="section-title">基本信息</h4>
              <div class="form-item">
                <label class="form-label">工具名称 <span class="required-star">*</span></label>
                <input
                  v-model="newToolName"
                  type="text"
                  placeholder="例如: weather_query_v1"
                  :class="['form-input', { error: !!nameError }]"
                  ref="nameInput"
                  :maxlength="VALIDATION.TOOL_NAME.MAX_LENGTH"
                  @input="filterToolName"
                  aria-label="工具名称"
                />
                <div class="field-hints">
                  <span class="hint-text">字母开头，{{ VALIDATION.TOOL_NAME.MIN_LENGTH }}-{{ VALIDATION.TOOL_NAME.MAX_LENGTH }}字符，仅字母/数字/下划线</span>
                  <span v-if="nameError" class="field-error">{{ nameError }}</span>
                  <span v-else-if="newToolName && !nameError" class="field-success">✓ 格式正确</span>
                </div>
              </div>
              <div class="form-item">
                <label class="form-label">工具描述 <span class="required-star">*</span></label>
                <input
                  v-model="newToolDescription"
                  type="text"
                  placeholder="请清晰描述工具的功能、用途和使用场景（例如：查询指定城市的实时天气数据）"
                  :class="['form-input', { error: !!descError }]"
                  ref="descInput"
                  :maxlength="VALIDATION.TOOL_DESCRIPTION.MAX_LENGTH"
                  aria-label="工具描述"
                />
                <div class="field-hints">
                  <span class="hint-text">{{ newToolDescription.length }}/{{ VALIDATION.TOOL_DESCRIPTION.MAX_LENGTH }} 字符</span>
                  <span v-if="descError" class="field-error">{{ descError }}</span>
                </div>
              </div>
            </div>

            <div class="form-section">
              <div class="section-header">
                <h4 class="section-title">参数配置</h4>
                <button
                  type="button"
                  v-if="newToolParams.length < VALIDATION.MAX_PARAMS"
                  class="add-param-btn"
                  @click="addNewParam"
                  aria-label="添加参数"
                >
                  + 添加参数 ({{ newToolParams.length }}/{{ VALIDATION.MAX_PARAMS }})
                </button>
                <span v-else class="param-limit">已达最大限制</span>
              </div>
              <div class="parameters-list">
                <div
                  v-for="(param, index) in newToolParams"
                  :key="index"
                  class="parameter-item editable"
                >
                  <div class="param-row">
                    <div class="param-input-group">
                      <input
                        v-model="param.name"
                        type="text"
                        placeholder="参数名（如: city_name）"
                        :class="['form-input small', { error: paramErrors[index]?.name }]"
                        :maxlength="VALIDATION.PARAM_NAME.MAX_LENGTH"
                        @input="filterParamName(index)"
                        :aria-label="`参数名 ${index + 1}`"
                      />
                      <span v-if="paramErrors[index]?.name" class="field-error small">{{ paramErrors[index].name }}</span>
                    </div>
                    <div class="param-input-group">
                      <input
                        v-model="param.description"
                        type="text"
                        placeholder="参数描述（如: 需要查询天气的城市名称）"
                        :class="['form-input small', { error: paramErrors[index]?.description }]"
                        :maxlength="VALIDATION.PARAM_DESCRIPTION.MAX_LENGTH"
                        :aria-label="`参数描述 ${index + 1}`"
                      />
                      <span v-if="paramErrors[index]?.description" class="field-error small">{{ paramErrors[index].description }}</span>
                    </div>
                    <div class="param-toggle">
                      <label class="toggle-label">
                        <input type="checkbox" v-model="param.required" />
                        <span>必填</span>
                      </label>
                    </div>
                    <button
                      type="button"
                      v-if="newToolParams.length > 1"
                      class="remove-param-btn"
                      @click="removeParam(index)"
                      aria-label="移除参数"
                    >✕</button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="closeAddToolModal" aria-label="取消">取消</button>
            <button type="button" v-if="canWrite" class="btn btn-primary" @click="submitNewTool" :disabled="addToolLoading" aria-label="验证并添加">
              {{ addToolLoading ? '添加中...' : '验证并添加' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showDeleteConfirmModal && toolToDelete" class="modal-overlay" @click.self="closeDeleteConfirmModal" role="dialog" aria-modal="true" aria-labelledby="delete-modal-title">
        <div class="modal-content delete-confirm-modal">
          <div class="modal-header">
            <h2 id="delete-modal-title" class="modal-title">
              <span class="tool-icon-large">⚠️</span>
              删除工具
            </h2>
            <button type="button" class="modal-close" @click="closeDeleteConfirmModal" aria-label="关闭">✕</button>
          </div>

          <div class="modal-body">
            <div v-if="deleteToolMessage" :class="['message-box', deleteToolSuccess ? 'success' : 'error']">
              {{ deleteToolMessage }}
            </div>

            <div v-if="!deleteToolSuccess" class="warning-message">
              <p>确定要删除工具 <strong>{{ toolToDelete.name }}</strong> 吗？</p>
              <p class="warning-text">此操作将永久删除该工具，无法恢复。</p>
            </div>
          </div>

          <div v-if="!deleteToolSuccess" class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="closeDeleteConfirmModal" aria-label="取消">取消</button>
            <button type="button" v-if="canWrite" class="btn btn-danger" @click="deleteTool" :disabled="deleteToolLoading" aria-label="确认删除">
              {{ deleteToolLoading ? '删除中...' : '确认删除' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.mcp-tools {
  position: relative;
  animation: page-enter 0.5s ease-out;
  min-height: 100vh;
  padding: 24px;
}

.mcp-bg {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: var(--z-base);
  overflow: hidden;
}

.bg-grid {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background-image:
    linear-gradient(rgba(22, 93, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(22, 93, 255, 0.03) 1px, transparent 1px);
  background-size: 60px 60px;
  mask-image: radial-gradient(ellipse 80% 60% at 50% 30%, black 20%, transparent 70%);
}

.bg-glow {
  position: absolute;
  border-radius: var(--radius-full);
  filter: blur(80px);
  opacity: 0.4;
  will-change: transform, opacity;
}

.glow-1 {
  width: 400px;
  height: 400px;
  background: rgba(22, 93, 255, 0.08);
  top: -100px;
  right: 10%;
  animation: glow-float 12s ease-in-out infinite;
}

.glow-2 {
  width: 300px;
  height: 300px;
  background: rgba(139, 92, 246, 0.06);
  bottom: 10%;
  left: 5%;
  animation: glow-float 15s ease-in-out infinite reverse;
}

.mcp-tools > *:not(.mcp-bg) {
  position: relative;
  z-index: var(--z-content);
}

.mcp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--color-bg-hover);
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  margin: 0;
  background: linear-gradient(135deg, var(--color-text-secondary) 0%, var(--color-purple) 50%, var(--color-text-secondary) 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: title-shimmer 4s ease-in-out infinite;
  will-change: background-position;
}

.page-subtitle {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin: 0;
  font-weight: 400;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.data-freshness {
  font-size: var(--font-size-xs);
  padding: 4px 10px;
  border-radius: var(--radius-lg);
  background: var(--color-success-bg);
  color: var(--color-success);
  transition: all 0.3s ease;
  border: 1px solid var(--color-success-border);
  display: flex;
  align-items: center;
  gap: 6px;
}

.freshness-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--radius-full);
  background: currentColor;
  animation: freshness-pulse 2s ease-in-out infinite;
  will-change: opacity, box-shadow;
}

.data-freshness.degraded {
  background: var(--color-warning-bg);
  color: var(--color-warning);
  border-color: var(--color-warning-border);
}

.last-refresh {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.action-btn {
  padding: 6px 14px;
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-xs);
  transition: all 0.25s ease;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
  backdrop-filter: blur(8px);
  min-height: 44px;
  will-change: transform;
}

.action-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: rgba(59, 130, 246, 0.5);
  box-shadow: 0 2px 16px rgba(59, 130, 246, 0.25), 0 0 8px rgba(59, 130, 246, 0.12);
  color: var(--color-primary-lighter);
  transform: scale(1.02);
}

.action-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.action-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.refresh-btn:hover:not(:disabled) .refresh-icon {
  animation: spin 0.6s ease;
  filter: brightness(1.2);
}

.refresh-icon {
  display: inline-block;
  transition: transform 0.3s ease;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
  will-change: transform;
}

.add-tool-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--gradient-success);
  color: var(--color-text-primary);
  border: none;
  padding: 8px 18px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: var(--button-transition);
  min-height: 44px;
  will-change: transform;
}

.add-tool-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-glow-success);
}

.btn-icon {
  font-size: var(--font-size-lg);
  font-weight: bold;
}

.export-wrapper {
  position: relative;
}

.export-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--radius-lg);
  overflow: hidden;
  z-index: var(--z-fixed);
  min-width: 140px;
  backdrop-filter: blur(16px);
  box-shadow: var(--shadow-dropdown);
  animation: dropdown-enter 0.15s ease-out;
}

.export-dropdown button {
  display: block;
  width: 100%;
  padding: 10px 16px;
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  text-align: left;
  cursor: pointer;
  transition: all 0.15s ease;
}

.export-dropdown button:hover {
  background: var(--color-primary-glow);
  color: var(--color-primary-light);
  padding-left: 20px;
}

.skeleton {
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-line {
  height: 14px;
  background: var(--gradient-shimmer);
  background-size: 200% 100%;
  border-radius: var(--radius-default);
  margin-bottom: 10px;
  animation: skeleton-slide 1.5s ease-in-out infinite;
  will-change: background-position;
}

.skeleton-line.wide { width: 70%; }
.skeleton-line.narrow { width: 40%; }

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.metric-card {
  background: var(--gradient-glass);
  border-radius: var(--radius-xl);
  padding: 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  border: var(--card-border);
  transition: all 0.35s var(--ease-out);
  position: relative;
  overflow: hidden;
  backdrop-filter: blur(12px);
  animation: card-enter 0.4s var(--ease-out) backwards;
  animation-delay: var(--delay, 0s);
  box-shadow: var(--shadow-card);
  will-change: transform, opacity;
}

.metric-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--accent), transparent);
  opacity: 0;
  transition: opacity 0.35s ease;
}

.metric-card:hover {
  transform: translateY(-2px);
  border-color: rgba(22, 93, 255, 0.3);
  box-shadow: 0 4px 20px rgba(22, 93, 255, 0.1), 0 0 12px rgba(22, 93, 255, 0.06);
}

.metric-card:hover::before {
  opacity: 1;
}

.metric-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xl);
  flex-shrink: 0;
  transition: transform 0.3s ease;
  will-change: transform;
}

.metric-card:hover .metric-icon {
  transform: scale(1.08);
  animation: icon-pulse 1.5s ease-in-out infinite;
}

.metric-content {
  flex: 1;
  min-width: 0;
}

.metric-value {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.5px;
}

.metric-unit {
  font-size: var(--font-size-sm);
  font-weight: 400;
  color: var(--color-text-tertiary);
  margin-left: 2px;
  letter-spacing: 0;
}

.metric-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-top: 2px;
}

.metric-bottom-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--color-bg-hover);
}

.metric-bottom-fill {
  height: 100%;
  border-radius: 0 var(--radius-xs) 0 0;
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding: 14px 18px;
  background: var(--gradient-glass);
  border-radius: var(--radius-xl);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  flex-wrap: wrap;
}

.filter-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.search-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 10px;
  font-size: var(--font-size-base);
  pointer-events: none;
}

.search-input {
  padding: 8px 32px 8px 32px;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  width: 240px;
  transition: all 0.25s var(--ease-out);
  outline: none;
}

.search-input::placeholder {
  color: var(--color-text-disabled);
}

.search-input:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
  background: rgba(15, 23, 42, 0.8);
}

.search-clear {
  position: absolute;
  right: 8px;
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  cursor: pointer;
  font-size: var(--font-size-xs);
  padding: 2px;
  transition: color 0.2s ease;
}

.search-clear:hover {
  color: var(--color-text-primary);
}

.category-tabs {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.category-btn {
  padding: 4px 10px;
  background: rgba(22, 93, 255, 0.06);
  border: 1px solid var(--color-primary-glow);
  border-radius: var(--radius-md);
  color: rgba(255, 255, 255, 0.7);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.25s ease;
  white-space: nowrap;
  min-height: 44px;
  backdrop-filter: blur(8px);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  will-change: transform;
}

.category-btn:hover {
  background: rgba(22, 93, 255, 0.12);
  color: var(--color-primary-light);
  border-color: rgba(22, 93, 255, 0.3);
  box-shadow: 0 0 10px rgba(22, 93, 255, 0.1);
  transform: scale(1.02);
}

.category-btn:hover .cat-icon {
  filter: brightness(1.3);
  transform: scale(1.15);
}

.category-btn:active {
  transform: scale(0.97);
}

.category-btn.active {
  background: rgba(22, 93, 255, 0.18);
  color: var(--color-primary-light);
  border: 1px solid rgba(22, 93, 255, 0.4);
  border-radius: var(--radius-md);
  box-shadow: 0 0 12px rgba(22, 93, 255, 0.15);
}

.category-btn.active .cat-icon {
  filter: brightness(1.5) drop-shadow(0 0 8px rgba(59, 130, 246, 0.7));
  animation: icon-pulse 1.5s ease-in-out infinite;
}

.cat-icon {
  font-size: var(--font-size-xs);
}

.filter-select {
  padding: 6px 28px 6px 10px;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--radius-default);
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.25s var(--ease-out);
  outline: none;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2394A3B8' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
}

.filter-select:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
}

.filter-select option {
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
}

.clear-filter-btn {
  padding: 6px 12px;
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-default);
  color: var(--color-error-light);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.clear-filter-btn:hover {
  background: var(--color-error-hover);
  border-color: rgba(255, 77, 79, 0.4);
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  gap: 16px;
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 3px solid rgba(100, 116, 139, 0.2);
  border-top-color: var(--color-primary);
  border-radius: var(--radius-full);
  animation: spin 1s linear infinite;
  will-change: transform;
}

.loading-text {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
}

.loading-container.small {
  padding: 40px 20px;
}

.loading-spinner.small {
  width: 32px;
  height: 32px;
  border-width: 2px;
}

.empty-state {
  text-align: center;
  padding: 48px 24px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.4) 0%, rgba(20, 30, 48, 0.3) 100%);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-bg-hover);
}

.empty-state.small {
  padding: 32px 20px;
  background: rgba(15, 23, 42, 0.4);
  border-radius: var(--radius-lg);
  border: 2px dashed var(--color-border-primary);
}

.empty-icon {
  font-size: var(--font-size-4xl);
  margin-bottom: 12px;
  opacity: 0.6;
}

.empty-text {
  margin-bottom: 12px;
}

.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
}

.tool-card {
  background: var(--gradient-glass);
  border: var(--card-border);
  border-radius: var(--radius-xl);
  padding: 20px;
  cursor: pointer;
  transition: all 0.35s var(--ease-out);
  backdrop-filter: blur(12px);
  animation: card-enter 0.4s var(--ease-out) backwards;
  animation-delay: var(--delay, 0s);
  position: relative;
  overflow: hidden;
  box-shadow: var(--shadow-card);
  will-change: transform, opacity;
}

.tool-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--accent, var(--color-primary)), transparent);
  opacity: 0;
  transition: opacity 0.35s ease;
}

.tool-card:hover {
  background: var(--color-bg-glass-strong);
  border-color: var(--color-primary-border);
  transform: translateY(-2px);
  box-shadow: var(--shadow-card-hover);
}

.tool-card:hover::before {
  opacity: 1;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.tool-icon-badge {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xl);
  flex-shrink: 0;
  transition: transform 0.3s ease;
  will-change: transform;
}

.tool-icon-badge.network_config {
  background: var(--color-primary-glow);
}

.tool-icon-badge.network_diagnosis {
  background: rgba(245, 158, 11, 0.15);
}

.tool-icon-badge.security {
  background: rgba(239, 68, 68, 0.15);
}

.tool-icon-badge.device_management {
  background: var(--color-success-glow);
}

.tool-icon-badge.custom {
  background: rgba(139, 92, 246, 0.15);
}

.tool-card:hover .tool-icon-badge {
  transform: scale(1.08);
}

.tool-title-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.tool-name {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-badge {
  background: rgba(139, 92, 246, 0.2);
  color: var(--color-purple);
  font-size: var(--font-size-xs);
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.custom-badge-large {
  background: rgba(139, 92, 246, 0.2);
  color: var(--color-purple);
  font-size: var(--font-size-xs);
  font-weight: 600;
  padding: 4px 10px;
  border-radius: var(--radius-default);
}

.tool-description {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  line-height: 1.6;
  margin-bottom: 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tool-tags {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.tool-tag {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  cursor: pointer;
  transition: all 0.2s ease;
}

.tool-tag:hover {
  background: var(--color-primary-hover);
}

.tool-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.tool-rating {
  display: flex;
  align-items: center;
  gap: 4px;
}

.stars {
  color: var(--color-warning);
  font-size: var(--font-size-sm);
  letter-spacing: 1px;
}

.stars.large {
  font-size: var(--font-size-lg);
}

.stars.small {
  font-size: var(--font-size-xs);
}

.rating-num {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-warning);
}

.rating-num.large {
  font-size: var(--font-size-xl);
  font-weight: 700;
}

.rating-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.tool-downloads {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.tool-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid var(--color-bg-active);
}

.tool-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tool-params {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.tool-version {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  background: var(--color-bg-hover);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.tool-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.try-it-btn {
  background: linear-gradient(135deg, var(--color-primary-hover), var(--color-success-glow));
  color: var(--color-primary-light);
  border: 1px solid rgba(22, 93, 255, 0.3);
  padding: 0 14px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s ease;
  height: 44px;
  display: inline-flex;
  align-items: center;
  backdrop-filter: blur(8px);
  will-change: transform;
}

.try-it-btn:hover {
  transform: scale(1.05);
  box-shadow: var(--shadow-glow-primary);
  background: linear-gradient(135deg, rgba(22, 93, 255, 0.3), rgba(82, 196, 26, 0.22));
  border-color: rgba(22, 93, 255, 0.45);
  color: var(--color-primary-lighter);
}

.try-it-btn:active {
  transform: scale(0.97);
}

.delete-tool-btn {
  background: rgba(239, 68, 68, 0.1);
  color: #EF4444;
  border: none;
  padding: 0;
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  cursor: pointer;
  transition: all 0.3s ease;
  width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  will-change: transform;
}

.delete-tool-btn:hover {
  background: rgba(239, 68, 68, 0.2);
  transform: translateY(-1px);
}

.modal-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background: var(--modal-overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-overlay);
  padding: 20px;
  animation: fade-in 0.2s var(--ease-out);
  backdrop-filter: blur(var(--modal-backdrop-blur));
}

.modal-content {
  background: var(--color-bg-elevated);
  border-radius: var(--modal-border-radius);
  border: 1px solid var(--color-border-primary);
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-modal);
}

.detail-modal {
  width: 100%;
  max-width: 650px;
}

.try-it-modal {
  width: 100%;
  max-width: 700px;
}

.add-tool-modal {
  width: 100%;
  max-width: 650px;
}

.delete-confirm-modal {
  width: 100%;
  max-width: 500px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--color-bg-active);
}

.modal-title {
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.tool-icon-large {
  font-size: var(--font-size-3xl);
}

.modal-close {
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-2xl);
  cursor: pointer;
  padding: 4px;
  line-height: 1;
  transition: color 0.2s ease;
}

.modal-close:hover {
  color: var(--color-text-primary);
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.message-box {
  padding: 12px 16px;
  border-radius: var(--radius-md);
  margin-bottom: 20px;
  font-size: var(--font-size-base);
}

.message-box.success {
  background: var(--color-success-glow);
  color: var(--color-success);
  border: 1px solid rgba(82, 196, 26, 0.3);
}

.message-box.error {
  background: rgba(239, 68, 68, 0.15);
  color: #EF4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.warning-message {
  text-align: center;
  padding: 20px 0;
}

.warning-message p {
  color: var(--color-text-secondary);
  font-size: var(--font-size-md);
  margin-bottom: 12px;
}

.warning-text {
  color: #EF4444 !important;
  font-size: var(--font-size-base) !important;
  margin-bottom: 0 !important;
}

.detail-section {
  margin-bottom: 20px;
}

.section-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-primary-light);
  margin-bottom: 12px;
}

.section-content {
  font-size: var(--font-size-base);
  color: var(--color-text-tertiary);
  line-height: 1.6;
  margin: 0;
}

.detail-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 20px;
  padding: 14px;
  background: rgba(15, 23, 42, 0.4);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-bg-hover);
}

.detail-meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.meta-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.meta-value {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-weight: 500;
}

.rating-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rating-display {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rating-input {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rating-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.star-input {
  display: flex;
  gap: 2px;
}

.star-btn {
  font-size: var(--font-size-xl);
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: color 0.2s ease;
}

.star-btn.active {
  color: var(--color-warning);
}

.star-btn:hover {
  color: #FBBF24;
}

.review-input {
  flex: 1;
  min-width: 120px;
  padding: 6px 10px;
  background: var(--color-bg-input);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-default);
  color: var(--color-text-primary);
  font-size: var(--font-size-xs);
  outline: none;
}

.review-input:focus {
  border-color: rgba(22, 93, 255, 0.5);
}

.review-submit-btn {
  padding: 6px 14px;
  background: linear-gradient(135deg, var(--color-primary), #0040C9);
  color: var(--color-text-primary);
  border: none;
  border-radius: var(--radius-default);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.2s ease;
}

.review-submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.reviews-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.review-item {
  padding: 10px 12px;
  background: rgba(15, 23, 42, 0.4);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-bg-hover);
}

.review-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.review-user {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.review-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-left: auto;
}

.review-comment {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin: 0;
  line-height: 1.5;
}

.detail-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.detail-tag {
  font-size: var(--font-size-xs);
  padding: 4px 10px;
  border-radius: var(--radius-default);
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border: 1px solid var(--color-primary-glow);
}

.form-section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.add-param-btn {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border: 1px solid var(--color-primary-hover);
  padding: 6px 12px;
  border-radius: var(--radius-default);
  font-size: var(--font-size-xs);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.add-param-btn:hover {
  background: var(--color-primary-hover);
}

.parameters-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.parameter-item {
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  padding: 16px;
}

.parameter-item.editable {
  padding: 12px 16px;
}

.param-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.param-input-group {
  flex: 1;
}

.form-input.small {
  padding: 8px 12px;
  font-size: var(--font-size-sm);
}

.form-input.error {
  border-color: rgba(239, 68, 68, 0.5);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
}

.remove-param-btn {
  background: rgba(239, 68, 68, 0.1);
  color: #EF4444;
  border: none;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-base);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.remove-param-btn:hover {
  background: rgba(239, 68, 68, 0.2);
}

.parameter-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.param-name {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text-primary);
}

.param-badge {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-weight: 500;
}

.param-badge.required {
  background: rgba(239, 68, 68, 0.2);
  color: #EF4444;
}

.param-badge.optional {
  background: rgba(100, 116, 139, 0.2);
  color: var(--color-text-tertiary);
}

.param-description {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  line-height: 1.5;
  margin: 0 0 8px 0;
}

.param-type,
.param-default {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-right: 12px;
}

.schema-json {
  font-family: 'Courier New', monospace;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  background: rgba(0, 0, 0, 0.3);
  padding: 16px;
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin: 0;
  line-height: 1.5;
}

.modal-footer {
  padding: 20px 24px;
  border-top: 1px solid var(--color-bg-active);
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.btn {
  padding: 10px 24px;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-secondary {
  background: var(--color-bg-input);
  color: var(--color-text-tertiary);
}

.btn-secondary:hover {
  background: rgba(15, 23, 42, 0.8);
  color: var(--color-text-primary);
}

.btn-primary {
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  will-change: transform;
}

.btn-primary:hover:not(:disabled) {
  box-shadow: var(--shadow-glow-primary);
  transform: translateY(-1px);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-danger {
  background: var(--gradient-danger);
  color: var(--color-text-primary);
  will-change: transform;
}

.btn-danger:hover:not(:disabled) {
  box-shadow: var(--shadow-glow-error);
  transform: translateY(-1px);
}

.btn-danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.try-it-section {
  margin-bottom: 20px;
}

.try-it-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.preview-badge {
  background: var(--color-primary-glow);
  color: var(--color-primary);
  padding: 4px 10px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  font-weight: 600;
}

.parameters-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.required-star {
  color: #EF4444;
  margin-left: 2px;
}

.form-input {
  width: 100%;
  padding: var(--input-padding);
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-primary);
  font-size: var(--font-size-base);
  transition: all 0.3s var(--ease-out);
  box-sizing: border-box;
}

.form-input:focus {
  outline: none;
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
}

.form-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.field-hints {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 6px;
}

.hint-text {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.field-error {
  font-size: var(--font-size-xs);
  color: #EF4444;
}

.field-error.small {
  font-size: var(--font-size-xs);
}

.field-success {
  font-size: var(--font-size-xs);
  color: var(--color-success);
}

.param-toggle {
  margin-left: 8px;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  white-space: nowrap;
}

.toggle-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.param-limit {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  padding: 6px 12px;
}

.result-json {
  font-family: 'Courier New', monospace;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  background: rgba(0, 0, 0, 0.3);
  padding: 16px;
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin: 0;
  line-height: 1.6;
  border-left: 3px solid var(--color-success);
}

.execution-history-section {
  margin-top: 24px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-bg-hover);
}
.execution-history-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.execution-history-section .section-header h3 {
  font-size: var(--font-size-md);
  color: rgba(255, 255, 255, 0.85);
  margin: 0;
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.history-item {
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: var(--radius-md);
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.history-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.history-header .tool-name {
  font-weight: 500;
  color: rgba(255, 255, 255, 0.85);
}
.history-header .status-badge {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}
.history-header .status-badge.success {
  background: var(--color-success-glow);
  color: var(--color-success);
}
.history-header .status-badge.error {
  background: var(--color-error-glow);
  color: var(--color-error);
}
.history-header .history-time {
  font-size: var(--font-size-xs);
  color: rgba(255, 255, 255, 0.4);
  margin-left: auto;
}
.history-params {
  font-size: var(--font-size-xs);
  color: rgba(255, 255, 255, 0.5);
  word-break: break-all;
}
.btn-text {
  background: none;
  border: none;
  color: #1890ff;
  cursor: pointer;
  font-size: var(--font-size-base);
}
.btn-text:hover {
  color: #40a9ff;
}

@media (max-width: 1200px) {
  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }
}

@media (max-width: 768px) {
  .mcp-tools {
    padding: 16px;
  }

  .mcp-header {
    flex-direction: column;
    gap: 12px;
    align-items: flex-start;
  }

  .header-actions {
    flex-wrap: wrap;
    width: 100%;
  }

  .metrics-grid {
    grid-template-columns: 1fr 1fr;
  }

  .metric-label {
    font-size: var(--font-size-base);
  }

  .tools-grid {
    grid-template-columns: 1fr;
  }

  .search-input {
    width: 100%;
    font-size: var(--font-size-base);
  }

  .category-tabs {
    overflow-x: auto;
  }

  .detail-meta-grid {
    grid-template-columns: 1fr;
  }

  .action-btn {
    min-height: 44px;
    padding: 8px 14px;
    font-size: var(--font-size-base);
  }

  .filter-select {
    min-height: 44px;
    font-size: var(--font-size-base);
  }

  .search-input {
    min-height: 44px;
  }

  .tool-card {
    min-height: 48px;
  }

  .tool-name {
    font-size: var(--font-size-base);
  }

  .tool-desc {
    font-size: var(--font-size-base);
  }

  .category-tab {
    min-height: 44px;
    padding: 8px 16px;
    font-size: var(--font-size-base);
  }

  .page-title {
    font-size: var(--font-size-xl);
  }

  .page-subtitle {
    font-size: var(--font-size-base);
  }

  .panel-title {
    font-size: var(--font-size-md);
  }
}

@media (max-width: 480px) {
  .metrics-grid {
    grid-template-columns: 1fr;
  }

  .metric-card {
    padding: 14px;
  }

  .metric-value {
    font-size: var(--font-size-xl);
  }

  .metric-label {
    font-size: var(--font-size-sm);
  }

  .mcp-tools {
    padding: 8px;
  }

  .page-title {
    font-size: var(--font-size-lg);
  }

  .page-subtitle {
    font-size: var(--font-size-sm);
  }

  .panel-title {
    font-size: var(--font-size-md);
  }

  .tool-card {
    padding: 10px;
  }

  .category-tab {
    font-size: var(--font-size-sm);
    padding: 6px 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .mcp-tools,
  .metric-card,
  .tool-card,
  .filter-bar,
  .bg-glow,
  .freshness-dot,
  .refresh-icon.spinning,
  .skeleton,
  .skeleton-line,
  .page-title {
    animation: none !important;
    transition: none !important;
  }
}
</style>
