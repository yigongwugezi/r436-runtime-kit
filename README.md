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

> **v1.1.0 起：AI 凭据为每用户配置，不再放在 `.env`。**
> 所有 API key / secret / app_id 由每个登录用户在前端「系统设置 → AI 模型配置」
> 中独立填写（存 `user_ai_config` 表，默认为空，用户之间互不可见）。
> 未配置密钥时，AI 功能返回 `AI_CONFIG_MISSING` 友好提示并引导前往设置页，
> 不会产出模拟内容。接口详见 `docs/api/api-contract.md` 第 3 节。

每用户可配置的服务：主对话模型（DeepSeek / Qwen / GLM / OpenAI，选提供商+填 key；
Base URL 与模型名为代码内官方默认值）、通义 DashScope（识图/图像/视频）、讯飞星火
（图像与识图三元组）、Wan 视频、ARK/Seedream、讯飞智文 AIPPT、Tavily 搜索。

后端 `.env` 只保留技术项（超时、重试、温度、端点 URL、角色模型微调、搜索缓存与
熔断参数等），示例：

```env
APP_NAME=r436-runtime-kit-backend
APP_ENV=development
FRONTEND_ORIGIN=http://localhost:5173
# user = 真实提供商由每个用户在系统设置中选择（默认部署值）；
# mock = 自动化测试逃生舱（仅当用户未配置密钥时生效，用户配置始终优先）。
LLM_PROVIDER=user
LLM_TEMPERATURE=0.2
```

注意：真实 `.env` 不要提交到 GitHub。

### 资源比赛模式

比赛核心只需要演示账号在「系统设置 → AI 模型配置」中选择 DeepSeek 并填写有效
API Key。讲义、阅读材料、练习材料与基础导图使用该核心能力；`pyahocorasick`
缺失时会使用安全的纯 Python 内容检查降级。

以下服务均为可选项，在设置页留空不会阻止后端或已生成资源读取：Tavily（联网搜索）、
AIPPT（PPT）、通义 DashScope / Wan（视频/图像）、ARK/Seedream、讯飞星火、
OpenAI/GLM（备用提供商）、DeepTutor、RAG 与 Manim。未配置时接口会返回明确
unavailable/provider-not-configured 状态，不会创建空资源或伪造搜索结果。

不要提交真实 `backend/.env`；从 `backend/.env.example` 复制后仅在本机填写变量值。

## 开源依赖与协议声明

本系统在开发过程中使用了以下开源项目及 AI 工具/框架，在此列出名称、来源及相关协议要求。

### 前端依赖

| 名称 | 来源 | 协议 |
|------|------|------|
| React | https://react.dev | MIT |
| TypeScript | https://www.typescriptlang.org | Apache-2.0 |
| Vite | https://vitejs.dev | MIT |
| React Router | https://reactrouter.com | MIT |
| Zustand | https://zustand.docs.pmnd.rs | MIT |
| Axios | https://axios-http.com | MIT |
| Tailwind CSS | https://tailwindcss.com | MIT |
| @tailwindcss/typography | https://github.com/tailwindlabs/tailwindcss-typography | MIT |
| Mermaid | https://mermaid.js.org | MIT |
| react-markdown | https://github.com/remarkjs/react-markdown | MIT |
| remark-gfm | https://github.com/remarkjs/remark-gfm | MIT |
| remark-math | https://github.com/remarkjs/remark-math | MIT |
| rehype-katex | https://github.com/remarkjs/remark-math | MIT |
| KaTeX | https://katex.org | MIT |
| ECharts | https://echarts.apache.org | Apache-2.0 |
| echarts-for-react | https://github.com/hustcc/echarts-for-react | MIT |
| markmap-lib / markmap-view | https://markmap.js.org | MIT |
| react-syntax-highlighter | https://github.com/react-syntax-highlighter/react-syntax-highlighter | MIT |
| lucide-react | https://lucide.dev | ISC |

### 后端依赖

| 名称 | 来源 | 协议 |
|------|------|------|
| Python | https://www.python.org | PSF |
| FastAPI | https://fastapi.tiangolo.com | MIT |
| Uvicorn | https://www.uvicorn.org | BSD-3-Clause |
| Pydantic | https://docs.pydantic.dev | MIT |
| SQLAlchemy | https://www.sqlalchemy.org | MIT |
| httpx | https://www.python-httpx.org | BSD-3-Clause |
| LangGraph | https://langchain-ai.github.io/langgraph | MIT |
| LlamaIndex (llama-index-core) | https://www.llamaindex.ai | MIT |
| llama-index-vector-stores-faiss | https://github.com/run-llama/llama_index | MIT |
| FAISS (faiss-cpu) | https://github.com/facebookresearch/faiss | MIT |
| llama-index-embeddings-huggingface | https://github.com/run-llama/llama_index | MIT |
| sentence-transformers | https://www.sbert.net | Apache-2.0 |
| PyMuPDF (pymupdf4llm) | https://github.com/pymupdf/PyMuPDF | **AGPL-3.0** ⚠️ |
| ddgs (DuckDuckGo Search) | https://github.com/ivandabella/ddgs | MIT |
| python-multipart | https://github.com/Kludex/python-multipart | Apache-2.0 |

### AI 模型与外部服务

| 名称 | 来源 | 说明 |
|------|------|------|
| DeepSeek | https://www.deepseek.com | 默认 LLM Provider（deepseek-v4-pro）|
| 科大讯飞 星火 | https://www.xfyun.cn | 图像/语音多模态 Provider（可选）|
| 阿里云 DashScope / Qwen | https://dashscope.aliyun.com | 多模态生成与 VLM 评审（可选）|
| Wan Video | https://github.com/Wan-Video/Wan2.1 | 视频生成 Provider（可选）|
| HuggingFace Embedding Models | https://huggingface.co | RAG Embedding 模型 |

### 外部智能体项目

| 名称 | 来源 | 说明 |
|------|------|------|
| DeepTutor | https://github.com/HKUDS/DeepTutor (推断) | 终身个性化辅导系统 v1.5.0 |
| OpenMAIC | 独立前端子项目 | 开源多智能体教练 |

### ⚠️ 重要协议提示

- **PyMuPDF** 使用 **AGPL-3.0** 协议，属于强 Copyleft 许可证。若将本项目用于商业目的或作为 SaaS 服务提供，需特别注意 AGPL 协议的合规义务——包括但不限于向用户公开完整的源代码。如无法满足 AGPL 要求，建议替换为其他 PDF 解析库（如 pdfplumber、PyPDF2 等 MIT/BSD 协议的替代品）。
- 其余依赖大多使用 MIT、Apache-2.0、BSD 等宽松协议，商业使用友好，仅需保留版权声明。

---

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
