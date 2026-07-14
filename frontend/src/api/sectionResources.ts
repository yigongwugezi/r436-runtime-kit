import client from './client';
import { cancelWorkflow, consumeWorkflowEvents, readWorkflow, startWorkflow } from './workflows';
import type { ChapterMindmap, GeneratedSectionResource, GeneratedSectionResourceType, SearchProgressEvent, SectionRecommendationResult } from '../types/sectionResources';

export async function recommendSectionResources(sectionId: string, payload: Record<string, unknown>): Promise<SectionRecommendationResult> {
  const { data } = await client.post(`/api/sections/${encodeURIComponent(sectionId)}/resources/recommendations`, payload);
  return data.recommendations;
}

export async function streamSectionResourceRecommendations(
  sectionId: string,
  payload: Record<string, unknown>,
  onProgress: (event: SearchProgressEvent) => void,
  signal?: AbortSignal,
): Promise<SectionRecommendationResult> {
  const started = await startWorkflow('resource_search', { ...payload, sectionId });
  try {
    await consumeWorkflowEvents(started.task_id, (event) => {
      if (!event.stage_id || event.event.startsWith('workflow_')) return;
      const safe = event.safe_metadata || {};
      onProgress({
        event: 'search_progress', stage: event.stage_id as SearchProgressEvent['stage'],
        status: event.status as SearchProgressEvent['status'], fallback_used: event.used_fallback,
        source_count: Number(safe.source_count || 0), result_count: Number(safe.result_count || 0),
      });
    }, signal);
    const task = await readWorkflow(started.task_id, String(payload.sessionId || ''));
    if (task.status === 'completed') return task.result?.data?.recommendations;
  } catch (error) {
    if (signal?.aborted) await cancelWorkflow(started.task_id, String(payload.sessionId || '')).catch(() => undefined);
    throw error;
  }
  throw new Error('Search stream ended without a result');
}

export async function submitSectionResourceFeedback(sectionId: string, payload: Record<string, unknown>): Promise<{ feedback: Record<string, string> }> {
  const { data } = await client.post(`/api/sections/${encodeURIComponent(sectionId)}/resources/feedback`, payload);
  return data;
}

export async function generateSectionResource(sectionId: string, payload: Record<string, unknown>): Promise<{ resource: GeneratedSectionResource; reused: boolean }> {
  const { data } = await client.post(`/api/sections/${encodeURIComponent(sectionId)}/resources/generate`, payload);
  return data;
}

export async function getGeneratedSectionResources(sectionId: string, sessionId: string, subjectId?: string): Promise<GeneratedSectionResource[]> {
  const { data } = await client.get(`/api/sections/${encodeURIComponent(sectionId)}/generated-resources`, { params: { sessionId, subjectId } });
  return data.resources || [];
}

export async function submitGeneratedSectionResourceFeedback(sectionId: string, resourceType: GeneratedSectionResourceType, payload: Record<string, unknown>): Promise<{ feedback: Record<string, string> }> {
  const { data } = await client.post(`/api/sections/${encodeURIComponent(sectionId)}/generated-resources/${encodeURIComponent(resourceType)}/feedback`, payload);
  return data;
}

export async function generateChapterMindmap(chapterId: string, payload: Record<string, unknown>): Promise<{ mindmap: ChapterMindmap; reused: boolean }> {
  const { data } = await client.post(`/api/chapters/${encodeURIComponent(chapterId)}/mindmap/generate`, payload);
  return data;
}

export async function getChapterMindmap(chapterId: string, sessionId: string): Promise<ChapterMindmap | null> {
  const { data } = await client.get(`/api/chapters/${encodeURIComponent(chapterId)}/mindmap`, { params: { sessionId } });
  return data.mindmap || null;
}

export async function generateSectionMindmap(sectionId: string, payload: Record<string, unknown>): Promise<{ mindmap: ChapterMindmap; reused: boolean }> {
  const { data } = await client.post(`/api/sections/${encodeURIComponent(sectionId)}/mindmap/generate`, payload);
  return data;
}

export async function getSectionMindmap(sectionId: string, sessionId: string): Promise<ChapterMindmap | null> {
  const { data } = await client.get(`/api/sections/${encodeURIComponent(sectionId)}/mindmap`, { params: { sessionId } });
  return data.mindmap || null;
}

export async function tutorSection(sectionId: string, payload: Record<string, unknown>): Promise<{ reply: string }> {
  const { data } = await client.post(`/api/sections/${encodeURIComponent(sectionId)}/tutor`, payload);
  return data;
}

export const generatedResourceLabels: Record<GeneratedSectionResourceType, string> = {
  summary_card: '生成总结卡片',
  concept_comparison: '生成概念对比',
  worked_example: '生成例题详解',
  mistake_checklist: '生成易错清单',
  review_notes: '生成复习笔记',
  knowledge_map: '生成知识结构图',
  process_flow: '生成学习流程图',
  concept_diagram: '生成概念对比图',
  execution_trace: '生成执行过程图',
  code_trace: '生成代码运行轨迹',
};
