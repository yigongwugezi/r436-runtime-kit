import client from './client';
import type { Resource, ResourceFilter } from '../types/resource';

export interface ResourceListResponse {
  resources: Resource[];
  total: number;
  page: number;
}

export async function getResources(filter?: ResourceFilter & { sessionId: string; subjectId?: string }): Promise<ResourceListResponse> {
  const { data } = await client.get('/resources', { params: filter });
  return data;
}

export async function getResourceById(
  id: string,
  params: { sessionId: string; subjectId?: string },
): Promise<{ resource: Resource }> {
  const { data } = await client.get(`/resources/${id}`, { params });
  return data;
}

export async function toggleBookmark(
  id: string,
  params: { sessionId: string; subjectId?: string },
): Promise<{ bookmarked: boolean }> {
  const { data } = await client.post(`/resources/${id}/bookmark`, null, { params });
  return data;
}

export async function generateResource(params: {
  sessionId?: string;
  type: string;
  topic: string;
  difficulty?: string;
  subjectId?: string;
}): Promise<{ resource: Resource }> {
  const { data } = await client.post('/resources/generate', params);
  return data;
}

export async function getResourceKnowledgeGraph(
  resourceId: string,
  params: { sessionId: string; subjectId?: string },
): Promise<{ mermaidDef: string; source?: string; resourceId?: string }> {
  const { data } = await client.get(`/resources/${resourceId}/knowledge-graph`, {
    params,
  });
  return data;
}
