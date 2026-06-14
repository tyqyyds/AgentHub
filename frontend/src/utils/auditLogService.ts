import { authFetch } from '@/utils/apiClient'

const API_BASE = '/api/v1/audit-logs'

export interface AuditLog {
  id: string
  user: string
  action: string
  actionLabel: string
  targetDevice: string
  commands: string[]
  timestamp: string
  status: 'success' | 'pending' | 'failed' | 'running'
  approvalId?: string
  ip?: string
  result?: string
  details?: string
  securityLevel?: 'info' | 'warning' | 'critical'
  context: {
    intentId?: string
    intentText: string
    prompt?: string
    modelResponse?: string
    tokens?: {
      prompt: number
      completion: number
      total: number
    }
    latency_ms?: number
    model?: string
  }
}

interface BackendAuditLog {
  id: number
  user_id: string
  action: string
  target_device: string | null
  commands: string[] | null
  timestamp: string | null
  approval_id: string | null
  status: string | null
  security_type: string | null
  prompt_tokens: number | null
  completion_tokens: number | null
  latency_ms: number | null
  raw_prompt: string | null
  raw_response: string | null
}

const ACTION_LABELS: Record<string, string> = {
  create_intent: '提交意图',
  approve_intent: '审批意图',
  approve_intent_with_conflict_check: '审批意图(冲突检查)',
  reject_intent: '拒绝意图',
  execute_intent: '执行意图',
  rollback_intent: '回滚意图',
  config_deploy: '配置下发',
  config_rollback: '配置回滚',
  self_healing: '自愈执行',
  security_alert: '安全告警',
  lock_resource: '锁定资源',
  unlock_resource: '解锁资源',
  commit_config: '提交配置',
  create_event: '创建事件',
  resolve_event: '解决事件',
  escalate_event: '升级事件',
  auto_heal_event: '自动修复',
}

function mapActionLabel(action: string): string {
  return ACTION_LABELS[action] || action
}

function mapSecurityLevel(securityType: string | null): 'info' | 'warning' | 'critical' {
  if (securityType === 'critical') return 'critical'
  if (securityType === 'warning') return 'warning'
  return 'info'
}

function mapStatus(status: string | null): 'success' | 'pending' | 'failed' | 'running' {
  if (status === 'success') return 'success'
  if (status === 'pending') return 'pending'
  if (status === 'failed') return 'failed'
  if (status === 'running') return 'running'
  return 'success'
}

function backendToFrontend(log: BackendAuditLog): AuditLog {
  return {
    id: `AL-${log.id}`,
    user: log.user_id,
    action: log.action,
    actionLabel: mapActionLabel(log.action),
    targetDevice: log.target_device || '系统',
    commands: log.commands || [],
    timestamp: log.timestamp || new Date().toISOString().replace('T', ' ').slice(0, 19),
    status: mapStatus(log.status),
    approvalId: log.approval_id || undefined,
    securityLevel: mapSecurityLevel(log.security_type),
    context: {
      intentText: log.raw_prompt || log.action,
      prompt: log.raw_prompt || undefined,
      modelResponse: log.raw_response || undefined,
      tokens: log.prompt_tokens != null && log.completion_tokens != null
        ? { prompt: log.prompt_tokens, completion: log.completion_tokens, total: log.prompt_tokens + log.completion_tokens }
        : undefined,
      latency_ms: log.latency_ms ?? undefined,
    }
  }
}

class AuditLogService {
  async loadLogs(signal?: AbortSignal): Promise<AuditLog[]> {
    try {
      const resp = await authFetch(`${API_BASE}?limit=100`, { signal })
      if (resp.ok) {
        const data = await resp.json()
        return (data.data || []).map(backendToFrontend)
      }
    } catch {
      // fallback to empty
    }
    return []
  }

