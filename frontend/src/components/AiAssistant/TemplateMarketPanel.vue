<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, apiClient } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'

interface TemplateParameter {
  name: string
  type: 'string' | 'number' | 'boolean' | 'select'
  description: string
  default_value?: any
  required: boolean
  options?: string[]
}

interface IntentTemplate {
  id: string | number
  name: string
  description: string
  category: string
  intent_type: string
  template_content: string
  parameters_schema: TemplateParameter[]
  priority: number
  is_public: boolean
  tags: string[]
  author: string
  usage_count: number
  rating: number
  rating_count: number
  created_at: string
  updated_at: string
}

const emit = defineEmits<{
  (e: 'apply', template: string): void
  (e: 'close'): void
}>()

const CATEGORIES = [
  { key: 'all', label: '全部' },
  { key: '网络保障', label: '带宽保障', intentTypes: ['bandwidth_guarantee', 'qos_policy'] },
  { key: '安全管理', label: '访问控制', intentTypes: ['access_control'] },
  { key: '故障处理', label: '故障诊断', intentTypes: ['fault_diagnosis'] },
  { key: '监控管理', label: '性能监控', intentTypes: ['performance_monitor'] },
  { key: '流量管理', label: '流量整形', intentTypes: ['traffic_shaping'] },
  { key: '网络管理', label: '链路管理', intentTypes: ['link_management'] },
  { key: '配置管理', label: '设备配置', intentTypes: ['device_config'] }
]

const CATEGORY_COLOR_MAP: Record<string, string> = {
  '网络保障': '#165DFF',
  '安全管理': '#F77234',
  '故障处理': '#FF4D4F',
  '监控管理': '#52C41A',
  '流量管理': '#FAAD14',
  '网络管理': '#0FC6C2',
  '配置管理': '#722ED1',
  // intent_type fallbacks
  bandwidth_guarantee: '#165DFF',
  access_control: '#F77234',
  fault_diagnosis: '#FF4D4F',
  performance_monitor: '#52C41A',
  traffic_shaping: '#FAAD14',
  link_management: '#0FC6C2',
  qos_policy: '#722ED1'
}

const templates = ref<IntentTemplate[]>([])
const popularTemplates = ref<IntentTemplate[]>([])
const isLoading = ref(true)
const activeCategory = ref('all')
const showCreateDialog = ref(false)
const showInstantiateDialog = ref(false)
const showDetailDrawer = ref(false)
const isEditing = ref(false)
const editingTemplateId = ref<string | number>('')
const selectedTemplate = ref<IntentTemplate | null>(null)
const instantiateParams = ref<Record<string, any>>({})
const ratingValue = ref(0)
const isSubmitting = ref(false)

const templateForm = ref({
  name: '',
  description: '',
  category: '网络保障',
  intent_type: 'bandwidth_guarantee',
  template_content: '',
  parameters_schema: [] as TemplateParameter[],
  priority: 5,
  is_public: true,
  tags: [] as string[]
})

const tagInput = ref('')

const filteredTemplates = computed(() => {
  let result = templates.value
  if (activeCategory.value !== 'all') {
    const cat = CATEGORIES.find(c => c.key === activeCategory.value)
    result = result.filter(t => {
      if (t.category === activeCategory.value) return true
      if (cat?.intentTypes?.includes(t.intent_type)) return true
      return false
    })
  }
  return result
})

const getCategoryLabel = (key: string) => {
  const cat = CATEGORIES.find(c => c.key === key)
  if (cat) return cat.label
  // Fallback: look up by intent_type when API returns English intent_type as category
  const catByType = CATEGORIES.find(c => c.intentTypes?.includes(key))
  if (catByType) return catByType.label
  return key
}

const getCategoryColor = (key: string) => {
  if (CATEGORY_COLOR_MAP[key]) return CATEGORY_COLOR_MAP[key]
  // Fallback: look up category by intent_type and use its key for color
  const cat = CATEGORIES.find(c => c.intentTypes?.includes(key))
  if (cat && CATEGORY_COLOR_MAP[cat.key]) return CATEGORY_COLOR_MAP[cat.key]
  return '#94A3B8'
}

