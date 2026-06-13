import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/utils/apiClient'

interface NotificationItem {
  id: string
  type: 'info' | 'warning' | 'error' | 'success'
  title: string
  message: string
  read: boolean
  created_at: string
  source?: 'system' | 'websocket' | 'api'
}

export const useNotificationStore = defineStore('notification', () => {
  const notifications = ref<NotificationItem[]>([])
  const loading = ref(false)

  const unreadCount = computed(() =>
    notifications.value.filter(n => !n.read).length
  )

  async function fetchNotifications() {
    loading.value = true
    try {
      const data = await api.get<NotificationItem[]>('/api/v1/observability/notifications')
      notifications.value = data
    } finally {
      loading.value = false
    }
  }

  async function markAsRead(id: string) {
    const notification = notifications.value.find(n => n.id === id)
    if (notification) {
      notification.read = true
    }
    try {
      await api.put(`/api/v1/observability/notifications/${id}/read`)
    } catch {
      // 回滚
      if (notification) {
        notification.read = false
      }
    }
  }

  async function markAllAsRead() {
    const previousStates = notifications.value.map(n => ({ id: n.id, read: n.read }))
    notifications.value.forEach(n => { n.read = true })
    try {
      await api.put('/api/v1/observability/notifications/read-all')
    } catch {
      // 回滚
      previousStates.forEach(({ id, read }) => {
        const n = notifications.value.find(item => item.id === id)
        if (n) n.read = read
      })
    }
  }

  function addNotification(notification: NotificationItem) {
    notifications.value.unshift(notification)
    // 最多保留100条
    if (notifications.value.length > 100) {
      notifications.value = notifications.value.slice(0, 100)
    }
  }

  function clearAll() {
    notifications.value = []
  }

  return {
    notifications,
    loading,
    unreadCount,
    fetchNotifications,
    markAsRead,
    markAllAsRead,
    addNotification,
    clearAll
  }
})
