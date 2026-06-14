# AI 助手全面升级设计规格 — 方案 B：智能体编排型

## 1. 概述

### 1.1 目标

对智维 AgentHub 的 AI 助手进行全面系统性升级，实现：
- **更智能**：从被动问答升级为主动感知+意图链推断+复杂任务自动编排
- **更便捷**：从多步操作简化为一句话/一键触发全流程
- **更专业**：知识库从静态文档升级为实时注入+混合检索+反馈闭环

### 1.2 核心原则

- **增强不重建**：在现有架构上升级，保持向后兼容
- **降级策略**：每个新能力都有降级路径，确保 LLM 不可用时系统仍可用
- **权限扩大**：助手可调用系统资源和功能，但遵循 RBAC 和高危操作审批机制
- **并行推进**：6 大模块独立升级，互不阻塞

### 1.3 升级模块总览

| 模块 | 当前状态 | 升级目标 |
|------|---------|---------|
| 意图理解 | 正则匹配+LLM增强 | 双轨竞速+隐含意图推断 |
| 对话管理 | 简单对话记忆 | DST状态追踪+跨会话记忆+行为学习 |
| Agent引擎 | ReAct单步推理 | Plan-Execute多步编排+反思修正 |
| 知识引擎 | 关键词RAG+8篇文档 | 混合RAG+实时注入+反馈闭环+扩充文档 |
| 交互体验 | 被动文本对话 | 主动推送+运维向导+多模态+语音+自适应模式 |
| 测试体系 | 无 | 自动化测试+指标基准 |

---

## 2. 意图理解引擎 v2

### 2.1 双轨竞速架构

```
用户消息
    ├─→ 正则快速路径 (<50ms) ──命中──→ 直接返回意图
    │                              未命中↓
    └─→ LLM FC 深度路径 (~1s) ────────→ 返回意图
         ∥
    隐含意图推断 (并行) ──────────→ 补充隐含意图
```

**正则快速路径**：保留现有 `NAVIGATION_PATTERNS`/`QUERY_PATTERNS`/`CONTROL_PATTERNS`，扩充更多模式（模糊匹配、口语化表达、缩写）。

**LLM FC 深度路径**：使用智谱 GLM 的 Function Calling，将意图分类定义为 tool schema：
- `navigate`：导航意图，参数 `route`
- `query`：查询意图，参数 `query_type`、`target`
- `control`：操控意图，参数 `action`、`target`、`params`
- `clarify`：澄清意图，参数 `question`
- `chitchat`：闲聊意图

**隐含意图推断**：基于对话上下文+系统状态，推断用户未明说的意图：
- "核心交换机CPU好像有点高" → 隐含意图：诊断+修复
- "又是这个告警" → 隐含意图：查看历史+批量处理

### 2.2 意图分类扩展

新增意图类型：

| 意图类型 | 示例 | 处理方式 |
|---------|------|---------|
| `plan_execute` | "帮我处理今天所有告警" | 触发 Plan-Execute Agent |
| `proactive_query` | "有什么需要注意的吗" | 触发环境感知引擎 |
| `wizard` | "帮我排查故障" | 触发运维向导 |
| `feedback` | "这个回答不对" | 触发知识反馈闭环 |
| `multimodal` | 图片/语音输入 | 触发多模态处理 |

### 2.3 实体识别增强

- 设备名模糊匹配（支持缩写、别名、正则）
- 时间实体解析（"昨天"、"最近一小时"、"上个季度"）
- 数量实体解析（"所有"、"前10个"、"超过80%的"）
- 代词消解增强（支持跨轮次指代）

### 2.4 文件变更

- 修改：`backend/agents/assistant_router.py` — 新增 LLM FC 意图分类、隐含意图推断、意图类型扩展
- 修改：`backend/agents/prompts.py` — 新增意图分类 Prompt、隐含意图推断 Prompt
- 新增：`backend/agents/intent_classifier.py` — 双轨竞速意图分类器
- 修改：`backend/api/assistant.py` — 新增 `/plan-execute` 端点

---

## 3. 对话状态追踪器 (DST)

