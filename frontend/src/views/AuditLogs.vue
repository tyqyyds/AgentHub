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
  font-size: 24px;
  font-weight: 700;
  color: white;
  margin-bottom: 24px;
}

.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding: 16px 20px;
  background: rgba(30, 41, 59, 0.6);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.search-box {
  flex: 1;
  max-width: 400px;
}

.search-input {
  width: 100%;
  padding: 12px 16px;
  background: rgba(15, 23, 42, 0.5);
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: white;
  font-size: 14px;
  transition: all 0.3s ease;
}

.search-input:focus {
  outline: none;
  border-color: #165DFF;
  box-shadow: 0 0 0 4px rgba(22, 93, 255, 0.1);
}

.search-input::placeholder {
  color: #64748B;
}

.filter-selects {
  display: flex;
  gap: 12px;
}

.filter-select {
  padding: 12px 16px;
  background: rgba(15, 23, 42, 0.5);
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: white;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.filter-select:focus {
  outline: none;
  border-color: #165DFF;
}

.filter-select option {
  background: #1E293B;
  color: white;
}

.logs-table-container {
  background: rgba(30, 41, 59, 0.6);
  border-radius: 16px;
  padding: 20px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  overflow-x: auto;
}

.logs-table {
  width: 100%;
  border-collapse: collapse;
}

.logs-table thead tr {
  border-bottom: 2px solid rgba(255, 255, 255, 0.1);
}

.logs-table th {
  text-align: left;
  padding: 14px 16px;
  font-size: 13px;
  font-weight: 600;
  color: #94A3B8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.logs-table tbody tr {
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  transition: background 0.2s ease;
}

.logs-table tbody tr:hover {
  background: rgba(22, 93, 255, 0.05);
}

.logs-table td {
  padding: 14px 16px;
  font-size: 14px;
  color: #E2E8F0;
}

.log-id {
  font-family: monospace;
  color: #69B1FF;
}

.log-user {
  font-weight: 500;
}

.action-badge {
  padding: 4px 10px;
  background: rgba(22, 93, 255, 0.2);
  color: #69B1FF;
  border-radius: 8px;
  font-size: 12px;
}

.log-device {
  font-family: monospace;
}

.commands-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.command-item {
  font-size: 12px;
  color: #52C41A;
  font-family: monospace;
  padding: 4px 8px;
  background: rgba(82, 196, 26, 0.1);
  border-radius: 4px;
}

.no-commands {
  color: #64748B;
  font-size: 12px;
}

.approval-link {
  font-size: 12px;
  color: #FF7D00;
  text-decoration: underline;
  cursor: pointer;
}

.no-approval {
  color: #64748B;
  font-size: 12px;
}

.status-badge {
  padding: 4px 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
}

.status-badge.success {
  background: rgba(82, 196, 26, 0.2);
  color: #52C41A;
}

.status-badge.pending {
  background: rgba(255, 125, 0, 0.2);
  color: #FF7D00;
}

.status-badge.failed {
  background: rgba(255, 77, 79, 0.2);
  color: #FF4D4F;
}

.log-time {
  font-size: 13px;
  color: #64748B;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #64748B;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state p {
  font-size: 14px;
}
</style>