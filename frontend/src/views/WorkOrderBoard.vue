<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiClient, api } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'
import { useAuthStore } from '@/stores/auth'

interface ApprovalStep {
  role: string
  status: string
  reason?: string
}

interface WorkOrder {
  id: string
  title: string
  description: string
  priority: string
  status: string
  created_by: string
  created_at: string
  updated_at?: string
  assigned_to: string
  approval_chain: ApprovalStep[]
  current_step: number
  intent_id?: string | null
  result?: string
  reject_reason?: string
}

interface BoardSummary {
  total: number
  pending: number
  approved: number
  executing: number
  completed: number
  rejected: number
}

const orders = ref<WorkOrder[]>([])
const boardSummary = ref<BoardSummary>({ total: 0, pending: 0, approved: 0, executing: 0, completed: 0, rejected: 0 })
const isLoading = ref(true)
const authStore = useAuthStore()
const canWrite = computed(() => authStore.userRole !== 'viewer')
const expandedOrderId = ref<string | null>(null)
const showCreateDialog = ref(false)
const newOrder = ref({ title: '', description: '', priority: 'medium' })
const isSubmitting = ref(false)

const columns = [
  { key: 'pending', label: '待审批', color: '#F59E0B', icon: '⏳' },
  { key: 'approved', label: '已批准', color: '#3b82f6', icon: '✅' },
  { key: 'executing', label: '执行中', color: '#00d4ff', icon: '⚡' },
  { key: 'completed', label: '已完成', color: 'var(--color-success)', icon: '🎯' },
  { key: 'rejected', label: '已拒绝', color: 'var(--color-error)', icon: '✕' }
]

const ordersByStatus = computed(() => {
  const grouped: Record<string, WorkOrder[]> = {}
  columns.forEach(col => {
    grouped[col.key] = orders.value.filter(o => o.status === col.key)
  })
  return grouped
})

const priorityConfig: Record<string, { label: string; color: string; bg: string }> = {
  critical: { label: '紧急', color: 'var(--color-error)', bg: 'rgba(239, 68, 68, 0.15)' },
  high: { label: '高', color: '#FF7D00', bg: 'rgba(255, 125, 0, 0.15)' },
  medium: { label: '中', color: '#F59E0B', bg: 'rgba(245, 158, 11, 0.15)' },
  low: { label: '低', color: 'var(--color-success)', bg: 'rgba(82, 196, 26, 0.15)' }
}

const fetchBoard = async () => {
  isLoading.value = true
  try {
    const [boardRes, ordersRes] = await Promise.all([
      apiClient.get(api.workflow.board),
      apiClient.get(api.workflow.orders)
    ])
    const boardData = boardRes.data
    boardSummary.value = boardData || { total: 0, pending: 0, approved: 0, executing: 0, completed: 0, rejected: 0 }
    const orderData = ordersRes.data
    orders.value = Array.isArray(orderData) ? orderData : (orderData?.items || [])
  } catch {
    loadMockData()
  } finally {
    isLoading.value = false
  }
}

