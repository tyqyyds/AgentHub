<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useLogger } from '@/utils/logger'
import { POLLING_INTERVAL, FEATURES } from '@/config'
import { api, apiClient, authFetch } from '@/utils/apiClient'
import { showToast } from '../utils/toast'
import { useApi } from '@/composables/useApi'
import { themeColors } from '@/utils/themeColors'
import { useCountUp } from '@/composables/useCountUp'
import { safeAnimate } from '@/utils/animation'
import gsap from 'gsap'
import PageLayout from '@/components/PageLayout.vue'
import StatCard from '@/components/StatCard.vue'

const router = useRouter()
const { info, warn } = useLogger()
const { error: apiError } = useApi()
const dashboardError = ref<string | null>(null)

interface Stat {
  label: string
  value: number
  unit: string
  color: string
  icon: string
  trend: 'up' | 'down' | 'stable'
  trendValue: number
  historyData: number[]
  route: string
}

interface Intent {
  id: number
  name: string
  status: string
  time: string
  type: string
}

interface DeviceHealth {
  name: string
  health: number | null
  status: string
  type: string
  cpu: number | null
  memory: number | null
}

interface RateLimitData {
  timestamp: string
  requests: number
  allowed: number
  limited: number
}

interface SelfHealingEvent {
  id: number
  type: string
  device: string
  action: string
  time: string
  status: 'success' | 'failed' | 'running'
}

const INTENT_TYPE_MAP: Record<string, string> = {
  bandwidth_guarantee: '带宽保障',
  access_control: '访问控制',
  qos_policy: 'QoS策略',
  link_management: '链路管理',
  fault_diagnosis: '故障诊断',
  traffic_shaping: '流量整形',
  security_policy: '安全策略',
  route_optimization: '路由优化',
  general: '通用'
}

const DEVICE_TYPE_MAP: Record<string, string> = {
  router: '路由器',
  switch: '交换机',
  firewall: '防火墙',
  server: '服务器',
  core: '核心设备',
  ap: '无线AP',
  loadbalancer: '负载均衡'
}

const stats = ref<Stat[]>([
  {
    label: '活跃意图',
    value: 0,
    unit: '个',
    color: themeColors.primary,
    icon: '🎯',
    trend: 'up',
    trendValue: 0,
    historyData: [],
    route: '/intent'
  },
  {
    label: '在线设备',
    value: 0,
    unit: '台',
    color: themeColors.success,
    icon: '🖥️',
    trend: 'up',
    trendValue: 0,
    historyData: [],
    route: '/topology'
  },
  {
    label: '自愈事件',
    value: 0,
    unit: '次',
    color: themeColors.orange,
    icon: '🛡️',
    trend: 'down',
    trendValue: 0,
    historyData: [],
    route: '/self-healing'
  },
  {
    label: '待审批',
    value: 0,
    unit: '项',
    color: themeColors.error,
    icon: '📋',
    trend: 'stable',
    trendValue: 0,
    historyData: [],
    route: '/intent'
  }
])

const rateLimitStats = ref({
  totalRequests: 0,
  allowedRequests: 0,
  limitedRequests: 0,
  limitThreshold: 1000,
  currentRate: 0
})

const rateLimitHistory = ref<RateLimitData[]>([])
let rateLimitInterval: number | null = null
let dashboardInterval: number | null = null
let handleDataUpdate: (() => void) | null = null
const isRefreshing = ref(false)
const lastRefreshTime = ref('')
const isRateLimitRefreshing = ref(false)
const showDebug = ref(false)
const lastUpdateTime = ref('')
const isDebugEnabled = FEATURES.DEBUG_PANEL || import.meta.env.DEV
const isMockData = ref(false)
const isLoading = ref(true)
const autoRefreshInterval = ref(30)
const autoRefreshOptions = [10, 30, 60, 120]
const showExportMenu = ref(false)
const intentFilter = ref<'all' | 'pending' | 'completed' | 'rejected'>('all')

const recentIntents = ref<Intent[]>([])
const healthStatus = ref<DeviceHealth[]>([])
const selfHealingEvents = ref<SelfHealingEvent[]>([])
const topologyLinks = ref<any[]>([])

const systemUptime = computed(() => {
  const devices = healthStatus.value
  if (!devices || devices.length === 0) return { value: 0, label: '暂无数据' }
  const devicesWithHealth = devices.filter((d: any) => d.health !== null && d.health !== undefined)
  if (devicesWithHealth.length === 0) return { value: 0, label: '暂无数据' }
  const avg = devicesWithHealth.reduce((sum: number, d: any) => sum + d.health, 0) / devicesWithHealth.length
  return { value: Math.round(avg * 10) / 10, label: `${Math.round(avg * 10) / 10}%` }
})

const networkLatency = computed(() => {
  const links = topologyLinks.value
  if (!links || links.length === 0) return { value: 0, label: '暂无数据' }
  const linksWithLatency = links.filter((l: any) => l.latency !== null && l.latency !== undefined)
  if (linksWithLatency.length === 0) return { value: 0, label: '暂无数据' }
  const avg = linksWithLatency.reduce((sum: number, l: any) => sum + l.latency, 0) / linksWithLatency.length
  return { value: Math.round(avg * 10) / 10, label: `${Math.round(avg * 10) / 10}ms` }
})
const dataFreshness = ref('实时')
const fetchCount = ref(0)
const errorCount = ref(0)
const onlineDevices = ref(0)
const totalDevices = ref(0)

const pendingCount = computed(() => stats.value[3].value)
const healthScore = computed(() => {
  const devices = healthStatus.value
  if (!devices.length) return 0
  const withHealth = devices.filter(d => d.health !== null && d.health !== undefined)
  if (withHealth.length === 0) return 0
  return Math.round(withHealth.reduce((sum, d) => sum + (d.health ?? 0), 0) / withHealth.length)
})

const warningDevices = computed(() =>
  healthStatus.value.filter(d => d.health !== null && d.health !== undefined && (d.status === 'warning' || d.health < 90)).length
)

const highCpuDevices = computed(() =>
  healthStatus.value.filter(d => d.cpu !== null && d.cpu !== undefined && d.cpu > 80).length
)

const rateLimitPercentage = computed(() =>
  Math.min(100, (rateLimitStats.value.currentRate / rateLimitStats.value.limitThreshold) * 100)
)

const filteredIntents = computed(() => {
  if (intentFilter.value === 'all') return recentIntents.value
  return recentIntents.value.filter(i => i.status === intentFilter.value)
})

const selfHealingSuccessRate = computed(() => {
  const events = selfHealingEvents.value
  if (!events.length) return 0
  const success = events.filter(e => e.status === 'success').length
  return Math.round((success / events.length) * 100)
})

let fetchAbortController: AbortController | null = null
let isFetching = false
let visibilityDebounceTimer: number | null = null

const translateIntentType = (type: string): string => {
  return INTENT_TYPE_MAP[type] || type
}

const translateDeviceType = (type: string): string => {
  return DEVICE_TYPE_MAP[type] || type
}

// 使用 useCountUp Composable 替代手动 requestAnimationFrame
const stat0Display = useCountUp(computed(() => stats.value[0].value), { duration: 0.6 })
const stat1Display = useCountUp(computed(() => stats.value[1].value), { duration: 0.6 })
const stat2Display = useCountUp(computed(() => stats.value[2].value), { duration: 0.6 })
const stat3Display = useCountUp(computed(() => stats.value[3].value), { duration: 0.6 })
const statDisplays = [stat0Display, stat1Display, stat2Display, stat3Display]

// GSAP 入场动画
let entranceCtx: gsap.Context | undefined
const dashboardRef = ref<HTMLElement>()

const playEntranceAnimation = () => {
  nextTick(() => {
    if (!dashboardRef.value) return
    entranceCtx?.revert()
    entranceCtx = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: 'power2.out' } })

      // 统计卡片依次入场
      tl.from('.stats-grid .stat-card-clickable', {
        opacity: 0,
        y: 20,
        scale: 0.95,
        stagger: 0.08,
        duration: 0.4,
      })

      // 摘要条入场
      tl.from('.summary-bar', {
        opacity: 0,
        y: 12,
        duration: 0.35,
      }, '-=0.15')

      // 面板依次入场
      tl.from('.content-row .panel', {
        opacity: 0,
        x: 20,
        stagger: 0.1,
        duration: 0.4,
      }, '-=0.2')

      // 限流面板入场
      tl.from('.content-row.three-col .panel', {
        opacity: 0,
        y: 16,
        stagger: 0.1,
        duration: 0.4,
      }, '-=0.15')
    }, dashboardRef.value)
  })
}

