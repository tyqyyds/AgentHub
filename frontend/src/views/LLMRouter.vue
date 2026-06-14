<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useLogger } from '@/utils/logger'
import { api, apiClient } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'
import PageLayout from '@/components/PageLayout.vue'

const { info, warn } = useLogger()

interface Provider {
  name: string
  model: string
  api_base: string
  api_key: string
  priority: number
  max_tokens: number
  temperature: number
  is_active: boolean
  request_count: number
  avg_latency: number
  error_rate: number
}

interface Metrics {
  total_requests: number
  avg_latency: number
  total_providers: number
  active_providers: number
}

interface Recommendation {
  task_type: string
  provider: string
  model: string
  reason: string
}

const providers = ref<Provider[]>([])
const metrics = ref<Metrics>({ total_requests: 0, avg_latency: 0, total_providers: 0, active_providers: 0 })
const recommendations = ref<Recommendation[]>([])
const isLoading = ref(true)
const isRefreshing = ref(false)
const showFormDialog = ref(false)
const showDeleteConfirm = ref(false)
const isEditing = ref(false)
const isSubmitting = ref(false)
const deletingProvider = ref<string>('')
const taskTypeFilter = ref('all')

const TASK_TYPES = ['chat', 'code', 'analysis', 'translation', 'summarization']

const form = ref({
  name: '',
  model: '',
  api_base: '',
  api_key: '',
  priority: 1,
  max_tokens: 4096,
  temperature: 0.7
})

const resetForm = () => {
  form.value = { name: '', model: '', api_base: '', api_key: '', priority: 1, max_tokens: 4096, temperature: 0.7 }
}

const statsBar = computed(() => [
  { label: '供应商总数', value: metrics.value.total_providers, icon: '🏢', color: '#165DFF' },
  { label: '活跃供应商', value: metrics.value.active_providers, icon: '✅', color: '#52C41A' },
  { label: '总请求数', value: metrics.value.total_requests, icon: '📡', color: '#FAAD14' },
  { label: '平均延迟', value: `${metrics.value.avg_latency}ms`, icon: '⚡', color: '#69B1FF' }
])

const filteredRecommendations = computed(() => {
  if (taskTypeFilter.value === 'all') return recommendations.value
  return recommendations.value.filter(r => r.task_type === taskTypeFilter.value)
})

const loadMockData = () => {
  providers.value = [
    {
      name: 'deepseek',
      model: 'deepseek-chat',
      api_base: 'https://api.deepseek.com/v1',
      api_key: 'sk-************',
      priority: 1,
      max_tokens: 8192,
      temperature: 0.7,
      is_active: true,
      request_count: 12480,
      avg_latency: 320,
      error_rate: 0.012
    },
    {
      name: 'zhipu-glm',
      model: 'glm-4',
      api_base: 'https://open.bigmodel.cn/api/paas/v4',
      api_key: '************',
      priority: 2,
      max_tokens: 4096,
      temperature: 0.6,
      is_active: true,
      request_count: 8350,
      avg_latency: 450,
      error_rate: 0.025
    }
  ]
  metrics.value = {
    total_providers: 2,
    active_providers: 2,
    total_requests: 20830,
    avg_latency: 385
  }
  recommendations.value = [
    { task_type: 'chat', provider: 'deepseek', model: 'deepseek-chat', reason: '低延迟、高并发，适合对话场景' },
    { task_type: 'code', provider: 'deepseek', model: 'deepseek-chat', reason: '代码生成准确率高，延迟低' },
    { task_type: 'analysis', provider: 'zhipu-glm', model: 'glm-4', reason: '长文本理解能力强，适合深度分析' },
    { task_type: 'translation', provider: 'zhipu-glm', model: 'glm-4', reason: '多语言翻译质量稳定' },
    { task_type: 'summarization', provider: 'deepseek', model: 'deepseek-chat', reason: '摘要精度高，响应速度快' }
  ]
}

const fetchProviders = async () => {
  try {
    const res = await apiClient.get<Provider[]>(api.llmRouter.providers)
    if (res.data) {
      const items = Array.isArray(res.data) ? res.data : (res.data?.items || Object.values(res.data))
      if (items.length > 0) {
        providers.value = items
        return true
      }
    }
    return false
  } catch {
    return false
  }
}

