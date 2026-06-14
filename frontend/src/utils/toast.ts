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

export const showToast = (
  message: string,
  type: ToastType = 'info',
  duration: number = 3000
) => {
  if (toasts.value.length >= 5) {
    toasts.value.shift()
  }
  const id = ++toastId
  toasts.value.push({ id, message, type, duration })
  
  if (duration > 0) {
    setTimeout(() => {
      hideToast(id)
    }, duration)
  }
  
  return id
}

export const hideToast = (id: number) => {
  const index = toasts.value.findIndex(t => t.id === id)
  if (index !== -1) {
    toasts.value.splice(index, 1)
  }
}

export const clearAllToasts = () => {
  toasts.value = []
}

export const toastIcons: Record<ToastType, string> = {
  success: '✅',
  error: '❌',
  warning: '⚠️',
  info: 'ℹ️'
}

export const toastColors: Record<ToastType, string> = {
  success: '#52C41A',
  error: '#FF4D4F',
  warning: '#FAAD14',
  info: '#1890FF'
}

export { toasts }