const loadMockData = () => {
  const now = new Date()
  const h = 3600000
  const d = 86400000
  orders.value = [
    { id: 'wo_001', title: '核心交换机固件升级', description: '对核心交换机BJ-01和SH-01进行固件升级，修复已知安全漏洞', status: 'pending', priority: 'high', created_by: 'admin', assigned_to: 'operator1', approval_chain: [{ role: 'operator', status: 'pending' }, { role: 'admin', status: 'pending' }], current_step: 0, intent_id: null, created_at: new Date(now.getTime() - 2 * h).toISOString(), updated_at: new Date(now.getTime() - h).toISOString() },
    { id: 'wo_006', title: '防火墙规则批量更新', description: '根据安全审计建议，批量更新数据中心防火墙入站规则，封禁高危端口', status: 'pending', priority: 'critical', created_by: 'admin', assigned_to: 'operator1', approval_chain: [{ role: 'operator', status: 'pending' }, { role: 'admin', status: 'pending' }], current_step: 0, intent_id: null, created_at: new Date(now.getTime() - 30 * 60 * 1000).toISOString() },
    { id: 'wo_007', title: 'SD-WAN策略优化', description: '优化全国SD-WAN链路选择策略，提升视频会议业务优先级', status: 'pending', priority: 'medium', created_by: 'operator1', assigned_to: 'operator2', approval_chain: [{ role: 'operator', status: 'pending' }, { role: 'admin', status: 'pending' }], current_step: 0, intent_id: null, created_at: new Date(now.getTime() - 4 * h).toISOString() },
    { id: 'wo_013', title: 'BGP路由策略优化', description: '优化与3家运营商的BGP路由策略，实现流量智能调度', status: 'pending', priority: 'high', created_by: 'admin', assigned_to: 'operator1', approval_chain: [{ role: 'operator', status: 'pending' }, { role: 'admin', status: 'pending' }], current_step: 0, intent_id: null, created_at: new Date(now.getTime() - 6 * h).toISOString() },
    { id: 'wo_002', title: '新增办公网ACL策略', description: '为新建办公区域配置网络访问控制策略，限制非授权访问', status: 'approved', priority: 'medium', created_by: 'operator1', assigned_to: 'operator2', approval_chain: [{ role: 'operator', status: 'approved' }, { role: 'admin', status: 'approved' }], current_step: 2, intent_id: null, created_at: new Date(now.getTime() - d).toISOString() },
    { id: 'wo_008', title: '核心路由器OSPF重配置', description: '重新配置核心路由器OSPF区域划分，解决路由环路问题', status: 'approved', priority: 'high', created_by: 'admin', assigned_to: 'operator1', approval_chain: [{ role: 'operator', status: 'approved' }, { role: 'admin', status: 'approved' }], current_step: 2, intent_id: 'intent_001', created_at: new Date(now.getTime() - 2 * d).toISOString() },
    { id: 'wo_014', title: '容灾切换演练', description: '组织数据中心容灾切换演练，验证RTO/RPO达标', status: 'approved', priority: 'critical', created_by: 'admin', assigned_to: 'operator2', approval_chain: [{ role: 'operator', status: 'approved' }, { role: 'admin', status: 'approved' }], current_step: 2, intent_id: null, created_at: new Date(now.getTime() - 3 * d).toISOString() },
    { id: 'wo_003', title: '广域网链路扩容', description: '北京到上海广域网链路从10G扩容至40G，满足业务增长需求', status: 'executing', priority: 'high', created_by: 'admin', assigned_to: 'operator1', approval_chain: [{ role: 'operator', status: 'approved' }, { role: 'admin', status: 'approved' }], current_step: 2, intent_id: null, created_at: new Date(now.getTime() - 3 * d).toISOString() },
    { id: 'wo_009', title: '无线AP固件批量升级', description: '对园区200+无线AP进行固件批量升级，修复连接稳定性问题', status: 'executing', priority: 'medium', created_by: 'operator2', assigned_to: 'operator1', approval_chain: [{ role: 'operator', status: 'approved' }, { role: 'admin', status: 'approved' }], current_step: 2, intent_id: null, created_at: new Date(now.getTime() - 4 * d).toISOString() },
    { id: 'wo_015', title: 'SSL证书批量续期', description: '对即将到期的15张SSL证书进行批量续期部署', status: 'executing', priority: 'medium', created_by: 'operator1', assigned_to: 'operator1', approval_chain: [{ role: 'operator', status: 'approved' }, { role: 'admin', status: 'approved' }], current_step: 2, intent_id: null, created_at: new Date(now.getTime() - 5 * d).toISOString() },
    { id: 'wo_004', title: '数据中心网络设备巡检', description: '对贵阳数据中心全部网络设备进行季度巡检', status: 'completed', priority: 'low', created_by: 'operator2', assigned_to: 'operator1', approval_chain: [{ role: 'operator', status: 'approved' }, { role: 'admin', status: 'approved' }], current_step: 2, intent_id: null, result: '巡检完成，发现2台设备CPU偏高，已创建自愈事件', created_at: new Date(now.getTime() - 7 * d).toISOString() },
    { id: 'wo_010', title: 'QoS策略调整', description: '调整生产网QoS策略，保障ERP系统带宽优先级', status: 'completed', priority: 'medium', created_by: 'admin', assigned_to: 'operator2', approval_chain: [{ role: 'operator', status: 'approved' }, { role: 'admin', status: 'approved' }], current_step: 2, intent_id: 'intent_002', result: 'QoS策略已生效，ERP系统延迟降低40%', created_at: new Date(now.getTime() - 10 * d).toISOString() },
    { id: 'wo_011', title: 'DDoS防护规则更新', description: '更新DDoS防护设备清洗规则，应对新型攻击手法', status: 'completed', priority: 'high', created_by: 'admin', assigned_to: 'operator1', approval_chain: [{ role: 'operator', status: 'approved' }, { role: 'admin', status: 'approved' }], current_step: 2, intent_id: null, result: '防护规则已更新，已验证拦截效果', created_at: new Date(now.getTime() - 14 * d).toISOString() },
    { id: 'wo_005', title: 'VPN隧道配置更新', description: '更新与合作伙伴的IPSec VPN隧道配置，启用新的加密算法', status: 'rejected', priority: 'medium', created_by: 'operator1', assigned_to: '', approval_chain: [{ role: 'operator', status: 'approved' }, { role: 'admin', status: 'rejected' }], current_step: 1, intent_id: null, reject_reason: '加密算法兼容性未验证，需先在测试环境验证', created_at: new Date(now.getTime() - 5 * d).toISOString() },
    { id: 'wo_012', title: '网络监控探针部署', description: '在5个分支机构部署网络性能监控探针，实现端到端可观测性', status: 'rejected', priority: 'low', created_by: 'operator2', assigned_to: '', approval_chain: [{ role: 'operator', status: 'approved' }, { role: 'admin', status: 'rejected' }], current_step: 1, intent_id: null, reject_reason: '预算未审批，暂缓执行', created_at: new Date(now.getTime() - 8 * d).toISOString() },
  ]
  boardSummary.value = { total: 15, pending: 4, approved: 3, executing: 3, completed: 3, rejected: 2 }
}

