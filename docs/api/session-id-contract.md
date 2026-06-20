# Runtime Kit SessionId 协作约定

## 为什么必须统一 sessionId

当前系统的学习画像、学习路径、资源库和学习行为追踪都是按会话保存的。如果聊天接口使用一个 `sessionId`，但画像页、路径页或资源页不传这个 `sessionId`，页面就会读到默认会话的数据，出现“聊天里生成了数据结构，路径页还是人工智能导论”的问题。

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

## 当前已处理

已在前端 hooks 中接入当前会话：

- `useProfile`
- `useLearningPath`
- `useResources`

## 后续开发注意

新增页面或接口时，只要它读取的是学生画像、学习路径、资源、学习行为数据，就必须传当前 `sessionId`。不要在前端写死 `frontend_session_001`。
