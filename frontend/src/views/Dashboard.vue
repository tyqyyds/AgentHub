<script setup lang="ts">
import { ref, onMounted } from 'vue'

const stats = ref([
  { label: '活跃意图', value: 24, unit: '个', colorType: 'primary' },
  { label: '在线设备', value: 156, unit: '台', colorType: 'success' },
  { label: '自愈事件', value: 8, unit: '次', colorType: 'orange' },
  { label: '待审批', value: 3, unit: '项', colorType: 'error' }
])

const recentIntents = ref([
  { id: 'INT-001', name: '带宽保障-视频会议', status: 'running', device: 'Switch-A1', time: '10分钟前' },
  { id: 'INT-002', name: 'ACL规则更新', status: 'completed', device: 'Firewall-B1', time: '30分钟前' },
  { id: 'INT-003', name: 'QoS策略优化', status: 'pending', device: 'Router-C1', time: '1小时前' },
  { id: 'INT-004', name: '链路冗余配置', status: 'running', device: 'Switch-A2', time: '2小时前' }
])

const healthStatus = ref([
  { name: '核心路由器', health: 98, status: 'normal' },
  { name: '汇聚交换机', health: 92, status: 'normal' },
  { name: '防火墙集群', health: 87, status: 'warning' },
  { name: '接入交换机', health: 95, status: 'normal' }
])

onMounted(() => {
  // 模拟数据更新
  setTimeout(() => {
    stats.value[0].value = 25
  }, 2000)
})
</script>

<template>
  <div class="dashboard">
    <h1 class="page-title">指挥舱概览</h1>
    
    <div class="stats-grid">
      <div
        v-for="stat in stats"
        :key="stat.label"
        class="stat-card"
      >
        <div class="stat-icon" :class="`stat-${stat.colorType}`">
          {{ stat.label === '活跃意图' ? '🎯' : stat.label === '在线设备' ? '🖥️' : stat.label === '自愈事件' ? '🛡️' : '📋' }}
        </div>
        <div class="stat-content">
          <div class="stat-value">
            {{ stat.value }}
            <span class="stat-unit">{{ stat.unit }}</span>
          </div>
          <div class="stat-label">{{ stat.label }}</div>
        </div>
      </div>
    </div>

    <div class="content-row">
      <div class="panel">
        <h2 class="panel-title">最近意图执行</h2>
        <div class="intent-list">
          <div
            v-for="intent in recentIntents"
            :key="intent.id"
            class="intent-item"
          >
            <div class="intent-info">
              <div class="intent-id">{{ intent.id }}</div>
              <div class="intent-name">{{ intent.name }}</div>
            </div>
            <div class="intent-meta">
              <span class="intent-device">{{ intent.device }}</span>
              <span :class="['intent-status', intent.status]">
                {{ intent.status === 'running' ? '执行中' : intent.status === 'completed' ? '已完成' : '待审批' }}
              </span>
            </div>
            <div class="intent-time">{{ intent.time }}</div>
          </div>
        </div>
      </div>

      <div class="panel">
        <h2 class="panel-title">设备健康状态</h2>
        <div class="health-list">
          <div
            v-for="device in healthStatus"
            :key="device.name"
            class="health-item"
          >
            <div class="health-name">{{ device.name }}</div>
            <div class="health-bar-container">
              <div
                class="health-bar"
                :class="device.status === 'warning' ? 'health-bar-warning' : 'health-bar-normal'"
                :style="{ width: `${device.health}%` }"
              ></div>
            </div>
            <div :class="['health-value', device.status]">{{ device.health }}%</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-white);
  margin-bottom: var(--spacing-2xl);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-xl);
  margin-bottom: var(--spacing-2xl);
}

.stat-card {
  background: rgba(var(--color-bg-container-rgb), 0.6);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-xl);
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-3xl);
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: var(--font-size-4xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-white);
  line-height: var(--line-height-tight);
}

.stat-unit {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-regular);
  color: var(--color-text-tertiary);
  margin-left: var(--spacing-2xs);
}

.stat-label {
  font-size: var(--font-size-base);
  color: var(--color-text-tertiary);
  margin-top: var(--spacing-2xs);
}

.content-row {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--spacing-xl);
}

.panel {
  background: rgba(var(--color-bg-container-rgb), 0.6);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
}

.panel-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-white);
  margin-bottom: var(--spacing-lg);
}

.intent-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.intent-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  padding: var(--spacing-md-lg);
  background: rgba(var(--color-bg-base-rgb), 0.5);
  border-radius: var(--radius-lg);
}

.intent-info {
  flex: 1;
}

.intent-id {
  font-size: var(--font-size-sm);
  color: var(--color-text-quaternary);
  margin-bottom: var(--spacing-2xs);
}

.intent-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-white);
}

.intent-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--spacing-2xs);
}

.intent-device {
  font-size: var(--font-size-sm);
  color: var(--color-text-quaternary);
}

.intent-status {
  font-size: var(--font-size-sm);
  padding: var(--spacing-3xs) var(--spacing-sm);
  border-radius: var(--radius-xl);
  font-weight: var(--font-weight-medium);
}

.intent-status.running {
  background: rgba(var(--color-primary-rgb), 0.2);
  color: var(--color-info-light);
}

.intent-status.completed {
  background: rgba(var(--color-success-rgb), 0.2);
  color: var(--color-success);
}

.intent-status.pending {
  background: rgba(var(--color-orange-rgb), 0.2);
  color: var(--color-orange-light);
}

.intent-time {
  font-size: var(--font-size-sm);
  color: var(--color-text-quaternary);
}

.health-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.health-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.health-name {
  width: 100px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.health-bar-container {
  flex: 1;
  height: var(--spacing-sm);
  background: rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.health-bar {
  height: 100%;
  border-radius: var(--radius-sm);
  transition: width 0.3s ease;
}

.health-value {
  width: 50px;
  text-align: right;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.health-value.normal {
  color: var(--color-success);
}

.health-value.warning {
  color: var(--color-warning);
}

/* 动态颜色类 — stat-icon */
.stat-primary {
  background: rgba(var(--color-primary-rgb), 0.2);
  color: var(--color-primary);
}

.stat-success {
  background: rgba(var(--color-success-rgb), 0.2);
  color: var(--color-success);
}

.stat-orange {
  background: rgba(var(--color-orange-rgb), 0.2);
  color: var(--color-orange);
}

.stat-error {
  background: rgba(var(--color-error-rgb), 0.2);
  color: var(--color-error);
}

/* 动态颜色类 — health-bar */
.health-bar-warning {
  background: var(--color-warning);
}

.health-bar-normal {
  background: var(--color-success);
}
</style>