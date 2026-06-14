<template>
  <div
    class="ai-floating-ball"
    :class="[
      `state-${ballState}`,
      { 'chat-open': isOpen, 'is-dragging': isDragging }
    ]"
    :style="{
      left: position.x + 'px',
      top: position.y + 'px',
      opacity: opacity
    }"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
    @click="handleClick"
    @contextmenu.prevent="handleContextMenu"
    role="button"
    :aria-label="ariaLabel"
    tabindex="0"
    @keydown.enter="handleClick"
  >
    <svg
      v-if="ballState === 'thinking' || ballState === 'executing' || ballState === 'intercept'"
      class="state-ring"
      viewBox="0 0 72 72"
    >
      <template v-if="ballState === 'executing'">
        <circle
          class="progress-ring-bg"
          cx="36" cy="36" r="32"
          fill="none"
          stroke="rgba(64,158,255,0.15)"
          stroke-width="3"
        />
        <circle
          class="progress-ring"
          cx="36" cy="36" r="32"
          fill="none"
          stroke="#409EFF"
          stroke-width="3"
          stroke-linecap="round"
          :stroke-dasharray="circumference"
          :stroke-dashoffset="progressOffset"
          transform="rotate(-90 36 36)"
        />
      </template>
      <template v-if="ballState === 'thinking'">
        <circle
          class="brainwave-ring brainwave-ring-1"
          cx="36" cy="36" r="32"
          fill="none"
          stroke="rgba(64,158,255,0.6)"
          stroke-width="2"
          stroke-dasharray="4 8 12 8"
          stroke-linecap="round"
        />
        <circle
          class="brainwave-ring brainwave-ring-2"
          cx="36" cy="36" r="28"
          fill="none"
          stroke="rgba(64,158,255,0.3)"
          stroke-width="1.5"
          stroke-dasharray="6 6 3 9"
          stroke-linecap="round"
        />
        <circle
          class="brainwave-ring brainwave-ring-3"
          cx="36" cy="36" r="24"
          fill="none"
          stroke="rgba(64,158,255,0.15)"
          stroke-width="1"
          stroke-dasharray="2 10 8 4"
          stroke-linecap="round"
        />
      </template>
      <template v-if="ballState === 'intercept'">
        <circle
          class="intercept-ring"
          cx="36" cy="36" r="32"
          fill="none"
          stroke="rgba(230,162,60,0.6)"
          stroke-width="3"
          stroke-dasharray="8 6"
          stroke-linecap="round"
        />
      </template>
    </svg>

    <div class="ball-inner">
      <svg v-if="ballState !== 'executing'" class="ball-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z" fill="currentColor"/>
      </svg>
      <svg v-else class="ball-icon code-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M8 5l-5 7 5 7M16 5l5 7-5 7M14 3l-4 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>

    <div v-if="alertActive" class="alert-badge">!</div>
    <div v-if="unreadCount > 0 && !isOpen" class="unread-badge">{{ unreadCount > 9 ? '9+' : unreadCount }}</div>
    <div v-if="ballState === 'intercept'" class="intercept-badge">⚠</div>

    <Teleport to="body">
      <div v-if="showContextMenu" class="ball-context-menu" :style="{ left: contextMenuPos.x + 'px', top: contextMenuPos.y + 'px' }">
        <button class="ctx-item" @click="handleOpenChat">💬 打开助手</button>
        <button class="ctx-item" @click="handleHide">👁️ 隐藏至顶栏</button>
        <button class="ctx-item" @click="handleDndToggle">{{ dndMode ? '🔔 开启通知' : '🔕 免打扰模式' }}</button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, inject, watch } from 'vue'
import { useDraggable } from '@/composables/useDraggable'
import { useAssistantStore } from '@/stores/assistant'
import { ballPositionKey } from './injectionKeys'

const store = useAssistantStore()

const ballState = computed(() => store.ballState)
const alertActive = computed(() => store.alertActive)
const isOpen = computed(() => store.isOpen)
const unreadCount = computed(() => store.messages.filter(m => m.role === 'assistant' && m.status === 'sent').length)

const RING_RADIUS = 32
const circumference = 2 * Math.PI * RING_RADIUS

const progressOffset = computed(() => circumference * (1 - store.executionProgress / 100))

const dndMode = ref(false)

