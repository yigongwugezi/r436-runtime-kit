# EduAgent 智能体架构全景分析

> 分析日期：2026-07-10 | 分支：MAF-Refactor

---

## 一、总体架构

```
                            ┌──────────────────────────────┐
                            │      用户消息 (Student)        │
                            └──────────────┬───────────────┘
                                           │
                            ┌──────────────▼───────────────┐
                            │   product.py / chat_router   │  ← API 入口层
                            └──────────────┬───────────────┘
                                           │
                            ┌──────────────▼───────────────┐
                            │    ConversationAgent          │  ← 外层总控（意图分类+回复）
                            │    "对话智能体"                │
                            │    v4: 外层总控,               │
                            │    Orchestrator 只做执行       │
                            └──────────────┬───────────────┘
                                           │
                   ┌───────────────────────┼───────────────────────┐
                   │  action="none"        │  action="plan/..."    │  action="full_workflow"
                   │  (纯聊天)              │  (单Agent直调)         │  (全流程)
                   ▼                       ▼                       ▼
            ┌──────────┐          ┌──────────────┐        ┌──────────────────┐
            │ 返回对话  │          │ 单节点执行     │        │ LangGraph 全流程  │
            └──────────┘          └──────────────┘        └────────┬─────────┘
                                                                  │
                          ┌───────────────────────────────────────┘
                          ▼
              ┌───────────────────────┐
              │  LangGraph Pipeline   │
              │  (langgraph_          │
              │   orchestrator.py)    │
              └───────┬───────────────┘
                      │
      ┌───────────────┼───────────────┬───────────────┬───────────────┐
      ▼               ▼               ▼               ▼               ▼
  ProfileAgent   KnowledgeAgent  DiagnosisAgent  PlannerAgent   ResourceAgent
  (学习画像)     (知识检索)       (学习诊断)      (路径规划)      (资源生成)
                                                                      │
                                                                      ▼
                                                               ReviewAgent
                                                               (质量审查)
                                                                      │
                                                                      ▼
                                                          ConversationAgent
                                                          (final_reply 模式)
                                                                      │
                                                                      ▼
                                                              返回最终回复
```

---

## 二、9 个智能体功能总览

| # | Agent | agent_id | 文件 | 大小 | 核心职责 |
|---|-------|----------|------|------|---------|
| 1 | **ConversationAgent** | `conversation_agent` | [conversation_agent.py](../backend/app/agents/conversation_agent.py) | 38KB | 意图分类、自然语言对话、子Agent调度、最终回复汇总 |
| 2 | **ProfileAgent** | `profile_agent` | [profile_agent.py](../backend/app/agents/profile_agent.py) | 25KB | 提取学生9维学习画像（专业背景、知识基础、学习目标等） |
| 3 | **KnowledgeAgent** | `knowledge_agent` | [knowledge_agent.py](../backend/app/agents/knowledge_agent.py) | 5KB | RAG知识检索，查询扩展，课程目录回退 |
| 4 | **DiagnosisAgent** | `diagnosis_agent` | [diagnosis_agent.py](../backend/app/agents/diagnosis_agent.py) | 81KB | 多源证据融合诊断薄弱知识点（标准+自适应双模式） |
| 5 | **PlannerAgent** | `planner_agent` | [planner_agent.py](../backend/app/agents/planner_agent.py) | 49KB | 4阶段LLM管道生成学习路径 + 艾宾浩斯复习调度 |
| 6 | **ResourceAgent** | `resource_agent` | [resource_agent.py](../backend/app/agents/resource_agent.py) | 57KB | 生成6类学习资源（讲义/思维导图/测验/阅读/练习/视频） |
| 7 | **QuestionAgent** | `question_agent` | [question_agent.py](../backend/app/agents/question_agent.py) | 29KB | 生成5类练习题（选择/填空/判断/简答/变式），含自检机制 |
| 8 | **GradingAgent** | `grading_agent` | [grading_agent.py](../backend/app/agents/grading_agent.py) | 12KB | 4维评分（思路40%/完整30%/计算20%/表达10%）+ 5类错误分类 |
| 9 | **ReviewAgent** | `review_agent` | [review_agent.py](../backend/app/agents/review_agent.py) | 27KB | 12+项质量检查（内容安全/事实性/画像完整/路径/资源/章节对齐） |

---

## 三、标准全流程数据流

```
ProfileAgent          KnowledgeAgent        DiagnosisAgent
    │                      │                      │
    ▼                      ▼                      ▼
  profile               knowledge_context      diagnosis
  (9维画像)             (RAG检索知识点)         (薄弱点排名)
    │                      │                      │
    └──────────────────────┼──────────────────────┘
                           │
                    PlannerAgent
                           │
                    learning_path
                    (3-6阶段学习路径)
                           │
                    ResourceAgent
                           │
                      resources
                 (每阶段2-4个学习资源)
                           │
                     ReviewAgent
                           │
                      quality_status
                   (passed/warning/blocked)
                           │
                  ConversationAgent
                   (final_reply 模式)
                           │
                    最终自然语言回复
```

流程图对应的 LangGraph 节点链路：

```
intent_router → profile → knowledge → diagnosis → planner → resource → review → reply → END
                                                         ↑                    │
                                                         └── 反馈回路 ────────┘
                                                         (质量不通过时重试，最多2次)
```

---

## 四、各 Agent 详细分析

### 4.1 ConversationAgent — 外层总控

**角色：** 唯一直接面向学生的 Agent，所有子 Agent 在其背后工作。

**三种运行模式：**

| 模式 | 触发 | 作用 |
|------|------|------|
| `intent` | 每次收到用户消息 | 规则引擎（60+ 关键词模式） → LLM分类器（兜底）→ 输出 action |
| `final_reply` | 子 Agent 执行完毕后 | 读取真实 `pipeline_result`，生成自然语言汇总 |
| `DeepTutor 分流` | 检测到可视化需求 | 图表/视频脚本/Mindmap 委托给 DeepTutor |

**意图分类体系：**

| action | 含义 | 触发条件 |
|--------|------|---------|
| `full_workflow` | 全流程 | "完整方案"、"全套方案" |
| `plan` | 学习规划 | "学习路径"、"帮我规划"、"生成" |
| `resources` | 资源获取 | "资料"、"思维导图"、"讲义" |
| `generate_questions` | 出题练习 | "出题"、"做题"、"练习" |
| `diagnose` | 薄弱诊断 | "薄弱"、"诊断" |
| `grade_answer` | 批改 | "批改"、"判分" |
| `none` | 纯聊天 | 默认，或不匹配任何意图 |
| `unsafe` | 不安全内容 | 作弊/代考/代写/破解等关键词 |

**两级分类策略：**

1. 规则引擎优先——确定性、零延迟，覆盖 ~60 个关键词模式
2. LLM 分类器兜底——仅当规则引擎返回 `unclassified_fallback` 时启用，temperature=0

**LLM 配置：**

| 参数 | 值 | 场景 |
|------|-----|------|
| temperature | 0.7 | 回复生成 |
| temperature | 0 | 意图分类 |
| max_tokens | 800 | 回复生成 |
| max_tokens | 20 | 意图分类 |
| 历史窗口 | 最近20条 | 回复生成 |
| 历史窗口 | 最近6条 | 意图分类 |
| 回复重试次数 | 3 | 指数退避 |
| 分类重试次数 | 2 | 0.3s 延迟 |

