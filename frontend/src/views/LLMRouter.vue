<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface LLMProvider {
  id: string
  name: string
  model: string
  status: 'online' | 'degraded' | 'offline'
  latency: number
  rpm: number
  tokenUsage: number
  cost: number
}

interface RoutingRule {
  id: string
  name: string
  condition: string
  target: string
  priority: number
  enabled: boolean
}

const loading = ref(false)
const providers = ref<LLMProvider[]>([
  { id: 'LLM-001', name: 'DeepSeek V3', model: 'deepseek-chat', status: 'online', latency: 320, rpm: 58, tokenUsage: 1250000, cost: 18.5 },
  { id: 'LLM-002', name: '智谱GLM-4', model: 'glm-4-plus', status: 'online', latency: 450, rpm: 32, tokenUsage: 890000, cost: 22.3 },
  { id: 'LLM-003', name: 'Qwen2.5-72B', model: 'qwen-max', status: 'degraded', latency: 1200, rpm: 12, tokenUsage: 340000, cost: 8.7 },
  { id: 'LLM-004', name: 'GPT-4o-mini', model: 'gpt-4o-mini', status: 'offline', latency: 0, rpm: 0, tokenUsage: 0, cost: 0 }
])

const routingRules = ref<RoutingRule[]>([
  { id: 'RR-001', name: '网络运维意图', condition: 'intent.category == "network"', target: 'DeepSeek V3', priority: 1, enabled: true },
  { id: 'RR-002', name: '安全分析意图', condition: 'intent.category == "security"', target: '智谱GLM-4', priority: 1, enabled: true },
  { id: 'RR-003', name: '报告生成意图', condition: 'intent.category == "report"', target: 'Qwen2.5-72B', priority: 2, enabled: true },
  { id: 'RR-004', name: '故障降级路由', condition: 'provider.status != "online"', target: 'DeepSeek V3', priority: 99, enabled: true },
  { id: 'RR-005', name: '高复杂度意图', condition: 'intent.complexity > 0.8', target: '智谱GLM-4', priority: 3, enabled: false }
])

const activeTab = ref<'providers' | 'rules' | 'test'>('providers')
const showCreateRuleDialog = ref(false)
const newRule = ref({ name: '', condition: '', target: '', priority: 1 })

const testInput = ref('')
const testResult = ref<{ provider: string; latency: number; response: string } | null>(null)
const testLoading = ref(false)

function getStatusLabel(s: string) {
  return s === 'online' ? '在线' : s === 'degraded' ? '降级' : '离线'
}

function formatTokens(n: number) {
  return n >= 1000000 ? `${(n / 1000000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(0)}K` : String(n)
}

function toggleRule(rule: RoutingRule) {
  rule.enabled = !rule.enabled
}

function createRule() {
  if (!newRule.value.name.trim() || !newRule.value.condition.trim()) return
  routingRules.value.unshift({
    id: `RR-${String(routingRules.value.length + 1).padStart(3, '0')}`,
    name: newRule.value.name,
    condition: newRule.value.condition,
    target: newRule.value.target || providers.value[0]?.name || '',
    priority: newRule.value.priority,
    enabled: true
  })
  newRule.value = { name: '', condition: '', target: '', priority: 1 }
  showCreateRuleDialog.value = false
}

async function runTest() {
  if (!testInput.value.trim()) return
  testLoading.value = true
  testResult.value = null
  try {
    // 模拟路由测试
    await new Promise(r => setTimeout(r, 800))
    testResult.value = {
      provider: 'DeepSeek V3',
      latency: Math.floor(Math.random() * 500 + 200),
      response: `路由匹配: 规则"网络运维意图" → DeepSeek V3\n意图分类: network\n复杂度: 0.65\n预计Token: ~${Math.floor(Math.random() * 800 + 200)}`
    }
  } finally {
    testLoading.value = false
  }
}

onMounted(() => {
  // TODO: 调用API获取LLM路由配置
})
</script>

