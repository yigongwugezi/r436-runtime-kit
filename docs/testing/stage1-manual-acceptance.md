# Runtime Kit 第一阶段手动验收脚本

## 目标

用于快速确认当前版本是否可演示。验收重点不是最终内容质量，而是确认第一阶段主流程是否跑通：

```text
对话收集画像 -> 课程匹配 -> 生成学习方案 -> 页面展示 -> 学习追踪
```

## 启动服务

后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8001
```

前端：

```powershell
cd frontend
npm run dev
```

访问：

```text
http://localhost:5173
```

## 验收 1：课程库是否正常

打开：

```text
http://localhost:8001/api/courses
```

通过标准：

- 能看到 `ai_intro`
- 能看到 `data_structures`
- `data_structures` 的章节数为 6

再打开：

```text
http://localhost:8001/api/courses/data_structures/chapters/03
```

通过标准：

- 能看到章节标题“栈、队列与递归”
- 能看到 Markdown 内容

## 验收 2：对话画像是否正常

打开：

```text
http://localhost:5173/chat
```

输入：

```text
你好
```

通过标准：

- 回复为普通介绍
- 不应启动学习方案生成

继续输入：

```text
我是软件工程大二学生，数据结构基础一般，想学习数据结构，为了考试通过
```

通过标准：

- 意图识别应为 `profile_update`
- 回复里应出现画像更新
- 应识别出：
  - 软件工程大二学生
  - 数据结构
  - 数据结构基础一般
  - 为了考试通过

## 验收 3：学习方案生成是否正常

继续输入：

```text
开始生成学习方案
```

通过标准：

- 意图识别应为 `learning_plan`
- 页面应显示“学习方案已生成”
- 不应报 404 或 Stream error

注意：

当前学习路径和资源内容仍有 mock 成分，验收重点是流程能启动、结果能保存到当前会话。

## 验收 4：sessionId 页面贯通

在同一浏览器会话中，不刷新页面，依次切换：

```text
学习画像
学习路径
资源库
```

通过标准：

- 学习画像页能看到刚才对话生成的画像信息。
- 学习路径页标题应与当前课程一致，例如“数据结构学习路径”。
- 资源库能正常展示资源列表。
- 不应切回默认的“人工智能导论”旧结果。

## 验收 5：日期与澄清问题不污染画像

回到 AI 对话页，输入：

```text
今天是几号
```

通过标准：

- 意图识别应为 `date_query`
- 回复当前日期
- 不应显示“本次更新画像”

再输入：

```text
你啥意思
```

通过标准：

- 意图识别应为 `clarification`
- 回复解释系统当前逻辑
- 不应固定回复欢迎词

## 验收 6：学习行为追踪接口

可以用接口工具或浏览器控制台调用，也可以后续让前端按钮接入。

记录事件：

```http
POST http://localhost:8001/api/feedback/event
Content-Type: application/json

{
  "sessionId": "manual_acceptance",
  "event": "quiz_result",
  "resourceId": "res_quiz_001",
  "duration": 15,
  "metadata": {
    "topic": "stack",
    "correct": 3,
    "total": 5,
    "wrong": 2
  }
}
```

查询分析：

```text
http://localhost:8001/api/learning-analytics?sessionId=manual_acceptance
```

通过标准：

- `eventCount` 大于 0
- `totalStudyMinutes` 大于 0
- `quizAccuracy` 能计算出正确率
- `weakTopics` 中能看到 `stack`
- `recommendations` 有建议内容

## 自动测试

后端：

```bash
cd backend
python tests/import_app_test.py
python tests/course_catalog_test.py
python tests/learning_tracker_test.py
```

前端：

```bash
cd frontend
npm run build
```

通过标准：

- 后端测试全部 PASS
- 前端 build 成功

## 当前已知边界

以下不是验收失败，而是当前阶段边界：

- 学习路径具体任务仍有 mock 成分（DB 持久化已完成，内容待真实生成）。
- 资源库具体讲义、题库、代码案例仍有 mock 成分（DB schema 已完成，含 difficulty/format/mermaid/questions/code_blocks 等完整字段）。
- 画像页雷达图分数仍有 mock 成分。
- 防幻觉审核还只是雏形。
- **已实现**: DB 持久化（profile/path/resources 快照 + 学习事件追踪 + 聊天记录），session 隔离，AgentOrchestrator 错误隔离与超时处理，完整 API 端点集。

下一阶段优先替换：

```text
PlannerAgent -> ResourceAgent -> ProfileAgent -> DiagnosisAgent -> ReviewAgent
```
