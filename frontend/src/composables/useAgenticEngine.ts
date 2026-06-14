import { useRouter } from 'vue-router'
import { useAssistantStore, type WorkflowStep } from '@/stores/assistant'

interface AgenticAction {
  type: 'navigate' | 'highlight' | 'execute' | 'query' | 'render_chart' | 'confirm_approval' | 'frontend_action'
  action?: string
  params: Record<string, any>
  label?: string
}

interface ReActStepUI {
  stepNumber: number
  thought: string
  action: string | null
  actionInput: Record<string, any> | null
  observation: string | null
  status: 'thinking' | 'acting' | 'observing' | 'completed' | 'failed' | 'waiting_approval'
}

const reactStatusMap: Record<ReActStepUI['status'], WorkflowStep['status']> = {
  thinking: 'running',
  acting: 'running',
  observing: 'running',
  completed: 'completed',
  failed: 'failed',
  waiting_approval: 'waiting_confirm'
}

export function useAgenticEngine() {
  const router = useRouter()
  const store = useAssistantStore()

  const executeAgenticAction = (action: AgenticAction) => {
    switch (action.type) {
      case 'navigate': {
        const route = action.params.route
        if (route) {
          router.push(route)
        }
        break
      }
      case 'highlight': {
        window.dispatchEvent(new CustomEvent('topology:highlight', { detail: { nodeId: action.params.node_id } }))
        break
      }
      case 'execute': {
        window.dispatchEvent(new CustomEvent('assistant:execute', { detail: action.params }))
        break
      }
      case 'query': {
        const query = action.params.query
        if (query) {
          store.sendMessage(query)
        }
        break
      }
      case 'render_chart': {
        window.dispatchEvent(new CustomEvent('assistant:render_chart', { detail: action.params }))
        break
      }
      case 'confirm_approval': {
        store.pendingConfirmId = action.params.confirm_id || action.params.confirmId || null
        store.openChat()
        break
      }
      case 'frontend_action': {
        if (action.action) {
          window.dispatchEvent(new CustomEvent(action.action, { detail: action.params }))
        }
        break
      }
    }
  }

  const processReActSteps = (steps: ReActStepUI[]): WorkflowStep[] => {
    return steps.map((step) => ({
      id: `react_step_${step.stepNumber}`,
      agent: step.action ? `Tool: ${step.action}` : 'Agent',
      status: reactStatusMap[step.status],
      title: step.thought,
      detail: step.observation || undefined,
      timestamp: new Date().toISOString()
    }))
  }

  const handleReActResult = (result: any): string => {
    if (result.frontend_actions && Array.isArray(result.frontend_actions)) {
      for (const action of result.frontend_actions) {
        executeAgenticAction(action as AgenticAction)
      }
    }

    if (result.steps && Array.isArray(result.steps)) {
      const workflow = processReActSteps(result.steps as ReActStepUI[])
      store.setWorkflow(workflow)
    }

    if (result.requires_approval) {
      store.pendingConfirmId = result.confirm_id || result.confirmId || `approval_${Date.now()}`
      store.openChat()
    }

    return result.answer || result.content || result.final_answer || ''
  }

  return {
    executeAgenticAction,
    processReActSteps,
    handleReActResult
  }
}
