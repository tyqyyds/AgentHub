<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import { useLogger } from '@/utils/logger'
import { POLLING_INTERVAL } from '@/config'
import { api, apiClient, authFetch } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'
import { useApi } from '@/composables/useApi'
import { useAuthStore } from '@/stores/auth'
import gsap from 'gsap'
import { safeAnimate } from '@/utils/animation'

const { info, warn, error: logError } = useLogger()
const { error: apiError } = useApi()
const authStore = useAuthStore()
const canWrite = computed(() => authStore.userRole !== 'viewer')
const topologyError = ref<string | null>(null)

interface TopologyNode {
  id: string; name: string; type: string; health: number | null; cpu: number | null; memory: number | null
  traffic: string | null; x: number; y: number; locked: boolean; status: 'healthy' | 'warning' | 'error'
  originalX: number; originalY: number
}
interface TopologyLink {
  source: string; target: string; bandwidth: string; currentLoad: number
  status: 'active' | 'warning' | 'error' | 'down'; main: boolean; isCentralLink?: boolean; latency?: number | null
}
interface ContextMenuState { show: boolean; x: number; y: number; type: string; target: TopologyNode | TopologyLink | null }
interface LinkParticle { id: string; linkKey: string; progress: number; speed: number; color: string }
interface AlertItem { id: string; type: 'warning' | 'error' | 'info'; message: string; timestamp: number; dismissed: boolean }
interface A2AMessage {
  id: string; sender: string; receiver: string; task_id: string; action: string
  timestamp: string; payload: Record<string, unknown>; path: string[]
  status: 'pending' | 'in_progress' | 'completed'
}
interface MetricCard { label: string; value: number; displayValue: number; unit: string; icon: string; color: string; animFrameId: number | null }

const selectedNode = ref<string | null>(null)
const selectedLink = ref<string | null>(null)
const nodeDetails = ref<TopologyNode | null>(null)
const linkDetails = ref<TopologyLink | null>(null)
const showConfigModal = ref(false)
const showDiagnoseModal = ref(false)
const showSSHModal = ref(false)
const showQoSModal = ref(false)
const showDangerConfirm = ref(false)
const dangerConfirmAction = ref('')
const dangerConfirmTarget = ref<TopologyNode | TopologyLink | null>(null)
const sshCommand = ref('')
const qosBandwidth = ref('')
const qosPriority = ref('medium')
const isExecutingQoS = ref(false)
const isLeaving = ref(false)
const isRestoringSnapshot = ref(false)
const contextMenu = ref<ContextMenuState>({ show: false, x: 0, y: 0, type: '', target: null })
const animatingNodes = ref<Set<string>>(new Set())
const restartingNodes = ref<Set<string>>(new Set())
const restartingLinks = ref<Set<string>>(new Set())
const hiddenNodes = ref<Set<string>>(new Set())
const hiddenLinks = ref<Set<string>>(new Set())
const drainingLinks = ref<Set<string>>(new Set())
const originalLoads = ref<Map<string, number>>(new Map())
const isolatedLinks = ref<Set<string>>(new Set())
const svgContainer = ref<HTMLElement | null>(null)
const svgCanvas = ref<SVGSVGElement | null>(null)
const viewport = ref({ width: 1000, height: 550 })
const viewBox = ref('0 0 1000 550')
const isDragging = ref(false)
const dragOffset = ref({ x: 0, y: 0 })
const dragNode = ref<TopologyNode | null>(null)
let resizeObserver: ResizeObserver | null = null

let entranceCtx: gsap.Context | undefined

const playEntranceAnimation = () => {
  nextTick(() => {
    const container = document.querySelector('.topology-layout')
    if (!container) return
    entranceCtx?.revert()
    entranceCtx = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: 'power2.out' } })
      tl.from('.metrics-grid .metric-card', {
        opacity: 0, y: 16, stagger: 0.08, duration: 0.35
      })
      tl.from('.toolbar-panel', {
        opacity: 0, y: -10, duration: 0.3
      }, '-=0.15')
      tl.from('.stats-panel', {
        opacity: 0, x: -20, duration: 0.35
      }, '-=0.2')
    }, container as HTMLElement)
  })
}
const zoomLevel = ref(1)
const panOffset = ref({ x: 0, y: 0 })
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0 })
const panOffsetStart = ref({ x: 0, y: 0 })
const linkParticles = ref<LinkParticle[]>([])
let particleAnimFrame: number | null = null
let particleIdCounter = 0
const hoveredNode = ref<{ name: string; type: string; status: string; health: number | null; cpu: number | null; memory: number | null; traffic: string | null } | null>(null)
const tooltipPosition = ref({ x: 0, y: 0 })
const renderThrottleTimer = ref<number | null>(null)
const pendingRenderUpdate = ref(false)
type NodeUpdate = Array<{ id: string; health: number | null; cpu: number | null; memory: number | null; status: 'healthy' | 'warning' | 'error' }>
type LinkUpdate = Array<{ source: string; target: string; currentLoad: number; status: 'active' | 'warning' | 'error' | 'down' }>
let pendingNodeUpdates: NodeUpdate = []
let pendingLinkUpdates: LinkUpdate = []
const showMinimap = ref(true)
const searchInputRef = ref<HTMLElement | null>(null)
const linkLatencies = ref<Map<string, number>>(new Map())
const detailPanelOpen = ref(false)
const statsPanelFloating = ref(false)
const payloadExpanded = ref(false)
const transformString = computed(() => `translate(${panOffset.value.x}, ${panOffset.value.y}) scale(${zoomLevel.value})`)
const minimapViewBox = computed(() => `0 0 ${viewport.value.width} ${viewport.value.height}`)

