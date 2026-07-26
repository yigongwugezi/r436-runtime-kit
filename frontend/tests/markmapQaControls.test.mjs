import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../src/utils/markmap.tsx', import.meta.url), 'utf8');
for (const token of ['mindmap-container', 'mindmap-svg', 'mindmap-empty-state', 'autoFit: false', 'markmap.setData(root).then', 'new ResizeObserver(fit)', 'observer.disconnect()', 'markmap.destroy()', 'requestAnimationFrame']) assert.ok(source.includes(token));
console.log('markmap QA controls: PASS');
