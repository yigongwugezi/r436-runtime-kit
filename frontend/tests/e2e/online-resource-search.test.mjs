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
async function waitFor(url, label) { for (const deadline = Date.now() + 30_000; Date.now() < deadline; await sleep(100)) try { if ((await fetch(url)).ok) return; } catch {} throw new Error(`${label} did not start`); }
async function waitForBrowser(cdp, expression, label) { for (const deadline = Date.now() + 20_000; Date.now() < deadline; await sleep(100)) if (await cdp.evaluate(expression)) return; throw new Error(`${label} did not render`); }
async function waitForCondition(check, label, timeout = 15000) { for (const deadline = Date.now() + timeout; Date.now() < deadline; await sleep(100)) if (await check()) return; throw new Error(`${label} did not complete`); }

class Cdp {
  constructor(socket) { this.socket = socket; this.nextId = 1; this.pending = new Map(); this.events = []; socket.addEventListener('message', ({ data }) => { const message = JSON.parse(data); if (message.id) this.pending.get(message.id)?.(message); else this.events.push(message); }); }
  call(method, params = {}) { const id = this.nextId++; return new Promise((resolve, reject) => { this.pending.set(id, (message) => { this.pending.delete(id); message.error ? reject(new Error(message.error.message)) : resolve(message.result); }); this.socket.send(JSON.stringify({ id, method, params })); }); }
  async evaluate(expression) { const result = await this.call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text); return result.result.value; }
}

