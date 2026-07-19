import assert from 'node:assert/strict';
import test from 'node:test';
import { acceptsCanonicalResult, canLoadCanonicalData, canonicalRequestKey } from '../src/utils/canonicalSessionState.js';

test('subject data waits for the canonical session', () => {
  assert.equal(canLoadCanonicalData('unresolved', 'old-local-session'), false);
  assert.equal(canLoadCanonicalData('resolving', 'old-local-session'), false);
  assert.equal(canLoadCanonicalData('resolved', 'canonical-session'), true);
});

test('same subject requests share a stable key and stale subjects cannot win', () => {
  const current = canonicalRequestKey('learner', 'new-subject');
  assert.equal(canonicalRequestKey('learner', 'new-subject'), current);
  assert.equal(acceptsCanonicalResult(current, canonicalRequestKey('learner', 'old-subject')), false);
  assert.equal(acceptsCanonicalResult(current, current), true);
});
