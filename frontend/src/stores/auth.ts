import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/utils/apiClient'

interface UserInfo {
  id: number
  username: string
  role: 'admin' | 'operator' | 'viewer'
  is_active: boolean
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isOperator = computed(() => user.value?.role === 'operator' || user.value?.role === 'admin')

  async function login(username: string, password: string) {
    loading.value = true
    error.value = null
    try {
      const data = await api.post<{ access_token: string; refresh_token: string; token_type: string }>(
        '/api/v1/auth/login',
        new URLSearchParams({ username, password }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
      )
      token.value = data.access_token
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      await fetchUser()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '登录失败，请稍后重试'
      error.value = msg
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchUser() {
    try {
      const data = await api.get<UserInfo>('/api/v1/auth/me')
      user.value = data
    } catch {
      logout()
    }
  }

  function logout() {
    user.value = null
    token.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  // 初始化时如果有token则获取用户信息
  if (token.value) {
    fetchUser()
  }

  return {
    user,
    token,
    loading,
    error,
    isAuthenticated,
    isAdmin,
    isOperator,
    login,
    logout,
    fetchUser
  }
})
