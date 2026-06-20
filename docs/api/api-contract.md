# Runtime Kit API Contract

## 1. Base URLs

Frontend:

```text
http://localhost:5173
```

Backend:

```text
http://localhost:8001
```

The backend keeps two layers of APIs:

1. Core orchestration API for the module workflow.
2. Product APIs used directly by the React frontend.

## 2. Core API

### POST /api/agents/run

Purpose: run the complete module workflow.

Request:

```json
{
  "session_id": "demo_session_001",
  "course_id": "ai_intro",
  "user_message": "我是软件工程大三学生，想十天学懂神经网络，希望多给代码实验和图解。"
}
```

Response envelope:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "session_id": "demo_session_001",
    "course_id": "ai_intro",
    "user_message": "...",
    "profile": {},
    "knowledge_context": {},
    "diagnosis": {},
    "learning_path": [],
    "resources": [],
    "agent_steps": [],
    "review": {}
  },
  "request_id": "req_agents_run"
}
```

This API is the backend source of truth. Product APIs may transform its result for frontend pages.

## 3. Product APIs For React Frontend

### POST /chat/stream

Purpose: streaming chat entry. The React chat page calls this API.

Request:

```json
{
  "sessionId": "frontend_session_001",
  "message": "我是电子信息大二学生，Python基础一般，想两周入门人工智能。"
}
```

Response: Server-Sent Events.

```text
data: {"content":"正在启动工作流处理流程...\n","done":false}

data: {"content":"## 学习方案已生成\n","done":false}

