# Runtime Kit API Contract

> **sessionId 合约 (v0.2.1)**: `sessionId` 是所有产品 API 的**必填数据归属键**。
> 为空时返回 **HTTP 422**，响应体为完整的错误信封：
> ```json
> {
>   "status": "error",
>   "data": null,
>   "message": "sessionId 不能为空",
>   "detail": "sessionId 不能为空",
>   "code": "MISSING_SESSION_ID",
>   "is_user_error": true,
>   "sessionId": "",
>   "subjectId": ""
> }
> ```
> `subjectId` 仅作为课程上下文参数，**不作为** sessionId 的替代或 fallback。
> 前端始终通过 `chatStore.currentSessionId` 生成并传递唯一 `sessionId`。

> **事件类型校验 (v0.5.0)**: `POST /feedback/event` 的 `event` 字段必须是以下六种类型之一:
> `resource_view`, `resource_complete`, `quiz_result`, `practice_result`, `node_progress`, `feedback`。
> 非法事件类型返回 **HTTP 422**，响应体为:
> ```json
> {
>   "status": "error",
>   "data": null,
>   "message": "不支持的事件类型: xxx",
>   "code": "INVALID_EVENT_TYPE",
>   "is_user_error": true,
>   "sessionId": "",
>   "subjectId": ""
> }
> ```
> `stage_complete` 和 `chat_feedback` 为后端内部事件类型，不通过此公开接口写入。

> **统一响应信封 (v0.4.0)**: 所有 Product API（第 3 节）的响应均包裹在统一信封中：
> ```json
> {
>   "status": "success",
>   "data": { /* 各端点原有响应体 */ },
>   "message": "success",
>   "warnings": [],
>   "source": "runtime_kit",
>   "sessionId": "demo_session_001",
>   "subjectId": "",
>   "code": null,
>   "is_user_error": null
> }
> ```
> - `status`: `"success"` 或 `"error"`。
> - `data`: 端点原有响应体（与下文各端点文档中的结构一致）。`status: "error"` 时为 `null`。
> - `message`: 人类可读的结果说明。错误时为错误描述。
> - `warnings`: 非阻塞性提示信息列表。
> - `source`: 数据来源标识。可能值：`"runtime_kit"`（默认）、`"db"`、`"agent"`、`"agent_generated"`、`"user_action"`、`"user_input"`、`"system"`、`"generated"`、`"memory"`、`"mock"`、`"none"`。
> - `sessionId` / `subjectId`: 请求中的数据归属键和课程上下文键。错误时均为空字符串。
> - `code`: 机器可读错误码（如 `"MISSING_SESSION_ID"`）。成功时为 `null`。
> - `is_user_error`: 用户输入错误（4xx）时为 `true`，系统错误（5xx）时为 `false`。成功时为 `null`。
>
> **前端无感**：Axios 响应拦截器自动解包信封，将 `res.data` 替换为 `body.data`，
> 因此前端 API 调用代码无需任何修改。
>
> **注意**：HTTP 级错误（如缺少 sessionId 返回 422）同样使用以上信封格式（`status: "error"`, `data: null`）。

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
  "sessionId": "demo_session_001",
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
  "sessionId": "demo_session_001",
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

Query: `?sessionId=demo_session_001`

Response:

