<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, apiClient } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'
import { useLogger } from '@/utils/logger'
import PageLayout from '@/components/PageLayout.vue'
import StatCard from '@/components/StatCard.vue'
import { useAuthStore } from '@/stores/auth'

const { info, warn } = useLogger()
const authStore = useAuthStore()
const canWrite = computed(() => authStore.userRole !== 'viewer')

// ===== 类型定义 =====
interface TraceSpan {
  span_id: string
  operation: string
  agent: string
  duration_ms: number
  status: 'OK' | 'Error'
  start_time: string
  children?: TraceSpan[]
}

interface Trace {
  trace_id: string
  agent: string
  operation: string
  duration_ms: number
  status: 'OK' | 'Error'
  timestamp: string
  spans?: TraceSpan[]
}

interface AgentHealthInfo {
  agent_id: string
  status: 'Healthy' | 'Unhealthy' | 'Unknown'
  latency_p50: number
  latency_p95: number
  latency_p99: number
  error_rate: number
  qps: number
}

interface OverviewMetrics {
  request_rate: number
  error_rate: number
  p95_latency: number
  active_connections: number
}

// ===== 状态 =====
const activeTab = ref<'traces' | 'agents'>('traces')
const statusFilter = ref<'all' | 'OK' | 'Error'>('all')
const sortField = ref<'latency_p95' | 'error_rate'>('latency_p95')
const isRefreshing = ref(false)
const isLoading = ref(true)
const isMockData = ref(false)
const lastRefreshTime = ref('')

const traces = ref<Trace[]>([])
const selectedTrace = ref<Trace | null>(null)
const showTraceDetail = ref(false)
const agentsHealth = ref<AgentHealthInfo[]>([])
const overviewMetrics = ref<OverviewMetrics>({
  request_rate: 0,
  error_rate: 0,
  p95_latency: 0,
  active_connections: 0
})

let refreshTimer: number | null = null

// ===== 计算属性 =====
const totalTraces = computed(() => traces.value.length)
const healthyAgents = computed(() => agentsHealth.value.filter(a => a.status === 'Healthy').length)
const unhealthyAgents = computed(() => agentsHealth.value.filter(a => a.status === 'Unhealthy').length)
const avgResponseTime = computed(() => {
  if (!traces.value.length) return 0
  const sum = traces.value.reduce((acc, t) => acc + t.duration_ms, 0)
  return Math.round(sum / traces.value.length)
})

const filteredTraces = computed(() => {
  if (statusFilter.value === 'all') return traces.value
  return traces.value.filter(t => t.status === statusFilter.value)
})

const sortedAgents = computed(() => {
  const list = [...agentsHealth.value]
  if (sortField.value === 'latency_p95') {
    list.sort((a, b) => b.latency_p95 - a.latency_p95)
  } else {
    list.sort((a, b) => b.error_rate - a.error_rate)
  }
  return list
})

// ===== 数据获取 =====
const fetchAllData = async (showLoading = false) => {
  if (isRefreshing.value) return
  isRefreshing.value = true
  if (showLoading) isLoading.value = true
  lastRefreshTime.value = new Date().toLocaleTimeString()

  try {
    const [tracesRes, agentsRes, overviewRes] = await Promise.allSettled([
      apiClient.get<Trace[]>(api.observability.traces),
      apiClient.get<AgentHealthInfo[]>(api.observability.agentsHealth),
      apiClient.get<OverviewMetrics>(api.observability.overview)
    ])

    if (tracesRes.status === 'fulfilled' && tracesRes.value.data) {
      traces.value = Array.isArray(tracesRes.value.data) ? tracesRes.value.data : []
      isMockData.value = false
    }

    if (agentsRes.status === 'fulfilled' && agentsRes.value.data) {
      const raw = agentsRes.value.data
      agentsHealth.value = Array.isArray(raw) ? raw : (raw?.items || Object.values(raw))
    }

    if (overviewRes.status === 'fulfilled' && overviewRes.value.data) {
      overviewMetrics.value = overviewRes.value.data
    }

    if (tracesRes.status === 'rejected' && agentsRes.status === 'rejected') {
      loadMockData()
      isMockData.value = true
    }
  } catch (err: any) {
    warn('获取可观测性数据失败', { error: err.message })
    loadMockData()
    isMockData.value = true
  } finally {
    isRefreshing.value = false
    isLoading.value = false
  }
}

