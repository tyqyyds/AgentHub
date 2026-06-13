<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'

interface WorkOrder {
  id: string
  title: string
  priority: 'critical' | 'high' | 'medium' | 'low'
  status: 'open' | 'in_progress' | 'resolved' | 'closed'
  assignee: string
  slaDeadline: string
  createdAt: string
  description: string
}

const loading = ref(false)
const orders = ref<WorkOrder[]>([
  { id: 'WO-001', title: '核心路由器CPU利用率异常', priority: 'critical', status: 'in_progress', assignee: '张工', slaDeadline: '2026-06-13 16:00', createdAt: '2026-06-13 10:00', description: '核心路由器R1 CPU利用率持续超过90%' },
  { id: 'WO-002', title: '防火墙规则冲突', priority: 'high', status: 'open', assignee: '李工', slaDeadline: '2026-06-14 10:00', createdAt: '2026-06-13 09:30', description: '新部署的ACL规则与现有规则存在冲突' },
  { id: 'WO-003', title: '接入交换机端口故障', priority: 'medium', status: 'resolved', assignee: '王工', slaDeadline: '2026-06-15 10:00', createdAt: '2026-06-12 14:00', description: '3楼接入交换机端口4-8无法正常工作' },
  { id: 'WO-004', title: 'VPN隧道断连', priority: 'high', status: 'open', assignee: '赵工', slaDeadline: '2026-06-13 18:00', createdAt: '2026-06-13 11:00', description: '分支办公室VPN隧道频繁断连' },
  { id: 'WO-005', title: '日志服务器磁盘告警', priority: 'low', status: 'closed', assignee: '孙工', slaDeadline: '2026-06-16 10:00', createdAt: '2026-06-11 16:00', description: '日志服务器磁盘使用率超过85%' }
])

const activeTab = ref<'all' | 'my' | 'sla'>('all')
const showCreateDialog = ref(false)
const newOrder = ref({ title: '', priority: 'medium' as WorkOrder['priority'], description: '' })

const filteredOrders = computed(() => {
  if (activeTab.value === 'my') return orders.value.filter(o => o.assignee === '张工')
  if (activeTab.value === 'sla') return orders.value.filter(o => o.status === 'open' || o.status === 'in_progress')
  return orders.value
})

const stats = computed(() => ({
  open: orders.value.filter(o => o.status === 'open').length,
  inProgress: orders.value.filter(o => o.status === 'in_progress').length,
  resolved: orders.value.filter(o => o.status === 'resolved').length,
  slaAtRisk: orders.value.filter(o => (o.status === 'open' || o.status === 'in_progress') && o.priority === 'critical').length
}))

function getPriorityLabel(p: string) {
  return p === 'critical' ? '紧急' : p === 'high' ? '高' : p === 'medium' ? '中' : '低'
}

function getStatusLabel(s: string) {
  return s === 'open' ? '待处理' : s === 'in_progress' ? '处理中' : s === 'resolved' ? '已解决' : '已关闭'
}

function createOrder() {
  if (!newOrder.value.title.trim()) return
  orders.value.unshift({
    id: `WO-${String(orders.value.length + 1).padStart(3, '0')}`,
    title: newOrder.value.title,
    priority: newOrder.value.priority,
    status: 'open',
    assignee: '当前用户',
    slaDeadline: new Date(Date.now() + 24 * 3600000).toISOString().slice(0, 16).replace('T', ' '),
    createdAt: new Date().toISOString().slice(0, 16).replace('T', ' '),
    description: newOrder.value.description
  })
  newOrder.value = { title: '', priority: 'medium', description: '' }
  showCreateDialog.value = false
}

onMounted(() => {
  // TODO: 调用API获取工单列表
})
</script>