<template>
  <div class="llm-router">
    <h1 class="page-title">LLM路由</h1>

    <div class="tab-bar">
      <button :class="['tab-btn', { active: activeTab === 'providers' }]" @click="activeTab = 'providers'">服务状态</button>
      <button :class="['tab-btn', { active: activeTab === 'rules' }]" @click="activeTab = 'rules'">路由规则</button>
      <button :class="['tab-btn', { active: activeTab === 'test' }]" @click="activeTab = 'test'">路由测试</button>
    </div>

    <!-- 服务状态 -->
    <div v-if="activeTab === 'providers'" class="provider-grid">
      <div v-for="p in providers" :key="p.id" class="provider-card">
        <div class="card-top">
          <div class="provider-name">{{ p.name }}</div>
          <span :class="['status-dot', p.status]"></span>
        </div>
        <div class="model-tag">{{ p.model }}</div>
        <div class="metrics-grid">
          <div class="metric">
            <div class="metric-value">{{ p.status === 'offline' ? '-' : `${p.latency}ms` }}</div>
            <div class="metric-label">延迟</div>
          </div>
          <div class="metric">
            <div class="metric-value">{{ p.rpm }}</div>
            <div class="metric-label">RPM</div>
          </div>
          <div class="metric">
            <div class="metric-value">{{ formatTokens(p.tokenUsage) }}</div>
            <div class="metric-label">Token用量</div>
          </div>
          <div class="metric">
            <div class="metric-value">¥{{ p.cost.toFixed(1) }}</div>
            <div class="metric-label">今日费用</div>
          </div>
        </div>
        <div class="card-footer">
          <span :class="['status-text', p.status]">{{ getStatusLabel(p.status) }}</span>
        </div>
      </div>
    </div>

    <!-- 路由规则 -->
    <div v-if="activeTab === 'rules'" class="rules-section">
      <div class="toolbar">
        <div class="rule-count">共 {{ routingRules.length }} 条规则</div>
        <button class="action-btn" @click="showCreateRuleDialog = true">+ 新增规则</button>
      </div>
      <div class="rule-list">
        <div v-for="rule in routingRules" :key="rule.id" class="rule-card">
          <div class="rule-header">
            <span class="rule-id">{{ rule.id }}</span>
            <span class="priority-tag">P{{ rule.priority }}</span>
            <span :class="['enable-tag', { on: rule.enabled, off: !rule.enabled }]">{{ rule.enabled ? '启用' : '禁用' }}</span>
          </div>
          <div class="rule-name">{{ rule.name }}</div>
          <div class="rule-condition"><code>{{ rule.condition }}</code></div>
          <div class="rule-target">→ {{ rule.target }}</div>
          <div class="rule-actions">
            <button class="btn-sm" @click="toggleRule(rule)">{{ rule.enabled ? '禁用' : '启用' }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 路由测试 -->
    <div v-if="activeTab === 'test'" class="test-section">
      <div class="test-panel">
        <div class="form-group">
          <label>输入意图文本</label>
          <textarea v-model="testInput" class="form-textarea" placeholder="例如: 重启核心交换机SW-CORE-01并检查BGP邻居状态" rows="3"></textarea>
        </div>
        <button class="action-btn" :disabled="testLoading" @click="runTest">{{ testLoading ? '测试中...' : '执行路由测试' }}</button>
      </div>
      <div v-if="testResult" class="test-result">
        <div class="result-header">测试结果</div>
        <div class="result-body">
          <div class="result-item"><span class="label">路由目标</span><span>{{ testResult.provider }}</span></div>
          <div class="result-item"><span class="label">模拟延迟</span><span>{{ testResult.latency }}ms</span></div>
          <div class="result-detail">
            <pre>{{ testResult.response }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- 新增规则对话框 -->
    <div v-if="showCreateRuleDialog" class="dialog-overlay" @click.self="showCreateRuleDialog = false">
      <div class="dialog-box">
        <h3 class="dialog-title">新增路由规则</h3>
        <div class="form-group">
          <label>规则名称</label>
          <input v-model="newRule.name" class="form-input" placeholder="输入规则名称" />
        </div>
        <div class="form-group">
          <label>匹配条件</label>
          <input v-model="newRule.condition" class="form-input" placeholder="例如: intent.category == 'network'" />
          <div class="form-hint">支持条件表达式: intent.category, intent.complexity, provider.status</div>
        </div>
        <div class="form-group">
          <label>目标LLM</label>
          <select v-model="newRule.target" class="form-input">
            <option v-for="p in providers" :key="p.id" :value="p.name">{{ p.name }}</option>
          </select>
        </div>
        <div class="form-group">
          <label>优先级</label>
          <input v-model.number="newRule.priority" type="number" class="form-input" min="1" max="99" />
        </div>
        <div class="dialog-actions">
          <button class="btn-sm" @click="showCreateRuleDialog = false">取消</button>
          <button class="action-btn" @click="createRule">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); color: var(--color-white); margin-bottom: var(--spacing-2xl); }

