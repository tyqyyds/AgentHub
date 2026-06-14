<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import router from './router'
import { toasts, hideToast, toastIcons, toastColors, showToast } from './utils/toast'
import { useLogger } from './utils/logger'
import { useAppStore } from './stores/app'
import { useAuthStore } from './stores/auth'
import { useWebSocket } from './composables/useWebSocket'
import { useResponsive } from './composables/useResponsive'
import { usePageTransition } from './composables/usePageTransition'
import AiAssistant from './components/AiAssistant/AiAssistant.vue'
import { useAssistantStore } from './stores/assistant'
import { api, apiClient } from './utils/apiClient'

const { info: logInfo } = useLogger()
const appStore = useAppStore()
const authStore = useAuthStore()
const assistantStore = useAssistantStore()
const ws = useWebSocket()
const { isMobile, isTablet } = useResponsive()
const { transitionName, onBeforeEnter, onAfterLeave } = usePageTransition()

const activeMenu = ref('Dashboard')
const sidebarOpen = ref(false)
const sidebarCollapsed = ref(false)
const showUserDropdown = ref(false)
const showNotificationPanel = ref(false)
const unreadCount = ref(0)

const menuItems = [
  { name: 'Dashboard', icon: '🖥️', path: '/', label: '指挥舱', roles: ['admin', 'operator', 'viewer'] },
  { name: 'IntentCenter', icon: '🎯', path: '/intent', label: '意图中心', roles: ['admin', 'operator', 'viewer'] },
  { name: 'Topology', icon: '🔗', path: '/topology', label: '网络拓扑', roles: ['admin', 'operator', 'viewer'] },
  { name: 'SelfHealing', icon: '🛡️', path: '/self-healing', label: '自愈中心', roles: ['admin', 'operator', 'viewer'] },
  { name: 'MCPTools', icon: '🔧', path: '/mcp-tools', label: 'MCP工具', roles: ['admin', 'operator', 'viewer'] },
  { name: 'AgentMap', icon: '🌐', path: '/agent-map', label: '智能体中心', roles: ['admin', 'operator', 'viewer'] },
  { name: 'AuditLogs', icon: '📋', path: '/audit-logs', label: '审计日志', roles: ['admin', 'operator'] },
  { name: 'WorkOrderBoard', icon: '📌', path: '/workflow', label: '工单看板', roles: ['admin', 'operator', 'viewer'] },
  { name: 'Playbooks', icon: '📜', path: '/playbooks', label: '运维剧本', roles: ['admin', 'operator', 'viewer'] },
  { name: 'WebhookManager', icon: '🔗', path: '/webhooks', label: 'Webhook', roles: ['admin', 'operator'] },
  { name: 'UserManagement', icon: '👥', path: '/users', label: '用户管理', roles: ['admin'] },
  { name: 'KnowledgeBase', icon: '📚', path: '/knowledge', label: '知识库', roles: ['admin', 'operator', 'viewer'] },
  { name: 'LLMRouter', icon: '🤖', path: '/llm-router', label: 'LLM路由', roles: ['admin'] },
  { name: 'Scheduler', icon: '⏱️', path: '/scheduler', label: '意图调度', roles: ['admin', 'operator'] },
  { name: 'SLAPrediction', icon: '📊', path: '/sla', label: 'SLA预测', roles: ['admin', 'operator', 'viewer'] },
  { name: 'Observability', icon: '🔍', path: '/observability', label: '可观测性', roles: ['admin', 'operator', 'viewer'] },
  { name: 'FailedIntents', icon: '❌', path: '/failed-intents', label: '失败分析', roles: ['admin', 'operator'] },
  { name: 'Notifications', icon: '🔔', path: '/notifications', label: '通知中心', roles: ['admin', 'operator', 'viewer'] }
]

watch(() => router.currentRoute.value.path, (newPath) => {
  const match = menuItems.find(item => item.path === newPath)
  if (match) activeMenu.value = match.name
}, { immediate: true })

const isAuthPage = computed(() => router.currentRoute.value.name === 'Login')
const isAuthenticated = computed(() => authStore.isAuthenticated)

const pageTitle = computed(() => {
  const route = router.currentRoute.value
  return route.meta?.title || '智维 AgentHub'
})

const visibleMenuItems = computed(() => {
  const role = authStore.userRole || 'viewer'
  return menuItems.filter(item => item.roles.includes(role))
})

const bottomNavItems = computed(() => visibleMenuItems.value.slice(0, 5))

const canManageSystem = computed(() => {
  const role = authStore.userRole || 'viewer'
  return ['admin'].includes(role)
})

const userDisplayName = computed(() => {
  return authStore.userInfo?.username || '用户'
})

const userRole = computed(() => {
  const role = authStore.userRole || 'viewer'
  const roleMap: Record<string, string> = { admin: '管理员', operator: '运维员', viewer: '观察者' }
  return roleMap[role] || role
})

const handleMenuClick = (name: string, path: string) => {
  activeMenu.value = name
  router.push(path)
  if (isMobile.value) sidebarOpen.value = false
}

const toggleSidebar = () => {
  if (isMobile.value) {
    sidebarOpen.value = !sidebarOpen.value
  } else {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }
}

const closeSidebar = () => { sidebarOpen.value = false }

const handleLogout = () => {
  showUserDropdown.value = false
  authStore.logout()
  router.push('/login')
}

const toggleUserDropdown = () => {
  showUserDropdown.value = !showUserDropdown.value
  showNotificationPanel.value = false
}

const toggleNotificationPanel = () => {
  showNotificationPanel.value = !showNotificationPanel.value
  showUserDropdown.value = false
}

