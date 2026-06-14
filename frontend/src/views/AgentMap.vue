<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch, shallowRef } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import AMapLoader from '@amap/amap-jsapi-loader'
import { apiClient, api } from '@/utils/apiClient'
import { showToast } from '@/utils/toast'
import { useLogger } from '@/utils/logger'
import { useAuthStore } from '@/stores/auth'
import gsap from 'gsap'
import { safeAnimate } from '@/utils/animation'

const { info, warn } = useLogger()
const authStore = useAuthStore()
const canWrite = computed(() => authStore.userRole !== 'viewer')

declare global {
  interface Window {
    AMap: any
    _AMapSecurityConfig: any
  }
}

import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow
})

// ==================== AgentMap Interfaces ====================
interface AgentGeo {
  agent_id: string
  lat: number
  lng: number
  city: string
  status: string
  capabilities: string[]
  cpu_load: number
  memory_free: number
  endpoint?: string
}

interface POI {
  id: string
  name: string
  display_name?: string
  category: string
  lat: number
  lng: number
  address: string
  description: string
}

interface CustomMarker {
  id: string
  lat: number
  lng: number
  title: string
  description: string
  icon: string
  category: string
  agent_id?: string
}

interface RoutingDecision {
  intent_text?: string
  selected_agent: any
  matched_capabilities?: string[]
  capability_scores?: Record<string, number>
  load_score?: number
  total_score?: number
  explanation?: string
  candidates_count?: number
  reasoning?: string
  timestamp?: string
}

interface TopologyData {
  nodes: { id: string; label: string; status: string; type: string }[]
  edges: { source: string; target: string; label: string }[]
}

const DEFAULT_CENTER: [number, number] = [26.6470, 106.6302]
const DEFAULT_ZOOM = 7

const mapContainer = ref<HTMLDivElement | null>(null)
let map: L.Map | null = null
const amapInstance = shallowRef<any>(null)
const amapLoaded = ref(false)
const useAMap = ref(true)
const amapMarkers: Record<string, any> = {}
const amapPolylines: Record<string, any> = {}

const agentGeoList = ref<AgentGeo[]>([])
const routingDecisions = ref<RoutingDecision[]>([])
const topology = ref<TopologyData>({ nodes: [], edges: [] })
const customMarkers = ref<CustomMarker[]>([])
const poiResults = ref<POI[]>([])

const selectedAgent = ref<AgentGeo | null>(null)
const isLoading = ref(true)
const routeInput = ref('')

const currentLayer = ref<string>('amap-standard')
const showTopologyOverlay = ref(false)
const isFullscreen = ref(false)
const showLeftSidebar = ref(true)
const showRightSidebar = ref(true)

const searchQuery = ref('')
const searchDropdownOpen = ref(false)

const isAddingMarker = ref(false)
const newMarkerForm = ref({ title: '', description: '', category: 'default', icon: '📍' })
const showMarkerForm = ref(false)
const pendingMarkerLatLng = ref<any>(null)
const batchSelectMode = ref(false)
const selectedMarkerIds = ref<Set<string>>(new Set())

const cachedTilesCount = ref(0)
const isDownloadingOffline = ref(false)
const offlineDownloadProgress = ref(0)

const agentSearchQuery = ref('')
const agentPage = ref(1)
const agentPageSize = 6
const preferAMap = ref(true)
const mouseCoords = ref<{ lat: string; lng: string } | null>(null)
const lastDataUpdate = ref<Date | null>(null)
const showAddAgentModal = ref(false)
const newAgentForm = ref({
  agent_id: '',
  city: '',
  lat: 0,
  lng: 0,
  capabilities: '',
  endpoint: '',
})

let agentMarkers: L.Marker[] = []
let poiMarkers: L.Marker[] = []
let customLeafletMarkers: L.Marker[] = []
let topologyLayerGroup: L.LayerGroup | null = null
let minimapControl: L.Map | null = null

let pollingInterval: number | null = null
let searchDebounceTimer: number | null = null
let mapMoveThrottleTimer: number | null = null
const pendingRequests = new Map<string, Promise<any>>()

let entranceCtx: gsap.Context | undefined

const playEntranceAnimation = () => {
  nextTick(() => {
    const container = document.querySelector('.am-body')
    if (!container) return
    entranceCtx?.revert()
    entranceCtx = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: 'power2.out' } })
      tl.from('.am-toolbar', {
        opacity: 0, y: -12, duration: 0.3
      })
      tl.from('.left-sidebar', {
        opacity: 0, x: -20, duration: 0.35
      }, '-=0.15')
      tl.from('.right-sidebar', {
        opacity: 0, x: 20, duration: 0.35
      }, '-=0.25')
      tl.from('.am-bottom-bar', {
        opacity: 0, y: 12, duration: 0.3
      }, '-=0.2')
    }, container as HTMLElement)
  })
}

const onlineCount = computed(() => agentGeoList.value.filter(a => a.status === 'online').length)
const offlineCount = computed(() => agentGeoList.value.filter(a => a.status !== 'online').length)

const KNOWN_CITIES: Record<string, { lat: number; lng: number }> = {
  '北京': { lat: 39.90, lng: 116.41 }, '上海': { lat: 31.23, lng: 121.47 }, '广州': { lat: 23.13, lng: 113.26 },
  '深圳': { lat: 22.54, lng: 114.06 }, '成都': { lat: 30.57, lng: 104.07 }, '武汉': { lat: 30.59, lng: 114.31 },
  '南京': { lat: 32.06, lng: 118.80 }, '杭州': { lat: 30.27, lng: 120.16 }, '西安': { lat: 34.34, lng: 108.94 },
  '重庆': { lat: 29.43, lng: 106.91 }, '天津': { lat: 39.34, lng: 117.36 }, '苏州': { lat: 31.30, lng: 120.59 },
  '郑州': { lat: 34.75, lng: 113.63 }, '长沙': { lat: 28.23, lng: 112.94 }, '济南': { lat: 36.65, lng: 117.00 },
  '青岛': { lat: 36.07, lng: 120.38 }, '大连': { lat: 38.91, lng: 121.61 }, '沈阳': { lat: 41.81, lng: 123.43 },
  '哈尔滨': { lat: 45.80, lng: 126.54 }, '昆明': { lat: 25.04, lng: 102.72 }, '贵阳': { lat: 26.65, lng: 106.63 },
  '兰州': { lat: 36.06, lng: 103.83 }, '太原': { lat: 37.87, lng: 112.55 }, '合肥': { lat: 31.82, lng: 117.23 },
  '福州': { lat: 26.07, lng: 119.30 }, '厦门': { lat: 24.48, lng: 118.09 }, '南宁': { lat: 22.82, lng: 108.37 },
  '石家庄': { lat: 38.04, lng: 114.51 }, '呼和浩特': { lat: 40.84, lng: 111.75 }, '乌鲁木齐': { lat: 43.83, lng: 87.62 },
}

function onCityInput() {
  const city = newAgentForm.value.city.trim()
  if (KNOWN_CITIES[city] && !newAgentForm.value.lat && !newAgentForm.value.lng) {
    newAgentForm.value.lat = KNOWN_CITIES[city].lat
    newAgentForm.value.lng = KNOWN_CITIES[city].lng
  }
}

const filteredAgents = computed(() => {
  const q = agentSearchQuery.value.toLowerCase().trim()
  if (!q) return agentGeoList.value
  return agentGeoList.value.filter(a =>
    a.agent_id.toLowerCase().includes(q) ||
    a.city.toLowerCase().includes(q) ||
    a.capabilities.some(c => c.toLowerCase().includes(q))
  )
})

const agentTotalPages = computed(() => Math.max(1, Math.ceil(filteredAgents.value.length / agentPageSize)))

const pagedAgents = computed(() => {
  const start = (agentPage.value - 1) * agentPageSize
  return filteredAgents.value.slice(start, start + agentPageSize)
})

watch(agentSearchQuery, () => { agentPage.value = 1 })

const ICON_OPTIONS = ['📍', '🔧', '⚡', '🌐', '📡', '🖥️', '🔒', '📊', '🚀', '⭐']
const CATEGORY_OPTIONS = ['default', 'network', 'compute', 'storage', 'security', 'monitoring']
const CATEGORY_LABELS: Record<string, string> = {
  default: '默认', network: '网络', compute: '计算', storage: '存储', security: '安全', monitoring: '监控',
  datacenter: '数据中心', network_hub: '网络枢纽', agent_node: '智能体节点', custom: '自定义'
}

let amapTrafficLayer: any = null
let amapSatelliteLayer: any = null
let _amapCurrentLayerId = 'amap-standard'
let abortController: AbortController | null = null
let amapConfigCache: any = null

function dedupedFetch<T>(key: string, fn: () => Promise<T>): Promise<T> {
  if (pendingRequests.has(key)) return pendingRequests.get(key)!
  const p = fn().finally(() => pendingRequests.delete(key))
  pendingRequests.set(key, p)
  return p
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('AgentMapTileCache', 1)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains('tiles')) {
        db.createObjectStore('tiles', { keyPath: 'url' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function getCachedTile(url: string): Promise<Blob | null> {
  try {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction('tiles', 'readonly')
      const store = tx.objectStore('tiles')
      const getReq = store.get(url)
      getReq.onsuccess = () => resolve(getReq.result?.blob || null)
      getReq.onerror = () => reject(getReq.error)
    })
  } catch {
    return null
  }
}

async function setCachedTile(url: string, blob: Blob): Promise<void> {
  try {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction('tiles', 'readwrite')
      const store = tx.objectStore('tiles')
      store.put({ url, blob })
      tx.oncomplete = () => {
        cachedTilesCount.value++
        resolve()
      }
      tx.onerror = () => reject(tx.error)
    })
  } catch {
    return
  }
}

async function countCachedTiles(): Promise<number> {
  try {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction('tiles', 'readonly')
      const store = tx.objectStore('tiles')
      const countReq = store.count()
      countReq.onsuccess = () => resolve(countReq.result)
      countReq.onerror = () => reject(countReq.error)
    })
  } catch {
    return 0
  }
}

const SATELLITE_URL = 'https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}'
const SATELLITE_OPTS = { maxZoom: 18, subdomains: '1234', attribution: '© 高德地图' }
const ROAD_URL = 'https://webst0{s}.is.autonavi.com/appmaptile?style=7&x={x}&y={y}&z={z}'
const ROAD_OPTS = { maxZoom: 18, subdomains: '1234', attribution: '© 高德地图' }
const LABEL_URL = 'https://webst0{s}.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}'
const LABEL_OPTS = { maxZoom: 18, minZoom: 3, subdomains: '1234', attribution: '© 高德地图' }

const tileLayers: Record<string, L.TileLayer> = {
  standard: L.tileLayer(ROAD_URL, ROAD_OPTS),
  satellite: L.tileLayer(SATELLITE_URL, SATELLITE_OPTS),
  dark: L.tileLayer(SATELLITE_URL, SATELLITE_OPTS),
}

let activeBaseLayer: L.TileLayer | null = null
let _darkModeActive = false

let trafficOverlay: L.TileLayer | null = null
let trafficVisible = ref(false)

