import client from './client';
import type { ChapterMindmap, GeneratedSectionResource, GeneratedSectionResourceType, SectionRecommendationResult } from '../types/sectionResources';

export async function recommendSectionResources(sectionId: string, payload: Record<string, unknown>): Promise<SectionRecommendationResult> {
  const { data } = await client.post(`/api/sections/${encodeURIComponent(sectionId)}/resources/recommendations`, payload);
  return data.recommendations;
}

export async function generateSectionResource(sectionId: string, payload: Record<string, unknown>): Promise<{ resource: GeneratedSectionResource; reused: boolean }> {
  const { data } = await client.post(`/api/sections/${encodeURIComponent(sectionId)}/resources/generate`, payload);
  return data;
}

export async function getGeneratedSectionResources(sectionId: string, sessionId: string): Promise<GeneratedSectionResource[]> {
  const { data } = await client.get(`/api/sections/${encodeURIComponent(sectionId)}/generated-resources`, { params: { sessionId } });
  return data.resources || [];
}

export async function generateChapterMindmap(chapterId: string, payload: Record<string, unknown>): Promise<{ mindmap: ChapterMindmap; reused: boolean }> {
  const { data } = await client.post(`/api/chapters/${encodeURIComponent(chapterId)}/mindmap/generate`, payload);
  return data;
}

export async function getChapterMindmap(chapterId: string, sessionId: string): Promise<ChapterMindmap | null> {
  const { data } = await client.get(`/api/chapters/${encodeURIComponent(chapterId)}/mindmap`, { params: { sessionId } });
  return data.mindmap || null;
}

export const generatedResourceLabels: Record<GeneratedSectionResourceType, string> = {
  summary_card: '生成总结卡片',
  concept_comparison: '生成概念对比',
  worked_example: '生成例题详解',
  mistake_checklist: '生成易错清单',
  review_notes: '生成复习笔记',
};
