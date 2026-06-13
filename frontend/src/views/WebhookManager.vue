<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface WebhookSubscription {
  id: string
  name: string
  url: string
  events: string[]
  status: 'active' | 'inactive' | 'error'
  lastTriggered: string
  successRate: number
  createdAt: string
}

const loading = ref(false)
const subscriptions = ref<WebhookSubscription[]>([
  { id: 'WH-001', name: '告警通知', url: 'https://hooks.example.com/alert', events: ['device.alert', 'sla.warning'], status: 'active', lastTriggered: '5分钟前', successRate: 99.2, createdAt: '2026-05-01' },
  { id: 'WH-002', name: '工单同步', url: 'https://api.example.com/sync', events: ['workorder.created', 'workorder.updated'], status: 'active', lastTriggered: '30分钟前', successRate: 98.5, createdAt: '2026-04-15' },
  { id: 'WH-003', name: '自愈事件', url: 'https://hooks.example.com/healing', events: ['healing.started', 'healing.completed'], status: 'error', lastTriggered: '1小时前', successRate: 85.3, createdAt: '2026-03-20' }
])

const showCreateDialog = ref(false)
const newSubscription = ref({ name: '', url: '', events: [] as string[] })

const eventTypes = [
  { category: '设备事件', events: ['device.alert', 'device.offline', 'device.config_change'] },
  { category: '工单事件', events: ['workorder.created', 'workorder.updated', 'workorder.resolved'] },
  { category: '自愈事件', events: ['healing.started', 'healing.completed', 'healing.failed'] },
  { category: 'SLA事件', events: ['sla.warning', 'sla.breach', 'sla.recovered'] }
]

function toggleEvent(event: string) {
  const idx = newSubscription.value.events.indexOf(event)
  if (idx >= 0) newSubscription.value.events.splice(idx, 1)
  else newSubscription.value.events.push(event)
}

function createSubscription() {
  if (!newSubscription.value.name.trim() || !newSubscription.value.url.trim()) return
  subscriptions.value.unshift({
    id: `WH-${String(subscriptions.value.length + 1).padStart(3, '0')}`,
    name: newSubscription.value.name,
    url: newSubscription.value.url,
    events: [...newSubscription.value.events],
    status: 'active',
    lastTriggered: '从未触发',
    successRate: 100,
    createdAt: new Date().toISOString().slice(0, 10)
  })
  newSubscription.value = { name: '', url: '', events: [] }
  showCreateDialog.value = false
}

function testWebhook(wh: WebhookSubscription) {
  alert(`测试Webhook: ${wh.name} → ${wh.url}`)
}

onMounted(() => {
  // TODO: 调用API获取Webhook列表
})
</script>

<template>
  <div class="webhook-manager">
    <h1 class="page-title">Webhook管理</h1>

    <div class="toolbar">
      <div class="stats-row">
        <div class="stat-chip active">活跃 {{ subscriptions.filter(s => s.status === 'active').length }}</div>
        <div class="stat-chip error">异常 {{ subscriptions.filter(s => s.status === 'error').length }}</div>
      </div>
      <button class="action-btn" @click="showCreateDialog = true">+ 创建订阅</button>
    </div>

    <div class="webhook-list">
      <div v-for="wh in subscriptions" :key="wh.id" class="webhook-card">
        <div class="wh-header">
          <div class="wh-name">{{ wh.name }}</div>
          <span :class="['status-tag', wh.status]">{{ wh.status === 'active' ? '活跃' : wh.status === 'inactive' ? '停用' : '异常' }}</span>
        </div>
        <div class="wh-url">{{ wh.url }}</div>
        <div class="wh-events">
          <span v-for="event in wh.events" :key="event" class="event-tag">{{ event }}</span>
        </div>
        <div class="wh-footer">
          <span class="wh-meta">最近触发: {{ wh.lastTriggered }}</span>
          <span class="wh-meta">成功率: <span :class="wh.successRate >= 95 ? 'rate-success' : 'rate-fail'">{{ wh.successRate }}%</span></span>
          <span class="wh-meta">创建: {{ wh.createdAt }}</span>
        </div>
        <div class="wh-actions">
          <button class="btn-sm primary" @click="testWebhook(wh)">测试</button>
          <button class="btn-sm">编辑</button>
          <button class="btn-sm danger">删除</button>
        </div>
      </div>
    </div>

    <div v-if="showCreateDialog" class="dialog-overlay" @click.self="showCreateDialog = false">
      <div class="dialog-box">
        <h3 class="dialog-title">创建Webhook订阅</h3>
        <div class="form-group">
          <label>订阅名称</label>
          <input v-model="newSubscription.name" class="form-input" placeholder="输入订阅名称" />
        </div>
        <div class="form-group">
          <label>回调URL</label>
          <input v-model="newSubscription.url" class="form-input" placeholder="https://example.com/webhook" />
        </div>
        <div class="form-group">
          <label>事件类型</label>
          <div class="event-groups">
            <div v-for="group in eventTypes" :key="group.category" class="event-group">
              <div class="group-label">{{ group.category }}</div>
              <div class="group-events">
                <span
                  v-for="event in group.events"
                  :key="event"
                  :class="['event-chip', { selected: newSubscription.events.includes(event) }]"
                  @click="toggleEvent(event)"
                >{{ event }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="dialog-actions">
          <button class="btn-sm" @click="showCreateDialog = false">取消</button>
          <button class="action-btn" @click="createSubscription">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); color: var(--color-white); margin-bottom: var(--spacing-2xl); }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-2xl); }
