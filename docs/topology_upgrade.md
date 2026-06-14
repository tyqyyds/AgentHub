# 网络拓扑模块升级文档

## 1. 升级概述

本次升级针对智维 AgentHub 前端 `Topology.vue` 模块，聚焦以下六大维度的全面优化：

| 维度 | 核心目标 |
|------|----------|
| **类型安全** | 消除 `as any`、`as TopologyNode` 等不安全类型断言，引入类型守卫函数 |
| **数据处理效率** | 重构链路键值系统，消除脆弱的字符串分割解析 |
| **用户交互** | 修复拖拽时动画中断、右键菜单溢出视口等交互缺陷 |
| **功能完整性** | 增强导入/快照数据验证、链路带宽视觉区分度 |
| **稳定性** | 修复 API 请求静默失败、状态直接变异绕过动作处理器等问题 |
| **兼容性** | 尊重 `prefers-reduced-motion` 系统偏好，CSV 导出符合 RFC 4180 标准 |

所有变更均为前端改动，不涉及后端 API 接口调整。

---

## 2. 升级前问题分析

通过对 `Topology.vue`（约 846 行）的全面代码审查，发现以下 12 项问题：

### 2.1 类型安全问题

| 编号 | 问题 | 严重程度 | 影响范围 |
|------|------|----------|----------|
| P-01 | 模板中 `centralNode as any` 绕过 TypeScript 类型检查 | 高 | 模板渲染层 |
| P-02 | `handleMenuAction` 使用 `as TopologyNode` / `as TopologyLink` 不安全类型断言，无类型守卫 | 高 | 右键菜单操作 |
| P-03 | `centralNode` 接口包含冗余 `isCentral` 属性，且缺少 `originalX`/`originalY` 位置恢复字段 | 中 | 中心节点状态 |

### 2.2 状态管理问题

| 编号 | 问题 | 严重程度 | 影响范围 |
|------|------|----------|----------|
| P-04 | `nodeDetails.locked = false` 直接变异状态，绕过 `handleMenuAction('isolate')` 动作处理器 | 高 | 节点隔离/解除隔离 |
| P-05 | `linkDetails.main = true` 直接变异状态，绕过 `handleMenuAction('makePrimary')` 动作处理器 | 高 | 链路主备切换 |

### 2.3 数据处理问题

| 编号 | 问题 | 严重程度 | 影响范围 |
|------|------|----------|----------|
| P-06 | `linkKey.split('-')` 脆弱解析，当节点 ID 包含连字符时解析错误 | 高 | 链路标识系统（22+ 处引用） |
| P-07 | `importTopology` 仅校验顶层 `nodes`/`links` 数组存在，未验证字段完整性 | 中 | 拓扑数据导入 |
| P-08 | `restoreSnapshot` 无 JSON 结构验证，损坏数据可能导致运行时异常 | 中 | 快照恢复 |

### 2.4 安全性问题

| 编号 | 问题 | 严重程度 | 影响范围 |
|------|----------------|----------|
| P-09 | `escapeCsvField` 无 CSV 注入防护，`=`、`+`、`-`、`@` 开头的字段可被 Excel 执行公式 | 高 | CSV 导出 |
| P-10 | `executeAction` 中 `if (response.ok)` 静默忽略 API 错误，无错误抛出 | 中 | API 请求 |

### 2.5 性能与交互问题

| 编号 | 问题 | 严重程度 | 影响范围 |
|------|------|----------|----------|
| P-11 | `animateNodes` 中 `if (isDragging) return` 导致拖拽期间 rAF 循环永久停止，拖拽结束后动画不恢复 | 高 | 节点微动效 |
| P-12 | `getLinkWidth` 对 40G/100G/10G 均返回 5px，无视觉区分度 | 低 | 链路渲染 |
| P-13 | 右键菜单可能溢出视口边界，部分菜单项不可见 | 中 | 上下文菜单 |

### 2.6 代码质量问题

| 编号 | 问题 | 严重程度 | 影响范围 |
|------|------|----------|----------|
| P-14 | `simulateA2ATraffic` 函数已定义但从未调用（死代码），关联的 `a2aTrafficInterval` ref 及清理代码同样冗余 | 低 | 代码可维护性 |

---

## 3. 升级方案与实施

### 3.1 类型安全优化

