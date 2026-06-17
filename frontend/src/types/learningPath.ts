// ================================================================
// Learning Path types
// ================================================================

export interface LearningPath {
  id: string;
  title: string;
  description: string;
  courseName: string;
  stages: LearningStage[];
  createdAt: number;
  /** 总体进度 */
  overallProgress: number; // 0-100
  /** 预计完成天数 */
  estimatedDays: number;
  source?: 'db' | 'agent' | 'agent_generated' | 'system_inferred' | 'none';
}

export interface LearningStage {
  id: string;
  order: number;
  title: string;
  description: string;
  /** 知识点列表（按学习顺序） */
  nodes: PathNode[];
  /** 阶段目标 */
  objective: string;
  /** 预计天数 */
  estimatedDays: number;
}

export interface PathNode {
  id: string;
  topic: string;
  description: string;
  /** 前置依赖节点 ID */
  prerequisites: string[];
  /** 掌握度 0-100 */
  mastery: number;
  /** 状态 */
  status: PathNodeStatus;
  /** 推荐资源 */
  resources: PathResource[];
  /** 是否为重点/难点 */
  isKeyPoint?: boolean;
  /** 艾宾浩斯复习节点 */
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
  reviewCount: number; // 第几次复习 (1-6)
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
