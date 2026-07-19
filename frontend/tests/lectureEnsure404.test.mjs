import assert from 'node:assert/strict';
import test from 'node:test';
import { createLectureEnsureGuard } from '../src/utils/lectureEnsureGuard.js';

test('scope errors block automatic ensure repeats until explicit retry', () => {
  for (const status of [403, 404, 409]) {
    const guard = createLectureEnsureGuard();
    const scope = `session|subject|path|stage|task|${status}`;
    assert.equal(guard.blocks(scope), false);
    guard.recordError(scope, status);
    assert.equal(guard.blocks(scope), true);
    guard.retry(scope);
    assert.equal(guard.blocks(scope), false);
  }
});
