# EduAgent 演示 PPT 生成提示词（详细版）

---

## 角色设定

你是一位资深 AI 教育产品架构师，需要为 **EduAgent（r436-runtime-kit）—— AI 原生自适应学习平台** 制作一份对外演示 PPT。受众为教育科技领域专家、投资人、高校合作方和竞赛评委。

---

## 一、总体要求

### 1.1 基本规格
- **页数**：20-25 页
- **风格**：专业科技感 + 教育温度，以架构图/流程图/对比表/数据图表为主，避免大段纯文字
- **配色建议**：深蓝（#1a365d / #2b6cb0）为主色 + 暖橙（#ed8936）为点缀 + 白色背景
- **字体**：标题 28-36pt，正文 ≥18pt，代码/技术术语用等宽字体
- **逻辑线**：
  ```
  封面 → 行业背景与痛点 → 产品定位 → 核心功能全景 → 技术架构总览
  → 前沿AI技术融合（3-4页）→ 核心创新点详述（4-5页）→ 功能演示页（3-4页）
  → 扩展能力 → 可靠性保障 → 价值量化对比 → 总结与展望
  ```

### 1.2 全局设计约束
1. **每页标题**用陈述句结论（如"三级自适应诊断：从 15 题快速定位到掌握度矩阵"），禁用泛泛的"功能介绍"
2. **技术名保留英文原文**（LangGraph、FAISS、text2vec-large-chinese、DeepSeek、SSE、RAG、Ebbinghaus 等），其余正文用中文
3. **关键数字必须展示**：10 个 Agent、7 维画像、6 类资源、12 种多模态任务、23 个前端页面、20+ 路由模块、5 种 LLM 提供商、4 级降级、3 种学习模式、[1,2,4,7,15,30] 天记忆间隔
4. **架构图/流程图**在技术页面必须出现，建议用 Mermaid 或手绘风格框图
5. **多用对比**强化认知：传统方案 vs EduAgent、无闭环 vs 有闭环

---

## 二、逐页内容指引

---

### 第 1 页 · 封面

**标题**：EduAgent — 基于多智能体协同的 AI 原生自适应学习平台

**副标题**：从"千人一面"到"一人一策"——让每一位学习者拥有专属 AI 导师

**底部信息**：
- 项目代号：r436-runtime-kit
- 团队/机构名称
- 日期

**设计**：纯色深蓝背景 + 中央白色标题，底部放一个抽象的神经网络/知识图谱装饰图

---

### 第 2 页 · 行业背景与核心痛点

**标题**：传统在线教育的四大困局

**内容**：左侧痛点，右侧数据支撑

| # | 痛点 | 现状 | EduAgent 解法 |
|---|------|------|---------------|
| 1 | **内容千人一面** | 所有学生看同一套课程，无法适配个体差异 | 基于 7 维画像的个性化学习路径 |
| 2 | **诊断缺失** | 学生"不知道自己哪里不会"，缺乏精准定位 | 三级自适应诊断 + 掌握度矩阵 |
| 3 | **资源形式单一** | 仅有视频+文档，缺乏互动与多模态 | 6 类资源自动生成（讲稿/脑图/测验/阅读/练习/多模态） |
| 4 | **缺乏闭环反馈** | 学完即结束，无动态调优、无遗忘管理 | 事件驱动 + 周期复诊 + 艾宾浩斯调度 |

**关键语句**：大模型 + 多智能体技术的成熟，使得"因材施教"从理念走向工程落地成为可能。

---

### 第 3 页 · 产品定位与价值主张

**标题**：EduAgent = AI-Native 自适应学习引擎

**核心定位**（一句醒目展示）：
> 以自然语言对话为入口，构建「诊断 → 规划 → 生成 → 评估 → 迭代」全流程闭环的个性化学习系统

**三大价值主张**（三列卡片）：

| 🎯 精准 | 🧠 智能 | 🎨 丰富 |
|---------|---------|---------|
| 7 维学习者画像 | 10 个协同 Agent | 6 类学习资源 |
| 间接探测（绝不直接问） | LangGraph 编排 | 多模态生成 |
| 三级自适应诊断 | 全流程无人工干预 | 个性化适配 |
| 知识点级精确定位 | 质量审核+自动重试 | 交互式内容 |

---

### 第 4 页 · 核心功能全景图

**标题**：六大核心模块，覆盖学习全生命周期

**一张全景功能图**，以学习者为中心辐射六大模块：

```
                        ┌──────────────────┐
                        │   智能对话入口     │
                        │  (自然语言+流式)   │
                        └────────┬─────────┘
                                 │
        ┌────────────┬───────────┼───────────┬──────────┬────────────┐
        ▼            ▼           ▼           ▼          ▼            ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │学习者画像│ │知识诊断 │ │学习规划 │ │资源工厂 │ │学习执行 │ │闭环评估 │
   │         │ │         │ │         │ │         │ │         │ │         │
   │7维探测  │ │快速定位 │ │教材式   │ │讲稿/脑图│ │每日任务 │ │事件驱动 │
   │间接推断 │ │精细诊断 │ │每日一课 │ │测验/阅读│ │专注冲刺 │ │周期复诊 │
   │动态更新 │ │掌握矩阵 │ │冲刺特训 │ │练习/多模│ │练习中心 │ │遗忘曲线 │
   │         │ │         │ │         │ │态       │ │复习队列 │ │推荐引擎 │
   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
```