const makeLinkKey = (source: string, target: string) => `${source}::${target}`
const parseLinkKey = (key: string): { source: string; target: string } => { const idx = key.indexOf('::'); if (idx === -1) return { source: key, target: '' }; return { source: key.slice(0, idx), target: key.slice(idx + 2) } }
const startLinkParticles = () => {
  const activeLinks = topologyData.value.links.filter(l => l.status === 'active' || l.status === 'warning')
  activeLinks.forEach(link => {
    const linkKey = makeLinkKey(link.source, link.target)
    const existing = linkParticles.value.filter(p => p.linkKey === linkKey)
    const particleCount = link.currentLoad >= 75 ? 3 : link.currentLoad >= 50 ? 2 : 1
    while (existing.length < particleCount) {
      const p: LinkParticle = { id: `particle_${linkKey}_${Date.now()}_${++particleIdCounter}`, linkKey, progress: Math.random() * 100, speed: 0.5 + (link.currentLoad / 100) * 2, color: getLinkLoadColor(link.currentLoad) }
      linkParticles.value.push(p); existing.push(p)
    }
  })
  updateParticles()
}
const updateParticles = () => {
  if (isLeaving.value) return
  const currentLinkKeys = new Set(topologyData.value.links.map(l => makeLinkKey(l.source, l.target)))
  linkParticles.value = linkParticles.value.filter(p => currentLinkKeys.has(p.linkKey))
  linkParticles.value.forEach(particle => {
    particle.progress += particle.speed; if (particle.progress >= 100) particle.progress = 0
    const link = topologyData.value.links.find(l => makeLinkKey(l.source, l.target) === particle.linkKey)
    if (link) { particle.speed = 0.5 + (link.currentLoad / 100) * 2; particle.color = getLinkLoadColor(link.currentLoad) }
  })
  particleAnimFrame = requestAnimationFrame(updateParticles)
}
const stopLinkParticles = () => { if (particleAnimFrame !== null) { cancelAnimationFrame(particleAnimFrame); particleAnimFrame = null } linkParticles.value = [] }
const getParticlePosition = (linkKey: string, progress: number): { x: number; y: number } => {
  const { source: sourceId, target: targetId } = parseLinkKey(linkKey)
  const sx = getNodeX(sourceId), sy = getNodeY(sourceId), tx = getNodeX(targetId), ty = getNodeY(targetId)
  return { x: sx + (tx - sx) * (progress / 100), y: sy + (ty - sy) * (progress / 100) }
}
const handleNodeHover = (node: TopologyNode, event: MouseEvent) => {
  hoveredNode.value = { name: node.name, type: node.type, status: node.status, health: node.health, cpu: node.cpu, memory: node.memory, traffic: node.traffic }
  tooltipPosition.value = { x: event.clientX, y: event.clientY }
}
const handleNodeLeave = () => { hoveredNode.value = null }
const handleTopologyKeyboard = (event: KeyboardEvent) => {
  if (event.key === '+' || event.key === '=') { event.preventDefault(); zoomIn() }
  else if (event.key === '-') { event.preventDefault(); zoomOut() }
  else if (event.key === '0') { event.preventDefault(); resetView() }
  else if (event.key === 'f' && event.ctrlKey) { event.preventDefault(); searchInputRef.value?.focus() }
  else if (event.key === 'r' && event.altKey) { event.preventDefault(); refreshTopologyData() }
  else if (event.key === 'Escape') { showConfigModal.value = false; showDiagnoseModal.value = false; showSSHModal.value = false; showQoSModal.value = false; showCopilotModal.value = false; showDisplayOptions.value = false }
}
const takeSnapshot = () => {
  const snapshot = { nodePositions: topologyData.value.nodes.map(n => ({ id: n.id, x: n.x, y: n.y })), centralPosition: { x: centralNode.value.x, y: centralNode.value.y }, zoomLevel: zoomLevel.value, panOffset: { ...panOffset.value }, layoutType: currentLayout.value, displayOptions: { ...displayOptions.value } }
  localStorage.setItem('topology_snapshot', JSON.stringify(snapshot)); showToast('拓扑快照已保存', 'success')
}
const restoreSnapshot = () => {
  const raw = localStorage.getItem('topology_snapshot')
  if (!raw) { showToast('未找到拓扑快照', 'warning'); return }
  try {
    const snapshot = JSON.parse(raw)
    if (typeof snapshot !== 'object' || snapshot === null) { showToast('快照数据格式无效', 'error'); return }
    isRestoringSnapshot.value = true
    if (snapshot.nodePositions && Array.isArray(snapshot.nodePositions)) snapshot.nodePositions.forEach((pos: { id: string; x: number; y: number }) => { if (typeof pos.id === 'string' && typeof pos.x === 'number' && typeof pos.y === 'number') { const node = topologyData.value.nodes.find(n => n.id === pos.id); if (node) { node.x = pos.x; node.y = pos.y } } })
    if (snapshot.centralPosition && typeof snapshot.centralPosition.x === 'number' && typeof snapshot.centralPosition.y === 'number') { centralNode.value.x = snapshot.centralPosition.x; centralNode.value.y = snapshot.centralPosition.y }
    if (typeof snapshot.zoomLevel === 'number') zoomLevel.value = snapshot.zoomLevel
    if (snapshot.panOffset && typeof snapshot.panOffset.x === 'number' && typeof snapshot.panOffset.y === 'number') panOffset.value = snapshot.panOffset
    if (typeof snapshot.layoutType === 'string') currentLayout.value = snapshot.layoutType
    if (snapshot.displayOptions && typeof snapshot.displayOptions === 'object') Object.assign(displayOptions.value, snapshot.displayOptions)
    nextTick(() => { isRestoringSnapshot.value = false })
    showToast('拓扑快照已恢复', 'success')
  } catch (err: unknown) { isRestoringSnapshot.value = false; if (err instanceof Error) logError('快照数据损坏', { error: err.message }); showToast('快照数据损坏，无法恢复', 'error') }
}
const hasSnapshot = computed(() => localStorage.getItem('topology_snapshot') !== null)
const handleWheel = (event: WheelEvent) => { event.preventDefault(); const delta = event.deltaY > 0 ? -0.1 : 0.1; zoomLevel.value = Math.min(3.0, Math.max(0.3, Math.round((zoomLevel.value + delta) * 10) / 10)) }
let lastTouchDist = 0
const handleTouchStart = (event: TouchEvent) => { if (event.touches.length === 2) { event.preventDefault(); const dx = event.touches[0].clientX - event.touches[1].clientX; const dy = event.touches[0].clientY - event.touches[1].clientY; lastTouchDist = Math.sqrt(dx * dx + dy * dy) } else if (event.touches.length === 1 && event.shiftKey) { event.preventDefault(); isPanning.value = true; panStart.value = { x: event.touches[0].clientX, y: event.touches[0].clientY }; panOffsetStart.value = { ...panOffset.value } } }
const handleTouchMove = (event: TouchEvent) => { if (event.touches.length === 2) { event.preventDefault(); const dx = event.touches[0].clientX - event.touches[1].clientX; const dy = event.touches[0].clientY - event.touches[1].clientY; const dist = Math.sqrt(dx * dx + dy * dy); if (lastTouchDist > 0) { const scale = dist / lastTouchDist; const newZoom = Math.min(3.0, Math.max(0.3, Math.round((zoomLevel.value * scale) * 10) / 10)); zoomLevel.value = newZoom } lastTouchDist = dist } else if (isPanning.value && event.touches.length === 1) { event.preventDefault(); panOffset.value = { x: panOffsetStart.value.x + event.touches[0].clientX - panStart.value.x, y: panOffsetStart.value.y + event.touches[0].clientY - panStart.value.y } } }
const handleTouchEnd = () => { lastTouchDist = 0; isPanning.value = false }
const handleCanvasPanStart = (event: MouseEvent) => { if (event.button === 1 || (event.button === 0 && event.shiftKey)) { event.preventDefault(); isPanning.value = true; panStart.value = { x: event.clientX, y: event.clientY }; panOffsetStart.value = { ...panOffset.value } } }
const handleCanvasPanMove = (event: MouseEvent) => { if (!isPanning.value) return; panOffset.value = { x: panOffsetStart.value.x + event.clientX - panStart.value.x, y: panOffsetStart.value.y + event.clientY - panStart.value.y } }
const handleCanvasPanEnd = () => { isPanning.value = false }
const resetView = () => { zoomLevel.value = 1; panOffset.value = { x: 0, y: 0 } }
const zoomIn = () => { zoomLevel.value = Math.min(3.0, Math.round((zoomLevel.value + 0.1) * 10) / 10) }
const zoomOut = () => { zoomLevel.value = Math.max(0.3, Math.round((zoomLevel.value - 0.1) * 10) / 10) }
const searchQuery = ref('')
const searchResults = ref<TopologyNode[]>([])
const searchNodeIndex = ref(-1)
const searchNodes = () => {
  if (!searchQuery.value.trim()) { searchResults.value = []; searchNodeIndex.value = -1; return }
  const query = searchQuery.value.toLowerCase()
  searchResults.value = topologyData.value.nodes.filter(node => node.name.toLowerCase().includes(query) || node.id.toLowerCase().includes(query))
  if (searchResults.value.length > 0) { searchNodeIndex.value = 0; navigateSearch(1) } else { searchNodeIndex.value = -1 }
}
const navigateSearch = (direction: 1 | -1) => {
  if (searchResults.value.length === 0) return
  searchNodeIndex.value = (searchNodeIndex.value + direction + searchResults.value.length) % searchResults.value.length
  const node = searchResults.value[searchNodeIndex.value]
  selectedNode.value = node.id; nodeDetails.value = node; selectedLink.value = null; linkDetails.value = null
  panOffset.value = { x: viewport.value.width / 2 - node.x * zoomLevel.value, y: viewport.value.height / 2 - node.y * zoomLevel.value }
}
const currentLayout = ref('hierarchical')
const LAYOUT_TYPES = ['hierarchical', 'force', 'circular', 'grid']
const applyLayout = (layoutType: string) => {
  currentLayout.value = layoutType; const nodes = topologyData.value.nodes; const vw = viewport.value.width, vh = viewport.value.height, padding = 80
  if (layoutType === 'hierarchical') {
    const baseWidth = 1000, baseHeight = 550; const scale = Math.min(vw / baseWidth, vh / baseHeight, 1.5)
    nodes.forEach(node => { const original = initialNodePositions[node.id]; if (original) { const clamped = clampToBounds((original.x - baseWidth / 2) * scale + vw / 2, (original.y - baseHeight / 2) * scale + vh / 2); node.x = clamped.x; node.y = clamped.y } })
  } else if (layoutType === 'force') {
    const positions = nodes.map(n => ({ x: n.x, y: n.y, vx: 0, vy: 0 })); const links = topologyData.value.links
    for (let iter = 0; iter < 50; iter++) {
      for (let i = 0; i < positions.length; i++) { for (let j = i + 1; j < positions.length; j++) { const dx = positions[i].x - positions[j].x, dy = positions[i].y - positions[j].y; const dist = Math.sqrt(dx * dx + dy * dy) || 1; if (dist < 120) { const force = (120 - dist) / dist * 0.5; positions[i].vx += dx * force; positions[i].vy += dy * force; positions[j].vx -= dx * force; positions[j].vy -= dy * force } } }
      links.forEach(link => { const si = nodes.findIndex(n => n.id === link.source), ti = nodes.findIndex(n => n.id === link.target); if (si >= 0 && ti >= 0) { const dx = positions[ti].x - positions[si].x, dy = positions[ti].y - positions[si].y; const dist = Math.sqrt(dx * dx + dy * dy) || 1, force = (dist - 150) * 0.01; positions[si].vx += dx / dist * force; positions[si].vy += dy / dist * force; positions[ti].vx -= dx / dist * force; positions[ti].vy -= dy / dist * force } })
      positions.forEach(p => { p.vx *= 0.9; p.vy *= 0.9; p.x += p.vx; p.y += p.vy })
    }
    positions.forEach((p, i) => { const clamped = clampToBounds(p.x, p.y); nodes[i].x = clamped.x; nodes[i].y = clamped.y })
  } else if (layoutType === 'circular') {
    const cx = vw / 2, cy = vh / 2, radius = Math.min(vw, vh) / 2 - padding
    nodes.forEach((node, i) => { const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2; const clamped = clampToBounds(cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)); node.x = clamped.x; node.y = clamped.y })
  } else if (layoutType === 'grid') {
    const cols = Math.ceil(Math.sqrt(nodes.length)); const cellW = (vw - padding * 2) / cols, rows = Math.ceil(nodes.length / cols), cellH = (vh - padding * 2) / rows
    nodes.forEach((node, i) => { const clamped = clampToBounds(padding + (i % cols) * cellW + cellW / 2, padding + Math.floor(i / cols) * cellH + cellH / 2); node.x = clamped.x; node.y = clamped.y })
  }
}
const alerts = ref<AlertItem[]>([])
const checkAlerts = () => {
  const newAlerts: AlertItem[] = []
  topologyData.value.nodes.forEach(node => {
    if (node.health !== null && node.health < 70) { const alertId = `node_error_${node.id}`; if (!alerts.value.find(a => a.id === alertId)) newAlerts.push({ id: alertId, type: 'error', message: `节点 ${node.name} 健康值严重过低 (${Math.round(node.health)}%)`, timestamp: Date.now(), dismissed: false }) }
    else if (node.health !== null && node.health < 85) { const alertId = `node_warning_${node.id}`; if (!alerts.value.find(a => a.id === alertId)) newAlerts.push({ id: alertId, type: 'warning', message: `节点 ${node.name} 健康值偏低 (${Math.round(node.health)}%)`, timestamp: Date.now(), dismissed: false }) }
  })
  topologyData.value.links.forEach(link => {
    const linkKey = makeLinkKey(link.source, link.target)
    if (link.currentLoad >= 90) { const alertId = `link_error_${linkKey}`; if (!alerts.value.find(a => a.id === alertId)) newAlerts.push({ id: alertId, type: 'error', message: `链路 ${linkKey} 负载过高 (${Math.round(link.currentLoad)}%)`, timestamp: Date.now(), dismissed: false }) }
    else if (link.currentLoad >= 75) { const alertId = `link_warning_${linkKey}`; if (!alerts.value.find(a => a.id === alertId)) newAlerts.push({ id: alertId, type: 'warning', message: `链路 ${linkKey} 负载偏高 (${Math.round(link.currentLoad)}%)`, timestamp: Date.now(), dismissed: false }) }
  })
  alerts.value = [...alerts.value.filter(a => !a.dismissed), ...newAlerts]
  alerts.value.forEach(alert => { if (Date.now() - alert.timestamp > 30000) alert.dismissed = true })
  alerts.value = alerts.value.filter(a => !a.dismissed)
}
const dismissAlert = (id: string) => { alerts.value = alerts.value.filter(a => a.id !== id) }
const clearAllAlerts = () => { alerts.value = [] }
const escapeCsvField = (field: string): string => { let escaped = field.replace(/[\r\n]+/g, ' '); if (/^[=+\-@\t]/.test(escaped)) escaped = `'${escaped}`; if (escaped.includes(',') || escaped.includes('"')) return `"${escaped.replace(/"/g, '""')}"`; return escaped }
const exportTopology = (format: 'json' | 'csv') => {
  const timestamp = Date.now()
  if (format === 'json') {
    const blob = new Blob([JSON.stringify(topologyData.value, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `topology_export_${timestamp}.json`; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(url); document.body.removeChild(a) }, 100)
  } else {
    const headers = 'id,name,type,status,health,cpu,memory'; const rows = topologyData.value.nodes.map(n => [escapeCsvField(n.id), escapeCsvField(n.name), escapeCsvField(n.type), escapeCsvField(n.status), String(n.health), String(n.cpu), String(n.memory)].join(','))
    const csv = '\uFEFF' + headers + '\n' + rows.join('\n'); const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `topology_export_${timestamp}.csv`; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(url); document.body.removeChild(a) }, 100)
  }
  showToast(`拓扑数据已导出为 ${format.toUpperCase()} 格式`, 'success')
}
const importTopology = (event: Event) => {
  const input = event.target as HTMLInputElement; const file = input.files?.[0]; if (!file) return
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const data = JSON.parse(e.target?.result as string)
      if (!data.nodes || !Array.isArray(data.nodes) || !data.links || !Array.isArray(data.links)) { showToast('导入失败：数据结构无效，缺少 nodes 或 links', 'error'); return }
      const validNodeFields = ['id', 'name', 'type', 'health', 'cpu', 'memory', 'x', 'y', 'status']
      const validLinkFields = ['source', 'target', 'bandwidth', 'currentLoad', 'status']
      const hasInvalidNode = data.nodes.some((n: Record<string, unknown>) => validNodeFields.some(f => !(f in n)))
      const hasInvalidLink = data.links.some((l: Record<string, unknown>) => validLinkFields.some(f => !(f in l)))
      if (hasInvalidNode) { showToast('导入失败：节点数据缺少必要字段', 'error'); return }
      if (hasInvalidLink) { showToast('导入失败：链路数据缺少必要字段', 'error'); return }
      topologyData.value = data; calculateResponsivePositions(); showToast('拓扑数据导入成功', 'success')
    } catch (err: unknown) { if (err instanceof Error) logError('导入失败', { error: err.message }); showToast('导入失败：JSON 解析错误', 'error') }
  }
  reader.readAsText(file); input.value = ''
}
const displayOptions = ref({ showLabels: true, showBandwidth: true, showHealth: true, showFlows: true, showA2A: true, nodeSize: 1 })
const showDisplayOptions = ref(false)
const NODE_MIN_DISTANCE = 100
const a2aMessages = ref<A2AMessage[]>([])
const showA2APanel = ref(false)
const currentA2AMessage = ref<A2AMessage | null>(null)
const mockA2AMessages: A2AMessage[] = [
  { id: 'msg_001', sender: 'central_agent', receiver: 'edge_agent_1', task_id: 'task_2024_001', action: 'exec_cli', timestamp: new Date().toLocaleTimeString(), payload: { command: 'show interfaces', device: 'core1' }, path: ['central', 'core1'], status: 'completed' },
  { id: 'msg_002', sender: 'edge_agent_1', receiver: 'central_agent', task_id: 'task_2024_001', action: 'response', timestamp: new Date().toLocaleTimeString(), payload: { status: 'success', output: 'Interface GigabitEthernet0/1 is up' }, path: ['core1', 'central'], status: 'completed' },
  { id: 'msg_003', sender: 'central_agent', receiver: 'edge_agent_2', task_id: 'task_2024_002', action: 'validate_config', timestamp: new Date().toLocaleTimeString(), payload: { config: 'interface GigabitEthernet0/2', device: 'agg2' }, path: ['central', 'agg2'], status: 'completed' }
]
const flowIntervals = new Set<number>()
const centralNode = ref<TopologyNode>({ x: 500, y: 80, id: 'central', name: '中心控制', type: 'central', status: 'healthy', health: 100, cpu: 25, memory: 40, traffic: '12.5G', locked: false, originalX: 500, originalY: 80 })
const initialNodePositions: Record<string, { x: number; y: number }> = { core1: { x: 400, y: 150 }, core2: { x: 600, y: 150 }, agg1: { x: 200, y: 300 }, agg2: { x: 500, y: 300 }, agg3: { x: 800, y: 300 }, acc1: { x: 100, y: 450 }, acc2: { x: 300, y: 450 }, acc3: { x: 600, y: 450 }, acc4: { x: 900, y: 450 } }
const topologyData = ref({
  nodes: [
    { id: 'core1', name: '核心路由器CR-01', type: 'router', health: 98, cpu: 45, memory: 62, traffic: '8.2G', x: 400, y: 150, locked: false, status: 'healthy' as const, originalX: 400, originalY: 150 },
    { id: 'core2', name: '核心路由器CR-02', type: 'router', health: 95, cpu: 58, memory: 71, traffic: '7.5G', x: 600, y: 150, locked: false, status: 'healthy' as const, originalX: 600, originalY: 150 },
    { id: 'agg1', name: '汇聚交换机AS-01', type: 'switch', health: 92, cpu: 32, memory: 48, traffic: '3.1G', x: 200, y: 300, locked: false, status: 'healthy' as const, originalX: 200, originalY: 300 },
    { id: 'agg2', name: '汇聚交换机AS-02', type: 'switch', health: 87, cpu: 78, memory: 82, traffic: '4.5G', x: 500, y: 300, locked: false, status: 'warning' as const, originalX: 500, originalY: 300 },
    { id: 'agg3', name: '汇聚交换机AS-03', type: 'switch', health: 96, cpu: 28, memory: 39, traffic: '2.8G', x: 800, y: 300, locked: false, status: 'healthy' as const, originalX: 800, originalY: 300 },
    { id: 'acc1', name: '接入交换机AC-01', type: 'switch', health: 99, cpu: 15, memory: 25, traffic: '450M', x: 100, y: 450, locked: false, status: 'healthy' as const, originalX: 100, originalY: 450 },
    { id: 'acc2', name: '接入交换机AC-02', type: 'switch', health: 94, cpu: 42, memory: 55, traffic: '680M', x: 300, y: 450, locked: false, status: 'healthy' as const, originalX: 300, originalY: 450 },
    { id: 'acc3', name: '接入交换机AC-03', type: 'switch', health: 97, cpu: 22, memory: 38, traffic: '520M', x: 600, y: 450, locked: false, status: 'healthy' as const, originalX: 600, originalY: 450 },
    { id: 'acc4', name: '接入交换机AC-04', type: 'switch', health: 72, cpu: 88, memory: 91, traffic: '950M', x: 900, y: 450, locked: false, status: 'error' as const, originalX: 900, originalY: 450 }
  ],
  links: [
    { source: 'central', target: 'core1', bandwidth: '40G', currentLoad: 65, status: 'active' as const, main: true, isCentralLink: true },
    { source: 'central', target: 'core2', bandwidth: '40G', currentLoad: 58, status: 'active' as const, main: true, isCentralLink: true },
    { source: 'core1', target: 'core2', bandwidth: '10G', currentLoad: 82, status: 'active' as const, main: true },
    { source: 'core1', target: 'agg1', bandwidth: '10G', currentLoad: 31, status: 'active' as const, main: true },
    { source: 'core1', target: 'agg2', bandwidth: '10G', currentLoad: 45, status: 'active' as const, main: true },
    { source: 'core2', target: 'agg2', bandwidth: '10G', currentLoad: 28, status: 'active' as const, main: false },
    { source: 'core2', target: 'agg3', bandwidth: '10G', currentLoad: 75, status: 'warning' as const, main: true },
    { source: 'agg1', target: 'acc1', bandwidth: '1G', currentLoad: 45, status: 'active' as const, main: true },
    { source: 'agg1', target: 'acc2', bandwidth: '1G', currentLoad: 68, status: 'active' as const, main: false },
    { source: 'agg2', target: 'acc2', bandwidth: '1G', currentLoad: 52, status: 'active' as const, main: true },
    { source: 'agg2', target: 'acc3', bandwidth: '1G', currentLoad: 38, status: 'active' as const, main: false },
    { source: 'agg3', target: 'acc3', bandwidth: '1G', currentLoad: 41, status: 'active' as const, main: true },
    { source: 'agg3', target: 'acc4', bandwidth: '1G', currentLoad: 95, status: 'error' as const, main: true }
  ] as TopologyLink[],
  flows: [
    { id: 'flow1', path: ['acc1', 'agg1', 'core1', 'core2', 'agg3', 'acc4'], type: 'data', bandwidth: '100M' },
    { id: 'flow2', path: ['acc2', 'agg2', 'core2', 'agg3', 'acc3'], type: 'video', bandwidth: '500M' }
  ]
})
const fetchTopologyData = async () => {
  try {
    const result = await apiClient.get<{
      nodes: Array<{
        id: string; name: string; type: string; status: string
        ip: string; vendor: string; cpu_usage: number; memory_usage: number
        uptime: string | null; location: string | null
        health?: number | null; traffic?: string | null
      }>;
      links: Array<{
        source: string; target: string; status: string
        bandwidth: string; currentLoad: number; link_type: string | null
        latency?: number | null
      }>
    }>(api.topology)
    const apiNodes = result.data.nodes
    const apiLinks = result.data.links
    const centralApiNode = apiNodes.find(n => n.id === 'central')
    const otherApiNodes = apiNodes.filter(n => n.id !== 'central')
    const typeOrder: Record<string, number> = { core: 0, aggregation: 1, access: 2 }
    const sortedNodes = [...otherApiNodes].sort((a, b) => (typeOrder[a.type] ?? 3) - (typeOrder[b.type] ?? 3))
    const groups: Record<string, typeof otherApiNodes> = { core: [], aggregation: [], access: [] }
    sortedNodes.forEach(n => { if (groups[n.type]) groups[n.type].push(n) })
    const baseWidth = 1000
    const newPositions: Record<string, { x: number; y: number }> = {}
    if (centralApiNode) {
      const cx = baseWidth / 2, cy = 80
      centralNode.value = {
        x: cx, y: cy, id: 'central', name: centralApiNode.name, type: 'central',
        status: centralApiNode.status as TopologyNode['status'],
        health: centralApiNode.health ?? null,
        cpu: centralApiNode.cpu_usage, memory: centralApiNode.memory_usage,
        traffic: centralApiNode.traffic ?? null, locked: false, originalX: cx, originalY: cy
      }
      newPositions['central'] = { x: cx, y: cy }
    }
    const yPositions: Record<string, number> = { core: 150, aggregation: 300, access: 450 }
    Object.entries(groups).forEach(([type, nodes]) => {
      const y = yPositions[type] || 450
      const count = nodes.length
      nodes.forEach((n, i) => {
        const x = count === 1 ? baseWidth / 2 : (baseWidth / (count + 1)) * (i + 1)
        newPositions[n.id] = { x, y }
      })
    })
    Object.keys(initialNodePositions).forEach(k => delete initialNodePositions[k])
    Object.assign(initialNodePositions, newPositions)
    const typeMap: Record<string, string> = { core: 'router', aggregation: 'switch', access: 'switch' }
    const mappedNodes: TopologyNode[] = otherApiNodes.map(n => {
      const pos = newPositions[n.id] || { x: 500, y: 300 }
      return {
        id: n.id, name: n.name, type: typeMap[n.type] || 'switch',
        health: n.health ?? null, cpu: n.cpu_usage, memory: n.memory_usage,
        traffic: n.traffic ?? null,
        x: pos.x, y: pos.y, locked: false,
        status: n.status as TopologyNode['status'],
        originalX: pos.x, originalY: pos.y
      }
    })
    const mappedLinks: TopologyLink[] = apiLinks.map(l => ({
      source: l.source, target: l.target,
      bandwidth: l.bandwidth, currentLoad: l.currentLoad,
      status: l.status as TopologyLink['status'],
      main: l.source === 'central' || (l.source.startsWith('core') && l.target.startsWith('agg')),
      isCentralLink: l.source === 'central' || l.target === 'central'
    }))
    topologyData.value = {
      nodes: mappedNodes as typeof topologyData.value.nodes,
      links: mappedLinks,
      flows: topologyData.value.flows
    }
    nextTick(() => { calculateResponsivePositions() })
    info('Topology data loaded from API', { nodeCount: mappedNodes.length, linkCount: mappedLinks.length })
    isMockData.value = false
    topologyError.value = null
  } catch (err) {
    warn('Failed to fetch topology from API, using local data', { error: err instanceof Error ? err.message : String(err) })
    isMockData.value = true
    topologyError.value = err instanceof Error ? err.message : '拓扑数据加载失败'
  }
}
const nodeMenuItems = computed(() => { const target = contextMenu.value?.target; const isLocked = isTopologyNode(target) ? target.locked : false; const items = [{ id: 'isolate', label: isLocked ? '取消隔离' : '隔离节点', icon: isLocked ? '🔓' : '🔒', danger: !isLocked, write: true }, { id: 'drain', label: '流量排空', icon: '🌊', danger: false, write: true }, { id: 'restart', label: '紧急重启', icon: '🔄', danger: true, write: true }, { id: 'ssh', label: 'Web SSH', icon: '💻', danger: false, write: true }, { id: 'viewConfig', label: '查看配置', icon: '📋', danger: false, write: false }, { id: 'diagnose', label: '执行诊断', icon: '🔍', danger: false, write: true }, { id: 'copilot', label: '唤醒智能副驾', icon: '🤖', danger: false, write: false }]; return canWrite.value ? items : items.filter(i => !i.write) })
const linkMenuItems = computed(() => { const items = [{ id: 'makePrimary', label: '设为主用', icon: '⭐', danger: false, write: true }, { id: 'limitBandwidth', label: 'QoS限速', icon: '📊', danger: false, write: true }, { id: 'viewLink', label: '查看详情', icon: '🔍', danger: false, write: false }, { id: 'copilot', label: '唤醒智能副驾', icon: '🤖', danger: false, write: false }]; return canWrite.value ? items : items.filter(i => !i.write) })
const checkCollision = (node: { x: number; y: number }, excludeNodeId: string) => { for (const otherNode of topologyData.value.nodes) { if (otherNode.id === excludeNodeId) continue; const dx = node.x - otherNode.x, dy = node.y - otherNode.y; if (Math.sqrt(dx * dx + dy * dy) < NODE_MIN_DISTANCE) return { collides: true, node: otherNode } } return { collides: false } }
const clampToBounds = (x: number, y: number) => { const padding = 50; return { x: Math.max(padding, Math.min(x, viewport.value.width - padding)), y: Math.max(padding, Math.min(y, viewport.value.height - padding)) } }
const calculateResponsivePositions = () => {
  if (!svgContainer.value) { warn('svgContainer 未初始化'); return }
  const containerRect = svgContainer.value.getBoundingClientRect(); const containerWidth = containerRect.width - 48, containerHeight = Math.max(400, containerRect.height - 200)
  const baseWidth = 1000, baseHeight = 550; const scale = Math.min(containerWidth / baseWidth, containerHeight / baseHeight, 1.5)
  viewport.value = { width: containerWidth, height: containerHeight }; viewBox.value = `0 0 ${containerWidth} ${containerHeight}`
  if (isRestoringSnapshot.value) return
  if (!isDragging.value || dragNode.value?.id !== 'central') { centralNode.value.x = containerWidth / 2; centralNode.value.y = 80 }
  topologyData.value.nodes.forEach(node => { const original = initialNodePositions[node.id]; if (original && !isDragging.value && dragNode.value?.id !== node.id) { const clamped = clampToBounds((original.x - baseWidth / 2) * scale + containerWidth / 2, (original.y - baseHeight / 2) * scale + containerHeight / 2); node.x = clamped.x; node.y = clamped.y } })
}
const handleDragStart = (event: MouseEvent | TouchEvent, node: TopologyNode) => { event.preventDefault(); event.stopPropagation(); if (node.locked) return; isDragging.value = true; dragNode.value = node; const svgPoint = getSvgPoint(event); if (svgPoint) dragOffset.value = { x: svgPoint.x - node.x, y: svgPoint.y - node.y } }
const handleDragMove = (event: MouseEvent | TouchEvent) => { if (!isDragging.value || !dragNode.value) return; const svgPoint = getSvgPoint(event); if (!svgPoint) return; let newX = svgPoint.x - dragOffset.value.x, newY = svgPoint.y - dragOffset.value.y; const clamped = clampToBounds(newX, newY); newX = clamped.x; newY = clamped.y; const collision = checkCollision({ x: newX, y: newY }, dragNode.value.id); if (collision.collides && collision.node) { const dx = newX - collision.node.x, dy = newY - collision.node.y; const distance = Math.sqrt(dx * dx + dy * dy); if (distance > 0) { newX = collision.node.x + (dx / distance) * NODE_MIN_DISTANCE; newY = collision.node.y + (dy / distance) * NODE_MIN_DISTANCE } } dragNode.value.x = newX; dragNode.value.y = newY }
const handleDragEnd = () => { isDragging.value = false; dragNode.value = null }
const getSvgPoint = (event: MouseEvent | TouchEvent) => { if (!svgCanvas.value) return null; const svg = svgCanvas.value as SVGSVGElement; let clientX: number, clientY: number; if ('touches' in event && event.touches.length > 0) { clientX = event.touches[0].clientX; clientY = event.touches[0].clientY } else { clientX = (event as MouseEvent).clientX; clientY = (event as MouseEvent).clientY } const CTM = svg.getScreenCTM(); if (!CTM) return null; return { x: (clientX - CTM.e) / CTM.a, y: (clientY - CTM.f) / CTM.d } }
const handleNodeClick = (node: TopologyNode) => { if (isDragging.value) return; selectedNode.value = node.id; selectedLink.value = null; nodeDetails.value = node; linkDetails.value = null; detailPanelOpen.value = true; closeContextMenu() }
const handleLinkClick = (link: TopologyLink) => { if (isDragging.value) return; selectedLink.value = makeLinkKey(link.source, link.target); selectedNode.value = null; linkDetails.value = link; nodeDetails.value = null; detailPanelOpen.value = true; closeContextMenu() }
const handleBackgroundClick = () => { selectedNode.value = null; selectedLink.value = null; nodeDetails.value = null; linkDetails.value = null; detailPanelOpen.value = false; closeContextMenu() }
const handleContextMenu = (event: MouseEvent, target: TopologyNode | TopologyLink, type: string) => { if (isDragging.value) return; event.preventDefault(); const menuW = 220, menuH = 300; const x = event.clientX + menuW > window.innerWidth ? event.clientX - menuW : event.clientX; const y = event.clientY + menuH > window.innerHeight ? event.clientY - menuH : event.clientY; contextMenu.value = { show: true, x, y, type, target } }
const closeContextMenu = () => { contextMenu.value.show = false }
let fetchAbortController: AbortController | null = null
let isFetching = false
let addA2AMessageTimer: number | null = null
let copilotNavTimer: number | null = null
let visibilityDebounceTimer: number | null = null
const isTopologyNode = (t: TopologyNode | TopologyLink | null): t is TopologyNode => t !== null && 'id' in t && 'health' in t
const isTopologyLink = (t: TopologyNode | TopologyLink | null): t is TopologyLink => t !== null && 'source' in t && 'target' in t
const handleMenuAction = async (actionId: string) => {
  const target = contextMenu.value.target; const isNode = isTopologyNode(target); const isLink = isTopologyLink(target)
  try {
    switch (actionId) {
      case 'isolate': if (!isNode) break; if (target.locked) { showToast(`正在取消隔离节点 ${target.name}...`, 'info'); await executeAction('unisolate_node', target); showToast(`节点 ${target.name} 已取消隔离`, 'success') } else { dangerConfirmAction.value = 'isolate_node'; dangerConfirmTarget.value = target; showDangerConfirm.value = true } break
      case 'drain': if (!isNode) break; showToast(`正在排空节点 ${target.name} 的流量...`, 'info'); await executeDrainAnimation(target); showToast(`节点 ${target.name} 流量排空和恢复完成`, 'success'); break
      case 'restart': if (!isNode) break; dangerConfirmAction.value = 'restart_device'; dangerConfirmTarget.value = target; showDangerConfirm.value = true; break
      case 'ssh': if (!isNode) break; sshCommand.value = `ssh admin@${target.id}`; showSSHModal.value = true; showToast('打开 SSH 终端', 'info'); break
      case 'viewConfig': if (!isNode) break; nodeDetails.value = target; showConfigModal.value = true; break
      case 'diagnose': if (!isNode) break; nodeDetails.value = target; showDiagnoseModal.value = true; showToast('执行设备诊断...', 'info'); break
      case 'makePrimary': if (!isLink) break; showToast(`正在将链路 ${makeLinkKey(target.source, target.target)} 设为主用...`, 'info'); await executeAction('make_primary', target); showToast(`链路 ${makeLinkKey(target.source, target.target)} 已设为主用`, 'success'); break
      case 'limitBandwidth': if (!isLink) break; linkDetails.value = target; qosBandwidth.value = target.bandwidth; showQoSModal.value = true; break
      case 'copilot': if (!isNode) break; openCopilotFromNode(target); break
    }
  } catch (err: unknown) { if (err instanceof Error) logError('执行操作失败', { error: err.message }); showToast('操作执行失败，请稍后重试', 'error') }
  closeContextMenu()
}