const fetchTraceDetail = async (traceId: string) => {
  try {
    const res = await apiClient.get<Trace>(api.observability.traceDetail(traceId))
    if (res.data) {
      selectedTrace.value = res.data
      showTraceDetail.value = true
    }
  } catch {
    const found = traces.value.find(t => t.trace_id === traceId)
    if (found) {
      selectedTrace.value = { ...found, spans: generateMockSpans(found) }
      showTraceDetail.value = true
    }
  }
}

const triggerHealthCheck = async () => {
  try {
    await apiClient.post(api.observability.healthCheck)
    showToast('健康检查已触发', 'success')
    await fetchAllData()
  } catch {
    showToast('健康检查触发失败', 'error')
  }
}

const manualRefresh = async () => {
  isRefreshing.value = true
  try {
    await fetchAllData(true)
    showToast('数据已刷新', 'success')
  } catch {
    showToast('刷新失败', 'error')
  }
}

// ===== Mock 数据 =====
const loadMockData = () => {
  traces.value = [
    { trace_id: 'tr-001', agent: 'bandwidth-agent', operation: 'allocate_bandwidth', duration_ms: 142, status: 'OK', timestamp: '2026-06-03T10:12:00Z' },
    { trace_id: 'tr-002', agent: 'qos-agent', operation: 'apply_policy', duration_ms: 89, status: 'OK', timestamp: '2026-06-03T10:11:30Z' },
    { trace_id: 'tr-003', agent: 'firewall-agent', operation: 'update_acl', duration_ms: 356, status: 'Error', timestamp: '2026-06-03T10:10:45Z' },
    { trace_id: 'tr-004', agent: 'route-agent', operation: 'optimize_path', duration_ms: 67, status: 'OK', timestamp: '2026-06-03T10:09:20Z' },
    { trace_id: 'tr-005', agent: 'diagnosis-agent', operation: 'analyze_fault', duration_ms: 210, status: 'OK', timestamp: '2026-06-03T10:08:00Z' },
    { trace_id: 'tr-006', agent: 'healing-agent', operation: 'auto_repair', duration_ms: 520, status: 'Error', timestamp: '2026-06-03T10:07:10Z' },
    { trace_id: 'tr-007', agent: 'traffic-agent', operation: 'shape_flow', duration_ms: 95, status: 'OK', timestamp: '2026-06-03T10:06:30Z' },
    { trace_id: 'tr-008', agent: 'security-agent', operation: 'scan_vulnerability', duration_ms: 180, status: 'OK', timestamp: '2026-06-03T10:05:00Z' }
  ]

  agentsHealth.value = [
    { agent_id: 'bandwidth-agent', status: 'Healthy', latency_p50: 45, latency_p95: 120, latency_p99: 210, error_rate: 0.02, qps: 15.3 },
    { agent_id: 'qos-agent', status: 'Healthy', latency_p50: 32, latency_p95: 85, latency_p99: 150, error_rate: 0.01, qps: 22.1 },
    { agent_id: 'firewall-agent', status: 'Unhealthy', latency_p50: 180, latency_p95: 420, latency_p99: 680, error_rate: 0.15, qps: 8.7 },
    { agent_id: 'route-agent', status: 'Healthy', latency_p50: 28, latency_p95: 65, latency_p99: 110, error_rate: 0.005, qps: 30.5 },
    { agent_id: 'diagnosis-agent', status: 'Healthy', latency_p50: 55, latency_p95: 150, latency_p99: 280, error_rate: 0.03, qps: 12.8 },
    { agent_id: 'healing-agent', status: 'Unhealthy', latency_p50: 200, latency_p95: 530, latency_p99: 890, error_rate: 0.18, qps: 5.2 },
    { agent_id: 'traffic-agent', status: 'Healthy', latency_p50: 38, latency_p95: 95, latency_p99: 170, error_rate: 0.01, qps: 18.4 },
    { agent_id: 'security-agent', status: 'Unknown', latency_p50: 0, latency_p95: 0, latency_p99: 0, error_rate: 0, qps: 0 }
  ]

  overviewMetrics.value = {
    request_rate: 143.2,
    error_rate: 0.047,
    p95_latency: 185,
    active_connections: 328
  }
}

