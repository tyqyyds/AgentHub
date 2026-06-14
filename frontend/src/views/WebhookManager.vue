<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useLogger } from '@/utils/logger'
import { api, apiClient } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'

const { info, warn } = useLogger()

interface Subscription {
  id: number
  subscription_id: string
  name: string
  url: string
  secret?: string
  event_types: string[]
  is_active: boolean
  last_status: string | null
  failure_count: number
  headers?: Record<string, string>
  retry_policy?: Record<string, any>
  created_by: string
  last_triggered_at: string | null
  created_at: string
  updated_at: string | null
}

interface DeliveryLog {
  subscription_id: string
  event_type: string
  status: string
  status_code: number | null
  attempt: number
  timestamp: string
  error: string | null
  url: string
}

const EVENT_CATEGORY_MAP: Record<string, { label: string; color: string }> = {
  'intent.created':        { label: '意图创建',   color: '#165DFF' },
  'intent.completed':      { label: '意图完成',   color: '#165DFF' },
  'intent.failed':         { label: '意图失败',   color: '#F77234' },
  'sla.achieving':         { label: 'SLA达标',    color: '#52C41A' },
  'sla.deviating':         { label: 'SLA偏离',    color: '#FAAD14' },
  'sla.violated':          { label: 'SLA违规',    color: '#FF4D4F' },
  'sla.violation_predicted': { label: 'SLA预测违规', color: '#FF7A45' },
  'healing.started':       { label: '自愈启动',   color: '#0FC6C2' },
  'healing.completed':     { label: '自愈完成',   color: '#52C41A' },
  'healing.failed':        { label: '自愈失败',   color: '#FF4D4F' },
  'device.alert':          { label: '设备告警',   color: '#F77234' },
  'device.status_changed': { label: '设备状态变更', color: '#722ED1' },
  'agent.health_changed':  { label: '智能体健康变更', color: '#0FC6C2' },
  'workflow.step_completed': { label: '工单步骤完成', color: '#165DFF' },
  'workflow.completed':    { label: '工单完成',   color: '#52C41A' },
}

const subscriptions = ref<Subscription[]>([])
const availableEvents = ref<string[]>([])
const deliveryLogs = ref<DeliveryLog[]>([])
const isLoading = ref(true)
const isRefreshing = ref(false)
const showFormDialog = ref(false)
const showLogsDialog = ref(false)
const isEditing = ref(false)
const editingId = ref<string>('')
const isSubmitting = ref(false)
const logsLoading = ref(false)
const activeFilter = ref<'all' | 'active' | 'inactive' | 'failed'>('all')

const form = ref({
  name: '',
  url: '',
  secret: '',
  event_types: [] as string[],
  headers: {} as Record<string, string>,
  retry_policy: { max_retries: 3, retry_interval: 5 }
})

const formRules = {
  name: [{ required: true, message: '请输入订阅名称', trigger: 'blur' }],
  url: [
    { required: true, message: '请输入Webhook URL', trigger: 'blur' },
    { pattern: /^https?:\/\/.+/, message: 'URL格式不正确，需以http://或https://开头', trigger: 'blur' }
  ],
  event_types: [{ required: true, type: 'array' as const, min: 1, message: '请至少选择一个事件类型', trigger: 'change' }]
}
const formRef = ref<any>(null)

const headerKey = ref('')
const headerValue = ref('')

let pollTimer: number | null = null

// ── 统计数据 ──
const stats = computed(() => {
  const all = subscriptions.value
  const active = all.filter(s => s.is_active)
  const failed = all.filter(s => s.last_status === 'failed')
  const inactive = all.filter(s => !s.is_active)
  const eventSet = new Set(all.flatMap(s => s.event_types))
  return {
    total: all.length,
    active: active.length,
    failed: failed.length,
    inactive: inactive.length,
    eventTypes: eventSet.size,
  }
})

const filteredSubscriptions = computed(() => {
  const list = subscriptions.value
  switch (activeFilter.value) {
    case 'active': return list.filter(s => s.is_active)
    case 'inactive': return list.filter(s => !s.is_active)
    case 'failed': return list.filter(s => s.last_status === 'failed')
    default: return list
  }
})

