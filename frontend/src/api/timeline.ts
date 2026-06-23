import client from './client';
import type { TimelineResponse } from '../types/timeline';

/** 获取学习时间线 */
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
