/** Knowledge Graph — G6 wrapper component.

Handles rendering the graph, interactions, and events. */
import { useEffect, useRef, useMemo, useState, useCallback } from 'react';
import { Graph } from '@antv/g6';
import type { LayoutOptions } from '@antv/g6';
import type { KGNode, KGEdge, KGNodeStatus } from '../../types/knowledgeGraph';

// ── Style maps ──

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
  selectedNodeId: string | null;
  onNodeClick: (node: KGNode | null) => void;
  searchTerm: string;
  filterStatus: KGNodeStatus[];
  filterChapter: string;
}

// ══════════════════════════════════════════════════════════════════════

const LAYOUTS: Record<LayoutType, LayoutOptions> = {
  force: { type: 'force', preventOverlap: true, linkDistance: 150, nodeStrength: -200, edgeStrength: 0.1 },
  dagre: { type: 'dagre', rankdir: 'LR', nodesep: 60, ranksep: 120 },
  circular: { type: 'circular', radius: 250 },
};

// ══════════════════════════════════════════════════════════════════════

export default function KGGraph({
  nodes,
  edges,
  layoutType,
  selectedNodeId,
  onNodeClick,
  searchTerm,
}: KGGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);
  const nodeClickRef = useRef(onNodeClick);
  nodeClickRef.current = onNodeClick;

  // ── Stable key for re-creating graph on layout change ──
  const [layoutVersion, setLayoutVersion] = useState(0);
  useEffect(() => {
    setLayoutVersion((v) => v + 1);
  }, [layoutType]);

  // ── Stable data identity (avoid re-init when parent re-renders) ──
  const dataKey = useMemo(() => {
    const nIds = nodes.map((n) => n.id).join(',');
    const eIds = edges.map((e) => `${e.source}->${e.target}`).join(',');
    return `${nIds}|${eIds}`;
  }, [nodes, edges]);

  // ── Build G6 data ──
  const graphData = useMemo(
    () => ({
      nodes: nodes.map((n) => ({
        id: n.id,
        data: {
          label: n.label,
          status: n.status,
          mastery: n.mastery,
          type: n.type,
          difficulty: n.difficulty,
          importance: n.importance,
          chapter: n.chapter,
          category: n.category,
        },
        style: {
          size: 20 + n.importance * 5,
          fill: STATUS_COLORS[n.status] || '#94a3b8',
          stroke: '#fff',
          lineWidth: 2,
          cursor: 'pointer',
        },
      })),
      edges: edges.map((e) => ({
        id: `${e.source}->${e.target}`,
        source: e.source,
        target: e.target,
        data: { relation: e.relation },
        style: { stroke: '#cbd5e1', lineWidth: 1.5, endArrow: true },
      })),
    }),
    [dataKey],
  );

  // ── Initialize graph ──
  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return;

    const container = containerRef.current;
    const { width, height } = container.getBoundingClientRect();

    if (graphRef.current) {
      graphRef.current.destroy();
      graphRef.current = null;
    }

    const graph = new Graph({
      container,
      width,
      height: height || 600,
      autoFit: 'view',
      animation: true,
      layout: LAYOUTS[layoutType] || LAYOUTS.force,
      data: graphData,
      node: {
        style: {
          size: (d: any) => 20 + (d.data?.importance || 1) * 5,
          fill: (d: any) => STATUS_COLORS[d.data?.status as KGNodeStatus] || '#94a3b8',
          stroke: '#fff',
          lineWidth: 2,
          cursor: 'pointer',
        },
        label: {
          text: (d: any) => d.data?.label || d.id,
          fontSize: 11,
          fill: '#374151',
          position: 'bottom',
          offset: 6,
          maxLines: 1,
        },
        state: {
          selected: { stroke: '#2563eb', lineWidth: 3, shadowBlur: 6, shadowColor: '#2563eb33' },
          searched: { stroke: '#f59e0b', lineWidth: 3, shadowBlur: 10, shadowColor: '#f59e0b66' },
        },
      },
      edge: {
        style: { stroke: '#cbd5e1', lineWidth: 1.5, endArrow: true, radius: 8 },
        state: {
          highlighted: { stroke: '#2563eb', lineWidth: 2.5 },
          dimmed: { stroke: '#e2e8f0', opacity: 0.15 },
        },
      },
      behaviors: [
        'drag-canvas',
        'zoom-canvas',
        'drag-element',
        { type: 'hover-activate', key: 'hover', degree: 1 },
      ],
      plugins: [
        { type: 'minimap', key: 'minimap', size: [180, 120], padding: 10 },
      ],
    });

    graph.on('node:click', (e: any) => {
      const nodeId = e.target?.id || e.itemId;
      if (nodeId) {
        const original = nodes.find((n) => n.id === nodeId);
        nodeClickRef.current(original || null);
      }
    });
    graph.on('canvas:click', () => {
      nodeClickRef.current(null);
    });

    graph.render();
    graphRef.current = graph;

    return () => {
      graph.destroy();
      graphRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataKey, layoutVersion]);

  // ── Update data without full re-init ──
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    graph.setData(graphData);
    graph.render();
  }, [graphData]);

  // ── Search highlight ──
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;

    graph.setElementState({ all: [] });

    if (searchTerm) {
      const match = nodes.find((n) =>
        n.label.toLowerCase().includes(searchTerm.toLowerCase()),
      );
      if (match) {
        graph.setElementState({ [match.id]: 'searched' });
        graph.focusElement(match.id, { animation: true });
      }
    } else if (selectedNodeId) {
      graph.setElementState({ [selectedNodeId]: 'selected' });
    }
  }, [searchTerm, selectedNodeId, nodes]);

  // ── Resize ──
  useEffect(() => {
    const onResize = () => {
      const graph = graphRef.current;
      const container = containerRef.current;
      if (graph && container) {
        const { width, height } = container.getBoundingClientRect();
        graph.resize(width, height || 600);
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  return (
    <div
      ref={containerRef}
      className="w-full h-full bg-surface-50 rounded-2xl overflow-hidden"
      style={{ minHeight: 500 }}
    />
  );
}
