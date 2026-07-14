export type GeneratedSectionResourceType =
  | 'summary_card' | 'concept_comparison' | 'worked_example' | 'mistake_checklist' | 'review_notes'
  | 'knowledge_map' | 'process_flow' | 'concept_diagram' | 'execution_trace' | 'code_trace';

export interface ExternalSectionResource {
  title: string;
  url: string;
  source: string;
  resource_type: 'video' | 'article' | 'course' | 'paper' | 'document';
  platform?: string | null;
  snippet: string;
  reason: string;
  relevance_score: number;
  language: string;
  trust_level: 'official' | 'educational' | 'general';
  match_level?: 'exact_topic' | 'chapter_level' | 'course_level' | 'expanded_research';
  feedback?: 'helpful' | 'not_relevant' | 'too_hard' | 'too_easy' | null;
}

export interface SectionRecommendationResult {
  query: string[];
  resources: ExternalSectionResource[];
  status: 'completed' | 'search_unavailable' | 'no_high_relevance' | 'expanded_no_results' | 'failed' | 'cancelled' | 'stale_results' | 'partial_results';
  warnings: string[];
}

export interface SearchProgressEvent {
  event: 'search_progress';
  stage: 'topic_analysis' | 'cache' | 'primary_search' | 'fallback_search' | 'quality_filter' | 'personalized_ranking' | 'completed' | 'cancelled' | 'failed' | 'stale_cache';
  status: 'pending' | 'running' | 'completed' | 'cancelled' | 'failed';
  fallback_used?: boolean;
  stale?: boolean;
  candidate_count?: number;
  result_count?: number;
  source_count?: number;
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
  mermaidDef?: string;
  format?: string;
  quality?: 'passed' | 'repaired' | 'fallback' | 'failed' | '';
  qualityScore?: number | null;
  personalization?: Record<string, unknown>;
  feedback?: { feedback: 'helpful' | 'not_relevant' | 'too_hard' | 'too_easy' | 'other'; rating?: number; comment?: string } | null;
  workflowTrace?: Array<{ agent: string; status: string; summary: string }>;
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