const fetchSubscriptions = async (showLoading = false) => {
  if (showLoading) isRefreshing.value = true
  try {
    const data = await apiClient.get(api.webhooks.subscriptions)
    if (data.data) {
      const items = data.data.items ?? data.data
      subscriptions.value = Array.isArray(items) ? items : []
    }
  } catch (err: any) {
    warn('获取订阅列表失败', { error: err.message })
    loadMockData()
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

const fetchAvailableEvents = async () => {
  try {
    const data = await apiClient.get(api.webhooks.events)
    if (data.data) {
      availableEvents.value = Array.isArray(data.data) ? data.data : []
    }
  } catch {
    availableEvents.value = Object.keys(EVENT_CATEGORY_MAP)
  }
}

const loadMockData = () => {
  const now = Date.now()
  const h = 3600000
  subscriptions.value = [
    { id: 1, subscription_id: 'wh_monitor', name: '监控告警通知', url: 'https://monitor.example.com/webhook/alerts', event_types: ['device.alert', 'device.status_changed', 'agent.health_changed'], is_active: true, last_status: 'success', failure_count: 0, headers: { 'X-Source': 'AgentHub' }, retry_policy: { max_retries: 3, backoff_seconds: [5, 30, 120] }, created_by: 'admin', last_triggered_at: new Date(now - h).toISOString(), created_at: new Date(now - 72 * h).toISOString(), updated_at: null },
    { id: 2, subscription_id: 'wh_sla', name: 'SLA违规告警', url: 'https://sla.example.com/webhook/violations', event_types: ['sla.violated', 'sla.violation_predicted', 'sla.deviating'], is_active: true, last_status: 'success', failure_count: 1, headers: { 'X-Source': 'AgentHub' }, retry_policy: { max_retries: 5, backoff_seconds: [10, 60, 300, 600, 1800] }, created_by: 'admin', last_triggered_at: new Date(now - 6 * h).toISOString(), created_at: new Date(now - 120 * h).toISOString(), updated_at: null },
    { id: 3, subscription_id: 'wh_ci_cd', name: 'CI/CD集成', url: 'https://cicd.example.com/webhook/deploy', event_types: ['intent.completed', 'intent.failed'], is_active: true, last_status: 'success', failure_count: 0, headers: { 'X-Source': 'AgentHub', 'X-Pipeline': 'network-ops' }, retry_policy: { max_retries: 2, backoff_seconds: [5, 30] }, created_by: 'operator1', last_triggered_at: new Date(now - 12 * h).toISOString(), created_at: new Date(now - 48 * h).toISOString(), updated_at: null },
    { id: 4, subscription_id: 'wh_healing', name: '自愈事件通知', url: 'https://ops.example.com/webhook/healing', event_types: ['healing.started', 'healing.completed', 'healing.failed'], is_active: false, last_status: 'failed', failure_count: 5, headers: { 'X-Source': 'AgentHub' }, retry_policy: { max_retries: 3, backoff_seconds: [5, 30, 120] }, created_by: 'admin', last_triggered_at: new Date(now - 48 * h).toISOString(), created_at: new Date(now - 96 * h).toISOString(), updated_at: null },
    { id: 5, subscription_id: 'wh_intent_track', name: '意图全生命周期追踪', url: 'https://intent.example.com/webhook/lifecycle', event_types: ['intent.created', 'intent.completed', 'intent.failed'], is_active: true, last_status: 'success', failure_count: 0, headers: { 'X-Source': 'AgentHub', 'X-Service': 'intent-tracker' }, retry_policy: { max_retries: 3, backoff_seconds: [5, 30, 120] }, created_by: 'admin', last_triggered_at: new Date(now - 2 * h).toISOString(), created_at: new Date(now - 36 * h).toISOString(), updated_at: null },
    { id: 6, subscription_id: 'wh_sla_predict', name: 'SLA预测预警', url: 'https://sla-predict.example.com/webhook/forecast', event_types: ['sla.violation_predicted', 'sla.deviating', 'sla.achieving'], is_active: true, last_status: 'success', failure_count: 0, headers: { 'X-Source': 'AgentHub', 'X-Alert-Level': 'early-warning' }, retry_policy: { max_retries: 3, backoff_seconds: [10, 60, 300] }, created_by: 'operator1', last_triggered_at: new Date(now - 8 * h).toISOString(), created_at: new Date(now - 60 * h).toISOString(), updated_at: null },
    { id: 7, subscription_id: 'wh_workflow', name: '工单流程联动', url: 'https://workflow.example.com/webhook/steps', event_types: ['workflow.step_completed', 'workflow.completed'], is_active: true, last_status: 'success', failure_count: 0, headers: { 'X-Source': 'AgentHub', 'X-System': 'work-order' }, retry_policy: { max_retries: 2, backoff_seconds: [5, 30] }, created_by: 'admin', last_triggered_at: new Date(now - 4 * h).toISOString(), created_at: new Date(now - 24 * h).toISOString(), updated_at: null },
    { id: 8, subscription_id: 'wh_device_alert', name: '设备异常实时告警', url: 'https://alert.example.com/webhook/device', event_types: ['device.alert', 'device.status_changed'], is_active: true, last_status: 'failed', failure_count: 3, headers: { 'X-Source': 'AgentHub', 'X-Priority': 'high' }, retry_policy: { max_retries: 5, backoff_seconds: [5, 15, 60, 180, 600] }, created_by: 'operator1', last_triggered_at: new Date(now - 3 * h).toISOString(), created_at: new Date(now - 168 * h).toISOString(), updated_at: null },
    { id: 9, subscription_id: 'wh_healing_audit', name: '自愈审计归档', url: 'https://audit.example.com/webhook/healing-log', event_types: ['healing.completed', 'healing.failed'], is_active: false, last_status: 'success', failure_count: 0, headers: { 'X-Source': 'AgentHub', 'X-Archive': 'true' }, retry_policy: { max_retries: 1, backoff_seconds: [30] }, created_by: 'admin', last_triggered_at: new Date(now - 72 * h).toISOString(), created_at: new Date(now - 240 * h).toISOString(), updated_at: null },
    { id: 10, subscription_id: 'wh_agent_health', name: '智能体健康监控', url: 'https://agent-monitor.example.com/webhook/health', event_types: ['agent.health_changed', 'device.status_changed'], is_active: true, last_status: 'success', failure_count: 1, headers: { 'X-Source': 'AgentHub' }, retry_policy: { max_retries: 3, backoff_seconds: [5, 30, 120] }, created_by: 'admin', last_triggered_at: new Date(now - h).toISOString(), created_at: new Date(now - 48 * h).toISOString(), updated_at: null },
  ]
}

const openCreateDialog = () => {
  isEditing.value = false
  editingId.value = ''
  form.value = { name: '', url: '', secret: '', event_types: [], headers: {}, retry_policy: { max_retries: 3, retry_interval: 5 } }
  showFormDialog.value = true
}

const openEditDialog = (sub: Subscription) => {
  isEditing.value = true
  editingId.value = sub.subscription_id
  form.value = {
    name: sub.name,
    url: sub.url,
    secret: sub.secret || '',
    event_types: [...sub.event_types],
    headers: sub.headers ? { ...sub.headers } : {},
    retry_policy: sub.retry_policy ? { ...sub.retry_policy } : { max_retries: 3, retry_interval: 5 }
  }
  showFormDialog.value = true
}

const addHeader = () => {
  if (headerKey.value && headerValue.value) {
    form.value.headers[headerKey.value] = headerValue.value
    headerKey.value = ''
    headerValue.value = ''
  }
}

const removeHeader = (key: string) => {
  delete form.value.headers[key]
}

const submitForm = async () => {
  if (formRef.value) {
    try {
      await formRef.value.validate()
    } catch {
      return
    }
  }
  isSubmitting.value = true
  try {
    if (isEditing.value) {
      await apiClient.put(api.webhooks.subscriptionById(editingId.value), form.value)
      showToast('订阅已更新', 'success')
    } else {
      await apiClient.post(api.webhooks.subscriptions, form.value)
      showToast('订阅已创建', 'success')
    }
    showFormDialog.value = false
    fetchSubscriptions()
  } catch (err: any) {
    warn(isEditing.value ? '更新订阅失败' : '创建订阅失败', { error: err.message })
    showToast(isEditing.value ? '更新失败' : '创建失败', 'error')
  } finally {
    isSubmitting.value = false
  }
}

const deleteSubscription = async (sub: Subscription) => {
  try {
    await apiClient.delete(api.webhooks.subscriptionById(sub.subscription_id))
    showToast(`订阅 ${sub.name} 已删除`, 'success')
    fetchSubscriptions()
  } catch (err: any) {
    warn('删除订阅失败', { error: err.message })
    showToast('删除失败', 'error')
  }
}

const toggleSubscription = async (sub: Subscription) => {
  try {
    await apiClient.post(api.webhooks.toggle(sub.subscription_id))
    sub.is_active = !sub.is_active
    showToast(`订阅 ${sub.name} 已${sub.is_active ? '启用' : '禁用'}`, 'success')
  } catch (err: any) {
    warn('切换订阅状态失败', { error: err.message })
    showToast('操作失败', 'error')
  }
}

const testWebhook = async () => {
  try {
    await apiClient.post(api.webhooks.test, { url: form.value.url, event_type: 'test', secret: form.value.secret })
    showToast('测试事件已发送', 'success')
  } catch (err: any) {
    warn('测试Webhook失败', { error: err.message })
    showToast('测试失败', 'error')
  }
}

const fetchDeliveryLogs = async (sub: Subscription) => {
  showLogsDialog.value = true
  logsLoading.value = true
  deliveryLogs.value = []
  try {
    const data = await apiClient.get(api.webhooks.logs(sub.subscription_id))
    if (data.data) {
      const items = data.data.items ?? data.data
      deliveryLogs.value = Array.isArray(items) ? items : []
    }
  } catch (err: any) {
    warn('获取投递日志失败', { error: err.message })
    const now = Date.now()
    deliveryLogs.value = [
      { subscription_id: sub.subscription_id, event_type: sub.event_types[0] || 'intent.created', status: 'success', status_code: 200, attempt: 1, timestamp: new Date(now - 600000).toISOString(), error: null, url: sub.url },
      { subscription_id: sub.subscription_id, event_type: sub.event_types[1] || 'healing.started', status: 'failed', status_code: 502, attempt: 3, timestamp: new Date(now - 1200000).toISOString(), error: 'Bad Gateway', url: sub.url },
      { subscription_id: sub.subscription_id, event_type: sub.event_types[0] || 'device.alert', status: 'success', status_code: 200, attempt: 1, timestamp: new Date(now - 1800000).toISOString(), error: null, url: sub.url },
    ]
  } finally {
    logsLoading.value = false
  }
}

const getEventLabel = (evt: string) => EVENT_CATEGORY_MAP[evt]?.label ?? evt
const getEventColor = (evt: string) => EVENT_CATEGORY_MAP[evt]?.color ?? '#86909C'

const formatTime = (dateStr: string | null): string => {
  if (!dateStr) return '--'
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  return date.toLocaleString('zh-CN')
}

const timeAgo = (dateStr: string | null): string => {
  if (!dateStr) return '--'
  const diff = Date.now() - new Date(dateStr).getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return `${Math.floor(diff / 86400000)}天前`
}

onMounted(() => {
  info('WebhookManager mounted')
  fetchAvailableEvents()
  fetchSubscriptions(true)
  pollTimer = window.setInterval(() => {
    if (!document.hidden) fetchSubscriptions()
  }, 30000)
})

onUnmounted(() => {
  if (pollTimer !== null) clearInterval(pollTimer)
})
</script>

<template>
  <div class="webhook-manager">
    <div class="wm-bg">
      <div class="bg-grid"></div>
      <div class="bg-glow glow-1"></div>
      <div class="bg-glow glow-2"></div>
    </div>

    <div class="wm-header">
      <div class="header-left">
        <h1 class="page-title">Webhook管理</h1>
        <p class="page-subtitle">事件订阅与Webhook投递管理</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" class="action-btn" @click="openCreateDialog">+ 新建订阅</el-button>
        <el-button class="action-btn refresh-btn" :loading="isRefreshing" @click="fetchSubscriptions(true)">
          <span v-if="!isRefreshing" class="refresh-icon">↻</span>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div
        class="stat-card"
        :class="{ active: activeFilter === 'all' }"
        @click="activeFilter = 'all'"
      >
        <div class="stat-icon stat-icon-primary">🔗</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">订阅总数</div>
        </div>
      </div>
      <div
        class="stat-card"
        :class="{ active: activeFilter === 'active' }"
        @click="activeFilter = activeFilter === 'active' ? 'all' : 'active'"
      >
        <div class="stat-icon stat-icon-success">✅</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.active }}</div>
          <div class="stat-label">已启用</div>
        </div>
      </div>
      <div
        class="stat-card"
        :class="{ active: activeFilter === 'failed' }"
        @click="activeFilter = activeFilter === 'failed' ? 'all' : 'failed'"
      >
        <div class="stat-icon stat-icon-error">⚠️</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.failed }}</div>
          <div class="stat-label">投递失败</div>
        </div>
      </div>
      <div
        class="stat-card"
        :class="{ active: activeFilter === 'inactive' }"
        @click="activeFilter = activeFilter === 'inactive' ? 'all' : 'inactive'"
      >
        <div class="stat-icon stat-icon-muted">⏸</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.inactive }}</div>
          <div class="stat-label">已禁用</div>
        </div>
      </div>
      <div class="stat-card no-click">
        <div class="stat-icon stat-icon-cyan">📡</div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.eventTypes }}</div>
          <div class="stat-label">事件类型</div>
        </div>
      </div>
    </div>

    <div class="content-section">
      <div class="panel">
        <div class="panel-header">
          <h2 class="panel-title">订阅列表</h2>
          <span class="panel-count">共 {{ filteredSubscriptions.length }} 条</span>
        </div>
        <el-table :data="filteredSubscriptions" style="width: 100%" class="dark-table" v-loading="isLoading" empty-text="暂无订阅数据">
          <el-table-column label="名称" min-width="150">
            <template #default="{ row }">
              <div class="sub-name-cell">
                <span class="sub-name">{{ row.name }}</span>
                <span class="sub-id">{{ row.subscription_id }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="url" label="URL" min-width="220">
            <template #default="{ row }">
              <span class="url-text">{{ row.url }}</span>
            </template>
          </el-table-column>
          <el-table-column label="事件类型" min-width="260">
            <template #default="{ row }">
              <div class="event-tags">
                <span
                  v-for="evt in row.event_types"
                  :key="evt"
                  class="event-tag"
                  :style="{ background: getEventColor(evt) + '18', color: getEventColor(evt), borderColor: getEventColor(evt) + '40' }"
                >
                  {{ getEventLabel(evt) }}
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-switch :model-value="row.is_active" @change="toggleSubscription(row)" size="small" class="toggle-switch" />
            </template>
          </el-table-column>
          <el-table-column label="最近投递" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="row.last_status === 'success' ? 'success' : row.last_status === 'failed' ? 'danger' : 'info'" size="small" effect="dark">
                {{ row.last_status === 'success' ? '成功' : row.last_status === 'failed' ? '失败' : '--' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="失败" width="70" align="center">
            <template #default="{ row }">
              <span :class="{ 'fail-count': row.failure_count > 0 }">{{ row.failure_count }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最近触发" width="120">
            <template #default="{ row }">
              <span class="time-ago">{{ timeAgo(row.last_triggered_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="创建者" width="90" align="center">
            <template #default="{ row }">
              <span class="creator-text">{{ row.created_by }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <div class="action-group">
                <el-button size="small" link type="primary" class="action-icon-btn" @click="openEditDialog(row)">编辑</el-button>
                <el-button size="small" link type="info" class="action-icon-btn" @click="fetchDeliveryLogs(row)">日志</el-button>
                <el-popconfirm title="确定删除此订阅？" @confirm="deleteSubscription(row)">
                  <template #reference>
                    <el-button size="small" link type="danger" class="action-icon-btn">删除</el-button>
                  </template>
                </el-popconfirm>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-dialog v-model="showFormDialog" :title="isEditing ? '编辑订阅' : '新建订阅'" width="560px" class="dark-dialog" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="formRules" label-position="top" class="dark-form">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="输入订阅名称" />
        </el-form-item>
        <el-form-item label="URL" prop="url">
          <el-input v-model="form.url" placeholder="https://example.com/webhook" />
        </el-form-item>
        <el-form-item label="Secret">
          <el-input v-model="form.secret" placeholder="Webhook签名密钥（可选）" show-password />
        </el-form-item>
        <el-form-item label="事件类型" prop="event_types">
          <el-select v-model="form.event_types" multiple placeholder="选择事件类型" style="width: 100%">
            <el-option v-for="evt in availableEvents" :key="evt" :label="getEventLabel(evt)" :value="evt" />
          </el-select>
        </el-form-item>
        <el-form-item label="自定义Headers">
          <div class="header-editor">
            <div class="header-input-row">
              <el-input v-model="headerKey" placeholder="Key" style="width: 40%" />
              <el-input v-model="headerValue" placeholder="Value" style="width: 40%" />
              <el-button @click="addHeader" size="small">添加</el-button>
            </div>
            <div v-for="(_, key) in form.headers" :key="key" class="header-item">
              <span class="header-key">{{ key }}</span>
              <span class="header-val">{{ form.headers[key] }}</span>
              <el-button size="small" link type="danger" @click="removeHeader(key as string)">删除</el-button>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="重试策略">
          <div class="retry-row">
            <div class="retry-field">
              <span class="retry-label">最大重试</span>
              <el-input-number v-model="form.retry_policy.max_retries" :min="0" :max="10" size="small" />
            </div>
            <div class="retry-field">
              <span class="retry-label">重试间隔(秒)</span>
              <el-input-number v-model="form.retry_policy.retry_interval" :min="1" :max="300" size="small" />
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="testWebhook">测试</el-button>
        <el-button @click="showFormDialog = false">取消</el-button>
        <el-button type="primary" :loading="isSubmitting" @click="submitForm">{{ isEditing ? '更新' : '创建' }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showLogsDialog" title="投递日志" width="750px" class="dark-dialog">
      <el-table :data="deliveryLogs" style="width: 100%" class="dark-table" v-loading="logsLoading" empty-text="暂无投递日志">
        <el-table-column label="事件类型" width="160">
          <template #default="{ row }">
            <span class="event-tag" :style="{ background: getEventColor(row.event_type) + '18', color: getEventColor(row.event_type) }">
              {{ getEventLabel(row.event_type) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small" effect="dark">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status_code" label="状态码" width="90" align="center" />
        <el-table-column prop="attempt" label="尝试" width="70" align="center" />
        <el-table-column label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.timestamp) }}
          </template>
        </el-table-column>
        <el-table-column label="错误" min-width="120">
          <template #default="{ row }">
            <span v-if="row.error" class="error-text">{{ row.error }}</span>
            <span v-else class="muted">--</span>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped>
.webhook-manager {
  position: relative;
  will-change: transform;
  animation: page-enter 0.5s var(--ease-out);
  min-height: 100vh;
  padding: var(--content-padding);
}

.wm-bg {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(var(--color-primary-bg) 1px, transparent 1px),
    linear-gradient(90deg, var(--color-primary-bg) 1px, transparent 1px);
  background-size: 60px 60px;
  mask-image: radial-gradient(ellipse 80% 60% at 50% 30%, black 20%, transparent 70%);
}

.bg-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
}

.glow-1 { width: 400px; height: 400px; background: var(--color-primary-glow); top: -100px; right: 10%; animation: glow-float 12s ease-in-out infinite; }
.glow-2 { width: 300px; height: 300px; background: var(--color-orange-glow); bottom: 10%; left: 5%; animation: glow-float 15s ease-in-out infinite reverse; }



.webhook-manager > *:not(.wm-bg) {
  position: relative;
  z-index: 1;
}

.wm-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-border-primary);
}

.header-left { display: flex; flex-direction: column; gap: var(--spacing-xs); }

.page-subtitle { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin: 0; }

.header-actions { display: flex; align-items: center; gap: var(--spacing-sm); }

/* ── 统计卡片 ── */
.stats-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-lg);
}

.stat-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--gradient-glass);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-primary);
  cursor: pointer;
  transition: all 0.25s var(--ease-out);
  backdrop-filter: blur(12px);
}

