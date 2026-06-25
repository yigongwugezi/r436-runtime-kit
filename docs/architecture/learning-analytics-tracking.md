# Runtime Kit 学习行为追踪与效果评估雏形

## 当前目标

第一阶段先完成一个轻量级学习效果评估闭环：

1. 前端记录学生学习行为。
2. 后端接收并归档事件。
3. 系统计算学习时长、资源使用、练习正确率和薄弱知识点。
4. 后续智能体可基于这些数据动态调整画像、学习路径和资源推荐。

## 当前已接入接口

### 记录学习事件

`POST /api/feedback/event`

示例：

```json
{
  "sessionId": "demo_session_001",
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

常用事件名：

- `resource_view`: 查看资源
- `resource_complete`: 完成资源
- `quiz_result`: 练习或测验结果
- `practice_result`: 实操练习结果
- `node_progress`: 学习路径节点进度
- `feedback`: 学生对资源的反馈

### 查询学习分析

`GET /api/learning-analytics?sessionId=demo_session_001`

返回字段：

- `eventCount`: 事件数量
- `totalStudyMinutes`: 累计学习分钟数
- `activeResourceCount`: 使用过的资源数量
- `viewedResources`: 查看资源次数
- `completedResources`: 完成资源次数
- `practiceCount`: 实践练习次数
- `eventBreakdown`: 事件类型统计
- `topResources`: 高频资源
- `quizAccuracy`: 练习正确率
- `weakTopics`: 根据错题统计出的薄弱知识点
- `recommendations`: 系统给出的调整建议
- `recentEvents`: 最近学习事件（按时间倒序）

## 前端接入建议

前端在这些动作发生时调用 `logStudyEvent`：

- 打开资源详情页时记录 `resource_view`
- 学完一个资源时记录 `resource_complete`
- 做完练习题时记录 `quiz_result`
- 点击学习路径节点完成时记录 `node_progress`
- 对资源打分时记录 `feedback`

## 后续升级方向

当前实现是内存版，适合第一阶段演示。第二阶段建议升级为：

1. 存入数据库，重启后不丢数据。
2. 和学生画像联动，把低正确率知识点写入薄弱点。
3. 和资源推荐联动，低正确率时降低资源难度。
4. 和学习路径联动，未掌握节点自动延后下一阶段。
5. 接入评估智能体，由 Agent 生成更完整的诊断报告。
