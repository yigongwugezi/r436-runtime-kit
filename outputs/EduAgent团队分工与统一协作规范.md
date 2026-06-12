# EduAgent 团队分工与统一协作规范

## 1. 项目定位

EduAgent 是一个 Web 软件系统，不是单独的聊天机器人，也不是只运行在命令行里的智能体脚本。

系统形态：

```text
前端 Vue 页面
  -> 后端 FastAPI 接口
  -> 多智能体调度器
  -> 大模型 API + 课程知识库
  -> 返回学生画像、学习路径和学习资源
```

第一阶段目标：

```text
学生输入学习情况
-> 系统生成学生画像
-> 多智能体生成学习路径
-> 生成至少 5 类学习资源
-> 前端展示智能体运行状态和结果
```

第一阶段允许先使用 mock 数据，先跑通软件闭环，再逐步接入真实大模型和知识库。

## 2. 最终技术栈

### 第一阶段必须使用

| 模块 | 技术 |
| --- | --- |
| 前端 | Vue 3 + Vite |
| UI 组件 | Element Plus |
| 前端状态管理 | Pinia |
| HTTP 请求 | Axios |
| Markdown 渲染 | markdown-it 或 md-editor-v3 |
| 思维导图/流程图 | Mermaid |
| 后端 | Python 3.13+ + FastAPI |
| 后端服务 | Uvicorn |
| 数据校验 | Pydantic |
| 智能体 | 自研轻量多智能体调度器 |
| 大模型 | 讯飞星火优先，DeepSeek/Qwen 备用 |
| 知识库 | Markdown + JSON |
| 数据存储 | 第一阶段 JSON/SQLite |
| 开发工具 | VS Code 为主，后端可用 PyCharm |
| 代码管理 | Git + GitHub |

### 后续增强再考虑

| 模块 | 技术 |
| --- | --- |
| Agent 编排 | LangGraph / LangChain |
| 向量数据库 | Chroma / Qdrant |
| Embedding | bge-large-zh / 讯飞 Embedding / Qwen Embedding |
| 数据库 | PostgreSQL |
| 缓存和队列 | Redis + Celery |
| 容器化 | Docker + docker-compose |
| 认知诊断 | NeuralCD / DINA |
| 学习数据集 | ASSISTments / EdNet |

## 3. 开发环境统一

所有成员尽量保持以下环境：

| 工具 | 统一版本建议 | 是否必须统一 |
| --- | --- | --- |
| Node.js | 24.x LTS | 必须 |
| npm | 11.x | 必须 |
| Python | 3.13+，建议全员统一到同一个小版本 | 必须 |
| Git | 2.40+ | 不严格 |
| VS Code | 最新版 | 不严格 |

注意：

- 后端统一使用 Python 3.13 及以上，建议全员尽量使用同一个小版本，例如 3.13.x，避免依赖兼容和虚拟环境差异。
- 前端依赖以 `frontend/package-lock.json` 为准。
- 后端依赖以 `backend/requirements.txt` 为准。
- 任何人不要提交 `.env`、`.venv/`、`node_modules/`、`dist/`。

## 4. 三人最终分工

### 4.1 组长：智能体、知识库、接口契约、文档和整合

负责范围：

```text
docs/
knowledge_base/
backend/app/agents/ 的设计和部分实现
backend/app/mock/ 的 mock 内容
```

具体任务：

1. 定学生画像 8 个维度。
2. 定多智能体协作流程。
3. 定 API 请求和响应格式。
4. 准备统一演示案例。
5. 准备《人工智能导论》课程知识库初版。
6. 编写智能体 Prompt 草稿。
7. 编写 mock 输出内容。
8. 编写系统架构、API 契约、演示脚本、PPT 大纲。
9. 检查前端、后端、智能体是否按统一格式对接。

组长不是只写规划，组长负责最贴合赛题的 AI 逻辑和最终演示质量。