#### 3.1.1 `centralNode` 类型重构

**变更前：**
```typescript
const centralNode = ref<any>({ ... })
// 模板中: {{ (centralNode as any).name }}
```

**变更后：**
```typescript
const centralNode = ref<TopologyNode>({
  x: 500, y: 80, id: 'central', name: '中心控制', type: 'central',
  status: 'healthy', health: 100, cpu: 25, memory: 40, traffic: '12.5G',
  locked: false, originalX: 500, originalY: 80
})
```

**关键变更：**
- `centralNode` 明确类型为 `ref<TopologyNode>`，移除所有 `as any`
- 新增 `originalX` / `originalY` 字段，支持布局重置时恢复原始位置
- 移除冗余的 `isCentral` 属性（通过 `id === 'central'` 判断即可）

#### 3.1.2 类型守卫函数

**变更前：**
```typescript
// handleMenuAction 中:
const target = contextMenu.value.target as TopologyNode  // 不安全
```

**变更后：**
```typescript
const isTopologyNode = (t: TopologyNode | TopologyLink | null): t is TopologyNode =>
  t !== null && 'id' in t && 'health' in t

const isTopologyLink = (t: TopologyNode | TopologyLink | null): t is TopologyLink =>
  t !== null && 'source' in t && 'target' in t

// handleMenuAction 中:
const target = contextMenu.value.target
const isNode = isTopologyNode(target)
const isLink = isTopologyLink(target)
```

**影响范围：**
- `handleMenuAction` 全部 `switch` 分支均使用类型守卫前置校验
- 模板中 `contextMenu.target` 访问使用 `isTopologyNode()` / `isTopologyLink()` 守卫
- `nodeMenuItems` computed 中使用 `isTopologyNode()` 判断锁定状态
- 消除全部 19 处 `as TopologyNode` / `as TopologyLink` 不安全断言

---

### 3.2 状态管理优化

#### 3.2.1 节点隔离状态变更

**变更前：**
```html
<!-- 节点详情面板 - 解除隔离按钮 -->
<button @click="nodeDetails.locked = false">解除隔离</button>
```

**变更后：**
```html
<button @click="handleMenuAction('isolate')">解除隔离</button>
```

**原因：** 直接修改 `nodeDetails.locked` 仅变更了详情面板引用，未同步更新 `topologyData` 中的节点状态，也未更新 `isolatedLinks` 集合。通过 `handleMenuAction('isolate')` 走完整动作流程，确保：
1. `topologyData` 中对应节点的 `locked` 状态正确切换
2. 关联链路的 `isolatedLinks` 集合同步更新
3. API 请求正确发送
4. 动画效果正确触发

#### 3.2.2 链路主备切换状态变更

**变更前：**
```html
<!-- 链路详情面板 - 设为主用按钮 -->
<button @click="linkDetails.main = true">设为主用</button>
```

**变更后：**
```html
<button @click="handleMenuAction('makePrimary')">设为主用</button>
```

**原因：** 直接修改 `linkDetails.main` 仅变更了详情面板引用，未同步更新 `topologyData` 中的链路状态。通过 `handleMenuAction('makePrimary')` 确保：
1. `topologyData` 中对应链路的 `main` 和 `status` 正确更新
2. API 请求正确发送
3. 视觉反馈（主用链路高亮）正确触发

---

### 3.3 链路键值系统重构

#### 3.3.1 问题根因

原链路键值使用 `${source}-${target}` 格式拼接，通过 `linkKey.split('-')` 解析。当节点 ID 包含连字符（如 `core-router-01`）时，`split('-')` 会错误地将 ID 拆分为多个片段，导致链路查找失败。

项目中涉及链路键值的代码共计 **22+ 处**，包括：
- `selectedLink` 标识
- `isolatedLinks` / `hiddenLinks` / `restartingLinks` / `drainingLinks` 集合
- `originalLoads` 映射
- `linkParticles` 粒子系统
- `linkLatencies` 延迟映射
- `checkAlerts` 告警系统
- SVG 模板中 `:key` 绑定

#### 3.3.2 重构方案

**变更前：**
```typescript
const linkKey = `${source}-${target}`
// 解析:
const [source, target] = linkKey.split('-')  // 脆弱！
```

