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
  | 'learning_rhythm'
  | 'self_efficacy';

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
  self_efficacy: '学习效能',
};

export interface KnowledgeGap {
  topic: string;
  mastery: number;
  priority: number;
  suggestedResources: string[];
}

export interface LearningPreferences {
  preferredFormats: ResourceFormat[];
  paceMinutes: number;
  difficulty: DifficultyLevel | 'unknown';
  explainStyle: 'diagram' | 'code' | 'case' | 'theory' | 'unknown';
}

export type ResourceFormat = 'text' | 'diagram' | 'video' | 'code' | 'quiz';

export type DifficultyLevel = 'beginner' | 'intermediate' | 'advanced';

export interface StudyHistory {
  totalStudyMinutes: number;
  completedTopics: string[];
  quizAccuracy: number | null;
  streak: number;
  lastStudyDate: number;
}