data: {"done":true}
```

### POST /chat/send

Purpose: non-streaming chat fallback.

Response:

```json
{
  "sessionId": "frontend_session_001",
  "reply": {
    "id": "assistant_msg_001",
    "role": "assistant",
    "content": "## 学习方案已生成...",
    "timestamp": 1781321459000
  }
}
```

### GET /profile

Purpose: get the current student profile. Reads from database — never triggers agents. Returns empty structure with `source: "none"` when no data exists.

Query: `?sessionId=frontend_session_001`

Response:

```json
{
  "profile": {
    "id": "frontend_session_001",
    "learnerId": null,
    "nickname": "学习者",
    "createdAt": 1781235059000,
    "updatedAt": 1781321459000,
    "dimensions": [],
    "weaknesses": [],
    "preferences": {
      "preferredFormats": ["text"],
      "paceMinutes": 45,
      "difficulty": "beginner",
      "explainStyle": "text"
    },
    "history": {
      "totalStudyMinutes": 0,
      "completedTopics": [],
      "quizAccuracy": null,
      "streak": 0,
      "lastStudyDate": 0
    },
    "source": "db",
    "readiness": {
      "filledCount": 3,
      "totalCount": 7,
      "score": 0.43,
      "missingCore": ["background"],
      "readyToPlan": false
    }
  }
}
```

The `source` field indicates data provenance: `"db"` (from SQLite), `"agent"` (in-memory last result), `"none"` (no data yet).

### POST /profile/build

Purpose: build or refresh the student profile from a new message. This triggers the full workflow pipeline and persists results.

Request:

```json
{
  "sessionId": "frontend_session_001",
  "message": "我是软件工程大三学生，线性代数比较弱，想十天学懂神经网络。"
}
```

Response:

```json
{
  "profile": {
    "id": "frontend_session_001",
    "learnerId": null,
    "nickname": "学习者",
    "dimensions": [...],
    "weaknesses": [...],
    "preferences": {...},
    "history": {...},
    "source": "agent",
    "readiness": {"filledCount": 4, "totalCount": 7, "readyToPlan": true}
  }
}
```

### PATCH /profile

Purpose: update profile fields directly (client-side edits).

Request:

```json
{
  "sessionId": "frontend_session_001",
  "nickname": "新昵称"
}
```

Response:

```json
{
  "profile": {...}
}
```

### GET /learning-path

Purpose: get the current study path. Reads from database — never triggers agents.

Query: `?sessionId=frontend_session_001`

Response:

```json
{
  "path": {
    "id": "path_ai_intro",
    "title": "人工智能导论学习路径",
    "description": "采用先概念、再图解、再代码实验的学习策略",
    "courseName": "人工智能导论",
    "courseId": "ai_intro",
    "stages": [
      {
        "id": "stage_1",
        "order": 1,
        "title": "补齐机器学习基础",
        "description": "第 1-3 天",
        "nodes": [
          {
            "id": "stage_1_node_1",
            "topic": "阅读机器学习基础讲义",
            "status": "available",
            "prerequisites": [],
            "resources": [...]
          }
        ],
        "objective": "理解监督学习、特征、损失函数",
        "estimatedDays": 3
      }
    ],
    "createdAt": 1781321459000,
    "overallProgress": 18,
    "estimatedDays": 14,
    "source": "db"
  }
}
```

### POST /learning-path/generate

Purpose: trigger agent pipeline to generate a new learning path based on current profile.

Request:

```json
{
  "sessionId": "frontend_session_001"
}
```

Response:

```json
{
  "path": {...}
}
```

### PATCH /learning-path/nodes/{node_id}

Purpose: update the progress/status of a learning path node.

Request:

```json
{
  "sessionId": "frontend_session_001",
  "status": "completed"
}
```

Response:

```json
{
  "ok": true
}
```

### GET /learner/{learner_id}

Purpose: get learner details with aggregated profile across all learning sessions.

Response:

```json
{
  "learner": {
    "id": "learner_001",
    "nickname": "学习者",
    "createdAt": 1781235059000,
    "updatedAt": 1781321459000,
    "sessionCount": 3,
    "sessions": [
      {"id": "session_001", "title": "未命名会话", "status": "active"}
    ],
    "aggregatedProfile": {
      "dimensions": [...],
      "weaknesses": [...],
      "totalStudyMinutes": 120
    }
  }
}
```

### GET /resources

Purpose: get generated learning resources. Reads from database — never triggers agents.

Query: `?sessionId=frontend_session_001`

Response:

```json
{
  "resources": [
    {
      "id": "res_lecture_001",
      "type": "lecture",
      "title": "机器学习基础入门讲义",
      "description": "适合具备 Python 基础但机器学习较薄弱的学生",
      "content": "## 1. 为什么要先学机器学习基础...",
      "knowledgePoints": ["stage_1"],
      "tags": ["markdown", "mock"],
      "difficulty": "easy",
      "estimatedMinutes": 20,
      "format": "text",
      "mermaidDef": null,
      "codeBlocks": null,
      "questions": null,
      "pptOutline": null,
      "createdAt": 1781321459000,
      "bookmarked": false,
      "studyStatus": "new",
      "source": "db"
    }
  ],
  "total": 6,
  "page": 1,
  "sessionId": "frontend_session_001"
}
```

Resource `type` values: `lecture`, `mindmap`, `quiz`, `reading`, `practice` (case_study), `multimodal` (video script).

Resource `format` values: `text`, `diagram` (for mindmap mermaid content), `code` (for practice).

### POST /resources/generate

Purpose: trigger agent pipeline to generate a new resource on a topic.

Request:

```json
{
  "sessionId": "frontend_session_001",
  "topic": "链表",
  "type": "quiz"
}
```

Response:

```json
{
  "resource": {...}
}
```

### POST /resources/{resource_id}/bookmark

Purpose: toggle the bookmarked state of a resource.

Query: `?sessionId=frontend_session_001`

Response:

```json
{
  "bookmarked": true
}
```

### GET /resources/{resource_id}/knowledge-graph

Purpose: get the Mermaid mindmap definition for a resource.

Response:

```json
{
  "mermaidDef": "mindmap\n  root((人工智能导论))\n    ..."
}
```

### GET /chat/sessions

Purpose: list all active chat sessions.

Response:

```json
{
  "sessions": [
    {
      "id": "frontend_session_001",
      "title": "未命名会话",
      "status": "active",
      "createdAt": 1781235059000,
      "updatedAt": 1781321459000
    }
  ]
}
```

### GET /chat/sessions/{session_id}

Purpose: get all messages for a specific session.

Response:

```json
{
  "sessionId": "frontend_session_001",
  "messages": [
    {
      "id": "msg_1",
      "role": "user",
      "content": "你好",
      "timestamp": 1781235059000
    }
  ]
}
```

### POST /chat/sessions/{session_id}/reset

Purpose: reset a session — clears all messages and profile/path/resource data.

Response:

```json
{
  "ok": true,
  "sessionId": "frontend_session_001"
}
```

### GET /chat/quick-commands

Purpose: get suggested quick-start prompts for the chat page.

Response:

```json
{
  "commands": [
    {"id": "ai_intro", "label": "AI 入门", "icon": "AI", "prompt": "我是大二学生，想两周入门人工智能"},
    {"id": "data_structures", "label": "数据结构", "icon": "DS", "prompt": "我是软件工程大二学生，想复习数据结构"}
  ]
}
```

### GET /chat/progress/{task_id}

Purpose: get mock generation progress indicator (for UI display during agent runs).

Response:

```json
{
  "progress": {
    "stage": "工作流生成中",
    "progress": 100,
    "agentName": "runtime-kit",
    "detail": "task_001"
  }
}
```

### POST /feedback

Purpose: submit general learning feedback.

Request:

```json
{
  "sessionId": "frontend_session_001",
  "content": "这道题太简单了"
}
```

Response:

```json
{
  "ok": true
}
```

### POST /feedback/event

Purpose: record learning behavior events for tracking and evaluation.

Request:

```json
{
  "event": "resource_view",
  "resourceId": "res_lecture_001",
  "duration": 5,
  "metadata": {
    "page": "resources"
  }
}
```

Response:

```json
{
  "ok": true
}
```

### GET /learning-analytics

Purpose: return basic learning behavior analytics.

Response:

```json
{
  "eventCount": 1,
  "totalStudyMinutes": 5,
  "recentEvents": [],
  "summary": "已接入学习事件追踪，可用于后续动态调整画像、资源推荐和学习路径。"
}
```

## 4. Agent Workflow

Current agent pipeline (6 agents, orchestrated by `AgentOrchestrator`):

```text
IntentAgent (pre-pipeline: classifies user intent)
  ↓
