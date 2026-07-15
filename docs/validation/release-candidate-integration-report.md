# EduAgent 发布候选整合审计

审计日期：2026-07-15
审计基线：`integrate/maf-refactor-31613f2` at `3b4feb7`（本报告与测试稳定化修改将在后续候选提交中一并纳入）。

## 结论

候选线适合以 **PR、人工处理冲突、禁止自动合并** 的方式交给团队审阅；不适合直接 `git pull` 或把候选线直接推到 `origin/MAF-Refactor`。

- 候选远端跟踪在审计开始时为 `0 ahead / 0 behind`。
- 正式远端为 `4a4233e`，共同祖先为 `a454be6`；正式远端独有 9 个提交，候选独有 28 个提交。
- 候选当前树没有运行时数据库、用户数据、搜索缓存、日志、生成的 PPT/视频或 `outputs/` 文件；只有目录占位 `backend/data/.gitkeep`。
- 正式远端当前树仍有 72 个 `backend/data/` 路径、4 个 `outputs/` 路径和 6 个运行时扩展名路径。因此合线前必须在 PR 的合并结果上再次做路径卫生检查。

## 正式远端逐提交审计

| 提交 | 实际代码范围与判断 | 运行时路径 | 与候选关系 / 建议 |
|---|---|---|---|
| `2986748` | 修改 Conversation、Planner、Orchestrator、产品路由并加入 PPT/Manim。包含 LLM 标记解析和计划天数重算。 | 有聊天 trace、偏好和搜索结果路径。 | 与候选的独立 PPT/Manim、聊天边界、路径显示适配重叠；不能整提交吸收。仅在独立代码评审后手工挑选。 |
| `31613f2` | 合并提交；相对第一父提交主要引入已在共同祖先一侧的 P5/workflow 基础。 | 无独立运行时内容判断；其父历史含运行时路径。 | 不能作为 cherry-pick 对象；候选已有 P5/P6 回归覆盖。 |
| `e177283` | 增加评估状态持久化和自动重规划触发，修改聊天和工作流授权。 | 有 trace、搜索结果、Manim 音视频/中间产物路径。 | 不吸收：工作流路由把跨 learner 不匹配由拒绝改为放行，和候选的隔离边界冲突。 |
| `447b787` | 扩展多智能体注册与 LLM assessment 适配器，涉及 Orchestrator、Profile、ResourceAgent。 | 无直接运行时路径。 | 高耦合且无候选等价回归；不直接吸收，需团队单独评审。 |
| `0a39863` | 新增同 learner + 同 subject 的跨 session 查询。 | 删除 trace，同时添加生成媒体路径。 | 候选已实现 learner 全局 explicit 与 subject 局部画像的明确优先级；该实现范围不同，不能直接叠加。 |
| `043d3f4` | 修改教材解析、教材模式和 Planner。 | 无直接运行时路径。 | 候选以 ViewModel 兼容旧/新路径，不改 Planner 语义；该提交需单独手工比较，不随本 PR 合入。 |
| `2db372c` | 合并 `447b787` 与 `0a39863`。 | 继承其运行时媒体路径。 | 不可单独吸收。 |
| `de988af` | Planner 从章节结构派生任务和时长。 | 无直接运行时路径。 | 改变 Planner 语义，超出候选发布范围；保留为团队后续专题。 |
| `4a4233e` | 合并 `043d3f4`。 | 无独立运行时内容判断。 | 不可单独吸收；需要在 PR 冲突解决中重新验证教材路径。 |

远端提交中还存在历史运行时路径。候选提交 `aef349e` 与 `e746bbd` 只清理了候选树和忽略规则，**不会重写 Git 历史**；历史净化、任何必要的访问令牌轮换以及正式远端现存运行时文件的移除，应由仓库管理员在单独的安全流程中完成。

## Planner、评估与 Agent 调度审计

- 候选路径兼容层位于前端 ViewModel；没有改写 Planner 的生成触发边界或重新计算计划。
- 远端 `2986748`、`043d3f4`、`de988af` 均触及 Planner；不纳入本候选 PR。
- 远端 `e177283` 触及评估闭环，并放宽跨 learner workflow 授权；该安全回退是明确阻断项。
- 远端 `447b787` 变更多智能体注册和 Orchestrator；候选不覆盖其代码，当前候选的动态协同、Provider 路由和 workflow 选择保持既有回归范围。

## 用户问题关闭矩阵复核

权威矩阵见 `docs/validation/user-reported-functional-issues.md`。提交和测试文件均仍可定位。

- **30 CLOSED：** F01–F10、F12–F16、F18–F24、F27–F33、F35。
- **5 PARTIAL：** F11、F17、F25、F26、F34。
- **0 OPEN：** 当前隔离环境内没有可继续修复但未修复的用户报告项。

