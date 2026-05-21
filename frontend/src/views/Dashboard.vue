<script setup lang="ts">
import { ref, onMounted } from 'vue'

const stats = ref([
  { label: '活跃意图', value: 24, unit: '个', color: '#165DFF' },
  { label: '在线设备', value: 156, unit: '台', color: '#52C41A' },
  { label: '自愈事件', value: 8, unit: '次', color: '#FF7D00' },
  { label: '待审批', value: 3, unit: '项', color: '#FF4D4F' }
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
        <div class="stat-icon" :style="{ background: `${stat.color}20`, color: stat.color }">
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
                :style="{ width: `${device.health}%`, background: device.status === 'warning' ? '#FAAD14' : '#52C41A' }"
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
  font-size: 24px;
  font-weight: 700;
  color: white;
  margin-bottom: 24px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 24px;
}

.stat-card {
  background: rgba(30, 41, 59, 0.6);
  border-radius: 16px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: white;
  line-height: 1.2;
}

.stat-unit {
  font-size: 14px;
  font-weight: 400;
  color: #94A3B8;
  margin-left: 4px;
}

.stat-label {
  font-size: 14px;
  color: #94A3B8;
  margin-top: 4px;
}

.content-row {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 20px;
}

.panel {
  background: rgba(30, 41, 59, 0.6);
  border-radius: 16px;
  padding: 20px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: white;
  margin-bottom: 16px;
}

.intent-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.intent-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 10px;
}

.intent-info {
  flex: 1;
}

.intent-id {
  font-size: 12px;
  color: #64748B;
  margin-bottom: 4px;
}

.intent-name {
  font-size: 14px;
  font-weight: 500;
  color: white;
}

.intent-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.intent-device {
  font-size: 12px;
  color: #64748B;
}

.intent-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 500;
}

.intent-status.running {
  background: rgba(22, 93, 255, 0.2);
  color: #69B1FF;
}

.intent-status.completed {
  background: rgba(82, 196, 26, 0.2);
  color: #52C41A;
}

.intent-status.pending {
  background: rgba(255, 125, 0, 0.2);
  color: #FF7D00;
}

.intent-time {
  font-size: 12px;
  color: #64748B;
}

.health-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.health-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.health-name {
  width: 100px;
  font-size: 13px;
  color: #E2E8F0;
}

.health-bar-container {
  flex: 1;
  height: 8px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  overflow: hidden;
}

.health-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.health-value {
  width: 50px;
  text-align: right;
  font-size: 13px;
  font-weight: 500;
}

.health-value.normal {
  color: #52C41A;
}

.health-value.warning {
  color: #FAAD14;
}
</style>