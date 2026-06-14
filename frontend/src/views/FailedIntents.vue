<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, apiClient } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'

interface FailedIntentCase {
  id: string
  user_input: string
  parse_method: string
  failure_reason: string
  failure_reason_category: string
  resolved: boolean
  resolution_notes: string
  created_at: string
}

interface FailedIntentStats {
  total: number
  unresolved: number
  resolved: number
  resolution_rate: number
  top_failure_reason: string
  by_reason: Record<string, number>
}

const cases = ref<FailedIntentCase[]>([])
const stats = ref<FailedIntentStats>({
  total: 0,
  unresolved: 0,
  resolved: 0,
  resolution_rate: 0,
  top_failure_reason: '--',
  by_reason: {}
})
const isLoading = ref(true)
const isRefreshing = ref(false)
const isMockData = ref(false)

const filterResolved = ref<'all' | 'unresolved' | 'resolved'>('all')
const filterReasonCategory = ref('all')
const searchQuery = ref('')

const showDetailModal = ref(false)
const selectedCase = ref<FailedIntentCase | null>(null)

const showResolveModal = ref(false)
const resolveTarget = ref<FailedIntentCase | null>(null)
const resolutionNotes = ref('')
const isResolving = ref(false)

const reasonCategories = computed(() => {
  const cats = new Set<string>()
  cases.value.forEach(c => cats.add(c.failure_reason_category))
  return Array.from(cats)
})

const filteredCases = computed(() => {
  let list = cases.value
  if (filterResolved.value === 'unresolved') list = list.filter(c => !c.resolved)
  if (filterResolved.value === 'resolved') list = list.filter(c => c.resolved)
  if (filterReasonCategory.value !== 'all') {
    list = list.filter(c => c.failure_reason_category === filterReasonCategory.value)
  }
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(c =>
      c.id.toLowerCase().includes(q) ||
      c.user_input.toLowerCase().includes(q) ||
      c.failure_reason.toLowerCase().includes(q) ||
      c.parse_method.toLowerCase().includes(q)
    )
  }
  return list
})

const chartData = computed(() => {
  const byReason = stats.value.by_reason
  const entries = Object.entries(byReason).sort((a, b) => b[1] - a[1])
  const maxVal = entries.length > 0 ? entries[0][1] : 1
  const colors = [
    'var(--color-error)', 'var(--color-warning)', 'var(--color-primary)',
    'var(--color-success)', 'var(--color-purple)', 'var(--color-cyan)',
    'var(--color-pink)', 'var(--color-orange)'
  ]
  return entries.map(([reason, count], i) => ({
    reason,
    count,
    percent: Math.round((count / maxVal) * 100),
    color: colors[i % colors.length]
  }))
})

const truncate = (text: string, max: number) => {
  if (!text) return '--'
  return text.length > max ? text.slice(0, max) + '...' : text
}

const formatTime = (dateStr: string): string => {
  if (!dateStr) return '--'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return dateStr
  return d.toLocaleString('zh-CN')
}

const getReasonTagClass = (category: string) => {
  const map: Record<string, string> = {
    parse_error: 'tag-error',
    ambiguous_input: 'tag-warning',
    unsupported_intent: 'tag-info',
    entity_missing: 'tag-purple',
    timeout: 'tag-cyan'
  }
  return map[category] || 'tag-default'
}

const getReasonLabel = (category: string) => {
  const map: Record<string, string> = {
    parse_error: '解析错误',
    ambiguous_input: '输入歧义',
    unsupported_intent: '不支持的意图',
    entity_missing: '实体缺失',
    timeout: '超时'
  }
  return map[category] || category
}

