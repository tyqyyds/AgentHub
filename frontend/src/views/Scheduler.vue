<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, apiClient } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'
import { themeColors } from '@/utils/themeColors'
import PageLayout from '@/components/PageLayout.vue'
import StatCard from '@/components/StatCard.vue'

interface QueueItem {
  intent_id: string
  priority: number
  position: number
  status: string
  wait_time: number
  enqueued_at?: string
}

interface ResourcePool {
  cpu_usage: number
  memory_usage: number
  active_connections: number
  max_cpu: number
  max_memory: number
  max_connections: number
}

const queueItems = ref<QueueItem[]>([])
const resources = ref<ResourcePool>({
  cpu_usage: 0,
  memory_usage: 0,
  active_connections: 0,
  max_cpu: 100,
  max_memory: 100,
  max_connections: 1000
})

const isRefreshing = ref(false)
const isLoading = ref(true)
const showEnqueueModal = ref(false)
const showResourceModal = ref(false)
const isMockData = ref(false)

const enqueueForm = ref({ intent_id: '', priority: 5 })
const resourceForm = ref({ max_cpu: 100, max_memory: 100, max_connections: 1000 })

let refreshInterval: number | null = null

const stats = ref([
  { label: '队列长度', value: 0, displayValue: 0, unit: '个', color: themeColors.primary, icon: '📋', type: 'default' as const },
  { label: '处理中', value: 0, displayValue: 0, unit: '个', color: themeColors.warning, icon: '⚙️', type: 'warning' as const },
  { label: '已完成', value: 0, displayValue: 0, unit: '个', color: themeColors.success, icon: '✅', type: 'success' as const },
  { label: '已失败', value: 0, displayValue: 0, unit: '个', color: themeColors.error, icon: '❌', type: 'danger' as const },
  { label: '平均等待', value: 0, displayValue: 0, unit: '秒', color: themeColors.primaryLight, icon: '⏱️', type: 'default' as const }
])

const isAdmin = computed(() => {
  try {
    const userInfo = localStorage.getItem('user_info')
    if (userInfo) {
      const parsed = JSON.parse(userInfo)
      return parsed?.role === 'admin'
    }
  } catch {}
  return false
})

const getPriorityColor = (priority: number): string => {
  if (priority <= 3) return themeColors.error
  if (priority <= 6) return themeColors.warning
  if (priority <= 9) return themeColors.primary
  return themeColors.success
}

const getPriorityLabel = (priority: number): string => {
  if (priority <= 3) return '紧急'
  if (priority <= 6) return '高优'
  if (priority <= 9) return '普通'
  return '低优'
}

const getStatusColor = (status: string): string => {
  switch (status) {
    case 'queued': return themeColors.primaryLight
    case 'processing': return themeColors.warning
    case 'completed': return themeColors.success
    case 'failed': return themeColors.error
    default: return themeColors.textTertiary
  }
}

const getStatusText = (status: string): string => {
  switch (status) {
    case 'queued': return '排队中'
    case 'processing': return '处理中'
    case 'completed': return '已完成'
    case 'failed': return '已失败'
    default: return status
  }
}

const formatWaitTime = (seconds: number): string => {
  if (seconds < 60) return `${seconds}秒`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  if (mins < 60) return `${mins}分${secs}秒`
  const hours = Math.floor(mins / 60)
  const remainMins = mins % 60
  return `${hours}时${remainMins}分`
}

const getProgressColor = (percentage: number): string => {
  if (percentage >= 90) return themeColors.error
  if (percentage >= 70) return themeColors.warning
  return themeColors.success
}

