import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
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

test('opening an empty lecture only reads existing content and waits for an explicit generate click', () => {
  const page = readFileSync(new URL('../src/pages/LecturePage.tsx', import.meta.url), 'utf8');
  const start = page.indexOf('// ── 加载已有文档');
  const loader = page.slice(start, page.indexOf('\n\n  useEffect(() => {', start));
  assert.match(loader, /readSectionLecture\(/);
  assert.doesNotMatch(loader, /ensureLecture\(/);
});
