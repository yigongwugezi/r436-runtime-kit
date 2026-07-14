import type { WorkflowEvent, WorkflowState, WorkflowStatus } from '../api/workflows';

const STORAGE_PREFIX = 'eduagent.workflow-task.v1';
const MAX_AGE_MS = 30 * 60 * 1000;

export interface WorkflowTaskScope {
  workflowType: string;
  sessionId: string;
  subjectId?: string;
  pathId?: string;
  stageId?: string;
  chapterId?: string;
  sectionId?: string;
}

export interface WorkflowTaskRecoveryRecord extends WorkflowTaskScope {
  taskId: string;
  createdAt: number;
  resourceType?: string;
  mode?: string;
}

const scopeFields: Array<keyof Omit<WorkflowTaskScope, 'workflowType'>> = [
  'sessionId', 'subjectId', 'pathId', 'stageId', 'chapterId', 'sectionId',
];

function storage(): Storage | null {
  try { return typeof window === 'undefined' ? null : window.sessionStorage; } catch { return null; }
}

function value(scope: WorkflowTaskScope, field: keyof Omit<WorkflowTaskScope, 'workflowType'>): string {
  return String(scope[field] || '');
}

export function workflowTaskRecoveryKey(scope: WorkflowTaskScope): string {
  return `${STORAGE_PREFIX}:${[scope.workflowType, ...scopeFields.map((field) => value(scope, field))].map(encodeURIComponent).join(':')}`;
}

export function workflowTaskScopeMatches(record: WorkflowTaskRecoveryRecord, scope: WorkflowTaskScope): boolean {
  return record.workflowType === scope.workflowType
    && scopeFields.every((field) => value(record, field) === value(scope, field));
}

export function saveWorkflowTask(record: WorkflowTaskRecoveryRecord, target = storage()): void {
  if (!target || !record.taskId || !record.sessionId) return;
  target.setItem(workflowTaskRecoveryKey(record), JSON.stringify(record));
}

export function clearWorkflowTask(scope: WorkflowTaskScope, target = storage()): void {
  target?.removeItem(workflowTaskRecoveryKey(scope));
}

export function readWorkflowTask(scope: WorkflowTaskScope, target = storage(), now = Date.now()): WorkflowTaskRecoveryRecord | null {
  if (!target) return null;
  const key = workflowTaskRecoveryKey(scope);
  const raw = target.getItem(key);
  if (!raw) return null;
  try {
    const record = JSON.parse(raw) as WorkflowTaskRecoveryRecord;
    if (!record.taskId || !Number.isFinite(record.createdAt) || now - record.createdAt > MAX_AGE_MS || !workflowTaskScopeMatches(record, scope)) {
      target.removeItem(key);
      return null;
    }
    return record;
  } catch {
    target.removeItem(key);
    return null;
  }
}

export function isActiveWorkflowStatus(status: WorkflowStatus | string): boolean {
  return status === 'queued' || status === 'running';
}

export function isTerminalWorkflowStatus(status: WorkflowStatus | string): boolean {
  return ['completed', 'partial', 'cancelled', 'failed', 'expired'].includes(status);
}

export function workflowStateFromEvent(current: WorkflowState, event: WorkflowEvent): WorkflowState {
  if (event.sequence <= (current.events[current.events.length - 1]?.sequence || 0)) return current;
  const status: WorkflowStatus = event.event === 'workflow_completed' ? 'completed'
    : event.event === 'workflow_cancelled' ? 'cancelled'
      : event.event === 'workflow_failed' ? 'failed' : 'running';
  return { ...current, status, events: [...current.events, event], preview: event.text_delta ?? current.preview, elapsedMs: event.elapsed_ms };
}
