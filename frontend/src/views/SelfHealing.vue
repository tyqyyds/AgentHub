<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useLogger } from '@/utils/logger'
import { POLLING_INTERVAL, UI } from '@/config'
import { api, apiClient, authFetch } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'
import { useApi } from '@/composables/useApi'
import { useAuthStore } from '@/stores/auth'

const { info, warn } = useLogger()
const { error: apiError } = useApi()
const authStore = useAuthStore()
const canWrite = computed(() => authStore.userRole !== 'viewer')
const healingError = ref<string | null>(null)

interface TimelineStep {
  id: string
  type: 'alert' | 'analysis' | 'solution' | 'approval' | 'execution' | 'verification'
  title: string
  description: string
  timestamp: string
  status: 'completed' | 'in-progress' | 'pending'
  agent?: string
  details?: Record<string, unknown>
}

interface StateMachineNode {
  id: string
  label: string
  type: 'start' | 'agent' | 'approval' | 'end'
  status: 'pending' | 'active' | 'completed' | 'skipped'
  agentName?: string
  reasoning?: string
  input?: Record<string, unknown>
  output?: Record<string, unknown>
  timestamp?: string
}

interface StateMachineEdge {
  id: string
  source: string
  target: string
  label?: string
  condition?: string
}

interface StateMachine {
  nodes: StateMachineNode[]
  edges: StateMachineEdge[]
}

interface HealingEvent {
  id: string
  type: string
  severity: string
  title: string
  description: string
  status: string
  targetDevice: string
  timeline: TimelineStep[]
  stateMachine: StateMachine
  createdAt?: string
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

interface GrayscaleTask {
  id: number
  task_id: string
  event_id: number
  target_devices: string[]
  canary_device: string
  canary_status: string
  canary_result?: Record<string, any> | null
  batch_progress: number
  batch_status?: string
  batch_completed_devices?: string[]
  batch_failed_devices?: string[]
  rollback_triggered?: boolean
  rollback_reason?: string | null
  overall_status: string
  created_by: string
  created_at: string
}

interface Evaluation {
  id: number
  evaluation_id: string
  event_id: number
  task_id: string
  effectiveness_score: number | null
  healing_action?: string
  root_cause_analysis?: string | null
  side_effects?: string[]
  recommendation?: string | null
  metrics_before?: Record<string, any>
  metrics_after?: Record<string, any> | null
  evaluated_at?: string | null
  created_at: string
}

const activeTab = ref<'events' | 'grayscale'>('events')

const healingMode = ref(localStorage.getItem('healingMode') || 'suggested')
const activeView = ref<'timeline' | 'state-machine'>('timeline')
const healingEvents = ref<HealingEvent[]>([])
const selectedEventId = ref<string | null>(null)
const selectedStateMachineNode = ref<StateMachineNode | null>(null)

const showRollbackModal = ref(false)
const rollbackMessage = ref('')
const rollbackSuccess = ref(false)
const showEventRollbackModal = ref(false)
const eventRollbackMessage = ref('')
const eventRollbackSuccess = ref(false)
const eventRollbackTarget = ref<HealingEvent | null>(null)
const showStateDetailModal = ref(false)

const isMockData = ref(false)
const isLoading = ref(true)
const isRefreshing = ref(false)
const lastRefreshTime = ref('')
const dataFreshness = ref('实时')
const fetchCount = ref(0)
const errorCount = ref(0)

const searchQuery = ref('')
const filterSeverity = ref<string>('all')
const filterStatus = ref<string>('all')
const filterType = ref<string>('all')
const currentPage = ref(1)
const totalPages = ref(1)
const totalEvents = ref(0)
const pageSize = UI.PAGE_SIZE

const showExportMenu = ref(false)

const grayscaleTasks = ref<GrayscaleTask[]>([])
const grayscaleEvaluations = ref<Evaluation[]>([])
const showCreateDialog = ref(false)
const showDetailDialog = ref(false)
const selectedTask = ref<GrayscaleTask | null>(null)
const isSubmitting = ref(false)

const createForm = ref({
  event_id: '',
  target_devices: [] as string[],
  canary_device: '',
  created_by: ''
})

const availableEvents = ref<any[]>([])
const availableDevices = ref<string[]>([])

let grayscalePollTimer: number | null = null

const metrics = ref<MetricCard[]>([
  { label: '自愈事件', value: 0, displayValue: 0, unit: '次', icon: '🛡️', color: 'var(--color-primary)', animFrameId: null },
  { label: '成功率', value: 0, displayValue: 0, unit: '%', icon: '✅', color: 'var(--color-success)', animFrameId: null },
  { label: '平均响应', value: 0, displayValue: 0, unit: '秒', icon: '⚡', color: 'var(--color-orange)', animFrameId: null },
  { label: '待处理', value: 0, displayValue: 0, unit: '项', icon: '📋', color: 'var(--color-error)', animFrameId: null }
])

const modes = [
  { value: 'auto', label: '全自动', desc: '自动检测并执行自愈方案' },
  { value: 'suggested', label: '建议模式', desc: '生成方案后需人工审批' },
  { value: 'alert', label: '仅告警', desc: '仅发送告警通知' }
]

const eventTypes = [
  { value: 'all', label: '全部类型' },
  { value: 'bandwidth', label: '带宽' },
  { value: 'link', label: '链路' },
  { value: 'acl', label: 'ACL' },
  { value: 'routing', label: '路由' }
]

const severityOptions = [
  { value: 'all', label: '全部级别' },
  { value: 'critical', label: '严重' },
  { value: 'high', label: '高危' },
  { value: 'medium', label: '中危' },
  { value: 'low', label: '低危' }
]

const statusOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'pending', label: '处理中' },
  { value: 'completed', label: '已完成' },
  { value: 'rejected', label: '已拒绝' },
  { value: 'rolled-back', label: '已回滚' }
]

let fetchAbortController: AbortController | null = null
let isFetching = false
let visibilityDebounceTimer: number | null = null
let pollingInterval: number | null = null
let handleDataUpdate: (() => void) | null = null
let rollbackTimer: number | null = null
let eventRollbackTimer: number | null = null

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

watch([filterSeverity, filterStatus, filterType], () => {
  currentPage.value = 1
  fetchHealingEvents()
})

const filteredEvents = computed(() => {
  let events = healingEvents.value

  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    events = events.filter(e =>
      (e.title || '').toLowerCase().includes(q) ||
      (e.description || '').toLowerCase().includes(q) ||
      (e.targetDevice || '').toLowerCase().includes(q) ||
      (e.id || '').toLowerCase().includes(q)
    )
  }

  if (filterSeverity.value !== 'all') {
    events = events.filter(e => e.severity === filterSeverity.value)
  }

  if (filterStatus.value !== 'all') {
    events = events.filter(e => e.status === filterStatus.value)
  }

  if (filterType.value !== 'all') {
    events = events.filter(e => e.type === filterType.value)
  }

  return events
})

const pendingCount = computed(() => healingEvents.value.filter(e => e.status === 'pending').length)
const completedCount = computed(() => healingEvents.value.filter(e => e.status === 'completed').length)
const criticalCount = computed(() => healingEvents.value.filter(e => e.severity === 'high' || e.severity === 'critical').length)

const selectMode = async (modeValue: string) => {
  healingMode.value = modeValue
  localStorage.setItem('healingMode', modeValue)
  info(`自愈模式切换: ${modeValue}`)
  try {
    await authFetch(api.events, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'mode_change', mode: modeValue })
    })
  } catch {
    // Silently fail - mode is saved locally anyway
  }
  showToast(`已切换至${modes.find(m => m.value === modeValue)?.label || modeValue}模式`, 'success')
}

const toggleEventDetail = (eventId: string) => {
  selectedEventId.value = selectedEventId.value === eventId ? null : eventId
}

const isExpanded = (eventId: string) => selectedEventId.value === eventId

const getStepIcon = (type: string) => {
  const icons: Record<string, string> = {
    alert: '🔔', analysis: '🔍', solution: '💡',
    approval: '✅', execution: '⚡', verification: '📊'
  }
  return icons[type] || '📌'
}

const getStepColor = (type: string, status: string) => {
  if (status === 'pending') return 'rgba(100, 116, 139, 0.3)'
  if (status === 'in-progress') return 'var(--color-primary)'
  const colors: Record<string, string> = {
    alert: '#EF4444', analysis: '#F59E0B', solution: '#6366F1',
    approval: '#10B981', execution: 'var(--color-primary)', verification: 'var(--color-success)'
  }
  return colors[type] || 'var(--color-text-tertiary)'
}

const getNodeColor = (status: string) => {
  const statusColors: Record<string, string> = {
    pending: 'rgba(100, 116, 139, 0.3)', active: 'var(--color-primary)',
    completed: 'var(--color-success)', skipped: 'rgba(100, 116, 139, 0.2)'
  }
  return statusColors[status] || statusColors.pending
}

const getNodeIcon = (type: string) => {
  const icons: Record<string, string> = { start: '▶️', agent: '🤖', approval: '✅', end: '🏁' }
  return icons[type] || '📌'
}

const getNodeStatusText = (status: string) => {
  const statusText: Record<string, string> = {
    completed: '已完成', active: '执行中', pending: '等待中', skipped: '已跳过'
  }
  return statusText[status] || '等待中'
}

const getSeverityText = (severity: string) => {
  const map: Record<string, string> = { critical: '严重', high: '高危', medium: '中危', low: '低危' }
  return map[severity] || severity
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    completed: '已完成', pending: '处理中', rejected: '已拒绝', 'rolled-back': '已回滚'
  }
  return map[status] || status
}

const getGrayscaleStatusType = (status: string) => {
  const map: Record<string, string> = {
    pending: 'info', canary_running: 'warning', canary_passed: 'success',
    canary_failed: 'danger', batch_running: 'warning', batch_completed: 'success',
    rolled_back: 'info', failed: 'danger'
  }
  return map[status] || 'info'
}

const getGrayscaleStatusText = (status: string) => {
  const map: Record<string, string> = {
    pending: '待执行', canary_running: '金丝雀执行中', canary_passed: '金丝雀通过',
    canary_failed: '金丝雀失败', batch_running: '批量执行中', batch_completed: '批量完成',
    rolled_back: '已回滚', failed: '失败'
  }
  return map[status] || status
}

const getCanaryStatusType = (status: string) => {
  const map: Record<string, string> = {
    pending: 'info', running: 'warning', passed: 'success', failed: 'danger'
  }
  return map[status] || 'info'
}

const getCanaryStatusText = (status: string) => {
  const map: Record<string, string> = {
    pending: '待执行', running: '执行中', passed: '通过', failed: '失败'
  }
  return map[status] || status
}