async function initMap() {
  abortController = new AbortController()

  if (preferAMap.value) {
    try {
      let config = amapConfigCache
      if (!config) {
        const configResp = await apiClient.get(api.map.amapConfig)
        config = configResp.data?.data || configResp.data
        if (!config?.key || config?.key_available === false) throw new Error('AMap key not configured')
        amapConfigCache = config
      }

      window._AMapSecurityConfig = { securityJsCode: config.security_code }

      const AMap = await AMapLoader.load({
        key: config.key,
        version: config.version || '2.0',
        plugins: config.plugins || ['AMap.Scale', 'AMap.ToolBar', 'AMap.PlaceSearch', 'AMap.Geolocation', 'AMap.AutoComplete', 'AMap.MarkerCluster']
      })

      const container = document.getElementById('map-container')
      if (!container) {
        throw new Error('Map container element not found in DOM')
      }
      if (container.offsetWidth === 0 || container.offsetHeight === 0) {
        await new Promise<void>(resolve => {
          const check = () => {
            if (container.offsetWidth > 0 && container.offsetHeight > 0) resolve()
            else requestAnimationFrame(check)
          }
          requestAnimationFrame(check)
        })
      }

      amapInstance.value = new AMap.Map('map-container', {
        center: [26.6470, 106.6302],
        zoom: 7,
        mapStyle: 'amap://styles/normal',
        viewMode: '2D',
        resizeEnable: true,
        lang: 'zh_cn',
      })

      amapInstance.value.addControl(new AMap.Scale())
      amapInstance.value.addControl(new AMap.ToolBar({ position: 'LB' }))

      amapInstance.value.on('click', (e: any) => {
        onMapClick({ latlng: { lat: e.lnglat.getLat(), lng: e.lnglat.getLng() } })
      })
      amapInstance.value.on('rightclick', (e: any) => {
        onMapRightClick({ latlng: { lat: e.lnglat.getLat(), lng: e.lnglat.getLng() } })
      })
      amapInstance.value.on('mousemove', (e: any) => {
        mouseCoords.value = { lat: e.lnglat.getLat().toFixed(4), lng: e.lnglat.getLng().toFixed(4) }
      })

      const tilesLoaded = await new Promise<boolean>(resolve => {
        let resolved = false
        const done = (val: boolean) => { if (!resolved) { resolved = true; resolve(val) } }
        amapInstance.value.on('complete', () => done(true))
        amapInstance.value.on('error', () => done(false))
        setTimeout(() => done(false), 5000)
      })

      if (!tilesLoaded) {
        console.warn('AMap tiles failed to load, falling back to Leaflet')
        amapInstance.value.destroy()
        amapInstance.value = null
        useAMap.value = false
        currentLayer.value = 'standard'
        isLoading.value = false
        initLeafletMap()
        return
      }

      amapLoaded.value = true
      useAMap.value = true
      isLoading.value = false

      loadAgentGeoMarkers()
      loadCustomMarkers()
      fetchRoutingDecisions()
      fetchTopology()
      startPolling()
      return
    } catch (err) {
      console.warn('AMap load failed, falling back to Leaflet:', err)
      useAMap.value = false
      currentLayer.value = 'standard'
      isLoading.value = false
      initLeafletMap()
      return
    }
  }

  useAMap.value = false
  currentLayer.value = 'standard'
  isLoading.value = false
  initLeafletMap()
}

function initLeafletMap() {
  if (!mapContainer.value) return

  map = L.map(mapContainer.value, {
    center: DEFAULT_CENTER,
    zoom: DEFAULT_ZOOM,
    zoomControl: false,
    attributionControl: false
  })

  tileLayers['standard'].addTo(map)
  activeBaseLayer = tileLayers['standard']

  L.control.zoom({ position: 'bottomleft' }).addTo(map)

  const miniContainer = document.createElement('div')
  miniContainer.className = 'custom-minimap'
  miniContainer.style.cssText = 'position:absolute;bottom:30px;right:10px;width:140px;height:110px;border-radius:8px;overflow:hidden;border:1px solid rgba(255,255,255,0.15);z-index:800;opacity:0.8;'
  minimapControl = L.map(miniContainer, {
    center: DEFAULT_CENTER,
    zoom: 3,
    zoomControl: false,
    attributionControl: false,
    dragging: false,
    scrollWheelZoom: false,
    doubleClickZoom: false
  })
  L.tileLayer(ROAD_URL, ROAD_OPTS).addTo(minimapControl)
  map.getContainer().appendChild(miniContainer)
  map.on('moveend', () => {
    if (minimapControl) minimapControl.setView(map!.getCenter(), Math.max(map!.getZoom() - 4, 2))
  })

  L.control.attribution({ position: 'bottomright', prefix: false }).addTo(map)
  map.attributionControl.addAttribution('AgentHub Map')

  map.on('click', onMapClick)
  map.on('contextmenu', onMapRightClick)
  map.on('moveend', onMapMoveEnd)
  map.on('mousemove', (e: L.LeafletMouseEvent) => {
    mouseCoords.value = { lat: e.latlng.lat.toFixed(4), lng: e.latlng.lng.toFixed(4) }
  })

  styleLeafletControls()
}

function styleLeafletControls() {
  nextTick(() => {
    if (!map) return
    const container = map.getContainer()
    const zoomCtrl = container.querySelector('.leaflet-control-zoom')
    if (zoomCtrl) {
      ;(zoomCtrl as HTMLElement).style.cssText = 'border:1px solid rgba(255,255,255,0.15)!important;border-radius:8px!important;overflow:hidden;'
      zoomCtrl.querySelectorAll('a').forEach(a => {
        ;(a as HTMLElement).style.cssText = 'background:rgba(15,23,42,0.85)!important;color:var(--color-text-secondary)!important;border-color:rgba(255,255,255,0.1)!important;backdrop-filter:blur(8px);'
      })
    }
    const attrCtrl = container.querySelector('.leaflet-control-attribution')
    if (attrCtrl) {
      ;(attrCtrl as HTMLElement).style.cssText = 'background:rgba(15,23,42,0.7)!important;color:var(--color-text-disabled)!important;font-size:10px!important;border-radius:4px!important;backdrop-filter:blur(8px);'
    }
  })
}

function switchLayer(layerId: string) {
  currentLayer.value = layerId
  if (useAMap.value && amapInstance.value) {
    switchAMapLayer(layerId)
  } else if (map) {
    switchLeafletLayer(layerId)
  }
}

function switchAMapLayer(layerId: string) {
  if (!amapInstance.value) return
  _amapCurrentLayerId = layerId

  if (amapTrafficLayer) {
    amapInstance.value.remove(amapTrafficLayer)
    amapTrafficLayer = null
    trafficVisible.value = false
  }

  if (layerId === 'amap-satellite') {
    if (!amapSatelliteLayer) {
      amapSatelliteLayer = new window.AMap.TileLayer.Satellite()
    }
    amapInstance.value.setLayers([amapSatelliteLayer])
  } else {
    const styleMap: Record<string, string> = {
      'amap-standard': 'amap://styles/normal',
      'amap-traffic': 'amap://styles/normal',
      'topology': 'amap://styles/dark',
    }
    amapInstance.value.setMapStyle(styleMap[layerId] || 'amap://styles/normal')
    if (amapSatelliteLayer) {
      amapInstance.value.remove(amapSatelliteLayer)
      amapSatelliteLayer = null
    }
    amapInstance.value.setLayers([new window.AMap.TileLayer()])
  }

  if (layerId === 'amap-traffic') {
    amapTrafficLayer = new window.AMap.TileLayer.Traffic({
      zIndex: 10,
      autoRefresh: true,
      interval: 180,
    })
    amapInstance.value.add(amapTrafficLayer)
    trafficVisible.value = true
  } else {
    trafficVisible.value = false
  }
}

function switchLeafletLayer(layerId: string) {
  if (!map) return

  if (activeBaseLayer) map.removeLayer(activeBaseLayer)

  const layerMap: Record<string, string> = {
    'standard': 'standard',
    'satellite': 'satellite',
    'topology': 'dark',
    'amap-standard': 'standard',
    'amap-satellite': 'satellite',
    'amap-traffic': 'standard',
  }

  const targetKey = layerMap[layerId] || 'standard'
  const targetLayer = tileLayers[targetKey]

  if (targetLayer) {
    targetLayer.addTo(map)
    activeBaseLayer = targetLayer
  }

  const isDark = targetKey === 'dark'
  _darkModeActive = isDark

  const tilePane = map.getContainer().querySelector('.leaflet-tile-pane')
  if (tilePane) {
    if (isDark) {
      tilePane.classList.add('dark-tiles')
    } else {
      tilePane.classList.remove('dark-tiles')
    }
  }

  if (trafficVisible.value && trafficOverlay) {
    map.removeLayer(trafficOverlay)
    trafficOverlay.addTo(map)
  }

  if (showTopologyOverlay.value && topologyLayerGroup) {
    map.removeLayer(topologyLayerGroup)
    topologyLayerGroup.addTo(map)
  }

  styleLeafletControls()
}

function toggleTrafficOverlay() {
  if (useAMap.value && amapInstance.value) {
    if (trafficVisible.value) {
      if (amapTrafficLayer) {
        amapInstance.value.remove(amapTrafficLayer)
        amapTrafficLayer = null
      }
      trafficVisible.value = false
    } else {
      if (!amapTrafficLayer) {
        amapTrafficLayer = new window.AMap.TileLayer.Traffic({
          zIndex: 10,
          autoRefresh: true,
          interval: 180,
        })
      }
      amapInstance.value.add(amapTrafficLayer)
      trafficVisible.value = true
    }
    return
  }
  if (!map) return
  if (trafficVisible.value) {
    if (trafficOverlay) map.removeLayer(trafficOverlay)
    trafficVisible.value = false
  } else {
    if (!trafficOverlay) {
      trafficOverlay = L.tileLayer(LABEL_URL, LABEL_OPTS)
    }
    trafficOverlay.addTo(map)
    trafficVisible.value = true
  }
}

function toggleFullscreen() {
  const container = useAMap.value && amapInstance.value
    ? amapInstance.value.getContainer()
    : map?.getContainer()
  if (!container) return
  if (!document.fullscreenElement) {
    container.requestFullscreen()
    isFullscreen.value = true
  } else {
    document.exitFullscreen()
    isFullscreen.value = false
  }
}

function resetView() {
  if (useAMap.value && amapInstance.value) {
    amapInstance.value.setZoomAndCenter(DEFAULT_ZOOM, DEFAULT_CENTER, false, 1000)
    return
  }
  if (!map) return
  map.flyTo(DEFAULT_CENTER, DEFAULT_ZOOM, { duration: 1 })
}

async function toggleMapEngine() {
  preferAMap.value = !preferAMap.value
  if (pollingInterval !== null) {
    clearInterval(pollingInterval)
    pollingInterval = null
  }
  if (amapInstance.value) {
    amapInstance.value.destroy()
    amapInstance.value = null
  }
  if (map) {
    map.remove()
    map = null
  }
  amapLoaded.value = false
  useAMap.value = false
  isLoading.value = true
  trafficVisible.value = false
  showTopologyOverlay.value = false
  isAddingMarker.value = false
  batchSelectMode.value = false
  selectedMarkerIds.value = new Set()
  showMarkerForm.value = false
  pendingMarkerLatLng.value = null
  Object.keys(amapMarkers).forEach(k => delete amapMarkers[k])
  Object.keys(amapPolylines).forEach(k => delete amapPolylines[k])
  amapTopologyMarkers = []
  amapTopologyPolylines = []
  amapTrafficLayer = null
  amapSatelliteLayer = null
  _amapCurrentLayerId = 'amap-standard'
  currentLayer.value = preferAMap.value ? 'amap-standard' : 'standard'
  await nextTick()
  await new Promise<void>(r => requestAnimationFrame(() => requestAnimationFrame(() => r())))
  await initMap()
  if (!useAMap.value) {
    await loadAllData()
  }
  startPolling()
}

function createAgentMarkerIcon(agent: AgentGeo): L.DivIcon {
  const isOnline = agent.status === 'online'
  const color = isOnline ? 'var(--color-success)' : 'var(--color-text-disabled)'
  const pulseHtml = isOnline ? '<div class="agent-pulse-ring" style="border-color:' + color + '"></div>' : ''
  return L.divIcon({
    className: 'agent-marker-icon',
    html: `
      <div class="agent-marker-wrapper">
        ${pulseHtml}
        <div class="agent-marker-dot" style="background:${color};box-shadow:0 0 8px ${color}80;"></div>
        <div class="agent-marker-label">${agent.agent_id.length > 10 ? agent.agent_id.slice(0, 10) + '…' : agent.agent_id}</div>
      </div>
    `,
    iconSize: [80, 40],
    iconAnchor: [40, 20]
  })
}

function addAgentMarkersToMap() {
  if (!map) return
  agentMarkers.forEach(m => map!.removeLayer(m))
  agentMarkers = []

  agentGeoList.value.forEach(agent => {
    const icon = createAgentMarkerIcon(agent)
    const marker = L.marker([agent.lat, agent.lng], { icon })
    marker.on('click', () => {
      const popupContent = createAgentPopupContent(agent)
      marker.bindPopup(popupContent, {
        className: 'agent-popup',
        maxWidth: 280,
        closeButton: true
      }).openPopup()
    })
    marker.addTo(map!)
    agentMarkers.push(marker)
  })
}

function createAgentPopupContent(agent: AgentGeo): string {
  const statusColor = agent.status === 'online' ? 'var(--color-success)' : 'var(--color-text-disabled)'
  const statusText = agent.status === 'online' ? '在线' : '离线'
  const caps = (agent.capabilities || []).slice(0, 4).map(c => `<span class="popup-cap">${c}</span>`).join('')
  return `
    <div class="agent-popup-content">
      <div class="popup-header">
        <span class="popup-status-dot" style="background:${statusColor}"></span>
        <span class="popup-agent-id">${agent.agent_id}</span>
      </div>
      <div class="popup-city">${agent.city}</div>
      <div class="popup-row"><span class="popup-label">状态</span><span style="color:${statusColor}">${statusText}</span></div>
      <div class="popup-row"><span class="popup-label">CPU</span><span>${agent.cpu_load}%</span></div>
      <div class="popup-row"><span class="popup-label">内存</span><span>${agent.memory_free} MB</span></div>
      ${agent.endpoint ? `<div class="popup-row"><span class="popup-label">端点</span><span class="popup-mono">${agent.endpoint}</span></div>` : ''}
      <div class="popup-caps">${caps}</div>
      <button class="popup-detail-btn" data-agent-id="${agent.agent_id}" aria-label="查看详情">详情</button>
    </div>
  `
}

