# 练习中心设计文档

> **状态**: 已实现（Parts 1-5）。本文档描述当前实现状态。

## 路由

`/practice` — 单一页面组件 `PracticePage.tsx`，通过内部状态切换五个视图。

## 五大视图

| 视图 | 状态值 | 说明 |
|------|--------|------|
| 首页 | `home` | 快捷卡片 + 题集列表 + 题目集列表 + 统计 |
| 答题 | `quiz` | 逐题展示（小测/题集通用），提交 + 评分 |
| 错题本 | `weak` | 错误题目回顾，按类型筛选 |
| 历史 | `history` | 全部答题记录 |
| 题集详情 | `examSet` | 题集元数据 + 操作 + 作答历史 |

---

## 首页

四张快捷卡片 + 班级练习（教师推送）+ 题集列表 + 题目集列表 + 右侧统计。数据来自 `getQuestionSets()`, `listExamSets()`, `getPushedQuestions()`, `getAnswerHistory()`, `getWeakQuestions()`。

## 答题视图（小测 & 题集共用）

逐题展示：左侧题号列表（显示正确/错误状态），右侧题目卡片（选择/判断/填空/简答），底部导航（上一题、提交/保存进度、下一题）。

- **小测模式**：每题独立提交评分，`POST /api/questions/{id}/grade`
- **题集模式**：保存进度 `PATCH /api/attempts/{id}`，提交全部 `POST /api/exam-sets/{id}/submit`

评分后内联显示：绿色（≥60分）/红色（<60分），分数、错误类型标签、解析、建议。

## 题集详情视图

题集元数据（题数/时间/总分/难度）+ 状态 + 最近成绩。操作按钮：
- **开始作答** — `POST /api/exam-sets/{id}/attempts` → 进入答题
- **继续作答** — 恢复 `in_progress` 的 attempt
- **再次作答** — 创建新 attempt（不同 attemptId）
- 提交后显示成绩 + 薄弱知识点 + 作答历史列表

## 实现状态

单文件 `PracticePage.tsx`（~820 行），通过 `view` 状态切换五个视图。未拆分为多文件。所有视图共用 quiz 答题组件，通过 `activeExamSet` 判断是题集模式还是小测模式。
