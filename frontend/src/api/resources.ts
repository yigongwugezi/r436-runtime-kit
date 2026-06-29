import client from './client';
import type { Resource, ResourceFilter } from '../types/resource';

export interface ResourceListResponse {
  resources: Resource[];
  total: number;
  completedCount: number;
  incompleteCount: number;
  completionRate: number;
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

// ── Batch operations ────────────────────────────────────────────────

export interface BatchResult {
  ok: boolean;
  updated: number;
  error?: string;
  studyStatus?: string;
  bookmarked?: boolean;
}

export interface BatchExportResult {
  ok: boolean;
  export: string;
  count: number;
  error?: string;
}

/** 批量标记完成/学习中/未开始 */
export async function batchUpdateStudyStatus(
  sessionId: string,
  resourceIds: string[],
  studyStatus: string,
): Promise<BatchResult> {
  const { data } = await client.post('/resources/batch/study-status', {
    sessionId,
    resourceIds,
    studyStatus,
  });
  return data;
}

/** 批量收藏/取消收藏 */
export async function batchSetBookmark(
  sessionId: string,
  resourceIds: string[],
  bookmarked: boolean,
): Promise<BatchResult> {
  const { data } = await client.post('/resources/batch/bookmark', {
    sessionId,
    resourceIds,
    bookmarked,
  });
  return data;
}

/** 批量导出资源标题清单 */
export async function batchExportResources(
  sessionId: string,
  resourceIds?: string[],
): Promise<BatchExportResult> {
  const { data } = await client.post('/resources/batch/export', {
    sessionId,
    resourceIds: resourceIds || undefined,
  });
  return data;
}

/** 更新单个资源的学习状态 */
export async function updateStudyStatus(
  resourceId: string,
  studyStatus: string,
  sessionId: string,
): Promise<{ ok: boolean; studyStatus: string }> {
  const { data } = await client.patch(`/resources/${resourceId}/study-status`, {
    studyStatus,
  }, { params: { sessionId } });
  return data;
}

/** 自动推进学习路径节点 */
export async function autoAdvanceNode(params: {
  sessionId: string;
  relatedStageId: string;
  taskId?: string;
  event: string;
}): Promise<{ ok: boolean }> {
  const { data } = await client.patch('/learning-path/auto-advance', params);
  return data;
}

/** 从知识库直接导入资源 */
export interface ImportFromKbResult {
  imported: number;
  resources: { id: string; type: string; title: string; description: string; difficulty?: string }[];
}

export async function importResourcesFromKb(params: {
  sessionId: string;
  courseId?: string;
  subjectId?: string;
}): Promise<ImportFromKbResult> {
  const { data } = await client.post('/resources/import-from-kb', params);
  return data;
}
