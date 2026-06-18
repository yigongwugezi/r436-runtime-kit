// ================================================================
// Student Profile types — 10-dimension portrait
// ================================================================

export interface StudentProfile {
  id: string;
  nickname: string;
  avatar?: string;
  createdAt: number;
  updatedAt: number;
  dimensions: ProfileDimension[];
  /** 知识短板列表 */
  weaknesses: KnowledgeGap[];
  /** 学习偏好 */
  preferences: LearningPreferences;
  /** 学习历史摘要 */
  history: StudyHistory;
}

export interface ProfileDimension {
  key: DimensionKey;
  label: string;
  value: number;       // 0-100 掌握度
  confidence: number;  // 0-1 置信度
  description: string;
  updatedAt: number;
  /** 数据来源 */
  source?: 'user_input' | 'agent_generated' | 'system_inferred' | 'mock_fallback';
}

export type DimensionKey =
  | 'major_background'    // 专业背景
  | 'knowledge_base'      // 知识基础
  | 'learning_goal'       // 学习目标
  | 'cognitive_style'     // 认知风格
  | 'error_patterns'      // 易错点
  | 'coding_ability'      // 编程能力
  | 'learning_progress'   // 学习进度
  | 'interest_direction'  // 兴趣方向
  | 'learning_rhythm'     // 学习节奏
  | 'self_efficacy';      // 学习效能感

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
  mastery: number;       // 0-100
  priority: number;      // 1-10 优先修复
  suggestedResources: string[];
}

export interface LearningPreferences {
  preferredFormats: ResourceFormat[];
  paceMinutes: number;        // 单次理想学习时长(分钟)
  difficulty: DifficultyLevel;
  explainStyle: 'diagram' | 'code' | 'case' | 'theory';
}

export type ResourceFormat = 'text' | 'diagram' | 'video' | 'code' | 'quiz';

export type DifficultyLevel = 'beginner' | 'intermediate' | 'advanced';

export interface StudyHistory {
  totalStudyMinutes: number;
  completedTopics: string[];
  quizAccuracy: number | null;     // 0-100, null when no quiz events exist
  streak: number;            // 连续学习天数
  lastStudyDate: number;
}