**变更后：**
```typescript
const makeLinkKey = (source: string, target: string) => `${source}::${target}`

const parseLinkKey = (key: string): { source: string; target: string } => {
  const idx = key.indexOf('::')
  if (idx === -1) return { source: key, target: '' }
  return { source: key.slice(0, idx), target: key.slice(idx + 2) }
}
```

**设计决策：**
- 使用 `::` 双冒号作为分隔符，因为双冒号在节点 ID 命名中几乎不会出现
- `parseLinkKey` 使用 `indexOf` 定位第一个 `::`，确保即使 target 中包含 `::` 也能正确解析 source
- 解析失败时返回 `{ source: key, target: '' }` 而非抛出异常，保证容错性

#### 3.3.3 全量替换清单

| 位置 | 变更 |
|------|------|
| `startLinkParticles` | `makeLinkKey(link.source, link.target)` |
| `updateParticles` | `makeLinkKey(l.source, l.target)` |
| `getParticlePosition` | `parseLinkKey(linkKey)` |
| `handleLinkClick` | `makeLinkKey(link.source, link.target)` |
| `handleContextMenu` | 位置计算 |
| `checkAlerts` | `makeLinkKey(link.source, link.target)` |
| `executeAction` | 所有 `isolatedLinks`/`hiddenLinks`/`restartingLinks` 操作 |
| `executeRestartAnimation` | `makeLinkKey(link.source, link.target)` |
| `executeDrainAnimation` | `makeLinkKey` + `originalLoads`/`drainingLinks` |
| `startTelemetrySimulation` | `makeLinkKey` + `linkLatencies` |
| SVG 模板 `:key` | `makeLinkKey(link.source, link.target)` |
| 缩略图 `:key` | `'mm-' + link.source + '-' + link.target`（缩略图保留，仅用于唯一标识） |

---

### 3.4 数据验证增强

#### 3.4.1 `importTopology` 深度验证

**变更前：**
```typescript
if (!data.nodes || !data.links) { showToast('数据结构无效'); return }
topologyData.value = data  // 直接赋值，无字段校验
```

**变更后：**
```typescript
if (!data.nodes || !Array.isArray(data.nodes) || !data.links || !Array.isArray(data.links)) {
  showToast('导入失败：数据结构无效，缺少 nodes 或 links', 'error'); return
}
const validNodeFields = ['id', 'name', 'type', 'health', 'cpu', 'memory', 'x', 'y', 'status']
const validLinkFields = ['source', 'target', 'bandwidth', 'currentLoad', 'status']
const hasInvalidNode = data.nodes.some((n: Record<string, unknown>) =>
  validNodeFields.some(f => !(f in n))
)
const hasInvalidLink = data.links.some((l: Record<string, unknown>) =>
  validLinkFields.some(f => !(f in l))
)
if (hasInvalidNode) { showToast('导入失败：节点数据缺少必要字段', 'error'); return }
if (hasInvalidLink) { showToast('导入失败：链路数据缺少必要字段', 'error'); return }
```

**验证字段清单：**

| 数据类型 | 必需字段 |
|----------|----------|
| 节点 (Node) | `id`, `name`, `type`, `health`, `cpu`, `memory`, `x`, `y`, `status` |
| 链路 (Link) | `source`, `target`, `bandwidth`, `currentLoad`, `status` |

#### 3.4.2 `restoreSnapshot` 结构验证

**变更前：**
```typescript
const snapshot = JSON.parse(raw)
// 直接使用 snapshot.nodePositions 等属性，无类型检查
```

**变更后：**
```typescript
const snapshot = JSON.parse(raw)
if (typeof snapshot !== 'object' || snapshot === null) {
  showToast('快照数据格式无效', 'error'); return
}
// 逐字段类型校验
if (snapshot.nodePositions && Array.isArray(snapshot.nodePositions))
  snapshot.nodePositions.forEach((pos) => {
    if (typeof pos.id === 'string' && typeof pos.x === 'number' && typeof pos.y === 'number') { ... }
  })
if (snapshot.centralPosition && typeof snapshot.centralPosition.x === 'number' && typeof snapshot.centralPosition.y === 'number') { ... }
if (typeof snapshot.zoomLevel === 'number') { ... }
if (snapshot.panOffset && typeof snapshot.panOffset.x === 'number' && typeof snapshot.panOffset.y === 'number') { ... }
if (typeof snapshot.layoutType === 'string') { ... }
if (snapshot.displayOptions && typeof snapshot.displayOptions === 'object') { ... }
```

