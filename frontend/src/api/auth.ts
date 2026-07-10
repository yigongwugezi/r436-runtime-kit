import client from './client';
import type {
  Learner,
  LoginRequest,
  RegisterRequest,
  TokenResponse,
  UpdateProfileRequest,
  LearningHistoryResponse,
} from '../types/auth';

// ── Auth ────────────────────────────────────────────────────────────

export async function login(body: LoginRequest): Promise<TokenResponse> {
  const { data } = await client.post('/api/auth/login', body);
  return data as TokenResponse;
}

export async function register(body: RegisterRequest): Promise<TokenResponse> {
  const { data } = await client.post('/api/auth/register', body);
  return data as TokenResponse;
}

export async function refreshToken(): Promise<TokenResponse> {
  const { data } = await client.post('/api/auth/refresh');
  return data as TokenResponse;
}

export async function logout(): Promise<void> {
  await client.post('/api/auth/logout');
}

export async function getMe(): Promise<{ learner: Learner }> {
  const { data } = await client.get('/api/auth/me');
  return data as { learner: Learner };
}

// ── Profile ─────────────────────────────────────────────────────────

export async function getProfile(): Promise<{ learner: Learner }> {
  const { data } = await client.get('/api/learner/me');
  return data as { learner: Learner };
}

export async function updateProfile(body: UpdateProfileRequest): Promise<{ learner: Learner }> {
  const { data } = await client.patch('/api/learner/me', body);
  return data as { learner: Learner };
}

// ── Learning History ────────────────────────────────────────────────

export async function getLearningHistory(params: {
  start_date?: string;
  end_date?: string;
  subject_id?: string;
  page?: number;
  page_size?: number;
}): Promise<LearningHistoryResponse> {
  const { data } = await client.get('/api/learner/me/history', { params });
  return data as LearningHistoryResponse;
}

export async function getLearningHeatmap(days: number = 90): Promise<{
  days: number;
  data: Array<{ date: string; count: number }>;
}> {
  const { data } = await client.get('/api/learner/me/history/heatmap', { params: { days } });
  return data as { days: number; data: Array<{ date: string; count: number }> };
}

// ── Metadata ────────────────────────────────────────────────────────

export async function getMetaOptions(): Promise<{ grades: string[]; exams: string[] }> {
  const { data } = await client.get('/api/learner/meta/options');
  return data as { grades: string[]; exams: string[] };
}

// ── Preferences (cross-browser sync) ─────────────────────────────────

export async function getPreferences(): Promise<Record<string, any>> {
  const { data } = await client.get('/api/learner/me/preferences');
  return (data as any)?.preferences ?? {};
}

export async function savePreferences(preferences: Record<string, any>): Promise<void> {
  await client.put('/api/learner/me/preferences', { preferences });
}
