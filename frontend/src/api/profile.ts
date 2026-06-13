import client from './client';
import type { StudentProfile } from '../types/profile';

export interface BuildProfileParams {
  message: string;
  sessionId?: string;
}

export async function buildProfile(params: BuildProfileParams): Promise<{ profile: StudentProfile }> {
  const { data } = await client.post('/profile/build', params);
  return data;
}

export async function getProfile(): Promise<{ profile: StudentProfile }> {
  const { data } = await client.get('/profile');
  return data;
}

export async function updateProfile(updates: Partial<StudentProfile>): Promise<{ profile: StudentProfile }> {
  const { data } = await client.patch('/profile', updates);
  return data;
}