const fetchQueueData = async (showLoading = false) => {
  if (showLoading) isRefreshing.value = true

  try {
    const [queueResult, resourceResult] = await Promise.allSettled([
      apiClient.get(api.scheduler.queue),
      apiClient.get(api.scheduler.resources)
    ])

    if (queueResult.status === 'fulfilled' && queueResult.value.data) {
      const data = queueResult.value.data
      const items = Array.isArray(data) ? data : (data.items || [])
      queueItems.value = items
      isMockData.value = false

      const queued = items.filter((i: QueueItem) => i.status === 'queued').length
      const processing = items.filter((i: QueueItem) => i.status === 'processing').length
      const completed = items.filter((i: QueueItem) => i.status === 'completed').length
      const failed = items.filter((i: QueueItem) => i.status === 'failed').length
      const waitTimes = items
        .filter((i: QueueItem) => i.status === 'queued' && i.wait_time > 0)
        .map((i: QueueItem) => i.wait_time)
      const avgWait = waitTimes.length > 0
        ? Math.round(waitTimes.reduce((a: number, b: number) => a + b, 0) / waitTimes.length)
        : 0

      stats.value[0].value = queued; stats.value[0].displayValue = queued
      stats.value[1].value = processing; stats.value[1].displayValue = processing
      stats.value[2].value = completed; stats.value[2].displayValue = completed
      stats.value[3].value = failed; stats.value[3].displayValue = failed
      stats.value[4].value = avgWait; stats.value[4].displayValue = avgWait
    } else {
      loadMockData()
      isMockData.value = true
    }

    if (resourceResult.status === 'fulfilled' && resourceResult.value.data) {
      const r = resourceResult.value.data
      resources.value = {
        cpu_usage: r.cpu_usage ?? r.cpu ?? 0,
        memory_usage: r.memory_usage ?? r.memory ?? 0,
        active_connections: r.active_connections ?? r.connections ?? 0,
        max_cpu: r.max_cpu ?? 100,
        max_memory: r.max_memory ?? 100,
        max_connections: r.max_connections ?? 1000
      }
      resourceForm.value = {
        max_cpu: resources.value.max_cpu,
        max_memory: resources.value.max_memory,
        max_connections: resources.value.max_connections
      }
    }
  } catch {
    loadMockData()
    isMockData.value = true
  } finally {
    isRefreshing.value = false
    isLoading.value = false
  }
}

const loadMockData = () => {
  queueItems.value = [
    { intent_id: 'INT-2024-001', priority: 1, position: 1, status: 'processing', wait_time: 45 },
    { intent_id: 'INT-2024-002', priority: 2, position: 2, status: 'queued', wait_time: 120 },
    { intent_id: 'INT-2024-003', priority: 5, position: 3, status: 'queued', wait_time: 85 },
    { intent_id: 'INT-2024-004', priority: 8, position: 4, status: 'queued', wait_time: 30 },
    { intent_id: 'INT-2024-005', priority: 10, position: 5, status: 'queued', wait_time: 10 }
  ]

  resources.value = {
    cpu_usage: 67,
    memory_usage: 54,
    active_connections: 342,
    max_cpu: 100,
    max_memory: 100,
    max_connections: 1000
  }
  resourceForm.value = { max_cpu: 100, max_memory: 100, max_connections: 1000 }

  stats.value[0].value = 4; stats.value[0].displayValue = 4
  stats.value[1].value = 1; stats.value[1].displayValue = 1
  stats.value[2].value = 0; stats.value[2].displayValue = 0
  stats.value[3].value = 0; stats.value[3].displayValue = 0
  stats.value[4].value = 61; stats.value[4].displayValue = 61
}

const handleEnqueue = async () => {
  if (!enqueueForm.value.intent_id.trim()) {
    showToast('请输入意图ID', 'error')
    return
  }
  try {
    await apiClient.post(api.scheduler.enqueue, {
      intent_id: enqueueForm.value.intent_id,
      priority: enqueueForm.value.priority
    })
    showToast('意图已加入队列', 'success')
    showEnqueueModal.value = false
    enqueueForm.value = { intent_id: '', priority: 5 }
    await fetchQueueData()
  } catch (err: any) {
    showToast(`入队失败: ${err.message || '未知错误'}`, 'error')
  }
}

const handleDequeue = async (intentId: string) => {
  try {
    await apiClient.post(api.scheduler.dequeue, { intent_id: intentId })
    showToast('意图已出队', 'success')
    await fetchQueueData()
  } catch (err: any) {
    showToast(`出队失败: ${err.message || '未知错误'}`, 'error')
  }
}