const confirmDangerAction = async () => {
  const action = dangerConfirmAction.value
  const target = dangerConfirmTarget.value
  showDangerConfirm.value = false
  if (!action || !target) return
  const isNode = isTopologyNode(target)
  try {
    if (action === 'isolate_node' && isNode) {
      showToast(`正在隔离节点 ${target.name}...`, 'info')
      await executeAction('isolate_node', target)
      showToast(`节点 ${target.name} 已成功隔离`, 'success')
    } else if (action === 'restart_device' && isNode) {
      showToast(`正在重启设备 ${target.name}...`, 'warning')
      await executeAction('restart_device', target)
      showToast(`设备 ${target.name} 正在重启`, 'success')
    }
  } catch (err: unknown) {
    if (err instanceof Error) logError('执行操作失败', { error: err.message })
    showToast('操作执行失败，请稍后重试', 'error')
  }
}

const executeAction = async (action: string, target: TopologyNode | TopologyLink) => {
  const nodeId = isTopologyNode(target) ? target.id : ''
  try {
    if (action === 'restart_device' && isTopologyNode(target)) { await executeRestartAnimation(target) }
    else {
      if (nodeId) animatingNodes.value.add(nodeId); await nextTick()
      if (action === 'isolate_node' && isTopologyNode(target)) { const node = topologyData.value.nodes.find(n => n.id === target.id); if (node) { node.locked = true; topologyData.value.links.filter(link => link.source === target.id || link.target === target.id).forEach(link => isolatedLinks.value.add(makeLinkKey(link.source, link.target))) } }
      else if (action === 'unisolate_node' && isTopologyNode(target)) { const node = topologyData.value.nodes.find(n => n.id === target.id); if (node) { node.locked = false; topologyData.value.links.filter(link => link.source === target.id || link.target === target.id).forEach(link => isolatedLinks.value.delete(makeLinkKey(link.source, link.target))) } }
      else if (action === 'make_primary' && isTopologyLink(target)) { const link = topologyData.value.links.find(l => l.source === target.source && l.target === target.target); if (link) { link.main = true; link.status = 'active' } }
      await new Promise(resolve => setTimeout(resolve, 600)); if (nodeId) animatingNodes.value.delete(nodeId)
    }
    try { if (fetchAbortController) fetchAbortController.abort(); fetchAbortController = new AbortController(); const targetLabel = isTopologyNode(target) ? target.name : isTopologyLink(target) ? makeLinkKey(target.source, target.target) : ''; const linkTarget = isTopologyLink(target) ? makeLinkKey(target.source, target.target) : ''; const response = await authFetch(api.intents, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_input: `对${targetLabel}执行${action}操作`, structured_params: { intent_name: action, target: nodeId || linkTarget, action } }), signal: fetchAbortController.signal }); if (!response.ok) throw new Error(`API请求失败: ${response.status}`); await response.json() } catch (err: unknown) { if (err instanceof Error && err.name !== 'AbortError') { showToast(`操作${action}同步失败`, 'warning') } }
    window.dispatchEvent(new CustomEvent('dashboardDataUpdated')); return true
  } catch (err: unknown) { if (err instanceof Error) logError('操作失败', { error: err.message }); if (nodeId) { animatingNodes.value.delete(nodeId); restartingNodes.value.delete(nodeId); hiddenNodes.value.delete(nodeId); topologyData.value.links.forEach(link => { const lk = makeLinkKey(link.source, link.target); hiddenLinks.value.delete(lk); restartingLinks.value.delete(lk) }) } return false }
}
const executeRestartAnimation = async (target: TopologyNode) => {
  const nodeId = target.id; const relatedLinks = topologyData.value.links.filter(link => link.source === nodeId || link.target === nodeId)
  try { hiddenNodes.value.add(nodeId); relatedLinks.forEach(link => hiddenLinks.value.add(makeLinkKey(link.source, link.target))); await new Promise(resolve => setTimeout(resolve, 400)); await new Promise(resolve => setTimeout(resolve, 2000)); hiddenNodes.value.delete(nodeId); relatedLinks.forEach(link => hiddenLinks.value.delete(makeLinkKey(link.source, link.target))); restartingNodes.value.add(nodeId); relatedLinks.forEach(link => restartingLinks.value.add(makeLinkKey(link.source, link.target))); await nextTick(); await new Promise(resolve => setTimeout(resolve, 400)) }
  finally { restartingNodes.value.delete(nodeId); hiddenNodes.value.delete(nodeId); relatedLinks.forEach(link => { restartingLinks.value.delete(makeLinkKey(link.source, link.target)); hiddenLinks.value.delete(makeLinkKey(link.source, link.target)) }) }
}
const executeDrainAnimation = async (target: TopologyNode) => {
  const nodeId = target.id; const relatedLinks = topologyData.value.links.filter(link => link.source === nodeId || link.target === nodeId)
  try { relatedLinks.forEach(link => { originalLoads.value.set(makeLinkKey(link.source, link.target), link.currentLoad); drainingLinks.value.add(makeLinkKey(link.source, link.target)) }); await nextTick(); const drainStart = Date.now(); while (Date.now() - drainStart < 2000) { const progress = (Date.now() - drainStart) / 2000; relatedLinks.forEach(link => { link.currentLoad = Math.max(0, (originalLoads.value.get(makeLinkKey(link.source, link.target)) || 0) * (1 - progress)) }); await new Promise(resolve => setTimeout(resolve, 16)) }; relatedLinks.forEach(link => { link.currentLoad = 0 }); const recoverStart = Date.now(); while (Date.now() - recoverStart < 5000) { const progress = (Date.now() - recoverStart) / 5000; relatedLinks.forEach(link => { const orig = originalLoads.value.get(makeLinkKey(link.source, link.target)) || 0; link.currentLoad = Math.min(orig, orig * progress) }); await new Promise(resolve => setTimeout(resolve, 16)) }; relatedLinks.forEach(link => { link.currentLoad = originalLoads.value.get(makeLinkKey(link.source, link.target)) || 0 }) }
  finally { relatedLinks.forEach(link => { drainingLinks.value.delete(makeLinkKey(link.source, link.target)); originalLoads.value.delete(makeLinkKey(link.source, link.target)) }) }
}
const handleExecuteQoS = async () => {
  if (!nodeDetails.value) return
  isExecutingQoS.value = true
  try {
    const response = await authFetch(api.mcpToolsExecute, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tool_name: 'config_qos',
        parameters: {
          device_id: nodeDetails.value.id || nodeDetails.value.name,
          bandwidth: qosBandwidth.value,
          priority: qosPriority.value
        }
      })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    if (data.status === 'success' || data.result) {
      showToast('QoS 配置已下发', 'success')
    } else {
      showToast('QoS 配置下发失败: ' + (data.message || 'Unknown error'), 'error')
    }
  } catch (e: unknown) {
    showToast('QoS 配置下发失败', 'error')
  } finally {
    isExecutingQoS.value = false
    showQoSModal.value = false
    fetchTopologyData()
  }
}
const addA2AMessage = (message: A2AMessage) => { a2aMessages.value.unshift({ ...message, id: `msg_${Date.now()}_${++particleIdCounter}` }); if (a2aMessages.value.length > 10) a2aMessages.value.pop(); currentA2AMessage.value = message; showA2APanel.value = true; if (addA2AMessageTimer !== null) clearTimeout(addA2AMessageTimer); addA2AMessageTimer = window.setTimeout(() => { showA2APanel.value = false; addA2AMessageTimer = null }, 5000) }
const simulateA2AMessage = () => { const randomMsg = mockA2AMessages[Math.floor(Math.random() * mockA2AMessages.length)]; addA2AMessage({ ...randomMsg, id: `msg_${Date.now()}_${++particleIdCounter}`, timestamp: new Date().toLocaleTimeString() }) }
const getActionColor = (action: string) => { const colors: Record<string, string> = { 'exec_cli': 'var(--color-primary)', 'response': 'var(--color-success)', 'validate_config': 'var(--color-warning)', 'isolate_node': '#FF4D4F', 'default': 'var(--color-text-tertiary)' }; return colors[action] || colors['default'] }
const getA2APath = (path: string[]) => { if (!path || path.length < 2) return ''; const nodes: Record<string, { x: number; y: number }> = { central: { x: centralNode.value.x, y: centralNode.value.y } }; topologyData.value.nodes.forEach(node => { nodes[node.id] = { x: node.x, y: node.y } }); let d = `M ${nodes[path[0]]?.x || 0} ${nodes[path[0]]?.y || 0}`; for (let i = 1; i < path.length; i++) { const prev = nodes[path[i - 1]], curr = nodes[path[i]]; if (prev && curr) d += ` Q ${(prev.x + curr.x) / 2} ${Math.min(prev.y, curr.y) - 20} ${curr.x} ${curr.y}` } return d }
const topologyStats = computed(() => {
  const nodes = topologyData.value.nodes, links = topologyData.value.links
  return { totalNodes: nodes.length, healthyNodes: nodes.filter(n => n.status === 'healthy').length, warningNodes: nodes.filter(n => n.status === 'warning').length, errorNodes: nodes.filter(n => n.status === 'error').length, totalLinks: links.length, activeLinks: links.filter(l => l.status === 'active').length, warningLinks: links.filter(l => l.status === 'warning').length, errorLinks: links.filter(l => l.status === 'error').length, mainLinks: links.filter(l => l.main).length, backupLinks: links.filter(l => !l.main).length, avgHealth: nodes.length > 0 ? Math.round(nodes.reduce((sum, n) => sum + (n.health ?? 0), 0) / nodes.length) : 0, avgLoad: links.length > 0 ? Math.round(links.reduce((sum, l) => sum + l.currentLoad, 0) / links.length) : 0 }
})
let animationFrame: number | null = null
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const animateNodes = () => { if (isLeaving.value) return; if (isDragging.value || prefersReducedMotion) { animationFrame = requestAnimationFrame(animateNodes); return }; topologyData.value.nodes.forEach(node => { if (!node.locked) { node.x += (Math.random() - 0.5) * 0.3; node.y += (Math.random() - 0.5) * 0.3 } }); animationFrame = requestAnimationFrame(animateNodes) }
const flushRenderUpdate = () => { if (!pendingRenderUpdate.value) return; pendingRenderUpdate.value = false; pendingNodeUpdates.forEach(update => { const node = topologyData.value.nodes.find(n => n.id === update.id); if (node && !node.locked) { if (update.health !== null) node.health = update.health; if (update.cpu !== null) node.cpu = update.cpu; if (update.memory !== null) node.memory = update.memory; node.status = update.status } }); pendingLinkUpdates.forEach(update => { const link = topologyData.value.links.find(l => l.source === update.source && l.target === update.target); if (link) { const lk = makeLinkKey(link.source, link.target); if (!drainingLinks.value.has(lk)) { link.currentLoad = update.currentLoad; link.status = update.status } } }); pendingNodeUpdates = []; pendingLinkUpdates = []; checkAlerts() }
const updateTopologyData = async () => {
  if (isFetching) return; isFetching = true
  try {
    const response = await authFetch(api.topology)
    if (response.ok) {
      const resp = await response.json()
      const topo = resp.data || resp
      if (topo?.nodes) {
        const newNodeUpdates: NodeUpdate = [];
        (topo.nodes || []).forEach((apiNode: any) => {
          const health = apiNode.health ?? null
          let status: 'healthy' | 'warning' | 'error' = 'healthy'
          if (health !== null && health < 70) status = 'error'
          else if (health !== null && health < 85) status = 'warning'
          newNodeUpdates.push({ id: apiNode.id, health, cpu: apiNode.cpu_usage ?? null, memory: apiNode.memory_usage ?? null, status })
        })
        pendingNodeUpdates = newNodeUpdates
      }
      if (topo?.links) {
        const newLinkUpdates: LinkUpdate = [];
        (topo.links || []).forEach((apiLink: any) => {
          newLinkUpdates.push({ source: apiLink.source, target: apiLink.target, currentLoad: apiLink.currentLoad ?? 0, status: apiLink.status ?? 'active' })
        })
        pendingLinkUpdates = newLinkUpdates
      }
      pendingRenderUpdate.value = true
      if (renderThrottleTimer.value === null) { flushRenderUpdate(); renderThrottleTimer.value = window.setTimeout(() => { renderThrottleTimer.value = null; if (pendingRenderUpdate.value) flushRenderUpdate() }, 1000) }
    }
  } catch {
    // Silently fail, keep existing data
  } finally { isFetching = false }
}
const refreshTopologyData = async () => { await fetchTopologyData(); showToast('拓扑数据已刷新', 'success') }
const getNodeStatusColor = (status: string) => { const colors: Record<string, string> = { healthy: 'var(--color-success)', warning: 'var(--color-warning)', error: '#FF4D4F' }; return colors[status] || colors.healthy }
const getNodeX = (nodeId: string): number => { if (nodeId === 'central') return centralNode.value.x; return topologyData.value.nodes.find(n => n.id === nodeId)?.x || 0 }
const getNodeY = (nodeId: string): number => { if (nodeId === 'central') return centralNode.value.y; return topologyData.value.nodes.find(n => n.id === nodeId)?.y || 0 }
const getLinkLoadColor = (load: number) => { if (load >= 90) return '#FF4D4F'; if (load >= 75) return '#FF7D00'; if (load >= 50) return 'var(--color-warning)'; if (load >= 25) return 'var(--color-success)'; return '#1890FF' }
const telemetryInterval = ref<number | null>(null)
const faultRipples = ref<Array<{ id: string; x: number; y: number; startTime: number }>>([])
const startTelemetrySimulation = () => {
  if (telemetryInterval.value) clearInterval(telemetryInterval.value)
  telemetryInterval.value = window.setInterval(async () => {
    if (!selectedNode.value) return
    try {
      const response = await authFetch(api.topologyDeviceById(selectedNode.value))
      if (response.ok) {
        const data = await response.json()
        const node = topologyData.value.nodes.find(n => n.id === selectedNode.value)
        if (node && !node.locked) {
          if (data.cpu_usage !== undefined) node.cpu = data.cpu_usage
          if (data.memory_usage !== undefined) node.memory = data.memory_usage
          if (data.health !== undefined) node.health = data.health
        }
        if (selectedNode.value === 'central') {
          if (data.cpu_usage !== undefined) centralNode.value.cpu = data.cpu_usage
          if (data.memory_usage !== undefined) centralNode.value.memory = data.memory_usage
          if (data.health !== undefined) centralNode.value.health = data.health
        }
        topologyData.value.links.forEach(link => {
          const linkId = makeLinkKey(link.source, link.target)
          if (link.latency != null) linkLatencies.value.set(linkId, link.latency)
          else linkLatencies.value.delete(linkId)
        })
      }
    } catch {
      // Keep existing data on failure
    }
  }, 5000)
}
const getLatencyColor = (latency: number) => { if (latency < 10) return 'var(--color-success)'; if (latency < 30) return 'var(--color-warning)'; if (latency < 60) return '#FF7D00'; return '#FF4D4F' }
const stopTelemetrySimulation = () => { if (telemetryInterval.value) { clearInterval(telemetryInterval.value); telemetryInterval.value = null } }
const copilotInput = ref('')
const showCopilotModal = ref(false)
const copilotTarget = ref<TopologyNode | TopologyLink | null>(null)
const openCopilotFromNode = (node: TopologyNode | TopologyLink) => { copilotTarget.value = node; copilotInput.value = ''; showCopilotModal.value = true }
const submitCopilotIntent = () => { if (!copilotInput.value.trim()) return; showCopilotModal.value = false; window.dispatchEvent(new CustomEvent('navigate', { detail: { view: 'IntentCenter' } })); if (copilotNavTimer !== null) clearTimeout(copilotNavTimer); copilotNavTimer = window.setTimeout(() => { window.dispatchEvent(new CustomEvent('prefill-intent', { detail: { text: copilotInput.value } })); copilotNavTimer = null }, 500) }
const handleClickOutside = (event: MouseEvent) => { if (!(event.target as HTMLElement).closest('.context-menu')) closeContextMenu() }
let a2aInterval: number | null = null
const topologyUpdateInterval = ref<number | null>(null)
const handleDashboardDataUpdated = () => { updateTopologyData() }
const handleVisibilityChange = () => { if (!document.hidden) { if (visibilityDebounceTimer !== null) clearTimeout(visibilityDebounceTimer); visibilityDebounceTimer = window.setTimeout(() => { if (!isFetching) updateTopologyData(); visibilityDebounceTimer = null }, 300) } }
const isMockData = ref(false)
const isLoading = ref(true)
const dataFreshness = ref('实时')
const lastRefreshTime = ref('')
const metrics = ref<MetricCard[]>([
  { label: '节点总数', value: 0, displayValue: 0, unit: '个', icon: '🖥️', color: 'var(--color-primary)', animFrameId: null },
  { label: '健康节点', value: 0, displayValue: 0, unit: '个', icon: '💚', color: 'var(--color-success)', animFrameId: null },
  { label: '活跃链路', value: 0, displayValue: 0, unit: '条', icon: '🔗', color: '#FF7D00', animFrameId: null },
  { label: '平均负载', value: 0, displayValue: 0, unit: '%', icon: '📊', color: 'var(--color-purple)', animFrameId: null }
])
const animateValue = (metric: MetricCard, from: number, to: number, duration: number = 600) => {
  if (metric.animFrameId) cancelAnimationFrame(metric.animFrameId); const startTime = performance.now()
  const animate = (currentTime: number) => { const elapsed = currentTime - startTime; const progress = Math.min(elapsed / duration, 1); const eased = 1 - Math.pow(1 - progress, 3); metric.displayValue = Math.round(from + (to - from) * eased); if (progress < 1) { metric.animFrameId = requestAnimationFrame(animate) } else { metric.animFrameId = null } }
  metric.animFrameId = requestAnimationFrame(animate)
}
watch(() => topologyStats.value, (stats) => { const newValues = [stats.totalNodes, stats.healthyNodes, stats.activeLinks, stats.avgLoad]; metrics.value.forEach((m, i) => { const oldVal = m.displayValue; m.value = newValues[i]; if (oldVal !== newValues[i]) animateValue(m, oldVal, newValues[i]) }); lastRefreshTime.value = new Date().toLocaleTimeString(); dataFreshness.value = '实时' }, { deep: true })
const getFlowPath = (path: string[]) => { if (!path || path.length < 2) return ''; const nodes: Record<string, { x: number; y: number }> = { central: { x: centralNode.value.x, y: centralNode.value.y } }; topologyData.value.nodes.forEach(node => { nodes[node.id] = { x: node.x, y: node.y } }); let d = `M ${nodes[path[0]]?.x || 0} ${nodes[path[0]]?.y || 0}`; for (let i = 1; i < path.length; i++) { const prev = nodes[path[i - 1]], curr = nodes[path[i]]; if (prev && curr) d += ` Q ${(prev.x + curr.x) / 2} ${Math.min(prev.y, curr.y) - 30} ${curr.x} ${curr.y}` } return d }
const getNodeIcon = (type: string) => { const icons: Record<string, { path: string; viewBox: string }> = { router: { path: 'M12 2L8 6h3v4H7V7.5L3 12l4 4.5V14h4v4H8l4 4 4-4h-3v-4h4v2.5l4-4.5-4-4.5V10h-4V6h3l-4-4z', viewBox: '0 0 24 24' }, switch: { path: 'M6 6h12v12H6V6zm2 2v8h8V8H8zm1 2h2v1H9v-1zm4 0h2v1h-2v-1zm-4 3h2v1H9v-1zm4 0h2v1h-2v-1z', viewBox: '0 0 24 24' }, firewall: { path: 'M12 2C8 4 4 5 2 6v7c0 5.5 4.3 8.7 10 11 5.7-2.3 10-5.5 10-11V6c-2-1-6-2-10-4zm0 2c3 1.5 6 2.5 8 3.2V13c0 4-3.2 6.5-8 8.5-4.8-2-8-4.5-8-8.5V7.2c2-.7 5-1.7 8-3.2z', viewBox: '0 0 24 24' }, server: { path: 'M4 4h16v4H4V4zm0 6h16v4H4v-4zm0 6h16v4H4v-4zm2-9h1v2H6V7zm0 6h1v2H6v-2zm0 6h1v2H6v-2z', viewBox: '0 0 24 24' }, core: { path: 'M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 16.8l-6.2 4.5 2.4-7.4L2 9.4h7.6L12 2z', viewBox: '0 0 24 24' } }; return icons[type] || icons.router }
const getLinkWidth = (link: TopologyLink): number => { const bw = link.bandwidth || ''; let width = 1.5; if (bw.includes('100G')) width = 6; else if (bw.includes('40G')) width = 5; else if (bw.includes('10G')) width = 4; else if (bw.includes('1G')) width = 3.5; else if (bw.includes('100M')) width = 2.5; if ((link.currentLoad ?? 0) > 80) width = Math.min(7, width + 1); return width }
const getResourceRingPath = (cx: number, cy: number, r: number, percentage: number): string => { const clampedPct = Math.min(100, Math.max(0, percentage)); if (clampedPct === 0) return ''; const startAngle = -90, endAngle = startAngle + (clampedPct / 100) * 360; const startRad = (startAngle * Math.PI) / 180, endRad = (endAngle * Math.PI) / 180; const x1 = cx + r * Math.cos(startRad), y1 = cy + r * Math.sin(startRad), x2 = cx + r * Math.cos(endRad), y2 = cy + r * Math.sin(endRad); return `M ${x1} ${y1} A ${r} ${r} 0 ${clampedPct > 50 ? 1 : 0} 1 ${x2} ${y2}` }
const getResourceColor = (percentage: number): string => { if (percentage < 60) return 'var(--color-success)'; if (percentage < 80) return 'var(--color-warning)'; if (percentage < 90) return '#FF7A45'; return '#FF4D4F' }
const getLinkLabelTransform = (link: TopologyLink): string => { const x1 = getNodeX(link.source), y1 = getNodeY(link.source), x2 = getNodeX(link.target), y2 = getNodeY(link.target); const mx = (x1 + x2) / 2, my = (y1 + y2) / 2; let angle = Math.atan2(y2 - y1, x2 - x1) * (180 / Math.PI); if (angle > 90) angle -= 180; if (angle < -90) angle += 180; return `translate(${mx}, ${my}) rotate(${angle})` }
const lodLevel = computed<'full' | 'medium' | 'low'>(() => { const nodeCount = topologyData.value.nodes.length + 1; const zoom = zoomLevel.value; if (zoom >= 0.8 && nodeCount <= 20) return 'full'; if (zoom >= 0.5 || nodeCount <= 50) return 'medium'; return 'low' })
const effectiveDisplayOptions = computed(() => { const base = { ...displayOptions.value }; if (lodLevel.value === 'low') { base.showFlows = false; base.showHealth = false } return base })
const visibleNodes = computed(() => { const vw = viewport.value.width, vh = viewport.value.height, zoom = zoomLevel.value, pan = panOffset.value, padding = 100; const minX = (-pan.x / zoom) - padding, minY = (-pan.y / zoom) - padding, maxX = ((vw - pan.x) / zoom) + padding, maxY = ((vh - pan.y) / zoom) + padding; return topologyData.value.nodes.filter(n => n.x >= minX && n.x <= maxX && n.y >= minY && n.y <= maxY) })
const visibleLinks = computed(() => { const visibleIds = new Set(visibleNodes.value.map(n => n.id)); visibleIds.add('central'); return topologyData.value.links.filter(l => visibleIds.has(l.source) && visibleIds.has(l.target)) })