const fetchData = async (showLoading = false) => {
  if (showLoading) isRefreshing.value = true
  try {
    const [listResp, statsResp] = await Promise.all([
      apiClient.get(api.failedIntents.list),
      apiClient.get(api.failedIntents.stats)
    ])
    if (listResp.data) {
      const items = Array.isArray(listResp.data) ? listResp.data : (listResp.data.items || [])
      cases.value = items
    }
    if (statsResp.data) {
      stats.value = { ...stats.value, ...statsResp.data }
    }
    isMockData.value = false
  } catch {
    loadMockData()
    isMockData.value = true
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

const loadMockData = () => {
  const now = Date.now()
  cases.value = [
    {
      id: 'FI-001',
      user_input: '帮我把核心交换机的QoS策略调整一下，让视频会议流量优先级更高',
      parse_method: 'deepseek_v3',
      failure_reason: '无法识别"调整一下"的具体操作类型，缺少明确动作动词',
      failure_reason_category: 'ambiguous_input',
      resolved: false,
      resolution_notes: '',
      created_at: new Date(now - 0.5 * 3600000).toISOString()
    },
    {
      id: 'FI-002',
      user_input: '网络好慢啊',
      parse_method: 'rule_based',
      failure_reason: '输入过于模糊，无法提取有效意图和实体',
      failure_reason_category: 'ambiguous_input',
      resolved: false,
      resolution_notes: '',
      created_at: new Date(now - 1.2 * 3600000).toISOString()
    },
    {
      id: 'FI-003',
      user_input: '把防火墙规则改成允许所有流量通过',
      parse_method: 'deepseek_v3',
      failure_reason: '检测到高危操作意图，安全策略拦截解析',
      failure_reason_category: 'unsupported_intent',
      resolved: true,
      resolution_notes: '已确认为误操作，用户重新提交了合规的ACL规则',
      created_at: new Date(now - 2.8 * 3600000).toISOString()
    },
    {
      id: 'FI-004',
      user_input: '配置BGP对等体192.168.1.1',
      parse_method: 'rule_based',
      failure_reason: '缺少目标设备标识，无法确定配置下发的目标网元',
      failure_reason_category: 'entity_missing',
      resolved: false,
      resolution_notes: '',
      created_at: new Date(now - 4.1 * 3600000).toISOString()
    },
    {
      id: 'FI-005',
      user_input: '优化链路质量',
      parse_method: 'deepseek_v3',
      failure_reason: 'LLM响应超时，解析请求在30秒内未返回结果',
      failure_reason_category: 'timeout',
      resolved: true,
      resolution_notes: 'DeepSeek API临时过载，已切换至备用模型重试成功',
      created_at: new Date(now - 5.5 * 3600000).toISOString()
    },
    {
      id: 'FI-006',
      user_input: '把SW-BJ-01的GE0/0/1接口带宽限制到100M',
      parse_method: 'hybrid',
      failure_reason: '规则引擎与LLM解析结果冲突，无法自动裁决',
      failure_reason_category: 'parse_error',
      resolved: false,
      resolution_notes: '',
      created_at: new Date(now - 7.3 * 3600000).toISOString()
    },
    {
      id: 'FI-007',
      user_input: '帮我做一次全网安全扫描并自动修复所有漏洞',
      parse_method: 'deepseek_v3',
      failure_reason: '意图范围过大且包含自动修复，超出当前系统支持能力',
      failure_reason_category: 'unsupported_intent',
      resolved: true,
      resolution_notes: '已拆分为多个子意图逐步执行，用户确认接受',
      created_at: new Date(now - 9.0 * 3600000).toISOString()
    },
    {
      id: 'FI-008',
      user_input: '路由表里那些奇怪的路由帮我清理掉',
      parse_method: 'rule_based',
      failure_reason: '无法识别"奇怪的路由"的具体筛选条件，实体提取失败',
      failure_reason_category: 'entity_missing',
      resolved: false,
      resolution_notes: '',
      created_at: new Date(now - 12.6 * 3600000).toISOString()
    }
  ]

  stats.value = {
    total: 8,
    unresolved: 5,
    resolved: 3,
    resolution_rate: 37.5,
    top_failure_reason: '输入歧义',
    by_reason: {
      ambiguous_input: 2,
      entity_missing: 2,
      unsupported_intent: 2,
      parse_error: 1,
      timeout: 1
    }
  }
}

const openDetail = async (item: FailedIntentCase) => {
  try {
    const resp = await apiClient.get(api.failedIntents.byId(item.id))
    if (resp.data) {
      selectedCase.value = { ...item, ...resp.data }
    } else {
      selectedCase.value = { ...item }
    }
  } catch {
    selectedCase.value = { ...item }
  }
  showDetailModal.value = true
}

const openResolveModal = (item: FailedIntentCase) => {
  resolveTarget.value = item
  resolutionNotes.value = ''
  showResolveModal.value = true
}

const confirmResolve = async () => {
  if (!resolveTarget.value) return
  isResolving.value = true
  try {
    await apiClient.post(api.failedIntents.resolve(resolveTarget.value.id), {
      resolution_notes: resolutionNotes.value
    })
    const idx = cases.value.findIndex(c => c.id === resolveTarget.value!.id)
    if (idx !== -1) {
      cases.value[idx].resolved = true
      cases.value[idx].resolution_notes = resolutionNotes.value
    }
    stats.value.resolved++
    stats.value.unresolved = Math.max(0, stats.value.unresolved - 1)
    stats.value.resolution_rate = stats.value.total > 0
      ? Math.round((stats.value.resolved / stats.value.total) * 1000) / 10
      : 0
    showToast('已标记为已解决', 'success')
    showResolveModal.value = false
  } catch {
    showToast('解决操作失败', 'error')
  } finally {
    isResolving.value = false
  }
}

const getFinetuningData = async () => {
  try {
    const resp = await apiClient.get(api.failedIntents.finetuningData)
    const data = resp.data || cases.value.filter(c => c.resolved).map(c => ({
      user_input: c.user_input,
      failure_reason: c.failure_reason,
      resolution_notes: c.resolution_notes
    }))
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `finetuning_data_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    showToast('微调数据已导出', 'success')
  } catch {
    showToast('导出微调数据失败', 'error')
  }
}

const exportJSON = () => {
  const payload = {
    exportTime: new Date().toISOString(),
    total: cases.value.length,
    stats: stats.value,
    cases: cases.value
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `failed_intents_${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
  showToast('数据已导出为 JSON', 'success')
}

const manualRefresh = async () => {
  isRefreshing.value = true
  try {
    await fetchData(true)
    showToast('数据已刷新', 'success')
  } catch {
    showToast('刷新失败', 'error')
  }
}

const clearFilters = () => {
  searchQuery.value = ''
  filterResolved.value = 'all'
  filterReasonCategory.value = 'all'
}

const handleKeydown = (e: KeyboardEvent) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
    e.preventDefault()
    manualRefresh()
  }
  if (e.key === 'Escape') {
    if (showResolveModal.value) showResolveModal.value = false
    else if (showDetailModal.value) showDetailModal.value = false
  }
}

let pollingTimer: number | null = null

onMounted(() => {
  fetchData(true)
  document.addEventListener('keydown', handleKeydown)
  pollingTimer = window.setInterval(() => {
    if (!document.hidden) fetchData(false)
  }, 30000)
})

onUnmounted(() => {
  if (pollingTimer !== null) clearInterval(pollingTimer)
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div class="failed-intents">
    <div class="fi-bg">
      <div class="bg-grid"></div>
      <div class="bg-glow glow-1"></div>
      <div class="bg-glow glow-2"></div>
    </div>

    <!-- Header -->
    <div class="fi-header">
      <div class="header-left">
        <h1 class="page-title">失败意图分析</h1>
        <p class="page-subtitle">分析解析失败的意图案例，优化模型微调数据</p>
      </div>
      <div class="header-actions">
        <span v-if="isMockData" class="mock-badge">模拟数据</span>
        <button type="button" class="fi-btn fi-btn-ghost" @click="getFinetuningData" title="导出微调数据">
          🧠 获取微调数据
        </button>
        <button type="button" class="fi-btn fi-btn-ghost" @click="exportJSON" title="导出 JSON">
          📥 导出 JSON
        </button>
        <button
          type="button"
          class="fi-btn fi-btn-primary"
          :class="{ refreshing: isRefreshing }"
          :disabled="isRefreshing"
          @click="manualRefresh"
        >
          <span class="refresh-icon" :class="{ spinning: isRefreshing }">🔄</span>
          {{ isRefreshing ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </div>

    <!-- Stats Bar -->
    <div class="stats-bar">
      <div class="stat-item">
        <span class="stat-icon">📊</span>
        <div class="stat-content">
          <span class="stat-value">{{ stats.total }}</span>
          <span class="stat-label">总失败数</span>
        </div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <span class="stat-icon">❌</span>
        <div class="stat-content">
          <span class="stat-value danger">{{ stats.unresolved }}</span>
          <span class="stat-label">未解决</span>
        </div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <span class="stat-icon">✅</span>
        <div class="stat-content">
          <span class="stat-value success">{{ stats.resolved }}</span>
          <span class="stat-label">已解决</span>
        </div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <span class="stat-icon">📈</span>
        <div class="stat-content">
          <span class="stat-value primary">{{ stats.resolution_rate }}%</span>
          <span class="stat-label">解决率</span>
        </div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <span class="stat-icon">🔥</span>
        <div class="stat-content">
          <span class="stat-value warning">{{ stats.top_failure_reason }}</span>
          <span class="stat-label">高频失败原因</span>
        </div>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <div class="filter-left">
        <div class="search-wrapper">
          <span class="search-icon">🔍</span>
          <input
            v-model="searchQuery"
            type="text"
            class="search-input"
            placeholder="搜索案例ID、用户输入、失败原因..."
            aria-label="搜索失败意图"
          />
          <button v-if="searchQuery" type="button" class="search-clear" @click="searchQuery = ''">✕</button>
        </div>
        <select v-model="filterResolved" class="filter-select" aria-label="按解决状态筛选">
          <option value="all">全部状态</option>
          <option value="unresolved">未解决</option>
          <option value="resolved">已解决</option>
        </select>
        <select v-model="filterReasonCategory" class="filter-select" aria-label="按失败原因分类筛选">
          <option value="all">全部原因</option>
          <option v-for="cat in reasonCategories" :key="cat" :value="cat">{{ getReasonLabel(cat) }}</option>
        </select>
        <button
          v-if="filterResolved !== 'all' || filterReasonCategory !== 'all' || searchQuery"
          type="button"
          class="clear-filter-btn"
          @click="clearFilters"
        >
          清除筛选
        </button>
      </div>
    </div>

    <!-- Failure Stats Chart -->
    <div v-if="chartData.length > 0" class="chart-section">
      <div class="chart-panel">
        <h3 class="chart-title">失败原因分布</h3>
        <div class="chart-bars">
          <div v-for="item in chartData" :key="item.reason" class="chart-row">
            <span class="chart-label">{{ getReasonLabel(item.reason) }}</span>
            <div class="chart-bar-track">
              <div
                class="chart-bar-fill"
                :style="{ width: item.percent + '%', background: item.color }"
              ></div>
            </div>
            <span class="chart-count">{{ item.count }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Cases Table -->
    <div class="table-panel">
      <div v-if="isLoading" class="loading-state">
        <div class="loading-spinner"></div>
        <span>加载中...</span>
      </div>
      <template v-else>
        <table class="cases-table">
          <thead>
            <tr>
              <th class="col-id">案例ID</th>
              <th class="col-input">用户输入</th>
              <th class="col-method">解析方法</th>
              <th class="col-reason">失败原因</th>
              <th class="col-resolved">状态</th>
              <th class="col-time">创建时间</th>
              <th class="col-actions">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="filteredCases.length === 0">
              <td colspan="7" class="empty-cell">
                <div class="empty-inner">
                  <span class="empty-icon">📭</span>
                  <span>{{ searchQuery || filterResolved !== 'all' || filterReasonCategory !== 'all' ? '没有匹配的案例' : '暂无失败意图案例' }}</span>
                </div>
              </td>
            </tr>
            <tr
              v-for="item in filteredCases"
              :key="item.id"
              class="case-row"
              :class="{ 'row-resolved': item.resolved }"
            >
              <td class="cell-id">
                <span class="id-badge">{{ item.id }}</span>
              </td>
              <td class="cell-input" :title="item.user_input">
                {{ truncate(item.user_input, 40) }}
              </td>
              <td class="cell-method">
                <span class="method-tag">{{ item.parse_method }}</span>
              </td>
              <td class="cell-reason">
                <span class="reason-tag" :class="getReasonTagClass(item.failure_reason_category)">
                  {{ getReasonLabel(item.failure_reason_category) }}
                </span>
              </td>
              <td class="cell-resolved">
                <span class="resolved-badge" :class="item.resolved ? 'badge-yes' : 'badge-no'">
                  {{ item.resolved ? '已解决' : '未解决' }}
                </span>
              </td>
              <td class="cell-time">{{ formatTime(item.created_at) }}</td>
              <td class="cell-actions">
                <div class="action-group">
                  <button type="button" class="fi-btn fi-btn-sm fi-btn-ghost" @click="openDetail(item)">详情</button>
                  <button
                    v-if="!item.resolved"
                    type="button"
                    class="fi-btn fi-btn-sm fi-btn-success"
                    @click="openResolveModal(item)"
                  >解决</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>

    <!-- Detail Modal -->
    <Teleport to="body">
      <div v-if="showDetailModal && selectedCase" class="modal-overlay" @click.self="showDetailModal = false" role="dialog" aria-modal="true">
        <div class="modal-content detail-modal">
          <div class="modal-header">
            <h3 class="modal-title">📋 案例详情 - {{ selectedCase.id }}</h3>
            <button type="button" class="modal-close" @click="showDetailModal = false" aria-label="关闭">✕</button>
          </div>
          <div class="detail-body">
            <div class="detail-section">
              <h4 class="detail-label">用户输入</h4>
              <p class="detail-value detail-text-block">{{ selectedCase.user_input }}</p>
            </div>
            <div class="detail-row-pair">
              <div class="detail-section">
                <h4 class="detail-label">解析方法</h4>
                <span class="method-tag">{{ selectedCase.parse_method }}</span>
              </div>
              <div class="detail-section">
                <h4 class="detail-label">失败原因分类</h4>
                <span class="reason-tag" :class="getReasonTagClass(selectedCase.failure_reason_category)">
                  {{ getReasonLabel(selectedCase.failure_reason_category) }}
                </span>
              </div>
            </div>
            <div class="detail-section">
              <h4 class="detail-label">失败原因详情</h4>
              <p class="detail-value">{{ selectedCase.failure_reason }}</p>
            </div>
            <div class="detail-section">
              <h4 class="detail-label">解决状态</h4>
              <span class="resolved-badge" :class="selectedCase.resolved ? 'badge-yes' : 'badge-no'">
                {{ selectedCase.resolved ? '已解决' : '未解决' }}
              </span>
            </div>
            <div v-if="selectedCase.resolution_notes" class="detail-section">
              <h4 class="detail-label">解决备注</h4>
              <p class="detail-value detail-text-block resolved-notes">{{ selectedCase.resolution_notes }}</p>
            </div>
            <div class="detail-section">
              <h4 class="detail-label">创建时间</h4>
              <p class="detail-value">{{ formatTime(selectedCase.created_at) }}</p>
            </div>
          </div>
          <div class="modal-actions">
            <button type="button" class="fi-btn fi-btn-ghost" @click="showDetailModal = false">关闭</button>
            <button
              v-if="!selectedCase.resolved"
              type="button"
              class="fi-btn fi-btn-success"
              @click="showDetailModal = false; openResolveModal(selectedCase)"
            >标记为已解决</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Resolve Modal -->
    <Teleport to="body">
      <div v-if="showResolveModal && resolveTarget" class="modal-overlay" @click.self="showResolveModal = false" role="dialog" aria-modal="true">
        <div class="modal-content resolve-modal">
          <div class="modal-header">
            <h3 class="modal-title">✅ 解决案例 - {{ resolveTarget.id }}</h3>
            <button type="button" class="modal-close" @click="showResolveModal = false" aria-label="关闭">✕</button>
          </div>
          <div class="resolve-body">
            <p class="resolve-desc">
              <strong>用户输入：</strong>{{ truncate(resolveTarget.user_input, 80) }}
            </p>
            <p class="resolve-desc">
              <strong>失败原因：</strong>{{ resolveTarget.failure_reason }}
            </p>
            <div class="form-group">
              <label class="form-label" for="resolution-notes">解决备注</label>
              <textarea
                id="resolution-notes"
                v-model="resolutionNotes"
                class="resolve-textarea"
                placeholder="请输入解决方案说明、微调建议等..."
                rows="4"
              ></textarea>
            </div>
          </div>
          <div class="modal-actions">
            <button type="button" class="fi-btn fi-btn-ghost" @click="showResolveModal = false">取消</button>
            <button
              type="button"
              class="fi-btn fi-btn-success"
              :disabled="isResolving"
              @click="confirmResolve"
            >
              {{ isResolving ? '提交中...' : '确认解决' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.failed-intents {
  position: relative;
  animation: page-enter 0.5s ease-out;
  min-height: 100vh;
  padding: var(--content-padding);
  will-change: opacity;
}

.fi-bg {
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
  inset: 0;
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
  background: var(--color-error-bg);
  bottom: 10%;
  left: 5%;
  animation: glow-float 15s ease-in-out infinite reverse;
  will-change: transform, opacity;
}

/* glow-float uses global definition from tokens.css */
/* page-enter uses global definition from tokens.css */

.failed-intents > *:not(.fi-bg) {
  position: relative;
  z-index: var(--z-content);
}

/* Header */
.fi-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-bg-hover);
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
  background: linear-gradient(135deg, var(--color-text-secondary) 0%, var(--color-error) 50%, var(--color-text-secondary) 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: title-shimmer 4s ease-in-out infinite;
  will-change: background-position;
}

/* title-shimmer uses global definition from tokens.css */

.page-subtitle {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.mock-badge {
  font-size: var(--font-size-xs);
  padding: var(--spacing-xs) 10px;
  border-radius: var(--radius-lg);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  border: 1px solid var(--color-warning-border);
}

/* Buttons */
.fi-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  padding: 0.375rem 14px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
  border: 1px solid transparent;
  min-height: 36px;
  white-space: nowrap;
  will-change: transform;
}

.fi-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.97);
}

.fi-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.fi-btn-primary {
  background: var(--gradient-primary);
  color: white;
  border: none;
  box-shadow: var(--shadow-glow-primary);
}

.fi-btn-primary:hover:not(:disabled) {
  box-shadow: var(--shadow-glow-primary-lg);
  transform: translateY(-2px);
}

.fi-btn-ghost {
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
}

.fi-btn-ghost:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-border-focus);
  box-shadow: var(--shadow-glow-primary);
  transform: translateY(-2px);
}

.fi-btn-success {
  background: var(--color-success-bg);
  color: var(--color-success-light);
  border: 1px solid var(--color-success-border);
}

.fi-btn-success:hover:not(:disabled) {
  background: var(--color-success-hover);
  border-color: var(--color-success-border);
  box-shadow: var(--shadow-glow-success);
  transform: translateY(-2px);
}

.fi-btn-sm {
  padding: var(--spacing-xs) 10px;
  font-size: var(--font-size-xs);
  min-height: 28px;
}

.refresh-icon {
  display: inline-block;
  transition: transform 0.3s ease;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

/* spin uses global definition from tokens.css */

/* Stats Bar */
.stats-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: 0.75rem var(--spacing-lg);
  background: linear-gradient(135deg, var(--color-error-bg) 0%, var(--color-bg-glass) 50%, var(--color-primary-bg) 100%);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-bg-hover);
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

.stat-item:hover .stat-icon {
  transform: scale(1.2);
}

.stat-content {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: var(--font-size-base);
  font-weight: 700;
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
  line-height: 1.3;
}

.stat-value.danger { color: var(--color-error-light); }
.stat-value.success { color: var(--color-success); }
.stat-value.primary { color: var(--color-primary-light); }
.stat-value.warning { color: var(--color-warning); font-size: var(--font-size-sm); }

.stat-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.stat-divider {
  width: 1px;
  height: 20px;
  background: linear-gradient(180deg, transparent, var(--color-border-secondary), transparent);
}

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
  width: 260px;
  transition: all 0.25s var(--ease-out);
  outline: none;
}

.search-input::placeholder { color: var(--color-text-disabled); }

.search-input:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
  background: var(--color-bg-glass-strong);
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

.search-clear:hover { color: var(--color-text-primary); }

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
  border-color: var(--color-error-border);
}

/* Chart Section */
.chart-section {
  margin-bottom: 1.25rem;
}

.chart-panel {
  background: var(--gradient-glass);
  border-radius: var(--radius-xl);
  padding: 1.25rem;
  border: var(--card-border);
  backdrop-filter: blur(12px);
}

.chart-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 1rem 0;
  padding-left: 0.625rem;
  border-left: 3px solid var(--color-error);
}

.chart-bars {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.chart-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.chart-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  min-width: 80px;
  text-align: right;
}

.chart-bar-track {
  flex: 1;
  height: 20px;
  background: var(--color-bg-hover);
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.chart-bar-fill {
  height: 100%;
  border-radius: var(--radius-xs);
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
  min-width: 4px;
  will-change: width;
}

.chart-count {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  min-width: 24px;
  font-variant-numeric: tabular-nums;
}

/* Table Panel */
.table-panel {
  background: var(--gradient-glass);
  border-radius: var(--radius-xl);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  overflow: hidden;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  gap: 0.75rem;
  color: var(--color-text-tertiary);
}

.loading-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--color-border-primary);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  will-change: transform;
}

