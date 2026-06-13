          
以下是对 **智维 AgentHub** 项目的全面分析报告。

---

## 一、项目概述

**智维 AgentHub** 是一套基于大语言模型多智能体协同的**意图驱动网络自愈与运维系统**。核心定位：面向电信运营商、大型企业网络运维场景，通过自然语言意图输入，经多Agent协同编排实现从意图理解、冲突检测、策略生成、命令执行到结果验证的全链路自动化网络运维闭环。

---

## 二、项目结构

```
智维 AgentHub/
├── backend/                        # 后端（Python/FastAPI）
│   ├── api/                        # 30+ REST API路由模块
│   ├── agents/                     # 智能体编排（15+ Agent）
│   ├── core/                       # 核心模块（安全/配置/WebSocket）
│   │   └── security/               # RBAC/Prompt注入防护/Token黑名单
│   ├── cross_domain/               # A2A跨域通信协议
│   ├── database/                   # SQLAlchemy数据模型（30+表）
│   ├── knowledge/                  # RAG知识库引擎
│   ├── mcp/                        # MCP工具管理
│   ├── observability/              # 可观测性（链路追踪/指标/健康）
│   ├── security/                   # 安全模块（沙箱/回滚/限流/异常检测）
│   ├── telemetry/                  # 遥测/SLA评估/策略重建
│   ├── workflow/                   # 工单管理
│   ├── compute/                    # 算力调度
│   ├── map/                        # 地图POI/路径规划
│   ├── integrations/               # Prometheus/Terraform/Webhook集成
│   ├── edge_agent/                 # 边缘Agent
│   └── requirements.txt
├── frontend/                       # 前端（Vue 3 + Vite）
│   ├── src/
│   │   ├── components/AiAssistant/ # AI助手组件群
│   │   ├── composables/            # 7个组合式函数
│   │   ├── router/                 # 路由配置（19个页面）
│   │   ├── stores/                 # 5个Pinia状态仓库
│   │   ├── utils/                  # 工具函数（API客户端/JWT/意图解析等）
│   │   ├── views/                  # 19个页面视图
│   │   └── config/                 # 前端配置
│   └── package.json
├── docs/                           # 设计文档与升级方案
├── docker-compose.yml              # 9个容器服务编排
├── SYSTEM_INTRODUCTION.md          # 系统完整介绍文档
├── README.md                       # 项目说明
└── start.py                        # 启动脚本
```

---

## 三、技术栈

### 前端
| 技术 | 版本 | 用途 |
|------|------|------|
| Vue 3 | 3.4+ | Composition API + Script Setup |
| Vite | 5.1+ | 构建工具，esbuild压缩 |
| Element Plus | 2.6+ | UI组件库 |
| Pinia | 2.1+ | 状态管理 |
| Vue Router | 4.3+ | 路由（含RBAC守卫） |
| ECharts | 5.5+ | 图表/拓扑可视化 |
| Leaflet + 高德地图 | 1.9+ / JSAPI | 双引擎地图 |
| TypeScript | 5.3+ | 类型检查 |
| DOMPurify | 3.4+ | XSS防护 |
| Sass Embedded | 1.100+ | 样式预处理 |

### 后端
| 技术 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.100+ | 异步ASGI框架 |
| SQLAlchemy | 2.0+ | ORM（异步模式+asyncpg） |
| Pydantic | 2.0+ | 数据验证 + Settings |
| LangChain + LangGraph | 0.1+ / 0.0.30+ | LLM编排/Agent工作流 |
| DeepSeek API | deepseek-chat | 意图解析/对话增强/配置生成 |
| 智谱GLM | glm-4-flash | Function Calling/流式对话 |
| ncclient | 0.6+ | NETCONF设备管理 |
| websockets | 12.0+ | WebSocket实时通信 |
| InfluxDB Client | 1.30+ | 时序遥测数据 |
| Redis | 5.0+ | 缓存/限流 |
| OpenTelemetry | 1.20+ | 链路追踪 |
| sentence-transformers | 2.2+ | RAG语义嵌入 |
| scikit-learn | 1.3+ | SLA预测模型 |

### 数据库
- **PostgreSQL 15** — 业务数据（生产环境）
- **SQLite** — 开发模式
- **Redis 7** — 缓存/限流/会话
- **InfluxDB** — 时序遥测数据
- **ChromaDB** — 向量存储（RAG）

