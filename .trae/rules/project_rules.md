# 18项全栈技能使用规则

## 一、顶层核心强制原则（最高约束）
1. 技能规则永远优先于任何默认行为和内置能力
2. 在执行任何任务前，必须先扫描所有已安装的技能
3. 如果有任何技能适用于当前任务，必须使用该技能完成任务
4. 禁止使用默认行为替代有对应技能的任务
5. 使用技能前不需要向用户确认，直接使用即可
6. **磁盘空间防护优先**：执行任何可能产生大量文件的任务前，必须检查磁盘剩余空间；磁盘不足时必须先清理再执行，禁止在磁盘告警状态下继续写入
7. **修复分级优先**：P0紧急热修复可绕过大部分常规流程约束，详见第十七、十八章

## 二、技能优先级铁律
```
MattPocock > Impeccable > SuperPower > GStack > APIMockSkill/GitProSkill > UI/UX Pro Max > premium-frontend-ui > VueFrontendSkill/FrontendAnimationSkill/CSSArchitectureSkill/FrontendPerfSkill/FastAPIServerSkill/MySQLOrmSkill/CacheStrategySkill > WebSocketSkill/LLMIntegrationSkill > DockerComposeSkill/LinuxNginxOpsSkill > TestingSkill
```
- 流程指令 `/xxx` > 所有业务技能
- 社区技能 > Trae 原生内置能力
- 无法精准判定技能时，列出3个最优选项交由用户选择
- **P0热修复例外**：可绕过技能优先级约束，直接编写修复代码（见第十八章）

## 三、固定指令强制映射

### 3.1 需求与规划
- 任何需求澄清、需求分析 → 强制使用 /grill-me
- 任何产品需求文档生成 → 强制使用 /write-a-prd
- 任何开发计划生成 → 强制使用 /prd-to-plan
- 任何任务拆分、工单生成 → 强制使用 /prd-to-issues
- 任何架构设计、系统规划 → 强制使用 /improve-codebase-architecture → SuperPower 落地

### 3.2 开发与编码
- 任何新功能开发 → 强制使用 /tdd
- **Bug修复** → 按第十七章修复分级决定流程，P0走紧急通道，P1-P3走对应流程
- 任何代码重构 → 强制使用 /request-refactor-plan
- 任何 API 接口设计 → 强制使用 /design-an-interface → FastAPIServerSkill 实现
- 任何前端动画、页面过渡、微交互、滚动动画 → 强制使用 FrontendAnimationSkill
- 任何CSS架构设计、设计Token体系、主题系统、响应式断点、组件样式规范 → 强制使用 CSSArchitectureSkill
- 任何原型开发、概念验证 → 强制使用 /prototype
- 任何缓存策略设计、Redis集成、分布式锁、限流、缓存失效方案 → 强制使用 CacheStrategySkill
- 任何前端性能优化、Bundle分析、构建优化、Lighthouse CI、懒加载、图片/字体优化、Core Web Vitals监控 → 强制使用 FrontendPerfSkill
- 后端未完成时自动启用 APIMockSkill 生成模拟接口
- 任何UI视觉设计决策（风格/色板/字体/布局/交互）→ 强制使用 Impeccable（craft→shape→audit→polish 流水线）
- 任何沉浸式页面架构（入口序列/英雄区/导航/动效系统）→ 强制使用 premium-frontend-ui
- 任何数据驱动的设计选型（样式库搜索/配色方案/字体搭配/UX准则/图表类型）→ 强制使用 UI/UX Pro Max

### 3.3 调试与问题解决
- 任何 bug 诊断、错误排查、性能问题分析 → 强制使用 /diagnose
- 任何 TypeScript 类型问题 → 强制使用 /debug-typescript + MattPocock 全权处理
- **P0紧急热修复例外**：简单TS类型修复可直接处理，无需MattPocock（见18.1节）

### 3.4 代码质量与审查
- 任何代码审查、代码改进 → 强制使用 /code-review
- 任何提交信息生成 → 强制使用 /write-a-commit-message + GitProSkill 规范化提交

### 3.5 文档与协作
- 任何 README 文档生成 → 强制使用 /write-readme
- 任何架构决策记录 → 强制使用 /write-adr
- 任何总结、全局视角 → 强制使用 /zoom-out
- 任何简洁输出要求 → 强制使用 /caveman

## 四、18项技能权责分工

### 4.1 SuperPower｜全局架构总指挥
- 承接架构设计输出，统一项目目录分层、编码规范、技术栈选型
- 根据PRD拆解全栈任务，按需分发至对应技能
- 统筹Mock环境、版本管理、上线全链路方案
- 不直接写代码，只做调度分发

### 4.2 MattPocock｜TS/JS类型&代码规范（优先级全技能最高）
- 绑定 /debug-typescript，全项目JS/TS类型定义、类型报错、编码规范校验
- VueFrontendSkill生成前端代码后必经Matt类型校验，其余技能禁止手写TS类型
- 核心实践：satisfies替代as、品牌类型、Zod schema + z.infer推导、shoehorn替代测试as
- **修复例外**（v5.0新增）：P0/P1修复中涉及简单TS类型（基本类型标注、接口字段增删、联合类型扩展），修复技能可直接处理，无需经过MattPocock。复杂类型（泛型、条件类型、类型体操）仍需MattPocock

### 4.3 GStack｜接口联调请求层
- 对接真实后端接口或APIMockSkill模拟接口，自动生成前端请求封装代码
- 仅负责接口调用调试，不写后端逻辑、不建数据表
- 浏览器端QA验证（Edge DevTools MCP）

### 4.4 APIMockSkill｜前端模拟接口
- 后端接口未开发完成时，自动根据接口文档生成Mock接口、模拟分页/列表/表单假数据
- 配合GStack实现前端先行开发，后端完工一键切真实接口
- 适配小程序、H5、管理后台前置开发

### 4.5 VueFrontendSkill｜Vue3前端工程（当前项目优先使用）
- Vite+Vue3+Pinia+VueRouter，适配Web管理后台/小程序/H5/APP前端
- 代码产出→FrontendAnimationSkill添加动画层→MattPocock校验→GStack对接真实/Mock接口
- 当前项目（智维AgentHub）是Vue3技术栈，前端开发优先使用本技能

### 4.5b FrontendAnimationSkill｜前端动画与交互增强
- 集成GSAP + Vue Transition + Lottie，涵盖页面过渡、微交互、滚动驱动动画、性能优化
- VueFrontendSkill产出页面/组件后由本Skill添加动画层
- 动画Composable的TS类型必须经MattPocock校验，本Skill禁止自行编写TS类型定义
- GSAP免费功能（Tween/Timeline/ScrollTrigger/Flip）优先，付费插件提供替代方案

### 4.5c CSSArchitectureSkill｜CSS架构与设计系统
- CSS变量设计Token体系（色板/间距/圆角/阴影/字体/字号），亮/暗双主题
- 响应式断点系统 + 弹性排版（clamp）+ 容器查询（@container）
- 组件变体模式（variant → CSS class），BEM/CUBE CSS/CSS Modules方法论
- PostCSS插件链 + Tailwind/UnoCSS集成
- **任何前端项目第一项任务**：无论Vue3/React/小程序，必须先建Token体系
- 强制：所有颜色/间距/圆角/阴影必须使用CSS变量，禁止硬编码
- **修复例外**（v5.0新增）：样式修复（颜色调整、间距微调、圆角修改）可直接修改CSS变量或组件样式，无需完整设计审批链

### 4.5d FrontendPerfSkill｜前端性能工程化
- Vite/Rollup构建优化（manualChunks/tree-shaking/代码分割），Bundle分析（rollup-plugin-visualizer）
- 资源加载优化：图片压缩管线（WebP/AVIF）、字体子集化（woff2 + swap）、懒加载（Intersection Observer）
- 运行时监控：Core Web Vitals（LCP/INP/CLS/TTFB）、长任务检测、FPS追踪、内存监控
- CI/CD集成：Lighthouse CI自动化审计、性能预算校验、bundlesize回归检查、GitHub Actions集成
- 资源提示策略（preload/prefetch/preconnect/dns-prefetch）、Service Worker缓存、Brotli/Gzip压缩
- **强制**：所有路由必须懒加载（() => import()），所有图片必须提供WebP格式回退
- **强制**：构建产物单chunk不得超500KB，总构建体积不得超2MB（Brotli压缩后）

