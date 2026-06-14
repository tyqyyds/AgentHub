import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'

export interface Notification {
  id: string
  type: 'alert' | 'info' | 'warning' | 'success'
  title: string
  message: string
  timestamp: number
  read: boolean
  data?: Record<string, unknown>
}

export const useNotificationStore = defineStore('notification', () => {
  const notifications = ref<Notification[]>([])
  const maxNotifications = 100

  const unreadCount = computed(() => notifications.value.filter(n => !n.read).length)
  const recentNotifications = computed(() => notifications.value.slice(-20).reverse())
  const alertNotifications = computed(() => notifications.value.filter(n => n.type === 'alert' && !n.read))

  const addNotification = (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => {
    const newNotification: Notification = {
      ...notification,
      id: `notif_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      timestamp: Date.now(),
      read: false
    }
    notifications.value.push(newNotification)
    if (notifications.value.length > maxNotifications) {
      notifications.value = notifications.value.slice(-maxNotifications)
    }
  }

  const markAsRead = (id: string) => {
    const notification = notifications.value.find(n => n.id === id)
    if (notification) notification.read = true
  }

  const markAllAsRead = () => {
    notifications.value.forEach(n => { n.read = true })
  }

  const clearAll = () => {
    notifications.value = []
  }

  const clearRead = () => {
    notifications.value = notifications.value.filter(n => !n.read)
  }

  const ws = useWebSocket()
  ws.on('alert', (msg) => {
    const data = msg.data || {}
    addNotification({
      type: (data.level as Notification['type']) || 'warning',
      title: (data.title as string) || '系统告警',
      message: (data.message as string) || '',
      data: data as Record<string, unknown>
    })
  })
  ws.on('intent_update', (msg) => {
    const data = msg.data || {}
    addNotification({
      type: 'info',
      title: '意图状态更新',
      message: (data.message as string) || '意图状态已变更',
      data: data as Record<string, unknown>
    })
  })

  return {
    notifications,
    unreadCount,
    recentNotifications,
    alertNotifications,
    addNotification,
    markAsRead,
    markAllAsRead,
    clearAll,
    clearRead
  }
})
