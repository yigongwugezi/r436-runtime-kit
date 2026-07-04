# EduAgent 用 MAF 替换 OpenClaw 详细方案

## 一、为什么换

| | 当前（自写 Express） | MAF（微软 Agent Framework） |
|--|---------------------|---------------------------|
| 语言 | Node.js | Python（与项目一致） |
| Agent 间通信 | 单向串行调用 | A2A 协议：Agent 间对等对话协商 |
| 容错 | 无 | Checkpoint 断点恢复 |
| 安全 | 无 | 内置内容安全过滤中间件 |
| 编排方式 | 关键词匹配工作流 | 图编排（顺序/并发/条件分支/循环） |
| 可观测 | print 日志 | OpenTelemetry 追踪 |
| 部署 | 独立进程 :8400 | 内嵌后端，不额外占用端口 |
| 协议 | — | MIT |

## 二、架构变化

```
改前：
前端 → 后端 → OpenClaw(:8400 Node.js) → Agent

改后：
前端 → 后端（内嵌 MAF 编排） → Agent
```

删掉一个 Node.js 进程，后端直接编排 Agent。

## 三、文件清单

### 删除

| 文件 | 原因 |
|------|------|
| `external_agents/openclaw_workspace/` | Node.js 编排层，已删 |
| `backend/app/services/openclaw_bridge.py` | 替换为 maf_orchestrator.py |
| `scripts/start_all.ps1` 中 OpenClaw 行 | 不再需要独立进程 |

### 新增

| 文件 | 说明 |
|------|------|
| `backend/app/services/maf_orchestrator.py` | MAF 编排引擎 |

### 修改

| 文件 | 改动 |
|------|------|
| `backend/app/routers/product.py` | `_classify_intent` → 调 MAF；`_agent_worker` → 用 MAF 流式 |
| `backend/app/services/agent_service.py` | `run_agents()` → 调 MAF |
| `scripts/start_all.ps1` | 删 OpenClaw 终端窗口 |
| `backend/requirements.txt` | 加 `agent-framework` |

### 不变（17 个文件）

`frontend/` 全部、`external_agents/deeptutor/`、`external_agents/socratic_profiler/`、`external_agents/grade_agent/`、`external_agents/openmaic/`、`config/`、`docker-compose.yml`、`.env`、`integrations/`、`knowledge_base/`、`runtime_data/`、`backend/app/routers/auth.py`、`backend/app/routers/agent_proxy.py`、`backend/app/routers/grade_proxy.py`、`backend/app/main.py`

## 四、MAF 编排引擎设计

### 4.1 四种 Agent 注册

```python
from agent_framework import Agent, tool

# Agent 1: DeepTutor — 主引擎
deeptutor = Agent(
    id="deeptutor",
    name="DeepTutor 主引擎",
    description="学习辅导核心，内部6Agent协同（Investigate/Note/Plan/Manager/Solve/Check）",
    tools=[
        tool(chat, "对话交互"),
        tool(generate_plan, "生成学习路径"),
        tool(generate_resources, "生成学习资源"),
        tool(solve_question, "智能答疑"),
        tool(review_content, "内容审核"),
    ]
)

# Agent 2: Socratic Profiler — 画像
socratic = Agent(
    id="socratic_profiler",
    name="学生画像 Agent",
    description="教育心理学家，构建6维动态学生画像",
    tools=[
        tool(analyze_profile, "分析学生画像"),
        tool(get_profile, "读取画像"),
        tool(update_weak_points, "更新易错点"),
    ]
)

# Agent 3: GRADE — 批改
grade = Agent(
    id="grade_agent",
    name="GRADE 批改 Agent",
    description="4维评分（思路/步骤/计算/表达）+5类错误归类",
    tools=[
        tool(assess_answer, "批改作答"),
        tool(get_stats, "学习统计"),
    ]
)

# Agent 4: OpenMAIC — 课件
openmaic = Agent(
    id="openmaic",
    name="OpenMAIC 课件 Agent",
    description="多模态课件：PPT/TTS/动画分镜",
    tools=[
        tool(generate_slides, "生成课件"),
        tool(generate_tts, "语音讲解"),
        tool(export_pptx, "导出PPTX"),
    ]
)
```

