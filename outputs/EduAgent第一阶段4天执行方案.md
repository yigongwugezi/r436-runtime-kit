# EduAgent 第一阶段 4 天执行方案

## 1. 第一阶段目标

第一阶段周期定为 4 天。

目标不是做完整系统，而是做出一个可以演示的 EduAgent MVP 工作台：

```text
学生输入学习情况
-> 后端返回画像、诊断、学习路径、资源、智能体状态
-> 前端完整展示结果
```

第一阶段允许使用 mock 数据，重点是先把软件闭环跑通。

## 2. 第一阶段产品形态

第一阶段只做一个核心页面：

```text
EduAgent 学习工作台
```

页面布局统一为：

```text
顶部：系统标题 + 当前课程选择
左侧：学生输入区
中间：学习路径 + 学习资源
右侧：学生画像 + 智能体运行状态
```

第一阶段不是宣传页，不做登录注册，不做课程商城，不做后台管理。

## 3. 固定演示课程

第一阶段只做一门课程：

```text
course_id: ai_intro
course_name: 人工智能导论
```

但代码和接口必须保留 `course_id`，为后续多课程扩展做准备。

知识库第一阶段至少准备 4 章：

```text
01 人工智能概述
02 搜索算法
03 机器学习基础
04 神经网络基础
```

有余力再补：

```text
05 NLP 入门
06 计算机视觉入门
07 强化学习基础
08 AI 伦理与安全
```

## 4. 固定演示输入

第一阶段统一使用这个案例测试：

```text
我是电子信息专业大二学生，学过 Python，但机器学习基础比较薄弱。我想用两周时间入门人工智能，重点理解神经网络和自然语言处理，希望多给我一些图解、代码案例和练习题。
```

所有 mock 数据、页面展示和演示话术都围绕这个案例。

## 5. 第一阶段必须展示的内容

页面最终必须展示：

```text
1. 学生画像 8 个维度
2. 学习诊断
3. 两周学习路径
4. 5 类学习资源
5. 智能体运行状态
6. 质量检查结果
```

5 类资源固定为：

```text
lecture：课程讲义
mindmap：思维导图
quiz：练习题
reading：拓展阅读
practice：Python 实操案例
```

可选加分资源：

```text
multimodal：视频脚本 / PPT 大纲 / 动画分镜
```

## 6. 第一阶段接口范围

第一阶段只实现 3 个接口：

```text
GET /api/health
GET /api/courses
POST /api/agents/run
```

主流程只接：

```text
POST /api/agents/run
```

前端点击“生成学习方案”后，只调用这个接口。

## 7. /api/agents/run 统一格式

请求格式：

```json
{
  "session_id": "demo_session_001",
  "course_id": "ai_intro",
  "user_message": "我是电子信息专业大二学生，学过 Python，但机器学习基础比较薄弱。我想用两周时间入门人工智能，重点理解神经网络和自然语言处理，希望多给我一些图解、代码案例和练习题。"
}
```

