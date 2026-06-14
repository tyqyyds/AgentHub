<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useLogger } from '@/utils/logger'
import { api, apiClient } from '@/utils/apiClient'
import { showToast } from '../utils/toast'
import { useAuthStore } from '@/stores/auth'

const { info, warn } = useLogger()
const authStore = useAuthStore()
const canWrite = computed(() => authStore.userRole !== 'viewer')

interface PlaybookStep {
  id: string
  type: 'intent' | 'mcp_tool' | 'approval' | 'notification' | 'delay' | 'condition'
  name: string
  params: Record<string, any>
}

interface Playbook {
  id: string | number
  name: string
  description: string
  category: string
  steps: PlaybookStep[]
  execution_count: number
  last_status: string
  author: string
  created_at: string
  updated_at: string
}

interface ExecutionStep {
  id: string
  step_name: string
  step_type: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'waiting_approval'
  started_at: string | null
  completed_at: string | null
  result: any
}

interface Execution {
  id: string | number
  playbook_id: string | number
  playbook_name: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'waiting_approval'
  steps: ExecutionStep[]
  current_step: number
  total_steps: number
  started_at: string
  completed_at: string | null
  triggered_by: string
}

const STEP_TYPES = [
  { value: 'intent', label: '意图执行', icon: '🎯' },
  { value: 'mcp_tool', label: 'MCP工具', icon: '🛠️' },
  { value: 'approval', label: '人工审批', icon: '✅' },
  { value: 'notification', label: '通知', icon: '📢' },
  { value: 'delay', label: '延时等待', icon: '⏱️' },
  { value: 'condition', label: '条件判断', icon: '🔀' }
]

const PLAYBOOK_CATEGORIES = [
  { value: 'fault_recovery', label: '故障恢复' },
  { value: 'routine_maintenance', label: '日常巡检' },
  { value: 'emergency_response', label: '应急响应' },
  { value: 'capacity_planning', label: '容量规划' },
  { value: 'security_hardening', label: '安全加固' }
]

const playbooks = ref<Playbook[]>([])
const executions = ref<Execution[]>([])
const isLoading = ref(true)
const showCreateDialog = ref(false)
const showExecuteDialog = ref(false)
const showMonitorDialog = ref(false)
const showStepResultDialog = ref(false)
const isEditing = ref(false)
const editingPlaybookId = ref<string | number>('')
const selectedPlaybook = ref<Playbook | null>(null)
const selectedExecution = ref<Execution | null>(null)
const selectedStep = ref<ExecutionStep | null>(null)
const executeParams = ref<Record<string, any>>({})
const isSubmitting = ref(false)
let pollTimer: number | null = null

const playbookForm = ref({
  name: '',
  description: '',
  category: 'fault_recovery',
  steps: [] as PlaybookStep[]
})

let stepCounter = 0
const genStepId = () => `step_${Date.now()}_${++stepCounter}`

const addStep = () => {
  playbookForm.value.steps.push({
    id: genStepId(),
    type: 'intent',
    name: '',
    params: {}
  })
}

const removeStep = (index: number) => {
  playbookForm.value.steps.splice(index, 1)
}

const moveStepUp = (index: number) => {
  if (index <= 0) return
  const steps = playbookForm.value.steps
  const temp = steps[index]
  steps[index] = steps[index - 1]
  steps[index - 1] = temp
}

const moveStepDown = (index: number) => {
  const steps = playbookForm.value.steps
  if (index >= steps.length - 1) return
  const temp = steps[index]
  steps[index] = steps[index + 1]
  steps[index + 1] = temp
}

const getStepTypeLabel = (type: string) => {
  return STEP_TYPES.find(s => s.value === type)?.label || type
}

const getStepTypeIcon = (type: string) => {
  return STEP_TYPES.find(s => s.value === type)?.icon || '📋'
}

const getCategoryLabel = (value: string) => {
  return PLAYBOOK_CATEGORIES.find(c => c.value === value)?.label || value
}

const getStatusColor = (status: string) => {
  const map: Record<string, string> = {
    completed: 'var(--color-success)',
    running: 'var(--color-primary)',
    pending: 'var(--color-text-tertiary)',
    failed: 'var(--color-error)',
    waiting_approval: 'var(--color-warning)',
    cancelled: 'var(--color-text-disabled)'
  }
  return map[status] || 'var(--color-text-tertiary)'
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    completed: '已完成',
    running: '运行中',
    pending: '待执行',
    failed: '失败',
    waiting_approval: '待审批',
    cancelled: '已取消'
  }
  return map[status] || status
}

const getStepStatusIcon = (status: string) => {
  const map: Record<string, string> = {
    completed: '✅',
    running: '🔄',
    pending: '⏳',
    failed: '❌',
    waiting_approval: '⏸️'
  }
  return map[status] || '📋'
}

