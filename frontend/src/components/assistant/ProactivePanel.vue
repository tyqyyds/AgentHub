<script setup lang="ts">
interface ProactiveNotification {
  id: string
  type: 'error' | 'warning' | 'info' | 'success'
  title: string
  description: string
  timestamp: number
  actions: Array<{ label: string; key: string }>
}

defineProps<{
  visible: boolean
  notifications: ProactiveNotification[]
}>()

const emit = defineEmits<{
  close: []
  action: [notificationId: string, action: string]
}>()

const typeConfig: Record<string, { icon: string; type: string }> = {
  error: { icon: '✕', type: 'error' },
  warning: { icon: '⚠', type: 'warning' },
  info: { icon: 'ℹ', type: 'info' },
  success: { icon: '✓', type: 'success' }
}

function getTypeConfig(type: string) {
  return typeConfig[type] || typeConfig.info
}

function formatTime(ts: number) {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
</script>

<template>
  <transition name="slide-right">
    <div v-if="visible" class="proactive-panel">
      <div class="panel-header">
        <span class="header-title">系统通知</span>
        <button class="close-btn" @click="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <div class="notification-list">
        <div
          v-for="notification in notifications"
          :key="notification.id"
          class="notification-item"
        >
          <div class="notification-icon" :class="`severity-${getTypeConfig(notification.type).type}`">
            {{ getTypeConfig(notification.type).icon }}
          </div>
          <div class="notification-body">
            <div class="notification-title">{{ notification.title }}</div>
            <div class="notification-desc">{{ notification.description }}</div>
            <div class="notification-time">{{ formatTime(notification.timestamp) }}</div>
          </div>
          <div class="notification-actions">
            <button
              v-for="action in notification.actions"
              :key="action.key"
              class="action-btn"
              :class="{ primary: action.key === 'view' }"
              @click="emit('action', notification.id, action.key)"
            >
              {{ action.label }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.proactive-panel {
  position: fixed;
  right: var(--spacing-2xl);
  bottom: var(--spacing-2xl);
  width: 360px;
  max-height: 400px;
  background: rgba(var(--color-bg-base-rgb), 0.95);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-2xl);
  z-index: 10001;
  box-shadow: 0 var(--spacing-sm) 40px rgba(0, 0, 0, 0.4);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px var(--spacing-lg);
  border-bottom: 1px solid rgba(var(--color-white-rgb), 0.08);
}

.header-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
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

.notification-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-sm);
}

.notification-item {
  display: flex;
  gap: 10px;
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  background: rgba(var(--color-white-rgb), 0.04);
  margin-bottom: var(--spacing-sm);
  transition: background 0.2s;
}

.notification-item:hover {
  background: rgba(var(--color-white-rgb), 0.08);
}

.notification-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  flex-shrink: 0;
}

.notification-icon.severity-error {
  background: rgba(var(--color-error-rgb), 0.12);
  color: var(--color-error);
}

.notification-icon.severity-warning {
  background: rgba(var(--color-warning-rgb), 0.12);
  color: var(--color-warning);
}

.notification-icon.severity-info {
  background: rgba(var(--color-primary-rgb), 0.12);
  color: var(--color-primary);
}

.notification-icon.severity-success {
  background: rgba(var(--color-success-rgb), 0.12);
  color: var(--color-success);
}

.notification-body {
  flex: 1;
  min-width: 0;
}

.notification-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-2xs);
}

.notification-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  line-height: 1.4;
  margin-bottom: var(--spacing-2xs);
}

.notification-time {
  font-size: var(--font-size-2xs);
  color: var(--color-text-quaternary);
}

.notification-actions {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2xs);
  flex-shrink: 0;
}

.action-btn {
  padding: var(--spacing-2xs) 10px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  cursor: pointer;
  background: rgba(var(--color-white-rgb), 0.06);
  color: var(--color-text-tertiary);
  transition: all 0.2s;
  white-space: nowrap;
}

.action-btn:hover {
  background: rgba(var(--color-white-rgb), 0.12);
}

.action-btn.primary {
  background: rgba(var(--color-primary-rgb), 0.2);
  color: var(--color-info-light);
}

.action-btn.primary:hover {
  background: rgba(var(--color-primary-rgb), 0.3);
}

.slide-right-enter-active,
.slide-right-leave-active {
  transition: all 0.3s ease;
}

.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
