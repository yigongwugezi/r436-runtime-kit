# 前端接口依赖表

> 所有 API 基路径由 `src/api/client.ts` 配置，默认 `http://localhost:8001`

| 页面 | API 路径 | 方法 | 必要参数 | 返回关键字段 |
|------|----------|------|----------|-------------|
| **Chat** | `/agents/run` | POST | `sessionId`, `userMessage`, `courseId?` | `profile`, `diagnosis`, `learning_path`, `resources`, `review`, `agent_steps` |
| **Chat** | `/agents/status/{sessionId}` | GET | `sessionId` | `progress`, `agentName`, `done`, `error` |
| **Chat** | `/chat/messages` | GET | `sessionId` | `messages[]` |
| **Chat** | `/chat/sessions` | GET | `learnerId` | `sessions[]` |
| **Profile** | `/learning-analytics/profile` | GET | `sessionId`, `subjectId?` | `dimensions[]`, `weaknesses[]`, `preferences`, `nickname`, `updatedAt` |
| **Profile** | `/profile` | GET | `sessionId`, `subjectId?` | `dimensions[]`, `weaknesses[]`, `preferences` |
| **Path** | `/learning-path` | GET | `sessionId`, `subjectId?` | `stages[]`, `nodes[]`, `currentStage?` |
| **Path** | `/learning-path/node/progress` | POST | `sessionId`, `nodeId`, `status` | `ok` |
| **Resources** | `/resources` | GET | `sessionId`, `subjectId?`, `type?`, `difficulty?`, `search?`, `sortBy?`, `taskId?`, `relatedStageId?`, `resourceIds?`, `chapter?`, `qualityStatus?`, `studyStatus?`, `bookmarked?` | `resources[]`, `total`, `completedCount`, `completionRate` |
| **Resources** | `/resources/{id}` | GET | `sessionId` | `resource` |
| **Resources** | `/resources/{id}/bookmark` | POST | `sessionId` | `bookmarked` |
| **Resources** | `/resources/generate` | POST | `sessionId`, `type`, `topic`, `difficulty?` | `resource` |
| **Resources** | `/resources/batch/study-status` | POST | `sessionId`, `resourceIds[]`, `studyStatus` | `ok`, `updated` |
| **Resources** | `/resources/batch/bookmark` | POST | `sessionId`, `resourceIds[]`, `bookmarked` | `ok`, `updated` |
| **Resources** | `/resources/batch/export` | POST | `sessionId`, `resourceIds[]` | `ok`, `export`, `count` |
| **Resources** | `/resources/study-status` | POST | `resourceId`, `studyStatus`, `sessionId` | (更新状态) |
| **Resources** | `/resources/auto-advance` | POST | `sessionId`, `relatedStageId`, `taskId`, `event` | (自动推进) |
| **Resources** | `/resources/{id}/knowledge-graph` | GET | `sessionId` | `mermaidDef`, `source` |
| **Analytics** | `/learning-analytics` | GET | `sessionId`, `subjectId?` | `eventCount`, `totalStudyMinutes`, `activeResourceCount`, `eventBreakdown`, `weakTopics[]`, `recommendations[]`, `completionTrend[]`, `quizTrend[]`, `topResources[]`, `recentEvents[]`, `summary`, `quizAccuracy` |
| **Timeline** | `/learning-events/timeline` | GET | `sessionId`, `limit`, `type?`, `days?` | `events[]`, `total` |
| **通用** | `/feedback` | POST | `sessionId`, `resourceId`, `rating`, `category?`, `comment?` | (提交反馈) |
| **通用** | `/learning-events` | POST | `sessionId`, `event`, `resourceId?`, `metadata?` | (记录学习事件) |
| **通用** | `/resources/{id}/bookmark` | POST | `sessionId` | `bookmarked` |

## 数据流说明

```
用户输入 → ChatPage → /agents/run → Agent Pipeline
                                         ↓
                                   ProfileAgent → /profile
                                   KnowledgeAgent → (知识库)
                                   DiagnosisAgent → (诊断)
                                   PlannerAgent → /learning-path
                                   ResourceAgent → /resources/generate
                                   ReviewAgent → (质量审核)
                                         ↓
                                   前端跳转至对应页面展示结果
```