const convertSchemaToArray = (schema: any, exampleValues?: Record<string, any>): TemplateParameter[] => {
  if (Array.isArray(schema)) return schema
  if (!schema || typeof schema !== 'object' || schema.type !== 'object' || !schema.properties) return []
  const required = schema.required || []
  return Object.entries(schema.properties).map(([name, prop]: [string, any]) => {
    const hasEnum = prop.enum && (Array.isArray(prop.enum) ? prop.enum.length > 0 : true)
    return {
      name,
      type: hasEnum ? 'select' : (prop.type || 'string'),
      description: prop.description || '',
      required: required.includes(name),
      options: hasEnum ? (Array.isArray(prop.enum) ? prop.enum : [prop.enum]) : undefined,
      default_value: prop.default ?? exampleValues?.[name]
    }
  })
}

const normalizeTemplate = (t: any): IntentTemplate => ({
  ...t,
  id: t.id || t.template_id,
  parameters_schema: convertSchemaToArray(t.parameters_schema, t.example_values)
})

const fetchTemplates = async () => {
  isLoading.value = true
  try {
    const result = await apiClient.get(api.intentTemplates.list)
    const raw = result.data?.items || result.data || []
    templates.value = (Array.isArray(raw) ? raw : []).map(normalizeTemplate)
  } catch {
    loadMockData()
  } finally {
    isLoading.value = false
  }
}

const fetchPopularTemplates = async () => {
  try {
    const result = await apiClient.get(api.intentTemplates.popular)
    const raw = result.data?.items || result.data || []
    popularTemplates.value = (Array.isArray(raw) ? raw : []).map(normalizeTemplate)
  } catch {
    popularTemplates.value = []
  }
}

const loadMockData = () => {
  templates.value = [
    {
      id: '1', name: '视频会议带宽保障', description: '为视频会议流量保障最低带宽，确保会议质量稳定',
      category: '网络保障', intent_type: 'bandwidth_guarantee',
      template_content: '保障{subnet}视频会议流量最小{bandwidth}M带宽',
      parameters_schema: [
        { name: 'subnet', type: 'string', description: '目标子网', required: true },
        { name: 'bandwidth', type: 'number', description: '保障带宽(Mbps)', default_value: 200, required: true }
      ],
      priority: 8, is_public: true, tags: ['视频会议', '带宽', 'QoS'], author: 'admin',
      usage_count: 156, rating: 4.5, rating_count: 23, created_at: '2025-05-01T10:00:00Z', updated_at: '2025-05-20T14:30:00Z'
    },
    {
      id: '2', name: 'ACL白名单配置', description: '配置基于源和目标的访问控制白名单规则',
      category: '安全管理', intent_type: 'access_control',
      template_content: '开放{source_net}到{target_net}的{port}端口访问',
      parameters_schema: [
        { name: 'source_net', type: 'string', description: '源网络', required: true },
        { name: 'target_net', type: 'string', description: '目标网络', required: true },
        { name: 'port', type: 'string', description: '端口号', default_value: '22', required: true }
      ],
      priority: 7, is_public: true, tags: ['ACL', '访问控制', '白名单'], author: 'operator1',
      usage_count: 89, rating: 4.2, rating_count: 15, created_at: '2025-04-15T08:00:00Z', updated_at: '2025-05-18T09:00:00Z'
    },
    {
      id: '3', name: '链路故障诊断', description: '自动诊断指定设备的链路连通性和故障原因',
      category: '故障处理', intent_type: 'fault_diagnosis',
      template_content: '诊断{device}的{fault_type}问题',
      parameters_schema: [
        { name: 'device', type: 'string', description: '目标设备', required: true },
        { name: 'fault_type', type: 'select', description: '故障类型', required: true, options: ['连通性', '丢包', '延迟', '链路中断'] }
      ],
      priority: 9, is_public: true, tags: ['故障', '诊断', '链路'], author: 'admin',
      usage_count: 234, rating: 4.8, rating_count: 42, created_at: '2025-03-20T12:00:00Z', updated_at: '2025-05-25T16:00:00Z'
    },
    {
      id: '4', name: 'QoS优先级策略', description: '为指定子网配置QoS优先级策略，保障关键业务流量',
      category: '网络保障', intent_type: 'qos_policy',
      template_content: '为{subnet}配置{priority}级QoS策略',
      parameters_schema: [
        { name: 'subnet', type: 'string', description: '目标子网', required: true },
        { name: 'priority', type: 'select', description: '优先级', required: true, options: ['高', '中', '低'] }
      ],
      priority: 6, is_public: true, tags: ['QoS', '优先级', '流量'], author: 'operator2',
      usage_count: 67, rating: 4.0, rating_count: 10, created_at: '2025-04-01T09:00:00Z', updated_at: '2025-05-15T11:00:00Z'
    },
    {
      id: '5', name: '主备链路切换', description: '将指定源设备到目标设备的主链路切换到备用链路',
      category: '网络管理', intent_type: 'link_management',
      template_content: '将{source_device}到{target_device}的主链路切换到备用链路',
      parameters_schema: [
        { name: 'source_device', type: 'string', description: '源设备', required: true },
        { name: 'target_device', type: 'string', description: '目标设备', required: true }
      ],
      priority: 8, is_public: true, tags: ['链路', '切换', '冗余'], author: 'admin',
      usage_count: 112, rating: 4.6, rating_count: 28, created_at: '2025-03-10T14:00:00Z', updated_at: '2025-05-22T10:00:00Z'
    },
    {
      id: '6', name: '流量整形策略', description: '对指定接口的流量进行整形控制，限制峰值带宽',
      category: '流量管理', intent_type: 'traffic_shaping',
      template_content: '对{interface}的流量整形，限制峰值{peak_bandwidth}M，均值{avg_bandwidth}M',
      parameters_schema: [
        { name: 'interface', type: 'string', description: '目标接口', required: true },
        { name: 'peak_bandwidth', type: 'number', description: '峰值带宽(Mbps)', required: true },
        { name: 'avg_bandwidth', type: 'number', description: '均值带宽(Mbps)', required: true }
      ],
      priority: 5, is_public: false, tags: ['流量整形', '带宽限制'], author: 'operator1',
      usage_count: 34, rating: 3.8, rating_count: 6, created_at: '2025-05-05T16:00:00Z', updated_at: '2025-05-28T08:00:00Z'
    }
  ]
  popularTemplates.value = templates.value.slice(0, 3)
}

