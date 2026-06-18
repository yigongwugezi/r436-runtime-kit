import client from './client';
import type { ChatMessage, ChatSession, GenerationProgress } from '../types/chat';

export interface SendMessageParams {
  sessionId?: string;
  subjectId?: string;
  message: string;
}

export interface ChatResponse {
  sessionId: string;
  reply: ChatMessage;
}

export interface SessionListResponse {
  sessions: ChatSession[];
}

/** 发送消息（非流式） */
export async function sendMessage(params: SendMessageParams): Promise<ChatResponse> {
  const { data } = await client.post('/chat/send', params);
  return data;
}

/** 获取会话列表 */
export async function getSessions(): Promise<SessionListResponse> {
  const { data } = await client.get('/chat/sessions');
  return data;
}

/** 获取会话消息 */
export async function getSessionMessages(sessionId: string): Promise<{ messages: ChatMessage[] }> {
  const { data } = await client.get(`/chat/sessions/${sessionId}`);
  return data;
}

/** 删除会话 */
export async function deleteSession(sessionId: string): Promise<void> {
  await client.delete(`/chat/sessions/${sessionId}`);
}

/** 获取快捷指令 */
export async function getQuickCommands(): Promise<{ commands: { id: string; label: string; icon: string; prompt: string }[] }> {
  const { data } = await client.get('/chat/quick-commands');
  return data;
}

/** 轮询生成进度 */
export async function getGenerationProgress(taskId: string): Promise<{ progress: GenerationProgress }> {
  const { data } = await client.get(`/chat/progress/${taskId}`);
  return data;
}
