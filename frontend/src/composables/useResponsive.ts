import { ref, computed, onUnmounted } from 'vue'

export const BREAKPOINTS = {
  XS: 480,
  SM: 640,
  MD: 768,
  LG: 1024,
  XL: 1200,
  XXL: 1600
} as const

export function useResponsive() {
  const width = ref(window.innerWidth)
  const height = ref(window.innerHeight)

  let timer: ReturnType<typeof setTimeout> | null = null

  const update = () => {
    width.value = window.innerWidth
    height.value = window.innerHeight
  }

  const debouncedUpdate = () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(update, 150)
  }

  const mediaQueries = [
    window.matchMedia(`(max-width: ${BREAKPOINTS.XS}px)`),
    window.matchMedia(`(max-width: ${BREAKPOINTS.SM}px)`),
    window.matchMedia(`(max-width: ${BREAKPOINTS.MD}px)`),
    window.matchMedia(`(max-width: ${BREAKPOINTS.LG}px)`),
    window.matchMedia(`(max-width: ${BREAKPOINTS.XL}px)`),
    window.matchMedia(`(max-width: ${BREAKPOINTS.XXL}px)`)
  ]

  const handleMediaChange = () => update()

  window.addEventListener('resize', debouncedUpdate)
  mediaQueries.forEach(mq => {
    mq.addEventListener('change', handleMediaChange)
  })

  onUnmounted(() => {
    if (timer) clearTimeout(timer)
    window.removeEventListener('resize', debouncedUpdate)
    mediaQueries.forEach(mq => {
      mq.removeEventListener('change', handleMediaChange)
    })
  })

  const isXs = computed(() => width.value <= BREAKPOINTS.XS)
  const isSm = computed(() => width.value <= BREAKPOINTS.SM)
  const isMobile = computed(() => width.value <= BREAKPOINTS.MD)
  const isTablet = computed(() => width.value > BREAKPOINTS.MD && width.value <= BREAKPOINTS.LG)
  const isDesktop = computed(() => width.value > BREAKPOINTS.LG)
  const isLargeDesktop = computed(() => width.value >= BREAKPOINTS.XL)
  const orientation = computed<'portrait' | 'landscape'>(() =>
    width.value >= height.value ? 'landscape' : 'portrait'
  )
  const isTouchDevice = computed(
    () => window.matchMedia('(pointer: coarse)').matches || ('ontouchstart' in window && navigator.maxTouchPoints > 0)
  )

  return {
    width,
    height,
    isXs,
    isSm,
    isMobile,
    isTablet,
    isDesktop,
    isLargeDesktop,
    orientation,
    isTouchDevice
  }
}
