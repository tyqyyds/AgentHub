<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, apiClient } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'
import { useAuthStore } from '@/stores/auth'
import { useWebSocket } from '@/composables/useWebSocket'

const authStore = useAuthStore()
const canWrite = computed(() => authStore.userRole !== 'viewer')

interface SLAPrediction {
  id: string
  intent_id: string
  sla_status: 'safe' | 'at_risk' | 'violated'
  violation_probability: number
  confidence: number
  predicted_time: string
  metrics_forecast: Record<string, number>
  created_at: string
}

interface SLAAlert {
  id: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  message: string
  time: string
  intent_id?: string
}

interface DynamicInterval {
  intent_id: string
  current_interval: number
  base_interval: number
  adjusted_reason: string
}

interface SLADashboard {
  total_predictions: number
  safe_count: number
  at_risk_count: number
  violated_count: number
  avg_confidence: number
  last_evaluation: string
}

const isLoading = ref(true)
const isRefreshing = ref(false)
const isMockData = ref(false)
const lastRefreshTime = ref('')
const dataFreshness = ref('实时')

const predictions = ref<SLAPrediction[]>([])
const alerts = ref<SLAAlert[]>([])
const dynamicIntervals = ref<DynamicInterval[]>([])
const dashboard = ref<SLADashboard | null>(null)

const filterStatus = ref<string>('all')
const showPredictModal = ref(false)
const predictIntentId = ref('')
const isPredicting = ref(false)

let pollTimer: number | null = null

const stats = computed(() => {
  const total = predictions.value.length
  const safe = predictions.value.filter(p => p.sla_status === 'safe').length
  const atRisk = predictions.value.filter(p => p.sla_status === 'at_risk').length
  const violated = predictions.value.filter(p => p.sla_status === 'violated').length
  const avgConf = total > 0
    ? Math.round(predictions.value.reduce((s, p) => s + p.confidence, 0) / total * 100)
    : 0
  return { total, safe, atRisk, violated, avgConf }
})

const filteredPredictions = computed(() => {
  if (filterStatus.value === 'all') return predictions.value
  return predictions.value.filter(p => p.sla_status === filterStatus.value)
})

const statusFilterOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'safe', label: '安全' },
  { value: 'at_risk', label: '有风险' },
  { value: 'violated', label: '已违反' }
]

const getStatusText = (status: string) => {
  const map: Record<string, string> = { safe: '安全', at_risk: '有风险', violated: '已违反' }
  return map[status] || status
}

const getStatusColor = (status: string) => {
  const map: Record<string, string> = { safe: 'var(--color-success)', at_risk: 'var(--color-orange)', violated: 'var(--color-error)' }
  return map[status] || 'var(--color-text-tertiary)'
}

const getStatusBg = (status: string) => {
  const map: Record<string, string> = { safe: 'var(--color-success-glow)', at_risk: 'var(--color-orange-bg)', violated: 'var(--color-error-glow)' }
  return map[status] || 'var(--color-bg-hover)'
}

const getSeverityText = (severity: string) => {
  const map: Record<string, string> = { critical: '严重', high: '高危', medium: '中危', low: '低危' }
  return map[severity] || severity
}

const getSeverityColor = (severity: string) => {
  const map: Record<string, string> = { critical: 'var(--color-error)', high: 'var(--color-error-light)', medium: 'var(--color-warning)', low: 'var(--color-success)' }
  return map[severity] || 'var(--color-text-tertiary)'
}

const formatTime = (dateStr: string): string => {
  if (!dateStr) return '--'
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  return date.toLocaleString('zh-CN')
}

