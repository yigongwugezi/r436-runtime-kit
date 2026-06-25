// ================================================================
// Resource types
// ================================================================

/** 资源类型 — 7 种资源 */
export type ResourceType =
  | 'lecture'     // 课程讲义
  | 'mindmap'     // 思维导图
  | 'quiz'        // 练习题
  | 'reading'     // 拓展阅读
  | 'case_study'  // 实操案例
  | 'video'       // 教学视频/动画
  | 'ppt';        // PPT大纲

/** 数据来源类型 */
export type DataSource = 'user_input' | 'agent_generated' | 'system_inferred' | 'fallback';

/** 内容格式 */
export type ResourceFormat = 'text' | 'diagram' | 'video' | 'code' | 'quiz';

/** 难度 */
export type DifficultyLevel = 'easy' | 'medium' | 'hard';

/** 学习状态 */
export type StudyStatus = 'new' | 'in_progress' | 'completed';

/** 质检状态 */
export type QualityStatus = 'passed' | 'needs_review' | 'fallback_passed';

/** 审核状态 */
export type ReviewStatus = 'passed' | 'warning' | 'blocked';

/** 审核问题项 */
export interface ReviewIssue {
  /** 问题描述 */
  issue: string;
  /** 严重程度 */
  severity: 'error' | 'warning' | 'info';
  /** 建议 */
  suggestion?: string;
  /** 涉及内容区域 */
  location?: string;
}

export interface Resource {
  id: string;
  type: ResourceType;
  title: string;
  description: string;
  content: string;
  knowledgePoints: string[];
  tags: string[];
  difficulty: DifficultyLevel;
  estimatedMinutes: number;
  format: ResourceFormat;
  /** Mermaid 图谱定义 (mindmap 类型) */
  mermaidDef?: string;
  /** 代码内容 (case_study 类型) */
  codeBlocks?: CodeBlock[];
  /** 题目 (quiz 类型) */
  questions?: QuizQuestion[];
  /** PPT 大纲 */
  pptOutline?: PptSlide[];
  createdAt: number;
  /** 数据来源 */
  source?: DataSource;
  /** 是否已收藏 */
  bookmarked?: boolean;
  /** 学习状态 */
  studyStatus?: StudyStatus;
  /** 完成时间 (epoch ms) */
  completedAt?: number | null;
  /** 关联的学习阶段 ID */
  relatedStageId?: string;
  /** 关联的子阶段/任务 ID */
  taskId?: string;
  /** 关联的章节名称 */
  relatedChapter?: string;
  /** 关联的知识点列表 */
  relatedKnowledgePoints?: string[];
  /** 质检状态 */
  qualityStatus?: QualityStatus;
  /** 审核状态 */
  reviewStatus?: ReviewStatus;
  /** 审核问题列表 */
  reviewIssues?: ReviewIssue[];
  /** 审核建议 */
  reviewSuggestions?: string[];
  /** ── 可信解释字段 ── */

  /** 来源类型：llm_generated / rule_based / knowledge_base / user_input */
  sourceType?: string;
  /** 生成方式：direct_generation / knowledge_retrieval / hybrid / rule_fallback */
  generationMode?: string;
  /** 推荐理由 */
  reason?: string;
  /** 证据/依据列表 */
  evidence?: string[];
  /** 兜底原因（仅 fallback 资源有） */
  fallbackReason?: string;
}

export interface CodeBlock {
  language: string;
  code: string;
  explanation?: string;
}

export interface QuizQuestion {
  id: string;
  type: 'choice' | 'truefalse' | 'short_answer' | 'code';
  stem: string;
  options?: string[];
  answer: string;
  explanation: string;
  knowledgePoint: string;
  difficulty: DifficultyLevel;
}

export interface PptSlide {
  title: string;
  bullets: string[];
  notes?: string;
}

export type SortBy =
  | 'default'    // 默认推荐：已完成靠后 → 有阶段优先 → 最新
  | 'newest'     // 最新生成
  | 'shortest'   // 预计时间短优先
  | 'easiest'    // 难度从低到高
  | 'hardest'    // 难度从高到低
  | 'status'     // 已完成 / 未完成
  | 'stage';     // 当前阶段优先

export interface ResourceFilter {
  type?: ResourceType;
  difficulty?: DifficultyLevel | string;
  source?: DataSource | string;
  knowledgePoint?: string;
  format?: ResourceFormat;
  search?: string;
  sortBy?: SortBy;
  relatedStageId?: string;
  taskId?: string;
  resourceIds?: string;
  /** 章节筛选 */
  chapter?: string;
  /** 质检状态 */
  qualityStatus?: QualityStatus | string;
  /** 学习状态 */
  studyStatus?: StudyStatus | string;
  /** 收藏筛选: "true" | "false" */
  bookmarked?: string;
}
