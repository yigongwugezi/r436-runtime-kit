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
const edgePath = process.env.EDGE_PATH || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function browserApi(cdp, url, token, method = 'GET', body) {
  return cdp.evaluate(`fetch(${JSON.stringify(url)}, {
    method: ${JSON.stringify(method)},
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + ${JSON.stringify(token)} },
    ${body === undefined ? '' : `body: ${JSON.stringify(JSON.stringify(body))},`}
  }).then(async (response) => ({ ok: response.ok, status: response.status, body: await response.json() }))`);
}

async function waitFor(url, label) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return response;
    } catch { /* service is still starting */ }
    await sleep(200);
  }
  throw new Error(`${label} did not start`);
}

async function waitForBrowser(cdp, expression, label) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (await cdp.evaluate(expression)) return;
    await sleep(100);
  }
  throw new Error(`${label} did not render`);
}

function start(command, args, options) {
  const child = spawn(command, args, { ...options, stdio: 'ignore', windowsHide: true });
  child.once('error', (error) => { throw error; });
  return child;
}

async function stop(child) {
  if (!child || child.exitCode !== null || child.killed) return;
  await new Promise((resolve) => {
    const timer = setTimeout(resolve, 5_000);
    child.once('exit', () => { clearTimeout(timer); resolve(); });
    child.kill();
  });
}

class Cdp {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    this.events = [];
    socket.addEventListener('message', ({ data }) => {
      const message = JSON.parse(data);
      if (message.id) this.pending.get(message.id)?.(message);
      else this.events.push(message);
    });
  }

  call(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, (message) => {
        this.pending.delete(id);
        if (message.error) reject(new Error(`${method}: ${message.error.message}`));
        else resolve(message.result);
      });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const result = await this.call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || 'browser evaluation failed');
    return result.result.value;
  }
}

