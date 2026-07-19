import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const route = readFileSync(new URL('../src/utils/learningTaskRoute.ts', import.meta.url), 'utf8');
const api = readFileSync(new URL('../src/api/learningPath.ts', import.meta.url), 'utf8');
const lecture = readFileSync(new URL('../src/pages/LecturePage.tsx', import.meta.url), 'utf8');
const path = readFileSync(new URL('../src/pages/LearningPathPage.tsx', import.meta.url), 'utf8');

assert.match(route, /\['legacy', '1'\]/);
assert.match(api, /\/api\/learning-path\/tasks\/\$\{encodeURIComponent\(taskId\)\}\/complete/);
assert.match(lecture, /completeLearningPathTask\(focusedTaskId/);
assert.match(lecture, /resourceDayScope\.status === 'completed'/);
assert.doesNotMatch(lecture, /updateKnowledgePoint\(focusedTaskId, \{ status: 'mastered'/);
assert.match(path, /const dayLocked = day\.progressStatus === 'locked';/);
console.log('learning task completion frontend: PASS');