const fetchDashboardData = async (showLoading = false) => {
  if (isFetching) return
  isFetching = true

  if (fetchAbortController) {
    fetchAbortController.abort()
  }
  fetchAbortController = new AbortController()

  const now = new Date()
  lastRefreshTime.value = now.toLocaleTimeString()
  if (showLoading) isRefreshing.value = true
  dashboardError.value = null

  try {
    const [intentResult, topologyResult] = await Promise.allSettled([
      apiClient.get(api.intents),
      apiClient.get(api.topology)
    ])

    if (intentResult.status === 'fulfilled') {
      const intentData = intentResult.value.data
      if (intentData) {
        isMockData.value = false
        const intents = intentData
        fetchCount.value++

        const activeIntentsCount = Array.isArray(intents) ? intents.length : 0
        const pendingIntentsCount = Array.isArray(intents) ? intents.filter((i: any) => i.approval_status === 'pending').length : 0

        const prevActive = stats.value[0].value
        const prevPending = stats.value[3].value

        stats.value[0] = {
            ...stats.value[0],
            value: activeIntentsCount,
            trend: activeIntentsCount > prevActive ? 'up' : activeIntentsCount < prevActive ? 'down' : 'stable',
            trendValue: prevActive > 0 ? Math.round(((activeIntentsCount - prevActive) / prevActive) * 100) : 0,
            historyData: [...stats.value[0].historyData.slice(1), activeIntentsCount]
          }
          stats.value[3] = {
            ...stats.value[3],
            value: pendingIntentsCount,
            trend: pendingIntentsCount > prevPending ? 'up' : pendingIntentsCount < prevPending ? 'down' : 'stable',
            trendValue: prevPending > 0 ? Math.round(((pendingIntentsCount - prevPending) / prevPending) * 100) : 0,
            historyData: [...stats.value[3].historyData.slice(1), pendingIntentsCount]
          }

        recentIntents.value = intents.slice(0, 8).map((item: any) => ({
          id: item.id,
          name: item.user_input || item.intent_name || '未命名意图',
          status: item.approval_status === 'pending' ? 'pending' :
                  item.approval_status === 'approved' ? 'completed' : 'rejected',
          time: formatTime(item.created_at),
          type: item.structured_params?.intent_type || 'general'
        }))

        dataFreshness.value = '实时'
      } else {
        loadMockIntentData()
        isMockData.value = true
      }
    }

    if (topologyResult.status === 'fulfilled') {
      const topoData = topologyResult.value.data
      if (topoData) {
        const nodes = topoData.nodes || []
        const online = nodes.filter((n: any) => n.status !== 'offline' && n.status !== 'isolated').length
        const total = nodes.length

        const prevOnline = stats.value[1].value
        stats.value[1] = {
          ...stats.value[1],
          value: online,
          trend: online > prevOnline ? 'up' : online < prevOnline ? 'down' : 'stable',
          trendValue: prevOnline > 0 ? Math.round(((online - prevOnline) / prevOnline) * 100) : 0,
          historyData: [...stats.value[1].historyData.slice(1), online]
        }

        onlineDevices.value = online
        totalDevices.value = total

        healthStatus.value = nodes
          .filter((n: any) => n.status !== 'offline')
          .slice(0, 6)
          .map((n: any) => ({
            name: n.name || n.id,
            health: n.health ?? null,
            status: n.status === 'warning' ? 'warning' : n.status === 'error' ? 'error' : 'normal',
            type: n.type || 'router',
            cpu: n.cpu_usage ?? n.cpu ?? null,
            memory: n.memory_usage ?? n.memory ?? null
          }))

        const links = topoData.links || topoData.edges || []
        topologyLinks.value = links

      }
    }

    try {
      const eventsResponse = await authFetch(api.events)
      if (eventsResponse.ok) {
        const eventsData = await eventsResponse.json()
        const eventsList = eventsData.status === 'success' ? (eventsData.data || []) : (eventsData.data || eventsData.items || [])
        selfHealingEvents.value = (Array.isArray(eventsList) ? eventsList : []).map((event: any) => ({
          id: event.id,
          type: event.event_type || event.type || 'unknown',
          title: event.title || event.event_type || 'Self-healing Event',
          status: event.status || 'pending',
          device: event.target_device || event.device_id || event.device || 'Unknown',
          action: event.suggested_action || event.action || '',
          time: formatTime(event.created_at || event.timestamp || new Date().toISOString())
        }))
        stats.value[2] = {
          ...stats.value[2],
          value: selfHealingEvents.value.length,
          historyData: [...stats.value[2].historyData.slice(1), selfHealingEvents.value.length]
        }
        isMockData.value = false
      } else {
        loadMockSelfHealingData()
        isMockData.value = true
      }
    } catch {
      loadMockSelfHealingData()
      isMockData.value = true
    }

    if (intentResult.status === 'rejected' && topologyResult.status === 'rejected') {
      loadMockData()
      isMockData.value = true
    }
  } catch (err: any) {
    if (err.name === 'AbortError') return
    warn('获取指挥舱数据失败', { error: err.message })
    errorCount.value++
    dashboardError.value = err.message || '数据加载失败'
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

const formatTime = (dateStr: string): string => {
  if (!dateStr) return '--'
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  if (diffMs < 0) return '刚刚'
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins}分钟前`
  if (diffHours < 24) return `${diffHours}小时前`
  return `${diffDays}天前`
}

const loadMockData = () => {
  loadMockIntentData()
  loadMockTopologyData()
  loadMockSelfHealingData()
}

const loadMockIntentData = () => {
  recentIntents.value = [
    { id: 1, name: '带宽保障-视频会议', status: 'completed', time: '5分钟前', type: 'bandwidth_guarantee' },
    { id: 2, name: 'ACL规则更新', status: 'pending', time: '15分钟前', type: 'access_control' },
    { id: 3, name: 'QoS策略优化', status: 'completed', time: '1小时前', type: 'qos_policy' },
    { id: 4, name: '链路冗余配置', status: 'rejected', time: '2小时前', type: 'link_management' },
    { id: 5, name: '故障诊断-核心路由', status: 'completed', time: '3小时前', type: 'fault_diagnosis' },
    { id: 6, name: '流量整形策略', status: 'pending', time: '4小时前', type: 'traffic_shaping' }
  ]
  stats.value[0].value = 24
  stats.value[3].value = 3
}

const loadMockTopologyData = () => {
  healthStatus.value = [
    { name: '核心路由器', health: 98, status: 'normal', type: 'router', cpu: 35, memory: 52 },
    { name: '汇聚交换机', health: 92, status: 'normal', type: 'switch', cpu: 28, memory: 45 },
    { name: '防火墙集群', health: 87, status: 'warning', type: 'firewall', cpu: 72, memory: 68 },
    { name: '接入交换机', health: 95, status: 'normal', type: 'switch', cpu: 22, memory: 38 },
    { name: '负载均衡器', health: 91, status: 'normal', type: 'loadbalancer', cpu: 45, memory: 55 }
  ]
  stats.value[1].value = 156
  onlineDevices.value = 156
  totalDevices.value = 160
}

const loadMockSelfHealingData = () => {
  selfHealingEvents.value = [
    { id: 1, type: '链路切换', device: '核心路由器-GE0/0/1', action: '自动切换至备用链路', time: '10分钟前', status: 'success' },
    { id: 2, type: 'CPU过载', device: '防火墙集群-Node2', action: '流量负载均衡再分配', time: '25分钟前', status: 'success' },
    { id: 3, type: '端口故障', device: '接入交换机-FE0/0/3', action: '端口隔离与流量迁移', time: '1小时前', status: 'success' },
    { id: 4, type: '内存泄漏', device: '汇聚交换机-主控', action: '进程重启恢复', time: '2小时前', status: 'failed' },
    { id: 5, type: '路由震荡', device: '核心路由器-BGP', action: '路由策略自动调整', time: '3小时前', status: 'success' }
  ]
  stats.value[2].value = 8
  stats.value[2].value = 8
}

const updateRateLimitData = async () => {
  try {
    const data = await apiClient.get(api.rateLimit.simulate)

    if (data.status === 'success') {
      const d = data.data || data
      rateLimitStats.value.totalRequests = d.requests + (rateLimitStats.value.totalRequests || 0)
      rateLimitStats.value.allowedRequests = d.allowed + (rateLimitStats.value.allowedRequests || 0)
      rateLimitStats.value.limitedRequests = d.limited + (rateLimitStats.value.limitedRequests || 0)
      rateLimitStats.value.currentRate = d.requests

      await loadRateLimitData()
    }
  } catch (err: any) {
    warn('更新限流数据失败', { error: err.message })
  }
}

const manualRefreshRateLimit = async () => {
  isRateLimitRefreshing.value = true
  try {
    await loadRateLimitData()
    showToast('限流数据已刷新', 'success')
  } catch (err: any) {
    warn('刷新限流数据失败', { error: err.message })
    showToast('刷新限流数据失败', 'error')
  } finally {
    isRateLimitRefreshing.value = false
  }
}

const manualRefreshDashboard = async () => {
  isRefreshing.value = true
  try {
    await fetchDashboardData(true)
    showToast('数据已刷新', 'success')
  } catch {
    showToast('刷新失败', 'error')
  }
}

const loadRateLimitData = async () => {
  try {
    const data = await apiClient.get(api.rateLimit.status)

    if (data.status === 'success' && data.data) {
      rateLimitStats.value = {
        totalRequests: data.data.total_requests,
        allowedRequests: data.data.allowed_requests,
        limitedRequests: data.data.limited_requests,
        limitThreshold: data.data.limit_threshold,
        currentRate: data.data.current_rate
      }

      const historyData = (data as any).history || (data.data as any)?.history
      if (historyData && historyData.length > 0) {
        rateLimitHistory.value = historyData.map((item: any) => ({
          timestamp: new Date(item.timestamp).toLocaleTimeString(),
          requests: item.requests,
          allowed: item.allowed,
          limited: item.limited
        }))
      }

      lastUpdateTime.value = new Date().toLocaleTimeString()
    }
  } catch (err: any) {
    warn('加载限流数据失败', { error: err.message })
    if (rateLimitHistory.value.length === 0) {
      loadMockRateLimitData()
      isMockData.value = true
    }
  }
}

const toggleDebug = () => {
  showDebug.value = !showDebug.value
}

const getBarHeight = (value: number, isLimited: boolean = false) => {
  if (value <= 0) return isLimited ? 0 : 5
  const minValue = 10
  const maxValue = 200
  const minHeight = isLimited ? 8 : 10
  const maxHeight = 90
  const clampedValue = Math.max(minValue, Math.min(maxValue, value))
  const logMin = Math.log(minValue)
  const logMax = Math.log(maxValue)
  const logValue = Math.log(clampedValue)
  const ratio = (logValue - logMin) / (logMax - logMin)
  return minHeight + ratio * (maxHeight - minHeight)
}

const loadMockRateLimitData = () => {
  const now = new Date()
  rateLimitHistory.value = []
  for (let i = 0; i < 20; i++) {
    const time = new Date(now.getTime() - (19 - i) * 5000)
    const requests = Math.floor(Math.random() * 100) + 50
    const limited = Math.random() > 0.8 ? Math.floor(Math.random() * 20) : 0
    rateLimitHistory.value.push({
      timestamp: time.toLocaleTimeString(),
      requests,
      allowed: requests - limited,
      limited
    })
  }
}

const resetRateLimit = async () => {
  try {
    const data = await apiClient.post(api.rateLimit.reset)
    if (data.status === 'success') {
      rateLimitStats.value = {
        totalRequests: 0,
        allowedRequests: 0,
        limitedRequests: 0,
        limitThreshold: 1000,
        currentRate: 0
      }
      rateLimitHistory.value = []
      showToast('限流统计已重置', 'success')
      return true
    }
    return false
  } catch (err: any) {
    warn('重置限流统计失败', { error: err.message })
    return false
  }
}

const getRateLimitStatus = () => {
  const rate = rateLimitStats.value.currentRate
  const threshold = rateLimitStats.value.limitThreshold
  const percentage = (rate / threshold) * 100
  if (percentage >= 90) return 'error'
  if (percentage >= 70) return 'warning'
  return 'normal'
}

const getRateLimitColor = () => {
  const status = getRateLimitStatus()
  if (status === 'error') return themeColors.error
  if (status === 'warning') return themeColors.warning
  return themeColors.success
}

const generateSmoothPath = (data: number[]) => {
  if (!data || data.length < 2) return ''
  const maxVal = Math.max(...data)
  const minVal = Math.min(...data)
  const range = maxVal - minVal || 1
  const points = data.map((val, index) => ({
    x: (index / (data.length - 1)) * 100,
    y: 28 - ((val - minVal) / range) * 24
  }))

  let path = `M ${points[0].x},${points[0].y}`
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1]
    const curr = points[i]
    const cpx1 = prev.x + (curr.x - prev.x) * 0.4
    const cpx2 = prev.x + (curr.x - prev.x) * 0.6
    path += ` C ${cpx1},${prev.y} ${cpx2},${curr.y} ${curr.x},${curr.y}`
  }
  return path
}

const generateSmoothArea = (data: number[]) => {
  if (!data || data.length < 2) return ''
  const linePath = generateSmoothPath(data)
  const lastX = ((data.length - 1) / (data.length - 1)) * 100
  return `${linePath} L ${lastX},30 L 0,30 Z`
}

const getIntentStatusColor = (status: string) => {
  switch (status) {
    case 'completed': return themeColors.success
    case 'pending': return themeColors.warning
    case 'rejected': return themeColors.error
    default: return themeColors.textTertiary
  }
}

const getIntentStatusText = (status: string) => {
  switch (status) {
    case 'completed': return '已完成'
    case 'pending': return '待审批'
    case 'rejected': return '已拒绝'
    default: return status
  }
}

const getHealthColor = (health: number) => {
  if (health >= 90) return themeColors.success
  if (health >= 70) return themeColors.warning
  return themeColors.error
}

const getSelfHealingStatusColor = (status: string) => {
  switch (status) {
    case 'success': return themeColors.success
    case 'failed': return themeColors.error
    case 'running': return themeColors.primary
    default: return themeColors.textTertiary
  }
}

const getSelfHealingStatusText = (status: string) => {
  switch (status) {
    case 'success': return '成功'
    case 'failed': return '失败'
    case 'running': return '执行中'
    default: return status
  }
}

const handleVisibilityChange = () => {
  if (!document.hidden) {
    if (visibilityDebounceTimer) clearTimeout(visibilityDebounceTimer)
    visibilityDebounceTimer = window.setTimeout(() => {
      if (!isFetching) {
        fetchDashboardData(false)
      }
    }, 300)
  }
}

const navigateTo = (route: string) => {
  router.push(route)
}

const handleStatClick = (stat: Stat) => {
  navigateTo(stat.route)
}

const handleIntentClick = (_intent: Intent) => {
  navigateTo('/intent')
}

const exportDashboardData = (format: 'json' | 'csv') => {
  const exportData = {
    exportTime: new Date().toISOString(),
    stats: stats.value.map(s => ({
      label: s.label,
      value: s.value,
      unit: s.unit,
      trend: s.trend,
      trendValue: s.trendValue
    })),
    recentIntents: recentIntents.value,
    healthStatus: healthStatus.value.map(h => ({
      name: h.name,
      type: translateDeviceType(h.type),
      health: h.health,
      cpu: h.cpu,
      memory: h.memory
    })),
    selfHealingEvents: selfHealingEvents.value,
    rateLimit: rateLimitStats.value,
    systemMetrics: {
      uptime: systemUptime.value.label,
      latency: networkLatency.value.label,
      healthScore: healthScore.value,
      onlineDevices: onlineDevices.value,
      totalDevices: totalDevices.value
    }
  }

  if (format === 'json') {
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `dashboard_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  } else {
    const escCsv = (v: string | number): string => { const s = String(v); return /[",\n\r=+\-@]/.test(s) ? `"${s.replace(/"/g, '""').replace(/[\r\n]+/g, ' ')}"` : s }
    const headers = '指标,数值,单位,趋势\n'
    const rows = stats.value.map(s =>
      [s.label, s.value, s.unit, `${s.trend === 'up' ? '↑' : s.trend === 'down' ? '↓' : '→'}${s.trendValue}%`].map(escCsv).join(',')
    ).join('\n')
    const blob = new Blob(['\uFEFF' + headers + rows], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `dashboard_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  showExportMenu.value = false
  showToast(`数据已导出为 ${format.toUpperCase()} 格式`, 'success')
}

const handleKeydown = (e: KeyboardEvent) => {
  if (e.altKey && e.key === 'r') {
    e.preventDefault()
    manualRefreshDashboard()
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

const healthRingPath = (health: number, radius: number = 18) => {
  const circumference = 2 * Math.PI * radius
  const dashLength = (health / 100) * circumference
  return {
    dashArray: `${dashLength} ${circumference - dashLength}`,
    transform: `rotate(-90 22 22)`
  }
}

onMounted(async () => {
  info('Dashboard mounted, initializing...')

  loadMockSelfHealingData()
  await loadRateLimitData()
  fetchDashboardData(true)

  handleDataUpdate = () => {
    fetchDashboardData(false)
  }

  window.addEventListener('dashboardDataUpdated', handleDataUpdate)
  window.addEventListener('auditLogsUpdated', handleDataUpdate)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('click', handleClickOutside)

  dashboardInterval = window.setInterval(() => {
    if (!document.hidden) {
      fetchDashboardData(false)
    }
  }, autoRefreshInterval.value * 1000)

  rateLimitInterval = window.setInterval(updateRateLimitData, POLLING_INTERVAL.RATE_LIMIT)

  // GSAP 入场动画
  playEntranceAnimation()

  info('Dashboard 初始化完成')
})

onUnmounted(() => {
  if (rateLimitInterval !== null) clearInterval(rateLimitInterval)
  if (dashboardInterval !== null) clearInterval(dashboardInterval)
  if (visibilityDebounceTimer !== null) clearTimeout(visibilityDebounceTimer)
  if (fetchAbortController) fetchAbortController.abort()
  entranceCtx?.revert()
  if (handleDataUpdate) {
    window.removeEventListener('dashboardDataUpdated', handleDataUpdate)
    window.removeEventListener('auditLogsUpdated', handleDataUpdate)
  }
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <PageLayout ref="dashboardRef" title="指挥舱" subtitle="网络运维全景监控">
    <template #actions>
      <span class="data-freshness" :class="{ degraded: dataFreshness === '降级' }">
        <span class="freshness-dot"></span>
        {{ dataFreshness === '实时' ? '实时' : '降级' }}
      </span>
      <span class="last-refresh" v-if="lastRefreshTime">
        {{ lastRefreshTime }}
      </span>
      <div class="export-wrapper">
        <button
          type="button"
          class="action-btn"
          @click.stop="showExportMenu = !showExportMenu"
          title="导出数据"
          aria-label="导出数据"
        >
          📥 导出
        </button>
        <div v-if="showExportMenu" class="export-dropdown">
          <button type="button" @click="exportDashboardData('json')" aria-label="导出JSON">导出 JSON</button>
          <button type="button" @click="exportDashboardData('csv')" aria-label="导出CSV">导出 CSV</button>
        </div>
      </div>
      <button
        type="button"
        class="action-btn refresh-btn"
        :class="{ refreshing: isRefreshing }"
        @click="manualRefreshDashboard"
        :disabled="isRefreshing"
        title="刷新数据 (Alt+R)"
        aria-label="刷新数据"
      >
        <span class="refresh-icon" :class="{ spinning: isRefreshing }">🔄</span>
        {{ isRefreshing ? '刷新中...' : '刷新' }}
      </button>
      <select
        v-model="autoRefreshInterval"
        class="auto-refresh-select"
        title="自动刷新间隔"
        aria-label="自动刷新间隔"
      >
        <option v-for="opt in autoRefreshOptions" :key="opt" :value="opt">{{ opt }}s</option>
      </select>
    </template>

    <div v-if="dashboardError && isMockData" class="error-banner">
      <span class="error-banner-icon">⚠️</span>
      <span class="error-banner-text">数据加载失败: {{ dashboardError }}，当前显示为模拟数据</span>
      <button type="button" class="error-banner-retry" @click="manualRefreshDashboard" aria-label="重试">🔄 重试</button>
    </div>

    <div v-if="isLoading" class="stats-grid">
      <div v-for="i in 4" :key="i" class="stat-card-skeleton">
        <div class="skeleton-line wide"></div>
        <div class="skeleton-line narrow"></div>
        <div class="skeleton-line medium"></div>
      </div>
    </div>

    <div v-else class="stats-grid">
      <StatCard
        v-for="(stat, idx) in stats"
        :key="stat.label"
        :icon="stat.icon"
        :label="stat.label"
        :value="statDisplays[idx].value"
        :suffix="stat.unit"
        :trend="stat.trendValue || undefined"
        :type="stat.label === '在线设备' ? 'success' : stat.label === '自愈事件' ? 'warning' : stat.label === '待审批' ? 'danger' : 'default'"
        class="stat-card-clickable"
        @click="handleStatClick(stat)"
      />
    </div>

    <div class="summary-bar">
      <div class="summary-item" :title="`在线 ${onlineDevices} / 总计 ${totalDevices} 台设备`">
        <span class="summary-icon">⬆</span>
        <span class="summary-label">系统可用率</span>
        <span class="summary-value success">{{ systemUptime.label }}</span>
      </div>
      <div class="summary-divider"></div>
      <div class="summary-item" :title="`基于设备CPU负载推算`">
        <span class="summary-icon">⚡</span>
        <span class="summary-label">平均延迟</span>
        <span class="summary-value">{{ networkLatency.label }}</span>
      </div>
      <div class="summary-divider"></div>
      <div class="summary-item" :title="`告警: ${warningDevices} 台 / 高CPU: ${highCpuDevices} 台`">
        <span class="summary-icon">💚</span>
        <span class="summary-label">设备健康分</span>
        <span class="summary-value" :style="{ color: getHealthColor(healthScore) }">{{ healthScore }}%</span>
      </div>
      <div class="summary-divider"></div>
      <div class="summary-item" :title="`需要审批的意图数量`">
        <span class="summary-icon">📝</span>
        <span class="summary-label">待处理</span>
        <span class="summary-value" :class="{ warning: pendingCount > 0 }">{{ pendingCount }} 项</span>
      </div>
      <div class="summary-divider"></div>
      <div class="summary-item" :title="`自愈成功率: ${selfHealingSuccessRate}%`">
        <span class="summary-icon">🛡️</span>
        <span class="summary-label">自愈成功率</span>
        <span class="summary-value" :class="{ warning: selfHealingSuccessRate < 80 }">{{ selfHealingSuccessRate }}%</span>
      </div>
      <div class="summary-divider"></div>
      <div class="summary-item" :title="`成功: ${fetchCount} / 失败: ${errorCount}`">
        <span class="summary-icon">📡</span>
        <span class="summary-label">数据请求</span>
        <span class="summary-value" :class="{ warning: errorCount > 3 }">{{ fetchCount }}/{{ fetchCount + errorCount }}</span>
      </div>
    </div>

    <div class="content-row">
      <div class="panel">
        <div class="panel-header">
          <h2 class="panel-title">最近意图执行</h2>
          <div class="filter-group">
            <button
              type="button"
              v-for="f in (['all', 'pending', 'completed', 'rejected'] as const)"
              :key="f"
              class="filter-btn"
              :class="{ active: intentFilter === f }"
              @click="intentFilter = f"
              :aria-label="'筛选: ' + (f === 'all' ? '全部' : getIntentStatusText(f))"
            >
              {{ f === 'all' ? '全部' : getIntentStatusText(f) }}
            </button>
          </div>
        </div>
        <div class="intent-list">
          <div
            v-for="(intent, idx) in filteredIntents"
            :key="intent.id"
            class="intent-item clickable"
            :style="{ '--item-delay': `${idx * 0.04}s` }"
            @click="handleIntentClick(intent)"
          >
            <span class="intent-index">{{ String(idx + 1).padStart(2, '0') }}</span>
            <div class="intent-left">
              <span class="intent-status-dot" :style="{ background: getIntentStatusColor(intent.status), boxShadow: `0 0 6px ${getIntentStatusColor(intent.status)}60` }"></span>
              <div class="intent-info">
                <div class="intent-name">{{ intent.name }}</div>
                <div class="intent-meta">
                  <span class="intent-type">{{ translateIntentType(intent.type) }}</span>
                  <span class="intent-time">{{ intent.time }}</span>
                </div>
              </div>
            </div>
            <span class="intent-status-badge" :style="{ color: getIntentStatusColor(intent.status), background: getIntentStatusColor(intent.status) + '12', borderColor: getIntentStatusColor(intent.status) + '25' }">
              {{ getIntentStatusText(intent.status) }}
            </span>
          </div>
          <div v-if="filteredIntents.length === 0" class="empty-state">
            <div class="empty-icon">📭</div>
            <div>{{ intentFilter === 'all' ? '暂无意图记录' : `暂无${getIntentStatusText(intentFilter)}的意图` }}</div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="health-overview">
          <div class="health-score-ring">
            <svg viewBox="0 0 80 80" class="health-score-svg" aria-hidden="true">
              <circle cx="40" cy="40" r="34" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="5" />
              <circle
                cx="40" cy="40" r="34" fill="none"
                :stroke="getHealthColor(healthScore)"
                stroke-width="5"
                stroke-linecap="round"
                :stroke-dasharray="`${(healthScore / 100) * 2 * Math.PI * 34} ${2 * Math.PI * 34 - (healthScore / 100) * 2 * Math.PI * 34}`"
                transform="rotate(-90 40 40)"
                class="health-score-arc"
              />
            </svg>
            <div class="health-score-text">
              <span class="health-score-value" :style="{ color: getHealthColor(healthScore) }">{{ healthScore }}</span>
              <span class="health-score-label">健康分</span>
            </div>
          </div>
          <div class="health-summary-stats">
            <div class="health-stat">
              <span class="health-stat-num">{{ healthStatus.length }}</span>
              <span class="health-stat-desc">在线设备</span>
            </div>
            <div class="health-stat">
              <span class="health-stat-num warn">{{ warningDevices }}</span>
              <span class="health-stat-desc">告警设备</span>
            </div>
            <div class="health-stat">
              <span class="health-stat-num danger">{{ highCpuDevices }}</span>
              <span class="health-stat-desc">高负载</span>
            </div>
          </div>
        </div>
        <div class="health-list">
          <div
            v-for="device in healthStatus"
            :key="device.name"
            class="health-item"
            :class="{ 'health-warning': device.status === 'warning' }"
          >
            <div class="health-ring-wrap">
              <svg viewBox="0 0 44 44" class="health-ring-svg" aria-hidden="true">
                <circle cx="22" cy="22" :r="18" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="3" />
                <circle
                  cx="22" cy="22" :r="18" fill="none"
                  :stroke="getHealthColor(device.health ?? 0)"
                  stroke-width="3"
                  stroke-linecap="round"
                  :stroke-dasharray="healthRingPath(device.health ?? 0).dashArray"
                  :transform="healthRingPath(device.health ?? 0).transform"
                />
              </svg>
              <span class="health-ring-value" :style="{ color: getHealthColor(device.health ?? 0) }">{{ device.health ?? '--' }}</span>
            </div>
            <div class="health-device-info">
              <span class="health-name">{{ device.name }}</span>
              <span class="health-type-tag">{{ translateDeviceType(device.type) }}</span>
            </div>
            <div class="health-resources">
              <span class="resource-tag" :class="{ danger: device.cpu !== null && device.cpu > 80 }" :title="`CPU: ${device.cpu ?? '--'}%`">
                CPU {{ device.cpu ?? '--' }}%
              </span>
              <span class="resource-tag" :class="{ danger: device.memory !== null && device.memory > 80 }" :title="`MEM: ${device.memory ?? '--'}%`">
                MEM {{ device.memory ?? '--' }}%
              </span>
            </div>
          </div>
          <div v-if="healthStatus.length === 0" class="empty-state">
            <div class="empty-icon">🔌</div>
            <div>暂无设备数据</div>
          </div>
        </div>
      </div>
    </div>

    <div class="content-row three-col">
      <div class="panel">
        <h2 class="panel-title">自愈事件追踪</h2>
        <div class="healing-timeline">
          <div
            v-for="event in selfHealingEvents"
            :key="event.id"
            class="healing-item"
          >
            <div class="healing-timeline-dot" :style="{ background: getSelfHealingStatusColor(event.status), boxShadow: `0 0 8px ${getSelfHealingStatusColor(event.status)}40` }"></div>
            <div class="healing-timeline-line"></div>
            <div class="healing-content">
              <div class="healing-header">
                <span class="healing-type">{{ event.type }}</span>
                <span class="healing-badge" :style="{ color: getSelfHealingStatusColor(event.status), background: getSelfHealingStatusColor(event.status) + '12' }">
                  {{ getSelfHealingStatusText(event.status) }}
                </span>
              </div>
              <div class="healing-device">{{ event.device }}</div>
              <div class="healing-action">{{ event.action }}</div>
              <div class="healing-time">{{ event.time }}</div>
            </div>
          </div>
          <div v-if="selfHealingEvents.length === 0" class="empty-state small">
            暂无自愈事件
          </div>
        </div>
      </div>

      <div class="panel rate-limit-panel" style="grid-column: span 2;">
        <div class="panel-header">
          <h2 class="panel-title">API限流监控</h2>
          <div class="panel-actions">
            <div :class="['rate-limit-status', getRateLimitStatus()]">
              <span class="status-dot"></span>
              <span class="status-text">
                {{ getRateLimitStatus() === 'error' ? '高负载' : getRateLimitStatus() === 'warning' ? '负载警告' : '正常' }}
              </span>
            </div>
            <button
              type="button"
              class="action-btn small"
              :class="{ refreshing: isRateLimitRefreshing }"
              @click="manualRefreshRateLimit"
              :disabled="isRateLimitRefreshing"
              aria-label="刷新限流数据"
            >
              {{ isRateLimitRefreshing ? '⏳ 刷新中...' : '🔄 刷新' }}
            </button>
            <button type="button" class="action-btn small danger-btn" @click="resetRateLimit" title="重置统计" aria-label="重置限流统计">🗑️ 重置</button>
          </div>
        </div>

        <div class="rate-limit-stats">
          <div class="rate-stat-item">
            <div class="rate-stat-value">{{ rateLimitStats.totalRequests }}</div>
            <div class="rate-stat-label">总请求数</div>
          </div>
          <div class="rate-stat-item">
            <div class="rate-stat-value allowed">{{ rateLimitStats.allowedRequests }}</div>
            <div class="rate-stat-label">通过请求</div>
          </div>
          <div class="rate-stat-item">
            <div class="rate-stat-value limited">{{ rateLimitStats.limitedRequests }}</div>
            <div class="rate-stat-label">拒绝请求</div>
          </div>
        </div>

        <div class="rate-limit-gauge">
          <div class="gauge-info">
            <div class="gauge-label">当前请求速率</div>
            <div class="gauge-value" :style="{ color: getRateLimitColor() }">
              {{ rateLimitStats.currentRate }} <span class="gauge-unit">req/s</span>
            </div>
          </div>
          <div class="gauge-bar-container">
            <div
              class="gauge-bar"
              :style="{
                width: `${rateLimitPercentage}%`,
                background: `linear-gradient(90deg, ${getRateLimitColor()}, ${getRateLimitColor()}88)`,
                boxShadow: `0 0 16px ${getRateLimitColor()}30`
              }"
            >
              <span v-if="rateLimitPercentage > 15" class="gauge-bar-text">
                {{ Math.round(rateLimitPercentage) }}%
              </span>
            </div>
          </div>
          <div class="gauge-threshold">
            <span>阈值: {{ rateLimitStats.limitThreshold }} req/s</span>
          </div>
        </div>

        <div class="rate-limit-history">
          <div class="history-title">
            请求历史 (最近20次)
            <span v-if="rateLimitHistory.length > 0" class="data-count">({{ rateLimitHistory.length }}条数据)</span>
            <span v-else class="data-empty">暂无数据</span>
          </div>
          <div class="history-chart">
            <div
              v-for="(item, index) in rateLimitHistory"
              :key="index"
              class="history-bar"
            >
              <div
                class="history-bar-allowed"
                :style="{ height: `${getBarHeight(item.allowed)}%`, background: themeColors.success }"
                :title="`${item.timestamp}: 允许 ${item.allowed} / 限制 ${item.limited}`"
              >
                <span class="bar-label">{{ item.allowed }}</span>
              </div>
              <div
                class="history-bar-limited"
                :style="{ height: `${getBarHeight(item.limited, true)}%`, background: themeColors.error }"
              >
                <span v-if="item.limited > 0" class="bar-label">{{ item.limited }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="isDebugEnabled" class="panel debug-panel">
      <div class="panel-header debug-panel-header">
        <h2 class="panel-title">调试信息</h2>
        <button
          type="button"
          class="action-btn small debug-toggle-btn"
          @click.stop="toggleDebug"
          :class="{ active: showDebug }"
          :aria-label="showDebug ? '隐藏调试信息' : '显示调试信息'"
        >
          {{ showDebug ? '🔒 隐藏' : '🔓 显示' }}
        </button>
      </div>
      <div v-if="showDebug" class="debug-content">
        <div class="debug-section">
          <div class="debug-section-title">🎯 意图数据</div>
          <div class="debug-item">
            <span class="debug-label">意图数量:</span>
            <span class="debug-value">{{ recentIntents.length }}</span>
          </div>
          <div class="debug-item">
            <span class="debug-label">最后刷新:</span>
            <span class="debug-value">{{ lastRefreshTime || '未更新' }}</span>
          </div>
          <div class="debug-item">
            <span class="debug-label">数据新鲜度:</span>
            <span class="debug-value" :class="{ degraded: dataFreshness === '降级' }">{{ dataFreshness }}</span>
          </div>
          <div class="debug-item">
            <span class="debug-label">请求统计:</span>
            <span class="debug-value">成功 {{ fetchCount }} / 失败 {{ errorCount }}</span>
          </div>
          <div class="debug-item">
            <span class="debug-label">设备数据:</span>
            <span class="debug-value">{{ healthStatus.length }} 台 / 在线 {{ onlineDevices }}</span>
          </div>
          <details class="debug-details">
            <summary>查看原始数据</summary>
            <pre class="debug-data">{{ JSON.stringify({ intents: recentIntents, health: healthStatus, selfHealing: selfHealingEvents }, null, 2) }}</pre>
          </details>
        </div>
        <div class="debug-divider"></div>
        <div class="debug-section">
          <div class="debug-section-title">📊 限流数据</div>
          <div class="debug-item">
            <span class="debug-label">历史数据数量:</span>
            <span class="debug-value">{{ rateLimitHistory.length }}</span>
          </div>
          <div class="debug-item">
            <span class="debug-label">最后更新时间:</span>
            <span class="debug-value">{{ lastUpdateTime || '未更新' }}</span>
          </div>
          <details class="debug-details">
            <summary>查看原始限流数据</summary>
            <pre class="debug-data">{{ JSON.stringify(rateLimitHistory.slice(0, 3), null, 2) }}</pre>
          </details>
        </div>
      </div>
    </div>
  </PageLayout>
</template>

<style scoped lang="scss">
:deep(.page-layout) {
  position: relative;
  animation: page-enter 0.5s var(--ease-out);
  min-height: 100vh;
}

.stat-card-clickable {
  cursor: pointer;
  transition: all 0.25s ease;
  backdrop-filter: blur(12px);
  will-change: transform;

  &:hover {
    transform: translateY(-2px);
    border-color: var(--color-primary-border);
    box-shadow: 0 4px 20px var(--color-primary-glow), 0 0 12px var(--color-primary-glow);

    :deep(.stat-icon) {
      animation: icon-pulse 1.2s ease-in-out infinite;
    }
  }

  &:active {
    transform: translateY(0) scale(0.98);
    transition-duration: 0.1s;
  }
}



.stat-card-skeleton {
  animation: skeleton-pulse 1.5s ease-in-out infinite;
  padding: 1.25rem;
  background: var(--gradient-glass);
  border-radius: var(--card-border-radius);
  border: var(--card-border);
  will-change: opacity;
}

.data-freshness {
  font-size: var(--font-size-xs);
  padding: var(--spacing-xs) 0.625rem;
  border-radius: var(--radius-lg);
  background: var(--color-success-bg);
  color: var(--color-success);
  transition: all 0.3s var(--ease-out);
  border: 1px solid var(--color-success-border);
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.freshness-dot {
  width: 0.375rem;
  height: 0.375rem;
  border-radius: 50%;
  background: currentColor;
  animation: freshness-pulse 2s ease-in-out infinite;
  will-change: opacity;
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

/* ===== Element Plus el-button 覆盖：毛玻璃风格 ===== */
:deep(.el-button) {
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
  color: var(--color-primary-light);
  border-radius: var(--button-radius);
  backdrop-filter: blur(8px);
  transition: all 0.25s ease;

  &:hover {
    background: var(--color-primary-hover);
    border-color: var(--color-primary-border);
    box-shadow: var(--shadow-glow-primary);
    transform: scale(1.02);
    color: var(--color-primary-light);
  }

  &:active {
    transform: scale(0.97);
  }

  &.is-disabled,
  &[disabled] {
    opacity: 0.35;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }
}

:deep(.el-button--primary) {
  background: var(--gradient-primary);
  border: 1px solid var(--color-primary-border);
  color: var(--color-primary-light);

  &:hover {
    background: var(--gradient-primary-hover);
    box-shadow: 0 0 16px var(--color-primary-glow);
  }
}

/* .action-btn uses global definition from tokens.css */

.refresh-icon {
  display: inline-block;
  transition: transform 0.3s ease;
  will-change: transform;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

.action-btn:hover .refresh-icon:not(.spinning) {
  animation: spin 0.6s linear;
}

.refresh-btn:hover:not(:disabled) .refresh-icon:not(.spinning) {
  animation: refresh-hover-spin 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes refresh-hover-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.danger-btn {
  background: var(--color-error-bg);
  color: var(--color-error-lighter);
  border-color: var(--color-error-border);
}

.danger-btn:hover:not(:disabled) {
  background: var(--color-error-hover);
  border-color: var(--color-error-border);
  box-shadow: var(--shadow-glow-error);
  color: var(--color-error-lighter);
  transform: translateY(-1px);
}

.danger-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.97);
}

.danger-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1.25rem;
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-lg);
  animation: banner-enter 0.3s var(--ease-out);
  box-shadow: var(--shadow-glow-error);
  will-change: transform, opacity;
}



.error-banner-icon { font-size: var(--font-size-lg); flex-shrink: 0; }
.error-banner-text { flex: 1; font-size: var(--font-size-sm); color: var(--color-error-light); }
.error-banner-retry {
  padding: 0.375rem 0.875rem;
  background: var(--color-error-hover);
  color: var(--color-error-light);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: var(--button-transition);
  white-space: nowrap;
  min-height: 36px;
}
.error-banner-retry:hover { background: var(--color-error-hover); box-shadow: var(--shadow-glow-error); }

.auto-refresh-select {
  padding: 0.375rem 1.75rem 0.375rem 0.625rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  outline: none;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%2394A3B8' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  min-height: 44px;
  transition: border-color 0.25s var(--ease-out), box-shadow 0.25s var(--ease-out);
}
.auto-refresh-select:focus { border-color: var(--input-border-focus); box-shadow: var(--input-shadow-focus); }
.auto-refresh-select option { background: var(--color-bg-secondary); color: var(--color-text-secondary); }

.export-wrapper {
  position: relative;
}

.export-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: var(--spacing-xs);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--radius-md);
  overflow: hidden;
  z-index: var(--z-dropdown);
  min-width: 8.75rem;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: var(--shadow-dropdown);
  animation: dropdown-enter 0.15s var(--ease-out);
  will-change: transform, opacity;
}

.export-dropdown button {
  display: block;
  width: 100%;
  padding: 0.625rem var(--spacing-md);
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  text-align: left;
  cursor: pointer;
  transition: all 0.15s var(--ease-out);
}

.export-dropdown button:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  padding-left: 1.25rem;
}

.skeleton-line {
  height: 0.875rem;
  background: var(--gradient-shimmer);
  background-size: 200% 100%;
  border-radius: var(--radius-sm);
  margin-bottom: 0.625rem;
  animation: skeleton-slide 1.5s ease-in-out infinite;
  will-change: background-position;
}

.skeleton-line.wide { width: 70%; }
.skeleton-line.narrow { width: 40%; }
.skeleton-line.medium { width: 55%; height: 1.875rem; margin-top: var(--spacing-md); }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(var(--grid-min-col), 1fr));
  gap: var(--panel-gap);
  margin-bottom: var(--panel-gap);
}

.summary-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: 0.875rem var(--spacing-lg);
  background: var(--gradient-glass);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-primary);
  margin-bottom: var(--spacing-lg);
  flex-wrap: wrap;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: var(--shadow-card);
}



.summary-item {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  cursor: default;
  padding: 0.125rem var(--spacing-xs);
  border-radius: var(--radius-sm);
  transition: background 0.2s var(--ease-out);
}

.summary-item:hover {
  background: var(--color-bg-hover);
}

.summary-icon {
  font-size: var(--font-size-base);
  transition: transform 0.3s var(--ease-spring);
}

.summary-item:hover .summary-icon {
  transform: scale(1.2);
}

.summary-label { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }

.summary-value {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.summary-value.success { color: var(--color-success); }
.summary-value.warning { color: var(--color-warning); }

.summary-divider {
  width: 1px;
  height: 1.25rem;
  background: linear-gradient(180deg, transparent, var(--color-border-secondary), transparent);
}

.content-row {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--panel-gap);
  margin-bottom: var(--panel-gap);
}

.content-row.three-col {
  grid-template-columns: 1fr 2fr;
}

/* Panel: page-specific additions only (base styles from tokens.css) */
.panel {
  box-shadow: var(--shadow-card);
}

.panel:hover {
  border-color: var(--color-border-secondary);
  box-shadow: var(--shadow-card-hover);
}



/* .panel-title, .panel-header, .panel-actions: base styles from tokens.css */
.panel-header .panel-title {
  margin-bottom: 0;
}

.filter-group {
  display: flex;
  gap: var(--spacing-xs);
}

.filter-btn {
  padding: var(--spacing-xs) 0.625rem;
  min-height: 44px;
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.25s var(--ease-out);
}

.filter-btn:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border-color: var(--color-primary-border);
}

.filter-btn.active {
  background: var(--color-primary-hover);
  color: var(--color-primary-light);
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-glow-primary);
  font-weight: var(--font-weight-medium);
}