const generateMockSpans = (trace: Trace): TraceSpan[] => [
  { span_id: 'sp-1', operation: 'validate_input', agent: trace.agent, duration_ms: Math.round(trace.duration_ms * 0.1), status: 'OK', start_time: trace.timestamp },
  { span_id: 'sp-2', operation: 'execute_task', agent: trace.agent, duration_ms: Math.round(trace.duration_ms * 0.7), status: trace.status, start_time: trace.timestamp, children: [
    { span_id: 'sp-2a', operation: 'query_database', agent: trace.agent, duration_ms: Math.round(trace.duration_ms * 0.3), status: 'OK', start_time: trace.timestamp },
    { span_id: 'sp-2b', operation: 'call_external', agent: trace.agent, duration_ms: Math.round(trace.duration_ms * 0.35), status: trace.status, start_time: trace.timestamp }
  ]},
  { span_id: 'sp-3', operation: 'format_response', agent: trace.agent, duration_ms: Math.round(trace.duration_ms * 0.05), status: 'OK', start_time: trace.timestamp }
]

// ===== 工具函数 =====
const formatTimestamp = (ts: string) => {
  if (!ts) return '--'
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  return d.toLocaleString('zh-CN', { hour12: false })
}

const getStatusColor = (status: string) => {
  if (status === 'OK' || status === 'Healthy') return 'var(--color-success)'
  if (status === 'Error' || status === 'Unhealthy') return 'var(--color-error)'
  return 'var(--color-text-tertiary)'
}

const getStatusText = (status: string) => {
  if (status === 'OK') return '成功'
  if (status === 'Error') return '错误'
  if (status === 'Healthy') return '健康'
  if (status === 'Unhealthy') return '异常'
  return '未知'
}

const getStatusBg = (status: string) => {
  if (status === 'OK' || status === 'Healthy') return 'var(--color-success-bg)'
  if (status === 'Error' || status === 'Unhealthy') return 'var(--color-error-bg)'
  return 'var(--color-bg-hover)'
}

const getStatusBorder = (status: string) => {
  if (status === 'OK' || status === 'Healthy') return 'var(--color-success-border)'
  if (status === 'Error' || status === 'Unhealthy') return 'var(--color-error-border)'
  return 'var(--color-border-hover)'
}

const getDurationColor = (ms: number) => {
  if (ms < 100) return 'var(--color-success)'
  if (ms < 300) return 'var(--color-warning)'
  return 'var(--color-error)'
}

const getErrorRateColor = (rate: number) => {
  if (rate < 0.05) return 'var(--color-success)'
  if (rate < 0.1) return 'var(--color-warning)'
  return 'var(--color-error)'
}

const closeTraceDetail = () => {
  showTraceDetail.value = false
  selectedTrace.value = null
}

// ===== 生命周期 =====
onMounted(async () => {
  info('Observability 页面挂载')
  await fetchAllData(true)
  refreshTimer = window.setInterval(() => {
    if (!document.hidden) fetchAllData(false)
  }, 15000)
})

onUnmounted(() => {
  if (refreshTimer !== null) clearInterval(refreshTimer)
})
</script>

