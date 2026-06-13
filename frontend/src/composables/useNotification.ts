import { ref, onMounted, onUnmounted } from 'vue'

export function useNotification() {
  const notifications = ref<Array<{
    id: string
    type: 'success' | 'warning' | 'error' | 'info'
    title: string
    message: string
    timestamp: number
  }>>([])

  function addNotification(
    type: 'success' | 'warning' | 'error' | 'info',
    title: string,
    message: string
  ) {
    const id = Date.now().toString()
    notifications.value.unshift({
      id,
      type,
      title,
      message,
      timestamp: Date.now()
    })
    // 最多保留50条
    if (notifications.value.length > 50) {
      notifications.value = notifications.value.slice(0, 50)
    }
    return id
  }

  function removeNotification(id: string) {
    notifications.value = notifications.value.filter(n => n.id !== id)
  }

  function clearAll() {
    notifications.value = []
  }

  return {
    notifications,
    addNotification,
    removeNotification,
    clearAll
  }
}