ProfileAgent        — extracts 8-dimension student profile (real LLM when DEEPSEEK configured)
  ↓
KnowledgeAgent      — retrieves course knowledge points (mock)
  ↓
DiagnosisAgent      — identifies weak knowledge points (mock)
  ↓
PlannerAgent        — generates staged learning path (mock)
  ↓
ResourceAgent       — generates 6 resource types (mock)
  ↓
ReviewAgent         — quality-checks outputs (mock)
```

`IntentAgent` classifies the user input before the system starts a workflow. It uses a lightweight semantic-router design:

```text
high-confidence rules
-> route example similarity
-> LLM JSON classification fallback
-> low-confidence clarification
```

Supported intents (from `intent_routes.py`):

```text
casual_chat, date_query, clarification, info_request,
profile_query, profile_update, start_advice,
learning_plan, tutoring, resource_request,
progress_feedback, unsafe, unknown
```

### Stage 2 Orchestration Features

- **Per-agent error isolation**: one agent failure does not crash the pipeline; results are returned with `overall_status: "partial"`.
- **Per-agent timeout**: configurable via `agent_timeout` (default 60s), enforced via `ThreadPoolExecutor`.
- **Structured step tracking**: each agent step records `agent_id`, `status`, `duration_ms`, `error` (if any).
- **Partial result aggregation**: successful agent outputs are merged; failed agents provide empty fallback structures.

### LLM Integration

`ProfileAgent` and `ResourceAgent` receive the LLM client. When `LLM_PROVIDER=deepseek`, they call the DeepSeek API with retry logic (`llm_retry_count` configurable). When `LLM_PROVIDER=mock`, they return deterministic mock responses. Other agents use mock data and will be upgraded to real LLM generation per the mock-to-real roadmap.

## 5. Development Rules

- React frontend calls Product APIs.
- Backend agents keep `/api/agents/run` stable.
- API changes must be updated here first.
- Frontend and backend should not invent new fields independently.


---

## 4. 多科目架构 (Multi-Subject Architecture) — v0.3.0

### 4.1 核心概念

```
Account (用户)
  └── Subject A (科目A, e.g. "数据结构")
  │     ├── Conversations (对话列表)
  │     │     ├── Session 1 (对话1)
  │     │     └── Session 2 (对话2)
  │     ├── Profile (科目画像)
  │     ├── Learning Path (学习路径)
  │     └── Resources (资源库)
  │
  └── Subject B (科目B, e.g. "人工智能导论")
        ├── Conversations
        ├── Profile
        ├── Learning Path
        └── Resources
