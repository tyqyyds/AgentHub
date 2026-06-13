import { ref } from 'vue'

interface WsMessage {
  type: string
  data: unknown
}

export type WsMessageType =
  | 'connection_established'
  | 'message'
  | 'notification'
  | 'status_update'
  | 'topology_update'
  | 'device_update'
  | 'alert'
  | 'intent_update'
  | 'assistant_action'
  | 'proactive_notification'
  | 'playbook_step'
  | 'grayscale_progress'
  | 'sla_alert'
  | 'emergency_fuse'
  | 'ping_pong'

// ── 单例模块级状态 ──
let instanceCount = 0
const sharedWs = ref<WebSocket | null>(null)
const sharedConnected = ref(false)
const sharedLastMessage = ref<WsMessage | null>(null)
const sharedReconnectAttempts = ref(0)
const sharedPollingMode = ref(false)
const sharedAuthFailed = ref(false)

let heartbeatTimer: ReturnType<typeof setInterval> | null = null
let pollingTimer: ReturnType<typeof setInterval> | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

const maxReconnectAttempts = 5
const heartbeatInterval = 30000
const pollingInterval = 10000

function clearHeartbeat() {
  if (heartbeatTimer !== null) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

function startHeartbeat() {
  clearHeartbeat()
  heartbeatTimer = setInterval(() => {
    if (sharedWs.value?.readyState === WebSocket.OPEN) {
      sharedWs.value.send(JSON.stringify({ type: 'ping_pong', data: {} }))
    }
  }, heartbeatInterval)
}

function getBaseUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}

function buildWsUrl(url?: string): string {
  const base = url || getBaseUrl()
  const token = localStorage.getItem('token')
  if (!token) return base
  const separator = base.includes('?') ? '&' : '?'
  return `${base}${separator}token=${encodeURIComponent(token)}`
}

function stopPolling() {
  if (pollingTimer !== null) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
  sharedPollingMode.value = false
}

function startPolling() {
  stopPolling()
  sharedPollingMode.value = true
  const poll = async () => {
    try {
      const token = localStorage.getItem('token')
      const headers: Record<string, string> = {}
      if (token) headers['Authorization'] = `Bearer ${token}`
      const res = await fetch('/api/v1/notifications/poll', { headers })
      if (res.status === 401) {
        sharedAuthFailed.value = true
        stopPolling()
        return
      }
      if (res.ok) {
        const data = await res.json()
        if (data) {
          sharedLastMessage.value = data
        }
      }
    } catch {
      // 轮询失败静默处理，下次间隔重试
    }
  }
  poll()
  pollingTimer = setInterval(poll, pollingInterval)
}

function connectInternal(baseUrl?: string) {
  if (sharedWs.value?.readyState === WebSocket.OPEN) return
  if (sharedAuthFailed.value) return

  const fullUrl = buildWsUrl(baseUrl)
  sharedWs.value = new WebSocket(fullUrl)

  sharedWs.value.onopen = () => {
    sharedConnected.value = true
    sharedReconnectAttempts.value = 0
    sharedAuthFailed.value = false
    startHeartbeat()
    // WebSocket 恢复连接后自动停止轮询
    if (sharedPollingMode.value) {
      stopPolling()
    }
  }

  sharedWs.value.onmessage = (event) => {
    try {
      const msg: WsMessage = JSON.parse(event.data)
      // 收到 pong 响应时重置心跳定时器
      if (msg.type === 'ping_pong') {
        clearHeartbeat()
        startHeartbeat()
      }
      // 检测 401 认证失败响应
      if (msg.type === 'error' && (msg.data as { code?: number })?.code === 401) {
        sharedAuthFailed.value = true
        clearHeartbeat()
        if (sharedWs.value) {
          sharedWs.value.close()
        }
        return
      }
      sharedLastMessage.value = msg
    } catch {
      sharedLastMessage.value = { type: 'raw', data: event.data }
    }
  }

  sharedWs.value.onclose = (event) => {
    sharedConnected.value = false
    clearHeartbeat()

    // 认证失败（close code 4001）停止重连
    if (event.code === 4001) {
      sharedAuthFailed.value = true
      return
    }

    if (sharedAuthFailed.value) return

    if (sharedReconnectAttempts.value < maxReconnectAttempts) {
      sharedReconnectAttempts.value++
      reconnectTimer = setTimeout(() => connectInternal(baseUrl), 2000 * sharedReconnectAttempts.value)
    } else {
      // 连续 5 次重连失败，降级为 HTTP 轮询
      startPolling()
    }
  }

  sharedWs.value.onerror = () => {
    sharedConnected.value = false
  }
}

function disconnectInternal() {
  clearHeartbeat()
  stopPolling()
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (sharedWs.value) {
    sharedWs.value.close()
    sharedWs.value = null
    sharedConnected.value = false
  }
  sharedAuthFailed.value = false
}

function sendInternal(message: WsMessage) {
  if (sharedWs.value?.readyState === WebSocket.OPEN) {
    sharedWs.value.send(JSON.stringify(message))
  }
}

export function useWebSocket(url?: string) {
  instanceCount++

  function connect() {
    connectInternal(url)
  }

  function disconnect() {
    disconnectInternal()
  }

  function send(message: WsMessage) {
    sendInternal(message)
  }

  return {
    ws: sharedWs,
    connected: sharedConnected,
    lastMessage: sharedLastMessage,
    reconnectAttempts: sharedReconnectAttempts,
    pollingMode: sharedPollingMode,
    authFailed: sharedAuthFailed,
    connect,
    disconnect,
    send,
    startPolling,
    stopPolling
  }
}