### 4.2 前端负责人：Vue 页面、交互和结果展示

负责范围：

```text
frontend/
```

具体任务：

1. 搭建 Vue 3 + Vite 项目。
2. 接入 Element Plus、Pinia、Axios、Mermaid、Markdown 渲染。
3. 实现首页学习工作台。
4. 实现聊天输入区。
5. 实现学生画像展示。
6. 实现学习路径时间线。
7. 实现资源卡片展示。
8. 实现智能体运行状态面板。
9. 对接后端 `/api/agents/run`。
10. 处理 loading、empty、error 状态。

### 4.3 后端负责人：FastAPI、接口、调度器和模型封装

负责范围：

```text
backend/
```

具体任务：

1. 搭建 FastAPI 项目。
2. 实现 `/api/health`。
3. 实现 `/api/agents/run`。
4. 定义 Pydantic 数据模型。
5. 实现 mock 数据返回。
6. 实现 `AgentOrchestrator` 调度器雏形。
7. 实现统一 `LLMClient` 接口。
8. 预留讯飞星火、DeepSeek、Qwen 的模型切换能力。
9. 配置 CORS，让前端能访问后端。
10. 编写后端启动说明。

## 5. 仓库目录统一

项目目录统一为：

```text
EduAgent/
  README.md
  .gitignore
  frontend/
    package.json
    package-lock.json
    vite.config.js
    .env.example
    src/
      main.js
      App.vue
      router/
      stores/
      api/
      views/
      components/
      assets/
  backend/
    requirements.txt
    .env.example
    app/
      main.py
      config.py
      schemas/
      routers/
      services/
      agents/
      mock/
    data/
    scripts/
  knowledge_base/
    courses/
      ai_intro/
        course.json
        outline.md
        chapters/
          01-ai-overview.md
          02-search-algorithms.md
          03-machine-learning-basics.md
          04-neural-networks.md
          05-nlp-intro.md
          06-computer-vision-intro.md
          07-reinforcement-learning.md
          08-ai-ethics.md
  docs/
    architecture/
    api/
    schemas/
    development/
    testing/
    presentation/
  demo/
  outputs/
```

统一要求：

- 第一阶段只填充 `ai_intro` 一门课程，但目录按多课程扩展设计。
- 后续新增课程时，只新增 `knowledge_base/courses/{course_id}/`，不要改智能体主流程。
- 所有 Markdown 文件统一使用 UTF-8 编码。
- 文件名尽量使用小写英文和短横线，例如 `student-profile-schema.md`。

## 6. 多课程扩展约定

系统不能写死《人工智能导论》。第一阶段只做这一门课，但代码必须支持多课程。

统一字段：

```text
course_id
```

第一阶段默认值：

```text
ai_intro
```

课程目录：

```text
knowledge_base/courses/{course_id}/
```

课程元数据文件：

```text
knowledge_base/courses/{course_id}/course.json
```

`course.json` 统一格式：

```json
{
  "course_id": "ai_intro",
  "course_name": "人工智能导论",
  "target_students": ["人工智能", "计算机", "电子信息", "自动化"],
  "difficulty": "introductory",
  "chapters": [
    {
      "chapter_id": "01",
      "title": "人工智能概述与发展历史",
      "file": "chapters/01-ai-overview.md"
    }
  ]
}
```

前端请求后端时必须带 `course_id`。后端根据 `course_id` 选择课程知识库。

## 7. API 统一约定

### 7.1 基础约定

后端地址：

```text
http://localhost:8000
```

前端地址：

```text
http://localhost:5173
```

API 前缀：

```text
/api
```

JSON 字段命名：

```text
统一使用 snake_case
```

原因：

- 后端 Python/Pydantic 使用 snake_case 更自然。
- 前端直接按接口字段展示，不再自行转换字段名。
- 避免 `learningPath` 和 `learning_path` 混用。