.intent-list {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.intent-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem var(--spacing-md);
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  transition: all 0.25s var(--ease-out);
  border: 1px solid transparent;
  animation: item-enter 0.3s var(--ease-out) backwards;
  animation-delay: var(--item-delay, 0s);
  will-change: transform;
}

.intent-index {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-tertiary);
  font-family: var(--font-family-mono);
  min-width: 1.25rem;
}

.intent-item.clickable { cursor: pointer; }

.intent-item.clickable:hover {
  background: var(--color-bg-glass-strong);
  border-color: var(--color-primary-border);
  transform: translateX(4px);
  box-shadow: var(--shadow-glow-primary);
}

.intent-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex: 1;
  min-width: 0;
}

.intent-status-dot {
  width: var(--spacing-sm);
  height: var(--spacing-sm);
  border-radius: 50%;
  flex-shrink: 0;
  animation: dot-pulse 2s ease-in-out infinite;
  will-change: opacity;
}



.intent-info { min-width: 0; }

.intent-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.intent-meta {
  display: flex;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-xs);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.intent-type {
  padding: 1px 0.375rem;
  background: var(--color-primary-bg);
  border-radius: var(--radius-xs);
  color: var(--color-primary-light);
}

.intent-status-badge {
  font-size: var(--font-size-xs);
  padding: 0.1875rem var(--spacing-sm);
  border-radius: var(--radius-sm);
  border: 1px solid;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all 0.2s var(--ease-out);
}

