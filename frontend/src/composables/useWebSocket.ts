import { ref, onUnmounted, readonly, getCurrentInstance } from 'vue'
import { API_BASE_URL } from '@/config'
import { useLogger } from '@/utils/logger'

const { info, warn } = useLogger()

type WsMessageType = 'connection_established' | 'message' | 'notification' | 'status_update' | 'topology_update' | 'alert' | 'intent_update' | 'device_update' | 'assistant_action' | 'pong' | 'proactive_notification' | 'playbook_step' | 'grayscale_progress' | 'sla_alert' | 'emergency_fuse'

interface WsMessage {
  type: WsMessageType
  data?: Record<string, unknown>
  sender?: string
  role?: string
  timestamp?: number
}

type MessageHandler = (message: WsMessage) => void

const wsInstance = ref<WebSocket | null>(null)
const isConnected = ref(false)
const reconnectAttempts = ref(0)
const MAX_RECONNECT_ATTEMPTS = 5
const RECONNECT_DELAY = 3000
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let pingTimer: ReturnType<typeof setInterval> | null = null
const handlers: Map<WsMessageType, Set<MessageHandler>> = new Map()
let activeComposableCount = 0

const getWsUrl = (): string => {
  const token = localStorage.getItem('access_token')
  let base: string
  if (API_BASE_URL) {
    base = API_BASE_URL.replace(/^http/, 'ws')
  } else {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    base = `${protocol}//${window.location.host}`
  }
  return `${base}/ws${token ? `?token=${token}` : ''}`
}

const startPing = () => {
  if (pingTimer) clearInterval(pingTimer)
  pingTimer = setInterval(() => {
    if (wsInstance.value?.readyState === WebSocket.OPEN) {
      wsInstance.value.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }))
    }
  }, 30000)
}

const stopPing = () => {
  if (pingTimer) { clearInterval(pingTimer); pingTimer = null }
}

const POLLING_FALLBACK_INTERVAL = 15000
let pollingTimer: ReturnType<typeof setInterval> | null = null
let wsFailedPermanently = false

const startPollingFallback = () => {
  if (pollingTimer) return
  pollingTimer = setInterval(() => {
    if (isConnected.value) return
    const token = localStorage.getItem('access_token')
    if (!token) return
    fetch(`${API_BASE_URL || ''}/api/v1/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` },
      credentials: 'include'
    }).catch(() => {})
  }, POLLING_FALLBACK_INTERVAL)
}

const stopPollingFallback = () => {
  if (pollingTimer) { clearInterval(pollingTimer); pollingTimer = null }
}

const connect = () => {
  if (wsInstance.value?.readyState === WebSocket.OPEN || wsInstance.value?.readyState === WebSocket.CONNECTING) return

  const token = localStorage.getItem('access_token')
  if (!token) { warn('WebSocket: No access token, skipping connection'); return }

  if (wsFailedPermanently) {
    startPollingFallback()
    return
  }

  try {
    const url = getWsUrl()
    wsInstance.value = new WebSocket(url)

    wsInstance.value.onopen = () => {
      isConnected.value = true
      reconnectAttempts.value = 0
      startPing()
      stopPollingFallback()
      info('WebSocket connected')
    }

    wsInstance.value.onmessage = (event) => {
      try {
        const message: WsMessage = JSON.parse(event.data)
        const typeHandlers = handlers.get(message.type)
        if (typeHandlers) {
          typeHandlers.forEach(handler => handler(message))
        }
        const allHandlers = handlers.get('*' as WsMessageType)
        if (allHandlers) {
          allHandlers.forEach(handler => handler(message))
        }
      } catch { /* ignore non-JSON messages */ }
    }

    wsInstance.value.onclose = (event) => {
      isConnected.value = false
      stopPing()
      if (event.code === 4001 || event.code === 4003) {
        warn('WebSocket: auth failed, stopping reconnect')
        wsFailedPermanently = true
        startPollingFallback()
        return
      }
      if (event.code !== 1000 && reconnectAttempts.value < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts.value++
        const delay = RECONNECT_DELAY * Math.min(reconnectAttempts.value, 3)
        info(`WebSocket reconnecting in ${delay}ms (attempt ${reconnectAttempts.value})`)
        reconnectTimer = setTimeout(connect, delay)
      } else if (reconnectAttempts.value >= MAX_RECONNECT_ATTEMPTS) {
        warn('WebSocket: max reconnect attempts reached, falling back to polling')
        wsFailedPermanently = true
        startPollingFallback()
      }
    }

    wsInstance.value.onerror = () => {
      warn('WebSocket connection error')
    }
  } catch (err) {
    warn('WebSocket: Failed to create connection', { error: err instanceof Error ? err.message : String(err) })
    wsFailedPermanently = true
    startPollingFallback()
  }
}

const disconnect = () => {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  stopPing()
  stopPollingFallback()
  wsFailedPermanently = false
  reconnectAttempts.value = 0
  if (wsInstance.value) {
    wsInstance.value.close(1000, 'Client disconnect')
    wsInstance.value = null
  }
  isConnected.value = false
}

const send = (type: WsMessageType, data?: Record<string, unknown>) => {
  if (wsInstance.value?.readyState === WebSocket.OPEN) {
    wsInstance.value.send(JSON.stringify({ type, data, timestamp: Date.now() }))
  }
}

const on = (type: WsMessageType | '*', handler: MessageHandler): (() => void) => {
  const t = type as WsMessageType
  if (!handlers.has(t)) handlers.set(t, new Set())
  handlers.get(t)!.add(handler)
  return () => { handlers.get(t)?.delete(handler) }
}

const off = (type: WsMessageType | '*', handler: MessageHandler) => {
  const t = type as WsMessageType
  handlers.get(t)?.delete(handler)
}

export function useWebSocket() {
  const instance = getCurrentInstance()
  if (instance) {
    activeComposableCount++
    onUnmounted(() => {
      activeComposableCount--
      if (activeComposableCount <= 0) {
        activeComposableCount = 0
        disconnect()
      }
    })
  }

  return {
    isConnected: readonly(isConnected),
    reconnectAttempts: readonly(reconnectAttempts),
    connect,
    disconnect,
    send,
    on,
    off
  }
}
