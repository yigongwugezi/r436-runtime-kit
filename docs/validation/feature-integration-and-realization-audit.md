# 功能接入、真实实现与产品闭环审计

## 2026-07-16 候选线收口更新

本节覆盖并取代下文仍以 `619607a` 为基线的“当前阻塞／下一轮”描述。当前本地候选为 `MAF-Refactor` 的 `c94957c`，在 `619607a` 之后已经完成以下独立、可回归的本地修复：

| 状态 | 提交 | 已证实的结果 | 验证 |
|---|---|---|---|
| FIXED_LOCAL / BLOCKED_BY_NETWORK | `619607a` | `/api/questions*` 只保留具备 learner/session 归属校验的 canonical router，消除重复路由的权限绕过。 | 隔离 SQLite 的 question authorization 回归；网络不可用，尚未发布。 |
| FIXED_LOCAL / BLOCKED_BY_NETWORK | `7e6bdc9` | 合并后 5 项 TypeScript 契约错误已修复：资源质量状态、资源类型映射、渲染正文变量与流式聊天 `image_provider` 均有明确类型。 | `npm run build` 成功；`workflowTaskRecovery` 与 learning-path ViewModel 回归通过。 |
| FIXED_LOCAL / BLOCKED_BY_NETWORK | `c6dbc39` | 新对话只创建 session；未明确主题不会继承浏览器中历史 active subject。显式主题消息才会原子绑定该 session；无主题 Profile 只显示 learner-global 画像与“暂未选择学习主题”。 | 临时 SQLite 的 current-subject、learner/session、subject identity、Profile V2、chat fallback 测试，以及隔离 fake-Provider Edge 旅程均通过。 |
| FIXED_LOCAL / BLOCKED_BY_NETWORK | `498d95c`, `00eccf4` | 多类型在线搜索为每种所选类型预留两次 primary 调用，`paper` 有独立两次 fallback reserve；等待已在途首选层，避免多发无意义 fallback。 | recommendations、general search、cascade、search client 与 fake Edge online-search 回归通过；未调用真实搜索 Provider。 |
| FIXED_LOCAL / BLOCKED_BY_NETWORK | `c94957c` | Provider fallback 回归改为验证现行统一工厂的 `UnifiedChatClient` 契约，而非已经被工厂替代的旧 client 实现。 | `deeptutor_client_test.py` 在临时 SQLite／测试 key 下通过；没有发起网络请求，也没有修改 Provider 代码。 |

`PUSHED` 目前为 0：本轮与此前多次 `git fetch origin` 都因 GitHub 连接被重置而失败，因此没有依据过期远端状态推送。上述四项均为本地候选修复，远端仍可能缺少它们，尤其是 `619607a` 的权限修复。

### 当前收口分类

- **FIXED_LOCAL**：前端构建、无主题新会话 subject 边界、资源搜索类型预算与冗余 fallback 均已修复并由安全 fake/临时 SQLite 回归验证。
- **BLOCKED_BY_NETWORK**：所有本地候选提交仍待网络恢复后的 fetch 安全门和普通 push；没有使用 force push、pull、merge 或 rebase。
- **CONFIRMED_OPEN**：专门的规划需求收集／草案确认／执行调整旅程仍未形成产品闭环；P6 后端任务表仍是单进程内存，不能跨后端重启或多实例恢复。
- **ASSIGNED_TO_TEAMMATE**：引导式学习路径规划流程由组员独立施工；本工作区没有重写 Planner、也没有修改该路径规划功能。
- **DEFERRED**：Manim、视频／图像与 RAG 依赖外部 Provider 或系统工具；真实外部 Provider 冒烟未在本轮执行。

### 当前 Top 10