每个模块下方标注 2-3 个关键特性

---

### 第 5 页 · 技术架构总览（重点页）

**标题**：三层架构 + 多智能体协同引擎

**完整架构图**：

```
┌──────────────────────────────────────────────────────────────────┐
│                     前端展示层 (React 19 + TypeScript + Vite)      │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌────────┐ │
│  │ 学习中心 │ │ 对话页面 │ │ 知识图谱  │ │ 资源库   │ │ 管理端 │ │
│  │ (Home)  │ │ (Chat)   │ │ (AntV G6) │ │(23页)    │ │(Admin) │ │
│  └──────────┘ └──────────┘ └───────────┘ └──────────┘ └────────┘ │
│  状态管理: Zustand │ 可视化: ECharts/Mermaid/markmap/KaTeX       │
│  路由: React Router │ 样式: Tailwind CSS │ 图标: lucide-react     │
├──────────────────────────────────────────────────────────────────┤
│                     网关层 (FastAPI + Uvicorn)                     │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────────────┐ │
│  │ 20+ 路由 │ │ SSE 流式 │ │ JWT 认证  │ │ 中间件: Request-ID   │ │
│  │ 模块     │ │ 传输     │ │ 角色鉴权  │ │ CORS / 用户凭证绑定  │ │
│  └──────────┘ └──────────┘ └───────────┘ └──────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                    智能体层 (10 Agent + LangGraph 编排)            │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │              ConversationAgent (外层调度中枢)                  │ │
│  │   意图分类 → 动态人设 → 间接探测 → 事实抽取 → 子Agent调度    │ │
│  └──────────────────────────┬───────────────────────────────────┘ │
│                             │                                      │
│  ┌─────────────┐ ┌──────────┴──────┐ ┌─────────────┐              │
│  │ProfileAgent │ │LangGraphOrchestrator│ │KnowledgeAgent│           │
│  │7维画像构建  │ │  状态图工作流     │ │RAG语义检索  │              │
│  └──────┬──────┘ └────────┬─────────┘ └──────┬──────┘              │
│         │                 │                  │                      │
│  ┌──────┴──────┐  ┌───────┴───────┐  ┌──────┴──────┐              │
│  │DiagnosisAgent│  │ PlannerAgent  │  │ResourceAgent│              │
│  │三级自适应   │  │ 3模式+4级降级│  │ 6类资源生成│              │
│  └──────┬──────┘  └───────┬───────┘  └──────┬──────┘              │
│         │                 │                  │                      │
│  ┌──────┴──────┐  ┌───────┴───────┐  ┌──────┴──────┐              │
│  │QuestionAgent│  │ GradingAgent  │  │ ReviewAgent │              │
│  │5类题目+变式│  │ 5类错误分类  │  │ 7维质量审核│              │
│  └─────────────┘  └───────────────┘  └──────┬──────┘              │
│                                              │                      │
│                                    ┌─────────┴─────────┐           │
│                                    │MultimodalAgent    │           │
│                                    │12类多模态任务路由 │           │
│                                    └───────────────────┘           │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  基础设施层                                                    │ │
│  │  ┌──────┐ ┌──────┐ ┌───────┐ ┌──────┐ ┌───────┐ ┌─────────┐ │ │
│  │  │RAG   │ │LLM   │ │Search │ │Safety│ │State  │ │Assessment│ │ │
│  │  │FAISS │ │工厂  │ │多源搜索│ │内容  │ │会话状态│ │Loop     │ │ │
│  │  │+Llama│ │5提供商│ │+熔断  │ │安全  │ │持久化  │ │闭环调度 │ │ │
│  │  │Index │ │      │ │       │ │      │ │       │ │         │ │ │
│  │  └──────┘ └──────┘ └───────┘ └──────┘ └───────┘ └─────────┘ │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

**说明**：标注每层的核心组件数量（23 页面 / 20+ 路由 / 10 Agent / 5 LLM / 等等），突出"全栈自研"

---

### 第 6 页 · 前沿 AI 技术融合（一）：多智能体协同编排

**标题**：LangGraph 状态图编排 —— 10 个 Agent 的指挥中枢

**内容要点**：

1. **LangGraph StateGraph 引擎**
   - 11 个节点（intent_router → 9 个 agent 节点 + reply / END 节点）
   - 条件路由：根据意图分类结果动态决策执行路径
   - 并行执行：同一流水线中多个 Agent 可并行执行
   - 重试机制：ReviewAgent 审查不通过 → 自动退回 ResourceAgent 重试（最多 2 次）

2. **意图路由注册表**（IntentRouter — 14 种意图 → Agent 计划映射）：
   ```
   "chat"      → 仅对话（DeepTutor）
   "profile"   → ProfileAgent 单独执行
   "diagnose"  → DiagnosisAgent 单独执行
   "plan"      → ProfileAgent + PlannerAgent
   "tutor"     → ProfileAgent + DiagnosisAgent + ResourceAgent + MultimodalAgent
   "full_workflow" → 全流水线: Profile → Knowledge → Diagnosis → Planner → Resource → Review
   "assess"    → GradingAgent + DiagnosisAgent + ProfileAgent + PlannerAgent + ResourceAgent
   ```

3. **ConversationAgent V4 外层调度**
   - 每次对话先经由 ConversationAgent 进行意图分类（XML 标签 `<execute>` / `<proposal>`）
   - 轻量级 Semantic Router 模式：毫秒级意图识别
   - 动态人设构建：基于画像完善程度（4 阶段），自动调整对话策略

**图示**：用 Mermaid 流程图展示 LangGraph 节点和边的关系

---

### 第 7 页 · 前沿 AI 技术融合（二）：RAG 知识增强 + 多模型工厂

**标题**：知识检索增强 + 多模型可插拔架构

**上半部分 — RAG 知识增强系统**：

| 环节 | 技术 | 说明 |
|------|------|------|
| 数据底座 | 中文维基百科 | 离线预处理，向量化后存入 FAISS 索引 |
| 文档切分 | LlamaIndex SentenceSplitter | chunk_size=512, overlap=50，中文友好分隔符 |
| 向量化 | HuggingFace text2vec-large-chinese | 1024 维向量，CPU 友好 |
| 向量存储 | FAISS IndexFlatIP | Inner Product（等价余弦相似度），单文件流式组装，内存峰值可控 |
| 查询增强 | LLM 查询扩展 | 短查询（<80字符）自动扩展为 2-3 个精准关键词 |
| 降级策略 | 课程目录回退 | RAG 无结果 → 回退到 course_catalog 结构化课程数据 |

**下半部分 — 多模型工厂（LLM Factory）**：

| 提供商 | 模型 | 用途 |
|--------|------|------|
| **DeepSeek** | deepseek-chat / deepseek-reasoner | **默认主模型** — 对话、诊断、规划、资源生成 |
| **阿里 Qwen** | qwen-plus / qwen-max / qwen-coder / qwen-vl | 多模态理解、编程、视觉问答 |
| **智谱 GLM** | glm-4 | 备用对话与生成 |
| **OpenAI** | gpt-4o | 备用对话与推理 |
| **讯飞星火** | Spark | 图像生成、语音识别 |

**关键设计**：
- **每用户独立配置**：API Key 存在 `user_ai_config` 表，用户间隔离，前端「系统设置」页面自助配置
- **运行时切换 + 优雅降级**：用户未配置 → 返回 `AI_CONFIG_MISSING` 友好提示，不产出模拟内容
- **Mock 逃生舱**：测试环境下可用 Mock Provider 快速验证流程

---

### 第 8 页 · 前沿 AI 技术融合（三）：多模态生成 + 外部智能体集成

**标题**：12 类多模态任务路由 + DeepTutor 终身学习引擎

**上半部分 — 多模态任务路由（MultimodalAgent）**：

| 任务类型 | 路由目标 | 说明 |
|----------|---------|------|
| 图片理解 / OCR / VQA | Qwen Vision（通义千问视觉） | 上传题目截图 → AI 识别并解答 |
| 图片生成 | 讯飞星火 / Seedream / ARK | 学习插图、概念可视化 |
| 视频生成 | Wan Video | 知识点讲解视频 |
| 代码可视化视频 | code2video (Manim) | 算法执行过程动画 |
| PPT 生成 | 讯飞智文 AIPPT | 学习讲义自动转 PPT |
| 思维导图 | Markmap / LLM 生成 | 知识结构可视化 |
| 错题分析 | Qwen Vision + LLM | 拍照上传 → 识别 → 诊断 → 变式题生成 |
| 闪卡生成 | LLM 结构化生成 | 记忆卡片（正面/背面/提示） |
| 概念对比图 | LLM + 结构化模板 | 易混淆概念对比表 |
| 知识地图 | LLM + markmap | 章节知识点关系图 |
| 执行追踪 | LLM + code2video | 代码逐步执行演示 |
| 学习计划可视化 | LLM + Mermaid | 甘特图/流程图展示学习路径 |

**下半部分 — DeepTutor 集成**：

- 对接香港大学 **DeepTutor v1.5.0** — 终身个性化辅导系统
- 作为**主对话引擎**（`deeptutor_facade.py`），提供：
  - 聊天对话（带长期记忆上下文）
  - deep_solve（逐步解题，展示完整推理过程）
  - 知识检索
  - 学习进度追踪（`dt_bridge.py` — 构建学习进度、获取下一步建议、到期复习提醒）
- 优雅降级：DeepTutor 不可用 → 回退到 DeepSeek 直连

---

### 第 9 页 · 创新点一：间接探测式 7 维学习者画像

**标题**：不直接问"你哪里不会"——基于行为证据链的精准画像

**核心创新**：所有结论由行为证据推断，**绝不直接询问学生的薄弱点**

**7 个画像维度**：

| 维度 | 探测方式 | 证据标签 |
|------|---------|----------|
| 1. 学科背景 (major_background) | 概念解释任务 → 推断知识深度 | `[探测]` |
| 2. 学习历史 (learning_history) | 自述式对话引导 → 提取学习经历 | `[学生自述]` |
| 3. 知识基础 (knowledge_base) | 诊断性测验 → 间接推断掌握情况 | `[探测]` |
| 4. 学习目标 (learning_goal) | 目标探查对话 → 提取目标描述 | `[学生自述]` / `[探测]` |
| 5. 认知风格 (cognitive_style) | 偏好选择题 → 推断学习风格 | `[探测]` |
| 6. 错误模式 (error_patterns) | 练习结果分析 → 分类错误类型 | `[行为观察]` |
| 7. 学习节奏 (learning_rhythm) | 时间现实检验 → 观察学习行为数据 | `[行为观察]` |

**6 种探测策略**：诊断测验 · 概念解释 · 偏好选择 · 情境测试 · 目标探查 · 时间现实检验

**动态更新机制**：
- 每次对话后自动运行 `_extract_facts_after_chat()`
- 从学生回复 AND AI 回复中双向提取新事实
- Rich Facts 系统：以知识点为粒度维护话题级画像
- 画像深度分 4 阶段 → 驱动动态对话人设（越了解学生，对话策略越精准）

---

### 第 10 页 · 创新点二：三级自适应诊断 + 艾宾浩斯遗忘调度

**标题**：从 15 题快速定位到精准掌握度矩阵

**三级诊断流程**：

```
第一级：快速定位（15题）
  覆盖面广、难度分散的快速扫描
  → 识别"可能薄弱"的知识点集合
           ↓