function openAgentDetail(agentId: string) {
  const agent = agentGeoList.value.find(a => a.agent_id === agentId)
  if (agent) selectedAgent.value = agent
}

function onMapClick(e: any) {
  if (isAddingMarker.value) {
    pendingMarkerLatLng.value = e.latlng
    showMarkerForm.value = true
    isAddingMarker.value = false
    return
  }
}

function onMapRightClick(e: any) {
  const target = e.originalEvent?.target as HTMLElement
  if (!target) return
  const markerEl = target.closest('.custom-marker-icon')
  if (markerEl) {
    const markerId = markerEl.getAttribute('data-marker-id')
    if (markerId && !batchSelectMode.value) {
      deleteCustomMarker(markerId)
    }
  }
}

function onMapMoveEnd() {
  if (mapMoveThrottleTimer) return
  mapMoveThrottleTimer = window.setTimeout(() => {
    mapMoveThrottleTimer = null
  }, 500)
}

function refreshAMapAgentMarkers() {
  if (!amapInstance.value) return
  Object.keys(amapMarkers).forEach(k => {
    if (!k.startsWith('cm-')) {
      amapMarkers[k].setMap(null)
      delete amapMarkers[k]
    }
  })
  agentGeoList.value.forEach((agent: any) => {
    const isOnline = agent.status === 'online'
    const color = isOnline ? 'var(--color-success)' : '#666'
    const marker = new window.AMap.Marker({
      position: [agent.lat, agent.lng],
      title: agent.agent_id,
      content: `<div style="display:flex;flex-direction:column;align-items:center;"><div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid ${color};box-shadow:0 0 8px ${isOnline ? 'var(--color-success)80' : 'transparent'};${isOnline ? 'animation:pulse 2s infinite;' : ''}"></div><span style="color:#fff;font-size:9px;margin-top:2px;white-space:nowrap;text-shadow:0 1px 3px rgba(0,0,0,0.8),0 0 6px rgba(0,0,0,0.6);font-weight:500;">${(agent.agent_id || '').slice(0, 12)}</span></div>`,
      offset: new window.AMap.Pixel(-20, -20),
    })
    marker.on('click', () => {
      const statusText = isOnline ? '在线' : '离线'
      const statusColor = isOnline ? 'var(--color-success)' : 'var(--color-text-disabled)'
      const caps = (agent.capabilities || []).slice(0, 4).map((c: string) => `<span style="font-size:9px;padding:1px 6px;border-radius:4px;background:rgba(59,130,246,0.15);color:var(--color-primary);">${c}</span>`).join(' ')
      const info = new window.AMap.InfoWindow({
        content: `<div style="padding:10px;color:var(--color-text-secondary);min-width:220px;"><div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;"><span style="width:8px;height:8px;border-radius:50%;background:${statusColor};"></span><span style="font-size:13px;font-weight:600;color:#fff;font-family:monospace;">${agent.agent_id}</span></div><div style="font-size:11px;color:var(--color-text-tertiary);margin-bottom:6px;">${agent.city}</div><div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;"><span style="color:var(--color-text-disabled);">状态</span><span style="color:${statusColor};">${statusText}</span></div><div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;"><span style="color:var(--color-text-disabled);">CPU</span><span>${agent.cpu_load}%</span></div><div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;"><span style="color:var(--color-text-disabled);">内存</span><span>${agent.memory_free} MB</span></div><div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:3px;">${caps}</div></div>`,
        offset: new window.AMap.Pixel(0, -25),
      })
      info.open(amapInstance.value, marker.getPosition())
      selectedAgent.value = agent
    })
    marker.setMap(amapInstance.value)
    amapMarkers[agent.agent_id] = marker
  })
}

async function fetchAgentGeo() {
  try {
    const res = await dedupedFetch('agentGeo', () =>
      apiClient.get<AgentGeo[]>(api.map.agentsGeo)
    )
    const data = (res.data as any)?.data || res.data || []
    agentGeoList.value = data.length > 0 ? data : loadMockAgentGeo()
    lastDataUpdate.value = new Date()
    if (useAMap.value && amapInstance.value) {
      refreshAMapAgentMarkers()
    } else {
      addAgentMarkersToMap()
    }
  } catch {
    agentGeoList.value = loadMockAgentGeo()
    if (useAMap.value && amapInstance.value) {
      refreshAMapAgentMarkers()
    } else {
      addAgentMarkersToMap()
    }
  }
}

function loadMockAgentGeo(): AgentGeo[] {
  return [
    { agent_id: 'agenthub-local', lat: 26.647, lng: 106.63, city: '贵阳', status: 'online', capabilities: ['intent_parsing', 'qos_config', 'event_diagnosis', 'policy_planning', 'execution'], cpu_load: 0, memory_free: 100 },
    { agent_id: 'agent_bandwidth_guarantor', lat: 39.9, lng: 116.4, city: '北京', status: 'online', capabilities: ['qos_config', 'intent_parsing'], cpu_load: 12.5, memory_free: 90 },
    { agent_id: 'agent_fault_diagnostician', lat: 31.2, lng: 121.5, city: '上海', status: 'online', capabilities: ['event_diagnosis', 'intent_parsing'], cpu_load: 28.3, memory_free: 77.4 },
    { agent_id: 'agent_config_generator', lat: 23.1, lng: 113.3, city: '广州', status: 'online', capabilities: ['execution', 'policy_planning'], cpu_load: 45.7, memory_free: 63.4 },
    { agent_id: 'agent_security_scanner', lat: 22.5, lng: 114.1, city: '深圳', status: 'online', capabilities: ['event_diagnosis', 'execution'], cpu_load: 33.2, memory_free: 73.4 },
    { agent_id: 'agent_healing_executor', lat: 30.6, lng: 104.1, city: '成都', status: 'online', capabilities: ['execution', 'event_diagnosis'], cpu_load: 21.8, memory_free: 82.6 },
    { agent_id: 'agent_topology_analyzer', lat: 30.6, lng: 114.3, city: '武汉', status: 'online', capabilities: ['policy_planning', 'intent_parsing'], cpu_load: 15.6, memory_free: 87.5 },
    { agent_id: 'agent_sla_predictor', lat: 32.1, lng: 118.8, city: '南京', status: 'online', capabilities: ['qos_config', 'policy_planning'], cpu_load: 38.4, memory_free: 69.3 },
    { agent_id: 'agent_intent_parser', lat: 30.3, lng: 120.2, city: '杭州', status: 'online', capabilities: ['intent_parsing', 'qos_config'], cpu_load: 9.2, memory_free: 92.6 },
    { agent_id: 'agent_traffic_shaper', lat: 34.3, lng: 108.9, city: '西安', status: 'online', capabilities: ['qos_config', 'execution'], cpu_load: 52.1, memory_free: 58.3 },
    { agent_id: 'agent_link_manager', lat: 29.6, lng: 106.5, city: '重庆', status: 'online', capabilities: ['policy_planning', 'execution'], cpu_load: 27.9, memory_free: 77.7 },
    { agent_id: 'agent_performance_monitor', lat: 28.2, lng: 113.0, city: '长沙', status: 'online', capabilities: ['qos_config', 'event_diagnosis'], cpu_load: 18.5, memory_free: 85.2 },
    { agent_id: 'agent_access_controller', lat: 26.6, lng: 106.7, city: '贵阳', status: 'online', capabilities: ['execution', 'policy_planning'], cpu_load: 41.3, memory_free: 67.0 },
  ]
}

async function loadAgentGeoMarkers() {
  try {
    const resp = await apiClient.get(api.map.agentsGeo)
    const agents = resp.data?.data || resp.data || []
    agentGeoList.value = agents.length > 0 ? agents : loadMockAgentGeo()
    if (useAMap.value && amapInstance.value) {
      Object.keys(amapMarkers).forEach(k => {
        if (!k.startsWith('cm-')) {
          amapMarkers[k].setMap(null)
          delete amapMarkers[k]
        }
      })
      agentGeoList.value.forEach((agent: any) => {
        const isOnline = agent.status === 'online'
        const color = isOnline ? 'var(--color-success)' : '#666'
        const marker = new window.AMap.Marker({
          position: [agent.lat, agent.lng],
          title: agent.agent_id,
          content: `<div style="display:flex;flex-direction:column;align-items:center;"><div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid ${color};box-shadow:0 0 8px ${isOnline ? 'var(--color-success)80' : 'transparent'};${isOnline ? 'animation:pulse 2s infinite;' : ''}"></div><span style="color:#fff;font-size:9px;margin-top:2px;white-space:nowrap;text-shadow:0 1px 3px rgba(0,0,0,0.8),0 0 6px rgba(0,0,0,0.6);font-weight:500;">${(agent.agent_id || '').slice(0, 12)}</span></div>`,
          offset: new window.AMap.Pixel(-20, -20),
        })
        marker.on('click', () => {
          const statusText = isOnline ? '在线' : '离线'
          const statusColor = isOnline ? 'var(--color-success)' : 'var(--color-text-disabled)'
          const caps = (agent.capabilities || []).slice(0, 4).map((c: string) => `<span style="font-size:9px;padding:1px 6px;border-radius:4px;background:rgba(59,130,246,0.15);color:var(--color-primary);">${c}</span>`).join(' ')
          const info = new window.AMap.InfoWindow({
            content: `<div style="padding:10px;color:var(--color-text-secondary);min-width:220px;"><div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;"><span style="width:8px;height:8px;border-radius:50%;background:${statusColor};"></span><span style="font-size:13px;font-weight:600;color:#fff;font-family:monospace;">${agent.agent_id}</span></div><div style="font-size:11px;color:var(--color-text-tertiary);margin-bottom:6px;">${agent.city}</div><div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;"><span style="color:var(--color-text-disabled);">状态</span><span style="color:${statusColor};">${statusText}</span></div><div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;"><span style="color:var(--color-text-disabled);">CPU</span><span>${agent.cpu_load}%</span></div><div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;"><span style="color:var(--color-text-disabled);">内存</span><span>${agent.memory_free} MB</span></div><div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:3px;">${caps}</div></div>`,
            offset: new window.AMap.Pixel(0, -25),
          })
          info.open(amapInstance.value, marker.getPosition())
          selectedAgent.value = agent
        })
        marker.setMap(amapInstance.value)
        amapMarkers[agent.agent_id] = marker
      })
    } else if (map) {
      addAgentMarkersToMap()
    }
  } catch (err) {
    agentGeoList.value = loadMockAgentGeo()
    if (useAMap.value && amapInstance.value) {
      refreshAMapAgentMarkers()
    } else if (map) {
      addAgentMarkersToMap()
    }
  }
}

async function fetchRoutingDecisions() {
  // Load initial routing decisions as demo data
  routingDecisions.value = [
    {
      selected_agent: { agent_id: 'agent_bandwidth_guarantor', capabilities: ['qos_config', 'intent_parsing'], status: 'online', cpu_load: 12.5, memory_free: 90 },
      matched_capabilities: ['qos_config'],
      capability_scores: { qos_config: 0.8 },
      load_score: 0.88,
      total_score: 0.83,
      explanation: '意图文本匹配到能力: qos_config; 选择Agent: agent_bandwidth_guarantor; 能力匹配分数: 0.83 (能力权重0.7, 负载权重0.3); 负载评分: 0.88 (CPU: 12.5%); 候选Agent数: 1',
      candidates_count: 1,
    },
    {
      selected_agent: { agent_id: 'agent_fault_diagnostician', capabilities: ['event_diagnosis', 'intent_parsing'], status: 'online', cpu_load: 28.3, memory_free: 77.4 },
      matched_capabilities: ['event_diagnosis'],
      capability_scores: { event_diagnosis: 0.7 },
      load_score: 0.72,
      total_score: 0.71,
      explanation: '意图文本匹配到能力: event_diagnosis; 选择Agent: agent_fault_diagnostician; 能力匹配分数: 0.71 (能力权重0.7, 负载权重0.3); 负载评分: 0.72 (CPU: 28.3%); 候选Agent数: 1',
      candidates_count: 1,
    },
  ]
}

async function fetchTopology() {
  try {
    const res = await dedupedFetch('topology', () =>
      apiClient.get<TopologyData>(api.crossDomain.topology)
    )
    topology.value = res.data || { nodes: [], edges: [] }
  } catch {
    topology.value = { nodes: [], edges: [] }
  }
}

