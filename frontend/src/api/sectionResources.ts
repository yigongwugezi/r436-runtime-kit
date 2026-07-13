import client, { streamRequest } from './client';
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
  const reader = await streamRequest(`/api/sections/${encodeURIComponent(sectionId)}/resources/recommendations/stream`, payload, signal);
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split('\n\n');
      buffer = blocks.pop() || '';
      for (const block of blocks) {
        const data = block.split('\n').find((line) => line.startsWith('data: '))?.slice(6);
        if (!data) continue;
        const event = JSON.parse(data) as SearchProgressEvent | { event: 'result'; recommendations: SectionRecommendationResult };
        if (event.event === 'result') return event.recommendations;
        onProgress(event);
      }
    }
  } finally {
    reader.releaseLock();
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