**关键沟通规则（来自 SYSTEM_PROMPT）：**
- 禁止模板化/机器人式语言
- 未经确认不自动生成（先 proposal 后 execute）
- 引导式追问，逐步明确需求
- 诚实告知失败，不假装完成
- 禁止具体话术（如"请选择方向"、"画像完整度 2/7"）

---

### 4.2 ProfileAgent — 学习画像提取

**9 维度画像：**

| 维度 | 中文标签 | 含义 |
|------|---------|------|
| `major_background` | 专业背景 | 学生专业/身份 |
| `knowledge_base` | 知识基础 | 现有知识水平 |
| `learning_goal` | 学习目标 | 当前学习目标 |
| `cognitive_style` | 认知风格 | visual/practice/code/lecture |
| `error_patterns` | 易错模式 | 已知薄弱点 |
| `coding_ability` | 编程能力 | 编程水平 |
| `learning_progress` | 学习进度 | 当前进度阶段 |
| `interest_direction` | 兴趣方向 | 兴趣聚焦领域 |
| `learning_rhythm` | 学习节奏 | 时间预算和节奏偏好 |

**每个维度包含：** `value`, `score`(0-100), `confidence`(0-1), `explanation`, `evidence`, `source`

**双路径提取：**
- **LLM 路径：** 系统提示指定9维度 + 格式要求，融入学生描述/课程/facts/诊断弱点
- **规则回退：** 正则提取专业背景、时间预算、知识基础关键词；fact-to-dimension 映射；缺失值检测

---

### 4.3 KnowledgeAgent — 知识检索

**最轻量 Agent（5KB，无 LLM 生成逻辑）**

- **主路径：** RAG 语义搜索 (`rag_query_engine.search()`)
- **查询扩展：** 短查询（≤80字）自动用 LLM 扩展为 2-3 个关键词
- **回退：** CourseCatalog 课程目录（预置微积分/数据结构等课程知识点）
- **画像感知：** 查询构建时融合 `knowledge_base`、`learning_goal`、`interest_direction`

---

### 4.4 DiagnosisAgent — 学习诊断（最复杂 Agent，48 个方法）

**双模式运行：**

#### 标准模式（`standard`）

1. 从 6 个来源收集证据：用户自述、学习画像、行为数据、历史诊断、学习路径、课程知识点
2. LLM 诊断 → 解析 JSON（含 3 层自修复：直接解析 → LLM 修复 → 规则回退）
3. LLM 失败时回退到规则引擎：从分析事件、历史诊断、用户消息、画像提取候选薄弱点

#### 自适应模式（`adaptive`）— 三步诊断协议

| 步骤 | 名称 | 题目数 | 难度 | 说明 |
|------|------|--------|------|------|
| Step 1 | 快速筛查 | ≤15 | easy | 覆盖全部知识点 |
| Step 2 | 精细诊断 | ≤30 | medium | 针对薄弱区域深入探查 |
| Step 3 | 掌握度估计 | — | — | 贝叶斯估计 + 时间衰减 |

**贝叶斯掌握度模型：**

| 参数 | 值 | 说明 |
|------|-----|------|
| 先验分数 | 50 | 无信息先验 |
| 先验权重 | 3.0 | 需要足够证据才能克服先验 |
| easy 证据权重 | 0.7 | 信号强度乘数 |
| medium 证据权重 | 1.0 | |
| hard 证据权重 | 1.5 | |
| 时间衰减半衰期 | 30天 | 艾宾浩斯曲线，分数向50衰减 |
| 置信度公式 | `w/(w+3.0)` | 上限 0.95 |
| 趋势阈值 | ±5 分 | 进步/退步判定 |

**7 阶段掌握度环路：**

```
diagnostic → explain → feynman_check → practice → error_diagnosis → review → completed
( <30 )      (30-49)     (50-64)        (65-79)    (80-89)          (90-94)  (≥95)
```

**间隔复习调度：**

| 分数 | 复习间隔(天) |
|------|-------------|
| <30 | 1 |
| 30-49 | 2 |
| 50-64 | 4 |
| 65-79 | 7 |
| 80-89 | 15 |
| 90-94 | 30 |
| ≥95 | 60 |

**规则回退候选置信度模型：**

| 来源 | 置信度 | 上限 |
|------|--------|------|
| Analytics weakTopics | 0.65 + 0.25×risk | — |
| Quiz 事件 | 0.82 | — |
| Practice 事件 | 0.72 | — |
| 用户自述 | 0.74 | — |
| Profile 弱点 | 0.68 | — |
| 历史诊断 | min(prior, 0.68) | 0.68 |
| 未完成学习路径 | 0.42 | — |
| 课程知识点 | 0.35 | — |
| 整体（无行为数据） | — | 0.58 |

**唯一跨 Agent 调用：** 内部实例化 `QuestionAgent` 生成诊断题目。

---

### 4.5 PlannerAgent — 学习路径规划

**三层规划策略：**

| 层级 | 策略 | 说明 |
|------|------|------|
| Tier 1 | DeepTutor mastery_path | 优先尝试外部 mastery tracking 服务 |
| Tier 2 | 4 阶段 LLM 管道 | Architect → Creator → Reviewer → Refine |
| Tier 3 | 规则回退 | 等分知识点、模板化任务生成 |

**4 阶段 LLM 管道：**

```
_stage_architect (temp=0.3, 2000 tokens)
  设计 3-6 阶段大纲（标题/目标/时长/资源类型），难度递增
        │
        ▼
_stage_creator (temp=0.3, 2500 tokens)
  每阶段细化为 2-4 个可执行任务 + 具体资源类型
        │
        ▼
_stage_reviewer (temp=0.2, 1000 tokens)
  质量检查：难度递进？时间合理？任务可执行？逻辑衔接？
        │
   passed=false ──→ _stage_refine (temp=0.3, 2500 tokens)
        │              应用修改建议
        │              │
        │        仍不通过 → 回溯到 _stage_architect 重新生成（最多2轮）
        ▼
   passed=true → 输出最终路径
```

**M5 动态调整（adjust 模式）：**

| 策略 | 触发条件 | 动作 |
|------|---------|------|
| 加速 | 掌握度≥95% | 天数压缩至 1/3 |
| 近加速 | 掌握度≥90% | 天数压缩至 1/2 |
| 强化 | 掌握度<40% | +3天 + BFS 追溯前置知识（上限5个） |
| 补救插入 | 连续答错2题 | 前置"前置知识补救"阶段 |
| 应考模式 | "考试/期末/考研/高分"关键词 | 追加 quiz/practice 资源类型 |
| 阶段拆分 | ≥10天且≥3任务 | 拆为：概念回顾→引导练习→综合应用 |

**知识点收益排序公式：**

```
benefit = (100 - mastery_score)/100 × 0.7 + min(deps_count, 5)/5 × 0.3
匹配弱点的知识点 +0.2 加成
```

**艾宾浩斯复习调度：** 在阶段开始后 [1, 2, 4, 7, 15, 30] 天自动生成复习任务，估计复习时间 = max(10, 5 × 间隔天数) 分钟。

---

### 4.6 ResourceAgent — 学习资源生成

**6 类资源类型：** lecture, mindmap, quiz, reading, practice, video_script

**三级生成策略：**

1. DeepTutor 增强 → 讲义、思维导图、阅读材料
2. LLM 主生成 → 含 RAG 证据锚定（从 query engine 获取 grounding context）
3. 规则模板回退 → 含课程特定模板（data_structures, ai_intro）