.stat-card:hover {
  transform: translateY(-2px);
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-glow-primary);
}

.stat-card:active { transform: translateY(0); }

.stat-card.active { border-color: var(--color-primary); box-shadow: var(--shadow-glow-primary), var(--shadow-glow-primary); }

.stat-card.no-click { cursor: default; }
.stat-card.no-click:hover { border-color: var(--color-border-primary); box-shadow: none; transform: none; }
.stat-card.no-click:hover .stat-icon { animation: none; }

.stat-icon {
  width: 2.5rem; height: 2.5rem;
  border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
  font-size: var(--font-size-lg);
  flex-shrink: 0;
  transition: all 0.25s ease;
}

.stat-icon-primary { background: var(--color-primary-bg); color: var(--color-primary); }
.stat-icon-success { background: var(--color-success-bg); color: var(--color-success); }
.stat-icon-error { background: var(--color-error-bg); color: var(--color-error); }
.stat-icon-muted { background: var(--color-bg-glass); color: var(--color-text-disabled); }
.stat-icon-cyan { background: var(--color-cyan-bg); color: var(--color-cyan); }

.stat-card:hover .stat-icon { animation: icon-pulse 1.5s ease-in-out infinite; }


.stat-info { display: flex; flex-direction: column; }
.stat-value { font-size: var(--font-size-2xl); font-weight: var(--font-weight-bold); color: var(--color-text-primary); line-height: var(--line-height-tight); }
.stat-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); margin-top: 2px; }