function handleAssistantHighlight(e: Event) {
  const detail = (e as CustomEvent).detail
  if (!detail?.entityType || !detail?.entityId) return
  if (detail.entityType === 'device' || detail.entityType === 'node') {
    const nodeId = detail.entityId as string
    const node = topologyData.value.nodes.find(n => n.id === nodeId)
    if (node) {
      selectedNode.value = node.id
      selectedLink.value = null
      nodeDetails.value = node
      linkDetails.value = null
      detailPanelOpen.value = true
    }
  }
}

function handleAssistantExecute(e: Event) {
  const detail = (e as CustomEvent).detail
  if (detail?.command === 'highlight_fault_links') {
    const faultLinks = topologyData.value.links.filter(l => l.status === 'error' || l.status === 'warning')
    if (faultLinks.length > 0) {
      const firstFaultLink = faultLinks[0]
      selectedLink.value = makeLinkKey(firstFaultLink.source, firstFaultLink.target)
      selectedNode.value = null
      linkDetails.value = firstFaultLink
      nodeDetails.value = null
      detailPanelOpen.value = true
      faultLinks.forEach(link => {
        const linkKey = makeLinkKey(link.source, link.target)
        const srcX = getNodeX(link.source)
        const srcY = getNodeY(link.source)
        faultRipples.value.push({ id: `ripple_${linkKey}_${Date.now()}`, x: srcX, y: srcY, startTime: Date.now() })
      })
    }
  }
}

onMounted(() => {
  nextTick(() => { calculateResponsivePositions(); if (svgContainer.value) { resizeObserver = new ResizeObserver(() => calculateResponsivePositions()); resizeObserver.observe(svgContainer.value) } document.addEventListener('mousemove', handleDragMove); document.addEventListener('mouseup', handleDragEnd); document.addEventListener('touchmove', handleDragMove); document.addEventListener('touchend', handleDragEnd); document.addEventListener('mousemove', handleCanvasPanMove); document.addEventListener('mouseup', handleCanvasPanEnd) })
  animateNodes(); topologyUpdateInterval.value = window.setInterval(updateTopologyData, POLLING_INTERVAL.DASHBOARD); a2aInterval = window.setInterval(simulateA2AMessage, 8000)
  startTelemetrySimulation(); startLinkParticles(); window.addEventListener('dashboardDataUpdated', handleDashboardDataUpdated)
  window.addEventListener('assistant:highlight', handleAssistantHighlight)
  window.addEventListener('assistant:execute', handleAssistantExecute)
  document.addEventListener('click', handleClickOutside); document.addEventListener('keydown', handleTopologyKeyboard); document.addEventListener('visibilitychange', handleVisibilityChange)
  fetchTopologyData().finally(() => { isLoading.value = false; info('Topology mounted') })
  playEntranceAnimation()
})
onUnmounted(() => {
  isLeaving.value = true
  if (animationFrame !== null) { cancelAnimationFrame(animationFrame); animationFrame = null }
  if (a2aInterval !== null) { clearInterval(a2aInterval); a2aInterval = null }
  if (topologyUpdateInterval.value !== null) { clearInterval(topologyUpdateInterval.value); topologyUpdateInterval.value = null }
  if (telemetryInterval.value !== null) { clearInterval(telemetryInterval.value); telemetryInterval.value = null }
  if (renderThrottleTimer.value !== null) { clearTimeout(renderThrottleTimer.value); renderThrottleTimer.value = null }
  if (visibilityDebounceTimer !== null) { clearTimeout(visibilityDebounceTimer); visibilityDebounceTimer = null }
  if (addA2AMessageTimer !== null) { clearTimeout(addA2AMessageTimer); addA2AMessageTimer = null }
  if (copilotNavTimer !== null) { clearTimeout(copilotNavTimer); copilotNavTimer = null }
  if (fetchAbortController) fetchAbortController.abort()
  flowIntervals.forEach(id => clearInterval(id)); flowIntervals.clear()
  stopLinkParticles(); stopTelemetrySimulation()
  if (resizeObserver) resizeObserver.disconnect()
  metrics.value.forEach(m => { if (m.animFrameId) cancelAnimationFrame(m.animFrameId) })
  document.removeEventListener('mousemove', handleDragMove); document.removeEventListener('mouseup', handleDragEnd)
  document.removeEventListener('touchmove', handleDragMove); document.removeEventListener('touchend', handleDragEnd)
  document.removeEventListener('mousemove', handleCanvasPanMove); document.removeEventListener('mouseup', handleCanvasPanEnd)
  document.removeEventListener('click', handleClickOutside); document.removeEventListener('keydown', handleTopologyKeyboard)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  window.removeEventListener('dashboardDataUpdated', handleDashboardDataUpdated)
  window.removeEventListener('assistant:highlight', handleAssistantHighlight)
  window.removeEventListener('assistant:execute', handleAssistantExecute)
})
</script>

