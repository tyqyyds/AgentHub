<template>
  <div class="audit-logs-page">
    <div class="page-header">
      <h1>审计日志</h1>
      <div class="header-actions">
        <button class="btn btn-outline" @click="handleExport('json')">导出 JSON</button>
        <button class="btn btn-outline" @click="handleExport('csv')">导出 CSV</button>
        <button class="btn btn-primary" @click="refreshLogs">刷新</button>
      </div>
    </div>

    <div class="stats-bar">
      <div class="stat-card">
        <span class="stat-value">{{ stats.total }}</span>
        <span class="stat-label">总记录</span>
      </div>
      <div class="stat-card critical">
        <span class="stat-value">{{ stats.critical }}</span>
        <span class="stat-label">严重</span>
      </div>
      <div class="stat-card warning">
        <span class="stat-value">{{ stats.warning }}</span>
        <span class="stat-label">警告</span>
      </div>
      <div class="stat-card success">
        <span class="stat-value">{{ stats.success }}</span>
        <span class="stat-label">成功</span>
      </div>
      <div class="stat-card failed">
        <span class="stat-value">{{ stats.failed }}</span>
        <span class="stat-label">失败</span>
      </div>
    </div>

    <div class="filters">
      <input v-model="filters.search" type="text" placeholder="搜索关键词..." class="filter-input" @input="debouncedSearch" />
      <select v-model="filters.action" class="filter-select" @change="loadLogs">
        <option value="">全部操作</option>
        <option value="create_intent">提交意图</option>
        <option value="approve_intent">审批意图</option>
        <option value="approve_intent_with_conflict_check">审批意图(冲突检查)</option>
        <option value="reject_intent">拒绝意图</option>
        <option value="execute_intent">执行意图</option>
        <option value="rollback_intent">回滚意图</option>
        <option value="config_deploy">配置下发</option>
        <option value="config_rollback">配置回滚</option>
        <option value="self_healing">自愈执行</option>
        <option value="security_alert">安全告警</option>
      </select>
      <select v-model="filters.status" class="filter-select" @change="loadLogs">
        <option value="">全部状态</option>
        <option value="success">成功</option>
        <option value="pending">待处理</option>
        <option value="failed">失败</option>
        <option value="running">运行中</option>
      </select>
      <select v-model="filters.securityLevel" class="filter-select" @change="loadLogs">
        <option value="">全部级别</option>
        <option value="critical">严重</option>
        <option value="warning">警告</option>
        <option value="info">信息</option>
      </select>
    </div>

    <div class="logs-table-wrapper">
      <table class="logs-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>时间</th>
            <th>用户</th>
            <th>操作</th>
            <th>目标设备</th>
            <th>状态</th>
            <th>安全级别</th>
            <th>详情</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="8" class="loading-cell">加载中...</td>
          </tr>
          <tr v-else-if="logs.length === 0">
            <td colspan="8" class="empty-cell">暂无审计日志</td>
          </tr>
          <tr v-for="log in logs" :key="log.id" class="log-row" :class="{ 'row-critical': log.securityLevel === 'critical', 'row-warning': log.securityLevel === 'warning' }">
            <td class="cell-id">{{ log.id }}</td>
            <td class="cell-time">{{ log.timestamp }}</td>
            <td class="cell-user">{{ log.user }}</td>
            <td class="cell-action">
              <span class="action-badge">{{ log.actionLabel }}</span>
            </td>
            <td class="cell-target">{{ log.targetDevice }}</td>
            <td class="cell-status">
              <span class="status-badge" :class="'status-' + log.status">{{ statusLabels[log.status] || log.status }}</span>
            </td>
            <td class="cell-level">
              <span class="level-badge" :class="'level-' + (log.securityLevel || 'info')">{{ levelLabels[log.securityLevel || 'info'] }}</span>
            </td>
            <td class="cell-detail">
              <button class="btn-detail" @click="showDetail(log)">查看</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pagination">
      <button class="btn btn-outline" :disabled="currentPage <= 1" @click="goToPage(currentPage - 1)">上一页</button>
      <span class="page-info">第 {{ currentPage }} 页 / 共 {{ totalPages }} 页 ({{ totalRecords }} 条)</span>
      <button class="btn btn-outline" :disabled="currentPage >= totalPages" @click="goToPage(currentPage + 1)">下一页</button>
    </div>

    <div v-if="selectedLog" class="modal-overlay" @click.self="selectedLog = null">
      <div class="modal-content">
        <div class="modal-header">
          <h3>审计日志详情</h3>
          <button class="modal-close" @click="selectedLog = null">&times;</button>
        </div>
        <div class="modal-body">
          <div class="detail-grid">
            <div class="detail-item"><span class="detail-label">ID</span><span class="detail-value">{{ selectedLog.id }}</span></div>
            <div class="detail-item"><span class="detail-label">时间</span><span class="detail-value">{{ selectedLog.timestamp }}</span></div>
            <div class="detail-item"><span class="detail-label">用户</span><span class="detail-value">{{ selectedLog.user }}</span></div>
            <div class="detail-item"><span class="detail-label">操作</span><span class="detail-value">{{ selectedLog.actionLabel }}</span></div>
            <div class="detail-item"><span class="detail-label">目标设备</span><span class="detail-value">{{ selectedLog.targetDevice }}</span></div>
            <div class="detail-item"><span class="detail-label">状态</span><span class="detail-value">{{ statusLabels[selectedLog.status] || selectedLog.status }}</span></div>
            <div class="detail-item"><span class="detail-label">安全级别</span><span class="detail-value">{{ levelLabels[selectedLog.securityLevel || 'info'] }}</span></div>
            <div v-if="selectedLog.approvalId" class="detail-item"><span class="detail-label">审批ID</span><span class="detail-value">{{ selectedLog.approvalId }}</span></div>
          </div>
          <div v-if="selectedLog.context?.intentText" class="detail-section">
            <h4>意图内容</h4>
            <pre class="detail-pre">{{ selectedLog.context.intentText }}</pre>
          </div>
          <div v-if="selectedLog.commands?.length" class="detail-section">
            <h4>执行命令</h4>
            <pre class="detail-pre">{{ selectedLog.commands.join('\n') }}</pre>
          </div>
          <div v-if="selectedLog.context?.modelResponse" class="detail-section">
            <h4>模型响应</h4>
            <pre class="detail-pre">{{ selectedLog.context.modelResponse }}</pre>
          </div>
          <div v-if="selectedLog.context?.tokens" class="detail-section">
            <h4>Token 使用</h4>
            <p>Prompt: {{ selectedLog.context.tokens.prompt }}, Completion: {{ selectedLog.context.tokens.completion }}, Total: {{ selectedLog.context.tokens.total }}</p>
          </div>
          <div v-if="selectedLog.context?.latency_ms" class="detail-section">
            <h4>延迟</h4>
            <p>{{ selectedLog.context.latency_ms }} ms</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { auditLogService, type AuditLog } from '@/utils/auditLogService'

