# Runtime Kit SessionId 协作约定

## 为什么必须统一 sessionId

当前系统的学习画像、学习路径、资源库和学习行为追踪都是按会话保存的。如果聊天接口使用一个 `sessionId`，但画像页、路径页或资源页不传这个 `sessionId`，页面就会读到错误会话的数据，出现”聊天里生成了数据结构，路径页还是人工智能导论”的问题。

## 核心原则

- **`sessionId` 是唯一的数据归属键（data-ownership key）**。所有按会话存储的数据（画像、路径、资源、分析）必须通过 `sessionId` 进行隔离。
- **`subjectId` 只作为课程上下文（course context）**，用于标识当前学习的科目/课程。**绝对不允许** `subjectId` 被用作 `sessionId` 的替代或回退。
- **后端严格校验**：所有产品 API 端点要求必须提供 `sessionId`，缺失或为空时返回 HTTP 400，不再有硬编码默认值。

## 前端约定

前端统一从 `chatStore.currentSessionId` 读取当前会话 ID。

这些接口必须带同一个 `sessionId`：

- `POST /api/chat/send`
- `POST /api/chat/stream`
- `GET /api/profile?sessionId=xxx`
- `GET /api/learning-path?sessionId=xxx`
- `GET /api/resources?sessionId=xxx`
- `POST /api/feedback/event`
- `POST /api/feedback`

`subjectId` 可以作为额外参数传递（用于前端状态管理），但后端不会将其作为 `sessionId` 的替代。

## 当前已处理

已在前端 hooks 中接入当前会话：

- `useProfile`
- `useLearningPath`
- `useResources`

## 后续开发注意

新增页面或接口时，只要它读取的是学生画像、学习路径、资源、学习行为数据，就必须传当前 `sessionId`。不要在任何代码中硬编码 `frontend_session_001`。不要假设 `subjectId` 可以替代 `sessionId`。