const fetchPredictions = async (showLoading = false) => {
  if (showLoading) isRefreshing.value = true
  try {
    const data = await apiClient.get(api.sla.predictions)
    if (data.data) {
      predictions.value = Array.isArray(data.data) ? data.data : (data.data.items || [])
      isMockData.value = false
    }
  } catch {
    loadMockData()
    isMockData.value = true
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

const fetchAlerts = async () => {
  try {
    const data = await apiClient.get(api.sla.alerts)
    if (data.data) {
      alerts.value = Array.isArray(data.data) ? data.data : (data.data.items || [])
    }
  } catch {
    loadAlertsMockData()
  }
}

const fetchDynamicIntervals = async () => {
  try {
    const data = await apiClient.get(api.sla.dynamicIntervals)
    if (data.data) {
      dynamicIntervals.value = data.data || {}
    }
  } catch {
    loadIntervalsMockData()
  }
}

const fetchDashboard = async () => {
  try {
    const data = await apiClient.get(api.sla.dashboard)
    if (data.data) {
      dashboard.value = data.data || null
    }
  } catch {
    dashboard.value = null
  }
}

const fetchAll = async (showLoading = false) => {
  lastRefreshTime.value = new Date().toLocaleTimeString()
  await Promise.all([
    fetchPredictions(showLoading),
    fetchAlerts(),
    fetchDynamicIntervals(),
    fetchDashboard()
  ])
}

const runPrediction = async () => {
  if (!predictIntentId.value.trim()) {
    showToast('请输入意图ID', 'error')
    return
  }
  isPredicting.value = true
  try {
    await apiClient.post(api.sla.predict(predictIntentId.value.trim()))
    showToast('预测任务已触发', 'success')
    showPredictModal.value = false
    predictIntentId.value = ''
    await fetchPredictions()
  } catch {
    showToast('预测触发失败', 'error')
  } finally {
    isPredicting.value = false
  }
}

const manualRefresh = async () => {
  isRefreshing.value = true
  try {
    await fetchAll(true)
    showToast('数据已刷新', 'success')
  } catch {
    showToast('刷新失败', 'error')
  }
}

const exportJSON = () => {
  const payload = {
    exportTime: new Date().toISOString(),
    predictions: predictions.value,
    alerts: alerts.value,
    dynamicIntervals: dynamicIntervals.value,
    dashboard: dashboard.value
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `sla-prediction_${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
  showToast('数据已导出为 JSON', 'success')
}

const loadMockData = () => {
  predictions.value = [
    {
      id: 'pred_001', intent_id: 'INT-2024-001', sla_status: 'safe',
      violation_probability: 0.08, confidence: 0.95,
      predicted_time: new Date(Date.now() + 3600000).toISOString(),
      metrics_forecast: { bandwidth: 180, latency: 12, packet_loss: 0.01 },
      created_at: new Date(Date.now() - 300000).toISOString()
    },
    {
      id: 'pred_002', intent_id: 'INT-2024-002', sla_status: 'at_risk',
      violation_probability: 0.62, confidence: 0.87,
      predicted_time: new Date(Date.now() + 1800000).toISOString(),
      metrics_forecast: { bandwidth: 250, latency: 45, packet_loss: 0.8 },
      created_at: new Date(Date.now() - 600000).toISOString()
    },
    {
      id: 'pred_003', intent_id: 'INT-2024-003', sla_status: 'violated',
      violation_probability: 0.94, confidence: 0.92,
      predicted_time: new Date(Date.now() - 600000).toISOString(),
      metrics_forecast: { bandwidth: 320, latency: 85, packet_loss: 3.2 },
      created_at: new Date(Date.now() - 900000).toISOString()
    },
    {
      id: 'pred_004', intent_id: 'INT-2024-004', sla_status: 'safe',
      violation_probability: 0.12, confidence: 0.91,
      predicted_time: new Date(Date.now() + 7200000).toISOString(),
      metrics_forecast: { bandwidth: 150, latency: 8, packet_loss: 0.005 },
      created_at: new Date(Date.now() - 1200000).toISOString()
    },
    {
      id: 'pred_005', intent_id: 'INT-2024-005', sla_status: 'at_risk',
      violation_probability: 0.55, confidence: 0.78,
      predicted_time: new Date(Date.now() + 900000).toISOString(),
      metrics_forecast: { bandwidth: 280, latency: 38, packet_loss: 0.5 },
      created_at: new Date(Date.now() - 1500000).toISOString()
    },
    {
      id: 'pred_006', intent_id: 'INT-2024-006', sla_status: 'safe',
      violation_probability: 0.05, confidence: 0.97,
      predicted_time: new Date(Date.now() + 10800000).toISOString(),
      metrics_forecast: { bandwidth: 120, latency: 5, packet_loss: 0.002 },
      created_at: new Date(Date.now() - 1800000).toISOString()
    }
  ]
}

const loadAlertsMockData = () => {
  alerts.value = [
    { id: 'alert_001', severity: 'critical', message: '意图 INT-2024-003 SLA已违反，延迟超过阈值85ms', time: new Date(Date.now() - 300000).toISOString(), intent_id: 'INT-2024-003' },
    { id: 'alert_002', severity: 'high', message: '意图 INT-2024-002 SLA违反概率62%，预计30分钟内违反', time: new Date(Date.now() - 600000).toISOString(), intent_id: 'INT-2024-002' },
    { id: 'alert_003', severity: 'medium', message: '意图 INT-2024-005 带宽使用率持续升高，需关注', time: new Date(Date.now() - 900000).toISOString(), intent_id: 'INT-2024-005' },
    { id: 'alert_004', severity: 'low', message: '全局SLA评估间隔已动态调整为45秒', time: new Date(Date.now() - 1200000).toISOString() }
  ]
}

const loadIntervalsMockData = () => {
  dynamicIntervals.value = [
    { intent_id: 'INT-2024-001', current_interval: 60, base_interval: 60, adjusted_reason: '状态稳定，维持默认间隔' },
    { intent_id: 'INT-2024-002', current_interval: 30, base_interval: 60, adjusted_reason: '风险升高，缩短评估间隔' },
    { intent_id: 'INT-2024-003', current_interval: 15, base_interval: 60, adjusted_reason: '已违反，最高频率监控' },
    { intent_id: 'INT-2024-004', current_interval: 60, base_interval: 60, adjusted_reason: '状态稳定，维持默认间隔' },
    { intent_id: 'INT-2024-005', current_interval: 30, base_interval: 60, adjusted_reason: '风险升高，缩短评估间隔' },
    { intent_id: 'INT-2024-006', current_interval: 90, base_interval: 60, adjusted_reason: '低风险，延长评估间隔' }
  ]
}

const handleKeydown = (e: KeyboardEvent) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
    e.preventDefault()
    manualRefresh()
  }
  if (e.key === 'Escape') {
    showPredictModal.value = false
  }
}

onMounted(() => {
  fetchAll(true)
  pollTimer = window.setInterval(() => {
    if (!document.hidden) fetchAll(false)
  }, 30000)
  document.addEventListener('keydown', handleKeydown)

  // Listen for real-time SLA alerts via WebSocket
  const { on } = useWebSocket()
  const unsubSlaAlert = on('sla_alert' as any, (msg: any) => {
    showToast(`SLA告警: ${msg.data?.intent_name || '意图'} - ${msg.data?.metric || '指标'}偏离`, 'warning')
    fetchDashboard() // Refresh dashboard on SLA change
  })
  const unsubNotification = on('proactive_notification' as any, (msg: any) => {
    if (msg.data?.type === 'sla_warning') {
      fetchDashboard()
    }
  })
  // Store unsubscribers for cleanup
  ;(window as any).__sla_unsubs = [unsubSlaAlert, unsubNotification]
})

onUnmounted(() => {
  if (pollTimer !== null) clearInterval(pollTimer)
  document.removeEventListener('keydown', handleKeydown)
  // Cleanup WebSocket listeners
  const unsubs = (window as any).__sla_unsubs
  if (unsubs) unsubs.forEach((fn: () => void) => fn())
})
</script>

<template>
  <div class="sla-prediction" :class="{ loading: isLoading }">
    <div class="sla-bg">
      <div class="bg-grid"></div>
      <div class="bg-glow glow-1"></div>
      <div class="bg-glow glow-2"></div>
    </div>

    <!-- Header -->
    <div class="sla-header">
      <div class="header-left">
        <h1 class="page-title">SLA 预测监控</h1>
        <p class="page-subtitle">智能SLA违反预测、动态评估间隔与实时告警</p>
      </div>
      <div class="header-actions">
        <span class="data-freshness" :class="{ degraded: dataFreshness === '降级' }">
          <span class="freshness-dot"></span>
          {{ dataFreshness }}
        </span>
        <span class="last-refresh" v-if="lastRefreshTime">{{ lastRefreshTime }}</span>
        <button type="button" class="action-btn" @click="exportJSON" title="导出 JSON" aria-label="导出 JSON">
          📥 导出
        </button>
        <button
          type="button"
          class="action-btn refresh-btn"
          :class="{ refreshing: isRefreshing }"
          @click="manualRefresh"
          :disabled="isRefreshing"
          title="刷新数据"
          aria-label="刷新数据"
        >
          <span class="refresh-icon" :class="{ spinning: isRefreshing }">🔄</span>
          {{ isRefreshing ? '刷新中...' : '刷新' }}
        </button>
        <button type="button" v-if="canWrite" class="predict-btn" @click="showPredictModal = true" title="运行预测" aria-label="运行预测">
          🎯 运行预测
        </button>
      </div>
    </div>

    <!-- Stats Bar -->
    <div class="stats-bar">
      <div class="stat-item">
        <span class="stat-icon">📊</span>
        <div class="stat-content">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">总预测</div>
        </div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <span class="stat-icon icon-warning">⚠️</span>
        <div class="stat-content">
          <div class="stat-value at-risk">{{ stats.atRisk }}</div>
          <div class="stat-label">有风险</div>
        </div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <span class="stat-icon icon-error">🔴</span>
        <div class="stat-content">
          <div class="stat-value violated">{{ stats.violated }}</div>
          <div class="stat-label">已违反</div>
        </div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <span class="stat-icon icon-success">✅</span>
        <div class="stat-content">
          <div class="stat-value safe">{{ stats.safe }}</div>
          <div class="stat-label">安全</div>
        </div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <span class="stat-icon icon-primary">🎯</span>
        <div class="stat-content">
          <div class="stat-value">{{ stats.avgConf }}%</div>
          <div class="stat-label">平均置信度</div>
        </div>
      </div>
    </div>

    <!-- SLA Dashboard Summary -->
    <div v-if="dashboard" class="dashboard-summary">
      <div class="summary-header">
        <h2 class="summary-title">📋 SLA 仪表盘</h2>
        <span class="summary-time">最后评估: {{ formatTime(dashboard.last_evaluation) }}</span>
      </div>
      <div class="summary-grid">
        <div class="summary-card">
          <div class="summary-card-value">{{ dashboard.total_predictions }}</div>
          <div class="summary-card-label">预测总数</div>
        </div>
        <div class="summary-card safe">
          <div class="summary-card-value">{{ dashboard.safe_count }}</div>
          <div class="summary-card-label">安全</div>
        </div>
        <div class="summary-card at-risk">
          <div class="summary-card-value">{{ dashboard.at_risk_count }}</div>
          <div class="summary-card-label">有风险</div>
        </div>
        <div class="summary-card violated">
          <div class="summary-card-value">{{ dashboard.violated_count }}</div>
          <div class="summary-card-label">已违反</div>
        </div>
        <div class="summary-card confidence">
          <div class="summary-card-value">{{ Math.round(dashboard.avg_confidence * 100) }}%</div>
          <div class="summary-card-label">平均置信度</div>
        </div>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <div class="filter-left">
        <span class="filter-label">SLA 状态筛选:</span>
        <div class="filter-buttons">
          <button
            v-for="opt in statusFilterOptions"
            :key="opt.value"
            type="button"
            :class="['filter-btn', { active: filterStatus === opt.value }]"
            @click="filterStatus = opt.value"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>
      <div class="filter-right">
        <span class="auto-refresh-hint">🔄 自动刷新: 30秒</span>
      </div>
    </div>

    <!-- Predictions Table -->
    <div class="predictions-section">
      <div class="section-header">
        <h2 class="section-title">🧠 预测结果</h2>
        <span class="section-count">{{ filteredPredictions.length }} 条记录</span>
      </div>

      <div v-if="isLoading" class="table-skeleton">
        <div v-for="i in 3" :key="i" class="skeleton-row">
          <div class="skeleton-cell wide"></div>
          <div class="skeleton-cell medium"></div>
          <div class="skeleton-cell narrow"></div>
          <div class="skeleton-cell medium"></div>
          <div class="skeleton-cell wide"></div>
        </div>
      </div>

      <div v-else-if="filteredPredictions.length === 0" class="empty-state">
        <div class="empty-icon">📭</div>
        <div class="empty-text">暂无匹配的预测数据</div>
      </div>

      <div v-else class="predictions-table-wrapper">
        <table class="predictions-table">
          <thead>
            <tr>
              <th>意图 ID</th>
              <th>SLA 状态</th>
              <th>违反概率</th>
              <th>置信度</th>
              <th>预测时间</th>
              <th>指标预测</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="pred in filteredPredictions"
              :key="pred.id"
              class="prediction-row"
              :style="{ '--row-status': getStatusColor(pred.sla_status) }"
            >
              <td>
                <span class="intent-id">{{ pred.intent_id }}</span>
              </td>
              <td>
                <span
                  class="status-badge"
                  :style="{
                    background: getStatusBg(pred.sla_status),
                    color: getStatusColor(pred.sla_status),
                    borderColor: getStatusColor(pred.sla_status) + '40'
                  }"
                >
                  {{ getStatusText(pred.sla_status) }}
                </span>
              </td>
              <td>
                <div class="probability-cell">
                  <div class="probability-bar">
                    <div
                      class="probability-fill"
                      :style="{
                        width: `${Math.round(pred.violation_probability * 100)}%`,
                        background: `linear-gradient(90deg, ${getStatusColor(pred.sla_status)}, ${getStatusColor(pred.sla_status)}88)`
                      }"
                    ></div>
                  </div>
                  <span class="probability-value" :style="{ color: getStatusColor(pred.sla_status) }">
                    {{ Math.round(pred.violation_probability * 100) }}%
                  </span>
                </div>
              </td>
              <td>
                <span class="confidence-value">{{ Math.round(pred.confidence * 100) }}%</span>
              </td>
              <td>
                <span class="time-value">{{ formatTime(pred.predicted_time) }}</span>
              </td>
              <td>
                <div class="metrics-forecast">
                  <span v-for="(val, key) in pred.metrics_forecast" :key="key" class="metric-chip">
                    {{ key }}: {{ val }}
                  </span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Bottom Panels: Alerts + Dynamic Intervals -->
    <div class="bottom-panels">
      <!-- Alerts Section -->
      <div class="panel alerts-panel">
        <div class="panel-header">
          <h2 class="panel-title">🚨 SLA 告警</h2>
          <span class="alert-count">{{ alerts.length }} 条活跃告警</span>
        </div>
        <div class="alerts-list">
          <div v-if="alerts.length === 0" class="no-alerts">暂无活跃告警</div>
          <div
            v-for="alert in alerts"
            :key="alert.id"
            class="alert-item"
            :style="{ borderLeftColor: getSeverityColor(alert.severity) }"
          >
            <div class="alert-left">
              <span class="alert-severity" :style="{ color: getSeverityColor(alert.severity) }">
                {{ getSeverityText(alert.severity) }}
              </span>
              <span class="alert-message">{{ alert.message }}</span>
            </div>
            <div class="alert-right">
              <span class="alert-time">{{ formatTime(alert.time) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Dynamic Intervals Section -->
      <div class="panel intervals-panel">
        <div class="panel-header">
          <h2 class="panel-title">⏱️ 动态评估间隔</h2>
        </div>
        <div class="intervals-list">
          <div v-if="dynamicIntervals.length === 0" class="no-intervals">暂无间隔数据</div>
          <div
            v-for="interval in dynamicIntervals"
            :key="interval.intent_id"
            class="interval-item"
          >
            <div class="interval-left">
              <span class="interval-intent">{{ interval.intent_id }}</span>
              <span class="interval-reason">{{ interval.adjusted_reason }}</span>
            </div>
            <div class="interval-right">
              <span class="interval-current" :class="{ reduced: interval.current_interval < interval.base_interval, extended: interval.current_interval > interval.base_interval }">
                {{ interval.current_interval }}s
              </span>
              <span class="interval-base">/ {{ interval.base_interval }}s</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Run Prediction Modal -->
    <Teleport to="body">
      <div v-if="showPredictModal" class="modal-overlay" @click.self="showPredictModal = false" role="dialog" aria-modal="true" aria-labelledby="predict-modal-title">
        <div class="modal-content">
          <h3 id="predict-modal-title" class="modal-title">🎯 运行 SLA 预测</h3>
          <p class="modal-text">输入意图ID，触发SLA违反概率预测分析。</p>
          <div class="modal-form">
            <label class="form-label" for="predict-intent-input">意图 ID</label>
            <input
              id="predict-intent-input"
              v-model="predictIntentId"
              type="text"
              class="form-input"
              placeholder="例如: INT-2024-001"
              @keydown.enter="runPrediction"
            />
          </div>
          <div class="modal-actions">
            <button type="button" class="modal-btn cancel" @click="showPredictModal = false" aria-label="取消">取消</button>
            <button type="button" class="modal-btn confirm" :disabled="isPredicting || !predictIntentId.trim()" @click="runPrediction" aria-label="运行预测">
              {{ isPredicting ? '预测中...' : '运行预测' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.sla-prediction {
  position: relative;
  animation: page-enter 0.5s ease-out;
  min-height: 100vh;
  padding: var(--content-padding);
  will-change: opacity;
}

.sla-bg {
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
  background: var(--color-primary-bg);
  top: -100px;
  right: 10%;
  animation: glow-float 12s ease-in-out infinite;
  will-change: transform, opacity;
}

.glow-2 {
  width: 300px;
  height: 300px;
  background: var(--color-orange-bg);
  bottom: 10%;
  left: 5%;
  animation: glow-float 15s ease-in-out infinite reverse;
  will-change: transform, opacity;
}

/* glow-float uses global definition from tokens.css */

/* page-enter uses global definition from tokens.css */

.sla-prediction > *:not(.sla-bg) {
  position: relative;
  z-index: 1;
}

/* Header */
.sla-header {
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
  background: linear-gradient(135deg, var(--color-text-secondary) 0%, var(--color-primary-light) 50%, var(--color-text-secondary) 100%);
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
  will-change: opacity;
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

.action-btn {
  padding: 0.375rem 14px;
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-xs);
  transition: all 0.25s ease;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  white-space: nowrap;
  backdrop-filter: blur(8px);
  min-height: 44px;
}

.action-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-border-focus);
  box-shadow: var(--shadow-glow-primary);
  transform: translateY(-2px);
}

.action-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.refresh-icon {
  display: inline-block;
  transition: transform 0.3s ease;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

/* spin uses global definition from tokens.css */

.predict-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 0.375rem 14px;
  background: linear-gradient(135deg, var(--color-primary-hover), var(--color-primary-glow));
  color: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
  min-height: 44px;
  will-change: transform;
}

.predict-btn:hover {
  background: linear-gradient(135deg, var(--color-primary-border), var(--color-primary-hover));
  border-color: var(--color-border-focus);
  box-shadow: var(--shadow-glow-primary);
  transform: translateY(-2px);
}

.predict-btn:active {
  transform: scale(0.97);
}

/* Stats Bar */
.stats-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: 0.75rem var(--spacing-lg);
  background: linear-gradient(135deg, var(--color-primary-bg) 0%, var(--color-bg-glass) 50%, var(--color-orange-bg) 100%);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-primary);
  margin-bottom: 1.25rem;
  flex-wrap: wrap;
  backdrop-filter: blur(8px);
  animation: bar-enter 0.5s ease-out 0.25s backwards;
}

/* bar-enter uses global definition from tokens.css */

.stat-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 2px var(--spacing-xs);
  border-radius: var(--radius-sm);
  transition: background 0.2s ease;
}

.stat-item:hover {
  background: var(--color-bg-hover);
}

.stat-icon {
  font-size: var(--font-size-lg);
  transition: transform 0.3s ease;
}

.stat-icon.icon-warning { color: var(--color-orange); }
.stat-icon.icon-error { color: var(--color-error); }
.stat-icon.icon-success { color: var(--color-success); }
.stat-icon.icon-primary { color: var(--color-primary-light); }

.stat-item:hover .stat-icon {
  transform: scale(1.2);
}

.stat-content {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.stat-value.safe { color: var(--color-success); }
.stat-value.at-risk { color: var(--color-orange); }
.stat-value.violated { color: var(--color-error); }

.stat-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.stat-divider {
  width: 1px;
  height: 28px;
  background: linear-gradient(180deg, transparent, var(--color-border-secondary), transparent);
}

/* Dashboard Summary */
.dashboard-summary {
  background: var(--gradient-glass);
  border-radius: var(--radius-xl);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  padding: 1.25rem;
  margin-bottom: 1.25rem;
  box-shadow: var(--shadow-card);
}

.summary-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.summary-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  padding-left: 0.625rem;
  border-left: 3px solid var(--color-primary-light);
}

.summary-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--spacing-md);
}

.summary-card {
  background: var(--color-bg-input);
  border-radius: var(--radius-lg);
  padding: 1rem;
  text-align: center;
  border: 1px solid var(--color-border-primary);
  transition: all 0.25s ease;
  will-change: transform;
}

.summary-card:hover {
  border-color: var(--color-border-primary);
  transform: translateY(-3px);
  box-shadow: var(--shadow-card-hover);
}

.summary-card-value {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}

.summary-card-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: 4px;
}

.summary-card.safe { border-top: 3px solid var(--color-success); }
.summary-card.safe .summary-card-value { color: var(--color-success); }
.summary-card.at-risk { border-top: 3px solid var(--color-orange); }
.summary-card.at-risk .summary-card-value { color: var(--color-orange); }
.summary-card.violated { border-top: 3px solid var(--color-error); }
.summary-card.violated .summary-card-value { color: var(--color-error); }
.summary-card.confidence { border-top: 3px solid var(--color-primary-light); }
.summary-card.confidence .summary-card-value { color: var(--color-primary-light); }

/* Filter Bar */
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
}

.filter-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  font-weight: 500;
  white-space: nowrap;
}

.filter-buttons {
  display: flex;
  gap: var(--spacing-sm);
}

.filter-btn {
  padding: var(--spacing-sm) 1rem;
  background: var(--input-bg);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s ease;
  white-space: nowrap;
  min-height: 36px;
  backdrop-filter: blur(8px);
}

.filter-btn:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-color: var(--color-primary-border);
  transform: translateY(-2px);
}

.filter-btn:active {
  transform: scale(0.97);
}

.filter-btn.active {
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  border-color: var(--color-primary);
  box-shadow: var(--shadow-glow-primary);
}

.filter-right {
  display: flex;
  align-items: center;
}

.auto-refresh-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Predictions Section */
.predictions-section {
  background: var(--gradient-glass);
  border-radius: var(--radius-xl);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  padding: 1.25rem;
  margin-bottom: 1.25rem;
  box-shadow: var(--shadow-card);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.section-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  padding-left: 0.625rem;
  border-left: 3px solid var(--color-success);
}

.section-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

/* Table */
.predictions-table-wrapper {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.predictions-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0 6px;
}

.predictions-table thead th {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-align: left;
  padding: 8px 14px;
  border-bottom: 1px solid var(--color-border-primary);
  white-space: nowrap;
}

.prediction-row {
  background: var(--color-bg-glass);
  border-radius: var(--radius-lg);
  transition: all 0.25s ease;
  will-change: background, box-shadow;
}

.prediction-row:hover {
  background: var(--color-bg-input);
  box-shadow: var(--shadow-md);
}

.prediction-row td {
  padding: 12px 14px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  vertical-align: middle;
}

.prediction-row td:first-child {
  border-radius: var(--radius-lg) 0 0 var(--radius-lg);
}

.prediction-row td:last-child {
  border-radius: 0 var(--radius-lg) var(--radius-lg) 0;
}

.intent-id {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-primary-light);
  background: var(--color-primary-bg);
  padding: 3px 10px;
  border-radius: var(--radius-sm);
}

.status-badge {
  display: inline-block;
  font-size: 0.75rem;
  padding: 4px 12px;
  border-radius: var(--radius-md);
  font-weight: 600;
  border: 1px solid;
  white-space: nowrap;
}

.probability-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 140px;
}

.probability-bar {
  flex: 1;
  height: 8px;
  background: var(--color-bg-active);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.probability-fill {
  height: 100%;
  border-radius: var(--radius-sm);
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

.probability-value {
  font-size: var(--font-size-xs);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  min-width: 36px;
  text-align: right;
}

.confidence-value {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.time-value {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.metrics-forecast {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.metric-chip {
  font-size: 0.6875rem;
  padding: 2px 8px;
  background: var(--color-bg-hover);
  border-radius: var(--radius-sm);
  color: var(--color-text-tertiary);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  white-space: nowrap;
}

/* Skeleton */
.table-skeleton {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skeleton-row {
  display: flex;
  gap: 14px;
  padding: 12px 14px;
  background: var(--color-bg-glass);
  border-radius: var(--radius-lg);
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-cell {
  height: 14px;
  background: var(--gradient-shimmer);
  background-size: 200% 100%;
  border-radius: var(--radius-sm);
  animation: skeleton-slide 1.5s ease-in-out infinite;
  will-change: background-position;
}

.skeleton-cell.wide { width: 25%; }
.skeleton-cell.medium { width: 15%; }
.skeleton-cell.narrow { width: 10%; }

/* skeleton-slide uses global definition from tokens.css */

@keyframes skeleton-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 48px var(--spacing-lg);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
  background: var(--gradient-glass);
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

/* Bottom Panels */
.bottom-panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--panel-gap);
}

.panel {
  background: var(--gradient-glass);
  border-radius: var(--radius-xl);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  padding: 1.25rem;
  box-shadow: var(--shadow-card);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.panel-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  padding-left: 0.625rem;
  border-left: 3px solid var(--color-warning);
}

.alert-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  background: var(--color-orange-bg);
  padding: 2px 10px;
  border-radius: var(--radius-lg);
}

/* Alerts */
.alerts-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.no-alerts,
.no-intervals {
  text-align: center;
  padding: 24px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.alert-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: var(--color-bg-glass);
  border-radius: var(--radius-md);
  border-left: 3px solid;
  transition: background 0.2s ease;
  will-change: background;
}

.alert-item:hover {
  background: var(--color-bg-input);
}

.alert-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.alert-severity {
  font-size: var(--font-size-xs);
  font-weight: 600;
  white-space: nowrap;
}

.alert-message {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
}

.alert-right {
  flex-shrink: 0;
}

.alert-time {
  font-size: 0.6875rem;
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

/* Intervals */
.intervals-panel .panel-title {
  border-left-color: var(--color-primary-light);
}

.intervals-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.interval-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--color-bg-glass);
  border-radius: var(--radius-md);
  transition: background 0.2s ease;
  will-change: background;
}

.interval-item:hover {
  background: var(--color-bg-input);
}

.interval-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.interval-intent {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-primary-light);
}

.interval-reason {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.interval-right {
  display: flex;
  align-items: baseline;
  gap: 4px;
  flex-shrink: 0;
}

.interval-current {
  font-size: var(--font-size-sm);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.interval-current.reduced { color: var(--color-orange); }
.interval-current.extended { color: var(--color-success); }

.interval-base {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

/* Modal */
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
  max-width: 440px;
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

.modal-form {
  margin-bottom: 1.25rem;
}

.form-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
  margin-bottom: 6px;
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  font-size: var(--font-size-base);
  outline: none;
  transition: all 0.25s ease;
  box-sizing: border-box;
}

.form-input::placeholder {
  color: var(--color-text-disabled);
}

.form-input:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
  background: var(--color-bg-glass-strong);
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
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
  min-height: 44px;
}

.modal-btn:hover:not(:disabled) {
  transform: translateY(-2px);
}

.modal-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.modal-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
  background: var(--gradient-primary);
  color: var(--color-text-primary);
}

.modal-btn.confirm:hover:not(:disabled) {
  box-shadow: var(--shadow-glow-primary);
}

/* Responsive */
@media (max-width: 768px) {
  .sla-prediction {
    padding: var(--spacing-md);
  }

  .sla-header {
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

  .stats-bar {
    gap: 10px;
    padding: 10px var(--spacing-md);
  }

  .stat-divider {
    display: none;
  }

  .summary-grid {
    grid-template-columns: repeat(3, 1fr);
  }

  .filter-bar {
    flex-direction: column;
    align-items: stretch;
    padding: 0.75rem 14px;
  }

  .filter-left {
    flex-direction: column;
    align-items: flex-start;
  }

  .filter-buttons {
    flex-wrap: wrap;
  }

  .bottom-panels {
    grid-template-columns: 1fr;
  }

  .predictions-table {
    font-size: var(--font-size-xs);
  }

  .action-btn,
  .predict-btn {
    min-height: 44px;
    padding: 10px var(--spacing-md);
    font-size: var(--font-size-base);
  }

  .modal-content {
    width: 94%;
    padding: 1.25rem;
  }
}

@media (max-width: 480px) {
  .sla-prediction {
    padding: var(--spacing-sm);
  }

  .page-title {
    font-size: var(--font-size-lg);
  }

  .summary-grid {
    grid-template-columns: 1fr 1fr;
  }

  .probability-cell {
    min-width: 100px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sla-prediction,
  .stats-bar,
  .bg-glow,
  .freshness-dot,
  .refresh-icon.spinning,
  .skeleton-row,
  .skeleton-cell,
  .page-title,
  .probability-fill,
  .modal-overlay {
    animation: none !important;
    transition: none !important;
  }
}
</style>
