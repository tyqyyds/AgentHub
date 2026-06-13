import { ref } from 'vue'
import { api } from '@/utils/apiClient'
import { ElMessage } from 'element-plus'

type HttpMethod = 'get' | 'post' | 'put' | 'delete'

interface UseApiReturn<T> {
  data: ReturnType<typeof ref<T | null>>
  loading: ReturnType<typeof ref<boolean>>
  error: ReturnType<typeof ref<string | null>>
  execute: (url: string, method?: HttpMethod, payload?: unknown, config?: Record<string, unknown>) => Promise<T | null>
}

export function useApi<T = unknown>(): UseApiReturn<T> {
  const data = ref<T | null>(null) as ReturnType<typeof ref<T | null>>
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function execute(
    url: string,
    method: HttpMethod = 'get',
    payload?: unknown,
    config?: Record<string, unknown>
  ): Promise<T | null> {
    loading.value = true
    error.value = null
    try {
      let result: T
      switch (method) {
        case 'get':
          result = await api.get<T>(url, config)
          break
        case 'post':
          result = await api.post<T>(url, payload, config)
          break
        case 'put':
          result = await api.put<T>(url, payload, config)
          break
        case 'delete':
          result = await api.delete<T>(url, config)
          break
        default:
          throw new Error(`不支持的请求方法: ${method}`)
      }
      data.value = result
      return result
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '请求失败，请稍后重试'
      error.value = msg
      ElMessage.error(msg)
      return null
    } finally {
      loading.value = false
    }
  }

  return { data, loading, error, execute }
}
