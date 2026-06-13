<script setup lang="ts">
import { ref } from 'vue'

const searchQuery = ref('')
const filterType = ref('all')
const filterStatus = ref('all')

const auditLogs = ref([
  {
    id: 'AL-001',
    user: 'admin',
    action: 'intent_submit',
    actionLabel: '提交意图',
    targetDevice: 'Switch-A1',
    commands: ['class-map VIDEO_CONF', 'policy-map QOS_VIDEO'],
    timestamp: '2026-05-21 10:30:00',
    status: 'success',
    approvalId: 'APR-001'
  },
  {
    id: 'AL-002',
    user: 'admin',
    action: 'config_deploy',
    actionLabel: '配置下发',
    targetDevice: 'Router-C1',
    commands: ['interface GigabitEthernet0/0', 'ip address 192.168.1.1 255.255.255.0'],
    timestamp: '2026-05-21 10:25:00',
    status: 'success',
    approvalId: 'APR-002'
  },
  {
    id: 'AL-003',
    user: 'operator',
    action: 'intent_submit',
    actionLabel: '提交意图',
    targetDevice: 'Firewall-B1',
    commands: [],
    timestamp: '2026-05-21 10:20:00',
    status: 'pending',
    approvalId: 'APR-003'
  },
  {
    id: 'AL-004',
    user: 'admin',
    action: 'self_healing',
    actionLabel: '自愈执行',
    targetDevice: 'Switch-A2',
    commands: ['traffic-shape rate 50000000'],
    timestamp: '2026-05-21 09:45:00',
    status: 'success',
    approvalId: null
  },
  {
    id: 'AL-005',
    user: 'operator',
    action: 'config_rollback',
    actionLabel: '配置回滚',
    targetDevice: 'Switch-A1',
    commands: ['rollback configuration'],
    timestamp: '2026-05-21 09:30:00',
    status: 'success',
    approvalId: null
  }
])

const filteredLogs = ref(auditLogs.value)

const applyFilters = () => {
  filteredLogs.value = auditLogs.value.filter(log => {
    const matchesSearch = !searchQuery.value || 
      log.user.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      log.targetDevice.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      log.actionLabel.toLowerCase().includes(searchQuery.value.toLowerCase())
    
    const matchesType = filterType.value === 'all' || log.action === filterType.value
    const matchesStatus = filterStatus.value === 'all' || log.status === filterStatus.value
    
    return matchesSearch && matchesType && matchesStatus
  })
}

const actionTypes = [
  { value: 'all', label: '全部类型' },
  { value: 'intent_submit', label: '意图提交' },
  { value: 'config_deploy', label: '配置下发' },
  { value: 'self_healing', label: '自愈执行' },
  { value: 'config_rollback', label: '配置回滚' }
]

const statusOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'success', label: '成功' },
  { value: 'pending', label: '待审批' },
  { value: 'failed', label: '失败' }
]
</script>

<template>
  <div class="audit-container">
    <h1 class="page-title">审计日志</h1>
    
    <div class="filter-bar">
      <div class="search-box">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索用户、设备或操作..."
          class="search-input"
          @input="applyFilters"
        />
      </div>
      <div class="filter-selects">
        <select v-model="filterType" class="filter-select" @change="applyFilters">
          <option v-for="type in actionTypes" :key="type.value" :value="type.value">
            {{ type.label }}
          </option>
        </select>
        <select v-model="filterStatus" class="filter-select" @change="applyFilters">
          <option v-for="status in statusOptions" :key="status.value" :value="status.value">
            {{ status.label }}
          </option>
        </select>
      </div>
    </div>
    
    <div class="logs-table-container">
      <table class="logs-table">
        <thead>
          <tr>
            <th>日志ID</th>
            <th>用户</th>
            <th>操作类型</th>
            <th>目标设备</th>
            <th>命令</th>
            <th>审批ID</th>
            <th>状态</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in filteredLogs" :key="log.id">
            <td class="log-id">{{ log.id }}</td>
            <td class="log-user">{{ log.user }}</td>
            <td class="log-action">
              <span class="action-badge">{{ log.actionLabel }}</span>
            </td>
            <td class="log-device">{{ log.targetDevice }}</td>
            <td class="log-commands">
              <div v-if="log.commands.length > 0" class="commands-list">
                <span v-for="(cmd, idx) in log.commands" :key="idx" class="command-item">
                  {{ cmd }}
                </span>
              </div>
              <span v-else class="no-commands">-</span>
            </td>
            <td class="log-approval">
              <span v-if="log.approvalId" class="approval-link">{{ log.approvalId }}</span>
              <span v-else class="no-approval">-</span>
            </td>
            <td class="log-status">
              <span :class="['status-badge', log.status]">
                {{ log.status === 'success' ? '成功' : log.status === 'pending' ? '待审批' : '失败' }}
              </span>
            </td>
            <td class="log-time">{{ log.timestamp }}</td>
          </tr>
        </tbody>
      </table>
      
      <div v-if="filteredLogs.length === 0" class="empty-state">
        <span class="empty-icon">📭</span>
        <p>没有找到匹配的审计日志</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-white);
  margin-bottom: var(--spacing-2xl);
}

