<template>
  <div class="stat-card" :class="[`stat-card--${type}`]">
    <div class="stat-card__icon">
      <span>{{ icon }}</span>
    </div>
    <div class="stat-card__content">
      <div class="stat-card__value">{{ displayValue }}</div>
      <div class="stat-card__label">{{ label }}</div>
    </div>
    <div v-if="trend !== undefined" class="stat-card__trend" :class="trendClass">
      <span>{{ trend > 0 ? '↑' : '↓' }}</span>
      <span>{{ Math.abs(trend) }}%</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  icon: string
  label: string
  value: number | string
  trend?: number
  type?: 'default' | 'success' | 'warning' | 'danger'
  suffix?: string
}>(), {
  type: 'default',
  suffix: '',
})

const displayValue = computed(() => {
  if (typeof props.value === 'number') {
    return props.value.toLocaleString() + props.suffix
  }
  return props.value + props.suffix
})

const trendClass = computed(() => ({
  'stat-card__trend--up': props.trend && props.trend > 0,
  'stat-card__trend--down': props.trend && props.trend < 0,
}))
</script>

<style scoped lang="scss">
.stat-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--card-padding);
  background: var(--card-bg);
  border: var(--card-border);
  border-radius: var(--card-border-radius);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow-card);
  transition: all 0.25s ease;

  &:hover {
    border-color: rgba(22, 93, 255, 0.3);
    box-shadow: 0 4px 16px rgba(22, 93, 255, 0.12);
    transform: translateY(-2px);
  }

  &--default {
    &:hover {
      border-color: rgba(59, 130, 246, 0.4);
      box-shadow: 0 4px 16px rgba(59, 130, 246, 0.15);
    }
    .stat-card__icon {
      background: var(--color-primary-bg);
      color: var(--color-primary-light);
    }
  }

  &--success {
    &:hover {
      border-color: rgba(34, 197, 94, 0.4);
      box-shadow: 0 4px 16px rgba(34, 197, 94, 0.15);
    }
    .stat-card__icon {
      background: var(--color-success-bg);
      color: var(--color-success);
    }
  }

  &--warning {
    &:hover {
      border-color: rgba(245, 158, 11, 0.4);
      box-shadow: 0 4px 16px rgba(245, 158, 11, 0.15);
    }
    .stat-card__icon {
      background: var(--color-warning-bg);
      color: var(--color-warning);
    }
  }

  &--danger {
    &:hover {
      border-color: rgba(239, 68, 68, 0.4);
      box-shadow: 0 4px 16px rgba(239, 68, 68, 0.15);
    }
    .stat-card__icon {
      background: var(--color-error-bg);
      color: var(--color-error);
    }
  }
}

.stat-card__icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xl);
  flex-shrink: 0;
  transition: all 0.25s ease;

  .stat-card:hover & {
    animation: iconPulse 1.5s ease-in-out infinite;
  }
}

@keyframes iconPulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.1); }
}

.stat-card__content {
  flex: 1;
  min-width: 0;
}

.stat-card__value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  line-height: var(--line-height-tight);
  letter-spacing: -0.02em;
}

.stat-card__label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: 2px;
  font-weight: var(--font-weight-medium);
}

.stat-card__trend {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 8px;
  border-radius: var(--radius-full);

  &--up {
    color: var(--color-success);
    background: var(--color-success-bg);
  }
  &--down {
    color: var(--color-error);
    background: var(--color-error-bg);
  }
}

@media (max-width: 768px) {
  .stat-card {
    padding: var(--spacing-md);
  }
  .stat-card__value {
    font-size: var(--font-size-xl);
  }
  .stat-card__icon {
    width: 40px;
    height: 40px;
    font-size: var(--font-size-lg);
  }
}
</style>
