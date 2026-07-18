/** KGPreview — static knowledge graph preview. Big nodes, force layout, no jitter. */
import { useEffect, useRef } from 'react';
import { Graph } from '@antv/g6';

interface KGPreviewProps {
  graphData: { nodes: Array<{ id: string; label: string }>; edges: Array<{ source: string; target: string; relation?: string }> };
  height?: number;
}

export default function KGPreview({ graphData, height = 360 }: KGPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !graphData?.nodes?.length) return;
    const container = containerRef.current;
    const { width } = container.getBoundingClientRect();

    const graph = new Graph({
      container, width: width || 600, height,
      autoFit: false, animation: false,
      layout: { type: 'force', preventOverlap: true, nodeSize: 60, nodeStrength: 200, edgeStrength: 10, linkDistance: 800, coulombDisScale: 3, collideStrength: 10, gravity: 2, damping: 0.9, maxSpeed: 500, maxIteration: 3000, minMovement: 0.01 },
      data: {
        nodes: graphData.nodes.map((n) => ({ id: n.id, data: { label: n.label } })),
        edges: (graphData.edges || []).map((e) => ({ id: `${e.source}->${e.target}`, source: e.source, target: e.target, data: { relation: e.relation || '' } })),
      },
      node: {
        style: {
          size: 60, fill: '#6366f1', stroke: '#fff', lineWidth: 3, cursor: 'default',
          labelText: (d: any) => d.data?.label || d.id,
          labelFontSize: 13, labelFill: '#1f2937', labelFontWeight: 600,
        },
      },
      edge: {
        style: { stroke: '#cbd5e1', lineWidth: 2, endArrow: true },
        label: {
          text: (d: any) => {
            const r = d.data?.relation;
            return r === 'prerequisite' ? '前置' : r === 'contains' ? '包含' : '';
          },
          fontSize: 10, fill: '#94a3b8', background: true, backgroundFill: '#fff', backgroundOpacity: 0.8, padding: [2, 5],
        },
      },
      behaviors: [],
    });

    graph.render();
    setTimeout(() => { try { graph.fitView({ padding: 60 }); } catch {} }, 100);
    return () => { graph.destroy(); };
  }, [graphData]);

  return <div ref={containerRef} className="bg-white rounded-xl" style={{ height, width: '100%' }} />;
}