<template>
  <div class="work-order-board">
    <h1 class="page-title">工单看板</h1>

    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value stat-open">{{ stats.open }}</div>
        <div class="stat-label">待处理</div>
      </div>
      <div class="stat-card">
        <div class="stat-value stat-in-progress">{{ stats.inProgress }}</div>
        <div class="stat-label">处理中</div>
      </div>
      <div class="stat-card">
        <div class="stat-value stat-resolved">{{ stats.resolved }}</div>
        <div class="stat-label">已解决</div>
      </div>
      <div class="stat-card">
        <div class="stat-value stat-sla-risk">{{ stats.slaAtRisk }}</div>
        <div class="stat-label">SLA风险</div>
      </div>
    </div>

    <div class="toolbar">
      <div class="tabs">
        <button :class="['tab', { active: activeTab === 'all' }]" @click="activeTab = 'all'">全部</button>
        <button :class="['tab', { active: activeTab === 'my' }]" @click="activeTab = 'my'">我的工单</button>
        <button :class="['tab', { active: activeTab === 'sla' }]" @click="activeTab = 'sla'">SLA监控</button>
      </div>
      <button class="action-btn" @click="showCreateDialog = true">+ 创建工单</button>
    </div>

    <div class="order-list">
      <div v-for="order in filteredOrders" :key="order.id" class="order-card">
        <div class="order-header">
          <div class="order-id">{{ order.id }}</div>
          <span :class="['priority-badge', order.priority]">{{ getPriorityLabel(order.priority) }}</span>
          <span :class="['status-badge', order.status]">{{ getStatusLabel(order.status) }}</span>
        </div>
        <div class="order-title">{{ order.title }}</div>
        <div class="order-desc">{{ order.description }}</div>
        <div class="order-footer">
          <span class="footer-item">👤 {{ order.assignee }}</span>
          <span class="footer-item">📅 {{ order.createdAt }}</span>
          <span class="footer-item sla" v-if="order.status === 'open' || order.status === 'in_progress'">
            ⏰ SLA: {{ order.slaDeadline }}
          </span>
        </div>
      </div>
    </div>

    <div v-if="showCreateDialog" class="dialog-overlay" @click.self="showCreateDialog = false">
      <div class="dialog-box">
        <h3 class="dialog-title">创建工单</h3>
        <div class="form-group">
          <label>标题</label>
          <input v-model="newOrder.title" class="form-input" placeholder="输入工单标题" />
        </div>
        <div class="form-group">
          <label>优先级</label>
          <select v-model="newOrder.priority" class="form-input">
            <option value="critical">紧急</option>
            <option value="high">高</option>
            <option value="medium">中</option>
            <option value="low">低</option>
          </select>
        </div>
        <div class="form-group">
          <label>描述</label>
          <textarea v-model="newOrder.description" class="form-input" placeholder="输入工单描述" rows="3"></textarea>
        </div>
        <div class="dialog-actions">
          <button class="btn-sm" @click="showCreateDialog = false">取消</button>
          <button class="action-btn" @click="createOrder">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); color: var(--color-white); margin-bottom: var(--spacing-2xl); }

.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--spacing-lg); margin-bottom: var(--spacing-2xl); }

.stat-card {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-xl);
  padding: var(--spacing-lg);
  text-align: center;
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
}

.stat-value { font-size: var(--font-size-4xl); font-weight: var(--font-weight-bold); }
.stat-value.stat-open { color: var(--color-orange); }
.stat-value.stat-in-progress { color: var(--color-primary); }
.stat-value.stat-resolved { color: var(--color-success); }
.stat-value.stat-sla-risk { color: var(--color-error); }
.stat-label { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-top: var(--spacing-2xs); }

.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-xl); }

.tabs { display: flex; gap: var(--spacing-2xs); background: rgba(var(--color-bg-elevated-rgb), 0.6); border-radius: var(--radius-lg); padding: var(--spacing-2xs); }

.tab {
  padding: var(--spacing-sm) var(--spacing-lg);
  border: none;
  background: transparent;
  color: var(--color-text-tertiary);
  border-radius: var(--radius-lg);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: all 0.2s;
}

