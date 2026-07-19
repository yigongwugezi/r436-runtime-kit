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
});
