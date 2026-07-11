# EduAgent 讲义智能资源工作区 P1-P3

## 目标

在讲义页右侧形成三个互不混淆的能力：真实外部资源推荐、可保存的小节学习资源、可保存的章节思维导图。保留既有智能辅导、视频、知识点和测验。

## 边界

- 外部推荐必须使用真实 DuckDuckGo 检索，不展示 mock 或固定链接，不写资源库。
- 系统生成的小节资源和章节思维导图使用现有 `ResourceModel` 归档，并绑定现有 stage/chapter/section 字段。
- 不修改 Planner、Conversation、Profile、Diagnosis、Review、LangGraph、学习路径结构、数据库模型或迁移。
- 不重构 ResourceAgent；只复用其已有资源类型和安全生成模式。
- 不接入 MindSearch、SearXNG、RAGFlow、STORM 或其他大型系统。

## 接口与数据规则

- `POST /api/sections/{section_id}/resources/recommendations`：返回真实外部链接，状态为 `completed`、`search_unavailable` 或 `failed`。
- `POST /api/sections/{section_id}/resources/generate`：生成并保存 `summary_card`、`concept_comparison`、`worked_example`、`mistake_checklist`、`review_notes`。
- `GET /api/sections/{section_id}/generated-resources`：读取当前小节归档资源。
- `POST /api/chapters/{chapter_id}/mindmap/generate`、`GET /api/chapters/{chapter_id}/mindmap`：生成、读取并绑定章节 Mermaid 思维导图。
- 外部链接只允许 http/https；不得下载、写数据库或伪造来源。
- 生成资源不得回显画像 JSON 或 prompt；无效 LLM 输出必须使用与资源类型相关的确定性 fallback。
- 每个章节只保留一个当前有效思维导图；重新生成覆盖该资源。

## 实施阶段

1. P1：复用 DuckDuckGo 客户端实现查询拆分、过滤、去重、类型推断、排序与推荐理由。
2. P2：生成五类小节资源，使用现有 `ResourceModel` 保存和读取。
3. P3：生成 Mermaid 章节思维导图并绑定现有 `related_chapter_id`。
4. P4：在既有 LecturePage 右栏的“相关资源”页签中接入推荐、资源生成、思维导图和章节统计。

## 测试要求

- 推荐：URL/标题去重、排序、类型、真实结构、不可用状态、无数据库写入。
- 生成资源：五种类型、无效 LLM fallback、section 绑定、幂等、重新生成、读取。
- 思维导图：Mermaid、chapter 绑定、幂等、重新生成、失败不落空资源。
- 回归：section lecture、section tutor、后端 compileall、前端 build、diff check。

## Git 规则

- 从 `MAF-Refactor` 创建 `feature/lecture-intelligent-resources`。
- 允许最多四个本地 commit，按 P1、P2、P3、P4 划分。
- 只能明确路径暂存；不提交数据库、workspace 数据、搜索日志、缓存、密钥、虚拟环境、`tsconfig.tsbuildinfo` 或旧施工单。
- 不 push、不合并、不 rebase、不 reset、不 stash、不 clean。

## 阻塞规则

- 外网、DuckDuckGo 限流或依赖缺失不阻塞 P2/P3；对外返回友好 `search_unavailable`。
- 若必须修改数据库模型、Planner、LangGraph 或学习路径结构，停止该项并记录。
- 同一问题最多四次合理修复；仍失败则撤销最后一次无效改动并继续独立阶段。
