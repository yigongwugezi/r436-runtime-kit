import { readFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('../../..', import.meta.url)));
const metadata = resolve(root, '.qa/runtime/browser-qa/runtime-metadata.json');
try {
  const { backendPid, frontendPid } = JSON.parse(await readFile(metadata, 'utf8'));
  for (const pid of [frontendPid, backendPid]) if (Number.isInteger(pid)) await new Promise((done) => execFile('taskkill', ['/PID', String(pid), '/T', '/F'], () => done()));
  console.log('QA_RUNTIME_CLOSED');
} catch { console.log('QA_RUNTIME_CLOSED'); }