.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2xl);
  padding: var(--spacing-lg) var(--spacing-xl);
  background: rgba(var(--color-bg-container-rgb), 0.6);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
}

.search-box {
  flex: 1;
  max-width: 400px;
}

.search-input {
  width: 100%;
  padding: var(--spacing-md) var(--spacing-lg);
  background: rgba(var(--color-bg-base-rgb), 0.5);
  border: 2px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--spacing-sm-md);
  color: var(--color-white);
  font-size: var(--font-size-base);
  transition: all 0.3s ease;
}

.search-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 var(--spacing-sm) rgba(var(--color-primary-rgb), 0.1);
}

.search-input::placeholder {
  color: var(--color-text-quaternary);
}

.filter-selects {
  display: flex;
  gap: var(--spacing-md);
}

.filter-select {
  padding: var(--spacing-md) var(--spacing-lg);
  background: rgba(var(--color-bg-base-rgb), 0.5);
  border: 2px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--spacing-sm-md);
  color: var(--color-white);
  font-size: var(--font-size-base);
  cursor: pointer;
  transition: all 0.3s ease;
}

.filter-select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.filter-select option {
  background: var(--color-bg-container);
  color: var(--color-white);
}

.logs-table-container {
  background: rgba(var(--color-bg-container-rgb), 0.6);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  overflow-x: auto;
}

.logs-table {
  width: 100%;
  border-collapse: collapse;
}

.logs-table thead tr {
  border-bottom: 2px solid rgba(var(--color-white-rgb), 0.1);
}

.logs-table th {
  text-align: left;
  padding: var(--spacing-md-lg) var(--spacing-lg);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.logs-table tbody tr {
  border-bottom: 1px solid rgba(var(--color-white-rgb), 0.05);
  transition: background 0.2s ease;
}

.logs-table tbody tr:hover {
  background: rgba(var(--color-primary-rgb), 0.05);
}

.logs-table td {
  padding: var(--spacing-md-lg) var(--spacing-lg);
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
}

.log-id {
  font-family: monospace;
  color: var(--color-info-light);
}

.log-user {
  font-weight: var(--font-weight-medium);
}

.action-badge {
  padding: var(--spacing-2xs) var(--spacing-sm-md);
  background: rgba(var(--color-primary-rgb), 0.2);
  color: var(--color-info-light);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-sm);
}

.log-device {
  font-family: monospace;
}

.commands-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2xs);
}

.command-item {
  font-size: var(--font-size-sm);
  color: var(--color-success);
  font-family: monospace;
  padding: var(--spacing-2xs) var(--spacing-sm);
  background: rgba(var(--color-success-rgb), 0.1);
  border-radius: var(--radius-sm);
}

.no-commands {
  color: var(--color-text-quaternary);
  font-size: var(--font-size-sm);
}

.approval-link {
  font-size: var(--font-size-sm);
  color: var(--color-orange);
  text-decoration: underline;
  cursor: pointer;
}

.no-approval {
  color: var(--color-text-quaternary);
  font-size: var(--font-size-sm);
}

.status-badge {
  padding: var(--spacing-2xs) var(--spacing-md);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.status-badge.success {
  background: rgba(var(--color-success-rgb), 0.2);
  color: var(--color-success);
}

.status-badge.pending {
  background: rgba(var(--color-orange-rgb), 0.2);
  color: var(--color-orange);
}

.status-badge.failed {
  background: rgba(var(--color-error-rgb), 0.2);
  color: var(--color-error);
}

.log-time {
  font-size: var(--font-size-md);
  color: var(--color-text-quaternary);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-6xl) var(--spacing-xl);
  color: var(--color-text-quaternary);
}

.empty-icon {
  font-size: var(--font-size-6xl);
  margin-bottom: var(--spacing-lg);
}

.empty-state p {
  font-size: var(--font-size-base);
}
</style>