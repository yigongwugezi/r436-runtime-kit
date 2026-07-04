# OpenClaw 集成方案（详细版）

## 一、目标

用 OpenClaw 替换当前后端路由里的意图判断和 Agent 调度逻辑，实现真正的多 Agent 协同。前端 15 个页面不动，后端路由壳不动，只改中间调度层。

## 二、新架构

```
浏览器 :5173
   │
   ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI 后端 :8080                                 │
│                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ 路由壳 (不动) │  │ agent_proxy  │  │ grade_proxy│ │
│  │ product.py  │  │ (不动)       │  │ (不动)     │ │
│  │ auth.py     │  └──────┬───────┘  └─────┬──────┘ │
│  │ …           │         │               │        │
│  └──────┬──────┘         │               │        │
│         │                │               │        │
│         ▼                ▼               ▼        │
│  ┌─────────────────────────────────────────────┐   │
│  │         OpenClaw 桥接层（新增）               │   │
│  │  openclaw_bridge.py                         │   │
│  │                                             │   │
│  │  · 接收前端请求 → 转为 OpenClaw 任务         │   │
│  │  · OpenClaw 返回结果 → 转回前端格式          │   │
│  │  · 管理 SSE 流式进度推送                    │   │
│  └─────────────────┬───────────────────────────┘   │
│                    │ HTTP + SSE                     │
└────────────────────┼────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│  OpenClaw 编排层 :8400（新增 Node.js 进程）          │
│                                                     │
│  edu_workflow.yaml  — 协同工作流定义                 │
│  agents.yaml        — 外部 Agent 注册                │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │  Agent 协同引擎                              │    │
│  │                                             │    │
│  │  画像更新 ──→ Planner 重规划                 │    │
│  │  批改完成 ──→ Profiler 更新画像              │    │
│  │  错误检测 ──→ Resource 生成补救材料          │    │
│  │  资源生成 ──→ Check 质量审核                 │    │
│  │  全部完成 ──→ 前端一次性推送                 │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────┐ ┌──────────┐   │
│  │DeepTutor │ │Socratic  │ │GRADE │ │ OpenMAIC │   │
│  │HTTP Tool │ │HTTP Tool │ │Tool  │ │   Tool   │   │
│  └────┬─────┘ └────┬─────┘ └──┬───┘ └────┬─────┘   │
└───────┼────────────┼──────────┼──────────┼─────────┘
        │            │          │          │
        ▼            ▼          ▼          ▼
   :8000         :8001       :8002       :8003
  DeepTutor    Socratic     GRADE      OpenMAIC
  (Python)     Profiler     Agent      (Node.js)
               (Python)    (Python)
```

## 三、前端 15 个页面的数据适配

| 页面 | 当前数据源 | 改后数据源 | 改什么 |
|------|-----------|-----------|--------|
| ChatPage | `POST /api/chat/send` | 同上，路由不变 | 不改 |
| ProfilePage | `GET /api/profile` | 同上，路由不变 | 不改（已有 Socratic 兜底） |
| LearningPathPage | `GET /api/learning-path` | 同上 | 不改（已有 agent_proxy 兜底） |
| ResourceLibrary | `GET /api/resources` | 同上 | 不改（已有 agent_proxy 兜底） |
| ResourceGenerationPage | `POST /api/chat/send` | 同上 | 不改 |
| PracticePage | `POST /api/questions/…/grade` | `POST /api/grade-proxy/assess` | 改 API 调用 |
| LearningAnalyticsPage | `GET /api/learning-analytics` | 同上 | 不改（已有 GRADE 兜底） |
| LearningTimelinePage | `GET /api/learning-analytics` | 同上 | 不改 |
| Home | — | — | 不改 |
| SettingsPage | — | — | 不改 |
| ConversationHistoryPage | `GET /api/chat/sessions` | 同上 | 不改 |
| LoginPage | `POST /api/auth/*` | 同上 | 不改 |
| TeacherHome | — | — | 不改 |
| TeacherClassDetail | — | — | 不改 |
| AdminDashboard | — | — | 不改 |
| ReviewQueuePage | — | — | 不改 |
| NotFound | — | — | 不改 |

**结论：15 个页面中 14 个不改，只有 PracticePage 的批改 API 从旧路由切到 grade-proxy。**

## 四、后端改动

### 4.1 chat/send 路由 — 接 OpenClaw 桥

`product.py` 的 `_classify_intent` 和 `send_chat` 改为通过 `openclaw_bridge` 转发：

```python
# product.py - send_chat（伪代码）
def send_chat(message, session_id):
    # 不再自己做意图分类，全部交给 OpenClaw
    result = openclaw_bridge.process_message(message, session_id)
    return result.reply, result.action
```

### 4.2 openclaw_bridge.py — 新增核心模块