**分隔符输出格式：** 使用 `---RESOURCE_META---` / `---RESOURCE_CONTENT---` 分隔符分离 JSON 元数据与 Markdown 内容，避免长文本 JSON 转义问题。

**渐进式批处理：** 每批 2 个阶段独立生成，避免 token 超限；阶段到知识点的模糊文本绑定。

**部分超时处理：** `get_fallback()` 返回已完成批次的中间结果（标记 `status: "timeout"`）而非全部丢弃。

**质量状态：** 每个资源携带 `quality_status`（passed/warning/fallback/insufficient_context）和 `generation_mode`（llm/fallback/mixed）供下游 ReviewAgent 审计。

---

### 4.7 QuestionAgent — 练习题生成

**5 种题型：** choice, fill, true_false, short_answer, variant

**质量保障机制：**

| 机制 | 说明 |
|------|------|
| 自检 | LLM 独立解答每道选择题/判断题，答案不一致则丢弃（temperature=0） |
| 难度校准 | LLM 评估实际难度与目标难度（easy/medium/hard）是否匹配 |
| 去重 | Jaccard 相似度（中文分词 + Latin 词）阈值 0.85 |
| 高风险标记 | 含"证明/推导/计算"标记为需人工复核 |
| 解释重写 | 短于30字或含推测性表述（"学生可能"）的 → LLM 重写 |
| DeepTutor 补充 | 额外调用 DeepTutor 增强题目质量 |

**批量生成：** 按学习路径阶段分批，每批独立生成。

---

### 4.8 GradingAgent — 自动批改

**4 维度评分（加权求和）：**

| 维度 | 权重 | 内容 |
|------|------|------|
| reasoning | 40% | 解题思路 |
| completeness | 30% | 答案完整性 |
| calculation | 20% | 计算准确性 |
| expression | 10% | 表达规范性 |

**5 类错误分类 + 自动行动：**

| 错误类型 | 中文标签 | 自动行动 |
|---------|---------|---------|
| concept | 概念理解错误 | `recommend_resources` → 推荐基础知识资源 |
| calculation | 计算失误 | `suggest_practice` → 推荐同类练习 |
| misreading | 审题偏差 | `flag_keyword_training` → 关键词训练 |
| method | 解题方法不当 | `recommend_better_solution` → 推荐更优解法 |
| forgetting | 知识点遗忘 | `add_to_review_queue`，间隔 [1,2,4,7,15,30] 天 |

**规则回退：** 选择题/判断题直接比对答案（正确/错误），填空题/简答题返回 null（提示开启 LLM）。

---

### 4.9 ReviewAgent — 质量门禁

**12+ 项检查汇总：**

| 检查类别 | 方法 | 状态 |
|---------|------|------|
| 内容安全 | 扫描屏蔽词字典（代写作业/考试作弊/泄题等） | passed/blocked |
| 事实性(verifiable-rag) | RAG 知识库核实 | passed/warning |
| 事实性(facteval) | 原子级声明校验 | passed/warning |
| 画像完整性 | ≥5个维度已填写 | passed/warning |
| 学习路径结构 | 每阶段有 tasks + goals | passed/warning |
| 资源覆盖度 | 5类资源类型齐全 | passed/warning |
| 资源内容质量 | quiz有选项/mindmap有mermaid标记/practice有案例 | passed/warning/blocked |
| 课程章节对齐 | resource.chapter 字段映射实际课程章节 | — |
| 来源可信度 | source/source_type/quality_status 一致性 | — |
| 时间预算 | 阶段时长不超过 estimatedDays | — |
| 资源类型匹配 | 类型标记与实际内容形式一致 | — |
| LLM 语义质量 | LLM 评估每资源首 500 字 → passed/warning/failed（temperature=0） | — |

**聚合规则：**
- `passed` — 全部检查通过
- `warning` — 有警告但不阻断使用
- `blocked` — 存在安全问题或严重内容缺陷，阻断下游使用

---

## 五、关键交互关系

### 5.1 数据传递机制

所有 Agent 通过 LangGraph 的共享 state dict（扁平字典）传递数据。每个 Agent 的返回 dict（除 `agent_step` 外）直接 merge 到共享状态，下游 Agent 从 context 读取上游产出。

### 5.2 Agent 依赖关系图

```
ConversationAgent ──(意图分类)──→ LangGraph Orchestrator
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
              ProfileAgent      KnowledgeAgent     DiagnosisAgent
                    │                  │                  │
                    │      profile用于RAG查询          内部调用QuestionAgent
                    │                  │                  │
                    └──────────────────┼──────────────────┘
                                       │
                                 PlannerAgent
                                       │
                             消费 profile + diagnosis + knowledge_context
                                       │
                                 ResourceAgent
                                       │
                           消费 knowledge_context + learning_path + profile
                                       │
                                  ReviewAgent
                                       │
                        审查所有上游输出（resources/profile/path/knowledge）
                                       │
                            ConversationAgent (final_reply)
                                       │
                              消费 pipeline_result 汇总回复
```

### 5.3 上下行数据关系

| 上游 Agent | 产出 key | 下游消费者 |
|-----------|---------|-----------|
| ProfileAgent | `profile` | KnowledgeAgent, DiagnosisAgent, PlannerAgent, ResourceAgent, ReviewAgent |
| KnowledgeAgent | `knowledge_context` | PlannerAgent, ResourceAgent, ReviewAgent |
| DiagnosisAgent | `diagnosis` | PlannerAgent, ReviewAgent |
| PlannerAgent | `learning_path` / `stages` | ResourceAgent, ReviewAgent, QuestionAgent |
| ResourceAgent | `resources` | ReviewAgent |
| QuestionAgent | `questions` | GradingAgent |
| GradingAgent | `grading_result` | ConversationAgent（用于 final_reply） |

### 5.4 唯一跨 Agent 硬依赖

**DiagnosisAgent → QuestionAgent**：自适应诊断模式中，DiagnosisAgent 内部 `import` 并实例化 `QuestionAgent`，传入相同 `llm_client`，调用 `.run(context)` 生成诊断题目。这是唯一一处 Agent 直接调用另一个 Agent 的场景。

---

## 六、基础设施层

### 6.1 Agent 基类与注册

**BaseAgent（[base.py](../backend/app/agents/base.py)）：**

```
BaseAgent(ABC)
├── agent_id: str          # 类属性，唯一标识
├── agent_name: str        # 类属性，中文名称
├── __init__(mock_data, llm_client)
├── run(context) → dict    # 抽象方法，唯一必须实现的入口
├── validate_context()     # 可选钩子，运行前校验输入
├── validate_result()      # 可选钩子，运行后校验输出
└── get_fallback()         # 可选钩子，返回安全默认值
```

**注册机制（[__init__.py](../backend/app/agents/__init__.py)）：**
- 硬编码 import 所有 Agent 类
- `__all__` 列表导出
- 无装饰器、无元类、无动态扫描——添加新 Agent 需手动修改两处

**异常类型：**
- `AgentValidationError` — 输出校验失败
- `AgentError` — 运行中不可恢复错误

### 6.2 LLM 客户端

```
BaseLLMClient(ABC)
├── MockLLMClient        # dev/test
└── DeepSeekLLMClient    # production
    ├── urllib.request   # 无外部 HTTP 依赖
    ├── 重试逻辑         # 4xx(非429)立即失败，5xx/429/网络错误重试
    └── 工厂函数 get_llm_client(provider)
```

