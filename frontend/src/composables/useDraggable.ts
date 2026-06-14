import { ref, onMounted, onUnmounted } from 'vue'

interface Position {
  x: number
  y: number
}

export function useDraggable(options?: {
  initialPosition?: Position
  snapToEdge?: boolean
  onDragStart?: () => void
  onDragEnd?: () => void
}) {
  const position = ref<Position>(options?.initialPosition || { x: window.innerWidth - 70, y: window.innerHeight / 2 - 28 })
  const isDragging = ref(false)
  const dragOffset = ref<Position>({ x: 0, y: 0 })
  const opacity = ref(1)
  const snapToEdge = options?.snapToEdge !== false

  const handlePointerDown = (e: PointerEvent) => {
    isDragging.value = true
    dragOffset.value = {
      x: e.clientX - position.value.x,
      y: e.clientY - position.value.y
    }
    opacity.value = 0.5
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    options?.onDragStart?.()
  }

  const handlePointerMove = (e: PointerEvent) => {
    if (!isDragging.value) return
    const newX = e.clientX - dragOffset.value.x
    const newY = e.clientY - dragOffset.value.y
    position.value = {
      x: Math.max(0, Math.min(newX, window.innerWidth - 56)),
      y: Math.max(0, Math.min(newY, window.innerHeight - 56))
    }
  }

  const handlePointerUp = () => {
    if (!isDragging.value) return
    isDragging.value = false
    opacity.value = 1
    if (snapToEdge) {
      const centerX = window.innerWidth / 2
      position.value = {
        x: position.value.x < centerX ? 20 : window.innerWidth - 76,
        y: Math.max(20, Math.min(position.value.y, window.innerHeight - 76))
      }
    }
    options?.onDragEnd?.()
  }

  const handleResize = () => {
    if (position.value.x > window.innerWidth - 56) {
      position.value.x = window.innerWidth - 76
    }
    if (position.value.y > window.innerHeight - 56) {
      position.value.y = window.innerHeight - 76
    }
  }

  onMounted(() => window.addEventListener('resize', handleResize))
  onUnmounted(() => window.removeEventListener('resize', handleResize))

  return {
    position,
    isDragging,
    opacity,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp
  }
}