const toggleExpand = (orderId: string) => {
  expandedOrderId.value = expandedOrderId.value === orderId ? null : orderId
}

const approveOrder = async (order: WorkOrder) => {
  try {
    await apiClient.post(api.workflow.approveOrder(order.id))
    showToast('工单已审批通过', 'success')
    await fetchBoard()
    window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
  } catch {
    showToast('审批操作失败', 'error')
  }
}

const rejectReasonInput = ref('')
const showRejectModal = ref(false)
const rejectTargetOrder = ref<WorkOrder | null>(null)

const rejectOrder = (order: WorkOrder) => {
  rejectTargetOrder.value = order
  rejectReasonInput.value = ''
  showRejectModal.value = true
}

const confirmRejectOrder = async () => {
  if (!rejectTargetOrder.value) return
  const order = rejectTargetOrder.value
  const reason = rejectReasonInput.value.trim() || 'Rejected by user'
  showRejectModal.value = false
  try {
    await apiClient.post(api.workflow.rejectOrder(order.id), { reason })
    showToast('工单已拒绝', 'warning')
    await fetchBoard()
    window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
  } catch {
    showToast('拒绝操作失败', 'error')
  }
}

const executeOrder = async (order: WorkOrder) => {
  try {
    await apiClient.post(api.workflow.executeOrder(order.id))
    showToast('工单已开始执行', 'success')
    await fetchBoard()
    window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
  } catch {
    showToast('执行操作失败', 'error')
  }
}

const completeOrder = async (order: WorkOrder) => {
  try {
    await apiClient.post(api.workflow.completeOrder(order.id), { result: 'completed' })
    showToast('工单已完成', 'success')
    await fetchBoard()
    window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
  } catch {
    showToast('完成操作失败', 'error')
  }
}

const createOrder = async () => {
  if (!newOrder.value.title.trim()) {
    showToast('请输入工单标题', 'warning')
    return
  }
  isSubmitting.value = true
  try {
    await apiClient.post(api.workflow.orders, {
      title: newOrder.value.title,
      description: newOrder.value.description,
      priority: newOrder.value.priority
    })
    showToast('工单创建成功', 'success')
    showCreateDialog.value = false
    newOrder.value = { title: '', description: '', priority: 'medium' }
    await fetchBoard()
    window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
  } catch {
    showToast('工单创建失败', 'error')
  } finally {
    isSubmitting.value = false
  }
}

const formatDate = (dateStr: string) => {
  try {
    return new Date(dateStr).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return dateStr
  }
}

const timeAgo = (dateStr: string): string => {
  if (!dateStr) return '--'
  const diff = Date.now() - new Date(dateStr).getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return `${Math.floor(diff / 86400000)}天前`
}

const isRefreshing = ref(false)
const lastRefreshTime = ref('')

const refreshBoard = async () => {
  isRefreshing.value = true
  await fetchBoard()
  lastRefreshTime.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  isRefreshing.value = false
}

