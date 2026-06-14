<template>
  <div
    v-show="isOpen"
    class="chat-panel"
    :class="[
      `panel-${store.panelMode}`,
      { 'is-mobile': isMobile, 'is-dragging': isDragging }
    ]"
    :style="panelStyle"
  >
    <div
      class="panel-header"
      @mousedown="onDragStart"
    >
      <div class="header-center">
        <span class="ai-panel-title"><span class="title-icon">✦</span> 智维 AI 助手</span>
        <span
          class="status-dot"
          :class="statusDotClass"
        />
        <span v-if="store.llmAvailable" class="llm-badge">🧠 GLM</span>
      </div>
      <div class="header-actions">
        <button type="button" class="header-btn" :class="{ active: store.panelMode === 'split' }" @click.stop="toggleSplitMode" :title="store.panelMode === 'split' ? '退出分屏' : '分屏模式'" :aria-label="store.panelMode === 'split' ? '退出分屏' : '分屏模式'">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="5" height="12" rx="1" stroke="currentColor" stroke-width="1.2"/><rect x="8" y="1" width="5" height="12" rx="1" stroke="currentColor" stroke-width="1.2"/></svg>
        </button>
        <button type="button" class="header-btn react-btn" :class="{ active: reactMode }" @click.stop="toggleReactMode" :title="reactMode ? '普通模式' : 'ReAct推理模式'" :aria-label="reactMode ? '退出推理模式' : '推理模式'">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="7" cy="7" r="2.5" stroke="currentColor" stroke-width="1.2"/><ellipse cx="7" cy="7" rx="6" ry="3" stroke="currentColor" stroke-width="1.0" opacity="0.6"/><ellipse cx="7" cy="7" rx="3" ry="6" stroke="currentColor" stroke-width="1.0" opacity="0.6"/><ellipse cx="7" cy="7" rx="6" ry="3" stroke="currentColor" stroke-width="1.0" opacity="0.6" transform="rotate(60 7 7)"/><ellipse cx="7" cy="7" rx="6" ry="3" stroke="currentColor" stroke-width="1.0" opacity="0.6" transform="rotate(120 7 7)"/></svg>
        </button>
            <button
              type="button"
              class="header-btn plan-btn"
              :class="{ active: planExecuteMode }"
              @click.stop="togglePlanExecuteMode"
              title="Plan-Execute编排模式"
              aria-label="Plan-Execute编排模式"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="1" y="1" width="4" height="4" rx="1" stroke="currentColor" stroke-width="1.1"/>
                <rect x="9" y="1" width="4" height="4" rx="1" stroke="currentColor" stroke-width="1.1"/>
                <rect x="1" y="9" width="4" height="4" rx="1" stroke="currentColor" stroke-width="1.1"/>
                <rect x="9" y="9" width="4" height="4" rx="1" stroke="currentColor" stroke-width="1.1"/>
                <line x1="5" y1="3" x2="9" y2="3" stroke="currentColor" stroke-width="0.8"/>
                <line x1="3" y1="5" x2="3" y2="9" stroke="currentColor" stroke-width="0.8"/>
                <line x1="11" y1="5" x2="11" y2="9" stroke="currentColor" stroke-width="0.8"/>
              </svg>
            </button>
        <button type="button" class="header-btn clear-btn" @click.stop="clearChat" title="清空对话" aria-label="清空对话">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 4h8l-.7 8.1a1 1 0 01-1 .9H4.7a1 1 0 01-1-.9L3 4z" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><path d="M5.5 2h3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><path d="M2 4h10" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><path d="M6 6.5v3.5M8 6.5v3.5" stroke="currentColor" stroke-width="0.9" stroke-linecap="round"/></svg>
        </button>
        <button type="button" class="header-btn minimize-btn" @click.stop="minimize" aria-label="最小化" title="最小化">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 7h8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
        </button>
        <button type="button" class="header-btn close-btn" @click.stop="hide" aria-label="关闭" title="关闭">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
        </button>
      </div>
    </div>

    <div v-if="hasContextEntities" class="context-panel" :class="{ collapsed: contextCollapsed }">
      <div class="context-header" @click="contextCollapsed = !contextCollapsed">
        <span class="context-label">📎 上下文</span>
        <span class="context-toggle">{{ contextCollapsed ? '▸' : '▾' }}</span>
      </div>
      <div v-show="!contextCollapsed" class="context-body">
        <span
          v-for="(value, key) in store.contextEntities"
          :key="key"
          class="context-tag"
        >
          {{ key }}: {{ value }}
        </span>
      </div>
    </div>

    <ProactivePanel />

    <div ref="messagesContainer" class="messages-area">
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="message-wrapper"
        :class="`msg-${msg.role}`"
      >
        <div v-if="msg.role === 'system'" class="msg-system">
          <span class="msg-system-text">{{ msg.content }}</span>
        </div>

        <div v-else-if="msg.role === 'user'" class="msg-user">
          <div class="msg-bubble msg-bubble-user">{{ msg.content }}</div>
        </div>

        <div v-else-if="msg.role === 'assistant'" class="msg-assistant">
          <div class="msg-bubble msg-bubble-assistant">
            <div class="msg-content" v-html="renderContent(msg.content)" />
            <span v-if="msg.isStreaming" class="streaming-cursor">▌</span>

            <div v-if="msg.role === 'assistant' && !msg.isStreaming && msg.content" class="msg-feedback">
              <button
                type="button"
                class="feedback-btn feedback-positive"
                :class="{ active: feedbackMap[msg.id] === 'positive' }"
                @click="handleFeedback(msg, 'positive')"
                aria-label="有用"
                title="这个回答有帮助"
              >
                👍
              </button>
              <button
                type="button"
                class="feedback-btn feedback-negative"
                :class="{ active: feedbackMap[msg.id] === 'negative' }"
                @click="handleFeedback(msg, 'negative')"
                aria-label="没用"
                title="这个回答没有帮助"
              >
                👎
              </button>
            </div>

            <div v-if="msg.workflow && msg.workflow.length" class="workflow-timeline">
              <div
                v-for="(step, idx) in msg.workflow"
                :key="step.id"
                class="workflow-step"
                :class="`step-${step.status}`"
              >
                <div class="step-indicator">
                  <span class="step-icon">{{ stepStatusIcon(step.status) }}</span>
                  <span
                    v-if="idx < msg.workflow!.length - 1"
                    class="step-line"
                    :class="{ completed: step.status === 'completed' }"
                  />
                </div>
                <div class="step-body">
                  <div class="step-title">
                    <span class="step-agent">{{ step.agent }}</span>
                    <span class="step-name">{{ step.title }}</span>
                  </div>
                  <div v-if="step.detail" class="step-detail">{{ step.detail }}</div>
                </div>
              </div>
            </div>

            <div
              v-if="msg.requiresConfirm && msg.confirmType === 'danger' && msg.confirmId"
              class="danger-confirm-panel"
            >
              <div class="danger-header">
                <span class="danger-icon">⚠️</span>
                <span class="danger-text">此操作具有高风险，请确认后继续</span>
              </div>
              <label class="danger-checkbox-row">
                <input
                  v-model="dangerConfirmedMap[msg.confirmId]"
                  type="checkbox"
                  class="danger-checkbox"
                />
                <span>我已了解操作风险</span>
              </label>
              <div class="danger-actions">
                <button
                  type="button"
                  class="danger-btn danger-confirm-btn"
                  :disabled="!dangerConfirmedMap[msg.confirmId]"
                  @click="handleDangerConfirm(msg.confirmId)"
                  aria-label="确认执行"
                >
                  确认执行
                </button>
                <button type="button" class="danger-btn danger-cancel-btn" @click="handleDangerCancel(msg.confirmId)" aria-label="取消">
                  取消
                </button>
              </div>
            </div>

            <div v-if="msg.actions && msg.actions.length" class="msg-actions">
              <button
                type="button"
                v-for="(action, ai) in msg.actions"
                :key="ai"
                class="action-btn"
                @click="executeAction(action)"
                :aria-label="action.label || '执行操作'"
              >
                {{ action.label }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="isThinking" class="message-wrapper msg-assistant">
        <div class="msg-bubble msg-bubble-assistant">
          <div class="thinking-indicator">
            <span class="thinking-dot" />
            <span class="thinking-dot" />
            <span class="thinking-dot" />
          </div>
        </div>
      </div>
    </div>

    <div v-if="quickActions.length" class="quick-actions-bar">
      <button
        type="button"
        v-for="(qa, qi) in quickActions"
        :key="qi"
        class="quick-action-tag"
        @click="handleQuickAction(qa)"
        :aria-label="qa.label"
      >
        {{ qa.label }}
      </button>
    </div>

          <div v-if="showWizardBar" class="wizard-bar">
            <span class="wizard-bar-label">🧙 运维向导</span>
            <button
              type="button"
              v-for="wizard in store.availableWizards"
              :key="wizard.wizard_type"
              class="wizard-tag"
              @click="openWizard(wizard)"
              :aria-label="wizard.name"
            >
              {{ wizard.icon }} {{ wizard.name }}
            </button>
          </div>

    <div class="input-area">
      <textarea
        ref="inputEl"
        v-model="inputText"
        class="chat-input"
        :placeholder="inputPlaceholder"
        rows="1"
        @input="autoResize"
        @keydown.enter.exact.prevent="handleSend"
      />
      <VoiceInput :disabled="isThinking" @transcript="onVoiceTranscript" />
      <button
        type="button"
        class="send-btn"
        :class="{ active: inputText.trim().length > 0 }"
        :disabled="!inputText.trim() || isThinking"
        @click="handleSend"
        aria-label="发送"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      </button>
    </div>

        <div v-if="activeWizard" class="wizard-modal-overlay" @click.self="closeWizard">
          <div class="wizard-modal">
            <div class="wizard-modal-header">
              <span>{{ activeWizard.icon }} {{ activeWizard.name }}</span>
              <button type="button" class="header-btn" @click="closeWizard" aria-label="关闭">✕</button>
            </div>
            <div class="wizard-modal-body">
              <p class="wizard-desc">{{ activeWizard.description }}</p>
              <div v-for="field in activeWizard.param_schema" :key="field.name" class="wizard-field">
                <label class="wizard-field-label">
                  {{ field.label }}
                  <span v-if="field.required" class="required-mark">*</span>
                </label>
                <select
                  v-if="field.options && field.options.length"
                  v-model="wizardParams[field.name]"
                  class="wizard-select"
                >
                  <option value="" disabled>请选择</option>
                  <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
                </select>
                <input
                  v-else
                  v-model="wizardParams[field.name]"
                  type="text"
                  class="wizard-input"
                  :placeholder="field.label"
                />
              </div>
            </div>
            <div class="wizard-modal-footer">
              <button type="button" class="wizard-cancel-btn" @click="closeWizard">取消</button>
              <button
                type="button"
                class="wizard-execute-btn"
                :disabled="!isWizardParamsValid"
                @click="runWizard"
              >
                执行向导
              </button>
            </div>
          </div>
        </div>
        <WizardRunner ref="wizardRunner" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import DOMPurify from 'dompurify'
import { useAssistantStore, type AssistantAction, type AssistantMessage } from '@/stores/assistant'
import { useActionEngine } from '@/composables/useActionEngine'
import { useAssistantContext, type QuickAction } from '@/composables/useAssistantContext'
import ProactivePanel from './ProactivePanel.vue'
import VoiceInput from './VoiceInput.vue'
import WizardRunner from './WizardRunner.vue'

const store = useAssistantStore()
const { executeAction } = useActionEngine()
const { currentContext } = useAssistantContext()

const isOpen = computed(() => store.isOpen)
const messages = computed(() => store.messages)
const isThinking = computed(() => store.thinkingState === 'thinking' || store.thinkingState === 'executing')

const inputText = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLTextAreaElement | null>(null)
const contextCollapsed = ref(false)
const dangerConfirmedMap = ref<Record<string, boolean>>({})
const feedbackMap = ref<Record<string, string>>({})
const planExecuteMode = ref(false)
const activeWizard = ref<any>(null)
const wizardParams = ref<Record<string, any>>({})
const wizardRunner = ref<InstanceType<typeof WizardRunner> | null>(null)

const handleFeedback = async (msg: AssistantMessage, feedbackType: 'positive' | 'negative') => {
  if (feedbackMap.value[msg.id]) return
  feedbackMap.value[msg.id] = feedbackType

  try {
    const { authFetch, api } = await import('@/utils/apiClient')
    await authFetch(api.knowledge.feedback, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: messages.value.find(m => m.role === 'user' && messages.value.indexOf(m) < messages.value.indexOf(msg))?.content || '',
        answer: msg.content,
        feedback_type: feedbackType,
      })
    })
  } catch {
    feedbackMap.value[msg.id] = ''
  }
}