.intent-item:hover .intent-status-badge {
  transform: scale(1.05);
  box-shadow: 0 0 8px currentColor;
}

.health-overview {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--gradient-glass-strong);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-md);
  border: 1px solid var(--color-border-primary);
  box-shadow: var(--shadow-sm);
}

.health-score-ring {
  position: relative;
  width: 5rem;
  height: 5rem;
  flex-shrink: 0;
}

.health-score-svg {
  width: 100%;
  height: 100%;
  filter: drop-shadow(0 0 10px var(--color-success-glow));
}

.health-score-arc {
  transition: stroke-dasharray 0.8s var(--ease-out);
}

.health-score-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
}

.health-score-value {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.health-score-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: 2px;
}

.health-summary-stats {
  display: flex;
  gap: 1.25rem;
}

.health-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.health-stat-num {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.health-stat-num.warn { color: var(--color-warning); }
.health-stat-num.danger { color: var(--color-error-light); }

.health-stat-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.health-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.health-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.625rem 0.75rem;
  border-radius: var(--radius-md);
  transition: all 0.25s var(--ease-out);
}

.health-item:hover {
  background: var(--color-bg-hover);
}

.health-item.health-warning {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
}

.health-ring-wrap {
  position: relative;
  width: 2.75rem;
  height: 2.75rem;
  flex-shrink: 0;
}

