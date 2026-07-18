import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const frontendDir = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const repoDir = resolve(frontendDir, '..');
const backendPort = 8010;
const frontendPort = 5175;
const debugPort = 9222;
const edgePath = process.env.EDGE_PATH || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function start(command, args, options) { return spawn(command, args, { ...options, stdio: 'ignore', windowsHide: true }); }
async function stop(child) { if (child?.exitCode === null && !child.killed) { child.kill(); await Promise.race([new Promise((resolve) => child.once('exit', resolve)), sleep(5000)]); } }
async function waitFor(url, label) { for (const deadline = Date.now() + 30000; Date.now() < deadline; await sleep(100)) try { if ((await fetch(url)).ok) return; } catch {} throw new Error(`${label} did not start`); }
async function waitForBrowser(cdp, expression, label) { for (const deadline = Date.now() + 15000; Date.now() < deadline; await sleep(100)) if (await cdp.evaluate(expression)) return; throw new Error(`${label} did not render`); }
async function waitForCondition(check, label, timeout = 15000) { for (const deadline = Date.now() + timeout; Date.now() < deadline; await sleep(100)) if (await check()) return; throw new Error(`${label} did not complete`); }

class Cdp {
  constructor(socket) { this.socket = socket; this.nextId = 1; this.pending = new Map(); this.events = []; socket.addEventListener('message', ({ data }) => { const message = JSON.parse(data); if (message.id) this.pending.get(message.id)?.(message); else this.events.push(message); }); }
  call(method, params = {}) { const id = this.nextId++; return new Promise((resolve, reject) => { this.pending.set(id, (message) => { this.pending.delete(id); message.error ? reject(new Error(message.error.message)) : resolve(message.result); }); this.socket.send(JSON.stringify({ id, method, params })); }); }
  async evaluate(expression) { const result = await this.call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text); return result.result.value; }
}

async function connect(port, expectedUrl = '') {
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = pages.find((entry) => entry.type === 'page' && (!expectedUrl || entry.url.includes(expectedUrl)));
  assert.ok(page, 'expected Edge page');
  const socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }); });
  const cdp = new Cdp(socket); await cdp.call('Runtime.enable'); await cdp.call('Network.enable'); await cdp.call('Page.enable');
  return { cdp, socket };
}

