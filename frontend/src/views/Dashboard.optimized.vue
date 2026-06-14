<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api, ApiError } from '../utils/api'
import { cache, cacheKeys } from '../utils/cache'
import { useAppStore } from '../stores/app'

interface Stat {
  label: string
  value: number
  unit: string
  color: string
  trend: 'up' | 'down' | 'stable'
  trendValue: number
  historyData: number[]
}

interface Intent {
  id: string
  name: string
  status: string
  device: string
  time: string
}

interface DeviceHealth {
  name: string
  health: number
  status: string
}

interface RateLimitData {
  timestamp: string
  requests: number
  allowed: number
  limited: number
}

const appStore = useAppStore()

const stats = ref<Stat[]>([
  { 
    label: '活跃意图', 
    value: 0, 
    unit: '个', 
    color: '#165DFF',
    trend: 'up',
    trendValue: 12,
    historyData: [18, 20, 22, 19, 24, 20, 22, 24]
  },
  { 
    label: '在线设备', 
    value: 156, 
    unit: '台', 
    color: '#52C41A',
    trend: 'up',
    trendValue: 5,
    historyData: [148, 150, 152, 151, 153, 154, 155, 156]
  },
  { 
    label: '自愈事件', 
    value: 0, 
    unit: '次', 
    color: '#FF7D00',
    trend: 'down',
    trendValue: 8,
    historyData: [12, 11, 10, 9, 8, 7, 6, 8]
  },
  { 
    label: '待审批', 
    value: 0, 
    unit: '项', 
    color: '#FF4D4F',
    trend: 'stable',
    trendValue: 0,
    historyData: [3, 2, 3, 2, 3, 3, 2, 3]
  }
])

// API限流数据
const rateLimitStats = ref({
  totalRequests: 0,
  allowedRequests: 0,
  limitedRequests: 0,
  limitThreshold: 1000,
  currentRate: 0
})

const rateLimitHistory = ref<RateLimitData[]>([])
let rateLimitInterval: number | null = null
let handleDataUpdate: (() => void) | null = null
const isRefreshing = ref(false)
const lastRefreshTime = ref('')

const recentIntents = ref<Intent[]>([])
const healthStatus = ref<DeviceHealth[]>([
  { name: '核心路由器', health: 98, status: 'normal' },
  { name: '汇聚交换机', health: 92, status: 'normal' },
  { name: '防火墙集群', health: 87, status: 'warning' },
  { name: '接入交换机', health: 95, status: 'normal' }
])

const fetchDashboardData = async () => {
  console.log('========== fetchDashboardData called ==========')
  const now = new Date()
  lastRefreshTime.value = now.toLocaleTimeString()
  isRefreshing.value = true
  
  try {
    // 使用缓存包装API请求
    const result = await cache.wrap(
      cacheKeys.intents.list,
      () => api.get('/intents/'),
      { ttl: 10000 } // 10秒缓存
    )
    
    if (result.status === 'success') {
      const intents = result.data
      
      // 更新统计数据
      const activeIntentsCount = intents.length
      const pendingIntentsCount = intents.filter((i: any) => i.approval_status === 'pending').length
      
      stats.value = [
        { ...stats.value[0], value: activeIntentsCount },
        { ...stats.value[1], value: stats.value[1].value },
        { ...stats.value[2], value: stats.value[2].value },
        { ...stats.value[3], value: pendingIntentsCount }
      ]
      
      // 更新最近意图列表
      const sortedIntents = [...intents].sort((a: any, b: any) => b.id - a.id)
      const newIntents = sortedIntents.slice(0, 4).map((item: any) => ({
        id: `INT-${String(item.id).padStart(3, '0')}`,
        name: item.intent_name || item.user_input || '未命名意图',
        status: item.approval_status === 'approved' ? 'completed' : 
                item.approval_status === 'pending' ? 'pending' : 'running',
        device: '系统',
        time: formatTime(item.created_at)
      }))
      
      recentIntents.value = newIntents
    } else {
      loadMockData()
    }
  } catch (error) {
    console.error('获取指挥舱数据失败:', error)
    if (error instanceof ApiError) {
      console.error(`API错误: ${error.message} (${error.status})`)
    }
    loadMockData()
  } finally {
    isRefreshing.value = false
  }
}