.health-ring-svg {
  width: 100%;
  height: 100%;
  filter: drop-shadow(0 0 6px var(--color-success-glow));
}

.health-ring-svg circle:nth-child(2) {
  transition: stroke-dasharray 0.8s var(--ease-out);
}

.health-ring-value {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  font-variant-numeric: tabular-nums;
}

.health-device-info {
  min-width: 5rem;
}

.health-name {
  display: block;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

.health-type-tag {
  display: inline-block;
  font-size: var(--font-size-xs);
  color: var(--color-primary-light);
  background: var(--color-primary-bg);
  padding: 1px 0.375rem;
  border-radius: var(--radius-xs);
  margin-top: 2px;
}

.health-resources {
  display: flex;
  gap: 0.375rem;
  margin-left: auto;
}

.resource-tag {
  font-size: var(--font-size-xs);
  font-family: var(--font-family-mono);
  color: var(--color-text-tertiary);
  padding: 0.125rem 0.375rem;
  border-radius: var(--radius-xs);
  background: var(--color-bg-hover);
  transition: all 0.2s var(--ease-out);
}

.resource-tag.danger {
  color: var(--color-error-light);
  background: var(--color-error-bg);
  font-weight: var(--font-weight-semibold);
  animation: resource-pulse 2s ease-in-out infinite;
  will-change: background;
}

@keyframes resource-pulse {
  0%, 100% { background: var(--color-error-bg); }
  50% { background: var(--color-error-hover); }
}

.healing-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.healing-item {
  display: flex;
  align-items: stretch;
  gap: 0;
  min-height: 3.75rem;
  position: relative;
}

.healing-timeline-dot {
  width: 0.75rem;
  height: 0.75rem;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: var(--spacing-xs);
  margin-left: var(--spacing-xs);
  position: relative;
  z-index: var(--z-content);
}

.healing-timeline-line {
  width: 2px;
  flex-shrink: 0;
  margin-left: 0.5625rem;
  background: var(--color-border-primary);
  transform: translateX(-0.5px);
}

.healing-item:last-child .healing-timeline-line {
  display: none;
}

.healing-content {
  flex: 1;
  padding: 0 0 var(--spacing-md) 0.875rem;
  min-width: 0;
}

.healing-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: 2px;
}

