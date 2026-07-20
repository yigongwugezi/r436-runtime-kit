import assert from 'node:assert/strict';
import test from 'node:test';
import { groupTasksByDay, isTaskLocked, normalizePathForDisplay, restoreSelectedDay } from '../src/utils/learningPathDisplay.js';

test('does not repartition legacy tasks into guessed days', () => {
  assert.deepEqual(normalizePathForDisplay(undefined).stages, []);
  const legacy = normalizePathForDisplay({ stages: [{ id: 's', tasks: [{ task_id: 't1' }, { task_id: 't2' }, { task_id: 't3' }, { task_id: 't4' }] }] });
  assert.equal(legacy.formatInvalid, true);
  assert.deepEqual(legacy.stages[0].days, []);
  assert.deepEqual(legacy.stages[0].tasks, []);
});

test('keeps formal daily tasks and makes empty or malformed task arrays safe', () => {
  const display = normalizePathForDisplay({ stages: [{ id: 's', days: [{ id: 'd1', day: 1, globalDayIndex: 4, tasks: [{ id: 't1' }] }, { day: 2, globalDayIndex: 5, tasks: [] }] }] });
  assert.deepEqual(display.stages[0].tasks[0], { id: 't1', dayId: 'd1', globalDayIndex: 4 });
  assert.deepEqual(groupTasksByDay(display.stages)[0].days.map((day) => day.tasks.length), [1, 0]);
  assert.deepEqual(groupTasksByDay(display.stages)[0].days.map((day) => day.globalDayIndex), [4, 5]);
  assert.deepEqual(normalizePathForDisplay({ stages: [{ days: [], tasks: [] }] }).stages[0].days, []);
  const malformed = normalizePathForDisplay({ stages: [{ days: { tasks: [] } }] });
  assert.equal(malformed.formatInvalid, true);
  assert.deepEqual(groupTasksByDay(null), []);
});

test('restores a stale selected day without throwing during the path-page return', () => {
  const groups = groupTasksByDay(normalizePathForDisplay({ stages: [{ id: 's', days: [{ day: 2, tasks: [] }] }] }).stages);
  assert.deepEqual(restoreSelectedDay(groups, 'gone_day1'), { expandedStageId: 's', activeDayKey: 's_day2' });
});

test('does not mutate the API path object', () => {
  const raw = { stages: [{ id: 's', tasks: [{ task_id: 't' }] }] };
  normalizePathForDisplay(raw);
  assert.equal(raw.stages[0].days, undefined);
  assert.equal(raw.stages[0].tasks[0].task_id, 't');
});

test('keeps backend day locks and compares task positions inside the active day', () => {
  const tasks = [{ status: 'pending' }, { status: 'pending' }];
  const groups = groupTasksByDay([{ id: 's2', progressStatus: 'current', days: [{ day: 1, progressStatus: 'current', tasks }] }]);
  assert.equal(groups[0].days[0].progressStatus, 'current');
  assert.equal(isTaskLocked({ progressStatus: 'current' }, groups[0].days[0], tasks, 0), false);
  assert.equal(isTaskLocked({ progressStatus: 'current' }, groups[0].days[0], tasks, 1), true);
  assert.equal(isTaskLocked({ progressStatus: 'current' }, { progressStatus: 'locked' }, tasks, 0), true);
  assert.equal(isTaskLocked({ progressStatus: 'completed' }, { progressStatus: 'completed' }, tasks, 1), false);
});

test('defaults to the exact current day instead of an optional task in a completed stage', () => {
  const groups = groupTasksByDay([
    { id: 'done', progressStatus: 'completed', days: [{ day: 1, globalDayIndex: 1, progressStatus: 'completed', tasks: [] }, { day: 2, globalDayIndex: 2, progressStatus: 'completed', tasks: [{ required: false, status: 'pending' }] }] },
    { id: 'current', progressStatus: 'current', days: [{ day: 1, globalDayIndex: 3, progressStatus: 'current', tasks: [{ status: 'pending' }] }, { day: 2, globalDayIndex: 4, progressStatus: 'locked', tasks: [] }] },
  ]);
  assert.deepEqual(restoreSelectedDay(groups, null), { expandedStageId: 'current', activeDayKey: 'current_day1' });
  assert.deepEqual(restoreSelectedDay(groups, 'current_day2'), { expandedStageId: 'current', activeDayKey: 'current_day1' });
});