---

## 四、核心功能模块

### 4.1 前端页面（19个路由视图）

| 路由路径 | 页面 | 角色权限 | 说明 |
|----------|------|----------|------|
| `/` | Dashboard | admin/operator/viewer | 指挥舱仪表盘 |
| `/intent` | IntentCenter | admin/operator/viewer | 意图中心（核心页面） |
| `/topology` | Topology | admin/operator/viewer | 网络拓扑可视化 |
| `/self-healing` | SelfHealing | admin/operator/viewer | 自愈中心 |
| `/mcp-tools` | MCPTools | admin/operator/viewer | MCP工具管理 |
| `/agent-map` | AgentMap | admin/operator/viewer | 智能体地图 |
| `/workflow` | WorkOrderBoard | admin/operator/viewer | 工单看板 |
| `/playbooks` | Playbooks | admin/operator/viewer | 运维剧本 |
| `/knowledge` | KnowledgeBase | admin/operator/viewer | 知识库 |
| `/sla` | SLAPrediction | admin/operator/viewer | SLA预测 |
| `/observability` | Observability | admin/operator/viewer | 可观测性 |
| `/notifications` | Notifications | admin/operator/viewer | 通知中心 |
| `/audit-logs` | AuditLogs | admin/operator | 审计日志 |
| `/webhooks` | WebhookManager | admin/operator | Webhook管理 |
| `/scheduler` | Scheduler | admin/operator | 意图调度 |
| `/failed-intents` | FailedIntents | admin/operator | 失败意图分析 |
| `/llm-router` | LLMRouter | admin | LLM路由管理 |
| `/users` | UserManagement | admin | 用户管理 |
| `/login` | Login | 无需认证 | 登录页 |

### 4.2 后端API模块（30+路由模块，90+端点）

核心API模块列表（来自 `backend/api/main.py` 的路由注册）：

| 模块 | 前缀 | 文件 |
|------|------|------|
| 认证授权 | `/api/v1/auth` | auth.py |
| 意图管理 | `/api/v1/intents` | intents.py |
| 事件告警 | `/api/v1/events` | events.py |
| Agent管理 | `/api/v1/agents` | agents.py |
| 验证 | `/api/v1/validation` | validation.py |
| 系统熔断 | `/api/v1/system` | fuse.py |
| 分布式锁 | `/api/v1/locks` | locks.py |
| 配置提交 | `/api/v1/commit` | commit.py |
| MCP工具 | `/api/v1/mcp-tools` | mcp_tools.py |
| 速率限制 | `/api/v1/rate-limit` | rate_limit.py |
| 网络拓扑 | `/api/v1/topology` | topology.py |
| 跨域管理 | `/api/v1/cross-domain` | cross_domain.py |
| 遥测数据 | `/api/v1/telemetry` | telemetry.py |
| 知识问答 | `/api/v1/knowledge` | knowledge.py |
| 工单管理 | `/api/v1/workflow` | workflow.py |
| 算力调度 | `/api/v1/compute` | compute.py |
| 地图服务 | `/api/v1/map` | map.py |
| 澄清对话 | `/api/v1/clarification` | clarification.py |
| 可观测性 | `/api/v1/observability` | observability.py |
| 失败意图 | `/api/v1/failed-intents` | failed_intents.py |
| LLM路由 | `/api/v1/llm-router` | llm_router.py |
| 意图调度 | `/api/v1/scheduler` | intent_scheduler.py |
| SLA预测 | `/api/v1/sla` | sla_prediction.py |
| 意图模板 | `/api/v1/intent-templates` | intent_templates.py |
| 运维剧本 | `/api/v1/playbooks` | playbooks.py |
| 灰度自愈 | `/api/v1/grayscale-healing` | grayscale_healing.py |
| Webhook | `/api/v1/webhooks` | webhooks.py |
| 指标 | `/api/v1/metrics` | metrics.py |
| Agent管理增强 | `/api/v1/agent-management` | agent_management.py |
| Terraform | `/api/v1/terraform` | terraform.py |
| 审计日志 | `/api/v1/audit-logs` | audit_logs.py |
| V2增强 | `/api/v2/*` | v2.py |
| 健康检查 | `/api/v1/health` | main.py内联 |
| WebSocket | `/ws` | main.py内联 |

