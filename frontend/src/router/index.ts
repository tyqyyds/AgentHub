import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { decodeJwtPayload, isTokenExpired } from '@/utils/jwt'
import { API_BASE_URL } from '@/config'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    title?: string
    roles?: string[]
    icon?: string
    breadcrumb?: string
    /** 路由深度，用于方向感知过渡：depth 增大为前进（左滑），减小为后退（右滑） */
    depth?: number
  }
}

const Login = () => import('@/views/Login.vue')
const Dashboard = () => import('@/views/Dashboard.vue')
const IntentCenter = () => import('@/views/IntentCenter.vue')
const Topology = () => import('@/views/Topology.vue')
const SelfHealing = () => import('@/views/SelfHealing.vue')
const MCPTools = () => import('@/views/MCPTools.vue')
const AgentMap = () => import('@/views/AgentMap.vue')
const WorkOrderBoard = () => import('@/views/WorkOrderBoard.vue')
const Playbooks = () => import('@/views/Playbooks.vue')
const WebhookManager = () => import('@/views/WebhookManager.vue')
const AuditLogs = () => import('@/views/AuditLogs.vue')
const UserManagement = () => import('@/views/UserManagement.vue')
const KnowledgeBase = () => import('@/views/KnowledgeBase.vue')
const LLMRouter = () => import('@/views/LLMRouter.vue')
const Scheduler = () => import('@/views/Scheduler.vue')
const SLAPrediction = () => import('@/views/SLAPrediction.vue')
const Observability = () => import('@/views/Observability.vue')
const FailedIntents = () => import('@/views/FailedIntents.vue')
const Notifications = () => import('@/views/Notifications.vue')

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { requiresAuth: false, title: '登录', breadcrumb: '登录', depth: 0 }
  },
  {
    path: '/',
    name: 'Dashboard',
    component: Dashboard,
    meta: { requiresAuth: true, title: '指挥舱', roles: ['admin', 'operator', 'viewer'], icon: '📊', breadcrumb: '指挥舱', depth: 1 }
  },
  {
    path: '/intent',
    name: 'IntentCenter',
    component: IntentCenter,
    meta: { requiresAuth: true, title: '意图中心', roles: ['admin', 'operator', 'viewer'], icon: '🎯', breadcrumb: '意图中心', depth: 2 }
  },
  {
    path: '/topology',
    name: 'Topology',
    component: Topology,
    meta: { requiresAuth: true, title: '网络拓扑', roles: ['admin', 'operator', 'viewer'], icon: '🌐', breadcrumb: '网络拓扑', depth: 2 }
  },
  {
    path: '/self-healing',
    name: 'SelfHealing',
    component: SelfHealing,
    meta: { requiresAuth: true, title: '自愈中心', roles: ['admin', 'operator', 'viewer'], icon: '🛡️', breadcrumb: '自愈中心', depth: 2 }
  },
  {
    path: '/mcp-tools',
    name: 'MCPTools',
    component: MCPTools,
    meta: { requiresAuth: true, title: 'MCP工具', roles: ['admin', 'operator', 'viewer'], icon: '🛠️', breadcrumb: 'MCP工具', depth: 2 }
  },
  {
    path: '/agent-map',
    name: 'AgentMap',
    component: AgentMap,
    meta: { requiresAuth: true, title: '智能体中心', roles: ['admin', 'operator', 'viewer'], icon: '🌐', breadcrumb: '智能体中心', depth: 2 }
  },
  {
    path: '/audit-logs',
    name: 'AuditLogs',
    component: AuditLogs,
    meta: { requiresAuth: true, title: '审计日志', roles: ['admin', 'operator'], icon: '📋', breadcrumb: '审计日志', depth: 3 }
  },
  {
    path: '/workflow',
    name: 'WorkOrderBoard',
    component: WorkOrderBoard,
    meta: { requiresAuth: true, title: '工单看板', roles: ['admin', 'operator', 'viewer'], icon: '📌', breadcrumb: '工单看板', depth: 2 }
  },
  {
    path: '/playbooks',
    name: 'Playbooks',
    component: Playbooks,
    meta: { requiresAuth: true, title: '运维剧本', roles: ['admin', 'operator', 'viewer'], icon: '📜', breadcrumb: '运维剧本', depth: 2 }
  },
  {
    path: '/webhooks',
    name: 'WebhookManager',
    component: WebhookManager,
    meta: { requiresAuth: true, title: 'Webhook', roles: ['admin', 'operator'], icon: '🔗', breadcrumb: 'Webhook管理', depth: 3 }
  },
  {
    path: '/users',
    name: 'UserManagement',
    component: UserManagement,
    meta: { requiresAuth: true, title: '用户管理', roles: ['admin'], icon: '👥', breadcrumb: '用户管理', depth: 3 }
  },
  {
    path: '/knowledge',
    name: 'KnowledgeBase',
    component: KnowledgeBase,
    meta: { requiresAuth: true, title: '知识库', roles: ['admin', 'operator', 'viewer'], icon: '📚', breadcrumb: '知识库', depth: 2 }
  },
  {
    path: '/llm-router',
    name: 'LLMRouter',
    component: LLMRouter,
    meta: { requiresAuth: true, title: 'LLM路由', roles: ['admin'], icon: '🤖', breadcrumb: 'LLM路由', depth: 3 }
  },
  {
    path: '/scheduler',
    name: 'Scheduler',
    component: Scheduler,
    meta: { requiresAuth: true, title: '意图调度', roles: ['admin', 'operator'], icon: '⏱️', breadcrumb: '意图调度', depth: 3 }
  },
  {
    path: '/sla',
    name: 'SLAPrediction',
    component: SLAPrediction,
    meta: { requiresAuth: true, title: 'SLA预测', roles: ['admin', 'operator', 'viewer'], icon: '📊', breadcrumb: 'SLA预测', depth: 2 }
  },
  {
    path: '/observability',
    name: 'Observability',
    component: Observability,
    meta: { requiresAuth: true, title: '可观测性', roles: ['admin', 'operator', 'viewer'], icon: '🔍', breadcrumb: '可观测性', depth: 2 }
  },
  {
    path: '/failed-intents',
    name: 'FailedIntents',
    component: FailedIntents,
    meta: { requiresAuth: true, title: '失败分析', roles: ['admin', 'operator'], icon: '❌', breadcrumb: '失败意图分析', depth: 3 }
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: Notifications,
    meta: { requiresAuth: true, title: '通知中心', roles: ['admin', 'operator', 'viewer'], icon: '🔔', breadcrumb: '通知中心', depth: 2 }
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, _from, next) => {
  const token = localStorage.getItem('access_token')
  const requiresAuth = to.meta.requiresAuth !== false

  document.title = `${to.meta.title || '智维 AgentHub'} - 智维 AgentHub`

  if (requiresAuth && !token) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
  } else if (requiresAuth && token && isTokenExpired(token)) {
    // access_token过期，尝试用refresh_token续期
    const rt = localStorage.getItem('refresh_token')
    if (rt) {
      try {
        const response = await fetch(`${API_BASE_URL || ''}/api/v1/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: rt })
        })
        if (response.ok) {
          const data = await response.json()
          localStorage.setItem('access_token', data.access_token)
          localStorage.setItem('refresh_token', data.refresh_token)
          localStorage.setItem('user_info', JSON.stringify(data.user_info))
          if (data.expires_in) {
            localStorage.setItem('token_expires_at', String(Date.now() + data.expires_in * 1000))
          }
          // 续期成功，继续导航
          const payload = decodeJwtPayload(data.access_token)
          const userRole = payload?.role || 'viewer'
          if (to.meta.roles && to.meta.roles.length > 0 && !to.meta.roles.includes(userRole)) {
            next({ name: 'Dashboard' })
          } else {
            next()
          }
          return
        }
      } catch {
        // refresh失败，继续走登出逻辑
      }
    }
    // refresh_token也不可用，清除并跳登录
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user_info')
    localStorage.removeItem('token_expires_at')
    next({ name: 'Login', query: { redirect: to.fullPath } })
  } else if (to.name === 'Login' && token && !isTokenExpired(token)) {
    next({ name: 'Dashboard' })
  } else if (to.meta.roles && to.meta.roles.length > 0 && token) {
    const payload = decodeJwtPayload(token)
    if (!payload) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user_info')
      next({ name: 'Login', query: { redirect: to.fullPath } })
    } else {
      const userRole = payload.role || 'viewer'
      if (to.meta.roles.includes(userRole)) {
        next()
      } else {
        next({ name: 'Dashboard' })
      }
    }
  } else {
    next()
  }
})

export const menuRoutes = routes.filter(r => r.meta?.icon)

export default router
