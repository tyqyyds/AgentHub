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

const thinkingSteps = ref([])

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
  font-size: 24px;
  font-weight: 700;
  color: white;
  margin-bottom: 24px;
}

.workspace-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.intent-input-panel,
.intent-history-panel {
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

.input-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.intent-textarea {
  width: 100%;
  min-height: 150px;
  padding: 16px;
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.5);
  color: white;
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  transition: all 0.3s ease;
}

.intent-textarea:focus {
  outline: none;
  border-color: #165DFF;
  box-shadow: 0 0 0 4px rgba(22, 93, 255, 0.1);
}

.intent-textarea::placeholder {
  color: #64748B;
}

.submit-btn {
  padding: 14px 24px;
  background: linear-gradient(135deg, #165DFF 0%, #4080FF 100%);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(22, 93, 255, 0.4);
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.thinking-panel {
  margin-top: 20px;
  padding: 16px;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 12px;
}

.thinking-title {
  font-size: 14px;
  font-weight: 600;
  color: #69B1FF;
  margin-bottom: 12px;
}

.thinking-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.thinking-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #E2E8F0;
}

.step-dot {
  width: 8px;
  height: 8px;
  background: #165DFF;
  border-radius: 50%;
  animation: pulse 1s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.history-item {
  padding: 16px;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 12px;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.status-badge {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 12px;
  font-weight: 500;
}

.status-badge.completed {
  background: rgba(82, 196, 26, 0.2);
  color: #52C41A;
}

.status-badge.pending {
  background: rgba(255, 125, 0, 0.2);
  color: #FF7D00;
}

.status-badge.running {
  background: rgba(22, 93, 255, 0.2);
  color: #69B1FF;
}

.history-time {
  font-size: 12px;
  color: #64748B;
}

.history-input {
  font-size: 14px;
  color: white;
  margin-bottom: 12px;
  padding: 12px;
  background: rgba(22, 93, 255, 0.1);
  border-radius: 8px;
  border-left: 3px solid #165DFF;
}

.history-output {
  background: rgba(0, 0, 0, 0.3);
  border-radius: 8px;
  padding: 12px;
}

.history-output pre {
  font-size: 12px;
  color: #52C41A;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>