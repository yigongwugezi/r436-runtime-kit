import client from './client';
import type { ChatAttachment, ChatMessage, ChatSession, GenerationProgress } from '../types/chat';
import { getStableLearnerId } from '../store/authStore';

export interface SendMessageParams {
  sessionId?: string;
  subjectId?: string;
  learnerId?: string;
  message: string;
  attachments?: ChatAttachment[];
  image_url?: string;
  image_base64?: string;
  ignore_image_context?: boolean;
  image_provider?: string;
}

export interface ChatResponse {
  sessionId: string;
  reply: ChatMessage;
  multimodal_result?: ChatMessage['multimodalResult'];
  workflow_trace?: Record<string, unknown>;
  action?: string;
  agents_run?: string[];
  current_agent?: string;
  progress?: Record<string, unknown>;
  warnings?: string[];
  diagnosis_result?: Record<string, unknown>;
  planner_metadata?: Record<string, unknown>;
  done?: boolean;
  pipeline_executed?: boolean;
  learning_path_created?: boolean;
  resources_created?: boolean;
  questions_created?: boolean;
  current_subject?: { id: string; name: string; description?: string | null; created_at?: number; updated_at?: number } | null;
  error?: string;
}

export interface SessionListResponse {
  sessions: ChatSession[];
}

export async function createChatSession(params: { sessionId: string; subjectId?: string; learnerId?: string }): Promise<{ sessionId: string }> {
  const { data } = await client.post('/api/chat/sessions', { ...params, learnerId: params.learnerId || getStableLearnerId() });
  return data;
}

/** 发送消息（非流式） */
export async function sendMessage(params: SendMessageParams): Promise<ChatResponse> {
  const { data } = await client.post('/api/chat/send', { ...params, learnerId: params.learnerId || getStableLearnerId() });
  return data;
}

export async function uploadMultimodalImage(file: File, sessionId: string): Promise<ChatAttachment> {
  const form = new FormData();
  form.append('file', file);
  form.append('session_id', sessionId);
  const { data } = await client.post('/api/multimodal/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return { ...data, name: file.name };
}

export async function saveMultimodalResource(params: {
  sessionId: string;
  task_type?: string;
  result: any;
}): Promise<any> {
  const { data } = await client.post('/api/multimodal/save-resource', params);
  return data;
}

export async function prepareKnowledgeCandidates(params: {
  result: any;
  knowledge_candidates?: any[];
}): Promise<any> {
  const { data } = await client.post('/api/multimodal/knowledge-candidates', params);
  return data;
}

/** 获取会话列表，可按科目过滤 */
export async function getSessions(subjectId?: string): Promise<SessionListResponse> {
  const params: Record<string, string> = { learnerId: getStableLearnerId() };
  if (subjectId) params.subjectId = subjectId;
  const { data } = await client.get('/api/chat/sessions', { params });
  return data;
}

/** 获取会话消息 */
export async function getSessionMessages(sessionId: string): Promise<{ messages: ChatMessage[] }> {
  const { data } = await client.get(`/api/chat/sessions/${sessionId}`, { params: { learnerId: getStableLearnerId() } });
  return data;
}

/** 删除会话 */
export async function deleteSession(sessionId: string): Promise<void> {
  await client.delete(`/api/chat/sessions/${sessionId}`, { params: { learnerId: getStableLearnerId() } });
}

/** 获取快捷指令 */
export async function getQuickCommands(): Promise<{ commands: { id: string; label: string; icon: string; prompt: string }[] }> {
  const { data } = await client.get('/api/chat/quick-commands');
  return data;
}

/** 轮询生成进度 */
export async function getGenerationProgress(taskId: string): Promise<{ progress: GenerationProgress }> {
  const { data } = await client.get(`/api/chat/progress/${taskId}`);
  return data;
}

/** 获取可用智能体列表 */
export interface AgentInfo {
  id: string;
  name: string;
  icon: string;
  description: string;
  stage: string;
}

export async function getAgents(): Promise<{ agents: AgentInfo[] }> {
  const { data } = await client.get('/api/chat/agents');
  return data;
}

/** 恢复中断生成后的助手回复和实时进度 */
export async function recoverGeneration(sessionId: string): Promise<{
  sessionId: string;
  reply: ChatMessage | null;
  generating: boolean;
  currentProgress: import('../types/chat').GenerationProgress | null;
}> {
  const { data } = await client.get('/api/chat/recover', { params: { sessionId } });
  return data;
}

/** 查询试题列表 */
export async function listQuestions(sessionId: string): Promise<any> {
  const { data } = await client.get('/api/questions', { params: { sessionId, learnerId: getStableLearnerId() } });
  return data.data || data;
}

/** 提交作答并获取判卷结果 */
export async function gradeAnswer(questionId: string, answer: string, sessionId: string): Promise<any> {
  const { data } = await client.post(`/api/questions/${questionId}/grade`, { answer, sessionId, learnerId: getStableLearnerId() });
  return data.data || data;
}

/** 错题本 */
export async function getWeakQuestions(sessionId: string, errorType?: string): Promise<any> {
  const params: any = { sessionId, learnerId: getStableLearnerId() };
  if (errorType) params.errorType = errorType;
  const { data } = await client.get('/api/questions/weak', { params });
  return data.data || data;
}

/** 答题历史 */
export async function getAnswerHistory(sessionId: string): Promise<any> {
  const { data } = await client.get('/api/questions/history', { params: { sessionId, learnerId: getStableLearnerId() } });
  return data.data || data;
}

/** 题目集列表 */
export async function getQuestionSets(sessionId: string): Promise<any> {
  const { data } = await client.get('/api/questions/sets', { params: { sessionId, learnerId: getStableLearnerId() } });
  return data.data || data;
}

/** 删除题目集 */
export async function deleteQuestionSet(setId: string, sessionId: string): Promise<any> {
  const { data } = await client.delete(`/api/questions/sets/${setId}`, { params: { sessionId, learnerId: getStableLearnerId() } });
  return data;
}