.tab.active { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); }

.action-btn {
  padding: var(--spacing-sm-md) var(--spacing-xl);
  background: var(--gradient-primary);
  color: var(--color-white);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.action-btn:hover { transform: translateY(-1px); box-shadow: 0 var(--spacing-sm) var(--spacing-md) rgba(var(--color-primary-rgb), 0.4); }

.order-list { display: flex; flex-direction: column; gap: var(--spacing-md); }

.order-card {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-xl);
  padding: var(--spacing-lg) var(--spacing-xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  transition: all 0.2s;
}

.order-card:hover { border-color: rgba(var(--color-primary-rgb), 0.3); }

.order-header { display: flex; align-items: center; gap: var(--spacing-sm-md); margin-bottom: var(--spacing-sm); }

.order-id { font-size: var(--font-size-sm); color: var(--color-text-quaternary); font-family: monospace; }

.priority-badge {
  font-size: var(--font-size-xs);
  padding: var(--spacing-3xs) var(--spacing-sm);
  border-radius: var(--radius-lg);
  font-weight: var(--font-weight-medium);
}

.priority-badge.critical { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); }
.priority-badge.high { background: rgba(var(--color-orange-rgb), 0.2); color: var(--color-orange); }
.priority-badge.medium { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); }
.priority-badge.low { background: rgba(var(--color-text-quaternary-rgb), 0.2); color: var(--color-text-tertiary); }

.status-badge {
  font-size: var(--font-size-xs);
  padding: var(--spacing-3xs) var(--spacing-sm);
  border-radius: var(--radius-lg);
  font-weight: var(--font-weight-medium);
  margin-left: auto;
}

.status-badge.open { background: rgba(var(--color-orange-rgb), 0.2); color: var(--color-orange); }
.status-badge.in_progress { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); }
.status-badge.resolved { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); }
.status-badge.closed { background: rgba(var(--color-text-quaternary-rgb), 0.2); color: var(--color-text-tertiary); }

.order-title { font-size: var(--font-size-md); font-weight: var(--font-weight-semibold); color: var(--color-white); margin-bottom: var(--spacing-xs); }
.order-desc { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-bottom: var(--spacing-md); }

.order-footer { display: flex; gap: var(--spacing-lg); font-size: var(--font-size-sm); color: var(--color-text-quaternary); }
.footer-item.sla { color: var(--color-orange); font-weight: var(--font-weight-medium); }

.dialog-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; justify-content: center; z-index: var(--z-modal); }
.dialog-box { background: var(--color-bg-container); border-radius: var(--radius-2xl); padding: 28px; width: 440px; border: 1px solid rgba(var(--color-white-rgb), 0.1); }
.dialog-title { font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold); color: var(--color-white); margin-bottom: var(--spacing-xl); }
.form-group { margin-bottom: var(--spacing-lg); }
.form-group label { display: block; font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-bottom: var(--spacing-xs); }
.form-input { width: 100%; padding: var(--spacing-sm-md) var(--spacing-md-lg); background: rgba(var(--color-bg-base-rgb), 0.5); border: 1px solid rgba(var(--color-white-rgb), 0.1); border-radius: var(--radius-lg); color: var(--color-white); font-size: var(--font-size-base); font-family: inherit; resize: vertical; }
.form-input:focus { outline: none; border-color: var(--color-primary); }
.dialog-actions { display: flex; justify-content: flex-end; gap: var(--spacing-sm); margin-top: var(--spacing-xl); }
.btn-sm { padding: var(--spacing-sm) var(--spacing-lg); background: rgba(var(--color-text-quaternary-rgb), 0.2); color: var(--color-text-tertiary); border: 1px solid rgba(var(--color-text-quaternary-rgb), 0.3); border-radius: var(--radius-lg); font-size: var(--font-size-sm); cursor: pointer; }
</style>
