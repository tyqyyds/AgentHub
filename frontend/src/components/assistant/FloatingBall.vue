<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  unreadCount: number
}>()

const emit = defineEmits<{
  toggle: []
}>()

const position = ref({ x: window.innerWidth - 80, y: window.innerHeight - 100 })
const dragging = ref(false)
const dragOffset = ref({ x: 0, y: 0 })
const isHovered = ref(false)

function onMouseDown(e: MouseEvent) {
  dragging.value = true
  dragOffset.value = {
    x: e.clientX - position.value.x,
    y: e.clientY - position.value.y
  }
  e.preventDefault()
}

function onMouseMove(e: MouseEvent) {
  if (!dragging.value) return
  const newX = e.clientX - dragOffset.value.x
  const newY = e.clientY - dragOffset.value.y
  position.value = {
    x: Math.max(0, Math.min(window.innerWidth - 60, newX)),
    y: Math.max(0, Math.min(window.innerHeight - 60, newY))
  }
}

function onMouseUp() {
  dragging.value = false
}

function onClick() {
  if (!dragging.value) {
    emit('toggle')
  }
}

onMounted(() => {
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
})
</script>

<template>
  <div
    class="floating-ball"
    :class="{ hovered: isHovered, dragging }"
    :style="{ left: `${position.x}px`, top: `${position.y}px` }"
    @mousedown="onMouseDown"
    @mouseup="onMouseUp"
    @click="onClick"
    @mouseenter="isHovered = true"
    @mouseleave="isHovered = false"
  >
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="ball-icon">
      <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2z" />
      <path d="M8 14s1.5 2 4 2 4-2 4-2" />
      <line x1="9" y1="9" x2="9.01" y2="9" />
      <line x1="15" y1="9" x2="15.01" y2="9" />
    </svg>
    <span v-if="unreadCount > 0" class="badge">
      {{ unreadCount > 99 ? '99+' : unreadCount }}
    </span>
  </div>
</template>

<style scoped>
.floating-ball {
  position: fixed;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: var(--gradient-primary);
  box-shadow: 0 var(--spacing-2xs) 20px rgba(var(--color-primary-rgb), 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 9999;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  user-select: none;
}

.floating-ball.hovered {
  transform: scale(1.1);
  box-shadow: 0 var(--spacing-sm) 28px rgba(var(--color-primary-rgb), 0.6);
}

.floating-ball.dragging {
  transform: scale(0.95);
  box-shadow: 0 var(--spacing-3xs) var(--spacing-md) rgba(var(--color-primary-rgb), 0.3);
}

.ball-icon {
  width: 28px;
  height: 28px;
  color: var(--color-white);
}

.badge {
  position: absolute;
  top: calc(-1 * var(--spacing-2xs));
  right: calc(-1 * var(--spacing-2xs));
  min-width: 20px;
  height: 20px;
  padding: 0 var(--spacing-2xs);
  border-radius: var(--radius-md);
  background: var(--color-error);
  color: var(--color-white);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  line-height: 20px;
  text-align: center;
  box-shadow: 0 var(--spacing-3xs) var(--spacing-sm) rgba(var(--color-error-rgb), 0.5);
}
</style>