async function fetchCustomMarkers() {
  try {
    const res = await dedupedFetch('customMarkers', () =>
      apiClient.get<CustomMarker[]>(api.map.markers)
    )
    customMarkers.value = (res.data as any)?.data || res.data || []
    addCustomMarkersToMap()
  } catch {
    customMarkers.value = []
  }
}

function addCustomMarkersToMap() {
  if (useAMap.value && amapInstance.value) {
    Object.keys(amapMarkers).forEach(k => {
      if (k.startsWith('cm-')) {
        amapMarkers[k].setMap(null)
        delete amapMarkers[k]
      }
    })
    customMarkers.value.forEach(cm => {
      const marker = new window.AMap.Marker({
        position: [cm.lat, cm.lng],
        title: cm.title,
        content: `<div style="display:flex;flex-direction:column;align-items:center;"><span style="font-size:18px;filter:drop-shadow(0 2px 4px rgba(0,0,0,0.5));">${cm.icon || '📍'}</span><span style="color:#fff;font-size:9px;white-space:nowrap;text-shadow:0 1px 3px rgba(0,0,0,0.8);">${(cm.title || '').slice(0, 8)}</span></div>`,
        offset: new window.AMap.Pixel(-15, -20),
      })
      marker.on('click', () => {
        const info = new window.AMap.InfoWindow({
          content: `<div style="padding:8px;color:var(--color-text-secondary);font-size:13px;min-width:160px;"><div style="font-weight:600;margin-bottom:4px;">${cm.icon} ${cm.title}</div><div style="font-size:11px;color:var(--color-text-tertiary);">${cm.description || '无描述'}</div><div style="font-size:10px;color:var(--color-text-disabled);margin-top:4px;">分类: ${CATEGORY_LABELS[cm.category] || cm.category}</div>${canWrite.value ? '<div style="margin-top:6px;"><button class="delete-marker-btn" data-marker-id="' + cm.id + '" style="font-size:11px;padding:2px 8px;border-radius:4px;border:1px solid var(--color-error);color:var(--color-error);background:transparent;cursor:pointer;" aria-label="删除标记">删除标记</button></div>' : ''}</div>`,
          offset: new window.AMap.Pixel(0, -25),
        })
        info.open(amapInstance.value, marker.getPosition())
      })
      marker.setMap(amapInstance.value)
      amapMarkers['cm-' + cm.id] = marker
    })
    return
  }
  if (!map) return
  customLeafletMarkers.forEach(m => map!.removeLayer(m))
  customLeafletMarkers = []

  customMarkers.value.forEach(cm => {
    const icon = L.divIcon({
      className: 'custom-marker-icon',
      html: `<div class="custom-marker-wrapper" data-marker-id="${cm.id}">
        <span class="custom-marker-emoji">${cm.icon || '📍'}</span>
        <span class="custom-marker-title">${cm.title}</span>
        ${batchSelectMode.value ? `<input type="checkbox" class="marker-checkbox" data-id="${cm.id}" ${selectedMarkerIds.value.has(cm.id) ? 'checked' : ''}/>` : ''}
      </div>`,
      iconSize: [60, 36],
      iconAnchor: [30, 18]
    })
    const marker = L.marker([cm.lat, cm.lng], { icon })
    marker.bindPopup(`
      <div class="custom-popup-content">
        <div class="custom-popup-title">${cm.icon} ${cm.title}</div>
        <div class="custom-popup-desc">${cm.description || '无描述'}</div>
        <div class="custom-popup-cat">分类: ${CATEGORY_LABELS[cm.category] || cm.category}</div>
      </div>
    `, { className: 'custom-marker-popup', maxWidth: 220 })
    marker.on('contextmenu', (e: L.LeafletMouseEvent) => {
      if (!canWrite.value) return
      L.DomEvent.stopPropagation(e)
      deleteCustomMarker(cm.id)
    })
    marker.addTo(map!)
    customLeafletMarkers.push(marker)
  })
}

async function saveCustomMarker() {
  if (!pendingMarkerLatLng.value || !newMarkerForm.value.title.trim()) {
    showToast('请填写标记标题', 'warning')
    return
  }
  try {
    const payload = {
      id: 'cm-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8),
      lat: pendingMarkerLatLng.value.lat,
      lng: pendingMarkerLatLng.value.lng,
      title: newMarkerForm.value.title.trim(),
      description: newMarkerForm.value.description.trim(),
      icon: newMarkerForm.value.icon,
      category: newMarkerForm.value.category
    }
    await apiClient.post(api.map.markersBatch, { markers: [payload] })
    showToast('标记已保存', 'success')
    showMarkerForm.value = false
    newMarkerForm.value = { title: '', description: '', category: 'default', icon: '📍' }
    pendingMarkerLatLng.value = null
    await fetchCustomMarkers()
  } catch {
    showToast('保存标记失败', 'error')
  }
}

async function deleteCustomMarker(id: string) {
  try {
    await apiClient.delete(api.map.markerById(id))
    showToast('标记已删除', 'success')
    await fetchCustomMarkers()
  } catch {
    showToast('删除标记失败', 'error')
  }
}

async function batchDeleteSelectedMarkers() {
  if (selectedMarkerIds.value.size === 0) return
  try {
    const ids = Array.from(selectedMarkerIds.value)
    await Promise.all(ids.map(id => apiClient.delete(api.map.markerById(id))))
    showToast(`已删除 ${ids.length} 个标记`, 'success')
    selectedMarkerIds.value = new Set()
    batchSelectMode.value = false
    await fetchCustomMarkers()
  } catch {
    showToast('批量删除失败', 'error')
  }
}

function startAddingMarker() {
  isAddingMarker.value = true
  showToast('点击地图放置标记', 'info')
}

function cancelAddingMarker() {
  isAddingMarker.value = false
  showMarkerForm.value = false
  pendingMarkerLatLng.value = null
}

function onSearchInput() {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = window.setTimeout(() => {
    performSearch()
  }, 300)
}

async function performSearch() {
  const q = searchQuery.value.trim()
  if (!q) {
    poiResults.value = []
    searchDropdownOpen.value = false
    return
  }
  if (useAMap.value) {
    const amapResult = await searchPOIWithAMap(q)
    if (amapResult) return
  }
  try {
    const res = await apiClient.get<POI[]>(`${api.map.poiSearch}?q=${encodeURIComponent(q)}`)
    poiResults.value = (res.data as any)?.data || res.data || []
    searchDropdownOpen.value = poiResults.value.length > 0
  } catch {
    poiResults.value = []
    searchDropdownOpen.value = false
  }
}

async function searchPOIWithAMap(query: string) {
  if (!window.AMap?.PlaceSearch) return false
  const placeSearch = new window.AMap.PlaceSearch({ pageSize: 20, pageIndex: 1 })
  return new Promise((resolve) => {
    placeSearch.search(query, (status: string, result: any) => {
      if (status === 'complete' && result.poiList?.pois) {
        poiResults.value = result.poiList.pois.map((p: any) => ({
          id: p.id,
          name: p.name,
          category: p.type || '',
          lat: p.location?.lat || 0,
          lng: p.location?.lng || 0,
          address: p.address || p.cityname || '',
          description: p.adname || '',
        }))
        searchDropdownOpen.value = poiResults.value.length > 0
        resolve(true)
      } else {
        resolve(false)
      }
    })
  })
}

function flyToPOI(poi: POI) {
  if (useAMap.value && amapInstance.value) {
    amapInstance.value.setZoomAndCenter(14, [poi.lat, poi.lng], false, 1000)
    const displayName = poi.display_name || poi.name || poi.description || ''
    const info = new window.AMap.InfoWindow({
      content: `<div style="padding:10px;color:var(--color-text-secondary);min-width:180px;"><div style="font-size:14px;font-weight:600;margin-bottom:4px;">${displayName}</div><div style="font-size:11px;padding:2px 8px;border-radius:4px;background:rgba(245,158,11,0.15);color:var(--color-warning);display:inline-block;margin-bottom:4px;">${CATEGORY_LABELS[poi.category] || poi.category}</div><div style="font-size:11px;color:var(--color-text-tertiary);">${poi.address || ''}</div>${poi.description ? `<div style="font-size:11px;color:var(--color-text-disabled);margin-top:4px;">${poi.description}</div>` : ''}</div>`,
      offset: new window.AMap.Pixel(0, -30),
    })
    info.open(amapInstance.value, [poi.lat, poi.lng])
    searchDropdownOpen.value = false
    searchQuery.value = ''
    return
  }
  if (!map) return
  map.flyTo([poi.lat, poi.lng], 14, { duration: 1.2 })
  searchDropdownOpen.value = false
  searchQuery.value = ''

  poiMarkers.forEach(m => map!.removeLayer(m))
  poiMarkers = []

  const icon = L.divIcon({
    className: 'poi-marker-icon',
    html: '<div class="poi-marker-dot"></div>',
    iconSize: [24, 24],
    iconAnchor: [12, 12]
  })
  const marker = L.marker([poi.lat, poi.lng], { icon })
  marker.bindPopup(`
    <div class="poi-popup-content">
      <div class="poi-popup-name">${poi.display_name || poi.name}</div>
      <div class="poi-popup-cat">${CATEGORY_LABELS[poi.category] || poi.category}</div>
      <div class="poi-popup-addr">${poi.address}</div>
      ${poi.description ? `<div class="poi-popup-desc">${poi.description}</div>` : ''}
    </div>
  `, { className: 'poi-popup', maxWidth: 240 })
  marker.addTo(map)
  poiMarkers.push(marker)
  marker.openPopup()
}

let amapTopologyMarkers: any[] = []
let amapTopologyPolylines: any[] = []

function toggleTopologyOverlay() {
  if (useAMap.value && amapInstance.value) {
    if (showTopologyOverlay.value) {
      clearAMapTopology()
      showTopologyOverlay.value = false
    } else {
      renderAMapTopologyOverlay()
      showTopologyOverlay.value = true
    }
    return
  }
  if (!map) return
  if (showTopologyOverlay.value) {
    if (topologyLayerGroup) {
      map.removeLayer(topologyLayerGroup)
      topologyLayerGroup = null
    }
    showTopologyOverlay.value = false
  } else {
    renderTopologyOverlay()
    showTopologyOverlay.value = true
  }
}

function clearAMapTopology() {
  amapTopologyMarkers.forEach(m => m.setMap(null))
  amapTopologyPolylines.forEach(m => m.setMap(null))
  amapTopologyMarkers = []
  amapTopologyPolylines = []
}

function renderAMapTopologyOverlay() {
  if (!amapInstance.value || topology.value.nodes.length === 0) return
  clearAMapTopology()
  const center = amapInstance.value.getCenter()
  const nodes = topology.value.nodes
  const positions: Record<string, { lat: number; lng: number }> = {}
  const localNode = nodes.find(n => n.type === 'local')
  if (localNode) {
    positions[localNode.id] = { lat: center.lat, lng: center.lng }
  }
  const remoteNodes = nodes.filter(n => n.type !== 'local')
  const count = remoteNodes.length
  remoteNodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2
    const offset = 0.08
    positions[node.id] = {
      lat: center.lat + offset * Math.sin(angle),
      lng: center.lng + offset * Math.cos(angle),
    }
  })
  topology.value.edges.forEach(edge => {
    const from = positions[edge.source]
    const to = positions[edge.target]
    if (from && to) {
      const polyline = new window.AMap.Polyline({
        path: [[from.lat, from.lng], [to.lat, to.lng]],
        strokeColor: 'var(--color-primary)',
        strokeWeight: 2,
        strokeOpacity: 0.5,
        strokeStyle: 'dashed',
        strokeDasharray: [6, 4],
      })
      polyline.setMap(amapInstance.value)
      amapTopologyPolylines.push(polyline)
    }
  })
  nodes.forEach(node => {
    const pos = positions[node.id]
    if (!pos) return
    const color = node.status === 'online' ? 'var(--color-success)' : 'var(--color-text-disabled)'
    const marker = new window.AMap.Marker({
      position: [pos.lat, pos.lng],
      content: `<div style="display:flex;flex-direction:column;align-items:center;padding:4px 8px;border-radius:8px;border:1.5px solid ${color};background:${color}20;backdrop-filter:blur(4px);"><span style="width:6px;height:6px;border-radius:50%;background:${color};margin-bottom:2px;"></span><span style="font-size:8px;color:var(--color-text-secondary);font-weight:600;white-space:nowrap;text-shadow:0 1px 3px rgba(0,0,0,0.8);">${(node.label || node.id || '').slice(0, 8)}</span></div>`,
      offset: new window.AMap.Pixel(-35, -15),
    })
    marker.setMap(amapInstance.value)
    amapTopologyMarkers.push(marker)
  })
}