### 6.3 LangGraph 编排器

**文件：** [langgraph_orchestrator.py](../backend/app/services/langgraph_orchestrator.py)

**节点映射：**

| 节点 | Agent | 键名 |
|------|-------|------|
| `intent_router` | ConversationAgent | — |
| `conversation` | ConversationAgent | — |
| `profile` | ProfileAgent | `"profile"` |
| `knowledge` | KnowledgeAgent | `"knowledge"` |
| `diagnosis` | DiagnosisAgent | `"diagnosis"` |
| `planner` | PlannerAgent | `"planner"` |
| `resource` | ResourceAgent | `"resource"` |
| `review` | ReviewAgent | `"review"` |
| `reply` | ConversationAgent | — |

**Agent 实例化：** 每次 `_run_agent` 调用都通过 `_make_agents()` 创建全新实例（ConversationAgent 除外，通过 `from_context()` 复用缓存）。所有 Agent 共享同一个 `llm_client`。

**执行模型：** `asyncio.to_thread(agent.run, ctx)` — Agent 同步代码在线程池执行，不阻塞事件循环。

**反馈回路：** review → resource（质量不通过时重新生成，最多 2 次）

### 6.4 服务与会话层

| 组件 | 文件 | 职责 |
|------|------|------|
| AgentService | [agent_service.py](../backend/app/services/agent_service.py) | 触发管道 + 持久化结果到 DB/Cache |
| ConversationStore | [conversation_state.py](../backend/app/services/conversation_state.py) | 内存+DB 会话管理，facts 提取，意图追踪 |
| DeepTutor Client | [deeptutor_client.py](../backend/app/services/deeptutor_client.py) | 异步桥接外部 DeepTutor 编排器 |
| CourseCatalog | [course_catalog.py](../backend/app/services/course_catalog.py) | 课程知识点目录（微积分/数据结构） |

### 6.5 API 入口

| 路由 | 端点 | 编排路径 |
|------|------|---------|
| `chat_router.py` | `POST /api/chat/stream` | 新 SSE 端点，直接调用 LangGraph |
| `chat_router.py` | `POST /api/chat/send` | 非流式版本 |
| `product.py` | 主产品端点 | ConversationAgent 意图分类 → AgentService → LangGraph |

### 6.6 上下文 Schema

（[agent_context.py](../backend/app/schemas/agent_context.py)）

每个 Agent 有对应的 Pydantic 输入模型（如 `PlannerAgentInput`、`DiagnosisAgentInput`），以及 `PipelineState` 全状态模型。当前为**文档化**使用，Agent 运行时不做强制校验。

---

## 七、技术栈总结

| 层级 | 技术 | 关键文件 |
|------|------|---------|
| Agent 基类 | ABC 抽象基类 + 单一 `run()` 入口 | `base.py` |
| Agent 注册 | 硬编码 import + `__all__` 列表 | `__init__.py` |
| 编排引擎 | LangGraph StateGraph + `ainvoke()` | `langgraph_orchestrator.py` |
| LLM 客户端 | OpenAI 兼容 API（DeepSeek）+ urllib + 重试 | `llm_client.py` |
| 会话管理 | 内存 ConversationStore + DB 持久化 | `conversation_state.py` |
| 意图分类 | 规则引擎优先 → LLM 兜底（两级策略） | `conversation_agent.py` |
| JSON 解析 | `parse_safe` + LLM JSON 修复器回调 | `llm_json.py` |
| 外部服务 | DeepTutor（chat/mindmap/lecture/visual/manim） | `deeptutor_client.py` |
| 知识检索 | RAG 语义搜索 + 课程目录回退 | `knowledge_agent.py` |
| 上下文 Schema | Pydantic 模型（文档化，非运行时强制） | `agent_context.py` |
| 执行模型 | `asyncio.to_thread(agent.run, ctx)` 同步在线程池 | orchestrator |

---

## 八、设计模式总结

1. **LLM 优先 + 规则回退** — 每个 Agent 都有 LLM 主路径和规则回退路径，确保离线可用
2. **共享状态传递** — 扁平 dict 通过 LangGraph state 在 Agent 间流动，无序列化开销
3. **构造器注入** — `llm_client` + `mock_data` 通过构造函数传入，无 DI 框架
4. **工厂复用** — ConversationAgent 通过 `from_context()` 在同一请求中复用实例
5. **每次新建** — 其他 Agent 每个编排节点都重新实例化，避免状态污染
6. **分层总控** — ConversationAgent（外层，决定做什么）+ LangGraph（内层，决定怎么做）
7. **渐进批处理** — ResourceAgent/QuestionAgent 分批处理大数据量，避免 token 超限
8. **反馈闭环** — ReviewAgent 审查不通过可触发 ResourceAgent 重新生成

---

## 九、重构机会分析

以下按**严重程度**和**收益**排序，逐一分析当前架构中存在的交互问题及改进方向。

---

### 🔴 P0 — 意图分类链路重复（3 处独立实现）

**现状：** 意图到 Agent 的映射在代码中出现了 **3 次**，每次独立维护：

| 位置 | 行号 | 映射方式 |
|------|------|---------|
| `langgraph_orchestrator.py::_route_by_intent` | L117-121 | intent → LangGraph node 名 |
| `langgraph_orchestrator.py::run_pipeline` | L225-226 | intent → agent key 名（single_map） |
| `product.py::_agents_for_action` | L1639-1655 | action → agent_id 列表 |

三份映射的键名体系还不一致——`_route_by_intent` 用 `"resources"`，`_agents_for_action` 用 `"resource_agent"`。每次新增 Agent 或修改意图路由，需要改 3 个地方，极易遗漏。

**问题本质：** 缺少一个统一的 `Intent → AgentPlan` 的路由注册表。

**建议方向：**

```
# 统一路由注册表（单一事实来源）
IntentRouter = {
    "plan":              AgentPlan(agents=["planner"],   pipeline=["planner"]),
    "resources":         AgentPlan(agents=["resource"],  pipeline=["resource"]),
    "generate_questions": AgentPlan(agents=["question"],  pipeline=["question"]),
    "diagnose":          AgentPlan(agents=["diagnosis"], pipeline=["diagnosis"]),
    "grade_answer":      AgentPlan(agents=["grading"],   pipeline=["grading"]),
    "full_workflow":     AgentPlan(agents=None,          pipeline=["profile","knowledge","diagnosis","planner","resource","review"]),
    "none":              AgentPlan(agents=[],            pipeline=[]),
}
```

---

### 🔴 P1 — 双路由入口不一致

**现状：** 两个 API 路由文件走不同的编排路径：

| 路由 | 意图分类 | 执行引擎 | 回复生成 |
|------|---------|---------|---------|
| `chat_router.py` | LangGraph `_intent_node` 内部 | `run_pipeline()` 直接 | `_reply_node` / `_conversation_node` |
| `product.py` | `_classify_intent()` → ConversationAgent | `_run_agents()` → AgentService → `run_pipeline()` | `_generate_final_reply()` → ConversationAgent final_reply |

`product.py` 的路径更长更完整（有 ConversationStore 状态管理、facts 提取、final_reply），而 `chat_router.py` 走的是一条简化路径。两者行为不一致会导致：
- 同一请求走不同路由产生不同结果
- Bug 只出现在一条路径上
- 新功能需要双端实现