.healing-type {
  font-weight: var(--font-weight-semibold);
  color: var(--color-orange);
  font-size: var(--font-size-sm);
}

.healing-badge {
  font-size: var(--font-size-xs);
  padding: 0.125rem 0.375rem;
  border-radius: var(--radius-xs);
}

.healing-device {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: 2px;
}

.healing-action {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.healing-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: var(--spacing-xs);
}

.rate-limit-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 0.375rem 0.75rem;
  border-radius: var(--radius-lg);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.rate-limit-status.normal { background: var(--color-success-bg); color: var(--color-success); }
.rate-limit-status.warning { background: var(--color-warning-bg); color: var(--color-warning); animation: pulse-warning 1.5s ease-in-out infinite; will-change: opacity; }
.rate-limit-status.error { background: var(--color-error-bg); color: var(--color-error-light); animation: pulse-error 1s ease-in-out infinite; will-change: opacity; }

@keyframes pulse-warning { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
@keyframes pulse-error { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

.status-dot {
  width: var(--spacing-sm);
  height: var(--spacing-sm);
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 6px currentColor;
}

.rate-limit-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(var(--grid-min-col), 1fr));
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.rate-stat-item {
  text-align: center;
  padding: var(--spacing-md);
  background: var(--gradient-glass-strong);
  border-radius: var(--radius-lg);
  transition: all 0.25s var(--ease-out);
  border: 1px solid var(--color-border-primary);
  box-shadow: var(--shadow-sm);
  will-change: transform;
}

.rate-stat-item:hover {
  background: var(--color-bg-glass-strong);
  border-color: var(--color-primary-border);
  transform: translateY(-2px);
  box-shadow: var(--shadow-glow-primary);
}

.rate-stat-value { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); color: var(--color-text-primary); margin-bottom: var(--spacing-xs); font-variant-numeric: tabular-nums; }
.rate-stat-value.allowed { color: var(--color-success); }
.rate-stat-value.limited { color: var(--color-error-light); }
.rate-stat-label { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }

