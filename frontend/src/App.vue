<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const isLoginPage = computed(() => route.name === 'Login')

// 菜单分组定义：group=分组标题，items=该分组下的菜单项
// roles 字段与 router/index.ts 的 meta.roles 对齐
const menuGroups = [
  {
    group: '概览',
    items: [
      { name: 'Dashboard', icon: '🖥️', path: '/', label: '仪表盘', roles: ['admin', 'operator', 'viewer'] },
      { name: 'IntentCenter', icon: '🎯', path: '/intent', label: '意图中心', roles: ['admin', 'operator', 'viewer'] },
      { name: 'FailedIntents', icon: '⚠️', path: '/failed-intents', label: '失败意图', roles: ['admin', 'operator'] },
    ]
  },
  {
    group: '网络',
    items: [
      { name: 'Topology', icon: '🔗', path: '/topology', label: '网络拓扑', roles: ['admin', 'operator', 'viewer'] },
      { name: 'Observability', icon: '📊', path: '/observability', label: '可观测性', roles: ['admin', 'operator', 'viewer'] },
      { name: 'SLAPrediction', icon: '📈', path: '/sla', label: 'SLA预测', roles: ['admin', 'operator', 'viewer'] },
    ]
  },
  {
    group: '运维',
    items: [
      { name: 'SelfHealing', icon: '🛡️', path: '/self-healing', label: '自愈引擎', roles: ['admin', 'operator', 'viewer'] },
      { name: 'WorkOrderBoard', icon: '📋', path: '/workflow', label: '工单看板', roles: ['admin', 'operator', 'viewer'] },
      { name: 'Playbooks', icon: '📖', path: '/playbooks', label: 'Playbook库', roles: ['admin', 'operator', 'viewer'] },
      { name: 'Scheduler', icon: '⏰', path: '/scheduler', label: '调度中心', roles: ['admin', 'operator'] },
      { name: 'Notifications', icon: '🔔', path: '/notifications', label: '通知中心', roles: ['admin', 'operator', 'viewer'] },
    ]
  },
  {
    group: 'AI',
    items: [
      { name: 'AgentMap', icon: '🗺️', path: '/agent-map', label: 'Agent地图', roles: ['admin', 'operator', 'viewer'] },
      { name: 'MCPTools', icon: '🔧', path: '/mcp-tools', label: 'MCP工具', roles: ['admin', 'operator', 'viewer'] },
      { name: 'KnowledgeBase', icon: '📚', path: '/knowledge', label: '知识库', roles: ['admin', 'operator', 'viewer'] },
      { name: 'LLMRouter', icon: '🤖', path: '/llm-router', label: 'LLM路由', roles: ['admin'] },
    ]
  },
  {
    group: '系统',
    items: [
      { name: 'AuditLogs', icon: '📝', path: '/audit-logs', label: '审计日志', roles: ['admin', 'operator'] },
      { name: 'WebhookManager', icon: '🔗', path: '/webhooks', label: 'Webhook', roles: ['admin', 'operator'] },
      { name: 'UserManagement', icon: '👥', path: '/users', label: '用户管理', roles: ['admin'] },
    ]
  }
]

// RBAC 过滤：根据当前用户角色过滤可见菜单
const visibleMenuGroups = computed(() => {
  const userRole = authStore.user?.role || 'viewer'
  return menuGroups
    .map(group => ({
      group: group.group,
      items: group.items.filter(item => item.roles.includes(userRole))
    }))
    .filter(group => group.items.length > 0)
})

// 当前激活菜单：根据路由自动匹配
const activeMenu = computed(() => route.name as string)

const handleMenuClick = (name: string, path: string) => {
  router.push(path)
}

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <div v-if="isLoginPage" class="login-wrapper">
    <router-view />
  </div>
  <div v-else class="app-container">
    <aside class="sidebar">
      <div class="logo">
        <div class="logo-icon">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        </div>
        <span class="logo-text">智维 AgentHub</span>
      </div>
      <nav class="menu">
        <div v-for="group in visibleMenuGroups" :key="group.group" class="menu-group">
          <div class="menu-group-label">{{ group.group }}</div>
          <button
            v-for="item in group.items"
            :key="item.name"
            :class="['menu-item', { active: activeMenu === item.name }]"
            @click="handleMenuClick(item.name, item.path)"
          >
            <span class="menu-icon">{{ item.icon }}</span>
            <span class="menu-text">{{ item.label }}</span>
          </button>
        </div>
      </nav>
      <div class="user-section">
        <div class="user-info">
          <div class="user-avatar">{{ authStore.user?.username?.charAt(0)?.toUpperCase() || 'U' }}</div>
          <div class="user-detail">
            <span class="user-name">{{ authStore.user?.username || '用户' }}</span>
            <span class="user-role">{{ authStore.user?.role || '' }}</span>
          </div>
        </div>
        <button class="logout-btn" @click="handleLogout" title="退出登录">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>
          </svg>
        </button>
      </div>
    </aside>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--gradient-dark);
  min-height: 100vh;
}

.app-container {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: var(--sidebar-width);
  background: rgba(var(--color-bg-container-rgb), 0.8);
  backdrop-filter: blur(12px);
  border-right: 1px solid rgba(var(--color-white-rgb), 0.1);
  padding: var(--spacing-2xl) 0;
  display: flex;
  flex-direction: column;
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: 0 var(--spacing-2xl) var(--spacing-3xl);
}

.logo-icon {
  width: 40px;
  height: 40px;
  background: var(--gradient-primary);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-white);
}

.logo-icon svg {
  width: 24px;
  height: 24px;
}

.logo-text {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-white);
}

.menu {
  flex: 1;
  padding: 0 var(--spacing-md);
  overflow-y: auto;
}

.menu-group {
  margin-bottom: var(--spacing-sm);
}

.menu-group-label {
  padding: var(--spacing-sm) var(--spacing-lg) var(--spacing-2xs);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-quaternary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md) var(--spacing-lg);
  margin-bottom: var(--spacing-2xs);
  border: none;
  background: transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.3s ease;
  color: var(--color-text-tertiary);
}

.menu-item:hover {
  background: rgba(var(--color-primary-rgb), 0.1);
  color: var(--color-text-secondary);
}

.menu-item.active {
  background: linear-gradient(135deg, rgba(var(--color-primary-rgb), 0.2) 0%, rgba(var(--color-info-light-rgb), 0.1) 100%);
  color: var(--color-white);
}

.menu-icon {
  font-size: var(--font-size-xl);
}

.menu-text {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
}

.main-content {
  flex: 1;
  padding: var(--spacing-2xl);
  overflow-y: auto;
}

.login-wrapper {
  min-height: 100vh;
}

.user-section {
  padding: var(--spacing-lg) var(--spacing-lg) 0;
  border-top: 1px solid rgba(var(--color-white-rgb), 0.08);
  margin-top: var(--spacing-md);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--gradient-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-white);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-bold);
  flex-shrink: 0;
}

.user-detail {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.user-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-role {
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
  text-transform: capitalize;
}

.logout-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--color-text-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}

.logout-btn:hover {
  background: rgba(var(--color-error-rgb), 0.15);
  color: var(--color-error-light);
}

.logout-btn svg {
  width: 18px;
  height: 18px;
}
</style>