const handlePreempt = async (intentId: string) => {
  try {
    await apiClient.post(api.scheduler.enqueue, { intent_id: intentId, priority: 1, preempt: true })
    showToast('意图已优先处理', 'success')
    await fetchQueueData()
  } catch (err: any) {
    showToast(`优先处理失败: ${err.message || '未知错误'}`, 'error')
  }
}

const handleRebalance = async () => {
  try {
    await apiClient.post(api.scheduler.rebalance)
    showToast('队列已重新平衡', 'success')
    await fetchQueueData()
  } catch (err: any) {
    showToast(`重新平衡失败: ${err.message || '未知错误'}`, 'error')
  }
}

const handleUpdateResources = async () => {
  try {
    await apiClient.put(api.scheduler.resources, {
      max_cpu: resourceForm.value.max_cpu,
      max_memory: resourceForm.value.max_memory,
      max_connections: resourceForm.value.max_connections
    })
    showToast('资源配置已更新', 'success')
    showResourceModal.value = false
    await fetchQueueData()
  } catch (err: any) {
    showToast(`更新失败: ${err.message || '未知错误'}`, 'error')
  }
}

const manualRefresh = async () => {
  isRefreshing.value = true
  try {
    await fetchQueueData(true)
    showToast('数据已刷新', 'success')
  } catch {
    showToast('刷新失败', 'error')
  }
}

onMounted(() => {
  fetchQueueData(true)
  refreshInterval = window.setInterval(() => {
    if (!document.hidden) {
      fetchQueueData(false)
    }
  }, 10000)
})

onUnmounted(() => {
  if (refreshInterval !== null) clearInterval(refreshInterval)
})
</script>

