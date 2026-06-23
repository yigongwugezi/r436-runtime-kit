# 页面说明文档

## 路由概览

| 路由 | 页面文件 | 说明 |
|------|----------|------|
| `/login` | `LoginPage.tsx` | 登录/注册页 |
| `/` | `Home.tsx` | 首页 - 科目管理 |
| `/chat` | `ChatPage.tsx` | AI 对话页 |
| `/resources` | `ResourceLibrary.tsx` | 资源库列表 |
| `/resources/:id` | `ResourceLibrary.tsx` | 资源详情（弹窗） |
| `/path` | `LearningPathPage.tsx` | 学习路径 |
| `/profile` | `ProfilePage.tsx` | 学习画像 |
| `/analytics` | `LearningAnalyticsPage.tsx` | 学习分析 |
| `/timeline` | `LearningTimelinePage.tsx` | 学习时间线 |

---

## 各页面详情

### 1. 登录页 `/login`
- **组件**: `LoginPage.tsx`
- **功能**: 学习者登录/注册，管理本地 learner 实例
- **依赖**: `localStorage` 存储 learner 信息
- **状态**: 未登录时路由守卫自动重定向到此页

### 2. 首页 `/`
- **组件**: `Home.tsx`
- **功能**: 显示用户科目列表，支持新建/删除科目，激活科目后跳转对话页
- **数据来源**: `useSubjectStore` (Zustand)
- **子组件**: 无独立子组件

### 3. AI 对话 `/chat`
- **组件**: `ChatPage.tsx`
- **功能**: 多轮对话、学习需求输入、工作流管线（画像→路径→资源）展示
- **关键子组件**:
  - `MessageBubble` — 消息气泡（支持 Markdown 渲染）
  - `AgentPipelineProgress` — 多智能体生成管线进度展示
  - `ChatHistorySidebar` — 历史会话侧栏
  - `ChatClarification` — 低置信度澄清引导
  - `PromptTemplates` — 快捷输入模板
- **数据来源**: `useChatStore`, `useStreamChat`

### 4. 资源库 `/resources`
- **组件**: `ResourceLibrary.tsx`
- **功能**: 资源列表、搜索、筛选、详情弹窗、做题交互、收藏、标记完成
- **关键子组件**:
  - `ResourceCard` — 资源卡片
  - `ResourceFilters` — 筛选栏（类型、难度、来源等）
  - `QuizAnswerer` — 随堂练习做题器
  - `FeedbackForm` — 资源评价表单
  - `LongContent` — 长内容折叠
  - `QualityStatusPopover` — 质检状态说明弹窗
- **URL 参数**: `?type=`, `?difficulty=`, `?search=`, `?stage=`, `?taskId=`, `?resourceIds=`

### 5. 学习路径 `/path`
- **组件**: `LearningPathPage.tsx`
- **功能**: 展示分阶段的学习路径，节点状态（锁定/未开始/进行中/已完成），掌握度
- **关键子组件**:
  - `StageSection` — 阶段折叠组件
  - `NodeCard` — 知识点节点卡片
- **数据来源**: `useLearningPath`

### 6. 学习画像 `/profile`
- **组件**: `ProfilePage.tsx`
- **功能**: 10 维学生画像展示，包含雷达图、维度详析、知识短板、学习偏好
- **关键子组件**:
  - `DimensionRadar` — 能力雷达图 SVG
  - `DimensionBar` — 维度概要进度条
  - `ProfileDimensionCard` — 维度详情卡片（含置信度、支撑证据）
- **数据来源**: `useProfile`

### 7. 学习分析 `/analytics`
- **组件**: `LearningAnalyticsPage.tsx`
- **功能**: 学习数据统计、薄弱知识点、学习建议、趋势图表、诊断入口
- **关键子组件**:
  - `StatCard` — 指标卡片
  - `ProgressRing` — 正确率环形图
  - `CompletionTrendChart` — 资源完成趋势图
  - `QuizTrendChart` — Quiz 正确率折线图
  - `EventDistributionChart` — 事件分布条形图
  - `ResourceTypeChart` — 资源类型使用图
  - `DiagnosisPanel` — 诊断详情面板
- **数据来源**: `useLearningAnalytics`

### 8. 学习时间线 `/timeline`
- **组件**: `LearningTimelinePage.tsx`
- **功能**: 按时间倒序展示学习行为记录，支持事件类型筛选和时间范围筛选
- **关键子组件**:
  - `TimelineItem` — 时间线条目（可展开详情）
  - `TimelineEventDetail` — 事件详情面板
  - `TimelineSummaryCard` — 统计概览卡片
  - `FilterBar` — 筛选条
- **数据来源**: `useLearningEvents`