const ariaLabel = computed(() => {
  switch (ballState.value) {
    case 'alert': return '紧急告警 - 点击查看'
    case 'thinking': return 'AI 推理中 - 点击打开'
    case 'executing': return `AI 执行中 ${store.executionProgress}% - 点击打开`
    case 'intercept': return '等待审批 - 点击确认'
    default: return 'AI 助手 - 点击打开'
  }
})

const showContextMenu = ref(false)
const contextMenuPos = ref({ x: 0, y: 0 })

const { position, isDragging, opacity, handlePointerDown, handlePointerMove, handlePointerUp } = useDraggable({
  snapToEdge: true,
  onDragEnd: () => { showContextMenu.value = false }
})

const sharedBallPosition = inject(ballPositionKey, null)
watch(position, (pos) => {
  if (sharedBallPosition) {
    sharedBallPosition.value = { x: pos.x, y: pos.y + 28 }
  }
}, { immediate: true })

let dragDistance = 0
let startPos = { x: 0, y: 0 }

const onPointerDown = (e: PointerEvent) => {
  dragDistance = 0
  startPos = { x: e.clientX, y: e.clientY }
  handlePointerDown(e)
}

const onPointerMove = (e: PointerEvent) => {
  dragDistance = Math.abs(e.clientX - startPos.x) + Math.abs(e.clientY - startPos.y)
  handlePointerMove(e)
}

const onPointerUp = () => {
  handlePointerUp()
}

const handleClick = () => {
  if (dragDistance > 5) return
  showContextMenu.value = false
  if (alertActive.value) {
    store.dismissAlert()
  }
  store.openChat()
}

const handleContextMenu = (e: MouseEvent) => {
  contextMenuPos.value = { x: e.clientX, y: e.clientY }
  showContextMenu.value = true
}

const handleOpenChat = () => {
  showContextMenu.value = false
  store.openChat()
}

const handleHide = () => {
  showContextMenu.value = false
  store.hideAssistant()
}

const handleDndToggle = () => {
  dndMode.value = !dndMode.value
  showContextMenu.value = false
}

const handleClickOutside = () => {
  if (showContextMenu.value) showContextMenu.value = false
}

onMounted(() => document.addEventListener('click', handleClickOutside))
onUnmounted(() => document.removeEventListener('click', handleClickOutside))
</script>

<style scoped>
.ai-floating-ball {
  position: fixed;
  width: 56px;
  height: 56px;
  z-index: 9999;
  cursor: pointer;
  user-select: none;
  touch-action: none;
  transition: opacity var(--transition-fast);
}

.state-ring {
  position: absolute;
  top: -8px;
  left: -8px;
  width: 72px;
  height: 72px;
  pointer-events: none;
  overflow: visible;
}

.ball-inner {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.25s var(--ease-spring), box-shadow 0.3s var(--ease-out), background 0.4s var(--ease-out);
}

.ball-icon {
  width: 28px;
  height: 28px;
  color: white;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.2));
  z-index: 1;
}

.code-icon {
  width: 24px;
  height: 24px;
  animation: codeRotate 3s linear infinite;
}

@keyframes codeRotate {
  0% { transform: rotate(0deg); }
  25% { transform: rotate(5deg); }
  50% { transform: rotate(0deg); }
  75% { transform: rotate(-5deg); }
  100% { transform: rotate(0deg); }
}

.ai-floating-ball.state-breathing .ball-inner {
  background: var(--gradient-primary);
  box-shadow: var(--shadow-glow-primary), 0 4px 20px rgba(22, 93, 255, 0.35);
  animation: breathe 3s ease-in-out infinite;
}

@keyframes breathe {
  0%, 100% {
    box-shadow: var(--shadow-glow-primary), 0 4px 20px rgba(22, 93, 255, 0.35);
  }
  50% {
    box-shadow: 0 0 24px rgba(22, 93, 255, 0.3), 0 4px 28px rgba(22, 93, 255, 0.55);
  }
}

.ai-floating-ball.state-thinking .ball-inner {
  background: var(--gradient-primary);
  box-shadow: var(--shadow-glow-primary), 0 4px 20px rgba(22, 93, 255, 0.35);
  animation: brainwavePulse 2s ease-in-out infinite;
}