### 4.2 六条工作流

```python
from agent_framework import Graph

# 1. 新学习请求：画像 → 规划+资源（一步搞定）
plan_workflow = Graph("new_learning_request")
plan_workflow.add_step(socratic.analyze_profile)      # Step 1
plan_workflow.add_step(deeptutor.generate_all)         # Step 2（合并规划+资源）
plan_workflow.add_step(deeptutor.review_content)       # Step 3 审核

# 2. 补充资源：只调资源生成
regenerate_workflow = Graph("regenerate_resources")
regenerate_workflow.add_step(deeptutor.generate_resources)

# 3. 批改+联动：批改→更新画像→低分出补救
grade_workflow = Graph("grading_request")
grade_workflow.add_step(grade.assess_answer)
grade_workflow.add_step(
    socratic.update_weak_points,
    condition=lambda ctx: ctx["grading"]["error_type"] != "null"
)
grade_workflow.add_step(
    deeptutor.generate_remedial,
    condition=lambda ctx: ctx["grading"]["total_score"] < 60
)

# 4. 诊断：画像+薄弱分析
diagnosis_workflow = Graph("diagnosis_request")
diagnosis_workflow.add_step(socratic.analyze_profile)
diagnosis_workflow.add_step(deeptutor.diagnose)

# 5. 出题：画像→针对性出题
question_workflow = Graph("question_generation")
question_workflow.add_step(socratic.analyze_profile)
question_workflow.add_step(deeptutor.generate_questions)

# 6. 纯对话
chat_workflow = Graph("casual_chat")
chat_workflow.add_step(deeptutor.chat)
```

### 4.3 Agent 间事件驱动协同（MAF 独有）

```python
# GRADE 批改完成后 → 自动通知 Socratic 更新画像
@grade.on_result("assess_answer")
def on_grading_complete(ctx):
    if ctx["result"]["error_type"] != "null":
        # Socratic 自动更新易错点
        yield socratic.update_weak_points(ctx["result"])
        # 如果是概念错误，自动出补救练习
        if ctx["result"]["error_type"] == "concept":
            yield deeptutor.generate_remedial(ctx["result"])

# Socratic 画像更新后 → 自动通知 Planner 调整路径
@socratic.on_result("update_weak_points")
def on_profile_updated(ctx):
    if ctx.get("weak_points_changed"):
        yield deeptutor.replan(ctx["profile"])
```

## 五、启动方式

MAF 内嵌在后端启动时加载。`start_all.ps1` 从 7 个终端减为 6 个：

```
1. DeepTutor          :8000
2. Socratic Profiler  :8001
3. GRADE Agent        :8002
4. OpenMAIC           :8003
5. 后端（内嵌 MAF）   :8080    ← 删掉原来的 :8400
6. 前端               :5173
```

## 六、数据流（不变）

```
前端 → 后端 → MAF 编排 → Agent
              │
              ├─ 画像 → Socratic Profiler SQLite
              ├─ 路径/资源 → DeepTutor sessions
              └─ 批改 → GRADE Agent SQLite
              
agent_proxy 读缓存 → 前端页面展示
```

## 七、实施步骤

| 步骤 | 内容 | 时间 |
|------|------|:--:|
| 1 | pip install agent-framework | 5 分钟 |
| 2 | 写 maf_orchestrator.py（~300 行） | 40 分钟 |
| 3 | 改 product.py 的 _classify_intent + stream | 20 分钟 |
| 4 | 改 agent_service.py 的 run_agents | 5 分钟 |
| 5 | 改 start_all.ps1 删 OpenClaw | 5 分钟 |
| 6 | 联调测试 | 20 分钟 |
| **总计** | | **1.5 小时** |
