<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface Playbook {
  id: string
  name: string
  description: string
  steps: number
  lastRun: string
  status: 'ready' | 'running' | 'failed'
  author: string
}

const loading = ref(false)
const playbooks = ref<Playbook[]>([
  { id: 'PB-001', name: '链路故障自愈', description: '自动检测链路故障并切换备份路径', steps: 5, lastRun: '2026-06-13 09:00', status: 'ready', author: '系统' },
  { id: 'PB-002', name: '设备配置备份', description: '定期备份所有网络设备配置', steps: 3, lastRun: '2026-06-13 06:00', status: 'ready', author: '张工' },
  { id: 'PB-003', name: '安全策略巡检', description: '自动巡检防火墙安全策略合规性', steps: 8, lastRun: '2026-06-12 22:00', status: 'failed', author: '李工' },
  { id: 'PB-004', name: 'QoS动态调整', description: '根据流量模式动态调整QoS策略', steps: 6, lastRun: '运行中', status: 'running', author: '系统' }
])

const showEditDialog = ref(false)
const editingPlaybook = ref<Playbook | null>(null)

function editPlaybook(pb: Playbook) {
  editingPlaybook.value = { ...pb }
  showEditDialog.value = true
}

function executePlaybook(pb: Playbook) {
  pb.status = 'running'
  pb.lastRun = '运行中'
}

function getStatusLabel(s: string) {
  return s === 'ready' ? '就绪' : s === 'running' ? '执行中' : '失败'
}

onMounted(() => {
  // TODO: 调用API获取剧本列表
})
</script>

<template>
  <div class="playbooks">
    <h1 class="page-title">剧本管理</h1>

    <div class="toolbar">
      <div class="filter-group">
        <span class="filter-label">状态筛选:</span>
        <span class="filter-chip active">全部</span>
        <span class="filter-chip">就绪</span>
        <span class="filter-chip">执行中</span>
        <span class="filter-chip">失败</span>
      </div>
      <button class="action-btn">+ 新建剧本</button>
    </div>

    <div class="playbook-table">
      <div class="table-header">
        <div class="col id-col">ID</div>
        <div class="col name-col">剧本名称</div>
        <div class="col desc-col">描述</div>
        <div class="col steps-col">步骤数</div>
        <div class="col status-col">状态</div>
        <div class="col time-col">最近执行</div>
        <div class="col actions-col">操作</div>
      </div>
      <div v-for="pb in playbooks" :key="pb.id" class="table-row">
        <div class="col id-col">{{ pb.id }}</div>
        <div class="col name-col">{{ pb.name }}</div>
        <div class="col desc-col">{{ pb.description }}</div>
        <div class="col steps-col">{{ pb.steps }}</div>
        <div class="col status-col">
          <span :class="['status-tag', pb.status]">{{ getStatusLabel(pb.status) }}</span>
        </div>
        <div class="col time-col">{{ pb.lastRun }}</div>
        <div class="col actions-col">
          <button class="btn-sm primary" @click="executePlaybook(pb)" :disabled="pb.status === 'running'">执行</button>
          <button class="btn-sm" @click="editPlaybook(pb)">编辑</button>
          <button class="btn-sm secondary">历史</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); color: var(--color-white); margin-bottom: var(--spacing-2xl); }

.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-2xl); }

.filter-group { display: flex; align-items: center; gap: var(--spacing-sm); }
.filter-label { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }

.filter-chip {
  font-size: var(--font-size-sm);
  padding: var(--spacing-2xs) var(--spacing-md);
  border-radius: var(--radius-full);
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: all 0.2s;
}

.filter-chip.active { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); }

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

.playbook-table {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-2xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  overflow: hidden;
}

.table-header {
  display: flex;
  padding: var(--spacing-md-lg) var(--spacing-xl);
  background: rgba(var(--color-bg-base-rgb), 0.5);
  font-size: var(--font-size-sm);
  color: var(--color-text-quaternary);
  font-weight: var(--font-weight-semibold);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.table-row {
  display: flex;
  padding: var(--spacing-lg) var(--spacing-xl);
  border-top: 1px solid rgba(var(--color-white-rgb), 0.05);
  align-items: center;
  transition: background 0.2s;
}

.table-row:hover { background: rgba(var(--color-primary-rgb), 0.05); }

.col { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
.id-col { width: 80px; color: var(--color-text-quaternary); font-family: monospace; }
.name-col { width: 160px; font-weight: var(--font-weight-medium); }
.desc-col { flex: 1; color: var(--color-text-tertiary); }
.steps-col { width: 70px; text-align: center; }
.status-col { width: 90px; }
.time-col { width: 140px; color: var(--color-text-quaternary); }
.actions-col { width: 200px; display: flex; gap: var(--spacing-xs); }

.status-tag {
  font-size: var(--font-size-xs);
  padding: 3px var(--spacing-sm-md);
  border-radius: var(--radius-lg);
  font-weight: var(--font-weight-medium);
}

.status-tag.ready { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); }
.status-tag.running { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); }
.status-tag.failed { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); }

.btn-sm {
  padding: 5px var(--spacing-md);
  background: rgba(var(--color-text-quaternary-rgb), 0.2);
  color: var(--color-text-tertiary);
  border: 1px solid rgba(var(--color-text-quaternary-rgb), 0.3);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-sm:hover { background: rgba(var(--color-text-quaternary-rgb), 0.3); }
.btn-sm.primary { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); border-color: rgba(var(--color-primary-rgb), 0.3); }
.btn-sm.primary:hover { background: rgba(var(--color-primary-rgb), 0.3); }
.btn-sm.primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-sm.secondary { background: rgba(var(--color-text-quaternary-rgb), 0.1); }
</style>
