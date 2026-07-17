/** Knowledge Graph Types */

export type KGNodeStatus = 'not_started' | 'in_progress' | 'mastered' | 'needs_review';

export type KGEdgeRelation = 'prerequisite' | 'related' | 'contains';

export interface KGNode {
  id: string;
  label: string;
  type: 'concept' | 'procedure' | 'memory';
  category: string;
  chapter: string;
  mastery: number;
  status: KGNodeStatus;
  difficulty: string;
  importance: number;
  resourceCount: number;
  completedCount: number;
}

export interface KGEdge {
  source: string;
  target: string;
  relation: KGEdgeRelation;
}

export interface KGMeta {
  totalNodes: number;
  totalEdges: number;
  masteredCount: number;
  chapters: string[];
  source: string;
}

export interface KnowledgeGraphData {
  nodes: KGNode[];
  edges: KGEdge[];
  meta: KGMeta;
}

export interface KGNodeDetail extends KGNode {
  description: string;
  resources: Array<{
    id: string;
    title: string;
    type: string;
    studyStatus: string;
  }>;
  linkedSections: Array<{
    id: string;
    title: string;
    chapterTitle: string;
  }>;
  prerequisites: Array<{ id: string; label: string }>;
  dependents: Array<{ id: string; label: string }>;
}
