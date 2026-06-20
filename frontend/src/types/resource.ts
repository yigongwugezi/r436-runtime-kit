// ================================================================
// Resource types
// ================================================================

import type { ResourceType } from './chat';

export type ResourceFormat = 'text' | 'diagram' | 'video' | 'code' | 'quiz';

export interface Resource {
  id: string;
  type: ResourceType;
  title: string;
  description: string;
  content: string;          // Markdown body
  knowledgePoints: string[];
  tags: string[];
  difficulty: 'easy' | 'medium' | 'hard';
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
  source?: 'user_input' | 'agent_generated' | 'system_inferred';
  /** 是否已收藏 */
  bookmarked?: boolean;
  /** 学习状态 */
  studyStatus?: 'new' | 'in_progress' | 'completed';

  // ========== ResourceAgent P0 新增字段 ==========
  /** 关联的学习阶段 ID */
  relatedStageId?: string;
  /** 关联的章节名称 */
  relatedChapter?: string;
  /** 关联的知识点列表 */
  relatedKnowledgePoints?: string[];
  /** 质检状态: passed / needs_review / fallback_passed */
  qualityStatus?: string;
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
  difficulty: 'easy' | 'medium' | 'hard';
}

export interface PptSlide {
  title: string;
  bullets: string[];
  notes?: string;
}

export interface ResourceFilter {
  type?: ResourceType;
  difficulty?: string;
  source?: string;
  knowledgePoint?: string;
  format?: ResourceFormat;
  search?: string;
  sortBy?: 'newest' | 'relevance' | 'difficulty';
  relatedStageId?: string;
  taskId?: string;
  resourceIds?: string;
}