.tab-bar { display: flex; gap: var(--spacing-2xs); margin-bottom: var(--spacing-2xl); background: rgba(var(--color-bg-elevated-rgb), 0.6); border-radius: var(--radius-lg); padding: var(--spacing-2xs); width: fit-content; }
.tab-btn { padding: var(--spacing-sm) var(--spacing-xl); background: transparent; color: var(--color-text-tertiary); border: none; border-radius: var(--radius-lg); font-size: var(--font-size-base); cursor: pointer; }
.tab-btn.active { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); font-weight: var(--font-weight-semibold); }

/* Providers */
.provider-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--spacing-lg); }
.provider-card { background: rgba(var(--color-bg-elevated-rgb), 0.6); border-radius: var(--radius-xl); border: 1px solid rgba(var(--color-white-rgb), 0.1); padding: var(--spacing-xl); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-sm); }
.provider-name { font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--color-white); }
.status-dot { width: 10px; height: 10px; border-radius: 50%; }
.status-dot.online { background: var(--color-success); box-shadow: 0 0 var(--spacing-xs) rgba(var(--color-success-rgb), 0.5); }
.status-dot.degraded { background: var(--color-warning); box-shadow: 0 0 var(--spacing-xs) rgba(var(--color-warning-rgb), 0.5); }
.status-dot.offline { background: var(--color-error); }
.model-tag { font-size: var(--font-size-sm); color: var(--color-info-light); background: rgba(var(--color-primary-rgb), 0.1); padding: var(--spacing-3xs) var(--spacing-sm); border-radius: var(--spacing-2xs); display: inline-block; margin-bottom: var(--spacing-md-lg); font-family: monospace; }
.metrics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-sm-md); }
.metric { text-align: center; }
.metric-value { font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold); color: var(--color-text-secondary); }
.metric-label { font-size: var(--font-size-xs); color: var(--color-text-quaternary); margin-top: var(--spacing-3xs); }
.card-footer { margin-top: var(--spacing-md-lg); padding-top: var(--spacing-md); border-top: 1px solid rgba(var(--color-white-rgb), 0.05); }
.status-text { font-size: var(--font-size-sm); font-weight: var(--font-weight-medium); }
.status-text.online { color: var(--color-success); }
.status-text.degraded { color: var(--color-warning); }
.status-text.offline { color: var(--color-error); }