const showWizardBar = computed(() => store.availableWizards.length > 0)

const togglePlanExecuteMode = () => {
  planExecuteMode.value = !planExecuteMode.value
  if (planExecuteMode.value) {
    reactMode.value = false
    store.fetchWizards()
  }
}

const openWizard = (wizard: any) => {
  activeWizard.value = wizard
  wizardParams.value = {}
  for (const field of wizard.param_schema) {
    wizardParams.value[field.name] = field.default ?? ''
  }
}

const closeWizard = () => {
  activeWizard.value = null
  wizardParams.value = {}
}

const isWizardParamsValid = computed(() => {
  if (!activeWizard.value) return false
  return activeWizard.value.param_schema
    .filter((f: any) => f.required)
    .every((f: any) => wizardParams.value[f.name] && String(wizardParams.value[f.name]).trim() !== '')
})

const runWizard = async () => {
  if (!activeWizard.value) return
  const wizardType = activeWizard.value.wizard_type
  const params = { ...wizardParams.value }
  closeWizard()
  await store.executeWizard(wizardType, params)
}

const handlePlanConfirm = (approved: boolean) => {
  const planId = store.planExecuteState.planId
  const stepIndex = store.planExecuteState.currentStepIndex
  store.confirmPlanStep(planId, stepIndex, approved)
}

