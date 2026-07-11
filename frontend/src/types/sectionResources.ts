export type GeneratedSectionResourceType = 'summary_card' | 'concept_comparison' | 'worked_example' | 'mistake_checklist' | 'review_notes';

export interface ExternalSectionResource {
  title: string;
  url: string;
  source: string;
  resource_type: 'video' | 'article' | 'course' | 'paper' | 'document';
  snippet: string;
  reason: string;
  relevance_score: number;
  language: string;
  trust_level: 'official' | 'educational' | 'general';
}

export interface SectionRecommendationResult {
  query: string[];
  resources: ExternalSectionResource[];
  status: 'completed' | 'search_unavailable' | 'failed';
  warnings: string[];
}

export interface GeneratedSectionResource {
  id: string;
  title: string;
  content: string;
  type: string;
  resourceType: GeneratedSectionResourceType;
  source: string;
  sectionId: string;
  chapterId: string;
  stageId: string;
  createdAt: number;
}

export interface ChapterMindmap {
  id: string;
  title: string;
  mermaidDef: string;
  chapterId: string;
  stageId: string;
  source: string;
  createdAt: number;
}
