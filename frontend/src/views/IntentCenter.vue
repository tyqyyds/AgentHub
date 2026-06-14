<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick, onUnmounted } from 'vue'
import DOMPurify from 'dompurify'
import * as echarts from 'echarts'
import { auditLogService } from '../utils/auditLogService'
import { showToast } from '../utils/toast'
import { parseIntent, validateIntentInput } from '../utils/intentParser'
import { useLogger } from '@/utils/logger'
import { POLLING_INTERVAL, UI } from '@/config'
import { api, authFetch, apiClient } from '@/utils/apiClient'
import { useAuthStore } from '@/stores/auth'
import { getStatusConfig } from '@/utils/constants'
import { useApi } from '@/composables/useApi'
import TemplateMarketPanel from '@/components/AiAssistant/TemplateMarketPanel.vue'

const { info, warn, error: logError, debug } = useLogger()
const { error: apiError } = useApi()
const authStore = useAuthStore()
const canWrite = computed(() => authStore.userRole !== 'viewer')
const intentCenterError = ref<string | null>(null)

interface ProcessingLog { timestamp: string; message: string }
interface IntentHistoryItem {
  id: string | number; userInput: string; structuredOutput: Record<string, unknown>
  status: 'completed' | 'pending' | 'rejected' | 'running' | 'approved'; timestamp: string
  createdAt?: string; updatedAt?: string; approvalStatus: string; executionStatus: string
  processingLogs: ProcessingLog[]; device: string
  execution_result?: string | Record<string, unknown> | null; intent_name?: string
}
interface SmartSuggestion { type: string; icon: string; title: string; description: string; action?: string }
interface DiffLine { lineNumber: number; oldLine: string; newLine: string; type: 'same' | 'added' | 'removed' | 'changed'; selected: boolean }
interface MetricCard { label: string; value: number; displayValue: number; unit: string; icon: string; color: string; filterKey: string; animFrameId: number | null }
interface CopilotMessage { id: string; role: 'user' | 'assistant' | 'system'; content: string; timestamp: Date; suggestions?: string[] }
interface ThinkingStep { icon: string; title: string; desc: string }

let copilotMsgCounter = 0
const genCopilotId = () => `cp_${Date.now()}_${++copilotMsgCounter}`

const pageSize = UI.PAGE_SIZE
const intentInput = ref('')
const isProcessing = ref(false)
const intentHistory = ref<IntentHistoryItem[]>([])
const currentPage = ref(1)
const isPolling = ref(true)
const pollInterval = ref<number | null>(null)
const lastUpdateTime = ref<Date | null>(null)
const selectedIntent = ref<IntentHistoryItem | null>(null)
const showIntentDetail = ref(false)
const isRefreshing = ref(false)
const isMockData = ref(false)
const isLoading = ref(true)

const COPILOT_STORAGE_KEY = 'copilot_messages'
const COPILOT_STORAGE_TS_KEY = 'copilot_messages_ts'
const COPILOT_EXPIRY_MS = 24 * 60 * 60 * 1000

const defaultWelcomeMessage = (): CopilotMessage[] => [{
  id: genCopilotId(),
  role: 'assistant' as const,
  content: '您好！我是智能运维副驾，请描述您的网络运维需求。如果描述不够清晰，我会主动向您确认。',
  timestamp: new Date(),
  suggestions: ['保障带宽', '开放访问', '故障诊断', '链路切换']
}]

const loadCopilotMessages = (): CopilotMessage[] => {
  try {
    const storedTs = localStorage.getItem(COPILOT_STORAGE_TS_KEY)
    if (storedTs) {
      const savedTime = new Date(storedTs).getTime()
      if (Date.now() - savedTime > COPILOT_EXPIRY_MS) {
        localStorage.removeItem(COPILOT_STORAGE_KEY)
        localStorage.removeItem(COPILOT_STORAGE_TS_KEY)
        return defaultWelcomeMessage()
      }
    }
    const stored = localStorage.getItem(COPILOT_STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored)
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed.map((m: Record<string, unknown>) => ({ ...m, id: (m.id as string) || genCopilotId(), timestamp: new Date(m.timestamp as string) })) as CopilotMessage[]
      }
    }
  } catch (err: unknown) {
    if (err instanceof Error) warn('加载副驾消息失败', { error: err.message })
  }
  return defaultWelcomeMessage()
}

const saveCopilotMessages = () => {
  try {
    const toSave = copilotMessages.value.slice(-50)
    localStorage.setItem(COPILOT_STORAGE_KEY, JSON.stringify(toSave))
    localStorage.setItem(COPILOT_STORAGE_TS_KEY, new Date().toISOString())
  } catch (err: unknown) {
    if (err instanceof Error) warn('保存副驾消息失败', { error: err.message })
  }
}

const copilotMessages = ref<CopilotMessage[]>(loadCopilotMessages())
const showCopilotChat = ref(false)
const copilotInput = ref('')
const autocompleteSuggestions = ref<string[]>([])
const showAutocomplete = ref(false)

interface ValidationError {
  type: 'empty' | 'too_short' | 'meaningless' | 'low_confidence' | 'unrecognized' | 'semantic_mismatch' | 'security'
  title: string
  description: string
  suggestions: Array<{ text: string; fill: string }>
  icon: string
  severity: 'error' | 'warning'
}
const validationError = ref<ValidationError | null>(null)

const INTENT_SUGGESTIONS: Record<string, string[]> = {
  '带宽': ['保障带宽至少500M', '限制非关键流量带宽', '为视频会议保障200M带宽'],
  '访问': ['开放研发网到生产网访问', '限制外部网络访问', '配置ACL白名单'],
  '故障': ['诊断链路故障', '排查设备连通性', '分析丢包原因'],
  '链路': ['主备链路切换', '新增备用链路', '链路负载均衡'],
  '监控': ['监控设备CPU利用率', '监控带宽使用趋势', '设置延迟告警阈值'],
  'QoS': ['配置QoS优先级', '保障关键业务流量', '流量整形配置']
}

const MIN_DISPLAY_CONFIDENCE = 0.35

const buildValidationError = (type: ValidationError['type'], message: string, confidence?: number): ValidationError => {
  const errorMap: Record<string, Omit<ValidationError, 'description'>> = {
    empty: { type: 'empty', title: '输入为空', icon: '📝', severity: 'error', suggestions: [{ text: '保障研发子网视频会议流量最小200M带宽', fill: '保障研发子网视频会议流量最小200M带宽' }, { text: '开放办公子网到生产子网的SSH访问', fill: '开放办公子网到生产子网的SSH访问端口22' }] },
    too_short: { type: 'too_short', title: '描述过于简短', icon: '📏', severity: 'warning', suggestions: [{ text: '添加目标设备或子网', fill: '保障目标子网' }, { text: '指定操作类型和参数', fill: '配置设备的' }] },
    meaningless: { type: 'meaningless', title: '无法识别有效意图', icon: '❓', severity: 'error', suggestions: [{ text: '保障带宽', fill: '保障研发子网视频会议流量最小200M带宽' }, { text: '访问控制', fill: '开放办公子网到生产子网的SSH访问端口22' }, { text: '故障诊断', fill: '诊断核心路由器的连通性问题' }] },
    low_confidence: { type: 'low_confidence', title: `意图识别不确定（${Math.round((confidence || 0) * 100)}%）`, icon: '⚠️', severity: 'warning', suggestions: [{ text: '添加更多关键词', fill: '' }, { text: '指定目标设备', fill: '' }, { text: '使用模板快速输入', fill: '' }] },
    unrecognized: { type: 'unrecognized', title: '意图无法执行', icon: '🚫', severity: 'error', suggestions: [{ text: '带宽保障', fill: '保障研发子网视频会议流量最小200M带宽' }, { text: '访问控制', fill: '开放办公子网到生产子网的SSH访问端口22' }, { text: '故障诊断', fill: '诊断核心路由器的连通性问题' }, { text: '链路管理', fill: '将汇聚交换机1的流量切换到备用链路' }] },
    semantic_mismatch: { type: 'semantic_mismatch', title: '意图描述与操作类型不匹配', icon: '🔗', severity: 'error', suggestions: [{ text: '重新描述意图', fill: '' }, { text: '使用模板', fill: '' }] },
    security: { type: 'security', title: '安全扫描拦截', icon: '🛡️', severity: 'error', suggestions: [] }
  }
  const base = errorMap[type] || errorMap.unrecognized
  return { ...base, description: message }
}

const applyValidationSuggestion = (fill: string) => {
  if (fill) {
    intentInput.value = fill
    validationError.value = null
    nextTick(() => {
      const t = document.querySelector('.intent-textarea') as HTMLTextAreaElement
      if (t) t.focus()
    })
  } else {
    showTemplates.value = true
    validationError.value = null
  }
}

const dismissValidationError = () => { validationError.value = null }

const focusIntentInput = () => {
  nextTick(() => {
    const t = document.querySelector('.intent-textarea') as HTMLTextAreaElement
    if (t) t.focus()
  })
}

const showTemplates = ref(false)
const templateIntentType = ref<string | null>(null)
const applyTemplate = (templateData: any) => {
  if (typeof templateData === 'string') {
    intentInput.value = templateData
    templateIntentType.value = null
  } else {
    // Replace placeholders with parameter values or keep as hints
    let content = templateData.content || ''
    const schema = templateData.parameters_schema || []
    schema.forEach((param: any) => {
      if (param.default_value !== undefined) {
        content = content.replace(`{${param.name}}`, String(param.default_value))
      }
    })
    intentInput.value = content
    // Store intent type from template for submission
    if (templateData.intent_type) {
      templateIntentType.value = templateData.intent_type
    }
  }
  showTemplates.value = false
  nextTick(() => { const t = document.querySelector('.intent-textarea') as HTMLTextAreaElement; if (t) t.focus() })
}

const PINYIN_MAP: Record<string, string> = {
  'dk': '带宽', 'kf': '开放', 'gz': '故障', 'll': '链路', 'jk': '监控',
  'bz': '保障', 'xz': '限制', 'pg': '配置', 'zd': '诊断', 'qh': '切换',
  'fs': '访问', 'kz': '控制', 'cl': '策略', 'yx': '优先', 'llzx': '负载均衡',
  'acl': 'ACL', 'qos': 'QoS',
}

const updateAutocomplete = () => {
  const input = intentInput.value.toLowerCase().trim()
  if (!input || input.length < 1) { autocompleteSuggestions.value = []; showAutocomplete.value = false; return }
  const matches: string[] = []
  for (const [keyword, suggestions] of Object.entries(INTENT_SUGGESTIONS)) {
    if (input.includes(keyword) || keyword.includes(input)) { matches.push(...suggestions); continue }
    const pinyinMatch = Object.entries(PINYIN_MAP).some(
      ([py, cn]) => (input.includes(py) || py.includes(input)) && (keyword.includes(cn) || cn.includes(keyword))
    )
    if (pinyinMatch) matches.push(...suggestions)
  }
  autocompleteSuggestions.value = [...new Set(matches)].slice(0, 5)
  showAutocomplete.value = autocompleteSuggestions.value.length > 0
}

const selectAutocomplete = (suggestion: string) => { intentInput.value = suggestion; showAutocomplete.value = false }

const deepseekAvailable = ref(false)
const deepseekModel = ref('')
const zhipuAvailable = ref(false)
const zhipuModel = ref('')

interface SecurityThreat { input?: string; command?: string; pattern?: string; keyword?: string; level: string; description: string; type: string }
interface SecurityScanResult { is_safe: boolean; threat_level: string; threats: SecurityThreat[]; sanitized_commands: string[]; scan_time: string }
const securityScanResult = ref<SecurityScanResult | null>(null)
const showSecurityAlert = ref(false)
const securityScanLoading = ref(false)

const scanIntentSecurity = async (input: string): Promise<SecurityScanResult | null> => {
  try {
    const response = await authFetch(api.security.scan, { method: 'POST', body: JSON.stringify({ content: input, scan_type: 'natural_language' }) })
    if (!response.ok) { debug('安全扫描API不可用', { status: response.status }); return null }
    return await response.json()
  } catch (err: unknown) { if (err instanceof Error) debug('安全扫描请求失败', { error: err.message }); return null }
}
const activeProvider = ref('')
const copilotStreaming = ref(false)

const checkDeepSeekStatus = async () => {
  try {
    const response = await authFetch(api.deepseek.status)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    if (data.deepseek) { deepseekAvailable.value = data.deepseek.available; deepseekModel.value = data.deepseek.model || '' }
    if (data.zhipu) { zhipuAvailable.value = data.zhipu.available; zhipuModel.value = data.zhipu.model || '' }
    if (data.gateway) activeProvider.value = data.gateway.provider_priority?.[0] || ''
  } catch (err: unknown) {
    if (err instanceof Error) warn('检查DeepSeek状态失败', { error: err.message })
    deepseekAvailable.value = false; zhipuAvailable.value = false
  }
}

let copilotAbortController: AbortController | null = null

const handleCopilotSubmit = async () => {
  if (!copilotInput.value.trim() || copilotStreaming.value) return
  copilotMessages.value.push({ id: genCopilotId(), role: 'user', content: copilotInput.value, timestamp: new Date() })
  const input = copilotInput.value; copilotInput.value = ''
  if (zhipuAvailable.value || deepseekAvailable.value) { await streamDeepSeekResponse(input) }
  else { copilotMessages.value.push(generateLocalResponse(input)) }
}

const retryLastMessage = async () => {
  if (copilotStreaming.value) return
  const lastAssistantMsg = [...copilotMessages.value].reverse().find(m => m.role === 'assistant')
  if (!lastAssistantMsg || (!lastAssistantMsg.content.includes('⚠️') && !lastAssistantMsg.content.includes('失败'))) return
  const lastUserMsg = [...copilotMessages.value].reverse().find(m => m.role === 'user')
  if (!lastUserMsg) return
  copilotMessages.value = copilotMessages.value.filter(m => m !== lastAssistantMsg)
  if (zhipuAvailable.value || deepseekAvailable.value) await streamDeepSeekResponse(lastUserMsg.content)
  else copilotMessages.value.push(generateLocalResponse(lastUserMsg.content))
}

const copyMessage = async (content: string) => {
  try { await navigator.clipboard.writeText(content); showToast('消息已复制到剪贴板', 'success') }
  catch (err: unknown) { if (err instanceof Error) warn('复制消息失败', { error: err.message }); showToast('复制失败', 'error') }
}

const getConversationSummary = (): string => copilotMessages.value.filter(m => m.role === 'user').slice(-3).map(m => m.content).join(' | ')

let streamingFlushTimer: number | null = null

