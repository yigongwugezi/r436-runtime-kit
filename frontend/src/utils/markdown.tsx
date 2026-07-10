import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import 'katex/dist/katex.min.css';
import mermaid from 'mermaid';

mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose', suppressErrorRendering: true });

interface Props { content: string; }

function normalizeBareLatex(content: string) {
  return content
    .replace(/\\\(([\s\S]*?)\\\)/g, (_m, body) => `$${body}$`)
    .replace(/\\\[([\s\S]*?)\\\]/g, (_m, body) => `$$${body}$$`)
    .replace(/(?<![$\\])\\frac\{[^{}]+\}\{[^{}]+\}/g, (m) => `$${m}$`)
    .replace(/(?<![$\\])\\sqrt\{[^{}]+\}/g, (m) => `$${m}$`)
    .replace(/(?<![$\\])\\varphi/g, '$\\varphi$')
    .replace(/(?<![$\\])\\begin\{cases\}([\s\S]*?)\\end\{cases\}/g, (_m, body) => `$$\\begin{cases}${body}\\end{cases}$$`);
}

/** 节标题提取 —— 从 markdown 中提取所有 ## 标题用于目录 */
export function extractSections(md: string): { id: string; title: string }[] {
  const re = /^## (.+)$/gm;
  const sections: { id: string; title: string }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(md)) !== null) {
    const title = m[1].trim();
    sections.push({ id: `sec-${sections.length}`, title });
  }
  return sections;
}

