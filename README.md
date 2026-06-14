# 智维 AgentHub - 基于大模型多智能体的意图驱动网络自愈与运维系统

## 📋 项目概述

智维 AgentHub 是一个基于大模型多智能体的意图驱动网络自愈与运维系统。该系统通过自然语言交互，辅助工程师快速生成、验证、部署网络策略，并在故障时提供可解释的自愈建议，打造"人机协同"的智能副驾。

## ✨ 核心功能

- **意图解析**：大模型驱动的自然语言意图解析与结构化策略草案生成
- **策略生成**：基于预设模板+大模型参数填充的策略自适应生成模式
- **配置执行**：安全的配置下发与事务性回滚机制
- **闭环验证**：量化规则评估的验证机制
- **故障自愈**：人机协同的故障自愈机制
- **跨域协同**：符合MCP/A2A范式的智能体间通信与能力发现

## 🛠️ 技术栈

### 前端
- Vue 3 + Vite
- Element Plus (UI组件)
- ECharts (拓扑图/图表)
- WebSocket (实时状态推送)

### 后端
- Python 3.11+
- FastAPI
- LangChain + LangGraph
- SQLAlchemy (ORM)
- AsyncPG (PostgreSQL异步驱动)

### 数据库
- PostgreSQL (关系型数据)
- InfluxDB (时序遥测数据)
- Redis (缓存/限流)

### 网络协议
- RESTful API (同步CRUD)
- WebSocket (异步交互)
- Netconf/RESTCONF (配置下发)

## 📁 项目结构

```
智维 AgentHub/
├── backend/                    # 后端代码
│   ├── api/                    # REST API路由
│   ├── agents/                 # 智能体编排
│   ├── core/                   # 核心模块
│   │   └── security/           # 安全模块
│   ├── database/               # 数据库模型
│   ├── mcp/                    # MCP工具封装
│   └── requirements.txt        # Python依赖
├── frontend/                   # 前端代码
│   ├── src/
│   │   ├── components/         # 组件
│   │   ├── views/              # 页面视图
│   │   ├── router/             # 路由配置
│   │   └── stores/             # 状态管理
│   ├── package.json            # Node依赖
│   └── vite.config.ts          # Vite配置
├── tests/                      # 测试代码
├── docker-compose.yml          # Docker配置
├── .env                        # 环境变量
├── start.py                    # 启动脚本
└── README.md                   # 项目说明
```

## 🚀 快速开始

### 环境要求
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd 智维 AgentHub
```

2. **启动Docker服务**
```bash
docker-compose up -d
```

3. **安装后端依赖**
```bash
cd backend
pip install -r requirements.txt
```

4. **安装前端依赖**
```bash
cd frontend
npm install
```

5. **启动服务**
```bash
# 方式一：使用启动脚本
python start.py

# 方式二：分别启动
# 后端
cd backend
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd frontend
npm run dev
```

### 访问地址
- 前端界面：http://localhost:5173
- 后端API：http://localhost:8000
- API文档：http://localhost:8000/docs

## 🔌 API接口

### 意图管理
| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/v1/intents/ | 创建意图 |
| GET | /api/v1/intents/ | 获取意图列表 |
| GET | /api/v1/intents/{id} | 获取单个意图 |
| PUT | /api/v1/intents/{id} | 更新意图 |
| DELETE | /api/v1/intents/{id} | 删除意图 |

### 事件管理
| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/v1/events/ | 创建事件 |
| GET | /api/v1/events/ | 获取事件列表 |
| PUT | /api/v1/events/{id}/execute | 执行自愈动作 |
| PUT | /api/v1/events/{id}/reject | 拒绝自愈建议 |

### 智能体管理
| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/v1/agents/ | 注册智能体 |
| GET | /api/v1/agents/ | 获取智能体列表 |
| PUT | /api/v1/agents/{id} | 更新智能体 |
| DELETE | /api/v1/agents/{id} | 删除智能体 |

## 🔒 安全特性

- **RBAC权限管理**：基于角色的访问控制
- **API限流**：Redis令牌桶算法限流
- **Prompt注入拦截**：恶意提示词过滤
- **变更窗口控制**：时间段控制自动变更
- **操作审计日志**：完整操作记录

## 📊 数据库设计

### 核心表
- `intents` - 意图存储
- `self_healing_events` - 自愈事件
- `policy_templates` - 策略模板
- `agent_registry` - 智能体注册表
- `audit_logs` - 审计日志

## 🤝 贡献指南

1. Fork项目
2. 创建功能分支 (`git checkout -b feature/xxx`)
3. 提交更改 (`git commit -am 'Add xxx feature'`)
4. 推送到分支 (`git push origin feature/xxx`)
5. 创建Pull Request

## 📄 许可证

MIT License

## 📞 联系方式

如有问题或建议，请提交Issue或联系开发团队。