### 4.3 智能体系统（15+ Agent）

后端 `backend/agents/` 目录包含以下核心Agent模块：

| 文件 | Agent | 职责 |
|------|-------|------|
| `orchestrator.py` | MultiAgentOrchestrator | 多Agent编排（Supervisor/Parallel/Debate三种模式） |
| `intent_parser.py` | IntentParserAgent | 意图解析（9种意图类型） |
| `conflict_detector.py` | ConflictDetectorAgent | 5类冲突规则检测 |
| `policy_planner.py` | PolicyPlannerAgent | 华为/Cisco/H3C三厂商策略生成 |
| `execution_agent.py` | ExecutionAgent | 沙箱检测+设备下发 |
| `react_engine.py` | ReActEngine | ReAct推理引擎（智谱GLM Function Calling） |
| `assistant_router.py` | AssistantRouterAgent | AI助手路由（规则+LLM增强） |
| `llm_gateway.py` | LLMGateway | 统一LLM调用网关（DeepSeek/智谱双提供商） |
| `llm_router.py` | LLMRouter | LLM路由与故障转移 |
| `deepseek_service.py` | DeepSeekService | DeepSeek API封装 |
| `zhipu_service.py` | ZhiPuService | 智谱GLM API封装 |
| `a2a_bus.py` | A2ABus | Agent间通信总线（发布订阅模式） |
| `registry.py` | AgentRegistry | Agent注册发现 |
| `security.py` | SecurityAgent | 安全检测 |
| `clarification.py` | ClarificationAgent | 澄清对话 |
| `proactive_notifier.py` | ProactiveNotifier | 主动通知 |
| `playbook_engine.py` | PlaybookEngine | 运维剧本执行 |
| `tool_registry.py` | ToolRegistry | 工具注册 |
| `tool_orchestrator.py` | ToolOrchestrator | 工具编排 |
| `grayscale_healing.py` | GrayscaleHealing | 灰度自愈 |
| `agent_scorer.py` | AgentScorer | Agent评分 |
| `agent_hot_upgrade.py` | AgentHotUpgrade | Agent热升级 |
| `intent_scheduler.py` | IntentScheduler | 意图调度 |
| `dialogue_state.py` | ContextCompressor | 对话上下文压缩 |
| `multimodal_processor.py` | MultimodalProcessor | 多模态处理 |

---

## 五、系统架构

### 5.1 四层架构

```
展示层: Vue 3 + Element Plus + ECharts + Leaflet/高德地图
网关层: Nginx 反向代理 + Gzip + 静态缓存 + WebSocket代理
服务层: FastAPI + 30+ API模块 + WebSocket实时通信
数据层: PostgreSQL + Redis + InfluxDB + SQLite + ChromaDB
```

### 5.2 前后端通信

**REST API通信：**
- 前端通过 `apiClient.ts` 封装的 `fetch` 请求与后端通信
- JWT Bearer Token 认证，自动刷新（401时用refresh_token续期）
- 熔断检测（503响应自动触发前端熔断状态）
- 请求配置来自 `config/index.ts` 的 `VITE_API_BASE_URL` 环境变量

**WebSocket实时通信：**
- 端点：`/ws?token=<jwt_token>`
- 15种消息类型（connection_established / message / notification / status_update / topology_update / device_update / alert / intent_update / assistant_action / proactive_notification / playbook_step / grayscale_progress / sla_alert / emergency_fuse / ping/pong）
- 前端 `useWebSocket.ts` 组合式函数：单例模式、自动重连（最多5次递增延迟）、30秒心跳、认证失败停止重连、降级轮询
- 后端 `websocket_manager.py`：JWT认证、连接数限制（全局+每用户）、60秒超时检测

### 5.3 LLM集成架构

```
LLM Gateway (llm_gateway.py)
├── DeepSeek — 意图解析/对话增强/配置生成/故障诊断
├── 智谱GLM — Function Calling/流式对话/意图解析
├── 故障转移 — 自动切换提供商
└── 按任务类型路由：
    INTENT_PARSE → 智谱GLM → DeepSeek → 规则匹配
    COPILOT_CHAT → DeepSeek → 智谱GLM
    COPILOT_STREAM → DeepSeek → 智谱GLM
    CONFIG_GENERATE → 智谱GLM → DeepSeek
    FAULT_DIAGNOSE → 智谱GLM → DeepSeek
```

