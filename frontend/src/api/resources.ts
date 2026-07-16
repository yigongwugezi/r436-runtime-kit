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
  const { data } = await client.get('/api/resources', { params: filter });
  return data;
}

export async function getResourceById(
  id: string,
  params: { sessionId: string; subjectId?: string },
): Promise<{ resource: Resource }> {
  const { data } = await client.get(`/api/resources/${id}`, { params });
  return data;
}

export async function toggleBookmark(
  id: string,
  params: { sessionId: string; subjectId?: string },
): Promise<{ bookmarked: boolean }> {
  const { data } = await client.post(`/api/resources/${id}/bookmark`, null, { params });
  return data;
}

export async function generateResource(params: {
  sessionId?: string;
  type: string;
  topic: string;
  difficulty?: string;
  subjectId?: string;
}): Promise<{ resource: Resource }> {
  const { data } = await client.post('/api/resources/generate', params);
  return data;
}

export type GeneralResourceType = 'lecture' | 'mindmap' | 'quiz' | 'ppt' | 'video' | 'animation' | 'manim' | 'reading' | 'practice';

export interface GeneralResourceGenerationRequest {
  sessionId: string;
  learnerId?: string;
  subjectId?: string;
  pathId?: string;
  stageId?: string;
  chapterId?: string;
  sectionId?: string;
  topic: string;
  resourceTypes: GeneralResourceType[];
  difficulty: 'easy' | 'medium' | 'hard';
  operation: string;
  mode: string;
  profileSnapshotVersion?: string;
  generationOptions?: Record<string, unknown>;
}

export interface GeneralResourceWorkflowStart {
  task_id: string;
  workflow_type: string;
  resource_type: GeneralResourceType;
  status: string;
  reused_existing?: boolean;
}

export async function startGeneralResourceGeneration(params: GeneralResourceGenerationRequest): Promise<{ tasks: GeneralResourceWorkflowStart[] }> {
  const { data } = await client.post('/api/workflows/general_resource_generation/batch/start', params);
  return data;
}

export async function deleteResource(resourceId: string, sessionId: string): Promise<void> {
  await client.delete(`/api/resources/${resourceId}`, { params: { sessionId } });
}

export interface OnlineSearchResultToSave {
  title: string;
  url: string;
  resource_type: 'article' | 'video' | 'course' | 'document' | 'paper';
  source?: string;
  snippet?: string;
  reason?: string;
  quality_status?: string;
}

export async function saveOnlineSearchResult(params: {
  sessionId: string;
  subjectId?: string;
  query: string;
  taskId?: string;
  resource: OnlineSearchResultToSave;
}): Promise<{ resourceId: string; reused: boolean }> {
  const { data } = await client.post('/api/resources/search-results/save', params);
  return data.data || data;
}

export async function getResourceKnowledgeGraph(
  resourceId: string,
  params: { sessionId: string; subjectId?: string },
): Promise<{ mermaidDef: string; source?: string; resourceId?: string }> {
  const { data } = await client.get(`/api/resources/${resourceId}/knowledge-graph`, {
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
  const { data } = await client.post('/api/resources/batch/study-status', {
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
  const { data } = await client.post('/api/resources/batch/bookmark', {
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
  const { data } = await client.post('/api/resources/batch/export', {
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
  const { data } = await client.patch(`/api/resources/${resourceId}/study-status`, {
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
  const { data } = await client.patch('/api/learning-path/auto-advance', params);
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
  const { data } = await client.post('/api/resources/import-from-kb', params);
  return data;
}

// ── Recommend-v2: 联网搜索 + AI 生成 + DB 推荐，三路并行 ─────────────

export interface WebSearchResultItem {
  title: string;
  url: string;
  snippet: string;
  source: string;
  resource_type: string;
}

export interface GeneratedResourceItem {
  id: string;
  type: string;
  title: string;
  description: string;
  content: string;
  difficulty: string;
  format: string;
  source: string;
}

export interface RecommendGroup {
  label: string;
  type: string;
  items: WebSearchResultItem[] | GeneratedResourceItem[];
}

export interface RecommendCategory {
  id: string;
  label: string;
  description: string;
  /** flat items for DB recommendations */
  items?: any[];
  /** grouped items for web/AI results */
  groups?: RecommendGroup[];
}

export interface RecommendV2Response {
  categories: RecommendCategory[];
}

/** 三路并行推荐：DB 推荐 + 联网搜索 + AI 生成 */
export async function recommendV2(params: {
  sessionId: string;
  subjectId?: string;
}): Promise<RecommendV2Response> {
  const { data } = await client.post('/api/resources/recommend-v2', params);
  return data;
}