  async addLog(log: Omit<AuditLog, 'id' | 'timestamp'>, _signal?: AbortSignal): Promise<AuditLog> {
    // Audit logs are created by backend automatically during CRUD operations
    // This method creates a frontend-only entry for UI actions not covered by backend
    const newLog: AuditLog = {
      ...log,
      id: `AL-FE-${Date.now().toString(36)}`,
      timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19)
    }
    return newLog
  }

  async recordIntentSubmission(
    user: string,
    intentText: string,
    targetDevice: string,
    commands: string[],
    status: 'success' | 'pending' | 'failed' | 'running',
    approvalId?: string,
    context?: Partial<AuditLog['context']>
  ): Promise<AuditLog> {
    return this.addLog({
      user,
      action: 'intent_submit',
      actionLabel: '提交意图',
      targetDevice,
      commands,
      status,
      approvalId,
      context: {
        intentText,
        ...context
      }
    })
  }

  async recordConfigDeployment(
    user: string,
    intentText: string,
    targetDevice: string,
    commands: string[],
    status: 'success' | 'pending' | 'failed' | 'running',
    approvalId?: string,
    context?: Partial<AuditLog['context']>
  ): Promise<AuditLog> {
    return this.addLog({
      user,
      action: 'config_deploy',
      actionLabel: '配置下发',
      targetDevice,
      commands,
      status,
      approvalId,
      context: {
        intentText,
        ...context
      }
    })
  }

  async recordSelfHealing(
    user: string,
    intentText: string,
    targetDevice: string,
    commands: string[],
    status: 'success' | 'pending' | 'failed' | 'running',
    context?: Partial<AuditLog['context']>
  ): Promise<AuditLog> {
    return this.addLog({
      user,
      action: 'self_healing',
      actionLabel: '自愈执行',
      targetDevice,
      commands,
      status,
      context: {
        intentText,
        ...context
      }
    })
  }

  async recordConfigRollback(
    user: string,
    intentText: string,
    targetDevice: string,
    commands: string[],
    status: 'success' | 'pending' | 'failed' | 'running',
    context?: Partial<AuditLog['context']>
  ): Promise<AuditLog> {
    return this.addLog({
      user,
      action: 'config_rollback',
      actionLabel: '配置回滚',
      targetDevice,
      commands,
      status,
      context: {
        intentText,
        ...context
      }
    })
  }

  async recordSecurityAlert(
    user: string,
    intentText: string,
    threatLevel: string,
    threatDescriptions: string,
    context?: Partial<AuditLog['context']>
  ): Promise<AuditLog> {
    return this.addLog({
      user,
      action: 'security_alert',
      actionLabel: '安全告警',
      targetDevice: '系统',
      commands: [],
      status: 'failed',
      securityLevel: threatLevel === 'critical' ? 'critical' : threatLevel === 'high' ? 'critical' : 'warning',
      result: `安全扫描拦截: ${threatDescriptions}`,
      details: `威胁等级: ${threatLevel}`,
      context: {
        intentText,
        ...context
      }
    })
  }

  async getLogsPaginated(page: number = 1, limit: number = 20, filters?: {
    user?: string
    action?: string
    status?: string
    securityLevel?: string
    startDate?: string
    endDate?: string
  }, signal?: AbortSignal): Promise<{ data: AuditLog[]; total: number; page: number; limit: number }> {
    try {
      const params = new URLSearchParams({ page: String(page), limit: String(limit) })
      if (filters?.user) params.set('user', filters.user)
      if (filters?.action) params.set('action', filters.action)
      if (filters?.status) params.set('status', filters.status)
      if (filters?.securityLevel) params.set('security_type', filters.securityLevel)
      if (filters?.startDate) params.set('start_date', filters.startDate)
      if (filters?.endDate) params.set('end_date', filters.endDate)

      const resp = await authFetch(`${API_BASE}?${params.toString()}`, { signal })
      if (resp.ok) {
        const data = await resp.json()
        return {
          data: (data.data || []).map(backendToFrontend),
          total: data.total || 0,
          page: data.page || page,
          limit: data.limit || limit
        }
      }
    } catch {
      // fallback
    }
    return { data: [], total: 0, page, limit }
  }

  async getLogCount(filters?: {
    user?: string
    action?: string
    status?: string
    securityLevel?: string
  }, signal?: AbortSignal): Promise<number> {
    try {
      const params = new URLSearchParams({ page: '1', limit: '1' })
      if (filters?.user) params.set('user', filters.user)
      if (filters?.action) params.set('action', filters.action)
      if (filters?.status) params.set('status', filters.status)
      if (filters?.securityLevel) params.set('security_type', filters.securityLevel)

      const resp = await authFetch(`${API_BASE}?${params.toString()}`, { signal })
      if (resp.ok) {
        const data = await resp.json()
        return data.total || 0
      }
    } catch {
      // fallback
    }
    return 0
  }

  async searchLogs(query: string, action?: string, status?: string, signal?: AbortSignal): Promise<AuditLog[]> {
    const result = await this.getLogsPaginated(1, 100, { action, status }, signal)
    if (!query) return result.data
    const q = query.toLowerCase()
    return result.data.filter(log =>
      log.context.intentText.toLowerCase().includes(q) ||
      log.user.toLowerCase().includes(q) ||
      log.targetDevice.toLowerCase().includes(q)
    )
  }

  async getStats(signal?: AbortSignal): Promise<{ total: number; critical: number; warning: number; success: number; failed: number }> {
    try {
      const resp = await authFetch(`${API_BASE}/stats`, { signal })
      if (resp.ok) {
        return await resp.json()
      }
    } catch {
      // fallback
    }
    return { total: 0, critical: 0, warning: 0, success: 0, failed: 0 }
  }

  async exportLogs(format: 'json' | 'csv' = 'json', filters?: {
    user?: string
    action?: string
    status?: string
    securityLevel?: string
    startDate?: string
    endDate?: string
  }): Promise<void> {
    const result = await this.getLogsPaginated(1, 10000, filters)
    const exportData = result.data

    if (format === 'json') {
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `audit_logs_${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 100)
    } else {
      const escCsv = (v: string | number | boolean): string => { const s = String(v).replace(/[\r\n]+/g, ' '); return /[",=+\-@]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s }
      const headers = 'ID,用户,操作,操作标签,目标设备,状态,时间,安全级别,结果\n'
      const rows = exportData.map(l =>
        [l.id, l.user, l.action, l.actionLabel, l.targetDevice, l.status, l.timestamp, l.securityLevel || '', l.result || ''].map(escCsv).join(',')
      ).join('\n')
      const blob = new Blob(['\uFEFF' + headers + rows], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `audit_logs_${new Date().toISOString().slice(0, 10)}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 100)
    }
  }
}

export const auditLogService = new AuditLogService()
