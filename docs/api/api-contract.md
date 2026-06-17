# EduAgent API Contract

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

1. Core orchestration API for the multi-agent workflow.
2. Product APIs used directly by the React frontend.

## 2. Core API

### POST /api/agents/run

Purpose: run the complete multi-agent workflow.

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
data: {"content":"正在启动多智能体协同流程...\n","done":false}

data: {"content":"## 个性化学习方案已生成\n","done":false}

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
    "content": "## 个性化学习方案已生成...",
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

Purpose: build or refresh the student profile from a new message. This triggers the full multi-agent pipeline and persists results.

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

Purpose: get the current personalized learning path. Reads from database — never triggers agents.

Query: `?sessionId=frontend_session_001`

Response:

```json
{
  "path": {
    "id": "path_ai_intro",
    "title": "人工智能导论个性化学习路径",
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
    "stage": "多智能体生成中",
    "progress": 100,
    "agentName": "EduAgent",
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
