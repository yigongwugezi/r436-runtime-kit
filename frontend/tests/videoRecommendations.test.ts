import assert from 'node:assert/strict';
import { normalizeVideoRecommendations, requestVideoRecommendations, retryVideoRecommendations, videoRecommendationScope } from '../src/api/videoRecommendations.ts';

const scope = { sessionId: 'session', subjectId: 'subject', pathId: 'path', stageId: 'stage', dayId: 'day', globalDayIndex: 2, taskId: 'task' };
assert.equal(videoRecommendationScope(scope), 'session|subject|path|stage|day|2|task|video');
assert.equal(videoRecommendationScope({ ...scope, taskId: '' }), '');
assert.deepEqual(normalizeVideoRecommendations({ data: { recommendations: { status: 'completed', resources: [{ resource_type: 'video', title: 'Big O', url: 'https://www.bilibili.com/video/BV1bigO' }, { resource_type: 'article', title: 'Article' }] } } }), { status: 'completed', resources: [{ resource_type: 'video', title: 'Big O', url: 'https://www.bilibili.com/video/BV1bigO' }] });
assert.deepEqual(normalizeVideoRecommendations({ data: { recommendations: { status: 'no_high_relevance', resources: [] } } }), { status: 'no_high_relevance', resources: [] });
assert.deepEqual(normalizeVideoRecommendations({ data: { resources: [{ resourceType: 'video', title: 'Big O' }] } }), { status: 'completed', resources: [{ resourceType: 'video', title: 'Big O' }] });

let calls = 0;
const originalFetch = globalThis.fetch;
globalThis.fetch = async () => { calls += 1; return new Response(JSON.stringify({ data: { recommendations: { status: 'completed', resources: [{ resource_type: 'video', title: 'Big O' }] } } })); };
try {
  retryVideoRecommendations(scope);
  const [first, second] = await Promise.all([requestVideoRecommendations(scope), requestVideoRecommendations(scope)]);
  assert.equal(calls, 1);
  assert.equal(first.resources[0].title, second.resources[0].title);
  await requestVideoRecommendations(scope);
  assert.equal(calls, 1);
  retryVideoRecommendations(scope);
  await requestVideoRecommendations(scope);
  assert.equal(calls, 2);
} finally {
  globalThis.fetch = originalFetch;
}
console.log('video recommendations: PASS');