const logs = ref<AuditLog[]>([])
const loading = ref(false)
const currentPage = ref(1)
const totalRecords = ref(0)
const pageSize = 20
const selectedLog = ref<AuditLog | null>(null)

const stats = ref({ total: 0, critical: 0, warning: 0, success: 0, failed: 0 })

const filters = ref({
  search: '',
  action: '',
  status: '',
  securityLevel: '',
})

const statusLabels: Record<string, string> = { success: '成功', pending: '待处理', failed: '失败', running: '运行中' }
const levelLabels: Record<string, string> = { info: '信息', warning: '警告', critical: '严重' }

const totalPages = computed(() => Math.max(1, Math.ceil(totalRecords.value / pageSize)))

let searchTimer: ReturnType<typeof setTimeout> | null = null
let abortController: AbortController | null = null

function debouncedSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { currentPage.value = 1; loadLogs() }, 300)
}

async function loadLogs() {
  loading.value = true
  try {
    abortController?.abort()
    abortController = new AbortController()
    const result = await auditLogService.getLogsPaginated(currentPage.value, pageSize, {
      action: filters.value.action || undefined,
      status: filters.value.status || undefined,
      securityLevel: filters.value.securityLevel || undefined,
    }, abortController.signal)

    if (filters.value.search) {
      const q = filters.value.search.toLowerCase()
      logs.value = result.data.filter(l =>
        l.context.intentText.toLowerCase().includes(q) ||
        l.user.toLowerCase().includes(q) ||
        l.targetDevice.toLowerCase().includes(q)
      )
    } else {
      logs.value = result.data
    }
    totalRecords.value = result.total
  } catch {
    // aborted
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    stats.value = await auditLogService.getStats()
  } catch {
    // ignore
  }
}

