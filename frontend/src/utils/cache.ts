/**
 * 数据缓存工具 - Data Cache Utility
 * 提供请求缓存、TTL管理等功能
 */

interface CacheEntry<T> {
  data: T
  timestamp: number
  ttl: number
}

interface CacheOptions {
  ttl?: number
  key?: string
  invalidate?: string
  skipCache?: boolean
}

class DataCache {
  private cache: Map<string, CacheEntry<any>> = new Map()
  private defaultTTL: number = 60000
  private maxEntries: number = 100

  constructor(defaultTTL?: number, maxEntries?: number) {
    if (defaultTTL) {
      this.defaultTTL = defaultTTL
    }
    if (maxEntries) {
      this.maxEntries = maxEntries
    }
  }

  /**
   * 设置缓存
   */
  set<T>(key: string, data: T, options?: CacheOptions): void {
    const ttl = options?.ttl || this.defaultTTL
    if (this.cache.size >= this.maxEntries) {
      const oldestKey = this.cache.keys().next().value
      if (oldestKey !== undefined) {
        this.cache.delete(oldestKey)
      }
    }
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      ttl
    })
    console.log(`[Cache] Set: ${key} (TTL: ${ttl}ms)`)
  }

  /**
   * 获取缓存
   */
  get<T>(key: string): T | null {
    const entry = this.cache.get(key)
    if (!entry) {
      console.log(`[Cache] Miss: ${key}`)
      return null
    }

    if (Date.now() - entry.timestamp > entry.ttl) {
      console.log(`[Cache] Expired: ${key}`)
      this.cache.delete(key)
      return null
    }

    console.log(`[Cache] Hit: ${key}`)
    return entry.data
  }

  /**
   * 删除缓存
   */
  delete(key: string): boolean {
    const existed = this.cache.delete(key)
    if (existed) {
      console.log(`[Cache] Deleted: ${key}`)
    }
    return existed
  }

  /**
   * 按模式失效缓存
   */
  invalidate(pattern: string): void {
    let count = 0
    for (const key of this.cache.keys()) {
      if (key.includes(pattern)) {
        this.cache.delete(key)
        count++
      }
    }
    console.log(`[Cache] Invalidated ${count} entries matching: ${pattern}`)
  }

  /**
   * 清空所有缓存
   */
  clear(): void {
    this.cache.clear()
    console.log('[Cache] Cleared all')
  }

  /**
   * 获取缓存统计
   */
  getStats() {
    let totalSize = 0
    let entryCount = 0
    
    for (const [, entry] of this.cache.entries()) {
      entryCount++
      totalSize += JSON.stringify(entry).length
    }

    return {
      entries: entryCount,
      size: totalSize,
      sizeKB: (totalSize / 1024).toFixed(2)
    }
  }

  /**
   * 包装请求，自动缓存
   */
  async wrap<T>(
    key: string,
    fetcher: () => Promise<T>,
    options?: CacheOptions
  ): Promise<T> {
    if (!options?.skipCache) {
      const cached = this.get<T>(key)
      if (cached !== null) {
        return cached
      }
    }

    const data = await fetcher()
    this.set(key, data, options)
    return data
  }
}

// 创建全局缓存实例
export const cache = new DataCache()

// 常用缓存键生成
export const cacheKeys = {
  intents: {
    list: 'intents:list',
    detail: (id: string | number) => `intents:detail:${id}`
  },
  audit: {
    list: 'audit:list',
    recent: 'audit:recent'
  },
  topology: {
    nodes: 'topology:nodes',
    edges: 'topology:edges'
  },
  rateLimit: {
    status: 'ratelimit:status',
    history: 'ratelimit:history'
  }
}

export default cache