### 4.5e Impeccable｜设计智能总指挥（优先级设计技能最高）
- 命令驱动设计工作流：craft（创建）→ shape（塑形）→ audit（审计）→ polish（打磨）→ delight（愉悦）流水线
- 23个设计命令覆盖全生命周期：视觉设计、交互设计、动效设计、色彩、排版、布局、性能优化
- **强制前置步骤**：首次使用须运行 `node .agents/skills/impeccable/scripts/context.mjs`，注册 brand.md 或 product.md 参考文件
- **强制色彩规范**：所有颜色必须使用 OKLCH 色彩空间，禁止使用 hex/rgb/hsl 硬编码颜色值
- **绝对禁令**：禁止模板化设计、禁止默认蓝紫配色、禁止居中英雄区+三列特性卡、禁止占位图片
- 产出物为设计决策和代码实现指导，具体Vue3代码由 VueFrontendSkill 落地
- 与 CSSArchitectureSkill 协作：Impeccable 定义 OKLCH 色彩变量 → CSSArchitectureSkill 转换为 CSS 自定义属性并纳入 Token 体系
- 与 UI/UX Pro Max 协作：UI/UX Pro Max 提供数据驱动的风格/配色/字体候选 → Impeccable 从中选型并执行 craft 命令落地
- 与 premium-frontend-ui 协作：Impeccable 审计页面视觉品质 → premium-frontend-ui 提供沉浸式架构和动效系统增强

### 4.5f premium-frontend-ui｜沉浸式前端架构
- 4大创意基础风格：Editorial Brutalism（编辑式粗野主义）、Organic Fluidity（有机流动）、Cyber/Technical（赛博/技术）、Cinematic Pacing（电影节奏）
- 沉浸式页面架构：入口序列设计、英雄区架构、导航系统、动效设计系统
- 排版与视觉纹理：字体层级、视觉节奏、纹理叠加、深度感
- 性能命令式：所有视觉效果必须满足 Core Web Vitals 指标
- **强制**：选择创意基础风格前，须先经 UI/UX Pro Max 数据验证或 Impeccable craft 命令确认
- 与 FrontendAnimationSkill 协作：premium-frontend-ui 定义动效设计系统（时序曲线/持续时间/触发条件）→ FrontendAnimationSkill 用 GSAP 实现
- 与 CSSArchitectureSkill 协作：premium-frontend-ui 的视觉纹理/深度效果 → CSSArchitectureSkill 转为 CSS 变量和组件变体
- 与 FrontendPerfSkill 协作：premium-frontend-ui 的视觉效果必须经 FrontendPerfSkill 验证性能达标

### 4.5g UI/UX Pro Max｜数据驱动设计决策引擎
- 可搜索数据库：50+ UI 风格、97 配色方案、57 字体搭配、99 UX 准则、25 图表类型、9 技术栈
- Python3 搜索引擎（`scripts/search.py`）：按关键词/类别/优先级搜索设计数据
- 技术栈适配：包含 Vue 技术栈专用数据（`data/stacks/vue.csv`）
- 优先级分类系统（1-10级）：按任务场景自动推荐最优设计方案
- **强制**：设计选型决策前，须先通过 search.py 查询数据验证，禁止凭直觉选型
- **强制**：Vue3 项目须使用 `data/stacks/vue.csv` 中的技术栈适配数据
- 与 Impeccable 协作：UI/UX Pro Max 提供候选方案 → Impeccable 执行 craft/shape 命令深化并落地
- 与 CSSArchitectureSkill 协作：UI/UX Pro Max 的配色方案/字体搭配 → CSSArchitectureSkill 转为 CSS 变量 Token
- 与 VueFrontendSkill 协作：UI/UX Pro Max 的 Vue 技术栈数据 → VueFrontendSkill 实现组件代码

### 4.6 ViteReactDevSkill｜React前端工程（React项目使用）
- Vite+React+TypeScript，适配React技术栈项目
- 同样需经MattPocock校验→GStack联调

### 4.7 MySQLOrmSkill｜数据模型层
- MySQL建表、索引设计、SQLAlchemy 2.0 ORM、Alembic迁移、SQL优化
- 架构确认后优先生成数据模型，供给FastAPIServerSkill开发业务接口
- 所有写操作必须包含try/except/rollback

### 4.7b CacheStrategySkill｜后端缓存策略
- Redis连接管理（连接池/Sentinel/Cluster），hiredis加速
- 缓存模式实现：Cache-Aside（默认）/ Read-Through / Write-Behind
- TTL层级策略（热数据1min / 温数据10min / 冷数据1h），主动失效+缓存预热
- 高级场景：分布式锁（Redlock）、滑动窗口限流、缓存击穿/雪崩/穿透防护
- **强制**：所有缓存Key必须有命名空间前缀，所有写操作必须有TTL
- **强制**：所有Redis操作必须有try/except降级逻辑，缓存不可用不影响主流程

### 4.8 FastAPIServerSkill｜后端接口服务
- 依托ORM模型开发路由、JWT鉴权、Pydantic V2校验、异常捕获、Swagger文档
- 落地 /design-an-interface 接口方案
- 安全：SECRET_KEY环境变量、生产禁用/docs、错误响应禁止str(e)

### 4.9 WebSocketSkill｜实时通信
- WebSocket连接管理、心跳保活、断线重连、消息类型安全
- 前端useWebSocket Composable + 后端FastAPI WebSocket端点
- 连接数限制：全局1000，每用户5个

### 4.10 LLMIntegrationSkill｜LLM大模型集成
- DeepSeek/智谱GLM/OpenAI API调用、流式响应、多模型主备切换
- Prompt工程、Token管理、API Key安全（环境变量，后端代理）
- 前端流式渲染 + 后端SSE端点

### 4.11 GitProSkill｜代码版本管控
- 项目初始化仓库、创建开发/发布分支、处理代码冲突、推送Gitee/GitHub
- 联动 /write-a-commit-message，Conventional Commits规范
- Husky pre-commit + lint-staged + commitlint
- **修复例外**（v5.0新增）：P0热修复使用 `hotfix:` 前缀，可直接推送main/master（见18.1节）

### 4.12 DockerComposeSkill｜容器化打包
- 自动生成Dockerfile+docker-compose.yml，前后端+MySQL容器编排
- 多阶段构建、非root用户、健康检查
- 开发完成后打包镜像，交付运维部署