ReAct推理引擎（`react_engine.py`）：智谱GLM Function Calling，最多5轮推理循环，高危操作暂停等审批。

### 5.4 A2A跨域通信

- `a2a_bus.py` — 发布订阅消息总线，1000条历史消息缓存
- `a2a_protocol.py` — JSON-RPC 2.0协议，JWT认证
- 支持方法：`agent.discover` / `agent.call` / `agent.status`
- `semantic_router.py` — 语义路由（关键词提取 + 能力匹配0.7权重 + 负载评分0.3权重）

### 5.5 安全架构（6层纵深防护）

1. **Prompt注入防护** (`prompt_guard.py`) — 58种恶意模式检测
2. **意图安全扫描** (`intent_scanner.py`) — SQL/Shell/路径遍历检测
3. **命令沙箱检测** (`security.py`) — 19条危险命令 + 31条恶意模式
4. **变更窗口管理** (`change_window.py`) — 时间段控制
5. **配置回滚** (`config_rollback.py`) — 自动备份/回滚
6. **速率限制** (`rate_limiter_middleware.py`) — 滑动窗口 + 角色限流

---

## 六、数据模型

后端 `database/models.py` 定义了 **30+ 数据表**，核心表包括：

| 表名 | 用途 |
|------|------|
| users | 用户认证与RBAC权限 |
| intents | 意图生命周期（含SLA条件/执行状态/冲突检测） |
| self_healing_events | 故障自愈事件 |
| policy_templates | 策略配置模板（三厂商） |
| agent_registry | Agent注册信息 |
| devices | 网络设备（含CPU/内存/SSH/NETCONF端口） |
| device_links | 设备链路关系 |
| audit_logs | 操作审计日志 |
| mcp_tools | MCP工具定义 |
| intent_templates | 意图模板（含评分/标签/版本） |
| sla_evaluation_results | SLA评估结果 |
| sla_predictions | SLA预测 |
| work_orders | 工单（含审批链/优先级） |
| playbooks / playbook_executions | 运维剧本与执行记录 |
| trace_spans | 链路追踪 |
| agent_health_records | Agent健康记录 |
| failed_intent_cases | 失败意图案例 |
| intent_schedule_records | 意图调度记录 |
| grayscale_healing_tasks | 灰度自愈任务 |
| healing_evaluations | 自愈评估 |
| webhook_subscriptions | Webhook订阅 |
| behavior_anomalies | 行为异常检测 |
| change_impact_analyses | 变更影响分析 |
| execution_plans | 执行计划 |
| wizard_sessions | 向导会话 |
| knowledge_document_versions | 知识文档版本控制 |
| quick_commands | 快捷命令 |
| proactive_notifications | 主动通知 |
| remote_mcp_servers | 远程MCP服务器 |
| work_order_sla / work_order_dependencies / work_order_automation_rules | 工单SLA/依赖/自动化规则 |
| agent_capability_scores | Agent能力评分 |

---

## 七、Docker容器编排

`docker-compose.yml` 定义了 **9个服务**：

| 服务 | 镜像/构建 | 端口 | 说明 |
|------|-----------|------|------|
| postgres | postgres:15-alpine | 5432 | 业务数据库 |
| redis | redis:7-alpine | 6379 | 缓存/限流 |
| orchestrator | Dockerfile.orchestrator | 8000 | FastAPI后端主服务 |
| agent-worker-1 | Dockerfile.agent-worker | — | Agent工作节点1 |
| agent-worker-2 | Dockerfile.agent-worker | — | Agent工作节点2 |
| mcp-registry | Dockerfile.mcp-registry | — | MCP注册中心 |
| a2a-gateway | Dockerfile.a2a-gateway | 8080 | A2A通信网关 |
| frontend | ./frontend/Dockerfile | 5173 | Vue前端 |
| jaeger | jaegertracing/all-in-one:1.54 | — | 链路追踪 |
| chromadb | chromadb/chroma:latest | — | 向量数据库 |

---

## 八、前端状态管理

