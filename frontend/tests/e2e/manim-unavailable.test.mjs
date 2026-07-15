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
const start = (command, args, options) => spawn(command, args, { ...options, stdio: 'ignore', windowsHide: true });

async function stop(child) {
  if (child?.exitCode === null && !child.killed) {
    child.kill();
    await Promise.race([new Promise((resolve) => child.once('exit', resolve)), sleep(5000)]);
  }
}

async function waitFor(url, label) {
  for (const deadline = Date.now() + 30000; Date.now() < deadline; await sleep(100)) {
    try { if ((await fetch(url)).ok) return; } catch {}
  }
  throw new Error(label + ' did not start');
}

class Cdp {
  constructor(socket) {
    this.socket = socket; this.nextId = 1; this.pending = new Map();
    socket.addEventListener('message', ({ data }) => {
      const message = JSON.parse(data);
      if (message.id) this.pending.get(message.id)?.(message);
    });
  }
  call(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, (message) => {
        this.pending.delete(id);
        message.error ? reject(new Error(message.error.message)) : resolve(message.result);
      });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async evaluate(expression) {
    const result = await this.call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  }
}

async function waitForBrowser(cdp, expression, label) {
  for (const deadline = Date.now() + 15000; Date.now() < deadline; await sleep(100)) {
    if (await cdp.evaluate(expression)) return;
  }
  throw new Error(label + ' did not render');
}

async function setText(cdp, selector, value) {
  await cdp.evaluate('document.querySelector(' + JSON.stringify(selector) + ').focus()');
  await cdp.call('Input.dispatchKeyEvent', { type: 'keyDown', modifiers: 2, windowsVirtualKeyCode: 65, code: 'KeyA', key: 'a' });
  await cdp.call('Input.dispatchKeyEvent', { type: 'keyUp', modifiers: 2, windowsVirtualKeyCode: 65, code: 'KeyA', key: 'a' });
  await cdp.call('Input.insertText', { text: value });
}

test('real Edge shows a safe Manim-unavailable result without a fake resource', { timeout: 90000 }, async () => {
  const tempDir = await mkdtemp(join(tmpdir(), 'eduagent-manim-e2e-'));
  let backend; let frontend; let edge; let socket;
  try {
    backend = start('python', ['backend/tests/browser_fake_server.py'], {
      cwd: repoDir,
      env: { ...process.env, PYTHONPATH: 'backend', EDUAGENT_SKIP_ENV_FILE: '1', LLM_PROVIDER: 'mock', DATABASE_URL: 'sqlite:///' + join(tempDir, 'browser.db'), PORT: String(backendPort) },
    });
    await waitFor('http://127.0.0.1:' + backendPort + '/api/health', 'isolated backend');
    const registration = await fetch('http://127.0.0.1:' + backendPort + '/api/auth/register', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: '13900000008', password: 'e2e-only', nickname: 'fixture', role: 'student' }),
    });
    assert.equal(registration.ok, true);
    frontend = start(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort'], {
      cwd: frontendDir, env: { ...process.env, VITE_API_BASE_URL: 'http://127.0.0.1:' + backendPort },
    });
    await waitFor('http://127.0.0.1:' + frontendPort + '/login', 'isolated frontend');
    edge = start(edgePath, ['--headless=new', '--remote-debugging-port=' + debugPort, '--remote-allow-origins=*', '--user-data-dir=' + join(tempDir, 'edge'), '--no-first-run', 'http://127.0.0.1:' + frontendPort + '/login'], { cwd: repoDir, env: process.env });
    await waitFor('http://127.0.0.1:' + debugPort + '/json/list', 'Edge');
    const pages = await (await fetch('http://127.0.0.1:' + debugPort + '/json/list')).json();
    const page = pages.find((entry) => entry.type === 'page' && entry.url.includes(':' + frontendPort + '/login'));
    assert.ok(page, 'expected Edge page');
    socket = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }); });
    const cdp = new Cdp(socket);
    await cdp.call('Runtime.enable'); await cdp.call('Page.enable');
    await waitForBrowser(cdp, "Boolean(document.querySelector('form'))", 'login form');
    await setText(cdp, "input[type='text']", '13900000008');
    await setText(cdp, "input[type='password']", 'e2e-only');
    await cdp.evaluate("document.querySelector('form').requestSubmit()");
    await waitForBrowser(cdp, "location.pathname === '/'", 'authenticated home');

    await cdp.evaluate("location.assign('/generate?q=' + encodeURIComponent('Manim 安全测试') + '&types=manim')");
    await waitForBrowser(cdp, "document.body.innerText.includes('Manim 动画')", 'Manim generation option');
    await cdp.evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.includes('开始生成')).click()");
    await waitForBrowser(cdp, "document.body.innerText.includes('未生成伪造资源')", 'safe unavailable result');
    assert.equal(await cdp.evaluate("document.body.innerText.includes('已完成')"), false);
  } finally {
    socket?.close(); await stop(edge); await stop(frontend); await stop(backend);
    await rm(tempDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
  }
});
