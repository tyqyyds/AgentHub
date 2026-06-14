import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { resetSessionExpired } from '@/utils/apiClient'
import { API_BASE_URL } from '@/config'
import { decodeJwtPayload } from '@/utils/jwt'

interface UserInfo {
  id: number
  username: string
  role: string
  permissions: string[]
  email?: string
}

interface AuthTokens {
  access_token: string
  refresh_token: string
  expires_in: number
  user_info: UserInfo
}

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string>(localStorage.getItem('access_token') || '')
  const refreshToken = ref<string>(localStorage.getItem('refresh_token') || '')
  const userInfo = ref<UserInfo | null>(null)
  const tokenExpiresAt = ref<number>(Number(localStorage.getItem('token_expires_at')) || 0)
  const loading = ref(false)
  const error = ref<string>('')

  const isAuthenticated = computed(() => {
    if (!accessToken.value) return false
    if (tokenExpiresAt.value && Date.now() > tokenExpiresAt.value) return false
    return true
  })
  const userRole = computed(() => userInfo.value?.role || '')
  const permissions = computed(() => userInfo.value?.permissions || [])

  const loadUserInfo = () => {
    const stored = localStorage.getItem('user_info')
    if (stored) {
      try {
        const parsed = JSON.parse(stored)
        if (parsed && typeof parsed.username === 'string' && typeof parsed.role === 'string') {
          userInfo.value = parsed
        } else {
          localStorage.removeItem('user_info')
        }
      } catch {
        userInfo.value = null
        localStorage.removeItem('user_info')
      }
    }
  }

  const setTokens = (data: AuthTokens) => {
    accessToken.value = data.access_token
    refreshToken.value = data.refresh_token
    userInfo.value = data.user_info
    tokenExpiresAt.value = data.expires_in ? Date.now() + data.expires_in * 1000 : 0
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    localStorage.setItem('user_info', JSON.stringify(data.user_info))
    localStorage.setItem('token_expires_at', String(tokenExpiresAt.value))
  }

  const login = async (username: string, password: string) => {
    loading.value = true
    error.value = ''
    try {
      const response = await fetch(`${API_BASE_URL || ''}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
        credentials: 'include'
      })
      const text = await response.text()
      const data = text ? JSON.parse(text) : {}
      if (!response.ok) {
        throw new Error(data.detail || 'Login failed')
      }
      setTokens(data as AuthTokens)
      resetSessionExpired()
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '操作失败'
      return false
    } finally {
      loading.value = false
    }
  }

  const register = async (username: string, password: string, email?: string) => {
    loading.value = true
    error.value = ''
    try {
      const response = await fetch(`${API_BASE_URL || ''}/api/v1/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, email: email || null }),
        credentials: 'include'
      })
      const regText = await response.text()
      const data = regText ? JSON.parse(regText) : {}
      if (!response.ok) {
        throw new Error(data.detail || 'Registration failed')
      }
      setTokens(data as AuthTokens)
      resetSessionExpired()
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '操作失败'
      return false
    } finally {
      loading.value = false
    }
  }

  const refreshAccessToken = async (): Promise<boolean> => {
    if (!refreshToken.value) return false
    try {
      const response = await fetch(`${API_BASE_URL || ''}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken.value }),
        credentials: 'include'
      })
      if (!response.ok) {
        logout()
        return false
      }
      const refreshText = await response.text()
      const data: AuthTokens = refreshText ? JSON.parse(refreshText) : ({} as AuthTokens)
      setTokens(data)
      resetSessionExpired()
      return true
    } catch {
      logout()
      return false
    }
  }

  const logout = async () => {
    try {
      await fetch(`${API_BASE_URL || ''}/api/v1/auth/logout`, {
        method: 'POST',
        credentials: 'include'
      })
    } catch {}
    accessToken.value = ''
    refreshToken.value = ''
    userInfo.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user_info')
    localStorage.removeItem('token_expires_at')
  }

  const hasPermission = (permission: string): boolean => {
    return permissions.value.includes(permission)
  }

  loadUserInfo()

  return {
    accessToken,
    refreshToken,
    userInfo,
    tokenExpiresAt,
    loading,
    error,
    isAuthenticated,
    userRole,
    permissions,
    login,
    register,
    refreshAccessToken,
    logout,
    hasPermission,
    setTokens,
    decodeJwtPayload
  }
})
