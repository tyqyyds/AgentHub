<template>
  <div v-show="visible" class="ai-bubble-card" :class="{'bubble-hidden': !visible}" :style="bubbleStyle">
    <div class="bubble-header">
      <span class="bubble-icon">{{ context?.icon }}</span>
      <span class="bubble-title">{{ context?.title }}</span>
      <button type="button" class="bubble-close" @click="dismiss" aria-label="关闭">✕</button>
    </div>
    <p class="bubble-desc">{{ context?.description }}</p>
    <div class="bubble-actions">
      <button type="button" class="bubble-btn primary" @click="openChat" aria-label="查看详情">查看详情</button>
      <button type="button" class="bubble-btn ghost" @click="dismiss" aria-label="忽略">忽略</button>
    </div>
    <div v-if="context?.quickActions?.length" class="bubble-tags">
      <button
        type="button"
        v-for="qa in context.quickActions"
        :key="qa.label"
        class="bubble-tag"
        :aria-label="qa.label"
        @click="handleQuickAction(qa)"
      >{{ qa.label }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, ref, onMounted, onUnmounted, inject } from 'vue'
import { useAssistantStore } from '@/stores/assistant'
import { useAssistantContext, type QuickAction } from '@/composables/useAssistantContext'
import { useActionEngine, type AssistantAction } from '@/composables/useActionEngine'
import { ballPositionKey } from './injectionKeys'

const store = useAssistantStore()
const { currentContext } = useAssistantContext()
const { executeAction } = useActionEngine()

const visible = computed(() => store.panelState === 'bubble' && currentContext.value !== null)
const context = computed(() => currentContext.value)

const injectedBallPosition = inject(ballPositionKey, ref({ x: window.innerWidth - 70, y: window.innerHeight / 2 }))
const windowWidth = ref(window.innerWidth)

const bubbleStyle = computed(() => {
  const ballX = injectedBallPosition.value.x
  const ballY = injectedBallPosition.value.y
  const w = windowWidth.value
  const isLeftSide = ballX < w / 2
  if (isLeftSide) {
    return {
      left: `${ballX + 68}px`,
      top: `${ballY}px`,
      transform: 'translateY(-50%)'
    }
  }
  return {
    right: `${w - ballX + 12}px`,
    top: `${ballY}px`,
    transform: 'translateY(-50%)'
  }
})

let autoHideTimer: ReturnType<typeof setTimeout> | null = null

watch(visible, (v) => {
  if (v) {
    if (autoHideTimer) clearTimeout(autoHideTimer)
    autoHideTimer = setTimeout(() => {
      store.dismissBubble()
    }, 8000)
  } else {
    if (autoHideTimer) { clearTimeout(autoHideTimer); autoHideTimer = null }
  }
})

const dismiss = () => {
  store.dismissBubble()
}

const openChat = () => {
  store.openChat()
}

const handleQuickAction = (qa: QuickAction) => {
  store.openChat()
  const action: AssistantAction = { type: qa.type, label: qa.label, params: (qa.params || {}) as Record<string, any> }
  executeAction(action)
}

const onResize = () => {
  windowWidth.value = window.innerWidth
}

onMounted(() => {
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  if (autoHideTimer) clearTimeout(autoHideTimer)
})
</script>

<style scoped>
.ai-bubble-card {
  position: fixed;
  z-index: 9998;
  width: 280px;
  background: var(--gradient-glass-strong);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: var(--card-border);
  border-radius: var(--radius-lg);
  padding: var(--content-padding);
  box-shadow: var(--shadow-card);
  transition: opacity 0.3s var(--ease-out), transform 0.3s var(--ease-spring);
  animation: bubble-in 0.3s var(--ease-spring);
}

@keyframes bubble-in {
  from { opacity: 0; transform: translateY(-50%) translateX(12px) scale(0.92); }
  to { opacity: 1; transform: translateY(-50%) translateX(0) scale(1); }
}

.ai-bubble-card.bubble-hidden {
  opacity: 0;
  pointer-events: none;
  transform: translateY(-50%) translateX(20px) scale(0.9);
}

.bubble-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

.bubble-icon {
  font-size: var(--font-size-lg);
}

.bubble-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  flex: 1;
}

.bubble-close {
  background: none;
  border: none;
  color: var(--color-text-disabled);
  font-size: var(--font-size-base);
  cursor: pointer;
  padding: 2px var(--spacing-xs);
  border-radius: var(--radius-sm);
  transition: all 0.2s var(--ease-out);
  min-width: 44px;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.bubble-close:hover {
  color: var(--color-text-secondary);
  background: var(--color-bg-active);
}

.bubble-close:active {
  background: var(--color-primary-bg);
}

.bubble-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: var(--line-height-normal);
  margin: 0 0 0.75rem 0;
}

.bubble-actions {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: 10px;
}

.bubble-btn {
  padding: 0.375rem 14px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  cursor: pointer;
  border: none;
  transition: var(--button-transition);
  min-height: 44px;
}

.bubble-btn.primary {
  background: var(--gradient-primary);
  color: white;
  box-shadow: var(--shadow-glow-primary);
}

.bubble-btn.primary:hover {
  background: var(--gradient-primary-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(22, 93, 255, 0.3);
}

.bubble-btn.primary:active {
  transform: translateY(0) scale(0.98);
}

.bubble-btn.ghost {
  background: var(--color-bg-hover);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-primary);
}

.bubble-btn.ghost:hover {
  background: var(--color-bg-active);
  color: var(--color-text-secondary);
  border-color: var(--color-border-hover);
}

.bubble-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.bubble-tag {
  padding: var(--spacing-xs) 10px;
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-lg);
  font-size: 0.6875rem;
  cursor: pointer;
  transition: all 0.2s var(--ease-out);
  white-space: nowrap;
  min-height: 44px;
}

.bubble-tag:hover {
  background: var(--color-primary-hover);
  border-color: rgba(22, 93, 255, 0.5);
}

@media (max-width: 768px) {
  .ai-bubble-card {
    width: calc(100vw - 80px);
    max-width: 300px;
    left: var(--spacing-md) !important;
    right: var(--spacing-md) !important;
    top: auto !important;
    bottom: calc(80px + env(safe-area-inset-bottom, 0px)) !important;
    transform: none !important;
  }

  .bubble-btn {
    min-height: var(--button-min-height-touch);
    padding: 10px 18px;
  }

  .bubble-close {
    min-width: 44px;
    min-height: var(--button-min-height-touch);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .bubble-tag {
    min-height: var(--button-min-height-touch);
    padding: var(--spacing-sm) 14px;
  }
}

@media (max-width: 480px) {
  .ai-bubble-card {
    width: calc(100vw - 32px);
    max-width: none;
    left: var(--spacing-md) !important;
    right: var(--spacing-md) !important;
    bottom: calc(72px + env(safe-area-inset-bottom, 0px)) !important;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ai-bubble-card {
    transition: none;
  }

  .ai-bubble-card.bubble-hidden {
    transform: none;
  }

  .bubble-btn.primary:hover {
    transform: none;
  }
}
</style>
