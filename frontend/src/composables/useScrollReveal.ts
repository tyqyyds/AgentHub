import { onMounted, onUnmounted, type Ref } from 'vue'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { isMotionReduced } from '@/utils/animation'

gsap.registerPlugin(ScrollTrigger)

export interface UseScrollRevealOptions {
  /** 触发阈值 0-1，默认 0.15 */
  threshold?: number
  /** 从哪个方向进入: 'up' | 'down' | 'left' | 'right' | 'none'，默认 'up' */
  direction?: 'up' | 'down' | 'left' | 'right' | 'none'
  /** 动画时长（秒），默认 0.6 */
  duration?: number
  /** 延迟（秒），默认 0 */
  delay?: number
  /** 位移距离（px），默认 24 */
  distance?: number
  /** 是否只触发一次，默认 true */
  once?: boolean
  /** GSAP ease，默认 'power2.out' */
  ease?: string
}

/**
 * GSAP ScrollTrigger + prefers-reduced-motion 降级的 Vue Composable
 *
 * @example
 * ```vue
 * <script setup>
 * const sectionRef = ref<HTMLElement>()
 * useScrollReveal(sectionRef, { direction: 'up', stagger: 0.1 })
 * </script>
 * <template>
 *   <section ref="sectionRef">...</section>
 * </template>
 * ```
 */
export function useScrollReveal(
  targetRef: Ref<HTMLElement | undefined>,
  options: UseScrollRevealOptions = {}
) {
  const {
    threshold = 0.15,
    direction = 'up',
    duration = 0.6,
    delay = 0,
    distance = 24,
    once = true,
    ease = 'power2.out'
  } = options

  let ctx: gsap.Context | undefined

  onMounted(() => {
    if (!targetRef.value) return

    // prefers-reduced-motion 时直接显示
    if (isMotionReduced()) {
      gsap.set(targetRef.value, { opacity: 1, x: 0, y: 0 })
      return
    }

    ctx = gsap.context(() => {
      const fromVars: gsap.TweenVars = { opacity: 0 }

      switch (direction) {
        case 'up':    fromVars.y = distance; break
        case 'down':  fromVars.y = -distance; break
        case 'left':  fromVars.x = distance; break
        case 'right': fromVars.x = -distance; break
        case 'none':  break
      }

      gsap.from(targetRef.value!, {
        ...fromVars,
        duration,
        delay,
        ease,
        scrollTrigger: {
          trigger: targetRef.value!,
          start: `top ${(1 - threshold) * 100}%`,
          toggleActions: once ? 'play none none none' : 'play reverse play reverse',
        }
      })
    })
  })

  onUnmounted(() => {
    ctx?.revert()
  })
}