test('real Edge reaches the isolated application through the test backend', { timeout: 90_000 }, async () => {
  const tempDir = await mkdtemp(join(tmpdir(), 'eduagent-e2e-'));
  let backend;
  let frontend;
  let edge;
  let otherEdge;
  let otherSocket;
  try {
    const database = join(tempDir, 'browser.db');
    backend = start('python', ['backend/tests/browser_fake_server.py'], {
      cwd: repoDir,
      env: { ...process.env, EDUAGENT_SKIP_ENV_FILE: '1', PYTHONPATH: 'backend', DATABASE_URL: `sqlite:///${database}`, PORT: String(backendPort) },
    });
    await waitFor(`http://127.0.0.1:${backendPort}/api/health`, 'test backend');
    const authResponse = await fetch(`http://127.0.0.1:${backendPort}/api/auth/register`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: '13900000001', password: 'e2e-only', nickname: 'E2E', role: 'student' }),
    });
    assert.equal(authResponse.ok, true);
    const { access_token: accessToken } = await authResponse.json();

    frontend = start(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort'], {
      cwd: frontendDir,
      env: { ...process.env, VITE_API_BASE_URL: `http://127.0.0.1:${backendPort}` },
    });
    await waitFor(`http://127.0.0.1:${frontendPort}/login`, 'test frontend');

    const debugPort = 9222;
    edge = start(edgePath, [
      '--headless=new', `--remote-debugging-port=${debugPort}`, '--remote-allow-origins=*',
      `--user-data-dir=${join(tempDir, 'edge-profile')}`, '--no-first-run', `http://127.0.0.1:${frontendPort}/login`,
    ], { cwd: repoDir, env: process.env });
    await waitFor(`http://127.0.0.1:${debugPort}/json/list`, 'Edge CDP');

    const pages = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
    const page = pages.find((entry) => entry.type === 'page' && entry.url.includes(`:${frontendPort}/`));
    assert.ok(page, 'Edge must navigate to the test frontend');
    const socket = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener('open', resolve, { once: true });
      socket.addEventListener('error', reject, { once: true });
    });
    const cdp = new Cdp(socket);
    await cdp.call('Runtime.enable');
    await cdp.call('Network.enable');
    await cdp.call('Page.enable');

    await waitForBrowser(cdp, "Boolean(document.querySelector('form'))", 'login form');
    const apiRequests = cdp.events.filter((event) => event.method === 'Network.requestWillBeSent' && event.params.request.url.includes('/api/'));
    assert.ok(apiRequests.some((event) => event.params.request.url.includes(`:${backendPort}/api/`)), 'frontend must use the isolated backend');
    assert.equal(cdp.events.filter((event) => event.method === 'Runtime.exceptionThrown').length, 0);

    await cdp.evaluate(`localStorage.setItem('edu_token', ${JSON.stringify(accessToken)}); location.assign('/generate')`);
    await waitForBrowser(cdp, "Boolean(document.querySelector('textarea'))", 'resource generation page');
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.includes('CNN')).click()");
    assert.ok((await cdp.evaluate("document.querySelector('textarea').value")).includes('CNN'));
    assert.ok((await cdp.evaluate('location.search')).includes('q='), 'quick templates must persist the prompt in the URL');

    const apiBase = `http://127.0.0.1:${backendPort}/api`;
    const create = async (sessionId) => {
      const response = await browserApi(cdp, `${apiBase}/chat/sessions`, accessToken, 'POST', { sessionId });
      assert.equal(response.ok, true);
    };
    const send = async (sessionId, message, token = accessToken) => {
      const response = await browserApi(cdp, `${apiBase}/chat/send`, token, 'POST', { sessionId, message });
      assert.equal(response.ok, true);
      return response.body;
    };
    await cdp.evaluate("location.assign('/chat')");
    await waitForBrowser(cdp, "Boolean(document.querySelector('textarea'))", 'chat page');
    assert.equal(await cdp.evaluate("document.body.textContent.includes('可用协作能力')"), true, 'agent list must be labelled as available capability');
    assert.equal(await cdp.evaluate("document.body.textContent.includes('在线待命')"), false, 'static agent list must not claim live status');
    await create('browser-session-a');
    await send('browser-session-a', '我是大二学生');
    await send('browser-session-a', '我喜欢视频学习');
    await send('browser-session-a', '这一次不要生成路径');
    await create('browser-session-b');
    const grade = await send('browser-session-b', '我现在是什么年级');
    const preference = await send('browser-session-b', '我偏好什么学习方式');
    assert.match(grade.reply.content, /大二/);
    assert.match(preference.reply.content, /视频/);
    const profile = await browserApi(cdp, `${apiBase}/profile?sessionId=browser-session-b`, accessToken);
    assert.equal(profile.ok, true);
    assert.equal(profile.body.data.profileV2.subject_context.background, '大二学生');
    assert.deepEqual(profile.body.data.profileV2.subject_context.resource_preferences, ['视频']);
    await cdp.evaluate('location.reload()');
    await waitForBrowser(cdp, "Boolean(document.querySelector('textarea'))", 'reloaded chat page');
    assert.match((await send('browser-session-b', '我现在是什么年级')).reply.content, /大二/);

    for (const name of ['\u6570\u636e\u7ed3\u6784', '\u6570\u636e\u7ed3\u6784\u3001', ' \u6570\u636e\u7ed3\u6784 ', '\u6570\u636e\u7ed3\u6784\uff0c']) {
      const response = await browserApi(cdp, `${apiBase}/subjects`, accessToken, 'POST', { name });
      assert.equal(response.ok, true);
    }
    const subjectList = await browserApi(cdp, `${apiBase}/subjects`, accessToken);
    assert.equal(subjectList.ok, true);
    assert.equal(subjectList.body.data.subjects.filter((subject) => subject.name === '\u6570\u636e\u7ed3\u6784').length, 1);
    await cdp.evaluate("location.assign('/')");
    await waitForBrowser(cdp, "document.body.innerText.includes('数据结构')", 'deduplicated subject card');
    assert.equal(await cdp.evaluate("document.body.innerText.split('数据结构').length - 1"), 1);

    const otherAuth = await fetch(`http://127.0.0.1:${backendPort}/api/auth/register`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: '13900000002', password: 'e2e-only', nickname: 'E2E2', role: 'student' }),
    });
    assert.equal(otherAuth.ok, true);
    const { access_token: otherToken } = await otherAuth.json();
    const otherDebugPort = 9223;
    otherEdge = start(edgePath, [
      '--headless=new', `--remote-debugging-port=${otherDebugPort}`, '--remote-allow-origins=*',
      `--user-data-dir=${join(tempDir, 'edge-profile-other')}`, '--no-first-run', `http://127.0.0.1:${frontendPort}/login`,
    ], { cwd: repoDir, env: process.env });
    await waitFor(`http://127.0.0.1:${otherDebugPort}/json/list`, 'second Edge CDP');
    const otherPages = await (await fetch(`http://127.0.0.1:${otherDebugPort}/json/list`)).json();
    const otherPage = otherPages.find((entry) => entry.type === 'page' && entry.url.includes(`:${frontendPort}/`));
    assert.ok(otherPage, 'second Edge must use the isolated frontend');
    otherSocket = new WebSocket(otherPage.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      otherSocket.addEventListener('open', resolve, { once: true });
      otherSocket.addEventListener('error', reject, { once: true });
    });
    const otherCdp = new Cdp(otherSocket);
    await otherCdp.call('Runtime.enable');
    await waitForBrowser(otherCdp, "Boolean(document.querySelector('form'))", 'second profile login form');
    await otherCdp.evaluate(`localStorage.setItem('edu_token', ${JSON.stringify(otherToken)}); location.assign('/chat')`);
    await waitForBrowser(otherCdp, "Boolean(document.querySelector('textarea'))", 'second profile chat page');
    await browserApi(otherCdp, `${apiBase}/chat/sessions`, otherToken, 'POST', { sessionId: 'browser-session-other' });
    const otherProfile = await browserApi(otherCdp, `${apiBase}/profile?sessionId=browser-session-other`, otherToken);
    assert.equal(otherProfile.ok, true);
    assert.notEqual(otherProfile.body.data.profileV2.subject_context.background, '大二学生');
    otherSocket.close();
    otherSocket = undefined;
    socket.close();
  } finally {
    if (otherSocket) otherSocket.close();
    await stop(otherEdge);
    await stop(edge);
    await stop(frontend);
    await stop(backend);
    await rm(tempDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
  }
});