五项 PARTIAL 保持为部分完成，未被错误标为 CLOSED：

| 项目 | 已验证边界 | 未验证 / 不应宣称的能力 |
|---|---|---|
| F11 通用联网搜索 | 通用入口、P6 状态、取消/重试/刷新、缓存、保存和去重均由 fake Provider 的 Edge 旅程验证。 | 未调用真实外部搜索 Provider。 |
| F17 跨标签重复 runner | 单进程双标签复用同一运行中任务已在 Edge 和 workflow 测试中验证。 | 锁为进程内内存锁；多进程/多实例部署需要共享锁或数据库约束。 |
| F25 PPT 生命周期 | 本地 fake LLM 生成非空 PPTX 已自动验证；通用资源的刷新和删除边界已由 Edge 验证。 | 尚无 PPT 专项的 Edge 下载/刷新/删除旅程，且未调用真实内容 Provider。 |
| F26 Manim | 未安装时返回明确 `provider_not_configured`，页面不伪造成功资源。 | 未安装并验证 Manim、FFmpeg、LaTeX 的真实渲染链。 |
| F34 Provider 网络边界 | mock Provider 覆盖 TLS/超时后的有界、当前消息相关 fallback。 | 本轮没有真实外部 LLM 冒烟。 |

## 自动化与 Edge 验收

全部验证均使用临时 SQLite、`LLM_PROVIDER=mock`、禁用 `.env` 自动加载和 fake Provider；未读取凭据、未调用外部 LLM、搜索、图像或视频服务。

| 命令 / 范围 | 结果 |
|---|---|
| `python -m compileall -q backend/app` | 通过。 |
| 自动发现的 `backend/tests/*_test.py`（22 个可执行脚本） | 22/22 通过：聊天、Profile V2、learner/session、subject、资源生成/搜索/反馈、PPT、P5、workflow、教材小节和仓库卫生。 |
| `node frontend/tests/workflowTaskRecovery.test.ts` | 通过。 |
| `node frontend/tests/learningPathViewModel.test.ts` | 通过。 |
| `npm run test:e2e` | 5/5 通过；脚本已改为串行，避免独立测试争用 8010/5175。 |
| 三轮连续 `npm run test:e2e` | 3/3 通过。每轮覆盖登录/隔离 learner、通用生成与恢复、旧路径与三模式、Manim 未配置、通用联网搜索与双标签复用。 |
| `npm run build` | 通过；仅有既有的 chunk 大小和动态导入提示。 |
| 定向 ESLint（本轮两个 E2E 文件） | 通过。 |
| 全仓 `npm run lint` | 未通过；错误分布在大量既有、未触及的前端文件。该基线债务不被本次候选修改掩盖，需单独治理。 |

E2E 不再用固定完成时长判断成功：资源/搜索任务、CDP 请求、目标页面和资源计数均等待可观察状态；保留的短等待仅用于带超时的轮询和子进程退出。每轮结束后 8010、5175 和 Edge 调试端口均确认释放。

## 配置、数据和部署边界

- `backend/.env` 缺失不再阻止配置导入或隔离服务启动；生产环境仍应通过受管环境变量提供实际 Provider 配置。
- PPT 的 `python-pptx` 已在 `backend/requirements.txt` 声明并本地生成测试覆盖。
- Manim 是可选系统能力；未配置时必须保持安全不可用提示，不能作为发布前的成功渲染证据。
- 数据库启动路径使用现有的 `create_all` 和兼容迁移逻辑；本审计没有连接或迁移真实用户数据库。上线前应先备份、在副本上 dry-run，并按正式运维流程执行。
- 旧 subject 整理与 learner/session 升级已有兼容测试；不得把未知旧 session 批量归入同一 learner。

## 发布与合线建议

1. 推送本候选分支的审计提交后，创建以 `MAF-Refactor` 为 base、`integrate/maf-refactor-31613f2` 为 head 的 PR；不要自动合并。
2. PR 合并前由团队逐文件处理正式远端的 Planner、评估闭环和多智能体改动；保留候选的 learner 隔离、P6 恢复/锁、路径 ViewModel、资源类型与搜索边界。
3. 在最终合并结果上重新运行本报告的后端套件、三轮 Edge E2E、构建和仓库路径卫生扫描。
4. 合并结果必须不包含 `backend/data` 运行时内容、`outputs/`、数据库、日志、缓存、截图、媒体或凭据；现有历史数据净化另开管理员安全任务。
5. F17 的多实例全局锁、F11/F34 的真实 Provider 冒烟、F25 的真实 PPT 内容 Provider 以及 F26 的 Manim 系统栈仍是独立上线环境验证项，不是本候选可宣称已完成的能力。