### 4.13 LinuxNginxOpsSkill｜云服务器运维部署
- Ubuntu/openEuler环境配置、Nginx反向代理、防火墙、部署Shell脚本
- SSL证书(Let's Encrypt)、进程管理(Systemd)、日志分析
- 基于容器产物完成腾讯云等服务器上线发布

### 4.14 TestingSkill｜全栈测试
- Vitest前端单元测试 + Cypress E2E测试 + Pytest后端测试
- 配合 /tdd 流程落地：RED→GREEN→REFACTOR
- 测试数据使用shoehorn替代as断言，覆盖率要求：前端≥70%、后端≥80%
- **修复例外**（v5.0新增）：
  - P0热修复：跳过完整测试套件，仅手动验证核心路径，事后1周内补全测试
  - P1关键修复：执行受影响模块的核心测试，覆盖率检查可事后补全
  - P2常规修复：正常TDD流程（RED→GREEN→REFACTOR→VERIFY）
  - P3优化修复：正常TDD流程，要求测试覆盖率≥基线

## 五、标准开发流水线（全场景通用）
```
用户需求
→ /grill-me 需求梳理
→ /write-a-prd 产出产品文档
→ /prd-to-plan 生成开发计划
→ /prd-to-issues 拆分任务
→ /improve-codebase-architecture 架构设计（SuperPower落地）
→ MySQLOrmSkill 建库建模
→ CacheStrategySkill 设计缓存策略（Redis连接/缓存模式/失效策略）
→ /design-an-interface 接口方案 → FastAPIServerSkill 后端实现（/tdd落地）
→ 后端未完成：APIMockSkill 生成模拟接口
→ 【设计决策阶段】UI/UX Pro Max 数据驱动选型（风格/配色/字体/UX准则）→ Impeccable craft 命令确立视觉方向 → premium-frontend-ui 确定沉浸式架构风格
→ CSSArchitectureSkill 建立设计Token体系（Impeccable OKLCH色彩 → CSS变量，UI/UX Pro Max 配色/字体 → Token，premium-frontend-ui 视觉纹理 → 组件变体）
→ VueFrontendSkill 开发前端（遵循 Impeccable 设计决策 + premium-frontend-ui 架构规范）→ FrontendAnimationSkill 添加动画（premium-frontend-ui 动效系统 → GSAP实现）→ Impeccable audit 命令品质审计 → FrontendPerfSkill 性能优化 → MattPocock TS校验 → GStack 对接Mock接口
→ 后端就绪：GStack 切换真实接口
→ /code-review 代码评审 + /write-a-commit-message（GitProSkill规范化提交）
→ GitProSkill 分支管理推送远程仓库
→ DockerComposeSkill 容器打包
→ LinuxNginxOpsSkill 服务器部署上线
```

**修复任务流水线**：修复任务按第十七章分级走对应流程，不强制沿用完整开发流水线。

## 六、技能间协作红线
| 红线 | 说明 | 修复例外（v5.0） |
|------|------|-------------------|
| MattPocock 独占 TS 类型 | 其余17个技能禁止自行编写TS类型定义，必须交MattPocock | P0/P1修复：简单TS类型可直接处理 |
| GStack 不写后端 | GStack只做前端请求封装和联调，不写后端逻辑、不建表 | 无例外 |
| APIMockSkill 不改真实接口 | Mock仅在开发阶段使用，后端就绪后必须切换 | 无例外 |
| SuperPower 不写代码 | 只做调度分发，具体实现交给对应技能 | P0修复：SuperPower可直接协助编写修复代码 |
| VueFrontendSkill 产出必经 MattPocock | 前端代码未经TS校验不得进入联调 | P0修复：可事后补TS校验 |
| FrontendAnimationSkill 不写 TS 类型 | 动画 Composable 类型必须交 MattPocock 校验 | 同MattPocock例外 |
| FrontendAnimationSkill 不影响数据流 | 动画仅操作视觉层，不改变接口数据流和状态管理 | 无例外 |
| CSSArchitectureSkill 先于前端页面开发 | 任何前端项目必须先建立设计Token体系，再开发页面组件 | 样式修复：可直接修改，无需重建Token体系 |
| CSSArchitectureSkill 统管全局样式 | 其余技能禁止自行定义颜色/间距/圆角/阴影硬编码，必须引用CSS变量 | 样式修复：可直接修改CSS变量值 |
| FrontendPerfSkill 不破坏代码逻辑 | manualChunks/构建优化必须验证功能正常后合入 | 无例外 |
| FrontendPerfSkill 不降低视觉质量 | 图片压缩quality不低于70，字体子集不丢失关键字符 | 无例外 |
| MySQLOrmSkill 先于 FastAPIServerSkill | 先建表建模，再开发接口 | 无例外 |
| CacheStrategySkill 先于 FastAPIServerSkill | 先设计缓存层，再在接口中集成 | 无例外 |
| CacheStrategySkill 强制降级 | 所有缓存操作必须有try/except，Redis不可用时不影响主流程 | 无例外 |
| DockerComposeSkill 先于 LinuxNginxOpsSkill | 先容器打包，再服务器部署 | 无例外 |
| Impeccable 独占设计决策权 | 视觉方向/色彩/排版/布局的设计决策由 Impeccable 主导，其余设计技能提供输入但不做最终决策 | 样式修复：CSSArchitectureSkill可直接处理颜色/间距调整 |
| Impeccable 强制 OKLCH 色彩 | 所有颜色值必须使用 OKLCH 色彩空间，CSSArchitectureSkill 将其转为 CSS 自定义属性 | 无例外 |
| UI/UX Pro Max 先于 Impeccable 选型 | 设计选型前须先用 UI/UX Pro Max 搜索数据验证，Impeccable 基于数据做决策 | 样式修复：跳过 |
| premium-frontend-ui 不定义色彩/字体 | 色彩和字体由 Impeccable + UI/UX Pro Max 决定，premium-frontend-ui 仅负责架构和动效系统 | 无例外 |
| 设计技能不写 Vue 组件代码 | Impeccable/premium-frontend-ui/UI/UX Pro Max 产出设计指导，VueFrontendSkill 负责代码实现 | 无例外 |
| 设计技能不写 TS 类型 | 三个设计技能的 TS 类型必须交 MattPocock 校验，禁止自行编写 | 同MattPocock例外 |
| Impeccable audit 先于 FrontendPerfSkill | 先做视觉品质审计，再做性能优化，确保性能优化不牺牲视觉质量 | 性能修复：可直接执行，跳过audit |
| premium-frontend-ui 动效系统经 FrontendAnimationSkill 实现 | premium-frontend-ui 定义动效规范，FrontendAnimationSkill 用 GSAP 落地，禁止 premium-frontend-ui 直接写动画代码 | 无例外 |
| DiskGuard 阻断优先于任务执行 | 磁盘🔴危险级别时，任何技能不得执行写入操作，必须先清理至🟡警告以上 | P0热修复：可跳过磁盘检查（见16.2节） |
| 禁止在C盘默认路径生成缓存 | 所有包管理器缓存必须指向D盘（16.3节），违反即触发自动清理 | 无例外 |
| 大文件操作必须预检磁盘 | npm install / docker build / conda install 等高占用任务，执行前必须检查磁盘剩余空间 | 无例外 |
| 清理不碰当前项目 | 自动清理流程永远不删除 `D:\Trae CN\Project\智维 AgentHub` 下任何文件 | 无例外 |

## 七、异常处理通道
| 异常类型 | 触发 | 处理技能 |
|---------|------|---------|
| Bug/错误 | /diagnose | 定位后按第十七章修复分级分发对应技能修复 |
| TS 类型报错 | /debug-typescript | MattPocock 全权处理（P0/P1简单类型修复例外） |
| 性能问题 | /diagnose | 数据库→MySQLOrmSkill，缓存→CacheStrategySkill，前端→VueFrontendSkill，构建→FrontendPerfSkill，动画性能→FrontendAnimationSkill |
| 样式不一致/主题缺失 | CSS架构规范检查 | CSSArchitectureSkill（可直接修复，跳过完整设计审批链） |
| 缓存命中率低/击穿/雪崩 | 缓存策略诊断 | CacheStrategySkill |
| 构建体积超标/加载缓慢 | Bundle分析/性能诊断 | FrontendPerfSkill |
| 重构需求 | /request-refactor-plan | 方案确认后对应技能执行 |
| 概念验证 | /prototype | 快速原型，不进主线 |
| 视觉品质不达标 | Impeccable audit 命令 | Impeccable 执行 critique/audit → 定位问题 → polish 命令修复 |
| 设计选型犹豫 | UI/UX Pro Max 数据查询 | search.py 搜索候选方案 → Impeccable craft 命令决策 |
| 页面缺乏沉浸感 | premium-frontend-ui 架构增强 | 入口序列/英雄区/动效系统重构 |
| OKLCH 色彩违规 | Impeccable colorize 命令 | 检测 hex/rgb/hsl 硬编码 → 转换为 OKLCH → CSSArchitectureSkill 纳入 Token |
| 磁盘空间不足 | DiskGuard 规则（第十六章） | 自动清理缓存（16.4节）→ 深度清理 → 通知用户手动处理 |
| 缓存目录回退C盘 | 环境变量检查 | 重新设置环境变量指向D盘（16.3节） |
| **P0紧急故障** | **生产环境故障/安全漏洞/数据丢失** | **走第十八章紧急热修复通道** |

## 八、当前项目特别适配
- 智维 AgentHub 是 **Vue3** 技术栈 → 前端优先使用 **VueFrontendSkill**
- UI视觉设计决策 → **Impeccable**（craft→shape→audit→polish 设计流水线，OKLCH色彩强制）
- 沉浸式页面架构 → **premium-frontend-ui**（4大创意基础风格 + 入口序列/英雄区/动效系统）
- 数据驱动设计选型 → **UI/UX Pro Max**（50+风格/97配色/57字体搭配/Vue技术栈专用数据）
- 前端设计系统与CSS架构 → **CSSArchitectureSkill**（设计Token体系、响应式断点、组件变体规范）
- 前端性能工程化 → **FrontendPerfSkill**（构建优化/Bundle分析/Lighthouse CI/Web Vitals）
- 前端动画与交互增强 → **FrontendAnimationSkill**（GSAP + Vue Transition + Lottie）
- 使用 WebSocket 实时通信 → **WebSocketSkill**
- 集成 DeepSeek + 智谱 GLM → **LLMIntegrationSkill**
- SQLAlchemy ORM → **MySQLOrmSkill**
- JWT 认证 → **FastAPIServerSkill**
- 缓存策略与性能优化 → **CacheStrategySkill**（Redis缓存/分布式锁/限流）
- **设计技能协作链**：UI/UX Pro Max 数据选型 → Impeccable 设计决策 → premium-frontend-ui 沉浸式架构 → CSSArchitectureSkill Token体系 → VueFrontendSkill 代码实现 → FrontendAnimationSkill 动画 → Impeccable audit 品质审计 → FrontendPerfSkill 性能验证

## 九、违规约束
存在匹配指令/技能时，严禁使用AI默认原生能力，违规可要求重新使用指定技能重做任务
- **修复例外**（v5.0新增）：P0紧急热修复可绕过上述约束，详见第十八章

---

# 技能治理体系（Governance Framework）

## 十、技能匹配与分配原则

### 10.1 三层匹配决策模型

```
用户意图 → [第一层：指令匹配] → [第二层：场景匹配] → [第三层：能力匹配] → 分配技能
              ↓ 失败               ↓ 失败               ↓ 失败
          列出候选指令          列出候选技能          列出3个最优选项
                                                       交由用户选择
```

| 层级 | 匹配器 | 输入 | 输出 | 兜底策略 |
|------|--------|------|------|----------|
| L1 指令匹配 | 固定指令映射表（第三章） | 用户自然语言 | 匹配到的 `/xxx` 指令 | 降级至 L2 |
| L2 场景匹配 | 场景→技能路由表（10.2节） | 任务类型 + 技术栈 + 阶段 | 匹配到的技能名 | 降级至 L3 |
| L3 能力匹配 | 技能能力描述语义匹配 | 任务描述 + 技能 SKILL.md | Top-3 候选技能 | 用户人工选择 |

### 10.2 场景→技能路由表（核心决策矩阵）

| 任务场景 | 触发关键词 | 首选技能 | 备选技能 | 排除技能 |
|----------|-----------|---------|---------|---------|
| 数据库建模/迁移 | `建表` `索引` `ORM` `Alembic` `SQL` | MySQLOrmSkill | — | GStack, VueFrontendSkill |
| 缓存策略设计 | `Redis` `缓存` `TTL` `限流` `分布式锁` | CacheStrategySkill | — | GStack, APIMockSkill |
| REST API 开发 | `接口` `路由` `JWT` `FastAPI` `Swagger` | FastAPIServerSkill | — | GStack, VueFrontendSkill |
| Vue3 页面/组件 | `页面` `组件` `Pinia` `VueRouter` `Vite` | VueFrontendSkill | ViteReactDevSkill | FastAPIServerSkill |
| React 页面/组件 | `React` `JSX` `Redux` `ReactRouter` | ViteReactDevSkill | VueFrontendSkill | FastAPIServerSkill |
| 前端动画/交互 | `动画` `过渡` `GSAP` `Lottie` `微交互` | FrontendAnimationSkill | — | CSSArchitectureSkill |
| CSS/设计系统 | `样式` `主题` `Token` `断点` `CSS变量` | CSSArchitectureSkill | — | FrontendAnimationSkill |
| 前端性能优化 | `打包` `Bundle` `Lighthouse` `懒加载` `压缩` | FrontendPerfSkill | — | CSSArchitectureSkill |
| 实时通信 | `WebSocket` `Socket.IO` `心跳` `推送` | WebSocketSkill | — | FastAPIServerSkill |
| LLM/AI 集成 | `DeepSeek` `GLM` `OpenAI` `流式` `LLM` | LLMIntegrationSkill | — | FastAPIServerSkill |
| Git 版本管理 | `commit` `分支` `PR` `merge` `push` | GitProSkill | — | DockerComposeSkill |
| 容器化部署 | `Docker` `镜像` `编排` `docker-compose` | DockerComposeSkill | — | GitProSkill |
| 服务器运维 | `Nginx` `SSL` `部署` `防火墙` `Systemd` | LinuxNginxOpsSkill | — | DockerComposeSkill |
| 接口联调/HTTP请求 | `axios` `请求封装` `接口对接` `API调用` | GStack | APIMockSkill | FastAPIServerSkill |
| Mock 接口 | `Mock` `模拟数据` `MSW` `假数据` | APIMockSkill | GStack | FastAPIServerSkill |
| 单元/集成/E2E测试 | `测试` `pytest` `Vitest` `Cypress` `覆盖率` | TestingSkill | — | SuperPower |
| TS 类型定义/校验 | `类型` `interface` `泛型` `类型报错` | MattPocock | — | 其余全部技能 |
| 架构设计/技术选型 | `架构` `分层` `技术栈` `目录结构` | SuperPower | — | — |
| 需求分析/PRD | `需求` `PRD` `用户故事` `验收标准` | /grill-me → /write-a-prd | — | — |
| UI视觉设计决策 | `设计` `风格` `色板` `排版` `布局` `视觉` | Impeccable | UI/UX Pro Max | VueFrontendSkill |
| 沉浸式页面架构 | `沉浸` `入口序列` `英雄区` `动效系统` `视觉节奏` | premium-frontend-ui | Impeccable | VueFrontendSkill |
| 数据驱动设计选型 | `配色方案` `字体搭配` `UX准则` `图表类型` `风格搜索` | UI/UX Pro Max | Impeccable | VueFrontendSkill |
| 设计品质审计 | `audit` `品质` `视觉审查` `设计评审` | Impeccable（audit命令） | premium-frontend-ui | FrontendPerfSkill |
| **Bug修复**（v5.0新增） | `bug` `修复` `报错` `异常` `崩溃` | **按第十七章分级路由** | — | — |

### 10.3 技能分配优先级算法

```
技能匹配分数 = 场景匹配度(0-40) + 能力覆盖度(0-30) + 历史成功率(0-20) + 上下文亲和度(0-10)

场景匹配度：任务关键词与路由表的命中数 / 总关键词数 × 40
能力覆盖度：任务所需能力与技能 SKILL.md 声明的能力交集 / 任务所需能力总数 × 30
历史成功率：该技能在相似场景下的成功率 × 20（首次使用默认15分）
上下文亲和度：当前对话上下文中该技能被引用的频率 × 10

匹配分数 ≥ 70 → 自动分配
匹配分数 50-69 → 列出 Top-2 候选，自动选最高分
匹配分数 < 50 → 列出 Top-3 候选，用户人工选择
```

### 10.4 冲突仲裁规则

| 冲突场景 | 仲裁规则 | 示例 |
|----------|---------|------|
| 多技能声称覆盖同一任务 | 优先级铁律（第二章）决定 | CSSArchitectureSkill vs FrontendAnimationSkill 争抢样式任务 → CSSArchitectureSkill 胜出 |
| 指令与技能同时匹配 | 流程指令 > 业务技能 | /tdd 与 TestingSkill 同时触发 → /tdd 主导，TestingSkill 在 RED→GREEN→REFACTOR 框架内执行 |
| 前序技能产出未就绪 | 阻塞等待 + 并行降级 | FastAPIServerSkill 等 MySQLOrmSkill 模型产出 → 先启用 APIMockSkill 让前端并行推进 |
| 技能间循环依赖 | SuperPower 介入拆解 | A 依赖 B 产出，B 依赖 A 产出 → SuperPower 重新规划顺序 |
| **修复优先级 vs 常规流程**（v5.0新增） | **修复分级 > 常规流程** | P0热修复 vs TDD流程 → 修复分级优先，走紧急通道 |

---

## 十一、跨团队技能共享机制

### 11.1 技能资产目录（Skill Asset Registry）

每个项目维护 `.trae/skills/registry.json` 作为技能注册表：

```json
{
  "project": "智维AgentHub",
  "updated": "2026-06-13",
  "entries": [
    {
      "name": "MySQLOrmSkill",
      "version": "1.0.0",
      "source": "project-custom",
      "owner": "backend-team",
      "status": "active",
      "health": { "usageCount": 23, "successRate": 0.91, "lastUsed": "2026-06-09" },
      "exports": ["SQLAlchemy异步引擎", "Alembic迁移脚本", "索引设计模板"],
      "dependencies": [],
      "consumers": ["FastAPIServerSkill"]
    }
  ]
}
```

### 11.2 三级技能复用层级

| 层级 | 范围 | 目录 | 共享机制 | 更新策略 |
|------|------|------|----------|----------|
| L1 全局级 | 所有项目 | `~/.agents/skills/` | 社区技能市场安装，所有项目自动可用 | 跟随上游社区更新 |
| L2 组织级 | 团队/部门 | `组织仓库/skills/` | Git 子模块或私有技能仓库 | 团队CI/CD统一发布 |
| L3 项目级 | 单个项目 | `.trae/skills/` | 项目内直接使用，可覆盖L1/L2同名技能 | 项目自行维护 |

**复用规则**：
- 项目级(L3) > 组织级(L2) > 全局级(L1)，同名技能项目级优先
- 技能被3个以上项目使用时，必须提升至L2组织级
- 技能被5个以上团队使用时，必须提升至L1全局级并发布至社区

### 11.3 跨团队协作规范

| 规范项 | 要求 |
|--------|------|
| 技能命名 | 全局唯一，格式：`{领域}{职能}Skill`（如 `MySQLOrmSkill`） |
| 接口契约 | 每个技能必须声明 `inputs`（前置依赖产出物）和 `outputs`（产出物清单） |
| 变更通知 | 技能更新必须通知所有 `consumers`（下游消费者），提供迁移指南 |
| 兼容性承诺 | MAJOR 版本变更需提前30天通知，提供双版本并行过渡期 |
| 知识沉淀 | 每个技能使用案例必须沉淀至 `.trae/skills/cases/` 目录 |

### 11.4 技能发现与注册流程

```
新技能需求提出
  → 检查 registry.json 是否存在匹配技能
    → 存在：复用或适配
    → 不存在：检查 L2 组织级/L1 全局级
      → 存在：拉取至项目级
      → 不存在：创建新技能
        → 填写 SKILL.md（必须含 Four Workflows）
        → 注册至 registry.json
        → 提交至组织技能仓库（如需提升至L2）
```

---

## 十二、技能使用效率评估标准

### 12.1 核心KPI指标体系（SMART原则）

| KPI指标 | 计算方式 | 目标值 | 告警阈值 | 数据来源 |
|---------|----------|--------|---------|----------|
| 技能命中率 | 技能被正确匹配的次数 / 总任务分配次数 | ≥ 85% | < 70% | 会话日志分析 |
| 技能成功率 | 技能产出通过后续校验的次数 / 技能被调用总次数 | ≥ 90% | < 75% | 下游技能反馈 |
| 技能响应时长 | 从分配到产出交付的平均时间 | ≤ 任务预估时长的 120% | > 150% | 会话计时 |
| 技能复用率 | 跨项目使用的技能数 / 总技能数 | ≥ 60% | < 40% | registry.json 统计 |
| 技能闲置率 | 30天内未使用的技能数 / 总技能数 | ≤ 20% | > 35% | 使用日志 |
| 技能冲突率 | 触发仲裁的次数 / 总分配次数 | ≤ 5% | > 10% | 仲裁记录 |
| 流转合规率 | 按流水线顺序执行的次数 / 总任务数 | ≥ 90% | < 75% | 流水线审计 |
| 红线触犯率 | 违反协作红线的次数 / 总操作次数 | 0% | > 2% | 红线检查器 |

### 12.2 技能健康度评分模型

```
技能健康度 = 成功率(×0.35) + 响应效率(×0.25) + 复用价值(×0.20) + 维护活跃度(×0.15) + 满意度(×0.05)

各子项评分标准：
  成功率：      实际成功率 / 目标值90% × 35，上限35
  响应效率：    目标时长120% / 实际耗时比例 × 25，上限25
  复用价值：    实际复用项目数 / 预期复用数(3) × 20，上限20
  维护活跃度：  60天内更新次数 ≥ 2 → 15分，≥ 1 → 10分，0 → 5分
  满意度：      下游技能反馈好评率 × 5

评级标准：
  S级 ≥ 90分：核心技能，优先保障资源
  A级 75-89分：稳定技能，正常维护
  B级 60-74分：需优化技能，列入改进计划
  C级 45-59分：问题技能，限期整改（2周）
  D级 < 45分：待淘汰技能，启动废弃流程
```

### 12.3 效率瓶颈识别与改进

| 瓶颈类型 | 识别信号 | 根因分析方向 | 改进措施 |
|----------|---------|-------------|---------|
| 匹配瓶颈 | 技能命中率持续下降 | 路由表过时、场景覆盖不全 | 更新场景路由表、增加触发关键词 |
| 产出瓶颈 | 下游技能频繁驳回 | 技能能力退化、规范未遵守 | 补充 SKILL.md 约束、增加自动校验 |
| 协作瓶颈 | 技能间等待时间过长 | 串行依赖过多、产出物不兼容 | SuperPower 优化编排顺序 |
| 维护瓶颈 | 技能长期未更新 | 责任人缺失、知识流失 | 指定维护Owner、建立轮值制度 |
| 认知瓶颈 | 用户频繁人工选择 | 技能描述不清晰、边界模糊 | 优化技能描述、增加使用示例 |
| **修复瓶颈**（v5.0新增） | P2/P3修复走完整流水线耗时过长 | 流程过于僵化 | 按第十七章分级走对应流程 |

---

## 十三、技能更新与迭代流程

### 13.1 语义化版本规范（SemVer for Skills）

```
技能版本号：MAJOR.MINOR.PATCH

MAJOR：不兼容的产出物格式变更（下游技能必须修改适配）
  - 示例：MySQLOrmSkill 模型基类改名 → 3.0.0
MINOR：向后兼容的新能力添加（下游技能无需修改）
  - 示例：CacheStrategySkill 新增 Write-Through 模式 → 2.1.0
PATCH：向后兼容的缺陷修复、文档更新
  - 示例：APIMockSkill 修复假数据生成器的边界条件 → 1.0.1
```

### 13.2 技能生命周期状态机

```
                    ┌─────────────────────────────┐
                    ↓                             │
  [构思] → [草案] → [候选] → [活跃] → [维护] → [废弃]
              ↑                 ↓        ↓
              └─── 反馈修订 ────┘    [冻结]
                                        ↓
                                    [归档]
```

| 状态 | 含义 | 可用性 | 触发条件 |
|------|------|--------|---------|
| 构思 | 需求已识别，尚未开发 | 不可用 | 新场景出现，无匹配技能 |
| 草案 | SKILL.md 已编写，待审核 | 仅开发环境 | 新技能提交 PR |
| 候选 | 通过审核，等待实战验证 | 灰度启用（50%流量） | 审核通过 |
| 活跃 | 生产就绪，推荐使用 | 全量可用 | 灰度验证通过，成功率 ≥ 90% |
| 维护 | 正常运行，仅修Bug | 全量可用 | 活跃 ≥ 6个月且无新能力需求 |
| 冻结 | 停止新增能力，仅安全修复 | 仅存量项目 | 替代技能上线 |
| 废弃 | 不再使用，建议迁移 | 不可用 | 使用者全部迁移完成 |
| 归档 | 保留历史记录 | 不可用 | 废弃 ≥ 6个月 |

### 13.3 更新流程（Change Management）

```
变更发起（Issue/PR）
  → 影响分析（变更级别判定 + 下游影响评估）
    → PATCH 级：自动合并，无需审批
    → MINOR 级：技能Owner审批，通知下游消费者
    → MAJOR 级：SuperPower审批 + 下游消费者确认 + 迁移指南
  → 测试验证
    → 单元验证：SKILL.md 强制约束自检
    → 集成验证：与上下游技能联合演练
    → 回归验证：历史成功案例回放
  → 灰度发布（候选状态 → 50%流量，观察成功率 ≥ 48h）
  → 全量发布（活跃状态，更新 registry.json）
  → 下游迁移（MAJOR变更时，协助消费者完成迁移）
```

### 13.4 废弃与迁移规范

| 步骤 | 时间节点 | 动作 |
|------|---------|------|
| 1. 废弃预告 | T-30天 | 在 registry.json 标记 `status: "deprecating"`，通知所有消费者 |
| 2. 迁移指南 | T-25天 | 发布新旧技能对照文档，提供自动化迁移脚本 |
| 3. 双轨运行 | T-20天至T+0 | 新旧技能并行可用，新项目强制使用新技能 |
| 4. 正式废弃 | T+0 | 旧技能标记 `status: "deprecated"`，禁止新项目使用 |
| 5. 迁移验证 | T+15天 | 确认所有消费者完成迁移 |
| 6. 归档 | T+30天 | 旧技能移至归档目录，保留6个月备查 |

---

## 十四、技能监控与治理措施

### 14.1 实时监控面板指标

| 监控维度 | 指标 | 采集频率 | 告警条件 |
|----------|------|---------|---------|
| 使用活跃度 | 每技能日均调用次数 | 实时 | 连续7天为0 → 闲置告警 |
| 负载均衡 | 各技能调用量标准差 | 每小时 | 标准差 > 均值×2 → 分配偏差告警 |
| 成功率波动 | 成功率日环比变化 | 每小时 | 下降 > 15% → 技能退化告警 |
| 等待队列 | 技能排队等待任务数 | 实时 | > 5个 → 技能瓶颈告警 |
| 产出质量 | 下游技能驳回率 | 每次调用 | > 20% → 质量问题告警 |
| 合规性 | 红线触犯次数 | 实时 | > 0 → 立即告警 + 阻断 |

### 14.2 闲置技能检测与处理（Anti-Idle）

```
闲置判定标准：
  一级闲置：连续7天未使用 → 触发提醒
  二级闲置：连续30天未使用 → 触发评估
  三级闲置：连续90天未使用 → 触发处置

处置策略：
  一级闲置 → 通知技能Owner，确认是否为阶段性需求
  二级闲置 → 评估保留价值
    - 业务场景已消失 → 进入废弃流程
    - 场景仍存在但被替代 → 分析替代原因，优化或废弃
    - 场景仍存在且无替代 → 分析为什么没被使用（触发词缺失/文档不清）
  三级闲置 → 强制进入废弃流程，除非Owner提供充分保留理由
```

### 14.3 过度使用防护（Anti-Overuse）

| 防护措施 | 机制 | 阈值（v5.0优化） |
|----------|------|------|
| 单技能调用频控 | 令牌桶算法，每分钟最大调用次数 | 60次/分钟（原30次，提升以适应高频修复场景） |
| 会话技能配额 | 单次对话最多激活技能数 | 12个/会话（原8个，支持复杂修复场景） |
| 技能栈深度限制 | 技能嵌套调用最大层数 | 6层（原4层，支持深度调用链） |
| 重复调用去重 | 相同输入+相同技能 → 返回缓存结果 | 5分钟窗口 |
| 强制降级开关 | 技能连续失败3次 → 自动降级至备选技能 | 失败率 > 50% |

### 14.4 合规审计清单（每次PR/发布前强制执行）

| 审计项 | 检查方式 | 通过标准（v5.0优化） |
|--------|---------|------|
| 优先级合规 | 检查技能调用顺序是否符合第二章优先级铁律 | 100% 符合（P0修复例外） |
| 流水线合规 | 检查任务执行是否遵循第五章标准流水线 | 新功能 ≥ 90%，修复按第十七章分级 |
| 红线合规 | 检查是否存在第六章定义的违规行为 | 0 违规（修复例外条款不计入违规） |
| 缓存强制降级 | CacheStrategySkill 所有操作包含 try/except | 100% |
| TS 类型独占 | 非 MattPocock 技能无自定义 TS 类型代码 | P0/P1简单类型例外需事后补校验 |
| CSS 变量强制 | 前端代码无硬编码颜色/间距/圆角/阴影 | 100% |
| OKLCH 色彩合规 | 所有颜色值使用 OKLCH 色彩空间，无 hex/rgb/hsl 硬编码 | 100% |
| 数据驱动选型验证 | 设计选型前须通过 UI/UX Pro Max search.py 查询数据 | 新设计100%，样式修复可跳过 |
| 设计决策权威性 | 视觉方向决策由 Impeccable 主导，非其他技能越权 | 100%（样式修复：CSSArchitectureSkill可直接处理） |
| 构建体积约束 | 单chunk ≤ 500KB，总构建 ≤ 2MB (Brotli) | 100% |
| 测试覆盖率 | 前端 ≥ 70%，后端 ≥ 80% | 新功能100%，P0修复事后补全，P1修复核心路径≥基线 |
| 磁盘空间检查 | 任务执行前检查项目所在盘剩余空间 | 100%（P0修复可跳过） |
| 缓存路径合规 | 所有包管理器缓存指向D盘，无C盘默认路径 | 100% |
| 大文件操作预检 | npm install / docker build / conda install 前检查磁盘 | 100%（P0修复可跳过） |
| 项目目录保护 | 自动清理不删除当前项目目录 | 100% |

### 14.5 持续改进飞轮

```
[度量] → [分析] → [改进] → [验证] → [标准化]
   ↑                                       ↓
   └──────────── 反馈循环 ←────────────────┘

度量：每月自动采集 12.1 节全部 KPI
分析：识别 Top-3 瓶颈技能和 Top-3 闲置技能
改进：制定改进计划（参考 12.3 节）
验证：改进后观察30天，对比改进前后指标
标准化：成功经验写入本规则文档，失败教训加入反模式库
```

### 14.6 角色与责任矩阵

| 角色 | 职责 | 权限 | 持有者 |
|------|------|------|--------|
| 技能Owner | 单技能的质量、更新、文档维护 | 技能修改、发布、废弃 | 技能创建者或指定接班人 |
| SuperPower（架构师） | 技能间协作、流水线编排、冲突仲裁 | 跨技能决策、MAJOR变更审批 | 项目技术负责人 |
| 技能管理员 | 全局技能注册表维护、监控面板运营 | 技能注册/注销、告警配置 | 基础设施团队 |
| 技能使用者 | 按规范使用技能、反馈使用体验 | 技能调用、问题报告 | 全体开发人员 |

---

## 十五、规则版本与修订记录

| 版本 | 日期 | 修订内容 | 作者 |
|------|------|---------|------|
| v1.0 | 2026-06-09 | 初始版本：一至九章（18项技能使用规则） | 智维AgentHub团队 |
| v2.0 | 2026-06-10 | 新增十至十四章（技能治理体系） | 智维AgentHub团队 |
| v3.0 | 2026-06-10 | 新增3项GitHub热门设计技能及协作规则 | 智维AgentHub团队 |
| v4.0 | 2026-06-11 | 新增第十六章磁盘空间防护规则（DiskGuard） | 智维AgentHub团队 |
| v5.0 | 2026-06-13 | **修复规范全面评估优化**：新增第十七章（代码修复分级体系）、第十八章（紧急热修复通道）；优化第六章（协作红线增加修复例外）、第七章（异常处理增加P0紧急故障入口）、第十章（场景路由增加Bug修复行）、第十二章（瓶颈分析增加修复瓶颈）、第十四章（合规审计按修复级别差异化标准、防护阈值提升）；放宽P0/P1修复的TS类型/设计审批/测试覆盖率/磁盘检查约束 | 智维AgentHub团队 |

---

## 十六、磁盘空间防护规则（DiskGuard）

### 16.1 磁盘空间三级告警体系

| 告警级别 | C盘阈值 | D盘阈值 | 触发动作 |
|----------|---------|---------|---------|
| 🟢 安全 | > 15GB | > 30GB | 正常执行，无需干预 |
| 🟡 警告 | 8-15GB | 10-30GB | 执行前必须检查磁盘；大文件操作需用户确认 |
| 🔴 危险 | < 8GB | < 5GB | **强制阻断**：禁止任何写入操作，必须先清理磁盘 |

**v5.0变更说明**：D盘阈值从50GB/20GB下调至30GB/5GB，适配实际磁盘容量，减少误告警。

### 16.2 任务执行前强制检查（Pre-Task Disk Check）

```
任何开发任务执行前，必须按以下流程检查：

1. 检查项目所在盘（D盘）剩余空间
   PowerShell: Get-PSDrive D | Select-Object Free, Used

2. 判断告警级别：
   - 🟢 安全 → 正常执行
   - 🟡 警告 → 提示用户当前磁盘状态，大文件操作需确认
   - 🔴 危险 → 阻断任务，执行自动清理流程（16.4节）

3. 以下任务类型必须额外评估磁盘占用：
   - npm install / uv pip install / pip install（包安装）
   - docker build / docker pull（镜像拉取）
   - 数据库迁移/数据导入
   - 前端构建（npm run build）
   - 大文件下载/生成
   - conda install / conda create

4. P0紧急热修复例外：可跳过磁盘检查，修复完成后补充检查（见18.1节）
```

### 16.3 缓存目录统一管理（Cache Relocation）

**强制规范**：所有包管理器缓存必须指向D盘，禁止使用C盘默认路径。

| 包管理器 | 环境变量 | D盘路径 | 当前状态 |
|----------|---------|---------|---------|
| uv | UV_CACHE_DIR | D:\cache\uv | ✅ 已迁移 |
| npm | npm_config_cache | D:\cache\npm | ✅ 已迁移 |
| pip | PIP_CACHE_DIR | D:\cache\pip | ✅ 已迁移 |
| conda | CONDA_PKGS_DIRS | D:\cache\conda | ⚠️ 待迁移 |
| Gradle | GRADLE_USER_HOME | D:\cache\gradle | ⚠️ 待迁移 |

**待迁移项执行命令**：
```powershell
# Conda 缓存迁移
[Environment]::SetEnvironmentVariable("CONDA_PKGS_DIRS", "D:\cache\conda", "User")
conda config --add pkgs_dirs D:\cache\conda

# Gradle 缓存迁移
[Environment]::SetEnvironmentVariable("GRADLE_USER_HOME", "D:\cache\gradle", "User")
```

### 16.4 自动清理流程（Auto Cleanup）

当磁盘进入🔴危险级别时，按以下优先级自动清理：

| 优先级 | 清理目标 | 预计释放 | 清理命令 |
|--------|---------|---------|---------|
| 1 | uv 缓存 | 1-3GB | `uv cache clean` |
| 2 | npm 缓存 | 0.5-2GB | `npm cache clean --force` |
| 3 | pip 缓存 | 0.5-1GB | `pip cache purge` |
| 4 | conda 包缓存 | 1-4GB | `conda clean --all -y` |
| 5 | Gradle 缓存 | 0.5-1.5GB | `Remove-Item -Recurse -Force D:\cache\gradle\caches` |
| 6 | 临时文件 | 0.5-3GB | `Remove-Item -Recurse -Force D:\Temp\*` |
| 7 | Docker 无用资源 | 1-5GB | `docker system prune -af` |
| 8 | node_modules（非当前项目） | 1-5GB | 扫描并清理非活跃项目的 node_modules |
| 9 | 构建产物（dist/build） | 0.5-2GB | 清理非当前项目的构建输出 |

**清理安全规则**：
- 永远不清理当前正在开发的项目目录
- 永远不清理 `D:\Trae CN\Project\智维 AgentHub` 下的任何文件
- 清理前必须列出将要删除的目录及大小，经用户确认后执行
- 被进程锁定的文件跳过，不强制删除

### 16.5 高磁盘占用任务防护规则

| 任务类型 | 防护措施 | 磁盘占用预估 |
|----------|---------|-------------|
| `npm install` | 安装前检查 node_modules 是否已存在；优先使用 `npm ci`（更干净） | 200MB-1GB |
| `uv pip install` | 使用 `--no-cache` 安装非开发依赖；定期 `uv cache clean` | 100MB-500MB |
| `conda install` | 安装后立即 `conda clean --all`；优先用 pip 替代 conda | 500MB-3GB |
| `docker build` | 构建后立即删除中间镜像；使用 `--no-cache` 仅在必要时 | 1-5GB |
| 前端构建 | 构建完成后检查 dist 体积；超 50MB 发出警告 | 5-50MB |
| 数据库操作 | 大数据导入前检查磁盘空间；导入后清理临时文件 | 视数据量 |
| AI/ML 模型下载 | 下载前检查模型大小+磁盘剩余；优先使用 D 盘存储 | 1-10GB |

### 16.6 定期清理计划（Scheduled Cleanup）

| 频率 | 清理项 | 命令 |
|------|--------|------|
| 每次会话开始 | 检查磁盘空间 | `Get-PSDrive C,D \| Select-Object Name,Free,Used` |
| 每日 | uv/npm/pip 缓存清理 | `uv cache clean && npm cache clean --force && pip cache purge` |
| 每周 | conda 缓存清理 | `conda clean --all -y` |
| 每周 | 临时文件清理 | `Remove-Item -Recurse -Force D:\Temp\* -ErrorAction SilentlyContinue` |
| 每月 | Docker 资源清理 | `docker system prune -af` |
| 每月 | 非活跃项目 node_modules 扫描 | 扫描 > 30天未修改的 node_modules |

### 16.7 磁盘占用监控点

以下目录为已知高增长目录，每次会话应关注：

| 目录 | 盘符 | 增长原因 | 监控阈值 |
|------|------|---------|---------|
| `C:\Users\tyq\AppData\Local\uv\cache` | C | uv 包缓存（已迁移，旧目录待删） | > 500MB 告警 |
| `C:\Users\tyq\AppData\Roaming\npm-cache` | C | npm 缓存（已迁移，旧目录待删） | > 500MB 告警 |
| `D:\cache\*` | D | 统一缓存目录 | 总计 > 10GB 告警 |
| `D:\Trae CN\Project\*\node_modules` | D | 前端依赖 | 单项目 > 1GB 告警 |
| `D:\Anaconda\pkgs` | D | conda 包缓存 | > 5GB 告警 |
| `C:\Users\tyq\AppData\Local\Docker` | C | Docker 数据 | > 3GB 告警 |
| `C:\Users\tyq\.android` | C | Android SDK/AVD | > 4GB 告警 |
| `D:\Temp` | D | 临时文件 | > 2GB 告警 |

### 16.8 紧急磁盘恢复流程

```
磁盘空间 < 5GB（任一盘符）→ 触发紧急流程：

1. 立即停止当前所有写入操作
2. 执行快速清理（5分钟内完成）：
   a. uv cache clean
   b. npm cache clean --force
   c. pip cache purge
   d. 清空 D:\Temp
3. 检查清理后空间：
   - 恢复到 🟡 警告以上 → 可继续任务
   - 仍在 🔴 危险 → 执行深度清理（16.4节完整流程）
4. 深度清理后仍在 🔴 危险 → 通知用户手动处理：
   - 卸载不常用程序
   - 迁移大文件到其他盘/外置存储
   - 清理浏览器下载目录
```

---

## 十七、代码修复分级体系（v5.0 新增）

### 17.1 修复分级矩阵

| 级别 | 定义 | 响应时限 | 变更范围 | 审批要求 | 测试要求 | 提交格式 |
|------|------|---------|---------|---------|---------|---------|
| **P0 紧急热修复** | 生产环境故障、安全漏洞、数据丢失/损坏、核心功能完全不可用 | ≤ 30分钟 | ≤ 3个文件 | 事后补审 | 手动验证核心路径，事后1周内补全 | `hotfix: {描述}` |
| **P1 关键修复** | 核心功能异常但不完全阻塞、影响≥30%用户、关键路径性能严重退化 | ≤ 4小时 | ≤ 5个文件 | 1人快速过审 | 受影响模块核心测试，覆盖率事后补达基线 | `fix(p1): {描述}` |
| **P2 常规修复** | 非核心功能异常、UI显示问题、兼容性问题、偶发bug | ≤ 2个工作日 | ≤ 10个文件 | 常规CR | 正常TDD流程 | `fix: {描述}` |
| **P3 优化修复** | 技术债务清理、代码异味、性能微优化、可维护性提升 | 纳入迭代计划 | 不限 | 常规CR | 正常TDD流程，覆盖率≥基线 | `refactor: {描述}` |

### 17.2 修复级别判定流程图

```
发现问题
  → 是否影响生产环境/安全漏洞/数据丢失？
    → 是 → P0 紧急热修复
    → 否 → 是否核心功能异常/影响≥30%用户？
      → 是 → P1 关键修复
      → 否 → 是否非核心功能异常/UI问题/偶发bug？
        → 是 → P2 常规修复
        → 否 → P3 优化修复（技术债务/性能微优化）
```

### 17.3 分级流程对照表

| 流程环节 | P0 紧急热修复 | P1 关键修复 | P2 常规修复 | P3 优化修复 |
|----------|-------------|-----------|-----------|-----------|
| 需求分析 /grill-me | 跳过 | 跳过（仅根因分析） | 可选（复杂情况使用） | 使用 |
| PRD文档 /write-a-prd | 跳过 | 跳过 | 跳过 | 可选 |
| 开发计划 /prd-to-plan | 跳过 | 跳过 | 跳过 | 可选 |
| TDD /tdd | 跳过（事后补测试） | 简化（RED→GREEN→快速VERIFY） | 完整（RED→GREEN→REFACTOR→VERIFY） | 完整 |
| 接口设计 /design-an-interface | 跳过 | 仅涉及新接口时使用 | 涉及新接口时使用 | 使用 |
| 架构设计 SuperPower | 跳过 | 仅跨模块变更时咨询 | 仅架构变更时使用 | 使用 |
| 代码审查 /code-review | 1人快速过审 | 1人常规CR | 常规CR | 常规CR+技术评审 |
| 测试覆盖率 | 事后1周补达基线 | 核心路径≥基线，事后补全 | ≥ 基线 | ≥ 基线 |
| 变更文档 | 事后补充 | 事后补充 | 正常记录 | ADR（如需） |
| 分支管理 | 可直接推 main | 修复分支 → PR → main | 修复分支 → PR → main | 功能分支 → PR → main |

### 17.4 技能审批链简化（按修复级别）

| 技能审批步骤 | P0 | P1 | P2 | P3 |
|-------------|-----|-----|-----|-----|
| MattPocock TS类型校验 | 仅复杂类型需要，可事后补 | 简单类型可跳过 | 必须 | 必须 |
| Impeccable 设计审批 | 跳过 | 仅涉及新增UI元素 | 仅涉及视觉变更 | 必须 |
| CSSArchitectureSkill Token校验 | 跳过（但禁止新增硬编码） | 跳过（但禁止新增硬编码） | 仅新增样式时 | 必须 |
| FrontendPerfSkill 性能验证 | 跳过 | 仅涉及构建配置变更 | 仅涉及构建配置变更 | 必须 |
| FrontendAnimationSkill 动画审批 | 跳过 | 跳过 | 仅涉及动画变更 | 必须 |
| CacheStrategySkill 缓存审批 | 跳过 | 仅涉及缓存逻辑变更 | 必须 | 必须 |
| GitProSkill 规范化提交 | 使用 hotfix: 前缀 | 使用 fix(p1): 前缀 | 使用 fix: 前缀 | 使用 refactor: 前缀 |

---

## 十八、紧急热修复通道（v5.0 新增）

### 18.1 P0热修复五步快速通道

```
Step 1: 即时诊断（10分钟）
  → /diagnose 定位根因
  → 确定最小化修复方案
  → 可在当前分支直接修复，无需创建新分支
  → 可跳过磁盘检查

Step 2: 最小化修复（15分钟）
  → 仅修改直接相关的代码文件（≤ 3个文件）
  → 禁止重构、禁止优化、禁止涉及非修复目标的代码
  → 允许绕过技能审批链直接编写修复代码
  → 简单TS类型修复可直接处理，无需MattPocock

Step 3: 快速验证（3分钟）
  → 代码逻辑审查（1人快速过审）
  → 手动验证核心修复路径
  → 跳过完整测试套件

Step 4: 紧急上线（2分钟）
  → 提交信息使用 `hotfix: {描述}` 格式
  → 直接推送到 main/master
  → 触发紧急部署流程

Step 5: 事后补全（1周内完成）
  → 补充单元测试/集成测试
  → 补充修复文档（根因分析 + 修复说明）
  → 补充代码审查记录
  → 如需架构/设计变更，补充ADR
  → 清理热修复可能引入的技术债务
```

### 18.2 P0热修复判定标准

| 判定条件 | 是 → P0 | 否 → 降级 |
|----------|---------|----------|
| 生产环境服务完全不可用 | P0 | P1 |
| 安全漏洞（可被外部利用） | P0 | 视严重程度 |
| 用户数据丢失或损坏 | P0 | P1 |
| 支付/交易流程中断 | P0 | P1 |
| 核心功能崩溃（>50%用户受影响） | P0 | P1 |
| 数据库损坏 | P0 | P1 |

### 18.3 热修复反模式（禁止行为）

| 反模式 | 说明 | 风险 |
|--------|------|------|
| 热修复中重构 | P0修复时顺手重构代码 | 引入新bug，扩大影响面 |
| 热修复中新增功能 | 借热修复添加新特性 | 混淆修复边界，难以回滚 |
| 跨模块大范围修改 | 热修复涉及>3个文件 | 增加验证复杂度，延长修复时间 |
| 忽略事后补全 | 修复后不补测试和文档 | 技术债务积累，下次同类问题无据可查 |
| 连续热修复 | 同一模块连续2次P0修复 | 说明首次修复不彻底或存在设计缺陷，需升级为P1/P2深度修复 |
| 分支管理混乱 | 热修复在功能分支开发 | 需在最新 release 分支或 main 分支基础上修复 |

### 18.4 热修复后评估模板

```
## 热修复后评估报告

| 项目 | 内容 |
|------|------|
| 修复ID | HOTFIX-{YYYYMMDD}-{序号} |
| 修复日期 | {日期} |
| 修复级别 | P0 |
| 影响范围 | {受影响模块/用户比例} |
| 根因 | {根本原因分析} |
| 修复方案 | {修复描述} |
| 修复文件数 | {数量} |
| 修复耗时 | {从发现到上线总耗时} |
| 是否引入新问题 | {是/否} |
| 测试补全日期 | {日期} |
| 文档补全日期 | {日期} |
| 教训总结 | {经验教训} |
```

---

> **附则**：本规则体系每季度（3个月）进行一次全面审查和修订。任何开发者均可通过 Issue/PR 提出修订建议。规则修改需 SuperPower 审批后生效。
>
> **v5.0核心优化原则**：修复效率与质量并重，分级管控替代一刀切。P0保速度（30分钟上线），P1-P3保质量（逐级加强流程约束）。