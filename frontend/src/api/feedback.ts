import client from './client';

export interface SubmitFeedbackParams {
  sessionId?: string;
  resourceId: string;
  rating: number;          // 1-5
  comment?: string;
  difficultyMatch?: 'too_easy' | 'just_right' | 'too_hard';
  category?: string;
}

export async function submitFeedback(params: SubmitFeedbackParams): Promise<void> {
  await client.post('/feedback', params);
}

export interface StudyEventParams {
  sessionId?: string;
  event: string;
  resourceId?: string;
  duration?: number;
  metadata?: Record<string, unknown>;
}

export async function logStudyEvent(params: StudyEventParams): Promise<void> {
  await client.post('/feedback/event', params);
}

// ── Learning Timeline ─────────────────────────────────────────────

import type { TimelineResponse } from '../types/analytics';

export async function getLearningTimeline(
  sessionId: string,
  subjectId?: string,
  limit?: number,
  type?: string,
  range?: number,
): Promise<TimelineResponse> {
  const params: Record<string, string | number | undefined> = { sessionId, subjectId, limit };
  if (type) params.type = type;
  if (range && range > 0) params.range = range;
  const { data } = await client.get('/learning-events/timeline', { params });
  return data;
}
