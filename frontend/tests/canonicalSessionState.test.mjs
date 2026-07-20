import assert from 'node:assert/strict';
import test from 'node:test';
import {
  acceptsCanonicalResult,
  canLoadCanonicalData,
  canonicalRequestKey,
  hydrateChatSessions,
  resolveActiveSubjectContext,
} from '../src/utils/canonicalSessionState.js';

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

test('class subjects use their canonical subject and remote chat history keeps cached messages', () => {
  assert.deepEqual(resolveActiveSubjectContext(null, { subject: 'subject-class', name: '算法班' }), {
    subjectId: 'subject-class',
    subjectName: '算法班',
  });
  assert.deepEqual(resolveActiveSubjectContext({ id: 'subject-personal', name: '算法', textbookId: 'book-1' }, null), {
    subjectId: 'subject-personal',
    subjectName: '算法',
    textbookId: 'book-1',
  });

  const messages = [{ id: 'message-1', role: 'user', content: '解释复杂度', timestamp: 1 }];
  assert.deepEqual(
    hydrateChatSessions(
      [{ id: 'session-1', title: '', createdAt: 100, updatedAt: 200 }],
      [{ id: 'session-1', title: '本地标题', createdAt: 1, updatedAt: 2, messages }],
    ),
    [{ id: 'session-1', title: '未命名会话', createdAt: 100, updatedAt: 200, messages }],
  );
});
