<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface FailedIntent {
  id: string
  intent: string
  agent: string
  errorType: string
  errorMessage: string
  timestamp: string
  retryCount: number
  rootCause: string
  status: 'pending' | 'analyzing' | 'resolved'
}

const loading = ref(false)
const failedIntents = ref<FailedIntent[]>([
  { id: 'FI-001', intent: '重启核心交换机SW-CORE-01', agent: '网络运维Agent', errorType: '权限不足', errorMessage: 'Agent缺少设备写操作权限', timestamp: '2026-06-13 10:23', retryCount: 0, rootCause: 'RBAC策略未授权该Agent执行重启操作', status: 'pending' },
  { id: 'FI-002', intent: '批量更新防火墙规则', agent: '安全Agent', errorType: '超时', errorMessage: '目标设备响应超时(>30s)', timestamp: '2026-06-13 09:45', retryCount: 3, rootCause: '防火墙API负载过高，连接池耗尽', status: 'analyzing' },
  { id: 'FI-003', intent: '生成月度SLA报告', agent: '报告Agent', errorType: '数据缺失', errorMessage: '缺少6月5日-6月7日监控数据', timestamp: '2026-06-13 08:00', retryCount: 1, rootCause: '监控服务在6月5日维护期间数据采集中断', status: 'resolved' },
  { id: 'FI-004', intent: '配置BGP邻居关系', agent: '网络运维Agent', errorType: '参数错误', errorMessage: 'ASN参数格式不合法: "AS65001"', timestamp: '2026-06-12 22:15', retryCount: 0, rootCause: '意图解析阶段未正确提取ASN数值', status: 'pending' },
  { id: 'FI-005', intent: '扩容VPN隧道带宽', agent: '网络运维Agent', errorType: '依赖失败', errorMessage: '下游计费系统返回500', timestamp: '2026-06-12 18:30', retryCount: 2, rootCause: '计费系统API版本升级未通知，接口不兼容', status: 'analyzing' }
])

const filterStatus = ref('all')
const showDetailDialog = ref(false)
const selectedIntent = ref<FailedIntent | null>(null)

const filteredIntents = ref(failedIntents.value)

function filterIntents() {
  if (filterStatus.value === 'all') {
    filteredIntents.value = failedIntents.value
  } else {
    filteredIntents.value = failedIntents.value.filter(i => i.status === filterStatus.value)
  }
}

function getStatusLabel(s: string) {
  return s === 'pending' ? '待处理' : s === 'analyzing' ? '分析中' : '已解决'
}

function getErrorTypeClass(e: string) {
  const map: Record<string, string> = { '权限不足': 'error-permission', '超时': 'error-timeout', '数据缺失': 'error-data-missing', '参数错误': 'error-param', '依赖失败': 'error-dependency' }
  return map[e] || 'error-default'
}

function viewDetail(intent: FailedIntent) {
  selectedIntent.value = intent
  showDetailDialog.value = true
}

function retryIntent(intent: FailedIntent) {
  intent.retryCount++
  intent.status = 'analyzing'
  filterIntents()
}

function resolveIntent(intent: FailedIntent) {
  intent.status = 'resolved'
  filterIntents()
}

onMounted(() => {
  // TODO: 调用API获取失败意图列表
})
</script>