<template>
  <div class="topology-container">
    <div class="topo-bg"><div class="bg-grid"></div><div class="bg-glow glow-1"></div><div class="bg-glow glow-2"></div></div>
    <div class="topo-header">
      <div class="header-left"><h1 class="page-title">网络拓扑</h1><p class="page-subtitle">算力网络多智能体协同调度拓扑视图</p></div>
      <div class="header-actions">
        <span class="data-freshness" :class="{ degraded: dataFreshness === '降级' }"><span class="freshness-dot"></span>{{ dataFreshness }}</span>
        <span v-if="lastRefreshTime" class="last-refresh">{{ lastRefreshTime }}</span>
        <button type="button" class="action-btn" @click="simulateA2AMessage" title="模拟A2A通信" aria-label="模拟A2A通信">🚀 模拟 A2A</button>
      </div>
    </div>
    <div v-if="isLoading" class="metrics-grid"><div v-for="i in 4" :key="i" class="metric-card skeleton"><div class="skeleton-line wide"></div><div class="skeleton-line narrow"></div></div></div>
    <div v-else class="metrics-grid">
      <div v-for="(metric, idx) in metrics" :key="metric.label" class="metric-card" :style="{ '--accent': metric.color, '--delay': `${idx * 0.08}s` }">
        <div class="metric-icon" :style="{ background: `${metric.color}18`, color: metric.color }">{{ metric.icon }}</div>
        <div class="metric-content"><div class="metric-value" :style="{ textShadow: `0 0 24px ${metric.color}40` }">{{ metric.displayValue }}<span class="metric-unit">{{ metric.unit }}</span></div><div class="metric-label">{{ metric.label }}</div></div>
        <div class="metric-bottom-bar"><div class="metric-bottom-fill" :style="{ background: `linear-gradient(90deg, ${metric.color}, ${metric.color}66)` }"></div></div>
      </div>
    </div>
    <div class="toolbar-panel">
      <div class="toolbar-group"><button type="button" class="toolbar-btn" @click="zoomIn" title="放大" aria-label="放大">🔍+</button><button type="button" class="toolbar-btn" @click="zoomOut" title="缩小" aria-label="缩小">🔍-</button><button type="button" class="toolbar-btn" @click="resetView" title="重置视图" aria-label="重置视图">⟲</button><span class="zoom-level">{{ Math.round(zoomLevel * 100) }}%</span><span v-if="lodLevel !== 'full'" class="lod-indicator" :title="'当前渲染级别: ' + lodLevel">{{ lodLevel === 'medium' ? '🎨 中等画质' : '⚡ 性能模式' }}</span></div>
      <div class="toolbar-group"><select v-model="currentLayout" @change="applyLayout(currentLayout)" class="layout-select" title="布局方式" aria-label="布局方式"><option v-for="lt in LAYOUT_TYPES" :key="lt" :value="lt">{{ lt === 'hierarchical' ? '层次布局' : lt === 'force' ? '力导向' : lt === 'circular' ? '环形布局' : '网格布局' }}</option></select></div>
      <div class="toolbar-group search-group"><input v-model="searchQuery" ref="searchInputRef" class="search-input" placeholder="搜索节点..." @keydown.enter="searchNodes" aria-label="搜索节点" /><button type="button" class="toolbar-btn" @click="searchNodes" title="搜索" aria-label="搜索">🔎</button><button type="button" v-if="searchResults.length" class="toolbar-btn" @click="navigateSearch(1)" title="下一个" aria-label="下一个">↓</button><button type="button" v-if="searchResults.length" class="toolbar-btn" @click="navigateSearch(-1)" title="上一个" aria-label="上一个">↑</button><span v-if="searchResults.length" class="search-count">{{ searchNodeIndex + 1 }}/{{ searchResults.length }}</span></div>
      <div class="toolbar-group"><button type="button" class="toolbar-btn" @click="exportTopology('json')" title="导出JSON" aria-label="导出JSON">📤 JSON</button><button type="button" class="toolbar-btn" @click="exportTopology('csv')" title="导出CSV" aria-label="导出CSV">📊 CSV</button><label class="toolbar-btn import-btn" title="导入拓扑" aria-label="导入拓扑">📥 导入<input type="file" accept=".json" @change="importTopology" style="display:none" /></label></div>
      <div class="toolbar-group"><button type="button" class="toolbar-btn" @click="showDisplayOptions = !showDisplayOptions" title="显示选项" aria-label="显示选项">⚙️</button><button type="button" class="toolbar-btn" @click="takeSnapshot" title="保存快照" aria-label="保存快照">📸 快照</button><button type="button" v-if="hasSnapshot" class="toolbar-btn" @click="restoreSnapshot" title="恢复快照" aria-label="恢复快照">🔄 恢复</button></div>
    </div>
    <div class="topology-layout">
      <div v-if="topologyError && isMockData" class="error-banner">
        <span class="error-banner-icon">⚠️</span>
        <span class="error-banner-text">拓扑数据加载失败: {{ topologyError }}，当前显示为模拟数据</span>
        <button type="button" class="error-banner-retry" @click="refreshTopologyData" aria-label="重试">🔄 重试</button>
      </div>
      <aside :class="['stats-panel', { floating: statsPanelFloating }]">
        <div class="stats-panel-header">
          <h3 class="stats-panel-title">📊 拓扑统计</h3>
          <button type="button" class="stats-pin-btn" @click="statsPanelFloating = !statsPanelFloating" :title="statsPanelFloating ? '固定面板' : '浮动面板'" aria-label="固定/浮动面板">{{ statsPanelFloating ? '📌' : '📍' }}</button>
        </div>
        <div class="stats-section">
          <div class="stats-section-title">节点 ({{ topologyStats.totalNodes }})</div>
          <div class="stats-items">
            <div class="stats-item"><span class="stats-dot healthy"></span><span class="stats-item-label">健康</span><span class="stats-item-value healthy">{{ topologyStats.healthyNodes }}</span></div>
            <div class="stats-item"><span class="stats-dot warning"></span><span class="stats-item-label">警告</span><span class="stats-item-value warning">{{ topologyStats.warningNodes }}</span></div>
            <div class="stats-item"><span class="stats-dot error"></span><span class="stats-item-label">故障</span><span class="stats-item-value error">{{ topologyStats.errorNodes }}</span></div>
          </div>
          <div class="stats-highlight"><span class="stats-highlight-label">平均健康</span><span class="stats-highlight-value" :class="topologyStats.avgHealth >= 80 ? 'healthy' : topologyStats.avgHealth >= 60 ? 'warning' : 'error'">{{ topologyStats.avgHealth }}%</span></div>
        </div>
        <div class="stats-section">
          <div class="stats-section-title">链路 ({{ topologyStats.totalLinks }})</div>
          <div class="stats-items">
            <div class="stats-item"><span class="stats-line active"></span><span class="stats-item-label">主用</span><span class="stats-item-value">{{ topologyStats.mainLinks }}</span></div>
            <div class="stats-item"><span class="stats-line backup"></span><span class="stats-item-label">备用</span><span class="stats-item-value">{{ topologyStats.backupLinks }}</span></div>
            <div class="stats-item"><span class="stats-dot healthy"></span><span class="stats-item-label">正常</span><span class="stats-item-value">{{ topologyStats.activeLinks }}</span></div>
            <div class="stats-item"><span class="stats-dot warning"></span><span class="stats-item-label">警告</span><span class="stats-item-value warning">{{ topologyStats.warningLinks }}</span></div>
            <div class="stats-item"><span class="stats-dot error"></span><span class="stats-item-label">异常</span><span class="stats-item-value error">{{ topologyStats.errorLinks }}</span></div>
          </div>
          <div class="stats-highlight"><span class="stats-highlight-label">平均负载</span><span class="stats-highlight-value" :class="topologyStats.avgLoad < 60 ? 'healthy' : topologyStats.avgLoad < 80 ? 'warning' : 'error'">{{ topologyStats.avgLoad }}%</span></div>
        </div>
      </aside>

      <div ref="svgContainer" class="topology-canvas" v-loading="isLoading && !isMockData">
        <div v-if="isLoading && !isMockData" class="topo-skeleton">
          <div class="skeleton-node" style="top:20%;left:30%"></div>
          <div class="skeleton-node" style="top:50%;left:60%"></div>
          <div class="skeleton-node" style="top:70%;left:25%"></div>
          <div class="skeleton-node" style="top:35%;left:75%"></div>
          <div class="skeleton-line" style="top:35%;left:35%;width:25%;transform:rotate(15deg)"></div>
          <div class="skeleton-line" style="top:55%;left:45%;width:20%;transform:rotate(-20deg)"></div>
        </div>
        <svg v-show="!isLoading || isMockData" ref="svgCanvas" :viewBox="viewBox" class="svg-canvas" @click="handleBackgroundClick" @wheel.prevent="handleWheel" @mousedown="handleCanvasPanStart" @touchstart="handleTouchStart" @touchmove="handleTouchMove" @touchend="handleTouchEnd" @contextmenu.prevent="contextMenu.show = false">
          <defs>
            <linearGradient id="linkGradient" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="var(--color-primary)" /><stop offset="100%" stop-color="var(--color-primary-light)" /></linearGradient>
            <linearGradient id="mainLinkGradient" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="var(--color-success)" /><stop offset="100%" stop-color="var(--color-success-light)" /></linearGradient>
            <linearGradient id="centralNodeGradient" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="var(--color-purple)" /><stop offset="100%" stop-color="#9254DE" /></linearGradient>
            <filter id="glow"><feGaussianBlur stdDeviation="3" result="coloredBlur"/><feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
            <filter id="a2aGlow"><feGaussianBlur stdDeviation="4" result="coloredBlur"/><feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
            <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="var(--color-primary)" /></marker>
          </defs>
          <g :transform="transformString">
            <g class="a2a-flows" v-if="effectiveDisplayOptions.showA2A && currentA2AMessage"><path :d="getA2APath(currentA2AMessage.path)" fill="none" :stroke="getActionColor(currentA2AMessage.action)" stroke-width="3" stroke-dasharray="8, 4" class="a2a-flow-path" filter="url(#a2aGlow)" /></g>
            <g class="flows" v-if="effectiveDisplayOptions.showFlows"><path v-for="flow in topologyData.flows" :key="flow.id" :d="getFlowPath(flow.path)" fill="none" :stroke="flow.type === 'video' ? 'var(--color-warning)' : 'var(--color-primary)'" stroke-width="2" stroke-dasharray="10,5" class="flow-path" :class="flow.type" /></g>
            <g class="links">
              <g v-for="link in visibleLinks" :key="makeLinkKey(link.source, link.target)" class="link-group" :class="{ 'link-hidden': hiddenLinks.has(makeLinkKey(link.source, link.target)), 'restarting': restartingLinks.has(makeLinkKey(link.source, link.target)), 'draining': drainingLinks.has(makeLinkKey(link.source, link.target)), 'link-isolated': isolatedLinks.has(makeLinkKey(link.source, link.target)) }" @click.stop="handleLinkClick(link)" @contextmenu.stop="handleContextMenu($event, link, 'link')" style="cursor: pointer;">
                <line :x1="getNodeX(link.source)" :y1="getNodeY(link.source)" :x2="getNodeX(link.target)" :y2="getNodeY(link.target)" stroke="transparent" stroke-width="20" class="link-hitbox" />
                <line :x1="getNodeX(link.source)" :y1="getNodeY(link.source)" :x2="getNodeX(link.target)" :y2="getNodeY(link.target)" :class="['link', { warning: link.status === 'warning', error: link.status === 'error', main: link.main, isCentralLink: link.isCentralLink }]" :stroke="getLinkLoadColor(link.currentLoad)" :stroke-width="getLinkWidth(link)" marker-end="url(#arrowhead)" />
                <text v-if="effectiveDisplayOptions.showBandwidth" :transform="getLinkLabelTransform(link)" text-anchor="middle" dy="-6" fill="var(--color-text-tertiary)" font-size="11" class="link-label">{{ link.bandwidth }} ({{ Math.round(link.currentLoad) }}%)</text>
                <text v-if="effectiveDisplayOptions.showBandwidth && linkLatencies.has(makeLinkKey(link.source, link.target))" :transform="getLinkLabelTransform(link)" text-anchor="middle" dy="12" :fill="getLatencyColor(linkLatencies.get(makeLinkKey(link.source, link.target)) || 0)" font-size="9" class="link-label">{{ Math.round(linkLatencies.get(makeLinkKey(link.source, link.target)) || 0) }}ms</text>
              </g>
              <g class="link-particles" v-if="effectiveDisplayOptions.showFlows"><circle v-for="particle in linkParticles" :key="particle.id" :cx="getParticlePosition(particle.linkKey, particle.progress).x" :cy="getParticlePosition(particle.linkKey, particle.progress).y" r="3" :fill="particle.color" class="flow-particle" opacity="0.8" /></g>
            </g>
            <g class="central-node" :transform="'scale(' + displayOptions.nodeSize + ')'" :class="[{ selected: selectedNode === 'central', dragging: dragNode?.id === 'central', 'animating-isolate': animatingNodes.has('central') && centralNode.locked, 'animating-unisolate': animatingNodes.has('central') && !centralNode.locked, 'restarting': restartingNodes.has('central'), 'hidden': hiddenNodes.has('central') }]" @click.stop="handleNodeClick(centralNode)" @contextmenu.stop="handleContextMenu($event, centralNode, 'node')" @mousedown.stop="handleDragStart($event, centralNode)" @touchstart.stop="handleDragStart($event, centralNode)" @mouseenter="handleNodeHover(centralNode, $event)" @mouseleave="handleNodeLeave()" style="cursor: pointer; transform-origin: center;">
              <circle :cx="centralNode.x" :cy="centralNode.y" r="50" fill="transparent" stroke="transparent" class="click-area" />
              <circle :cx="centralNode.x" :cy="centralNode.y" r="40" fill="none" :stroke="getNodeStatusColor(centralNode.status)" stroke-width="2" :class="['status-ring', centralNode.status]" />
              <circle v-if="centralNode.locked" :cx="centralNode.x" :cy="centralNode.y" r="45" fill="none" stroke="#FF4D4F" stroke-width="2" stroke-dasharray="4,4" class="lock-ring" />
              <circle :cx="centralNode.x" :cy="centralNode.y" r="35" fill="url(#centralNodeGradient)" filter="url(#glow)" />
              <circle :cx="centralNode.x" :cy="centralNode.y" r="28" fill="#1E293B" />
              <g v-if="effectiveDisplayOptions.showHealth"><circle :cx="centralNode.x + 25" :cy="centralNode.y - 25" r="8" :fill="getNodeStatusColor(centralNode.status)" class="status-indicator" /><text :x="centralNode.x + 25" :y="centralNode.y - 25" text-anchor="middle" dominant-baseline="middle" fill="white" font-size="10" font-weight="600">{{ centralNode.status === 'healthy' ? '✓' : centralNode.status === 'warning' ? '!' : '✗' }}</text></g>
              <svg :x="centralNode.x - 12" :y="centralNode.y - 18" width="24" height="24" :viewBox="getNodeIcon('core').viewBox" class="node-type-icon"><path :d="getNodeIcon('core').path" fill="#D3ADF7" opacity="0.9"/></svg>
              <text :x="centralNode.x" :y="centralNode.y + 8" text-anchor="middle" fill="white" font-size="11" font-weight="600">中心控制</text>
              <text :x="centralNode.x" :y="centralNode.y + 20" text-anchor="middle" fill="#D3ADF7" font-size="9">Central Agent</text>
            </g>
            <g class="nodes">
              <g v-for="node in visibleNodes" :key="node.id" :class="['node-group', { selected: selectedNode === node.id, locked: node.locked, dragging: dragNode?.id === node.id, 'animating-isolate': animatingNodes.has(node.id) && node.locked, 'animating-unisolate': animatingNodes.has(node.id) && !node.locked, 'restarting': restartingNodes.has(node.id), 'hidden': hiddenNodes.has(node.id) }]" :transform="'scale(' + displayOptions.nodeSize + ')'" @click.stop="handleNodeClick(node)" @contextmenu.stop="handleContextMenu($event, node, 'node')" @mousedown.stop="handleDragStart($event, node)" @touchstart.stop="handleDragStart($event, node)" @mouseenter="handleNodeHover(node, $event)" @mouseleave="handleNodeLeave()" style="cursor: pointer; transform-origin: center;">
                <circle :cx="node.x" :cy="node.y" r="50" fill="transparent" stroke="transparent" class="click-area" />
                <circle :cx="node.x" :cy="node.y" r="35" fill="none" :stroke="getNodeStatusColor(node.status)" stroke-width="2" :class="['status-ring', node.status]" />
                <circle v-if="node.locked" :cx="node.x" :cy="node.y" r="42" fill="none" stroke="#FF4D4F" stroke-width="2" stroke-dasharray="4,4" class="lock-ring" />
                <circle :cx="node.x" :cy="node.y" r="30" :fill="getNodeStatusColor(node.status)" class="node-circle" />
                <circle :cx="node.x" :cy="node.y" r="25" fill="#1E293B" class="node-inner" />
                <g v-if="effectiveDisplayOptions.showHealth && lodLevel !== 'low'" class="resource-rings"><circle :cx="node.x" :cy="node.y" r="22" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="2" /><path v-if="node.cpu !== null" :d="getResourceRingPath(node.x, node.y, 22, node.cpu)" fill="none" :stroke="getResourceColor(node.cpu)" stroke-width="2" stroke-linecap="round" class="cpu-ring" /><circle :cx="node.x" :cy="node.y" r="18" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="2" /><path v-if="node.memory !== null" :d="getResourceRingPath(node.x, node.y, 18, node.memory)" fill="none" :stroke="getResourceColor(node.memory)" stroke-width="2" stroke-linecap="round" class="memory-ring" /></g>
                <svg :x="node.x - 10" :y="node.y - 10" width="20" height="20" :viewBox="getNodeIcon(node.type).viewBox" class="node-type-icon"><path :d="getNodeIcon(node.type).path" fill="white" opacity="0.9"/></svg>
                <text v-if="effectiveDisplayOptions.showLabels" :x="node.x" :y="node.y + 52" text-anchor="middle" fill="var(--color-text-secondary)" font-size="10" class="node-label">{{ (node.name || node.id || '').split(' ')[0] }}</text>
                <text v-if="effectiveDisplayOptions.showHealth" :x="node.x" :y="node.y - 40" text-anchor="middle" :fill="getNodeStatusColor(node.status)" font-size="10" font-weight="600">{{ node.status === 'healthy' ? '✓' : node.status === 'warning' ? '!' : '✗' }}</text>
              </g>
            </g>
          </g>
        </svg>
        <div v-if="hoveredNode" class="node-tooltip" :style="{ left: tooltipPosition.x + 'px', top: tooltipPosition.y + 'px' }"><div class="tooltip-header"><span class="tooltip-status-dot" :style="{ background: getNodeStatusColor(hoveredNode.status) }"></span><span class="tooltip-name">{{ hoveredNode.name }}</span></div><div class="tooltip-body"><div class="tooltip-row"><span>类型</span><span>{{ hoveredNode.type === 'router' ? '路由器' : hoveredNode.type === 'central' ? '中心控制' : hoveredNode.type === 'firewall' ? '防火墙' : hoveredNode.type === 'server' ? '服务器' : '交换机' }}</span></div><div class="tooltip-row"><span>健康</span><span :style="{ color: getNodeStatusColor(hoveredNode.status) }">{{ hoveredNode.health !== null ? hoveredNode.health + '%' : '--' }}</span></div><div class="tooltip-row"><span>CPU</span><span>{{ hoveredNode.cpu !== null ? hoveredNode.cpu + '%' : '--' }}</span></div><div class="tooltip-row"><span>内存</span><span>{{ hoveredNode.memory !== null ? hoveredNode.memory + '%' : '--' }}</span></div><div class="tooltip-row"><span>流量</span><span>{{ hoveredNode.traffic ?? '--' }}</span></div></div></div>
        <div v-if="showMinimap" class="minimap"><div class="minimap-header"><span>缩略图</span><button type="button" class="minimap-close" @click="showMinimap = false" aria-label="关闭缩略图">✕</button></div><svg class="minimap-svg" :viewBox="minimapViewBox"><g :transform="transformString"><line v-for="link in topologyData.links" :key="'mm-'+link.source+'-'+link.target" :x1="getNodeX(link.source)" :y1="getNodeY(link.source)" :x2="getNodeX(link.target)" :y2="getNodeY(link.target)" :stroke="getLinkLoadColor(link.currentLoad)" stroke-width="1" opacity="0.5" /><circle v-for="node in topologyData.nodes" :key="'mm-'+node.id" :cx="node.x" :cy="node.y" r="4" :fill="getNodeStatusColor(node.status)" /><circle :cx="centralNode.x" :cy="centralNode.y" r="5" fill="var(--color-purple)" /></g></svg></div>
      </div>

      <Transition name="detail-slide">
        <aside v-if="detailPanelOpen" class="detail-panel">
          <div class="detail-panel-header">
            <h3 class="detail-panel-title">{{ nodeDetails ? '节点详情' : (linkDetails ? '链路详情' : '详情') }}</h3>
            <button type="button" class="detail-close-btn" @click="detailPanelOpen = false" aria-label="关闭详情面板">✕</button>
          </div>
          <div class="detail-panel-body">
            <div v-if="nodeDetails" class="node-info">
              <div class="info-header"><div class="info-icon" :style="{ background: getNodeStatusColor(nodeDetails.status) }">{{ nodeDetails.type === 'router' ? 'R' : 'S' }}</div><div class="info-title"><h3>{{ nodeDetails.name }}</h3><span class="info-type">{{ nodeDetails.type === 'router' ? '路由器' : '交换机' }}</span><span v-if="nodeDetails.locked" class="locked-badge">已隔离</span><span :class="['status-badge', nodeDetails.status]">{{ nodeDetails.status === 'healthy' ? '健康' : nodeDetails.status === 'warning' ? '警告' : '异常' }}</span></div></div>
              <div class="info-stats"><div class="stat-row"><span class="stat-label">健康状态</span><div class="stat-value-row"><div class="health-bar-container"><div class="health-bar" :style="{ width: `${nodeDetails.health ?? 0}%`, background: getNodeStatusColor(nodeDetails.status) }"></div></div><span :style="{ color: getNodeStatusColor(nodeDetails.status) }">{{ nodeDetails.health !== null ? Math.round(nodeDetails.health) + '%' : '--' }}</span></div></div><div class="stat-row"><span class="stat-label">CPU 使用率</span><div class="stat-value-row"><div class="health-bar-container"><div class="health-bar cpu-bar" :style="{ width: `${nodeDetails.cpu ?? 0}%` }"></div></div><span class="stat-value">{{ nodeDetails.cpu !== null ? Math.round(nodeDetails.cpu) + '%' : '--' }}</span></div></div><div class="stat-row"><span class="stat-label">内存使用率</span><div class="stat-value-row"><div class="health-bar-container"><div class="health-bar memory-bar" :style="{ width: `${nodeDetails.memory ?? 0}%` }"></div></div><span class="stat-value">{{ nodeDetails.memory !== null ? Math.round(nodeDetails.memory) + '%' : '--' }}</span></div></div><div class="stat-row"><span class="stat-label">实时流量</span><span class="stat-value">{{ nodeDetails.traffic ?? '--' }}</span></div><div class="stat-row"><span class="stat-label">设备类型</span><span class="stat-value">{{ nodeDetails.type === 'router' ? '核心路由器' : '交换机' }}</span></div><div class="stat-row"><span class="stat-label">设备ID</span><span class="stat-value">{{ nodeDetails.id }}</span></div><div class="stat-row"><span class="stat-label">配置状态</span><span :class="['stat-value', { locked: nodeDetails.locked }]">{{ nodeDetails.locked ? '🔒 已锁定' : '✅ 正常' }}</span></div></div>
              <div class="info-actions"><button type="button" class="action-btn primary" @click="showConfigModal = true" aria-label="查看配置">查看配置</button><button type="button" v-if="canWrite" class="action-btn secondary" @click="showDiagnoseModal = true" aria-label="执行诊断">执行诊断</button><button type="button" v-if="canWrite && nodeDetails.locked" class="action-btn success" @click="handleMenuAction('isolate')" aria-label="解除隔离">解除隔离</button></div>
            </div>
            <div v-else-if="linkDetails" class="link-info">
              <div class="info-header"><div class="info-icon link-icon">🔗</div><div class="info-title"><h3>{{ linkDetails.source }} → {{ linkDetails.target }}</h3><span class="info-type">{{ linkDetails.main ? '主用链路' : '备用链路' }}</span><span :class="['status-badge', linkDetails.status]">{{ linkDetails.status === 'active' ? '正常' : linkDetails.status === 'warning' ? '警告' : '异常' }}</span></div></div>
              <div class="info-stats"><div class="stat-row"><span class="stat-label">带宽</span><span class="stat-value">{{ linkDetails.bandwidth }}</span></div><div class="stat-row"><span class="stat-label">当前负载</span><div class="stat-value-row"><div class="health-bar-container"><div class="health-bar" :style="{ width: `${linkDetails.currentLoad}%`, background: getLinkLoadColor(linkDetails.currentLoad) }"></div></div><span :style="{ color: getLinkLoadColor(linkDetails.currentLoad) }">{{ Math.round(linkDetails.currentLoad) }}%</span></div></div><div class="stat-row"><span class="stat-label">状态</span><span :class="['stat-value', linkDetails.status]">{{ linkDetails.status === 'active' ? '✅ 正常' : linkDetails.status === 'warning' ? '⚠️ 告警' : '🚨 异常' }}</span></div><div class="stat-row"><span class="stat-label">角色</span><span :class="['stat-value', { main: linkDetails.main }]">{{ linkDetails.main ? '⭐ 主用' : '备用' }}</span></div></div>
              <div class="info-actions"><button type="button" v-if="canWrite && !linkDetails.main" class="action-btn primary" @click="handleMenuAction('makePrimary')" aria-label="设为主用">设为主用</button><button type="button" v-if="canWrite" class="action-btn secondary" @click="showQoSModal = true" aria-label="QoS限速">QoS限速</button></div>
            </div>
            <div v-else class="empty-state"><span class="empty-icon">👆</span><p>点击节点或链路查看详情</p><p class="hint">右键点击可显示操作菜单</p></div>
          </div>
          <div v-if="showA2APanel && currentA2AMessage" class="a2a-section">
            <div class="a2a-section-header" @click="payloadExpanded = !payloadExpanded"><span>📡 A2A 报文<span class="sim-badge">模拟</span></span><span class="a2a-expand-icon">{{ payloadExpanded ? '▼' : '▶' }}</span></div>
            <div class="a2a-section-body">
              <div class="a2a-message-info"><div class="info-row"><span class="info-label">发送方</span><span class="info-value sender">{{ currentA2AMessage.sender }}</span></div><div class="info-row"><span class="info-label">接收方</span><span class="info-value receiver">{{ currentA2AMessage.receiver }}</span></div><div class="info-row"><span class="info-label">操作</span><span class="info-value action" :style="{ color: getActionColor(currentA2AMessage.action) }">{{ currentA2AMessage.action }}</span></div><div class="info-row"><span class="info-label">时间</span><span class="info-value">{{ currentA2AMessage.timestamp }}</span></div></div>
              <Transition name="payload-expand">
                <div v-if="payloadExpanded" class="a2a-payload"><div class="payload-label">Payload</div><pre class="payload-content">{{ JSON.stringify(currentA2AMessage.payload, null, 2) }}</pre></div>
              </Transition>
            </div>
          </div>
        </aside>
      </Transition>
    </div>
    <div v-if="alerts.length" class="alert-bar"><div v-for="alert in alerts.filter(a => !a.dismissed).slice(0, 5)" :key="alert.id" :class="['alert-item', alert.type]"><span class="alert-icon">{{ alert.type === 'error' ? '🚨' : alert.type === 'warning' ? '⚠️' : 'ℹ️' }}</span><span class="alert-msg">{{ alert.message }}</span><button type="button" class="alert-dismiss" @click="dismissAlert(alert.id)" aria-label="关闭告警">✕</button></div><button type="button" v-if="alerts.filter(a => !a.dismissed).length > 0" class="alert-clear" @click="clearAllAlerts" aria-label="清除全部告警">清除全部</button></div>
    <div v-if="showDisplayOptions" class="display-options-panel"><div class="display-options-header"><span>显示选项</span><button type="button" class="close-btn" @click="showDisplayOptions = false" aria-label="关闭">✕</button></div><div class="display-options-body"><label class="option-item"><input type="checkbox" v-model="displayOptions.showLabels" /> 节点标签</label><label class="option-item"><input type="checkbox" v-model="displayOptions.showBandwidth" /> 链路带宽</label><label class="option-item"><input type="checkbox" v-model="displayOptions.showHealth" /> 健康状态</label><label class="option-item"><input type="checkbox" v-model="displayOptions.showFlows" /> 流量路径</label><label class="option-item"><input type="checkbox" v-model="displayOptions.showA2A" /> A2A飞线</label><div class="option-item"><span>节点大小</span><input type="range" v-model.number="displayOptions.nodeSize" min="0.5" max="2" step="0.1" /><span>{{ (displayOptions.nodeSize * 100).toFixed(0) }}%</span></div></div></div>
    <Teleport to="body"><div v-if="contextMenu.show" class="context-menu" :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"><div class="menu-header"><span class="menu-title">{{ contextMenu.type === 'node' && isTopologyNode(contextMenu.target) ? contextMenu.target.name : isTopologyLink(contextMenu.target) ? makeLinkKey(contextMenu.target.source, contextMenu.target.target) : '' }}</span></div><div class="menu-items"><button type="button" v-for="item in (contextMenu.type === 'node' ? nodeMenuItems : linkMenuItems)" :key="item.id" :class="['menu-item', { danger: item.danger }]" @click="handleMenuAction(item.id)" :aria-label="item.label"><span class="menu-icon">{{ item.icon }}</span><span class="menu-label">{{ item.label }}</span></button></div></div></Teleport>
    <Teleport to="body"><div v-if="showConfigModal" class="modal-overlay" @click.self="showConfigModal = false"><div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="config-modal-title"><div class="modal-header"><h3 id="config-modal-title">设备配置</h3><button type="button" class="close-btn" @click="showConfigModal = false" aria-label="关闭">✕</button></div><div class="modal-body"><pre>{{ JSON.stringify(nodeDetails, null, 2) }}</pre></div></div></div></Teleport>
    <Teleport to="body"><div v-if="showDiagnoseModal" class="modal-overlay" @click.self="showDiagnoseModal = false"><div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="diagnose-modal-title"><div class="modal-header"><h3 id="diagnose-modal-title">诊断结果</h3><button type="button" class="close-btn" @click="showDiagnoseModal = false" aria-label="关闭">✕</button></div><div class="modal-body"><div class="diagnose-result"><div class="result-item"><span class="result-label">设备名称：</span><span class="result-value">{{ nodeDetails?.name }}</span></div><div class="result-item"><span class="result-label">诊断状态：</span><span class="result-value success">✓ 正常</span></div><div class="result-item"><span class="result-label">CPU使用率：</span><span class="result-value">{{ (nodeDetails?.cpu ?? '--') }}%</span></div><div class="result-item"><span class="result-label">内存使用率：</span><span class="result-value">{{ (nodeDetails?.memory ?? '--') }}%</span></div><div class="result-item"><span class="result-label">接口状态：</span><span class="result-value">全部正常</span></div></div></div></div></div></Teleport>
    <Teleport to="body"><div v-if="showSSHModal" class="modal-overlay" @click.self="showSSHModal = false"><div class="modal-content large" role="dialog" aria-modal="true" aria-labelledby="ssh-modal-title"><div class="modal-header"><h3 id="ssh-modal-title">Web SSH 终端</h3><button type="button" class="close-btn" @click="showSSHModal = false" aria-label="关闭">✕</button></div><div class="modal-body"><div class="ssh-terminal"><div class="terminal-header"><span class="terminal-title">{{ sshCommand }}</span></div><div class="terminal-body"><div class="terminal-line"><span class="terminal-prompt">$</span><input type="text" class="terminal-input" placeholder="输入命令..." aria-label="SSH命令输入" /></div><div class="terminal-output"><p><span class="success">Connected to {{ nodeDetails?.name }}</span></p><p>Welcome to NetOps Shell v1.0</p><p>Type 'help' for available commands</p></div></div></div></div></div></div></Teleport>
    <Teleport to="body"><div v-if="showQoSModal" class="modal-overlay" @click.self="showQoSModal = false"><div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="qos-modal-title"><div class="modal-header"><h3 id="qos-modal-title">QoS 限速配置</h3><button type="button" class="close-btn" @click="showQoSModal = false" aria-label="关闭">✕</button></div><div class="modal-body"><div class="form-group"><label>目标带宽</label><div class="bandwidth-input-group"><input v-model="qosBandwidth" type="text" class="form-input" placeholder="例如: 100M" aria-label="目标带宽" /><select class="form-select" aria-label="带宽单位"><option value="kbps">kbps</option><option value="Mbps">Mbps</option><option value="Gbps">Gbps</option></select></div></div><div class="form-group"><label>优先级</label><select v-model="qosPriority" class="form-select" aria-label="优先级"><option value="high">高优先级</option><option value="medium">中优先级</option><option value="low">低优先级</option></select></div><div class="modal-actions"><button type="button" class="modal-btn cancel" @click="showQoSModal = false" aria-label="取消">取消</button><button type="button" class="modal-btn confirm" @click="handleExecuteQoS" :disabled="isExecutingQoS" aria-label="执行配置">{{ isExecutingQoS ? '执行中...' : '执行配置' }}</button></div></div></div></div></Teleport>
    <Teleport to="body"><div v-if="showCopilotModal" class="modal-overlay" @click.self="showCopilotModal = false"><div class="modal-content" style="max-width: 500px;" role="dialog" aria-modal="true" aria-labelledby="copilot-modal-title"><div class="modal-header"><h3 id="copilot-modal-title">🤖 智能副驾</h3><button type="button" class="close-btn" @click="showCopilotModal = false" aria-label="关闭">✕</button></div><div class="modal-body"><div style="margin-bottom: 16px; color: var(--color-text-tertiary); font-size: 13px;">针对设备 <strong style="color: var(--color-primary);">{{ isTopologyNode(copilotTarget) ? copilotTarget.name || copilotTarget.id : '' }}</strong> 发起运维意图</div><div class="form-group"><label>描述您的运维需求</label><textarea v-model="copilotInput" class="form-input" style="min-height: 80px; resize: vertical;" placeholder="例如: 保障该设备上行带宽至少200M" @keydown.ctrl.enter="submitCopilotIntent" aria-label="运维需求描述"></textarea><div style="font-size: 11px; color: var(--color-text-tertiary); margin-top: 4px;">按 Ctrl+Enter 快速提交</div></div><div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px;"><button type="button" class="quick-intent-btn" @click="copilotInput = '保障该设备带宽至少500M'" aria-label="带宽保障">带宽保障</button><button type="button" class="quick-intent-btn" @click="copilotInput = '诊断该设备的连通性问题'" aria-label="故障诊断">故障诊断</button><button type="button" class="quick-intent-btn" @click="copilotInput = '查看该设备的实时性能指标'" aria-label="性能监控">性能监控</button></div><div class="modal-actions"><button type="button" class="modal-btn cancel" @click="showCopilotModal = false" aria-label="取消">取消</button><button type="button" class="modal-btn confirm" @click="submitCopilotIntent" :disabled="!copilotInput.trim()" aria-label="发起意图">发起意图</button></div></div></div></div></Teleport>
    <Teleport to="body"><div v-if="showDangerConfirm" class="modal-overlay" @click.self="showDangerConfirm = false" role="dialog" aria-modal="true"><div class="modal-content" style="max-width: 420px;"><div class="modal-header"><h3>⚠️ 确认操作</h3><button type="button" class="close-btn" @click="showDangerConfirm = false" aria-label="关闭">✕</button></div><div class="modal-body"><p style="color: var(--color-text-secondary); line-height: 1.6; margin: 0;">{{ dangerConfirmAction === 'isolate_node' ? '确认要隔离该节点吗？隔离后该节点将无法与其他节点通信。' : '确认要紧急重启该设备吗？此操作将导致设备短暂不可用。' }}</p></div><div class="modal-actions"><button type="button" class="modal-btn cancel" @click="showDangerConfirm = false" aria-label="取消">取消</button><button type="button" class="modal-btn confirm" style="background: #EF4444;" @click="confirmDangerAction" aria-label="确认">确认</button></div></div></div></Teleport>
  </div>
