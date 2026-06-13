import { ref, computed, onMounted, onUnmounted } from 'vue'

type BreakpointName = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

interface BreakpointConfig {
  name: BreakpointName
  query: string
}

const BREAKPOINTS: BreakpointConfig[] = [
  { name: 'xs', query: '(max-width: 575.98px)' },
  { name: 'sm', query: '(min-width: 576px) and (max-width: 767.98px)' },
  { name: 'md', query: '(min-width: 768px) and (max-width: 991.98px)' },
  { name: 'lg', query: '(min-width: 992px) and (max-width: 1199.98px)' },
  { name: 'xl', query: '(min-width: 1200px)' }
]

export function useResponsive() {
  const breakpoints = ref<Record<BreakpointName, boolean>>({
    xs: false,
    sm: false,
    md: false,
    lg: false,
    xl: false
  })

  const currentBreakpoint = ref<BreakpointName>('lg')

  const mediaQueryLists: MediaQueryList[] = []
  const handlers: Array<() => void> = []

  function updateBreakpoints(): void {
    for (const bp of BREAKPOINTS) {
      const mql = window.matchMedia(bp.query)
      breakpoints.value[bp.name] = mql.matches
      if (mql.matches) {
        currentBreakpoint.value = bp.name
      }
    }
  }

  const isMobile = computed(() => breakpoints.value.xs || breakpoints.value.sm)
  const isTablet = computed(() => breakpoints.value.md)
  const isDesktop = computed(() => breakpoints.value.lg || breakpoints.value.xl)

  onMounted(() => {
    updateBreakpoints()

    for (const bp of BREAKPOINTS) {
      const mql = window.matchMedia(bp.query)
      const handler = () => {
        breakpoints.value[bp.name] = mql.matches
        if (mql.matches) {
          currentBreakpoint.value = bp.name
        }
      }
      mql.addEventListener('change', handler)
      mediaQueryLists.push(mql)
      handlers.push(handler)
    }
  })

  onUnmounted(() => {
    for (let i = 0; i < mediaQueryLists.length; i++) {
      mediaQueryLists[i].removeEventListener('change', handlers[i])
    }
  })

  return {
    breakpoints,
    currentBreakpoint,
    isMobile,
    isTablet,
    isDesktop
  }
}