1. **P0，BLOCKED_BY_NETWORK**：网络恢复后先按安全门发布 `619607a` 及后续本地提交；远端在此之前可能仍有 questions 权限漏洞。
2. **P1，ASSIGNED_TO_TEAMMATE**：引导式规划体验（需求收集、草案确认、可见任务、执行与调整）尚未合线，不在本工作区重复实现。
3. **P1，CONFIRMED_OPEN**：为 `WorkflowTaskManager` 引入可恢复的共享任务存储与跨实例锁；当前刷新恢复只覆盖同一后端进程。
4. **P1，CONFIRMED_OPEN**：将 assessment/diagnosis 的事件、通知和重规划形成可重启、可解释的端到端闭环。
5. **P2，CONFIRMED_OPEN**：画出调用方后再收口 `product.py` 旧直调与 LangGraph 的重叠编排面，不能凭静态文件名删除。
6. **P2，CONFIRMED_OPEN**：清理已确认无调用方的 legacy router 与 `planner_agent.py.bak`；需要独立 OpenAPI/调用方审计。
7. **P2，后端能力缺前端旅程**：规划 workflow 存在，但缺少专门的产品入口和页面级取消／草案恢复体验。
8. **P2，数据展示未完全闭环**：Analytics 已有页面和接口，但推荐质量仍依赖学习事件覆盖度，未能仅靠静态代码证明。
9. **P3，DEFERRED**：Manim、视频／图像和 RAG 采用可选依赖；未配置时必须继续优雅降级，不应标记为默认可交付。
10. **P3，真实外部验证**：在线资源搜索、LLM 与媒体 Provider 仅完成 fake/不可用路径验证；真实调用必须另行受控验收。

本更新没有读取 `.env`、凭据、真实聊天、画像、题目或数据库正文，也没有运行真实外部 LLM、搜索或媒体 Provider。

## 范围与判定

- 审计基线：本地 `MAF-Refactor` 的 `619607a`；本报告为静态代码、路由、已有自动化验证记录和隔离 fake 环境结果的汇总。
- 本报告不读取凭据、真实聊天、画像、数据库正文或外部 Provider 结果；因此“真实外部服务已验收”不会因 mock 通过而被标记为完成。
- 状态：**A 已接入**、**B 部分接入**、**C 仅后端**、**D 仅前端**、**E 配置/系统依赖受限**、**F 死代码或重复实现候选**、**G 当前阻断/缺陷**。
- 合计 34 个审计单元：A 7、B 14、C 3、D 0、E 4、F 3、G 3、另有 1 个本地已修复但尚未发布的 P0（计入 B）。

## 执行摘要

项目已经具备聊天、画像显式事实、资源生成、资源库、在线资源搜索、学习路径视图、题目练习、反馈、任务 SSE/取消/重试/刷新恢复等主要骨架；这些能力不是纯 UI 占位。不过，完整产品闭环仍被三个当前问题卡住：前端 TypeScript 构建失败、空主题新对话继承旧学科、在线搜索的全局调用预算可能让 `paper` 没有机会执行。

`/api/questions*` 的重复路由权限绕过已由本地 `619607a` 修正：主应用只保留拥有 learner/session 归属校验的 questions router。该提交尚未推送；最近一次 `fetch` 被 GitHub 连接重置打断，远端仍可能保留旧漏洞，必须在网络恢复并通过常规 fast-forward 安全门后发布。

## 当前能力矩阵