<template>
  <PageLayout title="意图调度器" subtitle="Intent Scheduler 队列管理">
    <template #actions>
      <button type="button" class="action-btn" @click="showEnqueueModal = true" aria-label="入队意图">
        ➕ 入队意图
      </button>
      <button
        v-if="isAdmin"
        type="button"
        class="action-btn warning-btn"
        @click="handleRebalance"
        aria-label="重新平衡队列"
      >
        ⚖️ 重新平衡
      </button>
      <button type="button" class="action-btn" @click="showResourceModal = true" aria-label="更新资源">
        🔧 更新资源
      </button>
      <button
        type="button"
        class="action-btn refresh-btn"
        :class="{ refreshing: isRefreshing }"
        @click="manualRefresh"
        :disabled="isRefreshing"
        aria-label="刷新"
      >
        <span class="refresh-icon" :class="{ spinning: isRefreshing }">🔄</span>
        {{ isRefreshing ? '刷新中...' : '刷新' }}
      </button>
    </template>

    <!-- Stats Bar -->
    <div v-if="isLoading" class="stats-grid">
      <div v-for="i in 5" :key="i" class="stat-card-skeleton">
        <div class="skeleton-line wide"></div>
        <div class="skeleton-line narrow"></div>
      </div>
    </div>
    <div v-else class="stats-grid">
      <StatCard
        v-for="stat in stats"
        :key="stat.label"
        :icon="stat.icon"
        :label="stat.label"
        :value="stat.displayValue"
        :suffix="stat.unit"
        :type="stat.type"
      />
    </div>

    <div class="content-row">
      <!-- Queue Visualization -->
      <div class="panel queue-panel">
        <div class="panel-header">
          <h2 class="panel-title">调度队列</h2>
          <span class="queue-count">共 {{ queueItems.length }} 项</span>
        </div>
        <div class="queue-list">
          <div
            v-for="(item, idx) in queueItems"
            :key="item.intent_id"
            class="queue-item"
            :style="{ '--item-delay': `${idx * 0.04}s` }"
          >
            <div class="queue-item-left">
              <span
                class="priority-badge"
                :style="{
                  background: getPriorityColor(item.priority) + '18',
                  color: getPriorityColor(item.priority),
                  borderColor: getPriorityColor(item.priority) + '30',
                  boxShadow: `0 0 8px ${getPriorityColor(item.priority)}20`
                }"
              >
                P{{ item.priority }}
              </span>
              <div class="queue-item-info">
                <div class="intent-id">{{ item.intent_id }}</div>
                <div class="queue-item-meta">
                  <span class="priority-label" :style="{ color: getPriorityColor(item.priority) }">
                    {{ getPriorityLabel(item.priority) }}
                  </span>
                  <span class="meta-divider">·</span>
                  <span class="position-text">位置 #{{ item.position }}</span>
                </div>
              </div>
            </div>
            <div class="queue-item-center">
              <span
                class="status-badge"
                :style="{
                  color: getStatusColor(item.status),
                  background: getStatusColor(item.status) + '12',
                  borderColor: getStatusColor(item.status) + '25'
                }"
              >
                {{ getStatusText(item.status) }}
              </span>
              <span class="wait-time">⏱ {{ formatWaitTime(item.wait_time) }}</span>
            </div>
            <div class="queue-item-actions">
              <button
                type="button"
                class="action-btn small danger-btn"
                @click="handleDequeue(item.intent_id)"
                :disabled="item.status === 'processing'"
                aria-label="出队"
              >
                出队
              </button>
              <button
                type="button"
                class="action-btn small"
                @click="handlePreempt(item.intent_id)"
                :disabled="item.priority <= 3 || item.status === 'processing'"
                aria-label="优先处理"
              >
                优先
              </button>
            </div>
          </div>
          <div v-if="queueItems.length === 0" class="empty-state">
            <div class="empty-icon">📭</div>
            <div>队列为空，暂无待调度意图</div>
          </div>
        </div>
      </div>

      <!-- Resource Pool -->
      <div class="panel resource-panel">
        <div class="panel-header">
          <h2 class="panel-title">资源池</h2>
        </div>
        <div class="resource-list">
          <div class="resource-item">
            <div class="resource-header">
              <span class="resource-label">🖥️ CPU 使用率</span>
              <span class="resource-value" :style="{ color: getProgressColor(resources.cpu_usage) }">
                {{ resources.cpu_usage }}%
              </span>
            </div>
            <div class="progress-bar-track">
              <div
                class="progress-bar-fill"
                :style="{
                  width: `${resources.cpu_usage}%`,
                  background: `linear-gradient(90deg, ${getProgressColor(resources.cpu_usage)}, ${getProgressColor(resources.cpu_usage)}88)`,
                  boxShadow: `0 0 12px ${getProgressColor(resources.cpu_usage)}30`
                }"
              >
                <span v-if="resources.cpu_usage > 15" class="progress-bar-text">
                  {{ resources.cpu_usage }}%
                </span>
              </div>
            </div>
          </div>

          <div class="resource-item">
            <div class="resource-header">
              <span class="resource-label">💾 内存使用率</span>
              <span class="resource-value" :style="{ color: getProgressColor(resources.memory_usage) }">
                {{ resources.memory_usage }}%
              </span>
            </div>
            <div class="progress-bar-track">
              <div
                class="progress-bar-fill"
                :style="{
                  width: `${resources.memory_usage}%`,
                  background: `linear-gradient(90deg, ${getProgressColor(resources.memory_usage)}, ${getProgressColor(resources.memory_usage)}88)`,
                  boxShadow: `0 0 12px ${getProgressColor(resources.memory_usage)}30`
                }"
              >
                <span v-if="resources.memory_usage > 15" class="progress-bar-text">
                  {{ resources.memory_usage }}%
                </span>
              </div>
            </div>
          </div>

          <div class="resource-item">
            <div class="resource-header">
              <span class="resource-label">🔗 活跃连接</span>
              <span class="resource-value" :style="{ color: getProgressColor((resources.active_connections / resources.max_connections) * 100) }">
                {{ resources.active_connections }} / {{ resources.max_connections }}
              </span>
            </div>
            <div class="progress-bar-track">
              <div
                class="progress-bar-fill"
                :style="{
                  width: `${(resources.active_connections / resources.max_connections) * 100}%`,
                  background: `linear-gradient(90deg, ${getProgressColor((resources.active_connections / resources.max_connections) * 100)}, ${getProgressColor((resources.active_connections / resources.max_connections) * 100)}88)`,
                  boxShadow: `0 0 12px ${getProgressColor((resources.active_connections / resources.max_connections) * 100)}30`
                }"
              >
                <span v-if="(resources.active_connections / resources.max_connections) * 100 > 15" class="progress-bar-text">
                  {{ Math.round((resources.active_connections / resources.max_connections) * 100) }}%
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Priority Legend -->
        <div class="priority-legend">
          <div class="legend-title">优先级图例</div>
          <div class="legend-items">
            <div class="legend-item">
              <span class="legend-dot" :style="{ background: themeColors.error, boxShadow: `0 0 6px ${themeColors.error}40` }"></span>
              <span class="legend-label">P1-3 紧急</span>
            </div>
            <div class="legend-item">
              <span class="legend-dot" :style="{ background: themeColors.warning, boxShadow: `0 0 6px ${themeColors.warning}40` }"></span>
              <span class="legend-label">P4-6 高优</span>
            </div>
            <div class="legend-item">
              <span class="legend-dot" :style="{ background: themeColors.primary, boxShadow: `0 0 6px ${themeColors.primary}40` }"></span>
              <span class="legend-label">P7-9 普通</span>
            </div>
            <div class="legend-item">
              <span class="legend-dot" :style="{ background: themeColors.success, boxShadow: `0 0 6px ${themeColors.success}40` }"></span>
              <span class="legend-label">P10 低优</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Enqueue Modal -->
    <Teleport to="body">
      <div v-if="showEnqueueModal" class="modal-overlay" @click.self="showEnqueueModal = false">
        <div class="modal-content">
          <div class="modal-header">
            <h3 class="modal-title">入队意图</h3>
            <button type="button" class="modal-close" @click="showEnqueueModal = false" aria-label="关闭">✕</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label class="form-label">意图 ID</label>
              <input
                v-model="enqueueForm.intent_id"
                type="text"
                class="form-input"
                placeholder="输入意图ID，如 INT-2024-006"
              />
            </div>
            <div class="form-group">
              <label class="form-label">优先级 (1-10)</label>
              <div class="priority-input-group">
                <input
                  v-model.number="enqueueForm.priority"
                  type="range"
                  min="1"
                  max="10"
                  class="priority-slider"
                />
                <span
                  class="priority-display"
                  :style="{ color: getPriorityColor(enqueueForm.priority) }"
                >
                  P{{ enqueueForm.priority }} - {{ getPriorityLabel(enqueueForm.priority) }}
                </span>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="action-btn" @click="showEnqueueModal = false">取消</button>
            <button type="button" class="action-btn primary-btn" @click="handleEnqueue">确认入队</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Resource Modal -->
    <Teleport to="body">
      <div v-if="showResourceModal" class="modal-overlay" @click.self="showResourceModal = false">
        <div class="modal-content">
          <div class="modal-header">
            <h3 class="modal-title">更新资源配置</h3>
            <button type="button" class="modal-close" @click="showResourceModal = false" aria-label="关闭">✕</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label class="form-label">最大 CPU (%)</label>
              <input
                v-model.number="resourceForm.max_cpu"
                type="number"
                min="1"
                max="100"
                class="form-input"
                placeholder="100"
              />
            </div>
            <div class="form-group">
              <label class="form-label">最大内存 (%)</label>
              <input
                v-model.number="resourceForm.max_memory"
                type="number"
                min="1"
                max="100"
                class="form-input"
                placeholder="100"
              />
            </div>
            <div class="form-group">
              <label class="form-label">最大连接数</label>
              <input
                v-model.number="resourceForm.max_connections"
                type="number"
                min="1"
                class="form-input"
                placeholder="1000"
              />
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="action-btn" @click="showResourceModal = false">取消</button>
            <button type="button" class="action-btn primary-btn" @click="handleUpdateResources">确认更新</button>
          </div>
        </div>
      </div>
    </Teleport>
  </PageLayout>
