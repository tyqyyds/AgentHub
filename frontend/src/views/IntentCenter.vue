<script setup lang="ts">
import { ref } from 'vue'

const intentInput = ref('')
const isProcessing = ref(false)
const intentHistory = ref([
  {
    id: 1,
    userInput: '保证研发子网视频会议流量最小200M带宽',
    structuredOutput: {
      intent_name: 'bandwidth_guarantee',
      targets: ['研发子网'],
      actions: [{ type: 'qos', params: { min_bw: '200M' } }]
    },
    status: 'completed',
    timestamp: '2026-05-21 09:30:00'
  },
  {
    id: 2,
    userInput: '开放研发网到生产网数据库的访问',
    structuredOutput: {
      intent_name: 'access_control',
      targets: ['研发网', '生产网'],
      actions: [{ type: 'acl', params: { source: '研发网', destination: '生产网数据库' } }]
    },
    status: 'pending',
    timestamp: '2026-05-21 10:15:00'
  }
])

const thinkingSteps = ref<string[]>([])

const submitIntent = async () => {
  if (!intentInput.value.trim()) return
  
  isProcessing.value = true
  thinkingSteps.value = [
    '正在解析用户意图...',
    '正在提取结构化参数...',
    '正在匹配策略模板...',
    '正在生成配置命令...',
    '正在等待审批...'
  ]
  
  for (let i = 0; i < thinkingSteps.value.length; i++) {
    await new Promise(resolve => setTimeout(resolve, 500))
  }
  
  const newIntent = {
    id: Date.now(),
    userInput: intentInput.value,
    structuredOutput: {
      intent_name: 'bandwidth_guarantee',
      targets: ['目标网络'],
      actions: [{ type: 'qos', params: { min_bw: '100M' } }]
    },
    status: 'pending',
    timestamp: new Date().toLocaleString('zh-CN')
  }
  
  intentHistory.value.unshift(newIntent)
  intentInput.value = ''
  isProcessing.value = false
  thinkingSteps.value = []
}
</script>

<template>
  <div class="intent-center">
    <h1 class="page-title">智能副驾工作台</h1>
    
    <div class="workspace-layout">
      <div class="intent-input-panel">
        <h2 class="panel-title">意图输入</h2>
        <div class="input-container">
          <textarea
            v-model="intentInput"
            class="intent-textarea"
            placeholder="请输入您的网络运维意图，例如：&#10;保证研发子网视频会议流量最小200M带宽&#10;开放研发网到生产网数据库的访问"
            :disabled="isProcessing"
          ></textarea>
          <button
            class="submit-btn"
            :disabled="!intentInput.trim() || isProcessing"
            @click="submitIntent"
          >
            {{ isProcessing ? '处理中...' : '提交意图' }}
          </button>
        </div>
        
        <div v-if="thinkingSteps.length > 0" class="thinking-panel">
          <h3 class="thinking-title">🤖 思考过程</h3>
          <div class="thinking-steps">
            <div
              v-for="(step, index) in thinkingSteps"
              :key="index"
              class="thinking-step"
            >
              <span class="step-dot"></span>
              <span>{{ step }}</span>
            </div>
          </div>
        </div>
      </div>
      
      <div class="intent-history-panel">
        <h2 class="panel-title">意图执行历史</h2>
        <div class="history-list">
          <div
            v-for="intent in intentHistory"
            :key="intent.id"
            class="history-item"
          >
            <div class="history-header">
              <span :class="['status-badge', intent.status]">
                {{ intent.status === 'completed' ? '已完成' : intent.status === 'pending' ? '待审批' : '执行中' }}
              </span>
              <span class="history-time">{{ intent.timestamp }}</span>
            </div>
            <div class="history-input">{{ intent.userInput }}</div>
            <div class="history-output">
              <pre>{{ JSON.stringify(intent.structuredOutput, null, 2) }}</pre>
            </div>
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

.workspace-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-2xl);
}

.intent-input-panel,
.intent-history-panel {
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

.input-container {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.intent-textarea {
  width: 100%;
  min-height: 150px;
  padding: var(--spacing-lg);
  border: 2px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-lg);
  background: rgba(var(--color-bg-base-rgb), 0.5);
  color: var(--color-white);
  font-size: var(--font-size-base);
  font-family: inherit;
  resize: vertical;
  transition: all 0.3s ease;
}

.intent-textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 var(--spacing-2xs) rgba(var(--color-primary-rgb), 0.1);
}

.intent-textarea::placeholder {
  color: var(--color-text-quaternary);
}

.submit-btn {
  padding: 14px var(--spacing-2xl);
  background: var(--gradient-primary);
  color: var(--color-white);
  border: none;
  border-radius: 10px;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: all 0.3s ease;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 var(--spacing-xs) var(--spacing-xl) rgba(var(--color-primary-rgb), 0.4);
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.thinking-panel {
  margin-top: var(--spacing-xl);
  padding: var(--spacing-lg);
  background: rgba(var(--color-bg-base-rgb), 0.5);
  border-radius: var(--radius-lg);
}

.thinking-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-info-light);
  margin-bottom: var(--spacing-md);
}

.thinking-steps {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.thinking-step {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.step-dot {
  width: var(--spacing-sm);
  height: var(--spacing-sm);
  background: var(--color-primary);
  border-radius: var(--radius-full);
  animation: pulse 1s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.history-item {
  padding: var(--spacing-lg);
  background: rgba(var(--color-bg-base-rgb), 0.5);
  border-radius: var(--radius-lg);
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.status-badge {
  font-size: var(--font-size-xs);
  padding: var(--spacing-2xs) var(--spacing-md);
  border-radius: var(--radius-lg);
  font-weight: var(--font-weight-medium);
}

.status-badge.completed {
  background: rgba(var(--color-success-rgb), 0.2);
  color: var(--color-success);
}

.status-badge.pending {
  background: rgba(var(--color-orange-rgb), 0.2);
  color: var(--color-orange);
}

.status-badge.running {
  background: rgba(var(--color-primary-rgb), 0.2);
  color: var(--color-info-light);
}

.history-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
}

.history-input {
  font-size: var(--font-size-base);
  color: var(--color-white);
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-md);
  background: rgba(var(--color-primary-rgb), 0.1);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-primary);
}

.history-output {
  background: rgba(0, 0, 0, 0.3);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
}

.history-output pre {
  font-size: var(--font-size-xs);
  color: var(--color-success);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>