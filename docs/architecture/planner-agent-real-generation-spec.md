# PlannerAgent 真实生成学习路径规格

## 目标

将 `PlannerAgent` 从 mock 模板升级为真实生成：

```text
学生画像 + 目标课程 + 课程章节 + 时间安排
-> 个性化学习路径
```

## 输入数据

PlannerAgent 至少需要接收：

```json
{
  "session_id": "session_xxx",
  "course_id": "data_structures",
  "course": {
    "course_name": "数据结构",
    "chapters": [
      {
        "chapter_id": "01",
        "title": "数据结构与算法复杂度基础",
        "difficulty": "easy",
        "prerequisites": ["基础语法"]
      }
    ]
  },
  "profile_facts": {
    "background": "软件工程大二学生",
    "target_course": "数据结构",
    "knowledge_base": "数据结构基础一般",
    "weak_points": "栈和队列不熟",
    "learning_goal": "为了考试通过",
    "time_budget": "48小时",
    "preference": "图解、代码、练习题"
  }
}
```

## 输出格式

必须输出可被前端直接转换的结构：

```json
{
  "learning_path": [
    {
      "stage_id": "stage_1",
      "title": "补齐基础概念",
      "duration": "第 1 天",
      "goal": "理解复杂度、线性表和链表的核心概念",
      "tasks": [
        "阅读复杂度与线性表讲义",
        "完成链表插入删除图解练习"
      ],
      "resource_types": ["lecture", "mindmap", "quiz"],
      "reason": "学生目标是考试通过且基础一般，应先补齐高频基础概念。"
    }
  ]
}
```

## DeepSeek Prompt 草稿

System：

```text
你是 EduAgent 的学习路径规划智能体。你必须根据学生画像和课程知识库生成个性化学习路径。
要求：
1. 只输出 JSON，不输出 Markdown。
2. 不编造课程中不存在的章节。
3. 学习路径必须体现学生基础、薄弱点、目标、时间安排和学习偏好。
4. 如果时间很短，优先安排高频核心章节。
5. 每个阶段必须包含 title、duration、goal、tasks、resource_types、reason。
```

User：

```text
学生画像：
{profile_facts}

课程信息：
{course}

请生成 3-5 个阶段的学习路径。
```

## Fallback 规则

如果 DeepSeek 调用失败或返回 JSON 解析失败：

1. 使用课程章节顺序生成路径。
2. 每 1-2 个章节合并为一个阶段。
3. 根据 `time_budget` 压缩阶段数量。
4. 根据 `preference` 决定资源类型：
   - 图解 -> `mindmap`
   - 代码 -> `case_study`
   - 练习 -> `quiz`
   - 文字 -> `lecture`

## 验收标准

### 数据结构场景

输入：

```text
我是软件工程大二学生，数据结构基础一般，想学习数据结构，为了考试通过，48小时完成，喜欢图解和练习题
```

通过标准：

- 路径标题是“数据结构个性化学习路径”。
- 阶段内容包含复杂度、线性表、栈队列、树、图、查找排序等章节。
- 不应出现神经网络、NLP 等 AI 课程内容。
- 每个阶段都有排序理由。

### 人工智能导论场景

输入：

```text
我是电子信息大二学生，Python还可以，机器学习基础弱，想两周入门人工智能，希望多给代码和图解
```

通过标准：

- 路径标题是“人工智能导论个性化学习路径”。
- 阶段内容包含机器学习、神经网络、NLP 等章节。
- 资源类型包含代码和图解。

## 后续代码改动位置

优先修改：

```text
backend/app/agents/planner_agent.py
backend/app/services/orchestrator.py
backend/app/routers/product.py
backend/tests/
```

建议新增：

```text
backend/tests/planner_agent_test.py
```

## 注意事项

- 不要让 PlannerAgent 直接依赖前端字段。
- 不要把 DeepSeek API Key 写进代码。
- 返回 JSON 必须有 fallback 校验。
- 生成结果要保存在当前 `sessionId` 对应的 `last_result` 中。
