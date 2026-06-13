<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface MCPTool {
  id: string
  name: string
  description: string
  status: 'online' | 'offline' | 'error'
  lastCalled: string
  callCount: number
  version: string
}

const loading = ref(false)
const tools = ref<MCPTool[]>([
  { id: 'tool-001', name: 'network_scanner', description: '网络设备扫描工具', status: 'online', lastCalled: '5分钟前', callCount: 128, version: '1.2.0' },
  { id: 'tool-002', name: 'config_deployer', description: '配置下发工具', status: 'online', lastCalled: '15分钟前', callCount: 56, version: '2.0.1' },
  { id: 'tool-003', name: 'log_analyzer', description: '日志分析工具', status: 'offline', lastCalled: '2小时前', callCount: 34, version: '1.0.3' },
  { id: 'tool-004', name: 'health_checker', description: '健康检查工具', status: 'online', lastCalled: '1分钟前', callCount: 256, version: '1.5.0' },
  { id: 'tool-005', name: 'acl_manager', description: 'ACL规则管理工具', status: 'error', lastCalled: '30分钟前', callCount: 12, version: '1.1.0' }
])

const showRegisterDialog = ref(false)
const newToolName = ref('')
const newToolDesc = ref('')

async function fetchTools() {
  loading.value = true
  try {
    // TODO: 调用API获取工具列表
  } finally {
    loading.value = false
  }
}

function registerTool() {
  if (!newToolName.value.trim()) return
  tools.value.unshift({
    id: `tool-${Date.now()}`,
    name: newToolName.value,
    description: newToolDesc.value,
    status: 'offline',
    lastCalled: '从未调用',
    callCount: 0,
    version: '1.0.0'
  })
  newToolName.value = ''
  newToolDesc.value = ''
  showRegisterDialog.value = false
}

function testTool(tool: MCPTool) {
  alert(`测试工具: ${tool.name}`)
}

onMounted(() => {
  fetchTools()
})
</script>

<template>
  <div class="mcp-tools">
    <h1 class="page-title">MCP工具管理</h1>

    <div class="toolbar">
      <div class="stats-row">
        <div class="stat-chip online">在线 {{ tools.filter(t => t.status === 'online').length }}</div>
        <div class="stat-chip offline">离线 {{ tools.filter(t => t.status === 'offline').length }}</div>
        <div class="stat-chip error">异常 {{ tools.filter(t => t.status === 'error').length }}</div>
      </div>
      <button class="action-btn" @click="showRegisterDialog = true">+ 注册工具</button>
    </div>

    <div class="tool-grid">
      <div v-for="tool in tools" :key="tool.id" class="tool-card">
        <div class="tool-header">
          <div class="tool-name">{{ tool.name }}</div>
          <span :class="['status-dot', tool.status]"></span>
        </div>
        <div class="tool-desc">{{ tool.description }}</div>
        <div class="tool-meta">
          <span class="meta-item">v{{ tool.version }}</span>
          <span class="meta-item">调用 {{ tool.callCount }} 次</span>
          <span class="meta-item">{{ tool.lastCalled }}</span>
        </div>
        <div class="tool-actions">
          <button class="btn-sm" @click="testTool(tool)">测试</button>
          <button class="btn-sm secondary">配置</button>
        </div>
      </div>
    </div>

    <div v-if="showRegisterDialog" class="dialog-overlay" @click.self="showRegisterDialog = false">
      <div class="dialog-box">
        <h3 class="dialog-title">注册新工具</h3>
        <div class="form-group">
          <label>工具名称</label>
          <input v-model="newToolName" class="form-input" placeholder="输入工具名称" />
        </div>
        <div class="form-group">
          <label>工具描述</label>
          <textarea v-model="newToolDesc" class="form-input" placeholder="输入工具描述" rows="3"></textarea>
        </div>
        <div class="dialog-actions">
          <button class="btn-sm" @click="showRegisterDialog = false">取消</button>
          <button class="action-btn" @click="registerTool">注册</button>
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

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2xl);
}

.stats-row {
  display: flex;
  gap: var(--spacing-md);
}

.stat-chip {
  font-size: var(--font-size-sm);
  padding: var(--spacing-xs) var(--spacing-md-lg);
  border-radius: var(--radius-full);
  font-weight: var(--font-weight-medium);
}

.stat-chip.online { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); }
.stat-chip.offline { background: rgba(var(--color-text-quaternary-rgb), 0.2); color: var(--color-text-tertiary); }
.stat-chip.error { background: rgba(var(--color-error-rgb), 0.2); color: var(--color-error); }

.action-btn {
  padding: var(--spacing-sm-md) var(--spacing-xl);
  background: var(--gradient-primary);
  color: var(--color-white);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: all 0.3s ease;
}

.action-btn:hover { transform: translateY(-1px); box-shadow: 0 var(--spacing-2xs) var(--spacing-md) rgba(var(--color-primary-rgb), 0.4); }

.tool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--spacing-xl);
}

.tool-card {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  transition: all 0.3s ease;
}

.tool-card:hover { border-color: rgba(var(--color-primary-rgb), 0.3); transform: translateY(-2px); }

.tool-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.tool-name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-white);
  font-family: 'Courier New', monospace;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: var(--radius-full);
}

.status-dot.online { background: var(--color-success); box-shadow: 0 0 var(--spacing-sm) rgba(var(--color-success-rgb), 0.5); }
.status-dot.offline { background: var(--color-text-quaternary); }
.status-dot.error { background: var(--color-error); box-shadow: 0 0 var(--spacing-sm) rgba(var(--color-error-rgb), 0.5); animation: blink 1s infinite; }

@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.tool-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-lg);
}

.tool-meta {
  display: flex;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.meta-item {
  font-size: var(--font-size-sm);
  color: var(--color-text-quaternary);
}

.tool-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.btn-sm {
  padding: var(--spacing-xs) var(--spacing-md-lg);
  background: rgba(var(--color-primary-rgb), 0.2);
  color: var(--color-info-light);
  border: 1px solid rgba(var(--color-primary-rgb), 0.3);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-sm:hover { background: rgba(var(--color-primary-rgb), 0.3); }

.btn-sm.secondary {
  background: rgba(var(--color-text-quaternary-rgb), 0.2);
  color: var(--color-text-tertiary);
  border-color: rgba(var(--color-text-quaternary-rgb), 0.3);
}

.btn-sm.secondary:hover { background: rgba(var(--color-text-quaternary-rgb), 0.3); }

.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(var(--color-bg-base-rgb), 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.dialog-box {
  background: var(--color-bg-container);
  border-radius: var(--radius-2xl);
  padding: 28px;
  width: 420px;
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
}

.dialog-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-white);
  margin-bottom: var(--spacing-xl);
}

.form-group {
  margin-bottom: var(--spacing-lg);
}

.form-group label {
  display: block;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-xs);
}

.form-input {
  width: 100%;
  padding: var(--spacing-sm-md) var(--spacing-md-lg);
  background: rgba(var(--color-bg-base-rgb), 0.5);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-lg);
  color: var(--color-white);
  font-size: var(--font-size-base);
  font-family: inherit;
  resize: vertical;
}

.form-input:focus { outline: none; border-color: var(--color-primary); }

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-xl);
}
</style>
