<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const selectedNode = ref(null)
const nodeDetails = ref(null)

const topologyData = ref({
  nodes: [
    { id: 'core1', name: '核心路由器CR-01', type: 'router', health: 98, x: 400, y: 150 },
    { id: 'core2', name: '核心路由器CR-02', type: 'router', health: 95, x: 600, y: 150 },
    { id: 'agg1', name: '汇聚交换机AS-01', type: 'switch', health: 92, x: 200, y: 300 },
    { id: 'agg2', name: '汇聚交换机AS-02', type: 'switch', health: 87, x: 500, y: 300 },
    { id: 'agg3', name: '汇聚交换机AS-03', type: 'switch', health: 96, x: 800, y: 300 },
    { id: 'acc1', name: '接入交换机AC-01', type: 'switch', health: 99, x: 100, y: 450 },
    { id: 'acc2', name: '接入交换机AC-02', type: 'switch', health: 94, x: 300, y: 450 },
    { id: 'acc3', name: '接入交换机AC-03', type: 'switch', health: 97, x: 600, y: 450 },
    { id: 'acc4', name: '接入交换机AC-04', type: 'switch', health: 85, x: 900, y: 450 }
  ],
  links: [
    { source: 'core1', target: 'core2', bandwidth: '10G', status: 'active' },
    { source: 'core1', target: 'agg1', bandwidth: '10G', status: 'active' },
    { source: 'core1', target: 'agg2', bandwidth: '10G', status: 'active' },
    { source: 'core2', target: 'agg2', bandwidth: '10G', status: 'active' },
    { source: 'core2', target: 'agg3', bandwidth: '10G', status: 'warning' },
    { source: 'agg1', target: 'acc1', bandwidth: '1G', status: 'active' },
    { source: 'agg1', target: 'acc2', bandwidth: '1G', status: 'active' },
    { source: 'agg2', target: 'acc2', bandwidth: '1G', status: 'active' },
    { source: 'agg2', target: 'acc3', bandwidth: '1G', status: 'active' },
    { source: 'agg3', target: 'acc3', bandwidth: '1G', status: 'active' },
    { source: 'agg3', target: 'acc4', bandwidth: '1G', status: 'active' }
  ]
})

const handleNodeClick = (node) => {
  selectedNode.value = node.id
  nodeDetails.value = node
}

const getHealthColor = (health) => {
  if (health >= 90) return '#52C41A'
  if (health >= 70) return '#FAAD14'
  return '#FF4D4F'
}

let animationFrame = null

const animateNodes = () => {
  topologyData.value.nodes.forEach(node => {
    node.x += (Math.random() - 0.5) * 0.5
    node.y += (Math.random() - 0.5) * 0.5
  })
  animationFrame = requestAnimationFrame(animateNodes)
}

onMounted(() => {
  animateNodes()
})

onUnmounted(() => {
  if (animationFrame) {
    cancelAnimationFrame(animationFrame)
  }
})
</script>