const fetchUnreadCount = async () => {
  if (!authStore.isAuthenticated) return
  try {
    const result = await apiClient.get(api.notifications.unread)
    if (result.data) {
      unreadCount.value = result.data.count ?? result.data.unread_count ?? 0
    }
  } catch {
    unreadCount.value = 0
  }
}

const handleClickOutside = (e: MouseEvent) => {
  const target = e.target as HTMLElement
  if (!target.closest('.user-dropdown-wrapper')) {
    showUserDropdown.value = false
  }
  if (!target.closest('.notification-wrapper')) {
    showNotificationPanel.value = false
  }
}

let fuseCheckInterval: ReturnType<typeof setInterval> | undefined
let notificationInterval: ReturnType<typeof setInterval> | undefined

const handleEscapeKey = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    if (sidebarOpen.value) closeSidebar()
    if (showUserDropdown.value) showUserDropdown.value = false
    if (showNotificationPanel.value) showNotificationPanel.value = false
  }
}

const handleWsAlert = (msg: any) => {
  const data = msg.data || {}
  const level = (data.level as string) || 'info'
  const message = (data.message as string) || ''
  if (message) {
    const toastType = level === 'error' ? 'error' : level === 'warning' ? 'warning' : 'success'
    showToast(message, toastType)
    unreadCount.value++
  }
}
const handleWsTopologyUpdate = () => {
  window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
}
const handleWsIntentUpdate = () => {
  window.dispatchEvent(new CustomEvent('dashboardDataUpdated'))
}

onMounted(() => {
  if (authStore.isAuthenticated) {
    appStore.fetchFuseStatus()
    fuseCheckInterval = setInterval(() => appStore.fetchFuseStatus(), 30000)
    fetchUnreadCount()
    notificationInterval = setInterval(fetchUnreadCount, 60000)
  }
  logInfo('App mounted')
  window.addEventListener('keydown', handleEscapeKey)
  document.addEventListener('click', handleClickOutside)

  if (authStore.isAuthenticated) {
    ws.connect()
  }
  ws.on('alert', handleWsAlert as any)
  ws.on('topology_update', handleWsTopologyUpdate)
  ws.on('intent_update', handleWsIntentUpdate)
  ws.on('emergency_fuse' as any, (msg: any) => {
    const data = msg.data || {}
    if (data.action === 'fuse_enabled') {
      appStore.fuseEnabled = true
      appStore.fuseReason = data.reason || '系统紧急熔断'
      showToast(`🚨 系统紧急熔断: ${data.reason || '安全防护已激活'}`, 'error')
    } else if (data.action === 'fuse_disabled') {
      appStore.fuseEnabled = false
      appStore.fuseReason = ''
      showToast('✅ 系统熔断已解除，恢复正常运行', 'success')
    }
  })
})

watch(() => authStore.isAuthenticated, (authenticated) => {
  if (authenticated) {
    ws.connect()
    appStore.fetchFuseStatus()
    if (fuseCheckInterval) clearInterval(fuseCheckInterval)
    fuseCheckInterval = setInterval(() => appStore.fetchFuseStatus(), 30000)
    fetchUnreadCount()
    if (notificationInterval) clearInterval(notificationInterval)
    notificationInterval = setInterval(fetchUnreadCount, 60000)
  } else {
    ws.disconnect()
    if (fuseCheckInterval) clearInterval(fuseCheckInterval)
    fuseCheckInterval = undefined
    if (notificationInterval) clearInterval(notificationInterval)
    notificationInterval = undefined
  }
})

onUnmounted(() => {
  clearInterval(fuseCheckInterval)
  clearInterval(notificationInterval)
  window.removeEventListener('keydown', handleEscapeKey)
  document.removeEventListener('click', handleClickOutside)
  ws.off('alert', handleWsAlert as any)
  ws.off('topology_update', handleWsTopologyUpdate)
  ws.off('intent_update', handleWsIntentUpdate)
})
</script>