| 领域 | 状态 | 实际接入与证据 | 主要缺口 |
|---|---|---|---|
| learner/session 稳定标识 | B | `chatStore` 持久化匿名 learner；创建 session 可携带 learner ID；后端保留兼容链接策略 | 空主题新对话仍会继承前台激活学科，见 G-1 |
| subject 去重与标点规范化 | A | 已有 subject 复用、名称规范化和回归验证记录 | 只解决同名创建，不解决错误继承的 subject scope |
| learner 全局 explicit Profile V2 | A | explicit 事实按 learner 读取；聊天与画像页均可读取对应入口 | 当前页面 scope 选择仍可能把历史学科带入新会话 |
| subject/session Profile V2 | B | 全局、subject、session 作用域及优先级实现存在 | 无 subject 的新会话展示语义未独立处理 |
| 普通聊天与显式路径门控 | B | LangGraph 聊天入口、当前消息 fallback 和“明确生成”门控在正式链路 | Provider 可用性仍取决于本地网络/配置；未做本轮真实调用 |
| `/api/questions*` 访问控制 | B（本地修复） | `619607a` 移除 product 重复路由，canonical router 强制 ownership | 尚未发布到远端，见 P0-1 |
| 专门学习规划流程 | C | Planner、`learning_path_generation` workflow 和显式聊天触发均存在 | 无独立的需求收集、草案确认、调整入口和页面级任务体验 |
| 学习路径旧/新数据视图 | A | `learningPathViewModel`/adapter、三模式 URL 状态、旧字段兼容已有验证 | 真实历史数据与各模式完整 E2E 仍应复验 |
| 学习路径执行/自适应调整 | B | 章节/小节导航、资源工作区和 assessment loop 有连接点 | 重规划、通知与持久化不是端到端可证明闭环 |
| 通用资源生成 | A | `/generate`、多类型请求、资源持久化及列表视图均已接入 | 外部生成 Provider 未作为本审计的真实验证对象 |
| 通用资源生成 P6 | B | `general_resource_generation` 使用 task、SSE、取消、重试、刷新恢复 | 后端任务注册表为单进程内存，重启/多实例不具备同等恢复能力 |
| 讲义 section 工作区 | B | `lecture_generation`、`resource_search`、质量/反馈和恢复入口已存在 | 与路径实际执行的全旅程仍应重新 E2E |
| 资源质量与反馈 | B | 资源质量字段、反馈接口与 review/quality 组件存在 | 所有生成类型的真实 Provider 质量结论尚未验证 |
| 我的资源库 | A | 本地筛选、刷新读取、session 边界删除和类型渲染已实现 | 当前前端无法通过 TypeScript 生产构建 |
| 通用在线学习资源搜索 | B | Header 进入 `/resources?mode=online&query=...`；资源库明确区分本地筛选和联网搜索；复用 `resource_search`/SSE/P6 | 默认调用预算公平性有缺陷，真实搜索未作为本轮断言 |
| 在线结果保存与 URL 去重 | A | 保存接口持久化主题、来源、类型，按 canonical URL 去重 | 应在真实 Provider 冒烟中再验来源与类型质量 |
| 题目生成、作答与复习 | B | canonical questions API、作答、弱项和 review queue 均存在 | P0 修复未推送；师生入口发现性需产品验收 |
| Assessment / Diagnosis 闭环 | B | assessment state、触发器、Diagnosis/Planner 调用点、学习事件存在 | 通知为进程内存且真实重规划闭环未验证 |
| 学习分析 | A | `/learning-analytics`、timeline 和前端 analytics 页面存在 | 数据是否足以支撑真实推荐取决于事件覆盖与外部模型 |
| 通知 | B | 聊天端存在读取/展示路径 | `NotificationStore` 进程内存，不保证重启、多实例或跨设备 |
| Agent 注册与调度 | B | Conversation、Profile、Planner、Resource、Diagnosis、Grading、Question、Review、Knowledge、Multimodal agent 均有实现和调用点 | LangGraph 编排与 `product.py` 旧直调并存，职责边界仍需收口 |
| 动态协同展示 | B | 工作流事件可驱动部分任务状态展示 | 不能把固定“团队就绪”文案当作所有 Agent 的实时执行证明 |
| PPT 资源 | B | `python-pptx` 已声明，PPT 生成、下载、媒体卡片与隔离测试存在 | 真实模板质量和完整浏览器下载需环境验收 |
| Manim 动画 | E | provider/模板/媒体渲染路径存在 | 未配置 Manim、FFmpeg、LaTex 时应明确 `provider_not_configured`，不能承诺生成 |
| 视频/图像多模态 | E | Provider registry 与资源类型存在 | 依赖外部 Provider/系统工具，未完成本轮真实验收 |
| RAG/知识库 | E | 可选 router/服务存在 | 取决于可选依赖及配置；不是默认正式能力 |
| WorkflowTaskManager | B | 状态查询、SSE、取消、重试、前端 sessionStorage 恢复和同资源单进程防重存在 | 内存 task/event store 不跨后端重启、不支持多实例全局锁 |
| 数据持久化与恢复 | B | 资源、画像、学习路径等业务结果可重新读取 | task 本身和通知不全为持久化对象 |
| legacy router / service 表面 | F | `analytics_router` 标为 deprecated；多个 path/profile/resource/daily router 未在主应用注册；`planner_agent.py.bak` 存在 | 应在独立清理任务中确认调用者后删除或迁移，不能贸然删 |
| 前端生产构建 | G | 当前 `npm run build` 在 TypeScript 检查阶段失败 | 见 G-3；发布阻断 |
| 新会话 subject scope | G | 调用链可稳定复现 | 见 G-1 |
| 搜索类型预算 | G | 固定类型顺序和全局 provider budget 可静态证明 | 见 G-2 |

