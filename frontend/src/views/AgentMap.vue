<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface AgentNode {
  id: string
  name: string
  type: 'controller' | 'executor' | 'monitor'
  status: 'running' | 'idle' | 'error'
  ip: string
  connections: string[]
}

const agents = ref<AgentNode[]>([
  { id: 'agent-01', name: '主控Agent', type: 'controller', status: 'running', ip: '10.0.1.1', connections: ['agent-02', 'agent-03', 'agent-04'] },
  { id: 'agent-02', name: '执行Agent-A', type: 'executor', status: 'running', ip: '10.0.1.2', connections: ['agent-01'] },
  { id: 'agent-03', name: '执行Agent-B', type: 'executor', status: 'idle', ip: '10.0.1.3', connections: ['agent-01'] },
  { id: 'agent-04', name: '监控Agent', type: 'monitor', status: 'running', ip: '10.0.1.4', connections: ['agent-01', 'agent-05'] },
  { id: 'agent-05', name: '执行Agent-C', type: 'executor', status: 'error', ip: '10.0.1.5', connections: ['agent-04'] }
])

const selectedAgent = ref<AgentNode | null>(null)

function selectAgent(agent: AgentNode) {
  selectedAgent.value = agent
}

function getStatusLabel(status: string) {
  return status === 'running' ? '运行中' : status === 'idle' ? '空闲' : '异常'
}

function getTypeLabel(type: string) {
  return type === 'controller' ? '控制器' : type === 'executor' ? '执行器' : '监控器'
}

onMounted(() => {
  // TODO: 调用API获取Agent拓扑数据
})
</script>

<template>
  <div class="agent-map">
    <h1 class="page-title">Agent地图</h1>

    <div class="map-layout">
      <div class="topology-panel">
        <div class="topology-canvas">
          <div
            v-for="(agent, index) in agents"
            :key="agent.id"
            :class="['agent-node', agent.type, agent.status, { selected: selectedAgent?.id === agent.id }]"
            :style="{ left: `${15 + (index % 3) * 35}%`, top: `${15 + Math.floor(index / 3) * 40}%` }"
            @click="selectAgent(agent)"
          >
            <div class="node-icon">
              {{ agent.type === 'controller' ? '🎛️' : agent.type === 'executor' ? '⚙️' : '📡' }}
            </div>
            <div class="node-name">{{ agent.name }}</div>
            <span :class="['node-status', agent.status]"></span>
          </div>

          <svg class="connection-lines" v-if="false">
            <!-- 连接线由后续地图库渲染 -->
          </svg>
        </div>
      </div>

      <div class="detail-panel">
        <template v-if="selectedAgent">
          <h2 class="panel-title">{{ selectedAgent.name }}</h2>
          <div class="detail-grid">
            <div class="detail-item">
              <span class="detail-label">ID</span>
              <span class="detail-value">{{ selectedAgent.id }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">类型</span>
              <span class="detail-value">{{ getTypeLabel(selectedAgent.type) }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">状态</span>
              <span :class="['detail-value', selectedAgent.status]">{{ getStatusLabel(selectedAgent.status) }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">IP地址</span>
              <span class="detail-value">{{ selectedAgent.ip }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">连接数</span>
              <span class="detail-value">{{ selectedAgent.connections.length }}</span>
            </div>
          </div>
          <div class="connections-section">
            <h3 class="section-title">通信关系</h3>
            <div class="connection-list">
              <div v-for="connId in selectedAgent.connections" :key="connId" class="connection-item">
                <span class="conn-id">{{ connId }}</span>
                <span class="conn-name">{{ agents.find(a => a.id === connId)?.name || connId }}</span>
              </div>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="empty-state">
            <div class="empty-icon">🗺️</div>
            <div class="empty-text">点击节点查看Agent详情</div>
          </div>
        </template>
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

.map-layout {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--spacing-2xl);
  height: calc(100vh - 160px);
}

.topology-panel {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-2xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  position: relative;
  overflow: hidden;
}

.topology-canvas {
  width: 100%;
  height: 100%;
  position: relative;
}

.agent-node {
  position: absolute;
  width: 100px;
  padding: var(--spacing-md);
  background: rgba(var(--color-bg-base-rgb), 0.8);
  border-radius: var(--radius-xl);
  border: 2px solid rgba(var(--color-white-rgb), 0.1);
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  transform: translate(-50%, -50%);
}

.agent-node:hover { border-color: rgba(var(--color-primary-rgb), 0.5); transform: translate(-50%, -50%) scale(1.05); }
.agent-node.selected { border-color: var(--color-primary); box-shadow: 0 0 var(--spacing-xl) rgba(var(--color-primary-rgb), 0.3); }
.agent-node.error { border-color: rgba(var(--color-error-rgb), 0.5); }

.node-icon { font-size: var(--font-size-3xl); margin-bottom: var(--spacing-xs); }
.node-name { font-size: var(--font-size-sm); color: var(--color-text-secondary); font-weight: var(--font-weight-medium); }

.node-status {
  display: inline-block;
  width: var(--spacing-sm);
  height: var(--spacing-sm);
  border-radius: 50%;
  margin-top: var(--spacing-xs);
}

.node-status.running { background: var(--color-success); }
.node-status.idle { background: var(--color-text-quaternary); }
.node-status.error { background: var(--color-error); animation: blink 1s infinite; }

@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.detail-panel {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-2xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  overflow-y: auto;
}

.panel-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-white);
  margin-bottom: var(--spacing-xl);
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-2xl);
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2xs);
}

.detail-label { font-size: var(--font-size-sm); color: var(--color-text-quaternary); }
.detail-value { font-size: var(--font-size-base); color: var(--color-text-secondary); font-weight: var(--font-weight-medium); }
.detail-value.running { color: var(--color-success); }
.detail-value.idle { color: var(--color-text-quaternary); }
.detail-value.error { color: var(--color-error); }

.section-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-md);
}

.connection-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.connection-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: rgba(var(--color-bg-base-rgb), 0.5);
  border-radius: var(--radius-lg);
}

.conn-id { font-size: var(--font-size-sm); color: var(--color-text-quaternary); font-family: monospace; }
.conn-name { font-size: var(--font-size-sm); color: var(--color-text-secondary); }

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: var(--spacing-md);
}

.empty-icon { font-size: 48px; }
.empty-text { font-size: var(--font-size-base); color: var(--color-text-quaternary); }
</style>
