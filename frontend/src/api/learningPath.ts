import client from './client';
import type { LearningPath } from '../types/learningPath';

/** 获取学习路径 */
export async function getLearningPath(params: { sessionId: string; subjectId?: string }): Promise<{ path: LearningPath }> {
  const { data } = await client.get('/api/learning-path', { params });
  return data;
}

/** 触发智能体生成学习路径 */
export async function generateLearningPath(params: {
  sessionId?: string;
  subjectId?: string;
  courseId?: string;
  userMessage?: string;
}): Promise<{ path: LearningPath }> {
  const { data } = await client.post('/api/learning-path/generate', params);
  return data;
}

/** 更新节点进度 */
export async function updateNodeProgress(
  nodeId: string,
  mastery: number,
  params: { sessionId: string; subjectId?: string; status?: string },
): Promise<void> {
  await client.patch(`/api/learning-path/nodes/${nodeId}`, { mastery, ...params });
}

/** 验证课程名称 */
export async function validateCourse(courseName: string): Promise<{ valid: boolean; normalizedCourseName: string; reason: string | null }> {
  const { data } = await client.get('/api/learning-path/validate-course', { params: { courseName } });
  return data;
}

/** 为路径规划对话开启画像提取 */
export async function enableProfileExtraction(sessionId: string): Promise<{ ok: boolean }> {
  const { data } = await client.post('/api/learning-path/enable-profile-extraction', { sessionId });
  return data;
}

/** 路径规划专用对话：发送消息，返回提取的信息+引导语+是否就绪 */
export async function planningChat(params: {
  sessionId: string;
  message: string;
  facts?: Record<string, string>;
}): Promise<{ ok: boolean; extracted?: Record<string, string>; reply?: string; ready?: boolean; error?: string }> {
  const { data } = await client.post('/api/learning-path/planning-chat', params);
  return data;
}

// ── Planning Drafts ──

export interface PlanningDraft {
  draftId: string;
  learnerId: string;
  sessionId: string;
  subjectId: string;
  topic: string;
  goal: string;
  currentLevel: string;
  dailyTime: string;
  targetDuration: string;
  resourcePreferences: string[];
  status: string;
  createdAt: string | null;
  updatedAt: string | null;
  confirmedAt: string | null;
}

export interface DraftCompleteness {
  filled: number;
  total: number;
  percent: number;
  fields: Record<string, boolean>;
}

/** 创建或更新规划草稿 */
export async function upsertPlanningDraft(params: {
  draftId: string;
  sessionId: string;
  subjectId?: string;
  topic?: string;
  goal?: string;
  currentLevel?: string;
  dailyTime?: string;
  targetDuration?: string;
  resourcePreferences?: string[];
  confirmed?: boolean;
}): Promise<{ ok: boolean; draft: PlanningDraft; completeness: DraftCompleteness }> {
  const { data } = await client.post('/api/learning-path/drafts', params);
  return data;
}

/** 获取规划草稿 */
export async function getPlanningDraft(draftId: string): Promise<{ ok: boolean; draft: PlanningDraft | null; completeness: DraftCompleteness | null }> {
  const { data } = await client.get(`/api/learning-path/drafts/${draftId}`);
  return data;
}

/** 列出当前session的规划草稿 */
export async function listPlanningDrafts(params: { sessionId?: string; subjectId?: string }): Promise<{ ok: boolean; draft: PlanningDraft | null; drafts?: PlanningDraft[] }> {
  const { data } = await client.get('/api/learning-path/drafts', { params });
  return data;
}

// ── Workflow Tasks ──

export interface WorkflowTask {
  task_id: string;
  workflow_type: string;
  status: string;
  current_stage: string;
  result?: any;
  result_available?: boolean;
  safe_error_message?: string;
  created_at?: string;
  completed_at?: string;
  metadata?: any;
}

/** 创建路径生成workflow任务 */
export async function createPathGenerationTask(params: {
  sessionId: string;
  subjectId?: string;
  planMode?: string;
  pathMode?: string;
  totalDays?: number;
  weekends?: boolean;
  dynamicAdjust?: boolean;
  reviewEnabled?: boolean;
  draft?: Record<string, any>;
}): Promise<{ ok: boolean; task: WorkflowTask }> {
  const { data } = await client.post('/api/workflows/learning_path_generation/start', params);
  return data;
}

/** 查询workflow任务状态 */
export async function getWorkflowTask(taskId: string): Promise<{ ok: boolean; task: WorkflowTask }> {
  const { data } = await client.get(`/api/workflows/${taskId}`);
  return data;
}

/** 取消workflow任务 */
export async function cancelWorkflowTask(taskId: string): Promise<{ ok: boolean }> {
  const { data } = await client.post(`/api/workflows/${taskId}/cancel`);
  return data;
}

// ── Path Revision API ──

export async function getPendingRevision(sessionId: string): Promise<{
  pending_revision: any;
  diff?: any;
}> {
  const { data } = await client.get(`/api/learning-path/${sessionId}/pending-revision`);
  return data?.data || data;
}

export async function acceptPendingRevision(sessionId: string): Promise<{ ok: boolean }> {
  const { data } = await client.post(`/api/learning-path/${sessionId}/pending-revision/accept`);
  return data?.data || data;
}

export async function rejectPendingRevision(sessionId: string): Promise<{ ok: boolean }> {
  const { data } = await client.post(`/api/learning-path/${sessionId}/pending-revision/reject`);
  return data?.data || data;
}

export async function listRevisions(sessionId: string): Promise<{ revisions: any[]; current_version: number }> {
  const { data } = await client.get(`/api/learning-path/${sessionId}/revisions`);
  return data?.data || data;
}

// ── Document Download API ──

// Get auth token from localStorage (mirrors client.ts logic)
function _getDownloadToken(): string {
  try {
    return localStorage.getItem('edu_token') || '';
  } catch {
    return '';
  }
}

/** 下载学习路径文档（DOCX 或 PDF 格式） */
export async function downloadLearningPathDocument(params: {
  sessionId: string;
  format: 'docx' | 'pdf';
  subjectId?: string;
}): Promise<void> {
  const { sessionId, format, subjectId } = params;
  const query = new URLSearchParams({ format });
  if (subjectId) query.set('subjectId', subjectId);

  const token = _getDownloadToken();

  const response = await fetch(`/api/learning-path/${sessionId}/download?${query}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    const errBody = await response.text().catch(() => '');
    throw new Error(errBody || `下载失败 (${response.status})`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename\*?=(?:UTF-8'')?([^;\s]+)/i);
  const filename = match
    ? decodeURIComponent(match[1])
    : `学习路径_${format === 'docx' ? '文档' : 'PDF'}.${format}`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