</template>

<style scoped lang="scss">
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

.skeleton-line {
  height: 0.875rem;
  background: var(--gradient-shimmer);
  background-size: 200% 100%;
  border-radius: var(--radius-sm);
  margin-bottom: 0.625rem;
  animation: skeleton-slide 1.5s ease-in-out infinite;
}



@keyframes skeleton-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.skeleton-line.wide { width: 70%; }
.skeleton-line.narrow { width: 40%; }

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
}

.action-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary);
  box-shadow: var(--shadow-glow-primary);
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

.action-btn.small {
  padding: var(--spacing-xs) 0.625rem;
  font-size: var(--font-size-xs);
  min-height: 32px;
}

.action-btn.primary-btn {
  background: linear-gradient(135deg, var(--color-primary-bg), var(--gradient-primary));
  border-color: var(--color-primary-border);
  color: var(--color-primary-light);
}

.action-btn.primary-btn:hover:not(:disabled) {
  background: var(--gradient-primary-hover);
  box-shadow: var(--shadow-glow-primary);
  transform: scale(1.02);
}

.action-btn.primary-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.warning-btn {
  background: var(--color-warning-bg);
  color: var(--color-warning-light);
  border-color: var(--color-warning-border);
}

.warning-btn:hover:not(:disabled) {
  background: var(--color-warning-hover);
  border-color: var(--color-warning);
  box-shadow: var(--shadow-glow-warning);
  color: var(--color-warning-light);
  transform: scale(1.02);
}

