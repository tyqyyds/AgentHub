<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface KnowledgeDoc {
  id: string
  title: string
  category: string
  tags: string[]
  updatedAt: string
  author: string
  summary: string
}

const loading = ref(false)
const searchQuery = ref('')
const documents = ref<KnowledgeDoc[]>([
  { id: 'DOC-001', title: 'QoS策略配置指南', category: '配置规范', tags: ['QoS', '策略', '配置'], updatedAt: '2026-06-12', author: '张工', summary: '涵盖QoS策略的配置方法、最佳实践和常见问题排查' },
  { id: 'DOC-002', title: '防火墙ACL规则手册', category: '安全规范', tags: ['ACL', '防火墙', '安全'], updatedAt: '2026-06-10', author: '李工', summary: '防火墙ACL规则的编写规范、审核流程和变更管理' },
  { id: 'DOC-003', title: '网络故障排查手册', category: '运维手册', tags: ['故障', '排查', '运维'], updatedAt: '2026-06-08', author: '王工', summary: '常见网络故障的排查步骤、工具使用和解决方案' },
  { id: 'DOC-004', title: 'BGP路由策略文档', category: '配置规范', tags: ['BGP', '路由', '策略'], updatedAt: '2026-06-05', author: '赵工', summary: 'BGP路由策略的设计原则、配置模板和验证方法' }
])

const ragQuestion = ref('')
const ragAnswer = ref('')
const isRagLoading = ref(false)

const categories = ref(['全部', '配置规范', '安全规范', '运维手册', '架构设计'])

async function searchDocuments() {
  // TODO: 调用API搜索文档
}

async function askRag() {
  if (!ragQuestion.value.trim()) return
  isRagLoading.value = true
  try {
    // TODO: 调用RAG问答API
    ragAnswer.value = `基于知识库分析，关于"${ragQuestion.value}"的回答：\n\n建议参考QoS策略配置指南（DOC-001），其中详细描述了带宽保障的配置方法。核心步骤包括：1) 定义流量分类规则 2) 配置带宽策略 3) 应用到目标接口。`
  } finally {
    isRagLoading.value = false
  }
}

onMounted(() => {
  // TODO: 调用API获取文档列表
})
</script>

<template>
  <div class="knowledge-base">
    <h1 class="page-title">知识库</h1>

    <div class="layout">
      <div class="main-panel">
        <div class="search-bar">
          <input
            v-model="searchQuery"
            class="search-input"
            placeholder="搜索知识文档..."
            @keyup.enter="searchDocuments"
          />
          <button class="search-btn" @click="searchDocuments">搜索</button>
        </div>

        <div class="category-tabs">
          <span v-for="cat in categories" :key="cat" :class="['cat-chip', { active: cat === '全部' }]">
            {{ cat }}
          </span>
        </div>

        <div class="doc-list">
          <div v-for="doc in documents" :key="doc.id" class="doc-card">
            <div class="doc-header">
              <span class="doc-id">{{ doc.id }}</span>
              <span class="doc-category">{{ doc.category }}</span>
            </div>
            <div class="doc-title">{{ doc.title }}</div>
            <div class="doc-summary">{{ doc.summary }}</div>
            <div class="doc-tags">
              <span v-for="tag in doc.tags" :key="tag" class="tag">{{ tag }}</span>
            </div>
            <div class="doc-footer">
              <span>👤 {{ doc.author }}</span>
              <span>📅 {{ doc.updatedAt }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="rag-panel">
        <h2 class="panel-title">🤖 RAG智能问答</h2>
        <div class="rag-input-area">
          <textarea
            v-model="ragQuestion"
            class="rag-input"
            placeholder="输入您的问题，AI将基于知识库回答..."
            rows="3"
          ></textarea>
          <button class="action-btn" @click="askRag" :disabled="isRagLoading">
            {{ isRagLoading ? '思考中...' : '提问' }}
          </button>
        </div>
        <div v-if="ragAnswer" class="rag-answer">
          <div class="answer-label">AI回答</div>
          <div class="answer-content">{{ ragAnswer }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-title { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); color: var(--color-white); margin-bottom: var(--spacing-2xl); }

.layout { display: grid; grid-template-columns: 2fr 1fr; gap: var(--spacing-2xl); }

.main-panel { display: flex; flex-direction: column; gap: var(--spacing-lg); }

.search-bar { display: flex; gap: var(--spacing-sm); }

.search-input {
  flex: 1;
  padding: var(--spacing-md) var(--spacing-lg);
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-lg);
  color: var(--color-white);
  font-size: var(--font-size-base);
}