<template>
  <PageLayout title="可观测中心" subtitle="链路追踪 & Agent 健康">
    <template #actions>
      <span class="data-freshness" :class="{ degraded: isMockData }">
        <span class="freshness-dot"></span>
        {{ isMockData ? '降级' : '实时' }}
      </span>
      <span v-if="lastRefreshTime" class="last-refresh">{{ lastRefreshTime }}</span>
      <button
        type="button"
        class="action-btn refresh-btn"
        :class="{ refreshing: isRefreshing }"
        @click="manualRefresh"
        :disabled="isRefreshing"
        aria-label="刷新数据"
      >
        <span class="refresh-icon" :class="{ spinning: isRefreshing }">🔄</span>
        {{ isRefreshing ? '刷新中...' : '刷新' }}
      </button>
    </template>

    <!-- Stats Bar -->
    <div v-if="isLoading" class="stats-grid">
      <div v-for="i in 4" :key="i" class="stat-card-skeleton">
        <div class="skeleton-line wide"></div>
        <div class="skeleton-line narrow"></div>
      </div>
    </div>
    <div v-else class="stats-grid">
      <StatCard icon="🔗" label="总链路数" :value="totalTraces" suffix="条" type="default" />
      <StatCard icon="✅" label="健康 Agent" :value="healthyAgents" suffix="个" type="success" />
      <StatCard icon="⚠️" label="异常 Agent" :value="unhealthyAgents" suffix="个" type="danger" />
      <StatCard icon="⏱️" label="平均响应时间" :value="avgResponseTime" suffix="ms" type="warning" />
    </div>

    <!-- Metrics Overview -->
    <div class="metrics-overview">
      <div class="metric-item">
        <span class="metric-icon">📊</span>
        <div class="metric-info">
          <span class="metric-value">{{ overviewMetrics.request_rate }}</span>
          <span class="metric-label">请求速率 (req/s)</span>
        </div>
      </div>
      <div class="metric-divider"></div>
      <div class="metric-item">
        <span class="metric-icon">❌</span>
        <div class="metric-info">
          <span class="metric-value" :style="{ color: getErrorRateColor(overviewMetrics.error_rate) }">{{ (overviewMetrics.error_rate * 100).toFixed(1) }}%</span>
          <span class="metric-label">错误率</span>
        </div>
      </div>
      <div class="metric-divider"></div>
      <div class="metric-item">
        <span class="metric-icon">⏳</span>
        <div class="metric-info">
          <span class="metric-value" :style="{ color: getDurationColor(overviewMetrics.p95_latency) }">{{ overviewMetrics.p95_latency }}ms</span>
          <span class="metric-label">P95 延迟</span>
        </div>
      </div>
      <div class="metric-divider"></div>
      <div class="metric-item">
        <span class="metric-icon">🔌</span>
        <div class="metric-info">
          <span class="metric-value">{{ overviewMetrics.active_connections }}</span>
          <span class="metric-label">活跃连接</span>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="tab-bar">
      <button
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === 'traces' }"
        @click="activeTab = 'traces'"
      >🔗 链路追踪</button>
      <button
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === 'agents' }"
        @click="activeTab = 'agents'"
      >🩺 Agent 健康</button>
    </div>

    <!-- Traces Tab -->
    <div v-if="activeTab === 'traces'" class="panel">
      <div class="panel-header">
        <h2 class="panel-title">链路追踪</h2>
        <div class="panel-actions">
          <div class="filter-group">
            <button
              type="button"
              v-for="f in (['all', 'OK', 'Error'] as const)"
              :key="f"
              class="filter-btn"
              :class="{ active: statusFilter === f }"
              @click="statusFilter = f"
            >{{ f === 'all' ? '全部' : f === 'OK' ? '成功' : '错误' }}</button>
          </div>
          <button type="button" v-if="canWrite" class="action-btn" @click="triggerHealthCheck" aria-label="健康检查">
            🏥 健康检查
          </button>
        </div>
      </div>

      <div class="trace-table">
        <div class="trace-table-header">
          <span class="col-trace-id">Trace ID</span>
          <span class="col-agent">Agent</span>
          <span class="col-operation">操作</span>
          <span class="col-duration">耗时</span>
          <span class="col-status">状态</span>
          <span class="col-timestamp">时间</span>
        </div>
        <div
          v-for="trace in filteredTraces"
          :key="trace.trace_id"
          class="trace-row"
          @click="fetchTraceDetail(trace.trace_id)"
        >
          <span class="col-trace-id mono">{{ trace.trace_id }}</span>
          <span class="col-agent">{{ trace.agent }}</span>
          <span class="col-operation">{{ trace.operation }}</span>
          <span class="col-duration" :style="{ color: getDurationColor(trace.duration_ms) }">{{ trace.duration_ms }}ms</span>
          <span class="col-status">
            <span
              class="status-badge"
              :style="{ color: getStatusColor(trace.status), background: getStatusBg(trace.status), borderColor: getStatusBorder(trace.status) }"
            >{{ getStatusText(trace.status) }}</span>
          </span>
          <span class="col-timestamp">{{ formatTimestamp(trace.timestamp) }}</span>
        </div>
        <div v-if="filteredTraces.length === 0" class="empty-state">
          <div class="empty-icon">📭</div>
          <div>暂无链路记录</div>
        </div>
      </div>
    </div>

    <!-- Agent Health Tab -->
    <div v-if="activeTab === 'agents'" class="panel">
      <div class="panel-header">
        <h2 class="panel-title">Agent 健康状态</h2>
        <div class="panel-actions">
          <div class="filter-group">
            <button
              type="button"
              class="filter-btn"
              :class="{ active: sortField === 'latency_p95' }"
              @click="sortField = 'latency_p95'"
            >按延迟排序</button>
            <button
              type="button"
              class="filter-btn"
              :class="{ active: sortField === 'error_rate' }"
              @click="sortField = 'error_rate'"
            >按错误率排序</button>
          </div>
        </div>
      </div>

      <div class="agent-cards">
        <div
          v-for="agent in sortedAgents"
          :key="agent.agent_id"
          class="agent-card"
          :class="{ unhealthy: agent.status === 'Unhealthy', unknown: agent.status === 'Unknown' }"
        >
          <div class="agent-card-header">
            <span class="agent-status-dot" :style="{ background: getStatusColor(agent.status), boxShadow: `0 0 8px ${getStatusColor(agent.status)}40` }"></span>
            <span class="agent-id">{{ agent.agent_id }}</span>
            <span
              class="status-badge"
              :style="{ color: getStatusColor(agent.status), background: getStatusBg(agent.status), borderColor: getStatusBorder(agent.status) }"
            >{{ getStatusText(agent.status) }}</span>
          </div>
          <div class="agent-card-metrics">
            <div class="agent-metric">
              <span class="agent-metric-label">P50</span>
              <span class="agent-metric-value">{{ agent.latency_p50 }}ms</span>
            </div>
            <div class="agent-metric">
              <span class="agent-metric-label">P95</span>
              <span class="agent-metric-value" :style="{ color: getDurationColor(agent.latency_p95) }">{{ agent.latency_p95 }}ms</span>
            </div>
            <div class="agent-metric">
              <span class="agent-metric-label">P99</span>
              <span class="agent-metric-value" :style="{ color: getDurationColor(agent.latency_p99) }">{{ agent.latency_p99 }}ms</span>
            </div>
            <div class="agent-metric">
              <span class="agent-metric-label">错误率</span>
              <span class="agent-metric-value" :style="{ color: getErrorRateColor(agent.error_rate) }">{{ (agent.error_rate * 100).toFixed(1) }}%</span>
            </div>
            <div class="agent-metric">
              <span class="agent-metric-label">QPS</span>
              <span class="agent-metric-value">{{ agent.qps }}</span>
            </div>
          </div>
        </div>
        <div v-if="agentsHealth.length === 0" class="empty-state">
          <div class="empty-icon">🩺</div>
          <div>暂无 Agent 健康数据</div>
        </div>
      </div>
    </div>

    <!-- Trace Detail Modal -->
    <Teleport to="body">
      <div v-if="showTraceDetail" class="modal-overlay" @click.self="closeTraceDetail">
        <div class="modal-content large">
          <div class="modal-header">
            <h3 class="modal-title">链路详情 - {{ selectedTrace?.trace_id }}</h3>
            <button type="button" class="modal-close-btn" @click="closeTraceDetail" aria-label="关闭">✕</button>
          </div>
          <div class="modal-body" v-if="selectedTrace">
            <div class="trace-detail-info">
              <div class="detail-item">
                <span class="detail-label">Agent</span>
                <span class="detail-value">{{ selectedTrace.agent }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">操作</span>
                <span class="detail-value">{{ selectedTrace.operation }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">耗时</span>
                <span class="detail-value" :style="{ color: getDurationColor(selectedTrace.duration_ms) }">{{ selectedTrace.duration_ms }}ms</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">状态</span>
                <span class="detail-value">
                  <span class="status-badge" :style="{ color: getStatusColor(selectedTrace.status), background: getStatusBg(selectedTrace.status), borderColor: getStatusBorder(selectedTrace.status) }">{{ getStatusText(selectedTrace.status) }}</span>
                </span>
              </div>
              <div class="detail-item">
                <span class="detail-label">时间</span>
                <span class="detail-value">{{ formatTimestamp(selectedTrace.timestamp) }}</span>
              </div>
            </div>

            <div class="spans-section" v-if="selectedTrace.spans?.length">
              <h4 class="spans-title">Span 树</h4>
              <div class="spans-tree">
                <template v-for="span in selectedTrace.spans" :key="span.span_id">
                  <div class="span-node" :style="{ '--depth': 0 }">
                    <div class="span-connector"></div>
                    <div class="span-content">
                      <div class="span-header">
                        <span class="span-operation">{{ span.operation }}</span>
                        <span class="span-duration" :style="{ color: getDurationColor(span.duration_ms) }">{{ span.duration_ms }}ms</span>
                        <span class="status-badge small" :style="{ color: getStatusColor(span.status), background: getStatusBg(span.status), borderColor: getStatusBorder(span.status) }">{{ getStatusText(span.status) }}</span>
                      </div>
                      <div class="span-meta">
                        <span class="span-id mono">{{ span.span_id }}</span>
                        <span class="span-agent">{{ span.agent }}</span>
                      </div>
                    </div>
                  </div>
                  <template v-if="span.children?.length">
                    <div v-for="child in span.children" :key="child.span_id" class="span-node child" :style="{ '--depth': 1 }">
                      <div class="span-connector"></div>
                      <div class="span-content">
                        <div class="span-header">
                          <span class="span-operation">{{ child.operation }}</span>
                          <span class="span-duration" :style="{ color: getDurationColor(child.duration_ms) }">{{ child.duration_ms }}ms</span>
                          <span class="status-badge small" :style="{ color: getStatusColor(child.status), background: getStatusBg(child.status), borderColor: getStatusBorder(child.status) }">{{ getStatusText(child.status) }}</span>
                        </div>
                        <div class="span-meta">
                          <span class="span-id mono">{{ child.span_id }}</span>
                          <span class="span-agent">{{ child.agent }}</span>
                        </div>
                      </div>
                    </div>
                  </template>
                </template>
              </div>
            </div>
            <div v-else class="empty-state small">暂无 Span 数据</div>
          </div>
        </div>
      </div>
    </Teleport>
  </PageLayout>
</template>

<style scoped lang="scss">
/* ===== Data Freshness ===== */
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

/* ===== Action Buttons ===== */
.action-btn {
  padding: 0.375rem 0.875rem;
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
  will-change: transform;
}

.action-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-glow-primary);
  color: var(--color-primary-lighter);
  transform: translateY(-2px);
}