const onVoiceTranscript = (text: string) => {
  if (text) {
    inputText.value = text
    nextTick(() => handleSend())
  }
}

const isMobile = ref(false)
const checkMobile = () => {
  isMobile.value = window.innerWidth <= 768
}

const panelPos = ref({ x: window.innerWidth - 440, y: 80 })
const isDragging = ref(false)
let dragOffset = { x: 0, y: 0 }

const panelStyle = computed(() => {
  if (isMobile.value) return {}
  if (store.panelMode === 'split') return {}
  return {
    left: `${panelPos.value.x}px`,
    top: `${panelPos.value.y}px`
  }
})

const onDragStart = (e: MouseEvent) => {
  if (isMobile.value) return
  isDragging.value = true
  dragOffset = {
    x: e.clientX - panelPos.value.x,
    y: e.clientY - panelPos.value.y
  }
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup', onDragEnd)
}

const onDragMove = (e: MouseEvent) => {
  if (!isDragging.value) return
  const newX = e.clientX - dragOffset.x
  const newY = e.clientY - dragOffset.y
  panelPos.value = {
    x: Math.max(0, Math.min(newX, window.innerWidth - 420)),
    y: Math.max(0, Math.min(newY, window.innerHeight - 200))
  }
}

const onDragEnd = () => {
  isDragging.value = false
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
}

const statusDotClass = computed(() => {
  if (store.alertActive) return 'status-alert'
  if (store.thinkingState === 'thinking' || store.thinkingState === 'executing') return 'status-thinking'
  return 'status-online'
})

