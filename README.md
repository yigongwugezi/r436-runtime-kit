# r436-runtime-kit

A course workflow runtime kit for local demo and module integration.

## 当前技术路线

前端技术栈已统一调整为：

- React 19 + TypeScript + Vite
- React Router
- Zustand
- Axios
- Tailwind CSS
- Mermaid
- React Markdown
- ECharts
- lucide-react

后端技术栈：

- Python 3.13.x
- FastAPI
- Uvicorn
- Pydantic
- 自研轻量模块调度器
- 统一 LLM Client，支持 `mock` 与 `deepseek`，后续可扩展星火、Qwen、本地模型

## 当前功能

- 对话式学习入口
- 学生画像模块，已接入 DeepSeek，可从学生自然语言描述中抽取画像
- 意图识别模块，采用轻量 Semantic Router 思路，可区分闲聊、画像询问、学习规划、答疑、资源请求和学习反馈
- 调度骨架
- 知识库检索、学习诊断、路径规划、资源生成、质量审核模块
- 学习路径展示接口
- 学习资源展示接口
- 流式对话接口
- 学习行为事件追踪接口
- 学习分析接口雏形

## 模块流程

```text
React 前端
  -> FastAPI 接口
  -> IntentAgent 意图识别
  -> AgentOrchestrator
  -> ProfileAgent
  -> KnowledgeAgent
  -> DiagnosisAgent
  -> PlannerAgent
  -> ResourceAgent
  -> ReviewAgent
  -> 返回画像、诊断、路径、资源、模块状态和审核结果
```

## 主要接口

第一阶段保留底层主流程接口：

```text
POST /api/agents/run
```

React 前端正式使用产品化接口：

```text
POST /chat/stream
POST /chat/send
GET  /profile
POST /profile/build
GET  /learning-path
GET  /resources
POST /feedback/event
GET  /learning-analytics
```

## 快速启动

### 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --port 8001
```

健康检查：

```text
http://localhost:8001/api/health
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

访问：

```text
http://localhost:5173
```

本地前端 `.env` 可配置：

```env
VITE_API_BASE_URL=http://localhost:8001
```

## 模型配置

后端 `.env` 示例：

```env
APP_NAME=r436-runtime-kit-backend
APP_ENV=development
FRONTEND_ORIGIN=http://localhost:5173
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.2
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

不想调用真实模型时：

```env
LLM_PROVIDER=mock
```

注意：真实 `.env` 不要提交到 GitHub。

## 团队协作规则

- 当前前端路线统一为 React + TypeScript + Vite。
- 后端继续使用 FastAPI + Python 3.13.x。
- 禁止对 `main` 分支执行 force push。
- 接口变更必须先同步到文档。
- 前端不得自行删除后端、文档和知识库目录。
- 后端不得随意改前端字段结构，涉及接口需同步前端。

## 第一阶段验收目标

输入学生学习情况后，系统能够展示：

- 学生画像
- 学习诊断
- 学习路径
- 至少 5 类学习资源
- 模块运行过程
- 学习行为追踪和基础学习分析
