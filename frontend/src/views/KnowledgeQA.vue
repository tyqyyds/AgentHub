<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { apiClient, api, authFetch } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  confidence?: number
  sources?: string[]
  timestamp: string
}

interface DocumentInfo {
  id: string
  name: string
  type: string
  size: number
}

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isLoading = ref(false)
const documents = ref<DocumentInfo[]>([])
const chatContainer = ref<HTMLElement | null>(null)
const docPage = ref(1)
const docPageSize = 15
const MAX_INPUT_LENGTH = 500

const suggestedQuestions = [
  '如何配置QoS策略?',
  'OSPF区域划分原则?',
  'BGP故障排查步骤?'
]

const generateId = () => Math.random().toString(36).substring(2, 10)

const scrollToBottom = async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

const sendMessage = async (text?: string) => {
  const question = (text || inputText.value).trim()
  if (!question || isLoading.value) return
  if (question.length > MAX_INPUT_LENGTH) {
    showToast(`问题不能超过${MAX_INPUT_LENGTH}个字符`, 'warning')
    return
  }

  inputText.value = ''

  const userMsg: ChatMessage = {
    id: generateId(),
    role: 'user',
    content: question,
    timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  messages.value.push(userMsg)
  await scrollToBottom()

  isLoading.value = true
  try {
    const res = await apiClient.post<{ answer: string; sources: string[]; confidence: number }>(
      api.knowledge.query,
      { question }
    )

    const aiMsg: ChatMessage = {
      id: generateId(),
      role: 'assistant',
      content: res.data?.answer || '暂无相关回答',
      confidence: res.data?.confidence,
      sources: res.data?.sources || [],
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    messages.value.push(aiMsg)
  } catch {
    const errorMsg: ChatMessage = {
      id: generateId(),
      role: 'assistant',
      content: '抱歉，查询失败，请稍后重试。',
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    messages.value.push(errorMsg)
    showToast('知识查询失败', 'error')
  } finally {
    isLoading.value = false
    await scrollToBottom()
  }
}

const fetchDocuments = async () => {
  try {
    const res = await apiClient.get<DocumentInfo[]>(api.knowledge.documents)
    documents.value = res.data || []
  } catch {
    documents.value = []
  }
}

const getConfidenceColor = (confidence: number) => {
  if (confidence >= 0.8) return '#52C41A'
  if (confidence >= 0.6) return '#F59E0B'
  return '#EF4444'
}

const getConfidenceLabel = (confidence: number) => {
  if (confidence >= 0.8) return '高'
  if (confidence >= 0.6) return '中'
  return '低'
}

const paginatedDocs = computed(() => {
  const start = (docPage.value - 1) * docPageSize
  return documents.value.slice(start, start + docPageSize)
})

const totalDocPages = computed(() => Math.ceil(documents.value.length / docPageSize))

const showUploadDialog = ref(false)
const uploadForm = ref({ title: '', content: '' })
const isUploading = ref(false)
const showMobileSidePanel = ref(false)

const uploadDocument = async () => {
  if (!uploadForm.value.title.trim()) {
    showToast('请输入文档标题', 'warning')
    return
  }
  if (!uploadForm.value.content.trim()) {
    showToast('请输入文档内容', 'warning')
    return
  }
  isUploading.value = true
  try {
    await apiClient.post(api.knowledge.addDocument, {
      title: uploadForm.value.title,
      content: uploadForm.value.content
    })
    showToast('文档上传成功', 'success')
    showUploadDialog.value = false
    uploadForm.value = { title: '', content: '' }
    await fetchDocuments()
  } catch {
    showToast('文档上传失败', 'error')
  } finally {
    isUploading.value = false
  }
}

const handleFileUpload = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (file.size > 10 * 1024 * 1024) {
    showToast('文件大小不能超过10MB', 'warning')
    return
  }
  const reader = new FileReader()
  reader.onload = async (e) => {
    const content = e.target?.result as string
    uploadForm.value.title = file.name.replace(/\.[^/.]+$/, '')
    uploadForm.value.content = content
  }
  reader.readAsText(file)
  input.value = ''
}

const deleteDocument = async (docId: string) => {
  try {
    await apiClient.delete(api.knowledge.documents + '/' + docId)
    showToast('文档已删除', 'success')
    await fetchDocuments()
  } catch {
    showToast('删除文档失败', 'error')
  }
}

onMounted(() => {
  fetchDocuments()
})
</script>

<template>
  <div class="knowledge-qa">
    <div class="kq-bg">
      <div class="bg-grid"></div>
      <div class="bg-glow glow-1"></div>
      <div class="bg-glow glow-2"></div>
    </div>

    <div class="kq-header">
      <div class="header-left">
        <h1 class="page-title">运维知识助手</h1>
        <p class="page-subtitle">Knowledge-Based QA for Network Operations</p>
      </div>
      <div class="header-right">
        <button type="button" class="upload-btn" @click="showUploadDialog = true" aria-label="上传文档">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          上传文档
        </button>
        <span class="doc-count">
          📚 {{ documents.length }} 知识文档
        </span>
      </div>
    </div>

    <div class="kq-content">
      <div class="chat-panel">
        <div ref="chatContainer" class="chat-messages">
          <div v-if="messages.length === 0" class="welcome-state">
            <div class="welcome-icon">💡</div>
            <h3 class="welcome-title">运维知识助手</h3>
            <p class="welcome-desc">输入问题获取运维知识支持，或点击下方建议问题快速开始</p>
            <div class="suggested-questions">
              <button
                type="button"
                v-for="q in suggestedQuestions"
                :key="q"
                class="suggestion-btn"
                @click="sendMessage(q)"
                :aria-label="q"
              >
                {{ q }}
              </button>
            </div>
          </div>

          <div
            v-for="msg in messages"
            :key="msg.id"
            :class="['message-row', msg.role]"
          >
            <div :class="['message-bubble', msg.role]">
              <div v-if="msg.role === 'assistant'" class="bubble-avatar">🤖</div>
              <div class="bubble-content">
                <div class="bubble-text">{{ msg.content }}</div>
                <div v-if="msg.role === 'assistant' && msg.confidence !== undefined" class="bubble-meta">
                  <span
                    class="confidence-badge"
                    :style="{ background: `${getConfidenceColor(msg.confidence)}20`, color: getConfidenceColor(msg.confidence), borderColor: `${getConfidenceColor(msg.confidence)}40` }"
                  >
                    置信度: {{ Math.round(msg.confidence * 100) }}% ({{ getConfidenceLabel(msg.confidence) }})
                  </span>
                  <div v-if="msg.sources && msg.sources.length > 0" class="sources">
                    <span class="sources-label">来源:</span>
                    <span v-for="(src, idx) in msg.sources" :key="idx" class="source-tag">{{ src }}</span>
                  </div>
                </div>
                <span class="bubble-time">{{ msg.timestamp }}</span>
              </div>
              <div v-if="msg.role === 'user'" class="bubble-avatar user-avatar">👤</div>
            </div>
          </div>

          <div v-if="isLoading" class="message-row assistant">
            <div class="message-bubble assistant">
              <div class="bubble-avatar">🤖</div>
              <div class="bubble-content">
                <div class="typing-indicator">
                  <span class="typing-dot"></span>
                  <span class="typing-dot"></span>
                  <span class="typing-dot"></span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="chat-input-bar">
          <div class="input-wrapper">
            <button
              type="button"
              class="mobile-panel-toggle"
              @click="showMobileSidePanel = !showMobileSidePanel"
              aria-label="知识库面板"
              title="知识库面板"
            >
              📚
            </button>
            <input
              v-model="inputText"
              type="text"
              class="chat-input"
              placeholder="输入运维问题..."
              :disabled="isLoading"
              :maxlength="MAX_INPUT_LENGTH"
              @keyup.enter="sendMessage()"
              aria-label="输入运维问题"
            />
            <button
              type="button"
              class="send-btn"
              :disabled="!inputText.trim() || isLoading"
              @click="sendMessage()"
              aria-label="发送"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </div>
          <div v-if="messages.length === 0" class="quick-suggestions">
            <button
              type="button"
              v-for="q in suggestedQuestions"
              :key="q"
              class="quick-btn"
              @click="sendMessage(q)"
              :aria-label="q"
            >
              {{ q }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="showMobileSidePanel" class="mobile-panel-backdrop" @click="showMobileSidePanel = false"></div>
      <div :class="['side-panel', { 'mobile-open': showMobileSidePanel }]">
        <div class="panel-section">
          <h3 class="section-title">知识库文档</h3>
          <div class="doc-list">
            <div v-for="doc in paginatedDocs" :key="doc.id" class="doc-item">
              <span class="doc-icon">📄</span>
              <span class="doc-name" :title="doc.name">{{ doc.name }}</span>
              <button type="button" class="doc-delete-btn" @click="deleteDocument(doc.id)" aria-label="删除文档" title="删除">✕</button>
            </div>
            <div v-if="documents.length === 0" class="empty-docs">暂无文档</div>
          </div>
          <div v-if="totalDocPages > 1" class="doc-pagination">
            <button type="button" class="page-btn" :disabled="docPage <= 1" @click="docPage--" aria-label="上一页">‹</button>
            <span class="page-info">{{ docPage }} / {{ totalDocPages }}</span>
            <button type="button" class="page-btn" :disabled="docPage >= totalDocPages" @click="docPage++" aria-label="下一页">›</button>
          </div>
        </div>

        <div class="panel-section">
          <h3 class="section-title">建议问题</h3>
          <div class="side-suggestions">
            <button
              type="button"
              v-for="q in suggestedQuestions"
              :key="q"
              class="side-suggestion-btn"
              @click="sendMessage(q)"
              :aria-label="q"
            >
              {{ q }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showUploadDialog" class="modal-overlay" @click.self="showUploadDialog = false" role="dialog" aria-modal="true">
        <div class="modal-content">
          <div class="modal-header">
            <h3 class="modal-title">上传知识文档</h3>
            <button class="modal-close" @click="showUploadDialog = false">✕</button>
          </div>
          <div class="form-group">
            <label class="form-label">文档标题 <span class="required-star">*</span></label>
            <input v-model="uploadForm.title" type="text" class="form-input" placeholder="输入文档标题" />
          </div>
          <div class="form-group">
            <label class="form-label">文档内容 <span class="required-star">*</span></label>
            <textarea v-model="uploadForm.content" class="form-textarea" placeholder="输入或粘贴文档内容" rows="8"></textarea>
          </div>
          <div class="form-group">
            <label class="form-label">或从文件导入</label>
            <input type="file" class="file-input" accept=".txt,.md,.json,.csv,.log" @change="handleFileUpload" />
          </div>
          <div class="modal-actions">
            <button class="modal-btn cancel" @click="showUploadDialog = false">取消</button>
            <button class="modal-btn submit" @click="uploadDocument" :disabled="isUploading">
              {{ isUploading ? '上传中...' : '上传' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.knowledge-qa {
  position: relative;
  animation: page-enter 0.5s ease-out;
  min-height: 100vh;
  padding: 24px;
}

.kq-bg {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.bg-grid {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background-image:
    linear-gradient(rgba(59, 130, 246, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(59, 130, 246, 0.03) 1px, transparent 1px);
  background-size: 60px 60px;
  mask-image: radial-gradient(ellipse 80% 60% at 50% 30%, black 20%, transparent 70%);
}

.bg-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
}

.glow-1 {
  width: 400px;
  height: 400px;
  background: rgba(59, 130, 246, 0.08);
  top: -100px;
  right: 10%;
  animation: glow-float 12s ease-in-out infinite;
}

.glow-2 {
  width: 300px;
  height: 300px;
  background: rgba(0, 212, 255, 0.06);
  bottom: 10%;
  left: 5%;
  animation: glow-float 15s ease-in-out infinite reverse;
}

@keyframes glow-float {
  0%, 100% { transform: translate(0, 0); }
  33% { transform: translate(30px, -20px); }
  66% { transform: translate(-20px, 15px); }
}

@keyframes page-enter {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.knowledge-qa > *:not(.kq-bg) {
  position: relative;
  z-index: 1;
}

.kq-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  margin: 0;
  background: linear-gradient(135deg, #E2E8F0 0%, #3b82f6 50%, #E2E8F0 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: title-shimmer 4s ease-in-out infinite;
}

.page-subtitle {
  font-size: 13px;
  color: #94A3B8;
  margin: 0;
}

@keyframes title-shimmer {
  0%, 100% { background-position: 0% center; }
  50% { background-position: 200% center; }
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.upload-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.25s ease;
  min-height: 36px;
}

.upload-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
}

.doc-count {
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 20px;
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.2);
  font-weight: 500;
}

.kq-content {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 20px;
  height: calc(100vh - 160px);
}

.chat-panel {
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.65) 0%, rgba(20, 30, 48, 0.45) 100%);
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(12px);
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.welcome-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  text-align: center;
  padding: 40px 24px;
}

.welcome-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.welcome-title {
  font-size: 20px;
  font-weight: 700;
  color: white;
  margin: 0 0 8px;
}

.welcome-desc {
  font-size: 14px;
  color: #94A3B8;
  margin: 0 0 24px;
  max-width: 400px;
}

.suggested-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
}

.suggestion-btn {
  padding: 10px 20px;
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.25);
  border-radius: 10px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.25s ease;
  white-space: nowrap;
  min-height: 44px;
}

.suggestion-btn:hover {
  background: rgba(59, 130, 246, 0.2);
  border-color: rgba(59, 130, 246, 0.5);
  transform: translateY(-1px);
}

.message-row {
  display: flex;
  width: 100%;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.assistant {
  justify-content: flex-start;
}

.message-bubble {
  display: flex;
  gap: 10px;
  max-width: 80%;
  align-items: flex-start;
}

.message-bubble.user {
  flex-direction: row-reverse;
}

.bubble-avatar {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.user-avatar {
  background: rgba(59, 130, 246, 0.2);
  border-color: rgba(59, 130, 246, 0.3);
}

.bubble-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bubble-text {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.message-bubble.assistant .bubble-text {
  background: rgba(30, 41, 59, 0.8);
  color: #E2E8F0;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-top-left-radius: 4px;
}

.message-bubble.user .bubble-text {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: white;
  border-top-right-radius: 4px;
}

.bubble-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.confidence-badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 8px;
  font-weight: 600;
  border: 1px solid;
}

.sources {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.sources-label {
  font-size: 11px;
  color: #64748B;
}

.source-tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(100, 116, 139, 0.15);
  color: #94A3B8;
}

.bubble-time {
  font-size: 11px;
  color: #64748B;
  padding: 0 4px;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 14px 18px;
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  border-top-left-radius: 4px;
}

.typing-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #3b82f6;
  animation: typing-bounce 1.4s ease-in-out infinite;
}

.typing-dot:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

.chat-input-bar {
  padding: 16px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(15, 23, 42, 0.3);
}

.input-wrapper {
  display: flex;
  gap: 10px;
}

.chat-input {
  flex: 1;
  padding: 12px 16px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  color: #E2E8F0;
  font-size: 14px;
  outline: none;
  transition: all 0.25s ease;
}

.chat-input::placeholder {
  color: #64748B;
}

.chat-input:focus {
  border-color: rgba(59, 130, 246, 0.5);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.chat-input:disabled {
  opacity: 0.6;
}

.send-btn {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: white;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.25s ease;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.quick-suggestions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.quick-btn {
  padding: 6px 14px;
  background: rgba(59, 130, 246, 0.08);
  color: #94A3B8;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  min-height: 44px;
}

.quick-btn:hover {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
  border-color: rgba(59, 130, 246, 0.3);
}

.side-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel-section {
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.65) 0%, rgba(20, 30, 48, 0.45) 100%);
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(12px);
  padding: 16px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: white;
  margin: 0 0 12px;
}

.doc-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.doc-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.04);
  transition: all 0.2s ease;
}

.doc-item:hover {
  border-color: rgba(59, 130, 246, 0.2);
}

.doc-delete-btn {
  background: none;
  border: none;
  color: #64748B;
  font-size: 14px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.2s ease;
  flex-shrink: 0;
  line-height: 1;
}

.doc-delete-btn:hover {
  color: #EF4444;
  background: rgba(239, 68, 68, 0.1);
}

.doc-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.doc-name {
  font-size: 12px;
  color: #94A3B8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-docs {
  text-align: center;
  padding: 20px;
  color: #64748B;
  font-size: 13px;
}

.doc-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.page-btn {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.page-btn:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.2);
}