/* ── 内容面板（使用 tokens.css 全局 .panel 定义） ── */
.panel-count { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }

/* ── 表格样式 ── */
.sub-name-cell { display: flex; flex-direction: column; gap: 2px; }
.sub-name { font-weight: var(--font-weight-semibold); color: var(--color-text-primary); font-size: var(--font-size-sm); }
.sub-id { font-size: var(--font-size-xs); color: var(--color-text-tertiary); font-family: var(--font-family-mono); }

.url-text {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  font-family: var(--font-family-mono);
  word-break: break-all;
}

.event-tags { display: flex; flex-wrap: wrap; gap: 4px; }

.event-tag {
  font-size: var(--font-size-xs);
  padding: 1px 6px;
  border-radius: var(--radius-xs);
  border: 1px solid;
  white-space: nowrap;
  line-height: 1.6;
}

.fail-count { color: var(--color-error); font-weight: var(--font-weight-semibold); }

.time-ago { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }

.creator-text { font-size: var(--font-size-xs); color: var(--color-text-secondary); }

.error-text { font-size: var(--font-size-xs); color: var(--color-error); }
.muted { color: var(--color-text-tertiary); font-size: var(--font-size-xs); }

.action-group { display: flex; gap: 0.375rem; }

/* .action-btn 使用 tokens.css 全局定义 */

