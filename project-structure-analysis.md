# EduAgent 项目结构分析报告

> 生成时间: 2025-07-15 | 项目: D:\EduAgent (r436-runtime-kit)

---

## 1. 顶层目录

| 目录/文件 | 说明 |
|-----------|------|
| `backend/` | FastAPI后端主体 |
| `backend/app/agents/` | 10个智能体 (~360KB) |
| `backend/app/services/` | 27个服务模块 |
| `backend/app/routers/` | 20个API路由 |
| `backend/app/schemas/` | 10个Pydantic模型 |
| `backend/app/db/` | SQLAlchemy + SQLite |
| `backend/app/rag/` | FAISS向量知识库 |
| `external_agents/deeptutor/` | DeepTutor子项目 |
| `docs/` | ~50个架构/API/前端文档 |
| `venv/` | Python虚拟环境 |

---

## 2. 10大智能体

| Agent ID | 文件 | 职责 |
|----------|------|------|
| `conversation_agent` | conversation_agent.py (56KB) | 对话总控——唯一出口，意图理解，深度探测7维画像 |
| `profile_agent` | profile_agent.py (29KB) | 画像提取——7维度，LLM+规则+增量更新 |
| `knowledge_agent` | knowledge_agent.py (5KB) | 知识检索——RAG(FAISS)→课程目录→LLM扩展 |
| `diagnosis_agent` | diagnosis_agent.py (82KB) | 诊断——标准+自适应三步(定位→精细→掌握度矩阵) |
| `planner_agent` | planner_agent.py (90KB) | 路径规划——3种模式，4层降级 |
| `resource_agent` | resource_agent.py (70KB) | 资源生成——6类资源，分批+审核闭环 |
| `question_agent` | question_agent.py (27KB) | 试题生成——5种题型+变式题 |
| `grading_agent` | grading_agent.py (12KB) | 批改——5类错误→自动衔接 |
| `review_agent` | review_agent.py (30KB) | 审核——7项质量检查 |
| `multimodal_agent` | multimodal_agent.py (10KB) | 多模态——12种任务类型 |

注册机制：`@register_agent` 装饰器 → 全局 `_AGENT_REGISTRY`，`AgentFactory` 懒加载+共享LLM。

---

## 3. LangGraph编排引擎

```
intent_router (ConversationAgent)
 ├── conversation → END           (纯聊天)
 ├── profile→knowledge→diagnosis→planner→resource→review→reply (全流程)
 │                                                    ↓
 │                               review发现问题 → resource (重试≤2次)
 └── [单Agent] → 审核闭环 → END
```

### 动态/实时机制

- **事后事实提取**: `_extract_facts_after_chat()` — 每轮对话后自动提取，6种探测类型感知
- **动态Persona**: `_build_chat_persona()` — 根据fact深度分4阶段生成探测指令
- **自动模式选择器**: 7维完整 → 注入 `[[mode-pick:教材式,日课式,精进式]]`
- **增量画像更新**: facts变更 → `_profile_dirty` 标志 → 规则重算（不调LLM）

---

## 4. 学生画像系统

### 7核心维度
background / target_course / knowledge_base / weak_points / learning_goal / time_budget / preference

每个维度有专属间接探测策略（禁止直接询问，必须间接验证）。

### profile_v2 结构
按课程类别细化：computing(6子维度) / math(6) / language(6) / physics(6) / general(6)
+ 学习状态(兴趣/信心/投入/调节/压力) + 上下文(目标/截止/时间/偏好)

### 数据流
用户自然语言 → `profile_extractor.py` → `conversation_state.facts` → `ProfileAgent`(LLM) → `profile_v2`(结构化) → SQLite

---

## 5. 资源生成

6类: lecture / mindmap / quiz / reading / practice / multimodal

三层策略: DeepTutor → LLM分批(每批2阶段) → RAG+规则兜底

审核闭环: resource → review → 发现问题 → 重试修正(max 2次)

---

## 6. 学习路径

三种模式: 教材式(章→节) / 日课式(周→日) / 精进式(focus弱项)

四层降级: LLM章节 → DeepTutor结构 → LLM管道兜底 → 教材/规则

---

## 7. 评估体系

- **诊断**: 自适应三步(快速定位15题→精细诊断30题→掌握度矩阵+艾宾浩斯)
- **批改**: 5类错误(概念/计算/审题/方法/遗忘)→自动衔接(推荐/练习/复习队列[1,2,4,7,15,30天])
- **闭环调度器**: 事件驱动+3天重评估+动态阈值+SSE推送
- **追踪器**: 去重+模式转发+SQLite持久化
- **推荐引擎**: 6源(未完成/低准确率/练习/阶段/高频薄弱/画像个性化)

---

## 8. 技术栈

- 后端: Python 3.13 + FastAPI + LangGraph + SQLAlchemy/SQLite
- LLM: 统一BaseLLMClient (mock/deepseek/星火/Qwen)
- 向量: FAISS + LlamaIndex + text2vec-large-chinese
- 外部: DeepTutor子项目
- 多模态: 星火图片/Qwen VL/WAN视频
- 前端: React 19 + TypeScript + Vite + Zustand + Tailwind (不在本仓库)