function renderTopologyOverlay() {
  if (!map || topology.value.nodes.length === 0) return
  if (topologyLayerGroup) map.removeLayer(topologyLayerGroup)
  topologyLayerGroup = L.layerGroup()

  const nodes = topology.value.nodes
  const positions: Record<string, L.LatLng> = {}

  const localNode = nodes.find(n => n.type === 'local')
  if (localNode) {
    positions[localNode.id] = map.getCenter()
  }

  const remoteNodes = nodes.filter(n => n.type !== 'local')
  const count = remoteNodes.length
  remoteNodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2
    const offset = 0.08
    positions[node.id] = L.latLng(
      map!.getCenter().lat + offset * Math.sin(angle),
      map!.getCenter().lng + offset * Math.cos(angle)
    )
  })

  topology.value.edges.forEach(edge => {
    const from = positions[edge.source]
    const to = positions[edge.target]
    if (from && to) {
      L.polyline([from, to], {
        color: 'var(--color-primary)',
        weight: 2,
        opacity: 0.5,
        dashArray: '6, 4'
      }).addTo(topologyLayerGroup!)
    }
  })

  nodes.forEach(node => {
    const pos = positions[node.id]
    if (!pos) return
    const color = node.status === 'online' ? 'var(--color-success)' : 'var(--color-text-disabled)'
    const icon = L.divIcon({
      className: 'topology-node-icon',
      html: `<div class="topo-node" style="border-color:${color};background:${color}20">
        <span class="topo-node-dot" style="background:${color}"></span>
        <span class="topo-node-label">${(node.label || node.id || '').slice(0, 8)}</span>
      </div>`,
      iconSize: [70, 30],
      iconAnchor: [35, 15]
    })
    L.marker(pos, { icon }).addTo(topologyLayerGroup!)
  })

  topologyLayerGroup.addTo(map)
}

async function routeIntent() {
  if (!routeInput.value.trim()) return
  const intentText = routeInput.value.trim()
  try {
    const res = await apiClient.post(api.crossDomain.route, {
      intent_text: intentText
    })
    const data = (res.data as any)?.data || res.data
    if (data) {
      const decision: RoutingDecision = {
        intent_text: intentText,
        selected_agent: data.selected_agent || null,
        matched_capabilities: data.matched_capabilities || [],
        capability_scores: data.capability_scores || {},
        load_score: data.load_score || 0,
        total_score: data.total_score || 0,
        explanation: data.explanation || '',
        candidates_count: data.candidates_count || 0,
        timestamp: new Date().toLocaleTimeString('zh-CN'),
      }
      routingDecisions.value.unshift(decision)
      showToast('路由决策完成', 'success')
    }
    routeInput.value = ''
  } catch {
    // Fallback: generate local routing decision
    const decision: RoutingDecision = {
      intent_text: intentText,
      selected_agent: { agent_id: 'agenthub-local', capabilities: ['intent_parsing', 'qos_config', 'event_diagnosis', 'policy_planning', 'execution'], status: 'online', cpu_load: 0, memory_free: 100 },
      matched_capabilities: ['intent_parsing'],
      capability_scores: { intent_parsing: 0.5 },
      load_score: 1.0,
      total_score: 0.65,
      explanation: '本地路由: 后端路由服务不可用，已回退到本地AgentHub节点',
      candidates_count: 1,
      timestamp: new Date().toLocaleTimeString('zh-CN'),
    }
    routingDecisions.value.unshift(decision)
    routeInput.value = ''
    showToast('路由决策完成(本地回退)', 'warning')
  }
}

async function addAgent() {
  const form = newAgentForm.value
  if (!form.agent_id.trim() || !form.city.trim()) {
    showToast('Agent ID 和城市为必填项', 'error')
    return
  }
  try {
    const caps = form.capabilities.split(',').map(s => s.trim()).filter(Boolean)
    await apiClient.post(api.map.agentRegister, {
      agent_id: form.agent_id.trim(),
      capabilities: caps,
      lat: form.lat || 0,
      lng: form.lng || 0,
      city: form.city.trim(),
      endpoint: form.endpoint.trim(),
    })
    showToast('Agent 添加成功', 'success')
    showAddAgentModal.value = false
    newAgentForm.value = { agent_id: '', city: '', lat: 0, lng: 0, capabilities: '', endpoint: '' }
    await fetchAgentGeo()
  } catch {
    showToast('Agent 添加失败', 'error')
  }
}

function flyToAgent(agent: AgentGeo) {
  if (useAMap.value && amapInstance.value) {
    amapInstance.value.setZoomAndCenter(10, [agent.lat, agent.lng], false, 1000)
    selectedAgent.value = agent
    return
  }
  if (!map) return
  map.flyTo([agent.lat, agent.lng], 10, { duration: 1 })
  const marker = agentMarkers.find(m => {
    const ll = m.getLatLng()
    return Math.abs(ll.lat - agent.lat) < 0.001 && Math.abs(ll.lng - agent.lng) < 0.001
  })
  if (marker) marker.openPopup()
}

async function downloadOfflineTiles() {
  if (isDownloadingOffline.value) return
  isDownloadingOffline.value = true
  offlineDownloadProgress.value = 0

  let boundsObj: { north: number; south: number; east: number; west: number } = { north: 0, south: 0, east: 0, west: 0 }

  if (useAMap.value && amapInstance.value) {
    const b = amapInstance.value.getBounds()
    boundsObj = {
      north: b.northEast.lat,
      south: b.southWest.lat,
      east: b.northEast.lng,
      west: b.southWest.lng,
    }
  } else if (map) {
    const b = map.getBounds()
    boundsObj = {
      north: b.getNorth(),
      south: b.getSouth(),
      east: b.getEast(),
      west: b.getWest(),
    }
  } else {
    isDownloadingOffline.value = false
    return
  }

  let totalTiles = 0
  let completedTiles = 0

  const tileCoords: { z: number; x: number; y: number }[] = []
  for (let z = 3; z <= 8; z++) {
    const latRad = Math.PI / 180
    const n = Math.pow(2, z)
    const xMin = Math.floor((boundsObj.west + 180) / 360 * n)
    const xMax = Math.floor((boundsObj.east + 180) / 360 * n)
    const yMin = Math.floor((1 - Math.log(Math.tan(boundsObj.north * latRad) + 1 / Math.cos(boundsObj.north * latRad)) / Math.PI) / 2 * n)
    const yMax = Math.floor((1 - Math.log(Math.tan(boundsObj.south * latRad) + 1 / Math.cos(boundsObj.south * latRad)) / Math.PI) / 2 * n)
    for (let x = xMin; x <= xMax; x++) {
      for (let y = Math.min(yMin, yMax); y <= Math.max(yMin, yMax); y++) {
        tileCoords.push({ z, x, y })
      }
    }
  }

  totalTiles = tileCoords.length
  if (totalTiles === 0) {
    isDownloadingOffline.value = false
    return
  }

  const batchSize = 10
  const styles = [6, 7, 8]
  totalTiles = tileCoords.length * styles.length
  for (const style of styles) {
    for (let i = 0; i < tileCoords.length; i += batchSize) {
      const batch = tileCoords.slice(i, i + batchSize)
      await Promise.all(batch.map(async (tc) => {
        const s = ['1','2','3','4'][Math.floor(Math.random()*4)]
        const url = `https://webst0${s}.is.autonavi.com/appmaptile?style=${style}&x=${tc.x}&y=${tc.y}&z=${tc.z}`
        try {
          const cached = await getCachedTile(url)
          if (!cached) {
            const res = await fetch(url, { mode: 'cors' })
            if (res.ok) {
              const blob = await res.blob()
              await setCachedTile(url, blob)
            }
          }
        } catch {}
        completedTiles++
      }))
      offlineDownloadProgress.value = Math.round((completedTiles / totalTiles) * 100)
    }
  }

  isDownloadingOffline.value = false
  offlineDownloadProgress.value = 100
  showToast(`离线地图下载完成，共 ${totalTiles} 个瓦片`, 'success')
}

let loadRetryCount = 0
const MAX_LOAD_RETRIES = 5

async function loadAllData() {
  isLoading.value = true
  try {
    await Promise.all([
      fetchAgentGeo(),
      fetchRoutingDecisions(),
      fetchTopology(),
      fetchCustomMarkers()
    ])
    lastDataUpdate.value = new Date()
    loadRetryCount = 0
  } catch {
    loadRetryCount++
    if (loadRetryCount < MAX_LOAD_RETRIES) {
      showToast(`数据加载失败，5秒后自动重试 (${loadRetryCount}/${MAX_LOAD_RETRIES})...`, 'error')
      setTimeout(loadAllData, 5000)
    } else {
      showToast('数据加载多次失败，请检查网络连接后刷新页面', 'error')
      loadRetryCount = 0
    }
  } finally {
    isLoading.value = false
  }
}

function handleFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}

function closeAgentDetail() {
  selectedAgent.value = null
}

function toggleBatchSelect() {
  batchSelectMode.value = !batchSelectMode.value
  if (!batchSelectMode.value) {
    selectedMarkerIds.value = new Set()
  }
  addCustomMarkersToMap()
}

function startPolling() {
  if (pollingInterval !== null) return
  pollingInterval = window.setInterval(() => {
    Promise.all([fetchAgentGeo(), fetchTopology()]).then(() => {
      lastDataUpdate.value = new Date()
    })
  }, 15000)
}

function loadCustomMarkers() {
  fetchCustomMarkers()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (isAddingMarker.value) cancelAddingMarker()
    else if (searchDropdownOpen.value) searchDropdownOpen.value = false
    else if (selectedAgent.value) closeAgentDetail()
    else if (showMarkerForm.value) cancelAddingMarker()
  }
}

function handleClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (searchDropdownOpen.value && !target.closest('.search-wrapper')) {
    searchDropdownOpen.value = false
  }
}

function handleDelegatedClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  const detailBtn = target.closest('.popup-detail-btn') as HTMLElement | null
  if (detailBtn) {
    const agentId = detailBtn.getAttribute('data-agent-id')
    if (agentId) openAgentDetail(agentId)
    return
  }
  const deleteBtn = target.closest('.delete-marker-btn') as HTMLElement | null
  if (deleteBtn) {
    const markerId = deleteBtn.getAttribute('data-marker-id')
    if (markerId) deleteCustomMarker(markerId)
    return
  }
}

onMounted(async () => {
  document.addEventListener('fullscreenchange', handleFullscreenChange)
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('click', handleClickOutside)
  document.addEventListener('click', handleDelegatedClick)
  cachedTilesCount.value = await countCachedTiles()
  await nextTick()
  await new Promise<void>(r => requestAnimationFrame(() => requestAnimationFrame(() => r())))
  await initMap()
  if (!useAMap.value) {
    await loadAllData()
    startPolling()
  }
  playEntranceAnimation()
})

onUnmounted(() => {
  entranceCtx?.revert()
  if (pollingInterval !== null) clearInterval(pollingInterval)
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  if (mapMoveThrottleTimer) clearTimeout(mapMoveThrottleTimer)
  if (abortController) abortController.abort()
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('click', handleDelegatedClick)
  if (amapTrafficLayer) {
    amapTrafficLayer.setMap(null)
    amapTrafficLayer = null
  }
  if (amapSatelliteLayer) {
    amapSatelliteLayer = null
  }
  if (amapInstance.value) {
    amapInstance.value.destroy()
    amapInstance.value = null
  }
  if (map) {
    map.remove()
    map = null
  }
})

watch(showTopologyOverlay, (val) => {
  if (val) {
    if (useAMap.value && amapInstance.value) {
      renderAMapTopologyOverlay()
    } else if (map) {
      renderTopologyOverlay()
    }
  }
})
</script>