<template>
  <div class="app-container" :class="{ 'sidebar-collapsed': sidebarCollapsed && !isMobile }">
    <div v-if="sidebarOpen && isMobile && !isAuthPage" class="sidebar-backdrop" @click="closeSidebar"></div>

    <aside v-if="!isAuthPage" :class="['sidebar', { open: sidebarOpen, collapsed: sidebarCollapsed && !isMobile }]">
      <div class="sidebar-header">
        <div class="logo">
          <div class="logo-icon">
            <svg viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="智维 AgentHub">
              <title>智维 AgentHub</title>
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          </div>
          <transition name="fade-text">
            <span v-if="!sidebarCollapsed || isMobile" class="logo-text">智维 AgentHub</span>
          </transition>
        </div>
        <button v-if="isMobile" type="button" class="drawer-close-btn" @click="closeSidebar" aria-label="关闭菜单">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
        <button v-else type="button" class="collapse-btn" @click="sidebarCollapsed = !sidebarCollapsed" :aria-label="sidebarCollapsed ? '展开侧栏' : '收起侧栏'">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :class="{ rotated: sidebarCollapsed }">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
      </div>

      <nav class="menu" aria-label="主导航">
        <button
          type="button"
          v-for="item in visibleMenuItems"
          :key="item.name"
          :class="['menu-item', { active: activeMenu === item.name }]"
          @click="handleMenuClick(item.name, item.path)"
          :aria-label="item.label"
          :aria-current="activeMenu === item.name ? 'page' : undefined"
          :title="sidebarCollapsed && !isMobile ? item.label : ''"
        >
          <span class="menu-icon">{{ item.icon }}</span>
          <transition name="fade-text">
            <span v-if="!sidebarCollapsed || isMobile" class="menu-text">{{ item.label }}</span>
          </transition>
          <div v-if="activeMenu === item.name" class="active-indicator"></div>
        </button>
      </nav>

      <div class="sidebar-footer">
        <div v-if="canManageSystem && (!sidebarCollapsed || isMobile)" class="fuse-section">
          <button
            type="button"
            :class="['fuse-button', { active: appStore.fuseEnabled }]"
            @click="appStore.requestFuseToggle()"
            aria-label="熔断开关"
          >
            <span class="fuse-icon">{{ appStore.fuseEnabled ? '🚨' : '🛡️' }}</span>
            <span class="fuse-text">{{ appStore.fuseEnabled ? '熔断中' : '系统正常' }}</span>
          </button>
        </div>
        <div v-if="canManageSystem && sidebarCollapsed && !isMobile" class="fuse-section-collapsed">
          <button
            type="button"
            :class="['fuse-button-mini', { active: appStore.fuseEnabled }]"
            @click="appStore.requestFuseToggle()"
            :title="appStore.fuseEnabled ? '熔断中' : '系统正常'"
            aria-label="熔断开关"
          >
            {{ appStore.fuseEnabled ? '🚨' : '🛡️' }}
          </button>
        </div>
      </div>
    </aside>

    <div class="main-wrapper">
      <header v-if="!isAuthPage" class="header">
        <div class="header-left">
          <button v-if="isMobile" type="button" class="hamburger-btn" @click="toggleSidebar" aria-label="打开菜单">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="3" y1="12" x2="21" y2="12"/>
              <line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
          <h1 class="header-title">{{ pageTitle }}</h1>
        </div>
        <div class="header-right">
          <div :class="['system-status', { fused: appStore.fuseEnabled }]">
            <span class="status-dot"></span>
            <span class="status-text">{{ appStore.fuseEnabled ? '⚠️ 熔断中' : '✅ 正常' }}</span>
          </div>
          <div class="notification-wrapper">
            <button type="button" class="notification-btn" @click.stop="toggleNotificationPanel" aria-label="通知">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
                <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
              </svg>
              <span v-if="unreadCount > 0" class="notification-badge" :aria-label="unreadCount + '条未读通知'">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
            </button>
            <transition name="dropdown">
              <div v-if="showNotificationPanel" class="notification-panel" role="region" aria-label="通知面板" @click.stop>
                <div class="notification-panel-header">
                  <span class="notification-panel-title">通知</span>
                  <span v-if="unreadCount > 0" class="notification-count">{{ unreadCount }} 条未读</span>
                </div>
                <div class="notification-panel-body">
                  <div class="notification-empty">
                    <span class="notification-empty-icon">🔔</span>
                    <span>{{ unreadCount > 0 ? `${unreadCount} 条未读通知` : '暂无新通知' }}</span>
                  </div>
                </div>
              </div>
            </transition>
          </div>

          <button
            type="button"
            v-if="canManageSystem"
            :class="['emergency-button', { active: appStore.fuseEnabled }]"
            @click="appStore.requestFuseToggle()"
            aria-label="紧急制动"
          >
            <span class="emergency-icon">{{ appStore.fuseEnabled ? '✅' : '🚨' }}</span>
            <span class="emergency-text">{{ appStore.fuseEnabled ? '解除熔断' : '紧急制动' }}</span>
          </button>
          <button
            type="button"
            v-if="assistantStore.isHidden"
            class="ai-restore-btn"
            @click="assistantStore.showAssistant()"
            aria-label="显示AI助手"
            title="显示AI助手"
          >
            🤖
          </button>

          <div class="user-dropdown-wrapper">
            <button type="button" class="user-btn" @click.stop="toggleUserDropdown" aria-label="用户菜单">
              <div class="user-avatar">{{ userDisplayName.charAt(0).toUpperCase() }}</div>
              <span class="user-name">{{ userDisplayName }}</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :class="{ rotated: showUserDropdown }">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>
            <transition name="dropdown">
              <div v-if="showUserDropdown" class="user-dropdown" role="menu" @click.stop>
                <div class="user-dropdown-header">
                  <div class="user-dropdown-avatar">{{ userDisplayName.charAt(0).toUpperCase() }}</div>
                  <div class="user-dropdown-info">
                    <span class="user-dropdown-name">{{ userDisplayName }}</span>
                    <span class="user-dropdown-role">{{ userRole }}</span>
                  </div>
                </div>
                <div class="user-dropdown-divider"></div>
                <button type="button" class="user-dropdown-item logout" role="menuitem" @click="handleLogout">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                    <polyline points="16 17 21 12 16 7"/>
                    <line x1="21" y1="12" x2="9" y2="12"/>
                  </svg>
                  <span>退出登录</span>
                </button>
              </div>
            </transition>
          </div>
        </div>
      </header>

      <main :class="['main-content', { 'has-bottom-nav': isMobile }]">
        <router-view v-slot="{ Component, route }">
          <transition :name="transitionName" mode="out-in" @before-enter="onBeforeEnter" @after-leave="onAfterLeave">
            <component :is="Component" :key="route.path" />
          </transition>
        </router-view>
        <AiAssistant v-if="isAuthenticated" />
      </main>
    </div>

    <nav v-if="isMobile && !isAuthPage" class="bottom-nav" role="navigation" aria-label="主导航">
      <button
        type="button"
        v-for="item in bottomNavItems"
        :key="item.name"
        :class="['bottom-nav-item', { active: activeMenu === item.name }]"
        :aria-label="item.label"
        :aria-current="activeMenu === item.name ? 'page' : undefined"
        @click="handleMenuClick(item.name, item.path)"
      >
        <span class="bottom-nav-icon">{{ item.icon }}</span>
        <span class="bottom-nav-label">{{ item.label }}</span>
      </button>
      <button
        type="button"
        v-if="visibleMenuItems.length > 5"
        :class="['bottom-nav-item', { active: !bottomNavItems.some(i => i.name === activeMenu) }]"
        @click="toggleSidebar"
        aria-label="更多菜单"
      >
        <span class="bottom-nav-icon">⋯</span>
        <span class="bottom-nav-label">更多</span>
      </button>
    </nav>

    <Teleport to="body">
      <div v-if="appStore.fuseEnabled && appStore.fuseBannerVisible" class="fuse-overlay">
        <div class="fuse-banner">
          <span class="fuse-alert">🚨</span>
          <span class="fuse-message">系统紧急熔断中 - {{ appStore.fuseReason }}</span>
          <button type="button" class="fuse-dismiss" @click="appStore.dismissFuseBanner()" title="关闭横幅" aria-label="关闭横幅">✕</button>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="appStore.showFuseConfirm" class="modal-overlay fuse-confirm-overlay" @click.self="appStore.dismissFuseConfirm()" role="dialog" aria-modal="true" aria-labelledby="fuse-confirm-title">
        <div class="fuse-confirm-modal">
          <div class="fuse-confirm-header">
            <span class="fuse-confirm-icon">{{ appStore.fuseConfirmAction === 'enable' ? '🚨' : '✅' }}</span>
            <h3 id="fuse-confirm-title" :class="['fuse-confirm-title', appStore.fuseConfirmAction]">
              {{ appStore.fuseConfirmAction === 'enable' ? '确认紧急制动？' : '确认解除熔断？' }}
            </h3>
          </div>
          <p class="fuse-confirm-desc">
            {{ appStore.fuseConfirmAction === 'enable'
              ? '紧急制动将执行以下安全防护动作：\n• 阻止所有待执行意图\n• 暂停活跃工作流\n• 禁用自动自愈\n• 激活网络隔离模式\n• 挂起调度任务\n• 启用增强审计日志\n此操作需谨慎执行。'
              : '解除熔断将恢复所有自动操作，包括意图执行、自愈流程和配置下发。请确认系统状态已恢复正常。'
            }}
          </p>
          <div class="fuse-confirm-actions">
            <button type="button" class="fuse-confirm-btn cancel" @click="appStore.dismissFuseConfirm()" aria-label="取消">取消</button>
            <button type="button" :class="['fuse-confirm-btn', appStore.fuseConfirmAction]" @click="appStore.confirmFuseAction()" aria-label="确认制动">
              {{ appStore.fuseConfirmAction === 'enable' ? '确认制动' : '确认解除' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div class="toast-container">
        <TransitionGroup name="toast">
          <div
            v-for="toast in toasts"
            :key="toast.id"
            class="toast-item"
            role="alert"
            :style="{ borderLeftColor: toastColors[toast.type] }"
          >
            <span class="toast-icon">{{ toastIcons[toast.type] }}</span>
            <span class="toast-message">{{ toast.message }}</span>
            <button type="button" class="toast-close" @click="hideToast(toast.id)" aria-label="关闭通知">×</button>
          </div>
        </TransitionGroup>
      </div>
    </Teleport>
  </div>
</template>

<style>

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

*:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

button:focus-visible,
a:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}

.menu-item:focus-visible,
.collapse-btn:focus-visible,
.fuse-button:focus-visible,
.notification-btn:focus-visible,
.emergency-button:focus-visible,
.ai-restore-btn:focus-visible,
.user-btn:focus-visible,
.user-dropdown-item:focus-visible,
.bottom-nav-item:focus-visible,
.fuse-dismiss:focus-visible,
.fuse-confirm-btn:focus-visible,
.toast-close:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

html {
  -webkit-text-size-adjust: 100%;
  -webkit-tap-highlight-color: transparent;
}

body {
  font-family: var(--font-family-base);
  background: var(--color-bg-primary);
  min-height: 100vh;
  overscroll-behavior: none;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

button {
  min-height: var(--button-min-height);
  -webkit-tap-highlight-color: transparent;
  touch-action: manipulation;
}

input, select, textarea {
  font-size: var(--font-size-md);
}

@media (max-width: 768px) {
  button {
    min-height: var(--button-min-height-touch);
  }

  body {
    -webkit-overflow-scrolling: touch;
  }
}

.app-container {
  display: flex;
  min-height: 100vh;
  background: var(--color-bg-primary);
}

.sidebar-backdrop {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background: var(--modal-overlay-bg);
  z-index: var(--z-fixed);
  animation: backdrop-fade-in 0.2s var(--ease-out);
  backdrop-filter: blur(var(--modal-backdrop-blur));
  -webkit-backdrop-filter: blur(var(--modal-backdrop-blur));
}

@keyframes backdrop-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

.sidebar {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  width: var(--sidebar-width);
  background: var(--gradient-glass-strong);
  border-right: 1px solid var(--color-border-primary);
  padding: 0;
  display: flex;
  flex-direction: column;
  z-index: var(--z-fixed);
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  backdrop-filter: blur(var(--backdrop-blur-lg));
  -webkit-backdrop-filter: blur(var(--backdrop-blur-lg));
  transition: width 0.3s var(--ease-out), transform 0.3s var(--ease-out);
  will-change: transform;
}

.sidebar.collapsed {
  width: var(--sidebar-collapsed-width);
}

@media (max-width: 768px) {
  .sidebar {
    width: 280px;
    transform: translateX(-100%);
    box-shadow: none;
  }

  .sidebar.open {
    transform: translateX(0);
    box-shadow: var(--shadow-dropdown);
  }

  .sidebar.collapsed {
    width: 280px;
  }
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1rem 1rem 1.25rem;
  border-bottom: 1px solid var(--color-border-primary);
  min-height: var(--header-height);
  flex-shrink: 0;
}

.logo {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.logo-icon {
  width: 2.25rem;
  height: 2.25rem;
  background: var(--gradient-primary);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-primary);
  flex-shrink: 0;
  box-shadow: var(--shadow-glow-primary);
}

.logo-icon svg {
  width: 1.25rem;
  height: 1.25rem;
}

.logo-text {
  font-size: var(--font-size-base);
  font-weight: 700;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.drawer-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: var(--color-bg-active);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-default);
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: var(--button-transition);
  flex-shrink: 0;
  padding: 0;
}

.drawer-close-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-secondary);
  border-color: var(--color-border-hover);
}

