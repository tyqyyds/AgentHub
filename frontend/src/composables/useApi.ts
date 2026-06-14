import { ref } from 'vue'
import { apiClient } from '@/utils/apiClient'
import { useLogger } from '@/utils/logger'

const logger = useLogger()

export function useApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const _activeRequests = ref(0)

  function _startRequest() {
    _activeRequests.value++
    loading.value = true
    error.value = null
  }

  function _endRequest() {
    _activeRequests.value--
    if (_activeRequests.value <= 0) {
      _activeRequests.value = 0
      loading.value = false
    }
  }

  async function get<T = any>(url: string): Promise<T | null> {
    _startRequest()
    try {
      const response = await apiClient.get(url)
      const data = response.data?.data ?? response.data
      return data as T
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '请求失败'
      error.value = msg
      logger.error(`API GET ${url} failed:`, msg)
      return null
    } finally {
      _endRequest()
    }
  }

  async function post<T = any>(url: string, body?: any): Promise<T | null> {
    _startRequest()
    try {
      const response = await apiClient.post(url, body)
      const data = response.data?.data ?? response.data
      return data as T
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '请求失败'
      error.value = msg
      logger.error(`API POST ${url} failed:`, msg)
      return null
    } finally {
      _endRequest()
    }
  }

  async function put<T = any>(url: string, body?: any): Promise<T | null> {
    _startRequest()
    try {
      const response = await apiClient.put(url, body)
      const data = response.data?.data ?? response.data
      return data as T
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '请求失败'
      error.value = msg
      logger.error(`API PUT ${url} failed:`, msg)
      return null
    } finally {
      _endRequest()
    }
  }

  async function del<T = any>(url: string): Promise<T | null> {
    _startRequest()
    try {
      const response = await apiClient.delete(url)
      const data = response.data?.data ?? response.data
      return data as T
    } catch (e: any) {
      const msg = e.response?.data?.detail || e.message || '请求失败'
      error.value = msg
      logger.error(`API DELETE ${url} failed:`, msg)
      return null
    } finally {
      _endRequest()
    }
  }

  return { loading, error, get, post, put, del }
}