const formatTime = (dateStr: string): string => {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)
  
  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins}分钟前`
  if (diffHours < 24) return `${diffHours}小时前`
  return `${diffDays}天前`
}

const loadMockData = () => {
  recentIntents.value = [
    { id: 'INT-001', name: '带宽保障-视频会议', status: 'running', device: 'Switch-A1', time: '10分钟前' },
    { id: 'INT-002', name: 'ACL规则更新', status: 'completed', device: 'Firewall-B1', time: '30分钟前' },
    { id: 'INT-003', name: 'QoS策略优化', status: 'pending', device: 'Router-C1', time: '1小时前' },
    { id: 'INT-004', name: '链路冗余配置', status: 'running', device: 'Switch-A2', time: '2小时前' }
  ]
  stats.value[0].value = 24
  stats.value[2].value = 8
  stats.value[3].value = 3
}

// API限流监控函数
const updateRateLimitData = async () => {
  try {
    const result = await api.get('/rate-limit/simulate')
    
    if (result.status === 'success') {
      rateLimitStats.value.totalRequests += result.requests
      rateLimitStats.value.allowedRequests += result.allowed
      rateLimitStats.value.limitedRequests += result.limited
      rateLimitStats.value.currentRate = result.requests
      
      const now = new Date()
      rateLimitHistory.value.push({
        timestamp: now.toLocaleTimeString(),
        requests: result.requests,
        allowed: result.allowed,
        limited: result.limited
      })
      
      if (rateLimitHistory.value.length > 20) {
        rateLimitHistory.value = rateLimitHistory.value.slice(-20)
      }
    }
  } catch (error) {
    console.error('更新限流数据失败:', error)
    // 使用模拟数据，但确保历史记录不为空
    if (rateLimitHistory.value.length === 0) {
      loadMockRateLimitData()
    }
    const newRequests = Math.floor(Math.random() * 150) + 50
    const limitRate = Math.random() > 0.85 ? 0 : Math.floor(Math.random() * 20)
    
    rateLimitStats.value.totalRequests += newRequests
    rateLimitStats.value.allowedRequests += newRequests - limitRate
    rateLimitStats.value.limitedRequests += limitRate
    rateLimitStats.value.currentRate = newRequests
    
    const now = new Date()
    rateLimitHistory.value.push({
      timestamp: now.toLocaleTimeString(),
      requests: newRequests,
      allowed: newRequests - limitRate,
      limited: limitRate
    })
    
    if (rateLimitHistory.value.length > 20) {
      rateLimitHistory.value = rateLimitHistory.value.slice(-20)
    }
  }
}

// 从后端加载限流数据
const loadRateLimitData = async () => {
  try {
    console.log('正在加载限流历史数据...')
    const result = await api.get('/rate-limit/status')
    
    if (result.status === 'success') {
      rateLimitStats.value = {
        totalRequests: result.data.total_requests,
        allowedRequests: result.data.allowed_requests,
        limitedRequests: result.data.limited_requests,
        limitThreshold: result.data.limit_threshold,
        currentRate: result.data.current_rate
      }
      
      if (result.history && result.history.length > 0) {
        rateLimitHistory.value = result.history.map((item: any) => ({
          timestamp: new Date(item.timestamp).toLocaleTimeString(),
          requests: item.requests,
          allowed: item.allowed,
          limited: item.limited
        }))
        console.log('加载了', rateLimitHistory.value.length, '条历史记录')
      } else {
        console.warn('历史记录为空，加载初始数据')
        loadMockRateLimitData()
      }
    }
  } catch (error) {
    console.error('加载限流数据失败:', error)
    loadMockRateLimitData()
  }
}

// 加载模拟限流数据
const loadMockRateLimitData = () => {
  const now = new Date()
  rateLimitHistory.value = []
  for (let i = 0; i < 20; i++) {
    const time = new Date(now.getTime() - (19 - i) * 5000)
    const requests = Math.floor(Math.random() * 100) + 50
    const limited = Math.random() > 0.8 ? Math.floor(Math.random() * 20) : 0
    rateLimitHistory.value.push({
      timestamp: time.toLocaleTimeString(),
      requests: requests,
      allowed: requests - limited,
      limited: limited
    })
  }
  console.log('加载了模拟限流数据')
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
  if (status === 'error') return '#FF4D4F'
  if (status === 'warning') return '#FAAD14'
  return '#52C41A'
}

const generateChartPoints = (data: number[], color: string) => {
  if (!data || data.length === 0) return ''
  
  const maxVal = Math.max(...data)
  const minVal = Math.min(...data)
  const range = maxVal - minVal || 1
  
  const points = data.map((val, index) => {
    const x = (index / (data.length - 1)) * 100
    const y = 30 - ((val - minVal) / range) * 25
    return `${x},${y}`
  })
  
  return points.join(' ')
}

const generateChartArea = (data: number[], color: string) => {
  if (!data || data.length === 0) return ''
  
  const maxVal = Math.max(...data)
  const minVal = Math.min(...data)
  const range = maxVal - minVal || 1
  
  const points = data.map((val, index) => {
    const x = (index / (data.length - 1)) * 100
    const y = 30 - ((val - minVal) / range) * 25
    return `${x},${y}`
  })
  
  const firstX = 0
  const lastX = 100
  return `M ${points[0]} L ${points.slice(1).join(' L ')} L ${lastX},30 L ${firstX},30 Z`
}

onMounted(async () => {
  console.log('Dashboard mounted, initializing...')
  
  await loadRateLimitData()
  await fetchDashboardData()
  
  handleDataUpdate = () => {
    console.log('Data update event received, refreshing data...')
    fetchDashboardData()
  }
  
  window.addEventListener('dashboardDataUpdated', handleDataUpdate)
  window.addEventListener('auditLogsUpdated', handleDataUpdate)
  
  setInterval(() => {
    fetchDashboardData()
  }, 5000)
  
  rateLimitInterval = window.setInterval(updateRateLimitData, 5000)
  
  setTimeout(() => {
    for (let i = 0; i < 5; i++) {
      updateRateLimitData()
    }
  }, 1000)
})

onUnmounted(() => {
  if (rateLimitInterval !== null) {
    clearInterval(rateLimitInterval)
  }
  if (handleDataUpdate) {
    window.removeEventListener('dashboardDataUpdated', handleDataUpdate)
    window.removeEventListener('auditLogsUpdated', handleDataUpdate)
  }
})
</script>

<template>
  <div class="dashboard">
    <h1 class="page-title">指挥舱概览</h1>
    
    <div class="stats-grid">
      <div
        v-for="stat in stats"
        :key="stat.label"
        class="stat-card"
      >
        <div class="stat-top-row">
          <div class="stat-icon" :style="{ background: `${stat.color}20`, color: stat.color }">
            {{ stat.label === '活跃意图' ? '🎯' : stat.label === '在线设备' ? '🖥️' : stat.label === '自愈事件' ? '🛡️' : '📋' }}
          </div>
          <div class="stat-trend" :class="stat.trend">
            <span class="trend-arrow">
              {{ stat.trend === 'up' ? '↑' : stat.trend === 'down' ? '↓' : '→' }}
            </span>
            <span class="trend-value">{{ stat.trendValue > 0 ? '+' : '' }}{{ stat.trendValue }}%</span>
          </div>
        </div>
        <div class="stat-content">
          <div class="stat-value">
            {{ stat.value }}<span class="stat-unit">{{ stat.unit }}</span>
          </div>
          <div class="stat-label">{{ stat.label }}</div>
        </div>
        <svg class="stat-chart" viewBox="0 0 100 30" preserveAspectRatio="none">
          <defs>
            <linearGradient :id="'grad-' + stat.label" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" :style="{ stopColor: stat.color, stopOpacity: '0.3' }" />
              <stop offset="100%" :style="{ stopColor: stat.color, stopOpacity: '0' }" />
            </linearGradient>
          </defs>
          <path
            :d="generateChartArea(stat.historyData, stat.color)"
            :fill="`url(#grad-${stat.label})`"
          />
          <polyline
            :points="generateChartPoints(stat.historyData, stat.color)"
            fill="none"
            :stroke="stat.color"
            stroke-width="2"
            stroke-linecap="round"
          />
        </svg>
      </div>
    </div>

    <div class="content-grid">
      <div class="panel">
        <div class="panel-header">
          <h2 class="panel-title">最近意图执行</h2>
          <div class="header-actions">
            <span v-if="lastRefreshTime" class="last-refresh-time">最后刷新: {{ lastRefreshTime }}</span>
            <button
              class="refresh-button"
              :class="{ 'refreshing': isRefreshing }"
              :disabled="isRefreshing"
              @click="fetchDashboardData"
            >
              <span v-if="isRefreshing">⏳</span>
              <span v-else>🔄</span>
              {{ isRefreshing ? '刷新中...' : '刷新' }}
            </button>
          </div>
        </div>
        <div class="intent-list">
          <div
            v-for="intent in recentIntents"
            :key="intent.id"
            class="intent-item"
          >
            <div class="intent-info">
              <div class="intent-id">{{ intent.id }}</div>
              <div class="intent-name">{{ intent.name }}</div>
            </div>
            <div class="intent-meta">
              <span class="intent-device">{{ intent.device }}</span>
              <span class="intent-status" :class="intent.status">
                {{ intent.status === 'completed' ? '已完成' : intent.status === 'pending' ? '待审批' : '执行中' }}
              </span>
            </div>
            <div class="intent-time">{{ intent.time }}</div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2 class="panel-title">设备健康状态</h2>
        </div>
        <div class="health-list">
          <div
            v-for="(device, index) in healthStatus"
            :key="index"
            class="health-item"
          >
            <div class="health-info">
              <div class="health-name">{{ device.name }}</div>
              <div class="health-bar-wrapper">
                <div class="health-bar">
                  <div
                    class="health-bar-fill"
                    :class="device.status"
                    :style="{ width: `${device.health}%` }"
                  ></div>
                </div>
                <span class="health-value">{{ device.health }}%</span>
              </div>
            </div>
            <div class="health-status-indicator" :class="device.status">
              {{ device.status === 'normal' ? '正常' : device.status === 'warning' ? '警告' : '异常' }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="rate-limit-history panel">
      <div class="panel-header">
        <h2 class="history-title">请求历史 (最近20次)</h2>
      </div>
      <div class="history-chart">
        <div
          v-for="(item, index) in rateLimitHistory"
          :key="index"
          class="history-bar"
        >
          <div
            class="history-bar-allowed"
            :style="{
              height: `${(item.allowed / 200) * 100}%`,
              background: 'var(--color-success)'
            }"
            :title="`${item.timestamp}: 允许 ${item.allowed} / 限制 ${item.limited}`"
          ></div>
          <div
            class="history-bar-limited"
            :style="{
              height: `${(item.limited / 200) * 100}%`,
              background: 'var(--color-error)'
            }"
          ></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  padding: var(--spacing-lg);
  max-width: 1400px;
  margin: 0 auto;
}