</template>

<style scoped>
.topology-container { position: relative; animation: page-enter 0.5s ease-out; min-height: 100vh; }
.topo-bg { position: fixed; top: 0; left: 0; right: 0; bottom: 0; pointer-events: none; z-index: 0; overflow: hidden; }
.bg-grid { position: absolute; top: 0; right: 0; bottom: 0; left: 0; background-image: linear-gradient(var(--color-primary-bg) 1px, transparent 1px), linear-gradient(90deg, var(--color-primary-bg) 1px, transparent 1px); background-size: 60px 60px; -webkit-mask-image: radial-gradient(ellipse 80% 60% at 50% 30%, black 20%, transparent 70%); mask-image: radial-gradient(ellipse 80% 60% at 50% 30%, black 20%, transparent 70%); }
.bg-glow { position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.4; }
.glow-1 { width: 400px; height: 400px; background: var(--color-primary-glow); top: -100px; right: 10%; animation: glow-float 12s ease-in-out infinite; }
.glow-2 { width: 300px; height: 300px; background: var(--color-purple-glow); bottom: 10%; left: 5%; animation: glow-float 15s ease-in-out infinite reverse; }

.topology-container > *:not(.topo-bg) { position: relative; z-index: var(--z-content); }
.topo-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; padding-bottom: var(--spacing-md); border-bottom: 1px solid var(--color-border-primary); }
.header-left { display: flex; flex-direction: column; gap: var(--spacing-xs); }
.page-title { font-size: var(--font-size-2xl); font-weight: 700; margin: 0; background: linear-gradient(135deg, var(--color-text-secondary) 0%, var(--color-primary-light) 50%, var(--color-text-secondary) 100%); background-size: 200% auto; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: title-shimmer 4s ease-in-out infinite; }
.page-subtitle { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin: 0; font-weight: 400; }

.header-actions { display: flex; align-items: center; gap: 0.75rem; }
.data-freshness { font-size: var(--font-size-xs); padding: var(--spacing-xs) 10px; border-radius: var(--radius-lg); background: var(--color-success-bg); color: var(--color-success); transition: all 0.3s var(--ease-out); border: 1px solid var(--color-success-border); display: flex; align-items: center; gap: 0.375rem; }
.freshness-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; animation: freshness-pulse 2s ease-in-out infinite; }

.data-freshness.degraded { background: var(--color-warning-bg); color: var(--color-warning); border-color: var(--color-warning-border); }
.last-refresh { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.action-btn { padding: 8px 16px; background: var(--color-primary-bg); color: var(--color-primary-light); border: 1px solid var(--color-primary-border); border-radius: var(--radius-lg); cursor: pointer; font-size: var(--font-size-sm); transition: all 0.25s ease; display: flex; align-items: center; gap: 0.375rem; white-space: nowrap; backdrop-filter: blur(8px); min-height: 44px; }
.action-btn:hover:not(:disabled) { background: var(--color-primary-hover); border-color: var(--color-primary-border); box-shadow: var(--shadow-glow-primary); color: var(--color-primary-lighter); transform: scale(1.02); }
.action-btn:active:not(:disabled) { transform: scale(0.97); }
.action-btn:disabled { opacity: 0.35; cursor: not-allowed; transform: none; box-shadow: none; }
.action-btn.primary { flex: 1; height: 36px; padding: 0 16px; background: var(--gradient-primary); color: var(--color-primary-light); border: 1px solid var(--color-primary-border); border-radius: var(--radius-lg); font-size: var(--font-size-base); font-weight: 500; justify-content: center; backdrop-filter: blur(8px); transition: all 0.25s ease; }
.action-btn.primary:hover { transform: translateY(-1px) scale(1.03); box-shadow: var(--shadow-glow-primary); background: var(--gradient-primary-hover); border-color: var(--color-primary-border); color: var(--color-primary-lighter); }
.action-btn.primary:active { transform: scale(0.97); }
.action-btn.secondary { flex: 1; height: 36px; padding: 0 16px; background: var(--color-bg-glass); color: var(--color-text-secondary); border: 1px solid var(--color-border-secondary); border-radius: var(--radius-lg); font-size: var(--font-size-base); font-weight: 500; justify-content: center; backdrop-filter: blur(8px); transition: all 0.25s ease; }
.action-btn.secondary:hover { background: var(--color-bg-glass-strong); border-color: var(--color-border-secondary); box-shadow: var(--shadow-card); transform: scale(1.02); }
.action-btn.secondary:active { transform: scale(0.97); }
.action-btn.success { flex: 1; height: 36px; padding: 0 16px; background: var(--gradient-success); color: var(--color-text-primary); border: none; border-radius: var(--radius-lg); font-size: var(--font-size-base); font-weight: 500; justify-content: center; backdrop-filter: blur(8px); transition: all 0.25s ease; }
.action-btn.success:hover { transform: translateY(-1px) scale(1.02); box-shadow: var(--shadow-glow-success); }
.action-btn.success:active { transform: scale(0.97); }
.metrics-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--spacing-md); margin-bottom: var(--spacing-md); }
.metric-card { background: var(--gradient-glass); border-radius: var(--card-border-radius); padding: var(--spacing-md) 1.25rem; display: flex; align-items: center; gap: 14px; border: var(--card-border); -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); animation: card-enter 0.4s var(--ease-out) backwards; animation-delay: var(--delay, 0s); position: relative; overflow: hidden; will-change: transform, opacity; }
.metric-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, var(--accent), transparent); opacity: 0; transition: opacity 0.35s ease; }
.metric-card:hover::before { opacity: 1; }
.metric-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-card-hover); }

.skeleton { animation: skeleton-pulse 1.5s ease-in-out infinite; }
.skeleton-line { height: 14px; background: var(--gradient-shimmer); background-size: 200% 100%; border-radius: var(--radius-sm); margin-bottom: var(--spacing-sm); animation: skeleton-slide 1.5s ease-in-out infinite; }

.skeleton-line.wide { width: 70%; }
.skeleton-line.narrow { width: 40%; }
.metric-icon { width: 44px; height: 44px; border-radius: var(--radius-lg); display: flex; align-items: center; justify-content: center; font-size: var(--font-size-xl); flex-shrink: 0; }
.metric-content { flex: 1; }
.metric-value { font-size: var(--font-size-2xl); font-weight: 700; color: var(--color-text-primary); line-height: 1.2; font-variant-numeric: tabular-nums; }
.metric-unit { font-size: var(--font-size-sm); font-weight: 400; color: var(--color-text-tertiary); margin-left: 2px; }
.metric-label { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-top: 2px; }
.metric-bottom-bar { position: absolute; bottom: 0; left: 0; right: 0; height: 3px; background: var(--color-bg-glass); }
.metric-bottom-fill { height: 100%; border-radius: var(--radius-xs); transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1); }
.toolbar-panel { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; margin-bottom: var(--spacing-md); padding: 0.75rem 18px; background: var(--color-bg-glass-strong); -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); border-radius: var(--radius-lg); border: var(--card-border); }
.toolbar-group { display: flex; align-items: center; gap: 0.375rem; }
.toolbar-btn { padding: 8px 14px; background: var(--color-primary-bg); border: 1px solid var(--color-primary-border); border-radius: var(--radius-lg); color: var(--color-primary-light); font-size: var(--font-size-xs); cursor: pointer; transition: all 0.25s ease; white-space: nowrap; min-height: 44px; min-width: 44px; display: inline-flex; align-items: center; justify-content: center; backdrop-filter: blur(8px); }
.toolbar-btn:hover { background: var(--color-primary-hover); border-color: var(--color-primary-border); color: var(--color-primary-lighter); box-shadow: var(--shadow-glow-primary); transform: scale(1.02); }
.toolbar-btn:active { transform: scale(0.97); box-shadow: none; }
.toolbar-btn.active { background: var(--color-primary-hover); border-color: var(--color-primary-border); color: var(--color-primary-lighter); box-shadow: var(--shadow-glow-primary); }
.zoom-level { font-size: 0.6875rem; color: var(--color-text-tertiary); min-width: 36px; text-align: center; }
.lod-indicator { font-size: 0.6875rem; color: var(--color-warning); padding: 2px var(--spacing-sm); background: var(--color-warning-bg); border-radius: var(--radius-sm); border: 1px solid var(--color-warning-border); }
.layout-select { padding: 0.375rem 10px; background: var(--color-bg-hover); border: 1px solid var(--color-border-primary); border-radius: var(--radius-sm); color: var(--color-text-secondary); font-size: var(--font-size-base); cursor: pointer; }
.layout-select option { background: var(--color-bg-secondary); color: var(--color-text-secondary); }
.search-input { padding: 0.375rem 10px; background: var(--input-bg); border: 1px solid var(--input-border); border-radius: var(--radius-sm); color: var(--color-text-primary); font-size: var(--font-size-base); width: 140px; }
.search-input:focus { outline: none; border-color: var(--input-border-focus); box-shadow: var(--input-shadow-focus); }
.search-count { font-size: 0.6875rem; color: var(--color-text-tertiary); }
.import-btn { padding: 8px 16px; background: var(--color-warning-bg); color: var(--color-warning-light); border: 1px solid var(--color-warning-border); border-radius: var(--radius-lg); cursor: pointer; font-size: var(--font-size-xs); transition: all 0.25s ease; display: inline-flex; align-items: center; gap: 0.375rem; min-height: 44px; backdrop-filter: blur(8px); }
.import-btn:hover { background: var(--color-warning-hover); border-color: var(--color-warning-border); color: var(--color-warning-light); box-shadow: var(--shadow-glow-warning); transform: scale(1.02); }
.import-btn:active { transform: scale(0.97); }
.topology-layout { display: grid; grid-template-columns: 220px 1fr 320px; gap: var(--panel-gap); }
.stats-panel { background: var(--gradient-glass-strong); border-radius: var(--radius-lg); padding: 1.25rem; border: var(--card-border); -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); overflow-y: auto; position: sticky; top: 80px; max-height: calc(100vh - 100px); transition: all 0.3s var(--ease-out); }
.stats-panel.floating { position: fixed; left: 280px; top: 80px; z-index: var(--z-sticky); box-shadow: var(--shadow-card-hover); }
.stats-panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-md); padding-bottom: 0.75rem; border-bottom: 1px solid var(--color-border-primary); }
.stats-panel-title { font-size: var(--font-size-md); font-weight: 700; color: var(--color-text-primary); margin: 0; }
.stats-pin-btn { width: 32px; height: 32px; background: var(--color-bg-hover); border: 1px solid var(--color-border-primary); border-radius: var(--radius-md); cursor: pointer; font-size: var(--font-size-base); display: flex; align-items: center; justify-content: center; transition: var(--button-transition); }
.stats-pin-btn:hover { background: var(--color-bg-active); }
.stats-section { margin-bottom: var(--spacing-md); padding: 10px; background: var(--color-bg-input); border-radius: var(--radius-md); border: 1px solid var(--color-border-primary); }
.stats-section-title { font-size: var(--font-size-sm); font-weight: 600; color: var(--color-text-secondary); margin-bottom: 10px; }
.stats-items { display: flex; flex-direction: column; gap: 0.375rem; }
.stats-item { display: flex; align-items: center; gap: var(--spacing-sm); font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.stats-item-label { flex: 1; }
.stats-item-value { font-weight: 600; font-size: var(--font-size-md); color: var(--color-text-secondary); }
.stats-item-value.healthy { color: var(--color-success); }
.stats-item-value.warning { color: var(--color-warning); }
.stats-item-value.error { color: var(--color-error); }
.stats-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.stats-dot.healthy { background: var(--color-success); box-shadow: var(--shadow-glow-success-sm); }
.stats-dot.warning { background: var(--color-warning); box-shadow: var(--shadow-glow-warning-sm); }
.stats-dot.error { background: var(--color-error); box-shadow: var(--shadow-glow-error-sm); }
.stats-line { width: 16px; height: 3px; border-radius: var(--radius-xs); flex-shrink: 0; }
.stats-line.active { background: linear-gradient(90deg, var(--color-success), var(--color-success-light)); }
.stats-line.backup { background: linear-gradient(90deg, var(--color-primary), var(--color-primary-light)); }
.stats-highlight { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--color-border-primary); }
.stats-highlight-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.stats-highlight-value { font-size: var(--font-size-xl); font-weight: 800; letter-spacing: -0.5px; }
.stats-highlight-value.healthy { color: var(--color-success); text-shadow: var(--shadow-glow-success); }
.stats-highlight-value.warning { color: var(--color-warning); text-shadow: var(--shadow-glow-warning); }
.stats-highlight-value.error { color: var(--color-error); text-shadow: var(--shadow-glow-error); }
.topology-canvas { background: var(--gradient-glass); border-radius: var(--radius-lg); padding: var(--content-padding); border: var(--card-border); position: relative; overflow: hidden; -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); }

