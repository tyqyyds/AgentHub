import axios from 'axios'
import type { AxiosRequestConfig, AxiosResponse } from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || ''

const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器：自动附加JWT Token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器：处理401自动刷新Token
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean }
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const res = await axios.post(`${API_BASE}/api/v1/auth/refresh`, {
            refresh_token: refreshToken
          })
          const { access_token } = res.data
          localStorage.setItem('access_token', access_token)
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${access_token}`
          }
          return apiClient(originalRequest)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      } else {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// authFetch：带认证的fetch封装
export async function authFetch<T = unknown>(url: string, options?: AxiosRequestConfig): Promise<T> {
  const response: AxiosResponse<T> = await apiClient(url, options)
  return response.data
}

// api对象：提供便捷方法
export const api = {
  get<T = unknown>(url: string, config?: AxiosRequestConfig) {
    return authFetch<T>(url, { ...config, method: 'GET' })
  },
  post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) {
    return authFetch<T>(url, { ...config, method: 'POST', data })
  },
  put<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) {
    return authFetch<T>(url, { ...config, method: 'PUT', data })
  },
  delete<T = unknown>(url: string, config?: AxiosRequestConfig) {
    return authFetch<T>(url, { ...config, method: 'DELETE' })
  }
}

export default apiClient