.page-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.page-info {
  font-size: 12px;
  color: #94A3B8;
}

.side-suggestions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.side-suggestion-btn {
  width: 100%;
  padding: 10px 14px;
  background: rgba(59, 130, 246, 0.08);
  color: #94A3B8;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
  min-height: 44px;
}

.side-suggestion-btn:hover {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
  border-color: rgba(59, 130, 246, 0.3);
}

@media (max-width: 900px) {
  .kq-content {
    grid-template-columns: 1fr;
    height: calc(100vh - 160px);
  }

  .side-panel {
    display: none;
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 280px;
    z-index: 200;
    background: #1E293B;
    border-left: 1px solid rgba(255, 255, 255, 0.1);
    padding: 16px;
    overflow-y: auto;
    transform: translateX(100%);
    transition: transform 0.3s ease;
  }

  .side-panel.mobile-open {
    display: flex;
    transform: translateX(0);
  }

  .mobile-panel-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 199;
  }

  .mobile-panel-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    background: rgba(59, 130, 246, 0.1);
    border: 1px solid rgba(59, 130, 246, 0.2);
    border-radius: 12px;
    font-size: 18px;
    cursor: pointer;
    flex-shrink: 0;
    transition: all 0.2s ease;
  }

  .mobile-panel-toggle:hover {
    background: rgba(59, 130, 246, 0.2);
  }

  .kq-header {
    flex-direction: column;
    gap: 12px;
    align-items: flex-start;
  }
}