function refreshLogs() {
  loadLogs()
  loadStats()
}

function goToPage(page: number) {
  currentPage.value = page
  loadLogs()
}

function showDetail(log: AuditLog) {
  selectedLog.value = log
}

async function handleExport(format: 'json' | 'csv') {
  await auditLogService.exportLogs(format, {
    action: filters.value.action || undefined,
    status: filters.value.status || undefined,
    securityLevel: filters.value.securityLevel || undefined,
  })
}

onMounted(() => {
  loadLogs()
  loadStats()
})

onUnmounted(() => {
  abortController?.abort()
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<style scoped>
.audit-logs-page {
  padding: var(--content-padding);
  max-width: 1400px;
  margin: 0 auto;
  will-change: transform, opacity;
  animation: page-enter 0.4s var(--ease-out);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
}

.page-header h1 {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  background: linear-gradient(135deg, var(--color-primary-light) 0%, var(--color-primary) 50%, var(--color-primary-light) 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: title-shimmer 3s linear infinite;
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.stats-bar {
  display: flex;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.stat-card {
  flex: 1;
  background: var(--gradient-glass);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  text-align: center;
  border: var(--card-border);
  border-left: 4px solid var(--color-primary);
  backdrop-filter: blur(12px);
  box-shadow: var(--shadow-card);
  transition: all 0.25s var(--ease-out);
}

.stat-card:hover {
  transform: translateY(-2px);
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-glow-primary);
}

.stat-card.critical { border-left-color: var(--color-error); }
.stat-card.warning { border-left-color: var(--color-warning); }
.stat-card.success { border-left-color: var(--color-success); }
.stat-card.failed { border-left-color: var(--color-error); }

.stat-value {
  display: block;
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
}

.stat-label {
  display: block;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-top: var(--spacing-xs);
}

.filters {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-lg);
  flex-wrap: wrap;
}

.filter-input, .filter-select {
  padding: var(--input-padding);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  font-size: var(--font-size-base);
  background: var(--input-bg);
  color: var(--color-text-secondary);
  transition: all 0.25s var(--ease-out);
  outline: none;
}

.filter-input:focus, .filter-select:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
}

.filter-input { flex: 1; min-width: 200px; }
.filter-select { min-width: 140px; }

.logs-table-wrapper {
  overflow-x: auto;
  border-radius: var(--radius-md);
  border: var(--card-border);
  background: var(--gradient-glass);
  backdrop-filter: blur(12px);
}

.logs-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-base);
}

.logs-table th {
  background: var(--color-bg-glass-strong);
  padding: var(--spacing-sm) var(--spacing-md);
  text-align: left;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-tertiary);
  border-bottom: 1px solid var(--color-border-primary);
  white-space: nowrap;
}

.logs-table td {
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-border-primary);
  color: var(--color-text-secondary);
}

.log-row:hover { background: var(--color-bg-hover); }
.log-row.row-critical { background: var(--color-error-bg); }
.log-row.row-warning { background: var(--color-warning-bg); }

.loading-cell, .empty-cell {
  text-align: center;
  padding: var(--spacing-xl) !important;
  color: var(--color-text-tertiary);
}