const hasContextEntities = computed(() => {
  return Object.keys(store.contextEntities).length > 0
})

const quickActions = computed(() => {
  return currentContext.value?.quickActions || []
})

const inputPlaceholder = computed(() => {
  return '输入消息...'
})

const handleSend = async () => {
  const text = inputText.value.trim()
  if (!text || isThinking.value || store.isStreamingActive) return
  inputText.value = ''
  if (inputEl.value) {
    inputEl.value.style.height = 'auto'
  }
  if (planExecuteMode.value) {
    await store.sendPlanExecute(text)
    return
  }
  if (reactMode.value) {
    await store.sendReactMessage(text)
  } else if (store.llmAvailable) {
    await store.sendMessageStream(text)
  } else {
    await store.sendMessage(text)
  }
}

const handleQuickAction = (qa: QuickAction) => {
  const action: AssistantAction = {
    type: qa.type,
    label: qa.label,
    params: (qa.params || {}) as Record<string, any>
  }
  executeAction(action)
}

const minimize = () => store.minimizeChat()
const hide = () => store.hideAssistant()
const clearChat = () => {
  store.clearMessages()
  store.addMessage({ role: 'system', content: '对话已清空', status: 'sent' })
}

const reactMode = ref(false)

const toggleSplitMode = () => {
  if (store.panelMode === 'split') {
    store.setPanelMode('chat')
  } else {
    store.setPanelMode('split')
  }
}

const toggleReactMode = () => {
  reactMode.value = !reactMode.value
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  store.checkLlmStatus()
})

const autoResize = () => {
  if (inputEl.value) {
    inputEl.value.style.height = 'auto'
    inputEl.value.style.height = Math.min(inputEl.value.scrollHeight, 120) + 'px'
  }
}

const renderContent = (content: string) => {
  let html = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 代码块 (```...```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, _lang, code) => {
    return `<pre class="msg-code-block"><code>${code.trim()}</code></pre>`
  })

  // 行内代码 (`...`)
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')

  // 表格 (| ... | ... |)
  html = html.replace(/((?:\|[^\n]+\|\n)+)/g, (tableBlock) => {
    const rows = tableBlock.trim().split('\n')
    if (rows.length < 2) return tableBlock
    const isSeparatorRow = (row: string) => /^\|[\s\-:|]+\|$/.test(row.trim())
    let headerDone = false
    let tableHtml = '<table class="msg-table">'
    for (const row of rows) {
      if (isSeparatorRow(row)) { headerDone = true; continue }
      const cells = row.split('|').filter((_, i, arr) => i > 0 && i < arr.length - 1).map(c => c.trim())
      if (cells.length === 0) continue
      const tag = !headerDone ? 'th' : 'td'
      tableHtml += '<tr>' + cells.map(c => `<${tag}>${c}</${tag}>`).join('') + '</tr>'
      if (!headerDone) headerDone = true
    }
    tableHtml += '</table>'
    return tableHtml
  })

  // 加粗 (**...**)
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')

  // 有序列表 (1. 2. 3.)
  html = html.replace(/((?:^\d+\.\s+[^\n]+\n?)+)/gm, (listBlock) => {
    const items = listBlock.trim().split('\n').map(line => {
      const text = line.replace(/^\d+\.\s+/, '')
      return `<li>${text}</li>`
    })
    return `<ol class="msg-ol">${items.join('')}</ol>`
  })

  // 无序列表 (- ... 或 * ...)  注意：避免匹配 **加粗** 行首的 *
  html = html.replace(/((?:^[\-]\s+[^\n]+\n?)+)/gm, (listBlock) => {
    const items = listBlock.trim().split('\n').map(line => {
      const text = line.replace(/^[\-]\s+/, '')
      return `<li>${text}</li>`
    })
    return `<ul class="msg-ul">${items.join('')}</ul>`
  })
  html = html.replace(/((?:^\*\s+[^\n]+\n?)+)/gm, (listBlock) => {
    const items = listBlock.trim().split('\n').map(line => {
      const text = line.replace(/^\*\s+/, '')
      return `<li>${text}</li>`
    })
    return `<ul class="msg-ul">${items.join('')}</ul>`
  })

  // 换行
  html = html.replace(/\n/g, '<br/>')

  // 清理列表前后多余的br
  html = html.replace(/<br\/>(<(?:ol|ul) class="msg-[ou]l")>/g, '<$1>')
  html = html.replace(/<\/(?:ol|ul)><br\/>/g, '</$1>')

  return DOMPurify.sanitize(html, {
    ADD_TAGS: ['table', 'thead', 'tbody', 'tr', 'th', 'td', 'pre', 'ol', 'ul', 'li', 'code', 'strong'],
    ADD_ATTR: ['class']
  })
}

const stepStatusIcon = (status: string) => {
  const map: Record<string, string> = {
    pending: '⏳',
    running: '🔄',
    completed: '✅',
    failed: '❌',
    warning: '⚠️',
    waiting_confirm: '🔒'
  }
  return map[status] || '⏳'
}

const handleDangerConfirm = (confirmId: string) => {
  store.confirmDangerAction(confirmId)
  delete dangerConfirmedMap.value[confirmId]
}