.page-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-xl);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-xl);
}

.stat-card {
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border-primary);
  position: relative;
  overflow: hidden;
}

.stat-top-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-md);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.stat-trend {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: var(--radius-xs);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.stat-trend.up {
  background: rgba(82, 196, 26, 0.1);
  color: var(--color-success);
}

.stat-trend.down {
  background: rgba(255, 77, 79, 0.1);
  color: var(--color-error);
}

.stat-trend.stable {
  background: var(--color-bg-quaternary);
  color: var(--color-text-tertiary);
}

.stat-content {
  position: relative;
  z-index: 1;
}

.stat-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-xs);
}

.stat-unit {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  font-weight: var(--font-weight-normal);
  margin-left: var(--spacing-xs);
}

.stat-label {
  font-size: var(--font-size-base);
  color: var(--color-text-tertiary);
}

.stat-chart {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 60px;
  opacity: 0.6;
}

.content-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-xl);
}

.panel {
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border-primary);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
}

.panel-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.last-refresh-time {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.refresh-button {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-quaternary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-normal);
  font-size: var(--font-size-sm);
}

.refresh-button:hover:not(:disabled) {
  background: var(--color-primary-bg);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.refresh-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.refresh-button.refreshing {
  animation: pulse 1s ease-in-out infinite;
}

.intent-list,
.health-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.intent-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md);
  background: var(--color-bg-quaternary);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-primary);
  transition: all var(--transition-normal);
}