/* ── 刷新按钮旋转动画 ── */
.refresh-btn .refresh-icon {
  display: inline-block;
  transition: transform 0.6s ease;
  font-size: var(--font-size-sm);
  margin-right: 2px;
}

.refresh-btn:hover .refresh-icon {
  transform: rotate(360deg);
}

/* ── 开关按钮样式优化 ── */
.toggle-switch :deep(.el-switch__core) {
  border: 1px solid var(--color-primary-border);
  background-color: var(--color-bg-glass);
  transition: all 0.25s ease;
}

.toggle-switch :deep(.el-switch.is-checked .el-switch__core),
.toggle-switch :deep(.el-switch__core.is-checked) {
  border-color: var(--color-primary-border);
  background-color: var(--color-primary-bg);
  box-shadow: var(--shadow-glow-primary);
}

.toggle-switch :deep(.el-switch__action) {
  transition: all 0.25s ease;
}

/* ── 小图标按钮毛玻璃+hover发光 ── */
.action-icon-btn {
  position: relative;
  padding: 4px 8px !important;
  border-radius: var(--radius-sm) !important;
  transition: var(--button-transition) !important;
  backdrop-filter: blur(4px);
}

.action-icon-btn:hover {
  background: var(--color-primary-bg) !important;
  box-shadow: var(--shadow-glow-primary) !important;
  transform: translateY(-1px);
}