### 3.1 对话状态模型

```python
class DialogueState:
    session_id: str
    turn_count: int
    current_intent: Optional[str]
    intent_history: List[IntentRecord]
    entities: Dict[str, EntitySlot]        # 实体槽位
    pending_actions: List[ActionRecord]     # 待执行动作
    user_preferences: Dict[str, Any]        # 用户偏好
    context_summary: str                    # 上下文压缩摘要
    last_active_time: datetime
```

### 3.2 核心能力

**实体追踪**：
- 跨轮次实体槽位填充（"查一下核心交换机" → "它的CPU呢" → 实体=核心交换机）
- 实体值变更追踪（"不，我说的是汇聚交换机" → 更新实体）
- 多实体并行追踪（"对比核心和汇聚的CPU" → 两个实体槽位）

**意图切换检测**：
- 检测用户是否切换话题（"算了，先看看告警吧"）
- 保留原话题状态，支持回溯（"继续刚才的排查"）

**上下文压缩**：
- 超过 10 轮对话时，将早期对话压缩为结构化摘要
- 保留关键实体和未完成动作
- 压缩使用 LLM，保留语义信息

**跨会话记忆**：
- 基于 `user_id` 持久化对话摘要到数据库
- 新会话开始时加载最近 3 次会话摘要
- 记住用户常用操作模式（"你通常先看告警再处理"）

**行为学习**：
- 记录用户操作序列（查看设备→诊断→执行修复）
- 当检测到相似模式时，主动推荐下一步操作
- 基于频率统计，预加载用户可能查询的数据

### 3.3 文件变更

- 新增：`backend/agents/dialogue_state.py` — DST 核心实现
- 修改：`backend/agents/assistant_router.py` — 集成 DST
- 修改：`backend/agents/llm_gateway.py` — 上下文压缩集成 DST
- 修改：`frontend/src/stores/assistant.ts` — 前端 DST 状态同步
- 修改：`backend/api/assistant.py` — 会话状态 API

---

## 4. Plan-Execute Agent

### 4.1 核心流程

```
复杂意图
    ↓
PlanGenerator (LLM) → 生成执行计划
    ↓                      ↓
PlanReviewer (规则)  → 校验计划可行性
    ↓
StepExecutor → 逐步执行
    ├─ 工具调用 → 观察结果
    ├─ 条件分支 → 根据结果选择路径
    └─ 并行执行 → 无依赖步骤并发
    ↓
ResultValidator → 验证执行结果
    ├─ 成功 → 继续下一步
    ├─ 失败 → 自动重试(最多2次) / 降级方案
    └─ 需确认 → 暂停等待用户
    ↓
Reflector (LLM) → 反思修正
    ├─ 结果符合预期 → 完成
    └─ 结果不符 → 修改计划 → 重新执行
    ↓
FinalReport → 生成结构化执行报告
```

### 4.2 执行计划模型

```python
class ExecutionPlan:
    plan_id: str
    goal: str                          # 用户原始目标
    steps: List[PlanStep]              # 执行步骤
    dependencies: Dict[str, List[str]] # 步骤依赖关系
    conditions: Dict[str, Condition]   # 条件分支
    rollback_plan: Optional[ExecutionPlan]  # 回滚计划

class PlanStep:
    step_id: str
    description: str
    tool: str                          # 使用的工具
    params: Dict[str, Any]
    depends_on: List[str]              # 依赖的步骤ID
    risk_level: str                    # low/medium/high
    retry_count: int = 0
    max_retries: int = 2
    fallback: Optional[PlanStep]       # 降级方案
```

### 4.3 智能确认分级

| 风险等级 | 操作类型 | 确认方式 | 示例 |
|---------|---------|---------|------|
| low | 查询、导航 | 自动执行 | 查询设备状态 |
| medium | 创建、修改 | 面板内一键确认 | 创建意图、修改配置 |
| high | 删除、重启、隔离 | 详细确认(勾选+理由) | 重启设备、隔离节点 |

### 4.4 运维向导模板

预置向导模板，每个模板是一个预定义的 ExecutionPlan：

