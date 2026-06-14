import { ref, watch, onUnmounted, type Ref } from 'vue'
import gsap from 'gsap'
import { isMotionReduced } from '@/utils/animation'

export interface UseCountUpOptions {
  /** 动画时长（秒），默认 0.8 */
  duration?: number
  /** GSAP ease，默认 'power2.out' */
  ease?: string
  /** 小数位数，默认 0 */
  decimals?: number
  /** 千分位分隔符，默认 '' */
  separator?: string
}

/**
 * 数字滚动动画 Composable，替代 requestAnimationFrame 手动实现
 *
 * @example
 * ```vue
 * <script setup>
 * const count = ref(0)
 * const displayValue = useCountUp(count, { duration: 0.6 })
 * </script>
 * <template>
 *   <span>{{ displayValue.value }}</span>
 * </template>
 * ```
 */
export function useCountUp(
  source: Ref<number>,
  options: UseCountUpOptions = {}
) {
  const {
    duration = 0.8,
    ease = 'power2.out',
    decimals = 0,
    separator = ''
  } = options

  const formatNumber = (val: number, dec: number, sep: string): string => {
    const fixed = val.toFixed(dec)
    if (!sep) return fixed
    const [intPart, decPart] = fixed.split('.')
    const formatted = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, sep)
    return decPart ? `${formatted}.${decPart}` : formatted
  }

  const displayValue = ref(formatNumber(source.value, decimals, separator))
  let tween: gsap.core.Tween | undefined
  const proxy = { value: source.value }

  const animate = (from: number, to: number) => {
    if (isMotionReduced()) {
      proxy.value = to
      displayValue.value = formatNumber(to, decimals, separator)
      return
    }

    proxy.value = from
    tween?.kill()
    tween = gsap.to(proxy, {
      value: to,
      duration,
      ease,
      onUpdate: () => {
        displayValue.value = formatNumber(proxy.value, decimals, separator)
      }
    })
  }

  watch(source, (newVal, oldVal) => {
    animate(oldVal ?? 0, newVal)
  })

  onUnmounted(() => {
    tween?.kill()
  })

  return displayValue
}
