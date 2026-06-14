import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiClient, api } from '@/utils/apiClient'
import { useLogger } from '@/utils/logger'
import { showToast } from '@/utils/toast'
import { auditLogService } from '@/utils/auditLogService'
import { useAuthStore } from '@/stores/auth'

const { error: logError } = useLogger()

export interface AppState {
  loading: boolean
  sidebarCollapsed: boolean
  currentRoute: string
  fuseEnabled: boolean
  fuseReason: string
  showFuseConfirm: boolean
  fuseConfirmAction: 'enable' | 'disable'
  fuseBannerVisible: boolean
}

export const useAppStore = defineStore('app', () => {
  const loading = ref(false)
  const sidebarCollapsed = ref(false)
  const currentRoute = ref('Dashboard')
  const fuseEnabled = ref(false)
  const fuseReason = ref('')
  const showFuseConfirm = ref(false)
  const fuseConfirmAction = ref<'enable' | 'disable'>('enable')
  const fuseBannerVisible = ref(true)

  const isFused = computed(() => fuseEnabled.value)

  const setLoading = (value: boolean) => { loading.value = value }
  const toggleSidebar = () => { sidebarCollapsed.value = !sidebarCollapsed.value }
  const setCurrentRoute = (route: string) => { currentRoute.value = route }

  const fetchFuseStatus = async () => {
    try {
      const result = await apiClient.get(api.system.fuseStatus)
      const data = result.data
      if (data && typeof data.fuse_enabled === 'boolean') {
        const wasEnabled = fuseEnabled.value
        fuseEnabled.value = data.fuse_enabled
        fuseReason.value = data.fuse_reason || ''
        if (data.fuse_enabled && !wasEnabled) { fuseBannerVisible.value = true }
      }
    } catch (err: unknown) {
      if (err instanceof Error) logError('获取熔断状态失败', { error: err.message })
    }
  }

  const requestFuseToggle = () => {
    fuseConfirmAction.value = fuseEnabled.value ? 'disable' : 'enable'
    showFuseConfirm.value = true
  }

  const dismissFuseConfirm = () => { showFuseConfirm.value = false }

  const confirmFuseAction = async () => {
    showFuseConfirm.value = false
    const enabling = fuseConfirmAction.value === 'enable'
    const authStore = useAuthStore()
    try {
      setLoading(true)
      const result = await apiClient.post(api.system.fuse, {
        enable: enabling,
        reason: enabling ? '用户手动触发紧急熔断' : ''
      })
      const data = result.data
      if (data && typeof data.fuse_enabled === 'boolean') {
        fuseEnabled.value = data.fuse_enabled
        fuseReason.value = data.fuse_reason || ''
        if (fuseEnabled.value) {
          showToast('⚠️ 系统已进入紧急熔断状态！所有自动操作已暂停。', 'error')
          fuseBannerVisible.value = true
          auditLogService.recordSecurityAlert(authStore.userRole || 'unknown', '紧急熔断触发', 'critical', '用户手动触发紧急熔断')
        } else {
          showToast('✅ 系统熔断已解除，正常运行中。', 'success')
          auditLogService.recordSecurityAlert(authStore.userRole || 'unknown', '紧急熔断解除', 'info', '用户手动解除紧急熔断')
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error) logError('切换熔断状态失败', { error: err.message })
      showToast('熔断操作失败，请重试', 'error')
    } finally {
      setLoading(false)
    }
  }

  const dismissFuseBanner = () => { fuseBannerVisible.value = false }

  const reset = () => {
    loading.value = false
    sidebarCollapsed.value = false
    currentRoute.value = 'Dashboard'
    fuseEnabled.value = false
    fuseReason.value = ''
    showFuseConfirm.value = false
    fuseConfirmAction.value = 'enable'
    fuseBannerVisible.value = true
  }

  return {
    loading, sidebarCollapsed, currentRoute, fuseEnabled, fuseReason,
    showFuseConfirm, fuseConfirmAction, fuseBannerVisible,
    isFused,
    setLoading, toggleSidebar, setCurrentRoute,
    fetchFuseStatus, requestFuseToggle, dismissFuseConfirm, confirmFuseAction, dismissFuseBanner,
    reset
  }
})
