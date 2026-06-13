<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElSteps, ElStep, ElButton } from 'element-plus'

interface WizardStep {
  title: string
  description: string
  type: 'form' | 'confirm' | 'result'
  data?: Record<string, unknown>
}

const props = defineProps<{
  visible: boolean
  steps: WizardStep[]
}>()

const emit = defineEmits<{
  close: []
  complete: [result: Record<string, unknown>]
  stepChange: [stepIndex: number]
}>()

const currentStep = ref(0)

const isFirstStep = computed(() => currentStep.value === 0)
const isLastStep = computed(() => currentStep.value === props.steps.length - 1)

function nextStep() {
  if (isLastStep.value) {
    const result: Record<string, unknown> = {}
    props.steps.forEach((step, idx) => {
      result[`step${idx}`] = step.data || {}
    })
    emit('complete', result)
    return
  }
  currentStep.value++
  emit('stepChange', currentStep.value)
}

function prevStep() {
  if (currentStep.value > 0) {
    currentStep.value--
    emit('stepChange', currentStep.value)
  }
}

function skipStep() {
  if (!isLastStep.value) {
    currentStep.value++
    emit('stepChange', currentStep.value)
  }
}
</script>

<template>
  <transition name="slide">
    <div v-if="visible" class="wizard-panel">
      <div class="panel-header">
        <span class="header-title">执行向导</span>
        <button class="close-btn" @click="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <div class="wizard-body">
        <ElSteps :active="currentStep" align-center class="wizard-steps">
          <ElStep
            v-for="(step, idx) in steps"
            :key="idx"
            :title="step.title"
            :description="step.description"
          />
        </ElSteps>

        <div v-if="steps[currentStep]" class="step-content">
          <div class="step-type-badge">
            {{ steps[currentStep].type === 'form' ? '表单填写' : steps[currentStep].type === 'confirm' ? '确认执行' : '执行结果' }}
          </div>
          <div class="step-data">
            <template v-if="steps[currentStep].type === 'form'">
              <p class="step-hint">请填写当前步骤所需的信息</p>
            </template>
            <template v-else-if="steps[currentStep].type === 'confirm'">
              <p class="step-hint">请确认以下信息无误后执行</p>
            </template>
            <template v-else>
              <p class="step-hint">执行结果如下</p>
            </template>
          </div>
        </div>
      </div>

      <div class="wizard-footer">
        <ElButton v-if="!isFirstStep" @click="prevStep">上一步</ElButton>
        <ElButton v-if="!isLastStep" @click="skipStep">跳过</ElButton>
        <ElButton type="primary" @click="nextStep">
          {{ isLastStep ? '完成' : '下一步' }}
        </ElButton>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.wizard-panel {
  position: fixed;
  right: 24px;
  bottom: 24px;
  width: 420px;
  max-height: 520px;
  background: rgba(15, 23, 42, 0.95);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  z-index: 10003;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.4);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.header-title {
  font-size: 15px;
  font-weight: 600;
  color: #e2e8f0;
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

.wizard-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px;
}

.wizard-steps {
  margin-bottom: 24px;
}

.step-content {
  padding: var(--spacing-lg);
  background: rgba(var(--color-white-rgb), 0.04);
  border-radius: var(--radius-md);
  border: 1px solid rgba(var(--color-white-rgb), 0.06);
}

.step-type-badge {
  display: inline-block;
  padding: var(--spacing-2xs) 10px;
  border-radius: var(--radius-sm);
  background: rgba(var(--color-primary-rgb), 0.15);
  color: var(--color-info-light);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  margin-bottom: var(--spacing-md);
}

.step-hint {
  font-size: var(--font-size-base);
  color: var(--color-text-tertiary);
  line-height: 1.6;
}

.wizard-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
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
