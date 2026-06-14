<script setup lang="ts">
import { ref } from 'vue'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

interface Toast {
  id: number
  message: string
  type: ToastType
  duration: number
}

const toasts = ref<Toast[]>([])
let toastId = 0

const show = (
  message: string,
  type: ToastType = 'info',
  duration: number = 3000
) => {
  const id = ++toastId
  toasts.value.push({ id, message, type, duration })
  
  if (duration > 0) {
    setTimeout(() => {
      hide(id)
    }, duration)
  }
  
  return id
}

const hide = (id: number) => {
  const index = toasts.value.findIndex(t => t.id === id)
  if (index !== -1) {
    toasts.value.splice(index, 1)
  }
}

const clearAll = () => {
  toasts.value = []
}

const toastIcons: Record<ToastType, string> = {
  success: '✅',
  error: '❌',
  warning: '⚠️',
  info: 'ℹ️'
}

const toastColors: Record<ToastType, string> = {
  success: '#52C41A',
  error: '#FF4D4F',
  warning: '#FAAD14',
  info: '#1890FF'
}

// 暴露方法供外部使用
defineExpose({ show, hide, clearAll })
</script>

<template>
  <Teleport to="body">
    <div class="toast-container">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="toast-item"
          :style="{ borderLeftColor: toastColors[toast.type] }"
        >
          <span class="toast-icon">{{ toastIcons[toast.type] }}</span>
          <span class="toast-message">{{ toast.message }}</span>
          <button type="button" class="toast-close" @click="hide(toast.id)" aria-label="关闭通知">×</button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: var(--z-toast);
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 400px;
}

.toast-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: rgba(30, 41, 59, 0.95);
  backdrop-filter: blur(16px);
  border-left: 4px solid;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  animation: toastIn 0.3s ease;
}

.toast-item.toast-leave-active {
  animation: toastOut 0.3s ease forwards;
}

@keyframes toastIn {
  from {
    opacity: 0;
    transform: translateX(100%);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes toastOut {
  from {
    opacity: 1;
    transform: translateX(0);
  }
  to {
    opacity: 0;
    transform: translateX(100%);
  }
}

.toast-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.toast-message {
  flex: 1;
  color: var(--color-text-primary);
  font-size: var(--font-size-base);
  line-height: 1.5;
}

.toast-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  font-size: 18px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.toast-close:hover {
  background: var(--color-bg-quaternary);
  color: var(--color-text-secondary);
}

/* 响应式适配 */
@media (max-width: 768px) {
  .toast-container {
    left: 16px;
    right: 16px;
    max-width: none;
  }
  
  .toast-item {
    padding: 14px 16px;
  }
}
</style>
