import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiClient } from '@/utils/apiClient'
import { api } from '@/utils/apiClient'
import { useWebSocket } from '@/composables/useWebSocket'
import { useLogger } from '@/utils/logger'

const { info: logInfo, warn: logWarn } = useLogger()

export interface TopologyNode {
  id: string
  name: string
  type: string
  status: string
  ip: string
  vendor: string
  cpu_usage: number
  memory_usage: number
  uptime: string | null
  location: string | null
}

export interface TopologyLink {
  source: string
  target: string
  status: string
  bandwidth: string
  currentLoad: number
  link_type: string | null
}

export const useTopologyStore = defineStore('topology', () => {
  const nodes = ref<TopologyNode[]>([])
  const links = ref<TopologyLink[]>([])
  const loading = ref(false)
  const error = ref('')
  const lastUpdated = ref<Date | null>(null)

  const healthyNodes = computed(() => nodes.value.filter(n => n.status === 'healthy'))
  const warningNodes = computed(() => nodes.value.filter(n => n.status === 'warning'))
  const criticalNodes = computed(() => nodes.value.filter(n => n.status === 'critical'))
  const activeLinks = computed(() => links.value.filter(l => l.status === 'active'))
  const nodeMap = computed(() => {
    const map = new Map<string, TopologyNode>()
    nodes.value.forEach(n => map.set(n.id, n))
    return map
  })

  const fetchTopology = async () => {
    loading.value = true
    error.value = ''
    try {
      const result = await apiClient.get(api.topology)
      const data = result.data
      if (data) {
        nodes.value = data.nodes || []
        links.value = data.links || []
        lastUpdated.value = new Date()
        logInfo('Topology data loaded', { nodeCount: nodes.value.length, linkCount: links.value.length })
      }
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err)
      logWarn('Failed to fetch topology', { error: error.value })
    } finally {
      loading.value = false
    }
  }

  const fetchDevice = async (deviceId: string): Promise<TopologyNode | null> => {
    try {
      const result = await apiClient.get(api.topologyDeviceById(deviceId))
      return result.data as TopologyNode
    } catch {
      return null
    }
  }

  const getNodeById = (id: string): TopologyNode | undefined => {
    return nodeMap.value.get(id)
  }

  const ws = useWebSocket()
  ws.on('topology_update', () => {
    fetchTopology()
  })
  ws.on('device_update', (msg) => {
    const data = msg.data || {}
    const deviceId = data.id as string
    if (deviceId) {
      const node = nodes.value.find(n => n.id === deviceId)
      if (node) {
        if (data.status) node.status = data.status as string
        if (data.cpu_usage !== undefined) node.cpu_usage = data.cpu_usage as number
        if (data.memory_usage !== undefined) node.memory_usage = data.memory_usage as number
        if (data.uptime) node.uptime = data.uptime as string
      }
    }
  })

  return {
    nodes,
    links,
    loading,
    error,
    lastUpdated,
    healthyNodes,
    warningNodes,
    criticalNodes,
    activeLinks,
    nodeMap,
    fetchTopology,
    fetchDevice,
    getNodeById
  }
})