<template>
  <div class="failed-intents">
    <h1 class="page-title">失败意图</h1>

    <div class="toolbar">
      <div class="stats-row">
        <div class="stat-chip pending">待处理 {{ failedIntents.filter(i => i.status === 'pending').length }}</div>
        <div class="stat-chip analyzing">分析中 {{ failedIntents.filter(i => i.status === 'analyzing').length }}</div>
        <div class="stat-chip resolved">已解决 {{ failedIntents.filter(i => i.status === 'resolved').length }}</div>
      </div>
      <div class="filter-group">
        <button :class="['filter-btn', { active: filterStatus === 'all' }]" @click="filterStatus = 'all'; filterIntents()">全部</button>
        <button :class="['filter-btn', { active: filterStatus === 'pending' }]" @click="filterStatus = 'pending'; filterIntents()">待处理</button>
        <button :class="['filter-btn', { active: filterStatus === 'analyzing' }]" @click="filterStatus = 'analyzing'; filterIntents()">分析中</button>
        <button :class="['filter-btn', { active: filterStatus === 'resolved' }]" @click="filterStatus = 'resolved'; filterIntents()">已解决</button>
      </div>
    </div>

    <div class="intent-list">
      <div v-for="item in filteredIntents" :key="item.id" class="intent-card">
        <div class="card-header">
          <span class="intent-id">{{ item.id }}</span>
          <span :class="['status-badge', item.status]">{{ getStatusLabel(item.status) }}</span>
        </div>
        <div class="card-body">
          <div class="intent-text">{{ item.intent }}</div>
          <div class="meta-row">
            <span class="meta-item">Agent: {{ item.agent }}</span>
            <span class="meta-item">时间: {{ item.timestamp }}</span>
            <span class="meta-item">重试: {{ item.retryCount }}次</span>
          </div>
          <div class="error-row">
            <span class="error-type" :class="getErrorTypeClass(item.errorType)">{{ item.errorType }}</span>
            <span class="error-msg">{{ item.errorMessage }}</span>
          </div>
          <div class="root-cause">
            <span class="cause-label">根因:</span>
            <span class="cause-text">{{ item.rootCause }}</span>
          </div>
        </div>
        <div class="card-actions">
          <button class="btn-sm" @click="viewDetail(item)">详情</button>
          <button v-if="item.status !== 'resolved'" class="btn-sm retry" @click="retryIntent(item)">重试</button>
          <button v-if="item.status === 'analyzing'" class="btn-sm resolve" @click="resolveIntent(item)">标记解决</button>
        </div>
      </div>
    </div>

    <div v-if="showDetailDialog && selectedIntent" class="dialog-overlay" @click.self="showDetailDialog = false">
      <div class="dialog-box">
        <h3 class="dialog-title">失败意图详情</h3>
        <div class="detail-grid">
          <div class="detail-item"><span class="label">ID</span><span>{{ selectedIntent.id }}</span></div>
          <div class="detail-item"><span class="label">意图</span><span>{{ selectedIntent.intent }}</span></div>
          <div class="detail-item"><span class="label">Agent</span><span>{{ selectedIntent.agent }}</span></div>
          <div class="detail-item"><span class="label">错误类型</span><span class="error-type" :class="getErrorTypeClass(selectedIntent.errorType)">{{ selectedIntent.errorType }}</span></div>
          <div class="detail-item"><span class="label">错误信息</span><span>{{ selectedIntent.errorMessage }}</span></div>
          <div class="detail-item"><span class="label">发生时间</span><span>{{ selectedIntent.timestamp }}</span></div>
          <div class="detail-item"><span class="label">重试次数</span><span>{{ selectedIntent.retryCount }}</span></div>
          <div class="detail-item full"><span class="label">根因分析</span><span>{{ selectedIntent.rootCause }}</span></div>
        </div>
        <div class="dialog-actions">
          <button class="btn-sm" @click="showDetailDialog = false">关闭</button>
          <button v-if="selectedIntent.status !== 'resolved'" class="action-btn" @click="retryIntent(selectedIntent); showDetailDialog = false">重试</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); color: var(--color-white); margin-bottom: var(--spacing-2xl); }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-2xl); flex-wrap: wrap; gap: var(--spacing-md); }
.stats-row { display: flex; gap: var(--spacing-md); }
.stat-chip { font-size: var(--font-size-sm); padding: var(--spacing-xs) var(--spacing-md-lg); border-radius: var(--radius-full); font-weight: var(--font-weight-medium); }
.stat-chip.pending { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); }
.stat-chip.analyzing { background: rgba(var(--color-warning-rgb), 0.2); color: var(--color-warning); }
.stat-chip.resolved { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); }

.filter-group { display: flex; gap: var(--spacing-xs); }
.filter-btn { padding: var(--spacing-xs) var(--spacing-md-lg); background: rgba(var(--color-bg-elevated-rgb), 0.6); color: var(--color-text-tertiary); border: 1px solid rgba(var(--color-white-rgb), 0.1); border-radius: var(--radius-lg); font-size: var(--font-size-sm); cursor: pointer; }
.filter-btn.active { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); border-color: rgba(var(--color-primary-rgb), 0.4); }

