# EduAgent 小组每日同步模板

## 使用方式

每天晚上每个人按下面格式发到群里。重点是让组长快速判断：

- 代码有没有推进
- 项目还能不能跑
- 有没有改接口
- 有没有影响别人
- 明天要做什么

## 每日同步格式

```text
【姓名 / 负责方向】

1. 今天完成了什么
- 
- 

2. 改了哪些文件
- 
- 

3. 怎么测试的
- 运行命令：
- 测试页面/接口：
- 结果：

4. 有没有改接口或数据结构
- 没有 / 有
- 如果有，说明改了什么：

5. 有没有影响别人
- 没有 / 有
- 如果有，说明前端/后端/智能体谁需要同步：

6. 遇到的问题
- 

7. 明天计划
- 
```

## 前端成员示例

```text
【前端 / 页面与交互】

1. 今天完成了什么
- 优化 AI 对话页消息气泡和 loading 状态
- 修复移动端资源卡片文字溢出

2. 改了哪些文件
- frontend/src/pages/ChatPage.tsx
- frontend/src/index.css

3. 怎么测试的
- 运行命令：npm run build
- 测试页面：http://localhost:5173/chat
- 结果：build 通过，聊天页能正常发送消息

4. 有没有改接口或数据结构
- 没有

5. 有没有影响别人
- 没有

6. 遇到的问题
- 资源详情页还缺少后端字段说明

7. 明天计划
- 做资源详情弹窗
```

## 后端成员示例

```text
【后端 / 数据库与接口】

1. 今天完成了什么
- 新增 SQLite 表结构草稿
- 准备保存 learning_events

2. 改了哪些文件
- backend/app/services/storage.py
- docs/api/api-contract.md

3. 怎么测试的
- 运行命令：powershell -ExecutionPolicy Bypass -File backend\tests\run_conversation_tests.ps1
- 测试接口：POST /api/feedback/event
- 结果：测试通过

4. 有没有改接口或数据结构
- 有
- 新增 learning_events 表，但接口字段暂时没变

5. 有没有影响别人
- 前端暂时不受影响

6. 遇到的问题
- 还没决定是否保存完整 chat messages

7. 明天计划
- 完成画像和学习事件持久化
```

## 智能体成员示例

```text
【智能体 / Agent 与知识库】

1. 今天完成了什么
- 优化课程匹配逻辑
- 增加数据结构课程章节

2. 改了哪些文件
- backend/app/services/course_catalog.py
- knowledge_base/courses/data_structures/course.json

3. 怎么测试的
- 运行命令：backend tests 全部通过
- 测试接口：GET /api/courses
- 结果：能看到 ai_intro 和 data_structures

4. 有没有改接口或数据结构
- 没有改接口
- 新增课程知识库文件

5. 有没有影响别人
- 前端可展示更多课程

6. 遇到的问题
- PlannerAgent 还没有完全真实生成

7. 明天计划
- 开始替换 PlannerAgent mock
```

## 强制要求

- 不允许只说“做了一点”。
- 不允许只发截图不说明改了什么。
- 改接口必须写清楚。
- 没跑测试也必须说明“未测试”和原因。
- 不允许 force push main。
- 每次开始开发前先拉最新代码。
