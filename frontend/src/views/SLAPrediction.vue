<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface SLAMetric {
  name: string
  current: number
  target: number
  unit: string
  trend: 'up' | 'down' | 'stable'
  status: 'healthy' | 'warning' | 'critical'
}

const metrics = ref<SLAMetric[]>([
  { name: '网络可用性', current: 99.97, target: 99.95, unit: '%', trend: 'stable', status: 'healthy' },
  { name: '平均响应时间', current: 12, target: 20, unit: 'ms', trend: 'down', status: 'healthy' },
  { name: '故障恢复时间', current: 8, target: 15, unit: 'min', trend: 'up', status: 'warning' },
  { name: '配置变更成功率', current: 98.5, target: 99, unit: '%', trend: 'down', status: 'warning' },
  { name: '工单解决率', current: 95.2, target: 95, unit: '%', trend: 'up', status: 'healthy' },
  { name: '安全事件响应', current: 5, target: 10, unit: 'min', trend: 'stable', status: 'healthy' }
])

const alerts = ref([
  { id: 1, level: 'warning', message: '故障恢复时间MTTR接近SLA阈值', time: '10分钟前' },
  { id: 2, level: 'critical', message: '配置变更成功率低于目标值', time: '30分钟前' },
  { id: 3, level: 'info', message: '网络可用性持续达标30天', time: '1小时前' }
])

const predictionDays = ref(7)

function getTrendIcon(trend: string) {
  return trend === 'up' ? '📈' : trend === 'down' ? '📉' : '➡️'
}

function getStatusClass(status: string) {
  return status === 'healthy' ? 'status-healthy' : status === 'warning' ? 'status-warning' : 'status-critical'
}

onMounted(() => {
  // TODO: 调用API获取SLA指标
})
</script>

<template>
  <div class="sla-prediction">
    <h1 class="page-title">SLA预测</h1>

    <div class="metrics-grid">
      <div v-for="metric in metrics" :key="metric.name" class="metric-card">
        <div class="metric-header">
          <span class="metric-name">{{ metric.name }}</span>
          <span class="metric-trend">{{ getTrendIcon(metric.trend) }}</span>
        </div>
        <div class="metric-value" :class="getStatusClass(metric.status)">
          {{ metric.current }}
          <span class="metric-unit">{{ metric.unit }}</span>
        </div>
        <div class="metric-target">目标: {{ metric.target }}{{ metric.unit }}</div>
        <div class="metric-bar-container">
          <div
            class="metric-bar"
            :class="getStatusClass(metric.status)"
            :style="{ width: `${Math.min((metric.current / metric.target) * 100, 100)}%` }"
          ></div>
        </div>
      </div>
    </div>

    <div class="content-row">
      <div class="chart-panel">
        <div class="panel-header">
          <h2 class="panel-title">SLA趋势预测</h2>
          <div class="prediction-control">
            <span class="control-label">预测天数:</span>
            <select v-model="predictionDays" class="control-select">
              <option :value="7">7天</option>
              <option :value="14">14天</option>
              <option :value="30">30天</option>
            </select>
          </div>
        </div>
        <div class="chart-placeholder">
          <div class="chart-mock">
            <div class="chart-line" v-for="i in 7" :key="i" :style="{ height: `${40 + Math.random() * 50}%` }"></div>
          </div>
          <div class="chart-label">SLA指标趋势图（集成ECharts后替换）</div>
        </div>
      </div>

      <div class="alert-panel">
        <h2 class="panel-title">SLA告警</h2>
        <div class="alert-list">
          <div v-for="alert in alerts" :key="alert.id" :class="['alert-item', alert.level]">
            <span class="alert-icon">{{ alert.level === 'critical' ? '🔴' : alert.level === 'warning' ? '🟡' : '🟢' }}</span>
            <div class="alert-content">
              <div class="alert-message">{{ alert.message }}</div>
              <div class="alert-time">{{ alert.time }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); color: var(--color-white); margin-bottom: var(--spacing-2xl); }

.metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--spacing-lg); margin-bottom: var(--spacing-2xl); }

.metric-card {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-xl);
  padding: var(--spacing-xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
}

.metric-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-sm-md); }
.metric-name { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.metric-trend { font-size: var(--font-size-lg); }

.metric-value { font-size: var(--font-size-4xl); font-weight: var(--font-weight-bold); margin-bottom: var(--spacing-2xs); }
.metric-value.status-healthy { color: var(--color-success); }
.metric-value.status-warning { color: var(--color-warning); }
.metric-value.status-critical { color: var(--color-error); }
.metric-unit { font-size: var(--font-size-base); font-weight: var(--font-weight-regular); opacity: 0.7; }
.metric-target { font-size: var(--font-size-sm); color: var(--color-text-quaternary); margin-bottom: var(--spacing-sm-md); }

.metric-bar-container { height: var(--spacing-2xs); background: rgba(var(--color-white-rgb), 0.1); border-radius: 1px; overflow: hidden; }
.metric-bar { height: 100%; border-radius: 1px; transition: width 0.5s ease; }
.metric-bar.status-healthy { background: var(--color-success); }
.metric-bar.status-warning { background: var(--color-warning); }
.metric-bar.status-critical { background: var(--color-error); }

.content-row { display: grid; grid-template-columns: 2fr 1fr; gap: var(--spacing-2xl); }

.chart-panel, .alert-panel {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-2xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
}

.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-xl); }
.panel-title { font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--color-white); }

.prediction-control { display: flex; align-items: center; gap: var(--spacing-sm); }
.control-label { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.control-select {
  padding: var(--spacing-2xs) var(--spacing-sm);
  background: rgba(var(--color-bg-base-rgb), 0.5);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-md);
  color: var(--color-white);
  font-size: var(--font-size-sm);
}

.chart-placeholder { height: 200px; display: flex; flex-direction: column; align-items: center; justify-content: center; }

.chart-mock { display: flex; align-items: flex-end; gap: var(--spacing-md); height: 120px; width: 80%; }
.chart-line { flex: 1; background: linear-gradient(to top, rgba(var(--color-primary-rgb), 0.3), rgba(var(--color-primary-rgb), 0.8)); border-radius: var(--spacing-2xs) var(--spacing-2xs) 0 0; min-height: 20px; }
.chart-label { font-size: var(--font-size-sm); color: var(--color-text-quaternary); margin-top: var(--spacing-md); }

.alert-list { display: flex; flex-direction: column; gap: var(--spacing-sm-md); }

.alert-item { display: flex; gap: var(--spacing-sm-md); padding: var(--spacing-md); background: rgba(var(--color-bg-base-rgb), 0.5); border-radius: var(--radius-lg); }
.alert-item.critical { border-left: 3px solid var(--color-error); }
.alert-item.warning { border-left: 3px solid var(--color-warning); }
.alert-item.info { border-left: 3px solid var(--color-success); }

.alert-icon { font-size: var(--font-size-base); flex-shrink: 0; margin-top: 2px; }
.alert-message { font-size: var(--font-size-sm); color: var(--color-text-secondary); }
.alert-time { font-size: var(--font-size-xs); color: var(--color-text-quaternary); margin-top: var(--spacing-2xs); }
</style>
