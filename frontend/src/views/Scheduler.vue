<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface ScheduleTask {
  id: string
  name: string
  cron: string
  cronDesc: string
  status: 'active' | 'paused' | 'error'
  lastRun: string
  nextRun: string
  runCount: number
}

const loading = ref(false)
const tasks = ref<ScheduleTask[]>([
  { id: 'SCH-001', name: '设备健康巡检', cron: '0 */30 * * * *', cronDesc: '每30分钟', status: 'active', lastRun: '2026-06-13 10:30', nextRun: '2026-06-13 11:00', runCount: 1248 },
  { id: 'SCH-002', name: '配置备份', cron: '0 0 2 * * *', cronDesc: '每天凌晨2点', status: 'active', lastRun: '2026-06-13 02:00', nextRun: '2026-06-14 02:00', runCount: 365 },
  { id: 'SCH-003', name: '安全策略巡检', cron: '0 0 22 * * 1-5', cronDesc: '工作日22点', status: 'paused', lastRun: '2026-06-12 22:00', nextRun: '已暂停', runCount: 156 },
  { id: 'SCH-004', name: '日志归档', cron: '0 0 3 * * 0', cronDesc: '每周日凌晨3点', status: 'active', lastRun: '2026-06-08 03:00', nextRun: '2026-06-15 03:00', runCount: 52 },
  { id: 'SCH-005', name: 'SLA报告生成', cron: '0 0 9 1 * *', cronDesc: '每月1日9点', status: 'error', lastRun: '2026-06-01 09:00', nextRun: '执行异常', runCount: 6 }
])

const showCreateDialog = ref(false)
const newTask = ref({ name: '', cron: '', cronDesc: '' })

function getStatusLabel(s: string) {
  return s === 'active' ? '运行中' : s === 'paused' ? '已暂停' : '异常'
}

function toggleTask(task: ScheduleTask) {
  task.status = task.status === 'active' ? 'paused' : 'active'
}

function createTask() {
  if (!newTask.value.name.trim()) return
  tasks.value.unshift({
    id: `SCH-${String(tasks.value.length + 1).padStart(3, '0')}`,
    name: newTask.value.name,
    cron: newTask.value.cron || '0 0 * * * *',
    cronDesc: newTask.value.cronDesc || '自定义',
    status: 'paused',
    lastRun: '从未执行',
    nextRun: '待计算',
    runCount: 0
  })
  newTask.value = { name: '', cron: '', cronDesc: '' }
  showCreateDialog.value = false
}

onMounted(() => {
  // TODO: 调用API获取调度任务列表
})
</script>

<template>
  <div class="scheduler">
    <h1 class="page-title">调度器</h1>

    <div class="toolbar">
      <div class="stats-row">
        <div class="stat-chip active">运行 {{ tasks.filter(t => t.status === 'active').length }}</div>
        <div class="stat-chip paused">暂停 {{ tasks.filter(t => t.status === 'paused').length }}</div>
        <div class="stat-chip error">异常 {{ tasks.filter(t => t.status === 'error').length }}</div>
      </div>
      <button class="action-btn" @click="showCreateDialog = true">+ 创建调度</button>
    </div>

    <div class="task-table">
      <div class="table-header">
        <div class="col id-col">ID</div>
        <div class="col name-col">任务名称</div>
        <div class="col cron-col">Cron表达式</div>
        <div class="col desc-col">频率</div>
        <div class="col status-col">状态</div>
        <div class="col last-col">上次执行</div>
        <div class="col next-col">下次执行</div>
        <div class="col count-col">执行次数</div>
        <div class="col actions-col">操作</div>
      </div>
      <div v-for="task in tasks" :key="task.id" class="table-row">
        <div class="col id-col">{{ task.id }}</div>
        <div class="col name-col">{{ task.name }}</div>
        <div class="col cron-col"><code>{{ task.cron }}</code></div>
        <div class="col desc-col">{{ task.cronDesc }}</div>
        <div class="col status-col">
          <span :class="['status-tag', task.status]">{{ getStatusLabel(task.status) }}</span>
        </div>
        <div class="col last-col">{{ task.lastRun }}</div>
        <div class="col next-col">{{ task.nextRun }}</div>
        <div class="col count-col">{{ task.runCount }}</div>
        <div class="col actions-col">
          <button class="btn-sm" @click="toggleTask(task)">{{ task.status === 'active' ? '暂停' : '启用' }}</button>
          <button class="btn-sm secondary">历史</button>
        </div>
      </div>
    </div>

    <div v-if="showCreateDialog" class="dialog-overlay" @click.self="showCreateDialog = false">
      <div class="dialog-box">
        <h3 class="dialog-title">创建调度任务</h3>
        <div class="form-group">
          <label>任务名称</label>
          <input v-model="newTask.name" class="form-input" placeholder="输入任务名称" />
        </div>
        <div class="form-group">
          <label>Cron表达式</label>
          <input v-model="newTask.cron" class="form-input" placeholder="0 */30 * * * *" />
          <div class="form-hint">格式: 秒 分 时 日 月 周</div>
        </div>
        <div class="form-group">
          <label>频率描述</label>
          <input v-model="newTask.cronDesc" class="form-input" placeholder="例如: 每30分钟" />
        </div>
        <div class="dialog-actions">
          <button class="btn-sm" @click="showCreateDialog = false">取消</button>
          <button class="action-btn" @click="createTask">创建</button>
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
.stat-chip.paused { background: rgba(var(--color-warning-rgb), 0.2); color: var(--color-warning); }
.stat-chip.error { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); }