const openCreateDialog = () => {
  isEditing.value = false
  editingTemplateId.value = ''
  templateForm.value = {
    name: '', description: '', category: '网络保障', intent_type: 'bandwidth_guarantee',
    template_content: '', parameters_schema: [], priority: 5, is_public: true, tags: []
  }
  tagInput.value = ''
  showCreateDialog.value = true
}

const openEditDialog = (template: IntentTemplate) => {
  isEditing.value = true
  editingTemplateId.value = template.id
  templateForm.value = {
    name: template.name,
    description: template.description,
    category: template.category,
    intent_type: template.intent_type,
    template_content: template.template_content,
    parameters_schema: JSON.parse(JSON.stringify(template.parameters_schema)),
    priority: template.priority,
    is_public: template.is_public,
    tags: [...template.tags]
  }
  tagInput.value = ''
  showCreateDialog.value = true
}

const submitTemplate = async () => {
  if (!templateForm.value.name || !templateForm.value.template_content) {
    showToast('请填写模板名称和内容', 'error')
    return
  }
  isSubmitting.value = true
  try {
    if (isEditing.value) {
      await apiClient.put(api.intentTemplates.byId(String(editingTemplateId.value)), templateForm.value)
      showToast('模板更新成功', 'success')
    } else {
      await apiClient.post(api.intentTemplates.list, templateForm.value)
      showToast('模板创建成功', 'success')
    }
    showCreateDialog.value = false
    await fetchTemplates()
  } catch (err: any) {
    showToast('保存模板失败: ' + err.message, 'error')
  } finally {
    isSubmitting.value = false
  }
}

const deleteTemplate = async (id: string | number) => {
  try {
    await apiClient.delete(api.intentTemplates.byId(String(id)))
    showToast('模板已删除', 'success')
    await fetchTemplates()
  } catch (err: any) {
    showToast('删除失败: ' + err.message, 'error')
  }
}

const openInstantiateDialog = (template: IntentTemplate) => {
  selectedTemplate.value = template
  instantiateParams.value = {}
  template.parameters_schema.forEach(p => {
    instantiateParams.value[p.name] = p.default_value ?? (p.type === 'number' ? 0 : '')
  })
  showInstantiateDialog.value = true
}

const submitInstantiate = async () => {
  if (!selectedTemplate.value) return
  isSubmitting.value = true
  try {
    await apiClient.post(api.intentTemplates.instantiate(selectedTemplate.value.template_id || String(selectedTemplate.value.id)), {
      parameter_values: instantiateParams.value
    })
    showToast('意图实例化成功', 'success')
    showInstantiateDialog.value = false
    await fetchTemplates()
  } catch (err: any) {
    showToast('实例化失败: ' + err.message, 'error')
  } finally {
    isSubmitting.value = false
  }
}

