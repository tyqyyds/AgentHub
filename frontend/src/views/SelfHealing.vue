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

const executeAction = (event) => {
  const index = healingEvents.value.findIndex(e => e.id === event.id)
  if (index !== -1) {
    healingEvents.value[index].status = 'completed'
    healingEvents.value[index].executedBy = '管理员'
  }
}

const rejectAction = (event) => {
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
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: white;
}

.rollback-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  background: linear-gradient(135deg, #FF4D4F 0%, #FF7875 100%);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 14px rgba(255, 77, 79, 0.4);
}

.rollback-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(255, 77, 79, 0.5);
}

.rollback-icon {
  font-size: 18px;
}

.mode-selector {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  padding: 16px 20px;
  background: rgba(30, 41, 59, 0.6);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.mode-label {
  font-size: 14px;
  color: #E2E8F0;
  font-weight: 500;
}

.mode-btn {
  padding: 10px 20px;
  background: rgba(255, 255, 255, 0.1);
  color: #94A3B8;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.mode-btn:hover {
  background: rgba(22, 93, 255, 0.2);
  color: #E2E8F0;
}

.mode-btn.active {
  background: linear-gradient(135deg, #165DFF 0%, #4080FF 100%);
  color: white;
}

.events-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 20px;
}

.event-card {
  background: rgba(30, 41, 59, 0.6);
  border-radius: 16px;
  padding: 20px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-left: 4px solid;
}

.event-card.high {
  border-left-color: #FF4D4F;
}

.event-card.medium {
  border-left-color: #FAAD14;
}

.event-card.low {
  border-left-color: #52C41A;
}

.event-card.rejected {
  opacity: 0.6;
}

.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.event-type {
  display: flex;
  align-items: center;
  gap: 8px;
}

.type-icon {
  font-size: 16px;
}

.type-text {
  font-size: 13px;
  color: #64748B;
}

.severity-badge {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 12px;
  font-weight: 500;
}

.severity-badge.high {
  background: rgba(255, 77, 79, 0.2);
  color: #FF4D4F;
}

.severity-badge.medium {
  background: rgba(250, 173, 20, 0.2);
  color: #FAAD14;
}

.severity-badge.low {
  background: rgba(82, 196, 26, 0.2);
  color: #52C41A;
}

.event-title {
  font-size: 16px;
  font-weight: 600;
  color: white;
  margin-bottom: 8px;
}

.event-description {
  font-size: 13px;
  color: #94A3B8;
  line-height: 1.6;
  margin-bottom: 16px;
}

.suggested-action {
  display: flex;
  gap: 8px;
  padding: 12px;
  background: rgba(22, 93, 255, 0.1);
  border-radius: 10px;
  margin-bottom: 16px;
}

.action-label {
  font-size: 13px;
  color: #69B1FF;
  font-weight: 500;
}

.action-text {
  font-size: 13px;
  color: #E2E8F0;
  flex: 1;
}

.event-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
}

.meta-item {
  display: flex;
  gap: 8px;
}

.meta-label {
  font-size: 12px;
  color: #64748B;
}

.meta-value {
  font-size: 12px;
  color: #E2E8F0;
}

.event-status-bar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}

.status-tag {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 8px;
  font-weight: 500;
}

.status-tag.completed {
  background: rgba(82, 196, 26, 0.2);
  color: #52C41A;
}

.status-tag.pending {
  background: rgba(255, 125, 0, 0.2);
  color: #FF7D00;
}

.status-tag.rejected {
  background: rgba(100, 116, 139, 0.2);
  color: #64748B;
}

.event-actions {
  display: flex;
  gap: 12px;
}

.action-btn {
  flex: 1;
  padding: 12px;
  border: none;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
}

.action-btn.primary {
  background: linear-gradient(135deg, #165DFF 0%, #4080FF 100%);
  color: white;
}

.action-btn.primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(22, 93, 255, 0.4);
}

.action-btn.secondary {
  background: rgba(255, 255, 255, 0.1);
  color: #E2E8F0;
}

.action-btn.secondary:hover {
  background: rgba(255, 255, 255, 0.15);
}
</style>