.action-badge {
  background: var(--color-bg-glass);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-xs);
  font-size: var(--font-size-xs);
}

.status-badge {
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-xs);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.status-success { background: var(--color-success-bg); color: var(--color-success); }
.status-pending { background: var(--color-warning-bg); color: var(--color-warning); }
.status-failed { background: var(--color-error-bg); color: var(--color-error); }
.status-running { background: var(--color-primary-bg); color: var(--color-primary); }

.level-badge {
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-xs);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.level-info { background: var(--color-primary-bg); color: var(--color-primary); }
.level-warning { background: var(--color-warning-bg); color: var(--color-warning); }
.level-critical { background: var(--color-error-bg); color: var(--color-error); }

.btn-detail {
  padding: var(--spacing-xs) var(--spacing-sm);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-sm);
  background: var(--color-primary-bg);
  color: var(--color-primary);
  cursor: pointer;
  font-size: var(--font-size-xs);
  transition: var(--button-transition);
}

.btn-detail:hover {
  background: var(--color-primary-hover);
  border-color: var(--color-primary);
  transform: translateY(-1px);
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--spacing-md);
  margin-top: var(--spacing-lg);
}

.page-info { font-size: var(--font-size-base); color: var(--color-text-tertiary); }

.btn {
  padding: var(--button-padding-y) var(--button-padding-x);
  border-radius: var(--button-radius);
  font-size: var(--button-font-size);
  cursor: pointer;
  border: 1px solid var(--color-border-primary);
  transition: var(--button-transition);
}

.btn-primary {
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  border-color: var(--color-primary);
}

.btn-primary:hover { box-shadow: var(--shadow-glow-primary); transform: translateY(-1px); }

.btn-outline {
  background: transparent;
  color: var(--color-text-secondary);
}

.btn-outline:hover { background: var(--color-bg-hover); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: var(--modal-overlay-bg);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: var(--z-overlay);
  backdrop-filter: blur(var(--modal-backdrop-blur));
  animation: modal-overlay-in 0.2s var(--ease-out);
}

.modal-content {
  background: var(--color-bg-elevated);
  border-radius: var(--modal-border-radius);
  width: 90%;
  max-width: 700px;
  max-height: 80vh;
  overflow-y: auto;
  border: 1px solid var(--color-border-primary);
  box-shadow: var(--shadow-modal);
  animation: modal-content-in 0.25s var(--ease-out);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border-primary);
}

.modal-header h3 { font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--color-text-primary); }

.modal-close {
  background: none;
  border: none;
  font-size: var(--font-size-2xl);
  cursor: pointer;
  color: var(--color-text-tertiary);
  transition: color 0.2s ease;
}

.modal-close:hover { color: var(--color-text-primary); }

.modal-body { padding: var(--spacing-lg); }

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.detail-label {
  font-size: var(--font-size-xs);
  color: var(--color-form-label);
  font-weight: var(--font-weight-medium);
}

.detail-value { font-size: var(--font-size-base); color: var(--color-text-secondary); }

.detail-section { margin-top: var(--spacing-md); }
.detail-section h4 { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); margin-bottom: var(--spacing-sm); color: var(--color-text-primary); }

.detail-pre {
  background: var(--input-bg);
  padding: var(--spacing-sm);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid var(--color-border-primary);
  color: var(--color-text-tertiary);
}

@media (max-width: 768px) {
  .audit-logs-page { padding: var(--spacing-md); }
  .page-header { flex-direction: column; gap: var(--spacing-sm); align-items: flex-start; }
  .page-header h1 { font-size: var(--font-size-xl); }
  .stats-bar { flex-wrap: wrap; }
  .stat-card { min-width: calc(50% - var(--spacing-sm)); }
  .detail-grid { grid-template-columns: 1fr; }
}

@media (prefers-reduced-motion: reduce) {
  .audit-logs-page { animation: none !important; }
  .page-header h1 { animation: none; background: none; -webkit-text-fill-color: var(--color-text-primary); }
}
</style>