```python
# backend/app/services/openclaw_bridge.py
"""OpenClaw 桥接层 — Python → Node.js OpenClaw 编排引擎"""

class OpenClawBridge:
    def process_message(self, message, session_id):
        """发消息给 OpenClaw，阻塞等待结果"""
        resp = httpx.post(f"{OPENCLAW_URL}/process", json={
            "message": message,
            "session_id": session_id,
        }, timeout=120)
        return resp.json()
    
    def process_stream(self, message, session_id):
        """SSE 流式：OpenClaw 每个 Agent 执行完就推一次事件"""
        with httpx.stream("POST", f"{OPENCLAW_URL}/process/stream", ...) as resp:
            for line in resp.iter_lines():
                yield json.loads(line)  # {agent, status, progress, partial_result}
```

### 4.3 SSE 流式进度

前端对话页已有 SSE 接收能力。OpenClaw 执行多 Agent 时实时推送：

```
event: agent_start
data: {"agent": "Socratic Profiler", "status": "running"}

event: agent_progress  
data: {"agent": "Socratic Profiler", "progress": 50}

event: agent_complete
data: {"agent": "Socratic Profiler", "result": {...}}

event: agent_start
data: {"agent": "DeepTutor Planner", "status": "running"}

...

event: workflow_complete
data: {"reply": "已为你生成学习路径…", "resources": [...], "profile": {...}}
```

### 4.4 改动的文件清单

| 文件 | 操作 | 说明 |
|------|:--:|------|
| `backend/app/routers/product.py` | 改 | `_classify_intent` 替换为 bridge 调用 |
| `backend/app/services/openclaw_bridge.py` | **新增** | OpenClaw HTTP 桥接 |
| `backend/app/routers/agent_proxy.py` | 不动 | 已连 DeepTutor/Socratic/GRADE |
| `backend/app/routers/grade_proxy.py` | 不动 | 已连 GRADE Agent |
| `backend/app/main.py` | 改 | 注册 bridge 服务 |
| `frontend/src/api/chat.ts` | 不动 | SSE 流式接口不变 |
| `frontend/src/pages/PracticePage.tsx` | 改 | 批改 API 切到 grade-proxy |

## 五、OpenClaw 编排层（全部新增）

### 5.1 项目结构

```
external_agents/openclaw_workspace/
├── package.json
├── openclaw.config.yaml        # OpenClaw 主配置
├── agents/
│   ├── deeptutor.agent.yaml    # DeepTutor HTTP Tool 注册
│   ├── socratic.agent.yaml     # Socratic Profiler 注册
│   ├── grade.agent.yaml        # GRADE Agent 注册
│   └── openmaic.agent.yaml     # OpenMAIC 注册
├── workflows/
│   └── edu_workflow.yaml       # 协同工作流定义
├── server.js                   # OpenClaw HTTP API 入口
└── events/
    └── edu_events.js           # 事件驱动协同规则
```

### 5.2 Agent 注册示例

```yaml
# agents/socratic.agent.yaml
agent:
  id: socratic_profiler
  name: "学生画像 Agent"
  role: "教育心理学家，从对话和批改结果中构建6维动态学生画像"
  trigger_keywords: ["画像", "诊断", "薄弱", "水平", "基础"]
  tools:
    - name: analyze_profile
      endpoint: http://localhost:8001/api/profile/analyze
      method: POST
    - name: get_profile
      endpoint: http://localhost:8001/api/profile/{student_id}
      method: GET
    - name: update_from_grading
      endpoint: http://localhost:8001/api/profile/update
      method: POST
  
  output_events:
    - profile_updated    # 画像变更事件
    - weakness_detected  # 薄弱点发现事件

# agents/deeptutor.agent.yaml
agent:
  id: deeptutor
  name: "DeepTutor 主引擎"
  role: "学习辅导核心，提供对话、规划、资源生成、答疑"
  trigger_keywords: ["规划", "路径", "资源", "怎么学", "不会", "请问"]
  tools:
    - name: chat
      endpoint: http://localhost:8000/api/v1/partners/eduagent/chat
      method: POST
    - name: get_path
      endpoint: http://localhost:8000/api/v1/partners/eduagent/sessions
      method: GET
  dependencies: [socratic_profiler]  # 需要先有画像
```

### 5.3 协同工作流

