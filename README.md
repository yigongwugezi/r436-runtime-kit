# 🎓 EduAgent — 多智能体个性化学习资源生成系统

基于 **DeepTutor**（港大，Apache 2.0）多智能体主引擎 + **OpenMAIC**（清华，MIT）多模态课件引擎，底层大模型全面接入科大讯飞系列产品的个性化学习系统。

## 🏗️ 多智能体架构（8 Agent + 1 引擎）

| Agent | 来源 | 角色 |
|-------|------|------|
| InvestigateAgent | DeepTutor 内置 | 意图分析专家 — 从对话中提取学习需求 |
| NoteAgent | DeepTutor 内置 | 结构化记录专家 — 生成学习摘要和证据链 |
| **Profiler Agent** | Socratic ES (MIT) | 学生画像专家 — 构建 6 维动态画像 |
| PlanAgent | DeepTutor 内置 | 路径规划专家 — 分阶段学习路径 |
| ManagerAgent | DeepTutor 内置 | 资源调度专家 — 按阶段调度生成引擎 |
| CheckAgent | DeepTutor 内置 | 质量审核专家 — Agent 间互审 + 防幻觉 |
| SolveAgent | DeepTutor 内置 | 智能辅导专家 — 即时答疑 + 苏格拉底追问 |
| **Grading Agent** | GRADE (BEA 2025) | 批改评估专家 — 4 维评分 + 5 类错误归类 |
| OpenMAIC 引擎 | OpenMAIC (MIT) | 多模态课件 — PPT + TTS + 动画分镜 |

## 🚀 快速启动

### 前置条件

- Docker & Docker Compose
- 讯飞星火 API Key（[注册获取](https://xinghuo.xfyun.cn/)）

### 1. 配置环境

```bash
cp .env.example .env
# 编辑 .env 填入讯飞 API Key
```

### 2. 一键启动

```bash
docker-compose up -d
```

### 3. 上传课程知识库

```bash
curl -X POST http://localhost:8000/api/rag/upload \
  -F "files=@knowledge_base/courses/ai_intro/chapters/*.md"
```

### 4. 打开浏览器

```
http://localhost:3000
```

## 📂 项目结构

```
EduAgent/
├── config/
│   ├── agents.yaml              # 8 个 Agent 注册配置
│   ├── providers.yaml           # 讯飞 Spark/SeeDance/TTS/ASR/OCR
│   └── mcp_servers.yaml         # MCP 外部工具注册
├── external_agents/
│   ├── socratic_profiler/       # 学生画像 Agent 服务（FastAPI :8001）
│   └── grade_agent/             # 批改评估 Agent 服务（FastAPI :8002）
├── integrations/                # 讯飞 SDK 集成层
│   ├── spark_client.py          # 星火 LLM 客户端
│   ├── seedance_client.py       # SeeDance 视频生成
│   └── xunfei_platform.py       # TTS/ASR/OCR
├── frontend-extension/          # Next.js 前端（:3000）
│   ├── app/
│   │   ├── page.tsx             # 对话页
│   │   ├── profile/page.tsx     # 画像页
│   │   ├── grading/page.tsx     # 批改页
│   │   └── analytics/page.tsx   # 分析页
│   ├── components/              # 组件（雷达图/错误标签/进度流/骨架屏）
│   ├── hooks/                   # 数据 hooks
│   └── types/                   # TypeScript 类型
├── knowledge_base/              # 课程知识库（《人工智能导论》8 章）
├── docker-compose.yml           # 4 服务编排
├── .env.example                 # 环境变量模板
└── outputs/                     # 方案文档
    └── 最终技术方案.md
```

## 🔗 开源协议标注

| 项目 | 协议 | 用途 |
|------|------|------|
| DeepTutor (HKUDS) | Apache 2.0 | 多智能体主引擎、RAG、记忆系统 |
| Socratic Education System | MIT | 学生画像构建智能体 |
| GRADE (AIM-SCU) | 开源 | 自动批改智能体 |
| OpenMAIC (THU-MAIC) | MIT | 多模态课件生成引擎 |
| 讯飞星火 Spark | 科大讯飞 | 底层大语言模型 |
| 讯飞 SeeDance | 科大讯飞 | 多模态视频生成 |
| 讯飞开放平台 | 科大讯飞 | TTS/ASR/OCR |

## 🛡️ 防幻觉机制（五层防线）

1. **ManagerAgent 上下文限制** — 生成时传入知识库上下文，限制 LLM 边界
2. **CheckAgent 逐条审核** — 跨 Agent 一致性检查 + 内容扎实性验证
3. **Memory Graph 证据溯源** — 每条关键结论追溯到知识库来源
4. **讯飞星火安全过滤** — API 层面拦截敏感违规内容
5. **教育边界声明** — 明确只提供学习辅导，不代写作业/考试作弊