@keyframes brainwavePulse {
  0%, 100% {
    box-shadow: var(--shadow-glow-primary), 0 4px 20px rgba(22, 93, 255, 0.35);
  }
  30% {
    box-shadow: 0 0 28px rgba(22, 93, 255, 0.4), 0 4px 32px rgba(22, 93, 255, 0.6);
  }
  60% {
    box-shadow: 0 0 12px rgba(22, 93, 255, 0.1), 0 4px 14px rgba(22, 93, 255, 0.2);
  }
}

.brainwave-ring-1 {
  animation: brainwave1 2.5s linear infinite;
  transform-origin: 36px 36px;
  filter: drop-shadow(0 0 4px rgba(22, 93, 255, 0.5));
}

.brainwave-ring-2 {
  animation: brainwave2 3.5s linear infinite reverse;
  transform-origin: 36px 36px;
  filter: drop-shadow(0 0 3px rgba(22, 93, 255, 0.3));
}

.brainwave-ring-3 {
  animation: brainwave3 4s linear infinite;
  transform-origin: 36px 36px;
  filter: drop-shadow(0 0 2px rgba(22, 93, 255, 0.2));
}

@keyframes brainwave1 {
  from { transform: rotate(0deg); stroke-dashoffset: 0; }
  to { transform: rotate(360deg); stroke-dashoffset: -32; }
}

@keyframes brainwave2 {
  from { transform: rotate(0deg); stroke-dashoffset: 0; }
  to { transform: rotate(-360deg); stroke-dashoffset: 24; }
}

@keyframes brainwave3 {
  from { transform: rotate(0deg); stroke-dashoffset: 0; }
  to { transform: rotate(360deg); stroke-dashoffset: -48; }
}

.ai-floating-ball.state-alert .ball-inner {
  background: linear-gradient(135deg, #EF4444, #F56C6C);
  box-shadow: var(--shadow-glow-error), 0 4px 20px rgba(239, 68, 68, 0.45);
  animation: alertPulse 1s ease-in-out infinite, alertShake 0.5s ease-in-out infinite;
}

@keyframes alertPulse {
  0%, 100% {
    box-shadow: var(--shadow-glow-error), 0 4px 20px rgba(239, 68, 68, 0.45);
  }
  50% {
    box-shadow: 0 0 28px rgba(255, 77, 79, 0.4), 0 4px 32px rgba(239, 68, 68, 0.7);
  }
}

@keyframes alertShake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-3px); }
  40% { transform: translateX(3px); }
  60% { transform: translateX(-2px); }
  80% { transform: translateX(2px); }
}

.ai-floating-ball.state-executing .ball-inner {
  background: var(--gradient-primary);
  box-shadow: var(--shadow-glow-primary), 0 4px 20px rgba(22, 93, 255, 0.35);
}

.progress-ring-bg {
  transition: none;
}

.progress-ring {
  transition: stroke-dashoffset 0.35s var(--ease-out);
  filter: drop-shadow(0 0 3px rgba(22, 93, 255, 0.4));
}

.ai-floating-ball.state-intercept .ball-inner {
  background: linear-gradient(135deg, #E6A23C, #F0C78A);
  box-shadow: var(--shadow-glow-warning), 0 4px 20px rgba(230, 162, 60, 0.45);
  animation: interceptPulse 1.5s ease-in-out infinite, interceptShake 0.8s ease-in-out infinite;
}

@keyframes interceptPulse {
  0%, 100% {
    box-shadow: var(--shadow-glow-warning), 0 4px 20px rgba(230, 162, 60, 0.45);
  }
  50% {
    box-shadow: 0 0 24px rgba(250, 173, 20, 0.35), 0 4px 30px rgba(230, 162, 60, 0.65);
  }
}

@keyframes interceptShake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-2px); }
  75% { transform: translateX(2px); }
}

.intercept-ring {
  animation: interceptRingSpin 4s linear infinite;
  transform-origin: 36px 36px;
  filter: drop-shadow(0 0 4px rgba(250, 173, 20, 0.5));
}

@keyframes interceptRingSpin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.intercept-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 22px;
  height: 22px;
  background: var(--color-warning);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xs);
  font-weight: bold;
  border: 2px solid var(--color-bg-secondary);
  animation: badgePulse 1.5s ease-in-out infinite;
  z-index: 2;
}

.ai-floating-ball:not(.is-dragging):hover .ball-inner {
  transform: scale(1.1);
}

