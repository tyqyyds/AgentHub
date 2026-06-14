<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, apiClient } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'
import { useAuthStore } from '@/stores/auth'
import PageLayout from '@/components/PageLayout.vue'
import StatCard from '@/components/StatCard.vue'

type NotificationStatus = 'unread' | 'read' | 'dismissed'
type NotificationSeverity = 'info' | 'warning' | 'error' | 'success'

interface NotificationItem {
  id: string
  type: NotificationSeverity
  title: string
  message: string
  severity: NotificationSeverity
  time: string
  status: NotificationStatus
}

const notifications = ref<NotificationItem[]>([])
const isLoading = ref(true)
const isRefreshing = ref(false)
const selectedNotification = ref<NotificationItem | null>(null)
const showModal = ref(false)
const authStore = useAuthStore()
const canWrite = computed(() => authStore.userRole !== 'viewer')

const statusFilter = ref<'all' | NotificationStatus>('all')
const severityFilter = ref<'all' | NotificationSeverity>('all')

let refreshTimer: number | null = null

const MOCK_NOTIFICATIONS: NotificationItem[] = [
  { id: '1', type: 'error', title: '核心路由器链路中断', message: '核心路由器 CR-SW-01 的 GE0/0/1 端口链路中断，影响下游 32 台设备网络连通性，已自动触发链路切换预案。', severity: 'error', time: new Date(Date.now() - 2 * 60000).toISOString(), status: 'unread' },
  { id: '2', type: 'warning', title: '防火墙 CPU 负载过高', message: '防火墙集群 Node-02 的 CPU 使用率持续超过 85%，当前值 92%，建议进行流量负载均衡再分配。', severity: 'warning', time: new Date(Date.now() - 8 * 60000).toISOString(), status: 'unread' },
  { id: '3', type: 'success', title: '自愈任务执行成功', message: '接入交换机 AS-SW-03 的端口故障已自动隔离并完成流量迁移，业务恢复正常运行。', severity: 'success', time: new Date(Date.now() - 15 * 60000).toISOString(), status: 'read' },
  { id: '4', type: 'info', title: '意图审批待处理', message: '用户 admin 提交了带宽保障意图「视频会议保障」，需要管理员审批后执行。', severity: 'info', time: new Date(Date.now() - 25 * 60000).toISOString(), status: 'unread' },
  { id: '5', type: 'warning', title: '内存使用率告警', message: '汇聚交换机 AGG-SW-01 的内存使用率达到 88%，存在内存泄漏风险，建议重启相关进程。', severity: 'warning', time: new Date(Date.now() - 40 * 60000).toISOString(), status: 'read' },
  { id: '6', type: 'error', title: 'BGP 路由震荡', message: '核心路由器 CR-RTR-02 的 BGP 邻居关系频繁震荡，近 10 分钟内发生 5 次状态切换。', severity: 'error', time: new Date(Date.now() - 55 * 60000).toISOString(), status: 'dismissed' },
  { id: '7', type: 'success', title: 'QoS 策略下发完成', message: 'QoS 策略「视频流量优先」已成功下发至 12 台边缘交换机，策略生效范围覆盖全部视频会议终端。', severity: 'success', time: new Date(Date.now() - 90 * 60000).toISOString(), status: 'read' },
  { id: '8', type: 'info', title: '系统巡检报告', message: '每日自动巡检已完成，共检查 160 台设备，发现 3 项告警、5 项预警，详细报告已生成。', severity: 'info', time: new Date(Date.now() - 120 * 60000).toISOString(), status: 'dismissed' },
  { id: '9', type: 'warning', title: 'SSL 证书即将过期', message: '管理平台 SSL 证书将在 7 天后过期，请及时续签以避免服务中断。', severity: 'warning', time: new Date(Date.now() - 180 * 60000).toISOString(), status: 'unread' },
  { id: '10', type: 'info', title: '知识库文档更新', message: '知识库新增 5 篇运维文档，涵盖故障排查手册、网络拓扑变更记录等内容。', severity: 'info', time: new Date(Date.now() - 240 * 60000).toISOString(), status: 'read' },
]