.drawer-close-btn svg {
  width: 1rem;
  height: 1rem;
}

.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: var(--color-bg-hover);
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: var(--button-transition);
  flex-shrink: 0;
  padding: 0;
}

.collapse-btn:hover {
  background: var(--color-bg-active);
  color: var(--color-text-secondary);
}

.collapse-btn svg {
  width: 1rem;
  height: 1rem;
  transition: transform 0.3s var(--ease-out);
}

.collapse-btn svg.rotated {
  transform: rotate(180deg);
}

.menu {
  padding: 0.5rem 0.5rem;
  flex: 1;
}

.menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  margin-bottom: 2px;
  border: none;
  background: transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--button-transition);
  color: var(--color-text-tertiary);
  min-height: 2.75rem;
  position: relative;
  overflow: hidden;
}

.menu-item:hover {
  background: var(--color-primary-bg);
  color: var(--color-text-secondary);
  box-shadow: var(--shadow-glow-primary);
}

.menu-item.active {
  background: var(--color-primary-hover);
  color: var(--color-primary-light);
}

.active-indicator {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 60%;
  background: var(--gradient-primary);
  border-radius: 0 3px 3px 0;
  box-shadow: var(--shadow-glow-primary);
  animation: indicator-glow 2s var(--ease-in-out) infinite;
}