.warning-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.danger-btn {
  background: var(--color-error-bg);
  color: var(--color-error-light);
  border-color: var(--color-error-border);
}

.danger-btn:hover:not(:disabled) {
  background: var(--color-error-hover);
  border-color: var(--color-error);
  box-shadow: var(--shadow-glow-error);
  color: var(--color-error-light);
  transform: scale(1.02);
}

.danger-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.refresh-icon {
  display: inline-block;
  transition: transform 0.3s ease;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}



/* ===== Content Layout ===== */
.content-row {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--panel-gap);
}

.panel {
  background: var(--gradient-glass);
  border-radius: var(--card-border-radius);
  padding: var(--card-padding);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-card);
  will-change: transform, opacity;
  animation: panel-enter 0.5s var(--ease-out) backwards;
  transition: border-color 0.3s var(--ease-out), box-shadow 0.3s var(--ease-out);
}

.panel:hover {
  border-color: var(--color-border-secondary);
  box-shadow: var(--shadow-card-hover);
}

.content-row .panel:nth-child(1) { animation-delay: 0.3s; }
.content-row .panel:nth-child(2) { animation-delay: 0.35s; }



.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.panel-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: 0;
  padding-left: 0.625rem;
  border-left: 3px solid var(--color-primary);
}

.queue-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  padding: 0.125rem 0.5rem;
  background: var(--color-bg-hover);
  border-radius: var(--radius-full);
}

/* ===== Queue List ===== */
.queue-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 28rem;
  overflow-y: auto;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem var(--spacing-md);
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  transition: all 0.25s var(--ease-out);
  will-change: transform, opacity;
  animation: item-enter 0.3s var(--ease-out) backwards;
  animation-delay: var(--item-delay, 0s);
}



.queue-item:hover {
  background: var(--color-bg-glass-strong);
  border-color: var(--color-primary-border);
  transform: translateX(4px);
  box-shadow: var(--shadow-glow-primary);
}

.queue-item-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex: 1;
  min-width: 0;
}

.priority-badge {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-sm);
  border: 1px solid;
  flex-shrink: 0;
  font-family: var(--font-family-mono);
  min-width: 2.5rem;
  text-align: center;
}

.queue-item-info {
  min-width: 0;
}

.intent-id {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.queue-item-meta {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-top: 2px;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.priority-label {
  font-weight: var(--font-weight-semibold);
}

.meta-divider {
  opacity: 0.4;
}

.queue-item-center {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-shrink: 0;
}

.status-badge {
  font-size: var(--font-size-xs);
  padding: 0.1875rem var(--spacing-sm);
  border-radius: var(--radius-sm);
  border: 1px solid;
  white-space: nowrap;
  transition: all 0.2s var(--ease-out);
}

.queue-item:hover .status-badge {
  transform: scale(1.05);
  box-shadow: 0 0 8px currentColor;
}

.wait-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  font-family: var(--font-family-mono);
  white-space: nowrap;
}

.queue-item-actions {
  display: flex;
  gap: 0.375rem;
  flex-shrink: 0;
}

/* ===== Resource Panel ===== */
.resource-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.resource-item {
  padding: var(--spacing-md);
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  transition: all 0.25s var(--ease-out);
}

.resource-item:hover {
  background: var(--color-bg-glass-strong);
  border-color: var(--color-primary-border);
}

.resource-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.resource-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

.resource-value {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-bold);
  font-variant-numeric: tabular-nums;
}