<template>
  <div class="agent-map">
    <div class="am-bg">
      <div class="bg-grid"></div>
      <div class="bg-glow glow-1"></div>
      <div class="bg-glow glow-2"></div>
    </div>

    <div class="am-toolbar">
      <div class="toolbar-left">
        <h1 class="page-title">智能体中心</h1>
        <div class="layer-switcher">
          <template v-if="useAMap">
            <button type="button" :class="['layer-btn', { active: currentLayer === 'amap-standard' }]" @click="switchLayer('amap-standard')" aria-label="标准地图">标准</button>
            <button type="button" :class="['layer-btn', { active: currentLayer === 'amap-satellite' }]" @click="switchLayer('amap-satellite')" aria-label="卫星地图">卫星</button>
            <button type="button" :class="['layer-btn', { active: currentLayer === 'amap-traffic' }]" @click="switchLayer('amap-traffic')" aria-label="路况地图">路况</button>
            <button type="button" :class="['layer-btn', { active: currentLayer === 'topology' }]" @click="switchLayer('topology')" aria-label="暗色地图">暗色</button>
          </template>
          <template v-else>
            <button type="button" :class="['layer-btn', { active: currentLayer === 'standard' }]" @click="switchLayer('standard')" aria-label="标准地图">标准</button>
            <button type="button" :class="['layer-btn', { active: currentLayer === 'satellite' }]" @click="switchLayer('satellite')" aria-label="卫星地图">卫星</button>
            <button type="button" :class="['layer-btn', { active: currentLayer === 'topology' }]" @click="switchLayer('topology')" aria-label="暗色地图">暗色</button>
          </template>
        </div>
        <button type="button" :class="['toolbar-btn', { active: trafficVisible }]" @click="toggleTrafficOverlay" aria-label="叠加路况">
          🚦 叠加
        </button>
        <button type="button" :class="['toolbar-btn', { active: showTopologyOverlay }]" @click="toggleTopologyOverlay" aria-label="拓扑叠加">
          🔗 拓扑
        </button>
      </div>
      <div class="toolbar-center">
        <div class="search-wrapper">
          <input
            v-model="searchQuery"
            type="text"
            class="search-input"
            placeholder="搜索城市、数据中心、节点..."
            @input="onSearchInput"
            @focus="searchDropdownOpen = poiResults.length > 0"
          />
          <div v-if="searchDropdownOpen" class="search-dropdown">
            <div
              v-for="poi in poiResults"
              :key="poi.id"
              class="search-result-item"
              @click="flyToPOI(poi)"
            >
              <span class="poi-name">{{ poi.display_name || poi.name }}</span>
              <span class="poi-cat">{{ CATEGORY_LABELS[poi.category] || poi.category }}</span>
            </div>
            <div v-if="poiResults.length === 0" class="search-empty">无搜索结果</div>
          </div>
        </div>
      </div>
      <div class="toolbar-right">
        <button type="button" v-if="canWrite" :class="['toolbar-btn', { active: isAddingMarker }]" @click="startAddingMarker" aria-label="添加标记">
          📍 添加标记
        </button>
        <button type="button" :class="['toolbar-btn', { active: batchSelectMode }]" @click="toggleBatchSelect" aria-label="批量选择">
          ☑️ 批量选择
        </button>
        <button type="button" v-if="canWrite && batchSelectMode && selectedMarkerIds.size > 0" class="toolbar-btn danger" @click="batchDeleteSelectedMarkers" aria-label="批量删除标记">
          🗑️ 删除({{ selectedMarkerIds.size }})
        </button>
        <button type="button" class="toolbar-btn" @click="resetView" aria-label="复位视图">⟲ 复位</button>
        <button type="button" :class="['toolbar-btn', { active: preferAMap }]" @click="toggleMapEngine" :title="useAMap ? '当前: 高德地图' : '当前: Leaflet (点击切换高德)'" :aria-label="useAMap ? '当前: 高德地图' : '当前: Leaflet (点击切换高德)'">
          {{ useAMap ? '🗺️ 高德' : '🗺️ Leaflet' }}
        </button>
        <button type="button" class="toolbar-btn" @click="toggleFullscreen" aria-label="全屏">
          {{ isFullscreen ? '⤓' : '⤢' }} 全屏
        </button>
        <button type="button" class="toolbar-btn" :disabled="isDownloadingOffline" @click="downloadOfflineTiles" aria-label="下载离线地图">
          💾 离线
          <span v-if="cachedTilesCount > 0" class="cache-badge">{{ cachedTilesCount }}</span>
        </button>
      </div>
    </div>

    <!-- ==================== Map View ==================== -->
    <div v-if="isDownloadingOffline" class="offline-progress-bar">
      <div class="offline-progress-fill" :style="{ width: offlineDownloadProgress + '%' }"></div>
      <span class="offline-progress-text">{{ offlineDownloadProgress }}%</span>
    </div>

    <div v-if="isAddingMarker" class="mode-indicator marker-mode">
      标记模式 — 点击地图放置标记
    </div>

    <div class="am-body">
      <div v-if="showLeftSidebar" class="left-sidebar">
        <div class="sidebar-header">
          <h3>Agent 列表</h3>
          <div class="sidebar-header-actions">
            <button v-if="canWrite" class="add-agent-btn" @click="showAddAgentModal = true" aria-label="添加Agent">+</button>
            <div class="sidebar-stats">
              <span class="stat-chip online"><span class="stat-dot"></span>{{ onlineCount }} 在线</span>
              <span class="stat-chip offline"><span class="stat-dot"></span>{{ offlineCount }} 离线</span>
            </div>
          </div>
        </div>
        <div class="agent-search">
          <input
            v-model="agentSearchQuery"
            type="text"
            class="sidebar-search-input"
            placeholder="搜索 Agent..."
          />
        </div>
        <div class="agent-list">
          <div
            v-for="agent in pagedAgents"
            :key="agent.agent_id"
            :class="['agent-card', { selected: selectedAgent?.agent_id === agent.agent_id }]"
            @click="flyToAgent(agent)"
          >
            <div class="agent-card-header">
              <span :class="['status-indicator', agent.status]"></span>
              <span class="agent-id">{{ agent.agent_id }}</span>
              <span class="agent-city">{{ agent.city }}</span>
            </div>
            <div class="agent-capabilities">
              <span v-for="cap in (agent.capabilities || []).slice(0, 3)" :key="cap" class="cap-tag">{{ cap }}</span>
              <span v-if="(agent.capabilities || []).length > 3" class="cap-tag more">+{{ (agent.capabilities || []).length - 3 }}</span>
            </div>
            <div class="agent-metrics">
              <div class="metric-row">
                <span class="metric-label">CPU</span>
                <div class="metric-bar"><div class="metric-fill cpu" :style="{ width: agent.cpu_load + '%' }"></div></div>
                <span class="metric-value">{{ agent.cpu_load }}%</span>
              </div>
              <div class="metric-row">
                <span class="metric-label">MEM</span>
                <div class="metric-bar"><div class="metric-fill mem" :style="{ width: Math.min(Math.max(100 - (agent.memory_free / 1024 * 100), 0), 100) + '%' }"></div></div>
                <span class="metric-value">{{ agent.memory_free >= 1024 ? (agent.memory_free / 1024).toFixed(1) + 'G' : agent.memory_free + 'M' }}</span>
              </div>
            </div>
          </div>
          <div v-if="filteredAgents.length === 0" class="empty-agents">暂无注册 Agent</div>
          <div v-if="filteredAgents.length > agentPageSize" class="agent-pagination">
            <button class="page-btn" :disabled="agentPage <= 1" @click="agentPage--" aria-label="上一页">◀</button>
            <span class="page-info">{{ agentPage }} / {{ agentTotalPages }}</span>
            <button class="page-btn" :disabled="agentPage >= agentTotalPages" @click="agentPage++" aria-label="下一页">▶</button>
          </div>
        </div>
      </div>

      <div class="map-area">
        <div v-if="isLoading" class="map-loading-overlay">
          <div class="loading-spinner"></div>
          <span class="loading-text">地图加载中...</span>
        </div>
        <div ref="mapContainer" id="map-container" class="leaflet-map-container"></div>
        <div v-if="mouseCoords" class="coord-display">
          {{ mouseCoords.lat }}°N, {{ mouseCoords.lng }}°E
        </div>
        <div v-if="lastDataUpdate" class="data-freshness">
          更新于 {{ lastDataUpdate.toLocaleTimeString('zh-CN') }}
        </div>
      </div>

      <div v-if="showRightSidebar" class="right-sidebar">
        <div class="sidebar-header">
          <h3>路由决策</h3>
          <span class="panel-count">{{ routingDecisions.length }}</span>
        </div>
        <div class="decision-list">
          <div
            v-for="(decision, idx) in routingDecisions.slice(0, 20)"
            :key="idx"
            class="decision-card"
          >
            <div class="decision-intent">{{ decision.intent_text || '意图路由' }}</div>
            <div class="decision-meta">
              <span class="decision-agent">{{ decision.selected_agent?.agent_id || decision.selected_agent || '未知' }}</span>
              <span class="decision-time">{{ decision.timestamp || '' }}</span>
            </div>
            <div class="decision-reasoning">{{ decision.explanation || decision.reasoning || '' }}</div>
          </div>
          <div v-if="routingDecisions.length === 0" class="empty-decisions">暂无路由决策</div>
        </div>
      </div>
    </div>

    <div class="am-bottom-bar">
      <button type="button" class="sidebar-toggle" @click="showLeftSidebar = !showLeftSidebar" aria-label="切换侧边栏">
        {{ showLeftSidebar ? '◀' : '▶' }}
      </button>
      <div class="route-bar">
        <input
          v-model="routeInput"
          type="text"
          class="route-input"
          placeholder="输入意图文本进行路由..."
          @keyup.enter="routeIntent"
        />
        <button type="button" class="route-btn" @click="routeIntent" :disabled="!routeInput.trim()" aria-label="路由意图">路由</button>
      </div>
      <button type="button" class="sidebar-toggle" @click="showRightSidebar = !showRightSidebar" aria-label="切换侧边栏">
        {{ showRightSidebar ? '▶' : '◀' }}
      </button>
    </div>

    <Teleport to="body">
      <div v-if="selectedAgent" class="modal-overlay" @click.self="closeAgentDetail" role="dialog" aria-modal="true">
        <div class="modal-content agent-detail-modal">
          <div class="modal-header">
            <h3 class="modal-title">{{ selectedAgent.agent_id }}</h3>
            <button type="button" class="modal-close" @click="closeAgentDetail" aria-label="关闭">✕</button>
          </div>
          <div class="detail-grid">
            <div class="detail-item">
              <span class="detail-label">状态</span>
              <span :class="['detail-value', selectedAgent.status]">
                {{ selectedAgent.status === 'online' ? '在线' : '离线' }}
              </span>
            </div>
            <div class="detail-item">
              <span class="detail-label">城市</span>
              <span class="detail-value">{{ selectedAgent.city }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">CPU 负载</span>
              <span class="detail-value">{{ selectedAgent.cpu_load }}%</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">可用内存</span>
              <span class="detail-value">{{ selectedAgent.memory_free }} MB</span>
            </div>
            <div v-if="selectedAgent.endpoint" class="detail-item detail-item-full">
              <span class="detail-label">端点</span>
              <span class="detail-value mono">{{ selectedAgent.endpoint }}</span>
            </div>
          </div>
          <div class="detail-caps">
            <span class="detail-label">能力标签</span>
            <div class="caps-list">
              <span v-for="cap in selectedAgent.capabilities" :key="cap" class="cap-tag">{{ cap }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="showMarkerForm" class="modal-overlay" @click.self="cancelAddingMarker" role="dialog" aria-modal="true">
        <div class="modal-content marker-form-modal">
          <div class="modal-header">
            <h3 class="modal-title">添加标记</h3>
            <button type="button" class="modal-close" @click="cancelAddingMarker" aria-label="关闭">✕</button>
          </div>
          <div class="marker-form">
            <div class="form-group">
              <label class="form-label">标题</label>
              <input v-model="newMarkerForm.title" type="text" class="form-input" placeholder="标记标题" />
            </div>
            <div class="form-group">
              <label class="form-label">描述</label>
              <textarea v-model="newMarkerForm.description" class="form-textarea" placeholder="标记描述" rows="3"></textarea>
            </div>
            <div class="form-group">
              <label class="form-label">分类</label>
              <select v-model="newMarkerForm.category" class="form-select">
                <option v-for="cat in CATEGORY_OPTIONS" :key="cat" :value="cat">{{ CATEGORY_LABELS[cat] || cat }}</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">图标</label>
              <div class="icon-picker">
                <button
                  type="button"
                  v-for="ico in ICON_OPTIONS"
                  :key="ico"
                  :class="['icon-option', { selected: newMarkerForm.icon === ico }]"
                  @click="newMarkerForm.icon = ico"
                  :aria-label="'选择图标 ' + ico"
                >{{ ico }}</button>
              </div>
            </div>
            <div class="form-actions">
              <button type="button" class="form-btn cancel" @click="cancelAddingMarker" aria-label="取消">取消</button>
              <button type="button" v-if="canWrite" class="form-btn save" @click="saveCustomMarker" aria-label="保存">保存</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Add Agent Modal -->
    <Teleport to="body">
      <div v-if="showAddAgentModal" class="modal-overlay" @click.self="showAddAgentModal = false">
        <div class="modal-content add-agent-modal">
          <div class="modal-header">
            <h3>添加 Agent</h3>
            <button class="modal-close" @click="showAddAgentModal = false" aria-label="关闭">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-field">
              <label>Agent ID <span class="required">*</span></label>
              <input v-model="newAgentForm.agent_id" type="text" placeholder="如: agent_my_agent" />
            </div>
            <div class="form-field">
              <label>城市 <span class="required">*</span></label>
              <input v-model="newAgentForm.city" type="text" placeholder="如: 北京" @input="onCityInput" />
            </div>
            <div class="form-field-row">
              <div class="form-field">
                <label>纬度</label>
                <input v-model.number="newAgentForm.lat" type="number" step="0.01" placeholder="39.90" />
              </div>
              <div class="form-field">
                <label>经度</label>
                <input v-model.number="newAgentForm.lng" type="number" step="0.01" placeholder="116.40" />
              </div>
            </div>
            <div class="form-field">
              <label>能力标签</label>
              <input v-model="newAgentForm.capabilities" type="text" placeholder="逗号分隔，如: qos_config, intent_parsing" />
            </div>
            <div class="form-field">
              <label>端点地址</label>
              <input v-model="newAgentForm.endpoint" type="text" placeholder="如: http://localhost:8001" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="form-btn cancel" @click="showAddAgentModal = false">取消</button>
            <button v-if="canWrite" class="form-btn save" @click="addAgent" :disabled="!newAgentForm.agent_id.trim() || !newAgentForm.city.trim()">添加</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.agent-map {
  position: relative;
  animation: page-enter 0.5s ease-out;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  will-change: transform, opacity;
}

.am-bg {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.bg-grid {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  background-image:
    linear-gradient(rgba(22, 93, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(22, 93, 255, 0.03) 1px, transparent 1px);
  background-size: 60px 60px;
  mask-image: radial-gradient(ellipse 80% 60% at 50% 30%, black 20%, transparent 70%);
}

.bg-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
}

.glow-1 {
  width: 400px;
  height: 400px;
  background: rgba(22, 93, 255, 0.08);
  top: -100px;
  right: 10%;
  animation: glow-float 12s ease-in-out infinite;
  will-change: transform;
}

.glow-2 {
  width: 300px;
  height: 300px;
  background: rgba(22, 93, 255, 0.06);
  bottom: 10%;
  left: 5%;
  animation: glow-float 15s ease-in-out infinite reverse;
  will-change: transform;
}



.agent-map > *:not(.am-bg) {
  position: relative;
  z-index: var(--z-content);
}

.am-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: var(--gradient-glass-strong);
  border-bottom: 1px solid var(--color-border-primary);
  backdrop-filter: blur(16px);
  gap: 12px;
  flex-wrap: wrap;
  z-index: var(--z-dropdown);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.toolbar-center {
  flex: 1;
  min-width: 200px;
  max-width: 400px;
}

.page-title {
  font-size: var(--font-size-xl);
  font-weight: 700;
  margin: 0;
  background: linear-gradient(135deg, var(--color-text-secondary) 0%, var(--color-primary-light) 50%, var(--color-text-secondary) 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: title-shimmer 4s ease-in-out infinite;
  white-space: nowrap;
  margin-right: var(--spacing-md);
}

.layer-switcher {
  display: flex;
  gap: 2px;
  background: var(--input-bg);
  border-radius: var(--radius-lg);
  padding: 2px;
  border: 1px solid var(--input-border);
}

.layer-btn {
  padding: 4px 12px;
  border: 1px solid rgba(22, 93, 255, 0.15);
  border-radius: var(--radius-md);
  background: rgba(22, 93, 255, 0.06);
  color: rgba(255, 255, 255, 0.7);
  font-size: var(--font-size-xs);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s ease;
  min-height: 44px;
  backdrop-filter: blur(8px);
}

.layer-btn.active {
  background: rgba(22, 93, 255, 0.2);
  border-color: rgba(22, 93, 255, 0.4);
  color: var(--color-primary-light);
  box-shadow: var(--shadow-glow-primary-sm);
}

.layer-btn:hover:not(.active) {
  background: rgba(22, 93, 255, 0.15);
  border-color: rgba(22, 93, 255, 0.3);
  color: rgba(255, 255, 255, 0.85);
  transform: scale(1.02);
}

.layer-btn:active {
  transform: scale(0.97);
}

.toolbar-btn {
  padding: 6px 14px;
  border: 1px solid rgba(22, 93, 255, 0.2);
  border-radius: var(--radius-lg);
  background: rgba(22, 93, 255, 0.08);
  color: var(--color-primary-light);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.25s ease;
  white-space: nowrap;
  position: relative;
  backdrop-filter: blur(8px);
  min-height: 44px;
  min-width: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.toolbar-btn:hover {
  background: rgba(22, 93, 255, 0.18);
  border-color: rgba(22, 93, 255, 0.35);
  color: var(--color-primary-lighter);
  box-shadow: 0 0 12px rgba(22, 93, 255, 0.15);
  transform: scale(1.02);
}

.toolbar-btn.active {
  background: rgba(22, 93, 255, 0.2);
  border-color: rgba(22, 93, 255, 0.4);
  color: var(--color-primary-light);
  box-shadow: var(--shadow-glow-primary-lg);
}

.toolbar-btn.danger {
  border-color: rgba(239, 68, 68, 0.3);
  color: var(--color-error);
}

.toolbar-btn.danger:hover {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.5);
  box-shadow: var(--shadow-glow-error);
}

.toolbar-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.toolbar-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.cache-badge {
  font-size: var(--font-size-xs);
  padding: 1px 5px;
  border-radius: var(--radius-lg);
  background: var(--color-primary-glow);
  color: var(--color-primary-light);
  margin-left: 4px;
}

.search-wrapper {
  position: relative;
}

.search-input {
  width: 100%;
  padding: 6px 14px;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  outline: none;
  transition: all 0.25s var(--ease-out);
}

.search-input::placeholder {
  color: var(--color-text-disabled);
}

.search-input:focus {
  border-color: var(--input-border-focus);
  box-shadow: var(--input-shadow-focus);
}

.search-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 4px;
  background: rgba(15, 23, 42, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: var(--radius-lg);
  max-height: 240px;
  overflow-y: auto;
  z-index: var(--z-fixed);
  backdrop-filter: blur(16px);
}

.search-result-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 14px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.search-result-item:hover {
  background: var(--color-primary-bg);
}

.poi-name {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-weight: 500;
}

.poi-cat {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-md);
  background: rgba(59, 130, 246, 0.15);
  color: var(--color-primary);
}

.search-empty {
  padding: 16px;
  text-align: center;
  color: var(--color-text-disabled);
  font-size: var(--font-size-sm);
}

.offline-progress-bar {
  position: relative;
  height: 20px;
  background: rgba(15, 23, 42, 0.6);
  z-index: var(--z-dropdown);
  display: flex;
  align-items: center;
}

.offline-progress-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), var(--color-primary-light));
  border-radius: var(--radius-xs);
  transition: width 0.3s ease;
  opacity: 0.3;
}