## 关键架构与闭环

### 1. 聊天、身份与画像

```text
浏览器匿名 learner ID
        │
        ├── chatStore.createChatSession(sessionId, learnerId, subjectId?)
        │                                  │
        │                                  ▼
        │                         后端 session / learner 链接
        │                                  │
        ▼                                  ▼
Profile 页面 scope ───────────► Profile V2 (session > subject > learner)
        ▲                                  │
        └──────── 聊天 LangGraph 注入 ◄───┘
```

全局 explicit 事实跨 session 的底层链路已经存在；问题不在“每次新对话必建 learner”，而在前端把当前激活 subject 一并传给没有主题的新 session，随后画像页也继续按该 subject 请求。

### 2. 资源生成、搜索与 P6

```text
Header / 资源库 online mode / lecture workspace
                    │
                    ▼
       WorkflowTaskManager: task + SSE + cancel/retry
                    │
        ┌───────────┼────────────────┐
        ▼           ▼                ▼
general generation  resource_search  lecture generation
        │           │                │
        └────► 业务结果持久化 ────────┘
                    │
                    ▼
             ResourceLibrary / 保存 / 反馈
```

前端刷新恢复的是最小 task scope 并重新查询/连接仍存在的任务；结果通过既有资源/工作流读取路径恢复。它并不把内存 WorkflowTaskManager 变成跨进程任务系统。

### 3. 学习执行闭环

```text
明确规划请求 → Planner / path workflow → LearningPathViewAdapter
                                              │
                                      chapter / section / resource workspace
                                              │
                         quiz / feedback / learning events / analytics
                                              │
                              assessment loop → diagnosis / recommendation
```

链路两端已经存在，但“规划需求收集—确认—执行—自动调整—可解释通知”的单一用户旅程尚未完全产品化；当前更像多个已接入模块的组合。

## 三个当前缺陷的可复现根因

### G-1：无主题新对话错误显示历史学科（P1）

**现象**：用户新建对话且未选择主题，Profile 页面仍显示历史学科（用户报告为“人工智能导论”）。

**调用链**：

1. `frontend/src/store/chatStore.ts` 的 `newSession` 从 `subjectStore.activeSubject` 或 class subject 读取 `subjectId`，无条件传给 `createChatSession`。
2. `frontend/src/store/subjectStore.ts` 将 active subject 持久化，因此它可以是上一段学习的历史 scope。
3. `frontend/src/hooks/useProfile.ts` 和 `frontend/src/pages/ProfilePage.tsx` 也使用该 active subject 请求 `/api/profile`。
4. `backend/app/routers/product.py` 的 session 链接兼容逻辑会把新 session 关联到传入 subject；它不会知道该 subject 只是 UI 的历史选择。

**最小修复建议（独立提交）**：新对话默认只传 `learnerId` 和 `sessionId`；仅当用户在明确 subject 上下文中主动继续时才传 `subjectId`。Profile 页面在无当前 subject 时请求/展示 learner-global scope，而不是复用历史 active subject。该修复不应改写 Profile V2 的事实优先级或批量迁移旧数据。

### G-2：在线搜索默认预算让 paper 失去执行机会（P1）

**现象**：默认最多 8 次 provider 调用，而 article、video、course、document、paper 以固定顺序处理；前四类的多层 query/cascade 可耗尽全局预算，`paper` 因而没有 provider 调用机会。

**代码依据**：`backend/app/services/section_resource_recommendations.py` 固定 `RESOURCE_TYPES` 顺序并在搜索层中检查全局 `settings.search_max_provider_calls`；`backend/app/config.py` 默认值为 8。