| 向导名称 | 触发条件 | 流程步骤 |
|---------|---------|---------|
| 故障排查向导 | "帮我排查故障" / 告警触发 | 1.收集告警 2.定位设备 3.诊断根因 4.推荐修复 5.执行修复 6.验证结果 |
| 变更实施向导 | "我要做变更" / 变更窗口 | 1.备份配置 2.预检 3.实施变更 4.验证 5.回滚(如需) |
| 应急响应向导 | "应急" / 告警风暴 | 1.评估影响 2.隔离故障 3.通知相关方 4.修复 5.恢复 |
| 日常巡检向导 | "巡检" / 定时触发 | 1.设备健康检查 2.性能指标采集 3.异常识别 4.生成报告 |
| 批量操作向导 | "批量" + 操作 | 1.选择目标 2.预览影响 3.分批执行 4.结果汇总 |

### 4.5 文件变更

- 新增：`backend/agents/plan_executor.py` — Plan-Execute Agent 核心
- 新增：`backend/agents/wizard_templates.py` — 运维向导模板库
- 修改：`backend/agents/react_engine.py` — 与 Plan-Execute 协作
- 修改：`backend/agents/tool_registry.py` — 工具链组合支持
- 修改：`backend/api/assistant.py` — 新增 `/plan-execute`、`/wizards` 端点
- 修改：`frontend/src/stores/assistant.ts` — Plan-Execute 前端状态
- 修改：`frontend/src/components/AiAssistant/ChatPanel.vue` — 执行计划 UI、向导 UI

---

## 5. 环境感知引擎（主动式助手）

### 5.1 事件驱动感知

```python
class EnvironmentAwarenessEngine:
    async def on_alert(self, alert: Alert):
        # 告警事件 → 自动诊断 → 推送建议
        diagnosis = await self.diagnose(alert)
        suggestion = await self.generate_suggestion(diagnosis)
        await self.push_to_user(suggestion)

    async def on_metric_anomaly(self, metric: MetricAnomaly):
        # 指标异常 → 趋势分析 → 预警推送
        trend = await self.analyze_trend(metric)
        if trend.is_escalating:
            await self.push_warning(trend)

    async def on_schedule(self, schedule: CronSchedule):
        # 定时巡检 → 自动执行 → 报告推送
        report = await self.run_inspection(schedule)
        await self.push_report(report)
```

### 5.2 主动推送类型

| 推送类型 | 触发条件 | 推送内容 | 交互方式 |
|---------|---------|---------|---------|
| 告警诊断 | 新告警产生 | 根因分析+修复建议 | 一键执行/忽略 |
| 趋势预警 | 指标持续上升 | 趋势图+建议 | 查看详情/设置阈值 |
| 巡检报告 | 定时/手动触发 | 结构化报告 | 查看详情/导出 |
| 操作建议 | 检测到可优化项 | 优化建议+预期效果 | 确认执行/稍后 |
| 知识提醒 | 检测到用户可能需要的知识 | 相关知识链接 | 查看/忽略 |

### 5.3 行为预测

- 基于用户操作历史，预测下一步操作并预加载数据
- 基于时间模式（如每周二凌晨负载高峰），提前推送提醒
- 基于设备关联（如核心交换机异常时，提醒检查下游设备）

### 5.4 文件变更

- 新增：`backend/agents/environment_awareness.py` — 环境感知引擎
- 修改：`backend/api/assistant.py` — 新增 `/proactive` 端点
- 修改：`backend/core/websocket_manager.py` — 主动推送集成
- 新增：`frontend/src/components/AiAssistant/ProactivePanel.vue` — 主动推送面板
- 修改：`frontend/src/components/AiAssistant/FloatingBall.vue` — 推送通知角标
- 修改：`frontend/src/composables/useActionEngine.ts` — WebSocket 事件监听扩展

---

## 6. 知识引擎 v2

### 6.1 混合 RAG 检索