.action-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.97);
}

.action-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.refresh-icon {
  display: inline-block;
  transition: transform 0.3s ease;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

/* spin uses global definition from tokens.css */

/* ===== Stats Grid ===== */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(var(--grid-min-col), 1fr));
  gap: var(--panel-gap);
  margin-bottom: var(--panel-gap);
}

.stat-card-skeleton {
  animation: skeleton-pulse 1.5s ease-in-out infinite;
  padding: 1.25rem;
  background: var(--gradient-glass);
  border-radius: var(--card-border-radius);
  border: var(--card-border);
}

/* skeleton-pulse uses global definition from tokens.css */

.skeleton-line {
  height: 0.875rem;
  background: var(--gradient-shimmer);
  background-size: 200% 100%;
  border-radius: var(--radius-sm);
  margin-bottom: 0.625rem;
  animation: skeleton-slide 1.5s ease-in-out infinite;
  will-change: background-position;
}

/* skeleton-slide uses global definition from tokens.css */

.skeleton-line.wide { width: 70%; }
.skeleton-line.narrow { width: 40%; }

/* ===== Metrics Overview ===== */
.metrics-overview {
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
  animation: bar-enter 0.5s var(--ease-out) 0.25s backwards;
}

/* bar-enter uses global definition from tokens.css */

