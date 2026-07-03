import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import 'katex/dist/katex.min.css';

interface Props {
  content: string;
}

function normalizeBareLatex(content: string) {
  return content
    .replace(/\\\(([\s\S]*?)\\\)/g, (_m, body) => `$${body}$`)
    .replace(/\\\[([\s\S]*?)\\\]/g, (_m, body) => `$$${body}$$`)
    .replace(/(?<![$\\])\\frac\{[^{}]+\}\{[^{}]+\}/g, (m) => `$${m}$`)
    .replace(/(?<![$\\])\\sqrt\{[^{}]+\}/g, (m) => `$${m}$`)
    .replace(/(?<![$\\])\\varphi/g, '$\\varphi$')
    .replace(/(?<![$\\])\\begin\{cases\}([\s\S]*?)\\end\{cases\}/g, (_m, body) => `$$\\begin{cases}${body}\\end{cases}$$`);
}

export default function Markdown({ content }: Props) {
  return (
    <div className="prose-custom text-sm text-gray-800 leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#374151' }]]}
        components={{
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          code({ className, children, ...rest }: any) {
            const match = /language-(\w+)/.exec(className || '');
            const str = String(children).replace(/\n$/, '');
            if (match) {
              return (
                <SyntaxHighlighter
                  style={oneLight}
                  language={match[1]}
                  PreTag="div"
                  customStyle={{ borderRadius: '0.75rem', fontSize: '0.8125rem', margin: 0 }}
                >
                  {str}
                </SyntaxHighlighter>
              );
            }
            return <code className={className} {...rest}>{children}</code>;
          },
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          a({ href, children }: any) {
            return <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand-600 underline underline-offset-2">{children}</a>;
          },
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          img({ src, alt }: any) {
            return <img src={src} alt={alt} className="rounded-xl max-w-full" loading="lazy" />;
          },
        }}
      >
        {normalizeBareLatex(content)}
      </ReactMarkdown>
    </div>
  );
}
