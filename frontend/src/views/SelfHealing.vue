<script setup lang="ts">
import { ref } from 'vue'

const healingMode = ref('suggested')
const healingEvents = ref([
  {
    id: 'SH-001',
    type: 'bandwidth',
    severity: 'high',
    title: '视频会议带宽不足',
    description: '检测到研发子网视频会议流量带宽低于200M阈值，当前带宽150M',
    suggestedAction: '执行非视频流量限速50%，释放约50M带宽',
    status: 'completed',
    timestamp: '2026-05-21 08:30:00',
    targetDevice: 'Switch-A1',
    executedBy: '系统自动'
  },
  {
    id: 'SH-002',
    type: 'link',
    severity: 'medium',
    title: '链路A丢包率过高',
    description: '链路A丢包率>5%，影响网络稳定性',
    suggestedAction: '建议执行流量切换至备用链路B',
    status: 'pending',
    timestamp: '2026-05-21 09:15:00',
    targetDevice: 'Router-C1',
    executedBy: null
  },
  {
    id: 'SH-003',
    type: 'acl',
    severity: 'low',
    title: 'ACL规则冲突检测',
    description: '检测到新配置ACL规则与现有规则存在潜在冲突',
    suggestedAction: '建议审查并调整ACL规则优先级',
    status: 'pending',
    timestamp: '2026-05-21 10:00:00',
    targetDevice: 'Firewall-B1',
    executedBy: null
  }
])

interface HealingEvent {
  id: string
  type: string
  severity: string
  title: string
  description: string
  suggestedAction: string
  status: string
  timestamp: string
  targetDevice: string
  executedBy: string | null
}

const executeAction = (event: HealingEvent) => {
  const index = healingEvents.value.findIndex(e => e.id === event.id)
  if (index !== -1) {
    healingEvents.value[index].status = 'completed'
    healingEvents.value[index].executedBy = '管理员'
  }
}

const rejectAction = (event: HealingEvent) => {
  const index = healingEvents.value.findIndex(e => e.id === event.id)
  if (index !== -1) {
    healingEvents.value[index].status = 'rejected'
  }
}
</script>

<template>
  <div class="self-healing-container">
    <div class="page-header">
      <h1 class="page-title">故障与自愈中心</h1>
      <button class="rollback-btn">
        <span class="rollback-icon">🔴</span>
        一键回滚
      </button>
    </div>
    
    <div class="mode-selector">
      <span class="mode-label">自愈模式：</span>
      <button
        v-for="mode in [
          { value: 'auto', label: '全自动' },
          { value: 'suggested', label: '建议模式' },
          { value: 'alert', label: '仅告警' }
        ]"
        :key="mode.value"
        :class="['mode-btn', { active: healingMode === mode.value }]"
        @click="healingMode = mode.value"
      >
        {{ mode.label }}
      </button>
    </div>
    
    <div class="events-grid">
      <div
        v-for="event in healingEvents"
        :key="event.id"
        :class="['event-card', event.severity, event.status]"
      >
        <div class="event-header">
          <div class="event-type">
            <span class="type-icon">{{ event.type === 'bandwidth' ? '📊' : event.type === 'link' ? '🔗' : '🛡️' }}</span>
            <span class="type-text">{{ event.type === 'bandwidth' ? '带宽保障' : event.type === 'link' ? '链路故障' : '安全规则' }}</span>
          </div>
          <span :class="['severity-badge', event.severity]">
            {{ event.severity === 'high' ? '高' : event.severity === 'medium' ? '中' : '低' }}
          </span>
        </div>
        
        <h3 class="event-title">{{ event.title }}</h3>
        <p class="event-description">{{ event.description }}</p>
        
        <div class="suggested-action">
          <span class="action-label">💡 建议动作：</span>
          <span class="action-text">{{ event.suggestedAction }}</span>
        </div>
        
        <div class="event-meta">
          <div class="meta-item">
            <span class="meta-label">目标设备：</span>
            <span class="meta-value">{{ event.targetDevice }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">时间：</span>
            <span class="meta-value">{{ event.timestamp }}</span>
          </div>
          <div v-if="event.executedBy" class="meta-item">
            <span class="meta-label">执行者：</span>
            <span class="meta-value">{{ event.executedBy }}</span>
          </div>
        </div>
        
        <div class="event-status-bar">
          <span :class="['status-tag', event.status]">
            {{ event.status === 'completed' ? '已完成' : event.status === 'pending' ? '待处理' : '已拒绝' }}
          </span>
        </div>
        
        <div v-if="event.status === 'pending'" class="event-actions">
          <button class="action-btn primary" @click="executeAction(event)">
            执行建议
          </button>
          <button class="action-btn secondary" @click="rejectAction(event)">
            拒绝
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2xl);
}