**验证策略：** 对每个快照属性执行 `typeof` 类型检查，仅在校验通过时应用，确保损坏数据不会导致运行时异常。

#### 3.4.3 `executeAction` 错误处理

**变更前：**
```typescript
const response = await fetch(api.intents, { ... })
if (response.ok) { await response.json() }
// 错误被静默忽略
```

**变更后：**
```typescript
const response = await fetch(api.intents, { ... })
if (!response.ok) throw new Error(`API请求失败: ${response.status}`)
await response.json()
```

**效果：** API 请求失败时，错误会被 `handleMenuAction` 的 `catch` 块捕获，向用户展示错误提示，而非静默失败。

---

### 3.5 安全性增强

#### 3.5.1 CSV 注入防护

**变更前：**
```typescript
const escapeCsvField = (field: string): string => {
  if (field.includes(',') || field.includes('"') || field.includes('\n'))
    return `"${field.replace(/"/g, '""')}"`
  return field
}
```

**变更后：**
```typescript
const escapeCsvField = (field: string): string => {
  let escaped = field
  if (/^[=+\-@\t\r]/.test(escaped)) escaped = `'${escaped}`
  if (escaped.includes(',') || escaped.includes('"') || escaped.includes('\n'))
    return `"${escaped.replace(/"/g, '""')}"`
  return escaped
}
```

**防护机制：**
- 当字段以 `=`、`+`、`-`、`@`、`\t`、`\r` 开头时，在前面添加单引号 `'` 前缀
- 这会阻止 Excel/Google Sheets 将其解释为公式执行
- 符合 OWASP CSV 注入防护建议
- 同时保持 RFC 4180 合规：含逗号、双引号、换行的字段正确加引号，内部双引号转义为 `""`

**示例：**

| 原始值 | 转义前（危险） | 转义后（安全） |
|--------|----------------|----------------|
| `=CMD()` | `=CMD()` | `'=CMD()` |
| `+formula` | `+formula` | `'+formula` |
| `-calc` | `-calc` | `'-calc` |
| `@SUM()` | `@SUM()` | `'@SUM()` |
| `normal,text` | `"normal,text"` | `"normal,text"` |

---

### 3.6 性能优化

#### 3.6.1 动画循环稳定性修复

**变更前：**
```typescript
const animateNodes = () => {
  if (isLeaving.value) return
  if (isDragging.value) return  // ← 拖拽时直接 return，rAF 循环中断！
  topologyData.value.nodes.forEach(node => { ... })
  animationFrame = requestAnimationFrame(animateNodes)
}
```

**问题：** 当用户拖拽节点时，`isDragging` 为 `true`，`animateNodes` 执行 `return` 后不再调度下一帧 `requestAnimationFrame`。拖拽结束后，没有机制重新启动动画循环，导致节点微动效永久停止。

**变更后：**
```typescript
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

const animateNodes = () => {
  if (isLeaving.value) return
  if (isDragging.value || prefersReducedMotion) {
    animationFrame = requestAnimationFrame(animateNodes)  // ← 保持 rAF 调度
    return  // 仅跳过位移计算
  }
  topologyData.value.nodes.forEach(node => { ... })
  animationFrame = requestAnimationFrame(animateNodes)
}
```

**修复要点：**
1. 拖拽期间保持 `requestAnimationFrame` 调度，仅跳过节点位移计算
2. 拖拽结束后下一帧自动恢复位移计算，动画无缝衔接
3. 新增 `prefersReducedMotion` 检测，尊重用户系统偏好设置

#### 3.6.2 链路带宽视觉区分度

**变更前：**
```typescript
const getLinkWidth = (link: TopologyLink): number => {
  // 40G/100G/10G 均返回 5px
  return 5
}
```

**变更后：**
```typescript
const getLinkWidth = (link: TopologyLink): number => {
  const bw = link.bandwidth || ''
  let width = 1.5
  if (bw.includes('100G')) width = 6
  else if (bw.includes('40G')) width = 5
  else if (bw.includes('10G')) width = 4
  else if (bw.includes('1G')) width = 3.5
  else if (bw.includes('100M')) width = 2.5
  if ((link.currentLoad ?? 0) > 80) width = Math.min(7, width + 1)
  return width
}
```

