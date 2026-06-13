import { ref } from 'vue'
import { api } from '@/utils/apiClient'

type ActionStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

interface ActionInfo {
  id: string
  intentId: string
  status: ActionStatus
  result?: unknown
  error?: string
  started_at?: string
  completed_at?: string
}

interface ActionHistoryItem {
  id: string
  intentId: string
  status: ActionStatus
  started_at: string
  completed_at?: string
}

export function useActionEngine() {
  const currentAction = ref<ActionInfo | null>(null)
  const actionHistory = ref<ActionHistoryItem[]>([])
  const loading = ref(false)

  async function executeAction(intentId: string): Promise<ActionInfo | null> {
    loading.value = true
    try {
      const data = await api.post<ActionInfo>(`/api/v1/intents/${intentId}/execute`)
      currentAction.value = data
      actionHistory.value.unshift({
        id: data.id,
        intentId: data.intentId,
        status: data.status,
        started_at: data.started_at || new Date().toISOString(),
        completed_at: data.completed_at
      })
      return data
    } finally {
      loading.value = false
    }
  }

  async function cancelAction(intentId: string): Promise<void> {
    try {
      await api.post(`/api/v1/intents/${intentId}/cancel`)
      if (currentAction.value && currentAction.value.intentId === intentId) {
        currentAction.value.status = 'cancelled'
      }
    } catch {
      // 静默处理
    }
  }

  async function getActionStatus(intentId: string): Promise<ActionStatus | null> {
    try {
      const data = await api.get<ActionInfo>(`/api/v1/intents/${intentId}/status`)
      if (currentAction.value && currentAction.value.intentId === intentId) {
        currentAction.value = data
      }
      return data.status
    } catch {
      return null
    }
  }

  return {
    currentAction,
    actionHistory,
    loading,
    executeAction,
    cancelAction,
    getActionStatus
  }
}
