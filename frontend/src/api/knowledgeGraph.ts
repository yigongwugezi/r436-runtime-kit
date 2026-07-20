import client from './client';
import type { KnowledgeGraphData, KGNodeDetail } from '../types/knowledgeGraph';

export async function getKnowledgeGraph(params: {
  sessionId: string;
  subjectId?: string;
  chapter?: string;
}, signal?: AbortSignal): Promise<KnowledgeGraphData> {
  const { data } = await client.get('/api/knowledge-graph', { params, signal });
  return data;
}

export async function getNodeDetail(
  nodeId: string,
  params: { sessionId: string; subjectId?: string },
): Promise<KGNodeDetail> {
  const { data } = await client.get(`/api/knowledge-graph/nodes/${nodeId}`, { params });
  return data;
}