.offline-progress-text {
  position: relative;
  margin-left: auto;
  padding-right: 12px;
  font-size: var(--font-size-xs);
  color: var(--color-primary-light);
  font-weight: 600;
  z-index: var(--z-content);
}

.mode-indicator {
  padding: 6px 16px;
  text-align: center;
  font-size: var(--font-size-xs);
  font-weight: 600;
  z-index: var(--z-dropdown);
  backdrop-filter: blur(8px);
}

.marker-mode {
  background: rgba(245, 158, 11, 0.15);
  color: var(--color-warning);
  border-bottom: 1px solid rgba(245, 158, 11, 0.2);
}

.am-body {
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
}

.left-sidebar,
.right-sidebar {
  width: 280px;
  min-width: 280px;
  background: var(--gradient-glass-strong);
  border-right: 1px solid var(--color-border-primary);
  backdrop-filter: blur(14px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: var(--z-above);
}

.right-sidebar {
  border-right: none;
  border-left: 1px solid var(--color-border-primary);
}

.sidebar-header {
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border-primary);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}

.sidebar-header h3 {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.sidebar-stats {
  display: flex;
  gap: 8px;
}

.stat-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-xs);
  font-weight: 600;
}

.stat-chip.online {
  color: var(--color-success);
}

.stat-chip.offline {
  color: var(--color-text-tertiary);
}

.stat-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.stat-chip.online .stat-dot {
  animation: dot-pulse 2s ease-in-out infinite;
}



.panel-count {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-lg);
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  font-weight: 600;
}

.agent-search {
  padding: 10px 12px;
  flex-shrink: 0;
}

.sidebar-search-input {
  width: 100%;
  padding: 6px 12px;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: var(--input-radius);
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  outline: none;
}

.sidebar-search-input::placeholder {
  color: var(--color-text-disabled);
}

.sidebar-search-input:focus {
  border-color: var(--input-border-focus);
}

.agent-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.agent-card {
  padding: 10px 12px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-primary);
  background: var(--gradient-glass);
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  backdrop-filter: blur(8px);
}

.agent-card:hover {
  border-color: var(--color-border-secondary);
  background: var(--gradient-glass-strong);
}

.agent-card.selected {
  border-color: var(--color-primary-border);
  background: var(--color-primary-bg);
}

.agent-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-indicator.online {
  background: var(--color-success);
  box-shadow: var(--shadow-glow-success-sm);
}

.status-indicator.offline {
  background: var(--color-text-tertiary);
}

.agent-id {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-primary);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-city {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.agent-capabilities {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-bottom: 6px;
}

.cap-tag {
  font-size: var(--font-size-xs);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: rgba(59, 130, 246, 0.12);
  color: var(--color-primary);
  white-space: nowrap;
}

.cap-tag.more {
  background: rgba(148, 163, 184, 0.12);
  color: var(--color-text-tertiary);
}

.agent-metrics {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--font-size-xs);
}

.metric-label {
  color: var(--color-text-tertiary);
  width: 28px;
  flex-shrink: 0;
}

.metric-bar {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.metric-fill {
  height: 100%;
  border-radius: var(--radius-xs);
  transition: width 0.3s ease;
}

.metric-fill.cpu {
  background: linear-gradient(90deg, var(--color-primary), var(--color-primary-light));
}

.metric-fill.mem {
  background: linear-gradient(90deg, var(--color-purple), #A78BFA);
}

.metric-value {
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
  width: 40px;
  text-align: right;
  flex-shrink: 0;
}

.agent-list-more {
  text-align: center;
  padding: 8px;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.agent-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  margin-top: 4px;
}

.agent-pagination .page-btn {
  background: rgba(22, 93, 255, 0.08);
  border: 1px solid rgba(22, 93, 255, 0.2);
  color: var(--color-primary-light);
  border-radius: var(--radius-lg);
  padding: 4px 12px;
  cursor: pointer;
  font-size: var(--font-size-xs);
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
}

.agent-pagination .page-btn:hover:not(:disabled) {
  background: rgba(22, 93, 255, 0.18);
  border-color: rgba(22, 93, 255, 0.35);
  color: var(--color-primary-lighter);
  box-shadow: 0 0 12px rgba(22, 93, 255, 0.15);
  transform: scale(1.02);
}

.agent-pagination .page-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.agent-pagination .page-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.agent-pagination .page-info {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  min-width: 50px;
  text-align: center;
}

.empty-agents {
  text-align: center;
  padding: 24px 16px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.map-area {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.leaflet-map-container {
  width: 100%;
  height: 100%;
  min-height: 400px;
}

.map-loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.85);
  z-index: var(--z-sticky);
  backdrop-filter: blur(8px);
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-primary-hover);
  border-top-color: var(--color-primary-light);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}



.loading-text {
  margin-top: 12px;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.coord-display {
  position: absolute;
  bottom: 8px;
  left: 8px;
  padding: 3px 8px;
  background: rgba(15, 23, 42, 0.8);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-disabled);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  z-index: var(--z-above);
  backdrop-filter: blur(8px);
}

.data-freshness {
  position: absolute;
  bottom: 8px;
  right: 8px;
  padding: 3px 8px;
  background: rgba(15, 23, 42, 0.8);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-disabled);
  z-index: var(--z-above);
  backdrop-filter: blur(8px);
}

.decision-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.decision-card {
  padding: 10px 12px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-primary);
  background: var(--gradient-glass);
  margin-bottom: 6px;
  backdrop-filter: blur(8px);
}