```
用户问题
    ├─→ 向量检索 (top-5, 余弦相似度 > 0.6)
    ├─→ 关键词检索 (BM25, top-5)
    └─→ 实体检索 (设备/告警/配置匹配)
         ↓
    融合重排序 (RRF + LLM Reranker)
         ↓
    top-3 结果 → LLM 生成回答
```

**向量检索升级**：
- 保留现有 SentenceTransformer 降级策略
- 新增：如果 sentence-transformers 可用，使用 `shibing624/text2vec-base-chinese` 模型
- 新增：支持自定义 Embedding 模型配置

**BM25 关键词检索**：
- 使用 jieba 分词
- BM25 算法评分
- 与向量检索结果融合（Reciprocal Rank Fusion）

**LLM Reranker**：
- 对融合后的 top-10 结果，使用 LLM 判断相关性
- 输出重排序后的 top-3

### 6.2 实时知识注入

```python
class RealtimeKnowledgeInjector:
    async def inject_from_alerts(self):
        # 从告警系统提取实时知识
        alerts = await self.get_recent_alerts()
        for alert in alerts:
            doc = self.alert_to_knowledge(alert)
            await self.rag_engine.add_document(doc)

    async def inject_from_metrics(self):
        # 从指标系统提取实时知识
        metrics = await self.get_anomaly_metrics()
        for metric in metrics:
            doc = self.metric_to_knowledge(metric)
            await self.rag_engine.add_document(doc)

    async def inject_from_audit(self):
        # 从审计日志提取操作知识
        logs = await self.get_recent_operations()
        for log in logs:
            doc = self.operation_to_knowledge(log)
            await self.rag_engine.add_document(doc)
```

- 定时（每5分钟）从系统各模块提取实时数据
- 转化为结构化知识文档并注入 RAG 引擎
- 带过期时间，旧知识自动清理

### 6.3 知识反馈闭环

```python
class KnowledgeFeedbackLoop:
    async def on_user_feedback(self, feedback: Feedback):
        # 用户反馈"回答不对" → 记录 → 分析 → 优化
        if feedback.is_negative:
            await self.record_negative_case(feedback)
            await self.analyze_and_improve(feedback)

    async def on_correction(self, correction: Correction):
        # 用户纠正 → 更新知识
        await self.update_knowledge(correction)
        await self.rebuild_affected_index(correction)
```

- 前端消息增加 👍/👎 反馈按钮
- 负面反馈自动记录到 `knowledge_feedback` 表
- 定期分析负面反馈，优化 Prompt 或补充知识
- 用户纠正直接更新知识库

### 6.4 知识库扩充

新增运维知识文档（从8篇扩充到20+篇）：

| 类别 | 新增文档 |
|------|---------|
| 网络协议 | SD-WAN、IPv6、MPLS、VXLAN |
| 安全运维 | 防火墙策略管理、DDoS防护、零信任网络 |
| 云原生 | 容器网络(CNI)、K8s网络策略、Service Mesh |
| 自动化 | Ansible网络自动化、Netconf/YANG、Telemetry |
| 运维实践 | 变更管理流程、容量规划、SLA管理 |

### 6.5 智能预加载

- 用户打开某页面时，预加载该页面相关的知识文档到 RAG 上下文
- 根据当前系统状态（如告警数），预加载故障排查相关知识
- 基于用户历史，预加载其最可能查询的知识

### 6.6 文件变更

- 修改：`backend/knowledge/rag_engine.py` — 混合检索、BM25、Reranker
- 新增：`backend/knowledge/realtime_injector.py` — 实时知识注入
- 新增：`backend/knowledge/feedback_loop.py` — 知识反馈闭环
- 修改：`backend/knowledge/qa_agent.py` — 集成混合检索
- 修改：`backend/knowledge/document_parser.py` — 支持更多格式
- 修改：`backend/api/knowledge.py` — 反馈 API
- 修改：`frontend/src/components/AiAssistant/ChatPanel.vue` — 👍/👎 按钮

---

## 7. 交互体验升级

### 7.1 自适应对话模式