const previewContent = computed(() => {
  if (!selectedTemplate.value) return ''
  let content = selectedTemplate.value.template_content
  for (const [key, val] of Object.entries(instantiateParams.value)) {
    content = content.replace(new RegExp(`\\{${key}\\}`, 'g'), String(val || `{${key}}`))
  }
  return content
})

const openDetailDrawer = (template: IntentTemplate) => {
  selectedTemplate.value = template
  ratingValue.value = 0
  showDetailDrawer.value = true
}

const rateTemplate = async () => {
  if (!selectedTemplate.value || !ratingValue.value) return
  try {
    await apiClient.post(api.intentTemplates.rate(selectedTemplate.value.template_id || String(selectedTemplate.value.id)), {
      rating: ratingValue.value
    })
    showToast('评分成功', 'success')
    ratingValue.value = 0
    await fetchTemplates()
  } catch {
    showToast('评分失败', 'error')
  }
}

const cloneTemplate = async (template: IntentTemplate) => {
  try {
    await apiClient.post(api.intentTemplates.clone(template.template_id || String(template.id)))
    showToast('模板克隆成功', 'success')
    await fetchTemplates()
  } catch (err: any) {
    showToast('克隆失败: ' + err.message, 'error')
  }
}

const addParameter = () => {
  templateForm.value.parameters_schema.push({
    name: '', type: 'string', description: '', required: true
  })
}

const removeParameter = (index: number) => {
  templateForm.value.parameters_schema.splice(index, 1)
}

const addTag = () => {
  const tag = tagInput.value.trim()
  if (tag && !templateForm.value.tags.includes(tag)) {
    templateForm.value.tags.push(tag)
    tagInput.value = ''
  }
}

const removeTag = (index: number) => {
  templateForm.value.tags.splice(index, 1)
}

const applyToInput = (template: IntentTemplate) => {
  emit('apply', {
    content: template.template_content,
    intent_type: template.intent_type,
    parameters_schema: template.parameters_schema,
    name: template.name
  })
}

onMounted(() => {
  fetchTemplates()
  fetchPopularTemplates()
})
</script>

