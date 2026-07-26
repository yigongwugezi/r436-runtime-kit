import { createServer } from 'node:net';
import { createWriteStream } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('../../..', import.meta.url)));
const runtime = resolve(root, '.qa/runtime/browser-qa');
const port = () => new Promise((done, fail) => { const server = createServer(); server.once('error', fail); server.listen(0, '127.0.0.1', () => { const value = server.address().port; server.close(() => done(value)); }); });
const waitFor = async (url) => { const end = Date.now() + 30000; while (Date.now() < end) { try { if ((await fetch(url)).ok) return; } catch {} await new Promise((r) => setTimeout(r, 200)); } throw new Error(`READY_TIMEOUT: ${url}`); };

export async function startBrowserQa({ detached = true, scenario = '' } = {}) {
  await mkdir(runtime, { recursive: true });
  const seeded = spawnSync('python', ['backend/scripts/seed_browser_qa.py', '--db', '.qa/runtime/browser-qa/qa.db'], { cwd: root, encoding: 'utf8', env: { ...process.env, EDUAGENT_QA_SCENARIO: scenario } });
  if (seeded.status !== 0) throw new Error('SEED_FAILED');
  const backendPort = await port();
  const frontendPort = await port();
  const backendBaseUrl = `http://127.0.0.1:${backendPort}`;
  const frontendBaseUrl = `http://127.0.0.1:${frontendPort}`;
  const out = createWriteStream(resolve(runtime, 'backend.log'), { flags: 'w' });
  const err = createWriteStream(resolve(runtime, 'backend-error.log'), { flags: 'w' });
  await Promise.all([once(out, 'open'), once(err, 'open')]);
  const backend = spawn('python', ['tests/browser_fake_server.py'], { cwd: resolve(root, 'backend'), detached, stdio: ['ignore', out, err], env: { ...process.env, PYTHONPATH: resolve(root, 'backend'), EDUAGENT_SKIP_ENV_FILE: '1', DATABASE_URL: `sqlite:///${resolve(runtime, 'qa.db').replaceAll('\\', '/')}`, LLM_PROVIDER: 'mock', RAG_ENABLED: 'false', PORT: String(backendPort) } });
  if (detached) backend.unref();
  await waitFor(`${backendBaseUrl}/api/health`);
  const frontend = spawn(process.execPath, [resolve(root, 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort'], { cwd: resolve(root, 'frontend'), detached, stdio: 'ignore', env: { ...process.env, EDUAGENT_API_PROXY_TARGET: backendBaseUrl } });
  if (detached) frontend.unref();
  await waitFor(frontendBaseUrl);
  const metadata = { backendBaseUrl, frontendBaseUrl, backendPort, frontendPort, databasePath: resolve(runtime, 'qa.db'), seedMetadataPath: resolve(runtime, 'seed-metadata.json'), backendPid: backend.pid, frontendPid: frontend.pid, startedAt: new Date().toISOString() };
  await writeFile(resolve(runtime, 'runtime-metadata.json'), JSON.stringify(metadata, null, 2));
  return { metadata, backend, frontend };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) startBrowserQa().then(({ metadata }) => console.log(`QA_RUNTIME_READY backend=${metadata.backendPort} frontend=${metadata.frontendPort}`)).catch((error) => { console.error(`QA_START_FAILED: ${error.message}`); process.exitCode = 1; });