.error-banner { display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem 1.25rem; background: var(--color-error-bg); border: 1px solid var(--color-error-border); border-radius: var(--radius-lg); margin-bottom: 1.25rem; animation: banner-enter 0.3s var(--ease-out); will-change: transform, opacity; }

.error-banner-icon { font-size: var(--font-size-lg); flex-shrink: 0; }
.error-banner-text { flex: 1; font-size: var(--font-size-sm); color: var(--color-error-light); }
.error-banner-retry { padding: 0.375rem 0.875rem; background: var(--color-error-hover); color: var(--color-error-light); border: 1px solid var(--color-error-border); border-radius: var(--radius-md); font-size: var(--font-size-xs); cursor: pointer; transition: var(--button-transition); white-space: nowrap; min-height: 36px; }
.error-banner-retry:hover { background: var(--color-error-hover); }

.topo-skeleton { position: absolute; inset: 0; pointer-events: none; }
.skeleton-node { position: absolute; width: 60px; height: 60px; border-radius: 50%; background: var(--color-bg-quaternary); animation: skeleton-pulse 1.5s ease-in-out infinite; }
.skeleton-line { position: absolute; height: 2px; background: var(--color-bg-hover); animation: skeleton-pulse 1.5s ease-in-out infinite 0.3s; }
@keyframes skeleton-pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 0.7; } }
.svg-canvas { width: 100%; height: 100%; min-height: 450px; background: var(--color-bg-input); border-radius: var(--radius-lg); touch-action: none; -webkit-user-select: none; user-select: none; }
.link-group { cursor: pointer; transition: opacity 0.3s ease; }
.link-group:hover .link:not(.link-hitbox) { opacity: 1; }
.link { stroke-width: 3; opacity: 0.7; transition: stroke-width 0.3s ease, opacity 0.3s ease, stroke 0.3s ease; filter: url(#glow); }
.link.warning { animation: linkBlink 1s ease-in-out infinite; }
.link.error { animation: linkAlert 0.5s ease-in-out infinite; }
.link.main { stroke-width: 4; opacity: 1; animation: mainLinkPulse 2s ease-in-out infinite; }
.link.isCentralLink { stroke: url(#centralNodeGradient); stroke-width: 5; opacity: 0.9; stroke-dasharray: none; }
.link-hitbox { pointer-events: all; }
.link-label { pointer-events: none; user-select: none; }
@keyframes linkBlink { 0%, 100% { opacity: 0.8; } 50% { opacity: 0.4; } }
@keyframes linkAlert { 0%, 100% { opacity: 1; stroke-width: 4; } 50% { opacity: 0.5; stroke-width: 3; } }
@keyframes mainLinkPulse { 0%, 100% { filter: url(#glow); } 50% { filter: drop-shadow(var(--shadow-glow-success)); } }
.flow-path { opacity: 0.6; animation: flowAnimation 2s linear infinite; }
.flow-path.video { animation-duration: 1.5s; }
@keyframes flowAnimation { from { stroke-dashoffset: 30; } to { stroke-dashoffset: 0; } }
.status-ring { animation: statusRingPulse 2s ease-in-out infinite; }
.status-ring.healthy { animation: healthyPulse 2s ease-in-out infinite; }
.status-ring.warning { animation: warningPulse 1.5s ease-in-out infinite; }
.status-ring.error { animation: errorPulse 0.8s ease-in-out infinite; }
@keyframes statusRingPulse { 0%, 100% { opacity: 0.8; } 50% { opacity: 0.5; } }
@keyframes healthyPulse { 0%, 100% { opacity: 0.9; r: 35; } 50% { opacity: 0.4; r: 40; } }
@keyframes warningPulse { 0%, 100% { opacity: 0.9; r: 35; } 50% { opacity: 0.3; r: 42; } }
@keyframes errorPulse { 0%, 100% { opacity: 1; r: 35; } 50% { opacity: 0.5; r: 44; } }
.a2a-flow-path { animation: a2aFlowAnimation 1.5s linear infinite; }
@keyframes a2aFlowAnimation { from { stroke-dashoffset: 24; } to { stroke-dashoffset: 0; } }
.node-group { cursor: pointer; transition: opacity 0.3s ease; }
.node-group.animating-isolate, .central-node.animating-isolate { animation: isolateNode 0.5s ease-out forwards; }
@keyframes isolateNode { 0% { opacity: 1; filter: brightness(1) blur(0); } 30% { opacity: 0.8; filter: brightness(0.7) blur(2px); } 60% { opacity: 0.6; filter: brightness(0.5) blur(4px); } 100% { opacity: 0.5; filter: brightness(0.4) saturate(0.5) grayscale(0.3); } }
.node-group.animating-unisolate, .central-node.animating-unisolate { animation: unisolateNode 0.5s ease-out forwards; }
@keyframes unisolateNode { 0% { opacity: 0.5; filter: brightness(0.4) saturate(0.5) grayscale(0.3); } 30% { opacity: 0.7; filter: brightness(0.6) saturate(0.7) grayscale(0.15); } 60% { opacity: 0.9; filter: brightness(0.8) saturate(0.9) grayscale(0); } 100% { opacity: 1; filter: brightness(1) saturate(1) blur(0); } }
.lock-ring { animation: lockRingPulse 2s ease-in-out infinite; }
@keyframes lockRingPulse { 0%, 100% { stroke-dasharray: 4, 4; opacity: 1; } 50% { stroke-dasharray: 8, 8; opacity: 0.7; } }
.node-group.dragging { cursor: grabbing; }
.central-node { cursor: pointer; transition: transform 0.3s ease, opacity 0.3s ease; }
.central-node:hover { opacity: 0.9; }
.central-node.dragging { opacity: 0.8; cursor: grabbing; }
.status-indicator { transition: fill 0.3s ease; animation: statusPulse 2s ease-in-out infinite; }
@keyframes statusPulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
.node-group:hover .node-circle { filter: url(#glow); opacity: 0.9; }
.node-group:hover .status-ring { stroke-width: 3; }
.node-group.selected .node-circle { stroke: var(--color-primary); stroke-width: 3; filter: url(#glow); }
.node-group.locked .node-circle { opacity: 0.5; filter: brightness(0.4) saturate(0.5) grayscale(0.3); }
.node-group.locked .node-inner { opacity: 0.7; }
.node-circle { transition: filter 0.3s ease, opacity 0.3s ease; }
.click-area { pointer-events: all; }
.node-inner { transition: opacity 0.3s ease; pointer-events: none; }
.node-label { pointer-events: none; }
.cpu-ring, .memory-ring { transition: d 0.5s ease; }
.resource-rings { pointer-events: none; }
.node-type-icon { transition: opacity 0.2s ease; }
.node-group, .central-node { transition: opacity 0.4s ease-out; }
.node-group.hidden, .central-node.hidden { opacity: 0; pointer-events: none; }
.node-group.restarting, .central-node.restarting { animation: nodeReappear 0.4s ease-out forwards; }
@keyframes nodeReappear { 0% { opacity: 0; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
.link-group { transition: opacity 0.4s ease-out; }
.link-group.link-hidden { opacity: 0; pointer-events: none; }
.link-group.link-isolated { opacity: 0; pointer-events: none; transition: opacity 0.4s ease-out; }
.link-group.restarting { animation: linkReappear 0.4s ease-out forwards; }
@keyframes linkReappear { 0% { opacity: 0; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
.link-group.draining .link { stroke-dasharray: 10, 5; animation: drainPulse 0.5s ease-in-out infinite; }
@keyframes drainPulse { 0%, 100% { opacity: 1; stroke-dashoffset: 0; } 50% { opacity: 0.7; stroke-dashoffset: 10; } }
.flow-particle { transition: cx 0.1s linear, cy 0.1s linear; filter: url(#glow); }
.node-tooltip { position: absolute; z-index: var(--z-fixed); background: var(--color-bg-elevated); -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); border: 1px solid var(--color-border-secondary); border-radius: var(--radius-md); padding: 0.75rem var(--spacing-md); min-width: 180px; pointer-events: none; animation: tooltipFadeIn 0.15s var(--ease-out); box-shadow: var(--shadow-dropdown); }
.tooltip-header { display: flex; align-items: center; gap: var(--spacing-sm); margin-bottom: var(--spacing-sm); padding-bottom: var(--spacing-sm); border-bottom: 1px solid var(--color-border-primary); }
.tooltip-status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.tooltip-name { font-size: var(--font-size-sm); font-weight: 600; color: var(--color-text-primary); }
.tooltip-body { display: flex; flex-direction: column; gap: var(--spacing-xs); }
.tooltip-row { display: flex; justify-content: space-between; font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.tooltip-row span:last-child { color: var(--color-text-secondary); font-weight: 500; }
@keyframes tooltipFadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.minimap { position: absolute; bottom: 24px; right: 24px; width: 180px; background: var(--color-bg-elevated); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); border-radius: var(--radius-md); border: 1px solid var(--color-border-secondary); overflow: hidden; box-shadow: var(--shadow-dropdown); z-index: var(--z-dropdown); }
.minimap-header { display: flex; justify-content: space-between; align-items: center; padding: 0.375rem 10px; font-size: 0.6875rem; color: var(--color-text-tertiary); border-bottom: 1px solid var(--color-border-primary); }
.minimap-close { background: none; border: none; color: var(--color-text-tertiary); cursor: pointer; font-size: var(--font-size-xs); padding: 2px; min-width: 44px; min-height: 44px; display: flex; align-items: center; justify-content: center; }
.minimap-close:hover { color: var(--color-text-primary); }
.minimap-svg { width: 100%; height: 100px; background: var(--color-bg-input); }
.a2a-panel { position: absolute; top: 24px; right: 24px; width: 360px; background: var(--color-bg-elevated); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); border-radius: var(--radius-lg); border: 1px solid var(--color-purple-border-strong); box-shadow: var(--shadow-glow-purple-lg); overflow: hidden; animation: slideIn 0.3s var(--ease-out); }
@keyframes slideIn { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
.a2a-panel-header { display: flex; justify-content: space-between; align-items: center; padding: var(--spacing-md) 1.25rem; background: var(--gradient-purple); border-bottom: 1px solid var(--color-purple-border); }
.a2a-panel-title { display: flex; align-items: center; gap: 10px; font-size: var(--font-size-md); font-weight: 600; color: var(--color-text-primary); }
.a2a-icon { font-size: var(--font-size-lg); }
.a2a-close-btn { background: none; border: none; color: var(--color-text-tertiary); font-size: var(--font-size-lg); cursor: pointer; padding: var(--spacing-xs); width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border-radius: var(--radius-sm); transition: var(--button-transition); }
.a2a-close-btn:hover { color: var(--color-text-primary); background: var(--color-bg-hover); }
.a2a-panel-body { padding: 1.25rem; }
.a2a-message-info { display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1.25rem; }
.info-row { display: flex; justify-content: space-between; align-items: center; }
.info-label { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.info-value { font-size: var(--font-size-sm); color: var(--color-text-primary); font-weight: 500; font-family: 'Monaco', 'Menlo', monospace; }
.info-value.sender { color: var(--color-purple); }
.info-value.receiver { color: var(--color-success); }
.a2a-payload { background: var(--color-bg-input); border-radius: var(--radius-md); padding: 0.75rem; }
.payload-label { font-size: var(--font-size-xs); color: var(--color-text-tertiary); margin-bottom: var(--spacing-sm); }
.payload-content { font-family: 'Monaco', 'Menlo', monospace; font-size: var(--font-size-xs); color: var(--color-text-secondary); margin: 0; overflow-x: auto; white-space: pre-wrap; }
.legend { position: absolute; bottom: 24px; left: 24px; z-index: var(--z-dropdown); display: flex; gap: var(--spacing-lg); padding: var(--spacing-md) 1.25rem; background: var(--color-bg-elevated); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); border-radius: var(--radius-lg); border: 1px solid var(--color-border-secondary); flex-wrap: wrap; box-shadow: var(--shadow-dropdown); max-width: calc(100% - 450px); }
.legend-section { display: flex; flex-direction: column; gap: 10px; min-width: 140px; }
.legend-title { font-size: var(--font-size-sm); font-weight: 600; color: var(--color-text-primary); margin-bottom: 0.375rem; padding-bottom: var(--spacing-sm); border-bottom: 1px solid var(--color-border-primary); }
.legend-item { display: flex; align-items: center; gap: var(--spacing-sm); font-size: var(--font-size-xs); color: var(--color-text-secondary); transition: transform 0.2s var(--ease-out); }
.legend-item:hover { transform: translateX(2px); }
.legend-item.legend-summary { margin-top: 0.375rem; padding-top: var(--spacing-sm); border-top: 1px dashed var(--color-border-primary); font-weight: 500; }
.legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.legend-line { width: 18px; height: 4px; border-radius: var(--radius-xs); flex-shrink: 0; }
.detail-panel { background: var(--gradient-glass-strong); border-radius: var(--radius-lg); border: var(--card-border); overflow-y: auto; max-height: calc(100vh - 100px); position: sticky; top: 80px; -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px); box-shadow: var(--shadow-card); display: flex; flex-direction: column; }
.detail-panel-header { display: flex; justify-content: space-between; align-items: center; padding: var(--spacing-md) 1.25rem; border-bottom: 1px solid var(--color-border-primary); }
.detail-panel-title { font-size: var(--font-size-md); font-weight: 700; color: var(--color-text-primary); margin: 0; }
.detail-close-btn { width: 32px; height: 32px; background: var(--color-bg-hover); border: 1px solid var(--color-border-primary); border-radius: var(--radius-md); cursor: pointer; color: var(--color-text-tertiary); font-size: var(--font-size-base); display: flex; align-items: center; justify-content: center; transition: var(--button-transition); }
.detail-close-btn:hover { background: var(--color-error-bg); color: var(--color-error); border-color: var(--color-error-border); }
.detail-panel-body { padding: var(--spacing-md) 1.25rem; flex: 1; overflow-y: auto; }
.detail-slide-enter-active { animation: detailSlideIn 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.detail-slide-leave-active { animation: detailSlideOut 0.25s ease-in; }
@keyframes detailSlideIn { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
@keyframes detailSlideOut { from { opacity: 1; transform: translateX(0); } to { opacity: 0; transform: translateX(20px); } }
.a2a-section { border-top: 1px solid var(--color-purple-border); background: var(--color-purple-glow); }
.a2a-section-header { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 1.25rem; cursor: pointer; font-size: var(--font-size-sm); font-weight: 600; color: var(--color-purple-lighter); transition: background 0.2s ease; }
.a2a-section-header:hover { background: var(--color-purple-hover); }
.sim-badge { font-size: var(--font-size-xs); padding: 1px 0.375rem; background: var(--color-warning-bg); color: var(--color-warning); border-radius: var(--radius-sm); margin-left: 0.375rem; }
.a2a-expand-icon { font-size: var(--font-size-xs); }
.a2a-section-body { padding: 0 1.25rem var(--spacing-md); }
.payload-expand-enter-active { animation: payloadExpand 0.25s ease-out; }
.payload-expand-leave-active { animation: payloadCollapse 0.2s ease-in; }
@keyframes payloadExpand { from { opacity: 0; max-height: 0; } to { opacity: 1; max-height: 300px; } }
@keyframes payloadCollapse { from { opacity: 1; max-height: 300px; } to { opacity: 0; max-height: 0; } }
.panel-title { font-size: var(--font-size-md); font-weight: 600; color: var(--color-text-primary); margin-bottom: 1.25rem; padding-left: 10px; border-left: 3px solid var(--color-primary); }
.node-info, .link-info { display: flex; flex-direction: column; gap: var(--spacing-md); }
.info-header { display: flex; align-items: center; gap: var(--spacing-md); }
.info-icon { width: 56px; height: 56px; border-radius: var(--radius-xl); display: flex; align-items: center; justify-content: center; color: var(--color-text-primary); font-size: var(--font-size-2xl); font-weight: 700; }
.link-icon { background: var(--gradient-primary); }
.info-title { display: flex; flex-direction: column; gap: var(--spacing-xs); }
.info-title h3 { font-size: var(--font-size-lg); font-weight: 600; color: var(--color-text-primary); margin: 0; }
.info-type { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.locked-badge { font-size: var(--font-size-xs); color: var(--color-error); background: var(--color-error-bg); padding: 2px var(--spacing-sm); border-radius: var(--radius-md); width: fit-content; }
.status-badge { font-size: var(--font-size-xs); padding: 2px var(--spacing-sm); border-radius: var(--radius-md); width: fit-content; }
.status-badge.healthy { color: var(--color-success); background: var(--color-success-bg); }
.status-badge.warning { color: var(--color-warning); background: var(--color-warning-bg); }
.status-badge.error { color: var(--color-error); background: var(--color-error-bg); }
.status-badge.active { color: var(--color-success); background: var(--color-success-bg); }
.info-stats { display: flex; flex-direction: column; gap: 0.75rem; }
.stat-row { display: flex; justify-content: space-between; align-items: center; }
.stat-label { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.stat-value { font-size: var(--font-size-base); color: var(--color-text-primary); font-weight: 500; }
.stat-value.locked { color: var(--color-error); }
.stat-value.warning { color: var(--color-warning); }
.stat-value.main { color: var(--color-success); }
.stat-value-row { display: flex; align-items: center; gap: 0.75rem; flex: 1; justify-content: flex-end; }
.health-bar-container { flex: 1; height: 6px; background: var(--color-bg-hover); border-radius: 3px; overflow: hidden; }
.health-bar { height: 100%; border-radius: 3px; transition: width 0.3s ease; }
.info-actions { display: flex; gap: 0.75rem; margin-top: var(--spacing-md); padding-top: var(--spacing-md); border-top: 1px solid var(--color-border-primary); }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 1.25rem; color: var(--color-text-tertiary); }
.empty-icon { font-size: var(--font-size-4xl); margin-bottom: var(--spacing-md); }
.empty-state p { font-size: var(--font-size-base); margin: var(--spacing-xs) 0; }
.empty-state .hint { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.alert-bar { display: flex; flex-wrap: wrap; gap: var(--spacing-sm); margin-top: 0.75rem; padding: 10px var(--spacing-md); background: var(--color-bg-glass-strong); -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); border-radius: var(--radius-lg); border: var(--card-border); align-items: center; }
.alert-item { display: flex; align-items: center; gap: var(--spacing-sm); padding: 0.375rem 0.75rem; border-radius: var(--radius-md); font-size: var(--font-size-xs); animation: alertSlideIn 0.3s var(--ease-out); }
.alert-item.error { background: var(--color-error-bg); color: var(--color-error-light); border: 1px solid var(--color-error-border); }
.alert-item.warning { background: var(--color-warning-bg); color: var(--color-warning-light); border: 1px solid var(--color-warning-border); }
.alert-item.info { background: var(--color-primary-bg); color: var(--color-primary-light); border: 1px solid var(--color-primary-border); }
.alert-icon { font-size: var(--font-size-base); flex-shrink: 0; }
.alert-msg { flex: 1; }
.alert-dismiss { background: none; border: none; color: inherit; cursor: pointer; font-size: var(--font-size-base); padding: 0 2px; opacity: 0.6; transition: opacity 0.2s ease; min-width: 44px; min-height: 44px; display: flex; align-items: center; justify-content: center; }
.alert-dismiss:hover { opacity: 1; }
.alert-clear { padding: var(--spacing-xs) 0.75rem; background: var(--color-bg-hover); border: 1px solid var(--color-border-primary); border-radius: var(--radius-sm); color: var(--color-text-tertiary); font-size: var(--font-size-xs); cursor: pointer; transition: var(--button-transition); margin-left: auto; white-space: nowrap; min-height: 44px; }
.alert-clear:hover { background: var(--color-error-bg); color: var(--color-error-light); border-color: var(--color-error-border); }
@keyframes alertSlideIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
.display-options-panel { position: absolute; top: 60px; right: 20px; width: 240px; background: var(--color-bg-elevated); -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); border-radius: var(--radius-lg); border: 1px solid var(--color-border-secondary); box-shadow: var(--shadow-dropdown); z-index: var(--z-sticky); animation: panelSlideIn 0.2s var(--ease-out); overflow: hidden; }
@keyframes panelSlideIn { from { opacity: 0; transform: translateY(-8px) scale(0.96); } to { opacity: 1; transform: translateY(0) scale(1); } }
.display-options-header { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem var(--spacing-md); border-bottom: 1px solid var(--color-border-primary); font-size: var(--font-size-base); font-weight: 600; color: var(--color-text-primary); }
.display-options-body { padding: 0.75rem var(--spacing-md); display: flex; flex-direction: column; gap: 10px; }
.option-item { display: flex; align-items: center; gap: var(--spacing-sm); font-size: var(--font-size-sm); color: var(--color-text-secondary); cursor: pointer; }
.option-item input[type="checkbox"] { accent-color: var(--color-primary); cursor: pointer; }
.option-item input[type="range"] { flex: 1; accent-color: var(--color-primary); cursor: pointer; }
.context-menu { position: fixed; z-index: var(--z-modal); background: var(--color-bg-elevated); -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px); border-radius: var(--radius-lg); border: 1px solid var(--color-border-secondary); box-shadow: var(--shadow-dropdown); min-width: 200px; overflow: hidden; animation: contextMenuIn 0.15s var(--ease-out); }
@keyframes contextMenuIn { from { opacity: 0; transform: scale(0.92); } to { opacity: 1; transform: scale(1); } }
.menu-header { padding: 0.75rem var(--spacing-md); border-bottom: 1px solid var(--color-border-primary); }
.menu-title { font-size: var(--font-size-sm); font-weight: 600; color: var(--color-text-primary); }
.menu-items { padding: 0.375rem 0; }
.menu-item { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px var(--spacing-md); background: none; border: none; color: var(--color-text-secondary); font-size: var(--font-size-sm); cursor: pointer; transition: all 0.15s var(--ease-out); text-align: left; }
.menu-item:hover { background: var(--color-primary-bg); color: var(--color-primary-light); }
.menu-item.danger { color: var(--color-error-light); }
.menu-item.danger:hover { background: var(--color-error-bg); color: var(--color-error-light); }
.menu-icon { font-size: var(--font-size-md); width: 20px; text-align: center; flex-shrink: 0; }
.menu-label { flex: 1; }
.modal-overlay { position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: var(--z-toast); background: var(--modal-overlay-bg); -webkit-backdrop-filter: blur(var(--modal-backdrop-blur)); backdrop-filter: blur(var(--modal-backdrop-blur)); display: flex; align-items: center; justify-content: center; animation: overlayFadeIn 0.2s var(--ease-out); }
@keyframes overlayFadeIn { from { opacity: 0; } to { opacity: 1; } }
.modal-content { background: var(--color-bg-elevated); -webkit-backdrop-filter: blur(20px); backdrop-filter: blur(20px); border-radius: var(--modal-border-radius); border: 1px solid var(--color-border-secondary); box-shadow: var(--modal-shadow); width: 90%; max-width: 480px; max-height: 80vh; overflow-y: auto; animation: modalSlideIn 0.25s var(--ease-spring); }
.modal-content.large { max-width: 640px; }
@keyframes modalSlideIn { from { opacity: 0; transform: translateY(20px) scale(0.96); } to { opacity: 1; transform: translateY(0) scale(1); } }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem var(--spacing-lg); border-bottom: 1px solid var(--color-border-primary); }
.modal-header h3 { font-size: var(--font-size-lg); font-weight: 600; color: var(--color-text-primary); margin: 0; }
.modal-body { padding: var(--content-padding); }
.modal-body pre { background: var(--color-bg-input); border-radius: var(--radius-md); padding: var(--spacing-md); font-family: 'Monaco', 'Menlo', monospace; font-size: var(--font-size-xs); color: var(--color-text-secondary); overflow-x: auto; white-space: pre-wrap; margin: 0; border: 1px solid var(--color-border-primary); }
.close-btn { background: none; border: none; color: var(--color-text-tertiary); font-size: var(--font-size-xl); cursor: pointer; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: var(--radius-md); transition: var(--button-transition); }
.close-btn:hover { color: var(--color-text-primary); background: var(--color-bg-hover); }
.form-group { margin-bottom: 1.25rem; }
.form-group label { display: block; font-size: var(--font-size-sm); font-weight: 500; color: var(--color-text-secondary); margin-bottom: var(--spacing-sm); }
.form-input { width: 100%; padding: 10px 14px; background: var(--input-bg); border: 1px solid var(--input-border); border-radius: var(--input-radius); color: var(--color-text-primary); font-size: var(--font-size-base); transition: border-color 0.2s var(--ease-out); box-sizing: border-box; }
.form-input:focus { outline: none; border-color: var(--input-border-focus); box-shadow: var(--input-shadow-focus); }
.form-input::placeholder { color: var(--color-text-disabled); }
.form-select { width: 100%; padding: 10px 14px; background: var(--input-bg); border: 1px solid var(--input-border); border-radius: var(--input-radius); color: var(--color-text-primary); font-size: var(--font-size-base); cursor: pointer; }
.form-select:focus { outline: none; border-color: var(--input-border-focus); }
.form-select option { background: var(--color-bg-secondary); color: var(--color-text-secondary); }
.bandwidth-input-group { display: flex; gap: var(--spacing-sm); }
.bandwidth-input-group .form-input { flex: 1; }
.bandwidth-input-group .form-select { width: 100px; flex-shrink: 0; }
.modal-actions { display: flex; justify-content: flex-end; gap: 0.75rem; margin-top: var(--spacing-lg); padding-top: var(--spacing-md); border-top: 1px solid var(--color-border-primary); }
.modal-btn { padding: 10px var(--spacing-lg); border-radius: var(--radius-md); font-size: var(--font-size-base); font-weight: 500; cursor: pointer; transition: var(--button-transition); border: none; }
.modal-btn.cancel { background: var(--color-bg-hover); color: var(--color-text-tertiary); border: 1px solid var(--color-border-primary); }
.modal-btn.cancel:hover { background: var(--color-bg-active); color: var(--color-text-secondary); }
.modal-btn.confirm { background: var(--gradient-primary); color: var(--color-text-primary); }
.modal-btn.confirm:hover { box-shadow: var(--shadow-glow-primary); transform: translateY(-1px); }
.modal-btn.confirm:disabled { opacity: 0.5; cursor: not-allowed; transform: none; box-shadow: none; }
.diagnose-result { display: flex; flex-direction: column; gap: 14px; }
.result-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: var(--color-bg-input); border-radius: var(--radius-md); border: 1px solid var(--color-border-primary); }
.result-label { font-size: var(--font-size-sm); color: var(--color-text-tertiary); }
.result-value { font-size: var(--font-size-base); color: var(--color-text-primary); font-weight: 500; }
.result-value.success { color: var(--color-success); }
.ssh-terminal { background: var(--color-bg-terminal); border-radius: var(--radius-md); overflow: hidden; border: 1px solid var(--color-border-primary); }
.terminal-header { padding: 10px var(--spacing-md); background: var(--color-bg-hover); border-bottom: 1px solid var(--color-border-primary); }
.terminal-title { font-family: 'Monaco', 'Menlo', monospace; font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.terminal-body { padding: var(--spacing-md); min-height: 200px; }
.terminal-line { display: flex; align-items: center; gap: var(--spacing-sm); margin-bottom: 0.75rem; }
.terminal-prompt { color: var(--color-success); font-family: 'Monaco', 'Menlo', monospace; font-size: var(--font-size-base); font-weight: 700; }
.terminal-input { flex: 1; background: none; border: none; color: var(--color-text-secondary); font-family: 'Monaco', 'Menlo', monospace; font-size: var(--font-size-sm); outline: none; }
.terminal-output { font-family: 'Monaco', 'Menlo', monospace; font-size: var(--font-size-sm); color: var(--color-text-tertiary); line-height: 1.6; }
.terminal-output p { margin: var(--spacing-xs) 0; }
.terminal-output .success { color: var(--color-success); }
.quick-intent-btn { padding: 0.375rem 14px; background: var(--color-purple-bg); border: 1px solid var(--color-purple-border); border-radius: var(--radius-full); color: var(--color-purple-light); font-size: var(--font-size-xs); cursor: pointer; transition: var(--button-transition); white-space: nowrap; }
.quick-intent-btn:hover { background: var(--color-purple-hover); border-color: var(--color-purple-border-strong); color: var(--color-purple-lighter); box-shadow: var(--shadow-glow-purple); }
@media (max-width: 1200px) {
  .topology-layout { grid-template-columns: 1fr; }
  .stats-panel { display: none; }
  .detail-panel { position: fixed; right: 0; top: 0; bottom: 0; width: 340px; max-height: 100vh; border-radius: var(--radius-lg) 0 0 var(--radius-lg); z-index: var(--z-fixed); }
}
@media (max-width: 1024px) {
  .detail-panel { width: 300px; }
  .topology-canvas { padding: var(--spacing-md); }
  .toolbar-panel { flex-wrap: wrap; }
}
@media (max-width: 768px) {
  .topology-container { padding: 0.75rem; min-height: auto; }
  .topo-header { margin-bottom: 0.75rem; padding-bottom: 0.75rem; flex-wrap: wrap; gap: var(--spacing-sm); }
  .header-left { flex: 1 1 100%; }
  .page-title { font-size: var(--font-size-xl); }
  .page-subtitle { font-size: var(--font-size-base); }
  .header-actions { width: 100%; gap: var(--spacing-sm); flex-wrap: wrap; }
  .action-btn { min-height: var(--button-min-height-touch); padding: var(--spacing-sm) 12px; font-size: var(--font-size-base); }
  .action-btn.primary, .action-btn.secondary, .action-btn.success { height: 44px; }
  .toolbar-panel { padding: 10px 0.75rem; gap: var(--spacing-sm); flex-wrap: wrap; }
  .toolbar-group { flex-wrap: wrap; gap: 0.375rem; }
  .toolbar-btn { min-height: var(--button-min-height-touch); padding: var(--spacing-sm) 10px; font-size: var(--font-size-sm); }
  .search-input { width: 120px; font-size: var(--font-size-md); min-height: var(--button-min-height-touch); }
  .layout-select { min-height: var(--button-min-height-touch); font-size: var(--font-size-md); }
  .topology-layout { grid-template-columns: 1fr; }
  .stats-panel { display: none; }
  .topology-canvas { padding: 0.75rem; overflow: auto; -webkit-overflow-scrolling: touch; }
  .svg-canvas { min-height: 300px; touch-action: pan-x pan-y pinch-zoom; }
  .detail-panel { position: fixed; bottom: 0; left: 0; right: 0; top: auto; max-height: 55vh; border-radius: var(--radius-lg) var(--radius-lg) 0 0; width: 100%; max-width: 100%; box-shadow: var(--shadow-mobile-panel); padding-bottom: env(safe-area-inset-bottom, 0px); }
  .detail-panel .panel-title { font-size: var(--font-size-md); }
  .detail-label { font-size: var(--font-size-base); }
  .detail-value { font-size: var(--font-size-base); }
  .a2a-section-title { font-size: var(--font-size-base); }
  .minimap { width: 120px; bottom: 12px; right: 12px; }
  .minimap-svg { height: 70px; }
  .metrics-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .metric-card { padding: 0.75rem; }
  .metric-value { font-size: 22px; }
  .metric-label { font-size: var(--font-size-base); }
  .modal-content { width: 95%; max-height: 90vh; }
  .modal-header { padding: var(--spacing-md) 20px; }
  .modal-body { padding: 1.25rem; }
  .modal-actions { flex-wrap: wrap; }
  .modal-btn { flex: 1; min-height: var(--button-min-height-touch); }
  .context-menu { min-width: 160px; }
  .context-menu-item { min-height: var(--button-min-height-touch); font-size: var(--font-size-base); }
  .menu-item { min-height: var(--button-min-height-touch); padding: 10px 14px; }
  .display-options-panel { width: 200px; right: 12px; }
  .legend { max-width: calc(100% - 48px); gap: 0.75rem; padding: 0.75rem 14px; bottom: 12px; left: 12px; }
  .legend-section { min-width: 100px; }
  .a2a-panel { width: calc(100% - 24px); right: 12px; top: 12px; }
  .alert-bar { padding: var(--spacing-sm) 12px; gap: 0.375rem; }
  .alert-item { padding: var(--spacing-xs) 8px; font-size: 0.6875rem; min-height: 36px; }
  .alert-dismiss { min-width: 44px; min-height: var(--button-min-height-touch); display: flex; align-items: center; justify-content: center; }
  .alert-clear { min-height: 36px; }
  .node-tooltip { min-width: 150px; max-width: calc(100vw - 24px); }
  .bg-glow { display: none; }
  .info-actions { flex-wrap: wrap; }
  .info-actions .action-btn { min-height: var(--button-min-height-touch); }
  .form-input, .form-select { min-height: var(--button-min-height-touch); font-size: var(--font-size-base); }
}
@media (max-width: 480px) {
  .topology-container { padding: 0.375rem; }
  .topo-header { margin-bottom: var(--spacing-sm); padding-bottom: var(--spacing-sm); }
  .page-title { font-size: var(--font-size-lg); }
  .page-subtitle { font-size: var(--font-size-sm); }
  .action-btn { font-size: var(--font-size-sm); padding: var(--spacing-sm) 10px; min-height: var(--button-min-height-touch); }
  .action-btn.primary, .action-btn.secondary, .action-btn.success { height: 44px; font-size: var(--font-size-sm); }
  .metrics-grid { grid-template-columns: 1fr; gap: var(--spacing-sm); }
  .metric-card { padding: 10px; gap: 10px; }
  .metric-icon { width: 36px; height: 36px; font-size: var(--font-size-md); border-radius: var(--radius-md); }
  .metric-value { font-size: var(--font-size-xl); }
  .metric-label { font-size: var(--font-size-sm); }
  .toolbar-panel { padding: var(--spacing-sm) 10px; gap: 0.375rem; }
  .toolbar-group { gap: var(--spacing-xs); }
  .toolbar-btn { font-size: var(--font-size-xs); padding: 0.375rem 8px; min-height: var(--button-min-height-touch); }
  .search-input { width: 100%; min-height: var(--button-min-height-touch); }
  .layout-select { min-height: var(--button-min-height-touch); }
  .minimap { width: 100px; }
  .minimap-svg { height: 60px; }
  .detail-panel { max-height: 65vh; padding-bottom: env(safe-area-inset-bottom, 0px); }
  .detail-panel .panel-title { font-size: var(--font-size-md); }
  .detail-panel-header { padding: 0.75rem 14px; }
  .detail-panel-body { padding: 0.75rem 14px; }
  .svg-canvas { min-height: 250px; touch-action: pan-x pan-y pinch-zoom; }
  .topology-canvas { padding: var(--spacing-sm); border-radius: var(--radius-lg); }
  .legend { max-width: calc(100% - 16px); gap: var(--spacing-sm); padding: 10px 0.75rem; font-size: 0.6875rem; flex-direction: column; }
  .legend-section { min-width: unset; }
  .legend-item { font-size: var(--font-size-xs); }
  .a2a-panel { width: calc(100% - 16px); right: 8px; top: 8px; }
  .a2a-panel-header { padding: 0.75rem 14px; }
  .a2a-panel-body { padding: 14px; }
  .alert-bar { padding: 0.375rem 8px; gap: var(--spacing-xs); }
  .alert-item { font-size: var(--font-size-xs); padding: var(--spacing-xs) 6px; }
  .alert-msg { font-size: var(--font-size-xs); }
  .node-tooltip { min-width: 130px; padding: var(--spacing-sm) 12px; }
  .tooltip-name { font-size: var(--font-size-xs); }
  .tooltip-row { font-size: 0.6875rem; }
  .modal-content { width: 98%; max-height: 95vh; border-radius: var(--radius-lg); }
  .modal-header { padding: 14px var(--spacing-md); }
  .modal-header h3 { font-size: var(--font-size-md); }
  .modal-body { padding: var(--spacing-md); }
  .modal-body pre { font-size: 0.6875rem; padding: 0.75rem; }
  .modal-btn { min-height: var(--button-min-height-touch); font-size: var(--font-size-sm); padding: var(--spacing-sm) 16px; }
  .form-input, .form-select { min-height: var(--button-min-height-touch); font-size: var(--font-size-base); }
  .info-header { flex-wrap: wrap; gap: 10px; }
  .info-icon { width: 44px; height: 44px; font-size: var(--font-size-xl); border-radius: var(--radius-md); }
  .info-title h3 { font-size: var(--font-size-md); }
  .info-actions { gap: var(--spacing-sm); }
  .display-options-panel { width: calc(100% - 16px); right: 8px; }
  .context-menu { min-width: 140px; }
  .menu-item { min-height: var(--button-min-height-touch); font-size: var(--font-size-sm); }
  .stats-highlight-value { font-size: var(--font-size-md); }
  .data-freshness { font-size: 0.6875rem; padding: 3px var(--spacing-sm); }
  .last-refresh { font-size: 0.6875rem; }
  .empty-state { padding: 40px var(--spacing-md); }
  .empty-icon { font-size: 36px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
  .flow-path, .flow-particle, .a2a-flow-path, .status-ring, .link.main, .link.warning, .link.error, .lock-ring, .freshness-dot, .skeleton, .skeleton-line, .status-indicator, .node-group.animating-isolate, .central-node.animating-isolate, .node-group.animating-unisolate, .central-node.animating-unisolate, .node-group.restarting, .central-node.restarting, .link-group.restarting, .link-group.draining .link, .glow-1, .glow-2 { animation: none !important; }
  .metric-card:hover { transform: none; }
  .action-btn.primary:hover { transform: none; }
  .action-btn:active:not(:disabled) { transform: none; }
  .toolbar-btn:active { transform: none; }
  .legend-item:hover { transform: none; }
}
</style>