const handleDangerCancel = (confirmId: string) => {
  store.cancelDangerAction(confirmId)
  delete dangerConfirmedMap.value[confirmId]
}

const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

watch(messages, () => {
  scrollToBottom()
}, { deep: true })

watch(isOpen, (val) => {
  if (val) {
    scrollToBottom()
    checkMobile()
    if (isMobile.value) {
      panelPos.value = { x: 0, y: 0 }
    } else {
      panelPos.value = {
        x: Math.min(panelPos.value.x, window.innerWidth - 420),
        y: Math.min(panelPos.value.y, window.innerHeight - 200)
      }
    }
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
})
</script>

<style scoped>
.chat-panel {
  position: fixed;
  width: 420px;
  height: 75vh;
  min-height: 400px;
  max-height: 720px;
  background: var(--gradient-glass-strong);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: var(--radius-lg);
  border: var(--card-border);
  box-shadow: var(--shadow-modal);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.3s var(--ease-out), height 0.3s var(--ease-out), right 0.3s var(--ease-out), top 0.3s var(--ease-out), border-radius 0.3s var(--ease-out);
}

.chat-panel.panel-split {
  width: 30vw !important;
  min-width: 360px;
  height: 100vh;
  max-height: 100vh;
  top: 0 !important;
  right: 0 !important;
  left: auto !important;
  border-radius: 0;
  border-left: 1px solid var(--color-border-secondary);
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.3);
  z-index: 9999;
  transition: none;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.chat-panel.is-dragging {
  user-select: none;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem var(--spacing-md);
  background: var(--color-bg-input);
  border-bottom: 1px solid var(--color-border-primary);
  cursor: move;
  flex-shrink: 0;
}

.header-center {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.ai-panel-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-bold);
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: 1px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  flex-shrink: 0;
}

.ai-panel-title .title-icon {
  font-size: var(--font-size-base);
  -webkit-text-fill-color: initial;
  color: var(--color-primary-light);
  animation: icon-glow 2.5s ease-in-out infinite;
  filter: drop-shadow(0 0 4px var(--color-primary-glow));
}

@keyframes icon-glow {
  0%, 100% { opacity: 0.7; filter: drop-shadow(0 0 3px rgba(22, 93, 255, 0.3)); }
  50% { opacity: 1; filter: drop-shadow(0 0 8px rgba(22, 93, 255, 0.7)); }
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.llm-badge {
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-md);
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
  color: var(--color-primary-light);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.5px;
}

.streaming-cursor {
  display: inline;
  color: var(--color-primary-lighter);
  animation: blink 0.8s step-end infinite;
  font-weight: bold;
  margin-left: 2px;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.status-dot.status-online {
  background: var(--color-success);
  box-shadow: var(--shadow-glow-success);
}

.status-dot.status-thinking {
  background: var(--color-warning);
  box-shadow: var(--shadow-glow-warning);
  animation: pulse-dot 1.5s ease-in-out infinite;
}

.status-dot.status-alert {
  background: var(--color-error);
  box-shadow: var(--shadow-glow-error);
  animation: pulse-dot 0.8s ease-in-out infinite;
}

.header-actions {
  display: flex;
  gap: var(--spacing-xs);
}

.header-btn {
  width: 30px;
  height: 30px;
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  background: var(--color-bg-hover);
  color: var(--color-text-disabled);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--button-transition);
  position: relative;
  overflow: hidden;
}

.header-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  opacity: 0;
  transition: opacity 0.2s var(--ease-out);
}

.header-btn:hover {
  color: var(--color-text-secondary);
  border-color: var(--color-border-primary);
  transform: translateY(-1px);
}

.header-btn:active {
  transform: translateY(0) scale(0.92);
}

.header-btn.active {
  background: var(--color-primary-bg);
  border-color: var(--color-primary-border);
  color: var(--color-primary-light);
  box-shadow: var(--shadow-glow-primary);
}

.header-btn.active:hover {
  background: var(--color-primary-hover);
  color: var(--color-primary-light);
}

.react-btn:hover {
  color: #c084fc;
  border-color: rgba(192, 132, 252, 0.2);
  background: rgba(192, 132, 252, 0.08);
}

.react-btn.active {
  background: rgba(192, 132, 252, 0.15);
  border-color: rgba(192, 132, 252, 0.3);
  color: #c084fc;
  box-shadow: 0 0 8px rgba(192, 132, 252, 0.15);
}

.react-btn.active:hover {
  background: rgba(192, 132, 252, 0.25);
  color: #d8b4fe;
}

.clear-btn:hover {
  color: #fbbf24;
  border-color: rgba(251, 191, 36, 0.2);
  background: rgba(251, 191, 36, 0.08);
}

.minimize-btn:hover {
  color: #34d399;
  border-color: rgba(52, 211, 153, 0.2);
  background: rgba(52, 211, 153, 0.08);
}

.close-btn:hover {
  background: var(--color-error-bg);
  border-color: var(--color-error-border);
  color: #f87171;
  box-shadow: var(--shadow-glow-error);
}

.close-btn:active {
  background: var(--color-error-hover);
}

.context-panel {
  border-bottom: 1px solid var(--color-border-primary);
  background: var(--color-bg-input);
  flex-shrink: 0;
}