<template>
  <div class="topology-container">
    <h1 class="page-title">网络拓扑</h1>
    
    <div class="topology-layout">
      <div class="topology-canvas">
        <svg viewBox="0 0 1000 550" class="svg-canvas">
          <defs>
            <linearGradient id="linkGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stop-color="#165DFF" />
              <stop offset="100%" stop-color="#69B1FF" />
            </linearGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
              <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>
          
          <g class="links">
            <line
              v-for="link in topologyData.links"
              :key="`${link.source}-${link.target}`"
              :x1="topologyData.nodes.find(n => n.id === link.source)?.x || 0"
              :y1="topologyData.nodes.find(n => n.id === link.source)?.y || 0"
              :x2="topologyData.nodes.find(n => n.id === link.target)?.x || 0"
              :y2="topologyData.nodes.find(n => n.id === link.target)?.y || 0"
              :class="['link', link.status]"
              :stroke="link.status === 'warning' ? '#FAAD14' : 'url(#linkGradient)'"
            />
          </g>
          
          <g class="nodes">
            <g
              v-for="node in topologyData.nodes"
              :key="node.id"
              :class="['node-group', { selected: selectedNode === node.id }]"
              @click="handleNodeClick(node)"
            >
              <circle
                :cx="node.x"
                :cy="node.y"
                r="30"
                :fill="getHealthColor(node.health)"
                class="node-circle"
              />
              <circle
                :cx="node.x"
                :cy="node.y"
                r="25"
                fill="#1E293B"
                class="node-inner"
              />
              <text
                :x="node.x"
                :y="node.y + 5"
                text-anchor="middle"
                fill="white"
                font-size="12"
                font-weight="600"
              >
                {{ node.type === 'router' ? 'R' : 'S' }}
              </text>
              <text
                :x="node.x"
                :y="node.y + 55"
                text-anchor="middle"
                fill="#E2E8F0"
                font-size="11"
              >
                {{ node.name.split(' ')[0] }}
              </text>
            </g>
          </g>
        </svg>
        
        <div class="legend">
          <div class="legend-item">
            <span class="legend-dot" style="background: #52C41A;"></span>
            <span>健康 (≥90%)</span>
          </div>
          <div class="legend-item">
            <span class="legend-dot" style="background: #FAAD14;"></span>
            <span>警告 (70-89%)</span>
          </div>
          <div class="legend-item">
            <span class="legend-dot" style="background: #FF4D4F;"></span>
            <span>故障 (<70%)</span>
          </div>
        </div>
      </div>
      
      <div class="node-panel">
        <h2 class="panel-title">节点详情</h2>
        <div v-if="nodeDetails" class="node-info">
          <div class="info-header">
            <div class="info-icon" :style="{ background: getHealthColor(nodeDetails.health) }">
              {{ nodeDetails.type === 'router' ? 'R' : 'S' }}
            </div>
            <div class="info-title">
              <h3>{{ nodeDetails.name }}</h3>
              <span class="info-type">{{ nodeDetails.type === 'router' ? '路由器' : '交换机' }}</span>
            </div>
          </div>
          
          <div class="info-stats">
            <div class="stat-row">
              <span class="stat-label">健康状态</span>
              <div class="stat-value-row">
                <div class="health-bar-container">
                  <div
                    class="health-bar"
                    :style="{ width: `${nodeDetails.health}%`, background: getHealthColor(nodeDetails.health) }"
                  ></div>
                </div>
                <span :style="{ color: getHealthColor(nodeDetails.health) }">{{ nodeDetails.health }}%</span>
              </div>
            </div>
            <div class="stat-row">
              <span class="stat-label">设备类型</span>
              <span class="stat-value">{{ nodeDetails.type === 'router' ? '核心路由器' : '交换机' }}</span>
            </div>
            <div class="stat-row">
              <span class="stat-label">设备ID</span>
              <span class="stat-value">{{ nodeDetails.id }}</span>
            </div>
          </div>
          
          <div class="info-actions">
            <button class="action-btn">查看配置</button>
            <button class="action-btn secondary">执行诊断</button>
          </div>
        </div>
        <div v-else class="empty-state">
          <span class="empty-icon">👆</span>
          <p>点击拓扑图中的节点查看详情</p>
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

.topology-layout {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 24px;
}

.topology-canvas {
  background: rgba(30, 41, 59, 0.6);
  border-radius: 16px;
  padding: 24px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  position: relative;
}

.svg-canvas {
  width: 100%;
  height: 500px;
  background: rgba(15, 23, 42, 0.3);
  border-radius: 12px;
}

.link {
  stroke-width: 3;
  opacity: 0.8;
  transition: all 0.3s ease;
}

.link:hover {
  stroke-width: 5;
  opacity: 1;
}

.link.warning {
  animation: blink 1s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 0.8; }
  50% { opacity: 0.4; }
}

.node-group {
  cursor: pointer;
  transition: all 0.3s ease;
}

.node-group:hover .node-circle {
  filter: url(#glow);
}

.node-group.selected .node-circle {
  stroke: #165DFF;
  stroke-width: 3;
  filter: url(#glow);
}

.node-circle {
  transition: all 0.3s ease;
}

.node-inner {
  transition: all 0.3s ease;
}

.legend {
  position: absolute;
  bottom: 24px;
  right: 24px;
  display: flex;
  gap: 20px;
  padding: 12px 16px;
  background: rgba(15, 23, 42, 0.8);
  border-radius: 10px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #E2E8F0;
}

.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.node-panel {
  background: rgba(30, 41, 59, 0.6);
  border-radius: 16px;
  padding: 24px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: white;
  margin-bottom: 20px;
}

.node-info {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.info-header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.info-icon {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 24px;
  font-weight: 700;
}

.info-title h3 {
  font-size: 18px;
  font-weight: 600;
  color: white;
  margin-bottom: 4px;
}

.info-type {
  font-size: 13px;
  color: #64748B;
}

.info-stats {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-label {
  font-size: 13px;
  color: #94A3B8;
}

.stat-value {
  font-size: 14px;
  color: white;
  font-weight: 500;
}

.stat-value-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  justify-content: flex-end;
}

.health-bar-container {
  flex: 1;
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  overflow: hidden;
}

.health-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.info-actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

.action-btn {
  flex: 1;
  padding: 12px;
  background: linear-gradient(135deg, #165DFF 0%, #4080FF 100%);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
}

.action-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(22, 93, 255, 0.4);
}

.action-btn.secondary {
  background: rgba(255, 255, 255, 0.1);
}

.action-btn.secondary:hover {
  background: rgba(255, 255, 255, 0.15);
  box-shadow: none;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #64748B;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state p {
  font-size: 14px;
}
</style>