const fetchMetrics = async () => {
  try {
    const res = await apiClient.get<Metrics>(api.llmRouter.metrics)
    if (res.data) {
      metrics.value = res.data
      return true
    }
    return false
  } catch {
    return false
  }
}

const fetchRecommendations = async () => {
  try {
    const results = await Promise.allSettled(
      TASK_TYPES.map(t => apiClient.get<Recommendation>(api.llmRouter.recommendations(t)))
    )
    const recs: Recommendation[] = []
    results.forEach(r => {
      if (r.status === 'fulfilled' && r.value.data) recs.push(r.value.data)
    })
    if (recs.length > 0) {
      recommendations.value = recs
      return true
    }
    return false
  } catch {
    return false
  }
}

const fetchAll = async (showLoading = false) => {
  if (showLoading) isLoading.value = true
  isRefreshing.value = true
  try {
    const [pOk, mOk, rOk] = await Promise.all([
      fetchProviders(),
      fetchMetrics(),
      fetchRecommendations()
    ])
    if (!pOk || !mOk) {
      loadMockData()
      info('LLM Router: 使用模拟数据')
    }
  } catch {
    loadMockData()
    warn('LLM Router: 数据加载失败，使用模拟数据')
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

const handleRefresh = async () => {
  await fetchAll(true)
  showToast('数据已刷新', 'success')
}

const openAddDialog = () => {
  isEditing.value = false
  resetForm()
  showFormDialog.value = true
}

const openEditDialog = (provider: Provider) => {
  isEditing.value = true
  form.value = {
    name: provider.name,
    model: provider.model,
    api_base: provider.api_base,
    api_key: '',
    priority: provider.priority,
    max_tokens: provider.max_tokens,
    temperature: provider.temperature
  }
  showFormDialog.value = true
}

const closeFormDialog = () => {
  showFormDialog.value = false
  resetForm()
}

const handleSubmit = async () => {
  if (!form.value.name || !form.value.model || !form.value.api_base) {
    showToast('请填写必填字段', 'error')
    return
  }
  isSubmitting.value = true
  try {
    const payload: Record<string, any> = { ...form.value }
    if (!payload.api_key) delete payload.api_key

    if (isEditing.value) {
      await apiClient.put(api.llmRouter.providerByName(form.value.name), payload)
      showToast('供应商已更新', 'success')
    } else {
      await apiClient.post(api.llmRouter.providers, payload)
      showToast('供应商已添加', 'success')
    }
    closeFormDialog()
    await fetchAll()
  } catch (err: any) {
    showToast(err.message || '操作失败', 'error')
  } finally {
    isSubmitting.value = false
  }
}

const handleToggle = async (provider: Provider) => {
  try {
    await apiClient.post(api.llmRouter.toggleProvider(provider.name))
    provider.is_active = !provider.is_active
    showToast(`${provider.name} 已${provider.is_active ? '启用' : '停用'}`, 'success')
    await fetchMetrics()
  } catch (err: any) {
    showToast(err.message || '切换失败', 'error')
  }
}

const confirmDelete = (name: string) => {
  deletingProvider.value = name
  showDeleteConfirm.value = true
}

const handleDelete = async () => {
  try {
    await apiClient.delete(api.llmRouter.providerByName(deletingProvider.value))
    showToast('供应商已删除', 'success')
    showDeleteConfirm.value = false
    await fetchAll()
  } catch (err: any) {
    showToast(err.message || '删除失败', 'error')
  }
}

const getErrorRateColor = (rate: number) => {
  if (rate >= 0.05) return '#FF4D4F'
  if (rate >= 0.02) return '#FAAD14'
  return '#52C41A'
}

const getLatencyColor = (ms: number) => {
  if (ms >= 800) return '#FF4D4F'
  if (ms >= 400) return '#FAAD14'
  return '#52C41A'
}

const formatNumber = (n: number) => {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

onMounted(() => {
  fetchAll(true)
  info('LLM Router 页面已加载')
})
</script>

<template>
  <PageLayout title="LLM 路由管理" subtitle="大模型供应商配置与智能路由">
    <template #actions>
      <button type="button" class="action-btn" @click="handleRefresh" :disabled="isRefreshing" aria-label="刷新数据">
        <span class="refresh-icon" :class="{ spinning: isRefreshing }">🔄</span>
        {{ isRefreshing ? '刷新中...' : '刷新' }}
      </button>
      <button type="button" class="action-btn primary-btn" @click="openAddDialog" aria-label="添加供应商">
        ➕ 添加供应商
      </button>
    </template>

    <!-- 统计栏 -->
    <div v-if="isLoading" class="stats-grid">
      <div v-for="i in 4" :key="i" class="stat-skeleton">
        <div class="skeleton-line wide"></div>
        <div class="skeleton-line narrow"></div>
      </div>
    </div>
    <div v-else class="stats-grid">
      <div v-for="stat in statsBar" :key="stat.label" class="stat-card">
        <div class="stat-icon-wrap" :style="{ background: stat.color + '18', borderColor: stat.color + '30' }">
          <span class="stat-icon">{{ stat.icon }}</span>
        </div>
        <div class="stat-info">
          <span class="stat-value">{{ stat.value }}</span>
          <span class="stat-label">{{ stat.label }}</span>
        </div>
      </div>
    </div>

    <!-- 供应商列表 -->
    <div class="panel">
      <div class="panel-header">
        <h2 class="panel-title">供应商列表</h2>
        <span class="provider-count">{{ providers.length }} 个供应商</span>
      </div>

      <div v-if="isLoading" class="loading-placeholder">
        <div v-for="i in 2" :key="i" class="provider-skeleton">
          <div class="skeleton-line wide"></div>
          <div class="skeleton-line medium"></div>
        </div>
      </div>

      <div v-else-if="providers.length === 0" class="empty-state">
        <div class="empty-icon">🤖</div>
        <div>暂无供应商，点击"添加供应商"开始配置</div>
      </div>

      <div v-else class="provider-list">
        <div
          v-for="provider in providers"
          :key="provider.name"
          class="provider-card"
          :class="{ inactive: !provider.is_active }"
        >
          <div class="provider-main">
            <div class="provider-header">
              <div class="provider-identity">
                <span class="provider-name">{{ provider.name }}</span>
                <span class="provider-model badge-primary">{{ provider.model }}</span>
              </div>
              <div class="provider-status">
                <button
                  type="button"
                  class="toggle-btn"
                  :class="{ active: provider.is_active }"
                  @click="handleToggle(provider)"
                  :aria-label="provider.is_active ? '停用' : '启用'"
                >
                  <span class="toggle-dot"></span>
                  {{ provider.is_active ? '运行中' : '已停用' }}
                </button>
              </div>
            </div>

            <div class="provider-metrics">
              <div class="metric-item">
                <span class="metric-label">优先级</span>
                <span class="metric-value priority-badge">P{{ provider.priority }}</span>
              </div>
              <div class="metric-item">
                <span class="metric-label">请求数</span>
                <span class="metric-value">{{ formatNumber(provider.request_count) }}</span>
              </div>
              <div class="metric-item">
                <span class="metric-label">平均延迟</span>
                <span class="metric-value" :style="{ color: getLatencyColor(provider.avg_latency) }">{{ provider.avg_latency }}ms</span>
              </div>
              <div class="metric-item">
                <span class="metric-label">错误率</span>
                <span class="metric-value" :style="{ color: getErrorRateColor(provider.error_rate) }">{{ (provider.error_rate * 100).toFixed(1) }}%</span>
              </div>
            </div>
          </div>

          <div class="provider-actions">
            <button type="button" class="action-btn small" @click="openEditDialog(provider)" aria-label="编辑">✏️ 编辑</button>
            <button type="button" class="action-btn small danger-btn" @click="confirmDelete(provider.name)" aria-label="删除">🗑️ 删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 推荐路由 -->
    <div class="panel">
      <div class="panel-header">
        <h2 class="panel-title">智能推荐路由</h2>
        <div class="filter-group">
          <button
            type="button"
            class="filter-btn"
            :class="{ active: taskTypeFilter === 'all' }"
            @click="taskTypeFilter = 'all'"
          >全部</button>
          <button
            v-for="t in TASK_TYPES"
            :key="t"
            type="button"
            class="filter-btn"
            :class="{ active: taskTypeFilter === t }"
            @click="taskTypeFilter = t"
          >{{ t }}</button>
        </div>
      </div>

      <div v-if="filteredRecommendations.length === 0" class="empty-state small">
        暂无推荐数据
      </div>
      <div v-else class="recommendation-list">
        <div
          v-for="rec in filteredRecommendations"
          :key="rec.task_type"
          class="recommendation-card"
        >
          <div class="rec-task">
            <span class="rec-task-badge">{{ rec.task_type }}</span>
          </div>
          <div class="rec-arrow">→</div>
          <div class="rec-provider">
            <span class="rec-provider-name">{{ rec.provider }}</span>
            <span class="rec-model">{{ rec.model }}</span>
          </div>
          <div class="rec-reason">{{ rec.reason }}</div>
        </div>
      </div>
    </div>

    <!-- 指标概览 -->
    <div class="panel">
      <div class="panel-header">
        <h2 class="panel-title">指标概览</h2>
      </div>
      <div class="metrics-overview">
        <div class="metric-block">
          <div class="metric-block-value">{{ formatNumber(metrics.total_requests) }}</div>
          <div class="metric-block-label">总请求量</div>
          <div class="metric-bar">
            <div class="metric-bar-fill" :style="{ width: '100%', background: 'var(--gradient-primary)' }"></div>
          </div>
        </div>
        <div class="metric-block">
          <div class="metric-block-value" :style="{ color: getLatencyColor(metrics.avg_latency) }">{{ metrics.avg_latency }}ms</div>
          <div class="metric-block-label">平均延迟</div>
          <div class="metric-bar">
            <div class="metric-bar-fill" :style="{ width: Math.min(100, (metrics.avg_latency / 1000) * 100) + '%', background: getLatencyColor(metrics.avg_latency) }"></div>
          </div>
        </div>
        <div class="metric-block">
          <div class="metric-block-value success">{{ metrics.active_providers }}/{{ metrics.total_providers }}</div>
          <div class="metric-block-label">活跃率</div>
          <div class="metric-bar">
            <div class="metric-bar-fill" :style="{ width: metrics.total_providers ? (metrics.active_providers / metrics.total_providers) * 100 + '%' : '0%', background: 'var(--gradient-success)' }"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加/编辑弹窗 -->
    <Teleport to="body">
      <div v-if="showFormDialog" class="modal-overlay" @click.self="closeFormDialog">
        <div class="modal-content">
          <div class="modal-header">
            <h3 class="modal-title">{{ isEditing ? '编辑供应商' : '添加供应商' }}</h3>
            <button type="button" class="modal-close" @click="closeFormDialog" aria-label="关闭">✕</button>
          </div>
          <div class="modal-body">
            <div class="form-grid">
              <div class="form-group">
                <label class="form-label">名称 *</label>
                <input
                  v-model="form.name"
                  class="form-input"
                  placeholder="如: deepseek"
                  :disabled="isEditing"
                />
              </div>
              <div class="form-group">
                <label class="form-label">模型 *</label>
                <input v-model="form.model" class="form-input" placeholder="如: deepseek-chat" />
              </div>
              <div class="form-group">
                <label class="form-label">API Base *</label>
                <input v-model="form.api_base" class="form-input" placeholder="https://api.deepseek.com/v1" />
              </div>
              <div class="form-group">
                <label class="form-label">API Key</label>
                <input v-model="form.api_key" class="form-input" type="password" placeholder="sk-************" />
              </div>
              <div class="form-group">
                <label class="form-label">优先级</label>
                <input v-model.number="form.priority" class="form-input" type="number" min="1" max="10" />
              </div>
              <div class="form-group">
                <label class="form-label">Max Tokens</label>
                <input v-model.number="form.max_tokens" class="form-input" type="number" min="1" max="128000" />
              </div>
              <div class="form-group">
                <label class="form-label">Temperature</label>
                <input v-model.number="form.temperature" class="form-input" type="number" min="0" max="2" step="0.1" />
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="action-btn" @click="closeFormDialog">取消</button>
            <button type="button" class="action-btn primary-btn" @click="handleSubmit" :disabled="isSubmitting">
              {{ isSubmitting ? '提交中...' : (isEditing ? '保存' : '添加') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 删除确认弹窗 -->
    <Teleport to="body">
      <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
        <div class="modal-content small">
          <div class="modal-header">
            <h3 class="modal-title">确认删除</h3>
            <button type="button" class="modal-close" @click="showDeleteConfirm = false" aria-label="关闭">✕</button>
          </div>
          <div class="modal-body">
            <p class="confirm-text">确定要删除供应商 <strong>{{ deletingProvider }}</strong> 吗？此操作不可撤销。</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="action-btn" @click="showDeleteConfirm = false">取消</button>
            <button type="button" class="action-btn danger-btn" @click="handleDelete">确认删除</button>
          </div>
        </div>
      </div>
    </Teleport>
  </PageLayout>
</template>

<style scoped lang="scss">
/* ===== 统计栏 ===== */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(var(--grid-min-col), 1fr));
  gap: var(--panel-gap);
  margin-bottom: var(--panel-gap);
}

.stat-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--card-padding);
  background: var(--gradient-glass);
  border-radius: var(--card-border-radius);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-card);
  transition: all 0.25s ease;
  will-change: transform, opacity;
  animation: card-enter 0.5s var(--ease-out) backwards;

  &:hover {
    border-color: var(--color-border-secondary);
    box-shadow: var(--shadow-card-hover);
    transform: translateY(-2px);
  }

  &:active {
    transform: translateY(0) scale(0.98);
  }
}