@media (min-width: 901px) {
  .mobile-panel-toggle {
    display: none;
  }
}

@media (max-width: 480px) {
  .knowledge-qa {
    padding: 12px;
  }

  .page-title {
    font-size: 20px;
  }

  .message-bubble {
    max-width: 90%;
  }

  .chat-input {
    font-size: 16px;
  }

  .suggestion-btn {
    font-size: 12px;
    padding: 8px 14px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .knowledge-qa,
  .typing-dot,
  .bg-glow {
    animation: none !important;
    transition: none !important;
  }
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-content {
  background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
  border-radius: 16px;
  padding: 24px;
  width: 90%;
  max-width: 560px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.modal-title {
  font-size: 18px;
  font-weight: 600;
  color: white;
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  color: #94A3B8;
  font-size: 24px;
  cursor: pointer;
  padding: 4px;
  line-height: 1;
  transition: color 0.2s ease;
}

.modal-close:hover {
  color: white;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #94A3B8;
  margin-bottom: 6px;
}

.required-star {
  color: #EF4444;
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #E2E8F0;
  font-size: 14px;
  outline: none;
  transition: all 0.25s ease;
  box-sizing: border-box;
}

.form-input::placeholder {
  color: #64748B;
}

.form-input:focus {
  border-color: rgba(59, 130, 246, 0.5);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-textarea {
  width: 100%;
  padding: 10px 14px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #E2E8F0;
  font-size: 14px;
  outline: none;
  transition: all 0.25s ease;
  resize: vertical;
  font-family: inherit;
  box-sizing: border-box;
}

.form-textarea::placeholder {
  color: #64748B;
}

.form-textarea:focus {
  border-color: rgba(59, 130, 246, 0.5);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.file-input {
  width: 100%;
  padding: 10px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px dashed rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  color: #94A3B8;
  font-size: 13px;
  cursor: pointer;
}

.file-input::file-selector-button {
  padding: 6px 14px;
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  margin-right: 10px;
}

.modal-actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

.modal-btn {
  flex: 1;
  padding: 12px;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.25s ease;
}

.modal-btn.cancel {
  background: rgba(15, 23, 42, 0.6);
  color: #94A3B8;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.modal-btn.cancel:hover {
  background: rgba(15, 23, 42, 0.8);
  color: white;
}

.modal-btn.submit {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: white;
}

.modal-btn.submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
}

.modal-btn.submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
