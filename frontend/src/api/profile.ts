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

export async function assessInterest(sessionId: string, answers?: number[]): Promise<{ profileV2?: LearnerProfileV2; questions: string[] }> {
  const { data } = await client.post('/api/profile/v2/assess/interest', { sessionId, ...(answers ? { answers } : {}) });
  return data;
}
