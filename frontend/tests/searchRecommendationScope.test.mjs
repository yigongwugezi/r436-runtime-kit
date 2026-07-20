import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('../src/pages/LearningPathPage.tsx', import.meta.url), 'utf8');
assert.match(page, /const \{ stageId, dayId, globalDayIndex \} = activeDayStage/);
assert.match(page, /stageId, dayId, globalDayIndex,/);
assert.match(page, /taskId: activeDayTasks/);
assert.match(page, /暂无高相关资源/);
console.log('search recommendation scope frontend: PASS');