| 模式 | 触发条件 | UI特征 |
|------|---------|--------|
| 标准模式 | 默认 | 完整对话+解释 |
| 紧急模式 | 告警风暴(>5条/分钟) | 精简卡片，只显示关键信息和操作按钮 |
| 报告模式 | 巡检/汇总请求 | 结构化报告视图，支持导出 |
| 教学模式 | 新用户/主动请求 | 每步附带解释和知识链接 |

### 7.2 智能快捷栏

动态生成规则：
```
快捷栏 = f(当前页面, 用户角色, 系统状态, 用户偏好)

示例：
- 拓扑页 + admin + 有告警 → [定位故障节点] [批量诊断] [隔离故障]
- 意图中心 + admin + 待审批 > 0 → [批量审批] [查看高风险] [创建意图]
- 自愈页 + operator + 自愈中 → [查看进度] [暂停自愈] [手动接管]
```

### 7.3 语音交互

- 前端使用 Web Speech API 进行语音识别
- 识别结果作为文本输入发送给助手
- 助手回复可选择语音播报（SpeechSynthesis API）
- 语音模式下自动切换为精简回复

### 7.4 多模态输入

- 截图上传：OCR 识别文字 → 提取设备名/告警信息 → 自动关联
- 拓扑交互：在拓扑图上圈选节点 → 助手识别选中节点 → 批量操作
- 文件上传：支持日志文件、配置文件、PDF 上传分析

### 7.5 文件变更

- 修改：`frontend/src/components/AiAssistant/ChatPanel.vue` — 自适应模式、语音、多模态
- 新增：`frontend/src/components/AiAssistant/ProactivePanel.vue` — 主动推送面板
- 新增：`frontend/src/components/AiAssistant/VoiceInput.vue` — 语音输入组件
- 新增：`frontend/src/components/AiAssistant/WizardRunner.vue` — 运维向导组件
- 修改：`frontend/src/components/AiAssistant/BubbleCard.vue` — 智能快捷栏
- 修改：`frontend/src/stores/assistant.ts` — 新状态和方法
- 修改：`frontend/src/composables/useAssistantContext.ts` — 动态快捷栏生成

---

## 8. 工具编排引擎

### 8.1 工具链组合

```python
class ToolChain:
    name: str
    steps: List[ToolStep]
    parallel_groups: List[List[int]]  # 可并行执行的步骤索引

# 示例：故障自愈链
fault_healing_chain = ToolChain(
    name="fault_auto_healing",
    steps=[
        ToolStep(tool="query_topology", params={"filter": "alert"}),
        ToolStep(tool="query_device", params={"target": "$step1.devices[0]"}),
        ToolStep(tool="execute_self_healing", params={"device": "$step2.device"}),
        ToolStep(tool="system_health", params={}),  # 验证
    ]
)
```

### 8.2 并行执行

- 分析步骤间依赖关系（DAG）
- 无依赖步骤使用 `asyncio.gather` 并行执行
- 有依赖步骤按序执行

### 8.3 自动降级/重试

- 工具调用失败时，自动重试（最多2次，指数退避）
- 重试仍失败时，查找降级工具（如 `query_device` 降级为 `system_health`）
- 所有降级路径在工具注册时预定义

### 8.4 文件变更

- 修改：`backend/agents/tool_registry.py` — 工具链定义、依赖分析、并行执行
- 修改：`backend/agents/mcp_registry.py` — 语义路由增强
- 新增：`backend/agents/tool_chains.py` — 预定义工具链库

---

## 9. 测试体系

### 9.1 意图识别测试

```python
INTENT_TEST_CASES = [
    {"input": "看看核心交换机状态", "expected_intent": "query", "expected_type": "device_status"},
    {"input": "帮我处理告警", "expected_intent": "plan_execute"},
    {"input": "去拓扑页面", "expected_intent": "navigate", "expected_route": "/topology"},
    # ... 100+ test cases
]
```

目标：意图识别准确率 > 90%

### 9.2 对话连贯性测试

- 多轮对话测试集（5轮+）
- 实体追踪准确率 > 85%
- 指代消解准确率 > 80%

### 9.3 工具调用测试