```json
{
  "profile": {
    "id": "demo_session_001",
    "learnerId": null,
    "nickname": "学习者",
    "createdAt": 1781235059000,
    "updatedAt": 1781321459000,
    "dimensions": [
      {
        "key": "major_background",
        "label": "专业背景",
        "value": "软件工程",
        "score": 70,
        "confidence": 0.85,
        "description": "软件工程大三学生",
        "explanation": "软件工程大三学生",
        "evidence": "软件工程大三学生",
        "source": "user_input",
        "updatedAt": 1781321459000
      }
    ],
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

The profile-level `source` field indicates overall data provenance: `"db"` (from SQLite), `"agent"` (in-memory last result), `"none"` (no data yet).

Each dimension object includes:
- `key`, `label`: dimension identifier and display name.
- `value`: the extracted value (text).
- `score`: numeric score (0-100) for visualization.
- `confidence`: 0.0-1.0 confidence estimate.
- `description`, `explanation`: human-readable descriptions.
- `evidence`: supporting evidence text for the dimension value.
- `source`: dimension-level provenance. Values: `"user_input"`, `"inferred"`, `"llm_generated"`, `"rule_based_fallback"`, `"diagnosis"`, `"feedback"`.
- `updatedAt`: timestamp (milliseconds) of last update.

### POST /profile/build

Purpose: build or refresh the student profile from a new message. This triggers the full workflow pipeline and persists results.

Request:

```json
{
  "sessionId": "demo_session_001",
  "message": "我是软件工程大三学生，线性代数比较弱，想十天学懂神经网络。"
}
```

Response:

```json
{
  "profile": {
    "id": "demo_session_001",
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
  "sessionId": "demo_session_001",
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

Query: `?sessionId=demo_session_001`

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
    "stageResourceStats": {
      "stage_1": {"total": 3, "completed": 1},
      "stage_2": {"total": 2, "completed": 0}
    },
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
  "sessionId": "demo_session_001"
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
  "sessionId": "demo_session_001",
  "status": "completed"
}
```

Response:

```json
{
  "ok": true
}
```

### PATCH /learning-path/auto-advance

Purpose: auto-advance node progress based on user interaction events. When a resource is viewed, the corresponding node is set to in-progress; when completed, the node is marked mastered and the next node in the stage is unlocked.

Request:

```json
{
  "sessionId": "demo_session_001",
  "relatedStageId": "stage_1",
  "taskId": "stage_1_node_1",
  "event": "resource_complete"
}
```

`event` values: `"resource_view"` (starts node as `in_progress`), `"resource_complete"` (marks node `mastered` and unlocks next node).

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

Query: `?sessionId=demo_session_001`

Additional optional query parameters: `type`, `difficulty`, `source`, `search`, `knowledgePoint`, `relatedStageId`, `resourceIds`, `taskId`, `chapter`, `qualityStatus`, `studyStatus`, `bookmarked`, `sortBy`.

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
      "tags": ["markdown", "agent_generated", "passed"],
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
      "completedAt": null,
      "source": "system_inferred",
      "relatedStageId": "stage_1",
      "taskId": "stage_1_node_1",
      "relatedChapter": "第1章-机器学习基础",
      "relatedKnowledgePoints": ["线性回归", "梯度下降"],
      "qualityStatus": "passed",
      "sourceType": "",
      "generationMode": "",
      "reason": "",
      "evidence": [],
      "fallbackReason": ""
    }
  ],
  "total": 6,
  "page": 1,
  "sessionId": "demo_session_001"
}
```

Resource `type` values: `lecture`, `mindmap`, `quiz`, `reading`, `case_study`, `video`.

Resource `format` values: `text`, `diagram` (for mindmap mermaid content), `code` (for practice).

Per-resource `source` values (mapped by backend): `"user_input"`, `"agent_generated"`, `"system_inferred"`, `"fallback"`, `"rule_based_fallback"`.

`qualityStatus` values: `"passed"`, `"warning"`, `"blocked"`, `"fallback"`, `"insufficient_context"`, `"fallback_passed"`.

`studyStatus` values: `"new"`, `"in_progress"`, `"completed"`.

`completedAt`: timestamp (milliseconds) when study was completed, or `null`.

`evidence`: array of strings providing provenance evidence for the resource.

`fallbackReason`: populated when the resource was generated via fallback rather than by an agent.

### GET /resources/{resource_id}

Purpose: get a single resource by ID. Tries database first, then in-memory fallback.

Query: `?sessionId=demo_session_001`

Response (envelope `data` field):

```json
{
  "resource": {
    "id": "res_lecture_001",
    "type": "lecture",
    "title": "机器学习基础入门讲义",
    "description": "适合具备 Python 基础但机器学习较薄弱的学生",
    "content": "## 1. 为什么要先学机器学习基础...",
    "knowledgePoints": ["stage_1"],
    "tags": ["markdown", "agent_generated", "passed"],
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
    "source": "agent_generated"
  }
}
```

Envelope `source` for this endpoint: `"db"` (from database), `"memory"` (in-memory fallback), `"none"` (resource not found).

### POST /resources/generate

Purpose: trigger agent pipeline to generate a new resource on a topic.

Request:

```json
{
  "sessionId": "demo_session_001",
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

Query: `?sessionId=demo_session_001`

Response:

```json
{
  "bookmarked": true,
  "ok": true
}
```

### PATCH /resources/{resource_id}/study-status

Purpose: update the study status of a resource.

Query: `?sessionId=demo_session_001`

Request:

```json
{
  "studyStatus": "completed"
}
```

`studyStatus` values: `"new"`, `"in_progress"`, `"completed"`.

Response:

```json
{
  "ok": true,
  "studyStatus": "completed"
}
```

Note: This endpoint creates a minimal DB record if the resource has not been persisted yet.

### POST /resources/batch/study-status

Purpose: batch update study status for multiple resources in a session.

Request:

```json
{
  "sessionId": "demo_session_001",
  "resourceIds": ["res_lecture_001", "res_quiz_002"],
  "studyStatus": "completed"
}
```

Response:

```json
{
  "ok": true,
  "updated": 2,
  "studyStatus": "completed"
}
```

### POST /resources/batch/bookmark

Purpose: batch bookmark or unbookmark multiple resources.

Request:

```json
{
  "sessionId": "demo_session_001",
  "resourceIds": ["res_lecture_001", "res_quiz_002"],
  "bookmarked": true
}
```

Response:

```json
{
  "ok": true,
  "updated": 2,
  "bookmarked": true
}
```

### POST /resources/batch/export

Purpose: export resource titles as a formatted text list. Optionally filter by resourceIds.

Request:

```json
{
  "sessionId": "demo_session_001",
  "resourceIds": ["res_lecture_001"]
}
```

If `resourceIds` is omitted or empty, all resources for the session are exported.

Response:

```json
{
  "ok": true,
  "export": "EduAgent 资源导出 — 2026-06-24 10:00\n共 1 项资源\n---------------------------------------------\n  1. [lecture] 机器学习基础入门讲义 (easy) — 未开始",
  "count": 1
}
```

### GET /resources/{resource_id}/knowledge-graph

Purpose: get the Mermaid mindmap definition for a resource.

Query: `?sessionId=demo_session_001`

Response:

```json
{
  "mermaidDef": "mindmap\n  root((人工智能导论))\n    ...",
  "source": "generated",
  "resourceId": "res_lecture_001"
}
```

`source` values: `"db"` (from stored mermaid_def in database), `"generated"` (generated on-the-fly from resource metadata), `"none"` (resource not found).

### GET /resources/{resource_id}/knowledge-graph-legacy

Purpose: legacy mock knowledge graph endpoint. Returns a static mindmap for demonstration and backward compatibility.

Response:

```json
{
  "mermaidDef": "mindmap\n  root((人工智能导论))\n    机器学习基础\n    神经网络\n    自然语言处理\n    资源 res_lecture_001"
}
```

Note: This endpoint always returns mock data. New integrations should use `GET /resources/{resource_id}/knowledge-graph` instead, which returns real data from the database.

### GET /chat/sessions

Purpose: list all active chat sessions.

Response:

```json
{
  "sessions": [
    {
      "id": "demo_session_001",
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
  "sessionId": "demo_session_001",
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
  "sessionId": "demo_session_001"
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
  "sessionId": "demo_session_001",
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

Valid event types: `resource_view`, `resource_complete`, `quiz_result`, `practice_result`, `node_progress`, `feedback`. Invalid types return HTTP 422 with `INVALID_EVENT_TYPE`.

Request:

```json
{
  "sessionId": "demo_session_001",
  "subjectId": "ai_intro",
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

Purpose: return learning behavior analytics computed from tracked events.

Query: `?sessionId=demo_session_001`

Response:

```json
{
  "eventCount": 42,
  "totalStudyMinutes": 125,
  "activeResourceCount": 3,
  "resourceViewCount": 30,
  "resourceCompleteCount": 5,
  "lastStudyTime": 1781321459000,
  "eventBreakdown": {
    "resource_view": 30,
    "resource_complete": 5,
    "quiz_submit": 3,
    "feedback": 2,
    "node_progress": 2
  },
  "topResources": [
    {"resourceId": "res_lecture_001", "count": 15, "title": "机器学习基础入门讲义"}
  ],
  "quizAccuracy": 75,
  "weakTopics": [
    {
      "topic": "线性回归",
      "wrongCount": 3,
      "totalCount": 5,
      "risk": 0.6,
      "source": ["quiz", "diagnosis"],
      "priority": "high"
    }
  ],
  "recommendations": [
    {
      "recommendation_type": "incomplete_resource",
      "title": "完成未学完的资源：机器学习基础入门讲义",
      "reason": "资源「机器学习基础入门讲义」尚未完成学习（状态：in_progress）",
      "target_resource_id": "res_lecture_001",
      "target_stage_id": "stage_1",
      "priority": "medium",
      "source": "db",
      "confidence": 0.9,
      "evidence": "Resource 'res_lecture_001' of type 'lecture' has study_status='in_progress' in current session",
      "quality_status": "passed"
    },
    {
      "recommendation_type": "low_accuracy_topic",
      "title": "复习薄弱知识点：线性回归",
      "reason": "知识点「线性回归」正确率偏低（3/5 错误），建议重新学习相关资源",
      "target_resource_id": "res_quiz_002",
      "target_stage_id": "stage_1",
      "priority": "high",
      "source": "analytics",
      "confidence": 0.4,
      "evidence": "Topic '线性回归': 3 wrong out of 5 attempts (risk=0.6)",
      "quality_status": "passed"
    }
  ],
  "completionTrend": [
    {"date": "2026-06-10", "count": 0},
    {"date": "2026-06-11", "count": 1}
  ],
  "quizTrend": [
    {"date": "2026-06-20", "accuracy": 80, "topic": "梯度下降", "timestamp": "2026-06-20T10:00:00"}
  ],
  "resourceTypeBreakdown": {
    "lecture": 15,
    "quiz": 5
  },
  "recentEvents": [
    {"event": "resource_view", "resourceId": "res_lecture_001", "metadata": {}, "timestamp": "2026-06-24T10:00:00"}
  ],
  "summary": "已接入学习事件追踪，可用于后续动态调整画像、资源推荐和学习路径。"
}
```

`lastStudyTime` is a timestamp in milliseconds, or `null` if no events exist.
`quizAccuracy` is a percentage (0-100), or `null` if no quiz data.
`weakTopics[].source` lists the event types that contributed to this topic (e.g. `"quiz"`, `"diagnosis"`, `"feedback"`).
`weakTopics[].priority` is `"high"` when risk > 0.5, otherwise `"medium"`.
`completionTrend` covers the last 14 days.
`quizTrend` returns the last 20 quiz/practice results.
`recommendations` is an array of structured recommendation objects (not plain strings).
Each item contains: `recommendation_type` (one of `incomplete_resource`, `low_accuracy_topic`, `incomplete_practice`, `stage_incomplete`, `frequent_weak_topic`), `title`, `reason`, `target_resource_id` (nullable), `target_stage_id` (nullable), `priority` (`high`/`medium`/`low`), `source`, `confidence` (0-1), `evidence`, and `quality_status`.
Empty array when no data or no actionable recommendations exist.

`latestQuizScore` and `bestQuizScore` provide explicit clarity on quiz performance: `latestQuizScore` is the most recent result (chronologically last), while `bestQuizScore` is the highest-scoring result. Both contain `score`, `topic`, `timestamp`, `source`, and `quality_status` fields. They are `null` when no quiz events exist.

`feedbackStats` provides explainable feedback statistics: `count` (number of feedback events), `averageRating` (mean of numeric ratings), `source`, `quality_status`, and `evidence`. It is `null` when no feedback events exist.

### Event Deduplication

Since v0.6.0, the backend applies insert-time deduplication to prevent duplicate events from inflating analytics:

- **`resource_complete`** — Idempotent: only the first `resource_complete` event per (sessionId, resourceId) is recorded. Subsequent identical events are silently ignored. This ensures `completedResources` counts unique completed resources, not repeated completions.

- **`resource_view`** — Time-window dedup: a `resource_view` event for the same (sessionId, resourceId) within a 300-second (5-minute) window is treated as a duplicate and silently ignored. Views spaced more than 5 minutes apart are both recorded (cumulative tracking).

- **`quiz_result`, `practice_result`, `feedback`, `node_progress`** — No deduplication: each event is recorded independently. Analytics use appropriate aggregation for these multi-record types (e.g., `latestQuizScore`/`bestQuizScore` for quizzes, `feedbackStats` for feedback).

Deduplication is transparent to the API caller: the response `{"ok": true}` is returned regardless of whether the event was stored or deduped.

Analytics fields after dedup:
- `completedResources` reflects unique completed resources (one per session + resource).
- `viewedResources` reflects `resource_view` events after time-window dedup.
- `eventCount` counts all stored events (the deduped set).
- `eventBreakdown` counts all stored events per event type (the deduped set).

### GET /learning-events/timeline

Purpose: get recent learning events as a timeline, enriched with resource metadata (title, type, stage, chapter).

Query: `?sessionId=demo_session_001&limit=50&type=resource_view&range=7`

Parameters:
- `sessionId` (required): session identifier.
- `subjectId` (optional): subject identifier.
- `limit` (optional, default 50): max events to return.
- `type` (optional): filter by event type. Values: `resource_view`, `resource_complete`, `quiz_result`, `practice_result`, `feedback`, `stage_complete`, `node_progress`.
- `range` (optional): time range in days. 0 = all, 1 = today, 7 = last 7 days, 30 = last 30 days.

Response:

```json
{
  "events": [
    {
      "id": 1,
      "event": "resource_view",
      "label": "查看了资源",
      "icon": "👁️",
      "color": "blue",
      "resourceId": "res_lecture_001",
      "resourceTitle": "机器学习基础入门讲义",
      "resourceType": "lecture",
      "relatedStageId": "stage_1",
      "relatedChapter": "第1章-机器学习基础",
      "metadata": {
        "knowledgePoints": ["线性回归"]
      },
      "timestamp": 1781321459000
    }
  ],
  "total": 1
}
```

Event types and their display config:

| event | label | icon | color |
|-------|-------|------|-------|
| `resource_view` | 查看了资源 | 👁️ | blue |
| `resource_complete` | 完成了资源 | ✅ | green |
| `quiz_result` | 提交了练习 | 📝 | amber |
| `practice_result` | 提交了实操 | 💻 | cyan |
| `feedback` | 提交了反馈 | 💬 | purple |
| `stage_complete` | 完成了阶段 | 🎯 | rose |
| `node_progress` | 学习节点更新 | 📌 | gray |

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

## 4. 多科目架构 (Multi-Subject Architecture) — v0.3.0 [TARGET / PLANNED]

> **Status**: The endpoints and data models in this section describe the **target architecture**.
> They have **NOT yet been implemented** in the backend. Current product APIs (Section 3)
> operate under a single default subject (`subject_default`), with `subjectId` accepted
> as a pass-through parameter for future compatibility.
> **Frontend should NOT depend on these endpoints** until backend implementation is complete.

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
// r436_runtime_active_subject
{ "id": "subject_001", "name": "数据结构" }

// r436_runtime_subject_{learnerId}
[{ "id": "subject_001", "name": "数据结构", ... }]
```

### 4.6 迁移策略

1. **第一阶段** (当前): 所有数据挂在一个默认科目下 (`subject_default`)
2. **第二阶段** (目标): 前端先做科目切换 UI，后端逐步实现按 subjectId 隔离
3. 向后兼容: 不带 `subjectId` 的请求默认使用 `subject_default`
