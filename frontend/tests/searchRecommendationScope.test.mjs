import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('../src/pages/LearningPathPage.tsx', import.meta.url), 'utf8');
assert.match(page, /subjectId: subject\.subject_id, pathId: path\?\.id, stageId: activeDayStage\.stageId, taskId:/);
assert.match(page, /暂无高相关资源/);
console.log('search recommendation scope frontend: PASS');
