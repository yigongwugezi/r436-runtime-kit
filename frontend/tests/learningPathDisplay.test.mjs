import assert from 'node:assert/strict';
import test from 'node:test';
import { groupTasksByDay, normalizePathForDisplay, restoreSelectedDay } from '../src/utils/learningPathDisplay.js';

test('does not repartition legacy tasks into guessed days', () => {
  assert.deepEqual(normalizePathForDisplay(undefined).stages, []);
  const legacy = normalizePathForDisplay({ stages: [{ id: 's', tasks: [{ task_id: 't1' }, { task_id: 't2' }, { task_id: 't3' }, { task_id: 't4' }] }] });
  assert.equal(legacy.formatInvalid, true);
  assert.deepEqual(legacy.stages[0].days, []);
  assert.deepEqual(legacy.stages[0].tasks, []);
});

test('keeps formal daily tasks and makes empty or malformed task arrays safe', () => {
  const display = normalizePathForDisplay({ stages: [{ id: 's', days: [{ day: 1, globalDayIndex: 4 }, { day: 2, globalDayIndex: 5, tasks: [] }] }] });
  assert.deepEqual(groupTasksByDay(display.stages)[0].days.map((day) => day.tasks.length), [0, 0]);
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
