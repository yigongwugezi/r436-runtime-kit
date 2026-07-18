import assert from 'node:assert/strict';
import { adaptKnowledgeGraph } from '../src/utils/knowledgeGraphAdapter.ts';

const graph = adaptKnowledgeGraph({
  nodes: [{ id: 1, label: '数组' }, { id: 1, label: '重复' }, { id: 2, metadata: {} }],
  edges: [{ source: 1, target: 2 }, { source: 1, target: 9 }, { source: 1, target: 2 }],
  meta: { chapters: ['第一章'] },
});
assert.deepEqual(graph.nodes.map((node) => node.id), ['1', '2']);
assert.equal(graph.nodes[1].label, '2');
assert.equal(graph.edges.length, 1);
assert.deepEqual(adaptKnowledgeGraph({ nodes: [], edges: [] }), { nodes: [], edges: [], meta: { totalNodes: 0, totalEdges: 0, masteredCount: 0, chapters: [], source: 'unknown' } });
console.log('knowledge graph adapter tests: ok');