.cases-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.cases-table thead {
  background: var(--color-bg-hover);
}

.cases-table th {
  padding: 0.75rem 1rem;
  text-align: left;
  font-weight: 600;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--color-bg-hover);
  white-space: nowrap;
}

.cases-table td {
  padding: 0.75rem 1rem;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-bg-hover);
  vertical-align: middle;
}

.case-row {
  transition: background 0.2s ease;
  will-change: background;
}

.case-row:hover {
  background: var(--color-bg-hover);
}

.case-row.row-resolved {
  opacity: 0.75;
}

.col-id { width: 90px; }
.col-input { min-width: 200px; }
.col-method { width: 120px; }
.col-reason { width: 130px; }
.col-resolved { width: 80px; }
.col-time { width: 160px; }
.col-actions { width: 140px; }

.cell-id .id-badge {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-text-tertiary);
  background: var(--color-bg-hover);
  padding: var(--spacing-xs) 10px;
  border-radius: var(--radius-sm);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  white-space: nowrap;
}

.cell-input {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.method-tag {
  font-size: 0.6875rem;
  padding: 3px 10px;
  border-radius: var(--radius-md);
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  font-weight: 500;
  white-space: nowrap;
}

.reason-tag {
  font-size: 0.6875rem;
  padding: 3px 10px;
  border-radius: var(--radius-md);
  font-weight: 500;
  white-space: nowrap;
}

.tag-error { background: var(--color-error-hover); color: var(--color-error-light); }
.tag-warning { background: var(--color-warning-hover); color: var(--color-warning); }
.tag-info { background: var(--color-info-hover); color: var(--color-primary-light); }
.tag-purple { background: var(--color-purple-bg); color: var(--color-purple); }
.tag-cyan { background: var(--color-cyan-bg); color: var(--color-cyan); }
.tag-default { background: var(--color-bg-active); color: var(--color-text-tertiary); }

.resolved-badge {
  font-size: 0.6875rem;
  padding: 3px 10px;
  border-radius: var(--radius-md);
  font-weight: 600;
  white-space: nowrap;
}

.badge-yes { background: var(--color-success-hover); color: var(--color-success); }
.badge-no { background: var(--color-error-hover); color: var(--color-error-light); }

.cell-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.cell-actions .action-group {
  display: flex;
  gap: 0.375rem;
}

.empty-cell {
  text-align: center;
  padding: 3rem 1rem !important;
}

.empty-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  color: var(--color-text-tertiary);
}