const fetchPlaybooks = async () => {
  isLoading.value = true
  try {
    const result = await apiClient.get(api.playbooks.list)
    playbooks.value = result.data?.items || result.data || []
  } catch (err: any) {
    warn('获取剧本列表失败', { error: err.message })
    loadMockData()
  } finally {
    isLoading.value = false
  }
}

const fetchExecutions = async () => {
  try {
    const result = await apiClient.get(api.playbooks.executions)
    executions.value = result.data?.items || result.data || []
  } catch {
    executions.value = []
  }
}

const loadMockData = () => {
  playbooks.value = [
    {
      id: '1', name: '链路故障自动恢复', description: '检测链路故障后自动切换备用链路并验证恢复',
      category: 'fault_recovery',
      steps: [
        { id: 's1', type: 'intent', name: '检测链路状态', params: { intent: '检测核心路由器链路连通性' } },
        { id: 's2', type: 'intent', name: '切换备用链路', params: { intent: '将故障链路切换到备用链路' } },
        { id: 's3', type: 'delay', name: '等待稳定', params: { seconds: 30 } },
        { id: 's4', type: 'intent', name: '验证恢复', params: { intent: '验证链路切换后连通性' } },
        { id: 's5', type: 'notification', name: '通知运维团队', params: { channel: '钉钉', message: '链路故障已自动恢复' } }
      ],
      execution_count: 47, last_status: 'completed', author: 'admin',
      created_at: '2025-04-01T10:00:00Z', updated_at: '2025-05-20T14:30:00Z'
    },
    {
      id: '2', name: '日常网络巡检', description: '每日自动巡检网络设备健康状态并生成报告',
      category: 'routine_maintenance',
      steps: [
        { id: 's1', type: 'intent', name: '采集设备状态', params: { intent: '采集所有核心设备CPU、内存、端口状态' } },
        { id: 's2', type: 'condition', name: '判断异常', params: { condition: 'cpu > 80 OR memory > 90' } },
        { id: 's3', type: 'notification', name: '异常告警', params: { channel: '邮件', message: '设备异常告警' } },
        { id: 's4', type: 'mcp_tool', name: '生成巡检报告', params: { tool: 'report_generator' } }
      ],
      execution_count: 120, last_status: 'completed', author: 'operator1',
      created_at: '2025-03-15T08:00:00Z', updated_at: '2025-05-28T06:00:00Z'
    },
    {
      id: '3', name: '安全事件应急响应', description: '安全事件触发后自动隔离、分析并通知安全团队',
      category: 'emergency_response',
      steps: [
        { id: 's1', type: 'intent', name: '隔离受影响设备', params: { intent: '隔离受攻击设备的网络访问' } },
        { id: 's2', type: 'approval', name: '安全团队审批', params: { approver: 'security_team' } },
        { id: 's3', type: 'mcp_tool', name: '安全扫描', params: { tool: 'security_scanner' } },
        { id: 's4', type: 'notification', name: '通知管理层', params: { channel: '短信', message: '安全事件处理完成' } }
      ],
      execution_count: 8, last_status: 'waiting_approval', author: 'admin',
      created_at: '2025-05-10T12:00:00Z', updated_at: '2025-05-29T09:00:00Z'
    },
    {
      id: '4', name: '带宽扩容流程', description: '当带宽利用率持续超阈值时自动执行扩容审批和配置',
      category: 'capacity_planning',
      steps: [
        { id: 's1', type: 'intent', name: '分析带宽趋势', params: { intent: '分析核心链路带宽使用趋势' } },
        { id: 's2', type: 'approval', name: '扩容审批', params: { approver: 'network_manager' } },
        { id: 's3', type: 'intent', name: '执行扩容配置', params: { intent: '为指定链路增加带宽配额' } },
        { id: 's4', type: 'intent', name: '验证扩容效果', params: { intent: '验证扩容后带宽利用率' } }
      ],
      execution_count: 15, last_status: 'completed', author: 'operator2',
      created_at: '2025-04-20T09:00:00Z', updated_at: '2025-05-25T16:00:00Z'
    }
  ]
}

const openCreateDialog = () => {
  isEditing.value = false
  editingPlaybookId.value = ''
  stepCounter = 0
  playbookForm.value = {
    name: '', description: '', category: 'fault_recovery', steps: []
  }
  showCreateDialog.value = true
}

const openEditDialog = (playbook: Playbook) => {
  isEditing.value = true
  editingPlaybookId.value = playbook.id
  playbookForm.value = {
    name: playbook.name,
    description: playbook.description,
    category: playbook.category,
    steps: JSON.parse(JSON.stringify(playbook.steps))
  }
  showCreateDialog.value = true
}

