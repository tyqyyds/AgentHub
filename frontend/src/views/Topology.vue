<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

interface TopoNode {
  id: string
  name: string
  type: string
  health: number
  x: number
  y: number
}

const selectedNode = ref<string | null>(null)
const nodeDetails = ref<TopoNode | null>(null)

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

const handleNodeClick = (node: TopoNode) => {
  selectedNode.value = node.id
  nodeDetails.value = node
}

const getHealthLevel = (health: number): string => {
  if (health >= 90) return 'good'
  if (health >= 70) return 'warning'
  return 'bad'
}

let animationFrame: number | null = null

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
              <stop offset="0%" class="gradient-start" />
              <stop offset="100%" class="gradient-end" />
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
              :stroke="link.status === 'warning' ? 'var(--color-warning)' : 'url(#linkGradient)'"
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
                :class="['node-circle', 'health-' + getHealthLevel(node.health)]"
              />
              <circle
                :cx="node.x"
                :cy="node.y"
                r="25"
                class="node-inner"
              />
              <text
                :x="node.x"
                :y="node.y + 5"
                text-anchor="middle"
                class="node-type-text"
              >
                {{ node.type === 'router' ? 'R' : 'S' }}
              </text>
              <text
                :x="node.x"
                :y="node.y + 55"
                text-anchor="middle"
                class="node-name-text"
              >
                {{ node.name.split(' ')[0] }}
              </text>
            </g>
          </g>
        </svg>
        
        <div class="legend">
          <div class="legend-item">
            <span class="legend-dot health-good"></span>
            <span>健康 (≥90%)</span>
          </div>
          <div class="legend-item">
            <span class="legend-dot health-warning"></span>
            <span>警告 (70-89%)</span>
          </div>
          <div class="legend-item">
            <span class="legend-dot health-bad"></span>
            <span>故障 (<70%)</span>
          </div>
        </div>
      </div>
      
      <div class="node-panel">
        <h2 class="panel-title">节点详情</h2>
        <div v-if="nodeDetails" class="node-info">
          <div class="info-header">
            <div class="info-icon" :class="'health-bg-' + getHealthLevel(nodeDetails.health)">
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
                    :class="'health-bg-' + getHealthLevel(nodeDetails.health)"
                    :style="{ width: `${nodeDetails.health}%` }"
                  ></div>
                </div>
                <span :class="'health-text-' + getHealthLevel(nodeDetails.health)">{{ nodeDetails.health }}%</span>
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
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-white);
  margin-bottom: var(--spacing-2xl);
}

.topology-layout {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: var(--spacing-2xl);
}

.topology-canvas {
  background: rgba(var(--color-bg-container-rgb), 0.6);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-2xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  position: relative;
}

.svg-canvas {
  width: 100%;
  height: 500px;
  background: rgba(var(--color-bg-base-rgb), 0.3);
  border-radius: var(--radius-xl);
}

/* SVG gradient stops */
.gradient-start {
  stop-color: var(--color-primary);
}

.gradient-end {
  stop-color: var(--color-info-light);
}

/* Health state fills for SVG circles */
.health-good {
  fill: var(--color-success);
}

.health-warning {
  fill: var(--color-warning);
}

.health-bad {
  fill: var(--color-error);
}

.node-inner {
  fill: var(--color-bg-container);
  transition: all 0.3s ease;
}

.node-type-text {
  fill: var(--color-white);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.node-name-text {
  fill: var(--color-text-secondary);
  font-size: var(--font-size-xs);
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
  stroke: var(--color-primary);
  stroke-width: 3;
  filter: url(#glow);
}

.node-circle {
  transition: all 0.3s ease;
}

.legend {
  position: absolute;
  bottom: var(--spacing-2xl);
  right: var(--spacing-2xl);
  display: flex;
  gap: var(--spacing-xl);
  padding: var(--spacing-md) var(--spacing-lg);
  background: rgba(var(--color-bg-base-rgb), 0.8);
  border-radius: var(--radius-lg);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.legend-dot {
  width: var(--font-size-sm);
  height: var(--font-size-sm);
  border-radius: var(--radius-full);
}

/* Legend dot health states */
.legend-dot.health-good {
  background: var(--color-success);
}

.legend-dot.health-warning {
  background: var(--color-warning);
}

.legend-dot.health-bad {
  background: var(--color-error);
}

.node-panel {
  background: rgba(var(--color-bg-container-rgb), 0.6);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-2xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
}

.panel-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-white);
  margin-bottom: var(--spacing-xl);
}

.node-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.info-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
}

.info-icon {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-white);
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
}

/* Info icon health background states */
.info-icon.health-bg-good {
  background: var(--color-success);
}

.info-icon.health-bg-warning {
  background: var(--color-warning);
}

.info-icon.health-bg-bad {
  background: var(--color-error);
}

.info-title h3 {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-white);
  margin-bottom: var(--spacing-2xs);
}

.info-type {
  font-size: var(--font-size-md);
  color: var(--color-text-quaternary);
}

.info-stats {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-label {
  font-size: var(--font-size-md);
  color: var(--color-text-tertiary);
}

.stat-value {
  font-size: var(--font-size-base);
  color: var(--color-white);
  font-weight: var(--font-weight-medium);
}

.stat-value-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  flex: 1;
  justify-content: flex-end;
}

.health-bar-container {
  flex: 1;
  height: var(--spacing-xs);
  background: rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.health-bar {
  height: 100%;
  border-radius: var(--radius-xs);
  transition: width 0.3s ease;
}

/* Health bar background states */
.health-bar.health-bg-good {
  background: var(--color-success);
}

.health-bar.health-bg-warning {
  background: var(--color-warning);
}

.health-bar.health-bg-bad {
  background: var(--color-error);
}

/* Health text color states */
.health-text-good {
  color: var(--color-success);
}

.health-text-warning {
  color: var(--color-warning);
}

.health-text-bad {
  color: var(--color-error);
}

.info-actions {
  display: flex;
  gap: var(--spacing-md);
  margin-top: var(--spacing-xl);
}

.action-btn {
  flex: 1;
  padding: var(--spacing-md);
  background: var(--gradient-primary);
  color: var(--color-white);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all 0.3s ease;
}

.action-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 var(--spacing-sm) var(--spacing-md) rgba(var(--color-primary-rgb), 0.4);
}

.action-btn.secondary {
  background: rgba(var(--color-white-rgb), 0.1);
}

.action-btn.secondary:hover {
  background: rgba(var(--color-white-rgb), 0.15);
  box-shadow: none;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px var(--spacing-xl);
  color: var(--color-text-quaternary);
}

.empty-icon {
  font-size: var(--font-size-6xl);
  margin-bottom: var(--spacing-lg);
}

.empty-state p {
  font-size: var(--font-size-base);
}
</style>