const streamDeepSeekResponse = async (userInput: string) => {
  if (copilotStreaming.value) return
  copilotStreaming.value = true
  if (copilotAbortController) { copilotAbortController.abort(); await new Promise(r => setTimeout(r, 0)) }
  copilotAbortController = new AbortController()
  const controller = copilotAbortController
  const assistantMsg: CopilotMessage = { id: genCopilotId(), role: 'assistant', content: '', timestamp: new Date() }
  copilotMessages.value.push(assistantMsg)
  const msgId = assistantMsg.id
  const findMsgIdx = () => copilotMessages.value.findIndex(m => m.id === msgId)
  try {
    const conversationHistory = copilotMessages.value.slice(0, -1).map(m => ({ role: m.role, content: m.content }))
    const response = await authFetch(api.copilot.chatStream, {
      method: 'POST',
      body: JSON.stringify({ message: userInput, conversation_history: conversationHistory, context: { summary: getConversationSummary(), route: '/intent' }, session_id: 'copilot_session' }),
      signal: controller.signal
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const reader = response.body?.getReader()
    if (!reader) throw new Error('No reader')
    const decoder = new TextDecoder(); let buffer = ''; let pendingContent = ''
    const flushContent = () => { if (pendingContent) { const idx = findMsgIdx(); if (idx !== -1) { copilotMessages.value[idx] = { ...copilotMessages.value[idx], content: copilotMessages.value[idx].content + pendingContent } }; pendingContent = '' }; streamingFlushTimer = null }
    while (true) {
      const { done, value } = await reader.read()
      if (done) { flushContent(); break }
      buffer += decoder.decode(value, { stream: true }); const lines = buffer.split('\n'); buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const dataStr = line.slice(6)
          if (dataStr.trim() === '[DONE]') { flushContent(); break }
          try {
            const data = JSON.parse(dataStr)
            if (data.content) { pendingContent += data.content; if (!streamingFlushTimer) streamingFlushTimer = requestAnimationFrame(flushContent) }
            if (data.error) { flushContent(); const idx = findMsgIdx(); if (idx !== -1) { copilotMessages.value[idx] = { ...copilotMessages.value[idx], content: `⚠️ AI服务调用失败: ${data.error}\n\n已切换到本地模式，请重试。` } } }
          } catch { /* skip */ }
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && (err.name === 'AbortError' || err.message.includes('aborted'))) return
    if (err instanceof Error && err.name === 'AbortError') return
    const message = err instanceof Error ? err.message : String(err)
    if (message.includes('ERR_ABORTED') || message.includes('aborted') || message.includes('AbortError')) return
    warn('副驾流式响应失败', { error: message })
    const idx = findMsgIdx()
    if (idx !== -1) {
      copilotMessages.value[idx] = { ...copilotMessages.value[idx], content: copilotMessages.value[idx].content || '⚠️ 无法连接AI服务，已切换到本地模式。' }
      if (!copilotMessages.value[idx].content) { copilotMessages.value[idx] = generateLocalResponse(userInput) }
    }
  } finally { copilotStreaming.value = false; copilotAbortController = null }
}

const generateLocalResponse = (input: string): CopilotMessage => {
  const hasSubnet = /子网|网段|网络/.test(input); const hasBandwidth = /带宽|流量|\d+\s*[MmGg]/.test(input)
  const hasDevice = /设备|交换机|路由器|防火墙/.test(input); const hasAction = /保障|限制|开放|关闭|切换|诊断|监控/.test(input)
  if (!hasSubnet && !hasDevice && !hasBandwidth && !hasAction) return { id: genCopilotId(), role: 'assistant', content: '您的描述比较模糊，我需要更多信息来帮您处理。请问：\n1. 这涉及哪个子网或设备？\n2. 您希望执行什么操作（如带宽保障、访问控制等）？', timestamp: new Date(), suggestions: ['研发子网', '生产子网', '办公子网', '核心交换机'] }
  if (!hasSubnet && !hasDevice) return { id: genCopilotId(), role: 'assistant', content: '请确认目标范围：您要操作的是哪个子网或设备？', timestamp: new Date(), suggestions: ['研发子网', '生产子网', '核心交换机01', '汇聚交换机01'] }
  if (!hasAction) return { id: genCopilotId(), role: 'assistant', content: '请明确您要执行的操作类型：是保障带宽、开放访问、还是故障诊断？', timestamp: new Date(), suggestions: ['保障带宽', '开放访问', '故障诊断', '链路切换'] }
  return { id: genCopilotId(), role: 'assistant', content: `好的，我已理解您的意图："${input}"。正在为您生成配置方案，请稍候...`, timestamp: new Date() }
}

interface SubmissionFailureInfo {
  userInput: string
  errorType: 'validation' | 'http_error' | 'semantic_inconsistency' | 'security_blocked' | 'network_error' | 'unknown'
  statusCode?: number
  errorDetail?: string
  structuredParams?: Record<string, unknown>
}

const explainSubmissionFailure = async (failure: SubmissionFailureInfo) => {
  showCopilotChat.value = true
  copilotMessages.value.push({ id: genCopilotId(), role: 'user', content: failure.userInput, timestamp: new Date() })

  if (zhipuAvailable.value || deepseekAvailable.value) {
    const prompt = `用户的网络运维意图提交失败，请分析失败原因并给出建议。

用户输入：${failure.userInput}
失败类型：${failure.errorType}
${failure.statusCode ? `HTTP状态码：${failure.statusCode}` : ''}
${failure.errorDetail ? `错误详情：${failure.errorDetail}` : ''}
${failure.structuredParams ? `解析结果：${JSON.stringify(failure.structuredParams, null, 2)}` : ''}

请用中文回答，包含以下内容：
1. 失败原因分析（简明扼要）
2. 具体修改建议（给出修改后的意图描述示例）
3. 支持的意图类型提示（带宽保障、访问控制、流量整形、QoS策略、链路管理、故障诊断、性能监控、设备配置）`

    await streamDeepSeekResponse(prompt)
  } else {
    const localExplanation = generateFailureExplanation(failure)
    copilotMessages.value.push({ id: genCopilotId(), role: 'assistant', content: localExplanation, timestamp: new Date(), suggestions: generateFailureSuggestions(failure) })
  }
  saveCopilotMessages()
}

const generateFailureExplanation = (failure: SubmissionFailureInfo): string => {
  const input = failure.userInput
  switch (failure.errorType) {
    case 'validation': {
      const detail = failure.errorDetail || '意图识别失败'
      return `❌ 意图提交失败\n\n📋 失败原因：${detail}\n\n💡 建议：\n- 确保描述中包含明确的操作关键词（如"保障带宽"、"开放访问"、"禁止流量"等）\n- 指定目标子网或设备（如"研发子网"、"核心交换机"）\n- 包含具体参数（如带宽值"500M"、端口号"3306"）\n\n支持的意图类型：带宽保障、访问控制、流量整形、QoS策略、链路管理、故障诊断、性能监控、设备配置`
    }
    case 'semantic_inconsistency': {
      const detail = failure.errorDetail || '语义不一致'
      return `❌ 意图提交失败\n\n📋 失败原因：${detail}\n\n💡 建议：\n- 您的描述与系统识别的意图类型不匹配\n- 请确保描述中的关键词与您期望的操作一致\n- 例如：要保障带宽，请同时包含"带宽"和"保障"或"最小"关键词`
    }
    case 'http_error': {
      if (failure.statusCode === 422) {
        return `❌ 意图提交失败（验证错误 422）\n\n📋 失败原因：${failure.errorDetail || '服务端验证未通过'}\n\n💡 建议：\n- 系统无法将您的描述匹配到支持的意图类型\n- 请尝试使用更标准的描述方式\n- 参考：带宽保障需包含"带宽+保障/最小"，访问控制需包含"访问/开放/禁止+端口"`
      }
      if (failure.statusCode === 403) {
        return `❌ 意图提交失败（安全拦截 403）\n\n📋 失败原因：安全扫描检测到潜在风险内容\n\n💡 建议：\n- 请检查描述中是否包含可能被安全策略拦截的内容\n- 避免使用可能被误判的敏感词汇`
      }
      return `❌ 意图提交失败（HTTP ${failure.statusCode}）\n\n📋 失败原因：${failure.errorDetail || '服务器处理异常'}\n\n💡 建议：请稍后重试，或调整描述后重新提交`
    }
    case 'security_blocked':
      return `❌ 意图提交失败（安全拦截）\n\n📋 失败原因：安全扫描检测到潜在风险\n\n💡 建议：\n- 请检查描述中是否包含可疑内容\n- 确保意图描述仅包含正常的网络运维操作`
    case 'network_error':
      return `❌ 意图提交失败（网络错误）\n\n📋 失败原因：无法连接到服务器\n\n💡 建议：\n- 检查网络连接是否正常\n- 稍后重试提交`
    default:
      return `❌ 意图提交失败\n\n📋 失败原因：未知错误\n\n💡 建议：请尝试重新描述您的意图，或使用更明确的表述`
  }
}

const generateFailureSuggestions = (failure: SubmissionFailureInfo): string[] => {
  const input = failure.userInput
  const hasBandwidth = /带宽|流量|\d+\s*[MmGg]/.test(input)
  const hasAccess = /访问|开放|禁止|允许|阻断|限制/.test(input)
  const hasLink = /链路|切换|备用|专线/.test(input)
  const hasQoS = /QoS|优先级|队列/.test(input)
  const suggestions: string[] = []
  if (hasBandwidth) suggestions.push('保障XX子网最小500M带宽')
  if (hasAccess) suggestions.push('开放XX子网到YY的3306端口访问')
  if (hasLink) suggestions.push('将主链路流量切换至备用链路')
  if (hasQoS) suggestions.push('为XX子网配置最高QoS优先级')
  if (suggestions.length === 0) suggestions.push('保障研发子网最小200M带宽', '开放办公子网到生产子网的访问', '限制访客子网上行带宽最大20M')
  return suggestions
}

const applyCopilotToInput = () => { const lastUserMsg = [...copilotMessages.value].reverse().find(msg => msg.role === 'user'); if (lastUserMsg) intentInput.value = lastUserMsg.content; showCopilotChat.value = false }
const handlePrefillIntent = (event: CustomEvent) => { const text = event.detail?.text; if (text) { intentInput.value = text; nextTick(() => { const t = document.querySelector('.intent-textarea') as HTMLTextAreaElement; if (t) t.focus() }) } }

const smartSuggestions = ref<SmartSuggestion[]>([])
const copilotMessagesRef = ref<HTMLElement | null>(null)

const loadSmartSuggestions = async () => {
  try {
    const response = await authFetch(api.copilot.suggestions)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const resp = await response.json()
    smartSuggestions.value = resp.data?.suggestions || resp.suggestions || []
  } catch (err: unknown) {
    if (err instanceof Error) warn('加载智能建议失败', { error: err.message })
    smartSuggestions.value = [{ type: 'tip', icon: '💡', title: '快速开始', description: '输入您的运维需求，如"保障研发子网带宽"', action: '保障研发子网带宽至少500M' }]
    isMockData.value = true
  }
}

const applySuggestion = (suggestion: SmartSuggestion) => { if (suggestion.action) copilotInput.value = suggestion.action; smartSuggestions.value = [] }

const sanitizeHtml = (html: string): string => {
  const div = document.createElement('div')
  div.textContent = html
  return div.innerHTML
}

const renderMarkdown = (text: string): string => {
  if (!text) return ''
  let html = sanitizeHtml(text)
  html = html.replace(/```([\s\S]*?)```/g, (_, code) => `<pre class="code-block"><code>${code}</code></pre>`)
  html = html.replace(/`(.*?)`/g, '<code>$1</code>')
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/^### (.*$)/gm, '<h4 class="md-h4">$1</h4>')
  html = html.replace(/^## (.*$)/gm, '<h3 class="md-h3">$1</h3>')
  html = html.replace(/^# (.*$)/gm, '<h2 class="md-h2">$1</h2>')
  html = html.replace(/^- (.*$)/gm, '<li class="md-li">$1</li>')
  html = html.replace(/^(\d+)\. (.*$)/gm, '<li class="md-li">$2</li>')
  html = html.replace(/\n/g, '<br>')
  html = html.replace(/📋 \*\*分析\*\*/g, '<span class="emoji-label">📋</span> <strong>分析</strong>')
  html = html.replace(/🎯 \*\*方案\*\*/g, '<span class="emoji-label">🎯</span> <strong>方案</strong>')
  html = html.replace(/💻 \*\*命令\*\*/g, '<span class="emoji-label">💻</span> <strong>命令</strong>')
  html = html.replace(/⚠️ \*\*风险\*\*/g, '<span class="emoji-label warn">⚠️</span> <strong>风险</strong>')
  html = html.replace(/✅ \*\*验证\*\*/g, '<span class="emoji-label success">✅</span> <strong>验证</strong>')
  return DOMPurify.sanitize(html)
}

const formatTime = (date: Date): string => {
  const d = date instanceof Date ? date : new Date(date); const now = new Date()
  const diffMs = now.getTime() - d.getTime(); const diffDays = Math.floor(diffMs / (24 * 60 * 60 * 1000))
  const hours = d.getHours().toString().padStart(2, '0'); const minutes = d.getMinutes().toString().padStart(2, '0')
  const timeStr = `${hours}:${minutes}`
  if (diffDays === 0) return timeStr; else if (diffDays === 1) return `昨天 ${timeStr}`
  else if (diffDays < 7) return `${diffDays}天前 ${timeStr}`
  else return `${d.getMonth() + 1}/${d.getDate()} ${timeStr}`
}

let saveDebounceTimer: number | null = null
const debouncedSaveCopilot = () => { if (saveDebounceTimer) clearTimeout(saveDebounceTimer); saveDebounceTimer = window.setTimeout(() => { saveCopilotMessages(); saveDebounceTimer = null }, 500) }

const scrollToBottom = () => { nextTick(() => { if (copilotMessagesRef.value) copilotMessagesRef.value.scrollTop = copilotMessagesRef.value.scrollHeight }) }
watch(() => copilotMessages.value.length, () => { scrollToBottom(); debouncedSaveCopilot() })
watch(() => copilotMessages.value[copilotMessages.value.length - 1]?.content, () => { scrollToBottom(); debouncedSaveCopilot() })

const thinkingSteps = ref<ThinkingStep[]>([])
const thinkingIndex = ref(-1)
const displayedTexts = ref<string[]>([])
const reasoningFailed = ref(false)
const reasoningFailMessage = ref('')
let reasoningFailTimer: number | null = null
const showConfigDiff = ref(false)
const selectedIntentForDiff = ref<IntentHistoryItem | null>(null)
const runningConfig = computed(() => {
  if (!selectedIntentForDiff.value) return ''
  const result = selectedIntentForDiff.value.execution_result
  if (result) {
    try {
      const parsed = typeof result === 'string' ? JSON.parse(result) : result
      return parsed?.running_config || '! No running config available'
    } catch {
      return '! Unable to parse config'
    }
  }
  return '! No config data - execute intent first'
})
const candidateConfig = computed(() => {
  if (!selectedIntentForDiff.value) return ''
  const commands = generateCommandsFromIntent(selectedIntentForDiff.value)
  return commands.length > 0
    ? `! Candidate Configuration\n! Generated from intent: ${selectedIntentForDiff.value.intent_name}\n!\n${commands.join('\n')}`
    : '! No candidate config generated'
})
const diffLines = ref<DiffLine[]>([]); const selectedLines = ref<Set<number>>(new Set())
const leftLineNumbersRef = ref<HTMLElement | null>(null); const leftCodeBodyRef = ref<HTMLElement | null>(null)
const rightLineNumbersRef = ref<HTMLElement | null>(null); const rightCodeBodyRef = ref<HTMLElement | null>(null)

const clearCopilotChat = () => { copilotMessages.value = [{ id: genCopilotId(), role: 'assistant', content: '对话已清空。请描述您的运维需求，我会为您提供帮助。', timestamp: new Date(), suggestions: ['保障带宽', '开放访问', '故障诊断', '链路切换'] }]; smartSuggestions.value = []; saveCopilotMessages() }
const syncScroll = (source: HTMLElement | null, targets: HTMLElement[]) => { if (!source) return; targets.forEach(t => { if (t && t !== source) { t.scrollTop = source.scrollTop; t.scrollLeft = source.scrollLeft } }) }
const onLeftScroll = () => syncScroll(leftCodeBodyRef.value, [leftLineNumbersRef.value!, rightCodeBodyRef.value!, rightLineNumbersRef.value!])
const onRightScroll = () => syncScroll(rightCodeBodyRef.value, [rightLineNumbersRef.value!, leftCodeBodyRef.value!, leftLineNumbersRef.value!])

const showVerificationView = ref(false)
const showForceConfirm = ref(false)
const selectedIntentForVerify = ref<IntentHistoryItem | null>(null)
const verificationChartRef = ref<HTMLElement | null>(null)
let verificationChart: echarts.ECharts | null = null
const verificationData = computed(() => {
  if (!selectedIntentForDiff.value?.execution_result) {
    return null
  }
  try {
    const result = typeof selectedIntentForDiff.value.execution_result === 'string'
      ? JSON.parse(selectedIntentForDiff.value.execution_result)
      : selectedIntentForDiff.value.execution_result
    return result?.verification || null
  } catch {
    return null
  }
})

const metrics = ref<MetricCard[]>([
  { label: '意图总数', value: 0, displayValue: 0, unit: '个', icon: '🎯', color: 'var(--color-primary)', filterKey: 'all', animFrameId: null },
  { label: '待审批', value: 0, displayValue: 0, unit: '项', icon: '📋', color: '#FF7D00', filterKey: 'pending', animFrameId: null },
  { label: '已批准', value: 0, displayValue: 0, unit: '项', icon: '✅', color: 'var(--color-success)', filterKey: 'approved', animFrameId: null },
  { label: '已完成', value: 0, displayValue: 0, unit: '个', icon: '🏆', color: '#00B42A', filterKey: 'completed', animFrameId: null }
])

const animateValue = (metric: MetricCard, from: number, to: number, duration: number = 600) => {
  if (metric.animFrameId) cancelAnimationFrame(metric.animFrameId)
  const startTime = performance.now()
  const animate = (currentTime: number) => {
    const elapsed = currentTime - startTime; const progress = Math.min(elapsed / duration, 1)
    const eased = 1 - Math.pow(1 - progress, 3); metric.displayValue = Math.round(from + (to - from) * eased)
    if (progress < 1) metric.animFrameId = requestAnimationFrame(animate); else metric.animFrameId = null
  }
  metric.animFrameId = requestAnimationFrame(animate)
}


const updateMetrics = () => {
  const newValues = [
    intentHistory.value.length,
    intentHistory.value.filter(i => i.status === 'pending').length,
    intentHistory.value.filter(i => i.status === 'approved').length,
    intentHistory.value.filter(i => i.status === 'completed').length
  ]
  metrics.value.forEach((m, i) => {
    const oldVal = m.value
    const newVal = newValues[i]
    if (oldVal !== newVal) {
      m.value = newVal
      animateValue(m, oldVal, newVal)
    }
  })
}

const onMetricClick = (metric: MetricCard) => {
  if (!metric.filterKey) return
  filterStatus.value = filterStatus.value === metric.filterKey ? 'all' : metric.filterKey
}

const getMetricPercent = (metric: MetricCard) => {
  const total = intentHistory.value.length || 1
  if (metric.filterKey === 'all') return 100
  return total > 0 ? (metric.value / total) * 100 : 0
}

const searchQuery = ref(''); const filterStatus = ref<string>('all')
const statusOptions = [
  { value: 'all', label: '全部状态' }, { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已批准' }, { value: 'completed', label: '已完成' },
  { value: 'rejected', label: '已拒绝' }, { value: 'running', label: '运行中' }
]

const filteredHistory = computed(() => {
  let items = intentHistory.value
  if (searchQuery.value) { const q = searchQuery.value.toLowerCase(); items = items.filter(i => (i.userInput || '').toLowerCase().includes(q) || String(i.id).toLowerCase().includes(q) || (i.device || '').toLowerCase().includes(q)) }
  if (filterStatus.value !== 'all') items = items.filter(i => i.status === filterStatus.value)
  return items
})
const totalPages = computed(() => Math.ceil(filteredHistory.value.length / pageSize))
const paginatedHistory = computed(() => filteredHistory.value.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize))
const hasNextPage = computed(() => currentPage.value < totalPages.value)
const hasPrevPage = computed(() => currentPage.value > 1)
const isSubmitDisabled = computed(() => !intentInput.value.trim() || isProcessing.value)

const dataFreshness = ref('实时'); const lastRefreshTime = ref(''); const showExportMenu = ref(false)
let fetchAbortController: AbortController | null = null; let isFetching = false; let visibilityDebounceTimer: number | null = null
let handleDataUpdate: (() => void) | null = null; let approveAbortController: AbortController | null = null
let rejectAbortController: AbortController | null = null; let deepseekParseAbortController: AbortController | null = null
let thinkingTypeIntervalId: number | null = null; let thinkingStepTimeoutId: number | null = null

const fetchIntentHistory = async (showLoading = false) => {
  if (isFetching) return; isFetching = true
  if (fetchAbortController) fetchAbortController.abort()
  fetchAbortController = new AbortController(); const signal = fetchAbortController.signal
  lastRefreshTime.value = new Date().toLocaleTimeString(); if (showLoading) isRefreshing.value = true
  try {
    const response = await authFetch(api.intents, { signal })
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    const data = await response.json()
    if (data.status === 'success' && data.data) {
      const rawIntents = Array.isArray(data.data) ? data.data : []
      const newData: IntentHistoryItem[] = rawIntents.map((item: Record<string, unknown>) => {
        const approvalStatus = item.approval_status as string
        const executionStatus = item.execution_status as string
        let status: IntentHistoryItem['status']
        if (executionStatus === 'executed') status = 'completed'
        else if (executionStatus === 'approved_pending_execution') status = 'approved'
        else if (executionStatus === 'execution_failed' || executionStatus === 'conflict_blocked') status = 'rejected'
        else if (approvalStatus === 'pending') status = 'pending'
        else if (approvalStatus === 'rejected') status = 'rejected'
        else status = 'pending'
        return {
          id: item.id as string | number, userInput: item.user_input as string,
          structuredOutput: item.structured_params as Record<string, unknown>,
          status,
          timestamp: new Date(item.created_at as string).toLocaleString('zh-CN'),
          createdAt: item.created_at as string, updatedAt: item.updated_at as string | undefined,
          approvalStatus, executionStatus,
          processingLogs: (item.processing_logs || []) as ProcessingLog[],
          device: (item.device || '系统') as string,
          execution_result: (item.execution_result || null) as string | Record<string, unknown> | null,
          intent_name: ((item.structured_params as Record<string, unknown>)?.intent_name || item.intent_name || '') as string
        }
      })
      if (JSON.stringify(newData) !== JSON.stringify(intentHistory.value)) { intentHistory.value = newData; lastUpdateTime.value = new Date() }
      updateMetrics(); dataFreshness.value = '实时'; isMockData.value = false; intentCenterError.value = null
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    warn('获取意图历史失败', { error: err instanceof Error ? err.message : String(err) }); dataFreshness.value = '降级'; isMockData.value = true
    intentCenterError.value = err instanceof Error ? err.message : '获取意图记录失败'
    if (showLoading) showToast('获取意图记录失败，请重试', 'error')
  } finally { isRefreshing.value = false; isLoading.value = false; isFetching = false; if (fetchAbortController?.signal === signal) fetchAbortController = null }
}

const startPolling = () => { if (pollInterval.value) clearInterval(pollInterval.value); pollInterval.value = window.setInterval(() => { if (isPolling.value && !document.hidden) fetchIntentHistory(false) }, POLLING_INTERVAL.INTENT_HISTORY) }
const stopPolling = () => { if (pollInterval.value) { clearInterval(pollInterval.value); pollInterval.value = null } }

const handleVisibilityChange = () => {
  if (!document.hidden) {
    startPolling()
    if (visibilityDebounceTimer) clearTimeout(visibilityDebounceTimer)
    visibilityDebounceTimer = window.setTimeout(() => { if (!isFetching) fetchIntentHistory(false); visibilityDebounceTimer = null }, 300)
  } else { stopPolling(); if (visibilityDebounceTimer) { clearTimeout(visibilityDebounceTimer); visibilityDebounceTimer = null } }
}

const manualRefresh = async () => { isRefreshing.value = true; try { await fetchIntentHistory(true); showToast('意图记录已更新', 'success') } catch (err: unknown) { if (err instanceof Error) warn('手动刷新失败', { error: err.message }); showToast('刷新失败', 'error') } }
const openIntentDetail = (intent: IntentHistoryItem) => { selectedIntent.value = intent; showIntentDetail.value = true }
const closeIntentDetail = () => { showIntentDetail.value = false; selectedIntent.value = null }

const approveIntent = async (intent: IntentHistoryItem) => {
  if (approveAbortController) approveAbortController.abort(); approveAbortController = new AbortController()
  try {
    const response = await authFetch(api.intentUpdate(String(intent.id)), { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approval_status: 'approved' }), signal: approveAbortController.signal })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    if (data.status === 'success') { showToast('意图已批准', 'success'); await fetchIntentHistory(false); if (selectedIntent.value?.id === intent.id) { selectedIntent.value.status = 'approved'; selectedIntent.value.approvalStatus = 'approved'; selectedIntent.value.executionStatus = 'approved_pending_execution' }; window.dispatchEvent(new CustomEvent('dashboardDataUpdated')) }
  } catch (err: unknown) { if (err instanceof DOMException && err.name === 'AbortError') return; logError('批准意图失败', { error: err instanceof Error ? err.message : String(err) }); showToast('操作失败，请重试', 'error') }
  finally { approveAbortController = null }
}

const rejectIntent = async (intent: IntentHistoryItem) => {
  if (rejectAbortController) rejectAbortController.abort(); rejectAbortController = new AbortController()
  try {
    const response = await authFetch(api.intentUpdate(String(intent.id)), { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approval_status: 'rejected' }), signal: rejectAbortController.signal })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    if (data.status === 'success') { showToast('意图已拒绝', 'success'); await fetchIntentHistory(false); if (selectedIntent.value?.id === intent.id) { selectedIntent.value.status = 'rejected'; selectedIntent.value.approvalStatus = 'rejected' }; window.dispatchEvent(new CustomEvent('dashboardDataUpdated')) }
  } catch (err: unknown) { if (err instanceof DOMException && err.name === 'AbortError') return; logError('拒绝意图失败', { error: err instanceof Error ? err.message : String(err) }); showToast('操作失败，请重试', 'error') }
  finally { rejectAbortController = null }
}

const startThinkingAnimation = () => {
  thinkingSteps.value = [
    { icon: '🔍', title: '识别实体', desc: '正在分析用户输入，识别网络设备、带宽需求、目标子网等关键实体...' },
    { icon: '🎯', title: '提取参数', desc: '从自然语言中提取结构化参数：带宽值、协议类型、目标设备、优先级...' },
    { icon: '📄', title: '匹配模板', desc: '根据参数匹配最优策略模板，生成配置方案框架...' },
    { icon: '🔧', title: '生成命令', desc: '生成符合设备语法的配置命令集，确保语法正确...' },
    { icon: '🛡️', title: '安全校验', desc: '进行安全策略检查、冲突检测、权限验证...' },
    { icon: '✅', title: '完成解析', desc: '意图解析完成，生成待审批配置...' }
  ]
  thinkingIndex.value = 0; displayedTexts.value = ['']
  const typeNextStep = () => {
    if (thinkingIndex.value >= thinkingSteps.value.length) return
    const fullText = thinkingSteps.value[thinkingIndex.value].desc; let charIndex = 0
    if (displayedTexts.value.length <= thinkingIndex.value) displayedTexts.value.push('')
    thinkingTypeIntervalId = window.setInterval(() => {
      if (charIndex < fullText.length) { displayedTexts.value[thinkingIndex.value] = fullText.substring(0, charIndex + 1); charIndex++ }
      else { if (thinkingTypeIntervalId !== null) { clearInterval(thinkingTypeIntervalId); thinkingTypeIntervalId = null }; thinkingIndex.value++; if (thinkingIndex.value < thinkingSteps.value.length) thinkingStepTimeoutId = window.setTimeout(typeNextStep, 300) }
    }, 20)
  }
  typeNextStep()
}

const stopThinkingAnimation = () => {
  if (thinkingTypeIntervalId !== null) { clearInterval(thinkingTypeIntervalId); thinkingTypeIntervalId = null }
  if (thinkingStepTimeoutId !== null) { clearTimeout(thinkingStepTimeoutId); thinkingStepTimeoutId = null }
  thinkingIndex.value = -1
}

const triggerReasoningFailure = (message: string, errorType: ValidationError['type'], errorMsg: string, confidence?: number) => {
  if (thinkingTypeIntervalId !== null) { clearInterval(thinkingTypeIntervalId); thinkingTypeIntervalId = null }
  if (thinkingStepTimeoutId !== null) { clearTimeout(thinkingStepTimeoutId); thinkingStepTimeoutId = null }
  reasoningFailed.value = true
  reasoningFailMessage.value = message
  if (reasoningFailTimer) clearTimeout(reasoningFailTimer)
  reasoningFailTimer = window.setTimeout(() => {
    reasoningFailed.value = false
    thinkingSteps.value = []
    thinkingIndex.value = -1
    isProcessing.value = false
    validationError.value = buildValidationError(errorType, errorMsg, confidence)
    reasoningFailTimer = null
  }, 1500)
}

const generateConfigs = (intent: IntentHistoryItem) => {
  selectedIntentForDiff.value = intent
  calculateDiff()
}

const calculateDiff = () => {
  const oldLines = runningConfig.value.split('\n'); const newLines = candidateConfig.value.split('\n')
  const result: DiffLine[] = []; const maxLen = Math.max(oldLines.length, newLines.length)
  for (let i = 0; i < maxLen; i++) {
    const oldLine = oldLines[i] || ''; const newLine = newLines[i] || ''
    let type: DiffLine['type'] = 'same'
    if (oldLine && !newLine) type = 'removed'; else if (!oldLine && newLine) type = 'added'; else if (oldLine !== newLine) type = 'changed'
    result.push({ lineNumber: i + 1, oldLine, newLine, type, selected: false })
  }
  diffLines.value = result; selectedLines.value = new Set()
}

const toggleLineSelection = (index: number) => { if (selectedLines.value.has(index)) selectedLines.value.delete(index); else selectedLines.value.add(index); selectedLines.value = new Set(selectedLines.value) }

const generateCommandsFromIntent = (intent: IntentHistoryItem): string[] => {
  const so = intent.structuredOutput as Record<string, unknown>
  if (so?.intent_name === 'git_clone_bandwidth_guarantee') {
    const actions = (so.actions || []) as Array<{ params: Record<string, string> }>; const targets = (so.targets || []) as string[]
    if (actions && actions.length > 0) {
      const params = actions[0].params; const bw = parseInt(params.min_bw) || 500; const subnet = targets?.[0] || '研发子网'
      return [`! Git 克隆流量带宽保障配置`, `! 目标子网: ${subnet}`, `! 保障带宽: ${bw}M`, ``, `class-map match-any GIT-CLONE-TRAFFIC`, ` match protocol git`, ` match destination-port 22`, ` match protocol http`, ` match protocol https`, ``, `policy-map QOS_GIT_${subnet}`, ` class GIT-CLONE-TRAFFIC`, `  priority`, `  police cir ${params.cir} bc ${Math.floor(Number(params.cir) * 0.01)} be ${Math.floor(Number(params.cir) * 0.005)}`, `    conform-action transmit`, `    exceed-action drop`, `    violate-action drop`, ` class class-default`, `  bandwidth percent 30`, `  fair-queue`, ``, `interface GigabitEthernet0/1`, ` description ${subnet} Uplink`, ` service-policy output QOS_GIT_${subnet}`, ` load-interval 30`]
    }
  }
  return ['class-map match-any VIDEO-CONF', ' match protocol video', 'policy-map QOS_VIDEO_CONF', ' class VIDEO-CONF', '  priority percent 30', '  police cir 200000000 conform-action transmit exceed-action drop', ' class class-default', '  bandwidth percent 70']
}

const forceSubmitIntent = async () => {
  showForceConfirm.value = true
}

const doForceSubmit = async () => {
  showForceConfirm.value = false

  if (!intentInput.value.trim()) return

  const inputValidation = validateIntentInput(intentInput.value)
  if (!inputValidation.valid) {
    validationError.value = buildValidationError('meaningless', inputValidation.error || '意图输入无效')
    isProcessing.value = false
    return
  }

  isProcessing.value = true; startThinkingAnimation()
  try {
    const structuredParams = (zhipuAvailable.value || deepseekAvailable.value) ? await parseIntentWithDeepSeek(intentInput.value) : parseIntentWithLLM(intentInput.value)

    if (structuredParams.is_valid === false || structuredParams.validation_error) {
      const errorMsg = (structuredParams.validation_error as string) || '意图识别失败，请提供更明确的描述'
      const confidence = Number(structuredParams.confidence || 0)
      const errType = (confidence > 0 && confidence < MIN_DISPLAY_CONFIDENCE) ? 'low_confidence' : 'unrecognized'
      triggerReasoningFailure('推理结论无效，意图无法识别', errType, errorMsg, confidence)
      return
    }

    structuredParams.requires_approval = true
    structuredParams.security_override = true
    const response = await authFetch(api.intents, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_input: intentInput.value, structured_params: structuredParams as unknown as Record<string, unknown> }) })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    if (data.status === 'success') {
      stopThinkingAnimation(); await fetchIntentHistory(); currentPage.value = 1
      showToast('意图已提交（安全审批中）', 'warning')
      intentInput.value = ''; validationError.value = null; window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
    }
  } catch (err: unknown) { stopThinkingAnimation(); logError('强制提交意图失败', { error: err instanceof Error ? err.message : String(err) }); showToast('提交失败，请重试', 'error') }
  finally { isProcessing.value = false }
}