.rate-limit-gauge { margin-bottom: var(--spacing-lg); }

.gauge-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.gauge-label { font-size: var(--font-size-base); color: var(--color-text-tertiary); }
.gauge-value { font-size: var(--font-size-2xl); font-weight: var(--font-weight-bold); font-variant-numeric: tabular-nums; }
.gauge-unit { font-size: var(--font-size-base); font-weight: var(--font-weight-normal); color: var(--color-text-tertiary); margin-left: var(--spacing-xs); }

.gauge-bar-container {
  height: 0.875rem;
  background: var(--color-bg-quaternary);
  border-radius: 0.4375rem;
  overflow: hidden;
  position: relative;
  border: 1px solid var(--color-border-primary);
}

.gauge-bar {
  height: 100%;
  border-radius: 0.4375rem;
  transition: width 0.4s var(--ease-out), background 0.3s var(--ease-out);
  position: relative;
  min-width: 4px;
}

.gauge-bar-text {
  position: absolute;
  right: var(--spacing-sm);
  top: 50%;
  transform: translateY(-50%);
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-primary);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}

.gauge-threshold {
  margin-top: var(--spacing-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  text-align: right;
}

.rate-limit-history {
  padding-top: 1.25rem;
  border-top: 1px solid var(--color-border-primary);
}

.history-title {
  font-size: var(--font-size-base);
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.data-count {
  font-size: var(--font-size-xs);
  color: var(--color-primary-light);
  background: var(--color-primary-bg);
  padding: 0.125rem var(--spacing-sm);
  border-radius: var(--radius-md);
}

.data-empty { font-size: var(--font-size-xs); color: var(--color-warning); }

.history-chart {
  display: flex;
  gap: 0.375rem;
  align-items: flex-end;
  height: 7.5rem;
  min-height: 7.5rem;
  padding: var(--spacing-xs) 0;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  background: var(--color-bg-input);
}

.history-bar {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  min-height: 2.5rem;
}

.history-bar-allowed,
.history-bar-limited {
  border-radius: var(--radius-xs) var(--radius-xs) 0 0;
  transition: all 0.3s var(--ease-out);
  min-height: 6px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  position: relative;
  overflow: visible;
}

.history-bar-allowed {
  background: linear-gradient(180deg, var(--color-success) 0%, var(--color-success-dark, #3d9b14) 100%);
  box-shadow: 0 0 4px var(--color-success-glow);
}

.history-bar-allowed:hover {
  background: linear-gradient(180deg, var(--color-success-light) 0%, var(--color-success) 100%);
  box-shadow: 0 0 12px var(--color-success-glow);
  transform: scaleY(1.03);
  transform-origin: bottom;
}

.history-bar-limited {
  background: linear-gradient(180deg, var(--color-error) 0%, var(--color-error-dark, #d93a3c) 100%);
  box-shadow: 0 0 4px var(--color-error-glow);
}

.history-bar-limited:hover {
  background: linear-gradient(180deg, var(--color-error-light) 0%, var(--color-error) 100%);
  box-shadow: 0 0 12px var(--color-error-glow);
  transform: scaleY(1.03);
  transform-origin: bottom;
}

.bar-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-primary);
  font-weight: bold;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
  position: absolute;
  top: -0.875rem;
  white-space: nowrap;
  background: var(--color-bg-elevated);
  padding: 1px var(--spacing-xs);
  border-radius: var(--radius-xs);
  opacity: 0;
  transition: opacity 0.2s var(--ease-out);
  box-shadow: var(--shadow-sm);
}

.history-bar-allowed:hover .bar-label,
.history-bar-limited:hover .bar-label {
  opacity: 1;
}

.debug-panel {
  margin-top: var(--spacing-lg);
  background: linear-gradient(135deg, var(--color-purple-bg) 0%, var(--color-primary-bg) 100%);
  border: 1px solid var(--color-purple-border);
  box-shadow: var(--shadow-sm);
}

.debug-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0;
  padding-bottom: var(--spacing-sm);
}

.debug-content {
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-primary);
}

.debug-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) 0;
  border-bottom: 1px solid var(--color-border-primary);
}