.stat-card:nth-child(1) { animation-delay: 0s; }
.stat-card:nth-child(2) { animation-delay: 0.05s; }
.stat-card:nth-child(3) { animation-delay: 0.1s; }
.stat-card:nth-child(4) { animation-delay: 0.15s; }



.stat-icon-wrap {
  width: 3rem;
  height: 3rem;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid;
  flex-shrink: 0;
}

.stat-icon { font-size: var(--font-size-lg); }

.stat-info { display: flex; flex-direction: column; gap: 2px; }

.stat-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
  line-height: var(--line-height-tight);
}

.stat-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

/* ===== 面板 ===== */
.panel {
  background: var(--gradient-glass);
  border-radius: var(--card-border-radius);
  padding: var(--card-padding);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-card);
  margin-bottom: var(--panel-gap);
  will-change: transform, opacity;
  animation: panel-enter 0.5s var(--ease-out) backwards;
  transition: border-color 0.3s var(--ease-out), box-shadow 0.3s var(--ease-out);

  &:hover {
    border-color: var(--color-border-secondary);
    box-shadow: var(--shadow-card-hover);
  }
}



.panel:nth-of-type(1) { animation-delay: 0.2s; }
.panel:nth-of-type(2) { animation-delay: 0.3s; }
.panel:nth-of-type(3) { animation-delay: 0.4s; }

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
  margin: 0;
  padding-left: 0.625rem;
  border-left: 3px solid var(--color-primary);
}

