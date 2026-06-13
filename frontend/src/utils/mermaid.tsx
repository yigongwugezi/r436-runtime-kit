import { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';

// 初始化 mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  fontFamily: 'var(--font-sans)',
});

interface MermaidDiagramProps {
  definition: string;
  className?: string;
}

export default function MermaidDiagram({ definition, className }: MermaidDiagramProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const id = `mermaid-${Date.now()}`;
    mermaid
      .render(id, definition)
      .then(({ svg: rendered }) => {
        if (!cancelled) setSvg(rendered);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => { cancelled = true; };
  }, [definition]);

  if (error) {
    return (
      <div className="p-4 bg-gray-50 border border-gray-200 rounded-xl text-sm text-gray-500">
        ⚠️ 思维导图渲染失败，请检查数据格式
      </div>
    );
  }

  return (
    <div
      ref={ref}
      className={`mermaid-wrapper ${className || ''}`}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
