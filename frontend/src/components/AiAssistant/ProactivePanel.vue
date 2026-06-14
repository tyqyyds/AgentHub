<template>
  <div v-if="messages.length > 0" class="proactive-panel" :class="{ collapsed: isCollapsed }">
    <div class="proactive-header" @click="isCollapsed = !isCollapsed">
      <span class="proactive-icon">🔔</span>
      <span class="proactive-title">主动通知</span>
      <span class="proactive-count">{{ messages.length }}</span>
      <span class="proactive-toggle">{{ isCollapsed ? '▸' : '▾' }}</span>
    </div>
    <div v-show="!isCollapsed" class="proactive-body">
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="proactive-item"
        :class="`severity-${msg.severity}`"
      >
        <div class="proactive-item-header">
          <span class="item-type-icon">{{ typeIcon(msg.pushType) }}</span>
          <span class="item-title">{{ msg.title }}</span>
          <button type="button" class="item-dismiss" @click="dismiss(msg.id)" aria-label="关闭">✕</button>
        </div>
        <p class="item-message">{{ msg.message }}</p>
        <div v-if="msg.suggestedActions && msg.suggestedActions.length" class="item-actions">
          <button
            type="button"
            v-for="(action, ai) in msg.suggestedActions"
            :key="ai"
            class="item-action-btn"
            @click="executeProactiveAction(action)"
            :aria-label="action.label"
          >
            {{ action.label }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

interface ProactiveMessage {
  id: string
  pushType: string
  severity: string
  title: string
  message: string
  suggestedActions?: Array<{ label: string; type: string; params?: Record<string, unknown> }>
  timestamp: string
}

const messages = ref<ProactiveMessage[]>([])
const isCollapsed = ref(false)
let msgCounter = 0

const typeIcon = (pushType: string) => {
  const map: Record<string, string> = {
    alert_diagnosis: '🚨',
    trend_warning: '📈',
    inspection_report: '📊',
    operation_suggestion: '💡',
    knowledge_reminder: '📚',
  }
  return map[pushType] || '🔔'
}

const handleProactivePush = (event: Event) => {
  const customEvent = event as CustomEvent
  const data = customEvent.detail?.data
  if (!data) return
  messages.value.unshift({
    id: `pp_${Date.now()}_${++msgCounter}`,
    pushType: data.push_type || 'unknown',
    severity: data.severity || 'info',
    title: data.title || '通知',
    message: data.message || '',
    suggestedActions: data.suggested_actions || [],
    timestamp: data.timestamp || new Date().toISOString(),
  })
  if (messages.value.length > 20) {
    messages.value = messages.value.slice(0, 20)
  }
}

const dismiss = (id: string) => {
  messages.value = messages.value.filter(m => m.id !== id)
}

const executeProactiveAction = (action: { label: string; type: string; params?: Record<string, unknown> }) => {
  window.dispatchEvent(new CustomEvent('assistant:action', {
    detail: { type: action.type, label: action.label, params: action.params || {} }
  }))
}

onMounted(() => {
  window.addEventListener('proactive_push', handleProactivePush as EventListener)
})

onUnmounted(() => {
  window.removeEventListener('proactive_push', handleProactivePush as EventListener)
})
</script>

<style scoped>
.proactive-panel {
  background: var(--color-bg-input);
  border-bottom: 1px solid var(--color-border-primary);
  flex-shrink: 0;
  transition: max-height 0.3s var(--ease-out);
}

.proactive-panel.collapsed {
  max-height: 40px;
}

.proactive-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  transition: color 0.2s var(--ease-out);
}

.proactive-header:hover {
  color: var(--color-text-secondary);
}

.proactive-icon {
  font-size: var(--font-size-base);
}

.proactive-title {
  font-weight: var(--font-weight-medium);
  flex: 1;
}

.proactive-count {
  background: var(--color-error);
  color: white;
  border-radius: var(--radius-lg);
  padding: 1px 8px;
  font-size: 0.6875rem;
  font-weight: var(--font-weight-semibold);
  min-width: 20px;
  text-align: center;
}

.proactive-toggle {
  font-size: var(--font-size-xs);
  transition: transform 0.2s var(--ease-out);
}

.proactive-panel:not(.collapsed) .proactive-toggle {
  transform: rotate(0deg);
}

.proactive-body {
  max-height: 200px;
  overflow-y: auto;
  padding: 0 var(--spacing-md) var(--spacing-sm);
  animation: proactive-expand 0.25s var(--ease-out);
}

@keyframes proactive-expand {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 200px; }
}

.proactive-body::-webkit-scrollbar {
  width: 3px;
}

.proactive-body::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.2);
  border-radius: var(--radius-xs);
}

.proactive-item {
  padding: var(--spacing-sm);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-xs);
  border-left: 3px solid transparent;
  transition: background 0.2s var(--ease-out);
}

.proactive-item.severity-critical {
  background: var(--color-error-bg);
  border-left-color: var(--color-error);
}

.proactive-item.severity-warning {
  background: var(--color-warning-bg);
  border-left-color: var(--color-warning);
}

.proactive-item.severity-info {
  background: var(--color-primary-bg);
  border-left-color: var(--color-primary);
}

.proactive-item-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-bottom: 4px;
}

.item-type-icon {
  font-size: var(--font-size-sm);
}

.item-title {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  flex: 1;
}

.item-dismiss {
  background: none;
  border: none;
  color: var(--color-text-disabled);
  cursor: pointer;
  font-size: var(--font-size-xs);
  padding: 2px;
  border-radius: var(--radius-sm);
  min-width: 28px;
  min-height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s var(--ease-out);
}

.item-dismiss:hover {
  color: var(--color-text-secondary);
  background: var(--color-bg-active);
}

.item-message {
  font-size: 0.6875rem;
  color: var(--color-text-tertiary);
  line-height: var(--line-height-normal);
  margin: 0;
}

.item-actions {
  display: flex;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-xs);
}

.item-action-btn {
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-primary-border);
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  font-size: 0.6875rem;
  cursor: pointer;
  transition: var(--button-transition);
}

.item-action-btn:hover {
  background: var(--color-primary-hover);
  border-color: rgba(22, 93, 255, 0.6);
}
</style>
