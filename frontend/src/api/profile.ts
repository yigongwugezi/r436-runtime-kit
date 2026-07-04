import client from './client';
import type { StudentProfile } from '../types/profile';

export interface BuildProfileParams {
  message: string;
  subjectId?: string;
  sessionId?: string;
}

export async function buildProfile(params: BuildProfileParams): Promise<{ profile: StudentProfile }> {
  const { data } = await client.post('/api/profile/build', params);
  return data;
}

export async function getProfile(params: { sessionId: string; subjectId?: string }): Promise<{ profile: StudentProfile }> {
  const { data } = await client.get('/api/profile', { params });
  return data;
}

export async function updateProfile(updates: Partial<StudentProfile>): Promise<{ profile: StudentProfile }> {
  const { data } = await client.patch('/api/profile', updates);
  return data;
}

// Socratic Profiler 直连兜底
const PROFILER_URL = 'http://localhost:8001';

export async function getSocraticProfile(studentId: string): Promise<{ profile: any }> {
  const res = await fetch(`${PROFILER_URL}/api/profile/${studentId}`);
  if (!res.ok) throw new Error('Profiler unavailable');
  const data = await res.json();
  // 转换为前端格式
  const socraticToFrontend = (dims: Record<string, any>) =>
    Object.values(dims).map((d: any) => ({
      key: d.key,
      label: d.label,
      value: d.score ?? 50,
      confidence: d.confidence ?? 0.5,
      description: d.value ?? '',
      updatedAt: new Date().toISOString(),
    }));
  return { profile: { dimensions: socraticToFrontend(data.dimensions || {}) } as any };
}
