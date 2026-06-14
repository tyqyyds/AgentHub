import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getUserRole } from '@/utils/userRole'

export interface AssistantAction {
  type: string
  label: string
  params: Record<string, any>
}

export interface WorkflowStep {
  id: string
  agent: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'warning' | 'waiting_confirm'
  title: string
  detail?: string
  timestamp?: string
}

export interface AssistantMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  actions?: AssistantAction[]
  status: 'sending' | 'sent' | 'error' | 'streaming'
  workflow?: WorkflowStep[]
  requiresConfirm?: boolean
  confirmType?: 'danger' | 'normal'
  confirmId?: string
  contextEntities?: Record<string, string>
  isStreaming?: boolean
  llmProvider?: string
  isDanger?: boolean
  dangerAction?: AssistantAction
}

export type PanelState = 'dormant' | 'bubble' | 'chat' | 'open'
export type ThinkingState = 'idle' | 'thinking' | 'executing'
export type BallState = 'breathing' | 'thinking' | 'alert' | 'executing' | 'intercept'
export type PanelMode = 'bubble' | 'chat' | 'split'

export interface DialogueStateData {
  sessionId: string
  turnCount: number
  currentIntent: string | null
  entities: Record<string, any>
  intentHistory: Array<{ from: string; to: string; timestamp: number }>
}

export interface PlanStep {
  step_index: number
  description: string
  tool_name: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'waiting_confirm'
  result_preview?: string
  error?: string
}

export interface PlanExecuteState {
  planId: string
  goal: string
  status: 'idle' | 'generating' | 'executing' | 'paused' | 'completed' | 'failed'
  steps: PlanStep[]
  confirmLevel: 'low' | 'medium' | 'high'
  currentStepIndex: number
  report: {
    conclusion: string
    successCount: number
    failureCount: number
    duration: number
  } | null
}

export interface WizardInfo {
  wizard_type: string
  name: string
  description: string
  icon: string
  category: string
  param_schema: Array<{
    name: string
    label: string
    field_type: string
    required: boolean
    default?: any
    options?: string[]
  }>
  confirm_level: 'low' | 'medium' | 'high'
}