.metric-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.125rem var(--spacing-xs);
  border-radius: var(--radius-sm);
  transition: background 0.2s var(--ease-out);
}

.metric-item:hover {
  background: var(--color-bg-hover);
}

.metric-icon {
  font-size: var(--font-size-base);
  transition: transform 0.3s var(--ease-spring);
}

.metric-item:hover .metric-icon {
  transform: scale(1.2);
}

.metric-info {
  display: flex;
  flex-direction: column;
}

.metric-value {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.metric-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.metric-divider {
  width: 1px;
  height: 1.25rem;
  background: linear-gradient(180deg, transparent, var(--color-border-secondary), transparent);
}

/* ===== Tab Bar ===== */
.tab-bar {
  display: flex;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-lg);
  animation: bar-enter 0.5s var(--ease-out) 0.3s backwards;
}

.tab-btn {
  padding: 0.5rem 1.25rem;
  background: var(--gradient-glass);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
  min-height: 44px;
  will-change: transform;
}

.tab-btn:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border-color: var(--color-primary-border);
  transform: translateY(-2px);
}

.tab-btn:active {
  transform: translateY(0) scale(0.97);
}

.tab-btn.active {
  background: var(--color-primary-hover);
  color: var(--color-primary-light);
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-glow-primary);
  font-weight: var(--font-weight-semibold);
}

/* ===== Panel ===== */
.panel {
  background: var(--gradient-glass);
  border-radius: var(--card-border-radius);
  padding: var(--card-padding);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-card);
  animation: panel-enter 0.5s var(--ease-out) 0.35s backwards;
  transition: border-color 0.3s var(--ease-out), box-shadow 0.3s var(--ease-out);
  will-change: border-color, box-shadow;
}

.panel:hover {
  border-color: var(--color-border-secondary);
  box-shadow: var(--shadow-card-hover);
}

/* panel-enter uses global definition from tokens.css */

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.panel-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: 0;
  padding-left: 0.625rem;
  border-left: 3px solid var(--color-primary);
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
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
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
  will-change: transform;
}

