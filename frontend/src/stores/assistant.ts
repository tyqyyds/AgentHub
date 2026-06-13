import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/utils/apiClient'

interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
}

export const useAssistantStore = defineStore('assistant', () => {
  const conversations = ref<Conversation[]>([])
  const currentConversationId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const isStreaming = ref(false)
  const isLoading = ref(false)
  const streamingContent = ref('')

  const currentConversation = computed(() =>
    conversations.value.find(c => c.id === currentConversationId.value) ?? null
  )

  async function getConversations() {
    isLoading.value = true
    try {
      const data = await api.get<Conversation[]>('/api/v1/v2/copilot/conversations')
      conversations.value = data
    } finally {
      isLoading.value = false
    }
  }

  async function createConversation(title?: string) {
    isLoading.value = true
    try {
      const data = await api.post<Conversation>('/api/v1/v2/copilot/conversations', {
        title: title || '新对话'
      })
      conversations.value.unshift(data)
      currentConversationId.value = data.id
      messages.value = []
      return data
    } finally {
      isLoading.value = false
    }
  }

  async function deleteConversation(id: string) {
    try {
      await api.delete(`/api/v1/v2/copilot/conversations/${id}`)
      conversations.value = conversations.value.filter(c => c.id !== id)
      if (currentConversationId.value === id) {
        currentConversationId.value = null
        messages.value = []
      }
    } catch {
      // 静默处理
    }
  }

  async function sendMessage(content: string) {
    if (!content.trim() || isStreaming.value) return

    // 如果没有当前对话，先创建一个
    if (!currentConversationId.value) {
      const conv = await createConversation(content.slice(0, 30))
      if (!conv) return
    }

    // 添加用户消息
    const userMessage: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content,
      created_at: new Date().toISOString()
    }
    messages.value.push(userMessage)

    // 准备流式响应
    isStreaming.value = true
    streamingContent.value = ''

    const assistantMessage: ChatMessage = {
      id: `temp-assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString()
    }
    messages.value.push(assistantMessage)

    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/api/v1/v2/copilot/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          conversation_id: currentConversationId.value,
          message: content
        })
      })

      if (!response.ok) {
        throw new Error(`请求失败: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('无法获取响应流')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim()
            if (data === '[DONE]') continue
            try {
              const parsed = JSON.parse(data)
              if (parsed.content) {
                streamingContent.value += parsed.content
                assistantMessage.content = streamingContent.value
              }
            } catch {
              // 非 JSON 数据，作为纯文本处理
              streamingContent.value += data
              assistantMessage.content = streamingContent.value
            }
          }
        }
      }

      // 处理剩余 buffer
      if (buffer.startsWith('data: ') && buffer.slice(6).trim() !== '[DONE]') {
        try {
          const parsed = JSON.parse(buffer.slice(6).trim())
          if (parsed.content) {
            streamingContent.value += parsed.content
            assistantMessage.content = streamingContent.value
          }
        } catch {
          // 忽略解析错误
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '发送消息失败'
      assistantMessage.content = `[错误] ${msg}`
    } finally {
      isStreaming.value = false
      streamingContent.value = ''
    }
  }

  function clearConversations() {
    conversations.value = []
    currentConversationId.value = null
    messages.value = []
    streamingContent.value = ''
  }

  return {
    conversations,
    currentConversationId,
    messages,
    isStreaming,
    isLoading,
    streamingContent,
    currentConversation,
    getConversations,
    createConversation,
    deleteConversation,
    sendMessage,
    clearConversations
  }
})
