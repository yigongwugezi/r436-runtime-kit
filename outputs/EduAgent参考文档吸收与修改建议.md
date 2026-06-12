# EduAgent 参考文档吸收与修改建议

## 结论

你发来的《基于大模型的个性化资源生成与学习多智能体系统.md》整体方向是对的，适合作为“完整解决方案文档”的参考。

但它和我们当前已经确定的执行口径有几处冲突，需要统一：

- 原文档偏 4 周完整开发计划；我们当前按半个月推进。
- 原文档里前端多处写 React；我们现在确定用 Vue 3 + Vite + Element Plus。
- 原文档里 Python 写 3.11+；我们现在确定 Python 3.13+。
- 原文档里 Node.js 写 22.x；我们当前建议 Node.js 24.x LTS。
- 原文档里版本管理写 Gitee；我们已经创建 GitHub 仓库。
- 原文档把 LangChain、Chroma、PostgreSQL、完整 RAG 都放得比较靠前；我们第一阶段先保证 Web 闭环，后续增强。

所以建议：保留它的“总体方案、智能体设计、风险管理、交付物清单”思想，但技术栈和阶段安排要按我们自己的统一规范改。

## 可以直接吸收的内容

### 1. 项目定位

原文档对项目定位说得比较完整：

```text
EduAgent 是基于大模型的多智能体个性化学习资源生成与自适应学习系统。
```

这个可以吸收进 PPT 和系统开发说明书。

建议最终表述：

```text
EduAgent 是一个面向高等教育课程的多智能体个性化学习资源生成 Web 应用，系统通过对话式画像构建、多智能体协同、课程知识库和大模型生成能力，为学生自动规划学习路径并生成多模态学习资源。
```

### 2. 赛题需求对照表

原文档里的“赛题核心要求对照”很好，可以保留：

- 对话式画像：8 个维度
- 多智能体资源生成：10 个智能体
- 资源类型：讲义、思维导图、练习题、拓展阅读、代码实操案例
- 学习路径规划
- 智能辅导加分项
- 学习效果评估加分项
- 防幻觉与内容安全

这部分适合放进：

```text
docs/development/system-development-doc.md
PPT 功能设计页
答辩说明
```

### 3. 10 个智能体设计

原文档的智能体列表比较完整，可以作为最终系统设计目标：

| 智能体 | 是否第一阶段必须完整实现 |
| --- | --- |
| 对话画像智能体 | 必须 |
| 课程知识库智能体 | 必须有雏形 |
| 学习诊断智能体 | 必须 |
| 路径规划智能体 | 必须 |
| 内容讲解智能体 | 必须 |
| 题库生成智能体 | 必须 |
| 思维导图智能体 | 必须 |
| 实操案例智能体 | 必须 |
| 多模态资源智能体 | 可做脚本/提示词版本 |
| 质量检查智能体 | 必须有雏形 |

建议我们第一阶段按“7 个核心 Agent + ResourceAgent 内部拆资源”的方式做，文档中展示为 10 个智能体架构，代码中可以逐步细拆。

### 4. 防幻觉机制

原文档提到的防幻觉机制值得保留：

- RAG 知识库约束
- 质量检查智能体
- 引用来源标注
- 内容审核
- 低温生成
- 结构化输出校验

第一阶段可以先做到：

```text
source 字段
quality_status 字段
review 质量检查结果
mock/knowledge_base/llm 来源标识
```

第二阶段再接：

```text
RAG 检索
引用来源
内容审核接口
JSON 校验与重试
```

### 5. 风险管理

原文档风险管理部分可以直接吸收：

- 讯飞星火 API 不可用或额度不足
- LLM 输出格式不稳定
- 知识库内容来不及完成
- 前后端接口不匹配
- 多智能体编排复杂度超预期
- 开发时间不足

我们已经在协作规范里通过以下方式规避：

- 统一 LLM Client
- 第一阶段默认 mock
- API 契约先行
- mock 数据格式等同真实返回格式
- 第一阶段轻量顺序编排

## 必须修改的内容

### 1. 前端技术栈

原文档中多处写：

```text
React + Vite + TailwindCSS
```

现在统一改为：

```text
Vue 3 + Vite + Element Plus + Pinia + Axios + Mermaid
```

原因：

- 组员已有 Vue 方向方案
- Element Plus 适合快速搭后台/工作台式页面
- 比赛第一阶段更看重快速落地和稳定演示

### 2. 后端 Python 版本

原文档写：

```text
Python 3.11+
```

现在统一改为：

```text
Python 3.13+
```

注意：