async function setText(cdp, selector, value) {
  await cdp.evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`);
  await cdp.call('Input.dispatchKeyEvent', { type: 'keyDown', modifiers: 2, windowsVirtualKeyCode: 65, code: 'KeyA', key: 'a' });
  await cdp.call('Input.dispatchKeyEvent', { type: 'keyUp', modifiers: 2, windowsVirtualKeyCode: 65, code: 'KeyA', key: 'a' });
  await cdp.call('Input.insertText', { text: value });
}

async function login(cdp) {
  await waitForBrowser(cdp, "Boolean(document.querySelector('form'))", 'login form');
  await setText(cdp, "input[type='text']", '13900000009');
  await setText(cdp, "input[type='password']", 'e2e-only');
  await cdp.evaluate("document.querySelector('form').requestSubmit()");
  await waitForBrowser(cdp, "location.pathname === '/'", 'authenticated home');
}

function batchResponses(cdp) {
  const posts = new Set(cdp.events.filter((event) => event.method === 'Network.requestWillBeSent'
    && event.params.request.url.includes('/api/workflows/general_resource_generation/batch/start')
    && event.params.request.method === 'POST').map((event) => event.params.requestId));
  return cdp.events.filter((event) => event.method === 'Network.responseReceived' && posts.has(event.params.requestId));
}

async function responseBody(cdp, event) {
  const body = await cdp.call('Network.getResponseBody', { requestId: event.params.requestId });
  return JSON.parse(body.body);
}

async function authenticatedApi(cdp, apiBase, token, path, { method = 'GET', params, body } = {}) {
  const url = new URL(path, apiBase);
  for (const [key, value] of Object.entries(params || {})) if (value) url.searchParams.set(key, value);
  const result = await cdp.evaluate(`fetch(${JSON.stringify(url.toString())}, {
    method: ${JSON.stringify(method)}, headers: { Authorization: 'Bearer ' + ${JSON.stringify(token)}, 'Content-Type': 'application/json' },
    body: ${body === undefined ? 'undefined' : JSON.stringify(JSON.stringify(body))}
  }).then(async (response) => ({ ok: response.ok, status: response.status, body: await response.json() }))`);
  assert.ok(result.ok, `${method} ${path} failed with ${result.status}: ${JSON.stringify(result.body)}`);
  return result.body;
}

test('real Edge generates typed resources through recoverable workflows without duplicate children', { timeout: 120000 }, async () => {
  const tempDir = await mkdtemp(join(tmpdir(), 'eduagent-general-resource-e2e-'));
  let backend; let frontend; let edge; let socket; let secondSocket; let cdp;
  try {
    backend = start('python', ['backend/tests/browser_fake_server.py'], { cwd: repoDir, env: { ...process.env, PYTHONPATH: 'backend', EDUAGENT_SKIP_ENV_FILE: '1', LLM_PROVIDER: 'mock', DATABASE_URL: `sqlite:///${join(tempDir, 'browser.db')}`, PORT: String(backendPort), EDUAGENT_GENERAL_RESOURCE_DELAY_MS: '3000' } });
    await waitFor(`http://127.0.0.1:${backendPort}/api/health`, 'isolated backend');
    const registration = await fetch(`http://127.0.0.1:${backendPort}/api/auth/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone: '13900000009', password: 'e2e-only', nickname: 'fixture', role: 'student' }) });
    assert.equal(registration.ok, true);
    const identity = await registration.json();
    const apiBase = `http://127.0.0.1:${backendPort}/api/`;
    const subjectResponse = await fetch(`${apiBase}subjects`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${identity.access_token}` },
      body: JSON.stringify({ name: '资源生成测试科目' }),
    });
    assert.equal(subjectResponse.ok, true);
    const subjectPayload = await subjectResponse.json();
    const subject = subjectPayload.data?.subject || subjectPayload.subject;
    assert.ok(subject?.id);
    frontend = start(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort'], { cwd: frontendDir, env: { ...process.env, VITE_API_BASE_URL: `http://127.0.0.1:${backendPort}` } });
    await waitFor(`http://127.0.0.1:${frontendPort}/login`, 'isolated frontend');
    edge = start(edgePath, ['--headless=new', `--remote-debugging-port=${debugPort}`, '--remote-allow-origins=*', `--user-data-dir=${join(tempDir, 'edge')}`, '--no-first-run', `http://127.0.0.1:${frontendPort}/login`], { cwd: repoDir, env: process.env });
    await waitFor(`http://127.0.0.1:${debugPort}/json/list`, 'Edge');
    ({ cdp, socket } = await connect(debugPort, `:${frontendPort}/login`));
    await login(cdp);
    let sessionId = 'general-resource-session';
    const sessionResponse = await fetch(`http://127.0.0.1:${backendPort}/api/chat/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${identity.access_token}` },
      body: JSON.stringify({ sessionId, subjectId: subject.id }),
    });
    assert.equal(sessionResponse.ok, true);
    await cdp.evaluate(`localStorage.setItem(${JSON.stringify(`r436_runtime_active_subject_${identity.learner.id}`)}, ${JSON.stringify(JSON.stringify(subject))}); localStorage.setItem(${JSON.stringify(`r436_runtime_subjects_${identity.learner.id}`)}, ${JSON.stringify(JSON.stringify([subject]))}); localStorage.setItem(${JSON.stringify(`r436_runtime_session_${identity.learner.id}_${subject.id}`)}, ${JSON.stringify(sessionId)})`);
    await cdp.evaluate("location.assign('/generate')").catch(() => undefined);
    await waitForBrowser(cdp, "Boolean(document.querySelector('textarea'))", 'generation page');
    const capabilityStatus = await cdp.evaluate(`fetch('http://127.0.0.1:${backendPort}/api/health/capabilities').then((response) => response.status).catch((error) => String(error))`);
    assert.equal(capabilityStatus, 200);
    await setText(cdp, 'textarea', 'CNN 基础结构');
    assert.match(await cdp.evaluate("document.querySelector('textarea').value"), /CNN/);
    assert.match(await cdp.evaluate('location.search'), /q=/);
    await setText(cdp, 'textarea', '递归调用栈');
    await waitForBrowser(cdp, "document.body.innerText.includes('5/500')", 'prompt counter');
    assert.equal(await cdp.evaluate("document.body.innerText.includes('5/500')"), true);
    assert.equal(await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.includes('开始生成')).disabled"), false, await cdp.evaluate('document.body.innerText'));
    cdp.events.length = 0;
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.includes('开始生成')).click()");
    await sleep(1000);
    assert.ok(cdp.events.some((event) => event.method === 'Network.requestWillBeSent' && event.params.request.method === 'POST'), await cdp.evaluate('document.body.innerText'));
    await waitForCondition(() => batchResponses(cdp).length === 1, 'first batch request');
    assert.equal(batchResponses(cdp).length, 1, 'one UI batch click must make one batch request');
    const initial = await responseBody(cdp, batchResponses(cdp)[0]);
    assert.deepEqual(initial.tasks.map((task) => task.resource_type).sort(), ['lecture', 'mindmap', 'quiz']);
    sessionId = JSON.parse(cdp.events.find((event) => event.method === 'Network.requestWillBeSent' && event.params.request.url.includes('/batch/start')).params.request.postData).sessionId;
    assert.ok(sessionId);
    await cdp.call('Page.reload');
    await waitForBrowser(cdp, "Boolean(document.querySelector('textarea'))", 'reloaded generation page');
    await waitForCondition(async () => (await authenticatedApi(cdp, apiBase, identity.access_token, 'resources', { params: { sessionId, subjectId: subject.id } })).data?.total === 3, 'recovered generated resources', 30000);
    assert.equal(batchResponses(cdp).length, 1, 'refresh must reconnect, never create a second batch');
    const resources = await authenticatedApi(cdp, apiBase, identity.access_token, 'resources', { params: { sessionId, subjectId: subject.id } });
    assert.equal(resources.data.total, 3);
    assert.deepEqual(resources.data.resources.map((resource) => resource.type).sort(), ['lecture', 'mindmap', 'quiz']);
    assert.equal(new Set(resources.data.resources.map((resource) => resource.id)).size, 3);
    const quiz = resources.data.resources.find((resource) => resource.type === 'quiz');
    assert.ok(quiz.questions?.length && quiz.questions.every((question) => question.answer && question.explanation));
    const detail = await authenticatedApi(cdp, apiBase, identity.access_token, `resources/${quiz.id}`, { params: { sessionId, subjectId: subject.id } });
    assert.equal(detail.data.resource.id, quiz.id);
    assert.equal(detail.data.resource.type, 'quiz');
    assert.ok(String(detail.data.resource.content || '').trim());
    const deletion = await authenticatedApi(cdp, apiBase, identity.access_token, `resources/${quiz.id}`, { method: 'DELETE', params: { sessionId, subjectId: subject.id } });
    assert.equal(deletion.data.deleted, true);
    const remaining = await authenticatedApi(cdp, apiBase, identity.access_token, 'resources', { params: { sessionId, subjectId: subject.id } });
    assert.equal(remaining.data.resources.some((resource) => resource.id === quiz.id), false);
  } finally {
    secondSocket?.close(); socket?.close(); await stop(edge); await stop(frontend); await stop(backend); await rm(tempDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
  }
});
