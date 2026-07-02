import client from './client';

// ── Types ──────────────────────────────────────────────────────────

export interface AdminQuestion {
  id: string;
  subject: string;
  knowledge_point: string;
  type: string;
  difficulty: string;
  content: Record<string, unknown>;
  tags: string[];
  status: string;
  usage_count: number;
  avg_score: number;
  created_by: string | null;
  created_at: string | null;
  updated_at: string | null;
  // Review workflow
  review_status: string | null;
  review_comment: string | null;
  reviewed_at: string | null;
  // Difficulty calibration
  calibrated_difficulty: number | null;
}

export interface TagInfo {
  name: string;
  count: number;
  subjects: string[];
}

export interface AdminKP {
  id: string;
  subject: string;
  name: string;
  description: string | null;
  prerequisites: string[];
  difficulty: string;
  importance: number;
  chapter: string | null;
  grade_level: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface GraphData {
  nodes: Array<{ id: string; name: string; difficulty: string; importance: number; chapter: string | null }>;
  edges: Array<{ source: string; target: string }>;
}

export interface ConfigItem {
  key: string;
  value: string;
  description: string | null;
  category: string;
  updated_at: string | null;
}

// ── Questions ──────────────────────────────────────────────────────

export async function listQuestions(params: Record<string, string | number>) {
  const { data } = await client.get('/api/admin/questions', { params });
  return data as { questions: AdminQuestion[]; pagination: { total: number; page: number } };
}

export async function createQuestion(body: Record<string, unknown>) {
  const { data } = await client.post('/api/admin/questions', body);
  return data as { question: AdminQuestion };
}

export async function updateQuestion(id: string, body: Record<string, unknown>) {
  const { data } = await client.patch(`/api/admin/questions/${id}`, body);
  return data as { question: AdminQuestion };
}

export async function deleteQuestion(id: string) {
  await client.delete(`/api/admin/questions/${id}`);
}

export async function batchImport(questions: Record<string, unknown>[]) {
  const { data } = await client.post('/api/admin/questions/batch', questions);
  return data as { ok: boolean; imported: number };
}

export async function exportQuestions(subject?: string) {
  const { data } = await client.get('/api/admin/questions/export', { params: { subject } });
  return data as { questions: AdminQuestion[] };
}

// Review workflow
export async function reviewQuestion(id: string, body: { action: string; comment?: string }) {
  const { data } = await client.post(`/api/admin/questions/${id}/review`, body);
  return data as { question: AdminQuestion };
}

export async function batchReviewQuestions(body: { question_ids: string[]; action: string; comment?: string }) {
  const { data } = await client.post('/api/admin/questions/batch-review', body);
  return data as { ok: boolean; updated: number };
}

// Tag management
export async function listQuestionTags(subject?: string) {
  const { data } = await client.get('/api/admin/questions/tags', { params: { subject } });
  return data as { tags: TagInfo[] };
}

// Difficulty calibration
export async function calibrateDifficulty() {
  const { data } = await client.post('/api/admin/questions/calibrate-difficulty');
  return data as { calibrated: number; skipped: number };
}

// ── Model Monitoring ────────────────────────────────────────────────

export interface MonitorOverview {
  total_answered: number;
  active_students: number;
  overall_accuracy: number;
  questions_generated_today: number;
  daily_answer_count: Array<{ date: string; count: number }>;
  accuracy_trend: Array<{ date: string; accuracy: number }>;
  subject_breakdown: Array<{ subject: string; count: number; accuracy: number }>;
}

export interface DiagnosticAccuracy {
  total_diagnoses: number;
  avg_accuracy: number;
  accuracy_distribution: Array<{ range: string; count: number }>;
  trend: Array<{ date: string; avg_accuracy: number; count: number }>;
}

export interface QuestionQuality {
  total_questions: number;
  avg_score: number;
  score_distribution: Array<{ range: string; count: number }>;
  difficulty_calibration: Array<{ label: string; expected: number; actual: number }>;
  type_distribution: Array<{ type: string; count: number; avg_score: number }>;
  top_weak_questions: Array<{ question_id: string; stem: string; avg_score: number; attempt_count: number }>;
}

export async function getMonitorOverview() {
  const { data } = await client.get('/api/admin/monitor/overview');
  return data as MonitorOverview;
}

export async function getDiagnosticAccuracy() {
  const { data } = await client.get('/api/admin/monitor/diagnostic-accuracy');
  return data as DiagnosticAccuracy;
}

export async function getQuestionQuality() {
  const { data } = await client.get('/api/admin/monitor/question-quality');
  return data as QuestionQuality;
}

// ── Knowledge Graph ────────────────────────────────────────────────

export async function listKPs(params: Record<string, string>) {
  const { data } = await client.get('/api/admin/knowledge', { params });
  return data as { knowledge_points: AdminKP[] };
}

export async function getGraph(subject: string) {
  const { data } = await client.get('/api/admin/knowledge/graph', { params: { subject } });
  return data as GraphData;
}

export async function createKP(body: Record<string, unknown>) {
  const { data } = await client.post('/api/admin/knowledge', body);
  return data as { knowledge_point: AdminKP };
}

export async function updateKP(id: string, body: Record<string, unknown>) {
  const { data } = await client.patch(`/api/admin/knowledge/${id}`, body);
  return data as { knowledge_point: AdminKP };
}

export async function deleteKP(id: string) {
  await client.delete(`/api/admin/knowledge/${id}`);
}

export async function validateGraph(subject: string) {
  const { data } = await client.post('/api/admin/knowledge/validate', null, { params: { subject } });
  return data as { valid: boolean; total_nodes: number; has_cycle: boolean; message: string };
}

// ── Config ─────────────────────────────────────────────────────────

export async function listConfig() {
  const { data } = await client.get('/api/admin/config');
  return data as { configs: Record<string, ConfigItem[]> };
}

export async function updateConfig(key: string, body: { value: string; description?: string; category?: string }) {
  const { data } = await client.patch(`/api/admin/config/${key}`, body);
  return data as { config: ConfigItem };
}

export async function deleteConfig(key: string) {
  await client.delete(`/api/admin/config/${key}`);
}

// ── Stats ──────────────────────────────────────────────────────────

export async function getStatsOverview() {
  const { data } = await client.get('/api/admin/stats/overview');
  return data as { total_learners: number; active_today: number; total_sessions: number; total_messages: number };
}

export async function getStatsUsers(params: Record<string, string | number>) {
  const { data } = await client.get('/api/admin/stats/users', { params });
  return data as { users: Array<Record<string, unknown>>; pagination: { total: number } };
}

export async function getStatsDaily(days: number = 30) {
  const { data } = await client.get('/api/admin/stats/daily', { params: { days } });
  return data as { trend: Array<{ date: string; count: number }> };
}