.provider-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  background: var(--color-bg-hover);
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-sm);
}

/* ===== 供应商卡片 ===== */
.provider-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.provider-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--color-bg-input);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  transition: all 0.25s ease;
  will-change: transform, opacity;
  animation: item-enter 0.3s var(--ease-out) backwards;

  &:hover {
    background: var(--color-bg-glass-strong);
    border-color: var(--color-primary-border);
    box-shadow: var(--shadow-glow-primary);
    transform: translateX(4px);
  }

  &.inactive {
    opacity: 0.55;

    &:hover {
      opacity: 0.8;
    }
  }
}



.provider-main { flex: 1; min-width: 0; }

.provider-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-sm);
}

.provider-identity {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.provider-name {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.badge-primary {
  font-size: var(--font-size-xs);
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-sm);
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  white-space: nowrap;
}

/* ===== 开关按钮 ===== */
.toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.75rem;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-primary);
  background: var(--color-bg-hover);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
  min-height: 44px;

  &:hover {
    transform: scale(1.02);
  }

  &:active {
    transform: scale(0.97);
  }

  &.active {
    background: var(--color-success-bg);
    border-color: var(--color-success-border);
    color: var(--color-success);
    box-shadow: var(--shadow-glow-success);
  }
}

.toggle-dot {
  width: 0.375rem;
  height: 0.375rem;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 4px currentColor;
  animation: dot-pulse 2s ease-in-out infinite;
}