<template>
  <div class="template-market-panel">
    <div class="panel-header">
      <span class="panel-title">📋 模板市场</span>
      <div class="panel-header-actions">
        <button type="button" class="tpl-action-btn create-btn" @click="openCreateDialog">➕</button>
        <button type="button" class="tpl-close-btn" @click="emit('close')" aria-label="关闭">✕</button>
      </div>
    </div>

    <div class="panel-categories">
      <button
        v-for="cat in CATEGORIES"
        :key="cat.key"
        type="button"
        class="tpl-category-tag"
        :class="{ active: activeCategory === cat.key }"
        @click="activeCategory = cat.key"
      >
        {{ cat.label }}
      </button>
    </div>

    <div v-if="isLoading" class="loading-state">
      <div v-for="i in 2" :key="i" class="skeleton-row">
        <div class="skeleton-line wide"></div>
        <div class="skeleton-line short"></div>
      </div>
    </div>

    <div v-else class="tpl-list">
      <!-- 热门模板（仅全部+无搜索时显示前3） -->
      <template v-if="activeCategory === 'all'">
        <div class="section-label">🔥 热门</div>
        <div
          v-for="tpl in popularTemplates.slice(0, 3)"
          :key="'pop-' + tpl.id"
          class="tpl-row hot"
          @click="applyToInput(tpl)"
        >
          <div class="tpl-row-left">
            <span class="tpl-row-name">{{ tpl.name }}</span>
            <span class="tpl-row-badge" :style="{ color: getCategoryColor(tpl.category) }">{{ getCategoryLabel(tpl.category) }}</span>
          </div>
          <div class="tpl-row-right">
            <span class="tpl-row-stats">⭐{{ tpl.rating }}</span>
            <button type="button" class="tpl-btn-sm" @click.stop="openDetailDrawer(tpl)" title="详情">📋</button>
          </div>
        </div>
        <div class="section-divider"></div>
      </template>

      <!-- 模板列表（紧凑行） -->
      <div
        v-for="tpl in filteredTemplates"
        :key="tpl.id"
        class="tpl-row"
        @click="applyToInput(tpl)"
      >
        <div class="tpl-row-left">
          <span class="tpl-row-name">{{ tpl.name }}</span>
          <span class="tpl-row-badge" :style="{ color: getCategoryColor(tpl.category) }">{{ getCategoryLabel(tpl.category) }}</span>
        </div>
        <div class="tpl-row-right">
          <span class="tpl-row-stats">📊{{ tpl.usage_count }}</span>
          <button type="button" class="tpl-btn-sm" @click.stop="applyToInput(tpl)" title="填入">📝</button>
          <button type="button" class="tpl-btn-sm" @click.stop="openDetailDrawer(tpl)" title="详情">📋</button>
        </div>
      </div>
      <div v-if="filteredTemplates.length === 0" class="empty-state">📭 暂无匹配</div>
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      :title="isEditing ? '编辑模板' : '创建模板'"
      width="680px"
      class="dark-dialog"
      destroy-on-close
      append-to-body
    >
      <el-form label-position="top" class="dark-form">
        <el-form-item label="模板名称" required>
          <el-input v-model="templateForm.name" placeholder="输入模板名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="templateForm.description" type="textarea" :rows="2" placeholder="模板用途说明" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="分类" class="form-col">
            <el-select v-model="templateForm.category" placeholder="选择分类">
              <el-option
                v-for="cat in CATEGORIES.filter(c => c.key !== 'all')"
                :key="cat.key"
                :label="cat.label"
                :value="cat.key"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="意图类型" class="form-col">
            <el-select v-model="templateForm.intent_type" placeholder="选择意图类型">
              <el-option
                v-for="cat in CATEGORIES.filter(c => c.key !== 'all' && c.intentTypes)"
                :key="cat.key"
                :label="cat.label"
                :value="cat.intentTypes![0]"
              />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="模板内容" required>
          <el-input
            v-model="templateForm.template_content"
            type="textarea"
            :rows="3"
            placeholder="使用 {参数名} 语法标记可替换参数，如：保障{subnet}视频会议流量最小{bandwidth}M带宽"
          />
        </el-form-item>
        <el-form-item label="参数定义">
          <div class="params-editor">
            <div v-for="(param, idx) in templateForm.parameters_schema" :key="idx" class="param-row">
              <el-input v-model="param.name" placeholder="参数名" class="param-name" />
              <el-select v-model="param.type" placeholder="类型" class="param-type">
                <el-option label="字符串" value="string" />
                <el-option label="数字" value="number" />
                <el-option label="布尔" value="boolean" />
                <el-option label="选择" value="select" />
              </el-select>
              <el-input v-model="param.description" placeholder="描述" class="param-desc" />
              <el-checkbox v-model="param.required">必填</el-checkbox>
              <button type="button" class="remove-param-btn" @click="removeParameter(idx)">✕</button>
            </div>
            <button type="button" class="add-param-btn" @click="addParameter">+ 添加参数</button>
          </div>
        </el-form-item>
        <div class="form-row">
          <el-form-item label="优先级" class="form-col">
            <el-slider v-model="templateForm.priority" :min="1" :max="10" show-stops />
          </el-form-item>
          <el-form-item label="公开" class="form-col">
            <el-switch v-model="templateForm.is_public" />
          </el-form-item>
        </div>
        <el-form-item label="标签">
          <div class="tags-editor">
            <span v-for="(tag, idx) in templateForm.tags" :key="idx" class="tpl-tag removable">
              {{ tag }}
              <span class="tag-remove" @click="removeTag(idx)">✕</span>
            </span>
            <input
              v-model="tagInput"
              class="tag-input"
              placeholder="输入标签后回车"
              @keydown.enter.prevent="addTag"
            />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="isSubmitting" @click="submitTemplate">
          {{ isEditing ? '更新' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 实例化对话框 -->
    <el-dialog
      v-model="showInstantiateDialog"
      title="实例化模板"
      width="560px"
      class="dark-dialog"
      destroy-on-close
      append-to-body
    >
      <div v-if="selectedTemplate" class="instantiate-content">
        <div class="instantiate-template-name">{{ selectedTemplate.name }}</div>
        <div class="instantiate-template-desc">{{ selectedTemplate.description }}</div>
        <el-form label-position="top" class="dark-form">
          <el-form-item
            v-for="param in selectedTemplate.parameters_schema"
            :key="param.name"
            :label="param.description || param.name"
            :required="param.required"
          >
            <el-select
              v-if="param.type === 'select' && param.options"
              v-model="instantiateParams[param.name]"
              placeholder="请选择"
            >
              <el-option v-for="opt in param.options" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-switch
              v-else-if="param.type === 'boolean'"
              v-model="instantiateParams[param.name]"
            />
            <el-input-number
              v-else-if="param.type === 'number'"
              v-model="instantiateParams[param.name]"
              :placeholder="param.description"
            />
            <el-input
              v-else
              v-model="instantiateParams[param.name]"
              :placeholder="param.description"
            />
          </el-form-item>
        </el-form>
        <div class="preview-section">
          <div class="preview-label">预览结果</div>
          <div class="preview-content"><code>{{ previewContent }}</code></div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showInstantiateDialog = false">取消</el-button>
        <el-button type="primary" :loading="isSubmitting" @click="submitInstantiate">🚀 实例化</el-button>
      </template>
    </el-dialog>

    <!-- 详情抽屉 -->
    <el-drawer
      v-model="showDetailDrawer"
      title="模板详情"
      direction="rtl"
      size="420px"
      class="dark-drawer"
      append-to-body
    >
      <div v-if="selectedTemplate" class="detail-content">
        <div class="detail-header">
          <h2 class="detail-name">{{ selectedTemplate.name }}</h2>
          <span class="tpl-category-badge" :style="{ background: getCategoryColor(selectedTemplate.category) + '20', color: getCategoryColor(selectedTemplate.category), borderColor: getCategoryColor(selectedTemplate.category) + '40' }">
            {{ getCategoryLabel(selectedTemplate.category) }}
          </span>
        </div>
        <div class="detail-desc">{{ selectedTemplate.description }}</div>
        <div class="detail-section">
          <div class="detail-section-title">模板内容</div>
          <div class="detail-code"><code>{{ selectedTemplate.template_content }}</code></div>
        </div>
        <div class="detail-section">
          <div class="detail-section-title">参数定义</div>
          <div v-for="param in selectedTemplate.parameters_schema" :key="param.name" class="param-detail-item">
            <span class="param-detail-name">{{ param.name }}</span>
            <span class="param-detail-type">{{ param.type }}</span>
            <span class="param-detail-desc">{{ param.description }}</span>
            <span v-if="param.required" class="param-detail-required">必填</span>
          </div>
        </div>
        <div class="detail-section">
          <div class="detail-section-title">标签</div>
          <div class="detail-tags">
            <span v-for="tag in selectedTemplate.tags" :key="tag" class="tpl-tag">{{ tag }}</span>
          </div>
        </div>
        <div class="detail-meta-grid">
          <div class="meta-card">
            <div class="meta-card-value">{{ selectedTemplate.author }}</div>
            <div class="meta-card-label">作者</div>
          </div>
          <div class="meta-card">
            <div class="meta-card-value">{{ selectedTemplate.usage_count }}</div>
            <div class="meta-card-label">使用次数</div>
          </div>
          <div class="meta-card">
            <div class="meta-card-value">⭐ {{ selectedTemplate.rating }}</div>
            <div class="meta-card-label">评分 ({{ selectedTemplate.rating_count }}人)</div>
          </div>
          <div class="meta-card">
            <div class="meta-card-value">{{ selectedTemplate.priority }}</div>
            <div class="meta-card-label">优先级</div>
          </div>
        </div>
        <div class="detail-section">
          <div class="detail-section-title">评分</div>
          <div class="rating-row">
            <el-rate v-model="ratingValue" :max="5" />
            <el-button size="small" type="primary" :disabled="!ratingValue" @click="rateTemplate">提交评分</el-button>
          </div>
        </div>
        <div class="detail-actions">
          <el-button type="primary" @click="cloneTemplate(selectedTemplate)">📋 克隆模板</el-button>
          <el-button @click="openInstantiateDialog(selectedTemplate); showDetailDrawer = false">🚀 实例化</el-button>
          <el-button @click="applyToInput(selectedTemplate); showDetailDrawer = false">📝 填入输入框</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.template-market-panel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 50vh;
  overflow-y: auto;
  padding: 0.625rem;
  border: var(--card-border);
  border-radius: var(--radius-md);
  background: var(--gradient-glass);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  animation: panelSlideIn 0.25s var(--ease-out);
}

.template-market-panel::-webkit-scrollbar {
  width: 3px;
}

.template-market-panel::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.2);
  border-radius: var(--radius-xs);
}

