import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '@/utils/apiClient'
import { useWebSocket } from './useWebSocket'

type AgentStatus = 'idle' | 'busy' | 'error' | 'offline'
type CollaborationMode = 'supervisor' | 'parallel' | 'debate'

interface AgentInfo {
  id: string
  name: string
  type: string
  status: AgentStatus
  capabilities?: string[]
  last_active?: string
}

interface CollaborationConfig {
  mode: CollaborationMode
  agents: string[]
  task: string
  context?: Record<string, unknown>
}

interface CollaborationResult {
  id: string
  status: string
  result?: unknown
}

export function useAgenticEngine() {
  const agentStatuses = ref<Map<string, AgentInfo>>(new Map())
  const collaborationMode = ref<CollaborationMode>('supervisor')
  const loading = ref(false)
  const collaborating = ref(false)

  const { lastMessage, connect: wsConnect, disconnect: wsDisconnect } = useWebSocket()

  // 监听 WebSocket 消息中的 Agent 状态变更
  let stopWatch: (() => void) | null = null

  async function fetchAgentStatuses(): Promise<void> {
    loading.value = true
    try {
      const data = await api.get<AgentInfo[]>('/api/v1/agents')
      const map = new Map<string, AgentInfo>()
      for (const agent of data) {
        map.set(agent.id, agent)
      }
      agentStatuses.value = map
    } finally {
      loading.value = false
    }
  }

  async function startCollaboration(config: CollaborationConfig): Promise<CollaborationResult | null> {
    collaborating.value = true
    collaborationMode.value = config.mode
    try {
      const data = await api.post<CollaborationResult>('/api/v1/agents/collaborate', config)
      return data
    } finally {
      collaborating.value = false
    }
  }

  function watchAgentEvents(): void {
    wsConnect()

    // 使用定时器轮询 lastMessage 变更
    const interval = setInterval(() => {
      if (lastMessage.value?.type === 'status_update') {
        const agentData = lastMessage.value.data as AgentInfo
        if (agentData?.id) {
          const newMap = new Map(agentStatuses.value)
          newMap.set(agentData.id, agentData)
          agentStatuses.value = newMap
        }
      }
    }, 500)

    stopWatch = () => clearInterval(interval)
  }

  function stopWatching(): void {
    if (stopWatch) {
      stopWatch()
      stopWatch = null
    }
    wsDisconnect()
  }

  onMounted(() => {
    fetchAgentStatuses()
  })

  onUnmounted(() => {
    stopWatching()
  })

  return {
    agentStatuses,
    collaborationMode,
    loading,
    collaborating,
    fetchAgentStatuses,
    startCollaboration,
    watchAgentEvents,
    stopWatching
  }
}