.intent-item:hover {
  border-color: var(--color-primary);
  transform: translateX(4px);
}

.intent-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.intent-id {
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary);
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
}

.intent-name {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

.intent-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.intent-device {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.intent-status {
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.intent-status.completed {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.intent-status.pending {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.intent-status.running {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.intent-time {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.health-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md);
  background: var(--color-bg-quaternary);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-primary);
}

.health-info {
  flex: 1;
}

.health-name {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
  margin-bottom: var(--spacing-sm);
}

.health-bar-wrapper {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.health-bar {
  flex: 1;
  height: 8px;
  background: var(--color-bg-primary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.health-bar-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width var(--transition-normal);
}

.health-bar-fill.normal {
  background: linear-gradient(90deg, var(--color-success), #73d13d);
}

.health-bar-fill.warning {
  background: linear-gradient(90deg, var(--color-warning), #ffc53d);
}

.health-bar-fill.error {
  background: linear-gradient(90deg, var(--color-error), #ff7875);
}

.health-value {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  font-family: var(--font-family-mono);
  min-width: 40px;
  text-align: right;
}

.health-status-indicator {
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.health-status-indicator.normal {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.health-status-indicator.warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.rate-limit-history {
  margin-top: var(--spacing-xl);
}

.history-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-lg);
}

.history-chart {
  display: flex;
  gap: var(--spacing-xs);
  align-items: flex-end;
  height: 150px;
  padding: var(--spacing-sm) 0;
}

.history-bar {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  position: relative;
}

.history-bar-allowed,
.history-bar-limited {
  width: 100%;
  border-radius: var(--radius-xs) var(--radius-xs) 0 0;
  transition: height var(--transition-normal);
  min-height: 2px;
}

.history-bar-limited {
  position: absolute;
  bottom: 0;
}

@media (max-width: 768px) {
  .dashboard {
    padding: var(--spacing-md);
  }
  
  .stats-grid {
    grid-template-columns: 1fr;
  }
  
  .content-grid {
    grid-template-columns: 1fr;
  }
  
  .intent-item {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }
  
  .intent-meta {
    width: 100%;
    justify-content: space-between;
  }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
</style>
