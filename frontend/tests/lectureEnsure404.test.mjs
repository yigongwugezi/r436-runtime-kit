import assert from 'node:assert/strict';
import test from 'node:test';
import { createLectureEnsureGuard } from '../src/utils/lectureEnsureGuard.js';

test('a 404 blocks automatic ensure repeats until explicit retry', () => {
  const guard = createLectureEnsureGuard();
  const scope = 'session|subject|path|stage|task';
  assert.equal(guard.blocks(scope), false);
  guard.recordError(scope, 404);
  assert.equal(guard.blocks(scope), true);
  guard.retry(scope);
  assert.equal(guard.blocks(scope), false);
});