.decision-intent {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.decision-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.decision-agent {
  font-size: var(--font-size-xs);
  padding: 1px 6px;
  border-radius: var(--radius-default);
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  font-weight: 500;
}

.decision-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-disabled);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.decision-reasoning {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.empty-decisions {
  text-align: center;
  padding: 24px 16px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.am-bottom-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: var(--gradient-glass-strong);
  border-top: 1px solid var(--color-border-primary);
  backdrop-filter: blur(16px);
  z-index: var(--z-dropdown);
}

.sidebar-toggle {
  padding: 6px 10px;
  border: 1px solid rgba(22, 93, 255, 0.2);
  border-radius: var(--radius-lg);
  background: rgba(22, 93, 255, 0.08);
  color: var(--color-primary-light);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all 0.25s ease;
  flex-shrink: 0;
  min-height: 44px;
  min-width: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(8px);
}

.sidebar-toggle:hover {
  background: rgba(22, 93, 255, 0.18);
  border-color: rgba(22, 93, 255, 0.35);
  color: var(--color-primary-lighter);
  box-shadow: 0 0 12px rgba(22, 93, 255, 0.15);
  transform: scale(1.02);
}

.sidebar-toggle:active {
  transform: scale(0.97);
}

.route-bar {
  flex: 1;
  display: flex;
  gap: 8px;
}

.route-input {
  flex: 1;
  padding: var(--input-padding);
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: var(--radius-lg);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  outline: none;
  transition: all 0.25s ease;
  backdrop-filter: blur(8px);
}

.route-input::placeholder {
  color: var(--color-text-disabled);
}

.route-input:focus {
  border-color: rgba(59, 130, 246, 0.5);
  box-shadow: 0 0 12px rgba(59, 130, 246, 0.15);
}

.route-btn {
  padding: 8px 20px;
  background: rgba(22, 93, 255, 0.15);
  color: var(--color-primary-light);
  border: 1px solid rgba(22, 93, 255, 0.3);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.25s ease;
  white-space: nowrap;
  min-height: 44px;
  backdrop-filter: blur(8px);
}

.route-btn:hover:not(:disabled) {
  background: rgba(22, 93, 255, 0.25);
  border-color: rgba(22, 93, 255, 0.5);
  color: var(--color-primary-lighter);
  box-shadow: var(--shadow-glow-primary-lg);
  transform: scale(1.02);
}

.route-btn:active:not(:disabled) {
  transform: scale(0.97);
  box-shadow: var(--shadow-glow-primary-sm);
}

.route-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

/* ==================== Modal ==================== */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
  backdrop-filter: blur(4px);
}

.modal-content {
  background: rgba(15, 23, 42, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: var(--radius-2xl);
  padding: 24px;
  min-width: 360px;
  max-width: 480px;
  backdrop-filter: blur(20px);
  box-shadow: var(--shadow-modal);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.modal-title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}

.modal-close {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-lg);
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-md);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.modal-close:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--color-text-primary);
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-item-full {
  grid-column: 1 / -1;
}

.detail-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-disabled);
  font-weight: 500;
}

.detail-value {
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  font-weight: 600;
}

.detail-value.online {
  color: var(--color-success);
}

.detail-value.offline {
  color: var(--color-text-tertiary);
}

.detail-caps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.caps-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* ==================== Marker Form ==================== */
.marker-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: var(--font-size-xs);
  font-weight: 500;
  color: var(--color-text-tertiary);
}

.form-input,
.form-textarea,
.form-select {
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: var(--radius-lg);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  outline: none;
  transition: border-color 0.2s ease;
}

.form-input:focus,
.form-textarea:focus,
.form-select:focus {
  border-color: rgba(0, 212, 255, 0.5);
}

.form-textarea {
  resize: vertical;
  min-height: 60px;
}

.form-select {
  cursor: pointer;
}

.form-select option {
  background: var(--color-bg-primary);
  color: var(--color-text-secondary);
}

.icon-picker {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.icon-option {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-lg);
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  font-size: var(--font-size-lg);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.icon-option:hover {
  border-color: var(--color-primary-border);
  background: var(--color-primary-bg);
}

.icon-option.selected {
  border-color: rgba(0, 212, 255, 0.5);
  background: var(--color-primary-hover);
}

.form-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.form-btn {
  padding: 8px 20px;
  border-radius: var(--radius-lg);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  min-height: 44px;
}

.form-btn.cancel {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: var(--color-text-tertiary);
}

.form-btn.cancel:hover {
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-secondary);
}

.form-btn.save {
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
  border: none;
  color: var(--color-text-primary);
}

.form-btn.save:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px var(--color-primary-border);
}

.form-btn.save:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.add-agent-btn {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-lg);
  border: 1px solid rgba(22, 93, 255, 0.3);
  background: rgba(22, 93, 255, 0.15);
  color: var(--color-primary-light);
  font-size: var(--font-size-md);
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.25s ease;
  flex-shrink: 0;
  backdrop-filter: blur(8px);
}

.add-agent-btn:hover {
  background: rgba(22, 93, 255, 0.25);
  border-color: rgba(22, 93, 255, 0.5);
  box-shadow: var(--shadow-glow-primary-lg);
  transform: scale(1.03);
}

.add-agent-btn:active {
  transform: scale(0.95);
}

.sidebar-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.add-agent-modal .modal-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.add-agent-modal .form-field label {
  display: block;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: 4px;
}

.add-agent-modal .form-field label .required {
  color: var(--color-error);
}

.add-agent-modal .form-field input {
  width: 100%;
  padding: 8px 12px;
  border-radius: var(--radius-lg);
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.add-agent-modal .form-field input:focus {
  border-color: rgba(59, 130, 246, 0.5);
}

.add-agent-modal .form-field input::placeholder {
  color: var(--color-text-disabled);
}

.add-agent-modal .form-field-row {
  display: flex;
  gap: 12px;
}

.add-agent-modal .form-field-row .form-field {
  flex: 1;
}

.add-agent-modal .modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

@media (max-width: 1200px) {
  .left-sidebar,
  .right-sidebar {
    width: 240px;
    min-width: 240px;
  }
}

@media (max-width: 900px) {
  .left-sidebar,
  .right-sidebar {
    display: none;
  }

  .am-toolbar {
    flex-wrap: wrap;
    gap: 6px;
  }

  .toolbar-center {
    order: -1;
    min-width: 100%;
    max-width: 100%;
  }

  .am-bottom-bar {
    flex-wrap: wrap;
  }

  .route-bar {
    min-width: 100%;
    order: -1;
  }
}

@media (max-width: 480px) {
  .am-toolbar {
    padding: 8px 10px;
  }

  .page-title {
    font-size: var(--font-size-base);
  }

  .toolbar-btn {
    padding: 4px 8px;
    font-size: var(--font-size-xs);
  }

  .route-input {
    font-size: var(--font-size-xs);
  }
}

/* 侧边栏滑入过渡 */
.sidebar-slide-enter-active {
  transition: transform 0.3s var(--ease-out), opacity 0.3s var(--ease-out);
}
.sidebar-slide-leave-active {
  transition: transform 0.2s var(--ease-out), opacity 0.2s var(--ease-out);
}
.sidebar-slide-enter-from {
  opacity: 0;
}
.sidebar-slide-leave-to {
  opacity: 0;
}
.sidebar-slide-enter-from.left {
  transform: translateX(-20px);
}
.sidebar-slide-leave-to.left {
  transform: translateX(-20px);
}
.sidebar-slide-enter-from.right {
  transform: translateX(20px);
}
.sidebar-slide-leave-to.right {
  transform: translateX(20px);
}

@media (prefers-reduced-motion: reduce) {
  .sidebar-slide-enter-active,
  .sidebar-slide-leave-active {
    transition: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .agent-map,
  .agent-pulse-ring,
  .bg-glow,
  .stat-chip.online .stat-dot,
  .poi-marker-dot,
  .loading-spinner {
    animation: none !important;
    transition: none !important;
  }
}
</style>

<style>
.agent-marker-icon {
  background: none !important;
  border: none !important;
}

.agent-marker-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
}

.agent-marker-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.3);
}

.agent-pulse-ring {
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translateX(-50%);
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 2px solid;
  animation: agentPulse 2s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

@keyframes agentPulse {
  0% { transform: translateX(-50%) scale(1); opacity: 0.6; }
  100% { transform: translateX(-50%) scale(2.2); opacity: 0; }
}

@keyframes pulse {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.5); opacity: 0.5; }
  100% { transform: scale(1); opacity: 1; }
}

.agent-marker-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  font-weight: 600;
  margin-top: 2px;
  white-space: nowrap;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8), 0 0 6px rgba(0, 0, 0, 0.6);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.agent-popup .leaflet-popup-content-wrapper {
  background: rgba(15, 23, 42, 0.95) !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  border-radius: var(--radius-lg) !important;
  color: var(--color-text-secondary) !important;
  backdrop-filter: blur(12px);
  box-shadow: var(--shadow-dropdown) !important;
}

.agent-popup .leaflet-popup-tip {
  background: rgba(15, 23, 42, 0.95) !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
}

.agent-popup .leaflet-popup-close-button {
  color: var(--color-text-tertiary) !important;
}

.agent-popup-content {
  min-width: 200px;
}

.popup-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.popup-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.popup-agent-id {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.popup-city {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
}

.popup-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.popup-label {
  color: var(--color-text-disabled);
  font-size: var(--font-size-xs);
}

.popup-mono {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.popup-caps {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-top: 6px;
}

.popup-cap {
  font-size: var(--font-size-xs);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: rgba(59, 130, 246, 0.15);
  color: var(--color-primary);
}

.popup-detail-btn {
  margin-top: 8px;
  width: 100%;
  padding: 5px;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  background: var(--color-primary-bg);
  color: var(--color-primary-light);
  font-size: var(--font-size-xs);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.popup-detail-btn:hover {
  background: var(--color-primary-glow);
}

.custom-marker-icon {
  background: none !important;
  border: none !important;
}

.custom-marker-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
}

.custom-marker-emoji {
  font-size: var(--font-size-xl);
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.5));
}

.custom-marker-title {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  font-weight: 500;
  white-space: nowrap;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
}

.marker-checkbox {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 14px;
  height: 14px;
  cursor: pointer;
}

.custom-marker-popup .leaflet-popup-content-wrapper {
  background: rgba(15, 23, 42, 0.95) !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  border-radius: var(--radius-lg) !important;
  color: var(--color-text-secondary) !important;
  backdrop-filter: blur(12px);
}

.custom-marker-popup .leaflet-popup-tip {
  background: rgba(15, 23, 42, 0.95) !important;
}

.custom-popup-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 4px;
}

.custom-popup-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: 4px;
}

.custom-popup-cat {
  font-size: var(--font-size-xs);
  color: var(--color-text-disabled);
}

.poi-marker-icon {
  background: none !important;
  border: none !important;
}

.poi-marker-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-warning);
  border: 2px solid rgba(255, 255, 255, 0.4);
  box-shadow: 0 0 10px rgba(245, 158, 11, 0.5);
  animation: poiPulse 1.5s ease-in-out infinite;
}

@keyframes poiPulse {
  0%, 100% { box-shadow: 0 0 6px rgba(245, 158, 11, 0.4); }
  50% { box-shadow: 0 0 14px rgba(245, 158, 11, 0.7); }
}

.poi-popup .leaflet-popup-content-wrapper {
  background: rgba(15, 23, 42, 0.95) !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  border-radius: var(--radius-lg) !important;
  color: var(--color-text-secondary) !important;
  backdrop-filter: blur(12px);
}

.poi-popup .leaflet-popup-tip {
  background: rgba(15, 23, 42, 0.95) !important;
}

.poi-popup-name {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 4px;
}

.poi-popup-cat {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-md);
  background: rgba(245, 158, 11, 0.15);
  color: var(--color-warning);
  display: inline-block;
  margin-bottom: 4px;
}

.poi-popup-addr {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.poi-popup-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: 4px;
}

.topology-node-icon {
  background: none !important;
  border: none !important;
}

.topo-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 8px;
  border-radius: var(--radius-lg);
  border: 1.5px solid;
  backdrop-filter: blur(4px);
}

.topo-node-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-bottom: 2px;
}

.topo-node-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  font-weight: 600;
  white-space: nowrap;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
}

.leaflet-container {
  background: var(--color-bg-primary) !important;
}

.leaflet-control-zoom a {
  background: rgba(15, 23, 42, 0.85) !important;
  color: var(--color-text-secondary) !important;
  border-color: rgba(255, 255, 255, 0.1) !important;
}

.leaflet-control-zoom a:hover {
  background: rgba(30, 41, 59, 0.95) !important;
}

.leaflet-control-attribution {
  background: rgba(15, 23, 42, 0.7) !important;
  color: var(--color-text-disabled) !important;
  font-size: var(--font-size-xs) !important;
}

.leaflet-control-attribution a {
  color: var(--color-text-tertiary) !important;
}

.custom-minimap {
  position: absolute;
  bottom: 30px;
  right: 10px;
  width: 120px;
  height: 100px;
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.15);
  z-index: var(--z-fixed);
  opacity: 0.7;
}

.leaflet-popup-close-button {
  color: var(--color-text-tertiary) !important;
}

.leaflet-popup-close-button:hover {
  color: var(--color-text-primary) !important;
}
</style>
