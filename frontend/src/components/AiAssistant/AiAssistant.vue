<template>
  <div class="ai-assistant-root" :class="sceneClass">
    <FloatingBall />
    <BubbleCard />
    <ChatPanel />
  </div>
</template>

<script setup lang="ts">
import { watch, onMounted, onUnmounted, computed, ref, provide } from 'vue'
import { ballPositionKey, type BallPosition } from './injectionKeys'

import { useRouter } from 'vue-router'
import { useAssistantStore } from '@/stores/assistant'
import { useAssistantContext } from '@/composables/useAssistantContext'
import { useAppStore } from '@/stores/app'
import { useAgenticEngine } from '@/composables/useAgenticEngine'
import FloatingBall from './FloatingBall.vue'
import BubbleCard from './BubbleCard.vue'
import ChatPanel from './ChatPanel.vue'

const store = useAssistantStore()
const appStore = useAppStore()
const router = useRouter()
const { currentContext } = useAssistantContext()
const agenticEngine = useAgenticEngine()

const sharedBallPosition = ref<BallPosition>({ x: window.innerWidth - 70, y: window.innerHeight / 2 })
provide(ballPositionKey, sharedBallPosition)

let routeChangeTimer: ReturnType<typeof setTimeout> | null = null

watch(() => router.currentRoute.value.path, (newPath, oldPath) => {
  if (newPath !== oldPath) {
    store.dismissBubble()
    if (routeChangeTimer) clearTimeout(routeChangeTimer)
    routeChangeTimer = setTimeout(() => {
      if (store.panelState === 'dormant' && !store.isHidden) {
        if (!store.isPageVisited(newPath)) {
          store.showBubble()
          store.markPageVisited(newPath)
        }
      }
    }, 1500)
  }
})

watch(() => appStore.fuseEnabled, (enabled) => {
  if (enabled) {
    store.addMessage({
      role: 'system',
      content: '🛑 紧急制动已触发，所有执行中意图已暂停。需要我为您排查触发原因吗？',
      actions: [
        { type: 'navigate', label: '查看详情', params: { route: '/' } }
      ],
      status: 'sent'
    })
    if (!store.isOpen) {
      store.openChat()
    }
  }
})

onMounted(() => {
  store.initNotificationListener()
  const currentPath = router.currentRoute.value.path
  if (routeChangeTimer) clearTimeout(routeChangeTimer)
  routeChangeTimer = setTimeout(() => {
    if (store.panelState === 'dormant' && !store.isHidden) {
      if (!store.isPageVisited(currentPath)) {
        store.showBubble()
        store.markPageVisited(currentPath)
      }
    }
  }, 3000)

  window.addEventListener('assistant:agentic_actions', handleAgenticActions)
})

const handleAgenticActions = (event: Event) => {
  const detail = (event as CustomEvent).detail
  if (detail && Array.isArray(detail.actions)) {
    detail.actions.forEach((action: any) => {
      agenticEngine.executeAgenticAction(action)
    })
  }
}

onUnmounted(() => {
  if (routeChangeTimer) clearTimeout(routeChangeTimer)
  window.removeEventListener('assistant:agentic_actions', handleAgenticActions)
})
</script>

<style scoped>
.ai-assistant-root {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 9990;
}

.ai-assistant-root > * {
  pointer-events: auto;
}

.scene-emergency {
  filter: none;
}

.scene-freeze .ai-floating-ball {
  filter: sepia(0.3) saturate(0.7);
}
</style>
