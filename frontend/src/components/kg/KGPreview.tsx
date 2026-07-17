/** KGPreview — static G6 knowledge graph preview (no interactivity).

Renders a force-directed graph using G6 without behaviors or plugins.
Animation runs once and settles — no continuous shaking. */
import { useEffect, useRef } from 'react';
import { Graph } from '@antv/g6';

interface KGPreviewProps {
  graphData: {
    nodes: Array<{ id: string; label: string; type?: string; importance?: number; difficulty?: string }>;
    edges: Array<{ source: string; target: string; relation?: string }>;
  };
  className?: string;
  height?: number;
}

export default function KGPreview({ graphData, className = '', height = 360 }: KGPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !graphData?.nodes?.length) return;

    const container = containerRef.current;
    const { width } = container.getBoundingClientRect();

    const graph = new Graph({
      container,
      width: width || 600,
      height,
      autoFit: 'view',
      animation: false,
      layout: {
        type: 'force',
        preventOverlap: true,
        nodeSize: (d: any) => 20 + (d.data?.importance || 2) * 4 + 10,
        nodeStrength: -2000,
        edgeStrength: 0.8,
        linkDistance: 400,
        damping: 0.9,
        maxSpeed: 20,
        coulombScale: 2,
        workerEnabled: true,
      },
      data: {
        nodes: graphData.nodes.map((n) => ({
          id: n.id,
          data: {
            label: n.label,
            type: n.type || 'concept',
            importance: n.importance || 2,
          },
          style: {
            size: 20 + (n.importance || 2) * 4,
            fill: '#6366f1',
            stroke: '#fff',
            lineWidth: 2,
          },
        })),
        edges: graphData.edges.map((e) => ({
          id: `${e.source}->${e.target}`,
          source: e.source,
          target: e.target,
          data: { relation: e.relation },
          style: {
            stroke: '#cbd5e1',
            lineWidth: 1.5,
            endArrow: true,
          },
        })),
      },
      node: {
        style: {
          size: (d: any) => 20 + (d.data?.importance || 2) * 4,
          fill: '#6366f1',
          stroke: '#fff',
          lineWidth: 2,
          labelPlacement: 'bottom',
          labelOffset: 6,
          labelText: (d: any) => d.data?.label || d.id,
          labelFontSize: 12,
          labelFill: '#1f2937',
          labelFontWeight: 500,
        },
      },
      edge: {
        style: {
          stroke: '#cbd5e1',
          lineWidth: 1.5,
          endArrow: true,
          labelText: (d: any) => {
            const r = d.data?.relation;
            if (r === 'prerequisite') return '前置';
            if (r === 'contains') return '包含';
            if (r === 'related') return '关联';
            return '';
          },
          labelFontSize: 9,
          labelFill: '#94a3b8',
        },
      },
      behaviors: [],
    });

    graph.render();

    return () => {
      graph.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData]);

  return (
    <div
      ref={containerRef}
      className={`bg-white rounded-xl ${className}`}
      style={{ height, width: '100%' }}
    />
  );
}