/* ===== 指标行 ===== */
.provider-metrics {
  display: flex;
  gap: var(--spacing-lg);
  flex-wrap: wrap;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.metric-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.metric-value {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.priority-badge {
  display: inline-block;
  padding: 0.0625rem 0.375rem;
  background: var(--color-warning-bg);
  color: var(--color-warning);
  border-radius: var(--radius-xs);
  border: 1px solid var(--color-warning-border);
  font-size: var(--font-size-xs);
}

/* ===== 操作按钮 ===== */
.provider-actions {
  display: flex;
  gap: var(--spacing-sm);
  flex-shrink: 0;
}

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

  &:hover:not(:disabled) {
    background: var(--color-primary-hover);
    border-color: var(--color-primary);
    box-shadow: var(--shadow-glow-primary);
    color: var(--color-primary-lighter);
    transform: scale(1.02);
  }

  &:active:not(:disabled) {
    transform: scale(0.97);
  }

  &:disabled {
    opacity: 0.35;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  &.small {
    padding: var(--spacing-xs) 0.625rem;
    font-size: var(--font-size-xs);
    min-height: 44px;
  }

  &.primary-btn {
    background: var(--gradient-primary);
    color: var(--color-text-primary);
    border: none;
    box-shadow: var(--shadow-glow-primary);

    &:hover:not(:disabled) {
      background: var(--gradient-primary-hover);
      box-shadow: var(--shadow-glow-primary);
    }
  }

  &.danger-btn {
    background: var(--color-error-bg);
    color: var(--color-error-light);
    border-color: var(--color-error-border);

    &:hover:not(:disabled) {
      background: var(--color-error-hover);
      border-color: var(--color-error);
      box-shadow: var(--shadow-glow-error);
      transform: scale(1.02);
    }

    &:active:not(:disabled) {
      transform: scale(0.97);
    }
  }
}

.refresh-icon {
  display: inline-block;
  transition: transform 0.3s ease;

  &.spinning {
    animation: spin 1s linear infinite;
  }
}



/* ===== 筛选按钮 ===== */
.filter-group {
  display: flex;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
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
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);

  &:hover {
    background: var(--color-primary-bg);
    color: var(--color-primary-light);
    border-color: var(--color-primary-border);
  }

  &.active {
    background: var(--color-primary-hover);
    color: var(--color-primary-light);
    border-color: var(--color-primary-border);
    box-shadow: var(--shadow-glow-primary);
    font-weight: var(--font-weight-medium);
  }
}

/* ===== 推荐路由 ===== */
.recommendation-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.recommendation-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: 0.75rem var(--spacing-md);
  background: var(--color-bg-input);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  transition: all 0.25s ease;
  will-change: transform, opacity;
  animation: item-enter 0.3s var(--ease-out) backwards;

  &:hover {
    background: var(--color-bg-glass-strong);
    border-color: var(--color-primary-border);
    transform: translateX(4px);
  }
}