**最小修复建议（独立提交）**：先为每个被请求的资源类型保留一次可用尝试，再使用剩余预算做 cascade；预算不足时在 diagnostics/响应中明确该类型未执行，不把“未搜索”伪装成“无结果”。canonical query、缓存 key 和任务 key 保持不变。不要通过提高默认预算掩盖公平性问题。

### G-3：前端 TypeScript 生产构建失败（P0）

当前 `frontend` 的 `npm run build` 被五类既有静态错误阻断：

| 文件 | 错误类别 | 最小修复方向 |
|---|---|---|
| `components/common/QualityStatusPopover.tsx`、`types/resource.ts` | `QualityStatus` 未导出/未声明 | 统一类型唯一来源并导出 |
| `components/resources/ResourceCard.tsx` | 类型映射缺 `practice`、`multimodal` | 穷尽资源类型映射 |
| `components/resources/ResourceTypeRenderer.tsx` | 未定义 `content` | 使用已解构的资源正文变量或加安全分支 |
| `hooks/useStreamChat.ts` | `image_provider` 不在请求类型 | 将已有 API 字段同步进类型，或去掉未被后端消费的字段 |

这是发布阻断，不能通过跳过 TypeScript 检查、放宽断言或从 P0 权限提交中混入修复来关闭。

## 已发布前必须处理的 P0

### P0-1：questions 权限修复尚未发布

- 本地修复：`619607a fix: enforce ownership on question routes`。
- 修复内容：删除 `product.py` 中先注册的重复 `/questions*` 路由，保留 `questions.py` 的 canonical API，并在 service/router 中对 learner、session、question set、question 进行归属校验。
- 验证：隔离 SQLite 的 question authorization 回归、相关 assessment/Profile/workflow 回归以及应用 OpenAPI 路由唯一性检查均已通过。
- 发布阻塞：本轮 `git fetch origin` 因 GitHub 连接被重置失败，未更新远端引用、未 push。不得依据旧缓存强行 push；网络恢复后应 fetch、确认远端无独有提交且本地仅 ahead 1，再普通 push。

### P0-2：前端构建不可交付

见 G-3。应由单独前端类型修复提交处理，并运行 `npm run build`；不应与权限修复或搜索规则修复混合。

## 各产品面是否真正闭环

| 产品面 | 结论 | 说明 |
|---|---|---|
| Profile | **部分闭环** | explicit learner facts 可跨 conversation；global/subject/session 的 UI scope 选择尚有历史 subject 泄漏。禁用、锁定、删除等已有测试，但需在修复 scope 后重跑跨会话 E2E。 |
| Chat | **部分闭环** | 普通聊天、fallback、画像注入、显式规划门控已进入正式链路；真实 LLM 取决于 Provider 网络与配置，不能由 mock 代替。 |
| Planner | **后端能力强、产品流程弱** | Agent/workflow 存在，但缺规划需求采集、草案确认、可见进度、后续调整的一体化入口。 |
| Resource | **部分闭环** | 生成、列表、质量、反馈、保存和在线搜索入口都存在；搜索预算错误及真实 Provider 尚未关验。 |
| Diagnosis / Evaluation | **部分闭环** | assessment loop、状态、事件和调用点存在；通知与重规划未形成重启/多实例可靠闭环。 |
| Analytics | **已接入，效果待证** | API、事件和页面都在；对推荐质量与真实数据完整性不能仅凭静态审计下结论。 |

## 未进入正式流程或存在重复表面

1. 主应用注册的是 LangGraph chat router 与 `product.py` 的综合 API；后者仍含若干直接 Agent 调用。两条编排表面使聊天/工作流边界较难验证，应先画调用者清单再收口，不能直接删除旧代码。
2. `analytics_router` 明确标为 deprecated；若干 legacy path/profile/resource/daily router 未在 `main.py` 注册。它们是 F 类清理候选，不是本轮可以无验证删除的文件。
3. `planner_agent.py.bak` 是明显重复候选，应在确认没有工具/部署脚本引用后移除。
4. Manim、视频/图像和 RAG 具备实现表面，但不应在没有系统依赖或 Provider 配置时当作默认可交付功能。

