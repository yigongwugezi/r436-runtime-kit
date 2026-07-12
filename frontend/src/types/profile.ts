// ================================================================
// Student Profile types
// ================================================================

export interface StudentProfile {
  id: string;
  nickname: string;
  avatar?: string;
  createdAt: number;
  updatedAt: number;
  dimensions: ProfileDimension[];
  weaknesses: KnowledgeGap[];
  preferences: LearningPreferences;
  history: StudyHistory;
  profileV2?: LearnerProfileV2;
}

export interface LearnerProfileV2 {
  profile_version: 2;
  subject_context: Record<string, any>;
  general_states: ProfileStateV2[];
  subject_dimensions: SubjectDimensionV2[];
  knowledge_mastery: KnowledgeMasteryV2[];
  evidence_summary: Record<string, number>;
  profile_completeness: number;
  updated_at: string;
}

export interface ProfileStateV2 {
  key: string;
  label: string;
  status: 'assessed' | 'tentative' | 'unassessed';
  self_report: number | null;
  system_estimate: number | null;
  level: string;
  confidence: 'low' | 'medium' | 'high';
  evidence: Array<{ source: string; detail: string }>;
  updated_at: string;
}

export interface SubjectDimensionV2 {
  key: string;
  label: string;
  status: 'unassessed' | 'tentative' | 'basic' | 'developing' | 'proficient' | 'advanced';
  score: number | null;
  confidence: 'low' | 'medium' | 'high';
  evidence: Array<{ source: string; detail: string }>;
  recommended_action: string;
  updated_at: string;
}

export interface KnowledgeMasteryV2 {
  knowledge_id: string;
  label: string;
  status: 'unassessed' | 'learning' | 'partial' | 'mastered' | 'weak';
  confidence: 'low' | 'medium' | 'high';
  evidence: Array<{ source: string; detail: string }>;
  updated_at: string;
}

/** 维度数据来源类型 */
export type DimensionSource =
  | 'user_input'
  | 'inferred'
  | 'llm_generated'
  | 'rule_based_fallback'
  | 'diagnosis'
  | 'feedback';

export interface ProfileDimension {
  key: DimensionKey;
  label: string;
  value: string;
  score: number;
  confidence: number;
  description: string;
  explanation: string;
  evidence: string;
  updatedAt: number;
  source: DimensionSource;
}

export type DimensionKey =
  | 'major_background'
  | 'knowledge_base'
  | 'learning_goal'
  | 'cognitive_style'
  | 'error_patterns'
  | 'coding_ability'
  | 'learning_progress'
  | 'interest_direction'
  | 'learning_rhythm';

export const DIMENSION_LABELS: Record<DimensionKey, string> = {
  major_background: '专业背景',
  knowledge_base: '知识基础',
  learning_goal: '学习目标',
  cognitive_style: '认知风格',
  error_patterns: '易错模式',
  coding_ability: '编程能力',
  learning_progress: '学习进度',
  interest_direction: '兴趣方向',
  learning_rhythm: '学习节奏',
};

export interface KnowledgeGap {
  topic: string;
  mastery: number;
  priority: number;
  suggestedResources: string[];
  /** 来源: quiz, practice, feedback, diagnosis */
  source?: string[];
  /** 风险值 0-1 */
  risk?: number;
  /** 推荐原因 */
  reason?: string;
}

import type { ResourceFormat } from './resource';

export interface LearningPreferences {
  preferredFormats: ResourceFormat[];
  paceMinutes: number;
  difficulty: 'beginner' | 'intermediate' | 'advanced' | 'unknown';
  explainStyle: 'diagram' | 'code' | 'case' | 'theory' | 'unknown';
}

export type DifficultyLevel = 'beginner' | 'intermediate' | 'advanced';

export interface StudyHistory {
  totalStudyMinutes: number;
  completedTopics: string[];
  quizAccuracy: number | null;
  streak: number;
  lastStudyDate: number;
}