.ai-floating-ball.state-breathing:not(.is-dragging):hover .ball-inner {
  animation-play-state: paused;
  box-shadow: 0 0 28px rgba(22, 93, 255, 0.35), 0 6px 32px rgba(22, 93, 255, 0.55);
}

.ai-floating-ball.state-alert:not(.is-dragging):hover .ball-inner {
  animation-play-state: paused, running;
}

.ai-floating-ball.is-dragging .ball-inner {
  animation: none !important;
  transform: scale(1.12);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), 0 0 20px rgba(22, 93, 255, 0.3);
}

.ai-floating-ball.is-dragging .brainwave-ring,
.ai-floating-ball.is-dragging .intercept-ring {
  animation: none !important;
}

.ai-floating-ball.chat-open .ball-inner {
  background: linear-gradient(135deg, var(--color-success), var(--color-primary));
  box-shadow: var(--shadow-glow-success), 0 4px 20px rgba(82, 196, 26, 0.3);
}

.alert-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 20px;
  height: 20px;
  background: var(--color-error);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xs);
  font-weight: bold;
  border: 2px solid var(--color-bg-secondary);
  animation: badgePulse 1s ease-in-out infinite;
  z-index: 2;
}

@keyframes badgePulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.2); }
}

.unread-badge {
  position: absolute;
  top: -2px;
  right: -2px;
  min-width: 18px;
  height: 18px;
  background: var(--color-error);
  color: white;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0 var(--spacing-xs);
  border: 2px solid var(--color-bg-secondary);
  z-index: 2;
}

.ball-context-menu {
  position: fixed;
  z-index: 10001;
  background: var(--color-bg-elevated);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--radius-md);
  padding: var(--spacing-xs);
  min-width: 180px;
  box-shadow: var(--shadow-dropdown);
  animation: ctx-menu-in 0.15s var(--ease-out);
}

@keyframes ctx-menu-in {
  from { opacity: 0; transform: translateY(-4px) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.ctx-item {
  display: block;
  width: 100%;
  padding: var(--spacing-sm) 0.75rem;
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  text-align: left;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all 0.15s var(--ease-out);
}

.ctx-item:hover {
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  padding-left: 1rem;
}

.ctx-item:active {
  background: var(--color-primary-hover);
}

@media (max-width: 768px) {
  .ai-floating-ball {
    width: 52px;
    height: 52px;
  }
  .ball-icon {
    width: 26px;
    height: 26px;
  }
  .code-icon {
    width: 22px;
    height: 22px;
  }
  .state-ring {
    top: -6px;
    left: -6px;
    width: 64px;
    height: 64px;
  }
  .alert-badge {
    width: 18px;
    height: 18px;
    font-size: 0.6875rem;
    top: -3px;
    right: -3px;
  }
  .unread-badge {
    min-width: 16px;
    height: 16px;
    font-size: var(--font-size-xs);
  }
  .intercept-badge {
    width: 18px;
    height: 18px;
    font-size: var(--font-size-xs);
    top: -4px;
    right: -4px;
  }
  .ball-context-menu {
    min-width: 160px;
  }
  .ctx-item {
    padding: 10px 0.75rem;
    font-size: var(--font-size-base);
    min-height: var(--button-min-height-touch);
  }
}

@media (max-width: 480px) {
  .ai-floating-ball {
    width: 48px;
    height: 48px;
  }
  .ball-icon {
    width: 24px;
    height: 24px;
  }
  .code-icon {
    width: 20px;
    height: 20px;
  }
  .state-ring {
    top: -6px;
    left: -6px;
    width: 60px;
    height: 60px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ai-floating-ball.state-breathing .ball-inner {
    animation: none;
  }
  .ai-floating-ball.state-thinking .ball-inner {
    animation: none;
  }
  .ai-floating-ball.state-alert .ball-inner {
    animation: none;
  }
  .ai-floating-ball.state-intercept .ball-inner {
    animation: none;
  }
  .brainwave-ring-1,
  .brainwave-ring-2,
  .brainwave-ring-3 {
    animation: none;
  }
  .intercept-ring {
    animation: none;
  }
  .code-icon {
    animation: none;
  }
  .alert-badge {
    animation: none;
  }
  .intercept-badge {
    animation: none;
  }
  .unread-badge {
    animation: none;
  }
}
</style>