.stats-row { display: flex; gap: var(--spacing-md); }
.stat-chip { font-size: var(--font-size-sm); padding: var(--spacing-xs) var(--spacing-md-lg); border-radius: var(--radius-full); font-weight: var(--font-weight-medium); }
.stat-chip.active { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); }
.stat-chip.error { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); }

.action-btn { padding: var(--spacing-sm-md) var(--spacing-xl); background: var(--gradient-primary); color: var(--color-white); border: none; border-radius: var(--radius-lg); font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); cursor: pointer; }
.action-btn:hover { transform: translateY(-1px); box-shadow: 0 var(--spacing-xs) var(--spacing-md) rgba(var(--color-primary-rgb), 0.4); }

.webhook-list { display: flex; flex-direction: column; gap: var(--spacing-md); }

.webhook-card { background: rgba(var(--color-bg-elevated-rgb), 0.6); border-radius: var(--radius-xl); padding: 18px var(--spacing-xl); border: 1px solid rgba(var(--color-white-rgb), 0.1); }
.wh-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-sm); }
.wh-name { font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--color-white); }
.status-tag { font-size: var(--font-size-xs); padding: 3px var(--spacing-sm); border-radius: var(--radius-full); font-weight: var(--font-weight-medium); }
.status-tag.active { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); }
.status-tag.inactive { background: rgba(var(--color-text-quaternary-rgb), 0.2); color: var(--color-text-tertiary); }
.status-tag.error { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); }

.wh-url { font-size: var(--font-size-sm); color: var(--color-info-light); font-family: monospace; margin-bottom: var(--spacing-sm-md); word-break: break-all; }
.wh-events { display: flex; flex-wrap: wrap; gap: var(--spacing-xs); margin-bottom: var(--spacing-md); }
.event-tag { font-size: var(--font-size-xs); padding: var(--spacing-2xs) var(--spacing-sm); border-radius: var(--radius-md); background: rgba(var(--color-primary-rgb), 0.15); color: var(--color-info-light); }
.wh-footer { display: flex; gap: var(--spacing-xl); margin-bottom: var(--spacing-md); }
.wh-meta { font-size: var(--font-size-sm); color: var(--color-text-quaternary); }
.rate-success { color: var(--color-success); }
.rate-fail { color: var(--color-error); }
.wh-actions { display: flex; gap: var(--spacing-sm); }
.btn-sm { padding: 5px var(--spacing-md); background: rgba(var(--color-text-quaternary-rgb), 0.2); color: var(--color-text-tertiary); border: 1px solid rgba(var(--color-text-quaternary-rgb), 0.3); border-radius: var(--radius-md); font-size: var(--font-size-sm); cursor: pointer; }
.btn-sm.primary { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); border-color: rgba(var(--color-primary-rgb), 0.3); }
.btn-sm.danger { background: rgba(var(--color-error-rgb), 0.15); color: var(--color-error); border-color: rgba(var(--color-error-rgb), 0.3); }

.dialog-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; justify-content: center; z-index: var(--z-modal); }
.dialog-box { background: var(--color-bg-container); border-radius: var(--radius-2xl); padding: 28px; width: 520px; max-height: 80vh; overflow-y: auto; border: 1px solid rgba(var(--color-white-rgb), 0.1); }
.dialog-title { font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold); color: var(--color-white); margin-bottom: var(--spacing-xl); }
.form-group { margin-bottom: var(--spacing-lg); }
.form-group label { display: block; font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-bottom: var(--spacing-xs); }
.form-input { width: 100%; padding: var(--spacing-sm-md) var(--spacing-md-lg); background: rgba(var(--color-bg-base-rgb), 0.5); border: 1px solid rgba(var(--color-white-rgb), 0.1); border-radius: var(--radius-lg); color: var(--color-white); font-size: var(--font-size-base); }
.form-input:focus { outline: none; border-color: var(--color-primary); }

.event-groups { display: flex; flex-direction: column; gap: var(--spacing-md); }
.event-group { }
.group-label { font-size: var(--font-size-sm); color: var(--color-text-quaternary); margin-bottom: var(--spacing-xs); }
.group-events { display: flex; flex-wrap: wrap; gap: var(--spacing-xs); }
.event-chip { font-size: var(--font-size-xs); padding: var(--spacing-2xs) var(--spacing-sm); border-radius: var(--radius-md); background: rgba(var(--color-bg-elevated-rgb), 0.6); color: var(--color-text-tertiary); cursor: pointer; border: 1px solid rgba(var(--color-white-rgb), 0.1); transition: all 0.2s; }
.event-chip.selected { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); border-color: rgba(var(--color-primary-rgb), 0.3); }

.dialog-actions { display: flex; justify-content: flex-end; gap: var(--spacing-sm); margin-top: var(--spacing-xl); }
</style>
