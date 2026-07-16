import client from './client';
import type { LearnerProfileV2, StudentProfile } from '../types/profile';

export interface BuildProfileParams {
  message: string;
  subjectId?: string;
  sessionId?: string;
}

export async function buildProfile(params: BuildProfileParams): Promise<{ profile: StudentProfile }> {
  const { data } = await client.post('/api/profile/build', params);
  return { ...data, profile: { ...data.profile, profileV2: data.profileV2 } };
}

export async function getProfile(params: { sessionId: string; subjectId?: string }): Promise<{ profile: StudentProfile }> {
  const { data } = await client.get('/api/profile', { params });
  return { ...data, profile: { ...data.profile, profileV2: data.profileV2 } };
}

export async function updateProfile(updates: Partial<StudentProfile>): Promise<{ profile: StudentProfile }> {
  const { data } = await client.patch('/api/profile', updates);
  return data;
}

export async function updateProfileContext(sessionId: string, context: Record<string, unknown>): Promise<{ profileV2: LearnerProfileV2 }> {
  const { data } = await client.patch('/api/profile/v2/context', { sessionId, context });
  return data;
}

export async function updateProfileSelfReport(sessionId: string, selfReport: Record<string, number>): Promise<{ profileV2: LearnerProfileV2 }> {
  const { data } = await client.patch('/api/profile/v2/self-report', { sessionId, selfReport });
  return data;
}

export async function updateProfileFact(sessionId: string, factKey: string, action: 'edit' | 'delete' | 'disable' | 'enable' | 'lock' | 'unlock', value?: unknown, scope?: string) {
  const { data } = await client.patch(`/api/profile/v2/facts/${encodeURIComponent(factKey)}`, { sessionId, action, value, scope });
  return data;
}

export async function assessInterest(sessionId: string, answers?: number[]): Promise<{ profileV2?: LearnerProfileV2; questions: string[] }> {
  const { data } = await client.post('/api/profile/v2/assess/interest', { sessionId, ...(answers ? { answers } : {}) });
  return data;
}

export async function syncProfileFromConversation(subjectId: string, sessionId: string, preview = true): Promise<{ preview: any; profileV2: LearnerProfileV2; applied?: boolean }> {
  const { data } = await client.post(`/api/profiles/${encodeURIComponent(subjectId)}/sync-from-conversation`, { sessionId, preview });
  return data;
}

// ── 画像驱动的资源推荐 ────────────────────────────────────────────────
export interface ProfileRecommendation {
  recommendation_type: string;
  title: string;
  reason: string;
  target_resource_id: string | null;
  target_stage_id: string | null;
  priority: 'high' | 'medium' | 'low';
  source: string;
  confidence: number;
  evidence: string;
  quality_status: string;
}

export async function getProfileRecommendations(sessionId: string): Promise<{ recommendations: ProfileRecommendation[] }> {
  const { data } = await client.get('/api/profile/recommendations', { params: { sessionId } });
  return data;
}