.intent-list { display: flex; flex-direction: column; gap: var(--spacing-md); }
.intent-card { background: rgba(var(--color-bg-elevated-rgb), 0.6); border-radius: var(--radius-xl); border: 1px solid rgba(var(--color-white-rgb), 0.1); padding: 18px var(--spacing-xl); transition: border-color 0.2s; }
.intent-card:hover { border-color: rgba(var(--color-primary-rgb), 0.3); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-sm-md); }
.intent-id { font-size: var(--font-size-sm); color: var(--color-text-quaternary); font-family: monospace; }
.status-badge { font-size: var(--font-size-xs); padding: var(--spacing-3xs) var(--spacing-sm-md); border-radius: var(--radius-lg); font-weight: var(--font-weight-medium); }
.status-badge.pending { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); }
.status-badge.analyzing { background: rgba(var(--color-warning-rgb), 0.2); color: var(--color-warning); }
.status-badge.resolved { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); }

.intent-text { font-size: var(--font-size-md); color: var(--color-white); font-weight: var(--font-weight-medium); margin-bottom: var(--spacing-sm); }
.meta-row { display: flex; gap: var(--spacing-lg); margin-bottom: var(--spacing-sm); }
.meta-item { font-size: var(--font-size-sm); color: var(--color-text-quaternary); }
.error-row { display: flex; align-items: center; gap: var(--spacing-sm); margin-bottom: var(--spacing-sm); }
.error-type { font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold); padding: var(--spacing-3xs) var(--spacing-sm); border-radius: var(--spacing-2xs); background: rgba(var(--color-white-rgb), 0.05); }
.error-type.error-permission { color: var(--color-error); }
.error-type.error-timeout { color: var(--color-warning); }
.error-type.error-data-missing { color: var(--color-info-light); }
.error-type.error-param { color: var(--color-orange); }
.error-type.error-dependency { color: var(--color-purple); }
.error-type.error-default { color: var(--color-text-tertiary); }
.error-msg { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.root-cause { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.cause-label { color: var(--color-text-quaternary); margin-right: var(--spacing-2xs); }
.cause-text { color: var(--color-text-secondary); }

.card-actions { display: flex; gap: var(--spacing-xs); margin-top: var(--spacing-md); padding-top: var(--spacing-md); border-top: 1px solid rgba(var(--color-white-rgb), 0.05); }
.btn-sm { padding: var(--spacing-3xs) var(--spacing-md); background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); border: 1px solid rgba(var(--color-primary-rgb), 0.3); border-radius: var(--radius-md); font-size: var(--font-size-sm); cursor: pointer; }
.btn-sm.retry { background: rgba(var(--color-warning-rgb), 0.2); color: var(--color-warning); border-color: rgba(var(--color-warning-rgb), 0.3); }
.btn-sm.resolve { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); border-color: rgba(var(--color-success-rgb), 0.3); }

.action-btn { padding: var(--spacing-sm-md) var(--spacing-xl); background: var(--gradient-primary); color: var(--color-white); border: none; border-radius: var(--radius-lg); font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); cursor: pointer; }

.dialog-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; justify-content: center; z-index: var(--z-modal); }
.dialog-box { background: var(--color-bg-container); border-radius: var(--radius-2xl); padding: 28px; width: 520px; border: 1px solid rgba(var(--color-white-rgb), 0.1); }
.dialog-title { font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold); color: var(--color-white); margin-bottom: var(--spacing-xl); }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-md); }
.detail-item { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
.detail-item.full { grid-column: 1 / -1; }
.detail-item .label { display: block; font-size: var(--font-size-xs); color: var(--color-text-quaternary); margin-bottom: var(--spacing-3xs); text-transform: uppercase; letter-spacing: 0.5px; }
.dialog-actions { display: flex; justify-content: flex-end; gap: var(--spacing-sm); margin-top: var(--spacing-xl); }
</style>