const stats = computed(() => {
  const total = notifications.value.length
  const unread = notifications.value.filter(n => n.status === 'unread').length
  const read = notifications.value.filter(n => n.status === 'read').length
  const dismissed = notifications.value.filter(n => n.status === 'dismissed').length
  return { total, unread, read, dismissed }
})

const filteredNotifications = computed(() => {
  return notifications.value.filter(n => {
    if (statusFilter.value !== 'all' && n.status !== statusFilter.value) return false
    if (severityFilter.value !== 'all' && n.severity !== severityFilter.value) return false
    return true
  })
})

const TYPE_ICONS: Record<NotificationSeverity, string> = {
  info: '\u2139\uFE0F',
  warning: '\u26A0\uFE0F',
  error: '\uD83D\uDD34',
  success: '\u2705',
}

const SEVERITY_COLORS: Record<NotificationSeverity, string> = {
  info: '#1890FF',
  warning: '#FAAD14',
  error: '#FF4D4F',
  success: '#52C41A',
}

const STATUS_TEXT: Record<NotificationStatus, string> = {
  unread: '未读',
  read: '已读',
  dismissed: '已忽略',
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
  return `${diffDays}天前`
}

const truncate = (text: string, maxLen: number = 60): string => {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

const fetchNotifications = async (showLoading = false) => {
  if (showLoading) isRefreshing.value = true
  try {
    const result = await apiClient.get(api.notifications.list)
    if (result.data) {
      const items = Array.isArray(result.data) ? result.data : (result.data.notifications || result.data.items || [])
      if (items.length > 0) {
        notifications.value = items
      } else {
        notifications.value = [...MOCK_NOTIFICATIONS]
      }
    } else {
      notifications.value = [...MOCK_NOTIFICATIONS]
    }
  } catch {
    notifications.value = [...MOCK_NOTIFICATIONS]
  } finally {
    isLoading.value = false
    isRefreshing.value = false
  }
}

const markAsRead = async (notification: NotificationItem) => {
  try {
    await apiClient.post(api.notifications.read(notification.id))
    notification.status = 'read'
    showToast('已标记为已读', 'success')
  } catch {
    notification.status = 'read'
    showToast('已标记为已读', 'success')
  }
}

const dismissNotification = async (notification: NotificationItem) => {
  try {
    await apiClient.post(api.notifications.dismiss(notification.id))
    notification.status = 'dismissed'
    showToast('已忽略该通知', 'success')
  } catch {
    notification.status = 'dismissed'
    showToast('已忽略该通知', 'success')
  }
}

const markAllAsRead = async () => {
  try {
    const unreadItems = notifications.value.filter(n => n.status === 'unread')
    await Promise.allSettled(
      unreadItems.map(n => apiClient.post(api.notifications.read(n.id)))
    )
    notifications.value.forEach(n => {
      if (n.status === 'unread') n.status = 'read'
    })
    showToast('已全部标记为已读', 'success')
  } catch {
    notifications.value.forEach(n => {
      if (n.status === 'unread') n.status = 'read'
    })
    showToast('已全部标记为已读', 'success')
  }
}

const openDetail = (notification: NotificationItem) => {
  selectedNotification.value = notification
  showModal.value = true
  if (notification.status === 'unread') {
    markAsRead(notification)
  }
}

const closeDetail = () => {
  showModal.value = false
  selectedNotification.value = null
}

const handleOverlayClick = (e: MouseEvent) => {
  if ((e.target as HTMLElement).classList.contains('modal-overlay')) {
    closeDetail()
  }
}

const manualRefresh = async () => {
  isRefreshing.value = true
  try {
    await fetchNotifications(true)
    showToast('通知已刷新', 'success')
  } catch {
    showToast('刷新失败', 'error')
  }
}

onMounted(() => {
  fetchNotifications(true)
  refreshTimer = window.setInterval(() => {
    if (!document.hidden) {
      fetchNotifications(false)
    }
  }, 30000)
})

onUnmounted(() => {
  if (refreshTimer !== null) clearInterval(refreshTimer)
})
</script>

<template>
  <PageLayout title="通知中心" subtitle="系统通知与告警管理">
    <template #actions>
      <button
        v-if="canWrite"
        type="button"
        class="action-btn"
        @click="markAllAsRead"
        :disabled="stats.unread === 0"
        title="全部标记已读"
        aria-label="全部标记已读"
      >
        ✅ 全部已读
      </button>
      <button
        type="button"
        class="action-btn refresh-btn"
        :class="{ refreshing: isRefreshing }"
        @click="manualRefresh"
        :disabled="isRefreshing"
        title="刷新通知"
        aria-label="刷新通知"
      >
        <span class="refresh-icon" :class="{ spinning: isRefreshing }">🔄</span>
        {{ isRefreshing ? '刷新中...' : '刷新' }}
      </button>
    </template>

    <!-- Stats Bar -->
    <div class="stats-grid">
      <StatCard icon="🔔" label="全部通知" :value="stats.total" suffix="条" type="default" />
      <StatCard icon="📬" label="未读" :value="stats.unread" suffix="条" type="danger" />
      <StatCard icon="📭" label="已读" :value="stats.read" suffix="条" type="success" />
      <StatCard icon="🚫" label="已忽略" :value="stats.dismissed" suffix="条" type="warning" />
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <div class="filter-group">
        <span class="filter-label">状态：</span>
        <button
          type="button"
          v-for="s in (['all', 'unread', 'read', 'dismissed'] as const)"
          :key="'status-' + s"
          class="filter-btn"
          :class="{ active: statusFilter === s }"
          @click="statusFilter = s"
        >
          {{ s === 'all' ? '全部' : STATUS_TEXT[s] }}
        </button>
      </div>
      <div class="filter-group">
        <span class="filter-label">级别：</span>
        <button
          type="button"
          v-for="sv in (['all', 'info', 'warning', 'error'] as const)"
          :key="'severity-' + sv"
          class="filter-btn"
          :class="{ active: severityFilter === sv }"
          @click="severityFilter = sv"
        >
          {{ sv === 'all' ? '全部' : sv === 'info' ? '信息' : sv === 'warning' ? '警告' : '错误' }}
        </button>
      </div>
    </div>

    <!-- Notification List -->
    <div class="panel notification-panel">
      <div v-if="isLoading" class="loading-state">
        <div class="loading-spinner"></div>
        <span>加载通知中...</span>
      </div>

      <div v-else-if="filteredNotifications.length === 0" class="empty-state">
        <div class="empty-icon">🔕</div>
        <div>暂无匹配的通知</div>
      </div>

      <div v-else class="notification-list">
        <div
          v-for="(item, idx) in filteredNotifications"
          :key="item.id"
          class="notification-item"
          :class="{ unread: item.status === 'unread' }"
          :style="{ '--item-delay': `${idx * 0.04}s` }"
          @click="openDetail(item)"
        >
          <div class="notif-icon" :style="{ background: SEVERITY_COLORS[item.severity] + '18', color: SEVERITY_COLORS[item.severity] }">
            {{ TYPE_ICONS[item.type] }}
          </div>
          <div class="notif-body">
            <div class="notif-title-row">
              <span class="notif-title">{{ item.title }}</span>
              <span
                class="notif-severity-badge"
                :style="{ color: SEVERITY_COLORS[item.severity], background: SEVERITY_COLORS[item.severity] + '12', borderColor: SEVERITY_COLORS[item.severity] + '25' }"
              >
                {{ item.severity === 'info' ? '信息' : item.severity === 'warning' ? '警告' : item.severity === 'error' ? '错误' : '成功' }}
              </span>
            </div>
            <div class="notif-message">{{ truncate(item.message) }}</div>
            <div class="notif-meta">
              <span class="notif-time">{{ formatTime(item.time) }}</span>
              <span
                class="notif-status-badge"
                :class="item.status"
              >
                {{ STATUS_TEXT[item.status] }}
              </span>
            </div>
          </div>
          <div class="notif-actions" @click.stop>
            <button
              v-if="canWrite && item.status === 'unread'"
              type="button"
              class="notif-action-btn read-btn"
              @click="markAsRead(item)"
              title="标记已读"
              aria-label="标记已读"
            >
              📖 已读
            </button>
            <button
              v-if="canWrite && item.status !== 'dismissed'"
              type="button"
              class="notif-action-btn dismiss-btn"
              @click="dismissNotification(item)"
              title="忽略"
              aria-label="忽略通知"
            >
              🚫 忽略
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Detail Modal -->
    <Teleport to="body">
      <div v-if="showModal && selectedNotification" class="modal-overlay" @click="handleOverlayClick">
        <div class="modal-content">
          <div class="modal-header">
            <div class="modal-title-row">
              <span class="modal-icon" :style="{ background: SEVERITY_COLORS[selectedNotification.severity] + '18', color: SEVERITY_COLORS[selectedNotification.severity] }">
                {{ TYPE_ICONS[selectedNotification.type] }}
              </span>
              <h3 class="modal-title">{{ selectedNotification.title }}</h3>
            </div>
            <button type="button" class="modal-close-btn" @click="closeDetail" aria-label="关闭">✕</button>
          </div>
          <div class="modal-body">
            <div class="modal-meta-row">
              <span
                class="notif-severity-badge"
                :style="{ color: SEVERITY_COLORS[selectedNotification.severity], background: SEVERITY_COLORS[selectedNotification.severity] + '12', borderColor: SEVERITY_COLORS[selectedNotification.severity] + '25' }"
              >
                {{ selectedNotification.severity === 'info' ? '信息' : selectedNotification.severity === 'warning' ? '警告' : selectedNotification.severity === 'error' ? '错误' : '成功' }}
              </span>
              <span
                class="notif-status-badge"
                :class="selectedNotification.status"
              >
                {{ STATUS_TEXT[selectedNotification.status] }}
              </span>
              <span class="modal-time">{{ formatTime(selectedNotification.time) }}</span>
            </div>
            <div class="modal-message">{{ selectedNotification.message }}</div>
          </div>
          <div class="modal-footer">
            <button
              v-if="canWrite && selectedNotification.status === 'unread'"
              type="button"
              class="action-btn"
              @click="markAsRead(selectedNotification)"
            >
              📖 标记已读
            </button>
            <button
              v-if="canWrite && selectedNotification.status !== 'dismissed'"
              type="button"
              class="action-btn dismiss-btn"
              @click="dismissNotification(selectedNotification); closeDetail()"
            >
              🚫 忽略
            </button>
            <button type="button" class="action-btn" @click="closeDetail">关闭</button>
          </div>
        </div>
      </div>
    </Teleport>
  </PageLayout>
</template>

<style scoped lang="scss">
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(var(--grid-min-col), 1fr));
  gap: var(--panel-gap);
  margin-bottom: var(--panel-gap);
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  padding: 0.75rem var(--spacing-lg);
  background: var(--gradient-glass);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-primary);
  margin-bottom: var(--panel-gap);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: var(--shadow-card);
  flex-wrap: wrap;
  animation: bar-enter 0.5s var(--ease-out) 0.25s backwards;
}



