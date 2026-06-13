<script setup lang="ts">
import { ref } from 'vue'
import { ElTabs, ElTabPane, ElCard, ElTag } from 'element-plus'
import { api } from '@/utils/apiClient'

interface IntentTemplate {
  id: string
  name: string
  description: string
  tags: string[]
  usageCount: number
  category: string
}

defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
  select: [template: IntentTemplate]
}>()

const activeTab = ref('common')
const templates = ref<IntentTemplate[]>([])
const loading = ref(false)

const mockTemplates: IntentTemplate[] = [
  { id: '1', name: '带宽保障', description: '为关键业务保障网络带宽', tags: ['QoS', '带宽'], usageCount: 128, category: 'common' },
  { id: '2', name: '故障自愈', description: '自动检测并修复网络故障', tags: ['自愈', '故障'], usageCount: 96, category: 'common' },
  { id: '3', name: '安全策略更新', description: '批量更新防火墙ACL规则', tags: ['安全', 'ACL'], usageCount: 72, category: 'common' },
  { id: '4', name: '链路切换', description: '主备链路自动切换', tags: ['冗余', '切换'], usageCount: 54, category: 'common' },
  { id: '5', name: '流量分析', description: '分析网络流量模式和异常', tags: ['流量', '分析'], usageCount: 45, category: 'recommend' },
  { id: '6', name: '设备巡检', description: '定期自动巡检网络设备', tags: ['巡检', '运维'], usageCount: 38, category: 'recommend' },
  { id: '7', name: '配置备份', description: '自动备份网络设备配置', tags: ['备份', '配置'], usageCount: 31, category: 'recent' },
  { id: '8', name: '性能优化', description: '基于AI的网络性能优化建议', tags: ['优化', 'AI'], usageCount: 27, category: 'recommend' }
]

async function loadTemplates() {
  loading.value = true
  try {
    const data = await api.get<IntentTemplate[]>('/api/v1/assistant/templates')
    templates.value = data
  } catch {
    templates.value = mockTemplates
  } finally {
    loading.value = false
  }
}

function getFilteredTemplates(category: string) {
  return templates.value.filter((t) => t.category === category)
}

function handleSelect(template: IntentTemplate) {
  emit('select', template)
}

loadTemplates()
</script>

<template>
  <transition name="slide">
    <div v-if="visible" class="template-panel">
      <div class="panel-header">
        <span class="header-title">意图模板</span>
        <button class="close-btn" @click="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <ElTabs v-model="activeTab" class="template-tabs">
        <ElTabPane label="常用模板" name="common">
          <div class="template-grid">
            <ElCard
              v-for="tpl in getFilteredTemplates('common')"
              :key="tpl.id"
              shadow="hover"
              class="template-card"
              @click="handleSelect(tpl)"
            >
              <div class="tpl-name">{{ tpl.name }}</div>
              <div class="tpl-desc">{{ tpl.description }}</div>
              <div class="tpl-footer">
                <div class="tpl-tags">
                  <ElTag v-for="tag in tpl.tags" :key="tag" size="small" type="info" effect="plain">
                    {{ tag }}
                  </ElTag>
                </div>
                <span class="tpl-usage">{{ tpl.usageCount }}次使用</span>
              </div>
            </ElCard>
          </div>
        </ElTabPane>

        <ElTabPane label="最近使用" name="recent">
          <div class="template-grid">
            <ElCard
              v-for="tpl in getFilteredTemplates('recent')"
              :key="tpl.id"
              shadow="hover"
              class="template-card"
              @click="handleSelect(tpl)"
            >
              <div class="tpl-name">{{ tpl.name }}</div>
              <div class="tpl-desc">{{ tpl.description }}</div>
              <div class="tpl-footer">
                <div class="tpl-tags">
                  <ElTag v-for="tag in tpl.tags" :key="tag" size="small" type="info" effect="plain">
                    {{ tag }}
                  </ElTag>
                </div>
                <span class="tpl-usage">{{ tpl.usageCount }}次使用</span>
              </div>
            </ElCard>
          </div>
        </ElTabPane>

        <ElTabPane label="推荐模板" name="recommend">
          <div class="template-grid">
            <ElCard
              v-for="tpl in getFilteredTemplates('recommend')"
              :key="tpl.id"
              shadow="hover"
              class="template-card"
              @click="handleSelect(tpl)"
            >
              <div class="tpl-name">{{ tpl.name }}</div>
              <div class="tpl-desc">{{ tpl.description }}</div>
              <div class="tpl-footer">
                <div class="tpl-tags">
                  <ElTag v-for="tag in tpl.tags" :key="tag" size="small" type="info" effect="plain">
                    {{ tag }}
                  </ElTag>
                </div>
                <span class="tpl-usage">{{ tpl.usageCount }}次使用</span>
              </div>
            </ElCard>
          </div>
        </ElTabPane>
      </ElTabs>
    </div>
  </transition>
</template>

<style scoped>
.template-panel {
  position: fixed;
  right: var(--spacing-2xl);
  bottom: var(--spacing-2xl);
  width: 380px;
  height: 520px;
  background: rgba(var(--color-bg-base-rgb), 0.95);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(var(--color-white-rgb), 0.1);
  border-radius: var(--radius-2xl);
  z-index: 10002;
  box-shadow: 0 var(--spacing-sm) 40px rgba(0, 0, 0, 0.4);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px var(--spacing-lg);
  border-bottom: 1px solid rgba(var(--color-white-rgb), 0.08);
}

.header-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
}

.close-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--color-text-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(var(--color-white-rgb), 0.1);
  color: var(--color-text-secondary);
}

.close-btn svg {
  width: var(--font-size-lg);
  height: var(--font-size-lg);
}

.template-tabs {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.template-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow-y: auto;
  padding: 0 var(--spacing-md) var(--spacing-md);
}

.template-grid {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  padding-top: var(--spacing-sm);
}

.template-card {
  cursor: pointer;
  transition: all 0.2s;
  border-radius: var(--radius-md);
  background: rgba(var(--color-white-rgb), 0.04);
  border: 1px solid rgba(var(--color-white-rgb), 0.06);
}

.template-card :deep(.el-card__body) {
  padding: var(--spacing-md);
}

.template-card:hover {
  border-color: rgba(var(--color-primary-rgb), 0.3);
  background: rgba(var(--color-primary-rgb), 0.06);
}

.tpl-name {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-2xs);
}

.tpl-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-sm);
}

.tpl-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tpl-tags {
  display: flex;
  gap: var(--spacing-2xs);
}

.tpl-usage {
  font-size: var(--font-size-2xs);
  color: var(--color-text-quaternary);
}

.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
