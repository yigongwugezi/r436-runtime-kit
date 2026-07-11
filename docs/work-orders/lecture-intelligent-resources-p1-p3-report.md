# EduAgent 讲义智能资源工作区 P1-P3 执行报告

## 施工开始

- 基础分支：`MAF-Refactor`
- 开始 HEAD：`dd8368f`
- 开始状态：与 `origin/MAF-Refactor` 对齐；保留未跟踪旧施工单 `docs/work-orders/intelligent-learning-workspace-p1.md`。
- 预期分支：`feature/lecture-intelligent-resources`

## 现状确认

- LecturePage 的“相关资源”仅展示思维导图入口、讲义状态和章节统计，未调用外部搜索。
- `DuckDuckGoSearchClient.search(query, max_results=5)` 已存在，但当前没有被 router 或 Agent 调用；默认配置为 mock。
- ResourceModel 可复用 title、description、content、type、source、related_stage_id、related_chapter_id、related_section_id、knowledge_points、format 等字段；外部结果不入库。
- 现有资源类型包含 lecture、mindmap、quiz、reading、practice、multimodal 等；本轮小节派生资源使用 reading/practice 兼容类型和明确标签。
- 现有章节思维导图通过 mindmap Resource 与 `chapter.mindmapId` 展示；本轮复用 Mermaid 渲染和资源详情页。
- LecturePage 可提供 session、path、stage、chapter、section、标题、目标、知识点和讲义内容；profile/weak points 由后端按 session 读取。

## 预计文件

- 后端：section recommendation、generated resources、chapter mindmap service 和 product router。
- 前端：section resource types/API/components，以及 LecturePage 相关资源页签。
- 测试：三类后端直接测试。

## 预计提交

1. `feat: add section resource recommendations`
2. `feat: add generated section learning resources`
3. `feat: add chapter mindmap resource workflow`
4. `feat: integrate lecture resource workspace`

## 阶段记录

### P1 外部资源推荐

- 新增 `SectionResourceRecommendationService` 和 section recommendation 接口。
- 运行时显式使用 `get_search_client("duckduckgo")`，不读取默认 mock provider。
- 查询分为教程/讲解、官方文档/大学课程，并可按请求类型追加视频、公开课、论文或文档查询。
- 只保留 http/https 链接，清理 UTM 参数，按 URL 与标题去重；输出来源域名、类型、轻量可信度、匹配理由和排序分数。
- 外部检索不写 `ResourceModel`、不下载网页、不写 workspace 数据。网络或限流时返回 `search_unavailable` 和中文 warning。
- 项目没有预建虚拟环境；已创建未跟踪 `backend/.venv`，仅安装 requirements 中声明的 DuckDuckGo 和后端启动所需轻量依赖。真实 DuckDuckGo 查询被服务端 202 限流，服务和 API 冒烟均验证为安全返回 `search_unavailable`，未回退 mock。

### P2 小节生成资源

- 新增五类：总结卡片、概念对比、例题详解、易错清单、复习笔记。
- 使用已有 `ResourceModel`、`upsert_resource` 和关联字段保存；不迁移数据库。
- 用稳定 `section_{section_id}_{resource_type}` ID 实现默认复用和重新生成覆盖。
- Mock/画像 JSON/短输出会按资源类型回退为与当前小节、知识点和讲义片段相关的确定性 Markdown。
- 实际 API 冒烟已生成 summary_card，读取接口可返回同一 section 记录。

### P3 章节思维导图

- 复用已有本地 `MindMapTool` 生成 Mermaid，不依赖星火图片 Provider。
- 使用稳定 `chapter_{chapter_id}_mindmap` ID、`type=mindmap`、`related_chapter_id` 保存；重新生成覆盖当前导图。
- 当工具无结果时按章节、小节和知识点生成本地 Mermaid fallback；不写空资源。
- 实际 API 冒烟已生成并重新读取 chapter mindmap。

### P4 讲义右栏

- 在既有“相关资源”页签内接入单个 `SectionResourceWorkspace`，未创建第二套右栏。
- 外部资源需要用户点击才搜索；生成资源需要用户点击才写资源库；思维导图需要用户点击才生成。
- 提供加载、失败提示、重试、外链安全属性、生成预览、资源库跳转、已有导图回退和章节统计。
- 智能辅导、视频、讲义正文、知识点和测验未改动。

## 验证记录

- `python -m compileall -q backend/app`：通过。
- 三个新增直接测试、`section_lecture_test.py`、`section_tutor_test.py`：通过。
- `npm run build`：通过，仅保留既有大 chunk 提示。
- `git diff --check`：通过，只有 CRLF 提示。
- API smoke：P1 安全不可用、P2 持久化读取、P3 持久化读取均通过。