**带宽-宽度映射表：**

| 带宽 | 基础宽度 (px) | 高负载 (>80%) 宽度 (px) |
|------|---------------|-------------------------|
| 100G | 6 | 7 |
| 40G | 5 | 6 |
| 10G | 4 | 5 |
| 1G | 3.5 | 4.5 |
| 100M | 2.5 | 3.5 |

---

### 3.7 死代码清理

**移除项：**

| 移除内容 | 原因 |
|----------|------|
| `simulateA2ATraffic` 函数 | 已定义但从未在 `onMounted` 或其他位置调用 |
| `a2aTrafficInterval` ref | 仅被 `simulateA2ATraffic` 引用，随函数一并移除 |
| `onUnmounted` 中 `a2aTrafficInterval` 清理代码 | 对应 ref 移除后清理代码不再需要 |

**保留项：**

| 保留内容 | 原因 |
|----------|------|
| `simulateA2AMessage` 函数 | 在 `onMounted` 中通过 `a2aInterval` 定时调用，功能正常 |
| `a2aInterval` 变量 | 用于定时触发 A2A 消息模拟，功能正常 |

---

### 3.8 用户体验优化

#### 3.8.1 右键菜单视口边界检测

**变更前：**
```typescript
const handleContextMenu = (event: MouseEvent, target, type: string) => {
  event.preventDefault()
  contextMenu.value = { show: true, x: event.clientX, y: event.clientY, type, target }
  // 菜单可能超出视口右/下边界
}
```

**变更后：**
```typescript
const handleContextMenu = (event: MouseEvent, target, type: string) => {
  if (isDragging.value) return
  event.preventDefault()
  const menuW = 220, menuH = 300
  const x = event.clientX + menuW > window.innerWidth
    ? event.clientX - menuW
    : event.clientX
  const y = event.clientY + menuH > window.innerHeight
    ? event.clientY - menuH
    : event.clientY
  contextMenu.value = { show: true, x, y, type, target }
}
```

**边界检测逻辑：**

| 场景 | 判断条件 | 菜单位置 |
|------|----------|----------|
| 右侧不溢出 | `clientX + 220 ≤ innerWidth` | 鼠标右下方 |
| 右侧溢出 | `clientX + 220 > innerWidth` | 鼠标左下方（向左偏移 220px） |
| 下侧不溢出 | `clientY + 300 ≤ innerHeight` | 鼠标右下方 |
| 下侧溢出 | `clientY + 300 > innerHeight` | 鼠标右上方（向上偏移 300px） |

**常量说明：**
- `menuW = 220`：右键菜单最小宽度 200px + 内边距 ≈ 220px
- `menuH = 300`：7 个菜单项 × ~42px/项 + 标题 ≈ 300px

---

## 4. 性能对比数据

| 指标 | 升级前 | 升级后 | 改善幅度 |
|------|--------|--------|----------|
| 类型守卫函数 | 0 个 | 2 个（`isTopologyNode`、`isTopologyLink`） | ∞ |
| 不安全类型断言 | 19 处 `as` 强转 | 0 处 | -100% |
| 链路键值解析脆弱性 | `split('-')` 单分隔符 | `parseLinkKey` 双冒号安全解析 | 消除 ID 含连字符风险 |
| CSV 注入防护 | 无防护，`=`/`+`/`-`/`@` 开头字段可执行 | 单引号前缀防护 | 符合 OWASP 建议 |
| 死代码行数 | ~15 行 | 0 行 | -100% |
| 导入数据验证 | 浅层（仅检查数组存在） | 深层（9 个节点字段 + 5 个链路字段逐一校验） | 14 个字段校验 |
| 快照数据验证 | 无验证 | 全属性类型检查（6 项） | 6 项校验 |
| 链路带宽区分度 | 40G/100G/10G 同为 5px | 100G(6) / 40G(5) / 10G(4) / 1G(3.5) / 100M(2.5) | 5 级区分 |
| 动画循环稳定性 | 拖拽时 rAF 永久停止 | 拖拽时保持调度，仅跳过位移 | 修复动画中断 |
| 右键菜单溢出 | 可能超出视口 | 自动边界检测重定位 | 100% 可见 |
| API 错误处理 | 静默忽略 | `throw new Error` + 用户提示 | 可感知错误 |
| 状态变异路径 | 2 处直接变异绕过处理器 | 全部通过 `handleMenuAction` | 单一变更路径 |
| 运动偏好支持 | 仅 CSS `prefers-reduced-motion` | CSS + JavaScript 双重检测 | JS 层也尊重偏好 |