.empty-inner .empty-icon {
  font-size: var(--font-size-4xl);
  opacity: 0.6;
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
  animation: fade-in 0.2s var(--ease-out);
  backdrop-filter: blur(var(--modal-backdrop-blur));
}

/* fade-in uses global definition from tokens.css */

.modal-content {
  background: var(--color-bg-elevated);
  border-radius: var(--modal-border-radius);
  padding: var(--modal-padding);
  width: 90%;
  max-width: 560px;
  border: 1px solid var(--color-border-primary);
  box-shadow: var(--shadow-modal);
  animation: modal-content-in 0.25s var(--ease-out);
}

/* modal-content-in uses global definition from tokens.css */

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.25rem;
}

.modal-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
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

.modal-close:hover { color: var(--color-text-primary); }

.modal-actions {
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: 1px solid var(--color-bg-hover);
}

/* Detail Modal */
.detail-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.detail-section {
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-bg-hover);
}

.detail-row-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.detail-label {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-primary-light);
  margin: 0 0 0.375rem 0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-value {
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  margin: 0;
  line-height: 1.6;
}

.detail-text-block {
  background: var(--color-bg-glass-strong);
  padding: 0.625rem 0.75rem;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  white-space: pre-wrap;
  word-break: break-all;
}

.resolved-notes {
  border-left: 3px solid var(--color-success);
}