第二级：精细诊断（30题）
  针对第一级筛查出的薄弱点，加大题目密度+变式题
  正确率持续高 → 难度自动升级
  正确率持续低 → 难度自动降级
  → 动态收敛到真实掌握水平
           ↓
第三级：掌握度矩阵
  每个知识点 → {mastery_score: 0-100, confidence: 0-1, evidence_count: N}
  区分"真掌握"、"假掌握"、"真薄弱"、"假薄弱"
```

**艾宾浩斯遗忘曲线调度**：
- 复习间隔：**[1, 2, 4, 7, 15, 30] 天**
- 自动化触发：正确率、错误类型（概念/计算/审题/方法/遗忘）→ 映射不同复习间隔
- GradingAgent 5 类错误 → 每类自动路由到不同复习策略

**掌握度变化检测**：
- 动态阈值算法（分数越低，阈值越敏感）
- ≥1 个知识点显著变化 → 触发学习路径自动调整
- 衰减检测：自动发现"已遗忘"的知识点

---

### 第 11 页 · 创新点三：三层闭环学习引擎

**标题**：诊断→规划→生成→学习→评估→再诊断，永不停歇的学习飞轮

**三大闭环**：

**闭环一：学习主循环**
```
诊断(DiagnosisAgent) → 规划(PlannerAgent) → 资源生成(ResourceAgent)
    → 学习执行(Student) → 答题/测验 → 批改(GradingAgent)
    → 评估(AssessmentLoop) → 画像更新(ProfileAgent) → 再诊断