5个Pinia Store：

| Store | 文件 | 职责 |
|-------|------|------|
| auth | `stores/auth.ts` | JWT认证/Token管理/用户信息 |
| app | `stores/app.ts` | 应用全局状态（熔断/场景模式） |
| assistant | `stores/assistant.ts` | AI助手状态（对话/场景/模式） |
| topology | `stores/topology.ts` | 拓扑数据/布局/选中状态 |
| notification | `stores/notification.ts` | 通知管理 |

7个Composable：

| Composable | 文件 | 职责 |
|------------|------|------|
| useWebSocket | `composables/useWebSocket.ts` | WebSocket连接管理 |
| useApi | `composables/useApi.ts` | REST API请求封装 |
| useActionEngine | `composables/useActionEngine.ts` | AI助手前端动作执行 |
| useAgenticEngine | `composables/useAgenticEngine.ts` | Agentic推理引擎 |
| useAssistantContext | `composables/useAssistantContext.ts` | AI助手上下文感知 |
| useDraggable | `composables/useDraggable.ts` | 拖拽交互 |
| useResponsive | `composables/useResponsive.ts` | 响应式布局 |

---

## 九、AI助手组件群

`frontend/src/components/AiAssistant/` 包含8个组件：

| 组件 | 说明 |
|------|------|
| AiAssistant.vue | 主容器 |
| FloatingBall.vue | 可拖拽浮动球（5种状态动画） |
| BubbleCard.vue | 页面上下文感知气泡 |
| ChatPanel.vue | 对话面板（3种模式） |
| ProactivePanel.vue | 主动建议面板 |
| TemplateMarketPanel.vue | 模板市场 |
| VoiceInput.vue | 语音输入 |
| WizardRunner.vue | 向导执行器 |

---

## 十、文档

| 文件路径 | 内容 |
|----------|------|
| `README.md` | 项目概述/技术栈/快速开始/API接口/安全特性 |
| `SYSTEM_INTRODUCTION.md` | 完整系统介绍（780行），含架构图/业务流程/数据模型/部署架构 |
| `docs/topology_upgrade.md` | 拓扑模块升级方案 |
| `docs/mcp_tools_upgrade.md` | MCP工具升级方案 |
| `docs/audit_logs_upgrade.md` | 审计日志升级方案 |
| `docs/self_healing_upgrade.md` | 自愈模块升级方案 |
| `docs/intent_center_upgrade.md` | 意图中心升级方案 |
| `docs/superpowers/plans/` | 3个批次开发计划 |
| `docs/superpowers/specs/` | AI助手升级设计文档 |

---

## 十一、关键架构特征总结

1. **意图驱动**：自然语言 → 9种意图类型 → 全链路自动化执行 → SLA闭环监控
2. **多Agent协同**：15+专业Agent，A2A通信总线，3种协作模式（Supervisor/Parallel/Debate）
3. **ReAct推理**：智谱GLM Function Calling，最多5轮推理，高危操作人工审批
4. **双LLM网关**：DeepSeek + 智谱GLM，按任务类型自动路由，故障自动转移
5. **6层纵深安全**：Prompt注入防护 → 意图扫描 → 沙箱检测 → 变更窗口 → 配置回滚 → 限流
6. **RBAC权限**：admin/operator/viewer三级角色，路由守卫+组件层双重控制
7. **WebSocket实时**：15种消息类型，JWT认证，自动重连+降级轮询
8. **灰度自愈**：金丝雀验证 → 批量执行 → 自动回滚
9. **可观测性**：OpenTelemetry链路追踪 + Jaeger + Prometheus指标 + 健康检查
10. **跨域协作**：A2A协议 + 语义路由 + JSON-RPC 2.0
        
          
基于对项目的全面分析，以下是系统详细介绍：

---

# 智维 AgentHub 系统介绍

## 一、系统背景

随着5G/6G网络、云计算和物联网的快速发展，电信运营商和大型企业面临的网络运维挑战日益严峻：网络设备规模呈指数级增长，配置复杂度持续攀升，故障影响范围不断扩大。传统运维模式高度依赖人工经验，存在响应慢、易出错、知识难以沉淀等痛点。一次网络配置错误可能导致大面积业务中断，而故障定位往往需要跨多个系统、多个团队协作，平均修复时间（MTTR）居高不下。