const submitIntent = async () => {
  if (!intentInput.value.trim() || isProcessing.value) return

  const inputValidation = validateIntentInput(intentInput.value)
  if (!inputValidation.valid) {
    validationError.value = buildValidationError('meaningless', inputValidation.error || '意图输入无效')
    return
  }

  isProcessing.value = true; startThinkingAnimation()
  try {
    securityScanLoading.value = true
    const scanResult = await scanIntentSecurity(intentInput.value)
    securityScanLoading.value = false
    securityScanResult.value = scanResult
    if (scanResult && !scanResult.is_safe) {
      showSecurityAlert.value = true
      stopThinkingAnimation(); isProcessing.value = false
      logError('安全扫描拦截', { threat_level: scanResult.threat_level, threats: scanResult.threats.map(t => t.description) })
      auditLogService.recordSecurityAlert('admin', intentInput.value, scanResult.threat_level, scanResult.threats.map(t => t.description).join('; '))
      explainSubmissionFailure({ userInput: intentInput.value, errorType: 'security_blocked', errorDetail: `威胁等级: ${scanResult.threat_level}，威胁: ${scanResult.threats.map(t => t.description).join('; ')}` })
      return
    }
    const structuredParams = (zhipuAvailable.value || deepseekAvailable.value) ? await parseIntentWithDeepSeek(intentInput.value) : parseIntentWithLLM(intentInput.value)

    // If template provided intent_type, override the parsed one
    if (templateIntentType.value) {
      structuredParams.intent_name = templateIntentType.value
      structuredParams.is_valid = true
      templateIntentType.value = null // Reset after use
    }

    if (structuredParams.is_valid === false || structuredParams.validation_error) {
      const errorMsg = (structuredParams.validation_error as string) || '意图识别失败，请提供更明确的描述'
      const confidence = Number(structuredParams.confidence || 0)
      const errType = (confidence > 0 && confidence < MIN_DISPLAY_CONFIDENCE) ? 'low_confidence' : 'unrecognized'
      stopThinkingAnimation(); isProcessing.value = false
      explainSubmissionFailure({ userInput: intentInput.value, errorType: 'validation', errorDetail: errorMsg, structuredParams: structuredParams as Record<string, unknown> })
      triggerReasoningFailure('推理结论无效，意图无法识别', errType, errorMsg, confidence)
      return
    }

    if (structuredParams.clarification_needed && structuredParams.clarification_question) {
      stopThinkingAnimation(); isProcessing.value = false; showCopilotChat.value = true
      copilotMessages.value.push({ id: genCopilotId(), role: 'assistant', content: `🤔 您的意图描述需要进一步澄清：\n\n${structuredParams.clarification_question}\n\n（置信度: ${Math.round(Number(structuredParams.confidence || 0) * 100)}%）`, timestamp: new Date(), suggestions: ['重新描述', '查看示例'] }); return
    }
    const response = await authFetch(api.intents, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_input: intentInput.value, structured_params: structuredParams as unknown as Record<string, unknown> }) })
    if (!response.ok) {
      let errorDetail = ''
      try { const errBody = await response.json(); errorDetail = errBody.detail?.[0]?.msg || errBody.detail?.message || JSON.stringify(errBody.detail || errBody) } catch { errorDetail = `HTTP ${response.status}` }
      stopThinkingAnimation(); isProcessing.value = false
      const errorType = response.status === 422 ? 'semantic_inconsistency' : response.status === 403 ? 'security_blocked' : 'http_error'
      explainSubmissionFailure({ userInput: intentInput.value, errorType, statusCode: response.status, errorDetail, structuredParams: structuredParams as Record<string, unknown> })
      showToast('意图提交失败，智能副驾正在分析原因...', 'error')
      return
    }
    const data = await response.json()
    if (data.status === 'success') {
      stopThinkingAnimation(); await fetchIntentHistory(); currentPage.value = 1
      const createdIntent = intentHistory.value.find(intent => intent.id === data.data?.id)
      if (createdIntent) {
        selectedIntentForDiff.value = createdIntent; generateConfigs(createdIntent); showConfigDiff.value = true
        const intentId = String(createdIntent.id)
        auditLogService.recordIntentSubmission('admin', createdIntent.userInput, (createdIntent as Record<string, unknown>).device as string || '未知设备', generateCommandsFromIntent(createdIntent), 'pending', `APR-${Date.now().toString(36).slice(0, 6)}`, { intentId, prompt: `用户意图：${createdIntent.userInput}\n请解析并生成配置...`, modelResponse: JSON.stringify(createdIntent.structuredOutput, null, 2), tokens: { prompt: -1, completion: -1, total: -1 }, latency_ms: -1, model: (structuredParams as Record<string, unknown>)._deepseek_model as string || 'local-parser' })
        try {
          const conflictResult = await authFetch(api.intentConflictCheck(intentId), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
          })
          const conflictData = await conflictResult.json()
          if (conflictData.has_conflict) {
            showToast('检测到冲突，请查看冲突详情', 'warning')
          }
        } catch {
          // Conflict check failed, continue anyway
        }
      }
      intentInput.value = ''; validationError.value = null; window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
    } else {
      stopThinkingAnimation(); isProcessing.value = false
      explainSubmissionFailure({ userInput: intentInput.value, errorType: 'unknown', errorDetail: data.message || '提交返回非成功状态', structuredParams: structuredParams as Record<string, unknown> })
      intentInput.value = ''
    }
  } catch (err: unknown) {
    logError('提交意图失败', { error: err instanceof Error ? err.message : String(err) })
    stopThinkingAnimation(); isProcessing.value = false
    const isNetworkError = err instanceof TypeError && err.message.includes('fetch')
    explainSubmissionFailure({ userInput: intentInput.value, errorType: isNetworkError ? 'network_error' : 'unknown', errorDetail: err instanceof Error ? err.message : String(err) })
    showToast('意图提交失败，智能副驾正在分析原因...', 'error')
    intentInput.value = ''
  } finally { isProcessing.value = false; stopThinkingAnimation() }
}

const approveConfig = async () => {
  if (!selectedIntentForDiff.value) return
  try {
    const intentId = selectedIntentForDiff.value.id
    const response = await authFetch(api.intentApprove(intentId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved: true })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    selectedIntentForDiff.value.status = 'approved'
    selectedIntentForDiff.value.approvalStatus = 'approved'
    selectedIntentForDiff.value.executionStatus = 'approved_pending_execution'
    showConfigDiff.value = false; showVerificationView.value = true; selectedIntentForVerify.value = selectedIntentForDiff.value
    auditLogService.recordConfigDeployment('admin', selectedIntentForDiff.value.userInput, selectedIntentForDiff.value.device, generateCommandsFromIntent(selectedIntentForDiff.value), 'success', `APR-${Date.now().toString(36).slice(0, 6)}`, { intentId: String(selectedIntentForDiff.value.id), prompt: `审批通过，准备下发配置：${selectedIntentForDiff.value.userInput}`, modelResponse: '配置已成功下发', tokens: { prompt: -1, completion: -1, total: -1 }, latency_ms: -1, model: zhipuAvailable.value ? 'GLM-4' : deepseekAvailable.value ? 'DeepSeek' : 'local' })
    nextTick(() => initVerificationChart()); window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
    fetchIntentHistory()
  } catch (e: unknown) {
    showToast('审批操作失败', 'error')
  }
}

const rejectConfig = async () => {
  if (!selectedIntentForDiff.value) return
  try {
    const intentId = selectedIntentForDiff.value.id
    const response = await authFetch(api.intentReject(intentId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'Rejected by user' })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    selectedIntentForDiff.value.status = 'rejected'
    selectedIntentForDiff.value.approvalStatus = 'rejected'
    showConfigDiff.value = false
    auditLogService.recordIntentSubmission('admin', selectedIntentForDiff.value.userInput, selectedIntentForDiff.value.device, [], 'failed', undefined, { intentId: String(selectedIntentForDiff.value.id), prompt: `配置审批被拒绝：${selectedIntentForDiff.value.userInput}`, modelResponse: '配置不符合要求，已拒绝', tokens: { prompt: -1, completion: -1, total: -1 }, latency_ms: -1, model: 'GPT-4o' })
    window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
    fetchIntentHistory()
  } catch (e: unknown) {
    showToast('拒绝操作失败', 'error')
  }
}

const initVerificationChart = () => {
  if (!verificationChartRef.value) return
  if (!verificationData.value) return
  if (verificationChart) { verificationChart.dispose(); verificationChart = null }
  verificationChart = echarts.init(verificationChartRef.value)
  verificationChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(15, 23, 42, 0.9)', borderColor: 'rgba(255, 255, 255, 0.1)', textStyle: { color: '#fff' } },
    legend: { data: ['配置前', '配置后'], textStyle: { color: 'var(--color-text-tertiary)' }, top: 10 },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '60px', containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10'], axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.1)' } }, axisLabel: { color: 'var(--color-text-tertiary)' } },
    yAxis: { type: 'value', name: '带宽(M)', axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.1)' } }, axisLabel: { color: 'var(--color-text-tertiary)' }, splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.05)' } } },
    series: [
      { name: '配置前', type: 'line', data: verificationData.value.before, lineStyle: { color: 'var(--color-error)', width: 2 }, itemStyle: { color: 'var(--color-error)' }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(239, 68, 68, 0.3)' }, { offset: 1, color: 'rgba(239, 68, 68, 0.05)' }]) } },
      { name: '配置后', type: 'line', data: verificationData.value.after, lineStyle: { color: 'var(--color-success)', width: 2 }, itemStyle: { color: 'var(--color-success)' }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(82, 196, 26, 0.3)' }, { offset: 1, color: 'rgba(82, 196, 26, 0.05)' }]) } },
      { name: '阈值', type: 'line', data: Array(10).fill(verificationData.value.threshold), lineStyle: { color: '#FF7D00', width: 2, type: 'dashed' }, itemStyle: { color: '#FF7D00' }, symbol: 'none' }
    ]
  })
  window.removeEventListener('resize', handleChartResize)
  window.addEventListener('resize', handleChartResize)
}

const handleChartResize = () => { verificationChart?.resize() }

const openVerification = (intent: IntentHistoryItem) => { selectedIntentForVerify.value = intent; showVerificationView.value = true; nextTick(() => initVerificationChart()) }
const openConfigDiff = (intent: IntentHistoryItem) => { selectedIntentForDiff.value = intent; generateConfigs(intent); showConfigDiff.value = true }
const prevPage = () => { if (hasPrevPage.value) currentPage.value-- }
const nextPage = () => { if (hasNextPage.value) currentPage.value++ }
const parseIntentWithLLM = (input: string): Record<string, unknown> => parseIntent(input) as unknown as Record<string, unknown>

const parseIntentWithDeepSeek = async (input: string): Promise<Record<string, unknown>> => {
  if (deepseekParseAbortController) deepseekParseAbortController.abort(); deepseekParseAbortController = new AbortController()
  try {
    const response = await authFetch(api.deepseek.parse, { method: 'POST', body: JSON.stringify({ user_input: input }), signal: deepseekParseAbortController.signal })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    if (data.status === 'success' && data.parsed) {
      const p = data.parsed
      const validIntentNames = ['git_clone_bandwidth_guarantee', 'bandwidth_guarantee', 'fault_diagnosis', 'performance_monitoring', 'qos_policy', 'traffic_shaping', 'access_control', 'link_management', 'device_config']
      const rawIntentName = (p.intent_type as string) || ''
      const intent_name = validIntentNames.includes(rawIntentName) ? rawIntentName : 'bandwidth_guarantee'
      return { intent_name, targets: [p.target_subnet || '未知子网'].filter(Boolean), actions: (p.actions || []).map((a: Record<string, unknown>) => ({ type: a.type, params: a.params || {} })), confidence: p.confidence || 0.5, clarification_needed: p.clarification_needed || false, clarification_question: p.clarification_question || null, entities: p.entities || {}, bandwidth: p.bandwidth, duration: p.duration, priority: p.priority || 'medium', _deepseek_model: data.model, is_valid: validIntentNames.includes(rawIntentName) && (p.confidence || 0.5) >= 0.35 }
    }
  } catch (err: unknown) { if (err instanceof DOMException && err.name === 'AbortError') return parseIntent(input) as unknown as Record<string, unknown>; warn('DeepSeek解析失败，降级到本地解析', { error: err instanceof Error ? err.message : String(err) }) }
  finally { deepseekParseAbortController = null }
  return parseIntent(input) as unknown as Record<string, unknown>
}

const clearFilters = () => { searchQuery.value = ''; filterStatus.value = 'all'; currentPage.value = 1 }

const exportData = (format: 'json' | 'csv') => {
  const payload = { exportTime: new Date().toISOString(), totalIntents: intentHistory.value.length, intents: intentHistory.value.map(i => ({ id: i.id, userInput: i.userInput, status: i.status, approvalStatus: i.approvalStatus, device: i.device, timestamp: i.timestamp, createdAt: i.createdAt })), metrics: metrics.value.map(m => ({ label: m.label, value: m.value, unit: m.unit })) }
  if (format === 'json') { const b = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }); const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = `intents_${new Date().toISOString().slice(0, 10)}.json`; a.click(); URL.revokeObjectURL(u) }
  else { const escCsv = (v: string) => `"${String(v).replace(/"/g, '""').replace(/[\r\n]+/g, ' ')}"`; const h = '意图ID,用户输入,状态,审批状态,设备,时间\n'; const r = intentHistory.value.map(i => `${i.id},${escCsv(i.userInput)},${i.status},${escCsv(i.approvalStatus)},${escCsv(i.device)},${escCsv(i.timestamp)}`).join('\n'); const b = new Blob(['\uFEFF' + h + r], { type: 'text/csv;charset=utf-8' }); const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = `intents_${new Date().toISOString().slice(0, 10)}.csv`; a.click(); URL.revokeObjectURL(u) }
  showExportMenu.value = false; showToast(`数据已导出为 ${format.toUpperCase()} 格式`, 'success')
}

const handleClickOutside = (e: MouseEvent) => { if (showExportMenu.value) { const t = e.target as HTMLElement; if (!t.closest('.export-wrapper')) showExportMenu.value = false } }
const handleKeydown = (e: KeyboardEvent) => {
  if ((e.altKey) && e.key === 'r') { e.preventDefault(); manualRefresh() }
  if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); submitIntent() }
  else if (e.key === 'Escape') { if (showConfigDiff.value) showConfigDiff.value = false; else if (showVerificationView.value) showVerificationView.value = false; else if (showIntentDetail.value) closeIntentDetail(); else if (showTemplates.value) showTemplates.value = false; else if (showCopilotChat.value) showCopilotChat.value = false }
  else if (e.ctrlKey && e.key === '/') { e.preventDefault(); showCopilotChat.value = !showCopilotChat.value }
}

watch([filterStatus], () => { currentPage.value = 1 }); watch(searchQuery, () => { currentPage.value = 1 })

function handleAssistantFillForm(e: Event) {
  const detail = (e as CustomEvent).detail
  if (detail?.field === 'inputText' && detail.value) {
    intentInput.value = detail.value
    nextTick(() => {
      const t = document.querySelector('.intent-textarea') as HTMLTextAreaElement
      if (t) t.focus()
    })
  }
}

onMounted(async () => {
  info('IntentCenter mounted, initializing...'); fetchIntentHistory(true); startPolling(); await checkDeepSeekStatus()
  window.addEventListener('prefill-intent', handlePrefillIntent as EventListener)
  window.addEventListener('assistant:fill_form', handleAssistantFillForm)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('click', handleClickOutside)
  handleDataUpdate = () => fetchIntentHistory(false); window.addEventListener('dashboardDataUpdated', handleDataUpdate)
  if (zhipuAvailable.value || deepseekAvailable.value) copilotMessages.value[0] = { id: genCopilotId(), role: 'assistant', content: '您好！我是智能运维副驾，由多模型协同驱动（智谱GLM + DeepSeek）。请描述您的网络运维需求，我会为您提供专业的分析和建议。', timestamp: new Date(), suggestions: ['保障带宽', '开放访问', '故障诊断', '链路切换'] }
  info('IntentCenter 初始化完成')
})

interface FailedIntentStats {
  total_failures: number
  today_failures: number
  unresolved_cases: number
  resolution_rate: number
}

interface FailedIntent {
  id: number | string
  user_input: string
  parse_method: string
  failure_reason: string
  intent_type_attempted: string
  resolved: boolean
  created_at: string
  clarification?: string
  resolution_notes?: string
}

const activeTab = ref('intent')
const fiStats = ref<FailedIntentStats>({
  total_failures: 0,
  today_failures: 0,
  unresolved_cases: 0,
  resolution_rate: 0
})
const fiCases = ref<FailedIntent[]>([])
const fiIsLoading = ref(true)
const fiIsRefreshing = ref(false)
const fiCurrentPage = ref(1)
const fiTotalCases = ref(0)
const fiFilterResolved = ref<'all' | 'unresolved' | 'resolved'>('all')
const fiFilterParseMethod = ref<string>('all')
const fiShowDetailDialog = ref(false)
const fiShowResolveDialog = ref(false)
const fiSelectedCase = ref<FailedIntent | null>(null)
const fiResolveClarification = ref('')
const fiResolveNotes = ref('')
const fiIsResolving = ref(false)
const fiIsDeleting = ref(false)
const fiParseMethods = ['DeepSeek', 'LangChain', 'Regex', 'Unknown']

const fiTruncatedInput = (input: string, maxLen: number = 40) => {
  if (!input) return '--'
  return input.length > maxLen ? input.slice(0, maxLen) + '...' : input
}

const fiParseMethodText = (method: string) => {
  switch (method) {
    case 'deepseek': return 'DeepSeek'
    case 'langchain': return 'LangChain'
    case 'regex': return 'Regex'
    case 'unknown': return 'Unknown'
    default: return method
  }
}