```

**闭环二：质量保障环**
```
ResourceAgent 生成资源 → ReviewAgent 7 维质检 →
  ├── 通过 → 发布
  └── 不通过 → 退回 ResourceAgent 重试（最多 2 次）
```
ReviewAgent 7 项检查：
1. 内容安全审核（pyahocorasick 快速模式匹配 + LLM 二次审核）
2. RAG 可验证事实性检查（verifiable-rag）
3. FactEval 事实性评估
4. 画像一致性检查（内容是否与学习者背景匹配）
5. 学习路径覆盖验证
6. 资源内容质量评分
7. 题目质量审查

**闭环三：推荐与调度环**
- 推荐引擎 6 大信号源融合：
  1. 未完成资源
  2. 低正确率主题
  3. 未完成练习
  4. 阶段未完成
  5. 高频薄弱点
  6. 个性化偏好
- 后台调度器：
  - 事件驱动（每次测验提交 → 即时触发评估）
  - 周期性复诊（每 12 小时扫描过期会话，每周期最多处理 5 个）
  - 通知队列（SSE 推送：诊断更新/计划调整/推荐就绪/需复习）

---

### 第 12 页 · 创新点四：6 类学习资源 + 批量生成工厂

**标题**：从讲稿到思维导图，从测验到多模态——一站式学习资源工厂

**6 类核心资源**：

| 资源类型 | 生成方式 | 示例场景 |
|----------|---------|----------|
| 📖 **讲稿 (lecture)** | DeepTutor → LLM → 规则 | 教材式讲解、知识点深度剖析 |
| 🧠 **思维导图 (mindmap)** | LLM 结构化 → Markmap 渲染 | 章节知识结构、概念关系图 |
| ✏️ **测验 (quiz)** | QuestionAgent (5 类题型) | 选择题/填空题/判断题/简答题/变式题 |
| 📚 **阅读材料 (reading)** | LLM + RAG 知识库 | 拓展阅读、背景知识补充 |
| 🏋️ **练习 (practice)** | QuestionAgent + 变式生成 | 靶向练习、错题重练 |
| 🎬 **多模态 (multimodal)** | MultimodalAgent 路由 | 图片/视频/动画/PPT/闪卡/概念对比 |

**批量生成 + 智能修复流水线**：
```
输入：学习路径 (N 个阶段 M 个章节)
  → 检测变化（与前次对比，仅生成新增/变更部分）
  → 按需生成 6 类资源
  → ReviewAgent 逐类审核
  → 不通过 → 带 Review 反馈重试（修复模式）
  → 通过 → 写入 DB + 更新会话状态