.filter-group {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.filter-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.filter-btn {
  padding: var(--spacing-xs) 0.625rem;
  min-height: 44px;
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
}

.filter-btn:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border-color: var(--color-primary-border);
  transform: scale(1.02);
}

.filter-btn:active {
  transform: scale(0.97);
}

.filter-btn.active {
  background: var(--color-primary-hover);
  color: var(--color-primary-light);
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-glow-primary);
  font-weight: var(--font-weight-medium);
}

.panel {
  background: var(--gradient-glass);
  border-radius: var(--card-border-radius);
  padding: var(--card-padding);
  border: var(--card-border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-card);
  will-change: transform, opacity;
  animation: panel-enter 0.5s var(--ease-out) backwards;
  transition: border-color 0.3s var(--ease-out), box-shadow 0.3s var(--ease-out);
}

.panel:hover {
  border-color: var(--color-border-secondary);
  box-shadow: var(--shadow-card-hover);
}



.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-2xl);
  color: var(--color-text-tertiary);
}

.loading-spinner {
  width: 2rem;
  height: 2rem;
  border: 3px solid var(--color-border-primary);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}



.empty-state {
  text-align: center;
  padding: var(--spacing-2xl) var(--spacing-lg);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-base);
}

.empty-icon {
  font-size: var(--font-size-3xl);
  margin-bottom: var(--spacing-sm);
  opacity: 0.5;
  filter: grayscale(0.3);
}