与此同时，大语言模型（LLM）技术的突破为网络运维带来了全新范式——**意图驱动运维（Intent-Driven Operations）**。运维人员只需用自然语言描述业务需求，系统即可自动理解意图、检测冲突、生成策略、执行配置并验证结果，实现从"命令行操作"到"意图表达"的根本性转变。

**智维 AgentHub** 正是在这一背景下诞生的。它是一套基于大语言模型多智能体协同的**意图驱动网络自愈与运维平台**，面向电信运营商和大型企业网络运维场景，通过自然语言意图输入，经多Agent协同编排，实现从意图理解到策略执行的全链路自动化闭环。

---

## 二、系统功能

### 2.1 意图中心（核心功能）

- **自然语言意图解析**：用户输入自然语言描述，系统通过DeepSeek/智谱GLM大模型解析为9种结构化意图类型（带宽保障、流量调度、故障自愈、安全策略、QoS优化、链路保护、负载均衡、访问控制、路由优化）
- **意图模板市场**：预置标准化意图模板，支持一键创建，降低使用门槛
- **意图冲突检测**：5类冲突规则自动检测（资源冲突、策略冲突、时序冲突、依赖冲突、语义冲突），避免配置矛盾
- **意图审批流程**：RBAC权限控制，Admin审批后方可执行，防止误操作
- **意图调度**：支持定时执行、变更窗口管理，确保变更在安全时段内实施
- **失败意图分析**：自动归因失败原因，沉淀为知识库案例

### 2.2 多智能体协同

- **15+专业Agent**：意图解析Agent、冲突检测Agent、策略规划Agent、执行Agent、安全Agent、澄清Agent等，各司其职
- **3种协作模式**：Supervisor（监督编排）、Parallel（并行执行）、Debate（辩论决策）
- **A2A跨域通信**：Agent间通过发布订阅消息总线实时通信，支持跨域协作
- **Agent热升级**：无需停服即可升级Agent版本，支持一键回滚
- **Agent评分**：基于执行成功率、响应时间等维度自动评分，持续优化

### 2.3 网络拓扑可视化

- **实时拓扑渲染**：ECharts力导向图展示网络设备与链路关系
- **设备状态监控**：CPU、内存、端口状态实时刷新
- **链路健康度**：带宽利用率、延迟、丢包率可视化
- **交互式操作**：点击设备查看详情、拖拽调整布局

### 2.4 自愈中心

- **故障自动检测**：实时监控网络事件与告警
- **灰度自愈**：金丝雀验证 → 小范围执行 → 全量推广 → 自动回滚，确保自愈安全性
- **自愈评估**：执行后自动评估效果，形成闭环
- **运维剧本**：预置标准化运维流程，一键执行

### 2.5 AI智能助手

- **上下文感知**：根据当前页面自动推荐相关操作
- **多模式对话**：支持闲聊、意图创建、故障诊断三种模式
- **语音输入**：支持语音转文字输入
- **向导式操作**：WizardRunner引导用户完成复杂操作
- **主动通知**：系统主动推送告警、建议和状态变更

### 2.6 知识库

- **RAG语义检索**：基于ChromaDB向量数据库 + sentence-transformers语义嵌入
- **文档版本管理**：知识文档增删改查、版本追溯
- **智能问答**：自然语言提问，系统从知识库中检索并生成答案

### 2.7 可观测性

- **链路追踪**：OpenTelemetry + Jaeger，全链路请求追踪
- **指标监控**：Prometheus集成，实时采集系统与业务指标
- **健康检查**：各服务组件健康状态实时监控
- **审计日志**：全操作留痕，支持按时间/用户/操作类型检索

### 2.8 SLA预测

- **机器学习预测**：基于scikit-learn模型预测SLA达标率
- **趋势分析**：历史数据趋势可视化
- **预警通知**：SLA即将违约时主动告警

### 2.9 工单管理

- **工单全生命周期**：创建 → 审批 → 执行 → 验证 → 关闭
- **优先级管理**：紧急/高/中/低四级优先级
- **审批链**：多级审批流程，确保操作合规
- **SLA绑定**：工单与SLA关联，超时自动升级

### 2.10 系统管理