.action-icon-btn:active { transform: translateY(0) scale(0.95) !important; }

/* ── 表单样式 ── */
.header-editor { width: 100%; }
.header-input-row { display: flex; gap: var(--spacing-sm); margin-bottom: var(--spacing-sm); align-items: center; }
.header-item { display: flex; align-items: center; gap: var(--spacing-sm); padding: var(--spacing-xs) 0; border-bottom: 1px solid var(--color-border-primary); }
.header-key { font-size: var(--font-size-xs); color: var(--color-primary-light); font-family: var(--font-family-mono); min-width: 80px; }
.header-val { font-size: var(--font-size-xs); color: var(--color-text-tertiary); flex: 1; }

.retry-row { display: flex; gap: var(--spacing-lg); }
.retry-field { display: flex; flex-direction: column; gap: var(--spacing-xs); }
.retry-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }

@media (max-width: 768px) {
  .webhook-manager { padding: var(--spacing-md); }
  .wm-header { flex-direction: column; gap: var(--spacing-sm); align-items: flex-start; }
  .header-actions { flex-wrap: wrap; width: 100%; }
  .page-title { font-size: var(--font-size-xl); }
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .retry-row { flex-direction: column; gap: var(--spacing-sm); }
}

@media (prefers-reduced-motion: reduce) {
  .webhook-manager, .bg-glow, .page-title { animation: none !important; }
}
</style>
