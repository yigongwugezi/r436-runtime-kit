import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('generated resource callers send canonical task scope and abort stale reads', async () => {
  const [client, lecture, workspace] = await Promise.all([
    readFile(new URL('../src/api/sectionResources.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/pages/LecturePage.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/learning/SectionResourceWorkspace.tsx', import.meta.url), 'utf8'),
  ]);
  assert.match(client, /pathId: string;[\s\S]*stageId: string;[\s\S]*taskId: string;/);
  assert.match(client, /globalDayIndex\?: number/);
  assert.match(client, /if \(!scope\?\.pathId \|\| !scope\.stageId \|\| !scope\.taskId\) return \[\];/);
  assert.match(lecture, /resolveCanonicalLearningTaskScope\(path/);
  for (const source of [lecture, workspace]) {
    assert.match(source, /\{ pathId, stageId, taskId, dayId, globalDayIndex \}/);
    assert.match(source, /new AbortController\(\)/);
    assert.match(source, /controller\.abort\(\)/);
  }
  assert.match(workspace, /setNotice\(resourceErrorMessage\(error\)\)/);
});