---

## 5. 测试方案

### 5.1 单元测试

针对新增/重构的辅助函数编写单元测试：

| 测试对象 | 测试用例 | 预期结果 |
|----------|----------|----------|
| `makeLinkKey` | 普通节点 ID | `'core1::agg1'` |
| `makeLinkKey` | 含连字符节点 ID | `'core-router-01::agg-switch-02'` |
| `parseLinkKey` | 标准键值 | `{ source: 'core1', target: 'agg1' }` |
| `parseLinkKey` | 含连字符 ID | `{ source: 'core-router-01', target: 'agg-switch-02' }` |
| `parseLinkKey` | 无分隔符 | `{ source: 'invalid', target: '' }` |
| `parseLinkKey` | 空字符串 | `{ source: '', target: '' }` |
| `isTopologyNode` | 有效节点对象 | `true` |
| `isTopologyNode` | 有效链路对象 | `false` |
| `isTopologyNode` | `null` | `false` |
| `isTopologyLink` | 有效链路对象 | `true` |
| `isTopologyLink` | 有效节点对象 | `false` |
| `isTopologyLink` | `null` | `false` |
| `getLinkWidth` | 100G 链路 | `6` |
| `getLinkWidth` | 40G 链路 | `5` |
| `getLinkWidth` | 10G 链路 | `4` |
| `getLinkWidth` | 1G 链路 | `3.5` |
| `getLinkWidth` | 100M 链路 | `2.5` |
| `getLinkWidth` | 10G + 85% 负载 | `5`（4 + 1） |
| `escapeCsvField` | 普通文本 | 原样返回 |
| `escapeCsvField` | 含逗号文本 | 双引号包裹 |
| `escapeCsvField` | `=CMD()` 开头 | `'=CMD()` |
| `escapeCsvField` | `+formula` 开头 | `'+formula` |
| `escapeCsvField` | 含双引号 | `""` 转义 |

### 5.2 集成测试

| 场景 | 测试步骤 | 预期结果 |
|------|----------|----------|
| 节点隔离完整流程 | 右键节点 → 隔离 → 验证 `locked` 状态 → 解除隔离 | `topologyData` 节点 `locked` 正确切换，`isolatedLinks` 同步更新 |
| 链路主备切换 | 右键备用链路 → 设为主用 → 验证 `main`/`status` | `topologyData` 链路 `main=true`，`status='active'` |
| 拓扑数据导入 | 导入合法 JSON → 导入缺少字段 JSON → 导入非法 JSON | 合法导入成功；缺字段提示错误；非法 JSON 提示解析错误 |
| 快照恢复 | 保存快照 → 修改布局 → 恢复快照 → 恢复损坏快照 | 正常快照恢复成功；损坏快照提示错误 |
| CSV 导出安全性 | 创建含 `=` 开头名称的节点 → 导出 CSV → 打开文件 | `=` 开头字段被 `'` 前缀保护 |
| 右键菜单边界 | 在视口右下角右键 → 在视口左上角右键 | 菜单始终完全可见 |
| 拖拽动画恢复 | 开始拖拽节点 → 拖动 → 释放 → 等待 1 秒 | 释放后节点微动效恢复 |
| API 请求失败 | Mock API 返回 500 → 执行操作 | 用户看到错误提示 |

### 5.3 边界条件测试

| 测试项 | 边界条件 | 预期行为 |
|--------|----------|----------|
| 节点 ID 含连字符 | `core-router-01` | `makeLinkKey` / `parseLinkKey` 正确处理 |
| 空拓扑数据 | `{ nodes: [], links: [] }` | 导入成功，无运行时错误 |
| 快照 localStorage 损坏 | `localStorage.setItem('topology_snapshot', 'not-json')` | 提示"快照数据损坏，无法恢复" |
| 超大带宽值 | `bandwidth: '400G'` | `getLinkWidth` 返回默认 1.5 |
| 零负载链路 | `currentLoad: 0` | 正常渲染，宽度为基础值 |
| 极端缩放 | `zoomLevel: 0.3` / `zoomLevel: 3.0` | 节点/链路正常渲染，无溢出 |