统一响应外壳：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "request_id": "req_20260612_000001"
}
```

错误响应：

```json
{
  "code": 400,
  "message": "invalid course_id",
  "data": null,
  "request_id": "req_20260612_000002"
}
```

### 7.2 第一阶段必须实现的接口

#### GET /api/health

用途：检查后端是否启动。

响应：

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

#### GET /api/courses

用途：获取课程列表。第一阶段可以只返回一门课。

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "courses": [
      {
        "course_id": "ai_intro",
        "course_name": "人工智能导论",
        "difficulty": "introductory"
      }
    ]
  },
  "request_id": "req_courses"
}
```

#### POST /api/agents/run

用途：主流程接口。前端只需要调用这一个接口，就能跑完整演示闭环。

请求：

```json
{
  "session_id": "demo_session_001",
  "course_id": "ai_intro",
  "user_message": "我是电子信息专业大二学生，学过 Python，但机器学习基础比较薄弱。我想用两周时间入门人工智能，重点理解神经网络和自然语言处理，希望多给我一些图解、代码案例和练习题。"
}
```

响应：

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

### 7.3 第二阶段再实现的接口

```text
GET /api/profile/{session_id}
GET /api/resources/{session_id}
POST /api/tutor/ask
POST /api/feedback
GET /api/knowledge/search
```

第一阶段如果时间紧，这些接口可以先不做。

## 8. 核心数据格式统一

### 8.1 学生画像 profile

画像必须包含 8 个维度。

字段统一为：

```json
{
  "major_background": {
    "label": "专业背景",
    "value": "电子信息专业大二学生",
    "confidence": 0.95,
    "source": "user_input",
    "evidence": "我是电子信息专业大二学生"
  },
  "knowledge_base": {
    "label": "知识基础",
    "value": "Python 基础中等，机器学习基础薄弱",
    "confidence": 0.9,
    "source": "user_input",
    "evidence": "学过 Python，但机器学习基础比较薄弱"
  },
  "learning_goal": {
    "label": "学习目标",
    "value": "两周入门人工智能，重点理解神经网络和自然语言处理",
    "confidence": 0.95,
    "source": "user_input",
    "evidence": "想用两周时间入门人工智能"
  },
  "cognitive_style": {
    "label": "认知风格",
    "value": "偏好图解、代码案例和练习题",
    "confidence": 0.9,
    "source": "user_input",
    "evidence": "希望多给我一些图解、代码案例和练习题"
  },
  "weak_points": {
    "label": "易错点",
    "value": "机器学习概念、神经网络训练流程、NLP 基础概念",
    "confidence": 0.75,
    "source": "inferred",
    "evidence": "由知识基础和学习目标推断"
  },
  "programming_ability": {
    "label": "编程能力",
    "value": "具备 Python 基础，适合从可运行小案例入手",
    "confidence": 0.85,
    "source": "user_input",
    "evidence": "学过 Python"
  },
  "learning_progress": {
    "label": "学习进度",
    "value": "准备开始系统学习人工智能导论",
    "confidence": 0.75,
    "source": "inferred",
    "evidence": "希望两周入门"
  },
  "interests": {
    "label": "兴趣方向",
    "value": "神经网络、自然语言处理",
    "confidence": 0.95,
    "source": "user_input",
    "evidence": "重点理解神经网络和自然语言处理"
  }
}
```

统一要求：

- `confidence` 范围为 0 到 1。
- `source` 只允许：
  - `user_input`
  - `inferred`
  - `diagnosis`
  - `feedback`
- 前端展示中文用 `label`，逻辑判断用英文字段名。

### 8.2 学习诊断 diagnosis

统一格式：

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

`priority` 只允许：

```text
high / medium / low
```

### 8.3 学习路径 learning_path

统一格式：

