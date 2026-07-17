import type { KGEdge, KGEdgeRelation, KGMeta, KGNode, KGNodeStatus, KnowledgeGraphData } from '../types/knowledgeGraph';

const nodeTypes = new Set<KGNode['type']>(['concept', 'procedure', 'memory']);
const statuses = new Set<KGNodeStatus>(['not_started', 'in_progress', 'mastered', 'needs_review']);
const relations = new Set<KGEdgeRelation>(['prerequisite', 'related', 'contains']);

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function text(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}

function number(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function node(value: unknown): KGNode | null {
  const source = record(value);
  const id = text(source?.id);
  if (!source || !id) return null;
  const type = text(source.type);
  const status = text(source.status);
  return {
    id,
    label: text(source.label) || id,
    type: nodeTypes.has(type as KGNode['type']) ? type as KGNode['type'] : 'concept',
    category: text(source.category),
    chapter: text(source.chapter),
    mastery: number(source.mastery),
    status: statuses.has(status as KGNodeStatus) ? status as KGNodeStatus : 'not_started',
    difficulty: text(source.difficulty) || 'medium',
    importance: number(source.importance, 1),
    resourceCount: number(source.resourceCount),
    completedCount: number(source.completedCount),
  };
}

function edge(value: unknown, nodeIds: Set<string>): KGEdge | null {
  const source = record(value);
  const from = text(source?.source);
  const to = text(source?.target);
  if (!source || !nodeIds.has(from) || !nodeIds.has(to)) return null;
  const relation = text(source.relation);
  return { source: from, target: to, relation: relations.has(relation as KGEdgeRelation) ? relation as KGEdgeRelation : 'related' };
}

export function adaptKnowledgeGraph(input: unknown): KnowledgeGraphData {
  const root = record(input);
  const source = record(root?.data) ?? root ?? {};
  const nodes = (Array.isArray(source.nodes) ? source.nodes : []).map(node).filter((value): value is KGNode => value !== null);
  const uniqueNodes = [...new Map(nodes.map((value) => [value.id, value])).values()];
  const nodeIds = new Set(uniqueNodes.map((value) => value.id));
  const edges = (Array.isArray(source.edges) ? source.edges : []).map((value) => edge(value, nodeIds)).filter((value): value is KGEdge => value !== null);
  const uniqueEdges = [...new Map(edges.map((value) => [`${value.source}|${value.target}|${value.relation}`, value])).values()];
  const meta = record(source.meta) ?? {};
  const chapters = Array.isArray(meta.chapters) ? meta.chapters.map(text).filter(Boolean) : [];
  const normalizedMeta: KGMeta = {
    totalNodes: uniqueNodes.length,
    totalEdges: uniqueEdges.length,
    masteredCount: uniqueNodes.filter((value) => value.status === 'mastered').length,
    chapters,
    source: text(meta.source) || 'unknown',
  };
  return { nodes: uniqueNodes, edges: uniqueEdges, meta: normalizedMeta };
}
