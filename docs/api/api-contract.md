# EduAgent API Contract

## 1. Base Information

Backend base URL:

```text
http://localhost:8000
```

Frontend dev URL:

```text
http://localhost:5173
```

API prefix:

```text
/api
```

Field naming:

```text
snake_case
```

All API responses must use the same response envelope:

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "request_id": "req_demo_001"
}
```

Error response:

```json
{
  "code": 400,
  "message": "invalid request",
  "data": null,
  "request_id": "req_error_001"
}
```

## 2. GET /api/health

Purpose: check whether the backend service is running.

Response:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "ok",
    "service": "eduagent-backend"
  },
  "request_id": "req_health"
}
```

## 3. GET /api/courses

Purpose: return available courses. Stage 1 only returns one course, but the format must support multiple courses.

Response:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "courses": [
      {
        "course_id": "ai_intro",
        "course_name": "人工智能导论",
        "difficulty": "introductory",
        "description": "面向高校低年级学生的人工智能入门课程，覆盖 AI 概述、搜索算法、机器学习、神经网络、NLP、CV、强化学习与 AI 伦理。"
      }
    ]
  },
  "request_id": "req_courses"
}
```

## 4. POST /api/agents/run

Purpose: run the Stage 1 main flow. The frontend should call this API when the user clicks the generate button.

Request:

```json
{
  "session_id": "demo_session_001",
  "course_id": "ai_intro",
  "user_message": "我是电子信息专业大二学生，学过 Python，但机器学习基础比较薄弱。我想用两周时间入门人工智能，重点理解神经网络和自然语言处理，希望多给我一些图解、代码案例和练习题。"
}
```

Response:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "session_id": "demo_session_001",
    "course_id": "ai_intro",
    "profile": {},
    "diagnosis": {},
    "learning_path": [],
    "resources": [],
    "agent_steps": [],
    "review": {}
  },
  "request_id": "req_agents_run"
}
```

## 5. Data Field Requirements

### 5.1 profile

`profile` must include 8 dimensions:

```text
major_background
knowledge_base
learning_goal
cognitive_style
weak_points
programming_ability
learning_progress
interests
```

Each dimension must use this structure:

```json
{
  "label": "专业背景",
  "value": "电子信息专业大二学生",
  "confidence": 0.95,
  "source": "user_input",
  "evidence": "我是电子信息专业大二学生"
}
```

`source` allowed values:

```text
user_input
inferred
diagnosis
feedback
```

### 5.2 diagnosis

Format:

```json
{
  "summary": "学生具备 Python 基础，但机器学习和神经网络先修概念不足。",
  "weak_knowledge_points": [
    {
      "point_id": "ml_basic",
      "name": "机器学习基本概念",
      "reason": "后续神经网络和 NLP 学习需要先理解监督学习、特征、损失函数等概念。",
      "priority": "high"
    }
  ],
  "recommended_strategy": "先补机器学习基础，再学习神经网络，最后通过 NLP 小项目整合应用。"
}
```

`priority` allowed values:

```text
high
medium
low
```

### 5.3 learning_path

Format:

```json
[
  {
    "stage_id": "stage_1",
    "title": "补齐机器学习基础",
    "duration": "第 1-3 天",
    "goal": "理解监督学习、无监督学习、损失函数和模型训练流程。",
    "tasks": [
      "阅读机器学习基础讲义",
      "完成概念辨析练习",
      "运行一个简单分类案例"
    ],
    "resource_types": ["lecture", "quiz", "practice"]
  }
]
```

### 5.4 resources

Stage 1 required resource types:

```text
lecture
mindmap
quiz
reading
practice
```

Optional resource type:

```text
multimodal
```

Common resource format:

```json
{
  "resource_id": "res_lecture_001",
  "type": "lecture",
  "title": "神经网络基础个性化讲义",
  "description": "面向具备 Python 基础但机器学习较薄弱的学生。",
  "content_format": "markdown",
  "content": "## 神经网络是什么\n...",
  "related_stage_id": "stage_2",
  "source": "mock",
  "quality_status": "passed"
}
```

`content_format` allowed values:

```text
markdown
mermaid
json
code
text
```

`source` allowed values:

```text
mock
llm
knowledge_base
mixed
```

`quality_status` allowed values:

```text
pending
passed
warning
failed
```

### 5.5 agent_steps

Format:

```json
[
  {
    "agent_id": "profile_agent",
    "agent_name": "画像智能体",
    "status": "completed",
    "summary": "已完成 8 个维度学生画像抽取。",
    "started_at": "2026-06-12T10:00:00+08:00",
    "finished_at": "2026-06-12T10:00:02+08:00"
  }
]
```

`status` allowed values:

```text
pending
running
completed
warning
failed
```

### 5.6 review

Format:

```json
{
  "quality_status": "passed",
  "checks": [
    {
      "check_id": "format_check",
      "name": "格式完整性检查",
      "status": "passed",
      "message": "画像、路径、资源和智能体状态字段完整。"
    }
  ],
  "summary": "生成结果结构完整，适合第一阶段演示。"
}
```