.debug-item:last-child { border-bottom: none; }
.debug-label { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.debug-value { font-size: var(--font-size-sm); color: var(--color-text-secondary); font-weight: var(--font-weight-medium); }
.debug-value.degraded { color: var(--color-warning); }

.debug-details { margin-top: 0.75rem; }
.debug-details summary { cursor: pointer; color: var(--color-primary-light); font-size: var(--font-size-sm); padding: var(--spacing-sm) 0; }

.debug-data {
  margin: var(--spacing-sm) 0;
  padding: 0.75rem;
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  overflow-x: auto;
  max-height: 12.5rem;
  overflow-y: auto;
}

.debug-section { margin-bottom: 0.75rem; }
.debug-section:last-child { margin-bottom: 0; }

.debug-section-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  margin-bottom: 0.75rem;
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--color-border-primary);
}

.debug-divider {
  height: 1px;
  background: var(--color-border-primary);
  margin: var(--spacing-md) 0;
}

.debug-toggle-btn {
  background: var(--color-warning-bg);
  color: var(--color-warning-light);
  border-color: var(--color-warning-border);
}

.debug-toggle-btn:hover:not(:disabled) {
  background: var(--color-warning-hover);
}

.debug-toggle-btn.active {
  background: var(--color-emerald-bg);
  color: var(--color-emerald);
  border-color: var(--color-emerald-border);
}

@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .content-row {
    grid-template-columns: 1fr;
  }
  .content-row.three-col {
    grid-template-columns: 1fr;
  }
  .content-row.three-col .rate-limit-panel {
    grid-column: span 1;
  }
  .health-overview {
    flex-direction: column;
    text-align: center;
  }
  .health-summary-stats {
    justify-content: center;
  }
}

@media (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: var(--spacing-md);
  }
  .stat-card-clickable {
    font-size: var(--font-size-3xl);
  }
  .summary-bar {
    flex-wrap: wrap;
    gap: 0.625rem;
  }
  .summary-divider {
    display: none;
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .summary-bar {
    gap: 0.75rem;
  }
  .summary-divider {
    display: none;
  }
  .rate-limit-stats {
    grid-template-columns: 1fr;
  }
  .history-chart {
    height: 5rem;
    min-height: 5rem;
  }
  .stat-card-clickable {
    font-size: var(--font-size-2xl);
  }
  .filter-group {
    flex-wrap: wrap;
  }
  .panel-title {
    font-size: var(--font-size-md);
  }
  .summary-value {
    font-size: var(--font-size-md);
  }
  .summary-label {
    font-size: var(--font-size-base);
  }
  .intent-text {
    font-size: var(--font-size-base);
  }
  .intent-time {
    font-size: var(--font-size-base);
  }
  .health-stat-value {
    font-size: var(--font-size-base);
  }
  .health-stat-desc {
    font-size: var(--font-size-base);
  }
  .health-resources {
    flex-direction: column;
    gap: 2px;
  }
  .health-item {
    flex-wrap: wrap;
  }
  .health-device-info {
    min-width: 3.75rem;
  }
  .healing-content {
    min-width: 0;
  }
  .healing-header {
    flex-wrap: wrap;
  }
  .gauge-info {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-xs);
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr;
    gap: var(--spacing-sm);
  }
  .stat-card-clickable {
    font-size: var(--font-size-xl);
  }
  .stat-card-skeleton {
    padding: 0.625rem;
  }
  .content-row {
    gap: 0.75rem;
  }
  .filter-group {
    gap: 0.375rem;
  }
  .filter-btn {
    min-height: 2.75rem;
    font-size: var(--font-size-xs);
    padding: var(--spacing-sm) 0.75rem;
  }
  .intent-item {
    padding: 0.625rem 0.75rem;
  }
  .health-bar-track {
    height: var(--spacing-sm);
  }
  .panel {
    padding: 0.75rem;
  }
  .panel-title {
    font-size: var(--font-size-md);
  }
  .stat-card-clickable {
    font-size: var(--font-size-sm);
  }
  .summary-item {
    min-width: auto;
  }
  .summary-bar {
    padding: 0.625rem var(--spacing-md);
  }
  .rate-limit-stats {
    grid-template-columns: 1fr;
    gap: var(--spacing-sm);
  }
  .rate-stat-item {
    padding: 0.75rem;
  }
  .rate-stat-value {
    font-size: var(--font-size-2xl);
  }
  .history-chart {
    height: 3.75rem;
    min-height: 3.75rem;
  }
  .health-overview {
    flex-direction: column;
    text-align: center;
  }
  .health-summary-stats {
    justify-content: center;
  }
}

@media (prefers-reduced-motion: reduce) {
  .stat-card-clickable:hover {
    transform: none;
  }

  .health-score-arc {
    transition: none;
  }

  .health-ring-svg circle:nth-child(2) {
    transition: none;
  }

  .intent-item {
    animation: none;
  }

  .panel {
    animation: none;
  }

  .summary-bar {
    animation: none;
  }

  .stat-card-skeleton {
    animation: none;
  }

  .skeleton-line {
    animation: none;
  }

  .freshness-dot {
    animation: none;
  }

  .intent-status-dot {
    animation: none;
  }

  .resource-tag.danger {
    animation: none;
  }

  .rate-limit-status.warning,
  .rate-limit-status.error {
    animation: none;
  }

  .refresh-icon.spinning {
    animation: none;
  }

  .stat-card-clickable:hover :deep(.stat-icon) {
    animation: none;
  }

  .export-dropdown {
    animation: none;
  }
}
</style>
