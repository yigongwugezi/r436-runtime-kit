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
      page.on('response', (response) => { if (safePath(response.url()).endsWith(`/tasks/${meta.quizTaskId}/quiz/submit`)) submitStatuses.push(response.status()); });
      const answer = async (fixture) => { for (const [questionId, option] of Object.entries(fixture)) await page.getByTestId(`quiz-option-${questionId}-${option}`).click(); };
      await page.getByTestId(`quiz-question-${Object.keys(meta.quizAnswers.correct)[0]}`).waitFor({ timeout: 15000 });
      await answer(meta.quizAnswers.firstRound);
      await page.getByTestId('quiz-submit').click();
      await page.waitForFunction(() => document.querySelector('[data-testid="quiz-score"]')?.textContent?.trim() === '40');
      if (submitStatuses.length !== 1 || submitStatuses[0] !== 200) throw new Error(`QUIZ_FIRST_SUBMIT: ${submitStatuses.join(',')}`);
      await page.getByTestId('quiz-retake').click();
      await answer(meta.quizAnswers.correct);
      await page.getByTestId('quiz-submit').click();
      await page.waitForFunction(() => document.querySelector('[data-testid="quiz-score"]')?.textContent?.trim() === '100');
      if (submitStatuses.length !== 2 || submitStatuses.some((status) => status !== 200)) throw new Error(`QUIZ_SECOND_SUBMIT: ${submitStatuses.join(',')}`);
      await page.reload();
      await page.waitForFunction(() => document.querySelector('[data-testid="quiz-score"]')?.textContent?.trim() === '100');
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
