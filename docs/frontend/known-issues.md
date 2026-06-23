# 前端已知问题与后续计划

## 已知问题

### 1. 组件冗余
- `Loading.tsx` 与 `PageState.tsx` 中的 `PageLoading` 功能完全重叠，需统一
- `EmptyState.tsx` 与 `PageState.tsx` 中的 `PageEmpty` 功能完全重叠，需统一
- 多个组件（`Skeleton.tsx`, `RetryButton.tsx`, `Breadcrumb.tsx`, `UserSetup.tsx`）已创建但未被引用，属于死代码
- `BottomNav.tsx` 已创建但未集成到 `AppLayout` 中
- `SettingsPage.tsx` 已创建但未在路由中注册（功能由 `SettingsModal` 提供）

### 2. 类型导入问题
- `AnalyticsSummary` 中的 `resourceViewCount` 和 `resourceCompleteCount` 为可选字段，前端做了 fallback 推导但类型定义仍需完善
- `DiagnosisResult` 类型在 `DiagnosisPanel.tsx` 中已定义但未被外部使用（来自 analytics 数据转换）

### 3. 移动端适配
- 底部导航栏 (`BottomNav`) 尚未集成，移动端依赖顶部的汉堡菜单抽屉
- 部分页面在窄屏下的表格水平滚动体验可继续优化

### 4. 性能
- Mermaid 渲染库体积较大（约 600KB），建议按需引入
- 资源列表未做虚拟滚动，大量资源时可能卡顿

### 5. 错误处理
- 部分 API 调用缺少统一的错误重试机制
- 网络断开时没有全局离线提示

## 后续计划

### 短期（下一迭代）
- [ ] 统一 `Loading` / `EmptyState` → `PageState` 组件，删除冗余文件
- [ ] 清理死代码组件
- [ ] 集成 `BottomNav` 到移动端布局
- [ ] 补全页面级错误边界

### 中期
- [ ] 添加虚拟滚动支持（`react-window` 或类似方案）
- [ ] 实现全局离线检测和重连提示
- [ ] 完善 TypeScript 类型覆盖率
- [ ] 添加 E2E 测试覆盖核心交互路径

### 长期
- [ ] Mermaid 懒加载/代码分割
- [ ] 服务端渲染 (SSR) 支持
- [ ] 国际化 (i18n) 支持
- [ ] 主题定制（暗色模式增强）
- [ ] PWA 离线支持
