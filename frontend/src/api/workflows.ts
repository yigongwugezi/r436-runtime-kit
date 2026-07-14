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
}

export async function startWorkflow(workflowType: string, payload: Record<string, unknown>) {
  const { data } = await client.post(`/api/workflows/${encodeURIComponent(workflowType)}/start`, payload);
  return data as { task_id: string; workflow_type: string; status: WorkflowStatus; events_url: string };
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
  return data as { task_id: string; workflow_type: string; status: WorkflowStatus };
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
