import client from './client';
import { streamGet } from './client';

export type WorkflowStatus = 'queued' | 'running' | 'completed' | 'partial' | 'cancelled' | 'failed' | 'expired';
export interface WorkflowEvent {
  event: string;
  task_id: string;
  workflow_type: string;
  stage_id: string;
  status: string;
  label: string;
  summary?: string;
  completed_units?: number | null;
  total_units?: number | null;
  elapsed_ms: number;
  sequence: number;
  used_fallback?: boolean;
  text_delta?: string;
  safe_error_message?: string;
  safe_metadata?: Record<string, unknown>;
}
export interface WorkflowState {
  taskId: string;
  workflowType: string;
  status: WorkflowStatus;
  events: WorkflowEvent[];
  preview: string;
  elapsedMs: number;
  result?: any;
  errorMessage?: string;
}

export async function startWorkflow(workflowType: string, payload: Record<string, unknown>) {
  const { data } = await client.post(`/api/workflows/${encodeURIComponent(workflowType)}/start`, payload);
  return data as { task_id: string; workflow_type: string; status: WorkflowStatus; events_url: string; reused_existing?: boolean };
}

const pendingLectureEnsures = new Map<string, Promise<any>>();

export async function readSectionLecture(sectionId: string, payload: Record<string, unknown>) {
  const { data } = await client.get(`/api/sections/${encodeURIComponent(sectionId)}/lecture`, {
    params: { sessionId: payload.sessionId, pathId: payload.pathId, stageId: payload.stageId, taskId: payload.taskId },
  });
  return data;
}

export function ensureLecture(sectionId: string, payload: Record<string, unknown>) {
  const key = [payload.sessionId, payload.subjectId, payload.pathId, payload.stageId, payload.taskId].join('|');
  const pending = pendingLectureEnsures.get(key);
  if (pending) return pending;
  const request = client.post(`/api/sections/${encodeURIComponent(sectionId)}/lecture/ensure`, payload)
    .then(({ data }) => data as { status: 'ready' | 'running' | 'failed'; workflowId: string | null; lecture: any | null; errorCode?: string | null; errorMessage?: string | null })
    .finally(() => pendingLectureEnsures.delete(key));
  pendingLectureEnsures.set(key, request);
  return request;
}

export function ensureVideoFallbackLecture(taskId: string, payload: Record<string, unknown>) {
  const key = [payload.sessionId, payload.subjectId, payload.pathId, payload.stageId, payload.dayId, payload.globalDayIndex, taskId, 'video_fallback'].join('|');
  const pending = pendingLectureEnsures.get(key);
  if (pending) return pending;
  const request = client.post(`/api/learning-path/tasks/${encodeURIComponent(taskId)}/video-fallback/lecture/ensure`, payload)
    .then(({ data }) => data as { status: 'ready' | 'running' | 'failed'; workflowId: string | null; lecture: any | null; errorCode?: string | null; errorMessage?: string | null })
    .finally(() => pendingLectureEnsures.delete(key));
  pendingLectureEnsures.set(key, request);
  return request;
}

export async function readWorkflow(taskId: string, sessionId?: string) {
  const { data } = await client.get(`/api/workflows/${encodeURIComponent(taskId)}`, { params: sessionId ? { sessionId } : undefined });
  return data;
}

export async function cancelWorkflow(taskId: string, sessionId: string) {
  const { data } = await client.post(`/api/workflows/${encodeURIComponent(taskId)}/cancel`, { sessionId });
  return data;
}

export async function retryWorkflow(taskId: string) {
  const { data } = await client.post(`/api/workflows/${encodeURIComponent(taskId)}/retry`);
  return data as { task_id: string; workflow_type: string; status: WorkflowStatus; reused_existing?: boolean };
}

export async function consumeWorkflowEvents(
  taskId: string,
  onEvent: (event: WorkflowEvent) => void,
  signal?: AbortSignal,
  after = 0,
) {
  const reader = await streamGet(`/api/workflows/${encodeURIComponent(taskId)}/events?after=${after}`, signal, after);
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split('\n\n');
      buffer = blocks.pop() || '';
      for (const block of blocks) {
        const raw = block.split('\n').find((line) => line.startsWith('data: '))?.slice(6);
        if (!raw) continue;
        const event = JSON.parse(raw) as WorkflowEvent;
        if (event.event !== 'heartbeat') onEvent(event);
      }
    }
  } finally {
    reader.releaseLock();
  }
}