```json
[
  {
    "stage_id": "stage_1",
    "title": "补齐机器学习基础",
    "duration": "第 1-3 天",
    "goal": "理解监督学习、无监督学习、损失函数和模型训练流程。",
    "tasks": [
      "阅读机器学习基础讲义",
      "完成 5 道概念辨析题",
      "运行一个简单分类案例"
    ],
    "resource_types": ["lecture", "quiz", "practice"]
  }
]
```

### 8.4 学习资源 resources

第一阶段至少生成 5 类资源。

资源类型统一枚举：

```text
lecture     课程讲义
mindmap     思维导图
quiz        练习题
reading     拓展阅读
practice    Python 实操案例
```

可选加分资源：

```text
multimodal  视频脚本 / PPT 大纲 / 动画分镜
```

统一格式：

```json
[
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
]
```

`content_format` 只允许：

```text
markdown / mermaid / json / code / text
```

`source` 只允许：

```text
mock / llm / knowledge_base / mixed
```

`quality_status` 只允许：

```text
pending / passed / warning / failed
```

### 8.5 练习题 quiz 格式

当 `type = quiz` 时，`content` 可以是 JSON 字符串，或后端直接返回 `items` 字段。

推荐格式：

```json
{
  "resource_id": "res_quiz_001",
  "type": "quiz",
  "title": "机器学习基础练习题",
  "content_format": "json",
  "items": [
    {
      "question_id": "q_001",
      "question_type": "single_choice",
      "stem": "以下哪一项属于监督学习任务？",
      "options": ["聚类", "分类", "降维", "关联规则挖掘"],
      "answer": "分类",
      "explanation": "监督学习使用带标签数据训练模型，分类是典型监督学习任务。",
      "difficulty": "easy",
      "knowledge_point": "监督学习"
    }
  ]
}
```

`question_type` 只允许：

```text
single_choice / true_false / short_answer / coding
```

`difficulty` 只允许：

```text
easy / medium / hard
```

### 8.6 智能体步骤 agent_steps

前端展示多智能体运行过程，统一使用：

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

`status` 只允许：

```text
pending / running / completed / warning / failed
```

第一阶段可以不做真实时间，先写固定字符串或空值。

## 9. 智能体开发统一约定

### 9.1 智能体放在哪里

智能体属于后端，不是单独的软件。

目录：

```text
backend/app/agents/
```

调度器：

```text
backend/app/services/orchestrator.py
```

模型客户端：

```text
backend/app/services/llm_client.py
```

### 9.2 第一阶段智能体列表

第一阶段先做轻量版：

| 智能体 | 代码名 | 作用 |
| --- | --- | --- |
| 画像智能体 | `ProfileAgent` | 从用户输入提取 8 个维度画像 |
| 知识库智能体 | `KnowledgeAgent` | 根据 course_id 获取课程知识点 |
| 诊断智能体 | `DiagnosisAgent` | 分析知识短板 |
| 路径规划智能体 | `PlannerAgent` | 生成阶段化学习路径 |
| 资源生成智能体 | `ResourceAgent` | 生成 5 类资源 |
| 思维导图智能体 | `MindMapAgent` | 生成 Mermaid 思维导图 |
| 质量检查智能体 | `ReviewAgent` | 检查结果是否完整、合理、安全 |

第二阶段再细拆：

```text
LectureAgent
QuizAgent
ReadingAgent
PracticeAgent
MultimodalAgent
AssessmentAgent
```

### 9.3 智能体代码接口

所有智能体统一使用 `run()` 方法。

示例：

```python
class ProfileAgent:
    def __init__(self, llm_client):
        self.llm = llm_client

    def run(self, context: dict) -> dict:
        return {}
```

`context` 统一包含：

```json
{
  "session_id": "demo_session_001",
  "course_id": "ai_intro",
  "user_message": "...",
  "profile": {},
  "diagnosis": {},
  "learning_path": [],
  "knowledge_context": []
}
```

统一要求：