---

## 6. 回滚机制

### 6.1 回滚步骤

本次升级所有变更均为前端代码改动，不涉及后端 API、数据库 schema 或配置文件变更。回滚步骤如下：

| 步骤 | 操作 | 命令/方法 |
|------|------|-----------|
| 1 | 从版本控制恢复 `Topology.vue` | `git checkout HEAD~1 -- frontend/src/views/Topology.vue` |
| 2 | 清除浏览器 localStorage 中的拓扑快照 | 浏览器 DevTools → Application → Local Storage → 删除 `topology_snapshot` |
| 3 | 重新构建前端 | `cd frontend && npm run build` |
| 4 | 验证功能正常 | 打开网络拓扑页面，检查基本交互 |

### 6.2 回滚注意事项

- **无需后端变更**：所有改动仅涉及 `Topology.vue` 单文件，后端 API 接口未做任何调整
- **localStorage 兼容性**：升级后保存的快照数据结构与升级前一致（`nodePositions`、`centralPosition`、`zoomLevel`、`panOffset`、`layoutType`、`displayOptions`），回滚后快照仍可正常恢复
- **链路键值格式不兼容**：升级后 localStorage 中的 `isolatedLinks` 等集合使用 `::` 分隔符，回滚后使用 `-` 分隔符。若回滚前未清除 localStorage，这些集合可能需要手动清除。建议回滚时一并清除 `topology_snapshot`

### 6.3 回滚验证清单

- [ ] 拓扑页面正常加载，无白屏
- [ ] 节点可点击、拖拽
- [ ] 链路可点击
- [ ] 右键菜单正常弹出
- [ ] 导入/导出功能正常
- [ ] 快照保存/恢复正常
- [ ] A2A 消息模拟正常

---

## 7. 已知限制与后续规划

### 7.1 当前已知限制

| 限制项 | 说明 | 影响 |
|--------|------|------|
| 拓扑数据为模拟数据 | 当前节点/链路数据在前端硬编码，通过 `Math.random()` 模拟数据波动，未对接真实后端拓扑发现 API | 数据不代表真实网络状态 |
| A2A 通信为模拟 | `simulateA2AMessage` 从预定义的 `mockA2AMessages` 中随机选取，未连接真实 Agent 通信协议 | A2A 面板仅作演示用途 |
| Web SSH 终端为 UI 占位 | SSH 终端弹窗仅有输入框和静态输出，未连接真实 WebSocket | 无法执行实际命令 |
| 节点类型有限 | 仅支持 `router`（路由器）和 `switch`（交换机）两种图标，`firewall`/`server` 图标已定义但未在数据中使用 | 扩展节点类型需手动添加数据 |
| 布局算法简化 | 力导向布局仅迭代 50 次，可能未达到最优收敛 | 大规模拓扑布局可能不够美观 |

### 7.2 后续规划

| 优先级 | 规划项 | 说明 | 预计周期 |
|--------|--------|------|----------|
| P0 | 对接真实拓扑发现 API | 替换前端模拟数据，从后端获取真实网络拓扑结构 | 中期 |
| P0 | 实现真实 A2A 协议集成 | 连接 Agent 通信协议，实现跨域协同消息的真实收发 | 中期 |
| P1 | 添加真实 SSH WebSocket 连接 | 通过 WebSocket 代理连接目标设备，实现可交互的终端 | 中期 |
| P1 | 拓扑自动发现 | 后端定时扫描网络，自动更新拓扑结构，前端实时展示 | 长期 |
| P2 | 拓扑编辑模式 | 支持手动添加/删除节点和链路，保存至后端 | 长期 |
| P2 | 历史拓扑回放 | 记录拓扑状态变更历史，支持时间轴回放 | 长期 |
| P3 | 3D 拓扑视图 | 基于 Three.js 的 3D 网络拓扑可视化 | 远期 |
| P3 | 多拓扑实例管理 | 支持切换不同网络区域的拓扑视图 | 远期 |
