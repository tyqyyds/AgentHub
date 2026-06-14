import { onMounted, onUnmounted, type Ref } from 'vue'
import gsap from 'gsap'
import { isMotionReduced } from '@/utils/animation'

export interface UseHoverScaleOptions {
  /** hover 时缩放比例，默认 1.03 */
  scale?: number
  /** 动画时长（秒），默认 0.25 */
  duration?: number
  /** GSAP ease，默认 'power2.out' */
  ease?: string
  /** hover 时额外阴影（CSS box-shadow 值），默认 undefined */
  shadowOnHover?: string
}

/**
 * 卡片 hover 缩放微交互 Composable
 *
 * @example
 * ```vue
 * <script setup>
 * const cardRef = ref<HTMLElement>()
 * useHoverScale(cardRef, { scale: 1.04, shadowOnHover: '0 8px 24px rgba(22,93,255,0.2)' })
 * </script>
 * <template>
 *   <div ref="cardRef">...</div>
 * </template>
 * ```
 */
export function useHoverScale(
  targetRef: Ref<HTMLElement | undefined>,
  options: UseHoverScaleOptions = {}
) {
  const {
    scale = 1.03,
    duration = 0.25,
    ease = 'power2.out',
    shadowOnHover
  } = options

  let tween: gsap.core.Tween | undefined

  const handleEnter = () => {
    if (isMotionReduced() || !targetRef.value) return
    tween?.kill()
    const vars: gsap.TweenVars = { scale, duration, ease }
    if (shadowOnHover) {
      tween = gsap.to(targetRef.value, { ...vars, boxShadow: shadowOnHover })
    } else {
      tween = gsap.to(targetRef.value, vars)
    }
  }

  const handleLeave = () => {
    if (isMotionReduced() || !targetRef.value) return
    tween?.kill()
    const vars: gsap.TweenVars = { scale: 1, duration, ease }
    if (shadowOnHover) {
      tween = gsap.to(targetRef.value, { ...vars, boxShadow: 'none' })
    } else {
      tween = gsap.to(targetRef.value, vars)
    }
  }

  onMounted(() => {
    if (!targetRef.value) return
    targetRef.value.addEventListener('mouseenter', handleEnter)
    targetRef.value.addEventListener('mouseleave', handleLeave)
  })

  onUnmounted(() => {
    tween?.kill()
    if (targetRef.value) {
      targetRef.value.removeEventListener('mouseenter', handleEnter)
      targetRef.value.removeEventListener('mouseleave', handleLeave)
    }
  })
}