@keyframes indicator-glow {
  0%, 100% { box-shadow: var(--shadow-glow-primary); }
  50% { box-shadow: 0 0 20px var(--color-primary-glow); }
}

.menu-icon {
  font-size: var(--font-size-lg);
  flex-shrink: 0;
  width: 1.5rem;
  text-align: center;
}

.menu-text {
  font-size: var(--font-size-sm);
  font-weight: 500;
  white-space: nowrap;
}

.sidebar.collapsed .menu-item {
  justify-content: center;
  padding: 0.75rem 0;
}

.sidebar-footer {
  padding: 0.75rem;
  border-top: 1px solid var(--color-border-primary);
  flex-shrink: 0;
}

.fuse-section {
  padding: 0;
}

.fuse-button {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: 0.625rem;
  background: var(--color-success-bg);
  border: 1px solid var(--color-success-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--button-transition);
  color: var(--color-success);
  min-height: 2.5rem;
}

.fuse-button:hover {
  background: var(--color-success-hover);
  box-shadow: var(--shadow-glow-success);
}

.fuse-button.active {
  background: var(--color-error-bg);
  border-color: var(--color-error-border);
  color: var(--color-error);
  animation: fuse-pulse 2s ease-in-out infinite;
}

@keyframes fuse-pulse {
  0%, 100% { border-color: var(--color-error-border); }
  50% { border-color: var(--color-error); box-shadow: var(--shadow-glow-error); }
}

.fuse-icon {
  font-size: var(--font-size-md);
}

.fuse-text {
  font-size: var(--font-size-xs);
  font-weight: 500;
}

.fuse-section-collapsed {
  display: flex;
  justify-content: center;
}

.fuse-button-mini {
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-success-bg);
  border: 1px solid var(--color-success-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--button-transition);
  font-size: var(--font-size-md);
  padding: 0;
}

.fuse-button-mini.active {
  background: var(--color-error-bg);
  border-color: var(--color-error-border);
  animation: fuse-pulse 2s ease-in-out infinite;
}

.main-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  margin-left: var(--sidebar-width);
  transition: margin-left 0.3s var(--ease-out);
}

.sidebar-collapsed .main-wrapper {
  margin-left: var(--sidebar-collapsed-width);
}

@media (max-width: 768px) {
  .main-wrapper {
    margin-left: 0;
  }
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  min-height: 0;
  max-width: 100rem;
  width: 100%;
  margin: 0 auto;
}

.main-content.has-bottom-nav {
  padding-bottom: 4.5rem;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 1.5rem;
  height: var(--header-height);
  border-bottom: 1px solid var(--color-border-primary);
  background: var(--color-bg-glass-strong);
  backdrop-filter: blur(var(--backdrop-blur-lg));
  -webkit-backdrop-filter: blur(var(--backdrop-blur-lg));
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex: 1;
  min-width: 0;
}

.hamburger-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--button-transition);
  flex-shrink: 0;
  padding: 0;
  color: var(--color-text-tertiary);
}