.page-title {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-white);
}

.rollback-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md) var(--spacing-xl);
  background: linear-gradient(135deg, var(--color-error) 0%, #FF7875 100%);
  color: var(--color-white);
  border: none;
  border-radius: 10px;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 var(--spacing-2xs) 14px rgba(var(--color-error-rgb), 0.4);
}

.rollback-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 var(--spacing-xs) var(--spacing-xl) rgba(var(--color-error-rgb), 0.5);
}

.rollback-icon {
  font-size: var(--font-size-xl);
}

.mode-selector {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-2xl);
  padding: var(--spacing-lg) var(--spacing-xl);
  background: rgba(var(--color-bg-container-rgb), 0.6);
  border-radius: var(--radius-lg);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
}

.mode-label {
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

.mode-btn {
  padding: 10px var(--spacing-xl);
  background: rgba(var(--color-white-rgb), 0.1);
  color: var(--color-text-tertiary);
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all 0.3s ease;
}

.mode-btn:hover {
  background: rgba(var(--color-primary-rgb), 0.2);
  color: var(--color-text-secondary);
}

.mode-btn.active {
  background: var(--gradient-primary);
  color: var(--color-white);
}

.events-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: var(--spacing-xl);
}

.event-card {
  background: rgba(var(--color-bg-container-rgb), 0.6);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  border-left: 4px solid;
}

.event-card.high {
  border-left-color: var(--color-error);
}

.event-card.medium {
  border-left-color: var(--color-warning);
}

.event-card.low {
  border-left-color: var(--color-success);
}

.event-card.rejected {
  opacity: 0.6;
}

.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.event-type {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.type-icon {
  font-size: var(--font-size-lg);
}

.type-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-quaternary);
}

.severity-badge {
  font-size: var(--font-size-xs);
  padding: var(--spacing-2xs) 10px;
  border-radius: var(--radius-lg);
  font-weight: var(--font-weight-medium);
}

.severity-badge.high {
  background: rgba(var(--color-error-rgb), 0.2);
  color: var(--color-error);
}

.severity-badge.medium {
  background: rgba(var(--color-warning-rgb), 0.2);
  color: var(--color-warning);
}

.severity-badge.low {
  background: rgba(var(--color-success-rgb), 0.2);
  color: var(--color-success);
}

.event-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-white);
  margin-bottom: var(--spacing-sm);
}

.event-description {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  line-height: 1.6;
  margin-bottom: var(--spacing-lg);
}

.suggested-action {
  display: flex;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: rgba(var(--color-primary-rgb), 0.1);
  border-radius: 10px;
  margin-bottom: var(--spacing-lg);
}

.action-label {
  font-size: var(--font-size-sm);
  color: var(--color-info-light);
  font-weight: var(--font-weight-medium);
}

.action-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  flex: 1;
}

.event-meta {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-lg);
}

.meta-item {
  display: flex;
  gap: var(--spacing-sm);
}

.meta-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
}

.meta-value {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.event-status-bar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--spacing-lg);
}

.status-tag {
  font-size: var(--font-size-xs);
  padding: var(--spacing-2xs) var(--spacing-md);
  border-radius: var(--radius-md);
  font-weight: var(--font-weight-medium);
}

.status-tag.completed {
  background: rgba(var(--color-success-rgb), 0.2);
  color: var(--color-success);
}

.status-tag.pending {
  background: rgba(var(--color-orange-rgb), 0.2);
  color: var(--color-orange);
}

.status-tag.rejected {
  background: rgba(var(--color-text-quaternary-rgb), 0.2);
  color: var(--color-text-quaternary);
}

.event-actions {
  display: flex;
  gap: var(--spacing-md);
}

.action-btn {
  flex: 1;
  padding: var(--spacing-md);
  border: none;
  border-radius: 10px;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.3s ease;
}

.action-btn.primary {
  background: var(--gradient-primary);
  color: var(--color-white);
}

.action-btn.primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 var(--spacing-2xs) var(--spacing-md) rgba(var(--color-primary-rgb), 0.4);
}

.action-btn.secondary {
  background: rgba(var(--color-white-rgb), 0.1);
  color: var(--color-text-secondary);
}

.action-btn.secondary:hover {
  background: rgba(var(--color-white-rgb), 0.15);
}
</style>