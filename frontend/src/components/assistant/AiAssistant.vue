<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import FloatingBall from './FloatingBall.vue'
import ChatPanel from './ChatPanel.vue'
import ProactivePanel from './ProactivePanel.vue'

interface ProactiveNotification {
  id: string
  type: 'error' | 'warning' | 'info' | 'success'
  title: string
  description: string
  timestamp: number
  actions: Array<{ label: string; key: string }>
}

const STORAGE_KEY = 'ai-assistant-enabled'

const chatVisible = ref(false)
const proactiveVisible = ref(false)
const unreadCount = ref(0)
const notifications = ref<ProactiveNotification[]>([])
const assistantEnabled = ref(true)

const { lastMessage, connected, connect, disconnect } = useWebSocket()

function loadState() {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved !== null) {
    assistantEnabled.value = saved === 'true'
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, String(assistantEnabled.value))
}

function toggleChat() {
  chatVisible.value = !chatVisible.value
  if (chatVisible.value) {
    unreadCount.value = 0
  }
}

function closeChat() {
  chatVisible.value = false
}

function handleSend(message: string) {
  // Message sending is handled internally by ChatPanel
  void message
}

function closeProactive() {
  proactiveVisible.value = false
}

function handleProactiveAction(notificationId: string, action: string) {
  const notification = notifications.value.find((n) => n.id === notificationId)
  if (notification) {
    notifications.value = notifications.value.filter((n) => n.id !== notificationId)
  }
  if (action === 'view') {
    chatVisible.value = true
  }
  if (notifications.value.length === 0) {
    proactiveVisible.value = false
  }
}

watch(lastMessage, (msg) => {
  if (!msg || !assistantEnabled.value) return

  if (msg.type === 'alert' || msg.type === 'notification') {
    const data = msg.data as Record<string, unknown>
    const notification: ProactiveNotification = {
      id: String(Date.now()),
      type: (data.level as ProactiveNotification['type']) || 'info',
      title: String(data.title || '系统通知'),
      description: String(data.description || ''),
      timestamp: Date.now(),
      actions: [
        { label: '查看详情', key: 'view' },
        { label: '忽略', key: 'dismiss' }
      ]
    }
    notifications.value.push(notification)
    proactiveVisible.value = true
    if (!chatVisible.value) {
      unreadCount.value++
    }
  }
})

onMounted(() => {
  loadState()
  if (assistantEnabled.value) {
    connect()
  }
})

onUnmounted(() => {
  disconnect()
})

watch(assistantEnabled, (val) => {
  saveState()
  if (val) {
    connect()
  } else {
    disconnect()
    chatVisible.value = false
    proactiveVisible.value = false
  }
})
</script>

<template>
  <template v-if="assistantEnabled">
    <FloatingBall
      :unread-count="unreadCount"
      @toggle="toggleChat"
    />
    <ChatPanel
      :visible="chatVisible"
      :connected="connected"
      @close="closeChat"
      @send="handleSend"
    />
    <ProactivePanel
      :visible="proactiveVisible"
      :notifications="notifications"
      @close="closeProactive"
      @action="handleProactiveAction"
    />
  </template>
</template>
