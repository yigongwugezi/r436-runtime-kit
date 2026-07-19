import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('video fallback uses one delivery mode and never exposes ordinary generation', () => {
  const page = readFileSync(new URL('../src/pages/LecturePage.tsx', import.meta.url), 'utf8');
  const api = readFileSync(new URL('../src/api/learningPath.ts', import.meta.url), 'utf8');
  assert.match(api, /return data\?\.data \|\| data/);
  assert.match(page, /const deliveryMode =/);
  assert.match(page, /if \(deliveryMode !== 'lecture'\) return/);
  assert.match(page, /deliveryMode !== 'video_fallback_lecture'/);
  assert.match(page, /if \(executionMode === 'video'\) return/);
  assert.match(page, /const selectVideoFallback/);
  assert.match(page, /workflowType: 'video_fallback_lecture'/);
  assert.match(page, /recoveryKey: \[canonicalRequestScope\.dayId, canonicalRequestScope\.globalDayIndex, resourceTaskId/);
  assert.match(page, /saveWorkflowTask\(\{ \.\.\.fallbackWorkflowScope, taskId: data\.workflowId/);
  assert.match(page, /const workflow = await readWorkflow\(fallbackWorkflowId/);
  assert.match(page, /await getVideoFallbackState\(resourceTaskId, canonicalRequestScope\)/);
  assert.match(page, /重新生成图文讲解/);
  const content = page.indexOf("quizState !== 'idle' ? null : sectionContent ?");
  const fallbackError = page.indexOf('isVideoFallbackDelivery && fallbackEnsureError', content);
  const fallbackLoading = page.indexOf('isVideoFallbackDelivery ? (', fallbackError);
  const ordinaryLoading = page.indexOf(') : loadingLecture ? (', fallbackLoading);
  const ordinaryEmpty = page.indexOf('!isTextbookMode && !isVideoFallbackDelivery', ordinaryLoading);
  assert.ok(content >= 0 && content < fallbackError && fallbackError < fallbackLoading && fallbackLoading < ordinaryLoading && ordinaryLoading < ordinaryEmpty);
  assert.match(page, /正在生成图文讲解/);
  assert.match(page, /AI 正在将本视频任务转换为可阅读的图文教材，请稍候…/);
});