.filter-btn:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border-color: var(--color-primary-border);
  transform: translateY(-2px);
}

.filter-btn:active {
  transform: translateY(0) scale(0.97);
}

.filter-btn.active {
  background: var(--color-primary-hover);
  color: var(--color-primary-light);
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-glow-primary);
  font-weight: var(--font-weight-medium);
}

/* ===== Trace Table ===== */
.trace-table {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.trace-table-header {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1.2fr 0.8fr 0.8fr 1.2fr;
  gap: var(--spacing-sm);
  padding: 0.625rem var(--spacing-md);
  background: var(--color-bg-hover);
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.trace-row {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1.2fr 0.8fr 0.8fr 1.2fr;
  gap: var(--spacing-sm);
  padding: 0.75rem var(--spacing-md);
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  transition: all 0.25s ease;
  cursor: pointer;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  align-items: center;
  will-change: transform;
}

.trace-row:hover {
  background: var(--color-bg-glass-strong);
  border-color: var(--color-primary-border);
  transform: translateX(4px);
  box-shadow: var(--shadow-glow-primary);
}

.trace-row:active {
  transform: scale(0.99);
}

.mono {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-xs);
}

.col-duration {
  font-weight: var(--font-weight-semibold);
  font-variant-numeric: tabular-nums;
}

/* ===== Status Badge ===== */
.status-badge {
  font-size: var(--font-size-xs);
  padding: 0.1875rem var(--spacing-sm);
  border-radius: var(--radius-sm);
  border: 1px solid;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  font-weight: var(--font-weight-medium);
  transition: all 0.2s var(--ease-out);
}

.status-badge.small {
  font-size: var(--font-size-xs);
  padding: 1px 0.375rem;
}

.trace-row:hover .status-badge {
  transform: scale(1.05);
  box-shadow: var(--shadow-glow-primary-sm);
}

/* ===== Agent Cards ===== */
.agent-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--spacing-md);
}

.agent-card {
  background: var(--color-bg-input);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  border: 1px solid var(--color-border-primary);
  transition: all 0.25s ease;
  animation: card-enter 0.3s var(--ease-out) backwards;
  will-change: transform;
}

.agent-card:nth-child(1) { animation-delay: 0.05s; }
.agent-card:nth-child(2) { animation-delay: 0.1s; }
.agent-card:nth-child(3) { animation-delay: 0.15s; }
.agent-card:nth-child(4) { animation-delay: 0.2s; }
.agent-card:nth-child(5) { animation-delay: 0.25s; }
.agent-card:nth-child(6) { animation-delay: 0.3s; }
.agent-card:nth-child(7) { animation-delay: 0.35s; }
.agent-card:nth-child(8) { animation-delay: 0.4s; }

/* card-enter uses global definition from tokens.css */

.agent-card:hover {
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-glow-primary);
  transform: translateY(-3px);
}

.agent-card:active {
  transform: scale(0.98);
}

.agent-card.unhealthy {
  border-color: var(--color-error-border);
  background: var(--color-error-bg);
}

.agent-card.unhealthy:hover {
  border-color: var(--color-error-border);
  box-shadow: var(--shadow-glow-error);
}

.agent-card.unknown {
  border-color: var(--color-border-hover);
  opacity: 0.7;
}

.agent-card-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: var(--spacing-md);
}

.agent-status-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  flex-shrink: 0;
  animation: dot-pulse 2s ease-in-out infinite;
  will-change: opacity;
}

/* dot-pulse uses global definition from tokens.css */

.agent-id {
  flex: 1;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-card-metrics {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--spacing-xs);
}

.agent-metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: var(--spacing-xs);
  background: var(--color-bg-hover);
  border-radius: var(--radius-sm);
}

.agent-metric-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.agent-metric-value {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

/* ===== Modal ===== */
.modal-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background: var(--modal-overlay-bg);
  backdrop-filter: blur(var(--modal-backdrop-blur));
  -webkit-backdrop-filter: blur(var(--modal-backdrop-blur));
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-overlay);
  padding: var(--spacing-md);
  animation: modal-overlay-in 0.2s var(--ease-out);
}

/* modal-overlay-in uses global definition from tokens.css */

.modal-content {
  background: var(--color-bg-elevated);
  border-radius: var(--modal-border-radius);
  border: 1px solid var(--color-border-primary);
  padding: var(--modal-padding);
  box-shadow: var(--modal-shadow);
  animation: modal-content-in 0.25s var(--ease-out);
  max-height: 85vh;
  overflow-y: auto;
}

