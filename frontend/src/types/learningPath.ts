// ================================================================
// Learning Path types
// ================================================================

export type ContentStatus = 'not_started' | 'in_progress' | 'mastered' | 'needs_review' | 'blocked';
export const CONTENT_STATUS_ORDER: ContentStatus[] = ['not_started', 'in_progress', 'mastered', 'needs_review', 'blocked'];
export function legacyStatusToContent(s: PathNodeStatus): ContentStatus { switch (s) { case 'locked': return 'blocked'; case 'available': return 'not_started'; case 'in_progress': return 'in_progress'; case 'mastered': return 'mastered'; } }
export function nextContentStatus(c: ContentStatus): ContentStatus { const i = CONTENT_STATUS_ORDER.indexOf(c); return CONTENT_STATUS_ORDER[(i + 1) % CONTENT_STATUS_ORDER.length]; }
export function contentStatusToProgress(s: ContentStatus): number { switch (s) { case 'not_started': case 'blocked': return 0; case 'in_progress': return 40; case 'needs_review': return 70; case 'mastered': return 100; } }

export interface LearningPath {
  id: string;
  title: string;
  description: string;
  courseName: string;
  stages: LearningStage[];
  createdAt: number;
  overallProgress: number;
  estimatedDays: number;
  source?: 'agent_generated' | 'system_inferred' | 'none';
  stageResourceStats?: Record<string, { total: number; completed: number }>;
  /** 路径调整日志，由后端 adjust 模式产生 */
  adjustments: Adjustment[];
  /** 每次调整递增，前端用于检测路径结构变化 */
  pathVersion: number;
}

/** 一次路径调整的记录 */
export interface Adjustment {
  /** 调整描述，如 "加速 极限与连续：7天→3天" */
  description: string;
  /** 调整类型 */
  type?: 'accelerate' | 'remedial' | 'insert' | 'split' | 'sprint' | 'init';
  /** 调整时间戳 */
  timestamp?: number;
}

export type StageStatus = 'not_started' | 'in_progress' | 'completed';

export interface LearningStage {
  id: string;
  order: number;
  title: string;
  description: string;
  nodes: PathNode[];
  chapters: Chapter[];
  objective: string;
  estimatedDays: number;
  tasks?: string[];
  resourceTypes?: string[];
  orderingReason?: string;
  /** 路径结构模式: textbook | daily | project */
  path_mode?: string;
  /** 规划模式: textbook | focus | adjust */
  plan_mode?: string;
  /** 精进式专属：薄弱点名称 */
  focus?: string;
  /** 精进式专属：突破原因 */
  reason?: string;
}

export interface Chapter {
  id: string;
  title: string;
  order: number;
  status: ContentStatus;
  sections: Section[];
  mindmapId?: string;
}

export interface Section {
  id: string;
  title: string;
  goal: string;
  estimatedMinutes: number;
  status: ContentStatus;
  knowledgePoints: KnowledgePoint[];
  lectureIds: string[];
  /** 内容交互形式: lecture | memory_drill | step_through */
  contentType?: string;
  /** ── 日课式专属字段 ── */
  /** 每日任务类型: vocabulary | listening | reading | grammar | speaking | writing | review */
  task_type?: string;
  /** ── Textbook-linked fields ── */
  /** PDF start page for this section */
  textbookPageStart?: number;
  /** PDF end page for this section */
  textbookPageEnd?: number;
  /** Reference into TextbookModel.chapters_json section_id */
  textbookSectionId?: string;
}

export interface KnowledgePoint {
  id: string;
  name: string;
  type: 'concept' | 'procedure' | 'memory';
  description?: string;
  mastery: number;
  status: ContentStatus;
}

export interface PathNode {
  id: string;
  topic: string;
  description: string;
  prerequisites: string[];
  mastery: number;
  status: PathNodeStatus;
  resources: PathResource[];
  isKeyPoint?: boolean;
  reviewSchedule?: ReviewSchedule;
}

export type PathNodeStatus = 'locked' | 'available' | 'in_progress' | 'mastered';

export interface PathResource {
  resourceId: string;
  type: string;
  title: string;
  essential: boolean;
  completed: boolean;
}

export interface ReviewSchedule {
  nextReviewAt: number;
  intervalDays: number;
  reviewCount: number;
}

export interface KnowledgeGraph {
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
}

export interface KnowledgeNode {
  id: string;
  label: string;
  category: string;
  mastery: number;
  isKeyPoint: boolean;
}

export interface KnowledgeEdge {
  source: string;
  target: string;
  relation: 'prerequisite' | 'related' | 'contains';
}