响应格式：

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
  "request_id": "req_demo_001"
}
```

前端、后端、智能体都必须围绕这个格式开发。

## 8. 第一阶段 UI 风格

统一风格：

```text
现代 AI 学习工作台
浅色背景
蓝绿色主色
卡片式展示
清晰分区
有生成中 loading
有智能体运行状态
Markdown 能正常显示
Mermaid 思维导图能正常显示
```

前端使用：

```text
Vue 3 + Vite + Element Plus
```

## 9. 第一阶段不做什么

第一阶段明确不做：

```text
登录注册
真实数据库
复杂多页面
真实视频生成
完整 RAG
LangGraph
学习评估模型
多课程真实接入
PostgreSQL / Redis / Celery
Docker
```

这些放到第二阶段或后续增强。

## 10. 三人任务分工

### 组长任务

第一阶段交付：

```text
1. API 契约文档
2. 学生画像 Schema
3. 人工智能导论知识库初版
4. demo_result.json mock 输出样例
5. 多智能体流程说明
6. 第一阶段验收与整合
```

重点负责：

```text
画像 8 维度
诊断逻辑
学习路径逻辑
资源内容结构
演示案例
文档和最终表达
```

### 前端任务

第一阶段交付：

```text
1. Vue 项目跑起来
2. 首页学习工作台
3. ChatPanel
4. ProfilePanel
5. LearningPathPanel
6. ResourceCard
7. AgentStatusPanel
8. MindMapViewer
9. 接入 /api/agents/run
10. 展示画像、诊断、路径、资源和智能体状态
```

### 后端任务

第一阶段交付：

```text
1. FastAPI 项目跑起来
2. GET /api/health
3. GET /api/courses
4. POST /api/agents/run
5. Pydantic 数据模型
6. 读取 demo_result.json mock 返回
7. AgentOrchestrator 雏形
8. LLM Client 壳子
9. CORS 配置
```

## 11. 四天安排

### Day 1：定格式 + 搭骨架

组长：

```text
完成 API 契约
完成 profile schema
完成 demo_result.json 第一版
```

前端：

```text
Vue 项目跑起来
Element Plus 接好
首页工作台静态布局出来
```

后端：

```text
FastAPI 跑起来
/api/health 可用
/api/courses 可用
/api/agents/run 返回简单 mock
```

### Day 2：前后端接通

组长：

```text
补知识库 4 章
补多智能体流程说明
检查 mock 格式
```

前端：

```text
接 /api/agents/run
展示 profile
展示 learning_path
展示 agent_steps
```

后端：

```text
读取 demo_result.json
统一响应格式
Pydantic 模型初版
解决跨域
```

### Day 3：资源展示完整

组长：

```text
完善 5 类资源内容
补质量检查 review
准备演示话术
```

前端：

```text
展示 5 类资源卡片
渲染 Markdown
渲染 Mermaid
展示 quiz 和 practice
```

后端：

```text
AgentOrchestrator 雏形
LLM Client 壳子
MockLLMClient
```

### Day 4：联调验收 + 推 GitHub

组长：

```text
验收所有功能
整理 README 启动说明
记录问题和第二阶段任务
```

前端：

```text
UI 打磨
loading / error / empty 状态
页面适配演示屏幕
```

后端：

```text
接口稳定
错误处理
补运行说明
```

## 12. 第一阶段最终验收标准

四天结束时必须做到：

```text
1. 前端 npm run dev 能启动
2. 后端 uvicorn 能启动
3. /api/health 返回 ok
4. /api/courses 返回人工智能导论
5. /api/agents/run 返回统一格式 JSON
6. 前端能调用后端接口
7. 输入固定学生案例后，页面能展示学生画像
8. 页面能展示学习诊断
9. 页面能展示两周学习路径
10. 页面能展示 5 类学习资源
11. 页面能展示智能体运行状态
12. 页面能展示质量检查结果
13. 页面无明显报错
14. GitHub 仓库结构清晰
15. README 有启动说明
```

## 13. 第一阶段结束时页面应该长什么样

最终演示流程：

```text
1. 打开网页，看到 EduAgent 学习工作台
2. 顶部显示当前课程：人工智能导论
3. 左侧输入学生学习情况
4. 点击“生成学习方案”
5. 出现 loading 或智能体运行状态
6. 右侧出现 8 维学生画像
7. 中间出现两周学习路径
8. 下方出现 5 类资源卡片
9. 智能体状态显示全部 completed
10. 页面没有报错，刷新后还能再演示
```

## 14. 不能随便改的内容

以下内容改动前必须三个人同步确认：

```text
1. 页面布局
2. API 路径
3. /api/agents/run 请求和响应格式
4. profile 8 个维度
5. resources 资源类型
6. course_id = ai_intro
7. mock 数据结构
8. 前端字段读取方式
9. 后端统一响应外壳
```

第一阶段核心原则：

```text
先闭环，再增强。
先能演示，再接真实 AI。
先统一格式，再各自开发。
```

