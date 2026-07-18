/** Knowledge Graph — dagre layout, massive spacing, never moves, click zooms smoothly. */
import { useEffect, useRef } from 'react';
import { Graph } from '@antv/g6';
import type { LayoutOptions } from '@antv/g6';
import type { KGNode, KGEdge, KGNodeStatus } from '../../types/knowledgeGraph';

const STATUS_COLORS: Record<KGNodeStatus, string> = {
  not_started: '#94a3b8',
  in_progress: '#3b82f6',
  mastered: '#22c55e',
  needs_review: '#f59e0b',
};

export type LayoutType = 'force' | 'dagre' | 'circular';

interface KGGraphProps {
  nodes: KGNode[];
  edges: KGEdge[];
  layoutType: LayoutType;
  searchTerm: string;
  onNodeClick: (node: KGNode | null) => void;
}

const LAYOUTS: Record<LayoutType, LayoutOptions> = {
  dagre: { type: 'dagre', rankdir: 'LR', nodesep: 400, ranksep: 500 },
  force: { type: 'force', preventOverlap: true, nodeSize: 80, nodeStrength: 500, edgeStrength: 20, linkDistance: 1200, coulombDisScale: 5, collideStrength: 20, gravity: 0.5, damping: 0.95, maxSpeed: 500, maxIteration: 5000, minMovement: 0.001 },
  circular: { type: 'circular', radius: 600, startRadius: 200, endRadius: 800 },
};

const NODE_SIZE = 72;

export default function KGGraph({
  nodes, edges, layoutType, searchTerm, onNodeClick,
}: KGGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);
  const layoutKey = layoutType;

  useEffect(() => {
    if (!containerRef.current || !nodes.length) return;
    const container = containerRef.current;
    const { width, height } = container.getBoundingClientRect();

    if (graphRef.current) { graphRef.current.destroy(); graphRef.current = null; }

    const graph = new Graph({
      container, width, height: height || 600,
      autoFit: false,
      animation: true, // 只影响相机动画（点击飞行），不影响布局稳定性
      layout: LAYOUTS[layoutKey as LayoutType] || LAYOUTS.dagre,
      data: {
        nodes: nodes.map((n) => ({
          id: n.id,
          data: { label: n.label, status: n.status, chapter: n.chapter },
        })),
        edges: edges.map((e) => ({
          id: `${e.source}->${e.target}`, source: e.source, target: e.target,
          data: { relation: e.relation },
        })),
      },
      node: {
        style: {
          size: NODE_SIZE,
          fill: (d: any) => STATUS_COLORS[d.data?.status as KGNodeStatus] || '#94a3b8',
          stroke: '#fff', lineWidth: 3, cursor: 'pointer',
          labelText: (d: any) => d.data?.label || d.id,
          labelFontSize: 13, labelFill: '#1f2937', labelFontWeight: 600,
        },
        state: {
          searched: { stroke: '#f59e0b', lineWidth: 4, shadowBlur: 20, shadowColor: '#f59e0baa' },
        },
      },
      edge: {
        style: { stroke: '#cbd5e1', lineWidth: 2, endArrow: true },
        label: {
          text: (d: any) => {
            const r = d.data?.relation;
            if (r === 'prerequisite') return '前置';
            if (r === 'contains') return '包含';
            return '';
          },
          fontSize: 10, fill: '#94a3b8',
          background: true, backgroundFill: '#fff', backgroundOpacity: 0.8,
          padding: [2, 5],
        },
      },
      behaviors: [
        'drag-canvas', 'zoom-canvas', 'drag-element',
        { type: 'hover-activate', key: 'hover', degree: 1 },
      ],
      plugins: [
        { type: 'minimap', key: 'minimap', size: [180, 120], padding: 10 },
      ],
    });

    graph.on('node:click', (e: any) => {
      const nid = e.target?.id || e.itemId;
      if (!nid) return;
      const node = nodes.find((n) => n.id === nid);
      onNodeClick(node || null);
      // ONE absolute transform: zoom to 4x AND center on node, simultaneous
      try {
        const nd = graph.getNodeData(nid);
        const st = (nd as any).style || (nd as any).data?.style;
        const sx = parseFloat(st?.x);
        const sy = parseFloat(st?.y);
        if (!isNaN(sx) && !isNaN(sy)) {
          const sz = graph.getSize();
          const Z = 4;
          graph.transform({
            mode: 'absolute', zoom: Z,
            translate: { x: sz[0] / 2 - sx * Z, y: sz[1] / 2 - sy * Z },
          }, { duration: 800 });
          return;
        }
      } catch {}
      graph.focusElement(nid, { duration: 800 });
    });

    graph.render();
    graphRef.current = graph;

    return () => { graph.destroy(); graphRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, layoutKey]);

  // ── Search ──
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    if (searchTerm) {
      const match = (nodes || []).find((n) =>
        n.label?.toLowerCase().includes(searchTerm.toLowerCase()),
      );
      if (match) {
        graph.setElementState({ all: [], [match.id]: 'searched' });
        graph.focusElement(match.id, { duration: 800 });
      }
    } else { graph.setElementState({ all: [] }); }
  }, [searchTerm, nodes]);

  // ── Resize ──
  useEffect(() => {
    const onResize = () => {
      const g = graphRef.current;
      const c = containerRef.current;
      if (g && c) { const r = c.getBoundingClientRect(); g.resize(r.width, r.height || 600); }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  return <div ref={containerRef} className="w-full h-full bg-surface-50 rounded-2xl" />;
}