const submitPlaybook = async () => {
  if (!playbookForm.value.name || playbookForm.value.steps.length === 0) {
    showToast('请填写剧本名称并添加至少一个步骤', 'error')
    return
  }
  isSubmitting.value = true
  try {
    if (isEditing.value) {
      await apiClient.put(api.playbooks.byId(String(editingPlaybookId.value)), playbookForm.value)
      showToast('剧本更新成功', 'success')
    } else {
      await apiClient.post(api.playbooks.list, playbookForm.value)
      showToast('剧本创建成功', 'success')
    }
    showCreateDialog.value = false
    await fetchPlaybooks()
  } catch (err: any) {
    warn('保存剧本失败', { error: err.message })
    showToast('保存剧本失败: ' + err.message, 'error')
  } finally {
    isSubmitting.value = false
  }
}

const deletePlaybook = async (id: string | number) => {
  try {
    await apiClient.delete(api.playbooks.byId(String(id)))
    showToast('剧本已删除', 'success')
    await fetchPlaybooks()
  } catch (err: any) {
    warn('删除剧本失败', { error: err.message })
    showToast('删除失败: ' + err.message, 'error')
  }
}

const openExecuteDialog = (playbook: Playbook) => {
  selectedPlaybook.value = playbook
  executeParams.value = {}
  playbook.steps.forEach(step => {
    if (step.params) {
      for (const [key, val] of Object.entries(step.params)) {
        if (typeof val === 'string' && val.length > 0) {
          executeParams.value[`${step.id}_${key}`] = val
        }
      }
    }
  })
  showExecuteDialog.value = true
}

const submitExecute = async () => {
  if (!selectedPlaybook.value) return
  isSubmitting.value = true
  try {
    await apiClient.post(api.playbooks.execute(String(selectedPlaybook.value.id)), {
      parameters: executeParams.value
    })
    showToast('剧本执行已启动', 'success')
    showExecuteDialog.value = false
    await fetchExecutions()
  } catch (err: any) {
    warn('执行失败', { error: err.message })
    showToast('执行失败: ' + err.message, 'error')
  } finally {
    isSubmitting.value = false
  }
}

const openMonitor = async (execution: Execution) => {
  selectedExecution.value = execution
  showMonitorDialog.value = true
  await refreshExecution()
}

const refreshExecution = async () => {
  if (!selectedExecution.value) return
  try {
    const result = await apiClient.get(api.playbooks.executionById(String(selectedExecution.value.id)))
    if (result.data) {
      selectedExecution.value = result.data
    }
  } catch (err: any) {
    warn('刷新执行状态失败', { error: err.message })
  }
}

const approveExecution = async () => {
  if (!selectedExecution.value) return
  try {
    await apiClient.post(api.playbooks.approveExecution(String(selectedExecution.value.id)))
    showToast('审批通过', 'success')
    await refreshExecution()
    await fetchExecutions()
  } catch (err: any) {
    warn('审批失败', { error: err.message })
    showToast('审批失败: ' + err.message, 'error')
  }
}

const cancelExecution = async () => {
  if (!selectedExecution.value) return
  try {
    await apiClient.post(api.playbooks.cancelExecution(String(selectedExecution.value.id)))
    showToast('执行已取消', 'success')
    await refreshExecution()
    await fetchExecutions()
  } catch (err: any) {
    warn('取消失败', { error: err.message })
    showToast('取消失败: ' + err.message, 'error')
  }
}

const openStepResult = (step: ExecutionStep) => {
  selectedStep.value = step
  showStepResultDialog.value = true
}

const executionProgress = computed(() => {
  if (!selectedExecution.value) return 0
  const total = selectedExecution.value.total_steps || 1
  const completed = selectedExecution.value.steps.filter(s => s.status === 'completed').length
  return Math.round((completed / total) * 100)
})

const formatTime = (dateStr: string | null): string => {
  if (!dateStr) return '--'
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  return date.toLocaleString('zh-CN')
}

onMounted(() => {
  info('Playbooks mounted')
  fetchPlaybooks()
  fetchExecutions()
  pollTimer = window.setInterval(() => {
    fetchExecutions()
    if (selectedExecution.value && showMonitorDialog.value) {
      refreshExecution()
    }
  }, 10000)
})

onUnmounted(() => {
  if (pollTimer !== null) clearInterval(pollTimer)
})
</script>

