import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const router = readFileSync(new URL('../src/router/index.tsx', import.meta.url), 'utf8');
const chatPanel = readFileSync(new URL('../src/components/chat/ChatPanel.tsx', import.meta.url), 'utf8');
const layout = readFileSync(new URL('../src/components/layout/AppLayout.tsx', import.meta.url), 'utf8');
const resources = readFileSync(new URL('../src/pages/ResourceLibrary.tsx', import.meta.url), 'utf8');
const lecture = readFileSync(new URL('../src/pages/LecturePage.tsx', import.meta.url), 'utf8');

for (const page of ['Home', 'ChatPage', 'LecturePage', 'ResourceLibrary', 'LearningPathPage', 'KnowledgeGraphPage', 'AdminDashboard', 'LoginPage']) {
  assert.match(router, new RegExp(`const ${page} = lazy\\(\\(\\) => import\\('../pages/${page}'\\)\\)`));
}
assert.doesNotMatch(router, /import .* from '..\/pages\//);
assert.match(router, /<Suspense fallback=\{<RouteLoading \/>\}>/);
assert.match(router, /role="status"/);
assert.match(layout, /const ChatPanel = lazy\(\(\) => import\('\.\.\/chat\/ChatPanel'\)\)/);
assert.match(layout, /showChat && chatOpen && <ErrorBoundary><Suspense fallback=/);
assert.match(chatPanel, /const MarkmapDiagram = lazy\(\(\) => import\('\.\.\/\.\.\/utils\/markmap'\)\)/);
assert.match(chatPanel, /<Suspense fallback=\{<div role="status"/);
assert.doesNotMatch(resources, /import\('\.\.\/api\/resources'\)/);
assert.doesNotMatch(lecture, /import\('\.\.\/api\/sectionResources'\)/);

console.log('bundle lazy loading: PASS');
