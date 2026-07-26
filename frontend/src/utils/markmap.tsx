import { useEffect, useMemo, useRef } from 'react';
import { Transformer } from 'markmap-lib';
import { Markmap } from 'markmap-view';

interface MarkmapDiagramProps {
  definition: string;
  className?: string;
}

function cleanNodeLabel(value: string) {
  const cleaned = value
    .trim()
    .replace(/^root\s*/i, '')
    .replace(/^[\w-]+\s*\(\((.*)\)\)\s*$/, '$1')
    .replace(/^[\w-]+\s*\((.*)\)\s*$/, '$1')
    .replace(/^\(\((.*)\)\)$/, '$1')
    .replace(/^\((.*)\)$/, '$1')
    .replace(/\\(?:frac|sqrt|begin|end|varphi)[^，。；\s]*/g, '')
    .replace(/\s+/g, ' ')
    .replace(/^["']|["']$/g, '')
    .trim();
  return cleaned.length > 34 ? `${cleaned.slice(0, 32)}…` : cleaned;
}

export function mermaidMindmapToMarkdown(definition: string) {
  const trimmed = definition.trim();
  if (trimmed.startsWith('#') || trimmed.startsWith('- ')) return definition;

  const lines = definition
    .split(/\r?\n/)
    .filter((line) => line.trim() && line.trim().toLowerCase() !== 'mindmap');

  const items = lines
    .map((line) => {
      const indent = line.match(/^\s*/)?.[0].length || 0;
      const label = cleanNodeLabel(line.trim());
      return label ? `${'  '.repeat(Math.floor(indent / 2))}- ${label}` : '';
    })
    .filter(Boolean);

  return items.length ? items.join('\n') : `- ${cleanNodeLabel(definition) || '思维导图'}`;
}

export default function MarkmapDiagram({ definition, className }: MarkmapDiagramProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const markmapRef = useRef<Markmap | null>(null);
  const markdown = useMemo(() => mermaidMindmapToMarkdown(definition), [definition]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !definition.trim()) return;
    const transformer = new Transformer();
    const { root } = transformer.transform(markdown);
    const markmap = Markmap.create(svg, { autoFit: false, duration: 0, maxWidth: 200, paddingX: 12 });
    markmapRef.current = markmap;
    let active = true;
    let frame = 0;
    const fit = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const { width, height } = svg.getBoundingClientRect();
        if (width && height) void markmap.fit();
      });
    };
    void markmap.setData(root).then(() => { if (active) { svg.dataset.mindmapReady = 'true'; fit(); } });
    const observer = new ResizeObserver(fit);
    observer.observe(svg);
    return () => {
      active = false;
      cancelAnimationFrame(frame);
      observer.disconnect();
      markmap.destroy();
      delete svg.dataset.mindmapReady;
      if (markmapRef.current === markmap) markmapRef.current = null;
    };
  }, [definition, markdown]);

  if (!definition.trim()) return <div data-testid="mindmap-empty-state" className={className}>暂无思维导图</div>;

  return (
    <div data-testid="mindmap-container" className={`h-[480px] min-w-[560px] ${className || ''}`}>
      <svg ref={svgRef} data-testid="mindmap-svg" className="h-full w-full" />
    </div>
  );
}
