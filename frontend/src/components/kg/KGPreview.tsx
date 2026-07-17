/** KGPreview — static G6 knowledge graph preview (no interactivity).

Renders a simple force-directed graph using G6 without behaviors or plugins.
Used in ResourceLibrary for mindmap-type resources with graph_data content. */
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
      animation: true,
      layout: {
        type: 'force',
        preventOverlap: true,
        linkDistance: 120,
        nodeStrength: -150,
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
            size: 18 + (n.importance || 2) * 3,
            fill: '#6366f1',
            stroke: '#fff',
            lineWidth: 2,
          },
        })),
        edges: graphData.edges.map((e) => ({
          id: `${e.source}->${e.target}`,
          source: e.source,
          target: e.target,
          style: {
            stroke: '#cbd5e1',
            lineWidth: 1.5,
            endArrow: true,
          },
        })),
      },
      node: {
        label: {
          text: (d: any) => d.data?.label || d.id,
          fontSize: 11,
          fill: '#374151',
          position: 'bottom',
          offset: 4,
        },
      },
      edge: {
        style: {
          stroke: '#cbd5e1',
          lineWidth: 1.5,
          endArrow: true,
        },
      },
      // No behaviors = static, no interaction
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
      className={`bg-surface-50 rounded-xl overflow-hidden ${className}`}
      style={{ height, width: '100%' }}
    />
  );
}
