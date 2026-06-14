<template>
  <div v-if="wizard" class="wizard-runner">
    <div class="wizard-header">
      <span class="wizard-icon">🧙</span>
      <span class="wizard-title">{{ wizard.name }}</span>
      <button type="button" class="wizard-close" @click="closeWizard" aria-label="关闭向导">✕</button>
    </div>
    <div class="wizard-progress">
      <div
        v-for="(step, idx) in wizard.steps"
        :key="step.step_id"
        class="wizard-step-indicator"
        :class="{
          completed: idx < currentStepIndex,
          active: idx === currentStepIndex,
          pending: idx > currentStepIndex,
        }"
      >
        <span class="step-dot">{{ idx < currentStepIndex ? '✓' : idx + 1 }}</span>
        <span v-if="idx < wizard.steps.length - 1" class="step-connector" :class="{ filled: idx < currentStepIndex }" />
      </div>
    </div>
    <div v-if="currentStep" class="wizard-step-content">
      <h4 class="step-title">{{ currentStep.description }}</h4>
      <div v-if="currentStep.status === 'running'" class="step-running">
        <span class="running-spinner" />
        <span>执行中…</span>
      </div>
      <div v-if="currentStep.status === 'waiting_confirm'" class="step-confirm">
        <p class="confirm-text">此步骤需要您的确认</p>
        <div class="confirm-actions">
          <button type="button" class="confirm-btn approve" @click="approveStep" aria-label="确认执行">确认执行</button>
          <button type="button" class="confirm-btn cancel" @click="cancelStep" aria-label="跳过">跳过</button>
        </div>
      </div>
    </div>
    <div class="wizard-footer">
      <button type="button" class="wizard-nav-btn" :disabled="currentStepIndex === 0" @click="prevStep" aria-label="上一步">上一步</button>
      <span class="wizard-step-counter">{{ currentStepIndex + 1 }} / {{ wizard.steps.length }}</span>
      <button type="button" class="wizard-nav-btn primary" :disabled="currentStepIndex >= wizard.steps.length - 1" @click="nextStep" aria-label="下一步">下一步</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface WizardStep {
  step_id: string
  description: string
  tool: string
  params: Record<string, any>
  risk_level: 'low' | 'medium' | 'high'
  status: 'pending' | 'running' | 'completed' | 'failed' | 'waiting_confirm'
  result?: string
}

interface Wizard {
  name: string
  steps: WizardStep[]
}

const wizard = ref<Wizard | null>(null)
const currentStepIndex = ref(0)

const currentStep = computed(() => {
  if (!wizard.value) return null
  return wizard.value.steps[currentStepIndex.value] || null
})

const startWizard = (wizardData: Wizard) => {
  wizard.value = wizardData
  currentStepIndex.value = 0
}

const closeWizard = () => {
  wizard.value = null
  currentStepIndex.value = 0
}

const nextStep = () => {
  if (!wizard.value) return
  if (currentStepIndex.value < wizard.value.steps.length - 1) {
    currentStepIndex.value++
  }
}

const prevStep = () => {
  if (currentStepIndex.value > 0) {
    currentStepIndex.value--
  }
}

const approveStep = () => {
  if (!currentStep.value) return
  currentStep.value.status = 'running'
  window.dispatchEvent(new CustomEvent('assistant:wizard_approve', {
    detail: { step_id: currentStep.value.step_id }
  }))
}

const cancelStep = () => {
  if (!currentStep.value) return
  currentStep.value.status = 'pending'
  if (currentStepIndex.value < (wizard.value?.steps.length || 0) - 1) {
    currentStepIndex.value++
  }
}

defineExpose({ startWizard, closeWizard })
</script>

<style scoped>
.wizard-runner {
  background: var(--color-bg-input);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  margin: var(--spacing-sm) var(--spacing-md);
  overflow: hidden;
  box-shadow: var(--shadow-glow-primary);
}

