import gsap from 'gsap'
import { ref } from 'vue'

/** 用户是否偏好减少动画 */
const prefersReducedMotion = ref(false)

/** 监听 prefers-reduced-motion 媒体查询 */
export function watchMotionPreference() {
  if (typeof window === 'undefined') return
  const mql = window.matchMedia('(prefers-reduced-motion: reduce)')
  prefersReducedMotion.value = mql.matches
  const handler = (e: MediaQueryListEvent) => {
    prefersReducedMotion.value = e.matches
  }
  mql.addEventListener('change', handler)
  return () => mql.removeEventListener('change', handler)
}

/** 获取当前动画偏好状态 */
export function isMotionReduced() {
  return prefersReducedMotion.value
}

/**
 * 安全动画封装 — 自动处理 prefers-reduced-motion 降级
 * 当用户偏好减少动画时，直接设置目标值而不执行动画
 */
export function safeAnimate(
  targets: gsap.TweenTarget,
  vars: gsap.TweenVars,
  reducedVars?: gsap.TweenVars
): gsap.core.Tween | void {
  if (prefersReducedMotion.value) {
    const fallback = reducedVars || Object.fromEntries(
      Object.entries(vars).filter(([k]) => !['duration', 'delay', 'ease', 'onComplete', 'onUpdate', 'onStart', 'onRepeat', 'onReverseComplete', 'stagger', 'repeat', 'yoyo', 'repeatDelay', 'data', 'id', 'callbacks'].includes(k))
    )
    gsap.set(targets, fallback)
    vars.onComplete?.(vars as any)
    return
  }
  return gsap.to(targets, vars)
}

/**
 * 安全滚动揭示动画
 * 当 prefers-reduced-motion 时直接显示元素
 */
export function safeScrollReveal(
  targets: gsap.TweenTarget,
  vars?: gsap.TweenVars
): gsap.core.Tween | void {
  const defaults: gsap.TweenVars = {
    opacity: 1,
    y: 0,
    duration: 0.6,
    ease: 'power2.out',
    ...vars
  }

  if (prefersReducedMotion.value) {
    gsap.set(targets, { opacity: 1, y: 0, x: 0, scale: 1 })
    return
  }

  return gsap.from(targets, defaults)
}

/** 从 CSS 变量读取动画时长（秒），带 fallback */
export function getAnimDuration(tokenName: string, fallback: number = 0.3): number {
  if (typeof document === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(tokenName).trim()
  if (!value) return fallback
  const parsed = parseFloat(value)
  return isNaN(parsed) ? fallback : parsed / 1000
}

/** 从 CSS 变量读取缓动函数，带 fallback */
export function getAnimEasing(tokenName: string, fallback: string = 'power2.out'): string {
  if (typeof document === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(tokenName).trim()
  return value || fallback
}

// 初始化监听
watchMotionPreference()
