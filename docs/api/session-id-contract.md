# Runtime Kit SessionId 协作约定

## 为什么必须统一 sessionId

当前系统的学习画像、学习路径、资源库和学习行为追踪都是按会话保存的。如果聊天接口使用一个 `sessionId`，但画像页、路径页或资源页不传这个 `sessionId`，页面就会读到默认会话的数据，出现"聊天里生成了数据结构，路径页还是人工智能导论"的问题。

## 前端约定

前端统一从 `chatStore.currentSessionId` 读取当前会话 ID。

这些接口必须带同一个 `sessionId`：

- `POST /chat/send`
- `POST /chat/stream`
- `GET /profile?sessionId=xxx`
- `GET /learning-path?sessionId=xxx`
- `GET /resources?sessionId=xxx`
- `GET /resources/{resource_id}?sessionId=xxx`
- `PATCH /resources/{resource_id}/study-status?sessionId=xxx`
- `POST /resources/batch/study-status`
- `POST /resources/batch/bookmark`
- `POST /resources/batch/export`
- `PATCH /learning-path/auto-advance`
- `PATCH /learning-path/nodes/{node_id}`
- `POST /feedback/event`
- `POST /feedback`
- `GET /learning-events/timeline?sessionId=xxx`
- `GET /learning-analytics?sessionId=xxx`
- `GET /chat/sessions`
- `GET /chat/sessions/{session_id}`

> **注意**: Product API 路径**不带** `/api/` 前缀（如 `GET /profile`）。`/api/` 前缀仅用于 Core API（`/api/agents/run`）、Courses API（`/api/courses`）和 Health（`/api/health`）。虽然 product router 同时挂载在 `/` 和 `/api/` 下以实现向后兼容，但规范路径以不带前缀的为准。

## 当前已处理

已在前端 hooks 中接入当前会话：

- `useProfile`
- `useLearningPath`
- `useResources`

## 后续开发注意

1. 新增页面或接口时，只要它读取的是学生画像、学习路径、资源、学习行为数据，就必须传当前 `sessionId`。
2. **不要在前端写死 `frontend_session_001`**。
3. `subjectId` 仅作为课程上下文参数，**不能**替代 `sessionId` 或作为 `sessionId` 的 fallback。