<template>
  <div class="playbooks-page">
    <div class="playbooks-bg">
      <div class="bg-grid"></div>
      <div class="bg-glow glow-1"></div>
      <div class="bg-glow glow-2"></div>
    </div>

    <div class="playbooks-header">
      <div class="header-left">
        <h1 class="page-title">运维剧本</h1>
        <p class="page-subtitle">编排自动化运维流程，标准化故障恢复与日常巡检</p>
      </div>
      <div class="header-actions">
        <button type="button" v-if="canWrite" class="action-btn primary" @click="openCreateDialog">
          ➕ 创建剧本
        </button>
      </div>
    </div>

    <div class="content-layout">
      <div class="main-panel">
        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">剧本列表</h2>
          </div>

          <div v-if="isLoading" class="loading-state">
            <div v-for="i in 3" :key="i" class="skeleton-row">
              <div class="skeleton-line wide"></div>
              <div class="skeleton-line medium"></div>
            </div>
          </div>

          <div v-else class="playbook-table">
            <div class="table-header">
              <div class="col-name">名称</div>
              <div class="col-category">分类</div>
              <div class="col-steps">步骤</div>
              <div class="col-exec-count">执行次数</div>
              <div class="col-status">最近状态</div>
              <div class="col-author">作者</div>
              <div class="col-actions">操作</div>
            </div>
            <div
              v-for="pb in playbooks"
              :key="pb.id"
              class="table-row"
            >
              <div class="col-name">
                <div class="pb-name">{{ pb.name }}</div>
                <div class="pb-desc">{{ pb.description }}</div>
              </div>
              <div class="col-category">
                <span class="category-tag">{{ getCategoryLabel(pb.category) }}</span>
              </div>
              <div class="col-steps">
                <span class="steps-count">{{ pb.steps.length }}步</span>
              </div>
              <div class="col-exec-count">{{ pb.execution_count }}</div>
              <div class="col-status">
                <span class="status-badge" :style="{ color: getStatusColor(pb.last_status), background: getStatusColor(pb.last_status) + '15', borderColor: getStatusColor(pb.last_status) + '30' }">
                  {{ getStatusText(pb.last_status) }}
                </span>
              </div>
              <div class="col-author">{{ pb.author }}</div>
              <div class="col-actions">
                <button type="button" v-if="canWrite" class="action-icon-btn" @click="openExecuteDialog(pb)" title="执行">🚀</button>
                <button type="button" v-if="canWrite" class="action-icon-btn" @click="openEditDialog(pb)" title="编辑">✏️</button>
                <button type="button" v-if="canWrite" class="action-icon-btn danger" @click="deletePlaybook(pb.id)" title="删除">🗑️</button>
              </div>
            </div>
            <div v-if="playbooks.length === 0" class="empty-state">
              <div class="empty-icon">📭</div>
              <div>暂无剧本</div>
            </div>
          </div>
        </div>
      </div>

      <div class="side-panel">
        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">执行记录</h2>
          </div>
          <div class="execution-list">
            <div
              v-for="exec in executions.slice(0, 10)"
              :key="exec.id"
              class="execution-item"
              @click="openMonitor(exec)"
            >
              <div class="exec-header">
                <span class="exec-name">{{ exec.playbook_name }}</span>
                <span class="status-badge small" :style="{ color: getStatusColor(exec.status), background: getStatusColor(exec.status) + '15' }">
                  {{ getStatusText(exec.status) }}
                </span>
              </div>
              <div class="exec-progress-bar">
                <div
                  class="exec-progress-fill"
                  :style="{
                    width: `${exec.total_steps ? (exec.current_step / exec.total_steps) * 100 : 0}%`,
                    background: getStatusColor(exec.status)
                  }"
                ></div>
              </div>
              <div class="exec-meta">
                <span>{{ exec.triggered_by }}</span>
                <span>{{ formatTime(exec.started_at) }}</span>
              </div>
            </div>
            <div v-if="executions.length === 0" class="empty-state small">
              暂无执行记录
            </div>
          </div>
        </div>
      </div>
    </div>

    <el-dialog
      v-model="showCreateDialog"
      :title="isEditing ? '编辑剧本' : '创建剧本'"
      width="720px"
      class="dark-dialog"
      destroy-on-close
    >
      <el-form label-position="top" class="dark-form">
        <el-form-item label="剧本名称" required>
          <el-input v-model="playbookForm.name" placeholder="输入剧本名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="playbookForm.description" type="textarea" :rows="2" placeholder="剧本用途说明" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="playbookForm.category" placeholder="选择分类">
            <el-option
              v-for="cat in PLAYBOOK_CATEGORIES"
              :key="cat.value"
              :label="cat.label"
              :value="cat.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="步骤编排">
          <div class="steps-editor">
            <div
              v-for="(step, idx) in playbookForm.steps"
              :key="step.id"
              class="step-item"
            >
              <div class="step-index">{{ idx + 1 }}</div>
              <div class="step-controls">
                <button type="button" class="step-move-btn" :disabled="idx === 0" @click="moveStepUp(idx)">↑</button>
                <button type="button" class="step-move-btn" :disabled="idx === playbookForm.steps.length - 1" @click="moveStepDown(idx)">↓</button>
              </div>
              <el-select v-model="step.type" class="step-type-select">
                <el-option
                  v-for="st in STEP_TYPES"
                  :key="st.value"
                  :label="`${st.icon} ${st.label}`"
                  :value="st.value"
                />
              </el-select>
              <el-input v-model="step.name" placeholder="步骤名称" class="step-name-input" />
              <button type="button" class="step-remove-btn" @click="removeStep(idx)">✕</button>
            </div>
            <button type="button" class="add-step-btn" @click="addStep">+ 添加步骤</button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="isSubmitting" @click="submitPlaybook">
          {{ isEditing ? '更新' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showExecuteDialog"
      title="执行剧本"
      width="560px"
      class="dark-dialog"
      destroy-on-close
    >
      <div v-if="selectedPlaybook" class="execute-content">
        <div class="execute-playbook-name">{{ selectedPlaybook.name }}</div>
        <div class="execute-playbook-desc">{{ selectedPlaybook.description }}</div>
        <div class="execute-steps-preview">
          <div class="execute-step-label">执行步骤 ({{ selectedPlaybook.steps.length }}步)</div>
          <div v-for="(step, idx) in selectedPlaybook.steps" :key="step.id" class="execute-step-item">
            <span class="execute-step-index">{{ idx + 1 }}</span>
            <span class="execute-step-icon">{{ getStepTypeIcon(step.type) }}</span>
            <span class="execute-step-name">{{ step.name || getStepTypeLabel(step.type) }}</span>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showExecuteDialog = false">取消</el-button>
        <el-button type="primary" :loading="isSubmitting" @click="submitExecute">🚀 执行</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="showMonitorDialog"
      title="执行监控"
      width="640px"
      class="dark-dialog"
      destroy-on-close
    >
      <div v-if="selectedExecution" class="monitor-content">
        <div class="monitor-header">
          <div class="monitor-playbook-name">{{ selectedExecution.playbook_name }}</div>
          <span class="status-badge" :style="{ color: getStatusColor(selectedExecution.status), background: getStatusColor(selectedExecution.status) + '15', borderColor: getStatusColor(selectedExecution.status) + '30' }">
            {{ getStatusText(selectedExecution.status) }}
          </span>
        </div>
        <div class="monitor-progress">
          <div class="progress-info">
            <span>进度 {{ executionProgress }}%</span>
            <span>{{ selectedExecution.current_step }}/{{ selectedExecution.total_steps }} 步骤</span>
          </div>
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{
                width: `${executionProgress}%`,
                background: `linear-gradient(90deg, ${getStatusColor(selectedExecution.status)}, ${getStatusColor(selectedExecution.status)}88)`
              }"
            ></div>
          </div>
        </div>
        <div class="monitor-steps">
          <div
            v-for="(step, idx) in selectedExecution.steps"
            :key="step.id"
            class="monitor-step"
            :class="{ clickable: step.status === 'completed' || step.status === 'failed' }"
            @click="(step.status === 'completed' || step.status === 'failed') && openStepResult(step)"
          >
            <div class="monitor-step-dot" :style="{ background: getStatusColor(step.status), boxShadow: `0 0 6px ${getStatusColor(step.status)}40` }"></div>
            <div v-if="idx < selectedExecution.steps.length - 1" class="monitor-step-line"></div>
            <div class="monitor-step-content">
              <div class="monitor-step-header">
                <span class="monitor-step-icon">{{ getStepStatusIcon(step.status) }}</span>
                <span class="monitor-step-name">{{ step.step_name }}</span>
                <span class="monitor-step-type">{{ getStepTypeLabel(step.step_type) }}</span>
              </div>
              <div class="monitor-step-meta">
                <span v-if="step.started_at">开始: {{ formatTime(step.started_at) }}</span>
                <span v-if="step.completed_at">完成: {{ formatTime(step.completed_at) }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="monitor-actions">
          <el-button
            v-if="canWrite && selectedExecution.status === 'waiting_approval'"
            type="primary"
            @click="approveExecution"
          >
            ✅ 审批通过
          </el-button>
          <el-button
            v-if="canWrite && (selectedExecution.status === 'running' || selectedExecution.status === 'waiting_approval')"
            type="danger"
            @click="cancelExecution"
          >
            🛑 取消执行
          </el-button>
          <el-button @click="refreshExecution">🔄 刷新状态</el-button>
        </div>
      </div>
    </el-dialog>

    <el-dialog
      v-model="showStepResultDialog"
      title="步骤执行结果"
      width="560px"
      class="dark-dialog"
      destroy-on-close
    >
      <div v-if="selectedStep" class="step-result-content">
        <div class="step-result-header">
          <span class="step-result-icon">{{ getStepStatusIcon(selectedStep.status) }}</span>
          <span class="step-result-name">{{ selectedStep.step_name }}</span>
          <span class="status-badge small" :style="{ color: getStatusColor(selectedStep.status), background: getStatusColor(selectedStep.status) + '15' }">
            {{ getStatusText(selectedStep.status) }}
          </span>
        </div>
        <div class="step-result-meta">
          <span v-if="selectedStep.started_at">开始: {{ formatTime(selectedStep.started_at) }}</span>
          <span v-if="selectedStep.completed_at">完成: {{ formatTime(selectedStep.completed_at) }}</span>
        </div>
        <div class="step-result-body">
          <div class="result-label">执行结果</div>
          <pre class="result-json">{{ JSON.stringify(selectedStep.result, null, 2) }}</pre>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.playbooks-page {
  position: relative;
  animation: page-enter 0.5s ease-out;
  will-change: opacity, transform;
  min-height: 100vh;
}

.playbooks-bg {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.bg-grid {
  position: absolute;
  top: 0; right: 0; bottom: 0; left: 0;
  background-image:
    linear-gradient(rgba(22, 93, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(22, 93, 255, 0.03) 1px, transparent 1px);
  background-size: 3.75rem 3.75rem;
  mask-image: radial-gradient(ellipse 80% 60% at 50% 30%, black 20%, transparent 70%);
}

.bg-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
}

.glow-1 {
  width: 25rem; height: 25rem;
  background: rgba(22, 93, 255, 0.08);
  top: -6.25rem; right: 10%;
  animation: glow-float 12s ease-in-out infinite;
  will-change: transform;
}

.glow-2 {
  width: 18.75rem; height: 18.75rem;
  background: rgba(82, 196, 26, 0.06);
  bottom: 10%; left: 5%;
  animation: glow-float 15s ease-in-out infinite reverse;
  will-change: transform;
}

/* glow-float uses global definition from tokens.css */

/* page-enter uses global definition from tokens.css */

.playbooks-page > *:not(.playbooks-bg) {
  position: relative;
  z-index: 1;
}

.playbooks-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-border-primary);
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.page-title {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  margin: 0;
  background: linear-gradient(135deg, var(--color-text-secondary) 0%, var(--color-primary-light) 50%, var(--color-text-secondary) 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: title-shimmer 4s ease-in-out infinite;
}

.page-subtitle {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin: 0;
  font-weight: 400;
}

/* title-shimmer uses global definition from tokens.css */

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.action-btn {
  padding: 0.375rem 0.875rem;
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-xs);
  transition: all 0.25s ease;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  white-space: nowrap;
  backdrop-filter: blur(8px);
  min-height: 44px;
}

.action-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: rgba(59, 130, 246, 0.5);
  box-shadow: var(--shadow-glow-primary-sm);
  color: var(--color-primary-lighter);
  transform: scale(1.02);
}

.action-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.action-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.action-btn.primary {
  background: var(--color-primary-hover);
  border-color: rgba(22, 93, 255, 0.4);
  color: var(--color-primary-lighter);
  font-weight: 600;
}

.action-btn.primary:hover {
  background: rgba(22, 93, 255, 0.3);
  border-color: rgba(59, 130, 246, 0.6);
  box-shadow: var(--shadow-glow-primary-md);
  color: #BFDBFE;
  transform: scale(1.02);
}

.content-layout {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: var(--panel-gap);
}

.panel {
  background: var(--gradient-glass);
  border-radius: var(--radius-lg);
  padding: 1.25rem;
  border: var(--card-border);
  backdrop-filter: blur(12px);
  animation: panel-enter 0.5s var(--ease-out) backwards;
  box-shadow: var(--shadow-card);
}

/* panel-enter uses global definition from tokens.css */

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.panel-title {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
  padding-left: 0.625rem;
  border-left: 3px solid var(--color-primary);
}

.loading-state {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.skeleton-row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem;
  background: rgba(15, 23, 42, 0.3);
  border-radius: var(--radius-md);
}

.skeleton-line {
  height: 0.875rem;
  background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 75%);
  background-size: 200% 100%;
  border-radius: var(--radius-sm);
  animation: skeleton-slide 1.5s ease-in-out infinite;
}

/* skeleton-slide uses global definition from tokens.css */

.skeleton-line.wide { width: 70%; }
.skeleton-line.medium { width: 55%; }

.playbook-table {
  width: 100%;
}

.table-header {
  display: flex;
  align-items: center;
  padding: 0.625rem 0.75rem;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  font-weight: 600;
  border-bottom: 1px solid var(--color-border-primary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.table-row {
  display: flex;
  align-items: center;
  padding: 0.875rem 0.75rem;
  border-bottom: 1px solid var(--color-border-primary);
  transition: all 0.2s var(--ease-out);
}

.table-row:hover {
  background: var(--color-bg-hover);
}

.table-row:last-child {
  border-bottom: none;
}

.col-name { flex: 2; min-width: 0; }
.col-category { width: 100px; }
.col-steps { width: 60px; text-align: center; }
.col-exec-count { width: 80px; text-align: center; }
.col-status { width: 100px; }
.col-author { width: 80px; color: var(--color-text-tertiary); font-size: var(--font-size-sm); }
.col-actions { width: 100px; display: flex; gap: 0.25rem; justify-content: flex-end; }

.pb-name {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pb-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: 0.125rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.category-tag {
  font-size: var(--font-size-xs);
  padding: 2px 0.5rem;
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border-radius: var(--radius-xs);
}

.steps-count {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.status-badge {
  font-size: var(--font-size-xs);
  padding: 2px 0.5rem;
  border-radius: var(--radius-sm);
  border: 1px solid;
  white-space: nowrap;
}

.status-badge.small {
  font-size: var(--font-size-xs);
  padding: 1px 0.375rem;
}

.action-icon-btn {
  width: 1.75rem;
  height: 1.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(22, 93, 255, 0.08);
  border: 1px solid var(--color-primary-hover);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: all 0.25s ease;
  padding: 0;
  backdrop-filter: blur(8px);
}

.action-icon-btn:hover {
  background: var(--color-primary-hover);
  border-color: rgba(59, 130, 246, 0.5);
  box-shadow: var(--shadow-glow-primary-sm);
  transform: scale(1.1);
}

.action-icon-btn:active {
  transform: scale(0.95);
}

.action-icon-btn.danger:hover {
  background: var(--color-error-glow);
  border-color: rgba(239, 68, 68, 0.5);
  box-shadow: var(--shadow-glow-error-sm);
}

.empty-state {
  text-align: center;
  padding: var(--spacing-xl) var(--spacing-lg);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
}

.empty-state.small {
  padding: var(--spacing-md);
  font-size: var(--font-size-sm);
}

.empty-icon {
  font-size: var(--font-size-3xl);
  margin-bottom: var(--spacing-sm);
  opacity: 0.6;
}

.execution-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.execution-item {
  padding: 0.75rem;
  background: rgba(15, 23, 42, 0.4);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.execution-item:hover {
  background: rgba(15, 23, 42, 0.6);
  border-color: rgba(22, 93, 255, 0.15);
}

.exec-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.375rem;
}

.exec-name {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 70%;
}

.exec-progress-bar {
  height: 4px;
  background: var(--color-border-primary);
  border-radius: var(--radius-xs);
  overflow: hidden;
  margin-bottom: 0.375rem;
}

.exec-progress-fill {
  height: 100%;
  border-radius: var(--radius-xs);
  transition: width 0.4s ease;
}

.exec-meta {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-xs);
  color: var(--color-text-disabled);
}

.steps-editor {
  width: 100%;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: rgba(15, 23, 42, 0.4);
  border-radius: var(--radius-md);
  margin-bottom: 0.5rem;
  border: 1px solid var(--color-border-primary);
}

.step-index {
  width: 1.5rem;
  height: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border-radius: 50%;
  font-size: var(--font-size-xs);
  font-weight: 700;
  flex-shrink: 0;
}

.step-controls {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.step-move-btn {
  width: 1.25rem;
  height: 0.875rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-hover);
  border: 1px solid var(--color-bg-active);
  border-radius: var(--radius-xs);
  color: var(--color-text-tertiary);
  cursor: pointer;
  font-size: var(--font-size-xs);
  padding: 0;
}

.step-move-btn:hover:not(:disabled) {
  background: var(--color-primary-glow);
  color: var(--color-primary-light);
}

.step-move-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.step-type-select { width: 140px; }

.step-name-input { flex: 1; }

.step-remove-btn {
  width: 1.5rem;
  height: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-hover);
  border-radius: var(--radius-sm);
  color: var(--color-error-light);
  cursor: pointer;
  font-size: var(--font-size-xs);
  flex-shrink: 0;
}

.step-remove-btn:hover {
  background: var(--color-error-hover);
}

.add-step-btn {
  padding: var(--spacing-xs) 0.75rem;
  background: var(--color-primary-bg);
  border: 1px dashed var(--color-primary-border);
  border-radius: var(--radius-sm);
  color: var(--color-primary-light);
  cursor: pointer;
  font-size: var(--font-size-xs);
  transition: all 0.2s var(--ease-out);
  width: 100%;
}

.add-step-btn:hover {
  background: var(--color-primary-hover);
}

.execute-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.execute-playbook-name {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.execute-playbook-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.execute-steps-preview {
  background: rgba(15, 23, 42, 0.4);
  border-radius: var(--radius-md);
  padding: 0.75rem;
  border: 1px solid var(--color-border-primary);
}

.execute-step-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-bottom: 0.5rem;
}

.execute-step-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0;
}

.execute-step-index {
  width: 1.25rem;
  height: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-glow);
  color: var(--color-primary-light);
  border-radius: 50%;
  font-size: var(--font-size-xs);
  font-weight: 700;
  flex-shrink: 0;
}

.execute-step-icon {
  font-size: var(--font-size-sm);
}

.execute-step-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.monitor-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.monitor-playbook-name {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.monitor-progress {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.progress-bar {
  height: 0.5rem;
  background: var(--color-border-primary);
  border-radius: 0.25rem;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 0.25rem;
  transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.monitor-steps {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.monitor-step {
  display: flex;
  align-items: flex-start;
  gap: 0;
  min-height: 3rem;
  position: relative;
}

.monitor-step.clickable {
  cursor: pointer;
}

.monitor-step.clickable:hover .monitor-step-content {
  background: rgba(15, 23, 42, 0.4);
}

.monitor-step-dot {
  width: 0.75rem;
  height: 0.75rem;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 0.5rem;
  margin-left: 0.5rem;
  position: relative;
  z-index: 1;
}

.monitor-step-line {
  width: 2px;
  flex-shrink: 0;
  margin-left: 0.5625rem;
  background: var(--color-border-primary);
  transform: translateX(-0.5px);
  position: absolute;
  top: 1.25rem;
  bottom: 0;
}

.monitor-step:last-child .monitor-step-line {
  display: none;
}

.monitor-step-content {
  flex: 1;
  padding: 0.375rem 0 0.75rem 0.875rem;
  min-width: 0;
  border-radius: var(--radius-sm);
  transition: background 0.2s ease;
}

.monitor-step-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.125rem;
}

.monitor-step-icon {
  font-size: var(--font-size-sm);
}

.monitor-step-name {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.monitor-step-type {
  font-size: var(--font-size-xs);
  color: var(--color-primary-light);
  background: var(--color-primary-bg);
  padding: 1px 0.375rem;
  border-radius: var(--radius-xs);
}

.monitor-step-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-disabled);
  display: flex;
  gap: 0.75rem;
}

.monitor-actions {
  display: flex;
  gap: var(--spacing-sm);
  padding-top: var(--spacing-md);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.step-result-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.step-result-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.step-result-icon {
  font-size: var(--font-size-lg);
}

.step-result-name {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-secondary);
  flex: 1;
}

.step-result-meta {
  display: flex;
  gap: 0.75rem;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.step-result-body {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.result-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.result-json {
  background: rgba(0, 0, 0, 0.25);
  border-radius: var(--radius-md);
  padding: 0.75rem;
  border: 1px solid var(--color-border-primary);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  overflow-x: auto;
  max-height: 12.5rem;
  overflow-y: auto;
  margin: 0;
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.dark-dialog :deep(.el-dialog) {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-primary);
}

.dark-dialog :deep(.el-dialog__header) {
  border-bottom: 1px solid var(--color-border-primary);
}

.dark-dialog :deep(.el-dialog__title) {
  color: var(--color-text-secondary);
}

.dark-form :deep(.el-form-item__label) {
  color: var(--color-text-tertiary);
}

.dark-form :deep(.el-input__wrapper),
.dark-form :deep(.el-textarea__inner) {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  box-shadow: none;
}

.dark-form :deep(.el-input__inner),
.dark-form :deep(.el-textarea__inner) {
  color: var(--color-text-secondary);
}

@media (max-width: 1200px) {
  .content-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .playbooks-header {
    flex-direction: column;
    gap: 0.75rem;
    align-items: flex-start;
  }
  .table-header { display: none; }
  .table-row {
    flex-wrap: wrap;
    gap: 0.375rem;
  }
  .col-name { flex: 1 1 100%; }
  .col-category, .col-steps, .col-exec-count, .col-status, .col-author {
    width: auto;
    flex: 0 0 auto;
  }
  .col-actions {
    width: auto;
    flex: 0 0 auto;
    margin-left: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .playbooks-page { animation: none; }
  .panel { animation: none; }
  .bg-glow { animation: none; }
  .page-title { animation: none; background-size: 100% auto; }
  .skeleton-line { animation: none; }
}
</style>