- 智能体不要直接调用具体模型 API。
- 智能体只能调用 `self.llm.chat(...)`。
- 智能体输出必须符合第 8 节的数据格式。
- 单个智能体失败不能让整个流程崩溃，应返回 `warning` 或 fallback 内容。

### 9.4 大模型可替换约定

不要在智能体里写死讯飞星火、DeepSeek 或 Qwen 的 API。

统一抽象：

```python
class BaseLLMClient:
    def chat(self, messages: list[dict], **kwargs) -> str:
        raise NotImplementedError
```

不同模型单独实现：

```text
SparkClient
DeepSeekClient
QwenClient
MockLLMClient
```

通过 `.env` 控制：

```env
LLM_PROVIDER=mock
SPARK_API_KEY=
DEEPSEEK_API_KEY=
QWEN_API_KEY=
```

第一阶段默认：

```text
LLM_PROVIDER=mock
```

第二阶段再切换为：

```text
LLM_PROVIDER=spark
```

## 10. 前端开发统一约定

### 10.1 前端目录

```text
frontend/src/
  main.js
  App.vue
  router/
    index.js
  stores/
    useEduAgentStore.js
  api/
    client.js
    eduagent.js
  views/
    HomeView.vue
  components/
    ChatPanel.vue
    ProfilePanel.vue
    LearningPathPanel.vue
    ResourceCard.vue
    AgentStatusPanel.vue
    MindMapViewer.vue
```

### 10.2 第一阶段页面结构

第一阶段先做一个首页工作台，不做复杂多页面。

布局：

```text
左侧：学生对话输入
中间：学习路径 + 资源卡片
右侧：学生画像 + 智能体状态
```

### 10.3 前端状态统一

Pinia store 统一维护：

```js
{
  session_id: 'demo_session_001',
  course_id: 'ai_intro',
  user_message: '',
  profile: null,
  diagnosis: null,
  learning_path: [],
  resources: [],
  agent_steps: [],
  loading: false,
  error: null
}
```

### 10.4 前端环境变量

`frontend/.env.example`：

```env
VITE_API_BASE_URL=http://localhost:8000
```

前端不允许在组件里写死后端地址，必须从环境变量读取。

### 10.5 前端展示规则

- 中文标题从后端 `label` 或前端映射中读取。
- Markdown 内容统一用 Markdown 渲染组件展示。
- Mermaid 内容统一交给 `MindMapViewer.vue`。
- `resources.type` 决定资源卡片图标和样式。
- 所有异步请求必须有 loading 状态。
- 请求失败时不能白屏，要显示错误提示。

## 11. 后端开发统一约定

### 11.1 后端目录

```text
backend/app/
  main.py
  config.py
  schemas/
    common.py
    agent.py
    profile.py
    resource.py
  routers/
    health.py
    courses.py
    agents.py
  services/
    orchestrator.py
    llm_client.py
    course_loader.py
  agents/
    profile_agent.py
    knowledge_agent.py
    diagnosis_agent.py
    planner_agent.py
    resource_agent.py
    mindmap_agent.py
    review_agent.py
  mock/
    demo_result.json
```

### 11.2 后端启动方式

统一命令：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 11.3 CORS 统一

后端必须允许前端访问：

```text
http://localhost:5173
```

### 11.4 后端响应规则

- 所有接口都返回统一响应外壳。
- 所有异常都返回 JSON，不返回 HTML 错误页。
- 第一阶段 mock 数据必须和真实接口结构一致。
- 后端字段名统一 snake_case。
- `session_id` 和 `course_id` 不能为空。

## 12. Mock 数据统一

第一阶段先用统一演示案例。

用户输入：

```text
我是电子信息专业大二学生，学过 Python，但机器学习基础比较薄弱。我想用两周时间入门人工智能，重点理解神经网络和自然语言处理，希望多给我一些图解、代码案例和练习题。
```

mock 数据存放：