async function connect(port, expectedUrl) {
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = pages.find((entry) => entry.type === 'page' && entry.url.startsWith(`http://127.0.0.1:${frontendPort}/`) && entry.url.includes(expectedUrl));
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

function workflowStarts(cdp) {
  const requests = cdp.events.filter((event) => event.method === 'Network.requestWillBeSent' && event.params.request.url.includes('/api/workflows/resource_search/start') && event.params.request.method === 'POST');
  const ids = new Set(requests.map((event) => event.params.requestId));
  return cdp.events.filter((event) => event.method === 'Network.responseReceived' && ids.has(event.params.requestId));
}
function chatSessionStarts(cdp) {
  const requests = cdp.events.filter((event) => event.method === 'Network.requestWillBeSent' && event.params.request.url.includes('/api/chat/sessions') && event.params.request.method === 'POST');
  const ids = new Set(requests.map((event) => event.params.requestId));
  return cdp.events.filter((event) => event.method === 'Network.responseReceived' && ids.has(event.params.requestId));
}
async function responseBody(cdp, event) { return JSON.parse((await cdp.call('Network.getResponseBody', { requestId: event.params.requestId })).body); }
function requestBody(cdp, event) { return JSON.parse(cdp.events.find((item) => item.method === 'Network.requestWillBeSent' && item.params.requestId === event.params.requestId).params.request.postData); }
async function browserApi(cdp, url, token, method = 'GET', body) {
  return cdp.evaluate(`fetch(${JSON.stringify(url)}, { method: ${JSON.stringify(method)}, headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + ${JSON.stringify(token)} }, ${body === undefined ? '' : `body: ${JSON.stringify(JSON.stringify(body))},`} }).then(async (response) => ({ ok: response.ok, status: response.status, body: await response.json() }))`);
}

test('real Edge separates local resources from recoverable online search', { timeout: 120000 }, async () => {
  const tempDir = await mkdtemp(join(tmpdir(), 'eduagent-online-search-e2e-'));
  let backend; let frontend; let edge; let socket; let secondSocket;
  try {
    backend = start('python', ['backend/tests/browser_fake_server.py'], { cwd: repoDir, env: { ...process.env, PYTHONPATH: 'backend', EDUAGENT_SKIP_ENV_FILE: '1', LLM_PROVIDER: 'mock', DATABASE_URL: `sqlite:///${join(tempDir, 'browser.db')}`, PORT: String(backendPort), EDUAGENT_RESOURCE_SEARCH_DELAY_MS: '5000' } });
    await waitFor(`http://127.0.0.1:${backendPort}/api/health`, 'isolated backend');
    const registered = await fetch(`http://127.0.0.1:${backendPort}/api/auth/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone: '13900000011', password: 'e2e-only', nickname: 'search-fixture', role: 'student' }) });
    assert.equal(registered.ok, true);
    const { access_token: token } = await registered.json();
    frontend = start(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort'], { cwd: frontendDir, env: { ...process.env, VITE_API_BASE_URL: `http://127.0.0.1:${backendPort}` } });
    await waitFor(`http://127.0.0.1:${frontendPort}/login`, 'isolated frontend');
    edge = start(edgePath, ['--headless=new', `--remote-debugging-port=${debugPort}`, '--remote-allow-origins=*', `--user-data-dir=${join(tempDir, 'edge')}`, '--no-first-run', `http://127.0.0.1:${frontendPort}/login`], { cwd: repoDir, env: process.env });
    await waitFor(`http://127.0.0.1:${debugPort}/json/list`, 'Edge');
    const connected = await connect(debugPort, '/login'); const cdp = connected.cdp; socket = connected.socket;
    await waitForBrowser(cdp, `location.origin === 'http://127.0.0.1:${frontendPort}'`, 'login origin');
    await cdp.evaluate(`localStorage.setItem('edu_token', ${JSON.stringify(token)}); location.assign('/chat')`);
    await waitForBrowser(cdp, "Boolean(document.querySelector('textarea'))", 'chat page');
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.includes('新对话')).click()");
    await waitForCondition(() => chatSessionStarts(cdp).length === 1, 'new chat session');
    await cdp.evaluate(`location.assign(${JSON.stringify(`/resources?mode=online&query=${encodeURIComponent('递归调用栈')}`)})`);
    await waitForBrowser(cdp, "Boolean(document.querySelector(\"input[placeholder='例如：递归调用栈']\"))", 'online resource page');
    assert.equal(await cdp.evaluate("document.querySelector(\"input[placeholder='例如：递归调用栈']\").value"), '递归调用栈');
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.trim() === '联网搜索').click()");
    await waitForCondition(() => workflowStarts(cdp).length === 1, 'online search workflow start');
    assert.equal(workflowStarts(cdp).length, 1, 'online search creates one workflow task');
    const started = await responseBody(cdp, workflowStarts(cdp)[0]);
    const startPayload = requestBody(cdp, workflowStarts(cdp)[0]);
    assert.equal(started.workflow_type, 'resource_search');
    assert.equal(startPayload.query, '递归调用栈');
    const sessionId = startPayload.sessionId;
    assert.ok(sessionId);
    await cdp.call('Page.reload');
    await waitForBrowser(cdp, "Boolean(document.querySelector(\"input[placeholder='例如：递归调用栈']\"))", 'reloaded online resource page');
    await waitForCondition(async () => (await browserApi(cdp, `http://127.0.0.1:${backendPort}/api/workflows/${started.task_id}?sessionId=${encodeURIComponent(sessionId)}`, token)).body.status === 'completed', 'recovered search workflow');
    const finished = await browserApi(cdp, `http://127.0.0.1:${backendPort}/api/workflows/${started.task_id}?sessionId=${encodeURIComponent(sessionId)}`, token);
    assert.equal(finished.body.status, 'completed');
    assert.equal(finished.body.result.data.recommendations.resources.length, 5);
    await waitForBrowser(cdp, "document.body.innerText.includes('找到 5 条公开资源')", 'recovered search results');
    assert.equal(workflowStarts(cdp).length, 1, 'refresh reconnects instead of creating a second task');
    for (const label of ['文章', '视频', '课程', '文档', '论文']) assert.equal(await cdp.evaluate(`document.body.innerText.includes(${JSON.stringify(label)})`), true);
    assert.equal(await cdp.evaluate("[...document.querySelectorAll(\"a[target='_blank']\")].every((link) => !link.href.includes('example.com'))"), true, 'fixture must not surface mock URLs');

    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.trim() === '视频').click()");
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.trim() === '保存').click()");
    await waitForCondition(async () => (await browserApi(cdp, `http://127.0.0.1:${backendPort}/api/resources?sessionId=${encodeURIComponent(sessionId)}`, token)).body.data.resources.filter((item) => ['article', 'video'].includes(item.type)).length === 1, 'video save');
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.trim() === '文章').click()");
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.trim() === '保存').click()");
    await waitForCondition(async () => (await browserApi(cdp, `http://127.0.0.1:${backendPort}/api/resources?sessionId=${encodeURIComponent(sessionId)}`, token)).body.data.resources.filter((item) => ['article', 'video'].includes(item.type)).length === 2, 'article save');
    const resources = await browserApi(cdp, `http://127.0.0.1:${backendPort}/api/resources?sessionId=${encodeURIComponent(sessionId)}`, token);
    assert.equal(resources.ok, true);
    assert.equal(resources.body.data.resources.filter((item) => ['article', 'video'].includes(item.type)).length, 2);
    const duplicate = await browserApi(cdp, `http://127.0.0.1:${backendPort}/api/resources/search-results/save`, token, 'POST', { sessionId, query: '递归调用栈', resource: { title: '递归调用栈教学视频', url: 'https://www.bilibili.com/video/BV1fixture', resource_type: 'video', snippet: '递归调用栈和栈帧', reason: 'fixture', quality_status: 'passed' } });
    assert.equal(duplicate.ok, true); assert.equal(duplicate.body.data.reused, true);
    await cdp.call('Page.reload');
    await waitForBrowser(cdp, "document.body.innerText.includes('搜索我的资源')", 'reloaded resource library');
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.trim() === '搜索我的资源').click()");
    await waitForBrowser(cdp, "document.body.innerText.includes('递归调用栈教学视频')", 'saved resource library item');

    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.includes('联网搜索学习资源')).click()");
    await waitForBrowser(cdp, "Boolean(document.querySelector(\"input[placeholder='例如：递归调用栈']\"))", 'online search form');
    await setText(cdp, "input[placeholder='例如：递归调用栈']", '递归调用栈、');
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.trim() === '联网搜索').click()");
    await waitForCondition(() => workflowStarts(cdp).length >= 2, 'cancellable search workflow start');
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.trim() === '取消').click()");
    await waitForBrowser(cdp, "document.body.innerText.includes('任务已取消')", 'cancelled search task');
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.includes('重试')).click()");
    await waitForBrowser(cdp, "document.body.innerText.includes('找到 5 条公开资源')", 'retried search task');

    await setText(cdp, "input[placeholder='例如：递归调用栈']", '联网故障');
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.trim() === '联网搜索').click()");
    await waitForBrowser(cdp, "document.body.innerText.includes('外部搜索暂不可用')", 'search unavailable state');

    await setText(cdp, "input[placeholder='例如：递归调用栈']", '递归调用栈示例');
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.trim() === '联网搜索').click()");
    await waitForCondition(() => workflowStarts(cdp).length >= 4, 'active duplicate-search workflow');
    const firstActive = await responseBody(cdp, workflowStarts(cdp).at(-1));
    const firstActivePayload = requestBody(cdp, workflowStarts(cdp).at(-1));
    const target = await cdp.call('Target.createTarget', { url: `http://127.0.0.1:${frontendPort}/resources?mode=online&query=${encodeURIComponent('递归调用栈示例')}` });
    await waitForCondition(async () => (await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()).some((page) => page.id === target.targetId), 'second browser target', 10000);
    const pages = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json(); const second = pages.find((page) => page.id === target.targetId);
    secondSocket = new WebSocket(second.webSocketDebuggerUrl); await new Promise((resolve, reject) => { secondSocket.addEventListener('open', resolve, { once: true }); secondSocket.addEventListener('error', reject, { once: true }); });
    const secondCdp = new Cdp(secondSocket); await secondCdp.call('Runtime.enable'); await secondCdp.call('Network.enable');
    await waitForBrowser(secondCdp, "Boolean(document.querySelector(\"input[placeholder='例如：递归调用栈']\"))", 'second online resource page');
    await secondCdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.trim() === '联网搜索').click()");
    await waitForCondition(() => workflowStarts(secondCdp).length === 1, 'second tab workflow start');
    const secondActive = await responseBody(secondCdp, workflowStarts(secondCdp)[0]);
    const secondActivePayload = requestBody(secondCdp, workflowStarts(secondCdp)[0]);
    assert.equal(secondActivePayload.sessionId, firstActivePayload.sessionId, 'same browser profile must keep the same session scope');
    assert.equal(secondActive.task_id, firstActive.task_id, 'two tabs with same topic/context reuse one runner');
    assert.equal(secondActive.reused_existing, true);
  } finally {
    secondSocket?.close(); socket?.close(); await stop(edge); await stop(frontend); await stop(backend); await rm(tempDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
  }
});
