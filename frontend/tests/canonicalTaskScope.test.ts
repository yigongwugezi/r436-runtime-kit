import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { learningTaskRoute, resolveCanonicalLearningTaskScope } from '../src/utils/learningTaskRoute.ts';

const request = { sessionId: 's', subjectId: 'subject', pathId: 'path', stageId: 'stage', dayId: 'day-3', globalDayIndex: 3, taskId: 'task-2', sectionId: 'section-2', taskType: 'quiz_prac' };
const path = { id: 'path', stages: [{ id: 'stage', days: [{ id: 'day-3', globalDayIndex: 3, tasks: [{ id: 'task-1', type: 'read_doc' }, { id: 'task-2', type: 'quiz_prac' }] }, { id: 'day-2', globalDayIndex: 2, tasks: [{ id: 'old-task', type: 'quiz_prac' }] }] }] };

test('learning task route carries canonical day scope without section fallback', () => {
  const route = learningTaskRoute('quiz_prac', request);
  assert.match(route, /taskId=task-2/);
  assert.match(route, /dayId=day-3/);
  assert.match(route, /globalDayIndex=3/);
  assert.match(route, /^\/lecture\/section\/section-2\?/);
  const noSectionRoute = learningTaskRoute('quiz_prac', { ...request, sectionId: undefined });
  assert.match(noSectionRoute, /^\/lecture\/section\/\?/);
  assert.match(noSectionRoute, /taskId=task-2/);
});

test('canonical resolver only selects the requested task inside the requested day', () => {
  assert.equal(resolveCanonicalLearningTaskScope(path, request)?.taskId, 'task-2');
  assert.equal(resolveCanonicalLearningTaskScope(path, { ...request, taskId: 'old-task' }), null);
  assert.equal(resolveCanonicalLearningTaskScope(path, { ...request, globalDayIndex: 2 }), null);
  assert.equal(resolveCanonicalLearningTaskScope(path, { ...request, dayId: '' }), null);
});

test('workspace callers require the canonical scope', () => {
  const lecture = readFileSync(new URL('../src/pages/LecturePage.tsx', import.meta.url), 'utf8');
  const learningPath = readFileSync(new URL('../src/pages/LearningPathPage.tsx', import.meta.url), 'utf8');
  assert.match(learningPath, /dayId, globalDayIndex/);
  assert.match(lecture, /resolveCanonicalLearningTaskScope\(path/);
  assert.match(lecture, /canonicalScopePending = taskWorkspaceRequest && canonicalPathLoading/);
  assert.match(lecture, /taskScopeInvalid = taskWorkspaceRequest && !canonicalPathLoading && !canonicalTaskScope/);
  assert.match(lecture, /const lectureSemanticKey = canonicalTaskScope \? JSON\.stringify/);
  assert.match(lecture, /taskDescription: canonicalTaskScope\?\.task\.description/);
  assert.match(lecture, /if \(workspaceScopeInvalid\) return;/);
  assert.match(lecture, /if \(workspaceScopeInvalid\) \{/);
  assert.doesNotMatch(lecture, /taskDayScope\(path, resourceTaskId\)/);
  assert.match(lecture, /onComplete=\{\(\) => executionMode !== 'video' \|\| videoLectureFallback \? completeFocusedTask\(\) : false\}/);
  assert.doesNotMatch(lecture, /event: 'section_complete'/);
});
