/**
 * 统一API请求层 - Unified API Client
 * 提供标准化的请求、响应、错误处理
 */

export interface ApiResponse<T = any> {
  status: 'success' | 'error'
  data?: T
  message?: string
  errors?: Record<string, string[]>
}

export interface ApiConfig {
  baseURL?: string
  timeout?: number
  headers?: Record<string, string>
}

export interface RequestOptions extends RequestInit {
  timeout?: number
  skipCache?: boolean
  cacheTTL?: number
}

import { API_BASE_URL } from '@/config'

class ApiClient {
  private baseURL: string
  private timeout: number
  private headers: Record<string, string>
  private requestInterceptors: Array<(config: RequestOptions) => RequestOptions> = []
  private responseInterceptors: Array<(response: Response) => Response> = []

  constructor(config: ApiConfig = {}) {
    this.baseURL = config.baseURL || `${API_BASE_URL}/api/v1`
    this.timeout = config.timeout || 30000
    this.headers = config.headers || {
      'Content-Type': 'application/json'
    }
  }

  /**
   * 添加请求拦截器
   */
  addRequestInterceptor(interceptor: (config: RequestOptions) => RequestOptions) {
    this.requestInterceptors.push(interceptor)
  }

  /**
   * 添加响应拦截器
   */
  addResponseInterceptor(interceptor: (response: Response) => Response) {
    this.responseInterceptors.push(interceptor)
  }

  /**
   * 通用请求方法
   */
  async request<T = any>(
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseURL}${endpoint}`
    
    // 应用请求拦截器
    let config = { ...options }
    for (const interceptor of this.requestInterceptors) {
      config = interceptor(config)
    }

    // 设置超时
    const controller = new AbortController()
    const timeout = options.timeout || this.timeout
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    try {
      const response = await fetch(url, {
        ...config,
        headers: {
          ...this.headers,
          ...config.headers
        },
        signal: controller.signal
      })

      clearTimeout(timeoutId)

      // 应用响应拦截器
      let interceptedResponse = response
      for (const interceptor of this.responseInterceptors) {
        interceptedResponse = interceptor(interceptedResponse)
      }

      const data = await this.parseResponse(interceptedResponse)

      if (!interceptedResponse.ok) {
        throw new ApiError(
          data.message || `HTTP ${interceptedResponse.status}`,
          interceptedResponse.status,
          data.errors
        )
      }

      return data as ApiResponse<T>
    } catch (error) {
      clearTimeout(timeoutId)

      if (error instanceof ApiError) {
        throw error
      }

      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new ApiError('请求超时，请检查网络连接', 408)
      }

      throw new ApiError(
        error instanceof Error ? error.message : '网络错误',
        500
      )
    }
  }

  /**
   * 解析响应
   */
  private async parseResponse(response: Response) {
    const contentType = response.headers.get('content-type')
    
    if (contentType?.includes('application/json')) {
      return await response.json()
    }
    
    return {
      status: response.ok ? 'success' : 'error',
      message: response.statusText
    }
  }

  /**
   * GET请求
   */
  get<T = any>(endpoint: string, options?: RequestOptions): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'GET' })
  }

  /**
   * POST请求
   */
  post<T = any>(endpoint: string, data?: any, options?: RequestOptions): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined
    })
  }

  /**
   * PUT请求
   */
  put<T = any>(endpoint: string, data?: any, options?: RequestOptions): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined
    })
  }

  /**
   * DELETE请求
   */
  delete<T = any>(endpoint: string, options?: RequestOptions): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' })
  }

  /**
   * PATCH请求
   */
  patch<T = any>(endpoint: string, data?: any, options?: RequestOptions): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined
    })
  }
}

/**
 * API错误类
 */
export class ApiError extends Error {
  status: number
  errors?: Record<string, string[]>

  constructor(message: string, status: number, errors?: Record<string, string[]>) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.errors = errors
  }
}

// 创建默认实例
export const api = new ApiClient()

export default api
