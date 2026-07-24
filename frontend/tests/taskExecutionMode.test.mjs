import assert from 'node:assert/strict';
import { resolveTaskExecutionMode } from '../src/utils/taskExecutionMode.ts';

assert.equal(resolveTaskExecutionMode({ type: 'watch_video' }), 'video');
assert.equal(resolveTaskExecutionMode({ task_type: 'quiz_prac' }), 'quiz');
assert.equal(resolveTaskExecutionMode({ taskType: 'mindmap' }), 'mindmap');
assert.equal(resolveTaskExecutionMode({ type: 'unknown' }), 'unsupported');
assert.equal(resolveTaskExecutionMode({}), 'lecture');
console.log('task execution mode: PASS');