.hamburger-btn:hover {
  background: var(--color-bg-active);
  color: var(--color-text-secondary);
  border-color: var(--color-border-hover);
}

.hamburger-btn svg {
  width: 1.125rem;
  height: 1.125rem;
  transition: transform 0.3s var(--ease-out);
}

.hamburger-btn svg.rotated {
  transform: rotate(180deg);
}

.header-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.system-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 0.375rem 0.75rem;
  background: var(--color-success-bg);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-success-border);
  transition: var(--button-transition);
}

.system-status.fused {
  background: var(--color-error-bg);
  border-color: var(--color-error-border);
}

.status-dot {
  width: 8px;
  height: 8px;
  background: var(--color-success);
  border-radius: 50%;
  box-shadow: 0 0 6px var(--color-success-glow);
}

.system-status.fused .status-dot {
  background: var(--color-error);
  animation: pulse 1s ease-in-out infinite;
  box-shadow: 0 0 6px var(--color-error-glow);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-text {
  font-size: var(--font-size-xs);
  color: var(--color-success);
  font-weight: 500;
}

.system-status.fused .status-text {
  color: var(--color-error-light);
}

.notification-wrapper {
  position: relative;
}

.notification-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: var(--button-transition);
  padding: 0;
  position: relative;
}

.notification-btn:hover {
  background: var(--color-bg-active);
  color: var(--color-text-secondary);
  border-color: var(--color-border-hover);
  box-shadow: var(--shadow-glow-primary);
}

.notification-btn svg {
  width: 1.125rem;
  height: 1.125rem;
}

.notification-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: var(--color-error);
  color: var(--color-text-primary);
  font-size: var(--font-size-xs);
  font-weight: 700;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  box-shadow: 0 0 0 2px var(--color-bg-secondary), var(--shadow-glow-error);
  animation: badge-pop 0.3s var(--ease-spring);
}

@keyframes badge-pop {
  0% { transform: scale(0); }
  50% { transform: scale(1.2); }
  100% { transform: scale(1); }
}

.notification-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 320px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-dropdown);
  overflow: hidden;
  z-index: var(--z-overlay);
  backdrop-filter: blur(var(--backdrop-blur-lg));
  -webkit-backdrop-filter: blur(var(--backdrop-blur-lg));
  will-change: transform, opacity;
}

.notification-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.875rem 1rem;
  border-bottom: 1px solid var(--color-border-primary);
}

.notification-panel-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.notification-count {
  font-size: var(--font-size-xs);
  color: var(--color-primary-light);
  background: var(--color-primary-bg);
  padding: 2px 8px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-primary-border);
}

.notification-panel-body {
  padding: 1.5rem 1rem;
}

.notification-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.notification-empty-icon {
  font-size: 1.5rem;
  opacity: 0.6;
}

.emergency-button {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 0.375rem 0.875rem;
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-md);
  color: var(--color-error-light);
  cursor: pointer;
  transition: var(--button-transition);
  min-height: var(--button-height-md);
}

.emergency-button:hover {
  background: var(--color-error-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-glow-error);
}

.emergency-button.active {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
  color: var(--color-success);
}

.emergency-button.active:hover {
  background: var(--color-success-hover);
  box-shadow: var(--shadow-glow-success);
}

.emergency-icon {
  font-size: var(--font-size-sm);
}

.emergency-text {
  font-size: var(--font-size-xs);
  font-weight: 600;
}

.ai-restore-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-md);
  cursor: pointer;
  transition: var(--button-transition);
  padding: 0;
}

.ai-restore-btn:hover {
  background: var(--color-primary-hover);
  transform: scale(1.05);
  box-shadow: var(--shadow-glow-primary);
}

.user-dropdown-wrapper {
  position: relative;
}

.user-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem 0.25rem 0.25rem;
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: var(--button-transition);
  min-height: var(--button-height-md);
}

.user-btn:hover {
  background: var(--color-bg-active);
  border-color: var(--color-border-hover);
}

.user-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xs);
  font-weight: 700;
  flex-shrink: 0;
}

.user-name {
  font-size: var(--font-size-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-btn svg {
  width: 0.875rem;
  height: 0.875rem;
  transition: transform 0.2s var(--ease-out);
  flex-shrink: 0;
}

.user-btn svg.rotated {
  transform: rotate(180deg);
}

.user-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 220px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-dropdown);
  overflow: hidden;
  z-index: var(--z-overlay);
  backdrop-filter: blur(var(--backdrop-blur-lg));
  -webkit-backdrop-filter: blur(var(--backdrop-blur-lg));
  will-change: transform, opacity;
}

.user-dropdown-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
}

.user-dropdown-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-sm);
  font-weight: 700;
  flex-shrink: 0;
}

.user-dropdown-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.user-dropdown-name {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-dropdown-role {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.user-dropdown-divider {
  height: 1px;
  background: var(--color-border-primary);
}

.user-dropdown-item {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  width: 100%;
  padding: 0.75rem 1rem;
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all 0.15s var(--ease-out);
}

.user-dropdown-item:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-secondary);
}

.user-dropdown-item.logout {
  color: var(--color-error);
}

.user-dropdown-item.logout:hover {
  background: var(--color-error-bg);
  color: var(--color-error-light);
}

.user-dropdown-item svg {
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
}

.dropdown-enter-active {
  animation: dropdown-in 0.15s var(--ease-out);
}

.dropdown-leave-active {
  animation: dropdown-out 0.1s var(--ease-out);
}

