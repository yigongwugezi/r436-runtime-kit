# Agent 与前端能力映射

## 当前学习工作区

| 能力 | 后端入口 | 前端入口 | 当前状态 |
| --- | --- | --- | --- |
| 章节化学习路径 | PlannerAgent 输出 stages/chapters/sections | LearningPathPage | 已接入 |
| 小节讲义 | `/api/sections/{section_id}/lecture` | LecturePage | 可读取和生成，讲义以资源持久化 |
| 智能辅导 | `/api/sections/{section_id}/tutor/ask` | LecturePage 辅导标签 | 已接入画像、分析和讲义片段 |
| 小节测验 | assessment 接口 | LecturePage 测验标签 | 已接入 |
| 多模态 | MultimodalAgent 与星火 Provider | ChatPage | 统一公开状态并保留原始 Provider 状态 |
| Agent 进度 | chat stream done 事件 | ChatPage | 可查看执行详情和告警 |
| 新建会话 | `/api/chat/sessions` | chatStore | 创建唯一会话并同步数据会话 |

## 状态约定

多模态对前端公开 `completed`、`provider_not_configured`、`generation_failed` 三种状态。Provider 的原始状态保留在 `metadata.raw_status`，页面不展示内部异常堆栈。

## 尚未形成闭环的能力

- 讲义页资源标签目前展示思维导图入口、讲义状态和章节统计，尚未接入独立资源推荐或资源生成操作。
- 章节思维导图尚未形成自动生成并绑定 `mindmapId` 的闭环。
- 视频能力会按 Provider 配置返回结果或友好提示；当前讲义页展示视频脚本，不提供播放器。