## P6 长任务覆盖与边界

| 工作流 | P6 状态 | 仍缺什么 |
|---|---|---|
| `general_resource_generation` | 已接前端恢复 | 后端重启后的 task 查询不能恢复 |
| `resource_search` | 已接 online/section 两种入口 | 预算分配、真实 Provider、跨进程锁 |
| `lecture_generation` | 已接恢复 | 与学习路径全旅程复验 |
| `generated_resource`/regeneration | 已接 | 同上 |
| `profile_sync`/rebuild | 有任务能力 | 不是用户可见长任务的完整取消模型 |
| `learning_path_generation` | 有 workflow | 缺专门页面级恢复、取消和草案体验 |
| video/multimodal | 有接口表面 | Provider/系统依赖受限 |

`WorkflowTaskManager` 明确是进程内 registry。前端 sessionStorage 只能避免刷新页面重复创建，不能替代共享任务存储或分布式锁；两标签/同进程防重已覆盖，跨实例是后续基础设施任务。

## 建议优先级与可拆分工作

| 优先级 | 工作 | 最小文件范围 | 验收 |
|---|---|---|---|
| P0 | 网络恢复后发布 `619607a` | 无代码变更 | fetch 安全门、普通 push、远端 0/0 |
| P0 | 修复 5 类 TypeScript 错误 | 仅列出的前端类型/组件文件 | `npm run build`；资源、流式聊天组件回归 |
| P1 | 修复无主题 session 的 subject 继承 | `chatStore.ts`、Profile scope hook/page，必要时精确测试 | 两个 session、无 subject、Profile 页面、刷新、隔离 learner |
| P1 | 资源搜索预算公平分配 | `section_resource_recommendations.py` 与 mock cascade 测试 | 每种请求类型至少一次机会；paper 未执行可解释 |
| P1 | 产品化专门规划流程 | 学习路径页/专门 planning UI、既有 workflow API | 收集→确认→任务→恢复→执行→调整 |
| P1 | P6 后端持久化/跨实例策略 | task store/lock 的独立设计 | 重启、两实例、取消、TTL、结果读取 |
| P2 | 收口重复 legacy router/Agent 调用面 | 先调用图，再分批删除 | OpenAPI 对比、现有路由回归 |
| P2 | Assessment 通知持久化 | notification/state 边界 | 重启、多设备、重试/已读 |
| P3 | Manim/视频/RAG 可选部署包 | 文档、可选依赖、健康检查 | 有依赖时成功；无依赖时优雅不可用 |

推荐的组员拆分：前端类型构建（P0-2）、search budget + mock 回归（P1）、规划用户旅程（P1）、P6 多实例设计（P1）可并行；subject scope 修复应由熟悉 Profile V2 的负责人单独完成，以免与 learner/profile 语义冲突。所有人都应避免改动 `619607a` 的 questions 路由边界。

## 下一轮验证清单

1. 网络恢复后先发布 P0-1，不夹带任何其他修改。
2. TypeScript 修复后执行 `npm run build`，再开本地前端进行 `/chat`、`/resources`、`/generate` 基础路由冒烟。
3. 用隔离 fake 环境验证新 session 无 subject、显式 subject、跨 session Profile、不同 learner 隔离和页面刷新。
4. 用 mock provider 证明资源类型预算公平；最多再做有限、无隐私的真实搜索冒烟，验证非伪造 URL 与 `search_unavailable`。
5. 以旧/新学习路径 fixture 和真实浏览器复验三种模式、导航、无 `0/0`/`0h` 误导。
6. 将 P6 跨实例与外部 Provider 结果保持为 PARTIAL，直到满足相应部署与 E2E 条件；不以静态代码或 mock 文案关闭。

## 本报告的剩余边界

本审计没有修改生产代码、没有执行真实 LLM/搜索/媒体 Provider、没有读取真实用户数据，也没有以当前环境重新完成全量 Edge E2E。已有候选验证文档中的 fake/隔离环境结论被当作历史证据，而不是当前真实服务验收。报告本身保留未提交，供产品和团队先审核优先级。
