import { ref, computed, onMounted, onUnmounted, type Ref } from 'vue'

interface DragOptions {
  /** 初始 X 坐标 */
  initialX?: number
  /** 初始 Y 坐标 */
  initialY?: number
  /** 拖拽边界限制 */
  bounds?: {
    left?: number
    top?: number
    right?: number
    bottom?: number
  }
  /** 拖拽手柄选择器，仅在手柄区域内可拖拽 */
  handle?: string
  /** 是否禁用拖拽 */
  disabled?: boolean
}

interface DragPosition {
  x: number
  y: number
}

export function useDraggable(
  elementRef: Ref<HTMLElement | null>,
  options: DragOptions = {}
) {
  const x = ref(options.initialX ?? 0)
  const y = ref(options.initialY ?? 0)
  const isDragging = ref(false)

  let startX = 0
  let startY = 0
  let startPosX = 0
  let startPosY = 0

  const style = computed(() => ({
    position: 'absolute' as const,
    left: `${x.value}px`,
    top: `${y.value}px`,
    cursor: isDragging.value ? 'grabbing' : 'grab',
    userSelect: isDragging.value ? 'none' as const : 'auto' as const
  }))

  function clampPosition(posX: number, posY: number): DragPosition {
    const bounds = options.bounds
    if (!bounds) return { x: posX, y: posY }

    return {
      x: Math.max(bounds.left ?? -Infinity, Math.min(bounds.right ?? Infinity, posX)),
      y: Math.max(bounds.top ?? -Infinity, Math.min(bounds.bottom ?? Infinity, posY))
    }
  }

  function onMouseDown(event: MouseEvent): void {
    if (options.disabled) return

    // 如果指定了拖拽手柄，检查事件目标是否在手柄内
    if (options.handle && elementRef.value) {
      const handle = elementRef.value.querySelector(options.handle)
      if (handle && !handle.contains(event.target as Node)) {
        return
      }
    }

    event.preventDefault()
    isDragging.value = true
    startX = event.clientX
    startY = event.clientY
    startPosX = x.value
    startPosY = y.value

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }

  function onMouseMove(event: MouseEvent): void {
    if (!isDragging.value) return

    const deltaX = event.clientX - startX
    const deltaY = event.clientY - startY
    const newPos = clampPosition(startPosX + deltaX, startPosY + deltaY)

    x.value = newPos.x
    y.value = newPos.y
  }

  function onMouseUp(): void {
    isDragging.value = false
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  onMounted(() => {
    if (elementRef.value) {
      elementRef.value.addEventListener('mousedown', onMouseDown)
    }
  })

  onUnmounted(() => {
    if (elementRef.value) {
      elementRef.value.removeEventListener('mousedown', onMouseDown)
    }
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  })

  return {
    x,
    y,
    isDragging,
    style
  }
}
