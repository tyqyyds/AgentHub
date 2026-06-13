<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'

interface Notification {
  id: number
  title: string
  content: string
  type: 'system' | 'alert' | 'task' | 'approval'
  read: boolean
  createdAt: string
  priority: 'high' | 'medium' | 'low'
}

const loading = ref(false)
const notifications = ref<Notification[]>([
  { id: 1, title: '核心路由器CPU告警', content: '核心路由器R1 CPU利用率超过90%，请及时处理', type: 'alert', read: false, createdAt: '5分钟前', priority: 'high' },
  { id: 2, title: '工单审批请求', content: '工单WO-002需要您的审批：防火墙规则冲突', type: 'approval', read: false, createdAt: '15分钟前', priority: 'high' },
  { id: 3, title: '自愈任务完成', content: '链路故障自愈剧本执行完成，已切换至备份路径', type: 'task', read: false, createdAt: '30分钟前', priority: 'medium' },
  { id: 4, title: '系统维护通知', content: '计划于今晚22:00进行系统升级维护', type: 'system', read: true, createdAt: '2小时前', priority: 'low' },
  { id: 5, title: 'SLA预警', content: '配置变更成功率低于目标值，当前98.5%', type: 'alert', read: true, createdAt: '3小时前', priority: 'medium' }
])

const filterType = ref<'all' | 'unread'>('all')
const showSettings = ref(false)
const settings = ref({
  system: true,
  alert: true,
  task: true,
  approval: true
})

const filteredNotifications = computed(() => {
  if (filterType.value === 'unread') return notifications.value.filter(n => !n.read)
  return notifications.value
})

const unreadCount = computed(() => notifications.value.filter(n => !n.read).length)

function getTypeLabel(t: string) {
  return t === 'system' ? '系统' : t === 'alert' ? '告警' : t === 'task' ? '任务' : '审批'
}

function getTypeIcon(t: string) {
  return t === 'system' ? '🔔' : t === 'alert' ? '⚠️' : t === 'task' ? '✅' : '📝'
}

function markAsRead(n: Notification) {
  n.read = true
}

function markAllAsRead() {
  notifications.value.forEach(n => { n.read = true })
}

onMounted(() => {
  // TODO: 调用API获取通知列表
})
</script>

<template>
  <div class="notifications">
    <h1 class="page-title">通知中心</h1>

    <div class="toolbar">
      <div class="toolbar-left">
        <div class="filter-tabs">
          <button :class="['tab', { active: filterType === 'all' }]" @click="filterType = 'all'">全部</button>
          <button :class="['tab', { active: filterType === 'unread' }]" @click="filterType = 'unread'">
            未读 <span v-if="unreadCount" class="badge">{{ unreadCount }}</span>
          </button>
        </div>
      </div>
      <div class="toolbar-right">
        <button class="btn-text" @click="markAllAsRead">全部已读</button>
        <button class="btn-text" @click="showSettings = !showSettings">⚙️ 设置</button>
      </div>
    </div>

    <div v-if="showSettings" class="settings-panel">
      <h3 class="settings-title">通知设置</h3>
      <div class="settings-grid">
        <label v-for="(enabled, type) in settings" :key="type" class="setting-item">
          <input type="checkbox" v-model="settings[type as keyof typeof settings]" />
          <span>{{ getTypeLabel(type) }}通知</span>
        </label>
      </div>
    </div>

    <div class="notification-list">
      <div
        v-for="n in filteredNotifications"
        :key="n.id"
        :class="['notification-card', { unread: !n.read }]"
        @click="markAsRead(n)"
      >
        <div class="notification-icon">{{ getTypeIcon(n.type) }}</div>
        <div class="notification-body">
          <div class="notification-header">
            <span class="notification-title">{{ n.title }}</span>
            <span :class="['type-tag', n.type]">{{ getTypeLabel(n.type) }}</span>
            <span v-if="n.priority === 'high'" class="priority-dot"></span>
          </div>
          <div class="notification-content">{{ n.content }}</div>
          <div class="notification-time">{{ n.createdAt }}</div>
        </div>
        <div v-if="!n.read" class="unread-dot"></div>
      </div>
    </div>

    <div v-if="filteredNotifications.length === 0" class="empty-state">
      <div class="empty-icon">📭</div>
      <div class="empty-text">暂无通知</div>
    </div>
  </div>
</template>

<style scoped>
.page-title { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); color: var(--color-white); margin-bottom: var(--spacing-2xl); }

.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-lg); }

.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; gap: var(--spacing-md); }

.filter-tabs { display: flex; gap: var(--spacing-2xs); background: rgba(var(--color-bg-elevated-rgb), 0.6); border-radius: var(--radius-lg); padding: var(--spacing-2xs); }

.tab {
  padding: var(--spacing-sm) var(--spacing-lg);
  border: none;
  background: transparent;
  color: var(--color-text-tertiary);
  border-radius: var(--radius-lg);
  cursor: pointer;
  font-size: var(--font-size-sm);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.tab.active { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); }

.badge {
  font-size: var(--font-size-xs);
  padding: 1px var(--spacing-xs);
  border-radius: var(--radius-full);
  background: var(--color-error);
  color: var(--color-white);
  font-weight: var(--font-weight-semibold);
}

.btn-text {
  background: none;
  border: none;
  color: var(--color-info-light);
  font-size: var(--font-size-sm);
  cursor: pointer;
  padding: var(--spacing-2xs) var(--spacing-sm);
}

.btn-text:hover { text-decoration: underline; }

.settings-panel {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-xl);
  padding: var(--spacing-lg) var(--spacing-xl);
  margin-bottom: var(--spacing-lg);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
}

.settings-title { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); color: var(--color-white); margin-bottom: var(--spacing-md); }
.settings-grid { display: flex; gap: var(--spacing-2xl); }

.setting-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.notification-list { display: flex; flex-direction: column; gap: var(--spacing-sm); }

.notification-card {
  display: flex;
  gap: var(--spacing-md-lg);
  padding: var(--spacing-lg) var(--spacing-xl);
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.notification-card:hover { border-color: rgba(var(--color-primary-rgb), 0.3); }
.notification-card.unread { border-left: 3px solid var(--color-primary); }

.notification-icon { font-size: 20px; flex-shrink: 0; margin-top: 2px; }

.notification-body { flex: 1; }

.notification-header { display: flex; align-items: center; gap: var(--spacing-sm); margin-bottom: var(--spacing-xs); }
.notification-title { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); color: var(--color-white); }

.type-tag { font-size: var(--font-size-xs); padding: var(--spacing-2xs) var(--spacing-sm); border-radius: var(--radius-lg); }
.type-tag.system { background: rgba(var(--color-text-quaternary-rgb), 0.2); color: var(--color-text-tertiary); }
.type-tag.alert { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); }
.type-tag.task { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); }
.type-tag.approval { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); }

.priority-dot { width: var(--spacing-sm); height: var(--spacing-sm); border-radius: 50%; background: var(--color-error); animation: blink 1s infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.notification-content { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-bottom: var(--spacing-xs); }
.notification-time { font-size: var(--font-size-sm); color: var(--color-text-quaternary); }

.unread-dot { width: var(--spacing-sm); height: var(--spacing-sm); border-radius: 50%; background: var(--color-primary); flex-shrink: 0; margin-top: var(--spacing-xs); }

.empty-state { display: flex; flex-direction: column; align-items: center; padding: 60px; gap: var(--spacing-md); }
.empty-icon { font-size: 48px; }
.empty-text { font-size: var(--font-size-base); color: var(--color-text-quaternary); }
</style>