@keyframes panelSlideIn {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
}

.panel-header-actions {
  display: flex;
  gap: 0.25rem;
  align-items: center;
}

.tpl-action-btn {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(22, 93, 255, 0.25);
  background: rgba(22, 93, 255, 0.1);
  color: var(--color-primary-light);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
  box-shadow: 0 0 4px rgba(22, 93, 255, 0.06);
}

.tpl-action-btn:hover {
  background: rgba(22, 93, 255, 0.2);
  border-color: rgba(22, 93, 255, 0.5);
  box-shadow: 0 0 10px rgba(22, 93, 255, 0.15), 0 1px 4px rgba(22, 93, 255, 0.08);
  transform: scale(1.02);
}

.tpl-action-btn:active {
  transform: scale(0.97);
}

.tpl-close-btn {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-primary);
  background: transparent;
  color: var(--color-text-tertiary);
  cursor: pointer;
  font-size: var(--font-size-xs);
  transition: all 0.25s ease;
}

.tpl-close-btn:hover {
  background: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.3);
  color: var(--color-error-light);
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.1);
  transform: scale(1.05);
}

.tpl-close-btn:active {
  transform: scale(0.97);
}

.panel-search {
  width: 100%;
}

.tpl-search-input {
  width: 100%;
  padding: 5px 10px;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  outline: none;
  transition: border-color 0.2s var(--ease-out);
  box-sizing: border-box;
}

