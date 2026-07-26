import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { authenticateQaUser } from './helpers/authenticateQaUser.mjs';
import { bootstrapQaSubject } from './helpers/bootstrapQaSubject.mjs';
import { startBrowserQa } from './startBrowserQa.mjs';

const root = resolve(fileURLToPath(new URL('../../..', import.meta.url)));
const arg = (name, fallback = '') => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] || fallback : fallback;
const scenario = arg('--scenario', 'bootstrap');
const headed = process.argv.includes('--headed');
const runtime = resolve(root, '.qa/runtime/browser-qa');
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const evidence = resolve(root, 'frontend/test-results/dynamic-qa', `${stamp}-${scenario}`);
const safePath = (url) => { try { return new URL(url).pathname; } catch { return String(url).split('?')[0]; } };
const openTask = async (page, day, title) => {
  await page.evaluate((index) => { const url = new URL(location.href); url.searchParams.set('day', String(index)); history.pushState({}, '', url); dispatchEvent(new PopStateEvent('popstate')); }, day);
  const card = page.locator('article').filter({ hasText: title }).last();
  await card.getByRole('button').click();
  await page.waitForURL(/\/lecture\/section\//);
};

async function main() {
  const started = await startBrowserQa({ detached: false, scenario });
  const execution = started.metadata;
  const meta = JSON.parse(await readFile(execution.seedMetadataPath, 'utf8'));
  const storage = resolve(root, 'frontend/.qa-auth/browser-qa-storage-state.json');
  await mkdir(evidence, { recursive: true });
  await mkdir(resolve(root, 'frontend/.qa-auth'), { recursive: true });
  const events = { console: [], pageErrors: [], network: [] };
  const browser = await chromium.launch({ headless: !headed });
  let context;
  try {
    context = await browser.newContext({ baseURL: execution.frontendBaseUrl });
    await context.tracing.start({ screenshots: true, snapshots: true });
    let page = await context.newPage();
    page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') events.console.push(`${m.type()}: ${m.text()}`); });
    page.on('pageerror', (e) => events.pageErrors.push(e.message));
    page.on('response', (r) => { if (r.status() >= 400) events.network.push({ path: safePath(r.url()), status: r.status() }); });
    await page.goto('/login');
    const learnerId = await authenticateQaUser(page, { credentialsPath: resolve(runtime, 'auth-runtime.json'), storageStatePath: storage, expectedLearnerId: meta.learnerId });
    await context.close();
    context = await browser.newContext({ baseURL: execution.frontendBaseUrl, storageState: storage });
    await context.tracing.start({ screenshots: true, snapshots: true });
    page = await context.newPage();
    page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') events.console.push(`${m.type()}: ${m.text()}`); });
    page.on('pageerror', (e) => events.pageErrors.push(e.message));
    page.on('response', (r) => { if (r.status() >= 400) events.network.push({ path: safePath(r.url()), status: r.status() }); });
    await page.goto('/path');
    const me = await page.evaluate(async () => (await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${localStorage.edu_token}` } })).status);
    if (me !== 200) throw new Error(`AUTH_ME_VERIFY: ${me}`);
    const scope = await bootstrapQaSubject(page, resolve(runtime, 'seed-metadata.json'));
    if (scope.pathId !== meta.pathId) throw new Error('PATH_LOAD: unexpected path');
    await page.waitForFunction((title) => document.body.innerText.includes(title), 'Data Structures');
    if (scenario === 'path-performance') {
      const timings = [];
      for (let i = 0; i < 3; i += 1) { const start = Date.now(); await page.reload(); await page.waitForFunction((title) => document.body.innerText.includes(title), 'Data Structures'); timings.push(Date.now() - start); }
      await writeFile(resolve(evidence, 'performance.json'), JSON.stringify({ pathVisibleMs: timings }, null, 2));
    } else if (scenario === 'mindmap') {
      await openTask(page, 4, 'Mind map');
      await page.waitForSelector('svg', { timeout: 15000 });
      const box = await page.locator('svg').first().boundingBox();
      if (!box || box.width < 100 || box.height < 100) throw new Error('VISUAL_LAYOUT_ERROR: invalid mindmap bounds');
    } else if (scenario === 'zero-diff') {
      const actions = page.getByRole('button', { name: /确认调整|拒绝调整/ });
      if (await actions.count()) throw new Error('ZERO_DIFF_ACTIONS_VISIBLE');
    } else if (scenario === 'quiz-retake') {
      await openTask(page, 2, 'Quiz');
      await page.screenshot({ path: resolve(evidence, 'quiz-before-action.png'), fullPage: true });
      const submitStatuses = [];
      const timeline = [];
      const submitPath = `/tasks/${meta.quizTaskId}/quiz/submit`;
      const mark = (event, extra = {}) => timeline.push({ atMs: Date.now(), event, ...extra });
      page.on('request', (request) => {
        const path = safePath(request.url());
        if (path.endsWith(submitPath)) mark('submit-request-start');
        else if (/learning-path|quiz|attempt/.test(path)) mark('state-request-start', { path });
      });
      page.on('response', (response) => {
        if (safePath(response.url()).endsWith(submitPath)) {
          submitStatuses.push(response.status());
          mark('submit-response', { status: response.status() });
        }
      });
      const answer = async (fixture) => { for (const [questionId, option] of Object.entries(fixture)) await page.getByTestId(`quiz-option-${questionId}-${option}`).click(); };
      let navigated = false;
      page.on('framenavigated', (frame) => { if (frame === page.mainFrame()) navigated = true; });
      const submitAndRecord = async (round) => {
        const responsePromise = page.waitForResponse((response) => safePath(response.url()).endsWith(submitPath));
        mark(`${round}-submit-click`);
        await page.getByTestId('quiz-submit').click();
        const response = await responsePromise;
        const body = await response.json().catch(() => ({}));
        const data = body?.data || body || {};
        mark(`${round}-submit-finished`, {
          status: response.status(), score: data.score ?? data.totalScore ?? null,
          attemptPassed: data.attemptPassed ?? null, bestScore: data.bestScore ?? null,
          everPassed: data.everPassed ?? null, completed: data.pathTaskCompleted ?? null,
          hasAttempt: Boolean(data.attempt),
        });
        return data;
      };
      await page.getByTestId(`quiz-question-${Object.keys(meta.quizAnswers.correct)[0]}`).waitFor({ timeout: 15000 });
      await answer(meta.quizAnswers.firstRound);
      await submitAndRecord('first');
      await page.waitForFunction(() => document.querySelector('[data-testid="quiz-score"]')?.textContent?.trim() === '40');
      mark('first-score-visible');
      if (submitStatuses.length !== 1 || submitStatuses[0] !== 200) throw new Error(`QUIZ_FIRST_SUBMIT: ${submitStatuses.join(',')}`);
      await page.getByTestId('quiz-retake').click();
      await answer(meta.quizAnswers.correct);
      await page.screenshot({ path: resolve(evidence, 'quiz-second-before-submit.png'), fullPage: true });
      try {
        const second = await submitAndRecord('second');
        await page.screenshot({ path: resolve(evidence, 'quiz-second-response.png'), fullPage: true });
        await page.waitForFunction(() => document.querySelector('[data-testid="quiz-score"]')?.textContent?.trim() === '100', { timeout: 5000 });
        mark('second-score-visible');
        mark('second-result-state', { result: await page.getByTestId('quiz-result').innerText() });
        await page.waitForTimeout(5000);
        await page.screenshot({ path: resolve(evidence, 'quiz-second-5s.png'), fullPage: true });
        await page.waitForTimeout(25000);
        await page.screenshot({ path: resolve(evidence, 'quiz-second-30s.png'), fullPage: true });
        await writeFile(resolve(evidence, 'quiz-30s-dom-snapshot.html'), await page.locator('[data-testid="quiz-result"], [data-testid^="quiz-question-"]').evaluateAll((nodes) => nodes.map((node) => node.outerHTML).join('\n')));
        mark('second-30s-dom-captured', { navigated });
        await page.reload();
        const persisted = await page.evaluate(async ({ quizId, sessionId, subjectId, pathId, taskId }) => {
          const headers = { Authorization: `Bearer ${localStorage.edu_token}` };
          const [attemptResponse, pathResponse] = await Promise.all([
            fetch(`/api/quizzes/${encodeURIComponent(quizId)}/attempts`, { headers }),
            fetch(`/api/learning-path?sessionId=${encodeURIComponent(sessionId)}&subjectId=${encodeURIComponent(subjectId)}&pathId=${encodeURIComponent(pathId)}`, { headers }),
          ]);
          const attempts = ((await attemptResponse.json()).data?.attempts || []).map((attempt) => ({ score: attempt.totalScore, status: attempt.status }));
          const path = (await pathResponse.json()).data?.path || {};
          const findTask = (value) => {
            if (!value || typeof value !== 'object') return null;
            if (value.id === taskId) return value;
            for (const child of Array.isArray(value) ? value : Object.values(value)) { const found = findTask(child); if (found) return found; }
            return null;
          };
          const task = findTask(path.stages || path);
          return { attempts, completed: ['completed', 'mastered'].includes(task?.status), taskFound: Boolean(task) };
        }, { quizId: second.attempt?.quizId || second.attempt?.quiz_id || '', sessionId: meta.sessionId, subjectId: meta.subjectId, pathId: meta.pathId, taskId: meta.quizTaskId });
        const scores = persisted.attempts.map((attempt) => attempt.score);
        if (persisted.attempts.length < 2 || !scores.includes(40) || Math.max(...scores) !== 100 || !persisted.completed) throw new Error(`QUIZ_PERSISTENCE: ${JSON.stringify(persisted)}`);
        mark('reload-persistence-verified', { attempts: persisted.attempts.length, bestScore: Math.max(...scores), completed: persisted.completed });
      } finally {
        await writeFile(resolve(evidence, 'quiz-timeline.json'), JSON.stringify(timeline, null, 2));
        await writeFile(resolve(evidence, 'quiz-dom-snapshot.html'), await page.locator('[data-testid="quiz-result"], [data-testid^="quiz-question-"]').evaluateAll((nodes) => nodes.map((node) => node.outerHTML).join('\n')));
      }
      if (submitStatuses.length !== 2 || submitStatuses.some((status) => status !== 200)) throw new Error(`QUIZ_SECOND_SUBMIT: ${submitStatuses.join(',')}`);
      await writeFile(resolve(evidence, 'quiz-summary.json'), JSON.stringify({ firstScore: 40, secondScore: 100, submitStatuses }, null, 2));
    } else if (scenario === 'video-fallback') {
      await openTask(page, 3, 'Video');
      await page.getByRole('button', { name: '切换为图文讲解' }).click();
      await page.getByRole('button', { name: '返回视频学习' }).click();
      await page.getByRole('button', { name: '切换为图文讲解' }).click();
    }
    await page.screenshot({ path: resolve(evidence, 'screenshots.png'), fullPage: true });
    await writeFile(resolve(evidence, 'network-summary.json'), JSON.stringify(events.network, null, 2));
    await writeFile(resolve(evidence, 'console-summary.txt'), [...events.console, ...events.pageErrors].join('\n'));
    await writeFile(resolve(evidence, 'summary.json'), JSON.stringify({ scenario, learnerId, authMe: me, scope, status: 'PASS', evidence: relative(root, evidence) }, null, 2));
    await writeFile(resolve(evidence, 'result.md'), `# ${scenario}\n\nPASS\n`);
    console.log(`QA_${scenario.toUpperCase().replace(/-/g, '_')}=PASS`);
  } finally {
    if (context) { await context.tracing.stop({ path: resolve(evidence, 'trace.zip') }).catch(() => {}); await context.close().catch(() => {}); }
    await browser.close();
    started.frontend.kill();
    started.backend.kill();
  }
}

main().catch(async (error) => { await mkdir(evidence, { recursive: true }); await writeFile(resolve(evidence, 'result.md'), `# ${scenario}\n\nFAIL: ${String(error.message || error).replace(/(password|token|cookie|authorization)\S*/gi, '[redacted]')}\n`); console.error(`QA_${scenario.toUpperCase().replace(/-/g, '_')}=FAIL: ${String(error.message || error).replace(/(password|token|cookie|authorization)\S*/gi, '[redacted]')}`); process.exitCode = 1; });