@keyframes dropdown-in {
  from { opacity: 0; transform: translateY(-4px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes dropdown-out {
  from { opacity: 1; transform: translateY(0) scale(1); }
  to { opacity: 0; transform: translateY(-4px) scale(0.98); }
}

.fade-text-enter-active {
  transition: opacity 0.2s var(--ease-out) 0.1s;
}

.fade-text-leave-active {
  transition: opacity 0.1s var(--ease-out);
}

.fade-text-enter-from,
.fade-text-leave-to {
  opacity: 0;
}

.page-fade-enter-active {
  transition: opacity 0.2s var(--ease-out), transform 0.2s var(--ease-out);
}

.page-fade-leave-active {
  transition: opacity 0.15s var(--ease-out), transform 0.15s var(--ease-out);
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: stretch;
  justify-content: space-around;
  background: var(--color-bg-glass-strong);
  border-top: 1px solid var(--color-border-primary);
  backdrop-filter: blur(var(--backdrop-blur-lg));
  -webkit-backdrop-filter: blur(var(--backdrop-blur-lg));
  z-index: var(--z-fixed);
  padding-bottom: env(safe-area-inset-bottom, 0px);
  height: calc(56px + env(safe-area-inset-bottom, 0px));
}

.bottom-nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  flex: 1;
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  cursor: pointer;
  padding: 6px var(--spacing-xs);
  min-height: var(--button-min-height-touch);
  transition: var(--button-transition);
  -webkit-tap-highlight-color: transparent;
  position: relative;
  will-change: transform;
}

.bottom-nav-item.active {
  color: var(--color-primary-light);
}

.bottom-nav-item.active::after {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 24px;
  height: 2px;
  background: var(--gradient-primary);
  border-radius: 0 0 2px 2px;
  box-shadow: var(--shadow-glow-primary);
}

.bottom-nav-icon {
  font-size: var(--font-size-xl);
  line-height: 1;
}

.bottom-nav-label {
  font-size: var(--font-size-xs);
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
}

.fuse-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: var(--z-banner);
  pointer-events: none;
  animation: fuse-slide-in 0.3s var(--ease-spring);
}

@keyframes fuse-slide-in {
  from { transform: translateY(-100%); }
  to { transform: translateY(0); }
}

.fuse-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--gradient-danger);
  pointer-events: auto;
  box-shadow: var(--shadow-glow-error);
  padding-top: calc(var(--spacing-md) + env(safe-area-inset-top, 0px));
  will-change: transform;
}

.fuse-alert {
  font-size: var(--font-size-xl);
  animation: fuse-alert-pulse 1s ease-in-out infinite;
}

@keyframes fuse-alert-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.2); }
}

.fuse-message {
  flex: 1;
  text-align: center;
  color: var(--color-text-primary);
  font-weight: 600;
  font-size: var(--font-size-base);
}

.fuse-dismiss {
  background: var(--color-bg-active);
  border: none;
  color: var(--color-text-primary);
  font-size: var(--font-size-base);
  cursor: pointer;
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  transition: background 0.2s var(--ease-out);
  min-width: 44px;
  min-height: var(--button-min-height-touch);
  display: flex;
  align-items: center;
  justify-content: center;
}

.fuse-dismiss:hover {
  background: var(--color-bg-hover);
}

.fuse-confirm-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background: var(--modal-overlay-bg);
  backdrop-filter: blur(var(--modal-backdrop-blur));
  -webkit-backdrop-filter: blur(var(--modal-backdrop-blur));
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-max);
  padding: var(--spacing-md);
}

.fuse-confirm-modal {
  background: var(--color-bg-elevated);
  border-radius: var(--modal-border-radius);
  border: 1px solid var(--color-border-primary);
  padding: var(--modal-padding);
  box-shadow: var(--modal-shadow);
  max-width: 440px;
  width: 100%;
  animation: modal-in 0.25s var(--ease-spring);
}