- **用户管理**：RBAC三级角色（Admin/Operator/Viewer），精细权限控制
- **LLM路由管理**：多模型配置、按任务类型路由、故障转移策略
- **Webhook管理**：事件订阅与通知
- **MCP工具管理**：工具注册、发现与编排
- **紧急制动**：一键熔断，阻止所有写操作，保障系统安全

---

## 三、系统使用流程

### 3.1 核心流程：意图驱动运维闭环

```
┌─────────────────────────────────────────────────────────────────┐
│                    意图驱动运维全链路闭环                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ① 自然语言输入                                                 │
│     用户在意图中心输入："保障核心区域视频会议带宽不低于500Mbps"      │
│              │                                                  │
│              ▼                                                  │
│  ② 意图解析（DeepSeek/智谱GLM）                                 │
│     解析为结构化意图：intent_type=bandwidth_guarantee             │
│     提取参数：target=核心区域, bandwidth=500Mbps, service=视频会议 │
│              │                                                  │
│              ▼                                                  │
│  ③ 冲突检测（ConflictDetector Agent）                           │
│     检测5类冲突：资源/策略/时序/依赖/语义                         │
│     发现冲突 → 澄清对话 → 用户确认修改                           │
│              │                                                  │
│              ▼                                                  │
│  ④ 策略生成（PolicyPlanner Agent）                              │
│     根据设备厂商（华为/Cisco/H3C）生成对应配置命令                │
│     生成执行计划：设备列表、配置命令、执行顺序                     │
│              │                                                  │
│              ▼                                                  │
│  ⑤ 安全审查（6层纵深防护）                                      │
│     Prompt注入检测 → 意图安全扫描 → 沙箱命令检测                 │
│     → 变更窗口校验 → 配置备份 → 速率限制                        │
│              │                                                  │
│              ▼                                                  │
│  ⑥ 审批执行                                                    │
│     高危操作 → Admin审批 → 确认执行                              │
│     普通操作 → 自动执行（灰度策略：先验证后全量）                 │
│              │                                                  │
│              ▼                                                  │
│  ⑦ 结果验证与反馈                                              │
│     设备配置下发 → 执行结果采集 → SLA验证                        │
│     成功 → 更新意图状态为completed                               │
│     失败 → 自动回滚 → 记录失败案例 → 通知用户                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 典型使用场景

**场景一：带宽保障**
1. 运维人员在意图中心输入"为视频会议保障500Mbps带宽"
2. 系统解析为bandwidth_guarantee意图，提取目标区域和带宽参数
3. 冲突检测通过后，PolicyPlanner生成华为/Cisco设备QoS配置
4. 安全审查通过，Admin审批后灰度执行
5. 系统验证配置生效，SLA达标率提升

**场景二：故障自愈**
1. 系统检测到核心链路中断告警
2. 自愈中心自动触发故障诊断Agent
3. ReAct推理引擎5轮推理定位根因
4. 生成修复方案，灰度验证后自动执行
5. 执行后评估自愈效果，记录到知识库

**场景三：AI助手辅助**
1. 用户在拓扑页面查看网络状态，点击浮动球唤起AI助手
2. 助手自动感知当前页面上下文，推荐相关操作
3. 用户通过语音或文字描述需求
4. 助手调用对应Agent执行，实时反馈进度
5. 执行结果通过WebSocket实时推送到前端

---

## 四、系统优势

### 4.1 意图驱动，零门槛操作

传统网络运维需要运维人员记忆大量厂商命令行语法，不同设备（华为/Cisco/H3C）配置差异巨大。智维AgentHub通过自然语言交互，将"做什么"与"怎么做"解耦——用户只需描述业务意图，系统自动完成从意图理解到配置下发的全流程，大幅降低运维门槛。

### 4.2 多Agent协同，专业分工

单一AI模型难以兼顾网络运维的方方面面。系统采用15+专业Agent分工协作，每个Agent专注一个领域（意图解析、冲突检测、策略生成、安全审查等），通过A2A通信总线实时协同。三种协作模式（Supervisor/Parallel/Debate）灵活应对不同场景，确保决策质量。

### 4.3 全链路闭环，结果可验证

从意图输入到配置生效，每一步都有明确的输入输出和状态追踪。执行后自动验证SLA达标情况，失败自动回滚，形成"执行-验证-反馈"的完整闭环，避免"配了不知道对不对"的盲区。

### 4.4 六层纵深安全，操作可信赖

网络安全运维最怕"治了病反而添了伤"。系统构建了6层纵深安全防护：Prompt注入防护（58种恶意模式）→ 意图安全扫描 → 命令沙箱检测（19条危险命令+31条恶意模式）→ 变更窗口管理 → 配置自动备份回滚 → 速率限制。高危操作必须经Admin审批，紧急制动一键熔断，确保任何情况下系统都在可控范围内。

### 4.5 灰度自愈，安全演进

自愈操作风险高，系统采用灰度策略：先在金丝雀设备验证，确认无误后小范围执行，最后全量推广。任何阶段发现问题立即自动回滚，将自愈风险降到最低。

### 4.6 实时感知，全局可视

通过WebSocket实时推送15种消息类型，网络拓扑、设备状态、告警事件、意图进度等信息秒级更新。运维人员可全局掌控网络运行态势，快速定位问题。

### 4.7 知识沉淀，持续进化

每次运维操作（无论成功失败）都自动记录到知识库和审计日志。失败案例归因分析后沉淀为知识，RAG语义检索让历史经验可被随时调用。系统越用越聪明，组织知识持续积累。

---

## 五、优势技术

### 5.1 双LLM网关 + 智能路由

系统同时集成DeepSeek和智谱GLM两大模型，按任务类型智能路由：
- **意图解析**：优先智谱GLM（Function Calling能力强）→ 备选DeepSeek → 兜底规则匹配
- **对话增强**：优先DeepSeek（长文本理解优）→ 备选智谱GLM
- **配置生成**：优先智谱GLM → 备选DeepSeek
- **故障诊断**：优先智谱GLM → 备选DeepSeek

任一模型故障自动切换到备选，确保服务连续性。

### 5.2 ReAct推理引擎

基于智谱GLM Function Calling实现ReAct（Reasoning + Acting）推理循环：
- 最多5轮推理，每轮可选择：调用工具、请求人工确认、输出结论
- 高危操作自动暂停等待人工审批
- 推理过程全程可追溯，便于审计和调试

### 5.3 A2A跨域通信协议

Agent间通信采用JSON-RPC 2.0协议，支持：
- **agent.discover**：发现可用Agent及其能力
- **agent.call**：跨域调用Agent方法
- **agent.status**：查询Agent运行状态
- **语义路由**：关键词提取 + 能力匹配（0.7权重）+ 负载评分（0.3权重），智能选择最优Agent

### 5.4 RAG知识库引擎

基于ChromaDB向量数据库 + sentence-transformers语义嵌入：
- 文档切片后生成向量索引，支持语义级检索
- 检索结果注入LLM上下文，实现知识增强生成
- 文档版本管理，支持知识追溯

### 5.5 全栈容器化编排

Docker Compose编排9个服务容器：
- **前后端分离**：Vue3前端 + FastAPI后端独立部署
- **数据层隔离**：PostgreSQL + Redis + InfluxDB + ChromaDB各司其职
- **Agent工作节点**：2个Agent Worker横向扩展
- **A2A网关**：独立通信网关，支持跨域协作
- **链路追踪**：Jaeger全链路追踪

### 5.6 RBAC + 组件级双重权限控制

- **后端**：JWT认证 + requires_permission依赖注入，90+端点细粒度权限校验
- **前端**：路由守卫 + canWrite计算属性，Viewer角色自动隐藏所有写操作按钮
- **熔断保护**：check_fuse依赖注入，熔断状态下所有写操作返回503

### 5.7 WebSocket实时通信

- JWT认证握手，连接数限制（全局1000/每用户5）
- 15种消息类型覆盖全场景
- 自动重连（最多5次递增延迟）+ 30秒心跳保活
- 认证失败停止重连，降级为轮询模式

### 5.8 可观测性三支柱

- **链路追踪**：OpenTelemetry SDK自动埋点，Jaeger可视化
- **指标监控**：Prometheus格式暴露，Grafana可对接
- **日志审计**：全操作留痕，支持多维度检索

---

以上为智维AgentHub系统的完整介绍，涵盖系统背景、功能模块、使用流程、核心优势与关键技术。