- 全员最好统一到同一个小版本，比如 3.13.x。
- 如果有人使用 3.14，也要先确认 FastAPI、Pydantic、Chroma、模型 SDK 等依赖是否兼容。
- 后端依赖必须写入 `requirements.txt`，不要靠每个人自己随便安装。

### 3. Node.js 版本

原文档写：

```text
Node.js 22.x LTS
```

现在统一为：

```text
Node.js 24.x LTS
npm 11.x
```

### 4. 代码仓库

原文档写：

```text
Gitee
```

我们已经使用：

```text
GitHub
https://github.com/yigongwugezi/EduAgent
```

后续文档、PPT、README 都统一写 GitHub。

### 5. 开发周期

原文档按 4 周计划写。

我们当前应改成：

```text
半个月完成可演示版本。
```

推荐表述：

```text
项目采用分阶段开发策略：半个月内完成可演示 MVP，后续继续扩展 RAG、学习评估、知识追踪和认知诊断能力。
```

## 应该后置的内容

以下内容很有价值，但第一阶段不要作为阻塞项：

| 内容 | 建议阶段 |
| --- | --- |
| LangChain / LangGraph | 第二阶段或有余力再接 |
| Chroma / Qdrant 向量库 | 第二阶段 |
| PostgreSQL | 第二阶段或第三阶段 |
| Redis + Celery | 第三阶段，需要异步任务时再做 |
| Docker | 初赛提交前有时间再补 |
| NeuralCD / DINA | 学习效果评估加分项 |
| EdNet / ASSISTments | 认知诊断训练或展示规划，不作为第一阶段主线 |
| 真实视频生成 | 后续接 SeeDance 或多模态工具，第一阶段先生成视频脚本和分镜 |

## 建议合并后的最终口径

### 技术栈口径

```text
前端：Vue 3 + Vite + Element Plus + Pinia + Axios + Mermaid
后端：Python 3.13+ + FastAPI + Uvicorn + Pydantic
智能体：第一阶段自研轻量多智能体调度器，后续可扩展 LangGraph
大模型：讯飞星火 API 优先，DeepSeek/Qwen 备用
知识库：第一阶段 Markdown + JSON，第二阶段接 Chroma/Qdrant
数据存储：第一阶段 JSON/SQLite，后续扩展 PostgreSQL
开发工具：VS Code + GitHub
```

### 第一阶段口径

```text
第一阶段不追求完整平台化，先跑通可演示闭环：
用户输入学习情况 -> 生成学生画像 -> 学习诊断 -> 学习路径 -> 生成 5 类资源 -> 质量检查 -> 前端展示。
```

### 智能体口径

```text
系统设计展示 10 个智能体协同架构。
第一阶段代码先实现轻量版本，保证流程能跑通。
后续逐步将 ResourceAgent 细拆为 LectureAgent、QuizAgent、MindMapAgent、PracticeAgent、MultimodalAgent。
```

### 多课程口径

```text
第一阶段以《人工智能导论》为样例课程，但系统目录、接口和知识库结构均按多课程扩展设计。
新增课程时只需新增 course_id、course.json 和章节 Markdown 文档。
```

## 对原文档的具体修改建议

如果要把原文档改成我们团队正式方案，建议做这些替换：

1. 全文 `React + Vite + TailwindCSS` 替换为 `Vue 3 + Vite + Element Plus`。
2. 全文 `React-Markdown` 替换为 `markdown-it / md-editor-v3`。
3. 全文 `Python 3.11+` 替换为 `Python 3.13+`。
4. 全文 `Node.js 22.x LTS` 替换为 `Node.js 24.x LTS`。
5. 全文 `Gitee` 替换为 `GitHub`。
6. 把“4 周开发周期”改成“半个月完成 MVP，后续增强”。
7. 把第一阶段中 Chroma、LangChain、PostgreSQL、Docker 相关任务标记为“后续增强”。
8. 把文件结构中的 `frontend/src/pages/*.tsx` 改成 `frontend/src/views/*.vue`。
9. 把接口设计统一到 `/api/agents/run` 主流程接口，其他接口作为第二阶段补充。
10. 增加 `course_id`，确保系统支持多课程扩展。

## 最后建议

这份参考文档可以作为“完整解决方案”的材料库，但不能直接当第一阶段执行清单。

执行时以这两份文档为准：

```text
outputs/EduAgent团队分工与统一协作规范.md
outputs/EduAgent半个月开发路线图.md
```

参考文档里好的内容，逐步吸收到：

```text
docs/architecture/
docs/development/
docs/presentation/
```

