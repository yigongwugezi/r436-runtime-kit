import assert from 'node:assert/strict';
import test from 'node:test';
import { groupTasksByDay, normalizePathForDisplay, restoreSelectedDay } from '../src/utils/learningPathDisplay.js';

test('normalizes missing and legacy path arrays without assigning task ids', () => {
  assert.deepEqual(normalizePathForDisplay(undefined).stages, []);
  const legacy = normalizePathForDisplay({ stages: [{ id: 's', tasks: [{ task_id: 't1' }, { task_id: 't2' }, { task_id: 't3' }, { task_id: 't4' }] }] });
  assert.deepEqual(legacy.stages[0].days.map((day) => day.tasks.length), [3, 1]);
  assert.equal(legacy.stages[0].tasks[0].task_id, 't1');
});

test('keeps formal daily tasks and makes empty or malformed task arrays safe', () => {
  const display = normalizePathForDisplay({ stages: [{ id: 's', days: [{ day: 1 }, { day: 2, tasks: [] }] }] });
  assert.deepEqual(groupTasksByDay(display.stages)[0].days.map((day) => day.tasks.length), [0, 0]);
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
