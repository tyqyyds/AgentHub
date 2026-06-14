import { ref, computed, type ComputedRef } from 'vue'
import { useRouter } from 'vue-router'

export type TransitionDirection = 'forward' | 'backward' | 'none'

/**
 * 方向感知路由过渡 Composable
 * 根据路由 meta.depth 判断前进/后退方向，自动选择过渡动画
 *
 * @example
 * ```vue
 * <script setup>
 * const { transitionName, onBeforeEnter, onAfterLeave } = usePageTransition()
 * </script>
 * <template>
 *   <router-view v-slot="{ Component, route }">
 *     <transition :name="transitionName" mode="out-in"
 *       @before-enter="onBeforeEnter" @after-leave="onAfterLeave">
 *       <component :is="Component" :key="route.path" />
 *     </transition>
 *   </router-view>
 * </template>
 * ```
 */
export function usePageTransition() {
  const router = useRouter()
  const direction = ref<TransitionDirection>('none')

  // 路由守卫：根据 meta.depth 判断方向
  router.beforeEach((to, from) => {
    const toDepth = (to.meta?.depth as number) ?? 0
    const fromDepth = (from.meta?.depth as number) ?? 0
    if (toDepth > fromDepth) {
      direction.value = 'forward'
    } else if (toDepth < fromDepth) {
      direction.value = 'backward'
    } else {
      direction.value = 'none'
    }
  })

  const transitionName: ComputedRef<string> = computed(() => {
    switch (direction.value) {
      case 'forward':  return 'page-slide-left'
      case 'backward': return 'page-slide-right'
      default:         return 'page-fade'
    }
  })

  const onBeforeEnter = (el: Element) => {
    // 确保 GSAP JS 钩子可以访问到元素
    ;(el as HTMLElement).style.willChange = 'transform, opacity'
  }

  const onAfterLeave = (el: Element) => {
    ;(el as HTMLElement).style.willChange = 'auto'
  }

  return {
    direction,
    transitionName,
    onBeforeEnter,
    onAfterLeave
  }
}