```

**Section 级智能资源**（`section_generated_resources.py`）：
- 摘要卡片（summary_card）
- 概念对比（concept_comparison）
- 例题精讲（worked_example）
- 错题清单（mistake_checklist）
- 复习笔记（review_notes）
- 知识地图（knowledge_map）
- 流程图（process_flow）
- 概念图解（concept_diagram）
- 执行追踪（execution_trace）
- 代码追踪（code_trace）

---

### 第 13 页 · 创新点五：三种学习模式 + 自适应交互

**标题**：教材式系统学习、每日一课稳步推进、冲刺特训快速突破

**三种学习模式（PlannerAgent）**：

| 模式 | 适用场景 | 特点 |
|------|---------|------|
| 📗 **教材式 (textbook)** | 零基础系统学习 | 按教材章节顺序，完整覆盖所有知识点 |
| 📅 **每日一课 (daily)** | 在职/在校碎片化学习 | 每天 30-60 分钟，精心安排每日任务 |
| 🚀 **冲刺特训 (sprint)** | 考前突击/快速补缺 | 聚焦薄弱点 + 高频考点，短时间内高强度训练 |

**4 级降级策略**（PlannerAgent 生成兜底）：
```
Level 1: LLM (DeepSeek/Qwen/GLM) 直接生成完整规划
   ↓ 失败/不可用
Level 2: DeepTutor 结构化规划（利用终身学习模型）
   ↓ 失败/不可用
Level 3: LLM 流水线分步生成（分阶段调用、降低单次复杂度）
   ↓ 失败/不可用