const exportBoardData = () => {
  const data = { summary: boardSummary.value, orders: orders.value, exportedAt: new Date().toISOString() }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `work-orders-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
  showToast('工单数据已导出', 'success')
}

const resubmitOrder = async (order: WorkOrder) => {
  try {
    await apiClient.post(api.workflow.orders, { title: order.title, description: order.description, priority: order.priority })
    showToast('工单已重新提交', 'success')
    await fetchBoard()
  } catch {
    showToast('重新提交失败', 'error')
  }
}

const getStepStatusLabel = (status: string) => {
  const map: Record<string, string> = { pending: '待审批', approved: '已通过', rejected: '已拒绝' }
  return map[status] || status
}

const getRoleLabel = (role: string) => {
  const map: Record<string, string> = { operator: '操作员', admin: '管理员', cto: 'CTO' }
  return map[role] || role
}

onMounted(() => {
  fetchBoard()
  lastRefreshTime.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
})
</script>

<template>
  <div class="work-order-board">
    <div class="wob-bg">
      <div class="bg-grid"></div>
      <div class="bg-glow glow-1"></div>
      <div class="bg-glow glow-2"></div>
    </div>

    <div class="wob-header">
      <div class="header-left">
        <h1 class="page-title">工单编排看板</h1>
        <p class="page-subtitle">Work Order Orchestration Board</p>
      </div>
      <div class="header-actions">
        <span v-if="lastRefreshTime" class="last-refresh">{{ lastRefreshTime }}</span>
        <button type="button" class="action-btn export-btn" @click="exportBoardData" title="导出数据">导出</button>
        <button type="button" :class="['action-btn', 'refresh-btn', { spinning: isRefreshing }]" @click="refreshBoard" title="刷新数据">
          <span class="refresh-icon">🔄</span> 刷新
        </button>
        <button type="button" v-if="canWrite" class="create-btn" @click="showCreateDialog = true">
          <span class="create-icon">+</span> 新建工单
        </button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon" style="background: rgba(0,212,255,0.12); color: #00d4ff;">📋</div>
        <div class="stat-info">
          <div class="stat-value">{{ boardSummary.total }}</div>
          <div class="stat-label">工单总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: rgba(245,158,11,0.12); color: #F59E0B;">⏳</div>
        <div class="stat-info">
          <div class="stat-value">{{ boardSummary.pending }}</div>
          <div class="stat-label">待审批</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: rgba(59,130,246,0.12); color: #3b82f6;">✅</div>
        <div class="stat-info">
          <div class="stat-value">{{ boardSummary.approved }}</div>
          <div class="stat-label">已批准</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: rgba(0,212,255,0.12); color: #00d4ff;">⚡</div>
        <div class="stat-info">
          <div class="stat-value">{{ boardSummary.executing }}</div>
          <div class="stat-label">执行中</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: rgba(82,196,26,0.12); color: var(--color-success);">🎯</div>
        <div class="stat-info">
          <div class="stat-value">{{ boardSummary.completed }}</div>
          <div class="stat-label">已完成</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: rgba(239,68,68,0.12); color: var(--color-error);">✕</div>
        <div class="stat-info">
          <div class="stat-value">{{ boardSummary.rejected || 0 }}</div>
          <div class="stat-label">已拒绝</div>
        </div>
      </div>
    </div>

    <div v-if="isLoading" class="loading-state">
      <div class="loading-spinner"></div>
      <span>加载工单数据...</span>
    </div>

    <div v-else class="kanban-board">
      <div v-for="col in columns" :key="col.key" class="kanban-column">
        <div class="column-header" :style="{ borderTopColor: col.color }">
          <span class="column-dot" :style="{ background: col.color }"></span>
          <span class="column-title">{{ col.label }}</span>
          <span class="column-count">{{ ordersByStatus[col.key]?.length || 0 }}</span>
        </div>

        <div class="column-body">
          <div
            v-for="order in ordersByStatus[col.key]"
            :key="order.id"
            :class="['order-card', { expanded: expandedOrderId === order.id }]"
          >
            <div class="card-summary" @click="toggleExpand(order.id)">
              <div class="card-top">
                <span class="priority-badge" :style="{ background: priorityConfig[order.priority]?.bg, color: priorityConfig[order.priority]?.color }">
                  {{ priorityConfig[order.priority]?.label || order.priority }}
                </span>
                <span class="card-id">#{{ order.id }}</span>
              </div>
              <h4 class="card-title">{{ order.title }}</h4>
              <div class="card-meta">
                <span class="meta-creator">{{ order.created_by }}</span>
                <span class="meta-time">{{ timeAgo(order.created_at) }}</span>
              </div>
              <div v-if="order.assigned_to" class="card-assignee-inline">
                <span class="assignee-icon">👤</span> {{ order.assigned_to }}
              </div>
            </div>

            <div v-if="expandedOrderId === order.id" class="card-detail">
              <p class="detail-desc">{{ order.description }}</p>

              <div v-if="order.intent_id" class="detail-intent">
                <span class="intent-label">关联意图</span>
                <span class="intent-id">{{ order.intent_id }}</span>
              </div>

              <div v-if="order.approval_chain && order.approval_chain.length > 0" class="approval-chain">
                <span class="chain-label">审批链</span>
                <div class="chain-steps">
                  <div v-for="(step, idx) in order.approval_chain" :key="idx" :class="['chain-step', step.status]">
                    <span class="step-dot"></span>
                    <span class="step-info">
                      <span class="step-name">{{ getRoleLabel(step.role) }}</span>
                      <span class="step-status">{{ getStepStatusLabel(step.status) }}</span>
                    </span>
                  </div>
                </div>
              </div>

              <div v-if="order.assigned_to" class="detail-assignee">
                <span class="assignee-label">指派给</span>
                <span class="assignee-name">{{ order.assigned_to }}</span>
              </div>

              <div v-if="order.result" class="detail-result">
                <span class="result-label">执行结果</span>
                <span class="result-text">{{ order.result }}</span>
              </div>

              <div v-if="order.reject_reason" class="detail-reject-reason">
                <span class="reject-reason-label">拒绝原因</span>
                <span class="reject-reason-text">{{ order.reject_reason }}</span>
              </div>

              <div class="card-actions">
                <template v-if="canWrite && order.status === 'pending'">
                  <button class="action-btn approve" @click.stop="approveOrder(order)">审批通过</button>
                  <button class="action-btn reject" @click.stop="rejectOrder(order)">拒绝</button>
                </template>
                <template v-if="canWrite && order.status === 'approved'">
                  <button class="action-btn execute" @click.stop="executeOrder(order)">开始执行</button>
                </template>
                <template v-if="canWrite && order.status === 'executing'">
                  <button class="action-btn complete" @click.stop="completeOrder(order)">完成</button>
                </template>
                <template v-if="canWrite && order.status === 'rejected'">
                  <button class="action-btn resubmit" @click.stop="resubmitOrder(order)">重新提交</button>
                </template>
              </div>
            </div>
          </div>

          <div v-if="!ordersByStatus[col.key]?.length" class="empty-column">
            暂无{{ col.label }}工单
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showCreateDialog" class="modal-overlay" @click.self="showCreateDialog = false" role="dialog" aria-modal="true">
        <div class="modal-content">
          <div class="modal-header">
            <h3 class="modal-title">新建工单</h3>
            <button class="modal-close" @click="showCreateDialog = false">✕</button>
          </div>
          <div class="form-group">
            <label class="form-label">标题</label>
            <input v-model="newOrder.title" type="text" class="form-input" placeholder="输入工单标题" />
          </div>
          <div class="form-group">
            <label class="form-label">描述</label>
            <textarea v-model="newOrder.description" class="form-textarea" placeholder="输入工单描述" rows="4"></textarea>
          </div>
          <div class="form-group">
            <label class="form-label">优先级</label>
            <div class="priority-select">
              <button
                v-for="(cfg, key) in priorityConfig"
                :key="key"
                :class="['priority-option', { selected: newOrder.priority === key }]"
                :style="newOrder.priority === key ? { background: cfg.bg, color: cfg.color, borderColor: cfg.color } : {}"
                @click="newOrder.priority = key"
              >{{ cfg.label }}</button>
            </div>
          </div>
          <div class="modal-actions">
            <button class="modal-btn cancel" @click="showCreateDialog = false">取消</button>
            <button v-if="canWrite" class="modal-btn submit" @click="createOrder" :disabled="isSubmitting">{{ isSubmitting ? '提交中...' : '创建' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showRejectModal" class="modal-overlay" @click.self="showRejectModal = false">
        <div class="modal-content" style="max-width:440px">
          <h3 class="modal-title">拒绝工单</h3>
          <p style="color:var(--color-text-tertiary);font-size:var(--font-size-sm);margin-bottom:12px;">工单: {{ rejectTargetOrder?.title }}</p>
          <textarea v-model="rejectReasonInput" placeholder="请输入拒绝原因（可选）" rows="3" style="width:100%;background:#0F172A;border:1px solid #334155;border-radius:var(--radius-md);padding:10px;color:var(--color-text-secondary);font-size:var(--font-size-sm);resize:vertical;"></textarea>
          <div class="modal-actions" style="margin-top:16px;">
            <button class="modal-btn" @click="showRejectModal = false">取消</button>
            <button v-if="canWrite" class="modal-btn primary" style="background:var(--color-error);" @click="confirmRejectOrder">确认拒绝</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.work-order-board { position: relative; animation: page-enter 0.5s ease-out; min-height: 100vh; padding: 24px; will-change: transform, opacity; }
.wob-bg { position: fixed; top: 0; left: 0; right: 0; bottom: 0; pointer-events: none; z-index: 0; overflow: hidden; }
.bg-grid { position: absolute; inset: 0; background-image: linear-gradient(rgba(0,212,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.03) 1px, transparent 1px); background-size: 60px 60px; mask-image: radial-gradient(ellipse 80% 60% at 50% 30%, black 20%, transparent 70%); }
.bg-glow { position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.4; }
.glow-1 { width: 400px; height: 400px; background: rgba(0,212,255,0.08); top: -100px; right: 10%; animation: glow-float 12s ease-in-out infinite; will-change: transform, opacity; }
.glow-2 { width: 300px; height: 300px; background: rgba(59,130,246,0.06); bottom: 10%; left: 5%; animation: glow-float 15s ease-in-out infinite reverse; will-change: transform, opacity; }

.work-order-board > *:not(.wob-bg) { position: relative; z-index: var(--z-content); }

.wob-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--color-border-primary); }
.header-actions { display: flex; align-items: center; gap: 10px; }
.last-refresh { font-size: var(--font-size-xs); color: var(--color-text-disabled); font-family: 'SF Mono', 'Cascadia Code', monospace; }
.header-left { display: flex; flex-direction: column; gap: 4px; }
.page-title { font-size: var(--font-size-2xl); font-weight: 700; margin: 0; background: linear-gradient(135deg, var(--color-text-secondary) 0%, var(--color-cyan) 50%, var(--color-primary) 100%); background-size: 200% auto; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: title-shimmer 4s ease-in-out infinite; }
.page-subtitle { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin: 0; }


.action-btn { display: flex; align-items: center; gap: 6px; padding: 8px 16px; background: rgba(22, 93, 255, 0.1); color: var(--color-primary-light); border: 1px solid rgba(22, 93, 255, 0.25); border-radius: var(--radius-lg); font-size: var(--font-size-sm); font-weight: 500; cursor: pointer; transition: all 0.25s ease; min-height: 44px; backdrop-filter: blur(8px); }
.action-btn:hover:not(:disabled) { background: rgba(22, 93, 255, 0.2); border-color: rgba(59, 130, 246, 0.5); box-shadow: 0 2px 12px rgba(59, 130, 246, 0.2); color: var(--color-primary-lighter); transform: scale(1.02); }
.action-btn:active:not(:disabled) { transform: scale(0.97); }
.action-btn:disabled { opacity: 0.35; cursor: not-allowed; transform: none; box-shadow: none; }
.refresh-btn.spinning .refresh-icon { animation: spin 1s linear infinite; }
.refresh-icon { display: inline-block; transition: transform 0.6s ease; }
.refresh-btn:hover .refresh-icon:not(.spinning) { transform: rotate(360deg); }
.create-btn { display: flex; align-items: center; gap: 8px; padding: 10px 24px; background: var(--gradient-primary); color: var(--color-text-primary); border: none; border-radius: var(--radius-lg); font-size: var(--font-size-base); font-weight: 600; cursor: pointer; transition: var(--button-transition); min-height: 44px; }
.create-btn:hover { transform: translateY(-1px); box-shadow: var(--shadow-glow-primary); }
.create-icon { font-size: var(--font-size-lg); font-weight: 700; }
.export-btn { backdrop-filter: blur(8px); }
.export-btn:hover:not(:disabled) { background: rgba(22, 93, 255, 0.2); border-color: rgba(59, 130, 246, 0.5); box-shadow: 0 2px 16px rgba(59, 130, 246, 0.25); color: var(--color-primary-lighter); transform: scale(1.02); }
.export-btn:active:not(:disabled) { transform: scale(0.97); }

/* ── 统计卡片 ── */
.stats-row { display: grid; grid-template-columns: repeat(6, 1fr); gap: 0.75rem; margin-bottom: 24px; }
.stat-card { display: flex; align-items: center; gap: 0.75rem; padding: 0.875rem 1rem; background: var(--gradient-glass); border-radius: var(--radius-lg); border: 1px solid var(--color-border-primary); transition: all 0.3s ease; backdrop-filter: blur(12px); will-change: transform, opacity; }
.stat-card:hover { transform: translateY(-2px); border-color: rgba(22, 93, 255, 0.4); box-shadow: 0 4px 20px rgba(22, 93, 255, 0.15), 0 0 0 1px rgba(22, 93, 255, 0.1); }
.stat-icon { width: 40px; height: 40px; border-radius: var(--radius-lg); display: flex; align-items: center; justify-content: center; font-size: var(--font-size-lg); flex-shrink: 0; transition: all 0.25s ease; }
.stat-card:hover .stat-icon { animation: iconPulse 1.5s ease-in-out infinite; }
@keyframes iconPulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.1); } }
.stat-info { display: flex; flex-direction: column; }
.stat-value { font-size: var(--font-size-2xl); font-weight: 700; color: var(--color-text-primary); line-height: 1.2; }
.stat-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); margin-top: 2px; }

.loading-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; padding: 80px 24px; color: var(--color-text-tertiary); }
.loading-spinner { width: 40px; height: 40px; border: 3px solid rgba(0,212,255,0.2); border-top-color: var(--color-cyan); border-radius: 50%; animation: spin 1s linear infinite; will-change: transform, opacity; }


.kanban-board { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; min-height: 500px; }
.kanban-column { background: var(--gradient-glass); border-radius: var(--radius-xl); border: var(--card-border); border-top: 3px solid; display: flex; flex-direction: column; max-height: calc(100vh - 340px); }
.column-header { display: flex; align-items: center; gap: 8px; padding: 14px 16px; border-bottom: 1px solid var(--color-border-primary); }
.column-dot { width: 8px; height: 8px; border-radius: 50%; }
.column-title { font-size: var(--font-size-base); font-weight: 600; color: var(--color-text-primary); }
.column-count { font-size: var(--font-size-xs); padding: 2px 8px; border-radius: var(--radius-lg); background: var(--color-bg-glass); color: var(--color-text-tertiary); font-weight: 600; margin-left: auto; }
.column-body { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; }

.order-card { background: var(--color-bg-glass); border-radius: var(--radius-lg); border: 1px solid var(--color-border-primary); transition: all 0.25s var(--ease-out); cursor: pointer; will-change: transform, opacity; }
.order-card:hover { border-color: var(--color-border-secondary); box-shadow: var(--shadow-card-hover); }
.order-card.expanded { border-color: var(--color-primary-border); background: var(--color-bg-glass-strong); }
.card-summary { padding: 14px; }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.priority-badge { font-size: var(--font-size-xs); padding: 3px 10px; border-radius: var(--radius-lg); font-weight: 600; }
.card-id { font-size: var(--font-size-xs); color: var(--color-text-disabled); font-family: 'SF Mono', 'Cascadia Code', monospace; }
.card-title { font-size: var(--font-size-base); font-weight: 600; color: var(--color-text-primary); margin: 0 0 8px; line-height: 1.4; }
.card-meta { display: flex; justify-content: space-between; align-items: center; }
.meta-creator { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.meta-time { font-size: var(--font-size-xs); color: var(--color-text-disabled); }
.card-assignee-inline { font-size: var(--font-size-xs); color: var(--color-primary-light); margin-top: 6px; }
.assignee-icon { font-size: var(--font-size-xs); }

.card-detail { border-top: 1px solid var(--color-border-primary); padding: 14px; animation: detail-expand 0.2s var(--ease-out); }
@keyframes detail-expand { from { opacity: 0; max-height: 0; } to { opacity: 1; max-height: 500px; } }
.detail-desc { font-size: var(--font-size-sm); color: var(--color-text-tertiary); line-height: 1.6; margin: 0 0 12px; }

.detail-intent { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding: 6px 10px; background: rgba(22,93,255,0.08); border-radius: var(--radius-lg); border: 1px solid rgba(22,93,255,0.15); }
.intent-label { font-size: var(--font-size-xs); color: var(--color-primary); font-weight: 500; }
.intent-id { font-size: var(--font-size-xs); color: var(--color-primary-light); font-family: 'SF Mono', 'Cascadia Code', monospace; }

.approval-chain { margin-bottom: 12px; }
.chain-label { display: block; font-size: var(--font-size-xs); color: var(--color-text-disabled); margin-bottom: 8px; font-weight: 500; }
.chain-steps { display: flex; flex-direction: column; gap: 6px; }
.chain-step { display: flex; align-items: center; gap: 8px; font-size: var(--font-size-xs); }
.step-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-text-disabled); flex-shrink: 0; }
.chain-step.approved .step-dot { background: var(--color-success); }
.chain-step.rejected .step-dot { background: var(--color-error); }
.chain-step.pending .step-dot { background: var(--color-warning); animation: dot-pulse 2s ease-in-out infinite; }

.step-info { display: flex; gap: 6px; align-items: center; }
.step-name { color: var(--color-text-secondary); }
.step-status { color: var(--color-text-disabled); font-size: var(--font-size-xs); }

.detail-assignee { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.assignee-label { font-size: var(--font-size-xs); color: var(--color-text-disabled); }
.assignee-name { font-size: var(--font-size-sm); color: var(--color-primary); font-weight: 500; }

.detail-result { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; padding: 8px 10px; background: rgba(82,196,26,0.08); border-radius: var(--radius-lg); border: 1px solid rgba(82,196,26,0.15); }
.result-label { font-size: var(--font-size-xs); color: var(--color-success); font-weight: 500; }
.result-text { font-size: var(--font-size-xs); color: var(--color-text-tertiary); line-height: 1.5; }

.detail-reject-reason { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; padding: 8px 10px; background: rgba(239,68,68,0.08); border-radius: var(--radius-lg); border: 1px solid rgba(239,68,68,0.15); }
.reject-reason-label { font-size: var(--font-size-xs); color: var(--color-error); font-weight: 500; }
.reject-reason-text { font-size: var(--font-size-xs); color: var(--color-text-tertiary); line-height: 1.5; }

.card-actions { display: flex; gap: 8px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.04); }
.card-actions .action-btn { flex: 1; padding: 8px 12px; border-radius: var(--radius-lg); font-size: var(--font-size-xs); font-weight: 600; cursor: pointer; transition: all 0.25s ease; min-height: 44px; backdrop-filter: blur(8px); }
.card-actions .action-btn:active:not(:disabled) { transform: scale(0.97); }
.card-actions .action-btn:disabled { opacity: 0.35; cursor: not-allowed; transform: none; box-shadow: none; }
.card-actions .action-btn.approve { background: rgba(82, 196, 26, 0.12); color: var(--color-success-light); border: 1px solid rgba(82, 196, 26, 0.3); }
.card-actions .action-btn.approve:hover { background: rgba(82, 196, 26, 0.22); border-color: rgba(82, 196, 26, 0.55); box-shadow: 0 2px 16px rgba(82, 196, 26, 0.25); color: var(--color-success-light); transform: scale(1.02); }
.card-actions .action-btn.reject { background: rgba(239, 68, 68, 0.12); color: var(--color-error-light); border: 1px solid rgba(239, 68, 68, 0.3); }
.card-actions .action-btn.reject:hover { background: rgba(239, 68, 68, 0.22); border-color: rgba(239, 68, 68, 0.55); box-shadow: 0 2px 16px rgba(239, 68, 68, 0.25); color: var(--color-error-light); transform: scale(1.02); }
.card-actions .action-btn.execute { background: rgba(22, 93, 255, 0.12); color: var(--color-primary-light); border: 1px solid rgba(22, 93, 255, 0.3); }
.card-actions .action-btn.execute:hover { background: rgba(22, 93, 255, 0.22); border-color: rgba(22, 93, 255, 0.55); box-shadow: 0 2px 16px rgba(22, 93, 255, 0.25); color: var(--color-primary-lighter); transform: scale(1.02); }
.card-actions .action-btn.complete { background: rgba(0, 212, 255, 0.12); color: var(--color-cyan); border: 1px solid rgba(0, 212, 255, 0.3); }
.card-actions .action-btn.complete:hover { background: rgba(0, 212, 255, 0.22); border-color: rgba(0, 212, 255, 0.55); box-shadow: 0 2px 16px rgba(0, 212, 255, 0.25); color: var(--color-cyan); transform: scale(1.02); }
.card-actions .action-btn.resubmit { background: rgba(250, 173, 20, 0.12); color: var(--color-warning-light); border: 1px solid rgba(250, 173, 20, 0.3); }
.card-actions .action-btn.resubmit:hover { background: rgba(250, 173, 20, 0.22); border-color: rgba(250, 173, 20, 0.55); box-shadow: 0 2px 16px rgba(250, 173, 20, 0.25); color: var(--color-warning-light); transform: scale(1.02); }

.empty-column { text-align: center; padding: 32px 16px; color: var(--color-text-disabled); font-size: var(--font-size-sm); }

.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: var(--modal-overlay-bg); display: flex; align-items: center; justify-content: center; z-index: var(--z-overlay); backdrop-filter: blur(var(--modal-backdrop-blur)); animation: fade-in 0.2s var(--ease-out); }
.modal-content { background: var(--color-bg-elevated); border-radius: var(--modal-border-radius); padding: var(--modal-padding); width: 90%; max-width: 480px; border: 1px solid var(--color-border-primary); box-shadow: var(--shadow-modal); }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.modal-title { font-size: var(--font-size-lg); font-weight: 600; color: var(--color-text-primary); margin: 0; }
.modal-close { background: none; border: none; color: var(--color-text-tertiary); font-size: var(--font-size-2xl); cursor: pointer; padding: 4px; line-height: 1; transition: color 0.2s ease; }
.modal-close:hover { color: var(--color-text-primary); }
.form-group { margin-bottom: 16px; }
.form-label { display: block; font-size: var(--font-size-sm); font-weight: 500; color: var(--color-text-tertiary); margin-bottom: 6px; }
.form-input { width: 100%; padding: var(--input-padding); background: var(--input-bg); border: 1px solid var(--input-border); border-radius: var(--input-radius); color: var(--color-text-secondary); font-size: var(--font-size-base); outline: none; transition: all 0.25s var(--ease-out); box-sizing: border-box; }
.form-input::placeholder { color: var(--color-text-disabled); }
.form-input:focus { border-color: var(--input-border-focus); box-shadow: var(--input-shadow-focus); }
.form-textarea { width: 100%; padding: var(--input-padding); background: var(--input-bg); border: 1px solid var(--input-border); border-radius: var(--input-radius); color: var(--color-text-secondary); font-size: var(--font-size-base); outline: none; transition: all 0.25s var(--ease-out); resize: vertical; font-family: inherit; box-sizing: border-box; }
.form-textarea::placeholder { color: var(--color-text-disabled); }
.form-textarea:focus { border-color: var(--input-border-focus); box-shadow: var(--input-shadow-focus); }
.priority-select { display: flex; gap: 8px; }
.priority-option { flex: 1; padding: 8px 12px; background: rgba(15,23,42,0.6); color: var(--color-text-tertiary); border: 1px solid rgba(255,255,255,0.1); border-radius: var(--radius-lg); font-size: var(--font-size-sm); font-weight: 500; cursor: pointer; transition: all 0.25s ease; text-align: center; }
.priority-option:hover { border-color: rgba(255,255,255,0.2); }
.priority-option.selected { border-width: 1.5px; font-weight: 600; }
.modal-actions { display: flex; gap: 12px; margin-top: 20px; }
.modal-btn { flex: 1; padding: 12px; border: none; border-radius: var(--radius-lg); font-size: var(--font-size-base); font-weight: 600; cursor: pointer; transition: all 0.25s ease; }
.modal-btn.cancel { background: var(--input-bg); color: var(--color-text-tertiary); border: 1px solid var(--color-border-primary); }
.modal-btn.cancel:hover { background: var(--color-bg-active); color: var(--color-text-primary); }
.modal-btn.submit { background: var(--gradient-primary); color: var(--color-text-primary); }
.modal-btn.submit:hover:not(:disabled) { transform: translateY(-1px); box-shadow: var(--shadow-glow-primary); }
.modal-btn.submit:disabled { opacity: 0.6; cursor: not-allowed; }

@media (max-width: 1200px) { .kanban-board { grid-template-columns: repeat(3, 1fr); } .stats-row { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 768px) { .work-order-board { padding: 16px; } .kanban-board { grid-template-columns: 1fr; } .kanban-column { max-height: 400px; } .wob-header { flex-direction: column; gap: 12px; align-items: flex-start; } .page-title { font-size: var(--font-size-xl); } .stats-row { grid-template-columns: repeat(2, 1fr); } }
@media (prefers-reduced-motion: reduce) { .work-order-board, .bg-glow, .chain-step.pending .step-dot { animation: none !important; transition: none !important; } }
</style>