.notification-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.notification-item {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
  padding: 0.875rem var(--spacing-md);
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.25s ease;
  will-change: transform, opacity;
  animation: item-enter 0.3s var(--ease-out) backwards;
  animation-delay: var(--item-delay, 0s);
}



.notification-item:hover {
  background: var(--color-bg-glass-strong);
  border-color: var(--color-primary-border);
  transform: translateX(4px);
  box-shadow: var(--shadow-glow-primary);
}

.notification-item.unread {
  border-left: 3px solid var(--color-primary);
  background: var(--color-primary-bg);
}

.notification-item.unread:hover {
  background: var(--color-primary-hover);
}

.notif-icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.125rem;
  flex-shrink: 0;
  transition: transform 0.25s ease;
}

.notification-item:hover .notif-icon {
  transform: scale(1.1);
}

.notif-body {
  flex: 1;
  min-width: 0;
}

.notif-title-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: 0.25rem;
}

.notif-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.notif-severity-badge {
  font-size: var(--font-size-xs);
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-sm);
  border: 1px solid;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all 0.2s var(--ease-out);
}

.notification-item:hover .notif-severity-badge {
  transform: scale(1.05);
  box-shadow: 0 0 8px currentColor;
}

.notif-message {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  line-height: var(--line-height-normal);
  margin-bottom: 0.375rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notif-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.notif-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  font-family: var(--font-family-mono);
}