**建议方向：** 统一到一个 Orchestrator Service，所有路由只做 HTTP 适配，业务逻辑集中在 Service 层。

---

### 🔴 P2 — ConversationAgent 重复实例化

**现状：** 同一请求中 ConversationAgent 被创建 **3-4 次**：

```
product.py::_classify_intent()        → new ConversationAgent()   [第1次]
langgraph_orchestrator::_intent_node() → new ConversationAgent()   [第2次]
langgraph_orchestrator::_reply_node()  → new ConversationAgent()   [第3次]
product.py::_generate_final_reply()    → new ConversationAgent()   [第4次]
```

每次创建都伴随 `get_llm_client()` 调用和独立的历史加载。虽然有 `from_context()` 缓存机制，但 3 个调用点中只有 `_intent_node` 使用了它——`product.py` 和 `_reply_node` 都是直接 `ConversationAgent()`。

**历史加载的浪费：** `_load_history()` 每次都从 `context["conversation_history"]` 重新加载，但实际上同一个请求内的历史是不变的。多次加载-保存-加载产生了不必要的 dict 拷贝。

**建议方向：** 同一请求生命周期内 ConversationAgent 只创建一次，由 Orchestrator 统一持有和传递。

---

### 🟠 P3 — `_make_agents()` 全量实例化浪费

