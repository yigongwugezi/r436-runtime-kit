/** Knowledge Graph — G6 wrapper component.

Handles rendering the graph, interactions, and events. */
import { useEffect, useRef, useMemo, useState, useCallback } from 'react';
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
  selectedNodeId: string | null;
  onNodeClick: (node: KGNode | null) => void;
  searchTerm: string;
  filterStatus: KGNodeStatus[];
  filterChapter: string;
}

const LAYOUTS: Record<LayoutType, LayoutOptions> = {
  force: {
    type: 'force',
    preventOverlap: true,
    nodeSize: (d: any) => 20 + (d.data?.importance || 2) * 5 + 10,
    nodeStrength: -2000,
    edgeStrength: 0.8,
    linkDistance: 400,
    damping: 0.9,
    maxSpeed: 20,
    coulombScale: 2,
  },
  dagre: { type: 'dagre', rankdir: 'LR', nodesep: 120, ranksep: 200 },
  circular: { type: 'circular', radius: 350, startRadius: 100, endRadius: 400 },
};

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

  const [layoutVersion, setLayoutVersion] = useState(0);
  useEffect(() => { setLayoutVersion((v) => v + 1); }, [layoutType]);

  const dataKey = useMemo(() => {
    const nIds = nodes.map((n) => n.id).join(',');
    const eIds = edges.map((e) => `${e.source}->${e.target}`).join(',');
    return `${nIds}|${eIds}`;
  }, [nodes, edges]);

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
      })),
      edges: edges.map((e) => ({
        id: `${e.source}->${e.target}`,
        source: e.source,
        target: e.target,
        data: { relation: e.relation },
      })),
    }),
    [dataKey],
  );

  // Initialize graph
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
      animation: false,
      layout: LAYOUTS[layoutType] || LAYOUTS.force,
      data: graphData,
      node: {
        style: {
          size: (d: any) => 20 + (d.data?.importance || 2) * 5,
          fill: (d: any) => STATUS_COLORS[d.data?.status as KGNodeStatus] || '#94a3b8',
          stroke: '#fff',
          lineWidth: 2,
          cursor: 'pointer',
          labelText: (d: any) => d.data?.label || d.id,
          labelFontSize: 12,
          labelFill: '#1f2937',
          labelFontWeight: 500,
          labelPlacement: 'bottom',
          labelOffset: 6,
          labelMaxLines: 2,
        },
        state: {
          selected: { stroke: '#2563eb', lineWidth: 3, shadowBlur: 8, shadowColor: '#2563eb66' },
          searched: { stroke: '#f59e0b', lineWidth: 3, shadowBlur: 12, shadowColor: '#f59e0b88' },
        },
      },
      edge: {
        style: {
          stroke: '#cbd5e1',
          lineWidth: 1.5,
          endArrow: true,
          radius: 8,
        },
        label: {
          text: (d: any) => {
            const r = d.data?.relation;
            if (r === 'prerequisite') return '前置';
            if (r === 'contains') return '包含';
            if (r === 'related') return '关联';
            return '';
          },
          fontSize: 9,
          fill: '#94a3b8',
          background: true,
          backgroundFill: '#fff',
          backgroundOpacity: 0.8,
          padding: [2, 4],
        },
        state: {
          highlighted: { stroke: '#2563eb', lineWidth: 2.5 },
          dimmed: { stroke: '#e2e8f0', opacity: 0.15 },
        },
      },
      behaviors: [
        'drag-canvas',
        'zoom-canvas',
        'drag-element',
        { type: 'hover-activate', key: 'hover', degree: 1, enable: (e: any) => e.targetType === 'node' },
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
    graph.on('canvas:click', () => { nodeClickRef.current(null); });

    graph.render();
    graphRef.current = graph;

    return () => { graph.destroy(); graphRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataKey, layoutVersion]);

  // Update data
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    graph.setData(graphData);
    graph.render();
  }, [graphData]);

  // Search highlight
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    graph.setElementState({ all: [] });
    if (searchTerm) {
      const match = nodes.find((n) => n.label.toLowerCase().includes(searchTerm.toLowerCase()));
      if (match) {
        graph.setElementState({ [match.id]: 'searched' });
        graph.focusElement(match.id, { animation: true });
      }
    } else if (selectedNodeId) {
      graph.setElementState({ [selectedNodeId]: 'selected' });
    }
  }, [searchTerm, selectedNodeId, nodes]);

  // Resize
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
      className="w-full h-full bg-surface-50 rounded-2xl"
      style={{ minHeight: 500 }}
    />
  );
}
