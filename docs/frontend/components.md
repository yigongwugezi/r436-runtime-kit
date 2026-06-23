# 前端组件说明

## 布局组件 (`components/layout/`)

| 组件 | 说明 |
|------|------|
| `AppLayout` | 主布局容器，含左侧 ConsoleSidebar、移动端汉堡菜单抽屉、右侧主内容 Outlet |
| `ConsoleSidebar` | 左侧导航侧栏，支持展开/折叠，含用户信息、科目列表、导航按钮、聊天历史 |
| `Header` | 顶部导航栏（桌面端），显示 Logo、导航标签、用户下拉菜单 |
| `BottomNav` | 移动端底部导航（当前未使用） |

## 通用组件 (`components/common/`)

| 组件 | 说明 |
|------|------|
| `Modal` | 通用弹窗，支持标题、宽/超宽模式、点击遮罩/Esc 关闭、禁止 body 滚动 |
| `ConfirmDialog` | 确认弹窗，基于 Modal，支持 default/danger 变体 |
| `BaseCard` | 统一卡片容器，白底圆角阴影，支持 hover 效果 |
| `Toast` / `ToastProvider` | 全局 Toast 通知（success/error/warning/info），自动消失 |
| `ExpandableText` | 长文本折叠组件，超过行数时显示"展开全文"按钮 |
| `Loading` | 加载中状态（将被 PageLoading 统一替代） |
| `EmptyState` | 空状态展示（将被 PageEmpty 统一替代） |
| `Skeleton` | 骨架屏（当前未使用） |
| `PageState` | 页面级状态集合：`PageLoading`, `PageEmpty`, `PageError`, `FallbackBanner`, `RefreshOverlay`, `SourceTag`, `RetryActions` |
| `SourceBadge` | 数据来源标签（用户提供/智能体生成/系统推断/规则兜底） |
| `StatusBadge` | 通用状态标签 |
| `QualityStatusPopover` | 质检状态说明弹窗，含 fallback/审核问题/改进建议展示 |
| `Breadcrumb` | 面包屑导航（当前未使用） |
| `DebugPanel` | 开发调试面板（仅开发环境显示），拦截 fetch 记录 API 调用 |
| `ErrorBoundary` | 错误边界组件 |
| `RetryButton` | 重试按钮（当前未使用） |
| `SettingsModal` | 设置弹窗（个人资料、学习偏好、对话设置、诊断设置、数据管理） |
| `SectionHeader` | 区域标题组件 |
| `UserSetup` | 学习者创建/切换组件（当前未使用） |

## 对话组件 (`components/chat/`)

| 组件 | 说明 |
|------|------|
| `ChatClarification` | 低置信度澄清引导选项 |
| `ChatHistorySidebar` | 对话历史侧栏 |
| `PromptTemplates` | 快捷输入模板 |

## 分析组件 (`components/analytics/`)

| 组件 | 说明 |
|------|------|
| `DiagnosisPanel` | 诊断结果面板，展示薄弱知识点、优先级、置信度、推荐资源和阶段跳转 |

## 资源组件 (`components/resources/`)

| 组件 | 说明 |
|------|------|
| `ResourceCard` | 资源卡片（类型图标、标题、难度、标签、进度） |
| `ResourceFilters` | 资源筛选栏（类型、难度、来源、质检、学习状态、收藏） |
| `ResourceTypeRenderer` | 资源类型渲染器 |

## 画像组件 (`components/profile/`)

| 组件 | 说明 |
|------|------|
| `ProfileDimensionCard` | 画像维度详情卡片（分数条、值、置信度、支撑证据、低可信提示） |

## 时间线组件 (`components/timeline/`)

| 组件 | 说明 |
|------|------|
| `TimelineEventDetail` | 事件展开详情（分类型展示 Quiz/Practice/Feedback/Resource/Node 详情） |
| `TimelineSummaryCard` | 时间线统计概览卡片 |

## Hooks (`hooks/`)

| Hook | 说明 |
|------|------|
| `useChat` | 对话管理（发送消息、历史、状态） |
| `useStreamChat` | 流式对话管理 |
| `useProfile` | 学习画像获取 |
| `useLearningAnalytics` | 学习分析数据获取（含自动刷新） |
| `useLearningEvents` | 学习事件/时间线获取 |
| `useLearningPath` | 学习路径获取 |
| `useResources` | 资源列表管理（筛选、收藏、更新） |
| `useStudyTracker` | 学习追踪 |
| `useSessionContext` | 会话上下文 |
