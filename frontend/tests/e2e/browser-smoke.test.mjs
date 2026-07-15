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
  try {
    const database = join(tempDir, 'browser.db');
    backend = start('python', ['backend/tests/browser_fake_server.py'], {
      cwd: repoDir,
      env: { ...process.env, EDUAGENT_SKIP_ENV_FILE: '1', PYTHONPATH: 'backend', DATABASE_URL: `sqlite:///${database}`, PORT: String(backendPort) },
    });
    await waitFor(`http://127.0.0.1:${backendPort}/api/health`, 'test backend');

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
    socket.close();
  } finally {
    await stop(edge);
    await stop(frontend);
    await stop(backend);
    await rm(tempDir, { recursive: true, force: true });
  }
});