.context-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.context-header:hover {
  color: var(--color-text-secondary);
}

.context-label {
  font-weight: 500;
}

.context-toggle {
  font-size: var(--font-size-xs);
}

.context-body {
  padding: 0 var(--spacing-md) 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.context-tag {
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
  color: var(--color-primary-light);
  font-size: 0.6875rem;
  white-space: nowrap;
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: var(--content-padding);
  display: flex;
  flex-direction: column;
  gap: var(--panel-gap);
  scroll-behavior: smooth;
}

.messages-area::-webkit-scrollbar {
  width: 4px;
}

.messages-area::-webkit-scrollbar-track {
  background: transparent;
}

.messages-area::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.2);
  border-radius: var(--radius-sm);
}

.message-wrapper {
  display: flex;
  flex-direction: column;
}

.msg-system {
  display: flex;
  justify-content: center;
}

.msg-system-text {
  font-size: var(--font-size-xs);
  color: var(--color-text-disabled);
  padding: var(--spacing-xs) 0.75rem;
  border-radius: var(--radius-md);
  background: var(--color-bg-hover);
}

.msg-user {
  display: flex;
  justify-content: flex-end;
}

.msg-bubble-user {
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  padding: 10px 14px;
  border-radius: var(--radius-xl) var(--radius-xl) var(--radius-sm) var(--radius-xl);
  max-width: 80%;
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  word-break: break-word;
  box-shadow: var(--shadow-glow-primary);
}

.msg-assistant {
  display: flex;
  justify-content: flex-start;
}

.msg-bubble-assistant {
  background: var(--color-bg-glass-strong);
  border: 1px solid var(--color-border-primary);
  color: var(--color-text-secondary);
  padding: 0.75rem var(--spacing-md);
  border-radius: var(--radius-xl) var(--radius-xl) var(--radius-xl) var(--radius-sm);
  max-width: 88%;
  font-size: var(--font-size-base);
  line-height: var(--line-height-relaxed);
  word-break: break-word;
}

.msg-content :deep(code) {
  background: rgba(0, 0, 0, 0.3);
  padding: 2px 0.375rem;
  border-radius: var(--radius-sm);
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: var(--font-size-sm);
  color: #f0abfc;
}

.msg-content :deep(strong) {
  color: var(--color-text-primary);
  font-weight: 600;
}

.msg-content :deep(.msg-table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: var(--font-size-xs);
}

.msg-content :deep(.msg-table th) {
  background: rgba(22, 93, 255, 0.15);
  color: var(--color-primary-light);
  padding: 6px 10px;
  text-align: left;
  border: 1px solid var(--color-border-primary);
  font-weight: var(--font-weight-semibold);
  white-space: nowrap;
}

.msg-content :deep(.msg-table td) {
  padding: 5px 10px;
  border: 1px solid var(--color-border-primary);
  color: var(--color-text-secondary);
}

.msg-content :deep(.msg-table tr:hover td) {
  background: rgba(255, 255, 255, 0.03);
}

.msg-content :deep(.msg-ol) {
  margin: 6px 0;
  padding-left: 1.5em;
  color: var(--color-text-secondary);
}

.msg-content :deep(.msg-ol li) {
  margin-bottom: 4px;
  line-height: 1.6;
}

.msg-content :deep(.msg-ul) {
  margin: 6px 0;
  padding-left: 1.5em;
  color: var(--color-text-secondary);
  list-style-type: disc;
}

.msg-content :deep(.msg-ul li) {
  margin-bottom: 4px;
  line-height: 1.6;
}

.msg-content :deep(.msg-code-block) {
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  margin: 8px 0;
  overflow-x: auto;
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: var(--font-size-xs);
  line-height: 1.5;
  color: var(--color-text-secondary);
}

.msg-content :deep(.msg-code-block code) {
  background: none;
  padding: 0;
  border-radius: 0;
  color: inherit;
  font-size: inherit;
}

.workflow-timeline {
  margin-top: 0.75rem;
  padding-top: 10px;
  border-top: 1px solid var(--color-border-primary);
  display: flex;
  flex-direction: column;
  gap: 0;
}

.workflow-step {
  display: flex;
  gap: 10px;
  min-height: 36px;
}

.step-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 24px;
  flex-shrink: 0;
}

.step-icon {
  font-size: var(--font-size-base);
  line-height: 24px;
  z-index: 1;
}

.step-line {
  width: 2px;
  flex: 1;
  min-height: 12px;
  background: var(--color-border-primary);
  margin: 2px 0;
}

.step-line.completed {
  background: var(--color-success-border);
}

.step-body {
  padding-bottom: var(--spacing-sm);
  flex: 1;
  min-width: 0;
}

.step-title {
  display: flex;
  align-items: baseline;
  gap: 0.375rem;
  flex-wrap: wrap;
}

.step-agent {
  font-size: 0.6875rem;
  color: var(--color-text-tertiary);
  font-weight: var(--font-weight-medium);
}

.step-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.step-detail {
  font-size: var(--font-size-xs);
  color: var(--color-text-disabled);
  margin-top: 2px;
}

.workflow-step.step-running .step-icon {
  animation: spin 1.5s linear infinite;
}