/* Rules */
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-lg); }
.rule-count { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.action-btn { padding: var(--spacing-sm-md) var(--spacing-xl); background: var(--gradient-primary); color: var(--color-white); border: none; border-radius: var(--radius-lg); font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); cursor: pointer; }
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.rule-list { display: flex; flex-direction: column; gap: var(--spacing-sm-md); }
.rule-card { background: rgba(var(--color-bg-elevated-rgb), 0.6); border-radius: var(--radius-xl); border: 1px solid rgba(var(--color-white-rgb), 0.1); padding: var(--spacing-md) var(--spacing-xl); }
.rule-header { display: flex; align-items: center; gap: var(--spacing-sm); margin-bottom: var(--spacing-xs); }
.rule-id { font-size: var(--font-size-xs); color: var(--color-text-quaternary); font-family: monospace; }
.priority-tag { font-size: var(--font-size-xs); padding: var(--spacing-3xs) var(--spacing-sm); border-radius: var(--spacing-2xs); background: rgba(var(--color-primary-rgb), 0.15); color: var(--color-info-light); }
.enable-tag { font-size: var(--font-size-xs); padding: var(--spacing-3xs) var(--spacing-sm); border-radius: var(--spacing-2xs); }
.enable-tag.on { background: rgba(var(--color-success-rgb), 0.2); color: var(--color-success); }
.enable-tag.off { background: rgba(var(--color-text-quaternary-rgb), 0.2); color: var(--color-text-quaternary); }
.rule-name { font-size: var(--font-size-md); font-weight: var(--font-weight-medium); color: var(--color-white); margin-bottom: var(--spacing-xs); }
.rule-condition { margin-bottom: var(--spacing-2xs); }
.rule-condition code { font-size: var(--font-size-sm); color: var(--color-info-light); background: rgba(var(--color-primary-rgb), 0.1); padding: var(--spacing-3xs) var(--spacing-sm); border-radius: var(--spacing-2xs); }
.rule-target { font-size: var(--font-size-sm); color: var(--color-warning); }
.rule-actions { margin-top: var(--spacing-sm-md); }
.btn-sm { padding: var(--spacing-3xs) var(--spacing-md); background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); border: 1px solid rgba(var(--color-primary-rgb), 0.3); border-radius: var(--radius-md); font-size: var(--font-size-sm); cursor: pointer; }

/* Test */
.test-panel { background: rgba(var(--color-bg-elevated-rgb), 0.6); border-radius: var(--radius-xl); border: 1px solid rgba(var(--color-white-rgb), 0.1); padding: var(--spacing-2xl); margin-bottom: var(--spacing-xl); }
.form-group { margin-bottom: var(--spacing-lg); }
.form-group label { display: block; font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-bottom: var(--spacing-xs); }
.form-input { width: 100%; padding: var(--spacing-sm-md) var(--spacing-md-lg); background: rgba(var(--color-bg-base-rgb), 0.5); border: 1px solid rgba(var(--color-white-rgb), 0.1); border-radius: var(--radius-lg); color: var(--color-white); font-size: var(--font-size-base); }
.form-input:focus { outline: none; border-color: var(--color-primary); }
.form-textarea { width: 100%; padding: var(--spacing-sm-md) var(--spacing-md-lg); background: rgba(var(--color-bg-base-rgb), 0.5); border: 1px solid rgba(var(--color-white-rgb), 0.1); border-radius: var(--radius-lg); color: var(--color-white); font-size: var(--font-size-base); resize: vertical; font-family: inherit; }
.form-textarea:focus { outline: none; border-color: var(--color-primary); }
.form-hint { font-size: var(--font-size-xs); color: var(--color-text-quaternary); margin-top: var(--spacing-2xs); }
.test-result { background: rgba(var(--color-bg-elevated-rgb), 0.6); border-radius: var(--radius-xl); border: 1px solid rgba(var(--color-success-rgb), 0.3); overflow: hidden; }
.result-header { padding: var(--spacing-md) var(--spacing-xl); background: rgba(var(--color-success-rgb), 0.1); font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); color: var(--color-success); }
.result-body { padding: var(--spacing-xl); }
.result-item { font-size: var(--font-size-sm); color: var(--color-text-secondary); margin-bottom: var(--spacing-sm); }
.result-item .label { color: var(--color-text-quaternary); margin-right: var(--spacing-sm); }
.result-detail { margin-top: var(--spacing-md); }
.result-detail pre { font-size: var(--font-size-sm); color: var(--color-text-tertiary); background: rgba(var(--color-bg-base-rgb), 0.5); padding: var(--spacing-md-lg); border-radius: var(--radius-lg); white-space: pre-wrap; font-family: monospace; }

/* Dialog */
.dialog-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; justify-content: center; z-index: var(--z-modal); }
.dialog-box { background: var(--color-bg-container); border-radius: var(--radius-2xl); padding: 28px; width: 480px; border: 1px solid rgba(var(--color-white-rgb), 0.1); }
.dialog-title { font-size: var(--font-size-xl); font-weight: var(--font-weight-semibold); color: var(--color-white); margin-bottom: var(--spacing-xl); }
.dialog-actions { display: flex; justify-content: flex-end; gap: var(--spacing-sm); margin-top: var(--spacing-xl); }
</style>
