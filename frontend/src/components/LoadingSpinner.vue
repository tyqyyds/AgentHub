<template>
  <div class="loading-wrapper" :class="{ fullscreen: fullscreen }">
    <div class="loading-content">
      <div class="spinner">
        <div class="spinner-ring"></div>
        <div class="spinner-ring delay-1"></div>
        <div class="spinner-ring delay-2"></div>
      </div>
      <p v-if="text" class="loading-text">{{ text }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  text?: string
  fullscreen?: boolean
}>()
</script>

<style scoped>
.loading-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.loading-wrapper.fullscreen {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  z-index: 9999;
}

.loading-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.spinner {
  position: relative;
  width: 48px;
  height: 48px;
}

.spinner-ring {
  position: absolute;
  inset: 0;
  border: 3px solid rgba(100, 116, 139, 0.2);
  border-top-color: #165DFF;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.spinner-ring.delay-1 {
  animation-delay: 0.1s;
}

.spinner-ring.delay-2 {
  animation-delay: 0.2s;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  color: #94A3B8;
  font-size: 14px;
  margin: 0;
}
</style>