.danger-confirm-panel {
  margin-top: 0.75rem;
  padding: 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-error-border);
  background: var(--color-error-bg);
}

.danger-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: 10px;
}

.danger-icon {
  font-size: var(--font-size-lg);
}

.danger-text {
  font-size: var(--font-size-sm);
  color: var(--color-error-light);
  font-weight: var(--font-weight-medium);
}

.danger-checkbox-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: 0.75rem;
  cursor: pointer;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.danger-checkbox {
  width: 16px;
  height: 16px;
  accent-color: var(--color-error);
  cursor: pointer;
}

.danger-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.danger-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  border: none;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: var(--button-transition);
}

.danger-confirm-btn {
  background: var(--color-error-hover);
  color: var(--color-text-primary);
}

.danger-confirm-btn:disabled {
  background: rgba(239, 68, 68, 0.3);
  cursor: not-allowed;
  color: rgba(255, 255, 255, 0.5);
}

.danger-confirm-btn:not(:disabled):hover {
  background: var(--color-error);
}

.danger-cancel-btn {
  background: var(--color-bg-hover);
  color: var(--color-text-tertiary);
}

.danger-cancel-btn:hover {
  background: var(--color-bg-active);
  color: var(--color-text-secondary);
}

.msg-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-top: 10px;
}

.action-btn {
  padding: 5px 0.75rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-primary-border);
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: var(--button-transition);
}

.action-btn:hover {
  background: var(--color-primary-hover);
  border-color: rgba(22, 93, 255, 0.6);
}

.thinking-indicator {
  display: flex;
  gap: 5px;
  padding: var(--spacing-xs) 0;
}

.thinking-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-text-tertiary);
  animation: thinking-bounce 1.4s ease-in-out infinite;
}

.thinking-dot:nth-child(2) {
  animation-delay: 0.2s;
}

.thinking-dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes thinking-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

.quick-actions-bar {
  display: flex;
  gap: 0.375rem;
  padding: var(--spacing-sm) var(--spacing-md);
  overflow-x: auto;
  flex-shrink: 0;
  border-top: 1px solid var(--color-border-primary);
}

.quick-actions-bar::-webkit-scrollbar {
  display: none;
}

.quick-action-tag {
  padding: 5px 0.75rem;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-primary);
  background: var(--color-bg-hover);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  white-space: nowrap;
  cursor: pointer;
  transition: var(--button-transition);
  flex-shrink: 0;
}

.quick-action-tag:hover {
  background: var(--color-primary-bg);
  border-color: var(--color-primary-border);
  color: var(--color-primary-light);
}

.input-area {
  display: flex;
  align-items: flex-end;
  gap: var(--spacing-sm);
  padding: 0.75rem var(--spacing-md);
  border-top: 1px solid var(--color-border-primary);
  background: var(--color-bg-input);
  flex-shrink: 0;
}

.chat-input {
  flex: 1;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  padding: var(--input-padding);
  color: var(--color-text-secondary);
  font-size: var(--font-size-md);
  line-height: var(--line-height-normal);
  resize: none;
  outline: none;
  max-height: 120px;
  font-family: inherit;
  transition: border-color 0.2s var(--ease-out), box-shadow 0.2s var(--ease-out);
}

.chat-input::placeholder {
  color: var(--color-text-disabled);
}

.chat-input:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
}

.send-btn {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  border: none;
  background: var(--color-primary-bg);
  color: var(--color-text-disabled);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--button-transition);
  flex-shrink: 0;
}

.send-btn.active {
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-glow-primary);
}

.send-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.send-btn.active:hover:not(:disabled) {
  background: var(--gradient-primary-hover);
  transform: scale(1.05);
}

.chat-panel.is-mobile {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  width: 100%;
  height: 70vh;
  max-height: none;
  border-radius: var(--radius-full) var(--radius-full) 0 0;
  transition: opacity 0.3s var(--ease-out), transform 0.35s var(--ease-spring);
}

.chat-panel.is-mobile .panel-header {
  cursor: default;
}

.chat-panel.is-mobile .chat-input {
  font-size: var(--font-size-md);
}

.chat-panel.is-mobile .header-center {
  flex: 1;
  justify-content: center;
}

.chat-panel.is-mobile .header-actions {
  flex-shrink: 0;
}

.chat-panel.is-mobile .header-btn {
  width: 36px;
  height: 36px;
}

.chat-panel.is-mobile .header-btn svg {
  width: 16px;
  height: 16px;
}

.chat-panel.is-mobile .msg-bubble-user,
.chat-panel.is-mobile .msg-bubble-assistant {
  max-width: 92%;
  font-size: var(--font-size-md);
}

.chat-panel.is-mobile .quick-action-tag {
  padding: var(--spacing-sm) 14px;
  font-size: var(--font-size-sm);
  min-height: 40px;
}

.chat-panel.is-mobile .send-btn {
  width: 44px;
  height: 44px;
}

.chat-panel.is-mobile .danger-btn {
  min-height: var(--button-min-height-touch);
  padding: 10px 18px;
}

.chat-panel.is-mobile .action-btn {
  min-height: 40px;
  padding: 0.375rem 14px;
}

@media (min-width: 769px) and (max-width: 1024px) {
  .chat-panel:not(.panel-split) {
    width: 380px;
  }

  .chat-panel:not(.panel-split) .msg-bubble-user,
  .chat-panel:not(.panel-split) .msg-bubble-assistant {
    max-width: 85%;
  }
}