.search-input:focus { outline: none; border-color: var(--color-primary); }
.search-input::placeholder { color: var(--color-text-quaternary); }

.search-btn {
  padding: var(--spacing-md) var(--spacing-2xl);
  background: rgba(var(--color-primary-rgb), 0.2);
  color: var(--color-info-light);
  border: 1px solid rgba(var(--color-primary-rgb), 0.3);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-base);
  cursor: pointer;
}

.category-tabs { display: flex; gap: var(--spacing-sm); flex-wrap: wrap; }

.cat-chip {
  font-size: var(--font-size-sm);
  padding: 5px var(--spacing-md-lg);
  border-radius: var(--radius-2xl);
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  color: var(--color-text-tertiary);
  cursor: pointer;
  transition: all 0.2s;
}

.cat-chip.active { background: rgba(var(--color-primary-rgb), 0.2); color: var(--color-info-light); }

.doc-list { display: flex; flex-direction: column; gap: var(--spacing-md); }

.doc-card {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-xl);
  padding: var(--spacing-lg) var(--spacing-xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  transition: all 0.2s;
}

.doc-card:hover { border-color: rgba(var(--color-primary-rgb), 0.3); }

.doc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-sm); }
.doc-id { font-size: var(--font-size-sm); color: var(--color-text-quaternary); font-family: monospace; }
.doc-category { font-size: var(--font-size-xs); padding: 2px var(--spacing-sm-md); border-radius: var(--radius-lg); background: rgba(var(--color-primary-rgb), 0.15); color: var(--color-info-light); }

.doc-title { font-size: var(--font-size-md); font-weight: var(--font-weight-semibold); color: var(--color-white); margin-bottom: var(--spacing-xs); }
.doc-summary { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-bottom: var(--spacing-sm-md); line-height: 1.5; }

.doc-tags { display: flex; gap: var(--spacing-xs); margin-bottom: var(--spacing-sm-md); }

.tag {
  font-size: var(--font-size-xs);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-md);
  background: rgba(var(--color-text-quaternary-rgb), 0.15);
  color: var(--color-text-tertiary);
}

.doc-footer { display: flex; gap: var(--spacing-lg); font-size: var(--font-size-sm); color: var(--color-text-quaternary); }

.rag-panel {
  background: rgba(var(--color-bg-elevated-rgb), 0.6);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-2xl);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  height: fit-content;
  position: sticky;
  top: var(--spacing-xl);
}

.panel-title { font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--color-white); margin-bottom: var(--spacing-lg); }

.rag-input-area { display: flex; flex-direction: column; gap: var(--spacing-sm-md); }

.rag-input {
  width: 100%;
  padding: var(--spacing-md);
  background: rgba(var(--color-bg-base-rgb), 0.5);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-lg);
  color: var(--color-white);
  font-size: var(--font-size-sm);
  font-family: inherit;
  resize: vertical;
}

.rag-input:focus { outline: none; border-color: var(--color-primary); }
.rag-input::placeholder { color: var(--color-text-quaternary); }

.action-btn {
  padding: var(--spacing-sm-md) var(--spacing-xl);
  background: var(--gradient-primary);
  color: var(--color-white);
  border: none;
  border-radius: var(--radius-lg);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.rag-answer {
  margin-top: var(--spacing-lg);
  padding: var(--spacing-md-lg);
  background: rgba(var(--color-bg-base-rgb), 0.5);
  border-radius: var(--radius-lg);
  border-left: 3px solid var(--color-primary);
}

.answer-label { font-size: var(--font-size-sm); color: var(--color-info-light); font-weight: var(--font-weight-semibold); margin-bottom: var(--spacing-sm); }
.answer-content { font-size: var(--font-size-sm); color: var(--color-text-secondary); line-height: 1.6; white-space: pre-line; }
</style>
