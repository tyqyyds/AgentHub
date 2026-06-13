import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

interface BreadcrumbItem {
  title: string
  path?: string
}

type ThemeMode = 'light' | 'dark'

export const useAppStore = defineStore('app', () => {
  // 从 localStorage 恢复持久化状态
  const sidebarCollapsed = ref<boolean>(
    localStorage.getItem('sidebar_collapsed') === 'true'
  )
  const theme = ref<ThemeMode>(
    (localStorage.getItem('theme') as ThemeMode) || 'light'
  )
  const breadcrumbs = ref<BreadcrumbItem[]>([])
  const loading = ref(false)

  const isDark = computed(() => theme.value === 'dark')

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
    localStorage.setItem('sidebar_collapsed', String(sidebarCollapsed.value))
  }

  function setTheme(mode: ThemeMode) {
    theme.value = mode
    localStorage.setItem('theme', mode)
  }

  function setBreadcrumbs(items: BreadcrumbItem[]) {
    breadcrumbs.value = items
  }

  function setLoading(state: boolean) {
    loading.value = state
  }

  return {
    sidebarCollapsed,
    theme,
    breadcrumbs,
    loading,
    isDark,
    toggleSidebar,
    setTheme,
    setBreadcrumbs,
    setLoading
  }
})
