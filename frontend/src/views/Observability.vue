<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface TraceSpan {
  traceId: string
  service: string
  duration: number
  status: 'ok' | 'error' | 'timeout'
  timestamp: string
  spans: number
}

const activeTab = ref<'traces' | 'metrics' | 'logs'>('traces')
const loading = ref(false)

const traces = ref<TraceSpan[]>([
  { traceId: 'trace-a1b2c3', service: 'intent-engine', duration: 245, status: 'ok', timestamp: '2026-06-13 10:30:15', spans: 6 },
  { traceId: 'trace-d4e5f6', service: 'config-deployer', duration: 1820, status: 'timeout', timestamp: '2026-06-13 10:28:42', spans: 4 },
  { traceId: 'trace-g7h8i9', service: 'health-checker', duration: 89, status: 'ok', timestamp: '2026-06-13 10:25:00', spans: 3 },
  { traceId: 'trace-j0k1l2', service: 'self-healing', duration: 5600, status: 'error', timestamp: '2026-06-13 10:20:30', spans: 8 }
])

const logQuery = ref('')
const logResults = ref([
  { level: 'ERROR', service: 'config-deployer', message: '配置下发超时: Switch-A1 未响应', timestamp: '10:28:42' },
  { level: 'WARN', service: 'self-healing', message: '自愈流程第3步执行失败，正在重试', timestamp: '10:22:15' },
  { level: 'INFO', service: 'intent-engine', message: '意图解析完成: bandwidth_guarantee', timestamp: '10:30:16' },
  { level: 'INFO', service: 'health-checker', message: '健康检查完成: 156台设备在线', timestamp: '10:25:01' }
])

function getStatusLabel(s: string) {
  return s === 'ok' ? '成功' : s === 'error' ? '错误' : '超时'
}

function getLevelClass(level: string) {
  return level === 'ERROR' ? 'level-error' : level === 'WARN' ? 'level-warn' : 'level-info'
}

onMounted(() => {
  // TODO: 调用API获取可观测性数据
})
</script>

<template>
  <div class="observability">
    <h1 class="page-title">可观测性</h1>

    <div class="tabs">
      <button :class="['tab', { active: activeTab === 'traces' }]" @click="activeTab = 'traces'">链路追踪</button>
      <button :class="['tab', { active: activeTab === 'metrics' }]" @click="activeTab = 'metrics'">指标监控</button>
      <button :class="['tab', { active: activeTab === 'logs' }]" @click="activeTab = 'logs'">日志查询</button>
    </div>

    <div v-if="activeTab === 'traces'" class="trace-view">
      <div class="trace-list">
        <div v-for="trace in traces" :key="trace.traceId" class="trace-card">
          <div class="trace-header">
            <span class="trace-id">{{ trace.traceId }}</span>
            <span :class="['status-tag', trace.status]">{{ getStatusLabel(trace.status) }}</span>
          </div>
          <div class="trace-body">
            <div class="trace-info">
              <span class="info-label">服务</span>
              <span class="info-value">{{ trace.service }}</span>
            </div>
            <div class="trace-info">
              <span class="info-label">耗时</span>
              <span class="info-value">{{ trace.duration }}ms</span>
            </div>
            <div class="trace-info">
              <span class="info-label">Span数</span>
              <span class="info-value">{{ trace.spans }}</span>
            </div>
            <div class="trace-info">
              <span class="info-label">时间</span>
              <span class="info-value time">{{ trace.timestamp }}</span>
            </div>
          </div>
          <div class="trace-bar-container">
            <div
              class="trace-bar"
              :class="trace.status"
              :style="{ width: `${Math.min((trace.duration / 6000) * 100, 100)}%` }"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="activeTab === 'metrics'" class="metrics-view">
      <div class="metrics-grid">
        <div class="metric-card">
          <div class="metric-title">请求量 (QPS)</div>
          <div class="metric-value">1,284</div>
          <div class="metric-sub">较昨日 +12%</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">平均延迟</div>
          <div class="metric-value">45ms</div>
          <div class="metric-sub">P99: 230ms</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">错误率</div>
          <div class="metric-value metric-warning">0.3%</div>
          <div class="metric-sub">目标: < 0.5%</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">活跃连接</div>
          <div class="metric-value">342</div>
          <div class="metric-sub">最大: 1000</div>
        </div>
      </div>
      <div class="chart-placeholder">
        <div class="placeholder-text">指标监控图表（集成ECharts后替换）</div>
      </div>
    </div>

    <div v-if="activeTab === 'logs'" class="logs-view">
      <div class="log-search">
        <input v-model="logQuery" class="log-input" placeholder="搜索日志 (支持Lucene语法)..." />
        <button class="search-btn">查询</button>
      </div>
      <div class="log-list">
        <div v-for="(log, index) in logResults" :key="index" class="log-item">
          <span class="log-level" :class="getLevelClass(log.level)">{{ log.level }}</span>
          <span class="log-service">{{ log.service }}</span>
          <span class="log-message">{{ log.message }}</span>
          <span class="log-time">{{ log.timestamp }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); color: var(--color-white); margin-bottom: var(--spacing-2xl); }

