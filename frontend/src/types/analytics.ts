// ================================================================
// Learning Analytics types
// ================================================================

/** 薄弱知识点数据结构 — 来自后端 /learning-analytics + diagnosis_agent */
export interface WeakTopic {
  topic: string;
  wrongCount: number;
  totalCount: number;
  risk: number;
  /** 来源: quiz, practice, feedback, diagnosis */
  source: string[];
  /** 优先级: high | medium | low */
  priority?: string;
  /** 掌握度 (0-100) */
  mastery?: number;
  /** 推荐原因 */
  reason?: string;
  sampleCount?: number;
  status?: 'available' | 'insufficient_data' | 'unavailable';
}

/** 热门资源 */
export interface TopResource {
  resourceId: string;
  count: number;
  title?: string;
}

/** 完成趋势数据点 */
export interface CompletionTrendPoint {
  date: string;
  count: number;
}

/** Quiz 趋势数据点 */
export interface QuizTrendPoint {
  date: string;
  accuracy: number;
  topic: string;
  timestamp: string;
  attemptId?: string;
  answeredCount?: number;
  correctCount?: number;
  source?: 'attempt' | 'legacy_event';
}

export interface MetricDetail {
  value: number | null;
  status: 'available' | 'insufficient_data' | 'unavailable';
  sampleCount: number;
  source: string;
  updatedAt: string | null;
}

/** 最近事件 */
export interface RecentEvent {
  event: string;
  resourceId?: string;
  timestamp?: number | string;
  metadata?: Record<string, unknown>;
}

/** 结构化学习推荐项 — 来自后端 /learning-analytics */
export interface RecommendationItem {
  /** 推荐类型 */
  recommendation_type: 'incomplete_resource' | 'low_accuracy_topic'
    | 'incomplete_practice' | 'stage_incomplete' | 'frequent_weak_topic';
  /** 推荐标题 */
  title: string;
  /** 推荐原因 */
  reason: string;
  /** 目标资源 ID（可导航） */
  target_resource_id: string | null;
  /** 目标阶段 ID（可导航） */
  target_stage_id: string | null;
  /** 优先级 */
  priority: 'high' | 'medium' | 'low';
  /** 数据来源 */
  source: 'db' | 'event' | 'analytics';
  /** 置信度 0-1 */
  confidence: number;
  /** 支持证据 */
  evidence: string;
  /** 质量状态 */
  quality_status: string;
}

// ── M6 面板专用类型 ──

/** 能力热力图数据点 */
export interface HeatmapItem {
  knowledgePoint: string;
  mastery: number;
  level: string;
  evidenceCount: number;
  confidence?: number;    // 估计置信度 0-1
  trend?: 'improving' | 'declining' | 'stable';  // 趋势
  lastUpdated?: string;   // ISO datetime
}

/** 薄弱榜单项 */
export interface WeaknessRankingItem {
  name: string;
  priority: 'high' | 'medium' | 'low';
  reason: string;
  suggested_action?: string;
  resourceIds?: string[];
  mastery_score?: number;
  confidence?: number;     // 0-1
  trend?: 'improving' | 'declining' | 'stable';
  evidence_count?: number;
}

/** 进步曲线数据点 */
export interface ProgressCurvePoint {
  date: string;
  accuracy: number | null;
  questionCount: number;
}

/** 学习日历日 */
export interface StudyCalendarDay {
  date: string;
  active: boolean;
  questionCount: number;
  performanceLevel: number; // 0=无, 1=浏览, 2=需加强, 3=良好, 4=优秀
}

/** 目标追踪 */
export interface GoalTracking {
  estimatedDays: number;
  questionsCompleted: number;
  masteryPercentage: number;
  stagesCompleted: number;
  stagesTotal: number;
  examDate?: string | null;
  daysUntilExam?: number | null;
  progressPercent?: number;
}

/** 今日学习卡片 */
export interface TodayCard {
  questionsAnswered: number;
  averageScore: number | null;
  studyMinutes: number;
  weakPointsCount: number;
  rankChange?: number;  // -1=下降, 0=持平, 1=上升
  yesterdayQuestions?: number;
  yesterdayScore?: number | null;
}

/** 学习分析汇总 — 后端 /learning-analytics 返回 */
export interface AnalyticsSummary {
  eventCount: number;
  totalStudyMinutes: number;
  todayStudyMinutes: number;
  streak: number;
  activeResourceCount: number;
  /** 查看资源次数（后端直接返回，前端也可从 eventBreakdown 推导） */
  resourceViewCount?: number;
  /** 完成资源次数 */
  resourceCompleteCount?: number;
  /** 查看资源次数（同 resourceViewCount，语义化命名） */
  viewedResources: number;
  /** 完成资源次数（同 resourceCompleteCount，语义化命名） */
  completedResources: number;
  /** 实践次数 */
  practiceCount: number;
  assessmentCount?: number;
  questionAnsweredCount?: number;
  correctQuestionCount?: number;
  /** 最近学习时间（epoch ms，后端直接返回） */
  lastStudyTime?: number | null;
  eventBreakdown: Record<string, number>;
  topResources: TopResource[];
  quizAccuracy: number | null;
  latestQuizScore?: QuizTrendPoint | null;
  bestQuizScore?: QuizTrendPoint | null;
  scoreTrend?: QuizTrendPoint[];
  metricDetails?: Record<string, MetricDetail>;
  trackedStudyDuration?: number;
  durationDataQuality?: MetricDetail;
  timezoneUsed?: string;
  regularityScore?: number | null;
  regularityMetric?: MetricDetail;
  weakTopics: WeakTopic[];
  recommendations: RecommendationItem[];
  completionTrend: CompletionTrendPoint[];
  quizTrend: QuizTrendPoint[];
  resourceTypeBreakdown: Record<string, number>;
  recentEvents: RecentEvent[];
  summary: string;
  assessmentSummary?: string;
  topicMasteryTrend?: { topic: string; points: QuizTrendPoint[] }[];
  // ── M6 面板数据 ──
  heatmap?: HeatmapItem[];
  weaknessRanking?: WeaknessRankingItem[];
  progressCurve?: ProgressCurvePoint[];
  studyCalendar?: StudyCalendarDay[];
  goalTracking?: GoalTracking;
  todayCard?: TodayCard;
  pathProgress?: {
    pathId: string; subjectId: string; sessionId: string;
    totalStageCount: number; completedStageCount: number;
    currentStageId: string | null; currentStageTitle: string | null;
    totalRequiredTaskCount: number; completedRequiredTaskCount: number;
    taskProgressPercent: number; stageProgressPercent: number;
    pathCompleted: boolean; updatedAt: string | null;
    nextTask: null | { stageId: string; taskId: string; sectionId: string; taskType: string; title: string; accessible: boolean; routeContext: Record<string, string> };
  };
}

/** 时间线事件 — 后端 /learning-events/timeline 返回 */
export interface TimelineEvent {
  id: number;
  event: string;
  label: string;
  icon: string;
  color: string;
  resourceId: string;
  resourceTitle: string;
  resourceType: string;
  relatedStageId: string;
  relatedChapter: string;
  metadata: Record<string, unknown>;
  timestamp: number;
}

export interface TimelineResponse {
  events: TimelineEvent[];
  total: number;
}