@keyframes modal-in {
  from { opacity: 0; transform: scale(0.95) translateY(8px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

.fuse-confirm-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.fuse-confirm-icon {
  font-size: var(--font-size-3xl);
}

.fuse-confirm-title {
  font-size: var(--font-size-xl);
  font-weight: 700;
  margin: 0;
}

.fuse-confirm-title.enable {
  color: var(--color-error-light);
}

.fuse-confirm-title.disable {
  color: var(--color-success);
}

.fuse-confirm-desc {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
  line-height: 1.6;
  margin: 0 0 var(--spacing-lg);
}

.fuse-confirm-actions {
  display: flex;
  gap: var(--spacing-md);
  justify-content: flex-end;
}

.fuse-confirm-btn {
  padding: var(--spacing-sm) var(--spacing-lg);
  border-radius: var(--radius-md);
  border: none;
  cursor: pointer;
  font-size: var(--font-size-base);
  font-weight: 600;
  transition: var(--button-transition);
  min-height: var(--button-min-height-touch);
}

.fuse-confirm-btn.cancel {
  background: var(--color-bg-active);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-primary);
}

.fuse-confirm-btn.cancel:hover {
  background: var(--color-bg-hover);
  border-color: var(--color-border-hover);
  color: var(--color-text-secondary);
}

.fuse-confirm-btn.enable {
  background: var(--color-error-bg);
  color: var(--color-error-light);
  border: 1px solid var(--color-error-border);
}

.fuse-confirm-btn.enable:hover {
  background: var(--color-error-hover);
  box-shadow: var(--shadow-glow-error);
}

.fuse-confirm-btn.disable {
  background: var(--color-success-bg);
  color: var(--color-success);
  border: 1px solid var(--color-success-border);
}

.fuse-confirm-btn.disable:hover {
  background: var(--color-success-hover);
  box-shadow: var(--shadow-glow-success);
}

@media (max-width: 768px) {
  .sidebar {
    width: 280px;
  }

  .header {
    padding: 0 0.75rem;
  }

  .header-right {
    gap: 0.375rem;
  }

  .status-text {
    display: none;
  }

  .emergency-text {
    display: none;
  }

  .emergency-button {
    padding: 0.375rem 0.5rem;
  }

  .system-status {
    padding: 0.375rem 0.5rem;
  }

  .user-name {
    display: none;
  }

  .user-btn svg {
    display: none;
  }

  .notification-panel {
    width: 280px;
    right: -40px;
  }

  .main-content.has-bottom-nav {
    padding-bottom: calc(var(--header-height) + env(safe-area-inset-bottom, 0px));
  }

  .bottom-nav-label {
    font-size: var(--font-size-xs);
  }

  .toast-container {
    right: 12px;
    left: 12px;
    max-width: none;
  }
}

@media (max-width: 480px) {
  .header {
    padding: 0 0.5rem;
  }

  .header-right {
    gap: 0.25rem;
  }

  .system-status {
    padding: 0.25rem 0.375rem;
  }

  .emergency-button {
    padding: 0.25rem 0.375rem;
  }

  .fuse-confirm-modal {
    padding: var(--spacing-lg) 20px;
  }

  .fuse-confirm-title {
    font-size: var(--font-size-lg);
  }

  .fuse-confirm-actions {
    flex-direction: column;
  }

  .fuse-confirm-btn {
    width: 100%;
    text-align: center;
  }

  .bottom-nav {
    height: calc(60px + env(safe-area-inset-bottom, 0px));
  }

  .bottom-nav-item {
    padding: var(--spacing-xs) 2px;
    min-height: var(--button-min-height-touch);
  }

  .bottom-nav-icon {
    font-size: var(--font-size-lg);
  }

  .bottom-nav-label {
    font-size: var(--font-size-xs);
  }

  .main-content.has-bottom-nav {
    padding-bottom: calc(68px + env(safe-area-inset-bottom, 0px));
  }

  .sidebar {
    width: var(--sidebar-width);
  }

  .notification-panel {
    width: calc(100vw - 1.5rem);
    right: -60px;
  }
}

@media (min-width: 769px) and (max-width: 1024px) {
  .sidebar.tablet-mode {
    width: 240px;
  }

  .header {
    padding: 0 1.25rem;
  }

  .header-right {
    gap: 0.5rem;
  }

  .system-status {
    padding: 0.375rem 0.625rem;
  }

  .status-text {
    font-size: var(--font-size-xs);
  }

  .emergency-button {
    padding: 0.375rem 0.75rem;
  }

  .emergency-text {
    font-size: var(--font-size-xs);
  }

  .main-content {
    max-width: 100%;
  }
}

@media (min-width: 769px) {
  .bottom-nav {
    display: none !important;
  }
}

.toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: var(--z-toast);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  max-width: 400px;
}

.toast-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md) 20px;
  background: var(--color-bg-elevated);
  border-left: 4px solid;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-primary);
  box-shadow: var(--shadow-card);
  animation: toastIn 0.3s var(--ease-spring);
  will-change: transform;
}

.toast-item.toast-leave-active {
  animation: toastOut 0.3s var(--ease-out) forwards;
}

@keyframes toastIn {
  from {
    opacity: 0;
    transform: translateX(100%);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes toastOut {
  from {
    opacity: 1;
    transform: translateX(0);
  }
  to {
    opacity: 0;
    transform: translateX(100%);
  }
}

.toast-icon {
  font-size: var(--font-size-xl);
  flex-shrink: 0;
}

.toast-message {
  flex: 1;
  color: var(--color-text-secondary);
  font-size: var(--font-size-base);
  line-height: 1.5;
}

.toast-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-lg);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: var(--button-transition);
  flex-shrink: 0;
}

.toast-close:hover {
  background: var(--color-bg-active);
  color: var(--color-text-secondary);
}

@media (max-width: 768px) {
  .toast-container {
    left: var(--spacing-md);
    right: var(--spacing-md);
    top: calc(var(--spacing-md) + env(safe-area-inset-top, 0px));
    max-width: none;
  }

  .toast-item {
    padding: 14px var(--spacing-md);
  }
}

@media (prefers-reduced-motion: reduce) {
  .sidebar {
    transition: none;
  }

  .sidebar-backdrop {
    animation: none;
  }

  .fuse-banner {
    animation: none;
  }

  .fuse-alert {
    animation: none;
  }

  .system-status.fused .status-dot {
    animation: none;
  }

  .fuse-overlay {
    animation: none;
  }

  .fuse-confirm-modal {
    animation: none;
  }

  .toast-item {
    animation: none;
  }

  .toast-item.toast-leave-active {
    animation: none;
  }

  .fuse-button.active {
    animation: none;
  }

  .fuse-button-mini.active {
    animation: none;
  }

  .emergency-button:hover {
    transform: none;
  }

  .page-fade-enter-active,
  .page-fade-leave-active,
  .page-slide-left-enter-active,
  .page-slide-left-leave-active,
  .page-slide-right-enter-active,
  .page-slide-right-leave-active {
    transition: none;
  }

  .dropdown-enter-active,
  .dropdown-leave-active {
    animation: none;
  }

  .fade-text-enter-active,
  .fade-text-leave-active {
    transition: none;
  }

  .notification-badge {
    animation: none;
  }

  .main-wrapper {
    transition: none;
  }

  .active-indicator {
    animation: none;
  }
}
</style>
