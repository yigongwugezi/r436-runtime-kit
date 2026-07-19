import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const resolver = readFileSync(new URL('../src/utils/taskExecutionMode.ts', import.meta.url), 'utf8');
const page = readFileSync(new URL('../src/pages/LecturePage.tsx', import.meta.url), 'utf8');

assert.match(resolver, /\['mind_map', 'mindmap'\].*return 'mindmap'/);
assert.match(page, /executionMode !== 'mindmap'/);
assert.match(page, /getSectionMindmap\([\s\S]*generateSectionMindmap/);
assert.match(page, /MarkmapDiagram definition=\{taskMindmap\.mermaidDef\}/);
assert.match(page, /重新生成思维导图/);
assert.match(page, /evidenceType: 'mindmap_viewed', resourceId: taskMindmap!/);
assert.match(page, /确认学习完成/);

console.log('mindmap task execution: PASS');