/* Resolve Modal */
.resolve-body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.resolve-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin: 0;
  line-height: 1.6;
}

.resolve-desc strong {
  color: var(--color-text-secondary);
}

.resolve-textarea {
  width: 100%;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  padding: 0.75rem 1rem;
  color: var(--color-text-secondary);
  font-size: var(--font-size-base);
  resize: vertical;
  outline: none;
  transition: all 0.25s ease;
  font-family: inherit;
  box-sizing: border-box;
}

.resolve-textarea::placeholder { color: var(--color-text-disabled); }

.resolve-textarea:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.form-label {
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--color-form-label);
}

/* Responsive */
@media (max-width: 768px) {
  .failed-intents {
    padding: var(--spacing-md);
  }

  .fi-header {
    flex-direction: column;
    gap: 0.75rem;
    align-items: flex-start;
  }

  .header-actions {
    flex-wrap: wrap;
    width: 100%;
  }

  .page-title { font-size: var(--font-size-xl); }

  .stats-bar {
    gap: 10px;
    padding: 10px var(--spacing-md);
  }

  .stat-divider { display: none; }

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
    min-height: var(--button-min-height-touch);
  }

  .filter-select {
    width: 100%;
    min-height: var(--button-min-height-touch);
  }

  .cases-table {
    font-size: var(--font-size-xs);
  }

  .cases-table th,
  .cases-table td {
    padding: 0.5rem 0.5rem;
  }

  .col-method,
  .col-time {
    display: none;
  }

  .detail-row-pair {
    grid-template-columns: 1fr;
  }

  .modal-content {
    width: 96%;
    padding: var(--spacing-md);
  }
}

@media (max-width: 480px) {
  .failed-intents {
    padding: var(--spacing-sm);
  }

  .page-title { font-size: var(--font-size-lg); }

  .stats-bar {
    padding: var(--spacing-sm) 0.75rem;
    gap: 0.375rem;
  }

  .stat-item { padding: 2px; }
  .stat-value { font-size: var(--font-size-sm); }
  .stat-label { font-size: var(--font-size-xs); }

  .col-reason { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .failed-intents,
  .stats-bar,
  .bg-glow,
  .chart-bar-fill,
  .page-title,
  .refresh-icon.spinning,
  .loading-spinner,
  .modal-overlay,
  .modal-content {
    animation: none !important;
    transition: none !important;
  }
}
</style>