.tpl-search-input::placeholder {
  color: var(--color-text-disabled);
}

.tpl-search-input:focus {
  border-color: var(--input-border-focus);
}

.panel-categories {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.tpl-category-tag {
  padding: 2px 8px;
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: var(--button-transition);
  white-space: nowrap;
}

.tpl-category-tag:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border-color: var(--color-primary-border);
}

.tpl-category-tag.active {
  background: var(--color-primary-hover);
  color: var(--color-primary-light);
  border-color: rgba(22, 93, 255, 0.35);
}

.section-label {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-warning);
  margin-bottom: 0.25rem;
}

.section-divider {
  height: 1px;
  background: var(--color-border-primary);
  margin: 0.25rem 0;
}

.loading-state {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.skeleton-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem;
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-line {
  height: 0.625rem;
  background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 75%);
  background-size: 200% 100%;
  border-radius: var(--radius-xs);
  animation: skeleton-slide 1.5s ease-in-out infinite;
}

@keyframes skeleton-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.skeleton-line.wide { width: 60%; }
.skeleton-line.short { width: 25%; }

.tpl-list {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

/* Compact row style */
.tpl-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s var(--ease-out);
}

.tpl-row:hover {
  background: var(--color-bg-hover);
}

.tpl-row.hot {
  background: linear-gradient(135deg, rgba(250, 173, 20, 0.06), transparent);
  border-left: 2px solid var(--color-warning);
  padding-left: 10px;
}

.tpl-row-left {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
  flex: 1;
}

.tpl-row-name {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tpl-row-badge {
  font-size: var(--font-size-xs);
  padding: 0 4px;
  white-space: nowrap;
  opacity: 0.7;
}

.tpl-row-right {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex-shrink: 0;
}

.tpl-row-stats {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.tpl-btn-sm {
  width: 1.25rem;
  height: 1.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: var(--radius-xs);
  cursor: pointer;
  font-size: var(--font-size-xs);
  transition: all 0.25s ease;
  padding: 0;
  opacity: 0.5;
}

.tpl-btn-sm:hover {
  background: rgba(22, 93, 255, 0.12);
  opacity: 1;
  box-shadow: 0 0 8px rgba(22, 93, 255, 0.12);
  transform: scale(1.05);
}

.empty-state {
  text-align: center;
  padding: 1rem;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

/* Form styles */
.form-row {
  display: flex;
  gap: var(--spacing-md);
}

.form-col {
  flex: 1;
}

.params-editor {
  width: 100%;
}

.param-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.5rem;
}

.param-name { width: 120px; }
.param-type { width: 110px; }
.param-desc { flex: 1; }

.remove-param-btn {
  width: 1.5rem;
  height: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-sm);
  color: var(--color-error-light);
  cursor: pointer;
  font-size: var(--font-size-xs);
  flex-shrink: 0;
}

.remove-param-btn:hover {
  background: var(--color-error-hover);
}

.add-param-btn {
  padding: var(--spacing-xs) 0.75rem;
  background: rgba(22, 93, 255, 0.1);
  border: 1px dashed rgba(22, 93, 255, 0.3);
  border-radius: var(--radius-sm);
  color: var(--color-primary-light);
  cursor: pointer;
  font-size: var(--font-size-xs);
  backdrop-filter: blur(8px);
  transition: all 0.25s ease;
}

.add-param-btn:hover {
  background: rgba(22, 93, 255, 0.2);
  border-color: rgba(22, 93, 255, 0.5);
  box-shadow: 0 0 8px rgba(22, 93, 255, 0.1);
}

.tags-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  align-items: center;
  padding: 0.375rem;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--radius-sm);
  min-height: 2.5rem;
}