.progress-bar-track {
  height: 0.625rem;
  background: var(--color-bg-quaternary);
  border-radius: 0.3125rem;
  overflow: hidden;
  border: 1px solid var(--color-border-primary);
}

.progress-bar-fill {
  height: 100%;
  border-radius: 0.3125rem;
  transition: width 0.4s var(--ease-out), background 0.3s var(--ease-out);
  position: relative;
  min-width: 4px;
}

.progress-bar-text {
  position: absolute;
  right: var(--spacing-sm);
  top: 50%;
  transform: translateY(-50%);
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-primary);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}

/* ===== Priority Legend ===== */
.priority-legend {
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-primary);
}

.legend-title {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-sm);
  font-weight: var(--font-weight-medium);
}

.legend-items {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.375rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-sm);
  transition: background 0.2s var(--ease-out);
}

.legend-item:hover {
  background: var(--color-bg-hover);
}

.legend-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

/* ===== Empty State ===== */
.empty-state {
  text-align: center;
  padding: var(--spacing-xl) var(--spacing-lg);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
}

.empty-icon {
  font-size: var(--font-size-3xl);
  margin-bottom: var(--spacing-sm);
  opacity: 0.5;
  filter: grayscale(0.3);
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



.modal-content {
  background: var(--color-bg-elevated);
  border-radius: var(--modal-border-radius);
  border: 1px solid var(--color-border-primary);
  padding: var(--modal-padding);
  box-shadow: var(--modal-shadow);
  animation: modal-content-in 0.25s var(--ease-out);
  max-width: 28rem;
  width: 90vw;
}



.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-border-primary);
}

.modal-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
}

.modal-close {
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
  font-size: var(--font-size-sm);
  transition: all 0.2s var(--ease-out);
}

.modal-close:hover {
  background: var(--color-error-bg);
  color: var(--color-error-light);
  border-color: var(--color-error-border);
}

.modal-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.form-label {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.form-input {
  width: 100%;
  padding: var(--input-padding);
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-secondary);
  font-size: var(--font-size-md);
  transition: all 0.2s ease;
  outline: none;
  box-sizing: border-box;
}

.form-input:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
}

.form-input::placeholder {
  color: var(--color-text-disabled);
}

.priority-input-group {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.priority-slider {
  flex: 1;
  -webkit-appearance: none;
  appearance: none;
  height: 0.375rem;
  background: var(--color-bg-quaternary);
  border-radius: 0.1875rem;
  outline: none;
  border: 1px solid var(--color-border-primary);
}

.priority-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  background: var(--color-primary);
  cursor: pointer;
  box-shadow: var(--shadow-glow-primary);
  transition: all 0.2s ease;
}

.priority-slider::-webkit-slider-thumb:hover {
  transform: scale(1.2);
  box-shadow: var(--shadow-glow-primary);
}

.priority-slider::-moz-range-thumb {
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  background: var(--color-primary);
  cursor: pointer;
  border: none;
  box-shadow: var(--shadow-glow-primary);
}

.priority-display {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
  font-family: var(--font-family-mono);
  white-space: nowrap;
  min-width: 5.5rem;
  text-align: right;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-primary);
}

/* ===== Responsive ===== */
@media (max-width: 1200px) {
  .content-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .queue-item {
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .queue-item-center {
    width: 100%;
    justify-content: flex-start;
  }
  .queue-item-actions {
    width: 100%;
  }
  .legend-items {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
  .panel {
    padding: 0.75rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .panel,
  .queue-item,
  .modal-overlay,
  .modal-content {
    animation: none;
  }
  .refresh-icon.spinning {
    animation: none;
  }
  .stat-card-skeleton,
  .skeleton-line {
    animation: none;
  }
}
</style>