const fetchGrayscaleTasks = async (showLoading = false) => {
  if (showLoading) isRefreshing.value = true
  try {
    const data = await apiClient.get(api.grayscaleHealing.tasks)
    if (data.data) {
      const items = Array.isArray(data.data) ? data.data : (data.data?.items || [])
      grayscaleTasks.value = items
    }
  } catch (err: any) {
    warn('获取灰度自愈任务失败', { error: err.message })
    loadGrayscaleMockData()
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

const fetchGrayscaleEvaluations = async () => {
  try {
    const data = await apiClient.get(api.grayscaleHealing.evaluations)
    if (data.data) {
      const items = Array.isArray(data.data) ? data.data : (data.data?.items || [])
      grayscaleEvaluations.value = items
    }
  } catch (err: any) {
    warn('获取评估数据失败', { error: err.message })
    grayscaleEvaluations.value = [
      { id: 1, evaluation_id: 'eval_m3n4o5p6', event_id: 1, task_id: 'gs_a1b2c3d4', effectiveness_score: 0.92, healing_action: '切换到备用链路并重新路由流量', root_cause_analysis: '主用链路光纤衰减过大导致信号丢失', recommendation: '自愈效果良好，建议保持当前策略', created_at: new Date(Date.now() - 4.4*3600000).toISOString() },
      { id: 2, evaluation_id: 'eval_q7r8s9t0', event_id: 2, task_id: 'gs_e5f6g7h8', effectiveness_score: 0.15, healing_action: '优化路由表并清理无效ARP条目', root_cause_analysis: 'BGP邻居过多导致处理开销', recommendation: '自愈效果不佳，建议减少BGP邻居数量', created_at: new Date(Date.now() - 1.8*3600000).toISOString() },
      { id: 3, evaluation_id: 'eval_u1v2w3x4', event_id: 4, task_id: 'gs_i9j0k1l2', effectiveness_score: 0.88, healing_action: '重启防火墙进程并清理缓存', root_cause_analysis: '内存泄漏由规则匹配引擎引起', recommendation: '建议升级防火墙固件', created_at: new Date(Date.now() - 0.7*3600000).toISOString() },
      { id: 4, evaluation_id: 'eval_a1b2c3d4', event_id: 3, task_id: 'gs_m3n4o5p6', effectiveness_score: 0.95, healing_action: '重置接口GE0/0/1并检查光纤连接', root_cause_analysis: '光纤连接器松动导致误码率升高', recommendation: '建议定期检查光纤连接器', created_at: new Date(Date.now() - 6.9*3600000).toISOString() },
      { id: 5, evaluation_id: 'eval_e5f6g7h8', event_id: 5, task_id: 'gs_q7r8s9t0', effectiveness_score: 0.08, healing_action: '配置路由阻尼并检查对等体状态', root_cause_analysis: 'BGP对等体持续异常', recommendation: '建议先手动修复BGP对等体', created_at: new Date(Date.now() - 2.7*3600000).toISOString() },
      { id: 6, evaluation_id: 'eval_i9j0k1l2', event_id: 1, task_id: 'gs_u1v2w3x4', effectiveness_score: 0.90, healing_action: '切换到备用链路并重新路由流量', root_cause_analysis: '光模块老化引起链路故障', recommendation: '建议更换老化光模块', created_at: new Date(Date.now() - 10.4*3600000).toISOString() },
      { id: 7, evaluation_id: 'eval_m3n4o5p7', event_id: 4, task_id: 'gs_c9d0e1f2', effectiveness_score: 0.25, healing_action: '重启防火墙进程并清理缓存', root_cause_analysis: '深层内存泄漏需固件升级', recommendation: '建议联系厂商获取固件补丁', created_at: new Date(Date.now() - 4.9*3600000).toISOString() },
      { id: 8, evaluation_id: 'eval_q7r8s9t1', event_id: 3, task_id: 'gs_g3h4i5j6', effectiveness_score: null, healing_action: '重置接口并检查光纤连接', root_cause_analysis: null, recommendation: '任务尚未执行，等待完成', created_at: new Date(Date.now() - 0.1*3600000).toISOString() },
      { id: 9, evaluation_id: 'eval_u1v2w3x5', event_id: 5, task_id: 'gs_k7l8m9n0', effectiveness_score: 0.82, healing_action: '配置路由阻尼并检查对等体状态', root_cause_analysis: '路由阻尼有效抑制了路由震荡', recommendation: '建议持续监控BGP对等体', created_at: new Date(Date.now() - 14.2*3600000).toISOString() },
      { id: 10, evaluation_id: 'eval_y5z6a7b9', event_id: 2, task_id: 'gs_y5z6a7b8', effectiveness_score: null, healing_action: '优化路由表并清理无效ARP条目', root_cause_analysis: null, recommendation: '金丝雀阶段执行中', created_at: new Date(Date.now() - 0.2*3600000).toISOString() },
    ]
  }
}

const fetchAvailableOptions = async () => {
  try {
    const eventsResp = await apiClient.get(api.events)
    if (eventsResp.data) {
      availableEvents.value = Array.isArray(eventsResp.data) ? eventsResp.data : (eventsResp.data?.items || [])
    }
  } catch {
    availableEvents.value = [
      { id: '1', event_type: 'bandwidth', description: '带宽不足告警' },
      { id: '2', event_type: 'link', description: '链路故障告警' },
      { id: '3', event_type: 'routing', description: '路由异常告警' }
    ]
  }
  try {
    const topoResp = await apiClient.get(api.topologyDevices)
    if (topoResp.data) {
      const nodes = Array.isArray(topoResp.data) ? topoResp.data : (topoResp.data?.items || [])
      availableDevices.value = nodes.map((n: any) => n.name || n.id)
    }
  } catch {
    availableDevices.value = ['Switch-A1', 'Router-C1', 'Firewall-B1', 'Switch-B2', 'Core-Router-1']
  }
}

const loadGrayscaleMockData = () => {
  grayscaleTasks.value = [
    { id: 1, task_id: 'gs_a1b2c3d4', event_id: 1, target_devices: ['SW-BJ-01','SW-SH-01','SW-GZ-01'], canary_device: 'SW-GZ-01', canary_status: 'success', batch_progress: 100, batch_status: 'success', overall_status: 'batch_success', created_by: 'system', created_at: new Date(Date.now() - 5*3600000).toISOString() },
    { id: 2, task_id: 'gs_e5f6g7h8', event_id: 2, target_devices: ['RT-GZ-01','RT-CD-01'], canary_device: 'RT-CD-01', canary_status: 'failed', batch_progress: 0, batch_status: 'pending', rollback_triggered: true, rollback_reason: 'Canary device unhealthy', overall_status: 'rolled_back', created_by: 'admin', created_at: new Date(Date.now() - 2*3600000).toISOString() },
    { id: 3, task_id: 'gs_i9j0k1l2', event_id: 4, target_devices: ['FW-WH-01','FW-NJ-01'], canary_device: 'FW-WH-01', canary_status: 'success', batch_progress: 50, batch_status: 'running', overall_status: 'batch_running', created_by: 'system', created_at: new Date(Date.now() - 1*3600000).toISOString() },
    { id: 4, task_id: 'gs_m3n4o5p6', event_id: 3, target_devices: ['SW-CD-03','SW-CD-04','SW-CD-05'], canary_device: 'SW-CD-03', canary_status: 'success', batch_progress: 100, batch_status: 'success', overall_status: 'batch_success', created_by: 'admin', created_at: new Date(Date.now() - 8*3600000).toISOString() },
    { id: 5, task_id: 'gs_q7r8s9t0', event_id: 5, target_devices: ['RT-NJ-02','RT-NJ-03'], canary_device: 'RT-NJ-02', canary_status: 'failed', batch_progress: 0, batch_status: 'pending', rollback_triggered: true, rollback_reason: 'BGP对等体异常', overall_status: 'rolled_back', created_by: 'operator', created_at: new Date(Date.now() - 3*3600000).toISOString() },
    { id: 6, task_id: 'gs_u1v2w3x4', event_id: 1, target_devices: ['SW-BJ-02','SW-BJ-03','SW-BJ-04'], canary_device: 'SW-BJ-02', canary_status: 'success', batch_progress: 100, batch_status: 'success', overall_status: 'batch_success', created_by: 'system', created_at: new Date(Date.now() - 12*3600000).toISOString() },
    { id: 7, task_id: 'gs_y5z6a7b8', event_id: 2, target_devices: ['RT-GZ-01','RT-GZ-02','RT-GZ-03'], canary_device: 'RT-GZ-02', canary_status: 'running', batch_progress: 0, batch_status: 'pending', overall_status: 'canary_running', created_by: 'operator', created_at: new Date(Date.now() - 0.3*3600000).toISOString() },
    { id: 8, task_id: 'gs_c9d0e1f2', event_id: 4, target_devices: ['FW-WH-01','FW-CS-01'], canary_device: 'FW-CS-01', canary_status: 'success', batch_progress: 50, batch_status: 'failed', rollback_triggered: true, rollback_reason: '批量阶段FW-WH-01失败', overall_status: 'rolled_back', created_by: 'admin', created_at: new Date(Date.now() - 6*3600000).toISOString() },
    { id: 9, task_id: 'gs_g3h4i5j6', event_id: 3, target_devices: ['SW-CD-03'], canary_device: 'SW-CD-03', canary_status: 'pending', batch_progress: 0, batch_status: 'pending', overall_status: 'canary_pending', created_by: 'operator', created_at: new Date(Date.now() - 0.5*3600000).toISOString() },
    { id: 10, task_id: 'gs_k7l8m9n0', event_id: 5, target_devices: ['RT-NJ-02','RT-NJ-03','RT-NJ-04'], canary_device: 'RT-NJ-03', canary_status: 'success', batch_progress: 33, batch_status: 'running', overall_status: 'batch_running', created_by: 'system', created_at: new Date(Date.now() - 15*3600000).toISOString() },
  ]
}

const submitCreateTask = async () => {
  if (!createForm.value.event_id || !createForm.value.canary_device) {
    showToast('请填写必要字段', 'error')
    return
  }
  isSubmitting.value = true
  try {
    await apiClient.post(api.grayscaleHealing.tasks, createForm.value)
    showToast('灰度自愈任务已创建', 'success')
    showCreateDialog.value = false
    createForm.value = { event_id: '', target_devices: [], canary_device: '', created_by: '' }
    fetchGrayscaleTasks()
  } catch (err: any) {
    warn('创建任务失败', { error: err.message })
    showToast('创建任务失败', 'error')
  } finally {
    isSubmitting.value = false
  }
}

const executeCanary = async (task: GrayscaleTask) => {
  try {
    await apiClient.post(api.grayscaleHealing.canary(task.task_id))
    showToast(`任务 ${task.task_id} 金丝雀执行已触发`, 'success')
    fetchGrayscaleTasks()
  } catch (err: any) {
    warn('执行金丝雀失败', { error: err.message })
    showToast('执行金丝雀失败', 'error')
  }
}

const executeBatch = async (task: GrayscaleTask) => {
  try {
    await apiClient.post(api.grayscaleHealing.batch(task.task_id))
    showToast(`任务 ${task.task_id} 批量执行已触发`, 'success')
    fetchGrayscaleTasks()
  } catch (err: any) {
    warn('执行批量失败', { error: err.message })
    showToast('执行批量失败', 'error')
  }
}

const executeGrayscaleRollback = async (task: GrayscaleTask) => {
  try {
    await apiClient.post(api.grayscaleHealing.rollback(task.task_id))
    showToast(`任务 ${task.task_id} 回滚已触发`, 'success')
    fetchGrayscaleTasks()
  } catch (err: any) {
    warn('执行回滚失败', { error: err.message })
    showToast('执行回滚失败', 'error')
  }
}

const analyzeRootCause = async (task: GrayscaleTask) => {
  try {
    await apiClient.post(api.grayscaleHealing.analyze(task.task_id))
    showToast(`任务 ${task.task_id} 根因分析已触发`, 'success')
  } catch (err: any) {
    warn('根因分析失败', { error: err.message })
    showToast('根因分析失败', 'error')
  }
}

const openDetail = (task: GrayscaleTask) => {
  selectedTask.value = task
  showDetailDialog.value = true
}

const formatGrayscaleTime = (dateStr: string): string => {
  if (!dateStr) return '--'
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  return date.toLocaleString('zh-CN')
}

const upgradeToGrayscale = (event: HealingEvent) => {
  activeTab.value = 'grayscale'
  createForm.value.event_id = event.id
  createForm.value.target_devices = event.targetDevice ? [event.targetDevice] : []
  createForm.value.canary_device = event.targetDevice || ''
  showCreateDialog.value = true
}

const handleNodeClick = (node: StateMachineNode) => {
  if (node.status !== 'pending' && node.status !== 'skipped') {
    selectedStateMachineNode.value = node
    showStateDetailModal.value = true
  }
}

const getNodePosition = (nodeId: string, nodes: StateMachineNode[]) => {
  const index = nodes.findIndex(n => n.id === nodeId)
  return { x: 400, y: 80 + index * 120 }
}

const generateStateMachine = (event: HealingEvent): StateMachine => {
  // Build state machine from real event data
  const nodes: StateMachineNode[] = [
    { id: 'start', label: '开始', type: 'start', status: 'completed' },
    {
      id: 'detection', label: '故障检测Agent', type: 'agent',
      status: event.status !== 'pending' ? 'completed' : 'active',
      agentName: 'TelemetryAgent',
      reasoning: `检测到${event.type || event.eventType || '未知'}类型故障，严重程度: ${event.severity}`,
      input: { event_type: event.type || event.eventType, device: event.targetDevice },
      output: { description: event.description, severity: event.severity },
      timestamp: event.timestamp
    },
    {
      id: 'analysis', label: '根因分析Agent', type: 'agent',
      status: event.timeline.some(t => t.type === 'analysis' && t.status === 'completed') ? 'completed' :
              event.timeline.some(t => t.type === 'analysis' && t.status === 'in-progress') ? 'active' : 'pending',
      agentName: 'AnalysisAgent',
      reasoning: event.suggestedAction || '分析故障根因中...',
      input: { event: event.description, device: event.targetDevice },
      output: { rootCause: event.suggestedAction || '待分析' },
      timestamp: event.timeline.find(t => t.type === 'analysis')?.timestamp
    },
    {
      id: 'solution', label: '方案生成Agent', type: 'agent',
      status: event.timeline.some(t => t.type === 'solution' && t.status === 'completed') ? 'completed' : 'pending',
      agentName: 'SolutionAgent',
      reasoning: event.suggestedAction ? `基于根因分析生成自愈方案: ${event.suggestedAction}` : '基于根因分析生成自愈方案',
      input: { rootCause: event.suggestedAction, targetDevice: event.targetDevice },
      output: { solution: event.suggestedAction || '待生成' },
      timestamp: event.timeline.find(t => t.type === 'solution')?.timestamp
    },
    {
      id: 'approval', label: '安全审批', type: 'approval',
      status: event.status === 'completed' ? 'completed' : event.status === 'rejected' ? 'skipped' : 'pending',
      agentName: 'HumanApproval',
      reasoning: event.status === 'completed' ? '管理员审批通过' : '等待人工审批',
      input: { solution: event.suggestedAction },
      output: { approved: event.status === 'completed' },
      timestamp: event.timeline.find(t => t.type === 'approval')?.timestamp
    },
    {
      id: 'execution', label: '执行Agent', type: 'agent',
      status: event.status === 'completed' ? 'completed' : event.status === 'healing' ? 'active' : 'pending',
      agentName: 'ExecutionAgent',
      reasoning: '将配置命令转换为设备可执行指令，并通过边缘代理下发',
      input: { commands: [event.suggestedAction || 'N/A'] },
      output: { success: event.status === 'completed', device: event.targetDevice },
      timestamp: event.timeline.find(t => t.type === 'execution')?.timestamp
    },
    {
      id: 'verification', label: '验证Agent', type: 'agent',
      status: event.status === 'completed' ? 'completed' : 'pending',
      agentName: 'VerificationAgent',
      reasoning: '持续监控关键指标，确认自愈效果',
      input: { device: event.targetDevice },
      output: { verified: event.status === 'completed' },
      timestamp: event.timeline.find(t => t.type === 'verification')?.timestamp
    },
    { id: 'end', label: '结束', type: 'end', status: event.status === 'completed' ? 'completed' : 'pending' }
  ]

  const edges: StateMachineEdge[] = [
    { id: 'e1', source: 'start', target: 'detection' },
    { id: 'e2', source: 'detection', target: 'analysis' },
    { id: 'e3', source: 'analysis', target: 'solution' },
    { id: 'e4', source: 'solution', target: 'approval', condition: '方案已生成', label: '提交审批' },
    { id: 'e5', source: 'approval', target: 'execution', condition: 'approved = true', label: '通过' },
    { id: 'e6', source: 'approval', target: 'end', condition: 'approved = false', label: '拒绝' },
    { id: 'e7', source: 'execution', target: 'verification' },
    { id: 'e8', source: 'verification', target: 'end' }
  ]

  return { nodes, edges }
}

interface ApiEvent {
  id: number
  event_type: string
  severity: string
  description: string
  status: string
  target_device: string
  suggested_action?: string
  executed_by?: string
  created_at: string
}

const addMinutes = (date: Date, minutes: number): Date => {
  const newDate = new Date(date)
  newDate.setMinutes(newDate.getMinutes() + minutes)
  return newDate
}

const transformToTimelineEvent = (item: ApiEvent): HealingEvent => {
  const baseTime = new Date(item.created_at || Date.now())

  const timeline: TimelineStep[] = []

  timeline.push({
    id: `${item.id}-1`, type: 'alert', title: '遥测告警触发',
    description: getAlertDescription(item.event_type, item.severity),
    timestamp: baseTime.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    status: 'completed', agent: '遥测Agent'
  })

  if (item.status !== 'pending' || item.suggested_action) {
    timeline.push({
      id: `${item.id}-2`, type: 'analysis', title: '根因分析完成',
      description: getAnalysisDescription(item.event_type, item.description),
      timestamp: addMinutes(baseTime, 3).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      status: item.status === 'pending' ? 'in-progress' : 'completed', agent: '分析Agent'
    })
  }

  if (item.suggested_action) {
    timeline.push({
      id: `${item.id}-3`, type: 'solution', title: '自愈方案生成',
      description: item.suggested_action,
      timestamp: addMinutes(baseTime, 6).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      status: item.status === 'pending' ? 'pending' : 'completed', agent: '方案Agent'
    })
  }

  if (item.status === 'completed' || item.status === 'rejected') {
    timeline.push({
      id: `${item.id}-4`, type: 'approval',
      title: item.status === 'completed' ? '人工审批通过' : '人工拒绝',
      description: item.status === 'completed' ? '管理员确认执行自愈方案' : '管理员拒绝了自愈方案',
      timestamp: addMinutes(baseTime, 8).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      status: 'completed', agent: item.executed_by || '管理员'
    })
  }

  if (item.status === 'completed') {
    timeline.push({
      id: `${item.id}-5`, type: 'execution', title: '配置执行成功',
      description: `已在设备 ${item.target_device || '未知设备'} 上执行配置变更`,
      timestamp: addMinutes(baseTime, 10).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      status: 'completed', agent: '执行Agent'
    })
    timeline.push({
      id: `${item.id}-6`, type: 'verification', title: '闭环验证通过',
      description: '指标已恢复正常，自愈流程完成',
      timestamp: addMinutes(baseTime, 12).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      status: 'completed', agent: '验证Agent'
    })
  }

  const event: HealingEvent = {
    id: `SH-${String(item.id).padStart(3, '0')}`,
    type: item.event_type,
    severity: item.severity,
    title: getEventTitle(item.event_type, item.severity),
    description: item.description,
    status: item.status || 'pending',
    targetDevice: item.target_device || '未知设备',
    timeline,
    stateMachine: { nodes: [], edges: [] },
    createdAt: item.created_at
  }

  event.stateMachine = generateStateMachine(event)
  return event
}

const getAlertDescription = (type: string, severity: string): string => {
  const alerts: Record<string, Record<string, string>> = {
    bandwidth: { high: '检测到带宽指标超过阈值', medium: '带宽使用率偏高', low: '带宽出现波动' },
    link: { high: '链路健康度异常', medium: '链路质量下降', low: '链路延迟增加' },
    acl: { high: 'ACL规则冲突检测', medium: 'ACL规则异常', low: 'ACL规则建议优化' },
    routing: { high: '路由协议异常', medium: '路由收敛延迟', low: '路由配置建议' }
  }
  return alerts[type]?.[severity] || '检测到网络异常'
}

const getAnalysisDescription = (_type: string, desc: string): string => {
  return `通过多维度数据分析，确定问题根源：${desc}`
}

const getEventTitle = (type: string, severity: string): string => {
  const titles: Record<string, Record<string, string>> = {
    bandwidth: { high: '带宽不足自愈', medium: '带宽优化处理', low: '带宽波动提醒' },
    link: { high: '链路故障自愈', medium: '链路质量优化', low: '链路维护建议' },
    acl: { high: 'ACL冲突处理', medium: 'ACL规则优化', low: 'ACL配置建议' },
    routing: { high: '路由故障恢复', medium: '路由优化处理', low: '路由配置建议' }
  }
  return titles[type]?.[severity] || '未知事件'
}

const updateMetrics = () => {
  const events = healingEvents.value
  const total = events.length
  const completed = events.filter(e => e.status === 'completed').length
  const pending = events.filter(e => e.status === 'pending').length
  const successRate = total > 0 ? Math.round((completed / total) * 100) : 0
  const avgResponse = total > 0 && completed > 0
    ? Math.round(events.filter(e => e.status === 'completed').reduce((sum, e) => {
        const steps = e.timeline.length
        return sum + (steps > 0 ? steps * 2.5 : 0)
      }, 0) / completed)
    : 0

  metrics.value[0].value = total
  metrics.value[1].value = successRate
  metrics.value[2].value = avgResponse
  metrics.value[3].value = pending
}

const fetchHealingEvents = async (showLoading = false) => {
  if (isFetching) return
  isFetching = true

  if (fetchAbortController) {
    fetchAbortController.abort()
  }
  fetchAbortController = new AbortController()
  const signal = fetchAbortController.signal

  lastRefreshTime.value = new Date().toLocaleTimeString()
  if (showLoading) isRefreshing.value = true

  try {
    const params = new URLSearchParams()
    if (filterStatus.value !== 'all') params.set('status', filterStatus.value)
    if (filterSeverity.value !== 'all') params.set('severity', filterSeverity.value)
    params.set('page', String(currentPage.value))
    params.set('limit', String(pageSize))

    const response = await authFetch(`${api.events}?${params.toString()}`, { signal })
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    const data = await response.json()

    if (data.status === 'success' && data.data) {
      healingEvents.value = (data.data || []).map((item: any) => transformToTimelineEvent(item))
      fetchCount.value++

      if (data.pagination) {
        totalPages.value = data.pagination.pages
        totalEvents.value = data.pagination.total
      }

      updateMetrics()
      dataFreshness.value = '实时'
      isMockData.value = false
      healingError.value = null
    } else {
      loadMockData()
      isMockData.value = true
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    const message = err instanceof Error ? err.message : String(err)
    warn('获取自愈事件失败', { error: message })
    errorCount.value++
    healingError.value = message
    loadMockData()
    isMockData.value = true
    dataFreshness.value = '降级'
  } finally {
    isRefreshing.value = false
    isLoading.value = false
    isFetching = false
    fetchAbortController = null
  }
}

const loadMockData = () => {
  const events: HealingEvent[] = [
    {
      id: 'SH-001', type: 'bandwidth', severity: 'high', title: '视频会议带宽保障',
      description: '检测到研发子网视频会议流量带宽低于200M阈值，当前带宽150M',
      status: 'completed', targetDevice: 'Switch-A1',
      timeline: [
        { id: 'SH-001-1', type: 'alert', title: '遥测告警触发', description: '检测到带宽指标: 150M < 阈值: 200M', timestamp: '15:01:02', status: 'completed', agent: '遥测Agent' },
        { id: 'SH-001-2', type: 'analysis', title: '根因分析完成', description: '通过流量分析，确定为非视频业务占用过多带宽', timestamp: '15:01:05', status: 'completed', agent: '分析Agent' },
        { id: 'SH-001-3', type: 'solution', title: '自愈方案生成', description: '执行非视频流量限速50%，释放约50M带宽', timestamp: '15:01:08', status: 'completed', agent: '方案Agent' },
        { id: 'SH-001-4', type: 'approval', title: '人工审批通过', description: '管理员确认执行自愈方案', timestamp: '15:01:10', status: 'completed', agent: '管理员' },
        { id: 'SH-001-5', type: 'execution', title: '配置执行成功', description: '已在设备 Switch-A1 上执行 QoS 限速配置', timestamp: '15:01:12', status: 'completed', agent: '执行Agent' },
        { id: 'SH-001-6', type: 'verification', title: '闭环验证通过', description: '当前带宽已恢复至 220M，自愈流程完成', timestamp: '15:01:15', status: 'completed', agent: '验证Agent' }
      ],
      stateMachine: { nodes: [], edges: [] }
    },
    {
      id: 'SH-002', type: 'link', severity: 'medium', title: '链路质量优化',
      description: '链路A丢包率>5%，影响网络稳定性',
      status: 'pending', targetDevice: 'Router-C1',
      timeline: [
        { id: 'SH-002-1', type: 'alert', title: '遥测告警触发', description: '检测到链路丢包率: 5.2% > 阈值: 3%', timestamp: '15:15:30', status: 'completed', agent: '遥测Agent' },
        { id: 'SH-002-2', type: 'analysis', title: '根因分析完成', description: '分析显示链路A存在周期性丢包，建议切换至备用链路', timestamp: '15:15:35', status: 'in-progress', agent: '分析Agent' },
        { id: 'SH-002-3', type: 'solution', title: '自愈方案生成', description: '建议执行流量切换至备用链路B', timestamp: '15:15:40', status: 'pending', agent: '方案Agent' }
      ],
      stateMachine: { nodes: [], edges: [] }
    },
    {
      id: 'SH-003', type: 'acl', severity: 'low', title: 'ACL规则优化',
      description: '检测到新配置ACL规则与现有规则存在潜在冲突',
      status: 'pending', targetDevice: 'Firewall-B1',
      timeline: [
        { id: 'SH-003-1', type: 'alert', title: '遥测告警触发', description: '检测到ACL规则配置异常', timestamp: '15:30:00', status: 'completed', agent: '遥测Agent' },
        { id: 'SH-003-2', type: 'analysis', title: '根因分析中', description: '正在分析ACL规则优先级和匹配顺序', timestamp: '15:30:05', status: 'in-progress', agent: '分析Agent' }
      ],
      stateMachine: { nodes: [], edges: [] }
    },
    {
      id: 'SH-004', type: 'routing', severity: 'high', title: '路由故障恢复',
      description: '核心路由器BGP邻居关系频繁震荡',
      status: 'completed', targetDevice: 'Core-Router-1',
      timeline: [
        { id: 'SH-004-1', type: 'alert', title: '遥测告警触发', description: 'BGP邻居状态变化超过阈值', timestamp: '14:20:10', status: 'completed', agent: '遥测Agent' },
        { id: 'SH-004-2', type: 'analysis', title: '根因分析完成', description: 'BGP定时器配置不一致导致邻居震荡', timestamp: '14:20:15', status: 'completed', agent: '分析Agent' },
        { id: 'SH-004-3', type: 'solution', title: '自愈方案生成', description: '调整BGP keepalive和hold定时器参数', timestamp: '14:20:18', status: 'completed', agent: '方案Agent' },
        { id: 'SH-004-4', type: 'approval', title: '人工审批通过', description: '管理员确认执行', timestamp: '14:20:20', status: 'completed', agent: '管理员' },
        { id: 'SH-004-5', type: 'execution', title: '配置执行成功', description: '已在核心路由器上更新BGP定时器', timestamp: '14:20:25', status: 'completed', agent: '执行Agent' },
        { id: 'SH-004-6', type: 'verification', title: '闭环验证通过', description: 'BGP邻居关系稳定，震荡已消除', timestamp: '14:20:30', status: 'completed', agent: '验证Agent' }
      ],
      stateMachine: { nodes: [], edges: [] }
    },
    {
      id: 'SH-005', type: 'bandwidth', severity: 'medium', title: '带宽优化处理',
      description: '办公区网络带宽利用率持续超过80%',
      status: 'rejected', targetDevice: 'Switch-B2',
      timeline: [
        { id: 'SH-005-1', type: 'alert', title: '遥测告警触发', description: '带宽利用率: 85% > 阈值: 80%', timestamp: '16:00:00', status: 'completed', agent: '遥测Agent' },
        { id: 'SH-005-2', type: 'analysis', title: '根因分析完成', description: '非关键业务流量占用过多带宽', timestamp: '16:00:05', status: 'completed', agent: '分析Agent' },
        { id: 'SH-005-3', type: 'solution', title: '自愈方案生成', description: '建议对非关键业务实施流量整形', timestamp: '16:00:08', status: 'completed', agent: '方案Agent' },
        { id: 'SH-005-4', type: 'approval', title: '人工拒绝', description: '管理员拒绝了自愈方案，需进一步评估', timestamp: '16:00:12', status: 'completed', agent: '管理员' }
      ],
      stateMachine: { nodes: [], edges: [] }
    }
  ]

  healingEvents.value = events.map(event => {
    event.stateMachine = generateStateMachine(event)
    return event
  })

  totalEvents.value = events.length
  totalPages.value = 1
  updateMetrics()
}

const executeAction = async (event: HealingEvent) => {
  executeTargetEvent.value = event
  showExecuteConfirm.value = true
}

const doExecuteAction = async () => {
  const event = executeTargetEvent.value
  showExecuteConfirm.value = false
  if (!event) return

  const eventId = parseInt(event.id.replace('SH-', ''))

  try {
    const response = await authFetch(api.eventsExecute(eventId), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' }
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()

    if (data.status === 'success') {
      const index = healingEvents.value.findIndex(e => e.id === event.id)
      if (index !== -1) {
        healingEvents.value[index].status = 'completed'
        const baseTime = new Date()

        healingEvents.value[index].timeline = [
          ...healingEvents.value[index].timeline.filter(step => step.type !== 'approval' && step.type !== 'execution' && step.type !== 'verification'),
          {
            id: `${event.id}-4`, type: 'approval', title: '人工审批通过',
            description: '管理员确认执行自愈方案',
            timestamp: addMinutes(baseTime, 0).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            status: 'completed', agent: '管理员'
          },
          {
            id: `${event.id}-5`, type: 'execution', title: '配置执行成功',
            description: `已在设备 ${event.targetDevice} 上执行配置变更`,
            timestamp: addMinutes(baseTime, 2).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            status: 'completed', agent: '执行Agent'
          },
          {
            id: `${event.id}-6`, type: 'verification', title: '闭环验证通过',
            description: '指标已恢复正常，自愈流程完成',
            timestamp: addMinutes(baseTime, 4).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            status: 'completed', agent: '验证Agent'
          }
        ]

        healingEvents.value[index].stateMachine = generateStateMachine(healingEvents.value[index])
      }

      updateMetrics()
      window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
      showToast(`事件 ${event.id} 自愈方案已执行`, 'success')
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    warn('执行自愈失败', { error: message })
    showToast('执行自愈失败，请稍后重试', 'error')
  }
}

const rejectReasonInput = ref('')
const showRejectModal = ref(false)
const showExecuteConfirm = ref(false)
const executeTargetEvent = ref<HealingEvent | null>(null)
const rejectTargetEvent = ref<HealingEvent | null>(null)

const rejectAction = async (event: HealingEvent) => {
  rejectTargetEvent.value = event
  rejectReasonInput.value = ''
  showRejectModal.value = true
}

const confirmReject = async () => {
  if (!rejectTargetEvent.value) return
  const event = rejectTargetEvent.value
  const reason = rejectReasonInput.value.trim() || 'Rejected by user'
  showRejectModal.value = false

  const eventId = parseInt(event.id.replace('SH-', ''))

  try {
    const response = await authFetch(api.eventsReject(eventId), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason || 'Rejected by user' })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()

    if (data.status === 'success') {
      const index = healingEvents.value.findIndex(e => e.id === event.id)
      if (index !== -1) {
        healingEvents.value[index].status = 'rejected'
        healingEvents.value[index].timeline.push({
          id: `${event.id}-4`, type: 'approval', title: '人工拒绝',
          description: '管理员拒绝了自愈方案',
          timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          status: 'completed', agent: '管理员'
        })
        healingEvents.value[index].stateMachine = generateStateMachine(healingEvents.value[index])
      }

      updateMetrics()
      window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
      showToast(`事件 ${event.id} 自愈方案已拒绝`, 'warning')
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    warn('拒绝自愈失败', { error: message })
    showToast('操作失败，请稍后重试', 'error')
  }
}

const handleRollback = () => {
  showRollbackModal.value = true
}

const confirmRollback = async () => {
  try {
    rollbackMessage.value = '正在执行回滚...'
    const response = await authFetch(api.eventsGlobalRollback, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    rollbackSuccess.value = true
    rollbackMessage.value = '回滚操作已执行，请等待系统恢复...'
    showToast('全局回滚已执行', 'warning')
    rollbackTimer = window.setTimeout(() => {
      rollbackTimer = null
      showRollbackModal.value = false
      rollbackSuccess.value = false
      rollbackMessage.value = ''
      fetchHealingEvents()
    }, 2000)
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    warn('全局回滚失败', { error: message })
    rollbackMessage.value = '回滚失败，请稍后重试'
    rollbackSuccess.value = false
    showToast('全局回滚失败', 'error')
  }
}

const handleEventRollback = (event: HealingEvent) => {
  eventRollbackTarget.value = event
  showEventRollbackModal.value = true
}

const confirmEventRollback = async () => {
  if (eventRollbackTarget.value) {
    const eventId = parseInt(eventRollbackTarget.value.id.replace('SH-', ''))
    try {
      const response = await authFetch(api.eventsRollback(eventId), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' }
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const index = healingEvents.value.findIndex(e => e.id === eventRollbackTarget.value!.id)
      if (index !== -1) {
        healingEvents.value[index].status = 'rolled-back'
        healingEvents.value[index].timeline.push({
          id: `${eventRollbackTarget.value!.id}-rollback`, type: 'verification',
          title: '已回滚', description: '该自愈操作已被撤销',
          timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          status: 'completed', agent: '系统'
        })
        healingEvents.value[index].stateMachine = generateStateMachine(healingEvents.value[index])
      }
      eventRollbackSuccess.value = true
      eventRollbackMessage.value = `事件 ${eventRollbackTarget.value.id} 回滚成功！`
      updateMetrics()
      showToast(`事件 ${eventRollbackTarget.value.id} 已回滚`, 'warning')
      eventRollbackTimer = window.setTimeout(() => {
        eventRollbackTimer = null
        showEventRollbackModal.value = false
        eventRollbackSuccess.value = false
        eventRollbackMessage.value = ''
        eventRollbackTarget.value = null
      }, 2000)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      warn('事件回滚失败', { error: message })
      showToast('回滚失败，请稍后重试', 'error')
    }
  }
}

const cancelRollback = () => {
  showRollbackModal.value = false
  rollbackSuccess.value = false
  rollbackMessage.value = ''
}

const exportData = (format: 'json' | 'csv') => {
  const exportPayload = {
    exportTime: new Date().toISOString(),
    mode: healingMode.value,
    totalEvents: healingEvents.value.length,
    events: healingEvents.value.map(e => ({
      id: e.id,
      type: e.type,
      severity: e.severity,
      title: e.title,
      description: e.description,
      status: e.status,
      targetDevice: e.targetDevice,
      timelineSteps: e.timeline.length,
      createdAt: e.createdAt
    })),
    metrics: metrics.value.map(m => ({ label: m.label, value: m.value, unit: m.unit }))
  }

  if (format === 'json') {
    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `self-healing_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  } else {
    const escCsv = (v: string | number): string => { const s = String(v); return /[",\n\r=+\-@]/.test(s) ? `"${s.replace(/"/g, '""').replace(/[\r\n]+/g, ' ')}"` : s }
    const headers = '事件ID,类型,严重级别,标题,状态,目标设备,时间轴步骤数\n'
    const rows = healingEvents.value.map(e =>
      [e.id, e.type, e.severity, e.title, e.status, e.targetDevice, e.timeline.length].map(escCsv).join(',')
    ).join('\n')
    const blob = new Blob(['\uFEFF' + headers + rows], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `self-healing_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  showExportMenu.value = false
  showToast(`数据已导出为 ${format.toUpperCase()} 格式`, 'success')
}

const manualRefresh = async () => {
  isRefreshing.value = true
  try {
    await fetchHealingEvents(true)
    showToast('数据已刷新', 'success')
  } catch {
    showToast('刷新失败', 'error')
  }
}

const handleVisibilityChange = () => {
  if (!document.hidden) {
    if (visibilityDebounceTimer) clearTimeout(visibilityDebounceTimer)
    visibilityDebounceTimer = window.setTimeout(() => {
      if (!isFetching) {
        fetchHealingEvents(false)
      }
    }, 300)
  }
}

const handleKeydown = (e: KeyboardEvent) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
    e.preventDefault()
    manualRefresh()
  }
  if (e.key === 'Escape') {
    if (showStateDetailModal.value) showStateDetailModal.value = false
    else if (showRollbackModal.value) cancelRollback()
    else if (showEventRollbackModal.value) showEventRollbackModal.value = false
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

const goToPage = (page: number) => {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    fetchHealingEvents()
  }
}

const clearFilters = () => {
  searchQuery.value = ''
  filterSeverity.value = 'all'
  filterStatus.value = 'all'
  filterType.value = 'all'
}

function handleAssistantExecute(e: Event) {
  const detail = (e as CustomEvent).detail
  if (detail?.command === 'retry_failed_healing') {
    fetchHealingEvents(true)
  }
}

function handleAssistantFillForm(e: Event) {
  const detail = (e as CustomEvent).detail
  if (!detail?.field) return
  const field = detail.field as string
  if (field.includes('severity') && detail.value) {
    filterSeverity.value = detail.value
  }
  if (field.includes('filter') && detail.value) {
    if (detail.filterType === 'status') {
      filterStatus.value = detail.value
    } else if (detail.filterType === 'type') {
      filterType.value = detail.value
    } else {
      searchQuery.value = detail.value
    }
  }
}

onMounted(() => {
  info('SelfHealing mounted, initializing...')
  fetchHealingEvents(true)
  fetchAvailableOptions()
  fetchGrayscaleEvaluations()

  handleDataUpdate = () => {
    fetchHealingEvents(false)
  }

  window.addEventListener('dashboardDataUpdated', handleDataUpdate)
  window.addEventListener('assistant:execute', handleAssistantExecute)
  window.addEventListener('assistant:fill_form', handleAssistantFillForm)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('click', handleClickOutside)

  pollingInterval = window.setInterval(() => {
    if (!document.hidden) {
      fetchHealingEvents(false)
    }
  }, POLLING_INTERVAL.DASHBOARD)

  grayscalePollTimer = window.setInterval(() => {
    if (!document.hidden) fetchGrayscaleTasks()
  }, 30000)

  info('SelfHealing 初始化完成')
})

onUnmounted(() => {
  if (pollingInterval !== null) clearInterval(pollingInterval)
  if (grayscalePollTimer !== null) clearInterval(grayscalePollTimer)
  if (visibilityDebounceTimer !== null) clearTimeout(visibilityDebounceTimer)
  if (rollbackTimer !== null) clearTimeout(rollbackTimer)
  if (eventRollbackTimer !== null) clearTimeout(eventRollbackTimer)
  if (fetchAbortController) fetchAbortController.abort()
  metrics.value.forEach(m => {
    if (m.animFrameId) cancelAnimationFrame(m.animFrameId)
  })
  if (handleDataUpdate) {
    window.removeEventListener('dashboardDataUpdated', handleDataUpdate)
  }
  window.removeEventListener('assistant:execute', handleAssistantExecute)
  window.removeEventListener('assistant:fill_form', handleAssistantFillForm)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <div class="self-healing" :class="{ loading: isLoading }">
    <div class="sh-bg">
      <div class="bg-grid"></div>
      <div class="bg-glow glow-1"></div>
      <div class="bg-glow glow-2"></div>
    </div>

    <div class="sh-header">
      <div class="header-left">
        <h1 class="page-title">自愈中心</h1>
        <p class="page-subtitle">智能故障检测、根因分析、灰度验证与自动化修复</p>
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
            <button type="button" @click="exportData('json')" aria-label="导出 JSON">导出 JSON</button>
            <button type="button" @click="exportData('csv')" aria-label="导出 CSV">导出 CSV</button>
          </div>
        </div>
        <button
          type="button"
          class="action-btn refresh-btn"
          :class="{ refreshing: isRefreshing }"
          @click="manualRefresh"
          :disabled="isRefreshing"
          title="刷新数据 (Alt+R)"
          aria-label="刷新数据"
        >
          <span class="refresh-icon" :class="{ spinning: isRefreshing }">🔄</span>
          {{ isRefreshing ? '刷新中...' : '刷新' }}
        </button>
        <button type="button" v-if="canWrite" class="rollback-btn" @click="handleRollback" title="一键回滚" aria-label="一键回滚">
          <span class="rollback-icon">🔴</span>
          一键回滚
        </button>
      </div>
    </div>

    <div class="tab-selector">
      <button :class="['tab-btn', { active: activeTab === 'events' }]" @click="activeTab = 'events'">🛡️ 事件管理</button>
      <button :class="['tab-btn', { active: activeTab === 'grayscale' }]" @click="activeTab = 'grayscale'">🔬 灰度策略</button>
    </div>

    <div v-if="activeTab === 'events'">
    <div v-if="canWrite" class="mode-selector">
      <span class="mode-label">自愈模式</span>
      <div class="mode-buttons">
        <button
          type="button"
          v-for="mode in modes"
          :key="mode.value"
          :class="['mode-btn', { active: healingMode === mode.value }]"
          @click.stop="selectMode(mode.value)"
          :title="mode.desc"
          :aria-label="mode.label"
        >
          <span class="mode-btn-label">{{ mode.label }}</span>
        </button>
      </div>
      <span class="mode-desc">{{ modes.find(m => m.value === healingMode)?.desc }}</span>
    </div>

    <div v-if="isLoading" class="metrics-grid">
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

    <div class="summary-bar">
      <div class="summary-item">
        <span class="summary-icon">🛡️</span>
        <span class="summary-label">总事件</span>
        <span class="summary-value">{{ totalEvents }}</span>
      </div>
      <div class="summary-divider"></div>
      <div class="summary-item">
        <span class="summary-icon">✅</span>
        <span class="summary-label">已完成</span>
        <span class="summary-value success">{{ completedCount }}</span>
      </div>
      <div class="summary-divider"></div>
      <div class="summary-item">
        <span class="summary-icon">⏳</span>
        <span class="summary-label">待处理</span>
        <span class="summary-value warning">{{ pendingCount }}</span>
      </div>
      <div class="summary-divider"></div>
      <div class="summary-item">
        <span class="summary-icon">🔴</span>
        <span class="summary-label">高危/严重</span>
        <span class="summary-value danger">{{ criticalCount }}</span>
      </div>
      <div class="summary-divider"></div>
      <div class="summary-item">
        <span class="summary-icon">📡</span>
        <span class="summary-label">请求统计</span>
        <span class="summary-value" :class="{ warning: errorCount > 3 }">{{ fetchCount }}/{{ fetchCount + errorCount }}</span>
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
            placeholder="搜索事件ID、标题、设备..."
            aria-label="搜索自愈事件"
          />
          <button type="button" v-if="searchQuery" class="search-clear" @click="searchQuery = ''" aria-label="清除搜索">✕</button>
        </div>
        <select v-model="filterSeverity" class="filter-select" aria-label="按严重级别筛选">
          <option v-for="opt in severityOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <select v-model="filterStatus" class="filter-select" aria-label="按状态筛选">
          <option v-for="opt in statusOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <select v-model="filterType" class="filter-select" aria-label="按事件类型筛选">
          <option v-for="opt in eventTypes" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <button
          type="button"
          v-if="searchQuery || filterSeverity !== 'all' || filterStatus !== 'all' || filterType !== 'all'"
          class="clear-filter-btn"
          @click="clearFilters"
          aria-label="清除筛选"
        >
          清除筛选
        </button>
      </div>
      <div v-if="selectedEventId" class="view-selector">
        <button
          type="button"
          :class="['view-btn', { active: activeView === 'timeline' }]"
          @click="activeView = 'timeline'"
          aria-label="时间轴视图"
        >
          📅 时间轴
        </button>
        <button
          type="button"
          :class="['view-btn', { active: activeView === 'state-machine' }]"
          @click="activeView = 'state-machine'"
          aria-label="状态机视图"
        >
          🔄 状态机
        </button>
      </div>
    </div>

    <div class="events-list" v-loading="isRefreshing">
      <div v-if="healingError && isMockData" class="error-banner">
        <span class="error-banner-icon">⚠️</span>
        <span class="error-banner-text">数据加载失败: {{ healingError }}，当前显示为模拟数据</span>
        <button type="button" class="error-banner-retry" @click="manualRefresh" aria-label="重试">🔄 重试</button>
      </div>
      <div
        v-for="(event, idx) in filteredEvents"
        :key="event.id"
        :class="['event-wrapper', event.status, event.severity]"
        :style="{ '--event-delay': `${idx * 0.05}s` }"
      >
        <div class="event-summary" @click="toggleEventDetail(event.id)">
          <div class="summary-left">
            <div class="event-id">{{ event.id }}</div>
            <div class="event-info">
              <h3 class="event-title">{{ event.title }}</h3>
              <p class="event-desc">{{ event.description }}</p>
              <div class="event-meta">
                <span class="meta-item">📍 {{ event.targetDevice }}</span>
                <span class="meta-item">📅 {{ event.timeline.length }} 步骤</span>
              </div>
            </div>
          </div>
          <div class="summary-right">
            <span :class="['severity-badge', event.severity]">
              {{ getSeverityText(event.severity) }}
            </span>
            <span :class="['status-tag', event.status]">
              {{ getStatusText(event.status) }}
            </span>
            <button
              type="button"
              v-if="canWrite && event.status === 'completed'"
              class="rollback-icon-btn"
              @click.stop="handleEventRollback(event)"
              title="回滚此事件"
              aria-label="回滚此事件"
            >
              ⏪
            </button>
            <span class="expand-icon" :class="{ expanded: isExpanded(event.id) }">▼</span>
          </div>
        </div>

        <div v-if="isExpanded(event.id)" class="event-detail">
          <div v-if="activeView === 'timeline'" class="timeline-container">
            <div
              v-for="(step, index) in event.timeline"
              :key="step.id"
              :class="['timeline-item', { last: index === event.timeline.length - 1 }]"
            >
              <div class="timeline-line"></div>
              <div
                class="timeline-node"
                :style="{ backgroundColor: getStepColor(step.type, step.status) }"
              >
                <span class="node-icon">{{ getStepIcon(step.type) }}</span>
                <div v-if="step.status === 'in-progress'" class="node-pulse"></div>
              </div>
              <div class="timeline-content">
                <div class="timeline-header">
                  <span class="timeline-time">[{{ step.timestamp }}]</span>
                  <span class="timeline-title">{{ step.title }}</span>
                  <span v-if="step.agent" class="timeline-agent">by {{ step.agent }}</span>
                </div>
                <p class="timeline-desc">{{ step.description }}</p>
              </div>
            </div>
          </div>

          <div v-if="activeView === 'state-machine'" class="state-machine-container">
            <svg
              class="state-machine-svg"
              :viewBox="`0 0 800 ${event.stateMachine.nodes.length * 120 + 100}`"
            >
              <defs>
                <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                  <polygon points="0 0, 10 3.5, 0 7" fill="var(--color-text-tertiary)" class="arrow-marker" />
                </marker>
                <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
                  <feMerge>
                    <feMergeNode in="coloredBlur"/>
                    <feMergeNode in="SourceGraphic"/>
                  </feMerge>
                </filter>
              </defs>

              <g class="edges">
                <line
                  v-for="edge in event.stateMachine.edges"
                  :key="edge.id"
                  :x1="getNodePosition(edge.source, event.stateMachine.nodes).x"
                  :y1="getNodePosition(edge.source, event.stateMachine.nodes).y"
                  :x2="getNodePosition(edge.target, event.stateMachine.nodes).x"
                  :y2="getNodePosition(edge.target, event.stateMachine.nodes).y"
                  stroke="var(--color-text-tertiary)"
                  stroke-width="2"
                  stroke-dasharray="5,5"
                  marker-end="url(#arrowhead)"
                />
                <text
                  v-for="edge in event.stateMachine.edges.filter(e => e.label)"
                  :key="`label-${edge.id}`"
                  :x="(getNodePosition(edge.source, event.stateMachine.nodes).x + getNodePosition(edge.target, event.stateMachine.nodes).x) / 2"
                  :y="(getNodePosition(edge.source, event.stateMachine.nodes).y + getNodePosition(edge.target, event.stateMachine.nodes).y) / 2 - 10"
                  text-anchor="middle"
                  fill="var(--color-primary-light)"
                  font-size="12"
                >
                  {{ edge.label }}
                </text>
              </g>

              <g class="nodes">
                <g
                  v-for="node in event.stateMachine.nodes"
                  :key="node.id"
                  :transform="`translate(${getNodePosition(node.id, event.stateMachine.nodes).x - 90}, ${getNodePosition(node.id, event.stateMachine.nodes).y - 35})`"
                  @click="handleNodeClick(node)"
                  @keydown.enter.prevent="handleNodeClick(node)"
                  @keydown.space.prevent="handleNodeClick(node)"
                  class="node-group"
                  :class="{ clickable: node.status !== 'pending' && node.status !== 'skipped' }"
                  :tabindex="node.status !== 'pending' && node.status !== 'skipped' ? 0 : -1"
                  role="button"
                  :aria-label="`${node.label}，状态：${getNodeStatusText(node.status)}，点击查看详情`"
                >
                  <rect
                    width="180"
                    height="70"
                    rx="12"
                    :fill="getNodeColor(node.status)"
                    stroke="rgba(255,255,255,0.2)"
                    stroke-width="2"
                  />
                  <text x="90" y="30" text-anchor="middle" fill="white" font-size="14" font-weight="600">
                    {{ getNodeIcon(node.type) }} {{ node.label }}
                  </text>
                  <text x="90" y="52" text-anchor="middle" :fill="node.status === 'active' ? 'var(--color-orange)' : 'var(--color-text-tertiary)'" font-size="11">
                    {{ node.status === 'completed' ? '✅ 已完成' : node.status === 'active' ? '⏳ 执行中...' : node.status === 'skipped' ? '⏭️ 已跳过' : '📋 等待中' }}
                  </text>
                  <circle
                    v-if="node.status === 'active'"
                    cx="90" cy="35" r="40"
                    fill="none"
                    :stroke="getNodeColor(node.status)"
                    stroke-width="2"
                    opacity="0.3"
                    class="pulse-ring"
                  />
                </g>
              </g>
            </svg>
          </div>

          <div v-if="canWrite && event.status === 'pending'" class="action-buttons">
            <button type="button" class="action-btn primary" @click="executeAction(event)" aria-label="执行建议">
              执行建议
            </button>
            <button type="button" class="action-btn secondary" @click="rejectAction(event)" aria-label="拒绝">
              拒绝
            </button>
          </div>
          <div v-if="canWrite && event.status === 'completed'" class="action-buttons">
            <button type="button" class="upgrade-btn" @click="upgradeToGrayscale(event)" aria-label="升级为灰度">
              🔬 升级为灰度
            </button>
          </div>
        </div>
      </div>

      <div v-if="filteredEvents.length === 0 && !isLoading" class="empty-state">
        <div class="empty-icon">📭</div>
        <div class="empty-text">
          {{ searchQuery || filterSeverity !== 'all' || filterStatus !== 'all' || filterType !== 'all'
            ? '没有匹配的事件，请调整筛选条件' : '暂无自愈事件' }}
        </div>
        <button
          type="button"
          v-if="searchQuery || filterSeverity !== 'all' || filterStatus !== 'all' || filterType !== 'all'"
          class="clear-filter-btn"
          @click="clearFilters"
          aria-label="清除筛选"
        >
          清除筛选
        </button>
      </div>
    </div>

    <div v-if="totalPages > 1" class="pagination">
      <button type="button" class="page-btn" :disabled="currentPage <= 1" @click="goToPage(currentPage - 1)" aria-label="上一页">上一页</button>
      <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
      <button type="button" class="page-btn" :disabled="currentPage >= totalPages" @click="goToPage(currentPage + 1)" aria-label="下一页">下一页</button>
    </div>
    </div>

    <div v-if="activeTab === 'grayscale'">
      <div class="grayscale-header-actions">
        <el-button v-if="canWrite" type="primary" @click="showCreateDialog = true">🛡️ 创建任务</el-button>
        <el-button :loading="isRefreshing" @click="fetchGrayscaleTasks(true)">🔄 刷新</el-button>
      </div>

      <div class="content-section">
        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">灰度自愈任务</h2>
          </div>
          <el-table :data="grayscaleTasks" style="width: 100%" class="dark-table" v-loading="isLoading">
            <el-table-column prop="task_id" label="任务ID" width="130" />
            <el-table-column prop="event_id" label="事件ID" width="120" />
            <el-table-column prop="canary_device" label="金丝雀设备" width="140" />
            <el-table-column label="金丝雀状态" width="130">
              <template #default="{ row }">
                <el-tag :type="getCanaryStatusType(row.canary_status)" size="small">
                  {{ getCanaryStatusText(row.canary_status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="批量进度" width="180">
              <template #default="{ row }">
                <el-progress :percentage="row.batch_progress" :stroke-width="8" />
              </template>
            </el-table-column>
            <el-table-column label="整体状态" width="140">
              <template #default="{ row }">
                <el-tag :type="getGrayscaleStatusType(row.overall_status)" size="small">
                  {{ getGrayscaleStatusText(row.overall_status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_by" label="创建人" width="100" />
            <el-table-column label="操作" min-width="280">
              <template #default="{ row }">
                <div class="action-group">
                  <el-button v-if="canWrite" size="small" type="warning" @click="executeCanary(row)" :disabled="!['canary_pending','pending'].includes(row.overall_status)">金丝雀</el-button>
                  <el-button v-if="canWrite" size="small" type="primary" @click="executeBatch(row)" :disabled="row.canary_status !== 'success'">批量</el-button>
                  <el-button v-if="canWrite" size="small" type="danger" @click="executeGrayscaleRollback(row)" :disabled="row.overall_status === 'rolled_back'">回滚</el-button>
                  <el-button v-if="canWrite" size="small" @click="analyzeRootCause(row)">根因分析</el-button>
                  <el-button size="small" link type="primary" @click="openDetail(row)">详情</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <div class="content-section">
        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">自愈评估</h2>
          </div>
          <el-table :data="grayscaleEvaluations" style="width: 100%" class="dark-table">
            <el-table-column prop="evaluation_id" label="评估ID" width="130" />
            <el-table-column prop="task_id" label="关联任务" width="130" />
            <el-table-column label="有效性评分" width="160">
              <template #default="{ row }">
                <div class="score-cell">
                  <el-progress type="circle" :percentage="row.effectiveness_score != null ? Math.round(row.effectiveness_score * 100) : 0" :width="40" :stroke-width="4" />
                  <span class="score-text">{{ row.effectiveness_score != null ? Math.round(row.effectiveness_score * 100) + '分' : '待评估' }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="自愈动作" min-width="160">
              <template #default="{ row }">
                <span class="metrics-text">{{ row.healing_action || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="根因分析" min-width="200">
              <template #default="{ row }">
                <span class="metrics-text">{{ row.root_cause_analysis || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="建议" min-width="200">
              <template #default="{ row }">
                <span class="metrics-text">{{ row.recommendation || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="评估时间" width="180">
              <template #default="{ row }">
                {{ formatGrayscaleTime(row.evaluated_at || row.created_at) }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <el-dialog v-model="showCreateDialog" title="创建灰度自愈任务" width="520px" class="dark-dialog" :close-on-click-modal="false">
        <el-form label-position="top" class="dark-form">
          <el-form-item label="关联事件" required>
            <el-select v-model="createForm.event_id" placeholder="选择事件" style="width: 100%">
              <el-option v-for="evt in availableEvents" :key="evt.id" :label="`${evt.id} - ${evt.description || evt.event_type}`" :value="String(evt.id)" />
            </el-select>
          </el-form-item>
          <el-form-item label="目标设备" required>
            <el-select v-model="createForm.target_devices" multiple placeholder="选择目标设备" style="width: 100%">
              <el-option v-for="dev in availableDevices" :key="dev" :label="dev" :value="dev" />
            </el-select>
          </el-form-item>
          <el-form-item label="金丝雀设备" required>
            <el-select v-model="createForm.canary_device" placeholder="选择金丝雀设备" style="width: 100%">
              <el-option v-for="dev in availableDevices" :key="dev" :label="dev" :value="dev" />
            </el-select>
          </el-form-item>
          <el-form-item label="创建人">
            <el-input v-model="createForm.created_by" placeholder="输入创建人" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" :loading="isSubmitting" @click="submitCreateTask">创建</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="showDetailDialog" title="任务详情" width="640px" class="dark-dialog">
        <div v-if="selectedTask" class="detail-content">
          <div class="detail-row">
            <span class="detail-label">任务ID</span>
            <span class="detail-value">{{ selectedTask.task_id }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">事件ID</span>
            <span class="detail-value">{{ selectedTask.event_id }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">金丝雀设备</span>
            <span class="detail-value">{{ selectedTask.canary_device }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">金丝雀状态</span>
            <el-tag :type="getCanaryStatusType(selectedTask.canary_status)" size="small">{{ getCanaryStatusText(selectedTask.canary_status) }}</el-tag>
          </div>
          <div class="detail-row">
            <span class="detail-label">批量进度</span>
            <el-progress :percentage="selectedTask.batch_progress" :stroke-width="10" style="flex: 1" />
          </div>
          <div class="detail-row">
            <span class="detail-label">整体状态</span>
            <el-tag :type="getGrayscaleStatusType(selectedTask.overall_status)" size="small">{{ getGrayscaleStatusText(selectedTask.overall_status) }}</el-tag>
          </div>
          <div class="detail-row">
            <span class="detail-label">回滚状态</span>
            <span class="detail-value">{{ selectedTask.rollback_triggered ? '已回滚' : '未回滚' }}{{ selectedTask.rollback_reason ? ' - ' + selectedTask.rollback_reason : '' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">创建人</span>
            <span class="detail-value">{{ selectedTask.created_by }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">创建时间</span>
            <span class="detail-value">{{ formatGrayscaleTime(selectedTask.created_at) }}</span>
          </div>
          <div v-if="selectedTask.canary_result" class="detail-section">
            <h4 class="section-title">金丝雀阶段结果</h4>
            <pre class="detail-json">{{ JSON.stringify(selectedTask.canary_result, null, 2) }}</pre>
          </div>
        </div>
      </el-dialog>
    </div>

    <Teleport to="body">
      <div v-if="showRollbackModal" class="modal-overlay" @click.self="cancelRollback" role="dialog" aria-modal="true" aria-labelledby="rollback-modal-title">
        <div class="modal-content">
          <h3 id="rollback-modal-title" class="modal-title">⚠️ 确认全局回滚</h3>
          <p class="modal-text">确定要执行全局一键回滚吗？这将撤销所有最近的配置变更。</p>
          <div v-if="rollbackSuccess" class="success-message">✅ {{ rollbackMessage }}</div>
          <div class="modal-actions">
            <button type="button" class="modal-btn cancel" @click="cancelRollback" aria-label="取消">取消</button>
            <button type="button" class="modal-btn confirm" @click="confirmRollback" aria-label="确认回滚">确认回滚</button>
          </div>
        </div>
      </div>

      <div v-if="showEventRollbackModal" class="modal-overlay" @click.self="showEventRollbackModal = false" role="dialog" aria-modal="true" aria-labelledby="event-rollback-modal-title">
        <div class="modal-content">
          <h3 id="event-rollback-modal-title" class="modal-title">⏪ 确认回滚事件</h3>
          <p class="modal-text">确定要回滚事件 <strong>{{ eventRollbackTarget?.id }}</strong> 吗？</p>
          <div v-if="eventRollbackSuccess" class="success-message">✅ {{ eventRollbackMessage }}</div>
          <div class="modal-actions">
            <button type="button" class="modal-btn cancel" @click="showEventRollbackModal = false" aria-label="取消">取消</button>
            <button type="button" class="modal-btn confirm" @click="confirmEventRollback" aria-label="确认回滚">确认回滚</button>
          </div>
        </div>
      </div>

      <div v-if="showStateDetailModal && selectedStateMachineNode" class="modal-overlay" @click.self="showStateDetailModal = false" role="dialog" aria-modal="true" aria-labelledby="state-detail-modal-title">
        <div class="modal-content state-detail-modal">
          <div class="modal-header">
            <h3 id="state-detail-modal-title" class="modal-title">
              {{ getNodeIcon(selectedStateMachineNode.type) }} {{ selectedStateMachineNode.label }}
            </h3>
            <button type="button" class="modal-close" @click="showStateDetailModal = false" aria-label="关闭">✕</button>
          </div>

          <div class="state-detail-content">
            <div v-if="selectedStateMachineNode.agentName" class="detail-section">
              <h4 class="detail-title">🤖 Agent名称</h4>
              <p class="detail-value">{{ selectedStateMachineNode.agentName }}</p>
            </div>
            <div v-if="selectedStateMachineNode.timestamp" class="detail-section">
              <h4 class="detail-title">🕐 执行时间</h4>
              <p class="detail-value">{{ selectedStateMachineNode.timestamp }}</p>
            </div>
            <div v-if="selectedStateMachineNode.reasoning" class="detail-section">
              <h4 class="detail-title">💭 推理过程</h4>
              <p class="detail-value detail-text">{{ selectedStateMachineNode.reasoning }}</p>
            </div>
            <div v-if="selectedStateMachineNode.input" class="detail-section">
              <h4 class="detail-title">📥 输入数据</h4>
              <pre class="detail-json">{{ JSON.stringify(selectedStateMachineNode.input, null, 2) }}</pre>
            </div>
            <div v-if="selectedStateMachineNode.output" class="detail-section">
              <h4 class="detail-title">📤 输出结果</h4>
              <pre class="detail-json">{{ JSON.stringify(selectedStateMachineNode.output, null, 2) }}</pre>
            </div>
          </div>

          <div class="modal-actions">
            <button type="button" class="modal-btn primary" @click="showStateDetailModal = false" aria-label="关闭">关闭</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showRejectModal" class="modal-overlay" @click.self="showRejectModal = false">
        <div class="modal-content reject-modal">
          <h3 class="modal-title">拒绝自愈方案</h3>
          <p class="reject-modal-desc">事件: {{ rejectTargetEvent?.title || rejectTargetEvent?.id }} | 设备: {{ rejectTargetEvent?.targetDevice }}</p>
          <textarea v-model="rejectReasonInput" placeholder="请输入拒绝原因（可选）" rows="3" class="reject-modal-textarea"></textarea>
          <div class="modal-actions reject-modal-actions">
            <button type="button" class="modal-btn" @click="showRejectModal = false" aria-label="取消">取消</button>
            <button type="button" class="modal-btn primary reject-confirm-btn" @click="confirmReject" aria-label="确认拒绝">确认拒绝</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showExecuteConfirm" class="modal-overlay" @click.self="showExecuteConfirm = false" role="dialog" aria-modal="true">
        <div class="confirm-modal">
          <h3 class="confirm-title">⚠️ 确认执行自愈方案？</h3>
          <p class="confirm-desc">事件: {{ executeTargetEvent?.title || executeTargetEvent?.id }}<br/>设备: {{ executeTargetEvent?.targetDevice }}<br/><br/>此操作将自动修复检测到的网络问题。</p>
          <div class="confirm-actions">
            <button type="button" class="confirm-btn cancel" @click="showExecuteConfirm = false" aria-label="取消">取消</button>
            <button type="button" class="confirm-btn danger" @click="doExecuteAction" aria-label="确认执行">确认执行</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.self-healing {
  position: relative;
  animation: page-enter 0.5s ease-out;
  will-change: opacity, transform;
  min-height: 100vh;
  padding: var(--content-padding);
}

.sh-bg {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 0;
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
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
}

.glow-1 {
  width: 400px;
  height: 400px;
  background: rgba(22, 93, 255, 0.08);
  top: -100px;
  right: 10%;
  animation: glow-float 12s ease-in-out infinite;
  will-change: transform;
}

.glow-2 {
  width: 300px;
  height: 300px;
  background: rgba(255, 125, 0, 0.06);
  bottom: 10%;
  left: 5%;
  animation: glow-float 15s ease-in-out infinite reverse;
  will-change: transform;
}

/* glow-float uses global definition from tokens.css */

/* page-enter uses global definition from tokens.css */

.self-healing > *:not(.sh-bg) {
  position: relative;
  z-index: 1;
}

.sh-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-border-primary);
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.page-title {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  margin: 0;
  background: linear-gradient(135deg, var(--color-text-secondary) 0%, var(--color-orange) 50%, var(--color-text-secondary) 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: title-shimmer 4s ease-in-out infinite;
}

.page-subtitle {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin: 0;
  font-weight: 400;
}

/* title-shimmer uses global definition from tokens.css */

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.data-freshness {
  font-size: var(--font-size-xs);
  padding: var(--spacing-xs) 10px;
  border-radius: var(--radius-lg);
  background: var(--color-success-bg);
  color: var(--color-success);
  transition: all 0.3s ease;
  border: 1px solid var(--color-success-border);
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.freshness-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: freshness-pulse 2s ease-in-out infinite;
}

/* freshness-pulse uses global definition from tokens.css */

.data-freshness.degraded {
  background: var(--color-warning-bg);
  color: var(--color-warning);
  border-color: var(--color-warning-border);
}

.last-refresh {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

/* .action-btn uses global definition from tokens.css */

.refresh-icon {
  display: inline-block;
  transition: transform 0.3s ease;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

/* spin uses global definition from tokens.css */

.rollback-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 0.375rem 14px;
  background: var(--color-error-bg);
  color: var(--color-error-light);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  font-weight: 600;
  cursor: pointer;
  transition: var(--button-transition);
  backdrop-filter: blur(8px);
  min-height: 44px;
}

.rollback-btn:hover {
  background: var(--color-error-hover);
  border-color: rgba(239, 68, 68, 0.5);
  box-shadow: var(--shadow-glow-error);
  transform: translateY(-1px);
}

.rollback-icon {
  font-size: var(--font-size-base);
  animation: pulse 2s ease-in-out infinite;
}

/* pulse uses global pulse-dot definition from tokens.css */

.export-wrapper {
  position: relative;
}

.export-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: var(--spacing-xs);
  background: rgba(20, 30, 48, 0.95);
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--radius-md);
  overflow: hidden;
  z-index: var(--z-dropdown);
  min-width: 140px;
  backdrop-filter: blur(16px);
  box-shadow: var(--shadow-card);
  animation: dropdown-enter 0.15s ease-out;
}

/* dropdown-enter uses global definition from tokens.css */

.export-dropdown button {
  display: block;
  width: 100%;
  padding: 10px var(--spacing-md);
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
  padding-left: 1.25rem;
}

.mode-selector {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md) 1.25rem;
  background: var(--gradient-glass);
  border-radius: var(--radius-xl);
  border: var(--card-border);
  backdrop-filter: blur(12px);
}

.mode-label {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.mode-buttons {
  display: flex;
  gap: var(--spacing-sm);
}

.mode-btn {
  padding: var(--spacing-sm) 1.25rem;
  background: var(--input-bg);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  transition: var(--button-transition);
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  min-height: 44px;
}

.mode-btn:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-color: var(--color-primary-border);
}

.mode-btn.active {
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  border-color: var(--color-primary);
  box-shadow: var(--shadow-glow-primary);
}

.mode-btn:active {
  transform: scale(0.98);
}

.mode-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-left: auto;
}

.skeleton {
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-line {
  height: 14px;
  background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 75%);
  background-size: 200% 100%;
  border-radius: var(--radius-sm);
  margin-bottom: 10px;
  animation: skeleton-slide 1.5s ease-in-out infinite;
}

/* skeleton-slide uses global definition from tokens.css */

.skeleton-line.wide { width: 70%; }
.skeleton-line.narrow { width: 40%; }

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(var(--grid-min-col), 1fr));
  gap: var(--panel-gap);
  margin-bottom: 1.25rem;
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
}

/* card-enter uses global definition from tokens.css */

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
  box-shadow: var(--shadow-card-hover);
  border-color: var(--color-border-secondary);
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
}

.metric-card:hover .metric-icon {
  transform: scale(1.08);
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
  border-radius: 0 2px 0 0;
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

.summary-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: 0.75rem var(--spacing-lg);
  background: linear-gradient(135deg, rgba(255, 125, 0, 0.06) 0%, rgba(30, 41, 59, 0.5) 50%, rgba(22, 93, 255, 0.04) 100%);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-primary);
  margin-bottom: 1.25rem;
  flex-wrap: wrap;
  backdrop-filter: blur(8px);
  animation: bar-enter 0.5s ease-out 0.25s backwards;
}

/* bar-enter uses global definition from tokens.css */

.summary-item {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  cursor: default;
  padding: 2px var(--spacing-xs);
  border-radius: var(--radius-sm);
  transition: background 0.2s ease;
}

.summary-item:hover {
  background: var(--color-bg-hover);
}

.summary-icon {
  font-size: var(--font-size-base);
  transition: transform 0.3s ease;
}

.summary-item:hover .summary-icon {
  transform: scale(1.2);
}

.summary-label { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }

.summary-value {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.summary-value.success { color: var(--color-success); }
.summary-value.warning { color: var(--color-warning); }
.summary-value.danger { color: var(--color-error-light); }

.summary-divider {
  width: 1px;
  height: 20px;
  background: linear-gradient(180deg, transparent, rgba(255,255,255,0.12), transparent);
}

.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: 1.25rem;
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
  padding: var(--spacing-sm) var(--spacing-xl) var(--spacing-sm) var(--spacing-xl);
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-secondary);
  font-size: var(--font-size-base);
  width: 220px;
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

.filter-select {
  padding: var(--spacing-sm) 0.75rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-secondary);
  font-size: var(--font-size-base);
  cursor: pointer;
  transition: all 0.25s var(--ease-out);
  outline: none;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2394A3B8' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  padding-right: 28px;
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
  padding: 0.375rem 0.75rem;
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-sm);
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

.view-selector {
  display: flex;
  gap: var(--spacing-sm);
}

.view-btn {
  padding: 0.375rem 14px;
  background: var(--input-bg);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  font-weight: 500;
  cursor: pointer;
  transition: var(--button-transition);
  white-space: nowrap;
}

.view-btn:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-color: var(--color-primary-border);
}

.view-btn.active {
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  border-color: var(--color-primary);
  box-shadow: var(--shadow-glow-primary);
}

.events-list {
  display: flex;
  flex-direction: column;
  gap: var(--panel-gap);
}

.error-banner { display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem 1.25rem; background: var(--color-error-bg); border: 1px solid var(--color-error-border); border-radius: var(--radius-xl); margin-bottom: 1.25rem; animation: banner-enter 0.3s ease-out; }
/* banner-enter uses global definition from tokens.css */
.error-banner-icon { font-size: var(--font-size-lg); flex-shrink: 0; }
.error-banner-text { flex: 1; font-size: var(--font-size-sm); color: var(--color-error-light); }
.error-banner-retry { padding: 0.375rem 0.875rem; background: var(--color-error-glow); color: var(--color-error-light); border: 1px solid rgba(255, 77, 79, 0.3); border-radius: var(--radius-md); font-size: var(--font-size-xs); cursor: pointer; transition: all 0.2s ease; white-space: nowrap; min-height: 36px; }
.error-banner-retry:hover { background: var(--color-error-hover); }

.event-wrapper {
  background: var(--gradient-glass);
  border-radius: var(--radius-xl);
  border: var(--card-border);
  overflow: hidden;
  transition: all 0.35s var(--ease-out);
  backdrop-filter: blur(12px);
  animation: event-enter 0.35s var(--ease-out) backwards;
  animation-delay: var(--event-delay, 0s);
  box-shadow: var(--shadow-card);
}

/* event-enter uses global item-enter definition from tokens.css */

.event-wrapper:hover {
  border-color: var(--color-border-secondary);
  box-shadow: var(--shadow-card-hover);
}

.event-wrapper.completed {
  opacity: 0.85;
}

.event-wrapper.rejected {
  opacity: 0.7;
  border-color: var(--color-error-border);
}

.event-wrapper.high,
.event-wrapper.critical {
  border-left: 4px solid var(--color-error);
}

.event-wrapper.medium {
  border-left: 4px solid var(--color-warning);
}

.event-wrapper.low {
  border-left: 4px solid var(--color-success);
}

.event-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 1.25rem;
  cursor: pointer;
  transition: background 0.2s ease;
}

.event-summary:hover {
  background: var(--color-bg-hover);
}

.summary-left {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  flex: 1;
  min-width: 0;
}

.event-id {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-text-tertiary);
  background: rgba(100, 116, 139, 0.1);
  padding: var(--spacing-xs) 10px;
  border-radius: var(--radius-sm);
  white-space: nowrap;
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.event-info {
  flex: 1;
  min-width: 0;
}

.event-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-xs);
}

.event-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  line-height: 1.5;
  margin-bottom: 0.375rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-meta {
  display: flex;
  gap: 0.75rem;
}

.meta-item {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.summary-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.severity-badge {
  font-size: 0.6875rem;
  padding: 3px 10px;
  border-radius: var(--radius-md);
  font-weight: 500;
  white-space: nowrap;
}

.severity-badge.critical { background: var(--color-error-border); color: var(--color-error-light); }
.severity-badge.high { background: rgba(239, 68, 68, 0.2); color: var(--color-error); }
.severity-badge.medium { background: rgba(245, 158, 11, 0.2); color: var(--color-warning); }
.severity-badge.low { background: var(--color-success-border); color: var(--color-success); }

.status-tag {
  font-size: 0.6875rem;
  padding: 3px 10px;
  border-radius: var(--radius-md);
  font-weight: 500;
  white-space: nowrap;
}

.status-tag.completed { background: var(--color-success-border); color: var(--color-success); }
.status-tag.pending { background: rgba(255, 125, 0, 0.2); color: var(--color-orange); }
.status-tag.rejected { background: rgba(239, 68, 68, 0.2); color: var(--color-error); }
.status-tag.rolled-back { background: rgba(100, 116, 139, 0.2); color: var(--color-text-tertiary); }

.rollback-icon-btn {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  cursor: pointer;
  transition: all 0.3s ease;
  opacity: 0.7;
}

.rollback-icon-btn:hover {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.5);
  opacity: 1;
  transform: scale(1.05);
}

.expand-icon {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  transition: transform 0.3s ease;
}

.expand-icon.expanded {
  transform: rotate(180deg);
}

.event-detail {
  border-top: 1px solid var(--color-bg-active);
  padding: 1.25rem;
  background: rgba(15, 23, 42, 0.3);
}

.timeline-container {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.timeline-item {
  display: flex;
  gap: 14px;
  position: relative;
}

.timeline-item:not(.last) {
  padding-bottom: 22px;
}

.timeline-line {
  width: 2px;
  background: rgba(100, 116, 139, 0.2);
  position: absolute;
  left: 15px;
  top: 32px;
  bottom: 0;
}

.timeline-item.last .timeline-line {
  display: none;
}

.timeline-node {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
  box-shadow: var(--shadow-card-hover);
}

.node-icon {
  font-size: var(--font-size-md);
}

.node-pulse {
  position: absolute;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: inherit;
  animation: nodePulse 2s ease-out infinite;
  opacity: 0.6;
}

/* nodePulse uses global pulse-dot definition from tokens.css */

.timeline-content {
  flex: 1;
  padding-top: var(--spacing-xs);
}

.timeline-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: var(--spacing-xs);
  flex-wrap: wrap;
}

.timeline-time {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-tertiary);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.timeline-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.timeline-agent {
  font-size: 0.6875rem;
  color: var(--color-primary-light);
  background: rgba(105, 177, 255, 0.1);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-sm);
}

.timeline-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  line-height: 1.5;
  margin: 0;
}

.action-buttons {
  display: flex;
  gap: 0.75rem;
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--color-bg-active);
}

.action-btn.primary {
  flex: 1;
  padding: 0.75rem;
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: 600;
  cursor: pointer;
  transition: var(--button-transition);
}

.action-btn.primary:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-glow-primary);
}

.action-btn.secondary {
  flex: 1;
  padding: 0.75rem;
  background: var(--input-bg);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: 600;
  cursor: pointer;
  transition: var(--button-transition);
}

.action-btn.secondary:hover {
  background: var(--color-bg-active);
  color: var(--color-text-primary);
  border-color: var(--color-border-hover);
}

.state-machine-container {
  overflow-x: auto;
  padding: 1.25rem;
  background: rgba(15, 23, 42, 0.4);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-primary);
  transition: all 0.3s ease;
}

.state-machine-container:hover {
  border-color: var(--color-primary-hover);
  box-shadow: var(--shadow-glow-primary-sm);
}

.state-machine-svg {
  width: 100%;
  height: auto;
}

.state-machine-svg .edges line {
  transition: stroke 0.35s ease, stroke-width 0.35s ease;
}

.state-machine-svg .edges line:hover {
  stroke: var(--color-primary);
  stroke-width: 3;
  filter: url(#glow);
}

.node-group {
  cursor: default;
  transition: opacity 0.3s ease;
}

.node-group.clickable {
  cursor: pointer;
}

.node-group.clickable:hover {
  opacity: 0.9;
}

.node-group.clickable:hover rect {
  filter: brightness(1.08);
}

.node-group.clickable:focus {
  outline: 2px solid var(--color-primary);
  outline-offset: 4px;
  border-radius: var(--radius-lg);
}

.node-group rect {
  transition: fill 0.35s ease, filter 0.35s ease;
}

.pulse-ring {
  animation: pulseRing 3s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

/* pulseRing uses global definition from tokens.css */

.empty-state {
  text-align: center;
  padding: 48px var(--spacing-lg);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.4) 0%, rgba(20, 30, 48, 0.3) 100%);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-primary);
}

.empty-icon {
  font-size: var(--font-size-4xl);
  margin-bottom: 0.75rem;
  opacity: 0.6;
}

.empty-text {
  margin-bottom: 0.75rem;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--spacing-md);
  margin-top: var(--spacing-lg);
  padding: 0.75rem;
}

.page-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: var(--button-transition);
}

.page-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: rgba(22, 93, 255, 0.5);
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--modal-overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-overlay);
  animation: fadeIn 0.2s var(--ease-out);
  backdrop-filter: blur(var(--modal-backdrop-blur));
}

/* fadeIn uses global fade-in definition from tokens.css */

.modal-content {
  background: var(--color-bg-elevated);
  border-radius: var(--modal-border-radius);
  padding: var(--modal-padding);
  width: 90%;
  max-width: 400px;
  border: 1px solid var(--color-border-primary);
  box-shadow: var(--shadow-modal);
}

.modal-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 0.75rem;
}

.modal-text {
  font-size: var(--font-size-base);
  color: var(--color-text-tertiary);
  margin-bottom: 1.25rem;
  line-height: 1.6;
}

.success-message {
  background: var(--color-success-bg);
  color: var(--color-success);
  padding: 0.75rem;
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-md);
  text-align: center;
  border: 1px solid var(--color-success-border);
}

.modal-actions {
  display: flex;
  gap: 0.75rem;
}

.modal-btn {
  flex: 1;
  padding: 0.75rem;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
}

.modal-btn.cancel {
  background: var(--input-bg);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-primary);
}

.modal-btn.cancel:hover {
  background: var(--color-bg-active);
  color: var(--color-text-primary);
}

.modal-btn.confirm {
  background: var(--gradient-danger);
  color: var(--color-text-primary);
}

.modal-btn.confirm:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-glow-error);
}

.modal-btn.primary {
  background: var(--gradient-primary);
  color: var(--color-text-primary);
}

.modal-btn.primary:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-glow-primary);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.25rem;
}

.modal-close {
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-2xl);
  cursor: pointer;
  padding: var(--spacing-xs);
  line-height: 1;
  transition: color 0.2s ease;
}

.modal-close:hover {
  color: var(--color-text-primary);
}

.state-detail-modal {
  max-width: 600px;
  max-height: 80vh;
  overflow-y: auto;
}

.state-detail-content {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-section {
  background: rgba(15, 23, 42, 0.6);
  border-radius: var(--radius-md);
  padding: 14px;
  border: 1px solid var(--color-border-primary);
}

.detail-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-primary-light);
  margin-bottom: var(--spacing-sm);
}

.detail-value {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  margin: 0;
}

.detail-text {
  color: var(--color-text-tertiary);
  line-height: 1.6;
}

.detail-json {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  background: rgba(0, 0, 0, 0.3);
  padding: 0.75rem;
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin: 0;
  line-height: 1.5;
}

@media (max-width: 1200px) {
  .metrics-grid {
    grid-template-columns: repeat(auto-fit, minmax(var(--grid-min-col), 1fr));
  }
}

@media (max-width: 768px) {
  .self-healing {
    padding: var(--spacing-md);
  }

  .sh-header {
    flex-direction: column;
    gap: 0.75rem;
    align-items: flex-start;
  }

  .header-actions {
    flex-wrap: wrap;
    width: 100%;
  }

  .page-title {
    font-size: var(--font-size-xl);
  }

  .page-subtitle {
    font-size: var(--font-size-base);
  }

  .metrics-grid {
    grid-template-columns: 1fr 1fr;
  }

  .metric-label {
    font-size: var(--font-size-base);
  }

  .summary-bar {
    gap: 10px;
    padding: 10px var(--spacing-md);
  }

  .summary-divider {
    display: none;
  }

  .mode-selector {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
    padding: 0.75rem var(--spacing-md);
  }

  .mode-buttons {
    width: 100%;
  }

  .mode-btn {
    flex: 1;
    min-height: var(--button-min-height-touch);
    padding: 10px var(--spacing-md);
    font-size: var(--font-size-base);
  }

  .mode-desc {
    margin-left: 0;
    font-size: var(--font-size-base);
  }

  .filter-bar {
    flex-direction: column;
    align-items: stretch;
    padding: 0.75rem 14px;
  }

  .filter-left {
    flex-direction: column;
  }

  .search-input {
    width: 100%;
    font-size: var(--font-size-md);
    min-height: var(--button-min-height-touch);
  }

  .filter-select {
    min-height: var(--button-min-height-touch);
    font-size: var(--font-size-md);
    width: 100%;
  }

  .clear-filter-btn {
    min-height: var(--button-min-height-touch);
    padding: var(--spacing-sm) var(--spacing-md);
    font-size: var(--font-size-base);
  }

  .view-selector {
    width: 100%;
  }

  .view-btn {
    flex: 1;
    min-height: var(--button-min-height-touch);
    padding: var(--spacing-sm) 14px;
    font-size: var(--font-size-base);
  }

  .event-summary {
    flex-direction: column;
    gap: 0.75rem;
    padding: 14px var(--spacing-md);
  }

  .summary-right {
    flex-wrap: wrap;
    width: 100%;
    justify-content: flex-start;
  }

  .event-title {
    font-size: var(--font-size-md);
  }

  .event-desc {
    font-size: var(--font-size-base);
  }

  .rollback-icon-btn {
    min-width: 44px;
    min-height: var(--button-min-height-touch);
  }

  .expand-icon {
    min-width: 44px;
    min-height: var(--button-min-height-touch);
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .event-detail {
    padding: var(--spacing-md);
  }

  .timeline-item {
    gap: 10px;
  }

  .timeline-item:not(.last) {
    padding-bottom: 18px;
  }

  .timeline-line {
    left: 15px;
    top: 34px;
  }

  .timeline-node {
    width: 32px;
    height: 32px;
    flex-shrink: 0;
  }

  .timeline-title {
    font-size: var(--font-size-md);
  }

  .timeline-desc {
    font-size: var(--font-size-base);
  }

  .timeline-header {
    gap: 0.375rem;
  }

  .timeline-time {
    font-size: var(--font-size-xs);
  }

  .timeline-agent {
    font-size: 0.6875rem;
  }

  .state-machine-container {
    padding: 0.75rem;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .action-btn {
    min-height: var(--button-min-height-touch);
    padding: 10px var(--spacing-md);
    font-size: var(--font-size-base);
  }

  .action-btn.primary,
  .action-btn.secondary {
    min-height: var(--button-min-height-touch);
    padding: 0.75rem;
    font-size: var(--font-size-base);
  }

  .rollback-btn {
    min-height: var(--button-min-height-touch);
    padding: 10px var(--spacing-md);
    font-size: var(--font-size-base);
  }

  .page-btn {
    min-height: var(--button-min-height-touch);
    padding: 10px 1.25rem;
  }

  .modal-btn {
    min-height: var(--button-min-height-touch);
  }

  .modal-content {
    width: 94%;
    padding: 1.25rem;
  }
}

@media (max-width: 480px) {
  .self-healing {
    padding: var(--spacing-sm);
  }

  .page-title {
    font-size: var(--font-size-lg);
  }

  .page-subtitle {
    font-size: var(--font-size-sm);
  }

  .metrics-grid {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .metric-card {
    padding: 0.75rem;
  }

  .metric-value {
    font-size: var(--font-size-xl);
  }

  .metric-label {
    font-size: var(--font-size-sm);
  }

  .summary-bar {
    padding: var(--spacing-sm) 0.75rem;
    gap: 0.375rem;
  }

  .summary-item {
    padding: 2px;
  }

  .summary-label {
    font-size: var(--font-size-xs);
  }

  .summary-value {
    font-size: var(--font-size-sm);
  }

  .mode-selector {
    padding: 10px 0.75rem;
  }

  .mode-btn {
    padding: var(--spacing-sm) 0.75rem;
    font-size: var(--font-size-sm);
  }

  .filter-bar {
    padding: 10px 0.75rem;
  }

  .search-input {
    font-size: var(--font-size-md);
    padding: var(--spacing-sm) 28px var(--spacing-sm) 30px;
  }

  .filter-select {
    font-size: var(--font-size-md);
    padding: var(--spacing-sm) 28px var(--spacing-sm) 10px;
  }

  .event-summary {
    padding: 10px 0.75rem;
  }

  .event-title {
    font-size: var(--font-size-md);
  }

  .event-desc {
    font-size: var(--font-size-sm);
  }

  .event-detail {
    padding: 0.75rem;
  }

  .timeline-item:not(.last) {
    padding-bottom: 14px;
  }

  .timeline-title {
    font-size: var(--font-size-base);
  }

  .timeline-desc {
    font-size: var(--font-size-sm);
  }

  .state-machine-container {
    padding: var(--spacing-sm);
  }

  .state-machine-container::before,
  .state-machine-container::after {
    display: none;
  }

  .action-buttons {
    gap: var(--spacing-sm);
    margin-top: 14px;
    padding-top: 14px;
  }

  .action-btn.primary,
  .action-btn.secondary {
    padding: 10px;
    font-size: var(--font-size-sm);
  }

  .modal-content {
    padding: var(--spacing-md);
    width: 96%;
  }

  .modal-title {
    font-size: var(--font-size-md);
  }

  .modal-text {
    font-size: var(--font-size-sm);
  }

  .empty-state {
    padding: var(--spacing-xl) var(--spacing-md);
  }

  .pagination {
    padding: var(--spacing-sm);
  }
}

@media (prefers-reduced-motion: reduce) {
  .self-healing,
  .metric-card,
  .event-wrapper,
  .summary-bar,
  .bg-glow,
  .freshness-dot,
  .node-pulse,
  .pulse-ring,
  .rollback-icon,
  .refresh-icon.spinning,
  .skeleton,
  .skeleton-line,
  .page-title,
  .metric-bottom-fill,
  .expand-icon,
  .export-dropdown,
  .modal-overlay {
    animation: none !important;
    transition: none !important;
  }
}

.tab-selector {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-lg);
}
.tab-btn {
  padding: var(--spacing-sm) 1.25rem;
  background: var(--input-bg);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  transition: var(--button-transition);
  min-height: 44px;
}
.tab-btn:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-color: var(--color-primary-border);
}
.tab-btn.active {
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  border-color: var(--color-primary);
  box-shadow: var(--shadow-glow-primary);
}

.content-section {
  margin-bottom: var(--spacing-lg);
}
.panel {
  background: var(--gradient-glass);
  border-radius: var(--radius-xl);
  padding: 1.25rem;
  border: var(--card-border);
  backdrop-filter: blur(12px);
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}
.panel-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  padding-left: 0.625rem;
  border-left: 3px solid var(--color-success);
}
.action-group {
  display: flex;
  gap: 0.375rem;
  flex-wrap: wrap;
}
.score-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.score-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-weight: 600;
}
.metrics-text {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}
.detail-content {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.detail-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--color-border-primary);
}
.detail-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  min-width: 100px;
  flex-shrink: 0;
}
.detail-value {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-weight: 500;
}
.detail-section {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--color-bg-active);
}
.section-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-primary-light);
  margin-bottom: 0.5rem;
}
.detail-json {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  background: rgba(0, 0, 0, 0.3);
  padding: 0.75rem;
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin: 0;
  line-height: 1.5;
}
.upgrade-btn {
  padding: 0.375rem 0.75rem;
  background: var(--color-success-bg);
  color: var(--color-success);
  border: 1px solid var(--color-success-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}
.upgrade-btn:hover {
  background: var(--color-success-hover);
  border-color: var(--color-success-hover);
}
.grayscale-header-actions {
  display: flex;
  gap: 0.75rem;
  margin-bottom: var(--spacing-lg);
}

/* Extracted inline styles for reject modal */
.reject-modal { max-width: 440px; }
.reject-modal-desc { color: var(--color-text-tertiary); font-size: var(--font-size-sm); margin-bottom: 12px; }
.reject-modal-textarea { width: 100%; background: var(--color-bg-primary); border: 1px solid var(--color-bg-tertiary); border-radius: var(--radius-md); padding: 10px; color: var(--color-text-secondary); font-size: var(--font-size-sm); resize: vertical; }
.reject-modal-actions { margin-top: 16px; }
.reject-confirm-btn { background: #EF4444 !important; }
</style>