```yaml
# workflows/edu_workflow.yaml
workflows:
  
  # 新对话：画像 → 规划 → 资源 → 审核
  new_learning_request:
    trigger: ["规划", "路径", "怎么学", "入门", "学习"]
    steps:
      - agent: socratic_profiler
        tool: analyze_profile
        on_complete: store_as("profile")
      - agent: deeptutor
        tool: chat
        input: 
          content: "根据画像规划路径：{{profile}}。学生需求：{{message}}"
        on_complete: store_as("plan_reply")
      - agent: deeptutor
        tool: chat
        input:
          content: "生成学习资源：{{plan_reply}}"
        on_complete: store_as("resources")
      - agent: deeptutor
        tool: chat
        input:
          content: "审核以下资源：{{resources}}"
        on_complete: store_as("review")
    output:
      reply: "{{plan_reply}}"
      profile: "{{profile}}"
      resources: "{{resources}}"
      stages: "{{plan_reply.stages}}"
      review: "{{review}}"
  
  # 批改：批改 → 更新画像 → 可能生成补救
  grading_request:
    trigger: ["批改", "判分", "对不对", "练习"]
    steps:
      - agent: grade_agent
        tool: assess_answer
        on_complete: store_as("grading")
      - agent: socratic_profiler
        tool: update_from_grading
        input: "{{grading}}"
        condition: "grading.error_type != 'null'"
        on_complete: store_as("updated_profile")
      - agent: deeptutor
        tool: chat
        input: "学生错误类型是{{grading.error_type}}，生成针对性补救练习"
        condition: "grading.total_score < 60"
        on_complete: store_as("remedial_resources")
    output:
      grading: "{{grading}}"
      profile: "{{updated_profile}}"
      remedial: "{{remedial_resources}}"

  # 纯对话：直接转 DeepTutor
  casual_chat:
    trigger: []
    steps:
      - agent: deeptutor
        tool: chat
        input: "{{message}}"
    output:
      reply: "{{steps[0].content}}"
```

### 5.4 OpenClaw HTTP Server（Node.js）

```javascript
// server.js
const express = require('express');
const app = express();

// POST /process — 阻塞式，等全部 Agent 执行完
app.post('/process', async (req, res) => {
    const { message, session_id } = req.body;
    const workflow = matchWorkflow(message);  // 匹配工作流
    const result = await executeWorkflow(workflow, { message, session_id });
    res.json(result);
});

// POST /process/stream — SSE 流式，每个 Agent 执行时推送
app.post('/process/stream', async (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream');
    const { message, session_id } = req.body;
    const workflow = matchWorkflow(message);
    
    for await (const step of executeWorkflowStream(workflow, { message, session_id })) {
        res.write(`data: ${JSON.stringify(step)}\n\n`);
    }
    res.write('data: [DONE]\n\n');
    res.end();
});

app.listen(8400);
```

## 六、完整请求生命周期对比

### 改前（当前）

```
学生说"帮我规划神经网络学习路径"
  → 后端 _classify_intent → 规则判 action=plan
  → 后端调 DeepTutor Partner chat
  → DeepTutor 内部 6 Agent 处理
  → 返回对话回复
  → 同步触发 orchestrator → ProfileAgent/KnowledgeAgent
  → 画像存 Socratic Profiler
  → 路径/资源留在 DeepTutor 内部，前端 agent_proxy 兜底读
```

### 改后（OpenClaw）

```
学生说"帮我规划神经网络学习路径"
  → 后端 → OpenClaw Bridge → OpenClaw 编排层
  → OpenClaw 匹配 new_learning_request 工作流
  → Step 1: Socratic Profiler 分析画像
  → Step 2: DeepTutor 用画像+需求生成路径
  → Step 3: DeepTutor 用路径生成资源
  → Step 4: DeepTutor 审核资源
  → SSE 流式推送每步进度给前端
  → 全部完成后一次性返回 {reply, profile, stages, resources}
  → 后端存到对应数据表 / agent_proxy 缓存
```

## 七、实施计划

| 阶段 | 内容 | 时间 |
|------|------|:--:|
| 1 | 安装 OpenClaw + 创建项目结构 | 30 分钟 |
| 2 | 编写 4 个 Agent 注册配置 | 1 小时 |
| 3 | 编写协同工作流定义 | 2 小时 |
| 4 | 编写 server.js（Express HTTP API） | 1 小时 |
| 5 | 编写 openclaw_bridge.py（Python 桥接） | 1 小时 |
| 6 | 改 product.py 的 send_chat | 30 分钟 |
| 7 | 改 PracticePage 批改 API | 30 分钟 |
| 8 | 全流程联调测试 | 2 小时 |
| 9 | 修复前端数据展示问题 | 1 小时 |
| **总计** | | **1.5 天** |

## 八、启动命令

```powershell
# 终端 1-4：四个 Agent 服务（不变）
# 终端 5：OpenClaw 编排层
cd external_agents/openclaw_workspace
npm install
node server.js

# 终端 6：后端
cd backend && python -m uvicorn app.main:app --port 8080

# 终端 7：前端
cd frontend && npm run dev
```

浏览器 `http://localhost:5173`
