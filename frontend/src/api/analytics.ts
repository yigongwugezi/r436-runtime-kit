import client from './client';
import type { AnalyticsSummary } from '../types/analytics';

/**
 * 获取学习分析数据
 */
export async function getAnalytics(params: {
  sessionId?: string;
  subjectId?: string;
}, signal?: AbortSignal): Promise<AnalyticsSummary> {
  const { data } = await client.get('/api/learning-analytics', { params, signal });
  return data;
}