.tag-input {
  background: transparent;
  border: none;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  outline: none;
  min-width: 80px;
  flex: 1;
}

.tag-input::placeholder {
  color: var(--color-text-disabled);
}

.tpl-tag {
  font-size: var(--font-size-xs);
  padding: 1px 6px;
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  border-radius: var(--radius-xs);
  white-space: nowrap;
}

.tpl-tag.removable {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.tag-remove {
  cursor: pointer;
  opacity: 0.6;
  font-size: var(--font-size-xs);
}

.tag-remove:hover {
  opacity: 1;
}

/* Instantiate */
.instantiate-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.instantiate-template-name {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
}

.instantiate-template-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.preview-section {
  margin-top: var(--spacing-sm);
}

.preview-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-bottom: 0.375rem;
}

.preview-content {
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  padding: 0.75rem;
  border: 1px solid var(--color-border-primary);
}

.preview-content code {
  font-size: var(--font-size-sm);
  color: var(--color-success);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

/* Detail */
.detail-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.detail-name {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-secondary);
  margin: 0;
}

.detail-desc {
  font-size: var(--font-size-base);
  color: var(--color-text-tertiary);
  line-height: var(--line-height-relaxed);
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.detail-section-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  padding-bottom: 0.375rem;
  border-bottom: 1px solid var(--color-border-primary);
}

.detail-code {
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  padding: 0.75rem;
  border: 1px solid var(--color-border-primary);
}

.detail-code code {
  font-size: var(--font-size-sm);
  color: var(--color-primary-light);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.param-detail-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0;
  font-size: var(--font-size-sm);
}

.param-detail-name {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  min-width: 5rem;
}

.param-detail-type {
  color: var(--color-primary-light);
  background: var(--color-primary-bg);
  padding: 1px 0.375rem;
  border-radius: var(--radius-xs);
  font-size: var(--font-size-xs);
}

.param-detail-desc {
  color: var(--color-text-tertiary);
  flex: 1;
}

.param-detail-required {
  color: var(--color-error);
  font-size: var(--font-size-xs);
  background: var(--color-error-bg);
  padding: 1px 0.375rem;
  border-radius: var(--radius-xs);
}

.detail-tags {
  display: flex;
  gap: 0.375rem;
  flex-wrap: wrap;
}

.detail-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-sm);
}

.meta-card {
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  padding: 0.75rem;
  text-align: center;
  border: 1px solid var(--color-border-primary);
}

.meta-card-value {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-secondary);
}

.meta-card-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: 0.125rem;
}

.rating-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.detail-actions {
  display: flex;
  gap: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-primary);
}

/* Element Plus dark overrides */
.dark-dialog :deep(.el-dialog) {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-primary);
}

.dark-dialog :deep(.el-dialog__header) {
  border-bottom: 1px solid var(--color-border-primary);
}

.dark-dialog :deep(.el-dialog__title) {
  color: var(--color-text-secondary);
}

.dark-form :deep(.el-form-item__label) {
  color: var(--color-text-tertiary);
}

.dark-form :deep(.el-input__wrapper),
.dark-form :deep(.el-textarea__inner) {
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  box-shadow: none;
}

.dark-form :deep(.el-input__inner),
.dark-form :deep(.el-textarea__inner) {
  color: var(--color-text-secondary);
}

.dark-drawer :deep(.el-drawer) {
  background: var(--color-bg-elevated);
}

.dark-drawer :deep(.el-drawer__header) {
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border-primary);
}

@media (max-width: 768px) {
  .template-market-panel {
    max-height: 40vh;
  }
  .panel-categories {
    overflow-x: auto;
    flex-wrap: nowrap;
    padding-bottom: 0.25rem;
  }
}
</style>