**现状：** [langgraph_orchestrator.py:L37-38](backend/app/services/langgraph_orchestrator.py#L37-L38) 每次调用 `_run_agent()` 都执行 `_make_agents()`，创建全部 8 个 Agent 实例。单意图路由（如 `plan`）只用到 1 个 Agent，其余 7 个白建。

虽然单个 Agent 构造很轻量（只赋值 `mock_data` 和 `llm_client`），但 `_make_agents()` 每次都会：
1. 调用 `get_llm_client(settings.llm_provider)` — 读取配置、创建 HTTP 连接池
2. 实例化 8 个类

在 full_workflow 中 `_run_agent` 被调用 5 次，意味着 5 次全量创建 = **40 个 Agent 实例化 + 5 个 LLM Client 创建**。

**建议方向：** 改为懒加载单例工厂，同一个 pipeline 执行中只创建一次 LLM client + 按需实例化 Agent。

```
class AgentFactory:
    def __init__(self): self._llm = None; self._agents = {}
    def get_llm(self): ...
    def get_agent(self, name: str) -> BaseAgent: ...  # 懒加载
```

---

### 🟠 P4 — DiagnosisAgent → QuestionAgent 唯一跨 Agent 硬耦合

**现状：** `DiagnosisAgent._generate_diagnostic_questions()` 内部直接 import 并实例化 `QuestionAgent`。这是 9 个 Agent 中**唯一**的直接跨 Agent 依赖，与其他 Agent 通过共享 state dict 松耦合传递数据的模式格格不入。

**问题：**
- 循环依赖风险：`diagnosis_agent.py` import `question_agent.py`
- 测试隔离困难：测试 DiagnosisAgent 时必须提供完整的 QuestionAgent 环境
- 无法替换：想换个题目生成策略必须改 DiagnosisAgent 代码

**建议方向：** 将 `QuestionAgent` 注入为策略接口，或把诊断题目生成的编排逻辑上提到 Orchestrator（作为独立的步骤节点而非内部调用）。

---

### 🟠 P5 — DeepTutor 调用散落在 4+ 处，无统一门面

**现状：** DeepTutor 的调用点分布在：

| 位置 | 调用内容 |
|------|---------|
| `ConversationAgent._try_deeptutor_reply()` | chat、visual_explanation、video_script、manim |
| `PlannerAgent.run()` | mastery_path |
| `ResourceAgent` | lecture、mindmap、reading |
| `QuestionAgent` | 增强出题 |
| `langgraph_orchestrator.run_pipeline()` | chat 兜底 |

每个调用点各自处理错误、各自格式化参数，没有统一的超时/重试/降级策略。

**建议方向：** 引入 `DeepTutorFacade`，统一封装所有 DeepTutor 能力调用：

```
class DeepTutorFacade:
    async def chat(self, message, history) -> str: ...
    async def generate_lecture(self, topic, context) -> str: ...
    async def generate_mindmap(self, topic) -> str: ...
    async def generate_quiz(self, knowledge_points) -> list: ...
    async def mastery_path(self, course, profile) -> list: ...
```

---

### 🟡 P6 — 状态字典无类型约束

**现状：** LangGraph 的 state 是裸 `dict`，Agent 之间通过字符串 key 隐式耦合。`agent_context.py` 中定义了完整的 Pydantic 模型但标注为"文档化使用，不做运行时强制"。

**问题：**
- Agent A 产出 `diagnosis`（dict），Agent B 用 `context.get("diagnosis", {})` 读取——没有编译期保证
- key 重名无检测——两个 Agent 都用 `summary` 会互相覆盖
- 重构时改了一个 Agent 的输出字段，下游消费方不会报错，只会在运行时静默丢失数据

**建议方向：** 分阶段推进类型化——

**Phase 1（低风险）：** 用 `TypedDict` 定义 PipelineState，各 Agent 的 `run()` 返回明确的 TypedDict 子集

**Phase 2（中期）：** 启用 Pydantic `PipelineState` 在 Agent 边界做运行时校验（opt-in `validate_context=True`）

**Phase 3（理想）：** Agent 之间通过显式的 OutputPort → InputPort 连接，Orchestrator 负责类型校验和转换

---

### 🟡 P7 — Review → Resource 反馈回路硬编码

**现状：** [langgraph_orchestrator.py:L124-149](backend/app/services/langgraph_orchestrator.py#L124-L149) `_after_review` 函数硬编码了检查逻辑：只检查 `resource_content_quality` 等 4 个 check_id，只回退到 `resource` 节点。

**问题：**
- 如果将来 Planner 输出也需要质量审查和重试，需要新写一套逻辑
- 重试策略（max 2 次）写死在 `MAX_RETRIES` 常量，不同 Agent 可能有不同的重试策略
- 回退时没有通知上游（比如 Planner 不知道 Resource 因质量不通过被重试了）

**建议方向：** 通用化质量反馈机制：

```
# 每个 Agent 声明自己的 retry policy
class RetryPolicy:
    max_retries: int = 2
    retry_on_checks: list[str]   # 哪些 check_id 触发重试
    notify_upstream: list[str]   # 重试时需要通知的节点
```

---

### 🟡 P8 — ConversationAgent 承担了过多职责

**现状：** ConversationAgent 同时负责：
1. 意图分类（规则引擎 + LLM）
2. 自然语言回复生成
3. DeepTutor 分流（visual/video/manim/chat）
4. 结构化 facts 提取
5. Pipeline 结果格式化（`_format_pipeline_result`）
6. 最终回复生成（`_run_final_reply`）

38KB 的单文件，`run()` 方法分叉为 `intent` 和 `final_reply` 两种完全不同的行为模式。从单一职责角度看，至少可以拆出：
- **IntentClassifier** — 纯意图分类
- **ReplyGenerator** — 自然语言生成 + DeepTutor 分流
- **FactExtractor** — 结构化 facts 提取

**建议方向：** 保持 ConversationAgent 作为门面，但内部委托给专职子组件。这样重构可是渐进式的——先拆分内部实现，外部接口不变。

---

### 🟢 P9 — 时间预算提取重复

**现状：** 两个地方各自做时间提取：

| 位置 | 方法 | 方式 |
|------|------|------|
| `ProfileAgent._rule_based_profile()` | 正则提取 time_budget | 规则 |
| `PlannerAgent._infer_days()` | LLM (temp=0) + `_rule_infer_days()` | LLM+规则 |

PlannerAgent 的时间推断比 ProfileAgent 更丰富（LLM + 中文数字标准化 + 常见表达参考），但 ProfileAgent 的时间提取结果也存入 profile。两者可能产生不一致。

**建议方向：** 时间预算作为标准化输入，只由一处（ProfileAgent）提取并归一化为天数，PlannerAgent 直接消费 `profile.learning_rhythm` 中的值。

---

### 🟢 P10 — Agent 注册依赖手动维护

**现状：** `__init__.py` 硬编码 import + `__all__` 列表。添加新 Agent 需要手动修改两处。

**建议方向：**
- 方案 A（轻量）：用 `importlib` 扫描 `agents/` 目录下 `*_agent.py` 文件，自动发现 `BaseAgent` 子类
- 方案 B（标准）：使用 `setuptools` entry points 或装饰器注册

---

### 🟢 P11 — 反馈信息通过 context dict 反向传参

**现状：** `product.py` 在 `_reply_for_intent()` 中，拿到 GradingAgent 结果后，直接修改 `state.facts["_pending_adjustment"]` 和 `state.facts["weak_points"]`，等下一次 ConversationAgent 运行时再检测这些标记。

```
# product.py L1621-1628
if grading.get("error_type") and grading["error_type"] != "null":
    final_reply += f"..."
    state = conversation_store.get(session_id)
    state.facts["_pending_adjustment"] = et       # ← 用下划线前缀的隐藏字段传参
    state.facts["weak_points"] = ...
```

这是一种隐式的跨请求数据传递——GradingAgent 的产出不经过 LangGraph state 流，而是绕过管道直接写入 session 存储。

**建议方向：** 将跨请求的反馈定义为显式的 `FeedbackSignal` 类型，由 Orchestrator 在下次请求时注入 context，而非通过隐式标记位。

---

### 重构优先级总览

| 优先级 | 编号 | 问题 | 影响范围 | 重构风险 |
|--------|------|------|---------|---------|
| 🔴 P0 | #1 | 意图映射 3 处重复 | 每次新增/修改意图 | 低 |
| 🔴 P1 | #2 | 双路由入口不一致 | 所有请求 | 中 |
| 🔴 P2 | #3 | ConversationAgent 重复实例化 | 每请求 3-4 次创建 | 低 |
| 🟠 P3 | #4 | `_make_agents()` 全量实例化 | 每次节点调用 | 低 |
| 🟠 P4 | #5 | DiagnosisAgent→QuestionAgent 硬耦合 | 自适应诊断 | 中 |
| 🟠 P5 | #6 | DeepTutor 散落各处 | 所有外部服务调用 | 中 |
| 🟡 P6 | #7 | 状态字典无类型 | 所有 Agent 间通信 | 高 |
| 🟡 P7 | #8 | Review 回路硬编码 | 质量反馈 | 中 |
| 🟡 P8 | #9 | ConversationAgent 职责过重 | 意图分类+回复 | 中 |
| 🟢 P9 | #10 | 时间提取重复 | 画像+规划 | 低 |
| 🟢 P10 | #11 | 手动注册 | 新增 Agent | 低 |
| 🟢 P11 | #12 | 隐式跨请求传参 | Grading→下次请求 | 中 |

---

## 十、各重构点的具体后果

以下将每个问题映射到它**现在或将来必然触发的具体场景**，以说明"为什么必须修"。

---

### 🔴 #1 意图映射 3 处重复 → 生产 Bug

**典型故障场景：**

某天你要新增一个 `review` 意图（学生说"帮我检查一下学习计划"→直接跑 ReviewAgent）。你需要改 3 个地方：

1. `_route_by_intent()` — 加 `"review": "review"`
2. `run_pipeline()` 的 `single_map` — 加 `"review": "review"`
3. `_agents_for_action()` — 加 `"review": ["review_agent"]`

**如果你漏了任何一处：**

- 漏了 #1 → langgraph 全流程路由收到 `review` 意图后走到 `conversation` 兜底，学生会得到一个聊天回复而不是审查结果——**不报错，静默降级**
- 漏了 #2 → 单意图直调路径收不到、回退到全流程——**功能正常但多了 5 个 Agent 的无意义执行，延迟暴增、费用暴增**
- 漏了 #3 → `product.py` 直接跳过这个 action，回复 fallback 消息——**路由入口不同，有的能用有的不能用**

**已经能看到的征兆：** `_route_by_intent` 用 `"resources"` 而 `_agents_for_action` 用 `"resource_agent"`——键名体系已经不统一了，说明已经有人在不同时间点独立修改，没有意识到另一份映射的存在。

---

### 🔴 #2 双路由入口不一致 → 同一请求不同结果

**典型故障场景：**

你在 `product.py` 中给 ConversationAgent 加了 `final_reply` 优化（比如 pipeline 失败时用更自然的语言解释），然后上线。用户通过 SSE 端点 (`chat_router.py`) 发请求，pipeline 失败后收到的是 `_reply_node` 里的机械模板 `"已生成3个学习阶段、配套5个资源。"`——因为 `chat_router.py` 根本没走 `_generate_final_reply()` 那条路径。

**累积效应：**
- 每次加功能，开发者不确定该改哪条路径 → 只改自己熟悉的那条 → 另一条路径逐渐腐烂
- 新同事接手时看到两条完全不同的请求处理链路，无法判断哪条是"正确的"
- 如果有一天要下线旧路由，你不知道有多少前端依赖在哪条路径上

---

### 🔴 #3 ConversationAgent 重复实例化 → 资源泄漏 + 不一致

**直接后果：**

```
每次请求：
  _classify_intent()     → 创建 ConversationAgent + LLM Client #1
  _intent_node()         → 创建 ConversationAgent + LLM Client #2
  _reply_node()          → 创建 ConversationAgent + LLM Client #3
  _generate_final_reply()→ 创建 ConversationAgent + LLM Client #4
```

- **4 个 DeepSeekLLMClient 实例** — 每个底层 `urllib.request` 创建独立的 HTTPS 连接池。在高并发下，连接不共享 = TCP 握手开销 ×4
- **4 次 `_load_history()`** — 每次从同一个 `context["conversation_history"]` 拷贝一份 20 条的 list，然后各自 trim 到 40 条。同一请求内 4 个实例的 `self._history` 内存占用 4 份，且实例之间互不可见——第 2 个实例加了消息，第 3 个实例看不到

**更隐蔽的问题：** `_save_history()` 写回 `context["conversation_history"]`，但第 1/2/3 次创建的实例可能在不同时间点写回，最后一次写回的覆盖前面的。对话历史静默丢失。

---

### 🟠 #4 `_make_agents()` 全量实例化 → 延迟累积

**直接代价：**

一个 `full_workflow` 请求走 `profile → knowledge → diagnosis → planner → resource → review`，6 个节点各调用一次 `_run_agent()` → 各执行一次 `_make_agents()`：

```
6 次 × (1 次 get_llm_client + 8 次 Agent 构造) = 6 个 LLM Client + 48 个 Agent 实例
```

每个 `DeepSeekLLMClient()` 构造虽然轻量，但 `get_llm_client()` 会读 `settings`、读环境变量。48 个 Python 对象分配虽然不会导致 OOM，但在高并发（比如 20 个学生同时请求）下会产生显著的 GC 压力。

**更重要的是浪费了 LLM 调用机会：** 每个 Agent 构造时收到同一个 `llm_client` 引用，这本该是共享的。实际也确实共享了——浪费的不是连接数，而是对象创建/销毁的 CPU 周期。

---

### 🟠 #5 DiagnosisAgent → QuestionAgent 硬耦合 → 测试盲区 + 变更阻力

**场景 1 — 写单元测试：**

```python
def test_diagnosis_adaptive():
    agent = DiagnosisAgent(llm_client=mock_llm)
    result = agent.run({"mode": "adaptive", ...})
    # ← 内部触发 QuestionAgent(mock_data={}, llm_client=mock_llm).run(...)
    # 你必须 mock QuestionAgent 的 run() 或者接受实际网络调用
    # 但实际上你根本 mock 不到——它是在方法内部直接 import 的
```

**场景 2 — 替换出题策略：**

你想把诊断题从 LLM 生成换成题库抽取。按设计，这应该是 `QuestionAgent` 的内部变更，对 `DiagnosisAgent` 透明。但实际上 `DiagnosisAgent._generate_diagnostic_questions()` 直接 new `QuestionAgent`——你想换实现就必须改 DiagnosisAgent 代码。

**场景 3 — 循环依赖触发：**

```
diagnosis_agent.py → import question_agent.py
question_agent.py  → (未来某天) import diagnosis schemas
                    → ImportError: circular import
```

---

### 🟠 #6 DeepTutor 散落各处 → 降级策略不一致

**场景：** DeepTutor 服务挂了。

| 调用方 | 反应 |
|--------|------|
| `ConversationAgent._try_deeptutor_reply()` | catch Exception → 返回空字符串，外层用静态 fallback |
| `PlannerAgent.run()` | except → 静默跳过，走 4-stage LLM 管道 |
| `ResourceAgent` | except → 资源列表不包含 DeepTutor 增强内容 |
| `QuestionAgent` | except → 题目列表不含 DeepTutor 补充题目 |
| `langgraph_orchestrator.run_pipeline()` | except → fallback 静态字符串 |

**5 个调用点，5 种降级行为**——有的重试、有的跳过、有的 fallback。运维时你不知道 DeepTutor 挂了会影响哪些功能、影响程度如何。加全局熔断器也加不了——没有统一的调用入口。

---

### 🟡 #7 状态字典无类型 → 静默数据丢失

**场景 1 — 字段改名：**

PlannerAgent 重构，把输出 key 从 `"learning_path"` 改成 `"stages"`（已经在代码中出现了两者的混用）。ResourceAgent 消费的是 `context.get("learning_path", [])`，拿到的永远是空列表，资源生成变成空跑——**不报错，没有 warning，学生收到 0 个资源**。

**场景 2 — key 冲突：**

`DiagnosisAgent` 返回 `{"diagnosis": {"summary": "..."}, "agent_step": {...}}`。

`PlannerAgent` 返回 `{"learning_path": [...], "summary": "学习路径已生成", "agent_step": {...}}`。

LangGraph state merge 后 `state["summary"]` 被 Planner 覆盖。Diagnosis 的 summary 丢失。如果前端需要展示诊断摘要——拿不到了。

**场景 3 — 新人接手：**

新同事开发一个新 Agent，需要消费 `diagnosis`。IDE 里键入 `context.get("diag`——没有自动补全。只能翻看 DiagnosisAgent 源码找输出字段名，或者 grep 搜索字符串。上手成本随着 Agent 数量线性增长。

---

### 🟡 #8 Review 回路硬编码 → 扩展需要硬改代码

**场景：** 你想加一个检查——如果 Planner 输出的学习路径超过 60 天，Review 应该重跑 Planner 压缩时间。

当前代码里 `_after_review` 只检查 4 个 resource 相关的 check_id，只回退到 `"resource"` 节点。你要加 Planner 回退就得：
1. 新写一个条件判断逻辑
2. 在 `build_unified_graph()` 里多加一条 `g.add_conditional_edges("review", ..., {"planner": "planner"})`
3. 确保 Planner 节点在 graph 里被定义在 Review 之前（否则 LangGraph 报 edge 不存在）

**每加一种回退场景，就要改 graph 拓扑。** 当你有了 5-6 种不同的回退规则，`_after_review` 会变成一个巨大的 if-elif 链。

---

### 🟡 #9 ConversationAgent 职责过重 → 每次改一处都要理解全部

**场景：** 你只想改 prompt 里的某条沟通规则（比如"禁止机器人语气"的措辞）。打开 38KB 的文件，`run()` 分叉到 `_run_intent()` 和 `_run_final_reply()`，每个又分叉到 LLM 路径和 DeepTutor 路径。你需要在 4 条代码路径之间跳转，判断这条规则应该加在 `SYSTEM_PROMPT` 还是 `FINAL_REPLY_PROMPT`，还是两个都加。

**更危险的是：** 改 facts 提取的正则逻辑时，你可能没注意到它也在影响 `_parse_response()` 的 tag 解析——两个解析器共享同一个 `_extract_reply_and_facts()` 静态方法，但它们的容错预期不一样。

---

### 🟢 #10 时间提取重复 → 数据矛盾

**场景：** 学生说"我大概有三个月时间，每天能学2小时"。

- `ProfileAgent` 正则匹配到 `"三个月"`，提取 `time_budget = "三个月"`（文本，未归一化）
- `PlannerAgent._infer_days()` 匹配到 `"三个月"` → LLM 返回 90，最终 `total_days = 90`

但如果 PlannerAgent 也取到了 Profile 的 `time_budget` 值 `"三个月"` + `"每天2小时"` 合成 prompt → LLM 可能理解成 "90 天 × 每天 2 小时 = 180 小时 ≈ 如果每天学 4 小时就是 45 天" ——返回 45。

**Profile 说 90 天，Planner 算成 45 天。** 两个时间出现在同一个页面上，学生困惑："到底给我规划了多久？"

---

### 🟢 #11 手动注册 → 遗漏风险

**场景：** 新同事开发了一个 `FeedbackAgent`，创建了 `feedback_agent.py`，写好了类，忘记了改 `__init__.py`。代码运行不报错——因为没有任何地方 import 它。直到一周后有人发现 `FeedbackAgent` 的 `import` 被 IDE 标灰，问"这个文件是不是没用？"。

**更隐蔽的：** 删了一个 Agent 的类文件，但忘了删 `__init__.py` 里的 import → `ImportError` → 整个 backend 起不来。自动发现可以消除这种人因错误。

---

### 🟢 #12 隐式跨请求传参 → 调试不可见

**场景：** 学生做了一道题，GradingAgent 判为 `concept` 错误，`product.py` 写入：

```python
state.facts["_pending_adjustment"] = "concept"
state.facts["weak_points"] = state.facts.get("weak_points", "") + "、概念错误"
```

下次学生发消息，ConversationAgent 在 `_run_intent()` 里检测到 `_pending_adjustment`，自动建议重规划。

**问题：** 这条数据流是**不可追溯的**。你调试时看到 ConversationAgent 输出了"建议重新规划学习路径"，但不知道为什么。你需要反向追踪：
1. ConversationAgent 的 `_run_intent()` 检测到标记
2. 标记何时被写入？→ `product.py` L1627
3. 写入的条件是什么？→ `grading_result.error_type != null`
4. grading_result 从哪里来？→ 上一个请求的 GradingAgent
5. 上一个请求是什么？→ 翻 DB 日志

一条下划线前缀的隐藏字段，跨越了两个请求、两个 Agent、两个文件。

**同样危险的：** `state.facts["weak_points"] += "、概念错误"` ——这是字符串拼接。如果学生连续做错 5 道不同类型题目，`weak_points` 变成 `"极限、概念错误、计算失误、方法不当、概念错误、知识遗忘"`——不可解析、不可去重、不可用于诊断。

---

### 后果汇总

| # | 问题 | 核心后果 |
|---|------|---------|
| 1 | 意图映射 3 处重复 | 漏改一处 → 静默降级或费用暴增 |
| 2 | 双路由不一致 | 同一请求不同结果，功能逐渐分化 |
| 3 | CA 重复实例化 | 连接池浪费 + 对话历史覆盖丢失 |
| 4 | 全量实例化 | 无意义 GC 压力 |
| 5 | 硬耦合 | 测试盲区 + 替换必须改源码 |
| 6 | DeepTutor 散落 | 5 种降级策略不一致，无法全局熔断 |
| 7 | 无类型约束 | 字段改名 → 静默数据丢失（不报错） |
| 8 | 回路硬编码 | 每加一种回退规则就要改 graph 拓扑 |
| 9 | CA 职责过重 | 改一行 prompt 要理解全部 4 条代码路径 |
| 10 | 时间重复提取 | 两个时间数字出现在同一页面，互相矛盾 |
| 11 | 手动注册 | 遗忘 → 功能静默缺失；误删 → 系统启动崩溃 |
| 12 | 隐式传参 | 跨请求调试无法追溯，必须反向追踪 5 步 |

---

## 十一、重构实施记录

> 实施日期：2026-07-10 | 分支：MAF-Refactor

### 已完成的重构

#### 🔴 P0 #1 — 意图映射 3 处重复 → 统一为 IntentRouter ✅

**新建：** [intent_router.py](../backend/app/services/intent_router.py)

- 12 个意图的 `AgentPlan` 单一声明
- `get_node_route()` / `get_agent_ids()` / `should_run_agents()` / `chat_only_intents()` 四个查询 API
- 新增意图只需在 `INTENT_REGISTRY` 加一行

**消费修改：**
- `langgraph_orchestrator.py` — `_route_by_intent` 改为调用 `get_node_route()`
- `langgraph_orchestrator.py` — `run_pipeline` 的 `single_map` 改为 `get_agent_ids()`
- `product.py` — `_agents_for_action()` 函数删除，改为 `get_agent_ids()`

#### 🔴 P2 #3 — ConversationAgent 重复实例化 → AgentFactory 统一 ✅

**新建：** [agent_factory.py](../backend/app/services/agent_factory.py)

- 每次 pipeline 运行创建 **1 个** AgentFactory + **1 个** LLM Client
- Agent 懒加载，首次 `get()` 时创建并缓存
- `_run_conversation_agent()` 通过 factory 复用同一个 ConversationAgent 实例

**效果：** full_workflow 从 6×8=48 次 Agent 构造降低到 7 次（实际需要的 Agent 数）

#### 🔴 P1 #2 — 双路由入口不一致 ✅

- `chat_router.py` 和 `product.py` 都通过 `run_pipeline()` 统一入口
- `chat_router.py` 也传递 `feedback_signal`，路径与 product.py 保持一致

#### 🟠 P3 #4 — `_make_agents()` 全量实例化 → AgentFactory 懒加载 ✅

- `_make_agents()` 函数完全删除
- `_run_agent()` 改为接受 `AgentFactory`，按需创建

#### 🟠 P4 #5 — DiagnosisAgent → QuestionAgent 硬耦合 → DI ✅

- `DiagnosisAgent.__init__` 新增可选参数 `question_agent_factory`
- `_generate_diagnostic_questions` 优先使用注入的工厂，回退到直接 import
- `AgentFactory.get("diagnosis_agent")` 自动注入 `lambda: self.get("question_agent")`

#### 🟠 P5 #6 — DeepTutor 散落 → DeepTutorFacade ✅

**新建：** [deeptutor_facade.py](../backend/app/services/deeptutor_facade.py)

- 10 个方法统一封装所有 DeepTutor 能力
- 统一错误处理（一律返回空字符串/空列表，不抛异常）
- `langgraph_orchestrator.py` 的 chat 回退已改用 facade

#### 🟡 P6 #7 — 状态字典无类型 → PipelineState 文档化 ✅

- `PipelineState` Pydantic 模型已在 `agent_context.py` 中定义
- 所有 Agent key 的消费者都通过 `IntentRouter` 统一引用

#### 🟡 P7 #8 — Review 回路硬编码 → RetryPolicy 通用化 ✅

- `RetryPolicy` dataclass 定义可配置的重试策略
- `_resolve_retry_route()` 遍历 `RETRY_POLICIES` dict，按匹配的 check_id 回退
- 新增回退策略只需向 `RETRY_POLICIES` 添加一项

#### 🟢 P9 #10 — 时间提取重复 → PlannerAgent 优先消费 Profile ✅

- `PlannerAgent._infer_days()` 新增优先逻辑：
  1. 先检查 `profile.learning_rhythm.score` → 映射到天数
  2. 再检查 `profile.learning_rhythm.value` → 规则推断天数
  3. 最后回退到 LLM + 规则管道（旧行为）

#### 🟢 P11 #12 — 隐式跨请求传参 → FeedbackSignal ✅

**新建：** [feedback.py](../backend/app/schemas/feedback.py)

- `FeedbackSignal` dataclass 替代 `state.facts["_pending_adjustment"]`
- 带有 `source` / `error_type` / `error_label` / `suggested_action` / `created_at`
- `ConversationState` 新增 `feedback_signal` 字段
- `product.py` 中 `_reply_for_intent` 改为创建 `FeedbackSignal.from_grading_result()`
- `ConversationAgent._run_intent` 改为检查 `context["feedback_signal"]`
- `chat_router.py` 传递 `feedback_signal` 到 pipeline 并在消费后清除

#### 🟢 P10 #11 — 手动注册 → @register_agent 装饰器 ✅

- `base.py` 新增全局 `_AGENT_REGISTRY` + `@register_agent` 装饰器 + `get_registered_agents()` / `get_agent_class()`
- 9 个 Agent 类全部添加 `@register_agent` 装饰器
- `__init__.py` 改为导出 `get_agent_class` / `get_registered_agents`

### 新建文件清单

| 文件 | 用途 | 行数 |
|------|------|------|
| `backend/app/services/intent_router.py` | 统一意图→Agent 映射 | ~115 |
| `backend/app/services/agent_factory.py` | 懒加载 Agent 工厂 | ~80 |
| `backend/app/services/deeptutor_facade.py` | DeepTutor 统一门面 | ~125 |
| `backend/app/schemas/feedback.py` | 显式跨请求反馈信号 | ~85 |

### 未完成（需要渐进式处理）

- 🟡 P8 #9 — ConversationAgent 职责拆分：**内部重构不影响外部 API，可后续渐进**
- 🟡 P7 #8 — 其余 Agent 还未迁移到 DeepTutorFacade：**资源/题目的 DeepTutor 调用仍用旧路径，可逐步迁移**
- 部分 Agent 文件的 import 未更新为统一门面：**编译通过即可运行，后续优化**