export const useAssistantStore = defineStore('assistant', () => {
  const panelState = ref<PanelState>('dormant')
  const thinkingState = ref<ThinkingState>('idle')
  const isHidden = ref(false)
  const messages = ref<AssistantMessage[]>([])
  const alertActive = ref(false)
  const alertMessage = ref('')
  const executionProgress = ref(0)
  const panelMode = ref<PanelMode>('bubble')
  const currentWorkflow = ref<WorkflowStep[]>([])
  const visitedPages = ref<Record<string, boolean>>({})
  const pendingConfirmId = ref<string | null>(null)
  const contextEntities = ref<Record<string, string>>({})
  const llmAvailable = ref(false)
  const isStreamingActive = ref(false)
  const dialogueState = ref<DialogueStateData>({
    sessionId: '',
    turnCount: 0,
    currentIntent: null,
    entities: {},
    intentHistory: []
  })

  const planExecuteState = ref<PlanExecuteState>({
    planId: '',
    goal: '',
    status: 'idle',
    steps: [],
    confirmLevel: 'low',
    currentStepIndex: 0,
    report: null
  })

  const availableWizards = ref<WizardInfo[]>([])

  const isOpen = computed(() => panelState.value === 'chat' || panelState.value === 'open')
  const isBubbleVisible = computed(() => panelState.value === 'bubble')
  const ballState = computed<BallState>(() => {
    if (alertActive.value) return 'alert'
    if (pendingConfirmId.value) return 'intercept'
    if (thinkingState.value === 'executing') return 'executing'
    if (thinkingState.value === 'thinking') return 'thinking'
    return 'breathing'
  })

  let msgCounter = 0
  const genId = () => `msg_${Date.now()}_${++msgCounter}`

  let progressIntervalId: ReturnType<typeof setInterval> | null = null
  let progressTimeoutId: ReturnType<typeof setTimeout> | null = null

  const clearProgressTimers = () => {
    if (progressIntervalId) { clearInterval(progressIntervalId); progressIntervalId = null }
    if (progressTimeoutId) { clearTimeout(progressTimeoutId); progressTimeoutId = null }
  }

  const addMessage = (msg: Omit<AssistantMessage, 'id'>) => {
    const id = genId()
    const enriched: AssistantMessage = { ...msg, id }
    if (msg.isDanger && msg.role === 'assistant' && !msg.confirmId) {
      enriched.requiresConfirm = true
      enriched.confirmType = 'danger'
      enriched.confirmId = id
      pendingConfirmId.value = id
    }
    messages.value.push(enriched)
    if (messages.value.length > 100) {
      messages.value = messages.value.slice(-80)
    }
  }

  const updateLastAssistantMessage = (updates: Partial<AssistantMessage>) => {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].role === 'assistant') {
        messages.value[i] = { ...messages.value[i], ...updates }
        break
      }
    }
  }

  const updateWorkflowStep = (stepId: string, updates: Partial<WorkflowStep>) => {
    const idx = currentWorkflow.value.findIndex(s => s.id === stepId)
    if (idx !== -1) {
      currentWorkflow.value[idx] = { ...currentWorkflow.value[idx], ...updates }
      updateLastAssistantMessage({ workflow: [...currentWorkflow.value] })
    }
  }

  const setWorkflow = (steps: WorkflowStep[]) => {
    currentWorkflow.value = steps
  }

  const clearWorkflow = () => {
    currentWorkflow.value = []
  }

  const sendMessage = async (text: string) => {
    if (!text.trim()) return
    addMessage({ role: 'user', content: text.trim(), status: 'sent' })
    thinkingState.value = 'thinking'

    try {
      const { apiClient, api } = await import('@/utils/apiClient')
      const currentRoute = window.location.pathname

      const resp = await apiClient.post(api.assistant.chat, {
        message: text.trim(),
        context: {
          route: currentRoute,
          role: getUserRole()
        }
      })

      const data = resp.data
      thinkingState.value = 'idle'

      let workflowSteps: WorkflowStep[] = []
      if (data.workflow && data.workflow.length > 0) {
        workflowSteps = data.workflow.map((w: any) => ({
          id: w.id || `step_${Math.random().toString(36).slice(2, 8)}`,
          agent: w.agent || 'Agent',
          status: w.status || 'pending',
          title: w.title || '',
          detail: w.detail,
          timestamp: new Date().toISOString()
        }))
      } else if (data.progress && data.progress.length > 0) {
        workflowSteps = (data.progress as string[]).map((p: string, i: number) => ({
          id: `step_${i}`,
          agent: ['IntentParser', 'ConflictDetector', 'PolicyPlanner', 'ExecutionAgent'][i] || 'Agent',
          status: i < (data.progress || []).length - 1 ? 'completed' : 'running',
          title: p,
          timestamp: new Date().toISOString()
        }))
      }

      if (data.intent_type === 'control') {
        thinkingState.value = 'executing'
        executionProgress.value = 0
        clearProgressTimers()
        const totalSteps = workflowSteps.length || 3
        progressIntervalId = setInterval(() => {
          executionProgress.value = Math.min(executionProgress.value + Math.random() * 20, 95)
          if (executionProgress.value >= 95 && progressIntervalId) { clearInterval(progressIntervalId); progressIntervalId = null }
        }, 800)
        progressTimeoutId = setTimeout(() => {
          clearProgressTimers()
          executionProgress.value = 100
          thinkingState.value = 'idle'
          setTimeout(() => { executionProgress.value = 0 }, 1000)
        }, totalSteps * 2000 + 1000)
      }

      const isDanger = data.is_danger === true || (data.intent_type === 'control' && _isDangerAction(text.trim()))
      const dangerConfirmId = isDanger ? genId() : undefined
      if (isDanger && dangerConfirmId) {
        pendingConfirmId.value = dangerConfirmId
      }
      addMessage({
        role: 'assistant',
        content: data.content || '',
        actions: data.actions || [],
        status: 'sent',
        workflow: workflowSteps.length > 0 ? workflowSteps : undefined,
        requiresConfirm: isDanger,
        confirmType: isDanger ? 'danger' : undefined,
        confirmId: dangerConfirmId,
        contextEntities: data.entities || undefined
      })

      if (data.entities) {
        contextEntities.value = { ...contextEntities.value, ...data.entities }
      }

      dialogueState.value = {
        sessionId: dialogueState.value.sessionId || `sess_${Date.now()}`,
        turnCount: dialogueState.value.turnCount + 2,
        currentIntent: data.intent_type || null,
        entities: { ...dialogueState.value.entities, ...(data.entities || {}) },
        intentHistory: dialogueState.value.intentHistory
      }
    } catch (e: any) {
      thinkingState.value = 'idle'
      addMessage({
        role: 'assistant',
        content: '抱歉，处理您的请求时出现了错误，请稍后重试。',
        status: 'sent'
      })
    }
  }

  const _isDangerAction = (text: string): boolean => {
    const dangerKeywords = ['删除', '重启', '隔离', '关闭端口', 'shutdown', 'delete', 'restart', 'isolate', '切断', '断开']
    return dangerKeywords.some(k => text.includes(k))
  }

  const checkLlmStatus = async () => {
    try {
      const { authFetch, api } = await import('@/utils/apiClient')
      const resp = await authFetch(api.assistant.llmStatus)
      if (resp.ok) {
        const raw = await resp.json()
        const data = raw.data || raw
        llmAvailable.value = data?.zhipu?.available || data?.deepseek?.available || false
      } else {
        llmAvailable.value = false
      }
    } catch {
      llmAvailable.value = false
    }
  }

  const sendMessageStream = async (text: string) => {
    if (!text.trim() || isStreamingActive.value) return
    addMessage({ role: 'user', content: text.trim(), status: 'sent' })
    thinkingState.value = 'thinking'
    isStreamingActive.value = true

    const streamMsgId = genId()
    messages.value.push({
      id: streamMsgId,
      role: 'assistant',
      content: '',
      status: 'streaming',
      isStreaming: true
    })

    try {
      const { api, authFetch } = await import('@/utils/apiClient')
      const currentRoute = window.location.pathname

      const resp = await authFetch(api.assistant.chat + '/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text.trim(),
          context: {
            route: currentRoute,
            role: getUserRole()
          }
        })
      })

      if (!resp.ok || !resp.body) {
        throw new Error(`Stream request failed: ${resp.status}`)
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const jsonStr = line.slice(6).trim()
          if (!jsonStr) continue

          try {
            const chunk = JSON.parse(jsonStr)
            if (chunk.error) {
              const msgIdx = messages.value.findIndex(m => m.id === streamMsgId)
              if (msgIdx !== -1) {
                messages.value[msgIdx] = { ...messages.value[msgIdx], content: messages.value[msgIdx].content + `\n\n❌ 错误：${chunk.error}`, status: 'error', isStreaming: false }
              }
              break
            }
            if (chunk.content) {
              const msgIdx = messages.value.findIndex(m => m.id === streamMsgId)
              if (msgIdx !== -1) {
                messages.value[msgIdx] = { ...messages.value[msgIdx], content: messages.value[msgIdx].content + chunk.content }
              }
            }
            if (chunk.done) {
              const msgIdx = messages.value.findIndex(m => m.id === streamMsgId)
              if (msgIdx !== -1) {
                messages.value[msgIdx] = { ...messages.value[msgIdx], status: 'sent', isStreaming: false, llmProvider: chunk.provider || 'unknown' }
              }
            }
          } catch {
            continue
          }
        }
      }

      thinkingState.value = 'idle'
    } catch (e: any) {
      thinkingState.value = 'idle'
      const msgIdx = messages.value.findIndex(m => m.id === streamMsgId)
      if (msgIdx !== -1) {
        messages.value[msgIdx] = { ...messages.value[msgIdx], content: messages.value[msgIdx].content || '抱歉，AI 服务暂时不可用，请稍后重试。', status: 'error', isStreaming: false }
      }
    } finally {
      isStreamingActive.value = false
    }
  }

  const confirmDangerAction = (confirmId: string) => {
    pendingConfirmId.value = null
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].confirmId === confirmId) {
        messages.value[i].requiresConfirm = false
        break
      }
    }
    window.dispatchEvent(new CustomEvent('assistant:confirm_danger', { detail: { confirmId } }))
  }

  const cancelDangerAction = (confirmId: string) => {
    pendingConfirmId.value = null
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].confirmId === confirmId) {
        messages.value[i].requiresConfirm = false
        messages.value[i].content += '\n\n❌ 操作已取消。'
        break
      }
    }
  }

  const openChat = () => { panelState.value = 'chat' }
  const closeChat = () => { panelState.value = 'dormant' }
  const minimizeChat = () => { panelState.value = 'dormant' }
  const showBubble = () => { panelState.value = 'bubble' }
  const dismissBubble = () => { if (panelState.value === 'bubble') panelState.value = 'dormant' }
  const hideAssistant = () => { isHidden.value = true; panelState.value = 'dormant' }
  const showAssistant = () => { isHidden.value = false; panelState.value = 'bubble' }

  const triggerAlert = (msg: string) => {
    alertActive.value = true
    alertMessage.value = msg
    addMessage({
      role: 'system',
      content: `🚨 ${msg}`,
      status: 'sent'
    })
  }

  const dismissAlert = () => {
    alertActive.value = false
    alertMessage.value = ''
  }

  const setPanelMode = (mode: PanelMode) => {
    panelMode.value = mode
    if (mode === 'split') {
      panelState.value = 'open'
    } else if (mode === 'chat') {
      panelState.value = 'chat'
    }
  }

  const sendReactMessage = async (text: string) => {
    if (!text.trim()) return
    addMessage({ role: 'user', content: text.trim(), status: 'sent' })
    thinkingState.value = 'thinking'

    try {
      const { api, authFetch } = await import('@/utils/apiClient')
      const currentRoute = window.location.pathname

      const resp = await authFetch(api.assistant.reactChat, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text.trim(),
          context: {
            route: currentRoute,
            role: getUserRole()
          }
        })
      })

      if (!resp.ok) throw new Error(`React chat failed: ${resp.status}`)
      const raw = await resp.json()
      const data = raw.data || raw
      thinkingState.value = 'idle'

      if (data.workflow && data.workflow.length > 0) {
        currentWorkflow.value = data.workflow
      }

      if (data.requires_approval && data.approval_data) {
        pendingConfirmId.value = data.approval_data?.approval_id || genId()
      }

      if (data.frontend_actions && data.frontend_actions.length > 0) {
        window.dispatchEvent(new CustomEvent('assistant:agentic_actions', {
          detail: { actions: data.frontend_actions }
        }))
      }

      addMessage({
        role: 'assistant',
        content: data.content || '',
        status: 'sent',
        workflow: data.workflow,
        requiresConfirm: data.requires_approval,
        confirmType: data.is_danger ? 'danger' : 'normal',
        confirmId: data.requires_approval ? (pendingConfirmId.value ?? undefined) : undefined,
        contextEntities: data.entities,
        llmProvider: data.provider || 'unknown'
      })
    } catch (e: any) {
      thinkingState.value = 'idle'
      addMessage({
        role: 'assistant',
        content: '抱歉，推理引擎暂时不可用，请稍后重试。',
        status: 'error'
      })
    }
  }

  const approveReactAction = async (approvalId: string, approved: boolean, userCode?: string) => {
    try {
      const { api, authFetch } = await import('@/utils/apiClient')
      const resp = await authFetch(api.assistant.reactApprove, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approval_id: approvalId, approved, user_code: userCode })
      })

      if (!resp.ok) throw new Error(`Approve failed: ${resp.status}`)
      const data = await resp.json()
      pendingConfirmId.value = null

      if (data.frontend_actions && data.frontend_actions.length > 0) {
        window.dispatchEvent(new CustomEvent('assistant:agentic_actions', {
          detail: { actions: data.frontend_actions }
        }))
      }

      if (data.workflow && data.workflow.length > 0) {
        currentWorkflow.value = data.workflow
      }

      addMessage({
        role: 'assistant',
        content: data.content || (approved ? '操作已执行完成' : '操作已取消'),
        status: 'sent',
        workflow: data.workflow
      })
    } catch {
      addMessage({
        role: 'assistant',
        content: '审批操作失败，请重试。',
        status: 'error'
      })
    }
  }
  const clearMessages = () => {
    messages.value = []
    pendingConfirmId.value = null
    contextEntities.value = {}
  }

  const markPageVisited = (page: string) => { visitedPages.value = { ...visitedPages.value, [page]: true } }
  const isPageVisited = (page: string) => !!visitedPages.value[page]

  let notifUnsubscribe: (() => void) | null = null

  const initNotificationListener = () => {
    if (notifUnsubscribe) return
    import('@/stores/notification').then(mod => {
      const notifStore = mod.useNotificationStore()
      if (notifStore && notifStore.$onAction) {
        notifUnsubscribe = notifStore.$onAction(({ name, args }) => {
          if (name === 'addNotification') {
            const notif = args[0]
            if (notif && notif.type === 'alert') {
              triggerAlert(notif.message || '检测到紧急事件')
            }
          }
        })
      }
    }).catch(() => {})
  }

  const sendPlanExecute = async (goal: string) => {
    if (!goal.trim()) return
    addMessage({ role: 'user', content: goal.trim(), status: 'sent' })
    thinkingState.value = 'executing'
    planExecuteState.value = {
      planId: '',
      goal: goal.trim(),
      status: 'generating',
      steps: [],
      confirmLevel: 'low',
      currentStepIndex: 0,
      report: null
    }

    try {
      const { api, authFetch } = await import('@/utils/apiClient')
      const currentRoute = window.location.pathname

      const resp = await authFetch(api.knowledge.planExecute, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: goal.trim(),
          context: { route: currentRoute, role: 'admin' }
        })
      })

      if (!resp.ok) throw new Error(`Plan execute failed: ${resp.status}`)
      const data = await resp.json()
      thinkingState.value = 'idle'

      const resultData = data.data || data
      planExecuteState.value.planId = resultData.plan_id || ''
      planExecuteState.value.status = resultData.plan_status === 'paused' ? 'paused' :
        resultData.plan_status === 'success' ? 'completed' :
        resultData.plan_status === 'failed' ? 'failed' : 'executing'

      addMessage({
        role: 'assistant',
        content: resultData.content || '计划已生成',
        status: 'sent'
      })
    } catch {
      thinkingState.value = 'idle'
      planExecuteState.value.status = 'failed'
      addMessage({
        role: 'assistant',
        content: '计划执行失败，请稍后重试。',
        status: 'error'
      })
    }
  }

  const confirmPlanStep = async (planId: string, stepIndex: number, approved: boolean) => {
    try {
      const { authFetch } = await import('@/utils/apiClient')
      await authFetch('/api/v1/knowledge/plan-execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_id: planId, step_index: stepIndex, approved })
      })
    } catch {
      addMessage({ role: 'assistant', content: '确认操作失败，请重试。', status: 'error' })
    }
  }

  const fetchWizards = async () => {
    try {
      const { authFetch } = await import('@/utils/apiClient')
      const resp = await authFetch(api.knowledge.wizards)
      if (resp.ok) {
        const data = await resp.json()
        const resultData = data.data || data
        availableWizards.value = resultData.wizards || []
      }
    } catch {
      availableWizards.value = []
    }
  }

  const executeWizard = async (wizardType: string, params: Record<string, any>) => {
    thinkingState.value = 'executing'
    try {
      const { authFetch } = await import('@/utils/apiClient')
      const resp = await authFetch(api.knowledge.wizardExecute, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wizard_type: wizardType, params })
      })

      if (!resp.ok) throw new Error(`Wizard execute failed: ${resp.status}`)
      const data = await resp.json()
      thinkingState.value = 'idle'

      const resultData = data.data || data
      addMessage({
        role: 'assistant',
        content: resultData.goal || '向导已执行',
        status: 'sent'
      })
    } catch {
      thinkingState.value = 'idle'
      addMessage({
        role: 'assistant',
        content: '向导执行失败，请稍后重试。',
        status: 'error'
      })
    }
  }

  return {
    panelState, thinkingState, isHidden, messages, alertActive, alertMessage,
    executionProgress, panelMode, currentWorkflow, visitedPages, pendingConfirmId,
    contextEntities, llmAvailable, isStreamingActive, dialogueState,
    planExecuteState, availableWizards,
    isOpen, isBubbleVisible, ballState,
    addMessage, updateLastAssistantMessage, updateWorkflowStep, setWorkflow,
    clearWorkflow, clearMessages, sendMessage, sendMessageStream, sendReactMessage, approveReactAction,
    sendPlanExecute, confirmPlanStep, fetchWizards, executeWizard,
    checkLlmStatus, confirmDangerAction, cancelDangerAction,
    openChat, closeChat, minimizeChat, showBubble, dismissBubble,
    hideAssistant, showAssistant, triggerAlert, dismissAlert,
    setPanelMode, markPageVisited, isPageVisited, initNotificationListener
  }
})
