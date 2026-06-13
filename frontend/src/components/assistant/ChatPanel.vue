<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { ElScrollbar } from 'element-plus'
import { api } from '@/utils/apiClient'
import BubbleCard from './BubbleCard.vue'
import VoiceInput from './VoiceInput.vue'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

const props = defineProps<{
  visible: boolean
  connected: boolean
}>()

const emit = defineEmits<{
  close: []
  send: [message: string]
}>()

const messages = ref<ChatMessage[]>([
  {
    role: 'assistant',
    content: '你好！我是智维AI助手，可以帮你处理网络运维相关的意图。输入 /help 查看可用指令。',
    timestamp: Date.now()
  }
])
const inputText = ref('')
const isLoading = ref(false)
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>()

function scrollToBottom() {
  nextTick(() => {
    if (scrollbarRef.value) {
      scrollbarRef.value.setScrollTop(99999)
    }
  })
}

function handleSend() {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return

  // Handle quick commands
  if (text.startsWith('/')) {
    handleCommand(text)
    inputText.value = ''
    return
  }

  messages.value.push({
    role: 'user',
    content: text,
    timestamp: Date.now()
  })
  inputText.value = ''
  scrollToBottom()
  fetchAIResponse(text)
  emit('send', text)
}

function handleCommand(cmd: string) {
  const command = cmd.toLowerCase()
  switch (command) {
    case '/help':
      messages.value.push({
        role: 'assistant',
        content: '可用指令：\n- /help - 显示帮助\n- /clear - 清空对话\n- /status - 查看系统状态',
        timestamp: Date.now()
      })
      break
    case '/clear':
      messages.value = []
      break
    case '/status':
      messages.value.push({
        role: 'assistant',
        content: `系统状态：\n- WebSocket: ${props.connected ? '已连接' : '未连接'}\n- 消息数: ${messages.value.length}`,
        timestamp: Date.now()
      })
      break
    default:
      messages.value.push({
        role: 'assistant',
        content: `未知指令: ${cmd}，输入 /help 查看可用指令`,
        timestamp: Date.now()
      })
  }
  scrollToBottom()
}

async function fetchAIResponse(userMessage: string) {
  isLoading.value = true
  try {
    const data = await api.post<{ reply: string }>('/api/v1/assistant/chat', {
      message: userMessage,
      history: messages.value.slice(-10)
    })
    messages.value.push({
      role: 'assistant',
      content: data.reply,
      timestamp: Date.now()
    })
  } catch {
    messages.value.push({
      role: 'assistant',
      content: '抱歉，请求处理失败，请稍后重试。',
      timestamp: Date.now()
    })
  } finally {
    isLoading.value = false
    scrollToBottom()
  }
}

function handleVoiceResult(text: string) {
  inputText.value = text
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

watch(
  () => props.visible,
  (val) => {
    if (val) {
      scrollToBottom()
    }
  }
)
</script>

<template>
  <transition name="slide">
    <div v-if="visible" class="chat-panel">
      <div class="chat-header">
        <div class="header-left">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="header-icon">
            <circle cx="12" cy="12" r="10" />
            <path d="M8 14s1.5 2 4 2 4-2 4-2" />
            <line x1="9" y1="9" x2="9.01" y2="9" />
            <line x1="15" y1="9" x2="15.01" y2="9" />
          </svg>
          <span class="header-title">智维AI助手</span>
          <span class="connection-dot" :class="{ connected }" />
        </div>
        <button class="close-btn" @click="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <ElScrollbar ref="scrollbarRef" class="chat-messages">
        <div class="messages-inner">
          <BubbleCard
            v-for="(msg, idx) in messages"
            :key="idx"
            :message="msg"
          />
          <div v-if="isLoading" class="loading-indicator">
            <span class="dot" />
            <span class="dot" />
            <span class="dot" />
          </div>
        </div>
      </ElScrollbar>

      <div class="chat-input">
        <textarea
          v-model="inputText"
          class="input-field"
          placeholder="输入消息，/help 查看指令..."
          rows="1"
          @keydown="handleKeydown"
        />
        <VoiceInput :disabled="isLoading" @result="handleVoiceResult" />
        <button class="send-btn" :disabled="!inputText.trim() || isLoading" @click="handleSend">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.chat-panel {
  position: fixed;
  right: var(--spacing-2xl);
  bottom: var(--spacing-2xl);
  width: 380px;
  height: 520px;
  background: rgba(var(--color-bg-base-rgb), 0.95);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-2xl);
  display: flex;
  flex-direction: column;
  z-index: 10000;
  box-shadow: 0 var(--spacing-sm) 40px rgba(0, 0, 0, 0.4);
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px var(--spacing-lg);
  border-bottom: 1px solid rgba(var(--color-white-rgb), 0.08);
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.header-icon {
  width: var(--font-size-xl);
  height: var(--font-size-xl);
  color: var(--color-info-light);
}

.header-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
}

.connection-dot {
  width: var(--spacing-sm);
  height: var(--spacing-sm);
  border-radius: 50%;
  background: var(--color-error);
}

.connection-dot.connected {
  background: var(--color-success);
}

.close-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--color-text-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(var(--color-white-rgb), 0.1);
  color: var(--color-text-secondary);
}

.close-btn svg {
  width: var(--font-size-lg);
  height: var(--font-size-lg);
}

.chat-messages {
  flex: 1;
  overflow: hidden;
}

.messages-inner {
  padding: var(--spacing-lg);
}

.loading-indicator {
  display: flex;
  gap: var(--spacing-2xs);
  padding: var(--spacing-sm) 0;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-info-light);
  animation: bounce 1.4s infinite ease-in-out both;
}

.dot:nth-child(1) { animation-delay: 0s; }
.dot:nth-child(2) { animation-delay: 0.16s; }
.dot:nth-child(3) { animation-delay: 0.32s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.chat-input {
  display: flex;
  align-items: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg);
  border-top: 1px solid rgba(var(--color-white-rgb), 0.08);
}

.input-field {
  flex: 1;
  background: rgba(var(--color-white-rgb), 0.06);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-md);
  padding: var(--spacing-sm) var(--spacing-md);
  color: var(--color-text-secondary);
  font-size: var(--font-size-base);
  resize: none;
  outline: none;
  font-family: inherit;
  line-height: 1.5;
  max-height: 80px;
}

.input-field::placeholder {
  color: var(--color-text-quaternary);
}

.input-field:focus {
  border-color: rgba(var(--color-primary-rgb), 0.5);
}

.send-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: var(--color-primary);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--color-white);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}

.send-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.send-btn svg {
  width: var(--font-size-xl);
  height: var(--font-size-xl);
}

.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
