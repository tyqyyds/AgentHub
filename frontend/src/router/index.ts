import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/',
      name: 'Dashboard',
      component: () => import('@/views/Dashboard.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] }
    },
    {
      path: '/intent',
      name: 'IntentCenter',
      component: () => import('@/views/IntentCenter.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] }
    },
    {
      path: '/topology',
      name: 'Topology',
      component: () => import('@/views/Topology.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] }
    },
    {
      path: '/self-healing',
      name: 'SelfHealing',
      component: () => import('@/views/SelfHealing.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] }
    },
    {
      path: '/audit-logs',
      name: 'AuditLogs',
      component: () => import('@/views/AuditLogs.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator'] }
    },
    // --- 新增13条路由 ---
    {
      path: '/mcp-tools',
      name: 'MCPTools',
      component: () => import('@/views/MCPTools.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] }
    },
    {
      path: '/agent-map',
      name: 'AgentMap',
      component: () => import('@/views/AgentMap.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] }
    },
    {
      path: '/workflow',
      name: 'WorkOrderBoard',
      component: () => import('@/views/WorkOrderBoard.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] }
    },
    {
      path: '/playbooks',
      name: 'Playbooks',
      component: () => import('@/views/Playbooks.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] }
    },
    {
      path: '/knowledge',
      name: 'KnowledgeBase',
      component: () => import('@/views/KnowledgeBase.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] }
    },
    {
      path: '/sla',
      name: 'SLAPrediction',
      component: () => import('@/views/SLAPrediction.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] }
    },
    {
      path: '/observability',
      name: 'Observability',
      component: () => import('@/views/Observability.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] }
    },
    {
      path: '/notifications',
      name: 'Notifications',
      component: () => import('@/views/Notifications.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator', 'viewer'] }
    },
    {
      path: '/webhooks',
      name: 'WebhookManager',
      component: () => import('@/views/WebhookManager.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator'] }
    },
    {
      path: '/scheduler',
      name: 'Scheduler',
      component: () => import('@/views/Scheduler.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator'] }
    },
    {
      path: '/failed-intents',
      name: 'FailedIntents',
      component: () => import('@/views/FailedIntents.vue'),
      meta: { requiresAuth: true, roles: ['admin', 'operator'] }
    },
    {
      path: '/llm-router',
      name: 'LLMRouter',
      component: () => import('@/views/LLMRouter.vue'),
      meta: { requiresAuth: true, roles: ['admin'] }
    },
    {
      path: '/users',
      name: 'UserManagement',
      component: () => import('@/views/UserManagement.vue'),
      meta: { requiresAuth: true, roles: ['admin'] }
    }
  ]
})

router.beforeEach(async (to) => {
  const token = localStorage.getItem('access_token')

  // 未登录且需要认证 → 跳转登录页
  if (to.meta.requiresAuth !== false && !token) {
    return { name: 'Login' }
  }

  // 已登录访问登录页 → 跳转首页
  if (to.name === 'Login' && token) {
    return { name: 'Dashboard' }
  }

  // RBAC 权限检查
  if (to.meta.roles && token) {
    const authStore = useAuthStore()

    // 确保用户信息已加载
    if (!authStore.user) {
      await authStore.fetchUser()
    }

    // 用户信息仍不可用（如token过期），放行让后续逻辑处理
    if (!authStore.user) return

    const userRole = authStore.user.role
    const allowedRoles = to.meta.roles as string[]

    if (!allowedRoles.includes(userRole)) {
      // 无权限 → 重定向到首页
      return { name: 'Dashboard' }
    }
  }
})

export default router
