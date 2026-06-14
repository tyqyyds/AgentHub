<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useLogger } from '@/utils/logger'
import { api, apiClient, authFetch } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'
import PageLayout from '@/components/PageLayout.vue'
import StatCard from '@/components/StatCard.vue'
import { useAuthStore } from '@/stores/auth'

const { info, warn } = useLogger()
const authStore = useAuthStore()
const canWrite = computed(() => authStore.userRole !== 'viewer')

interface Document {
  id: string | number
  title: string
  content: string
  category: string
  version: number
  author: string
  updated_at: string
  created_at: string
}

interface Version {
  id: string | number
  doc_id: string | number
  version: number
  content: string
  author: string
  created_at: string
  change_summary: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

const CATEGORIES = [
  { value: 'all', label: '全部分类' },
  { value: 'network', label: '网络配置' },
  { value: 'security', label: '安全策略' },
  { value: 'operation', label: '运维手册' },
  { value: 'troubleshooting', label: '故障排查' },
  { value: 'architecture', label: '架构文档' },
  { value: 'api', label: '接口文档' },
  { value: 'other', label: '其他' }
]

const SUPPORTED_EXTENSIONS = '.txt,.md,.pdf,.json,.yaml,.yml,.xml,.csv,.cfg,.conf,.log'

const activeTab = ref<'documents' | 'assistant'>('documents')
const documents = ref<Document[]>([])
const isLoading = ref(true)
const searchQuery = ref('')
const categoryFilter = ref('all')
const showAddModal = ref(false)
const showUploadModal = ref(false)
const showVersionPanel = ref<string | number | null>(null)
const versions = ref<Version[]>([])
const isLoadingVersions = ref(false)
const isSubmitting = ref(false)
const isUploading = ref(false)
const uploadFile = ref<File | null>(null)

const docForm = ref({
  title: '',
  content: '',
  category: 'network'
})

const editingDocId = ref<string | number | null>(null)

const chatMessages = ref<ChatMessage[]>([])
const chatInput = ref('')
const isQuerying = ref(false)
const chatListRef = ref<HTMLElement | null>(null)

const stats = ref([
  { label: '文档总数', value: 0, icon: '📄', color: 'var(--color-primary)' },
  { label: '版本总数', value: 0, icon: '📋', color: 'var(--color-success)' },
  { label: 'RAG索引', value: 0, icon: '🔍', color: 'var(--color-warning)', statusText: '未构建' },
  { label: 'LLM状态', value: 0, icon: '🤖', color: 'var(--color-text-tertiary)', statusText: '离线' }
])

const llmStatus = ref<'online' | 'offline' | 'loading'>('offline')

const filteredDocuments = computed(() => {
  let list = documents.value
  if (categoryFilter.value !== 'all') {
    list = list.filter(d => d.category === categoryFilter.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(d =>
      d.title.toLowerCase().includes(q) ||
      d.content.toLowerCase().includes(q) ||
      d.author.toLowerCase().includes(q)
    )
  }
  return list
})

const getCategoryLabel = (value: string) => {
  return CATEGORIES.find(c => c.value === value)?.label || value
}

const formatTime = (dateStr: string): string => {
  if (!dateStr) return '--'
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  if (diffMs < 0) return '刚刚'
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)
  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins}分钟前`
  if (diffHours < 24) return `${diffHours}小时前`
  if (diffDays < 30) return `${diffDays}天前`
  return date.toLocaleDateString('zh-CN')
}

const fetchDocuments = async () => {
  isLoading.value = true
  try {
    const result = await apiClient.get(api.knowledge.documents)
    documents.value = result.data?.items || result.data || []
    stats.value[0].value = documents.value.length
  } catch (err: any) {
    warn('获取文档列表失败', { error: err.message })
    loadMockDocuments()
  } finally {
    isLoading.value = false
  }
}

const fetchVersionStats = async () => {
  try {
    const result = await apiClient.get(api.knowledgeVersions.stats)
    stats.value[1].value = result.data?.total_versions || 0
    stats.value[2].statusText = result.data?.rag_indexed ? '已构建' : '未构建'
    stats.value[2].value = result.data?.rag_indexed ? 1 : 0
  } catch {
    stats.value[1].value = documents.value.reduce((sum, d) => sum + (d.version || 1), 0)
  }
}

const fetchLlmStatus = async () => {
  try {
    const result = await apiClient.get(api.assistant.llmStatus)
    const online = result.data?.status === 'online' || result.data?.available === true
    llmStatus.value = online ? 'online' : 'offline'
    stats.value[3].statusText = online ? '在线' : '离线'
    stats.value[3].value = online ? 1 : 0
    stats.value[3].color = online ? 'var(--color-success)' : 'var(--color-text-tertiary)'
  } catch {
    llmStatus.value = 'offline'
    stats.value[3].statusText = '离线'
    stats.value[3].value = 0
    stats.value[3].color = 'var(--color-text-tertiary)'
  }
}

const loadMockDocuments = () => {
  documents.value = [
    { id: 1, title: '核心路由器配置规范', content: '本文档定义了核心路由器的基础配置标准，包括接口命名、路由协议、ACL规则等。', category: 'network', version: 3, author: 'admin', updated_at: '2025-05-28T10:30:00Z', created_at: '2025-03-01T08:00:00Z' },
    { id: 2, title: '防火墙安全策略手册', content: '防火墙策略管理规范，涵盖入站/出站规则、VPN隧道配置、IPS/IDS策略。', category: 'security', version: 5, author: 'security_admin', updated_at: '2025-05-27T14:20:00Z', created_at: '2025-02-15T09:00:00Z' },
    { id: 3, title: '日常巡检操作手册', content: '网络设备日常巡检流程，包括CPU/内存/端口状态检查、日志审计、配置备份。', category: 'operation', version: 2, author: 'operator1', updated_at: '2025-05-25T16:00:00Z', created_at: '2025-04-10T10:00:00Z' },
    { id: 4, title: 'BGP路由震荡排查指南', content: 'BGP路由震荡问题的诊断与排查流程，包含常见原因分析和解决方案。', category: 'troubleshooting', version: 4, author: 'neteng', updated_at: '2025-05-20T11:15:00Z', created_at: '2025-01-20T13:00:00Z' },
    { id: 5, title: '数据中心网络架构设计', content: 'Spine-Leaf架构设计文档，包括拓扑规划、容量计算、冗余策略。', category: 'architecture', version: 1, author: 'architect', updated_at: '2025-05-15T09:00:00Z', created_at: '2025-05-15T09:00:00Z' },
    { id: 6, title: '网络设备API接口文档', content: '设备管理RESTful API接口说明，包括认证、设备CRUD、配置下发等接口。', category: 'api', version: 7, author: 'dev_team', updated_at: '2025-05-29T08:30:00Z', created_at: '2025-01-05T10:00:00Z' },
    { id: 7, title: '链路故障应急处理流程', content: '链路故障的应急响应流程，包括故障定位、链路切换、业务恢复验证。', category: 'troubleshooting', version: 3, author: 'operator2', updated_at: '2025-05-22T15:45:00Z', created_at: '2025-03-18T11:00:00Z' },
    { id: 8, title: 'QoS策略配置指南', content: 'QoS流量整形与队列调度配置方法，包含DSCP标记、队列映射、带宽保障。', category: 'network', version: 2, author: 'neteng', updated_at: '2025-05-18T13:20:00Z', created_at: '2025-04-05T14:00:00Z' }
  ]
  stats.value[0].value = documents.value.length
  stats.value[1].value = documents.value.reduce((sum, d) => sum + d.version, 0)
}

const openAddModal = (doc?: Document) => {
  if (doc) {
    editingDocId.value = doc.id
    docForm.value = { title: doc.title, content: doc.content, category: doc.category }
  } else {
    editingDocId.value = null
    docForm.value = { title: '', content: '', category: 'network' }
  }
  showAddModal.value = true
}

const submitDocument = async () => {
  if (!docForm.value.title.trim()) {
    showToast('请输入文档标题', 'error')
    return
  }
  isSubmitting.value = true
  try {
    if (editingDocId.value) {
      await apiClient.put(api.knowledge.updateDocument(String(editingDocId.value)), docForm.value)
      showToast('文档更新成功', 'success')
    } else {
      await apiClient.post(api.knowledge.addDocument, docForm.value)
      showToast('文档创建成功', 'success')
    }
    showAddModal.value = false
    await fetchDocuments()
    await fetchVersionStats()
  } catch (err: any) {
    warn('保存文档失败', { error: err.message })
    showToast('保存失败: ' + err.message, 'error')
  } finally {
    isSubmitting.value = false
  }
}

const deleteDocument = async (id: string | number) => {
  try {
    await apiClient.delete(api.knowledge.deleteDocument(String(id)))
    showToast('文档已删除', 'success')
    if (showVersionPanel.value === id) showVersionPanel.value = null
    await fetchDocuments()
    await fetchVersionStats()
  } catch (err: any) {
    warn('删除文档失败', { error: err.message })
    showToast('删除失败: ' + err.message, 'error')
  }
}

const toggleVersions = async (docId: string | number) => {
  if (showVersionPanel.value === docId) {
    showVersionPanel.value = null
    return
  }
  showVersionPanel.value = docId
  isLoadingVersions.value = true
  try {
    const result = await apiClient.get(api.knowledgeVersions.versions(String(docId)))
    versions.value = result.data?.items || result.data || []
  } catch (err: any) {
    warn('获取版本历史失败', { error: err.message })
    const doc = documents.value.find(d => d.id === docId)
    versions.value = Array.from({ length: doc?.version || 1 }, (_, i) => ({
      id: `v_${docId}_${i + 1}`,
      doc_id: docId,
      version: (doc?.version || 1) - i,
      content: i === 0 ? (doc?.content || '') : `(版本 ${(doc?.version || 1) - i} 的内容)`,
      author: doc?.author || 'unknown',
      created_at: new Date(Date.now() - i * 86400000 * 3).toISOString(),
      change_summary: i === 0 ? '当前版本' : `更新至版本 ${(doc?.version || 1) - i}`
    }))
  } finally {
    isLoadingVersions.value = false
  }
}

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    uploadFile.value = target.files[0]
  }
}

const submitUpload = async () => {
  if (!uploadFile.value) {
    showToast('请选择文件', 'error')
    return
  }
  isUploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', uploadFile.value)
    await authFetch(api.upload, {
      method: 'POST',
      body: formData
    })
    showToast('文件上传成功', 'success')
    showUploadModal.value = false
    uploadFile.value = null
    await fetchDocuments()
    await fetchVersionStats()
  } catch (err: any) {
    warn('文件上传失败', { error: err.message })
    showToast('上传失败: ' + err.message, 'error')
  } finally {
    isUploading.value = false
  }
}

const sendQuery = async () => {
  const question = chatInput.value.trim()
  if (!question || isQuerying.value) return

  const userMsg: ChatMessage = {
    id: `msg_${Date.now()}`,
    role: 'user',
    content: question,
    timestamp: new Date().toISOString()
  }
  chatMessages.value.push(userMsg)
  chatInput.value = ''
  isQuerying.value = true

  await nextTick()
  scrollChatToBottom()

  const assistantMsg: ChatMessage = {
    id: `msg_${Date.now()}_resp`,
    role: 'assistant',
    content: '',
    timestamp: new Date().toISOString()
  }
  chatMessages.value.push(assistantMsg)

  try {
    const token = localStorage.getItem('access_token')
    const response = await fetch(api.knowledge.chatStream, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ message: question })
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response body')
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
          if (data === '[DONE]') break
          try {
            const parsed = JSON.parse(data)
            const content = parsed.content || parsed.delta || parsed.text || ''
            if (content) {
              assistantMsg.content += content
              await nextTick()
              scrollChatToBottom()
            }
          } catch {
            // Plain text chunk
            if (data && data !== '[DONE]') {
              assistantMsg.content += data
              await nextTick()
              scrollChatToBottom()
            }
          }
        }
      }
    }

    // Fallback: if stream produced no content, try non-stream endpoint
    if (!assistantMsg.content.trim()) {
      const result = await apiClient.post(api.knowledge.query, { query: question })
      assistantMsg.content = result.data?.answer || result.data?.response || result.data?.content || '未找到相关结果'
    }
  } catch (err: any) {
    // Fallback to non-stream on error
    try {
      const result = await apiClient.post(api.knowledge.query, { query: question })
      assistantMsg.content = result.data?.answer || result.data?.response || result.data?.content || '未找到相关结果'
    } catch {
      assistantMsg.content = `查询失败，请确认LLM服务是否可用。`
    }
  } finally {
    isQuerying.value = false
    await nextTick()
    scrollChatToBottom()
  }
}

const scrollChatToBottom = () => {
  if (chatListRef.value) {
    chatListRef.value.scrollTop = chatListRef.value.scrollHeight
  }
}

const clearChat = () => {
  chatMessages.value = []
}

let pollTimer: number | null = null

onMounted(async () => {
  info('KnowledgeBase mounted')
  await Promise.allSettled([
    fetchDocuments(),
    fetchVersionStats(),
    fetchLlmStatus()
  ])
  pollTimer = window.setInterval(() => {
    fetchLlmStatus()
  }, 30000)
})

onUnmounted(() => {
  if (pollTimer !== null) clearInterval(pollTimer)
})
</script>

<template>
  <PageLayout title="知识库管理" subtitle="文档管理与AI智能问答">
    <template #actions>
      <span class="llm-status-badge" :class="llmStatus">
        <span class="status-dot"></span>
        {{ llmStatus === 'online' ? 'LLM 在线' : llmStatus === 'loading' ? 'LLM 加载中' : 'LLM 离线' }}
      </span>
    </template>

    <div class="stats-grid">
      <StatCard
        v-for="stat in stats"
        :key="stat.label"
        :icon="stat.icon"
        :label="stat.label"
        :value="stat.statusText ? undefined : stat.value"
        :suffix="stat.statusText ? '' : '个'"
        :type="stat.label === 'RAG索引' ? (stat.value ? 'success' : 'warning') : stat.label === 'LLM状态' ? (stat.value ? 'success' : 'default') : 'default'"
      >
        <template v-if="stat.statusText" #default>
          <span class="stat-status-text" :class="{ online: stat.value }">{{ stat.statusText }}</span>
        </template>
      </StatCard>
    </div>

    <div class="tab-bar">
      <button
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === 'documents' }"
        @click="activeTab = 'documents'"
      >
        📄 文档管理
      </button>
      <button
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === 'assistant' }"
        @click="activeTab = 'assistant'"
      >
        🤖 AI助手
      </button>
    </div>

    <div v-if="activeTab === 'documents'" class="documents-tab">
      <div class="toolbar">
        <div class="toolbar-left">
          <div class="search-box">
            <span class="search-icon">🔍</span>
            <input
              v-model="searchQuery"
              type="text"
              class="search-input"
              placeholder="搜索文档标题、内容..."
            />
          </div>
          <select v-model="categoryFilter" class="category-select">
            <option v-for="cat in CATEGORIES" :key="cat.value" :value="cat.value">
              {{ cat.label }}
            </option>
          </select>
        </div>
        <div class="toolbar-right">
          <button type="button" v-if="canWrite" class="action-btn" @click="showUploadModal = true">
            📤 上传文档
          </button>
          <button type="button" v-if="canWrite" class="action-btn primary" @click="openAddModal()">
            ➕ 新建文档
          </button>
        </div>
      </div>

      <div v-if="isLoading" class="loading-state">
        <div v-for="i in 4" :key="i" class="skeleton-row">
          <div class="skeleton-line wide"></div>
          <div class="skeleton-line medium"></div>
        </div>
      </div>

      <div v-else class="doc-table">
        <div class="table-header">
          <div class="col-title">标题</div>
          <div class="col-category">分类</div>
          <div class="col-version">版本</div>
          <div class="col-updated">更新时间</div>
          <div class="col-author">作者</div>
          <div class="col-actions">操作</div>
        </div>
        <div
          v-for="doc in filteredDocuments"
          :key="doc.id"
          class="table-row"
        >
          <div class="col-title">
            <div class="doc-title">{{ doc.title }}</div>
            <div class="doc-content-preview">{{ doc.content.slice(0, 60) }}{{ doc.content.length > 60 ? '...' : '' }}</div>
          </div>
          <div class="col-category">
            <span class="category-tag">{{ getCategoryLabel(doc.category) }}</span>
          </div>
          <div class="col-version">
            <span class="version-badge">v{{ doc.version }}</span>
          </div>
          <div class="col-updated">{{ formatTime(doc.updated_at) }}</div>
          <div class="col-author">{{ doc.author }}</div>
          <div class="col-actions">
            <button type="button" v-if="canWrite" class="action-icon-btn" @click="openAddModal(doc)" title="编辑">✏️</button>
            <button type="button" class="action-icon-btn" @click="toggleVersions(doc.id)" title="版本历史">📋</button>
            <button type="button" v-if="canWrite" class="action-icon-btn danger" @click="deleteDocument(doc.id)" title="删除">🗑️</button>
          </div>

          <div v-if="showVersionPanel === doc.id" class="version-panel">
            <div class="version-panel-header">
              <span class="version-panel-title">版本历史</span>
              <button type="button" class="version-close-btn" @click="showVersionPanel = null">✕</button>
            </div>
            <div v-if="isLoadingVersions" class="version-loading">加载中...</div>
            <div v-else-if="versions.length === 0" class="version-empty">暂无版本记录</div>
            <div v-else class="version-list">
              <div v-for="ver in versions" :key="ver.id" class="version-item">
                <div class="version-dot"></div>
                <div class="version-info">
                  <div class="version-header">
                    <span class="version-number">v{{ ver.version }}</span>
                    <span class="version-summary">{{ ver.change_summary }}</span>
                  </div>
                  <div class="version-meta">
                    <span>{{ ver.author }}</span>
                    <span>{{ formatTime(ver.created_at) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-if="filteredDocuments.length === 0 && !isLoading" class="empty-state">
          <div class="empty-icon">📭</div>
          <div>{{ searchQuery ? '未找到匹配的文档' : '暂无文档' }}</div>
        </div>
      </div>
    </div>

    <div v-if="activeTab === 'assistant'" class="assistant-tab">
      <div class="chat-container">
        <div ref="chatListRef" class="chat-list">
          <div v-if="chatMessages.length === 0" class="chat-empty">
            <div class="chat-empty-icon">🤖</div>
            <div class="chat-empty-title">AI 知识库助手</div>
            <div class="chat-empty-desc">基于知识库文档智能回答问题，支持RAG检索增强</div>
            <div class="chat-suggestions">
              <button type="button" class="suggestion-btn" @click="chatInput = '核心路由器的配置规范是什么？'">核心路由器配置规范</button>
              <button type="button" class="suggestion-btn" @click="chatInput = '如何排查BGP路由震荡？'">BGP路由震荡排查</button>
              <button type="button" class="suggestion-btn" @click="chatInput = '防火墙安全策略有哪些？'">防火墙安全策略</button>
            </div>
          </div>
          <div
            v-for="msg in chatMessages"
            :key="msg.id"
            class="chat-message"
            :class="msg.role"
          >
            <div class="msg-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
            <div class="msg-bubble">
              <div class="msg-content">{{ msg.content }}</div>
              <div class="msg-time">{{ formatTime(msg.timestamp) }}</div>
            </div>
          </div>
          <div v-if="isQuerying" class="chat-message assistant">
            <div class="msg-avatar">🤖</div>
            <div class="msg-bubble">
              <div class="msg-typing">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        </div>
        <div class="chat-input-bar">
          <input
            v-model="chatInput"
            type="text"
            class="chat-input"
            placeholder="输入问题查询知识库..."
            @keydown.enter="sendQuery"
            :disabled="isQuerying"
          />
          <button
            type="button"
            class="action-btn primary query-btn"
            :disabled="isQuerying || !chatInput.trim()"
            @click="sendQuery"
          >
            {{ isQuerying ? '查询中...' : '🔍 查询知识库' }}
          </button>
          <button type="button" class="action-btn" @click="clearChat" title="清空对话">🗑️</button>
        </div>
      </div>
    </div>

    <div v-if="showAddModal" class="modal-overlay" @click.self="showAddModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3 class="modal-title">{{ editingDocId ? '编辑文档' : '新建文档' }}</h3>
          <button type="button" class="modal-close" @click="showAddModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">文档标题</label>
            <input v-model="docForm.title" type="text" class="form-input" placeholder="输入文档标题" />
          </div>
          <div class="form-group">
            <label class="form-label">分类</label>
            <select v-model="docForm.category" class="form-input">
              <option v-for="cat in CATEGORIES.filter(c => c.value !== 'all')" :key="cat.value" :value="cat.value">
                {{ cat.label }}
              </option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">内容</label>
            <textarea v-model="docForm.content" class="form-input content-textarea" placeholder="输入文档内容" rows="8"></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="action-btn" @click="showAddModal = false">取消</button>
          <button type="button" class="action-btn primary" :disabled="isSubmitting" @click="submitDocument">
            {{ isSubmitting ? '保存中...' : (editingDocId ? '更新' : '创建') }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="showUploadModal" class="modal-overlay" @click.self="showUploadModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3 class="modal-title">上传文档</h3>
          <button type="button" class="modal-close" @click="showUploadModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="upload-area">
            <div class="upload-icon">📤</div>
            <div class="upload-text">点击或拖拽文件到此处</div>
            <div class="upload-hint">支持格式: {{ SUPPORTED_EXTENSIONS }}</div>
            <input
              type="file"
              class="upload-file-input"
              :accept="SUPPORTED_EXTENSIONS"
              @change="handleFileSelect"
            />
          </div>
          <div v-if="uploadFile" class="upload-file-info">
            <span class="upload-file-name">📎 {{ uploadFile.name }}</span>
            <span class="upload-file-size">{{ (uploadFile.size / 1024).toFixed(1) }} KB</span>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="action-btn" @click="showUploadModal = false">取消</button>
          <button type="button" class="action-btn primary" :disabled="!uploadFile || isUploading" @click="submitUpload">
            {{ isUploading ? '上传中...' : '上传' }}
          </button>
        </div>
      </div>
    </div>
  </PageLayout>
</template>

<style scoped lang="scss">
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(var(--grid-min-col), 1fr));
  gap: var(--panel-gap);
  margin-bottom: var(--spacing-lg);
}

.stat-status-text {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-tertiary);
  &.online { color: var(--color-success); }
}

.llm-status-badge {
  font-size: var(--font-size-xs);
  padding: var(--spacing-xs) 0.625rem;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  gap: 0.375rem;
  backdrop-filter: blur(8px);
  transition: all 0.25s ease;

  &.online {
    background: var(--color-success-bg);
    color: var(--color-success);
    border: 1px solid var(--color-success-border);
  }
  &.offline {
    background: rgba(148, 163, 184, 0.1);
    color: var(--color-text-tertiary);
    border: 1px solid rgba(148, 163, 184, 0.25);
  }
  &.loading {
    background: var(--color-warning-bg);
    color: var(--color-warning);
    border: 1px solid var(--color-warning-border);
    animation: pulse-warning 1.5s ease-in-out infinite;
  }

  .status-dot {
    width: 0.375rem;
    height: 0.375rem;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 6px currentColor;
  }
}

@keyframes pulse-warning {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.tab-bar {
  display: flex;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-lg);
  background: var(--gradient-glass);
  padding: 0.25rem;
  border-radius: var(--radius-lg);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  width: fit-content;
}

.tab-btn {
  padding: 0.5rem 1.25rem;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
  white-space: nowrap;

  &:hover {
    color: var(--color-text-secondary);
    background: var(--color-bg-hover);
  }

  &.active {
    background: var(--color-primary-hover);
    color: var(--color-primary-light);
    border-color: rgba(22, 93, 255, 0.4);
    box-shadow: var(--shadow-glow-primary);
    font-weight: var(--font-weight-semibold);
  }
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  gap: var(--spacing-sm);
  flex: 1;
  min-width: 0;
}

.toolbar-right {
  display: flex;
  gap: var(--spacing-sm);
}

.search-box {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0 0.75rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  flex: 1;
  max-width: 360px;
  transition: border-color 0.25s ease, box-shadow 0.25s ease;

  &:focus-within {
    border-color: var(--input-border-focus);
    box-shadow: var(--input-shadow-focus);
  }
}

.search-icon {
  font-size: var(--font-size-sm);
  flex-shrink: 0;
}

.search-input {
  background: transparent;
  border: none;
  outline: none;
  color: var(--color-text-secondary);
  font-size: var(--font-size-base);
  padding: 0.625rem 0;
  width: 100%;

  &::placeholder { color: var(--color-text-disabled); }
}

.category-select {
  padding: 0.625rem 2rem 0.625rem 0.75rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-secondary);
  font-size: var(--font-size-base);
  cursor: pointer;
  outline: none;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%2394A3B8' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  transition: border-color 0.25s ease, box-shadow 0.25s ease;

  &:focus {
    border-color: var(--input-border-focus);
    box-shadow: var(--input-shadow-focus);
  }

  option {
    background: var(--color-bg-secondary);
    color: var(--color-text-secondary);
  }
}

.action-btn {
  padding: 0.375rem 0.875rem;
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-xs);
  transition: all 0.25s ease;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  white-space: nowrap;
  backdrop-filter: blur(8px);
  min-height: 44px;

  &:hover:not(:disabled) {
    background: var(--color-primary-hover);
    border-color: rgba(59, 130, 246, 0.5);
    box-shadow: var(--shadow-glow-primary-sm);
    color: var(--color-primary-lighter);
    transform: scale(1.02);
  }

  &:active:not(:disabled) {
    transform: scale(0.97);
  }

  &:disabled {
    opacity: 0.35;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  &.primary {
    background: var(--color-primary-hover);
    border-color: rgba(22, 93, 255, 0.4);
    color: var(--color-primary-lighter);
    font-weight: 600;

    &:hover:not(:disabled) {
      background: rgba(22, 93, 255, 0.3);
      border-color: rgba(59, 130, 246, 0.6);
      box-shadow: var(--shadow-glow-primary-md);
      color: #BFDBFE;
      transform: scale(1.02);
    }
  }
}

.loading-state {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.skeleton-row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem;
  background: rgba(15, 23, 42, 0.3);
  border-radius: var(--radius-md);
}

.skeleton-line {
  height: 0.875rem;
  background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 75%);
  background-size: 200% 100%;
  border-radius: var(--radius-sm);
  animation: skeleton-slide 1.5s ease-in-out infinite;
  &.wide { width: 70%; }
  &.medium { width: 55%; }
}

/* skeleton-slide uses global definition from tokens.css */

.doc-table {
  background: var(--gradient-glass);
  border-radius: var(--radius-lg);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  overflow: hidden;
  box-shadow: var(--shadow-card);
}

.table-header {
  display: flex;
  align-items: center;
  padding: 0.625rem 0.75rem;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  font-weight: 600;
  border-bottom: 1px solid var(--color-border-primary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  background: rgba(255, 255, 255, 0.02);
}

.table-row {
  display: flex;
  align-items: center;
  padding: 0.875rem 0.75rem;
  border-bottom: 1px solid var(--color-border-primary);
  transition: all 0.2s ease;
  flex-wrap: wrap;

  &:hover {
    background: var(--color-bg-hover);
  }

  &:last-child {
    border-bottom: none;
  }
}

.col-title { flex: 2; min-width: 0; }
.col-category { width: 100px; }
.col-version { width: 60px; text-align: center; }
.col-updated { width: 100px; color: var(--color-text-tertiary); font-size: var(--font-size-sm); }
.col-author { width: 100px; color: var(--color-text-tertiary); font-size: var(--font-size-sm); }
.col-actions { width: 120px; display: flex; gap: 0.25rem; justify-content: flex-end; }

.doc-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-content-preview {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: 0.125rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.category-tag {
  font-size: var(--font-size-xs);
  padding: 2px 0.5rem;
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border-radius: var(--radius-xs);
}

.version-badge {
  font-size: var(--font-size-xs);
  padding: 2px 0.5rem;
  background: var(--color-success-bg);
  color: var(--color-success);
  border-radius: var(--radius-xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.action-icon-btn {
  width: 1.75rem;
  height: 1.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(22, 93, 255, 0.08);
  border: 1px solid var(--color-primary-hover);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: all 0.25s ease;
  padding: 0;
  backdrop-filter: blur(8px);

  &:hover {
    background: var(--color-primary-hover);
    border-color: rgba(59, 130, 246, 0.5);
    box-shadow: var(--shadow-glow-primary-sm);
    transform: scale(1.1);
  }

  &:active {
    transform: scale(0.95);
  }

  &.danger:hover {
    background: var(--color-error-glow);
    border-color: rgba(239, 68, 68, 0.5);
    box-shadow: var(--shadow-glow-error-sm);
  }
}

.version-panel {
  flex: 1 1 100%;
  margin-top: 0.75rem;
  padding: 0.75rem;
  background: rgba(15, 23, 42, 0.5);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-primary);
  animation: panel-expand 0.25s ease;
}

@keyframes panel-expand {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 500px; }
}

.version-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.version-panel-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.version-close-btn {
  width: 1.25rem;
  height: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--color-text-tertiary);
  cursor: pointer;
  font-size: var(--font-size-sm);
  border-radius: var(--radius-sm);
  transition: all 0.2s ease;

  &:hover {
    background: var(--color-bg-hover);
    color: var(--color-text-secondary);
  }
}

.version-loading, .version-empty {
  text-align: center;
  padding: var(--spacing-md);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.version-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.version-item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.5rem 0;
  position: relative;
}

.version-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--color-primary);
  margin-top: 0.375rem;
  flex-shrink: 0;
  box-shadow: 0 0 6px rgba(22, 93, 255, 0.3);
}

.version-info {
  flex: 1;
  min-width: 0;
}

.version-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.version-number {
  font-size: var(--font-size-xs);
  font-weight: 700;
  color: var(--color-primary-light);
  background: var(--color-primary-bg);
  padding: 1px 0.375rem;
  border-radius: var(--radius-xs);
}

.version-summary {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.version-meta {
  display: flex;
  gap: 0.75rem;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: 0.125rem;
}

.empty-state {
  text-align: center;
  padding: var(--spacing-xl) var(--spacing-lg);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
}

.empty-icon {
  font-size: var(--font-size-3xl);
  margin-bottom: var(--spacing-sm);
  opacity: 0.6;
}

.chat-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 320px);
  min-height: 400px;
  background: var(--gradient-glass);
  border-radius: var(--radius-lg);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  overflow: hidden;
  box-shadow: var(--shadow-card);
}

.chat-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  text-align: center;
  gap: var(--spacing-sm);
}

.chat-empty-icon {
  font-size: 3rem;
  opacity: 0.6;
}

.chat-empty-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
}

.chat-empty-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  max-width: 320px;
}

.chat-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
  justify-content: center;
}

.suggestion-btn {
  padding: 0.375rem 0.75rem;
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  color: var(--color-primary-light);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);

  &:hover {
    background: var(--color-primary-hover);
    border-color: rgba(22, 93, 255, 0.5);
    transform: scale(1.02);
  }

  &:active {
    transform: scale(0.97);
  }
}

.chat-message {
  display: flex;
  gap: 0.75rem;
  animation: msg-enter 0.3s ease;

  &.user {
    flex-direction: row-reverse;
  }
}

/* msg-enter uses global item-enter definition from tokens.css */

.msg-avatar {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-hover);
  border-radius: 50%;
  font-size: var(--font-size-base);
  flex-shrink: 0;
}

.msg-bubble {
  max-width: 70%;
  padding: 0.75rem 1rem;
  border-radius: var(--radius-lg);
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
}

.user .msg-bubble {
  background: var(--color-primary-hover);
  color: var(--color-text-primary);
  border-bottom-right-radius: 4px;
}

.assistant .msg-bubble {
  background: rgba(15, 23, 42, 0.6);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-primary);
  border-bottom-left-radius: 4px;
}

.msg-content {
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-disabled);
  margin-top: 0.25rem;
  text-align: right;
}

.msg-typing {
  display: flex;
  gap: 0.375rem;
  padding: 0.25rem 0;

  span {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: var(--color-text-tertiary);
    animation: typing-bounce 1.2s ease-in-out infinite;

    &:nth-child(2) { animation-delay: 0.2s; }
    &:nth-child(3) { animation-delay: 0.4s; }
  }
}

@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

.chat-input-bar {
  display: flex;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-lg);
  border-top: 1px solid var(--color-border-primary);
  background: rgba(15, 23, 42, 0.4);
  align-items: center;
}

.chat-input {
  flex: 1;
  padding: 0.625rem 0.875rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-secondary);
  font-size: var(--font-size-base);
  outline: none;
  transition: border-color 0.25s ease, box-shadow 0.25s ease;

  &:focus {
    border-color: var(--input-border-focus);
    box-shadow: var(--input-shadow-focus);
  }

  &::placeholder { color: var(--color-text-disabled); }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.query-btn {
  min-width: 120px;
  justify-content: center;
}

.modal-overlay {
  position: fixed;
  top: 0; right: 0; bottom: 0; left: 0;
  background: var(--modal-overlay-bg);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-overlay);
  padding: var(--spacing-md);
  animation: modal-overlay-in 0.2s ease;
}

@keyframes modal-overlay-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-content {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-primary);
  padding: var(--spacing-xl);
  box-shadow: var(--shadow-modal);
  max-width: 600px;
  width: 90vw;
  max-height: 85vh;
  overflow-y: auto;
  animation: modal-content-in 0.25s ease;
}

@keyframes modal-content-in {
  from { opacity: 0; transform: scale(0.95) translateY(8px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-border-primary);
}

.modal-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
}

.modal-close {
  width: 1.75rem;
  height: 1.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);

  &:hover {
    background: var(--color-bg-hover);
    color: var(--color-text-secondary);
    border-color: var(--color-border-hover);
    transform: scale(1.02);
  }

  &:active {
    transform: scale(0.97);
  }
}

.modal-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.form-label {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
}

.form-input {
  width: 100%;
  padding: var(--input-padding);
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-secondary);
  font-size: var(--font-size-md);
  transition: all 0.2s ease;
  outline: none;
  box-sizing: border-box;

  &:focus {
    border-color: var(--input-border-focus);
    box-shadow: var(--input-shadow-focus);
  }

  &::placeholder { color: var(--color-text-disabled); }
}

.content-textarea {
  resize: vertical;
  min-height: 160px;
  font-family: var(--font-family-mono);
  line-height: var(--line-height-relaxed);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-primary);
}

.upload-area {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl);
  border: 2px dashed var(--color-border-primary);
  border-radius: var(--radius-lg);
  background: var(--color-bg-input);
  cursor: pointer;
  transition: all 0.25s ease;

  &:hover {
    border-color: var(--color-primary-border);
    background: var(--color-primary-bg);
  }
}

.upload-icon {
  font-size: 2rem;
  margin-bottom: var(--spacing-sm);
  opacity: 0.7;
}

.upload-text {
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

.upload-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: var(--spacing-xs);
}

.upload-file-input {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  opacity: 0;
  cursor: pointer;
}

.upload-file-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.75rem;
  background: var(--color-primary-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-primary-border);
}

.upload-file-name {
  font-size: var(--font-size-sm);
  color: var(--color-primary-light);
}

.upload-file-size {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .toolbar-left, .toolbar-right {
    flex-direction: column;
  }
  .search-box {
    max-width: none;
  }
  .table-header { display: none; }
  .table-row {
    flex-wrap: wrap;
    gap: 0.375rem;
  }
  .col-title { flex: 1 1 100%; }
  .col-category, .col-version, .col-updated, .col-author {
    width: auto;
    flex: 0 0 auto;
  }
  .col-actions {
    width: auto;
    flex: 0 0 auto;
    margin-left: auto;
  }
  .tab-bar {
    width: 100%;
  }
  .tab-btn {
    flex: 1;
    justify-content: center;
  }
  .chat-input-bar {
    flex-wrap: wrap;
  }
  .query-btn {
    min-width: auto;
    flex: 1;
  }
  .msg-bubble {
    max-width: 85%;
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
  .chat-suggestions {
    flex-direction: column;
  }
}

@media (prefers-reduced-motion: reduce) {
  .skeleton-line { animation: none; }
  .chat-message { animation: none; }
  .version-panel { animation: none; }
  .modal-overlay { animation: none; }
  .modal-content { animation: none; }
  .msg-typing span { animation: none; opacity: 0.6; }
  .llm-status-badge.loading { animation: none; }
}
</style>
