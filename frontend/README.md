# EduAgent 前端

基于大模型的多智能体个性化学习资源生成与自适应学习系统 — 前端。

## 技术栈

- **React 19** + TypeScript
- **Vite 8** 构建工具
- **Tailwind CSS v4** 样式
- **Zustand** 状态管理
- **React Router 7** 路由
- **Lucide React** 图标库

## 快速开始

```bash
# 安装依赖
npm install

# 启动开发服务器（默认 http://localhost:5173）
npm run dev

# 生产构建
npm run build

# 预览生产构建
npm run preview
```

## 启动要求

- Node.js >= 18
- 后端服务运行在 `http://localhost:8001`（可在 `src/api/client.ts` 中配置）

## 项目结构

```
src/
├── api/            # 后端 API 调用
├── components/     # UI 组件
│   ├── analytics/  # 分析相关组件
│   ├── chat/       # 对话相关组件
│   ├── common/     # 通用组件 (Modal, Toast, 按钮等)
│   ├── layout/     # 布局组件 (Sidebar, Header)
│   ├── learning-path/  # 学习路径组件
│   ├── profile/    # 画像组件
│   ├── resources/  # 资源组件
│   └── timeline/   # 时间线组件
├── hooks/          # 自定义 Hooks
├── pages/          # 页面组件
├── router/         # 路由配置
├── store/          # Zustand 状态
├── types/          # TypeScript 类型定义
└── utils/          # 工具函数
```

## 可用脚本

| 命令 | 说明 |
|------|------|
| `npm run dev` | 启动开发服务器 (HMR) |
| `npm run build` | 生产构建到 `dist/` |
| `npm run preview` | 预览生产构建 |
| `npm run lint` | ESLint 代码检查 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VITE_API_BASE_URL` | `http://localhost:8001` | API 后端地址 |