.action-btn { padding: var(--spacing-sm-md) var(--spacing-xl); background: var(--gradient-primary); color: var(--color-white); border: none; border-radius: var(--radius-lg); font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); cursor: pointer; }
.action-btn:hover { transform: translateY(-1px); box-shadow: 0 var(--spacing-xs) var(--spacing-md) rgba(var(--color-primary-rgb), 0.4); }

.task-table { background: rgba(var(--color-bg-elevated-rgb), 0.6); border-radius: var(--radius-2xl); border: 1px solid rgba(var(--color-white-rgb), 0.1); overflow: hidden; }
.table-header { display: flex; padding: var(--spacing-md-lg) var(--spacing-xl); background: rgba(var(--color-bg-base-rgb), 0.5); font-size: var(--font-size-sm); color: var(--color-text-quaternary); font-weight: var(--font-weight-semibold); text-transform: uppercase; letter-spacing: 0.5px; }
.table-row { display: flex; padding: var(--spacing-md-lg) var(--spacing-xl); border-top: 1px solid rgba(var(--color-white-rgb), 0.05); align-items: center; transition: background 0.2s; }
.table-row:hover { background: rgba(var(--color-primary-rgb), 0.05); }

.col { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
.id-col { width: 70px; color: var(--color-text-quaternary); font-family: monospace; }
.name-col { width: 140px; font-weight: var(--font-weight-medium); }
.cron-col { width: 150px; }
.cron-col code { font-size: var(--font-size-xs); color: var(--color-info-light); background: rgba(var(--color-primary-rgb), 0.1); padding: var(--spacing-3xs) var(--spacing-xs); border-radius: var(--spacing-2xs); }
.desc-col { width: 110px; color: var(--color-text-tertiary); }
.status-col { width: 80px; }
.last-col { width: 130px; color: var(--color-text-quaternary); font-size: var(--font-size-sm); }
.next-col { width: 130px; color: var(--color-text-quaternary); font-size: var(--font-size-sm); }
.count-col { width: 70px; text-align: center; }
.actions-col { width: 140px; display: flex; gap: var(--spacing-xs); }

.status-tag { font-size: var(--font-size-xs); padding: 3px var(--spacing-sm); border-radius: var(--radius-full); font-weight: var(--font-weight-medium); }
.status-tag.active { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); }
.status-tag.paused { background: rgba(var(--color-warning-rgb), 0.2); color: var(--color-warning); }
.status-tag.error { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); }

.btn-sm { padding: 5px var(--spacing-md); background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); border: 1px solid rgba(var(--color-primary-rgb), 0.3); border-radius: var(--radius-md); font-size: var(--font-size-sm); cursor: pointer; }
.btn-sm.secondary { background: rgba(var(--color-text-quaternary-rgb), 0.2); color: var(--color-text-tertiary); border-color: rgba(var(--color-text-quaternary-rgb), 0.3); }

.dialog-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; justify-content: center; z-index: var(--z-modal); }
.dialog-box { background: var(--color-bg-container); border-radius: var(--radius-2xl); padding: 28px; width: 440px; border: 1px solid rgba(var(--color-white-rgb), 0.1); }
.dialog-title { font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold); color: var(--color-white); margin-bottom: var(--spacing-xl); }
.form-group { margin-bottom: var(--spacing-lg); }
.form-group label { display: block; font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-bottom: var(--spacing-xs); }
.form-input { width: 100%; padding: var(--spacing-sm-md) var(--spacing-md-lg); background: rgba(var(--color-bg-base-rgb), 0.5); border: 1px solid rgba(var(--color-white-rgb), 0.1); border-radius: var(--radius-lg); color: var(--color-white); font-size: var(--font-size-base); font-family: monospace; }
.form-input:focus { outline: none; border-color: var(--color-primary); }
.form-hint { font-size: var(--font-size-xs); color: var(--color-text-quaternary); margin-top: var(--spacing-2xs); }
.dialog-actions { display: flex; justify-content: flex-end; gap: var(--spacing-sm); margin-top: var(--spacing-xl); }
</style>