.modal-content.large {
  max-width: 800px;
  width: 90vw;
}

/* modal-content-in uses global definition from tokens.css */

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-border-primary);
}

.modal-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
}

.modal-close-btn {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: all 0.25s ease;
  font-size: var(--font-size-base);
}

.modal-close-btn:hover {
  background: var(--color-error-bg);
  color: var(--color-error-light);
  border-color: var(--color-error-border);
  transform: scale(1.05);
}

.modal-close-btn:active {
  transform: scale(0.95);
}

/* ===== Trace Detail ===== */
.trace-detail-info {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.detail-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.detail-value {
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

.spans-section {
  border-top: 1px solid var(--color-border-primary);
  padding-top: var(--spacing-md);
}

.spans-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-md);
  padding-left: 0.625rem;
  border-left: 3px solid var(--color-warning);
}

.spans-tree {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.span-node {
  display: flex;
  align-items: stretch;
  gap: 0;
  position: relative;
  padding-left: calc(var(--depth, 0) * 1.5rem);
}

.span-node.child {
  padding-left: 2.5rem;
}

.span-connector {
  width: 2px;
  background: var(--color-border-primary);
  margin-left: 0.75rem;
  flex-shrink: 0;
}

.span-node:last-child .span-connector {
  display: none;
}

.span-content {
  flex: 1;
  padding: 0.5rem 0.75rem;
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  transition: all 0.2s var(--ease-out);
  margin-left: 0.5rem;
}

.span-content:hover {
  border-color: var(--color-primary-border);
  background: var(--color-bg-glass-strong);
}

.span-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: 2px;
}

.span-operation {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.span-duration {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  font-variant-numeric: tabular-nums;
}

.span-meta {
  display: flex;
  gap: var(--spacing-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.span-id {
  font-family: var(--font-family-mono);
}

/* ===== Empty State ===== */
.empty-state {
  text-align: center;
  padding: var(--spacing-xl) var(--spacing-lg);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
}

.empty-state.small {
  padding: var(--spacing-md);
  font-size: var(--font-size-sm);
}

.empty-icon {
  font-size: var(--font-size-3xl);
  margin-bottom: var(--spacing-sm);
  opacity: 0.5;
  filter: grayscale(0.3);
}

/* ===== Responsive ===== */
@media (max-width: 1200px) {
  .trace-table-header,
  .trace-row {
    grid-template-columns: 1fr 0.8fr 1fr 0.6fr 0.6fr 1fr;
  }
}

@media (max-width: 1024px) {
  .metrics-overview {
    flex-wrap: wrap;
    gap: 0.625rem;
  }
  .metric-divider {
    display: none;
  }
  .agent-cards {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  }
}

@media (max-width: 768px) {
  .trace-table-header,
  .trace-row {
    grid-template-columns: 1fr 1fr;
    gap: var(--spacing-xs);
  }
  .col-operation,
  .col-timestamp {
    display: none;
  }
  .trace-table-header .col-operation,
  .trace-table-header .col-timestamp {
    display: none;
  }
  .agent-cards {
    grid-template-columns: 1fr;
  }
  .agent-card-metrics {
    grid-template-columns: repeat(3, 1fr);
  }
  .tab-bar {
    flex-wrap: wrap;
  }
  .panel-header {
    flex-direction: column;
    align-items: flex-start;
  }
  .panel-actions {
    width: 100%;
  }
  .trace-detail-info {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr;
    gap: var(--spacing-sm);
  }
  .trace-table-header,
  .trace-row {
    grid-template-columns: 1fr;
  }
  .col-agent,
  .col-status {
    display: none;
  }
  .trace-table-header .col-agent,
  .trace-table-header .col-status {
    display: none;
  }
  .agent-card-metrics {
    grid-template-columns: repeat(2, 1fr);
  }
  .trace-detail-info {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .panel,
  .metrics-overview,
  .tab-bar,
  .agent-card {
    animation: none;
  }
  .freshness-dot,
  .agent-status-dot {
    animation: none;
  }
  .refresh-icon.spinning {
    animation: none;
  }
  .stat-card-skeleton,
  .skeleton-line {
    animation: none;
  }
  .trace-row:hover,
  .agent-card:hover,
  .tab-btn:hover,
  .filter-btn:hover,
  .action-btn:hover:not(:disabled) {
    transform: none;
  }
}
</style>