- 每个工具至少3个测试用例
- 工具链组合测试
- 降级路径测试

### 9.4 性能基准

| 指标 | 当前值 | 目标值 |
|------|-------|-------|
| 正则意图识别延迟 | <50ms | <50ms |
| LLM意图识别延迟 | ~2s | <1.5s |
| 首次响应时间 | ~3s | <2s |
| 流式首token延迟 | ~1s | <500ms |
| RAG检索延迟 | N/A | <500ms |
| Plan生成延迟 | N/A | <5s |

### 9.5 文件变更

- 新增：`tests/test_intent_classifier.py`
- 新增：`tests/test_dialogue_state.py`
- 新增：`tests/test_plan_executor.py`
- 新增：`tests/test_rag_engine.py`
- 新增：`tests/test_tool_chains.py`

---

## 10. API 端点汇总

### 新增端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/v1/assistant/plan-execute` | POST | Plan-Execute 复杂任务执行 |
| `/api/v1/assistant/plan-execute/{id}/step/{step_id}/confirm` | POST | 确认执行计划步骤 |
| `/api/v1/assistant/plan-execute/{id}/step/{step_id}/cancel` | POST | 取消执行计划步骤 |
| `/api/v1/assistant/wizards` | GET | 获取运维向导列表 |
| `/api/v1/assistant/wizards/{name}/start` | POST | 启动向导 |
| `/api/v1/assistant/wizards/{id}/step` | POST | 向导下一步 |
| `/api/v1/assistant/proactive/suggestions` | GET | 获取主动建议 |
| `/api/v1/assistant/proactive/insights` | GET | 获取环境洞察 |
| `/api/v1/assistant/voice/transcribe` | POST | 语音转文字 |
| `/api/v1/assistant/multimodal/analyze` | POST | 多模态分析 |
| `/api/v1/assistant/feedback` | POST | 提交反馈 |
| `/api/v1/assistant/dialogue-state/{session_id}` | GET | 获取对话状态 |
| `/api/v1/knowledge/feedback` | POST | 知识反馈 |
| `/api/v1/knowledge/feedback/stats` | GET | 反馈统计 |
| `/api/v1/knowledge/realtime/status` | GET | 实时知识注入状态 |

### 修改端点

| 端点 | 变更 |
|------|------|
| `/api/v1/assistant/chat` | 集成 DST + 双轨意图分类 |
| `/api/v1/assistant/react-chat` | 集成工具编排引擎 |
| `/api/v1/assistant/chat/stream` | 集成 DST + 自适应模式 |

---

## 11. 数据库变更

### 新增表

```sql
-- 对话状态持久化
CREATE TABLE dialogue_states (
    session_id VARCHAR(64) PRIMARY KEY,
    user_id INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 知识反馈
CREATE TABLE knowledge_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id VARCHAR(64),
    message_id VARCHAR(64),
    feedback_type VARCHAR(20) NOT NULL,  -- positive/negative/correction
    original_answer TEXT,
    correction TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 执行计划
CREATE TABLE execution_plans (
    plan_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64),
    user_id INTEGER NOT NULL,
    goal TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    result_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 用户行为记录
CREATE TABLE user_behavior_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    action_detail TEXT,
    context_route VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 主动推送记录
CREATE TABLE proactive_pushes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    push_type VARCHAR(50) NOT NULL,
    content_json TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP
);
```

---

## 12. 实施优先级

6 大模块并行推进，但内部按依赖关系排序：

**第一批（核心基础，无外部依赖）**：
1. 意图理解引擎 v2（双轨竞速 + 隐含意图）
2. 对话状态追踪器 (DST)
3. 知识引擎 v2（混合 RAG + 文档扩充）

**第二批（依赖第一批）**：
4. Plan-Execute Agent（依赖意图理解 + DST + 工具编排）
5. 工具编排引擎（依赖工具注册）

**第三批（依赖前两批）**：
6. 环境感知引擎（依赖 Plan-Execute + 知识引擎）
7. 交互体验升级（依赖所有后端模块）

**持续进行**：
8. 测试体系建设（随各模块同步建设）
