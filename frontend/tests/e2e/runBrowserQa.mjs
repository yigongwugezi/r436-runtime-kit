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
  await writeFile(resolve(evidence, 'charter.md'), `# Browser QA charter\n\n- Request: explainable adaptive revision v1\n- Goal: verify one failed quiz creates one explainable pending review revision and that accept/reject persist correctly.\n- Mode: SAFE_MUTATION\n- Data: ISOLATED_QA_SANDBOX (${scenario})\n- Permissions: isolated quiz submit and revision decision only; no resource generation or external LLM required.\n- Entry: /path\n- Watched APIs: quiz submit, pending revision, accept/reject, learning path.\n- Expected: one 200 submit, one pending nonzero diff, stable refresh persistence, no duplicate mutation, no console/page/network errors.\n- Evidence: screenshots, trace, network/console summaries, revision summary.\n- Recovery: runner closes only its child processes; sandbox is disposable.\n- PASS: all stated assertions pass. FAIL: product assertion fails. BLOCKED: auth or sandbox cannot start.\n`);
  const events = { console: [], pageErrors: [], network: [], profile: [], reactWarnings: [] };
  const consoleRecordings = [];
  let currentAction = 'initial load';
  const recordConsole = (page, message) => {
    if (message.type() !== 'error' && message.type() !== 'warning') return;
    const recording = (async () => {
      const text = message.text();
      const args = await Promise.all(message.args().map((arg) => arg.jsonValue().catch(() => arg.toString())));
      events.console.push(`${message.type()}: ${text}`);
      if (!/Cannot update a component/.test(text)) return;
      events.reactWarnings.push({ type: message.type(), text, args, atMs: Date.now(), url: page.url(), action: currentAction, location: message.location(), componentStack: args.filter((arg) => typeof arg === 'string' && /LecturePage|at /.test(arg)) });
      if (events.reactWarnings.length === 1) await writeFile(resolve(evidence, 'react-warning-dom.html'), await page.content());
    })();
    consoleRecordings.push(recording);
  };
  const profileStartedAt = new WeakMap();
  const profileRecordings = [];
  const recordProfileRequest = (request) => {
    if (safePath(request.url()) === '/api/profile') profileStartedAt.set(request, Date.now());
  };
  const recordProfileResponse = (response) => {
    if (safePath(response.url()) !== '/api/profile') return;
    const recording = (async () => {
      const request = response.request();
      const finishedAtMs = Date.now();
      const url = new URL(response.url());
      const body = await response.json().catch(() => ({}));
      events.profile.push({ method: request.method(), path: url.pathname, query: [...url.searchParams].map(([name, value]) => ({ name, empty: !value })), status: response.status(), detail: body?.detail || body?.message || null, startedAtMs: profileStartedAt.get(request) ?? finishedAtMs, finishedAtMs, durationMs: finishedAtMs - (profileStartedAt.get(request) ?? finishedAtMs), initiator: 'useProfile -> profileApi.getProfile' });
    })();
    profileRecordings.push(recording);
  };
  const browser = await chromium.launch({ headless: !headed });
  let context;
  try {
    context = await browser.newContext({ baseURL: execution.frontendBaseUrl });
    await context.tracing.start({ screenshots: true, snapshots: true });
    let page = await context.newPage();
    page.on('console', (m) => recordConsole(page, m));
    page.on('pageerror', (e) => events.pageErrors.push(e.message));
    page.on('request', recordProfileRequest);
    page.on('response', (r) => { if (r.status() >= 400) events.network.push({ path: safePath(r.url()), status: r.status() }); });
    page.on('response', recordProfileResponse);
    await page.goto('/login');
    const learnerId = await authenticateQaUser(page, { credentialsPath: resolve(runtime, 'auth-runtime.json'), storageStatePath: storage, expectedLearnerId: meta.learnerId });
    await context.close();
    context = await browser.newContext({ baseURL: execution.frontendBaseUrl, storageState: storage });
    await context.tracing.start({ screenshots: true, snapshots: true });
    page = await context.newPage();
    page.on('console', (m) => recordConsole(page, m));
    page.on('pageerror', (e) => events.pageErrors.push(e.message));
    page.on('request', recordProfileRequest);
    page.on('response', (r) => { if (r.status() >= 400) events.network.push({ path: safePath(r.url()), status: r.status() }); });
    page.on('response', recordProfileResponse);
    await page.goto('/path');
    const me = await page.evaluate(async () => (await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${localStorage.edu_token}` } })).status);
    if (me !== 200) throw new Error(`AUTH_ME_VERIFY: ${me}`);
    const primaryContentStartedAt = Date.now();
    const initialProfile = scenario === 'profile-load' ? page.waitForResponse((response) => safePath(response.url()) === '/api/profile') : null;
    const scope = await bootstrapQaSubject(page, resolve(runtime, 'seed-metadata.json'));
    if (scope.pathId !== meta.pathId) throw new Error('PATH_LOAD: unexpected path');
    await page.waitForFunction((title) => document.body.innerText.includes(title), 'Data Structures');
    if (scenario === 'path-performance') {
      const timings = [];
      for (let i = 0; i < 3; i += 1) { const start = Date.now(); await page.reload(); await page.waitForFunction((title) => document.body.innerText.includes(title), 'Data Structures'); timings.push(Date.now() - start); }
      await writeFile(resolve(evidence, 'performance.json'), JSON.stringify({ pathVisibleMs: timings }, null, 2));
    } else if (scenario === 'profile-load') {
      await initialProfile;
      await Promise.all(profileRecordings);
      const firstPageRequests = [...events.profile];
      await page.screenshot({ path: resolve(evidence, 'profile-load.png'), fullPage: true });
      const refreshedProfile = page.waitForResponse((response) => safePath(response.url()) === '/api/profile');
      await page.reload();
      await Promise.all([refreshedProfile, page.waitForFunction((title) => document.body.innerText.includes(title), 'Data Structures')]);
      await Promise.all(profileRecordings);
      await page.screenshot({ path: resolve(evidence, 'profile-load-refresh.png'), fullPage: true });
      const scopeSummary = { learnerId: meta.learnerId, subjectId: scope.subjectId, sessionId: scope.sessionId, pathId: scope.pathId };
      await writeFile(resolve(evidence, 'profile-summary.json'), JSON.stringify({ scope: scopeSummary, primaryContentMs: Date.now() - primaryContentStartedAt, requestCounts: { initial: firstPageRequests.length, refresh: events.profile.length - firstPageRequests.length }, requests: events.profile }, null, 2));
      await writeFile(resolve(evidence, 'network-summary.json'), JSON.stringify(events.network, null, 2));
      await writeFile(resolve(evidence, 'console-summary.txt'), [...events.console, ...events.pageErrors].join('\n'));
      if (firstPageRequests.length !== 1 || events.profile.length !== 2 || events.profile.some((request) => request.status !== 200 || request.query.some((item) => item.empty) || !request.query.some((item) => item.name === 'sessionId') || !request.query.some((item) => item.name === 'subjectId'))) throw new Error(`PROFILE_SCOPE_ERROR: ${JSON.stringify(events.profile)}`);
    } else if (scenario === 'mindmap') {
      const openedAt = Date.now();
      await openTask(page, 4, 'Mind map');
      const host = page.getByTestId('mindmap-container');
      const svg = page.getByTestId('mindmap-svg');
      await svg.waitFor({ timeout: 15000 });
      await page.waitForFunction(() => document.querySelector('[data-testid="mindmap-svg"]')?.dataset.mindmapReady === 'true');
      const diagnostics = await svg.evaluate((element, start) => {
        const box = element.getBoundingClientRect();
        const content = element.querySelector(':scope > g');
        const contentBox = content?.getBoundingClientRect();
        const nodes = [...element.querySelectorAll('g.markmap-node')].map((node) => {
          const rect = node.getBoundingClientRect();
          return { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) };
        });
        const ys = nodes.map((node) => node.y);
        const overlapCount = nodes.reduce((count, node, index) => count + nodes.slice(index + 1).filter((other) => node.x < other.x + other.width && other.x < node.x + node.width && node.y < other.y + other.height && other.y < node.y + node.height).length, 0);
        return {
          container: { width: Math.round(box.width), height: Math.round(box.height) },
          svg: { width: element.getAttribute('width'), height: element.getAttribute('height'), viewBox: element.getAttribute('viewBox') },
          content: contentBox ? { width: Math.round(contentBox.width), height: Math.round(contentBox.height), transform: content?.getAttribute('transform') || '' } : null,
          nodeCount: nodes.length,
          nodes,
          ySpread: ys.length ? Math.max(...ys) - Math.min(...ys) : 0,
          overlapCount,
          firstVisibleMs: Date.now() - start,
        };
      }, openedAt);
      await page.screenshot({ path: resolve(evidence, 'mindmap-full.png'), fullPage: true });
      await svg.screenshot({ path: resolve(evidence, 'mindmap-region.png') });
      await writeFile(resolve(evidence, 'mindmap-host.html'), await host.evaluate((element) => element.outerHTML));
      await writeFile(resolve(evidence, 'mindmap-svg.svg'), await svg.evaluate((element) => element.outerHTML));
      await writeFile(resolve(evidence, 'mindmap-diagnostics.json'), JSON.stringify(diagnostics, null, 2));
      await writeFile(resolve(evidence, 'console-summary.txt'), [...events.console, ...events.pageErrors].join('\n'));
      await writeFile(resolve(evidence, 'network-summary.json'), JSON.stringify(events.network, null, 2));
      if (diagnostics.container.width < 100 || diagnostics.container.height < 100 || !diagnostics.content || diagnostics.content.width < 100 || diagnostics.content.height < 100 || diagnostics.nodeCount < 2 || diagnostics.ySpread < 20 || diagnostics.overlapCount) throw new Error(`VISUAL_LAYOUT_ERROR: ${JSON.stringify(diagnostics)}`);
      await page.reload();
      await page.waitForFunction(() => document.querySelector('[data-testid="mindmap-svg"]')?.dataset.mindmapReady === 'true');
    } else if (scenario === 'zero-diff') {
      const actions = page.getByRole('button', { name: /确认调整|拒绝调整/ });
      if (await actions.count()) throw new Error('ZERO_DIFF_ACTIONS_VISIBLE');
    } else if (scenario === 'adaptive-revision' || scenario === 'adaptive-revision-reject') {
      const submitPath = `/tasks/${meta.quizTaskId}/quiz/submit`;
      const requests = [];
      page.on('response', (response) => { if (safePath(response.url()).endsWith(submitPath)) requests.push(response.status()); });
      await openTask(page, 2, 'Quiz');
      await page.getByTestId(`quiz-question-${Object.keys(meta.quizAnswers.correct)[0]}`).waitFor({ timeout: 15000 });
      for (const [questionId, option] of Object.entries(meta.quizAnswers.firstRound)) await page.getByTestId(`quiz-option-${questionId}-${option}`).click();
      const submitted = page.waitForResponse((response) => safePath(response.url()).endsWith(submitPath));
      await page.getByTestId('quiz-submit').click();
      if ((await submitted).status() !== 200 || requests.length !== 1) throw new Error(`ADAPTIVE_SUBMIT: ${requests.join(',')}`);
      await page.goto('/path');
      await page.getByTestId('adaptive-revision-card').waitFor({ timeout: 30000 });
      const before = await page.evaluate(async ({ sessionId, subjectId, pathId }) => {
        const headers = { Authorization: `Bearer ${localStorage.edu_token}` };
        const [revision, path] = await Promise.all([
          fetch(`/api/learning-path/${encodeURIComponent(sessionId)}/pending-revision?subjectId=${encodeURIComponent(subjectId)}&pathId=${encodeURIComponent(pathId)}`, { headers }),
          fetch(`/api/learning-path?sessionId=${encodeURIComponent(sessionId)}&subjectId=${encodeURIComponent(subjectId)}&pathId=${encodeURIComponent(pathId)}`, { headers }),
        ]);
        return { revision: await revision.json(), path: await path.json() };
      }, meta);
      const revision = before.revision.data?.pending_revision ?? before.revision.pending_revision;
      const added = revision?.explainability?.addedTasks || [];
      if (!revision || added.length !== 1 || !revision.workflow_trace?.some((item) => item.stage === 'REVISION_PENDING')) throw new Error(`ADAPTIVE_PENDING: ${JSON.stringify(revision)}`);
      await page.screenshot({ path: resolve(evidence, 'adaptive-pending.png'), fullPage: true });
      await writeFile(resolve(evidence, 'adaptive-pending.json'), JSON.stringify({ revision, added }, null, 2));
      const reject = scenario === 'adaptive-revision-reject';
      await page.getByTestId(reject ? 'adaptive-revision-reject' : 'adaptive-revision-accept').click();
      await page.getByTestId('adaptive-revision-status').waitFor();
      await page.reload();
      await page.waitForFunction((title) => document.body.innerText.includes(title), 'Data Structures');
      const after = await page.evaluate(async ({ sessionId, subjectId, pathId }) => {
        const headers = { Authorization: `Bearer ${localStorage.edu_token}` };
        const [revision, path] = await Promise.all([
          fetch(`/api/learning-path/${encodeURIComponent(sessionId)}/pending-revision?subjectId=${encodeURIComponent(subjectId)}&pathId=${encodeURIComponent(pathId)}`, { headers }),
          fetch(`/api/learning-path?sessionId=${encodeURIComponent(sessionId)}&subjectId=${encodeURIComponent(subjectId)}&pathId=${encodeURIComponent(pathId)}`, { headers }),
        ]);
        return { revision: await revision.json(), path: await path.json() };
      }, meta);
      const stages = (after.path.data?.path ?? after.path.path)?.stages || [];
      const count = stages.reduce((total, stage) => total + (stage.days?.length
        ? stage.days.flatMap((day) => day.tasks || [])
        : stage.tasks || []).filter((task) => task?.task_id === added[0].task_id).length, 0);
      const pending = after.revision.data?.pending_revision ?? after.revision.pending_revision;
      if (pending || count !== (reject ? 0 : 1)) throw new Error(`ADAPTIVE_PERSISTENCE: ${JSON.stringify({ reject, count, pending })}`);
      await page.screenshot({ path: resolve(evidence, 'adaptive-after-decision.png'), fullPage: true });
      await writeFile(resolve(evidence, 'adaptive-summary.json'), JSON.stringify({ reject, requestStatuses: requests, revisionId: revision.revision_id, addedTaskId: added[0].task_id, count, pending }, null, 2));
    } else if (scenario === 'quiz-retake') {
      currentAction = 'open quiz task';
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
      const answer = async (fixture, action) => { currentAction = action; for (const [questionId, option] of Object.entries(fixture)) await page.getByTestId(`quiz-option-${questionId}-${option}`).click(); };
      let navigated = false;
      page.on('framenavigated', (frame) => { if (frame === page.mainFrame()) navigated = true; });
      const submitAndRecord = async (round) => {
        const responsePromise = page.waitForResponse((response) => safePath(response.url()).endsWith(submitPath));
        currentAction = `${round} submit`;
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
      await answer(meta.quizAnswers.firstRound, 'answer first quiz round');
      await submitAndRecord('first');
      await page.waitForFunction(() => document.querySelector('[data-testid="quiz-score"]')?.textContent?.trim() === '40');
      mark('first-score-visible');
      if (submitStatuses.length !== 1 || submitStatuses[0] !== 200) throw new Error(`QUIZ_FIRST_SUBMIT: ${submitStatuses.join(',')}`);
      currentAction = 'retake quiz';
      await page.getByTestId('quiz-retake').click();
      await answer(meta.quizAnswers.correct, 'answer second quiz round');
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
      const timeline = [];
      const deliveryPath = `/api/learning-path/tasks/${meta.videoTaskId}/delivery-mode`;
      const completionPath = `/api/learning-path/tasks/${meta.videoTaskId}/complete`;
      const fallbackPath = `/api/learning-path/tasks/${meta.videoTaskId}/video-fallback/state`;
      const mark = (event, extra = {}) => timeline.push({ atMs: Date.now(), event, ...extra });
      const mutations = [];
      page.on('request', (request) => {
        const path = safePath(request.url());
        if (path === deliveryPath || path === completionPath) mark('mutation-request', { path });
      });
      page.on('response', (response) => {
        const path = safePath(response.url());
        if (path === deliveryPath || path === completionPath) { mutations.push({ path, status: response.status() }); mark('mutation-response', { path, status: response.status() }); }
      });
      const readFallback = () => page.evaluate(async ({ path, scope }) => {
        const query = new URLSearchParams(Object.entries(scope).map(([key, value]) => [key, String(value)]));
        const response = await fetch(`${path}?${query}`, { headers: { Authorization: `Bearer ${localStorage.edu_token}` } });
        return { status: response.status, body: await response.json() };
      }, { path: fallbackPath, scope: { sessionId: meta.sessionId, subjectId: meta.subjectId, pathId: meta.pathId, ...meta.videoScope } });
      const readTask = () => page.evaluate(async ({ sessionId, subjectId, pathId, taskId }) => {
        const response = await fetch(`/api/learning-path?sessionId=${encodeURIComponent(sessionId)}&subjectId=${encodeURIComponent(subjectId)}&pathId=${encodeURIComponent(pathId)}`, { headers: { Authorization: `Bearer ${localStorage.edu_token}` } });
        const body = await response.json();
        const find = (value) => {
          if (!value || typeof value !== 'object') return null;
          if (value.id === taskId) return value;
          for (const child of Array.isArray(value) ? value : Object.values(value)) { const found = find(child); if (found) return found; }
          return null;
        };
        const task = find((body.data?.path ?? body.path)?.stages || body.data?.path || body.path);
        return { status: response.status, taskStatus: task?.status || null };
      }, { sessionId: meta.sessionId, subjectId: meta.subjectId, pathId: meta.pathId, taskId: meta.videoTaskId });
      const setMode = async (buttonName, expectedButton) => {
        const responsePromise = page.waitForResponse((response) => safePath(response.url()) === deliveryPath, { timeout: 15000 });
        await page.getByRole('button', { name: buttonName }).click();
        const response = await responsePromise;
        if (response.status() !== 200) throw new Error(`VIDEO_DELIVERY_MODE: ${response.status()}`);
        await page.getByRole('button', { name: expectedButton }).waitFor({ timeout: 15000 });
      };
      await openTask(page, 3, 'Video');
      const initialTask = await readTask();
      if (initialTask.status !== 200 || initialTask.taskStatus === 'completed') throw new Error(`VIDEO_RESET_STATE: ${JSON.stringify(initialTask)}`);
      await setMode('切换为图文讲解', '返回视频学习');
      const firstFallback = await readFallback();
      await setMode('返回视频学习', '切换为图文讲解');
      await setMode('切换为图文讲解', '返回视频学习');
      const secondFallback = await readFallback();
      const complete = page.locator('button[data-testid="task-complete"]:visible');
      const completionReady = await page.waitForFunction(() => [...document.querySelectorAll('[data-testid="task-complete"]')].some((button) => !button.disabled && !!button.getBoundingClientRect().width && !!button.getBoundingClientRect().height), { timeout: 10000 }).then(() => true, () => false);
      const buttonStates = await page.getByTestId('task-complete').evaluateAll((buttons) => buttons.map((button) => { const box = button.getBoundingClientRect(); return { text: button.textContent?.trim(), disabled: button.disabled, ariaDisabled: button.getAttribute('aria-disabled'), visible: box.width > 0 && box.height > 0, box: { x: box.x, y: box.y, width: box.width, height: box.height } }; }));
      await page.screenshot({ path: resolve(evidence, 'video-before-click.png'), fullPage: true });
      await writeFile(resolve(evidence, 'video-before-click.html'), await page.content());
      await writeFile(resolve(evidence, 'video-preclick-diagnostics.json'), JSON.stringify({ firstFallback, secondFallback, buttonStates }, null, 2));
      if (!completionReady) throw new Error(`VIDEO_COMPLETE_UNREADY: ${JSON.stringify(buttonStates)}`);
      if (await complete.count() !== 1) throw new Error(`VIDEO_COMPLETE_LOCATOR_COUNT: ${await complete.count()}`);
      const button = await complete.evaluate((element) => { const box = element.getBoundingClientRect(); return { text: element.textContent?.trim(), role: element.getAttribute('role') || 'button', testId: element.getAttribute('data-testid'), disabled: element.disabled, ariaDisabled: element.getAttribute('aria-disabled'), visible: box.width > 0 && box.height > 0, box: { x: box.x, y: box.y, width: box.width, height: box.height } }; });
      if (button.disabled || !button.visible) throw new Error(`VIDEO_COMPLETE_BUTTON: ${JSON.stringify(button)}`);
      mark('completion-button-ready', button);
      const completionResponse = page.waitForResponse((response) => safePath(response.url()) === completionPath, { timeout: 5000 }).catch(() => null);
      await complete.click();
      mark('completion-click-returned');
      await page.screenshot({ path: resolve(evidence, 'video-after-click.png'), fullPage: true });
      await page.waitForTimeout(1000);
      await page.screenshot({ path: resolve(evidence, 'video-after-1s.png'), fullPage: true });
      const completion = await completionResponse;
      await page.waitForTimeout(4000);
      await page.screenshot({ path: resolve(evidence, 'video-after-5s.png'), fullPage: true });
      await writeFile(resolve(evidence, 'video-after-click.html'), await page.content());
      if (!completion || completion.status() !== 200) throw new Error(`VIDEO_COMPLETION: ${completion?.status() || 'missing'}`);
      await page.waitForURL(/\/path/, { timeout: 5000 });
      await page.waitForFunction((title) => document.body.innerText.includes(title), 'Data Structures');
      await page.reload();
      await page.waitForFunction((title) => document.body.innerText.includes(title), 'Data Structures');
      const persistedTask = await readTask();
      const persistedFallback = await readFallback();
      const resourceId = (state) => state?.body?.data?.lecture?.id || state?.body?.lecture?.id || null;
      const deliveryMutations = mutations.filter((item) => item.path === deliveryPath);
      const completionMutations = mutations.filter((item) => item.path === completionPath);
      const persistedMode = persistedFallback.body?.data?.activeDeliveryMode || persistedFallback.body?.activeDeliveryMode;
      if (deliveryMutations.length !== 3 || deliveryMutations.some((item) => item.status !== 200) || completionMutations.length !== 1 || completionMutations[0].status !== 200 || !resourceId(firstFallback) || resourceId(firstFallback) !== resourceId(secondFallback) || persistedTask.taskStatus !== 'completed' || persistedMode !== 'video_fallback_lecture') throw new Error(`VIDEO_PERSISTENCE: ${JSON.stringify({ deliveryMutations, completionMutations, firstResource: resourceId(firstFallback), secondResource: resourceId(secondFallback), persistedTask, persistedMode })}`);
      mark('reload-persistence-verified', { task: persistedTask, mode: persistedMode });
      await writeFile(resolve(evidence, 'video-timeline.json'), JSON.stringify(timeline, null, 2));
      await writeFile(resolve(evidence, 'video-summary.json'), JSON.stringify({ initialTask, button, deliveryMutations, completionMutations, fallbackResourceId: resourceId(secondFallback), persistedTask, persistedMode }, null, 2));
    }
    await Promise.all(consoleRecordings);
    await page.screenshot({ path: resolve(evidence, 'screenshots.png'), fullPage: true });
    await writeFile(resolve(evidence, 'network-summary.json'), JSON.stringify(events.network, null, 2));
    await writeFile(resolve(evidence, 'console-summary.txt'), [...events.console, ...events.pageErrors].join('\n'));
    await writeFile(resolve(evidence, 'react-warning-summary.json'), JSON.stringify(events.reactWarnings, null, 2));
    if (scenario === 'quiz-retake' && events.reactWarnings.length) throw new Error(`REACT_RENDER_WARNING: ${events.reactWarnings.length}`);
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
