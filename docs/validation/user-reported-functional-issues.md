# 用户报告功能问题关闭矩阵

> 2026-07-16 更新：以下矩阵已纳入 `7e6bdc9`、`c6dbc39`、`498d95c` 与 `00eccf4` 的隔离验证。所有新增提交仍为 **FIXED_LOCAL / BLOCKED_BY_NETWORK**：GitHub fetch 连接被重置，尚未推送；不应将其当作远端已发布状态。

验证对象为候选分支 integrate/maf-refactor-31613f2。所有浏览器验证均使用隔离 SQLite、假 Provider 和可见的 Edge 自动化；没有读取真实用户内容、凭据或调用外部 LLM／搜索服务。

状态含义：

- **CLOSED**：修复、自动回归和隔离 Edge 用户旅程均已覆盖。
- **PARTIAL**：用户可见的安全边界已验证，但真实外部 Provider、系统级运行时或多进程部署未在本轮调用／搭建。

| issue_id | 用户可见现象与原根因 | 修复 commit | 自动测试 | Edge E2E | 当前状态与剩余边界 |
|---|---|---|---|---|---|
| F01 | 新对话新建了逻辑用户；缺失稳定 learner 标识时后端会新建 learner。 | cfa0ad2, c6dbc39 | learner_session_profile_test.py, current_subject_scope_test.py | browser-smoke.test.mjs | **CLOSED**：新 session 复用匿名 learner，且不再携带历史 subject。 |
| F02 | 长期 explicit 画像只在原对话可见；读取未按 learner 聚合。 | cfa0ad2, c6dbc39 | learner_session_profile_test.py, profile_v2_test.py, current_subject_scope_test.py | browser-smoke.test.mjs | **CLOSED**：无主题 session 读取 learner-global explicit 事实，subject 局部事实不泄漏。 |
| F03 | 年级被过度泛化为大学生；explicit 原值未保留。 | cfa0ad2 | learner_session_profile_test.py | browser-smoke.test.mjs | **CLOSED** |
| F04 | 同主题重复建学科；无 canonical upsert。 | d8b1d24, c6dbc39 | subject_identity_test.py, current_subject_scope_test.py | browser-smoke.test.mjs | **CLOSED**：只有当前消息明确声明主题时才绑定／复用 subject。 |
| F05 | 尾随中文／英文标点创建重复学科。 | d8b1d24, c6dbc39 | subject_identity_test.py | browser-smoke.test.mjs | **CLOSED** |
| F06 | 多选生成类型在持久化或展示中退化为讲义。 | 9aa9dd1, a71f523 | general_resource_generation_test.py | general-resource-generation.test.mjs | **CLOSED** |
| F07 | 同资源生成出现重复条目；任务和资源没有共同去重边界。 | 9aa9dd1, a71f523, ec21157 | general_resource_generation_test.py | general-resource-generation.test.mjs | **CLOSED** |
| F08 | 删除后的资源会由内存 last_result 回填。 | 6a58272（回归覆盖） | general_resource_generation_test.py | 资源生成旅程刷新／删除回归 | **CLOSED** |
| F09 | 快捷模板只更新内存输入框。 | 8c32463 | 前端构建 | browser-smoke.test.mjs | **CLOSED** |
| F10 | 刷新后模板和类型选择丢失。 | 8c32463 | workflowTaskRecovery.test.ts | general-resource-generation.test.mjs | **CLOSED** |
| F11 | 资源库没有通用联网搜索入口。 | e9efe7e, 498d95c, 00eccf4 | general_resource_search_test.py, section_resource_recommendations_test.py, section_resource_search_cascade_test.py, search_client_test.py | online-resource-search.test.mjs | **PARTIAL**：通用入口、SSE、缓存与所有类型的预算覆盖已验证；真实 Provider 未调用。 |
| F12 | 顶部搜索只写入本地筛选参数。 | e9efe7e | general_resource_search_test.py | online-resource-search.test.mjs | **CLOSED** |
| F13 | 复合主题被压缩为首词。 | 027280e, e9efe7e, 498d95c | general_resource_search_test.py, section_resource_recommendations_test.py | online-resource-search.test.mjs | **CLOSED**：预算修复不改变 canonical query、缓存 key 或任务 key。 |
| F14 | 通用资源生成没有接入 P6。 | a71f523 | general_resource_generation_test.py, workflowTaskRecovery.test.ts | general-resource-generation.test.mjs | **CLOSED** |
| F15 | 静态“就绪／在线待命”被当作运行状态。 | 8ccd6bd | 前端构建 | browser-smoke.test.mjs | **CLOSED** |
| F16 | 刷新可能重新创建任务。 | 56f7b5e, 8c32463, e9efe7e | workflowTaskRecovery.test.ts | 通用生成与联网搜索刷新旅程 | **CLOSED** |
| F17 | 两标签页可能启动两个 runner。 | ec21157, a71f523, e9efe7e | workflow_progress_test.py | 通用生成、联网搜索双标签旅程 | **PARTIAL**：当前锁为单进程内存实现。 |
| F18 | 取消／重试状态边界不完整。 | a454be6, e9efe7e | workflow_progress_test.py, p5_hardening_test.py | online-resource-search.test.mjs | **CLOSED** |
| F19 | 缺少进度来源时误显示 0/0。 | ee823af | learningPathViewModel.test.ts | learning-path-compatibility.test.mjs | **CLOSED** |
| F20 | 缺少时长时误显示 0h。 | ee823af | learningPathViewModel.test.ts | learning-path-compatibility.test.mjs | **CLOSED** |
| F21 | 旧路径没有 stage.nodes 时无法显示／导航。 | ee823af | learningPathViewModel.test.ts | learning-path-compatibility.test.mjs | **CLOSED** |
| F22 | 教材、日课、项目模式路由串线。 | 215f310 | learningPathViewModel.test.ts | learning-path-compatibility.test.mjs | **CLOSED** |
| F23 | 长 objective／description 全量铺开。 | eeb3032 | learningPathViewModel.test.ts | learning-path-compatibility.test.mjs | **CLOSED** |
| F24 | PPT Python 依赖未声明。 | f58efee | ppt_generator_test.py | 不适用（依赖声明） | **CLOSED** |
| F25 | PPT 下载、刷新、删除链路不完整。 | abfb43e, f58efee | ppt_generator_test.py, 资源回归 | 通用资源生成旅程（非 PPT 专项） | **PARTIAL**：本地 PPT 文件生成和通用资源生命周期已覆盖；尚无 PPT 专项 Edge 下载/刷新/删除旅程，且真实内容 Provider 未调用。 |
| F26 | Manim 未安装时只有泛化失败或伪造成功风险。 | f58efee, e9efe7e, 6a58272 | general_resource_generation_test.py, workflowTaskRecovery.test.ts | manim-unavailable.test.mjs | **PARTIAL**：安全提示已验证；未安装系统级 Manim 栈，不宣称渲染成功。 |
| F27 | session A 可能删除 session B 资源。 | abfb43e, 6a58272（回归覆盖） | general_resource_generation_test.py | 资源删除旅程 | **CLOSED** |
| F28 | 缺失 backend/.env 时无法导入／启动。 | c3e5897 | config_env_file_test.py | 所有隔离 Edge 服务 | **CLOSED** |
| F29 | 运行时数据和生成产物被 Git 追踪；非 ASCII 路径绕过卫生测试。 | aef349e, e746bbd | repository_hygiene_test.py | 不适用（仓库卫生） | **CLOSED** |
| F30 | 普通聊天重复新会话欢迎语。 | 5c262f8 | chat_fallback_test.py | browser-smoke.test.mjs | **CLOSED** |
| F31 | 无上下文确认词可能错误触发路径；有明确提议时又可能被短消息分支吞掉。 | fd390c3 | deeptutor_client_test.py | 普通聊天隔离旅程 | **CLOSED** |
| F32 | “不生成路径”被当成学习“路径”主题。 | 5843dad | chat_fallback_test.py | 普通聊天隔离旅程 | **CLOSED** |
| F33 | Profile 注入会被固定回复模板覆盖。 | 5ffab9e, cfa0ad2 | chat_fallback_test.py, profile_v2_test.py | browser-smoke.test.mjs | **CLOSED** |
| F34 | Provider TLS／超时／fallback 需保持有界和当前消息相关。 | 4cda6ee, 3498f2a | deeptutor_client_test.py, chat_fallback_test.py | 假 Provider 普通聊天旅程 | **PARTIAL**：按要求未真实调用外部 Provider。 |
| F35 | 视频学习偏好未进入资源偏好映射。 | cfa0ad2 | learner_session_profile_test.py, profile_v2_test.py | browser-smoke.test.mjs | **CLOSED** |

## 隔离验证摘要

- 身份／画像：同 learner 的新会话读到长期 explicit 事实；另一浏览器身份隔离。
- 普通聊天：欢迎、当前输入、复合主题、拒绝路径、显式生成边界和无上下文确认词均有回归。
- 资源：lecture、mindmap、quiz 类型独立生成、刷新恢复、去重、删除；PPT 本地非空生成与媒体入口均回归。
- 联网搜索：资源库明确区分本地筛选和联网模式；完整主题、SSE、刷新、取消、重试、缓存、保存和双标签复用均通过隔离 Edge。
- 学习路径：旧／新结构、三模式、时长和进度缺失状态、导航、返回和刷新均通过隔离 Edge。

本轮关闭计数：**30 CLOSED，5 PARTIAL，0 OPEN**。PARTIAL 项只受真实外部 Provider、Manim 系统依赖或多进程锁范围限制；没有遗留可在当前隔离环境中继续修复的 OPEN 项。