.rec-task-badge {
  font-size: var(--font-size-xs);
  padding: 0.25rem 0.625rem;
  border-radius: var(--radius-sm);
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  font-weight: var(--font-weight-medium);
  text-transform: capitalize;
  white-space: nowrap;
}

.rec-arrow {
  font-size: var(--font-size-lg);
  color: var(--color-primary-light);
  font-weight: var(--font-weight-bold);
  flex-shrink: 0;
}

.rec-provider {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 6rem;
}

.rec-provider-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.rec-model {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.rec-reason {
  flex: 1;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  min-width: 0;
}

/* ===== 指标概览 ===== */
.metrics-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: var(--spacing-md);
}

.metric-block {
  padding: var(--spacing-md);
  background: var(--gradient-glass-strong);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-primary);
  transition: all 0.25s ease;

  &:hover {
    border-color: var(--color-primary-border);
    transform: translateY(-2px);
    box-shadow: var(--shadow-glow-primary);
  }
}

.metric-block-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
  line-height: var(--line-height-tight);

  &.success { color: var(--color-success); }
}

.metric-block-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-top: var(--spacing-xs);
  margin-bottom: var(--spacing-sm);
}

.metric-bar {
  height: 0.375rem;
  background: var(--color-bg-quaternary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.metric-bar-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width 0.5s var(--ease-out);
}

/* ===== 弹窗 ===== */
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
  max-height: 85vh;
  overflow-y: auto;
  max-width: 600px;
  width: 90vw;

  &.small {
    max-width: 420px;
  }
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
  font-size: var(--font-size-lg);
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
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);

  &:hover {
    background: var(--color-error-bg);
    color: var(--color-error-light);
    border-color: var(--color-error-border);
    transform: scale(1.02);
  }

  &:active {
    transform: scale(0.97);
  }
}