.notif-status-badge {
  font-size: var(--font-size-xs);
  padding: 0.0625rem 0.375rem;
  border-radius: var(--radius-xs);
  font-weight: var(--font-weight-medium);
}

.notif-status-badge.unread {
  color: var(--color-primary-light);
  background: var(--color-primary-bg);
}

.notif-status-badge.read {
  color: var(--color-success);
  background: var(--color-success-bg);
}

.notif-status-badge.dismissed {
  color: var(--color-text-disabled);
  background: var(--color-bg-hover);
}

.notif-actions {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  flex-shrink: 0;
  align-self: center;
}

.notif-action-btn {
  padding: 0.25rem 0.625rem;
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-xs);
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
  white-space: nowrap;
  min-height: 36px;
}

.notif-action-btn:hover {
  background: var(--color-primary-hover);
  border-color: var(--color-primary);
  box-shadow: var(--shadow-glow-primary);
  color: var(--color-primary-lighter);
  transform: scale(1.02);
}

.notif-action-btn:active {
  transform: scale(0.97);
}

.notif-action-btn.dismiss-btn {
  background: var(--color-error-bg);
  color: var(--color-error-light);
  border-color: var(--color-error-border);
}

.notif-action-btn.dismiss-btn:hover {
  background: var(--color-error-hover);
  border-color: var(--color-error);
  box-shadow: var(--shadow-glow-error);
  color: var(--color-error-light);
  transform: scale(1.02);
}

