# P4 多模态学习资源、质量审查与协同展示报告

## 实现范围

- 新增 `knowledge_map`、`process_flow`、`concept_diagram`、`execution_trace`、`code_trace` 五类小节级资源。
- 结构化资源通过现有 `MultimodalAgent` 调度到本地确定性模板，不新增模型 Provider、密钥或网络调用。
- 资源经 `ResourceQualityReviewer` 检查主题相关性、结构完整性、可渲染性、占位词、安全性和最小个性化信息；质量失败时最多一次本地重建。
- Mermaid 仅允许 flowchart、graph、sequenceDiagram、mindmap、stateDiagram-v2；拒绝脚本、事件属性、危险指令、未知图类型和超限图。
- 资源与反馈按 session、subject、section、resource type 隔离。生成入口在传入 subjectId 时复用既有会话-科目校验，避免刷新后读取到默认会话。
- ResourceModel 使用既有 metadata 字段保存质量、来源、个性化摘要和工作流记录；旧资源和旧数据库继续兼容。

## 多智能体协同记录

每个 P4 资源保存并可由接口读取以下真实步骤：ProfileAgent 读取最小画像上下文、ResourceAgent 创建任务、MultimodalAgent 使用本地模板生成、ResourceQualityReviewer 审查、ResourceModel 持久化。每一步仅包含 agent_name、capability、status、时间、provider、used_fallback 与安全摘要，不保存 prompt、密钥、完整画像或聊天记录。

## 浏览器验收

- 使用 Microsoft Edge 无头浏览器和 Playwright 控制真实本地网页。
- 新建隔离验收账户和数据结构科目后，受控生成“递归调用栈”的五类 P4 资源。
- 资源库刷新后恢复 5 条结构化资源，卡片显示中文资源类型与“质检通过”。
- 执行过程图详情正确显示 Mermaid、factorial(4)、栈深度、返回过程和 O(n)，未出现学习画像 JSON。
- 章节思维导图保存后资源库数量增至 6 条，详情使用 Mermaid 渲染，未显示原始对象。
- 发送“偏难”反馈后重新生成知识结构图，资源以稳定 ID 覆盖，正文新增初学者分步提示，没有创建重复资源。

截图只保存在系统临时目录：`%TEMP%/eduagent-p4/`，不纳入 Git。

## 验证结果

- `python -m compileall -q backend/app` 通过。
- `profile_v2_test.py`、`search_client_test.py`、`section_resource_recommendations_test.py`、`section_generated_resources_test.py`、`chapter_mindmap_resources_test.py`、`chat_section_resource_routing_test.py`、`section_resource_feedback_test.py`、`multimodal_resource_quality_test.py`、`section_lecture_test.py`、`section_tutor_test.py` 全部通过。
- `npm run build` 通过；仅保留既有动态导入与包体积警告。`frontend/tsconfig.tsbuildinfo` 已恢复且不提交。
- `git diff --check` 在提交前执行，LF/CRLF 提示不视为内容错误。

## 已知边界

- 新验收账户的普通聊天请求仍落入既有问候 fallback，未生成真实学习路径；这是本轮禁止修改的聊天主链路问题。遵循施工单，P4 使用受控小节资源接口建立确定性验收数据，并在真实资源库与详情页面完成渲染验收。
- 因没有可用的真实小节路径，讲义右栏的组合界面不能在该新账户中完成点击式验收；其请求、渲染和反馈逻辑由直接接口验证与前端构建覆盖，未伪造路径数据。