const fiFormatTime = (dateStr: string): string => {
  if (!dateStr) return '--'
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const fiTotalPages = computed(() => Math.max(1, Math.ceil(fiTotalCases.value / pageSize)))

const fetchFiStats = async () => {
  try {
    const res = await apiClient.get(api.failedIntents.stats)
    if (res.data) {
      const d = res.data
      fiStats.value = {
        total_failures: d.total_failures ?? 0,
        today_failures: d.today_failures ?? 0,
        unresolved_cases: d.unresolved_cases ?? 0,
        resolution_rate: d.resolution_rate ?? 0
      }
    }
  } catch (err: any) {
    warn('获取失败案例统计失败', { error: err.message })
  }
}

const fetchFiCases = async () => {
  fiIsLoading.value = true
  try {
    const params = new URLSearchParams()
    params.set('limit', String(pageSize))
    params.set('offset', String((fiCurrentPage.value - 1) * pageSize))
    if (fiFilterResolved.value === 'unresolved') params.set('resolved', 'false')
    else if (fiFilterResolved.value === 'resolved') params.set('resolved', 'true')
    if (fiFilterParseMethod.value !== 'all') params.set('parse_method', fiFilterParseMethod.value)
    const url = `${api.failedIntents.list}?${params.toString()}`
    const res = await apiClient.get(url)
    if (res.data) {
      const d = res.data
      const items = Array.isArray(d) ? d : d.items ?? []
      fiCases.value = items.map((item: any) => ({
        id: item.id,
        user_input: item.user_input ?? '',
        parse_method: item.parse_method ?? 'unknown',
        failure_reason: item.failure_reason ?? '',
        intent_type_attempted: item.intent_type_attempted ?? '',
        resolved: item.resolved ?? false,
        created_at: item.created_at ?? '',
        clarification: item.clarification ?? '',
        resolution_notes: item.resolution_notes ?? ''
      }))
      fiTotalCases.value = d.total ?? items.length
    }
  } catch (err: any) {
    warn('获取失败案例列表失败', { error: err.message })
  } finally {
    fiIsLoading.value = false
  }
}

const fetchFiData = async (showLoading = false) => {
  if (showLoading) fiIsRefreshing.value = true
  try {
    await Promise.all([fetchFiStats(), fetchFiCases()])
  } finally {
    fiIsRefreshing.value = false
  }
}

const fiViewDetail = async (item: FailedIntent) => {
  try {
    const res = await apiClient.get(api.failedIntents.byId(String(item.id)))
    if (res.data) {
      fiSelectedCase.value = {
        id: res.data.id ?? item.id,
        user_input: res.data.user_input ?? item.user_input,
        parse_method: res.data.parse_method ?? item.parse_method,
        failure_reason: res.data.failure_reason ?? item.failure_reason,
        intent_type_attempted: res.data.intent_type_attempted ?? item.intent_type_attempted,
        resolved: res.data.resolved ?? item.resolved,
        created_at: res.data.created_at ?? item.created_at,
        clarification: res.data.clarification ?? '',
        resolution_notes: res.data.resolution_notes ?? ''
      }
    } else {
      fiSelectedCase.value = { ...item }
    }
    fiShowDetailDialog.value = true
  } catch (err: any) {
    warn('获取案例详情失败', { error: err.message })
    fiSelectedCase.value = { ...item }
    fiShowDetailDialog.value = true
  }
}

const fiOpenResolveDialog = (item: FailedIntent) => {
  fiSelectedCase.value = { ...item }
  fiResolveClarification.value = ''
  fiResolveNotes.value = ''
  fiShowResolveDialog.value = true
}

const fiSubmitResolve = async () => {
  if (!fiSelectedCase.value) return
  fiIsResolving.value = true
  try {
    await apiClient.post(api.failedIntents.resolve(String(fiSelectedCase.value.id)), {
      clarification: fiResolveClarification.value,
      resolution_notes: fiResolveNotes.value
    })
    showToast('案例已标记为已解决', 'success')
    fiShowResolveDialog.value = false
    await fetchFiData(true)
  } catch (err: any) {
    warn('解决案例失败', { error: err.message })
    showToast('解决案例失败', 'error')
  } finally {
    fiIsResolving.value = false
  }
}

const fiDeleteCase = async (item: FailedIntent) => {
  fiIsDeleting.value = true
  try {
    await apiClient.delete(api.failedIntents.byId(String(item.id)))
    showToast('案例已删除', 'success')
    await fetchFiData(true)
  } catch (err: any) {
    warn('删除案例失败', { error: err.message })
    showToast('删除案例失败', 'error')
  } finally {
    fiIsDeleting.value = false
  }
}

const fiExportFinetuningData = async () => {
  try {
    const res = await apiClient.get(api.failedIntents.finetuningData)
    const data = res.data ?? res
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `finetuning_data_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    showToast('微调数据已导出', 'success')
  } catch (err: any) {
    warn('导出微调数据失败', { error: err.message })
    showToast('导出微调数据失败', 'error')
  }
}

const fiHandlePageChange = (page: number) => {
  fiCurrentPage.value = page
  fetchFiCases()
}

const fiHandleFilterChange = () => {
  fiCurrentPage.value = 1
  fetchFiCases()
}

const onTabChange = (tab: string | number) => {
  if (tab === 'failed' && fiCases.value.length === 0) {
    fetchFiData(true)
  }
}

onUnmounted(() => {
  if (pollInterval.value !== null) clearInterval(pollInterval.value)
  if (visibilityDebounceTimer !== null) clearTimeout(visibilityDebounceTimer)
  if (thinkingTypeIntervalId !== null) clearInterval(thinkingTypeIntervalId)
  if (thinkingStepTimeoutId !== null) clearTimeout(thinkingStepTimeoutId)
  if (reasoningFailTimer !== null) clearTimeout(reasoningFailTimer)
  if (streamingFlushTimer !== null) { cancelAnimationFrame(streamingFlushTimer); streamingFlushTimer = null }
  if (saveDebounceTimer !== null) { clearTimeout(saveDebounceTimer); saveDebounceTimer = null }
  if (fetchAbortController) fetchAbortController.abort()
  if (copilotAbortController) copilotAbortController.abort()
  if (approveAbortController) approveAbortController.abort()
  if (rejectAbortController) rejectAbortController.abort()
  if (deepseekParseAbortController) deepseekParseAbortController.abort()
  metrics.value.forEach(m => { if (m.animFrameId) cancelAnimationFrame(m.animFrameId) })
  if (verificationChart) { verificationChart.dispose(); verificationChart = null }
  window.removeEventListener('resize', handleChartResize)
  if (handleDataUpdate) window.removeEventListener('dashboardDataUpdated', handleDataUpdate)
  window.removeEventListener('prefill-intent', handlePrefillIntent as EventListener)
  window.removeEventListener('assistant:fill_form', handleAssistantFillForm)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <div class="intent-center" :class="{ loading: isLoading }">
    <div class="ic-bg"><div class="bg-grid"></div><div class="bg-glow glow-1"></div><div class="bg-glow glow-2"></div></div>
    <div class="ic-header">
      <div class="header-left"><h1 class="page-title">智能副驾工作台</h1><p class="page-subtitle">自然语言意图解析、配置生成与闭环验证</p></div>
      <div class="header-actions">
        <span class="data-freshness" :class="{ degraded: dataFreshness === '降级' }"><span class="freshness-dot"></span>{{ dataFreshness }}</span>
        <span class="last-refresh" v-if="lastRefreshTime">{{ lastRefreshTime }}</span>
        <div class="export-wrapper">
          <button type="button" class="action-btn" @click.stop="showExportMenu = !showExportMenu" title="导出数据" aria-label="导出数据">📥 导出</button>
          <div v-if="showExportMenu" class="export-dropdown"><button type="button" aria-label="导出JSON" @click="exportData('json')">导出 JSON</button><button type="button" aria-label="导出CSV" @click="exportData('csv')">导出 CSV</button></div>
        </div>
        <button type="button" class="action-btn refresh-btn" :class="{ refreshing: isRefreshing }" @click="manualRefresh" :disabled="isRefreshing" title="刷新数据 (Alt+R)" aria-label="刷新数据">
          <span class="refresh-icon" :class="{ spinning: isRefreshing }">🔄</span>{{ isRefreshing ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="ic-tabs" @tab-change="onTabChange">
      <el-tab-pane label="意图管理" name="intent">
    <div v-if="isLoading" class="metrics-grid"><div v-for="i in 4" :key="i" class="metric-card skeleton"><div class="skeleton-line wide"></div><div class="skeleton-line narrow"></div></div></div>
    <div v-else class="metrics-grid">
      <div v-for="(metric, idx) in metrics" :key="metric.label" class="metric-card" :class="{ active: metric.filterKey && filterStatus === metric.filterKey, clickable: !!metric.filterKey }" :style="{ '--accent': metric.color, '--delay': `${idx * 0.08}s` }" @click="onMetricClick(metric)">
        <div class="metric-icon" :style="{ background: `${metric.color}18`, color: metric.color, boxShadow: `0 0 20px ${metric.color}15` }">{{ metric.icon }}</div>
        <div class="metric-content">
          <div class="metric-value" :style="{ textShadow: `0 0 24px ${metric.color}40` }">{{ metric.displayValue }}<span class="metric-unit">{{ metric.unit }}</span></div>
          <div class="metric-label">{{ metric.label }}</div>
        </div>
        <div class="metric-bottom-bar"><div class="metric-bottom-fill" :style="{ background: `linear-gradient(90deg, ${metric.color}, ${metric.color}66)`, width: `${getMetricPercent(metric)}%` }"></div></div>
      </div>
    </div>

    <div class="workspace-layout">
      <div class="intent-input-panel">
        <div class="input-header">
          <h2 class="panel-title">意图输入</h2>
          <div class="input-header-actions">
            <button type="button" class="copilot-toggle-btn" @click="showTemplates = !showTemplates" title="快速模板" :aria-expanded="showTemplates" aria-controls="templates-panel" aria-label="快速模板">📋 模板</button>
            <button type="button" class="copilot-toggle-btn" @click="showCopilotChat = !showCopilotChat" :aria-expanded="showCopilotChat" aria-controls="copilot-panel" :aria-label="showCopilotChat ? '关闭智能副驾' : '打开智能副驾'">🤖 {{ showCopilotChat ? '关闭副驾' : '智能副驾' }}<span v-if="zhipuAvailable || deepseekAvailable" class="deepseek-badge" :title="zhipuAvailable ? '智谱 ' + zhipuModel : 'DeepSeek ' + deepseekModel">🧠</span></button>
          </div>
        </div>
        <TemplateMarketPanel v-if="showTemplates" @apply="applyTemplate" @close="showTemplates = false" />
        <div class="input-container">
          <textarea v-model="intentInput" class="intent-textarea" placeholder="请输入您的网络运维意图，例如：&#10;保证研发子网视频会议流量最小200M带宽&#10;开放研发网到生产网数据库的访问" :disabled="isProcessing" aria-label="意图输入框" @input="updateAutocomplete"></textarea>
          <div v-if="showAutocomplete" class="autocomplete-dropdown" role="listbox" aria-label="自动补全建议"><div v-for="suggestion in autocompleteSuggestions" :key="suggestion" class="autocomplete-item" role="option" @click="selectAutocomplete(suggestion)">{{ suggestion }}</div></div>
          <button type="button" v-if="canWrite" class="submit-btn" :disabled="isSubmitDisabled" @click="submitIntent" :aria-busy="isProcessing" aria-label="提交意图">{{ isProcessing ? '处理中...' : '提交意图' }}</button>
        </div>

        <Transition name="validation-slide">
          <div v-if="validationError" :class="['validation-error-panel', validationError.severity]" role="alert" aria-live="assertive">
            <div class="validation-error-header">
              <div class="validation-error-title-group">
                <span class="validation-error-icon">{{ validationError.icon }}</span>
                <span class="validation-error-title">{{ validationError.title }}</span>
                <span :class="['validation-severity-badge', validationError.severity]">{{ validationError.severity === 'error' ? '错误' : '警告' }}</span>
              </div>
              <button type="button" class="validation-dismiss-btn" @click="dismissValidationError" title="关闭" aria-label="关闭验证提示">✕</button>
            </div>
            <div class="validation-error-body">
              <p class="validation-error-desc">{{ validationError.description }}</p>
              <div v-if="validationError.suggestions.length > 0" class="validation-suggestions">
                <div class="validation-suggestions-label">💡 建议修正：</div>
                <div class="validation-suggestion-chips">
                  <button
                    type="button"
                    v-for="(suggestion, idx) in validationError.suggestions"
                    :key="idx"
                    class="validation-suggestion-chip"
                    @click="applyValidationSuggestion(suggestion.fill)"
                    aria-label="应用建议"
                  >{{ suggestion.text }}</button>
                </div>
              </div>
            </div>
            <div class="validation-error-footer">
              <span class="validation-error-type-tag">{{ validationError.type.replace('_', ' ') }}</span>
              <button type="button" class="validation-retry-btn" @click="dismissValidationError(); focusIntentInput()" aria-label="重新输入">重新输入</button>
            </div>
          </div>
        </Transition>

        <div v-if="showCopilotChat" id="copilot-panel" class="copilot-chat-panel" role="region" aria-label="智能副驾对话">
          <div class="copilot-header-bar">
            <div class="copilot-status-group">
              <div class="copilot-status"><span :class="['status-dot', zhipuAvailable ? 'online' : 'offline']"></span><span class="status-text">{{ zhipuAvailable ? `智谱 ${zhipuModel}` : '智谱离线' }}</span></div>
              <div class="copilot-status"><span :class="['status-dot', deepseekAvailable ? 'online' : 'offline']"></span><span class="status-text">{{ deepseekAvailable ? 'DeepSeek' : 'DS离线' }}</span></div>
            </div>
            <div class="copilot-header-actions"><button type="button" class="copilot-suggest-btn" @click="loadSmartSuggestions" title="获取智能建议" aria-label="获取智能建议">💡 建议</button><button type="button" class="copilot-suggest-btn" @click="clearCopilotChat" title="清空对话" aria-label="清空对话">🗑️ 清空</button></div>
          </div>
          <div v-if="smartSuggestions.length > 0" class="smart-suggestions-bar">
            <div v-for="(s, idx) in smartSuggestions" :key="idx" :class="['smart-suggestion-card', s.type]" @click="applySuggestion(s)">
              <span class="sg-icon">{{ s.icon }}</span><div class="sg-info"><div class="sg-title">{{ s.title }}</div><div class="sg-desc">{{ s.description }}</div></div><span class="sg-arrow">→</span>
            </div>
          </div>
          <div class="copilot-messages" ref="copilotMessagesRef">
            <div v-for="msg in copilotMessages" :key="msg.id" :class="['copilot-msg', msg.role]">
              <div class="msg-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
              <div class="msg-content">
                <div class="msg-text" v-html="renderMarkdown(msg.content)"></div>
                <div v-if="copilotStreaming && idx === copilotMessages.length - 1 && msg.role === 'assistant'" class="streaming-cursor"><span class="cursor-blink">▊</span></div>
                <div class="msg-meta">
                  <span v-if="msg.timestamp" class="msg-timestamp">{{ formatTime(msg.timestamp) }}</span>
                  <div class="msg-actions">
                    <button type="button" v-if="msg.role === 'assistant' && (msg.content.includes('⚠️') || msg.content.includes('失败'))" class="msg-action-btn" @click="retryLastMessage()" title="重试" aria-label="重试">🔄</button>
                  </div>
                </div>
                <div v-if="msg.suggestions" class="msg-suggestions"><button type="button" v-for="s in msg.suggestions" :key="s" class="suggestion-chip" @click="copilotInput = s" aria-label="应用建议">{{ s }}</button></div>
              </div>
            </div>
            <div v-if="copilotStreaming && (!copilotMessages.length || !copilotMessages[copilotMessages.length - 1]?.content)" class="copilot-msg assistant">
              <div class="msg-avatar">🤖</div><div class="msg-content"><div class="msg-text thinking-dots"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div></div>
            </div>
          </div>
          <div class="copilot-input-row">
            <input v-model="copilotInput" class="copilot-input" :placeholder="(zhipuAvailable || deepseekAvailable) ? '描述您的运维需求...' : '输入您的回复（本地模式）...'" :disabled="copilotStreaming" aria-label="副驾输入框" @keydown.enter.prevent="handleCopilotSubmit" />
            <button type="button" class="copilot-send-btn" @click="handleCopilotSubmit" :disabled="copilotStreaming || !copilotInput.trim()" aria-label="发送">{{ copilotStreaming ? '思考中...' : '发送' }}</button>
            <button type="button" class="copilot-apply-btn" @click="applyCopilotToInput" title="应用到意图输入框" aria-label="应用到意图输入框">应用到输入</button>
          </div>
        </div>

        <div v-if="thinkingSteps.length > 0 || reasoningFailed" :class="['thinking-panel', { failed: reasoningFailed }]">
          <template v-if="reasoningFailed">
            <div class="reasoning-failure-overlay">
              <div class="failure-icon-ring">
                <span class="failure-x-mark">✕</span>
              </div>
              <h3 class="failure-title">推理失败</h3>
              <p class="failure-message">{{ reasoningFailMessage }}</p>
              <div class="failure-hint">请提供更明确的意图描述或尝试其他表达方式</div>
            </div>
          </template>
          <template v-else>
            <h3 class="thinking-title">🤖 智能推理过程</h3>
            <div class="thinking-steps">
              <div v-for="(step, index) in thinkingSteps" :key="index" :class="['thinking-step', { active: index <= thinkingIndex, current: index === thinkingIndex }]">
                <div class="step-header"><span class="step-icon">{{ step.icon }}</span><span class="step-title">{{ step.title }}</span><span v-if="index <= thinkingIndex" class="step-status">✓</span></div>
                <div class="step-desc"><span v-if="index < thinkingIndex">{{ step.desc }}</span><span v-else-if="index === thinkingIndex" class="typing-text">{{ displayedTexts[index] || '' }}</span><span v-else class="step-pending">...</span></div>
              </div>
            </div>
          </template>
        </div>
      </div>

      <div class="intent-history-panel" v-loading="isRefreshing">
        <h2 class="panel-title">意图执行历史<span class="history-limit-badge">每页 {{ pageSize }} 条</span></h2>
        <div v-if="intentCenterError && isMockData" class="error-banner">
          <span class="error-banner-icon">⚠️</span>
          <span class="error-banner-text">数据加载失败: {{ intentCenterError }}</span>
          <button type="button" class="error-banner-retry" @click="manualRefresh" aria-label="重试">🔄 重试</button>
        </div>
        <div class="filter-bar">
          <div class="filter-left">
            <div class="search-wrapper"><span class="search-icon">🔍</span><input v-model="searchQuery" type="text" class="search-input" placeholder="搜索意图内容、ID、设备..." aria-label="搜索意图历史" /><button type="button" v-if="searchQuery" class="search-clear" @click="searchQuery = ''" aria-label="清除搜索">✕</button></div>
            <select v-model="filterStatus" class="filter-select" aria-label="按状态筛选"><option v-for="opt in statusOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option></select>
            <button type="button" v-if="searchQuery || filterStatus !== 'all'" class="clear-filter-btn" @click="clearFilters" aria-label="清除筛选">清除筛选</button>
          </div>
        </div>
        <div class="history-list">
          <div v-for="intent in paginatedHistory" :key="intent.id" class="history-item" tabindex="0" role="button" :aria-label="'查看意图: ' + intent.userInput" @click="openIntentDetail(intent)" @keydown.enter="openIntentDetail(intent)">
            <div class="history-header"><span :class="['status-badge', intent.status]">{{ getStatusConfig(intent.status).label }}</span><span class="history-time">{{ intent.timestamp }}</span></div>
            <div class="history-input">{{ intent.userInput }}</div>
            <div class="history-output"><pre>{{ JSON.stringify(intent.structuredOutput, null, 2) }}</pre></div>
            <div class="history-actions">
              <button type="button" v-if="intent.status === 'pending'" class="action-btn small" @click="openConfigDiff(intent)" aria-label="查看配置">查看配置</button>
              <button type="button" v-if="intent.status === 'approved' || intent.status === 'completed'" class="action-btn small success" @click="openVerification(intent)" aria-label="查看验证">查看验证</button>
            </div>
          </div>
          <div v-if="filteredHistory.length === 0 && intentHistory.length > 0" class="empty-state"><span class="empty-icon">🔍</span><p>未找到匹配的意图记录</p><button type="button" class="clear-filter-btn" @click="clearFilters" aria-label="清除筛选">清除筛选</button></div>
          <div v-if="intentHistory.length === 0" class="empty-state"><span class="empty-icon">📝</span><p>暂无意图历史记录</p></div>
        </div>
        <div v-if="totalPages > 1" class="pagination">
          <button type="button" class="pagination-btn prev" :disabled="!hasPrevPage" @click="prevPage">← 上一页</button>
          <div class="pagination-info">第 {{ currentPage }} / {{ totalPages }} 页<span class="pagination-total">（共 {{ filteredHistory.length }} 条）</span></div>
          <button type="button" class="pagination-btn next" :disabled="!hasNextPage" @click="nextPage">下一页 →</button>
        </div>
      </div>
    </div>
      </el-tab-pane>

      <el-tab-pane label="失败案例" name="failed">
    <div class="fi-header">
      <div class="fi-header-left">
        <h2 class="fi-page-title">失败案例库</h2>
        <p class="fi-page-subtitle">意图解析失败案例管理与微调数据导出</p>
      </div>
      <div class="fi-header-actions">
        <button type="button" class="action-btn fi-export-btn" @click="fiExportFinetuningData">📤 导出微调数据</button>
        <button type="button" class="action-btn refresh-btn" :disabled="fiIsRefreshing" @click="fetchFiData(true)">
          <span class="refresh-icon" :class="{ spinning: fiIsRefreshing }">🔄</span>
          {{ fiIsRefreshing ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-card" style="--accent: var(--color-error); --delay: 0s">
        <div class="stat-top-row">
          <div class="stat-icon" style="background: rgba(255, 77, 79, 0.12); color: var(--color-error-light); box-shadow: 0 0 20px rgba(255, 77, 79, 0.08)">❌</div>
        </div>
        <div class="stat-content">
          <div class="stat-value" style="text-shadow: 0 0 24px rgba(255, 77, 79, 0.25)">{{ fiStats.total_failures }}<span class="stat-unit">条</span></div>
          <div class="stat-label">总失败数</div>
        </div>
      </div>
      <div class="stat-card" style="--accent: var(--color-warning); --delay: 0.08s">
        <div class="stat-top-row">
          <div class="stat-icon" style="background: rgba(250, 173, 20, 0.12); color: var(--color-warning-light); box-shadow: 0 0 20px rgba(250, 173, 20, 0.08)">📅</div>
        </div>
        <div class="stat-content">
          <div class="stat-value" style="text-shadow: 0 0 24px rgba(250, 173, 20, 0.25)">{{ fiStats.today_failures }}<span class="stat-unit">条</span></div>
          <div class="stat-label">今日失败</div>
        </div>
      </div>
      <div class="stat-card" style="--accent: #FF7D00; --delay: 0.16s">
        <div class="stat-top-row">
          <div class="stat-icon" style="background: rgba(255, 125, 0, 0.12); color: #FF9A3C; box-shadow: 0 0 20px rgba(255, 125, 0, 0.08)">⚠️</div>
        </div>
        <div class="stat-content">
          <div class="stat-value" style="text-shadow: 0 0 24px rgba(255, 125, 0, 0.25)">{{ fiStats.unresolved_cases }}<span class="stat-unit">条</span></div>
          <div class="stat-label">未解决案例</div>
        </div>
      </div>
      <div class="stat-card" style="--accent: var(--color-success); --delay: 0.24s">
        <div class="stat-top-row">
          <div class="stat-icon" style="background: rgba(82, 196, 26, 0.12); color: var(--color-success-light); box-shadow: 0 0 20px rgba(82, 196, 26, 0.08)">✅</div>
        </div>
        <div class="stat-content">
          <div class="stat-value" style="text-shadow: 0 0 24px rgba(82, 196, 26, 0.25)">{{ fiStats.resolution_rate }}<span class="stat-unit">%</span></div>
          <div class="stat-label">解决率</div>
        </div>
      </div>
    </div>

    <div class="fi-panel">
      <div class="fi-panel-header">
        <h2 class="fi-panel-title">案例列表</h2>
        <div class="fi-filter-group">
          <div class="fi-filter-section">
            <span class="fi-filter-label">状态:</span>
            <button
              type="button"
              v-for="f in (['all', 'unresolved', 'resolved'] as const)"
              :key="f"
              class="fi-filter-btn"
              :class="{ active: fiFilterResolved === f }"
              @click="fiFilterResolved = f; fiHandleFilterChange()"
            >
              {{ f === 'all' ? '全部' : f === 'unresolved' ? '未解决' : '已解决' }}
            </button>
          </div>
          <div class="fi-filter-section">
            <span class="fi-filter-label">解析方式:</span>
            <button
              type="button"
              v-for="m in ['all', ...fiParseMethods]"
              :key="m"
              class="fi-filter-btn"
              :class="{ active: fiFilterParseMethod === m }"
              @click="fiFilterParseMethod = m; fiHandleFilterChange()"
            >
              {{ m === 'all' ? '全部' : m }}
            </button>
          </div>
        </div>
      </div>

      <div class="fi-table-wrapper">
        <table class="fi-data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>用户输入</th>
              <th>解析方式</th>
              <th>失败原因</th>
              <th>意图类型</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in fiCases" :key="item.id">
              <td class="fi-mono">{{ item.id }}</td>
              <td :title="item.user_input">{{ fiTruncatedInput(item.user_input) }}</td>
              <td><span class="fi-method-tag">{{ fiParseMethodText(item.parse_method) }}</span></td>
              <td :title="item.failure_reason">{{ fiTruncatedInput(item.failure_reason, 30) }}</td>
              <td>{{ item.intent_type_attempted || '--' }}</td>
              <td>
                <span class="fi-status-tag" :class="item.resolved ? 'resolved' : 'unresolved'">
                  {{ item.resolved ? '已解决' : '未解决' }}
                </span>
              </td>
              <td class="fi-mono">{{ fiFormatTime(item.created_at) }}</td>
              <td>
                <div class="fi-action-cell">
                  <button type="button" class="fi-table-action-btn" @click="fiViewDetail(item)">查看</button>
                  <button v-if="!item.resolved" type="button" class="fi-table-action-btn resolve" @click="fiOpenResolveDialog(item)">解决</button>
                  <button type="button" class="fi-table-action-btn danger" @click="fiDeleteCase(item)">删除</button>
                </div>
              </td>
            </tr>
            <tr v-if="fiCases.length === 0 && !fiIsLoading">
              <td colspan="8" class="fi-empty-state">暂无失败案例数据</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="fiTotalPages > 1" class="fi-pagination">
        <button type="button" class="fi-page-btn" :disabled="fiCurrentPage <= 1" @click="fiHandlePageChange(fiCurrentPage - 1)">上一页</button>
        <span class="fi-page-info">{{ fiCurrentPage }} / {{ fiTotalPages }}</span>
        <button type="button" class="fi-page-btn" :disabled="fiCurrentPage >= fiTotalPages" @click="fiHandlePageChange(fiCurrentPage + 1)">下一页</button>
      </div>
    </div>

    <div v-if="fiShowDetailDialog" class="fi-dialog-overlay" @click.self="fiShowDetailDialog = false">
      <div class="fi-dialog">
        <div class="fi-dialog-header">
          <h3 class="fi-dialog-title">案例详情</h3>
          <button type="button" class="fi-dialog-close" @click="fiShowDetailDialog = false">✕</button>
        </div>
        <div class="fi-dialog-body" v-if="fiSelectedCase">
          <div class="fi-detail-grid">
            <div class="fi-detail-item">
              <span class="fi-detail-label">ID</span>
              <span class="fi-detail-value fi-mono">{{ fiSelectedCase.id }}</span>
            </div>
            <div class="fi-detail-item">
              <span class="fi-detail-label">状态</span>
              <span class="fi-status-tag" :class="fiSelectedCase.resolved ? 'resolved' : 'unresolved'">
                {{ fiSelectedCase.resolved ? '已解决' : '未解决' }}
              </span>
            </div>
            <div class="fi-detail-item">
              <span class="fi-detail-label">解析方式</span>
              <span class="fi-detail-value">{{ fiParseMethodText(fiSelectedCase.parse_method) }}</span>
            </div>
            <div class="fi-detail-item">
              <span class="fi-detail-label">意图类型</span>
              <span class="fi-detail-value">{{ fiSelectedCase.intent_type_attempted || '--' }}</span>
            </div>
            <div class="fi-detail-item full-width">
              <span class="fi-detail-label">用户输入</span>
              <span class="fi-detail-value">{{ fiSelectedCase.user_input || '--' }}</span>
            </div>
            <div class="fi-detail-item full-width">
              <span class="fi-detail-label">失败原因</span>
              <span class="fi-detail-value failure-reason">{{ fiSelectedCase.failure_reason || '--' }}</span>
            </div>
            <div class="fi-detail-item">
              <span class="fi-detail-label">创建时间</span>
              <span class="fi-detail-value fi-mono">{{ fiFormatTime(fiSelectedCase.created_at) }}</span>
            </div>
            <div v-if="fiSelectedCase.clarification" class="fi-detail-item full-width">
              <span class="fi-detail-label">澄清说明</span>
              <span class="fi-detail-value">{{ fiSelectedCase.clarification }}</span>
            </div>
            <div v-if="fiSelectedCase.resolution_notes" class="fi-detail-item full-width">
              <span class="fi-detail-label">解决备注</span>
              <span class="fi-detail-value">{{ fiSelectedCase.resolution_notes }}</span>
            </div>
          </div>
        </div>
        <div class="fi-dialog-footer">
          <button type="button" class="action-btn" @click="fiShowDetailDialog = false">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="fiShowResolveDialog" class="fi-dialog-overlay" @click.self="fiShowResolveDialog = false">
      <div class="fi-dialog">
        <div class="fi-dialog-header">
          <h3 class="fi-dialog-title">解决案例</h3>
          <button type="button" class="fi-dialog-close" @click="fiShowResolveDialog = false">✕</button>
        </div>
        <div class="fi-dialog-body">
          <div class="fi-form-group">
            <label class="fi-form-label">澄清说明</label>
            <textarea v-model="fiResolveClarification" class="fi-form-textarea" placeholder="请输入对用户意图的澄清说明..." rows="3"></textarea>
          </div>
          <div class="fi-form-group">
            <label class="fi-form-label">解决备注</label>
            <textarea v-model="fiResolveNotes" class="fi-form-textarea" placeholder="请输入解决方案或备注..." rows="3"></textarea>
          </div>
        </div>
        <div class="fi-dialog-footer">
          <button type="button" class="action-btn" @click="fiShowResolveDialog = false">取消</button>
          <button type="button" v-if="canWrite" class="action-btn primary" :disabled="fiIsResolving" @click="fiSubmitResolve">
            {{ fiIsResolving ? '提交中...' : '确认解决' }}
          </button>
        </div>
      </div>
    </div>
      </el-tab-pane>
    </el-tabs>

    <Teleport to="body">
      <div v-if="showSecurityAlert && securityScanResult" class="modal-overlay" @click.self="showSecurityAlert = false" role="dialog" aria-modal="true" aria-labelledby="security-alert-title">
        <div class="modal-content security-alert-modal">
          <div class="modal-header"><h3 id="security-alert-title" class="modal-title security-alert-title">🛡️ 安全告警</h3><button type="button" class="close-btn" @click="showSecurityAlert = false" aria-label="关闭">×</button></div>
          <div class="security-alert-content">
            <div :class="['threat-level-badge', securityScanResult.threat_level]">
              <span class="threat-icon">{{ securityScanResult.threat_level === 'critical' ? '🔴' : securityScanResult.threat_level === 'high' ? '🟠' : securityScanResult.threat_level === 'medium' ? '🟡' : '🟢' }}</span>
              <span>威胁等级: {{ securityScanResult.threat_level === 'critical' ? '严重' : securityScanResult.threat_level === 'high' ? '高危' : securityScanResult.threat_level === 'medium' ? '中危' : '低危' }}</span>
            </div>
            <p class="security-message">您的意图输入被安全扫描引擎拦截，检测到以下威胁：</p>
            <div class="threat-list">
              <div v-for="(threat, idx) in securityScanResult.threats" :key="idx" :class="['threat-item', threat.level.toLowerCase()]">
                <span class="threat-level-dot"></span>
                <div class="threat-info"><span class="threat-desc">{{ threat.description }}</span><span class="threat-type">类型: {{ threat.type === 'chinese_dangerous_keyword' ? '危险关键词' : threat.type === 'malicious_input' ? '恶意输入' : threat.type === 'obfuscation' ? '混淆绕过' : threat.type === 'command_chaining' ? '命令链' : threat.type }}</span></div>
                <span :class="['threat-level-tag', threat.level.toLowerCase()]">{{ threat.level }}</span>
              </div>
            </div>
            <div class="security-actions">
              <button type="button" class="security-btn cancel" @click="showSecurityAlert = false; intentInput = ''" aria-label="取消输入">取消输入</button>
              <button type="button" v-if="canWrite" class="security-btn override" @click="showSecurityAlert = false; forceSubmitIntent()" aria-label="强制提交">强制提交（需审批）</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showConfigDiff" class="modal-overlay" @click.self="showConfigDiff = false" role="dialog" aria-modal="true" aria-labelledby="diff-modal-title">
        <div class="modal-content diff-modal">
          <div class="modal-header"><h3 id="diff-modal-title" class="modal-title">🔍 配置差异比对</h3><button type="button" class="close-btn" @click="showConfigDiff = false" aria-label="关闭">×</button></div>
          <div class="diff-toolbar">
            <div class="diff-legend"><span class="legend-item added"><span class="legend-color"></span> 新增</span><span class="legend-item removed"><span class="legend-color"></span> 删除</span><span class="legend-item changed"><span class="legend-color"></span> 修改</span></div>
            <div class="diff-actions-bar"><button type="button" class="toolbar-btn" @click="selectedLines = new Set(diffLines.map((_, i) => i))" aria-label="全选">全选</button><button type="button" class="toolbar-btn" @click="selectedLines = new Set()" aria-label="清空选择">清空</button><span class="selected-count">已选 {{ selectedLines.size }} 行</span></div>
          </div>
          <div class="diff-content">
            <div class="diff-panel"><h4 class="diff-title"><span class="diff-title-icon">📄</span>Running Config</h4><div class="diff-code-panel left"><div ref="leftLineNumbersRef" class="diff-line-numbers"><div v-for="(line, index) in diffLines" :key="index" class="line-number">{{ line.lineNumber }}</div></div><div ref="leftCodeBodyRef" class="diff-code-body" @scroll="onLeftScroll"><div v-for="(line, index) in diffLines" :key="'old-' + index" :class="['diff-line', line.type, { selected: selectedLines.has(index) }]" @click="toggleLineSelection(index)"><span class="line-marker">{{ line.type === 'removed' ? '-' : ' ' }}</span><span class="line-content">{{ line.oldLine || ' ' }}</span></div></div></div></div>
            <div class="diff-divider"><span class="diff-arrow">→</span></div>
            <div class="diff-panel"><h4 class="diff-title"><span class="diff-title-icon">📋</span>Candidate Config</h4><div class="diff-code-panel right"><div ref="rightLineNumbersRef" class="diff-line-numbers"><div v-for="(line, index) in diffLines" :key="index" class="line-number">{{ line.lineNumber }}</div></div><div ref="rightCodeBodyRef" class="diff-code-body" @scroll="onRightScroll"><div v-for="(line, index) in diffLines" :key="'new-' + index" :class="['diff-line', line.type, { selected: selectedLines.has(index) }]" @click="toggleLineSelection(index)"><span class="line-marker">{{ line.type === 'added' ? '+' : line.type === 'changed' ? '~' : ' ' }}</span><span class="line-content">{{ line.newLine || ' ' }}</span></div></div></div></div>
          </div>
          <div class="diff-summary"><span class="diff-summary-icon">💡</span><span class="diff-summary-text">检测到 {{ diffLines.filter(l => l.type !== 'same').length }} 处修改</span></div>
          <div class="modal-actions diff-actions"><button type="button" v-if="canWrite" class="modal-btn cancel" @click="rejectConfig" aria-label="拒绝">拒绝</button><button type="button" v-if="canWrite" class="modal-btn confirm" @click="approveConfig" aria-label="批准执行">批准执行</button></div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showVerificationView" class="modal-overlay" @click.self="showVerificationView = false" role="dialog" aria-modal="true" aria-labelledby="verify-modal-title">
        <div class="modal-content verification-modal">
          <div class="modal-header"><h3 id="verify-modal-title" class="modal-title">📊 闭环验证仪表板</h3><button type="button" class="close-btn" @click="showVerificationView = false" aria-label="关闭">×</button></div>
          <div class="verification-content">
            <div v-if="verificationData">
            <div class="verification-info"><h4 class="verification-intent">{{ selectedIntentForVerify?.userInput }}</h4>
              <div class="verification-metrics">
                <div class="metric-card"><span class="metric-icon">📈</span><span class="metric-value">210M</span><span class="metric-label">当前带宽</span></div>
                <div class="metric-card"><span class="metric-icon">✅</span><span class="metric-value success">正常</span><span class="metric-label">验证状态</span></div>
                <div class="metric-card"><span class="metric-icon">⏱️</span><span class="metric-value">10s</span><span class="metric-label">收敛时间</span></div>
              </div>
            </div>
            <div class="verification-chart" ref="verificationChartRef"></div>
            <div class="verification-timeline"><h4 class="timeline-title">验证时间轴</h4>
              <div class="timeline-items">
                <div class="timeline-item completed"><span class="timeline-dot"></span><span class="timeline-time">[15:01:02]</span><span class="timeline-text">配置下发成功</span></div>
                <div class="timeline-item completed"><span class="timeline-dot"></span><span class="timeline-time">[15:01:05]</span><span class="timeline-text">流量检测开始</span></div>
                <div class="timeline-item completed"><span class="timeline-dot"></span><span class="timeline-time">[15:01:08]</span><span class="timeline-text">带宽提升至目标值</span></div>
                <div class="timeline-item current"><span class="timeline-dot"></span><span class="timeline-time">[15:01:12]</span><span class="timeline-text">验证完成，闭环成功</span></div>
              </div>
            </div>
            </div>
            <div v-else class="empty-state">
              <p>暂无验证数据，请先执行意图</p>
            </div>
          </div>
          <div class="modal-actions"><button type="button" class="modal-btn cancel" @click="showVerificationView = false" aria-label="关闭">关闭</button></div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showIntentDetail" class="modal-overlay" @click.self="closeIntentDetail" role="dialog" aria-modal="true" aria-labelledby="detail-modal-title">
        <div class="modal-content intent-detail-modal">
          <div class="modal-header"><h3 id="detail-modal-title" class="modal-title">📄 意图详情</h3><button type="button" class="close-btn" @click="closeIntentDetail" aria-label="关闭">×</button></div>
          <div class="intent-detail-content" v-if="selectedIntent">
            <div class="detail-section"><h4 class="detail-title">基本信息</h4>
              <div class="detail-grid">
                <div class="detail-item"><span class="detail-label">ID</span><span class="detail-value">{{ selectedIntent.id }}</span></div>
                <div class="detail-item"><span class="detail-label">状态</span><span :class="['detail-value', 'status-badge', selectedIntent.status]">{{ getStatusConfig(selectedIntent.status).label }}</span></div>
                <div class="detail-item"><span class="detail-label">设备</span><span class="detail-value">{{ selectedIntent.device || '系统' }}</span></div>
                <div class="detail-item"><span class="detail-label">创建时间</span><span class="detail-value">{{ selectedIntent.timestamp }}</span></div>
              </div>
            </div>
            <div class="detail-section"><h4 class="detail-title">意图内容</h4><div class="intent-input-display">{{ selectedIntent.userInput }}</div></div>
            <div class="detail-section"><h4 class="detail-title">结构化数据</h4><div class="structured-output-display"><pre>{{ JSON.stringify(selectedIntent.structuredOutput, null, 2) }}</pre></div></div>
            <div class="detail-section" v-if="selectedIntent.processingLogs && selectedIntent.processingLogs.length > 0"><h4 class="detail-title">处理记录</h4>
              <div class="processing-logs"><div v-for="(log, index) in selectedIntent.processingLogs" :key="index" class="log-item"><div class="log-time">{{ log.timestamp }}</div><div class="log-message">{{ log.message }}</div></div></div>
            </div>
            <div class="detail-actions" v-if="canWrite && selectedIntent.status === 'pending'"><button type="button" class="detail-btn reject" @click="rejectIntent(selectedIntent)" aria-label="拒绝意图">拒绝</button><button type="button" class="detail-btn approve" @click="approveIntent(selectedIntent)" aria-label="批准意图">批准</button></div>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showForceConfirm" class="modal-overlay" @click.self="showForceConfirm = false" role="dialog" aria-modal="true">
        <div class="confirm-modal">
          <h3 class="confirm-title">⚠️ 确认强制提交？</h3>
          <p class="confirm-desc">安全扫描已拦截此意图，强制提交可能绕过安全检查，请确保您了解潜在风险。</p>
          <div class="confirm-actions">
            <button type="button" class="confirm-btn cancel" @click="showForceConfirm = false" aria-label="取消">取消</button>
            <button type="button" v-if="canWrite" class="confirm-btn danger" @click="doForceSubmit" aria-label="确认强制提交">确认强制提交</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.intent-center { position: relative; animation: page-enter 0.5s ease-out; min-height: 100vh; padding: var(--content-padding); }
.ic-bg { position: fixed; top: 0; left: 0; right: 0; bottom: 0; pointer-events: none; z-index: 0; overflow: hidden; }
.bg-grid { position: absolute; top: 0; right: 0; bottom: 0; left: 0; background-image: linear-gradient(rgba(22, 93, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(22, 93, 255, 0.03) 1px, transparent 1px); background-size: 60px 60px; mask-image: radial-gradient(ellipse 80% 60% at 50% 30%, black 20%, transparent 70%); }
.bg-glow { position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.4; }
.glow-1 { width: 400px; height: 400px; background: rgba(22, 93, 255, 0.08); top: -100px; right: 10%; animation: glow-float 12s ease-in-out infinite; }
.glow-2 { width: 300px; height: 300px; background: rgba(114, 46, 209, 0.06); bottom: 10%; left: 5%; animation: glow-float 15s ease-in-out infinite reverse; }

.intent-center > *:not(.ic-bg) { position: relative; z-index: var(--z-content); }
:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.ic-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-lg); padding-bottom: var(--spacing-md); border-bottom: 1px solid var(--color-border-primary); }
.header-left { display: flex; flex-direction: column; gap: var(--spacing-xs); }
.page-title { font-size: var(--font-size-xl); font-weight: 700; margin: 0; background: linear-gradient(135deg, var(--color-text-secondary) 0%, var(--color-primary) 50%, var(--color-text-secondary) 100%); background-size: 200% auto; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: title-shimmer 4s ease-in-out infinite; }
.page-subtitle { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin: 0; font-weight: 400; }

.header-actions { display: flex; align-items: center; gap: 0.75rem; }
.data-freshness { font-size: var(--font-size-xs); padding: var(--spacing-xs) 10px; border-radius: var(--radius-lg); background: var(--color-success-bg); color: var(--color-success); transition: all 0.3s var(--ease-out); border: 1px solid var(--color-success-border); display: flex; align-items: center; gap: 0.375rem; }
.freshness-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; animation: freshness-pulse 2s ease-in-out infinite; }

.data-freshness.degraded { background: var(--color-warning-bg); color: var(--color-warning); border-color: var(--color-warning-border); }
.last-refresh { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.action-btn { padding: var(--button-padding-y) var(--button-padding-x); background: var(--color-primary-bg); color: var(--color-primary-light); border: 1px solid var(--color-primary-border); border-radius: var(--button-radius); cursor: pointer; font-size: var(--button-font-size); transition: var(--button-transition); display: inline-flex; align-items: center; justify-content: center; gap: var(--spacing-sm); white-space: nowrap; backdrop-filter: blur(8px); min-height: var(--button-height-md); box-shadow: 0 0 6px var(--color-primary-glow); user-select: none; -webkit-tap-highlight-color: transparent; touch-action: manipulation; line-height: var(--line-height-tight); }
.action-btn:hover:not(:disabled) { background: var(--color-primary-hover); border-color: rgba(22, 93, 255, 0.5); box-shadow: var(--shadow-glow-primary); transform: translateY(-1px); }
.action-btn:active:not(:disabled) { transform: translateY(0) scale(0.97); }
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; pointer-events: none; }
.refresh-icon { display: inline-block; transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
.refresh-btn:hover:not(:disabled) .refresh-icon { transform: rotate(360deg); }
.refresh-icon.spinning { animation: spin 1s linear infinite; }
.export-wrapper { position: relative; }
.export-dropdown { position: absolute; top: 100%; right: 0; margin-top: var(--spacing-xs); background: var(--color-bg-elevated); border: 1px solid var(--color-border-secondary); border-radius: var(--radius-md); overflow: hidden; z-index: var(--z-dropdown); min-width: 140px; backdrop-filter: blur(16px); box-shadow: var(--shadow-dropdown); animation: dropdown-enter 0.15s var(--ease-out); }
.export-dropdown button { display: block; width: 100%; padding: 10px var(--spacing-md); background: none; border: none; color: var(--color-text-secondary); font-size: var(--font-size-xs); text-align: left; cursor: pointer; transition: all 0.15s ease; }
.export-dropdown button:hover { background: var(--color-primary-bg); color: var(--color-primary-light); padding-left: 1.25rem; }
.skeleton { animation: skeleton-pulse 1.5s ease-in-out infinite; }
.skeleton-line { height: 14px; background: var(--gradient-shimmer); background-size: 200% 100%; border-radius: var(--radius-sm); margin-bottom: var(--spacing-sm); animation: skeleton-slide 1.5s ease-in-out infinite; }
.skeleton-line.wide { width: 70%; }
.skeleton-line.narrow { width: 40%; }
.metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(var(--grid-min-col), 1fr)); gap: var(--spacing-md); margin-bottom: 1.25rem; }
.metric-card { background: var(--gradient-glass); border-radius: var(--card-border-radius); padding: var(--card-padding); display: flex; align-items: center; gap: var(--spacing-md); border: var(--card-border); transition: all 0.35s var(--ease-out); position: relative; overflow: hidden; backdrop-filter: blur(12px); animation: card-enter 0.4s var(--ease-out) backwards; animation-delay: var(--delay, 0s); will-change: transform, opacity; }
.metric-card.clickable { cursor: pointer; }
.metric-card.clickable:active { transform: scale(0.97); }
.metric-card.active { border-color: var(--accent); box-shadow: var(--shadow-glow-primary); }
.metric-card.active::before { opacity: 1; }
.metric-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--accent), transparent); opacity: 0; transition: opacity 0.35s ease; }
.metric-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-card-hover), var(--shadow-glow-primary); border-color: var(--color-primary-border); }
.metric-card:hover::before { opacity: 1; }
.metric-icon { width: 2.75rem; height: 2.75rem; border-radius: var(--radius-lg); display: flex; align-items: center; justify-content: center; font-size: var(--font-size-xl); flex-shrink: 0; transition: transform 0.3s ease; }
.metric-card:hover .metric-icon { transform: scale(1.08); }
.metric-content { flex: 1; min-width: 0; }
.metric-value { font-size: var(--font-size-2xl); font-weight: 700; color: var(--color-text-primary); line-height: var(--line-height-tight); font-variant-numeric: tabular-nums; letter-spacing: -0.5px; }
.metric-unit { font-size: var(--font-size-sm); font-weight: 400; color: var(--color-text-tertiary); margin-left: 2px; letter-spacing: 0; }
.metric-label { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-top: 2px; }
.metric-bottom-bar { position: absolute; bottom: 0; left: 0; right: 0; height: 3px; background: rgba(255, 255, 255, 0.04); }
.metric-bottom-fill { height: 100%; border-radius: 0 2px 0 0; transition: width 0.6s var(--ease-out); }
.workspace-layout { display: grid; grid-template-columns: 1fr 1fr; gap: var(--panel-gap); }
.intent-input-panel, .intent-history-panel { background: var(--gradient-glass); border-radius: var(--radius-lg); padding: var(--spacing-lg); border: var(--card-border); backdrop-filter: blur(12px); }
.error-banner { display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem 1.25rem; background: var(--color-error-bg); border: 1px solid var(--color-error-border); border-radius: var(--radius-lg); margin-bottom: 1.25rem; animation: banner-enter 0.3s var(--ease-out); will-change: transform, opacity; }

.error-banner-icon { font-size: var(--font-size-lg); flex-shrink: 0; }
.error-banner-text { flex: 1; font-size: var(--font-size-sm); color: var(--color-error-light); }
.error-banner-retry { padding: var(--spacing-xs) 0.875rem; background: var(--color-error-hover); color: var(--color-error-light); border: 1px solid var(--color-error-border); border-radius: var(--radius-md); font-size: var(--font-size-xs); cursor: pointer; transition: all 0.2s var(--ease-out); white-space: nowrap; min-height: var(--button-height-sm); }
.error-banner-retry:hover { background: var(--color-error-hover); }
.input-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; }
.input-header-actions { display: flex; gap: var(--spacing-sm); align-items: center; }
.panel-title { font-size: var(--font-size-md); font-weight: var(--font-weight-semibold); color: var(--color-text-primary); margin-bottom: var(--spacing-md); padding-left: 0.625rem; border-left: 3px solid var(--color-primary); display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem; }
.history-limit-badge { font-size: var(--font-size-xs); font-weight: 500; padding: var(--spacing-xs) 10px; background: var(--gradient-primary); color: var(--color-text-primary); border-radius: var(--radius-md); white-space: nowrap; }
.filter-bar { display: flex; justify-content: space-between; align-items: center; gap: var(--spacing-md); margin-bottom: var(--spacing-md); padding: 0.75rem var(--spacing-md); background: var(--color-bg-input); border-radius: var(--radius-lg); border: 1px solid var(--color-border-primary); flex-wrap: wrap; }
.filter-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.search-wrapper { position: relative; display: flex; align-items: center; }
.search-icon { position: absolute; left: 10px; font-size: var(--font-size-base); pointer-events: none; }
.search-input { padding: var(--spacing-sm) var(--spacing-xl) var(--spacing-sm) var(--spacing-xl); background: var(--input-bg); border: 1px solid var(--input-border); border-radius: var(--input-radius); color: var(--color-text-secondary); font-size: var(--font-size-sm); width: 220px; transition: all 0.25s var(--ease-out); outline: none; }
.search-input::placeholder { color: var(--color-text-disabled); }
.search-input:focus { border-color: var(--input-border-focus); box-shadow: var(--input-shadow-focus); background: var(--color-bg-input); }
.search-clear { position: absolute; right: 8px; background: none; border: none; color: var(--color-text-tertiary); cursor: pointer; font-size: var(--font-size-xs); padding: 2px; transition: color 0.2s ease; }
.search-clear:hover { color: var(--color-text-primary); }
.filter-select { padding: var(--spacing-sm) 0.75rem; background: var(--input-bg); border: 1px solid var(--input-border); border-radius: var(--input-radius); color: var(--color-text-secondary); font-size: var(--font-size-sm); cursor: pointer; transition: all 0.25s var(--ease-out); outline: none; appearance: none; -webkit-appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2394A3B8' d='M6 8L1 3h10z'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 10px center; padding-right: 28px; }
.filter-select:focus { border-color: var(--input-border-focus); box-shadow: var(--input-shadow-focus); }
.filter-select option { background: var(--color-bg-secondary); color: var(--color-text-secondary); }
.clear-filter-btn { padding: var(--spacing-xs) 0.75rem; background: var(--color-error-bg); border: 1px solid var(--color-error-border); border-radius: var(--radius-sm); color: var(--color-error-lighter); font-size: var(--font-size-xs); cursor: pointer; transition: all 0.2s var(--ease-out); white-space: nowrap; }
.clear-filter-btn:hover { background: var(--color-error-hover); border-color: rgba(255, 77, 79, 0.4); }
.input-container { display: flex; flex-direction: column; gap: var(--spacing-md); position: relative; }
.intent-textarea { width: 100%; min-height: 150px; padding: var(--input-padding); border: 2px solid var(--input-border); border-radius: var(--input-radius); background: var(--input-bg); color: var(--color-text-primary); font-size: var(--font-size-base); font-family: inherit; resize: vertical; transition: border-color 0.3s var(--ease-out), box-shadow 0.3s var(--ease-out); }
.intent-textarea:focus { outline: none; border-color: var(--input-border-focus); box-shadow: var(--input-shadow-focus); }
.intent-textarea::placeholder { color: var(--color-text-disabled); }
.intent-textarea:disabled { opacity: 0.6; cursor: not-allowed; }
.submit-btn { padding: var(--spacing-md) var(--spacing-lg); background: linear-gradient(135deg, rgba(22, 93, 255, 0.9) 0%, rgba(114, 46, 209, 0.75) 100%); color: var(--color-text-primary); border: 1px solid var(--color-primary-border); border-radius: var(--radius-md); font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); cursor: pointer; transition: var(--button-transition); box-shadow: var(--shadow-glow-primary), 0 2px 8px var(--color-primary-glow); backdrop-filter: blur(8px); min-height: var(--button-height-lg); }
.submit-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 0 28px rgba(22, 93, 255, 0.4), 0 6px 24px rgba(22, 93, 255, 0.3); background: linear-gradient(135deg, rgba(22, 93, 255, 1) 0%, rgba(114, 46, 209, 0.9) 100%); border-color: rgba(59, 130, 246, 0.6); }
.submit-btn:active:not(:disabled) { transform: scale(0.97); }
.submit-btn:disabled { opacity: 0.35; cursor: not-allowed; box-shadow: none; transform: none; }
.thinking-panel { margin-top: 1.25rem; padding: 1.25rem; background: var(--gradient-glass-strong); border-radius: var(--radius-lg); border: 1px solid var(--color-primary-border); box-shadow: var(--shadow-glow-primary); position: relative; overflow: hidden; }
.thinking-panel::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, transparent, var(--color-primary), transparent); animation: scanline 2s linear infinite; }
.thinking-panel.failed { border-color: var(--color-error-border); box-shadow: var(--shadow-glow-error), inset 0 0 60px rgba(239, 68, 68, 0.05); background: linear-gradient(135deg, var(--color-error-bg) 0%, var(--color-bg-glass-strong) 100%); animation: failureShake 0.5s cubic-bezier(0.36, 0.07, 0.19, 0.97) both; }
.thinking-panel.failed::before { background: linear-gradient(90deg, transparent, var(--color-error), transparent); animation: failureScanline 0.8s ease-out; animation-fill-mode: forwards; }
@keyframes failureShake { 0%, 100% { transform: translateX(0); } 10% { transform: translateX(-6px); } 20% { transform: translateX(5px); } 30% { transform: translateX(-4px); } 40% { transform: translateX(3px); } 50% { transform: translateX(-2px); } 60% { transform: translateX(1px); } }
@keyframes failureScanline { 0% { transform: translateX(-100%); opacity: 1; } 100% { transform: translateX(100%); opacity: 0.6; } }
.reasoning-failure-overlay { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: var(--spacing-lg) 1.25rem; animation: failureFadeIn 0.4s ease-out 0.3s both; }
@keyframes failureFadeIn { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }
.failure-icon-ring { width: 64px; height: 64px; border-radius: 50%; border: 3px solid var(--color-error); display: flex; align-items: center; justify-content: center; margin-bottom: var(--spacing-md); animation: failureRingPulse 1s ease-in-out infinite, failureRingAppear 0.5s var(--ease-spring) both; box-shadow: var(--shadow-glow-error), inset 0 0 12px rgba(239, 68, 68, 0.1); }
@keyframes failureRingPulse { 0%, 100% { box-shadow: 0 0 20px rgba(239, 68, 68, 0.3), inset 0 0 12px rgba(239, 68, 68, 0.1); } 50% { box-shadow: 0 0 30px rgba(239, 68, 68, 0.5), inset 0 0 16px rgba(239, 68, 68, 0.15); } }
@keyframes failureRingAppear { from { transform: scale(0); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.failure-x-mark { font-size: var(--font-size-3xl); font-weight: 900; color: var(--color-error); line-height: 1; animation: failureXAppear 0.3s ease-out 0.2s both; }
@keyframes failureXAppear { from { transform: scale(0) rotate(-90deg); opacity: 0; } to { transform: scale(1) rotate(0deg); opacity: 1; } }
.failure-title { font-size: var(--font-size-lg); font-weight: 700; color: var(--color-error); margin: 0 0 var(--spacing-sm); text-shadow: 0 0 12px rgba(239, 68, 68, 0.3); }
.failure-message { font-size: var(--font-size-base); color: rgba(255, 255, 255, 0.75); margin: 0 0 0.75rem; text-align: center; line-height: 1.6; }
.failure-hint { font-size: var(--font-size-sm); color: var(--color-text-tertiary); padding: var(--spacing-sm) var(--spacing-md); background: var(--color-primary-bg); border: 1px solid var(--color-primary-border); border-radius: var(--radius-md); text-align: center; line-height: 1.5; }
@keyframes scanline { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }
.thinking-title { font-size: 0.9375rem; font-weight: 700; color: var(--color-primary-light); margin-bottom: var(--spacing-md); display: flex; align-items: center; gap: var(--spacing-sm); }
.thinking-title::before { content: '🤖'; font-size: var(--font-size-lg); }
.thinking-steps { display: flex; flex-direction: column; gap: 0.75rem; }
.thinking-step { display: flex; align-items: center; gap: 0.75rem; font-size: var(--font-size-base); color: var(--color-text-tertiary); padding: 10px 14px; border-radius: var(--radius-md); transition: all 0.3s var(--ease-out); position: relative; }
.thinking-step.active { color: var(--color-text-secondary); background: var(--color-primary-bg); }
.thinking-step.current { color: var(--color-primary-light); font-weight: 600; background: linear-gradient(90deg, var(--color-primary-hover), transparent); animation: stepGlow 2s ease-in-out infinite; }
@keyframes stepGlow { 0%, 100% { box-shadow: 0 0 10px rgba(22, 93, 255, 0.2); } 50% { box-shadow: 0 0 20px rgba(22, 93, 255, 0.4); } }
.step-dot { width: 12px; height: 12px; background: var(--color-bg-tertiary); border-radius: 50%; border: 2px solid var(--color-text-tertiary); transition: all 0.3s var(--ease-out); position: relative; }
.step-dot.active { background: var(--color-primary); border-color: var(--color-primary-light); box-shadow: var(--shadow-glow-primary); }
.thinking-step.current .step-dot.active { animation: dotPulse 1.2s ease-in-out infinite; }
@keyframes dotPulse { 0%, 100% { transform: scale(1); box-shadow: 0 0 10px rgba(22, 93, 255, 0.5); } 50% { transform: scale(1.4); box-shadow: 0 0 20px rgba(22, 93, 255, 0.8); } }
@keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.5; transform: scale(1.2); } }
.history-list { display: flex; flex-direction: column; gap: var(--spacing-md); }
.history-item { padding: var(--spacing-md); background: var(--color-bg-input); border-radius: var(--radius-lg); transition: all 0.3s var(--ease-out); cursor: pointer; border: 1px solid transparent; }
.history-item:hover { background: var(--color-bg-active); transform: translateY(-1px); box-shadow: var(--shadow-card); border-color: var(--color-border-primary); }
.history-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
.status-badge { font-size: var(--font-size-xs); padding: var(--spacing-xs) 0.75rem; border-radius: var(--radius-lg); font-weight: 500; transition: background 0.25s var(--ease-out), color 0.25s var(--ease-out); }
.status-badge.completed { background: var(--color-success-bg); color: var(--color-success); border: 1px solid var(--color-success-border); }
.status-badge.approved { background: var(--color-success-bg); color: var(--color-success); border: 1px solid var(--color-success-border); }
.status-badge.pending { background: var(--color-warning-bg); color: var(--color-warning); border: 1px solid var(--color-warning-border); }
.status-badge.running { background: var(--color-primary-bg); color: var(--color-primary-light); border: 1px solid var(--color-primary-border); }
.status-badge.rejected { background: var(--color-error-bg); color: var(--color-error); border: 1px solid var(--color-error-border); }
.history-time { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.history-input { font-size: var(--font-size-base); color: var(--color-text-primary); margin-bottom: 0.75rem; padding: 0.75rem; background: var(--color-primary-bg); border-radius: var(--radius-md); border-left: 3px solid var(--color-primary); }
.history-output { background: rgba(0, 0, 0, 0.3); border-radius: var(--radius-md); padding: 0.75rem; margin-bottom: 0.75rem; max-height: 120px; overflow-y: auto; }
.history-output pre { font-size: var(--font-size-xs); color: var(--color-success); white-space: pre-wrap; word-break: break-all; margin: 0; }
.history-actions { display: flex; gap: var(--spacing-sm); }
.action-btn.small { padding: 0.375rem 0.75rem; font-size: var(--font-size-xs); background: rgba(22, 93, 255, 0.1); color: var(--color-primary-light); border: 1px solid rgba(22, 93, 255, 0.2); border-radius: var(--radius-md); font-weight: 500; cursor: pointer; transition: all 0.25s ease; min-height: 44px; backdrop-filter: blur(8px); }
.action-btn.small:hover { background: rgba(22, 93, 255, 0.2); border-color: rgba(22, 93, 255, 0.4); box-shadow: 0 0 8px rgba(22, 93, 255, 0.12); transform: scale(1.02); }
.action-btn.small:active { transform: scale(0.97); }
.action-btn.small.success { background: rgba(82, 196, 26, 0.1); color: var(--color-success); border-color: rgba(82, 196, 26, 0.2); }
.action-btn.small.success:hover { background: rgba(82, 196, 26, 0.2); border-color: rgba(82, 196, 26, 0.4); box-shadow: 0 0 8px rgba(82, 196, 26, 0.12); }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 1.25rem; color: var(--color-text-tertiary); }
.empty-icon { font-size: var(--font-size-4xl); margin-bottom: var(--spacing-md); }
.empty-state p { font-size: var(--font-size-base); margin-bottom: 0.75rem; }
.pagination { display: flex; align-items: center; justify-content: center; gap: var(--spacing-md); margin-top: 1.25rem; padding-top: var(--spacing-md); border-top: 1px solid var(--color-border-primary); }
.pagination-btn { padding: var(--spacing-sm) var(--spacing-md); background: var(--color-bg-hover); border: none; border-radius: var(--radius-md); color: var(--color-text-secondary); font-size: var(--font-size-sm); font-weight: 500; cursor: pointer; transition: var(--button-transition); white-space: nowrap; min-height: 40px; }
.pagination-btn:hover:not(:disabled) { background: var(--color-bg-active); }
.pagination-btn:active:not(:disabled) { background: var(--color-bg-hover); transform: scale(0.97); }
.pagination-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pagination-info { font-size: var(--font-size-sm); color: var(--color-text-tertiary); text-align: center; }
.pagination-total { display: block; font-size: var(--font-size-xs); color: var(--color-text-tertiary); margin-top: var(--spacing-xs); }
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: var(--modal-overlay-bg); backdrop-filter: blur(var(--modal-backdrop-blur)); -webkit-backdrop-filter: blur(var(--modal-backdrop-blur)); display: flex; align-items: center; justify-content: center; z-index: var(--z-overlay); animation: fade-in 0.2s var(--ease-out); }
.modal-content { background: var(--color-bg-elevated); border-radius: var(--modal-border-radius); border: 1px solid var(--color-border-primary); max-height: 90vh; overflow: hidden; display: flex; flex-direction: column; box-shadow: var(--modal-shadow); }
.diff-modal { width: 90%; max-width: 1100px; }
.security-alert-modal { width: 90%; max-width: 600px; }
.security-alert-content { padding: 1.25rem; }
.threat-level-badge { display: flex; align-items: center; gap: var(--spacing-sm); padding: 0.75rem var(--spacing-md); border-radius: var(--radius-md); margin-bottom: var(--spacing-md); font-weight: 600; font-size: 0.9375rem; }
.threat-level-badge.critical { background: rgba(255, 77, 79, 0.12); color: var(--color-error-lighter); border: 1px solid rgba(255, 77, 79, 0.3); }
.threat-level-badge.high { background: rgba(250, 173, 20, 0.12); color: var(--color-warning); border: 1px solid rgba(250, 173, 20, 0.3); }
.threat-level-badge.medium { background: rgba(250, 173, 20, 0.08); color: var(--color-warning-deep); border: 1px solid rgba(250, 173, 20, 0.2); }
.threat-level-badge.low { background: rgba(82, 196, 26, 0.08); color: var(--color-success); border: 1px solid rgba(82, 196, 26, 0.2); }
.threat-icon { font-size: var(--font-size-xl); }
.security-message { margin: 0 0 0.75rem; color: rgba(255,255,255,0.8); font-size: var(--font-size-base); }
.threat-list { display: flex; flex-direction: column; gap: var(--spacing-sm); margin-bottom: 1.25rem; max-height: 240px; overflow-y: auto; }
.threat-item { display: flex; align-items: center; gap: 10px; padding: 10px 0.75rem; border-radius: var(--radius-sm); background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06); }
.threat-item.critical { border-left: 3px solid var(--color-error); }
.threat-item.high { border-left: 3px solid var(--color-warning); }
.threat-item.medium { border-left: 3px solid var(--color-warning-deep); }
.threat-item.low { border-left: 3px solid var(--color-success); }
.threat-level-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.threat-item.critical .threat-level-dot { background: var(--color-error); }
.threat-item.high .threat-level-dot { background: var(--color-warning); }
.threat-item.medium .threat-level-dot { background: var(--color-warning-deep); }
.threat-item.low .threat-level-dot { background: var(--color-success); }
.threat-info { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.threat-desc { font-size: var(--font-size-sm); color: rgba(255,255,255,0.9); }
.threat-type { font-size: 0.6875rem; color: rgba(255,255,255,0.45); }
.threat-level-tag { font-size: 0.625rem; padding: 2px 0.375rem; border-radius: var(--radius-xs); font-weight: 600; }
.threat-level-tag.critical { background: rgba(255,77,79,0.15); color: var(--color-error-lighter); }
.threat-level-tag.high { background: rgba(250,173,20,0.15); color: var(--color-warning); }
.threat-level-tag.medium { background: rgba(212,136,6,0.15); color: var(--color-warning-deep); }
.threat-level-tag.low { background: rgba(82,196,26,0.15); color: var(--color-success); }
.security-actions { display: flex; gap: 0.75rem; justify-content: flex-end; }
.security-btn { padding: var(--spacing-sm) 1.25rem; border-radius: var(--radius-sm); border: none; cursor: pointer; font-size: var(--font-size-sm); font-weight: 500; transition: all 0.2s; }
.security-btn.cancel { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.7); }
.security-btn.cancel:hover { background: rgba(255,255,255,0.12); }
.security-btn.override { background: rgba(250,173,20,0.15); color: var(--color-warning); border: 1px solid rgba(250,173,20,0.3); }
.security-btn.override:hover { background: rgba(250,173,20,0.25); }
.verification-modal { width: 90%; max-width: 900px; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem var(--spacing-lg); border-bottom: 1px solid var(--color-border-primary); }
.modal-title { font-size: var(--font-size-lg); font-weight: 600; color: var(--color-text-primary); margin: 0; }
.security-alert-title { color: var(--color-error-lighter); }
.close-btn { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; background: var(--color-bg-hover); border: none; border-radius: var(--radius-md); color: var(--color-text-primary); font-size: var(--font-size-xl); cursor: pointer; transition: var(--button-transition); }
.close-btn:hover { background: var(--color-bg-active); }
.close-btn:active { transform: scale(0.97); }
.diff-toolbar { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem var(--spacing-lg); background: rgba(15, 23, 42, 0.4); border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
.diff-legend { display: flex; gap: var(--spacing-md); }
.legend-item { display: flex; align-items: center; gap: 0.375rem; font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.legend-color { width: 12px; height: 3px; border-radius: 2px; }
.legend-item.added .legend-color { background: var(--color-success); }
.legend-item.removed .legend-color { background: var(--color-error); }
.legend-item.changed .legend-color { background: #FBBF24; }
.diff-actions-bar { display: flex; align-items: center; gap: var(--spacing-sm); }
.toolbar-btn { padding: var(--spacing-xs) 10px; background: rgba(255, 255, 255, 0.08); border: none; border-radius: var(--radius-sm); color: var(--color-text-tertiary); font-size: var(--font-size-xs); cursor: pointer; transition: all 0.2s ease; }
.toolbar-btn:hover { background: rgba(255, 255, 255, 0.12); color: var(--color-text-primary); }
.selected-count { font-size: var(--font-size-xs); color: var(--color-text-tertiary); margin-left: var(--spacing-xs); }
.diff-content { display: grid; grid-template-columns: 1fr auto 1fr; gap: var(--spacing-md); padding: var(--spacing-lg); overflow: auto; max-height: 500px; }
.diff-panel { display: flex; flex-direction: column; gap: 0.75rem; }
.diff-title { font-size: var(--font-size-base); font-weight: 600; color: var(--color-text-secondary); margin: 0; display: flex; align-items: center; gap: var(--spacing-sm); }
.diff-title-icon { font-size: var(--font-size-md); }
.diff-code-panel { background: rgba(15, 23, 42, 0.9); border-radius: var(--radius-lg); border: 1px solid rgba(255, 255, 255, 0.15); overflow: hidden; max-height: 400px; display: flex; flex-direction: row; }
.diff-code-panel.left { border-left: 3px solid var(--color-error); }
.diff-code-panel.right { border-left: 3px solid var(--color-success); }
.diff-line-numbers { background: rgba(0, 0, 0, 0.4); padding: 0.75rem var(--spacing-sm); text-align: right; user-select: none; min-width: 50px; max-width: 60px; flex-shrink: 0; overflow-y: auto; overflow-x: hidden; }
.line-number { font-size: var(--font-size-base); color: var(--color-text-tertiary); font-family: 'Consolas', 'Monaco', monospace; line-height: 24px; }
.diff-code-body { flex: 1; overflow-y: auto; overflow-x: auto; padding: 0.75rem; }
.diff-line { display: flex; line-height: 24px; padding: 0 var(--spacing-xs); cursor: pointer; transition: background-color 0.2s ease; }
.diff-line:hover { background: rgba(255, 255, 255, 0.05); }
.diff-line.selected { background: rgba(22, 93, 255, 0.2); }
.diff-line.same { color: var(--color-text-tertiary); }
.diff-line.added { color: var(--color-success); background: rgba(82, 196, 26, 0.1); }
.diff-line.removed { color: var(--color-error); background: rgba(239, 68, 68, 0.1); }
.diff-line.changed { color: #FBBF24; background: rgba(251, 191, 36, 0.1); }
.line-marker { width: 20px; text-align: center; font-weight: bold; font-size: var(--font-size-base); flex-shrink: 0; }
.line-content { font-size: var(--font-size-base); font-family: 'Consolas', 'Monaco', 'Fira Code', monospace; white-space: pre; word-break: break-all; }
.diff-divider { display: flex; align-items: center; justify-content: center; }
.diff-arrow { font-size: var(--font-size-2xl); color: var(--color-text-tertiary); }
.diff-summary { display: flex; align-items: center; gap: 10px; padding: var(--spacing-md) var(--spacing-lg); background: rgba(22, 93, 255, 0.1); border-top: 1px solid rgba(22, 93, 255, 0.2); border-bottom: 1px solid rgba(22, 93, 255, 0.2); }
.diff-summary-icon { font-size: var(--font-size-lg); }
.diff-summary-text { font-size: var(--font-size-base); color: var(--color-primary-light); }
.modal-actions { display: flex; gap: 0.75rem; padding: 1.25rem var(--spacing-lg); justify-content: flex-end; }
.diff-actions { justify-content: space-between; }
.modal-btn { padding: 10px var(--spacing-lg); border: none; border-radius: var(--radius-md); font-size: var(--font-size-base); font-weight: 600; cursor: pointer; transition: var(--button-transition); }
.modal-btn:active { transform: scale(0.97); }
.modal-btn.cancel { background: var(--color-bg-hover); color: var(--color-text-tertiary); }
.modal-btn.cancel:hover { background: var(--color-bg-active); }
.modal-btn.confirm { background: var(--gradient-success); color: var(--color-text-primary); }
.modal-btn.confirm:hover { transform: translateY(-1px); box-shadow: var(--shadow-glow-success); }
.verification-content { padding: var(--spacing-lg); overflow: auto; }
.verification-info { margin-bottom: var(--spacing-lg); }
.verification-intent { font-size: var(--font-size-md); font-weight: 600; color: var(--color-text-primary); margin: 0 0 var(--spacing-md) 0; padding: 0.75rem var(--spacing-md); background: rgba(22, 93, 255, 0.1); border-radius: var(--radius-md); border-left: 3px solid var(--color-primary); }
.verification-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(var(--grid-min-col), 1fr)); gap: var(--spacing-md); margin-bottom: var(--spacing-lg); }
.verification-metrics .metric-card { display: flex; flex-direction: column; align-items: center; gap: var(--spacing-sm); padding: 1.25rem; background: rgba(15, 23, 42, 0.5); border-radius: var(--radius-lg); border: 1px solid rgba(255, 255, 255, 0.1); }
.verification-metrics .metric-icon { font-size: var(--font-size-2xl); width: auto; height: auto; background: none !important; box-shadow: none !important; }
.verification-metrics .metric-value { font-size: var(--font-size-2xl); font-weight: 700; color: var(--color-text-primary); text-shadow: none; }
.verification-metrics .metric-value.success { color: var(--color-success); }
.verification-metrics .metric-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.verification-chart { height: 300px; background: rgba(15, 23, 42, 0.5); border-radius: var(--radius-lg); margin-bottom: var(--spacing-lg); border: 1px solid rgba(255, 255, 255, 0.1); }
.verification-content .empty-state { display: flex; align-items: center; justify-content: center; min-height: 200px; color: var(--color-text-tertiary); font-size: var(--font-size-base); }
.verification-timeline { background: rgba(15, 23, 42, 0.5); border-radius: var(--radius-lg); padding: 1.25rem; border: 1px solid rgba(255, 255, 255, 0.1); }
.timeline-title { font-size: var(--font-size-base); font-weight: 600; color: var(--color-text-secondary); margin: 0 0 var(--spacing-md) 0; }
.timeline-items { display: flex; flex-direction: column; gap: 0.75rem; }
.timeline-item { display: flex; align-items: center; gap: 0.75rem; padding: 10px 0.75rem; border-radius: var(--radius-md); background: rgba(255, 255, 255, 0.02); }
.timeline-item.completed { background: rgba(82, 196, 26, 0.1); }
.timeline-item.current { background: rgba(22, 93, 255, 0.1); animation: timelinePulse 2s ease-in-out infinite; }
@keyframes timelinePulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(22, 93, 255, 0.3); } 50% { box-shadow: 0 0 0 8px rgba(22, 93, 255, 0); } }
.timeline-dot { width: 10px; height: 10px; background: var(--color-text-tertiary); border-radius: 50%; }
.timeline-item.completed .timeline-dot { background: var(--color-success); }
.timeline-item.current .timeline-dot { background: var(--color-primary); }
.timeline-time { font-size: var(--font-size-xs); color: var(--color-text-tertiary); font-family: 'Consolas', 'Monaco', monospace; min-width: 90px; }
.timeline-text { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
.intent-detail-modal { width: 90%; max-width: 700px; }
.intent-detail-content { padding: var(--spacing-lg); overflow-y: auto; max-height: 70vh; }
.detail-section { margin-bottom: var(--spacing-lg); }
.detail-section:last-child { margin-bottom: 0; }
.detail-title { font-size: var(--font-size-base); font-weight: 600; color: var(--color-text-secondary); margin-bottom: 0.75rem; display: flex; align-items: center; gap: var(--spacing-sm); }
.detail-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--spacing-md); }
.detail-item { display: flex; flex-direction: column; gap: 0.375rem; }
.detail-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); font-weight: 500; }
.detail-value { font-size: var(--font-size-base); color: var(--color-text-primary); font-weight: 500; }
.detail-value.status-badge { display: inline-flex; width: fit-content; padding: var(--spacing-xs) 0.75rem; }
.intent-input-display { padding: var(--spacing-md); background: rgba(22, 93, 255, 0.1); border-radius: var(--radius-lg); border-left: 3px solid var(--color-primary); color: var(--color-text-primary); font-size: var(--font-size-base); line-height: 1.6; }
.structured-output-display { background: rgba(0, 0, 0, 0.3); border-radius: var(--radius-lg); padding: var(--spacing-md); overflow-x: auto; }
.structured-output-display pre { margin: 0; font-size: var(--font-size-sm); color: var(--color-success); font-family: 'Consolas', 'Monaco', monospace; line-height: 1.6; }
.processing-logs { display: flex; flex-direction: column; gap: 0.75rem; }
.log-item { padding: 0.75rem; background: rgba(15, 23, 42, 0.5); border-radius: var(--radius-md); border-left: 3px solid var(--color-primary-light); }
.log-time { font-size: var(--font-size-xs); color: var(--color-text-tertiary); margin-bottom: var(--spacing-xs); font-family: 'Consolas', 'Monaco', monospace; }
.log-message { font-size: var(--font-size-base); color: var(--color-text-secondary); line-height: 1.5; }
.detail-actions { display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: var(--spacing-sm); padding-top: var(--spacing-md); border-top: 1px solid rgba(255, 255, 255, 0.08); }
.detail-btn { padding: 10px var(--spacing-lg); border: none; border-radius: var(--radius-md); font-size: var(--font-size-base); font-weight: 600; cursor: pointer; transition: all 0.25s ease; }
.detail-btn:active { transform: scale(0.97); }
.detail-btn.reject { background: rgba(239, 68, 68, 0.2); color: var(--color-error); }
.detail-btn.reject:hover { background: rgba(239, 68, 68, 0.3); transform: translateY(-1px); }
.detail-btn.approve { background: linear-gradient(135deg, var(--color-success) 0%, var(--color-success-light) 100%); color: var(--color-text-primary); }
.detail-btn.approve:hover { transform: translateY(-1px); box-shadow: 0 4px 14px rgba(82, 196, 26, 0.4); }
.copilot-toggle-btn { padding: 0.375rem 14px; border: 1px solid rgba(22, 93, 255, 0.3); border-radius: var(--radius-lg); background: rgba(22, 93, 255, 0.12); color: var(--color-primary-light); font-size: var(--font-size-sm); cursor: pointer; transition: all 0.25s ease; min-height: 44px; backdrop-filter: blur(8px); display: inline-flex; align-items: center; gap: 4px; box-shadow: 0 0 8px rgba(22, 93, 255, 0.08); }
.copilot-toggle-btn:hover { background: rgba(22, 93, 255, 0.22); border-color: rgba(59, 130, 246, 0.6); color: var(--color-primary-lighter); box-shadow: 0 0 16px rgba(22, 93, 255, 0.2), 0 2px 8px rgba(22, 93, 255, 0.12); transform: scale(1.02); }
.copilot-toggle-btn:active { transform: scale(0.97); }
.copilot-toggle-btn:disabled { opacity: 0.35; cursor: not-allowed; transform: none; box-shadow: none; }
.deepseek-badge { display: inline-flex; align-items: center; margin-left: var(--spacing-xs); font-size: var(--font-size-xs); padding: 2px 7px; border-radius: var(--radius-md); background: linear-gradient(135deg, rgba(22, 93, 255, 0.18), rgba(114, 46, 209, 0.15)); border: 1px solid rgba(22, 93, 255, 0.3); color: var(--color-primary-lighter); backdrop-filter: blur(4px); animation: pulse-glow 2s ease-in-out infinite; box-shadow: 0 0 6px rgba(22, 93, 255, 0.12); }
@keyframes pulse-glow { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
.copilot-send-btn:disabled, .copilot-apply-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.streaming-indicator { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--color-success); margin-right: 0.375rem; animation: blink 1s ease-in-out infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.autocomplete-dropdown { position: absolute; top: 100%; left: 0; right: 0; background: var(--color-bg-elevated); border: 1px solid var(--color-border-secondary); border-radius: var(--radius-md); box-shadow: var(--shadow-dropdown); z-index: var(--z-dropdown); max-height: 200px; overflow-y: auto; backdrop-filter: blur(16px); }
.autocomplete-item { padding: 10px 14px; cursor: pointer; font-size: var(--font-size-sm); color: var(--color-text-secondary); border-bottom: 1px solid var(--color-border-primary); transition: background 0.15s; }
.autocomplete-item:hover { background: var(--color-primary-bg); color: var(--color-primary-light); }
.autocomplete-item:last-child { border-bottom: none; }
.copilot-chat-panel { margin-top: var(--spacing-md); border: 1px solid var(--color-border-primary); border-radius: var(--radius-lg); background: var(--color-bg-glass-strong); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); overflow: hidden; transition: opacity 0.35s var(--ease-out), transform 0.35s var(--ease-out); animation: panelSlideIn 0.35s var(--ease-out); max-height: 600px; display: flex; flex-direction: column; }
@keyframes panelSlideIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
.copilot-messages { max-height: 300px; overflow-y: auto; padding: var(--spacing-md); }
.copilot-msg { display: flex; gap: 10px; margin-bottom: 14px; }
.copilot-msg.user { flex-direction: row-reverse; }
.msg-avatar { width: 32px; height: 32px; border-radius: 50%; background: rgba(22, 93, 255, 0.15); display: flex; align-items: center; justify-content: center; font-size: var(--font-size-md); flex-shrink: 0; }
.copilot-msg.user .msg-avatar { background: rgba(82, 196, 26, 0.15); }
.msg-content { max-width: 80%; }
.msg-text { padding: 10px 14px; border-radius: var(--radius-lg); font-size: var(--font-size-sm); line-height: 1.7; letter-spacing: 0.2px; white-space: pre-wrap; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15); }
.copilot-msg.assistant .msg-text { background: var(--color-bg-glass-strong); border: 1px solid var(--color-border-primary); border-left: 3px solid var(--color-primary); color: var(--color-text-secondary); }
.copilot-msg.user .msg-text { background: var(--color-primary); border-right: 3px solid rgba(255, 255, 255, 0.3); color: var(--color-text-primary); }
.msg-timestamp { font-size: 0.6875rem; color: var(--color-text-tertiary); }
.msg-meta { display: flex; justify-content: space-between; align-items: center; margin-top: var(--spacing-xs); gap: var(--spacing-sm); }
.msg-actions { display: flex; gap: var(--spacing-xs); opacity: 0; transition: opacity 0.2s ease; }
.copilot-msg:hover .msg-actions { opacity: 1; }
.msg-action-btn { background: none; border: none; cursor: pointer; font-size: var(--font-size-xs); padding: 2px var(--spacing-xs); border-radius: var(--radius-sm); opacity: 0.6; transition: opacity 0.2s ease, background 0.2s ease; min-width: 44px; min-height: 44px; }
.msg-action-btn:hover { opacity: 1; background: rgba(255, 255, 255, 0.1); }
.msg-suggestions { display: flex; gap: 0.375rem; flex-wrap: wrap; margin-top: var(--spacing-sm); }
.suggestion-chip { padding: var(--spacing-xs) 10px; border: 1px solid var(--color-border-secondary); border-radius: var(--radius-xl); background: var(--color-bg-glass); color: var(--color-text-tertiary); font-size: var(--font-size-xs); cursor: pointer; transition: var(--button-transition); min-height: 44px; }
.suggestion-chip:hover { border-color: var(--color-primary); color: var(--color-primary); background: var(--color-primary-bg); transform: scale(1.05); }
.suggestion-chip:active { transform: scale(0.97); }
.copilot-input-row { display: flex; gap: var(--spacing-sm); padding: 0.75rem var(--spacing-md); border-top: 1px solid var(--color-border-primary); background: var(--color-bg-input); }
.copilot-input { flex: 1; padding: var(--spacing-sm) 0.75rem; border: 1px solid var(--input-border); border-radius: var(--input-radius); font-size: var(--font-size-sm); background: var(--input-bg); color: var(--color-text-secondary); outline: none; transition: border-color 0.2s var(--ease-out); }
.copilot-input::placeholder { color: var(--color-text-disabled); }
.copilot-input:focus { border-color: var(--input-border-focus); box-shadow: var(--input-shadow-focus); }
.copilot-send-btn { padding: var(--spacing-sm) var(--spacing-md); border: none; border-radius: var(--radius-md); background: var(--gradient-primary); color: var(--color-text-primary); font-size: var(--font-size-sm); cursor: pointer; transition: var(--button-transition); min-height: 40px; }
.copilot-send-btn:hover { background: var(--gradient-primary-hover); }
.copilot-send-btn:active:not(:disabled) { transform: scale(0.97); }
.copilot-apply-btn { padding: var(--spacing-sm) 0.75rem; border: 1px solid var(--color-primary-border); border-radius: var(--radius-md); background: var(--color-primary-bg); color: var(--color-primary); font-size: var(--font-size-sm); cursor: pointer; transition: var(--button-transition); min-height: 44px; white-space: nowrap; }
.copilot-apply-btn:hover { background: var(--color-primary-hover); }
.copilot-apply-btn:active:not(:disabled) { transform: scale(0.97); }
.copilot-header-bar { display: flex; justify-content: space-between; align-items: center; padding: 10px var(--spacing-md); border-bottom: 1px solid var(--color-border-primary); background: linear-gradient(135deg, var(--color-bg-input) 0%, var(--color-primary-bg) 100%); }
.copilot-header-actions { display: flex; gap: 0.375rem; }
.copilot-status-group { display: flex; gap: 0.75rem; align-items: center; }
.copilot-status { display: flex; align-items: center; gap: 0.375rem; padding: 3px var(--spacing-sm); border-radius: var(--radius-md); transition: background 0.25s ease; }
.copilot-status:has(.status-dot.online) { background: rgba(82, 196, 26, 0.06); animation: providerActivePulse 3s ease-in-out infinite; }
@keyframes providerActivePulse { 0%, 100% { background: rgba(82, 196, 26, 0.06); } 50% { background: rgba(82, 196, 26, 0.12); } }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.online { background: var(--color-success); box-shadow: 0 0 8px rgba(82, 196, 26, 0.6), 0 0 16px rgba(82, 196, 26, 0.3); animation: pulse-dot 2s ease-in-out infinite; }
.status-dot.offline { background: var(--color-text-tertiary); }

.status-text { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.copilot-suggest-btn { padding: var(--spacing-xs) 10px; border: 1px solid var(--color-border-secondary); border-radius: var(--radius-md); background: var(--color-bg-glass); color: var(--color-text-tertiary); font-size: var(--font-size-xs); cursor: pointer; transition: var(--button-transition); min-height: 44px; }
.copilot-suggest-btn:hover { border-color: var(--color-primary); color: var(--color-primary); }
.copilot-suggest-btn:active { transform: scale(0.97); }
.smart-suggestions-bar { padding: 10px var(--spacing-md); border-bottom: 1px solid var(--color-border-primary); display: flex; flex-direction: column; gap: var(--spacing-sm); max-height: 200px; overflow-y: auto; }
.smart-suggestion-card { display: flex; align-items: center; gap: 10px; padding: 10px 0.75rem; border-radius: var(--radius-md); cursor: pointer; transition: var(--button-transition); border: 1px solid transparent; border-left: 3px solid transparent; }
.smart-suggestion-card:hover { background: var(--color-primary-bg); border-color: var(--color-primary-border); border-left-color: var(--color-primary); }
.smart-suggestion-card:active { transform: scale(0.97); }
.smart-suggestion-card.warning { background: var(--color-warning-bg); border-color: var(--color-warning-border); border-left-color: var(--color-warning); }
.smart-suggestion-card.warning:hover { background: var(--color-warning-hover); }
.smart-suggestion-card.info { background: var(--color-primary-bg); border-color: var(--color-primary-border); border-left-color: var(--color-primary); }
.smart-suggestion-card.tip { background: var(--color-success-bg); border-color: var(--color-success-border); border-left-color: var(--color-success); }
.sg-icon { font-size: var(--font-size-lg); flex-shrink: 0; }
.sg-info { flex: 1; min-width: 0; }
.sg-title { font-size: var(--font-size-sm); font-weight: 600; color: var(--color-text-secondary); margin-bottom: 2px; }
.sg-desc { font-size: var(--font-size-xs); color: var(--color-text-tertiary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sg-arrow { color: var(--color-text-tertiary); font-size: var(--font-size-base); flex-shrink: 0; }
.streaming-cursor { display: inline; margin-left: 2px; }
.cursor-blink { animation: cursorBlink 0.8s ease-in-out infinite; color: var(--color-primary-light); font-weight: bold; }
@keyframes cursorBlink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
.thinking-dots { display: flex; gap: var(--spacing-xs); align-items: center; padding: var(--spacing-sm) 0; }
.thinking-dots .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-primary-light); animation: dotBounce 1.4s ease-in-out infinite; }
.thinking-dots .dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots .dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes dotBounce { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }
.code-block { background: rgba(0, 0, 0, 0.4); border-radius: var(--radius-md); padding: 0.75rem; margin: var(--spacing-sm) 0; overflow-x: auto; font-family: 'Consolas', 'Monaco', 'Fira Code', monospace; font-size: var(--font-size-xs); line-height: 1.6; border: 1px solid rgba(255, 255, 255, 0.08); }
.msg-text code { background: rgba(22, 93, 255, 0.15); padding: 2px 0.375rem; border-radius: var(--radius-sm); font-family: 'Consolas', 'Monaco', monospace; font-size: var(--font-size-xs); color: var(--color-primary-light); }
.msg-text .md-h3, .msg-text .md-h4 { color: var(--color-text-secondary); font-weight: 600; margin: var(--spacing-sm) 0 var(--spacing-xs) 0; }
.msg-text .md-li { padding-left: var(--spacing-sm); position: relative; margin: 2px 0; }
.msg-text .emoji-label { font-size: var(--font-size-base); }
.msg-text .emoji-label.warn { color: var(--color-warning); }
.msg-text .emoji-label.success { color: var(--color-success); }
.step-header { display: flex; align-items: center; gap: var(--spacing-sm); margin-bottom: var(--spacing-xs); }
.step-icon { font-size: var(--font-size-lg); }
.step-title { font-weight: 600; font-size: var(--font-size-base); }
.step-status { color: var(--color-success); font-size: var(--font-size-base); margin-left: auto; }
.step-desc { font-size: var(--font-size-sm); color: var(--color-text-tertiary); padding-left: 26px; line-height: 1.5; }
.typing-text { color: var(--color-primary-light); border-right: 2px solid var(--color-primary-light); animation: typingCursor 0.8s ease-in-out infinite; display: inline; }
@keyframes typingCursor { 0%, 100% { border-right-color: var(--color-primary-light); } 50% { border-right-color: transparent; } }
.step-pending { color: var(--color-text-tertiary); font-style: italic; }
.validation-error-panel { margin-top: var(--spacing-md); border-radius: var(--radius-lg); overflow: hidden; border: 1px solid rgba(255, 255, 255, 0.1); backdrop-filter: blur(12px); }
.validation-error-panel.error { border-color: rgba(239, 68, 68, 0.4); background: linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(30, 41, 59, 0.7) 100%); box-shadow: 0 0 24px rgba(239, 68, 68, 0.1), inset 0 1px 0 rgba(239, 68, 68, 0.15); }
.validation-error-panel.warning { border-color: rgba(250, 173, 20, 0.4); background: linear-gradient(135deg, rgba(250, 173, 20, 0.08) 0%, rgba(30, 41, 59, 0.7) 100%); box-shadow: 0 0 24px rgba(250, 173, 20, 0.1), inset 0 1px 0 rgba(250, 173, 20, 0.15); }
.validation-error-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; }
.validation-error-panel.error .validation-error-header { border-bottom: 1px solid rgba(239, 68, 68, 0.2); background: rgba(239, 68, 68, 0.06); }
.validation-error-panel.warning .validation-error-header { border-bottom: 1px solid rgba(250, 173, 20, 0.2); background: rgba(250, 173, 20, 0.06); }
.validation-error-title-group { display: flex; align-items: center; gap: 10px; }
.validation-error-icon { font-size: var(--font-size-2xl); line-height: 1; }
.validation-error-title { font-size: 0.9375rem; font-weight: 700; color: var(--color-text-secondary); }
.validation-severity-badge { font-size: 0.6875rem; padding: 2px 10px; border-radius: var(--radius-md); font-weight: 600; letter-spacing: 0.5px; }
.validation-severity-badge.error { background: rgba(239, 68, 68, 0.2); color: var(--color-error); border: 1px solid rgba(239, 68, 68, 0.3); }
.validation-severity-badge.warning { background: rgba(250, 173, 20, 0.2); color: var(--color-warning); border: 1px solid rgba(250, 173, 20, 0.3); }
.validation-dismiss-btn { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; background: rgba(255, 255, 255, 0.08); border: none; border-radius: var(--radius-sm); color: var(--color-text-tertiary); font-size: var(--font-size-base); cursor: pointer; transition: all 0.2s ease; }
.validation-dismiss-btn:hover { background: rgba(255, 255, 255, 0.15); color: var(--color-text-primary); }
.validation-error-body { padding: var(--spacing-md) 18px; }
.validation-error-desc { margin: 0 0 14px; font-size: var(--font-size-base); color: rgba(255, 255, 255, 0.8); line-height: 1.7; }
.validation-suggestions { background: rgba(15, 23, 42, 0.4); border-radius: var(--radius-md); padding: 14px; border: 1px solid rgba(255, 255, 255, 0.06); }
.validation-suggestions-label { font-size: var(--font-size-sm); font-weight: 600; color: var(--color-text-tertiary); margin-bottom: 10px; }
.validation-suggestion-chips { display: flex; flex-wrap: wrap; gap: var(--spacing-sm); }
.validation-suggestion-chip { padding: 7px var(--spacing-md); border: 1px solid rgba(22, 93, 255, 0.3); border-radius: 1.25rem; background: rgba(22, 93, 255, 0.1); color: var(--color-primary-light); font-size: var(--font-size-sm); cursor: pointer; transition: all 0.25s ease; white-space: nowrap; }
.validation-suggestion-chip:hover { background: rgba(22, 93, 255, 0.22); border-color: rgba(22, 93, 255, 0.6); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(22, 93, 255, 0.15); }
.validation-suggestion-chip:active { transform: scale(0.97); }
.validation-error-footer { display: flex; justify-content: space-between; align-items: center; padding: 10px 18px; border-top: 1px solid rgba(255, 255, 255, 0.06); }
.validation-error-panel.error .validation-error-footer { background: rgba(239, 68, 68, 0.04); }
.validation-error-panel.warning .validation-error-footer { background: rgba(250, 173, 20, 0.04); }
.validation-error-type-tag { font-size: 0.6875rem; padding: 3px var(--spacing-sm); border-radius: var(--radius-sm); background: rgba(255, 255, 255, 0.06); color: var(--color-text-tertiary); font-family: 'Consolas', 'Monaco', monospace; text-transform: uppercase; letter-spacing: 0.5px; }
.validation-retry-btn { padding: 0.375rem var(--spacing-md); border: 1px solid rgba(22, 93, 255, 0.4); border-radius: var(--radius-md); background: rgba(22, 93, 255, 0.12); color: var(--color-primary-light); font-size: var(--font-size-sm); cursor: pointer; transition: all 0.25s ease; }
.validation-retry-btn:hover { background: rgba(22, 93, 255, 0.22); border-color: var(--color-primary); }
.validation-retry-btn:active { transform: scale(0.97); }
.validation-slide-enter-active { animation: validationSlideIn 0.35s cubic-bezier(0.34, 1.56, 0.64, 1); }
.validation-slide-leave-active { animation: validationSlideOut 0.25s ease-in; }
@keyframes validationSlideIn { from { opacity: 0; transform: translateY(-12px) scale(0.97); max-height: 0; } to { opacity: 1; transform: translateY(0) scale(1); max-height: 400px; } }
@keyframes validationSlideOut { from { opacity: 1; transform: translateY(0) scale(1); max-height: 400px; } to { opacity: 0; transform: translateY(-8px) scale(0.98); max-height: 0; } }
@media (max-width: 1200px) {
  .metrics-grid { grid-template-columns: repeat(auto-fit, minmax(var(--grid-min-col), 1fr)); }
  .workspace-layout { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .intent-center { padding: 0.75rem; }
  .ic-header { flex-direction: column; gap: 0.75rem; align-items: flex-start; }
  .header-actions { width: 100%; justify-content: space-between; flex-wrap: wrap; }
  .metrics-grid { grid-template-columns: 1fr; gap: 10px; }
  .metric-card { padding: 14px; }
  .metric-value { font-size: var(--font-size-2xl); }
  .metric-label { font-size: var(--font-size-base); }
  .filter-bar { flex-direction: column; gap: 10px; }
  .filter-left { width: 100%; }
  .search-input { width: 100%; font-size: var(--font-size-base); }
  .search-wrapper { flex: 1; min-width: 0; }
  .intent-input-panel, .intent-history-panel { padding: var(--spacing-md); }
  .panel-title { font-size: var(--font-size-base); margin-bottom: 14px; }
  .intent-textarea { min-height: 120px; padding: 0.75rem; font-size: var(--font-size-base); }
  .submit-btn { padding: 14px 1.25rem; font-size: var(--font-size-base); min-height: 48px; }
  .page-title { font-size: var(--font-size-xl); }
  .page-subtitle { font-size: var(--font-size-base); }
  .copilot-chat-panel { height: 300px; max-height: 300px; }
  .validation-suggestion-chips { gap: 0.375rem; }
  .validation-suggestion-chip { font-size: var(--font-size-xs); padding: var(--spacing-sm) 14px; min-height: var(--button-min-height-touch); }
  .history-item { padding: 0.75rem; min-height: 48px; }
  .history-intent-text { font-size: var(--font-size-base); }
  .history-time { font-size: var(--font-size-base); }
  .action-btn { min-height: var(--button-min-height-touch); padding: var(--spacing-sm) 14px; font-size: var(--font-size-base); }
  .copilot-toggle-btn { min-height: var(--button-min-height-touch); padding: var(--spacing-sm) 14px; }
  .validation-dismiss-btn { width: 44px; height: 44px; }
  .validation-retry-btn { min-height: var(--button-min-height-touch); padding: var(--spacing-sm) var(--spacing-md); }
  .template-card { min-height: var(--button-min-height-touch); padding: 10px 14px; }
  .template-name { font-size: var(--font-size-base); }
  .clear-filter-btn { min-height: var(--button-min-height-touch); }
  .filter-select { min-height: var(--button-min-height-touch); font-size: var(--font-size-base); }
  .search-clear { min-width: 44px; min-height: var(--button-min-height-touch); }
  .diff-content { grid-template-columns: 1fr; gap: var(--spacing-sm); padding: var(--spacing-md); }
  .diff-divider { display: none; }
  .verification-metrics { grid-template-columns: 1fr; }
  .detail-grid { grid-template-columns: 1fr; }
  .modal-content { width: 95%; max-height: 95vh; }
  .modal-header { padding: 14px var(--spacing-md); }
  .modal-actions { padding: 14px var(--spacing-md); }
  .security-actions { flex-direction: column; }
  .security-btn { width: 100%; text-align: center; min-height: var(--button-min-height-touch); }
  .copilot-input-row { flex-wrap: wrap; }
  .copilot-apply-btn { width: 100%; min-height: var(--button-min-height-touch); }
  .copilot-message { font-size: var(--font-size-base); }
  .copilot-input { font-size: var(--font-size-base); }
  .validation-error-title { font-size: var(--font-size-base); }
  .validation-error-message { font-size: var(--font-size-base); }
  .thinking-step-text { font-size: var(--font-size-base); }
  .failure-message { font-size: var(--font-size-base); }
  .failure-hint { font-size: var(--font-size-base); }
  .workspace-layout { grid-template-columns: 1fr; gap: var(--spacing-md); }
  .pagination-btn { min-height: var(--button-min-height-touch); }
  .copilot-send-btn { min-height: var(--button-min-height-touch); }
  .modal-btn { min-height: var(--button-min-height-touch); padding: 0.75rem 1.25rem; }
  .detail-btn { min-height: var(--button-min-height-touch); padding: 0.75rem 1.25rem; }
  .close-btn { width: 44px; height: 44px; }
  .export-dropdown button { min-height: var(--button-min-height-touch); padding: 0.75rem var(--spacing-md); }
  .suggestion-chip { min-height: var(--button-min-height-touch); padding: var(--spacing-sm) 14px; }
  .copilot-suggest-btn { min-height: var(--button-min-height-touch); padding: var(--spacing-sm) 14px; }
  .toolbar-btn { min-height: var(--button-min-height-touch); padding: var(--spacing-sm) 14px; }
  .msg-action-btn { min-width: 44px; min-height: var(--button-min-height-touch); }
  .history-output { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .history-input { overflow-wrap: break-word; word-break: break-word; }
  .structured-output-display { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .diff-code-panel { max-height: 300px; }
  .threat-list { max-height: 180px; }
  .code-block { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .line-content { white-space: pre-wrap; word-break: break-all; }
  .status-badge { font-size: var(--font-size-sm); }
  .history-output pre { font-size: var(--font-size-sm); }
  .msg-text { font-size: var(--font-size-base); }
  .copilot-messages { max-height: 250px; }
  .msg-content { max-width: 90%; }
  .intent-detail-content { padding: var(--spacing-md); }
  .verification-content { padding: var(--spacing-md); }
  .diff-toolbar { flex-wrap: wrap; gap: var(--spacing-sm); }
  .diff-legend { flex-wrap: wrap; }
  .diff-actions-bar { flex-wrap: wrap; }
  .copilot-header-bar { flex-wrap: wrap; gap: var(--spacing-sm); }
  .copilot-status-group { flex-wrap: wrap; }
  .smart-suggestions-bar { max-height: 150px; }
  .threat-level-badge { font-size: var(--font-size-base); }
  .threat-desc { font-size: var(--font-size-base); }
  .threat-info { min-width: 0; }
  .threat-item { overflow-wrap: break-word; }
  .history-actions { flex-wrap: wrap; }
  .action-btn.small { min-height: var(--button-min-height-touch); padding: var(--spacing-sm) 14px; }
  .modal-title { font-size: var(--font-size-md); }
  .thinking-title { font-size: var(--font-size-base); }
  .step-desc { font-size: var(--font-size-base); }
  .log-message { font-size: var(--font-size-base); }
  .validation-error-desc { font-size: var(--font-size-base); }
  .validation-suggestions-label { font-size: var(--font-size-base); }
  .validation-suggestion-chip { font-size: var(--font-size-sm); }
  .validation-error-type-tag { font-size: var(--font-size-xs); }
  .diff-summary-text { font-size: var(--font-size-base); }
  .legend-item { font-size: var(--font-size-sm); }
  .selected-count { font-size: var(--font-size-sm); }
  .timeline-text { font-size: var(--font-size-base); }
  .timeline-time { font-size: var(--font-size-sm); min-width: 70px; }
  .detail-label { font-size: var(--font-size-sm); }
  .detail-value { font-size: var(--font-size-base); }
  .log-time { font-size: var(--font-size-sm); }
  .sg-title { font-size: var(--font-size-base); }
  .sg-desc { font-size: var(--font-size-sm); }
  .status-text { font-size: var(--font-size-sm); }
  .copilot-status { padding: 0.375rem 10px; }
  .msg-timestamp { font-size: var(--font-size-xs); }
  .pagination-info { font-size: var(--font-size-base); }
  .pagination-total { font-size: var(--font-size-sm); }
  .last-refresh { font-size: var(--font-size-sm); }
  .data-freshness { font-size: var(--font-size-sm); padding: 0.375rem 0.75rem; }
  .intent-input-display { font-size: var(--font-size-base); padding: 14px; }
  .structured-output-display pre { font-size: var(--font-size-sm); }
  .diff-title { font-size: var(--font-size-base); }
  .diff-line .line-marker { font-size: var(--font-size-sm); }
  .diff-line .line-content { font-size: var(--font-size-sm); }
  .line-number { font-size: var(--font-size-sm); }
  .verification-intent { font-size: var(--font-size-base); padding: 10px 14px; }
  .verification-metrics .metric-value { font-size: var(--font-size-xl); }
  .verification-metrics .metric-label { font-size: var(--font-size-sm); }
  .timeline-title { font-size: var(--font-size-base); }
  .security-message { font-size: var(--font-size-base); }
  .threat-type { font-size: var(--font-size-xs); }
  .threat-level-tag { font-size: 0.6875rem; }
  .export-dropdown button { font-size: var(--font-size-sm); }
  .autocomplete-item { font-size: var(--font-size-base); min-height: var(--button-min-height-touch); }
}
@media (max-width: 480px) {
  .metrics-grid { gap: var(--spacing-sm); }
  .metric-card { padding: 0.75rem; gap: 10px; }
  .metric-icon { width: 36px; height: 36px; font-size: var(--font-size-lg); }
  .metric-value { font-size: var(--font-size-xl); }
  .metric-label { font-size: var(--font-size-sm); }
  .filter-left { gap: 0.375rem; }
  .filter-select { font-size: var(--font-size-md); padding: var(--spacing-sm) 10px; }
  .action-btn { padding: var(--spacing-sm) 10px; font-size: var(--font-size-sm); min-height: var(--button-min-height-touch); }
  .template-name { font-size: var(--font-size-sm); }
  .validation-error-panel { margin-top: 0.75rem; }
  .validation-error-header { padding: 10px 14px; }
  .validation-error-body { padding: 0.75rem 14px; }
  .validation-error-footer { padding: var(--spacing-sm) 14px; }
  .page-title { font-size: var(--font-size-lg); }
  .intent-textarea { min-height: 100px; font-size: var(--font-size-md); }
  .copilot-chat-panel { height: 250px; max-height: 250px; }
  .intent-input-panel, .intent-history-panel { padding: 0.75rem; }
  .history-item { padding: 10px; }
  .search-input { font-size: var(--font-size-md); }
  .copilot-input { font-size: var(--font-size-md); }
  .intent-center { padding: var(--spacing-sm); }
  .ic-header { margin-bottom: var(--spacing-md); padding-bottom: 0.75rem; }
  .panel-title { font-size: 0.9375rem; margin-bottom: 0.75rem; }
  .history-list { gap: 10px; }
  .submit-btn { padding: 0.75rem var(--spacing-md); }
  .copilot-messages { padding: 10px; }
  .copilot-input-row { padding: 10px 0.75rem; gap: 0.375rem; }
  .modal-header { padding: 0.75rem 14px; }
  .modal-actions { padding: 0.75rem 14px; }
  .modal-content { width: 98%; max-height: 98vh; border-radius: var(--radius-lg); }
  .diff-content { padding: 0.75rem; }
  .verification-content { padding: 0.75rem; }
  .intent-detail-content { padding: 0.75rem; }
  .thinking-panel { padding: 14px; margin-top: 14px; }
  .empty-state { padding: 40px var(--spacing-md); }
  .pagination { gap: 10px; margin-top: 14px; padding-top: 14px; }
  .page-subtitle { font-size: var(--font-size-sm); }
  .msg-text { font-size: var(--font-size-sm); }
  .status-badge { font-size: var(--font-size-xs); padding: var(--spacing-xs) 10px; }
  .history-time { font-size: var(--font-size-xs); }
  .threat-level-badge { font-size: var(--font-size-sm); padding: var(--spacing-sm) 10px; }
  .security-actions { gap: var(--spacing-sm); }
  .security-btn { padding: 10px var(--spacing-md); font-size: var(--font-size-base); }
  .metric-card { padding: 10px; gap: var(--spacing-sm); }
  .filter-bar { padding: var(--spacing-sm) 10px; gap: var(--spacing-sm); }
  .copilot-chat-panel { border-radius: var(--radius-md); }
  .validation-suggestion-chip { font-size: var(--font-size-xs); padding: 0.375rem 0.75rem; }
  .modal-title { font-size: 0.9375rem; }
  .thinking-panel { border-radius: var(--radius-lg); }
  .intent-input-panel, .intent-history-panel { border-radius: var(--radius-lg); }
  .metric-card { border-radius: var(--radius-md); }
  .history-item { border-radius: var(--radius-md); }
  .copilot-msg { gap: var(--spacing-sm); margin-bottom: 10px; }
  .msg-avatar { width: 28px; height: 28px; font-size: var(--font-size-base); }
  .msg-content { max-width: 85%; }
  .diff-code-panel { max-height: 250px; }
  .verification-chart { height: 220px; }
  .threat-list { max-height: 150px; }
  .smart-suggestions-bar { max-height: 120px; padding: var(--spacing-sm) 0.75rem; }
  .smart-suggestion-card { padding: var(--spacing-sm) 10px; }
  .sg-icon { font-size: var(--font-size-md); }
  .sg-title { font-size: var(--font-size-xs); }
  .sg-desc { font-size: 0.6875rem; }
  .msg-suggestions { gap: var(--spacing-xs); }
  .suggestion-chip { font-size: 0.6875rem; padding: var(--spacing-xs) var(--spacing-sm); }
  .copilot-header-bar { padding: var(--spacing-sm) 0.75rem; }
  .copilot-status-group { gap: var(--spacing-sm); }
  .step-dot { width: 10px; height: 10px; }
  .thinking-step { padding: var(--spacing-sm) 10px; gap: 10px; }
  .timeline-item { padding: var(--spacing-sm) 10px; gap: var(--spacing-sm); }
  .timeline-dot { width: 8px; height: 8px; }
  .detail-section { margin-bottom: var(--spacing-md); }
  .log-item { padding: 10px; }
  .validation-error-desc { font-size: var(--font-size-sm); }
  .validation-suggestions { padding: 10px; }
  .validation-suggestions-label { font-size: var(--font-size-xs); }
  .validation-suggestion-chips { gap: 0.375rem; }
  .threat-item { padding: var(--spacing-sm) 10px; gap: var(--spacing-sm); }
  .threat-desc { font-size: var(--font-size-xs); }
  .threat-type { font-size: 0.625rem; }
  .threat-level-dot { width: 6px; height: 6px; }
  .threat-level-tag { font-size: var(--font-size-xs); padding: 1px 5px; }
  .empty-icon { font-size: var(--font-size-3xl); margin-bottom: 0.75rem; }
  .empty-state p { font-size: var(--font-size-sm); }
  .last-refresh { font-size: 0.6875rem; }
  .data-freshness { font-size: 0.6875rem; padding: var(--spacing-xs) var(--spacing-sm); }
  .export-dropdown { min-width: 120px; }
}
@media (prefers-reduced-motion: reduce) {
  .intent-center, .metric-card, .copilot-chat-panel, .export-dropdown, .suggestion-chip, .smart-suggestion-card, .thinking-step.current, .bg-glow, .page-title, .thinking-panel::before, .timeline-item.current, .status-dot.online, .copilot-status:has(.status-dot.online), .deepseek-badge, .freshness-dot, .streaming-cursor .cursor-blink, .thinking-dots .dot, .refresh-icon.spinning, .modal-overlay, .skeleton, .skeleton-line, .typing-text, .step-dot.active, .validation-error-panel, .thinking-panel.failed, .reasoning-failure-overlay, .failure-icon-ring, .failure-x-mark, .validation-slide-enter-active, .validation-slide-leave-active, .thinking-panel, .metric-card::before, .metric-icon, .history-item, .bg-grid, .streaming-indicator, .thinking-step.current .step-dot.active, .copilot-status:has(.status-dot.online), .failure-icon-ring, .code-block, .msg-actions { animation: none !important; }
  .metric-card, .history-item, .action-btn, .submit-btn, .modal-btn, .detail-btn, .copilot-toggle-btn, .suggestion-chip, .smart-suggestion-card, .copilot-send-btn, .copilot-apply-btn, .copilot-suggest-btn, .toolbar-btn, .close-btn, .pagination-btn, .clear-filter-btn, .search-input, .filter-select, .intent-textarea, .validation-suggestion-chip, .validation-retry-btn, .validation-dismiss-btn, .msg-action-btn, .export-dropdown button, .security-btn, .copilot-input, .data-freshness, .status-badge, .thinking-step, .step-dot, .msg-actions, .refresh-icon, .metric-card::before, .metric-icon, .history-item, .action-btn.small, .copilot-chat-panel, .smart-suggestion-card, .sg-arrow, .msg-text, .code-block, .diff-line, .validation-error-panel, .threat-item, .threat-level-badge, .timeline-item, .log-item, .detail-btn, .modal-btn.confirm, .autocomplete-item { transition: none !important; }
  .metric-card:hover, .history-item:hover, .submit-btn:hover:not(:disabled), .modal-btn.confirm:hover, .detail-btn:hover, .copilot-toggle-btn:hover, .suggestion-chip:hover, .smart-suggestion-card:hover, .action-btn:hover:not(:disabled), .export-dropdown button:hover, .validation-suggestion-chip:hover, .detail-btn.approve:hover, .detail-btn.reject:hover, .copilot-send-btn:hover, .copilot-apply-btn:hover, .copilot-suggest-btn:hover, .action-btn.small:hover, .action-btn.small.success:hover, .toolbar-btn:hover, .close-btn:hover, .pagination-btn:hover:not(:disabled), .clear-filter-btn:hover, .security-btn.cancel:hover, .security-btn.override:hover, .validation-retry-btn:hover, .validation-dismiss-btn:hover, .msg-action-btn:hover, .autocomplete-item:hover, .smart-suggestion-card:hover, .suggestion-chip:hover, .metric-card:hover .metric-icon { transform: none !important; }
  .metric-card:hover { box-shadow: none !important; }
  .submit-btn:hover:not(:disabled) { box-shadow: none !important; }
  .detail-btn.approve:hover { box-shadow: none !important; }
  .modal-btn.confirm:hover { box-shadow: none !important; }
}

.ic-tabs { position: relative; z-index: var(--z-content); }
.ic-tabs :deep(.el-tabs__header) { margin-bottom: var(--spacing-lg); }
.ic-tabs :deep(.el-tabs__nav-wrap::after) { background-color: rgba(255, 255, 255, 0.06); }
.ic-tabs :deep(.el-tabs__item) { color: var(--color-text-tertiary); font-size: var(--font-size-base); font-weight: 500; }
.ic-tabs :deep(.el-tabs__item.is-active) { color: var(--color-primary-light); font-weight: 600; }
.ic-tabs :deep(.el-tabs__item:hover) { color: var(--color-primary-light); }
.ic-tabs :deep(.el-tabs__active-bar) { background-color: var(--color-primary); }

.fi-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-lg); padding-bottom: var(--spacing-md); border-bottom: 1px solid var(--color-border-primary); }
.fi-header-left { display: flex; flex-direction: column; gap: var(--spacing-xs); }
.fi-page-title { font-size: var(--font-size-xl); font-weight: 700; margin: 0; color: var(--color-text-secondary); }
.fi-page-subtitle { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin: 0; font-weight: 400; }
.fi-header-actions { display: flex; align-items: center; gap: 0.75rem; }
.fi-export-btn { background: rgba(250, 173, 20, 0.1) !important; color: var(--color-warning-light) !important; border: 1px solid rgba(250, 173, 20, 0.25) !important; border-radius: var(--radius-lg) !important; backdrop-filter: blur(8px) !important; transition: all 0.25s ease !important; box-shadow: 0 0 6px rgba(250, 173, 20, 0.06) !important; }
.fi-export-btn:hover:not(:disabled) { background: rgba(250, 173, 20, 0.2) !important; border-color: rgba(250, 173, 20, 0.5) !important; box-shadow: 0 0 12px rgba(250, 173, 20, 0.15), 0 2px 8px rgba(250, 173, 20, 0.08) !important; transform: scale(1.02) !important; color: #FFD666 !important; }
.fi-export-btn:active:not(:disabled) { transform: scale(0.97) !important; }
.fi-export-btn:disabled { opacity: 0.35 !important; cursor: not-allowed !important; transform: none !important; box-shadow: none !important; }

.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(var(--grid-min-col), 1fr)); gap: var(--panel-gap); margin-bottom: var(--panel-gap); }
.stat-card { background: var(--gradient-glass); border-radius: var(--card-border-radius); padding: 1.25rem; display: flex; flex-direction: column; gap: 0.75rem; border: var(--card-border); transition: all 0.35s var(--ease-out); position: relative; overflow: hidden; backdrop-filter: blur(12px); animation: card-enter 0.4s var(--ease-out) backwards; animation-delay: var(--delay, 0s); will-change: transform, opacity; }
.stat-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--accent), transparent); opacity: 0; transition: opacity 0.35s ease; }
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 0 20px rgba(22, 93, 255, 0.12), 0 4px 16px rgba(22, 93, 255, 0.06), var(--shadow-card-hover); border-color: rgba(22, 93, 255, 0.35); }
.stat-card:hover::before { opacity: 1; }
.stat-top-row { display: flex; justify-content: space-between; align-items: center; }
.stat-icon { width: 3rem; height: 3rem; border-radius: var(--radius-lg); display: flex; align-items: center; justify-content: center; font-size: var(--font-size-2xl); transition: all 0.3s ease; }
.stat-card:hover .stat-icon { transform: scale(1.08); }
.stat-content { flex: 1; }
.stat-value { font-size: var(--font-size-3xl); font-weight: 700; color: var(--color-text-primary); line-height: 1.2; font-variant-numeric: tabular-nums; letter-spacing: -0.5px; }
.stat-unit { font-size: var(--font-size-base); font-weight: 400; color: var(--color-text-tertiary); margin-left: var(--spacing-xs); letter-spacing: 0; }
.stat-label { font-size: var(--font-size-base); color: var(--color-text-tertiary); margin-top: var(--spacing-xs); }

.fi-panel { background: var(--gradient-glass); border-radius: var(--radius-lg); padding: 1.25rem; border: var(--card-border); backdrop-filter: blur(12px); animation: panel-enter 0.5s var(--ease-out) backwards; }
.fi-panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-md); flex-wrap: wrap; gap: var(--spacing-sm); }
.fi-panel-title { font-size: var(--font-size-md); font-weight: 600; color: var(--color-text-primary); margin-bottom: var(--spacing-md); padding-left: 0.625rem; border-left: 3px solid var(--color-primary); }
.fi-panel-header .fi-panel-title { margin-bottom: 0; }
.fi-filter-group { display: flex; gap: var(--spacing-lg); flex-wrap: wrap; }
.fi-filter-section { display: flex; align-items: center; gap: var(--spacing-xs); }
.fi-filter-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); white-space: nowrap; }
.fi-filter-btn { padding: var(--spacing-xs) 0.625rem; min-height: 44px; background: rgba(22, 93, 255, 0.08); border: 1px solid rgba(22, 93, 255, 0.2); border-radius: var(--radius-sm); color: var(--color-text-tertiary); font-size: var(--font-size-xs); cursor: pointer; transition: all 0.25s ease; backdrop-filter: blur(8px); }
.fi-filter-btn:hover { background: rgba(22, 93, 255, 0.15); color: var(--color-primary-light); border-color: rgba(22, 93, 255, 0.35); box-shadow: 0 0 6px rgba(22, 93, 255, 0.08); }
.fi-filter-btn.active { background: rgba(22, 93, 255, 0.2); color: var(--color-primary-light); border-color: rgba(22, 93, 255, 0.4); box-shadow: 0 0 10px rgba(22, 93, 255, 0.15); }

.fi-table-wrapper { overflow-x: auto; }
.fi-data-table { width: 100%; border-collapse: collapse; font-size: var(--font-size-sm); }
.fi-data-table th { text-align: left; padding: 0.75rem; color: var(--color-text-tertiary); font-weight: 500; border-bottom: 1px solid var(--color-border-primary); white-space: nowrap; }
.fi-data-table td { padding: 0.75rem; color: var(--color-text-secondary); border-bottom: 1px solid var(--color-border-primary); }
.fi-data-table tbody tr { transition: background 0.2s var(--ease-out); }
.fi-data-table tbody tr:hover { background: var(--color-bg-hover); }
.fi-mono { font-family: 'SF Mono', 'Cascadia Code', monospace; font-variant-numeric: tabular-nums; }
.fi-method-tag { display: inline-block; padding: 0.125rem 0.5rem; background: var(--color-primary-bg); color: var(--color-primary-light); border-radius: var(--radius-xs); font-size: var(--font-size-xs); }
.fi-status-tag { display: inline-block; padding: 0.1875rem 0.625rem; border-radius: var(--radius-sm); font-size: var(--font-size-xs); font-weight: 500; border: 1px solid; }
.fi-status-tag.resolved { color: var(--color-success); background: var(--color-success-bg); border-color: var(--color-success-border); }
.fi-status-tag.unresolved { color: var(--color-warning); background: var(--color-warning-bg); border-color: var(--color-warning-border); }
.fi-action-cell { display: flex; gap: 0.375rem; }
.fi-table-action-btn { padding: 0.25rem 0.5rem; background: rgba(22, 93, 255, 0.1); color: var(--color-primary-light); border: 1px solid rgba(22, 93, 255, 0.2); border-radius: var(--radius-xs); font-size: var(--font-size-xs); cursor: pointer; transition: all 0.25s ease; white-space: nowrap; backdrop-filter: blur(8px); }
.fi-table-action-btn:hover { background: rgba(22, 93, 255, 0.2); border-color: rgba(22, 93, 255, 0.35); box-shadow: 0 0 6px rgba(22, 93, 255, 0.1); transform: scale(1.02); }
.fi-table-action-btn.resolve { background: rgba(82, 196, 26, 0.1); color: var(--color-success-light); border-color: rgba(82, 196, 26, 0.2); }
.fi-table-action-btn.resolve:hover { background: rgba(82, 196, 26, 0.2); border-color: rgba(82, 196, 26, 0.35); box-shadow: 0 0 6px rgba(82, 196, 26, 0.1); }
.fi-table-action-btn.danger { background: var(--color-error-bg); color: var(--color-error-light); border-color: var(--color-error-border); }
.fi-table-action-btn.danger:hover { background: var(--color-error-hover); border-color: rgba(255, 77, 79, 0.35); }
.fi-empty-state { text-align: center; padding: var(--spacing-xl) var(--spacing-lg); color: var(--color-text-tertiary); font-size: var(--font-size-base); }

.fi-pagination { display: flex; align-items: center; justify-content: center; gap: var(--spacing-md); margin-top: var(--spacing-lg); padding-top: var(--spacing-md); border-top: 1px solid var(--color-border-primary); }
.fi-page-btn { padding: 0.375rem 0.875rem; background: rgba(22, 93, 255, 0.1); color: var(--color-primary-light); border: 1px solid rgba(22, 93, 255, 0.2); border-radius: var(--radius-md); font-size: var(--font-size-xs); cursor: pointer; transition: all 0.25s ease; min-height: 44px; backdrop-filter: blur(8px); }
.fi-page-btn:hover:not(:disabled) { background: rgba(22, 93, 255, 0.2); border-color: rgba(22, 93, 255, 0.4); box-shadow: 0 0 8px rgba(22, 93, 255, 0.1); transform: scale(1.02); }
.fi-page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.fi-page-info { font-size: var(--font-size-sm); color: var(--color-text-tertiary); font-variant-numeric: tabular-nums; }

.fi-dialog-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: var(--modal-overlay-bg); backdrop-filter: blur(var(--modal-backdrop-blur)); -webkit-backdrop-filter: blur(var(--modal-backdrop-blur)); display: flex; align-items: center; justify-content: center; z-index: var(--z-modal); animation: overlay-enter 0.2s var(--ease-out); }
@keyframes overlay-enter { from { opacity: 0; } to { opacity: 1; } }
.fi-dialog { background: var(--color-bg-elevated); border: 1px solid var(--color-border-secondary); border-radius: var(--modal-border-radius); width: 90%; max-width: 40rem; max-height: 80vh; overflow-y: auto; animation: dialog-enter 0.25s var(--ease-out); box-shadow: var(--modal-shadow); }
@keyframes dialog-enter { from { opacity: 0; transform: translateY(16px) scale(0.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
.fi-dialog-header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--color-border-primary); }
.fi-dialog-title { font-size: var(--font-size-lg); font-weight: 600; color: var(--color-text-primary); margin: 0; }
.fi-dialog-close { background: none; border: none; color: var(--color-text-tertiary); font-size: var(--font-size-lg); cursor: pointer; padding: 0.25rem; transition: color 0.2s var(--ease-out); line-height: 1; }
.fi-dialog-close:hover { color: var(--color-text-secondary); }
.fi-dialog-body { padding: 1.5rem; }
.fi-dialog-footer { display: flex; justify-content: flex-end; gap: var(--spacing-sm); padding: 1rem 1.5rem; border-top: 1px solid var(--color-border-primary); }

.fi-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-md); }
.fi-detail-item { display: flex; flex-direction: column; gap: 0.25rem; }
.fi-detail-item.full-width { grid-column: 1 / -1; }
.fi-detail-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); font-weight: 500; }
.fi-detail-value { font-size: var(--font-size-sm); color: var(--color-text-secondary); word-break: break-word; }
.fi-detail-value.failure-reason { color: var(--color-error-light); }

.fi-form-group { margin-bottom: var(--spacing-md); }
.fi-form-label { display: block; font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-bottom: 0.375rem; font-weight: 500; }
.fi-form-textarea { width: 100%; padding: 0.75rem; background: var(--input-bg); border: 1px solid var(--input-border); border-radius: var(--input-radius); color: var(--color-text-secondary); font-size: var(--font-size-sm); font-family: inherit; resize: vertical; transition: border-color 0.2s var(--ease-out); box-sizing: border-box; }
.fi-form-textarea:focus { outline: none; border-color: var(--input-border-focus); box-shadow: var(--input-shadow-focus); }
.fi-form-textarea::placeholder { color: var(--color-text-disabled); }

@media (max-width: 768px) {
  .fi-header { flex-direction: column; gap: 0.75rem; align-items: flex-start; }
  .fi-header-actions { flex-wrap: wrap; }
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .stat-value { font-size: var(--font-size-2xl); }
  .fi-filter-group { flex-direction: column; gap: var(--spacing-sm); }
  .fi-detail-grid { grid-template-columns: 1fr; }
}
@media (max-width: 480px) {
  .stats-grid { grid-template-columns: 1fr; }
  .stat-value { font-size: var(--font-size-xl); }
}
</style>