<template>
  <span :class="['status-badge', statusConfig.class]" :style="customStyle">
    {{ statusConfig.label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getStatusConfig } from '../utils/constants'

const props = defineProps<{
  status: string
}>()

const statusConfig = computed(() => getStatusConfig(props.status))

const customStyle = computed(() => ({
  backgroundColor: `${statusConfig.value.color}15`,
  color: statusConfig.value.color
}))
</script>

<style scoped>
.status-badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  display: inline-block;
}
</style>
