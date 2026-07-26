import { readFile } from 'node:fs/promises';

const phases = ['AUTH', 'SUBJECT_DISCOVERY', 'SUBJECT_SELECTION', 'SESSION_ENSURE', 'STORE_REHYDRATION', 'PATH_NAVIGATION', 'PATH_LOAD'];

/** Bootstrap an authenticated Playwright page into the isolated QA path.
 * This mirrors subjectStore's verified localStorage contract, then reloads so
 * the real auth -> subject-store -> canonical-session subscription runs. */
export async function bootstrapQaSubject(page, metadataPath) {
  const meta = JSON.parse(await readFile(metadataPath, 'utf8'));
  if (!meta?.subjectId || !meta?.sessionId || !meta?.pathId || Object.keys(meta).some((key) => /token|password|cookie|authorization/i.test(key))) {
    throw new Error('SUBJECT_DISCOVERY: invalid or sensitive QA metadata');
  }
  let phase = 'AUTH';
  try {
    const context = await page.evaluate(async (seed) => {
      const token = localStorage.getItem('edu_token');
      if (!token) throw new Error('AUTH: missing browser authentication');
      const headers = { Authorization: `Bearer ${token}` };
      const subjectsResponse = await fetch('/api/subjects', { headers });
      if (!subjectsResponse.ok) throw new Error(`SUBJECT_DISCOVERY: ${subjectsResponse.status}`);
      const subjectsBody = await subjectsResponse.json();
      const subjects = subjectsBody.data?.subjects ?? subjectsBody.subjects ?? [];
      const subject = subjects.find((item) => item.id === seed.subjectId);
      if (!subject) throw new Error('SUBJECT_SELECTION: seeded subject missing');
      const ensured = await fetch(`/api/subjects/${encodeURIComponent(seed.subjectId)}/session/ensure`, { method: 'POST', headers });
      if (!ensured.ok) throw new Error(`SESSION_ENSURE: ${ensured.status}`);
      const ensuredBody = await ensured.json();
      const canonical = ensuredBody.data ?? ensuredBody;
      if (canonical.session_id !== seed.sessionId || canonical.path_id !== seed.pathId) throw new Error('SESSION_ENSURE: unexpected canonical scope');
      localStorage.setItem(`r436_runtime_subjects_${seed.learnerId}`, JSON.stringify(subjects));
      localStorage.setItem(`r436_runtime_active_subject_${seed.learnerId}`, JSON.stringify(subject));
      return { subjectId: subject.id, sessionId: canonical.session_id, pathId: canonical.path_id };
    }, meta);
    phase = 'STORE_REHYDRATION';
    await page.reload();
    await page.waitForFunction(({ learnerId, subjectId }) => {
      try { return JSON.parse(localStorage.getItem(`r436_runtime_active_subject_${learnerId}`) || 'null')?.id === subjectId; } catch { return false; }
    }, { learnerId: meta.learnerId, subjectId: meta.subjectId });
    phase = 'PATH_NAVIGATION';
    await page.goto(`/path?pathId=${encodeURIComponent(context.pathId)}`);
    phase = 'PATH_LOAD';
    await page.waitForFunction(async ({ sessionId, subjectId, pathId }) => {
      const response = await fetch(`/api/learning-path?sessionId=${encodeURIComponent(sessionId)}&subjectId=${encodeURIComponent(subjectId)}&pathId=${encodeURIComponent(pathId)}`);
      const body = await response.json();
      return response.ok && (body.data?.path ?? body.path)?.id === pathId;
    }, context);
    return context;
  } catch (error) {
    const message = String(error?.message || error);
    const known = phases.find((item) => message.startsWith(item));
    throw new Error(`${known || phase}: ${message}`);
  }
}