/** 把 markdown 按 ## 拆成段，每段前面插 anchor */
export function splitSections(md: string): { id: string; title: string; content: string }[] {
  const parts = md.split(/^## /m);
  const result: { id: string; title: string; content: string }[] = [];
  if (parts[0]?.trim()) {
    result.push({ id: 'sec-overview', title: '概述', content: parts[0].trim() });
  }
  for (let i = 1; i < parts.length; i++) {
    const lines = parts[i].split('\n');
    const title = lines[0].trim();
    result.push({ id: `sec-${i - 1}`, title, content: `## ${parts[i].trim()}` });
  }
  return result;
}

function MermaidBlock({ definition }: { definition: string }) {
  const [svg, setSvg] = useState('');
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const id = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    mermaid.render(id, definition).then(({ svg: rendered }) => {
      if (!cancelled) {
        // mermaid 有时不抛异常但渲染出错误信息
        if (rendered.includes('error') || rendered.includes('Syntax error')) {
          setError(true);
        } else {
          setSvg(rendered);
        }
      }
    }).catch(() => {
      if (!cancelled) setError(true);
    });
    return () => { cancelled = true; };
  }, [definition]);

  // 解析 mermaid 文本提取节点名
  const fallbackNodes = definition.split('\n')
    .filter(l => l.trim() && !l.trim().startsWith('%') && !l.trim().startsWith('mindmap') && !l.trim().startsWith('graph'))
    .map(l => l.replace(/^[-\s]*/, '').replace(/[\[\](){}]/g, '').trim())
    .filter(Boolean);

  if (error || (!svg && fallbackNodes.length > 0 && definition.length < 50)) {
    return (
      <div className="my-4 p-4 bg-surface-50 border border-surface-200 rounded-xl">
        <p className="text-[10px] font-semibold text-surface-400 uppercase tracking-wide mb-2">知识结构图</p>
        {fallbackNodes.length > 0 ? (
          <ul className="space-y-0.5">
            {fallbackNodes.slice(0, 15).map((node, i) => (
              <li key={i} className="text-xs text-surface-500 flex items-center gap-1.5">
                <span className="w-1 h-1 rounded-full bg-surface-300 flex-shrink-0" />
                {node || '(节点)'}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-surface-400">图表数据暂无法解析</p>
        )}
      </div>
    );
  }

  return (
    <div className="my-4 p-4 bg-white border border-surface-200 rounded-xl overflow-x-auto">
      <p className="text-[10px] font-semibold text-surface-400 uppercase tracking-wide mb-2">知识结构图</p>
      <div dangerouslySetInnerHTML={{ __html: svg }} className="flex justify-center" />
    </div>
  );
}

export default function Markdown({ content }: Props) {
  return (
    <div className="prose-custom text-sm text-surface-700 leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#374151' }]]}
        components={{
          code({ className, children, ...rest }: any) {
            const match = /language-(\w+)/.exec(className || '');
            const str = String(children).replace(/\n$/, '');
            if (match && match[1] === 'mermaid') {
              return <MermaidBlock definition={str} />;
            }
            if (match) {
              return (
                <div className="my-4 rounded-xl overflow-hidden border border-surface-200 shadow-sm">
                  <div className="flex items-center gap-1.5 px-4 py-2 bg-surface-800 text-surface-300 text-[10px] font-medium uppercase tracking-wide">{match[1]}</div>
                  <SyntaxHighlighter style={oneLight} language={match[1]} PreTag="div" customStyle={{ borderRadius: 0, fontSize: '0.8125rem', margin: 0, padding: '1rem' }}>{str}</SyntaxHighlighter>
                </div>
              );
            }
            return <code className="px-1.5 py-0.5 bg-rose-50 text-rose-600 rounded text-[0.85em] font-mono" {...rest}>{children}</code>;
          },
          a({ href, children }: any) {
            return <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline underline-offset-2 hover:text-blue-700">{children}</a>;
          },
          img({ src, alt }: any) {
            return <img src={src} alt={alt} className="rounded-xl max-w-full my-4 shadow-sm" loading="lazy" />;
          },
          h1({ children }: any) {
            return <h1 className="text-2xl font-bold text-surface-900 mt-10 mb-5 pb-3 border-b-2 border-surface-200 tracking-tight">{children}</h1>;
          },
          h2({ children }: any) {
            return <h2 className="text-xl font-bold text-surface-800 mt-10 mb-4 flex items-center gap-3 before:content-[''] before:w-1.5 before:h-6 before:rounded-full before:bg-blue-500">{children}</h2>;
          },
          h3({ children }: any) {
            return <h3 className="text-base font-bold text-surface-800 mt-8 mb-3 pl-3 border-l-2 border-surface-300">{children}</h3>;
          },
          p({ children }: any) {
            return <p className="my-3 text-surface-700 leading-relaxed text-[15px]">{children}</p>;
          },
          ul({ children }: any) {
            return <ul className="my-4 pl-6 space-y-2 list-disc text-surface-700 marker:text-blue-400">{children}</ul>;
          },
          ol({ children }: any) {
            return <ol className="my-4 pl-6 space-y-2 list-decimal text-surface-700 marker:text-surface-400 marker:text-sm marker:font-semibold">{children}</ol>;
          },
          li({ children }: any) {
            return <li className="pl-1 leading-relaxed">{children}</li>;
          },
          blockquote({ children }: any) {
            return (
              <div className="my-5 pl-5 py-3.5 pr-4 bg-amber-50/80 border-l-[3px] border-amber-400 rounded-r-xl shadow-sm">
                <div className="flex items-center gap-1.5 mb-1.5 text-[10px] font-bold text-amber-600 uppercase tracking-wider">重点</div>
                <div className="text-sm text-amber-900 leading-relaxed">{children}</div>
              </div>
            );
          },
          table({ children }: any) {
            return <div className="my-5 overflow-x-auto rounded-xl border border-surface-200 shadow-sm"><table className="min-w-full text-sm [&_tr:nth-child(even)]:bg-surface-50/50">{children}</table></div>;
          },
          th({ children }: any) {
            return <th className="px-5 py-3 bg-surface-100 text-left text-xs font-bold text-surface-500 uppercase tracking-wider border-b-2 border-surface-200">{children}</th>;
          },
          td({ children }: any) {
            return <td className="px-5 py-3 border-b border-surface-100 text-surface-700 leading-relaxed">{children}</td>;
          },
          strong({ children }: any) {
            return <strong className="font-bold text-surface-900">{children}</strong>;
          },
          em({ children }: any) {
            return <em className="italic text-surface-600">{children}</em>;
          },
          hr() {
            return <hr className="my-10 border-surface-100" />;
          },
        }}
      >
        {normalizeBareLatex(content)}
      </ReactMarkdown>
    </div>
  );
}
