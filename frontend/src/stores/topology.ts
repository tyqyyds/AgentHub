import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/utils/apiClient'

interface TopologyNode {
  id: string
  name: string
  type: string
  status: 'online' | 'offline' | 'warning'
  ip?: string
  metadata?: Record<string, unknown>
}

interface TopologyLink {
  id: string
  source: string
  target: string
  type: string
  status: 'active' | 'inactive' | 'degraded'
  bandwidth?: string
  metadata?: Record<string, unknown>
}

interface TopologyData {
  nodes: TopologyNode[]
  links: TopologyLink[]
}

export const useTopologyStore = defineStore('topology', () => {
  const nodes = ref<TopologyNode[]>([])
  const links = ref<TopologyLink[]>([])
  const selectedNodeId = ref<string | null>(null)
  const loading = ref(false)

  const selectedNode = computed(() =>
    nodes.value.find(n => n.id === selectedNodeId.value) ?? null
  )

  const onlineNodeCount = computed(() =>
    nodes.value.filter(n => n.status === 'online').length
  )

  const offlineNodeCount = computed(() =>
    nodes.value.filter(n => n.status === 'offline').length
  )

  async function fetchTopology() {
    loading.value = true
    try {
      const data = await api.get<TopologyData>('/api/v1/topology')
      nodes.value = data.nodes
      links.value = data.links
    } finally {
      loading.value = false
    }
  }

  function selectNode(id: string | null) {
    selectedNodeId.value = id
  }

  async function refreshTopology() {
    await fetchTopology()
  }

  return {
    nodes,
    links,
    selectedNodeId,
    loading,
    selectedNode,
    onlineNodeCount,
    offlineNodeCount,
    fetchTopology,
    selectNode,
    refreshTopology
  }
})