.modal-body {
  margin-bottom: var(--spacing-lg);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-primary);
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-md);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;

  &:nth-child(odd):last-child {
    grid-column: 1 / -1;
  }
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

  &:focus {
    border-color: var(--input-border-focus);
    box-shadow: var(--input-shadow-focus);
  }

  &::placeholder {
    color: var(--color-text-disabled);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.confirm-text {
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  line-height: var(--line-height-normal);
  margin: 0;

  strong {
    color: var(--color-error);
  }
}

/* ===== 空状态 ===== */
.empty-state {
  text-align: center;
  padding: var(--spacing-xl) var(--spacing-lg);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);

  &.small {
    padding: var(--spacing-md);
    font-size: var(--font-size-sm);
  }
}

.empty-icon {
  font-size: var(--font-size-3xl);
  margin-bottom: var(--spacing-sm);
  opacity: 0.5;
}

/* ===== 骨架屏 ===== */
.stat-skeleton {
  padding: var(--card-padding);
  background: var(--gradient-glass);
  border-radius: var(--card-border-radius);
  border: var(--card-border);
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-line {
  height: 0.875rem;
  background: var(--gradient-shimmer);
  background-size: 200% 100%;
  border-radius: var(--radius-sm);
  margin-bottom: 0.625rem;
  animation: skeleton-slide 1.5s ease-in-out infinite;

  &.wide { width: 70%; }
  &.narrow { width: 40%; }
  &.medium { width: 55%; height: 1.875rem; margin-top: var(--spacing-md); }
}



.provider-skeleton {
  padding: var(--spacing-md);
  background: var(--color-bg-input);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-primary);
  margin-bottom: var(--spacing-sm);
}

.loading-placeholder {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

/* ===== 响应式 ===== */
@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .provider-card {
    flex-direction: column;
    align-items: flex-start;
  }

  .provider-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .provider-metrics {
    gap: var(--spacing-md);
  }

  .recommendation-card {
    flex-wrap: wrap;
  }

  .rec-reason {
    width: 100%;
    margin-top: var(--spacing-xs);
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .metrics-overview {
    grid-template-columns: 1fr;
  }

  .filter-group {
    flex-wrap: wrap;
  }

  .action-btn {
    min-height: 2.75rem;
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .panel {
    padding: 0.75rem;
  }

  .provider-metrics {
    flex-direction: column;
    gap: var(--spacing-sm);
  }
}

@media (prefers-reduced-motion: reduce) {
  .stat-card,
  .panel,
  .provider-card,
  .recommendation-card {
    animation: none;
  }

  .toggle-dot {
    animation: none;
  }

  .refresh-icon.spinning {
    animation: none;
  }

  .stat-skeleton,
  .skeleton-line {
    animation: none;
  }

  .provider-card:hover,
  .recommendation-card:hover {
    transform: none;
  }
}
</style>
