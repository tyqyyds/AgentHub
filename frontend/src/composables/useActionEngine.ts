import { nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useAssistantStore, type AssistantAction } from '@/stores/assistant'
import { useWebSocket } from '@/composables/useWebSocket'
import { useLogger } from '@/utils/logger'

const { info: logInfo, warn: logWarn } = useLogger()

let wsOffFn: (() => void) | null = null
let currentExecuteAction: ((action: AssistantAction) => Promise<void>) | null = null

function ensureWsListener(ws: ReturnType<typeof useWebSocket>) {
  if (wsOffFn) { wsOffFn(); wsOffFn = null }

  wsOffFn = ws.on('assistant_action', (msg) => {
    const data = msg.data || {}
    const action = data.action as AssistantAction | undefined
    if (action && currentExecuteAction) {
      currentExecuteAction(action)
    }
  })
}

export function useActionEngine() {
  const router = useRouter()
  const store = useAssistantStore()
  const ws = useWebSocket()

  const executeAction = async (action: AssistantAction) => {
    logInfo('执行助手动作', { type: action.type, label: action.label })

    switch (action.type) {
      case 'navigate': {
        const route = action.params.route as string
        if (route) {
          await router.push(route)
          store.addMessage({
            role: 'system',
            content: `已导航到 ${action.label}`,
            status: 'sent'
          })
        }
        break
      }
      case 'fill_form': {
        const route = action.params.route as string
        const field = action.params.field as string
        const value = action.params.value as string
        if (route && router.currentRoute.value.path !== route) {
          await router.push(route)
          await nextTick()
        }
        window.dispatchEvent(new CustomEvent('assistant:fill_form', { detail: { field, value } }))
        store.addMessage({
          role: 'system',
          content: `已为您填入表单：${action.label}`,
          status: 'sent'
        })
        break
      }
      case 'highlight': {
        const entityType = action.params.entityType as string
        const entityId = action.params.entityId as string
        window.dispatchEvent(new CustomEvent('assistant:highlight', { detail: { entityType, entityId } }))
        store.addMessage({
          role: 'system',
          content: `已高亮显示：${action.label}`,
          status: 'sent'
        })
        break
      }
      case 'execute': {
        const command = action.params.command as string
        window.dispatchEvent(new CustomEvent('assistant:execute', { detail: { command, params: action.params } }))
        store.addMessage({
          role: 'system',
          content: `⏳ 正在执行：${action.label}...`,
          status: 'sent'
        })
        break
      }
      case 'query': {
        const query = action.params.query as string
        if (query) {
          await store.sendMessage(`查询：${query}`)
        }
        break
      }
      case 'qos_config':
      case 'acl_config':
      case 'link_config':
      case 'traffic_config': {
        window.dispatchEvent(new CustomEvent('assistant:config_action', { detail: { type: action.type, params: action.params } }))
        store.addMessage({
          role: 'system',
          content: `📋 配置动作：${action.label || action.type}`,
          status: 'sent'
        })
        break
      }
      case 'diagnose': {
        window.dispatchEvent(new CustomEvent('assistant:diagnose', { detail: { params: action.params } }))
        store.addMessage({
          role: 'system',
          content: `🔍 诊断动作：${action.label || action.type}`,
          status: 'sent'
        })
        break
      }
      case 'monitor': {
        window.dispatchEvent(new CustomEvent('assistant:monitor', { detail: { params: action.params } }))
        store.addMessage({
          role: 'system',
          content: `📊 监控动作：${action.label || action.type}`,
          status: 'sent'
        })
        break
      }
      default:
        logWarn('未知的助手动作类型', { type: action.type })
    }
  }

  currentExecuteAction = executeAction
  ensureWsListener(ws)

  return { executeAction }
}

export function cleanupActionEngineWs() {
  if (wsOffFn) { wsOffFn(); wsOffFn = null }
  currentExecuteAction = null
}