.tabs { display: flex; gap: var(--spacing-2xs); background: rgba(var(--color-bg-elevated-rgb), 0.6); border-radius: var(--radius-lg); padding: var(--spacing-2xs); margin-bottom: var(--spacing-2xl); width: fit-content; }

.tab {
  padding: var(--spacing-sm-md) var(--spacing-xl);
  border: none;
  background: transparent;
  color: var(--color-text-tertiary);
  border-radius: var(--radius-lg);
  cursor: pointer;
  font-size: var(--font-size-base);
  transition: all 0.2s;
}

.tab.active { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); font-weight: var(--font-weight-medium); }

.trace-list { display: flex; flex-direction: column; gap: var(--spacing-md); }

.trace-card {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-xl);
  padding: var(--spacing-lg) var(--spacing-xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
}

.trace-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-md); }
.trace-id { font-size: var(--font-size-sm); color: var(--color-info-light); font-family: monospace; }

.status-tag { font-size: var(--font-size-xs); padding: 3px var(--spacing-sm-md); border-radius: var(--radius-full); font-weight: var(--font-weight-medium); }
.status-tag.ok { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); }
.status-tag.error { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); }
.status-tag.timeout { background: rgba(var(--color-warning-rgb), 0.2); color: var(--color-warning); }

.trace-body { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--spacing-md); margin-bottom: var(--spacing-md); }
.info-label { font-size: var(--font-size-xs); color: var(--color-text-quaternary); display: block; }
.info-value { font-size: var(--font-size-sm); color: var(--color-text-secondary); font-weight: var(--font-weight-medium); }
.info-value.time { font-size: var(--font-size-sm); color: var(--color-text-quaternary); font-weight: var(--font-weight-regular); }

.trace-bar-container { height: var(--spacing-2xs); background: rgba(var(--color-white-rgb), 0.1); border-radius: 1px; overflow: hidden; }
.trace-bar { height: 100%; border-radius: 1px; transition: width 0.3s; }
.trace-bar.ok { background: var(--color-success); }
.trace-bar.error { background: var(--color-error); }
.trace-bar.timeout { background: var(--color-warning); }

.metrics-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--spacing-lg); margin-bottom: var(--spacing-2xl); }

.metric-card {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-xl);
  padding: var(--spacing-xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  text-align: center;
}

.metric-title { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-bottom: var(--spacing-sm); }
.metric-value { font-size: var(--font-size-4xl); font-weight: var(--font-weight-bold); color: var(--color-white); }
.metric-warning { color: var(--color-orange); }
.metric-sub { font-size: var(--font-size-sm); color: var(--color-text-quaternary); margin-top: var(--spacing-2xs); }

.chart-placeholder {
  height: 250px;
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-2xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
}

.placeholder-text { color: var(--color-text-quaternary); font-size: var(--font-size-base); }

.log-search { display: flex; gap: var(--spacing-sm); margin-bottom: var(--spacing-lg); }

.log-input {
  flex: 1;
  padding: var(--spacing-md) var(--spacing-lg);
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-lg);
  color: var(--color-white);
  font-size: var(--font-size-base);
  font-family: monospace;
}

.log-input:focus { outline: none; border-color: var(--color-primary); }
.log-input::placeholder { color: var(--color-text-quaternary); }

.search-btn {
  padding: var(--spacing-md) var(--spacing-2xl);
  background: rgba(var(--color-primary-rgb), 0.2);
  color: var(--color-info-light);
  border: 1px solid rgba(var(--color-primary-rgb), 0.3);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-base);
  cursor: pointer;
}

.log-list { display: flex; flex-direction: column; gap: var(--spacing-3xs); background: rgba(var(--color-bg-base-rgb), 0.8); border-radius: var(--radius-xl); padding: var(--spacing-md); }

.log-item { display: flex; gap: var(--spacing-lg); padding: var(--spacing-sm) var(--spacing-md); border-radius: var(--radius-md); font-size: var(--font-size-sm); font-family: monospace; }
.log-item:hover { background: rgba(var(--color-white-rgb), 0.03); }

.log-level { width: 50px; font-weight: var(--font-weight-bold); font-size: var(--font-size-sm); }
.log-level.level-error { color: var(--color-error); }
.log-level.level-warn { color: var(--color-warning); }
.log-level.level-info { color: var(--color-success); }
.log-service { width: 130px; color: var(--color-info-light); }
.log-message { flex: 1; color: var(--color-text-secondary); }
.log-time { width: 80px; color: var(--color-text-quaternary); text-align: right; }
</style>
