import { useEffect, useMemo, useRef } from 'react';
import { Transformer } from 'markmap-lib';
import { Markmap } from 'markmap-view';

interface MarkmapDiagramProps {
  definition: string;
  className?: string;
}

function cleanNodeLabel(value: string) {
  return value
    .trim()
    .replace(/^root\s*/i, '')
    .replace(/^[\w-]+\s*\(\((.*)\)\)\s*$/, '$1')
    .replace(/^[\w-]+\s*\((.*)\)\s*$/, '$1')
    .replace(/^\(\((.*)\)\)$/, '$1')
    .replace(/^\((.*)\)$/, '$1')
    .replace(/^["']|["']$/g, '')
    .trim();
}

function mermaidMindmapToMarkdown(definition: string) {
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
    if (!svgRef.current) return;
    const transformer = new Transformer();
    const { root } = transformer.transform(markdown);

    if (!markmapRef.current) {
      markmapRef.current = Markmap.create(svgRef.current, {
        autoFit: true,
        duration: 250,
        maxWidth: 260,
        paddingX: 12,
      }, root);
    } else {
      markmapRef.current.setData(root);
    }
    markmapRef.current.fit();
  }, [markdown]);

  return (
    <div className={`h-80 min-w-[520px] ${className || ''}`}>
      <svg ref={svgRef} className="h-full w-full" />
    </div>
  );
}