Level 4: 教材/规则兜底（基于 textbook chapters + 课程目录规则生成）
```

**自适应交互亮点**：
- 学习内容 3 种渲染模式：**讲稿模式 / 闪卡模式 / 逐步推演模式**
- 内容类型自动检测（Markdown 语法分析 → 自动切换渲染器）
- 上下文感知快捷键（根据学科类别：编程/数理/人文/语言 → 自适应推荐操作）
- 语音输入（科大讯飞 ASR，WebSocket 实时识别，HMAC 签名后端代理）

---

### 第 14 页 · 功能演示一：智能对话式学习入口

**标题**：像和私教聊天一样学习——SSE 流式对话 + 多模态交互

**演示内容**（建议用截图/GIF）：

1. **对话界面**（ChatPage）：
   - 三模式切换：自由对话 / 指令调用 / 学习规划
   - SSE 流式响应（逐 token 实时显示 + 推理过程可见）
   - Agent 执行流水线可视化（每一步 Agent 的执行进度实时展示）
   - Markdown 富文本渲染：KaTeX 数学公式 + Mermaid 流程图 + Markmap 思维导图
   - 联网搜索开关 + 深度思考开关
   - 图片上传 + 引用（"这道题" → 自动关联已上传图片）
   - 语音输入按钮

2. **对话中的智能行为**：
   - 意图识别：自动判断是闲聊 / 提问 / 请求规划 / 请求资源
   - 间接探测：在自然对话中嵌入诊断问题，不让学生察觉"在被测试"
   - 事实抽取：每轮对话后自动分析 → 更新画像（事实标注为 `[探测]`、`[学生自述]`、`[行为观察]`）
   - 澄清提示：信息不足时主动发起追问

---

### 第 15 页 · 功能演示二：学习仪表盘 + 知识图谱

**标题**：一眼看清学习全貌——数据可视化驱动的学习驾驶舱

**演示内容**：

1. **学习中心首页（Home）**：
   - 学习统计数据卡片：连续学习天数 / 总学习时长 / 已完成资源数 / 测验正确率
   - 7 日完成趋势图（迷你柱状图）
   - 每日任务面板（今日待完成）
   - 学科管理：创建/切换学科，上传教材，加入班级（输入邀请码）
   - 快捷入口：对话 / 练习 / 资源库 / 学习路径 / 画像

2. **知识图谱页（KnowledgeGraphPage）**：
   - 基于 **AntV G6** 的交互式力导向图
   - 三种布局：力导向(force) / 层级(dagre) / 环形(circular)
   - 节点状态颜色编码：未开始 / 进行中 / 已掌握 / 需复习
   - 搜索/筛选：按节点名搜索，按状态/章节过滤
   - 点击节点 → 详情面板（知识点信息、掌握度、前置依赖）

3. **学习分析页（LearningAnalyticsPage）**：
   - ECharts 图表：掌握度雷达图 / 进度趋势折线图 / 薄弱点分布
   - 诊断面板：薄弱知识点列表 + 证据来源 + 置信度 + 趋势（改善/恶化）

---

### 第 16 页 · 功能演示三：学习路径 + 资源库

**标题**：个性化学习路径 + 丰富资源生态

**演示内容**：

1. **学习路径页（LearningPathPage）**：
   - 阶段 → 章节 → 小节层级结构，按天分组
   - 7 种任务类型：阅读文档 / 做测验 / 练习 / 写代码 / 方法论 / 模拟 / 复习
   - 规划向导（PlanningWizard）：多步骤引导式创建学习计划
   - 草稿管理：列表 / 加载 / 修订 / 丢弃规划草稿
   - AI 修订建议卡片

2. **资源库（ResourceLibrary）**：
   - 网格/列表视图切换
   - 按类型、难度、质量状态筛选
   - 内联测验（在资源页直接答题）
   - 书签 + 学习状态标记 + 导出 + 重新生成
   - 知识图谱预览
   - 在线资源搜索标签页
   - 个性化推荐标签页（RecommendationsTab，基于 6 信号源）

3. **讲稿页（LecturePage）**（最大页面 ~94KB）：
   - 讲稿模式 / 闪卡模式 / 逐步推演模式一键切换
   - PDF 教材侧边栏（TOC 导航）
   - 章节/小节导航 + 状态指示器
   - 小节资源工作区（关联资源展示）
   - 测验生成 + 提交
   - 内嵌聊天（针对当前小节提问）

---

### 第 17 页 · 功能演示四：练习中心 + 闭环评估

**标题**：练-批-诊-补-练，精准打击每一个薄弱点

**演示内容**：

1. **练习中心（PracticePage）**：
   - 四个视图：首页 / 测验 / 考试 / 历史
   - 弱项识别 + 靶向练习
   - 题库 + 试卷库
   - 答题批改：即时反馈（正确/错误 + 解析 + 建议）
   - 教师推送练习（班级学科）
   - 家长只读模式

2. **复习队列（ReviewQueuePage）**：
   - 艾宾浩斯驱动的复习提醒
   - 错题重练
   - 即将遗忘预警

3. **闭环评估流程（后台自动）**：
   ```
   学生完成测验
     → attempt 提交 → 触发 run_post_quiz_assessment()
     → GradingAgent 批改（5 类错误分类）
     → DiagnosisAgent 重新诊断（掌握度更新）
     → ProfileAgent 画像随学随新
     → PlannerAgent 路径自动调整（掌握度显著变化 → 重规划）
     → ResourceAgent 为新阶段生成资源
     → RecommendationEngine 生成新推荐
     → SSE 通知推送至前端
   ```

---

### 第 18 页 · 扩展能力：教师端与机构管理

**标题**：不只是学生工具——教师与机构的 AI 教学助手

**教师功能**：

| 功能 | 说明 |
|------|------|
| 🏫 **班级管理** (TeacherHome) | 创建班级学科 → 生成邀请码 → 学生加入 |
| 📋 **成员管理** (TeacherClassDetail) | 查看/移除学生，班级花名册 |
| ✏️ **练习推送** | 从题库选题推送至全班，或创建内联题目 |
| 📊 **学情统计** | 班级整体学情仪表盘，薄弱知识点分布 |
| 📖 **教材导入** | PDF 上传 → PyMuPDF 解析 → Markdown 提取 → LLM 章节识别 |
| 🔍 **题库管理** (AdminDashboard) | 题目 CRUD + 审核流程（待审/通过/拒绝） |
| 🧠 **知识图谱管理** | 知识点 CRUD + 前置依赖边管理 |
| ⚙️ **系统配置** | 全局参数调整 |

**架构特色**：
- 多角色权限模型：学生 / 教师 / 管理员 / 家长
- 家长模式：只读查看学习分析 + 时间线 + 画像
- 角色切换器（RoleSwitcher）：前端一键切换角色视角

---

### 第 19 页 · 技术可靠性保障

**标题**：工程化的鲁棒性设计——从降级策略到全链路追踪

**可靠性体系**：

| 保障维度 | 策略 | 说明 |
|----------|------|------|
| 🔽 **4 级降级** | LLM → DeepTutor 结构化 → LLM 流水线 → 教材/规则 | PlannerAgent 路径规划兜底 |
| 🔍 **多源搜索** | Tavily + DuckDuckGo 双源 | 熔断器 + 6h 缓存 + 动态排序 |
| 🛡️ **内容安全** | pyahocorasick 快速模式匹配 + LLM 二次审核 | 纯 Python 降级（pyahocorasick 缺失时） |
| 🔄 **重试机制** | ReviewAgent 退回 → ResourceAgent 重试 ≤2 次 | 质量不达标自动修复 |
| 🔑 **安全隔离** | 每用户独立 AI 凭据，API Key 仅存后端 | `to_safe_response()` 自动脱敏 |
| 📝 **全链路追踪** | X-Request-ID 贯穿所有请求 | Agent 级耗时日志 |
| 💾 **状态持久化** | SQLAlchemy + SQLite | 会话/画像/路径/资源/事件全量持久化 |
| 🔄 **崩溃恢复** | WorkflowTaskRecovery → sessionStorage | 前端工作流断点续传 |
| 🌐 **跨域安全** | CORS + JWT + HTTPBearer | 多角色鉴权（require_auth / reject_parent） |

---

### 第 20 页 · 价值量化与方案对比

**标题**：EduAgent vs 传统平台 —— 不只是"更好"，而是范式升级

**对比表**：

| 维度 | 传统在线教育平台 | EduAgent |
|------|-----------------|----------|
| **内容适配** | 统一课程，所有人相同 | **一人一策**，动态生成个性化学习路径 |
| **诊断方式** | 固定测验，粗粒度评分 | **三级自适应诊断**，精准到知识点 |
| **反馈周期** | 周/月（等考试结果） | **实时闭环**，每次答题即触发评估 |
| **资源形式** | 视频 + 文档（2-3 种） | **6 类核心 + 10 种 Section 级**智能资源 |
| **交互方式** | 被动观看 | **自然语言对话** + 多模态输入 |
| **教师负担** | 批改/诊断/规划全人工 | AI 分担诊断/规划/批改/推荐 |
| **遗忘管理** | 无 | **艾宾浩斯曲线**自动化调度 |
| **技术底座** | 规则引擎 + 简单推荐 | **10 Agent + LangGraph + RAG + 多模态** |
| **可扩展性** | 封闭系统 | **Agent 注册机制**，插件式扩展 |

**关键成果数据**（可填充实际测试数据）：
- 画像构建置信度：平均 XX%
- 诊断准确率：XX%
- 资源生成通过率（首次通过 ReviewAgent）：XX%
- 系统端到端延迟（全流水线）：XXs

---

### 第 21 页 · 技术栈一览

**标题**：全栈技术选型 —— 现代化工程体系

**前端**：

| 类别 | 技术 |
|------|------|
| 框架 | React 19 + TypeScript |
| 构建 | Vite |
| 路由 | React Router |
| 状态管理 | Zustand（7 个 Store） |
| HTTP | Axios + SSE 流式 |
| 样式 | Tailwind CSS + @tailwindcss/typography |
| 图表 | ECharts + echarts-for-react |
| 知识图谱 | AntV G6 |
| 思维导图 | markmap-lib + markmap-view |
| 流程图 | Mermaid.js |
| 数学公式 | KaTeX + remark-math + rehype-katex |
| Markdown | react-markdown + remark-gfm |
| 代码高亮 | react-syntax-highlighter (Prism) |
| 图标 | lucide-react |
| 语音 | 科大讯飞 ASR (WebSocket) |

**后端**：

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.13 |
| 框架 | FastAPI + Uvicorn |
| 数据校验 | Pydantic |
| ORM | SQLAlchemy + SQLite |
| 多智能体编排 | LangGraph (StateGraph) |
| RAG | LlamaIndex + FAISS + HuggingFace text2vec-large-chinese |
| PDF 处理 | PyMuPDF (pymupdf4llm) |
| 搜索引擎 | DuckDuckGo (ddgs) + Tavily |
| 内容安全 | pyahocorasick |
| 异步 HTTP | httpx |

**AI 模型**：

| 类别 | 模型/服务 |
|------|----------|
| 主 LLM | DeepSeek (deepseek-chat / deepseek-reasoner) |
| 多模态 VLM | Qwen-VL (通义千问视觉) |
| 图像生成 | 讯飞星火 / Seedream / ARK |
| 视频生成 | Wan Video |
| PPT 生成 | 讯飞智文 AIPPT |
| 代码可视化 | Manim (code2video) |
| 语音识别 | 科大讯飞 ASR |
| Embedding | text2vec-large-chinese (HuggingFace) |
| 外部智能体 | DeepTutor v1.5.0 (HKU) |

---

### 第 22-23 页 · 总结与展望

**标题**：EduAgent —— 让因材施教从理念走向工程现实

**一句话总结**：
> EduAgent = **多智能体协同** × **RAG 知识增强** × **多模态生成** × **闭环学习引擎** × **终身学习建模**

**核心成就回顾**（4 列亮点卡片）：
- 🔬 **技术创新**：10 Agent LangGraph 编排 + 间接探测 + 三级自适应诊断 + 艾宾浩斯调度
- 🏗️ **工程深度**：23 前端页面 + 20+ 路由 + 40+ 服务模块 + 20+ 数据表
- 🤖 **AI 广度**：5 种 LLM + 12 类多模态任务 + RAG + DeepTutor 集成
- 🎯 **产品闭环**：诊断→规划→生成→学习→评估→再诊断，全流程无断点

**近期路线图**：

| 阶段 | 内容 |
|------|------|
| **短期**（1-3 月） | 更多学科知识库接入、移动端 PWA 适配、家长端功能完善 |
| **中期**（3-6 月） | 情感计算 Agent（学习动机检测与激励）、协作学习模式、插件市场 |
| **远期**（6-12 月） | 通用自适应学习 OS、开放 Agent SDK、第三方 Agent 生态 |

**结束语**：
> 教育的本质不是灌输，而是点燃。EduAgent 用 AI 为每一位学习者点燃个性化的学习之光。

---

## 三、PPT 制作技术建议

### 3.1 架构图绘制
- 第 5 页的三层架构图用 **Mermaid** 或 **draw.io** 绘制
- 所有 Agent 之间的数据流用不同颜色箭头区分（蓝色：数据流、橙色：控制流、绿色：反馈流）

### 3.2 截图/演示录制
- 第 14-17 页的功能演示建议嵌入实际产品截图或 GIF 动图
- 关键交互：SSE 流式对话、知识图谱拖拽、闪卡翻转、逐步推演

### 3.3 图标使用
- 每个 Agent 使用独立 icon（脑图/齿轮/搜索/靶心/地图/书/问号/勾选/盾牌/图片）
- 资源类型用 emoji 区分（📖🧠✏️📚🏋️🎬）

### 3.4 数据可视化
- 第 20 页的对比表用雷达图 + 条形图结合展示
- 画像维度用雷达图
- 掌握度矩阵用热力图

### 3.5 动画建议
- Agent 流水线用递进式动画（按顺序逐个出现）
- 闭环流程图用循环动画箭头
- 数字用计数动画（从 0 滚动到目标数字）

---

## 四、附录：关键数据速查表（供制作时参考）

### 4.1 Agent 清单

| # | Agent | agent_id | 核心职责 |
|---|-------|----------|---------|
| 1 | ConversationAgent | conversation_agent | 意图分类 + 外层调度 + 间接探测 + 动态人设 |
| 2 | ProfileAgent | profile_agent | 7 维画像构建 + 增量更新 |
| 3 | KnowledgeAgent | knowledge_agent | RAG 检索 + 课程目录回退 + 查询扩展 |
| 4 | DiagnosisAgent | diagnosis_agent | 三级自适应诊断 + 掌握度矩阵 + 艾宾浩斯 |
| 5 | PlannerAgent | planner_agent | 3 种模式规划 + 4 级降级 + 日计划 |
| 6 | ResourceAgent | resource_agent | 6 类资源批量生成 + 修复模式 |
| 7 | QuestionAgent | question_agent | 5 类题目 + 变式题生成 |
| 8 | GradingAgent | grading_agent | 5 类错误分类 + 多维评分 |
| 9 | ReviewAgent | review_agent | 7 项质量审核 + 退回重试 |
| 10 | MultimodalAgent | multimodal_agent | 12 类多模态任务路由 |

### 4.2 前端页面清单（23 页）

1. Home（学习中心）2. ChatPage（对话）3. LecturePage（讲稿）4. LearningPathPage（学习路径）
5. PracticePage（练习中心）6. ResourceLibrary（资源库）7. KnowledgeGraphPage（知识图谱）
8. LearningAnalyticsPage（学习分析）9. LearningTimelinePage（学习时间线）10. ProfilePage（画像）
11. ResourceGenerationPage（资源生成）12. SettingsPage（设置）13. DailyTaskPage（每日任务）
14. FocusSprintPage（专注冲刺）15. ReviewQueuePage（复习队列）16. TaskPage（任务详情）
17. ConversationHistoryPage（对话历史）18. LoginPage（登录）19. AdminDashboard（管理后台）
20. TeacherHome（教师首页）21. TeacherClassDetail（班级详情）22. TextbookViewPage（教材查看）
23. NotFound（404）

### 4.3 服务模块清单（40+）

agent_factory, agent_service, assessment_access, assessment_loop, chapter_mindmap_resources,
code2video_provider, content_quality_service, content_safety, conversation_state, course_catalog,
day_planner, deeptutor_client, deeptutor_facade, diagnosis_snapshot_service, document_generator,
dt_bridge, iflytek_ppt_provider, intent_router, knowledge_point_service, langgraph_orchestrator,
learning_tracker, llm_assessment, llm_client, llm_factory, manim_templates, multimodal_provider,
multimodal_registry, personalization_context, profile_extractor, profile_v2, question_access,
recommendation_engine, resource_quality, search_client, section_generated_resources,
section_resource_recommendations, spark_provider, structured_multimodal_resources, subject_identity,
textbook_parser, textbook_processor, user_ai_config, web_ingest, workflow_tasks

### 4.4 数据库表清单（20+）

learners, sessions, messages, profile_snapshots, diagnosis_snapshots, learning_assessment_snapshots,
diagnosis_evidence, learning_paths, resources, learning_events, daily_tasks, questions,
knowledge_points, student_questions, practice_questions, answer_records, quizzes, exam_sets,
attempts, class_subjects, class_subject_members, class_pushes, personal_subjects, textbooks,
textbook_page_contents, user_preferences, user_ai_config, assessment_states, planning_drafts,
system_config, question_knowledge_point_mappings

---

**此提示词可直接用于 GPT-4o / Claude / 或其他支持长文本的 AI PPT 生成工具（如 Gamma、美图 AI PPT、讯飞智文等），生成高质量演示文稿。**