```

### 4.2 数据模型

#### Subject
```json
{
  "id": "subject_001",
  "learnerId": "learner_abc",
  "name": "数据结构",
  "description": "",
  "createdAt": 1781235059000,
  "updatedAt": 1781321459000,
  "status": "active"
}
```

#### Session (对话，属于某科目)
```json
{
  "id": "session_001",
  "subjectId": "subject_001",
  "learnerId": "learner_abc",
  "title": "链表练习题",
  "firstMessage": "帮我生成链表相关的练习题",
  "messageCount": 12,
  "createdAt": 1781235059000,
  "updatedAt": 1781321459000
}
```

### 4.3 新增 API

#### 科目管理

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/subjects?learnerId=xxx` | 获取用户的所有科目 |
| POST | `/api/subjects` | 创建新科目 |
| PATCH | `/api/subjects/{subjectId}` | 更新科目信息 |
| DELETE | `/api/subjects/{subjectId}` | 删除科目 |

**POST /api/subjects**
```json
// Request
{
  "learnerId": "learner_abc",
  "name": "数据结构"
}

// Response
{
  "subject": {
    "id": "subject_001",
    "learnerId": "learner_abc",
    "name": "数据结构",
    "status": "active",
    "createdAt": 1781235059000,
    "updatedAt": 1781321459000
  }
}
```

#### 科目内对话

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/subjects/{subjectId}/sessions` | 获取科目下的对话列表 |
| POST | `/api/subjects/{subjectId}/sessions` | 在科目下创建新对话 |
| GET | `/api/subjects/{subjectId}/sessions/{sessionId}` | 获取对话消息 |
| DELETE | `/api/subjects/{subjectId}/sessions/{sessionId}` | 删除对话 |

**GET /api/subjects/{subjectId}/sessions**
```json
// Response
{
  "sessions": [
    {
      "id": "session_001",
      "title": "链表练习题",
      "messageCount": 12,
      "createdAt": 1781235059000,
      "updatedAt": 1781321459000
    }
  ]
}
```

**POST /api/subjects/{subjectId}/sessions**
```json
// Request
{
  "title": "链表练习题"
}

// Response
{
  "session": { "...": "..." }
}
```

#### 科目内数据隔离

所有已有 API 增加 `subjectId` 参数：

| 原 API | 新路径/参数 |
|--------|------------|
| `GET /profile?sessionId=xxx` | `GET /api/subjects/{subjectId}/profile` |
| `GET /learning-path?sessionId=xxx` | `GET /api/subjects/{subjectId}/learning-path` |
| `GET /resources?sessionId=xxx` | `GET /api/subjects/{subjectId}/resources` |
| `POST /chat/stream` | 新增 `subjectId` 字段 |
| `GET /chat/sessions/{sessionId}` | `GET /api/subjects/{subjectId}/sessions/{sessionId}` |

#### 科目内画像

**GET /api/subjects/{subjectId}/profile**
```json
// Response
{
  "profile": {
    "subjectId": "subject_001",
    "learnerId": "learner_abc",
    "dimensions": [],
    "weaknesses": [],
    "preferences": {},
    "updatedAt": 1781321459000,
    "source": "db"
  }
}
```

#### 流式对话 (增加 subjectId)

**POST /chat/stream** (增强版)
```json
// Request
{
  "subjectId": "subject_001",
  "sessionId": "session_001",
  "message": "给我生成链表练习题"
}
```
后端根据 `subjectId` 加载该科目的画像、路径和资源上下文，
再调用智能体生成回复。回复内容会自动关联到该科目。

### 4.4 前端数据流

```
登录 → 获取科目列表 GET /api/subjects
  → 选择/创建科目
    → 进入科目工作台：
      → 加载科目画像  GET /api/subjects/{id}/profile
      → 加载科目路径  GET /api/subjects/{id}/learning-path
      → 加载科目资源  GET /api/subjects/{id}/resources
      → 加载对话列表  GET /api/subjects/{id}/sessions
        → 选择对话 → 加载消息
        → 新建对话 → POST /api/subjects/{id}/sessions
          → 发送消息 POST /chat/stream (带 subjectId + sessionId)
```

### 4.5 前端存储 (localStorage)

```json
// eduagent_active_subject
{ "id": "subject_001", "name": "数据结构" }

// eduagent_subject_{learnerId}
[{ "id": "subject_001", "name": "数据结构", ... }]
```

### 4.6 迁移策略

1. **第一阶段** (当前): 所有数据挂在一个默认科目下 (`subject_default`)
2. **第二阶段** (目标): 前端先做科目切换 UI，后端逐步实现按 subjectId 隔离
3. 向后兼容: 不带 `subjectId` 的请求默认使用 `subject_default`