@media (max-width: 480px) {
  .chat-panel.is-mobile {
    height: 80vh;
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  }

  .chat-panel.is-mobile .panel-header {
    padding: 10px 0.75rem;
  }

  .chat-panel.is-mobile .ai-panel-title {
    font-size: var(--font-size-sm);
  }

  .chat-panel.is-mobile .messages-area {
    padding: 0.75rem;
  }

  .chat-panel.is-mobile .input-area {
    padding: 10px 0.75rem;
    padding-bottom: calc(10px + env(safe-area-inset-bottom, 0px));
  }
}

@media (prefers-reduced-motion: reduce) {
  .chat-panel {
    transition: none;
  }

  .chat-panel.panel-split {
    transition: none;
  }

  .chat-panel.is-mobile {
    transition: none;
  }

  .thinking-dot {
    animation: none;
  }

  .ai-panel-title .title-icon {
    animation: none;
  }

  .status-dot.status-thinking,
  .status-dot.status-alert {
    animation: none;
  }

  .streaming-cursor {
    animation: none;
  }

  .workflow-step.step-running .step-icon {
    animation: none;
  }

  .header-btn,
  .action-btn,
  .quick-action-tag,
  .danger-btn,
  .chat-input {
    transition: none;
  }

  .header-btn:hover {
    transform: none;
  }

  .header-btn:active {
    transform: none;
  }

  .header-btn.active {
    box-shadow: none;
  }

  .close-btn:hover {
    box-shadow: none;
  }

  .send-btn.active:hover:not(:disabled) {
    transform: none;
  }
}
.msg-feedback {
  display: flex;
  gap: 0.25rem;
  margin-top: 6px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.msg-bubble-assistant:hover .msg-feedback {
  opacity: 1;
}

.feedback-btn {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  font-size: var(--font-size-base);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  padding: 0;
}

.feedback-btn:hover {
  background: var(--color-bg-hover);
  border-color: var(--color-border-primary);
}

.feedback-btn.active.feedback-positive {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
}

.feedback-btn.active.feedback-negative {
  background: var(--color-error-bg);
  border-color: var(--color-error-border);
}

.plan-btn:hover {
  color: var(--color-success);
  border-color: var(--color-success-border);
  background: var(--color-success-bg);
}

.plan-btn.active {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
  color: var(--color-success);
  box-shadow: var(--shadow-glow-success);
}

.wizard-bar {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: var(--spacing-sm) var(--spacing-md);
  overflow-x: auto;
  flex-shrink: 0;
  border-top: 1px solid var(--color-border-primary);
}

.wizard-bar-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  white-space: nowrap;
  flex-shrink: 0;
}

.wizard-tag {
  padding: 5px 0.75rem;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-success-border);
  background: var(--color-success-bg);
  color: var(--color-success);
  font-size: var(--font-size-xs);
  white-space: nowrap;
  cursor: pointer;
  transition: var(--button-transition);
  flex-shrink: 0;
}

.wizard-tag:hover {
  background: var(--color-success-hover);
  border-color: rgba(82, 196, 26, 0.5);
}

.wizard-modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--modal-overlay-bg);
  backdrop-filter: blur(var(--modal-backdrop-blur));
  -webkit-backdrop-filter: blur(var(--modal-backdrop-blur));
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  animation: wizard-overlay-in 0.2s var(--ease-out);
}

@keyframes wizard-overlay-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

.wizard-modal {
  width: 400px;
  max-width: 90vw;
  background: var(--color-bg-elevated);
  border: var(--card-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-modal);
  animation: wizard-modal-in 0.25s var(--ease-out);
}

@keyframes wizard-modal-in {
  from { opacity: 0; transform: scale(0.95) translateY(8px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

.wizard-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem var(--spacing-md);
  border-bottom: 1px solid var(--color-border-primary);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-semibold);
}

.wizard-modal-body {
  padding: var(--spacing-md);
}

.wizard-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-md);
}

.wizard-field {
  margin-bottom: var(--spacing-sm);
}

.wizard-field-label {
  display: block;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}

.required-mark {
  color: var(--color-error);
}

.wizard-input,
.wizard-select {
  width: 100%;
  padding: var(--input-padding);
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  outline: none;
  transition: border-color 0.2s var(--ease-out), box-shadow 0.2s var(--ease-out);
}

.wizard-input:focus,
.wizard-select:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
}

.wizard-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-top: 1px solid var(--color-border-primary);
}

.wizard-cancel-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  border: none;
  background: var(--color-bg-hover);
  color: var(--color-text-tertiary);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: var(--button-transition);
}

.wizard-cancel-btn:hover {
  background: var(--color-bg-active);
  color: var(--color-text-secondary);
}

.wizard-execute-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  border: none;
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  box-shadow: var(--shadow-glow-primary);
}

.wizard-execute-btn:disabled {
  background: var(--color-primary-bg);
  cursor: not-allowed;
  box-shadow: none;
  color: var(--color-text-disabled);
}

.wizard-execute-btn:not(:disabled):hover {
  background: var(--gradient-primary-hover);
  transform: translateY(-1px);
}
</style>