.wizard-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-primary-bg);
  border-bottom: 1px solid var(--color-primary-border);
}

.wizard-icon {
  font-size: var(--font-size-lg);
}

.wizard-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-primary-light);
  flex: 1;
}

.wizard-close {
  background: none;
  border: none;
  color: var(--color-text-disabled);
  cursor: pointer;
  font-size: var(--font-size-sm);
  padding: 2px;
  min-width: 28px;
  min-height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  transition: all 0.2s var(--ease-out);
}

.wizard-close:hover {
  color: var(--color-text-secondary);
  background: var(--color-bg-active);
}

.wizard-progress {
  display: flex;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  gap: 0;
}

.wizard-step-indicator {
  display: flex;
  align-items: center;
  gap: 0;
}

.step-dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.6875rem;
  font-weight: var(--font-weight-semibold);
  border: 2px solid var(--color-border-primary);
  color: var(--color-text-disabled);
  background: var(--color-bg-input);
  flex-shrink: 0;
  transition: all 0.25s var(--ease-out);
}

.wizard-step-indicator.completed .step-dot {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
  color: var(--color-success);
  box-shadow: var(--shadow-glow-success);
}

.wizard-step-indicator.active .step-dot {
  background: var(--color-primary-bg);
  border-color: var(--color-primary-border);
  color: var(--color-primary-light);
  box-shadow: var(--shadow-glow-primary);
  animation: step-pulse 2s ease-in-out infinite;
}

@keyframes step-pulse {
  0%, 100% { box-shadow: var(--shadow-glow-primary); }
  50% { box-shadow: 0 0 12px var(--color-primary-glow); }
}

.step-connector {
  width: 32px;
  height: 2px;
  background: var(--color-border-primary);
  flex-shrink: 0;
  transition: background 0.3s var(--ease-out);
}

.step-connector.filled {
  background: var(--color-success-border);
}

.wizard-step-content {
  padding: var(--spacing-md);
}

.step-title {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0 0 var(--spacing-sm) 0;
}

.step-running {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: var(--color-primary-light);
  font-size: var(--font-size-sm);
}

.running-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--color-primary-border);
  border-top-color: var(--color-primary-light);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.step-confirm {
  padding: var(--spacing-sm);
  background: var(--color-warning-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-warning-border);
}

.confirm-text {
  font-size: var(--font-size-xs);
  color: var(--color-warning);
  margin: 0 0 var(--spacing-sm) 0;
  font-weight: var(--font-weight-medium);
}

.confirm-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.confirm-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  border: none;
  cursor: pointer;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  transition: var(--button-transition);
}

.confirm-btn.approve {
  background: var(--gradient-primary);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-glow-primary);
}

.confirm-btn.approve:hover {
  background: var(--gradient-primary-hover);
  transform: translateY(-1px);
}

.confirm-btn.cancel {
  background: var(--color-bg-hover);
  color: var(--color-text-tertiary);
}

.confirm-btn.cancel:hover {
  background: var(--color-bg-active);
  color: var(--color-text-secondary);
}

.wizard-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  border-top: 1px solid var(--color-border-primary);
}

.wizard-nav-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-primary);
  background: var(--color-bg-hover);
  color: var(--color-text-tertiary);
  cursor: pointer;
  font-size: var(--font-size-xs);
  transition: var(--button-transition);
}

.wizard-nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.wizard-nav-btn:not(:disabled):hover {
  background: var(--color-bg-active);
  color: var(--color-text-secondary);
  border-color: var(--color-border-hover);
}

.wizard-nav-btn.primary {
  background: var(--color-primary-bg);
  border-color: var(--color-primary-border);
  color: var(--color-primary-light);
}

.wizard-nav-btn.primary:not(:disabled):hover {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-border);
}

.wizard-step-counter {
  font-size: var(--font-size-xs);
  color: var(--color-text-disabled);
}
</style>
