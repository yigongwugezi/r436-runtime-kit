import assert from 'node:assert/strict';
import {
  clearWorkflowTask,
  isActiveWorkflowStatus,
  isTerminalWorkflowStatus,
  readWorkflowTask,
  saveWorkflowTask,
  workflowStateFromEvent,
  type WorkflowTaskScope,
} from '../src/utils/workflowTaskRecovery.ts';

class MemoryStorage {
  private readonly values = new Map<string, string>();
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
  removeItem(key: string) { this.values.delete(key); }
}

const scope: WorkflowTaskScope = {
  workflowType: 'generated_resource', sessionId: 'session-a', subjectId: 'subject-a',
  pathId: 'path-a', stageId: 'stage-a', chapterId: 'chapter-a', sectionId: 'section-a',
};
const storage = new MemoryStorage();
const now = 1_000_000;

saveWorkflowTask({ ...scope, taskId: 'task-a', createdAt: now, resourceType: 'summary_card' }, storage as unknown as Storage);
assert.deepEqual(readWorkflowTask(scope, storage as unknown as Storage, now), { ...scope, taskId: 'task-a', createdAt: now, resourceType: 'summary_card' });
assert.equal(readWorkflowTask({ ...scope, sessionId: 'session-b' }, storage as unknown as Storage, now), null, 'a different session must not recover the task');
assert.deepEqual(readWorkflowTask(scope, storage as unknown as Storage, now), { ...scope, taskId: 'task-a', createdAt: now, resourceType: 'summary_card' });
assert.equal(readWorkflowTask(scope, storage as unknown as Storage, now + 30 * 60 * 1000 + 1), null, 'expired records must be removed');

saveWorkflowTask({ ...scope, taskId: 'task-b', createdAt: now }, storage as unknown as Storage);
clearWorkflowTask(scope, storage as unknown as Storage);
assert.equal(readWorkflowTask(scope, storage as unknown as Storage, now), null, 'terminal tasks can clear their marker');

const generalScope: WorkflowTaskScope = {
  workflowType: 'general_resource_generation', sessionId: 'session-a', subjectId: 'subject-a',
  resourceType: 'quiz', operation: 'generate', topicFingerprint: 'f00d', recoveryKey: 'quiz:f00d',
};
saveWorkflowTask({ ...generalScope, taskId: 'task-general', createdAt: now, resourceType: 'quiz' }, storage as unknown as Storage);
assert.equal(readWorkflowTask({ ...generalScope, resourceType: 'lecture', recoveryKey: 'lecture:f00d' }, storage as unknown as Storage, now), null, 'different type/topic recovery markers must not collide');
assert.equal(readWorkflowTask(generalScope, storage as unknown as Storage, now)?.taskId, 'task-general');
clearWorkflowTask(generalScope, storage as unknown as Storage);
assert.equal(isActiveWorkflowStatus('queued'), true);
assert.equal(isActiveWorkflowStatus('completed'), false);
assert.equal(isTerminalWorkflowStatus('failed'), true);
assert.equal(isTerminalWorkflowStatus('running'), false);

const updated = workflowStateFromEvent(
  { taskId: 'task-a', workflowType: 'generated_resource', status: 'running', events: [], preview: '', elapsedMs: 0 },
  { event: 'stage_progress', task_id: 'task-a', workflow_type: 'generated_resource', stage_id: 'generate', status: 'running', label: 'working', elapsed_ms: 50, sequence: 1, text_delta: 'preview' },
);
assert.equal(updated.events.length, 1);
assert.equal(updated.preview, 'preview');
assert.equal(workflowStateFromEvent(updated, updated.events[0]).events.length, 1, 'replayed events must not duplicate');
const failed = workflowStateFromEvent(
  updated,
  { event: 'workflow_failed', task_id: 'task-a', workflow_type: 'generated_resource', stage_id: 'generate', status: 'failed', label: 'failed', elapsed_ms: 60, sequence: 2, safe_error_message: 'provider unavailable' },
);
assert.equal(failed.status, 'failed');
assert.equal(failed.errorMessage, 'provider unavailable');
console.log('workflow task recovery tests: ok');