```text
backend/app/mock/demo_result.json
```

要求：

- mock 数据必须完全符合 `/api/agents/run` 的响应格式。
- 前端第一阶段只对接这个格式。
- 后续真实智能体输出也必须保持同样格式。

## 13. Git 协作统一

### 13.1 分支建议

主分支：

```text
main
```

开发分支：

```text
feat/frontend-workbench
feat/backend-api
feat/agent-knowledge
docs/stage1-plan
```

### 13.2 提交信息格式

统一格式：

```text
类型: 简短说明
```

常用类型：

```text
feat: 新功能
fix: 修复问题
docs: 文档
style: 样式调整
refactor: 重构
test: 测试
chore: 配置或杂项
```

示例：

```text
feat: add agents run mock api
docs: add api contract
style: polish dashboard cards
```

### 13.3 提交前检查

每次提交前确认：

```text
没有提交 .env
没有提交 node_modules
没有提交 .venv
前端能启动
后端能启动
README 或文档有必要更新
```

## 14. 文档统一

第一阶段至少需要这些文档：

```text
docs/api/api-contract.md
docs/architecture/system-architecture.md
docs/architecture/agent-collaboration-flow.md
docs/schemas/student-profile-schema.md
docs/development/stage1-development-plan.md
```

后续提交前补充：

```text
docs/development/system-development-doc.md
docs/testing/test-doc.md
docs/presentation/competition-ppt.md
docs/presentation/demo-video-script.md
docs/development/ai-coding-tools.md
docs/development/open-source-license.md
```

## 15. 内容安全和防幻觉统一

第一阶段至少在结构上体现：

1. 生成内容带 `source` 字段。
2. 质量检查智能体输出 `review`。
3. 资源带 `quality_status`。
4. 当知识库不足时，后端应允许返回提示：

```text
当前课程知识库证据不足，以下内容为通用学习建议。
```

第二阶段再加入：

```text
课程知识库检索
来源引用
敏感内容过滤
结构化 JSON 校验和重试
```

## 16. 第一阶段验收标准

第一阶段完成的标准不是“所有高级技术都接好”，而是：

1. `frontend/` 可以启动。
2. `backend/` 可以启动。
3. `/api/health` 正常返回。
4. `/api/agents/run` 返回统一格式 JSON。
5. 前端能调用后端。
6. 输入学生情况后，页面能展示学生画像。
7. 页面能展示学习诊断。
8. 页面能展示学习路径。
9. 页面能展示至少 5 类学习资源。
10. 页面能展示智能体运行状态。
11. mock 数据格式和未来真实智能体输出格式一致。
12. README 或文档里写明如何运行。

## 17. 今天开始的任务清单

### 组长今天完成

```text
1. 把本文档发给组员确认
2. 创建 docs/api/api-contract.md 初稿
3. 创建 knowledge_base/courses/ai_intro/ 目录规划
4. 写 demo 用户输入和 demo_result.json 内容草稿
5. 确认前后端负责人
```

### 前端今天完成

```text
1. 创建 frontend/
2. 初始化 Vue 3 + Vite
3. 安装 Element Plus、Pinia、Axios
4. 跑通 npm run dev
5. 做首页工作台静态布局
```

### 后端今天完成

```text
1. 创建 backend/
2. 创建 Python 3.13+ 虚拟环境
3. 安装 FastAPI、Uvicorn、Pydantic
4. 实现 GET /api/health
5. 实现 POST /api/agents/run mock 返回
```

## 18. 不能随便改的统一项

以下内容改动前必须三个人同步确认：

```text
1. 技术栈
2. 目录结构
3. API 路径
4. API 响应外壳
5. JSON 字段命名方式
6. profile 8 个维度字段名
7. resources 类型枚举
8. course_id 机制
9. session_id 机制
10. mock 数据格式
```

这些是前端、后端、智能体三方对接的地基，不能各自发挥。