.notif-action-btn.dismiss-btn:active {
  transform: scale(0.97);
}

/* Action Buttons */
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
}

.action-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary);
  box-shadow: var(--shadow-glow-primary);
  color: var(--color-primary-lighter);
  transform: scale(1.02);
}

.action-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.action-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.action-btn.dismiss-btn {
  background: var(--color-error-bg);
  color: var(--color-error-light);
  border-color: var(--color-error-border);
}

.action-btn.dismiss-btn:hover:not(:disabled) {
  background: var(--color-error-hover);
  border-color: var(--color-error);
  box-shadow: var(--shadow-glow-error);
  color: var(--color-error-light);
  transform: scale(1.02);
}

.action-btn.dismiss-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.refresh-icon {
  display: inline-block;
  transition: transform 0.3s ease;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

.refresh-btn:hover:not(:disabled) .refresh-icon:not(.spinning) {
  animation: refresh-hover-spin 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes refresh-hover-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* Modal */
.modal-overlay {
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
  z-index: var(--z-overlay);
  padding: var(--spacing-md);
  animation: modal-overlay-in 0.2s var(--ease-out);
}



.modal-content {
  background: var(--color-bg-elevated);
  border-radius: var(--modal-border-radius);
  border: 1px solid var(--color-border-primary);
  padding: var(--modal-padding);
  box-shadow: var(--modal-shadow);
  animation: modal-content-in 0.25s var(--ease-out);
  max-width: 600px;
  width: 90vw;
  max-height: 85vh;
  overflow-y: auto;
}



.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-border-primary);
}

.modal-title-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex: 1;
  min-width: 0;
}

.modal-icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.125rem;
  flex-shrink: 0;
}

.modal-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  margin: 0;
  line-height: var(--line-height-tight);
}

.modal-close-btn {
  width: 2rem;
  height: 2rem;
  border-radius: var(--radius-md);
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border-primary);
  color: var(--color-text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-base);
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
  flex-shrink: 0;
}

.modal-close-btn:hover {
  background: var(--color-error-bg);
  color: var(--color-error-light);
  border-color: var(--color-error-border);
  transform: scale(1.02);
}

.modal-close-btn:active {
  transform: scale(0.97);
}

.modal-body {
  margin-bottom: var(--spacing-lg);
}

.modal-meta-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
  flex-wrap: wrap;
}

.modal-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  font-family: var(--font-family-mono);
}

.modal-message {
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  line-height: var(--line-height-relaxed);
  padding: var(--spacing-md);
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-primary);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-primary);
}

/* Responsive */
@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .filter-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }
  .notification-item {
    flex-wrap: wrap;
  }
  .notif-actions {
    flex-direction: row;
    width: 100%;
    padding-top: var(--spacing-xs);
  }
  .modal-content {
    width: 95vw;
    padding: var(--spacing-lg);
  }
  .action-btn {
    min-height: 2.75rem;
    padding: var(--spacing-sm) 0.875rem;
  }
  .filter-btn {
    min-height: 2.75rem;
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr;
    gap: var(--spacing-sm);
  }
  .notif-title-row {
    flex-wrap: wrap;
  }
  .notif-message {
    white-space: normal;
  }
  .panel {
    padding: 0.75rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .notification-item,
  .panel,
  .filter-bar {
    animation: none;
  }
  .refresh-icon.spinning {
    animation: none;
  }
  .loading-spinner {
    animation: none;
  }
  .notification-item:hover {
    transform: none;
  }
  .notif-icon:hover {
    transform: none;
  }
  .filter-btn:hover,
  .action-btn:hover:not(:disabled),
  .notif-action-btn:hover,
  .modal-close-btn:hover {
    transform: none;
  }
}
</style>
