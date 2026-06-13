<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

const props = defineProps<{
  message: ChatMessage
}>()

const displayedContent = ref('')
const isTyping = ref(false)
const isUser = computed(() => props.message.role === 'user')

let typingTimer: ReturnType<typeof setTimeout> | null = null

function startTyping() {
  if (isUser.value) {
    displayedContent.value = props.message.content
    return
  }

  isTyping.value = true
  displayedContent.value = ''
  const content = props.message.content
  let index = 0

  function typeNext() {
    if (index < content.length) {
      displayedContent.value += content[index]
      index++
      typingTimer = setTimeout(typeNext, 20)
    } else {
      isTyping.value = false
    }
  }

  typeNext()
}

function copyCode(code: string) {
  navigator.clipboard.writeText(code)
}

function formatContent(content: string) {
  // Simple markdown-like rendering: code blocks, lists, links
  let html = content
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_match, lang: string, code: string) => {
      return `<div class="code-block"><div class="code-header"><span>${lang || 'code'}</span><button class="copy-btn" data-code="${encodeURIComponent(code.trim())}">复制</button></div><pre><code>${escapeHtml(code.trim())}</code></pre></div>`
    })
    .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
    .replace(/\n/g, '<br/>')
  return html
}

function escapeHtml(str: string) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function handleCodeCopy(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.classList.contains('copy-btn')) {
    const code = decodeURIComponent(target.getAttribute('data-code') || '')
    copyCode(code)
    target.textContent = '已复制'
    setTimeout(() => {
      target.textContent = '复制'
    }, 2000)
  }
}

onMounted(() => {
  startTyping()
})

watch(
  () => props.message,
  () => {
    if (typingTimer) clearTimeout(typingTimer)
    startTyping()
  }
)
</script>

<template>
  <div class="bubble-card" :class="{ 'is-user': isUser, 'is-assistant': !isUser }">
    <div class="bubble-avatar" v-if="!isUser">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10" />
        <path d="M8 14s1.5 2 4 2 4-2 4-2" />
        <line x1="9" y1="9" x2="9.01" y2="9" />
        <line x1="15" y1="9" x2="15.01" y2="9" />
      </svg>
    </div>
    <div class="bubble-content" @click="handleCodeCopy">
      <div class="bubble-text" v-html="formatContent(displayedContent)" />
      <span v-if="isTyping" class="typing-cursor">|</span>
    </div>
    <div class="bubble-time">
      {{ new Date(message.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}
    </div>
  </div>
</template>

<style scoped>
.bubble-card {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-lg);
  align-items: flex-start;
}

.bubble-card.is-user {
  flex-direction: row-reverse;
}

.bubble-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--gradient-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.bubble-avatar svg {
  width: var(--font-size-xl);
  height: var(--font-size-xl);
  color: var(--color-white);
}

.bubble-content {
  max-width: 280px;
  padding: var(--spacing-sm) var(--spacing-lg);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-base);
  line-height: 1.6;
  word-break: break-word;
}

.is-user .bubble-content {
  background: var(--color-primary);
  color: var(--color-white);
  border-top-right-radius: var(--radius-xs);
}

.is-assistant .bubble-content {
  background: rgba(var(--color-white-rgb), 0.08);
  color: var(--color-text-secondary);
  border-top-left-radius: var(--radius-xs);
}

.bubble-time {
  font-size: var(--font-size-2xs);
  color: var(--color-text-quaternary);
  align-self: flex-end;
  flex-shrink: 0;
}

.typing-cursor {
  animation: blink 0.8s infinite;
  color: var(--color-info-light);
  font-weight: var(--font-weight-bold);
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.bubble-content :deep(.code-block) {
  margin: var(--spacing-sm) 0;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: rgba(var(--color-black-rgb), 0.3);
}

.bubble-content :deep(.code-header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-2xs) var(--spacing-md);
  background: rgba(var(--color-black-rgb), 0.2);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.bubble-content :deep(.copy-btn) {
  background: none;
  border: none;
  color: var(--color-info-light);
  cursor: pointer;
  font-size: var(--font-size-xs);
  padding: var(--spacing-3xs) var(--spacing-sm);
  border-radius: var(--radius-xs);
}

.bubble-content :deep(.copy-btn:hover) {
  background: rgba(var(--color-primary-rgb), 0.2);
}

.bubble-content :deep(pre) {
  margin: 0;
  padding: var(--spacing-md);
  overflow-x: auto;
  font-size: var(--font-size-sm);
  line-height: 1.5;
}

.bubble-content :deep(code) {
  font-family: 'Fira Code', 'Consolas', monospace;
}

.bubble-content :deep(.inline-code) {
  background: rgba(var(--color-black-rgb), 0.2);
  padding: var(--spacing-3xs) var(--spacing-2xs);
  border-radius: var(--radius-xs);
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: var(--font-size-sm);
}

.bubble-content :deep(ul) {
  padding-left: var(--spacing-lg);
  margin: var(--spacing-2xs) 0;
}

.bubble-content :deep(a) {
  color: var(--color-info-light);
  text-decoration: underline;
}
</style>
