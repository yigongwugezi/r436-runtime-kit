import { useState, useEffect, useRef } from 'react';
import Markdown from '../../utils/markdown';
import { renderMermaid } from '../../utils/mermaid';
import type { Resource, CodeBlock, QuizQuestion, PptSlide } from '../../types/resource';

/* ===================================================================
 * LongContent — 超长内容折叠
 * =================================================================== */
function LongContent({ content, children, maxLen = 1500 }: {
  content: string;
  children?: React.ReactNode;
  maxLen?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const shouldTruncate = content.length > maxLen;
  const display = shouldTruncate && !expanded ? content.slice(0, maxLen) + '…' : content;
  return (
    <div>
      {children}
      <Markdown content={display} />
      {shouldTruncate && (
        <button onClick={() => setExpanded(!expanded)}
          className="mt-2 px-3 py-1.5 rounded-lg text-xs font-medium text-brand-500 bg-brand-50 hover:bg-brand-100 transition-colors">
          {expanded ? '收起' : `展开全部（共 ${content.length} 字）`}
        </button>
      )}
    </div>
  );
}

/* ===================================================================
 * 按类型渲染资源内容
 * =================================================================== */
interface Props {
  resource: Resource;
}

export default function ResourceTypeRenderer({ resource }: Props) {
  switch (resource.type) {
    case 'lecture':
      return <LectureRenderer resource={resource} />;
    case 'reading':
      return <ReadingRenderer resource={resource} />;
    case 'mindmap':
      return <MindmapRenderer resource={resource} />;
    case 'quiz':
      return <QuizRenderer resource={resource} />;
    case 'case_study':
      return <PracticeRenderer resource={resource} />;
    case 'video':
      return <VideoRenderer resource={resource} />;
    case 'ppt':
      return <PptRenderer resource={resource} />;
    default:
      return <Markdown content={resource.content || ''} />;
  }
}

/* ===================================================================
 * DocRenderer — 讲义/阅读公共组件：侧边目录导航 + 结构化渲染
 * =================================================================== */
function DocRenderer({ resource, type }: Props & { type: 'lecture' | 'reading' }) {
  const content = resource.content || '';
  const isLecture = type === 'lecture';

  // 提取 h2/h3 标题作为目录
  const headings = [...content.matchAll(/^(#{2,3})\s+(.+)$/gm)].map((m) => ({
    level: m[1].length,
    text: m[2].trim(),
    id: m[2].trim().replace(/\s+/g, '-').replace(/[^\w一-鿿-]/g, ''),
  }));

  // 给内容中的标题加 id 锚点
  let enrichedContent = content;
  let offset = 0;
  for (const h of headings) {
    const pattern = `${'#'.repeat(h.level)} ${h.text}`;
    const idx = enrichedContent.indexOf(pattern, offset);
    if (idx >= 0) {
      const anchor = `\n${'#'.repeat(h.level)} <span id="${h.id}">${h.text}</span>\n`;
      enrichedContent = enrichedContent.slice(0, idx) + anchor + enrichedContent.slice(idx + pattern.length);
      offset = idx + anchor.length;
    }
  }

  // 提取关键概念块（--- 或 > **重点** 包裹的内容）
  const conceptBlocks = [...content.matchAll(/> \*\*(重点|关键|核心|注意|考点|提示)\*\*[：:]\s*(.+)/g)];

  return (
    <div className="flex gap-6">
      {/* 侧边目录导航 */}
      {headings.length >= 3 && (
        <nav className="hidden lg:block w-48 flex-shrink-0">
          <div className="sticky top-4 space-y-1 max-h-[70vh] overflow-y-auto pr-2">
            <p className="text-[10px] font-semibold text-surface-400 uppercase tracking-wider mb-2">目录导航</p>
            {headings.map((h, i) => (
              <a key={i} href={`#${h.id}`}
                 className={`block text-xs py-1 transition-colors hover:text-brand-500 ${h.level === 2 ? 'pl-0 font-medium text-surface-600' : 'pl-3 text-surface-400'}`}
                 onClick={(e) => { e.preventDefault(); document.getElementById(h.id)?.scrollIntoView({ behavior: 'smooth' }); }}>
                {h.text}
              </a>
            ))}
          </div>
        </nav>
      )}

      {/* 正文区 */}
      <div className="flex-1 min-w-0">
        <div className={`mb-6 p-4 rounded-xl border ${isLecture ? 'bg-blue-50/70 border-blue-100' : 'bg-emerald-50/70 border-emerald-100'}`}>
          <div className="flex items-center gap-3">
            <span className="text-2xl">{isLecture ? '📖' : '📚'}</span>
            <div>
              <p className={`text-sm font-semibold ${isLecture ? 'text-blue-700' : 'text-emerald-700'}`}>
                {isLecture ? '课程讲义' : '拓展阅读'}
              </p>
              <p className="text-xs text-surface-500 mt-0.5">
                {resource.title} · 约 {Math.ceil(content.length / 500)} 分钟阅读
              </p>
            </div>
          </div>
          {/* 知识点标签 */}
          {resource.knowledgePoints && resource.knowledgePoints.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {resource.knowledgePoints.slice(0, 6).map((kp: string, i: number) => (
                <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-white/60 border border-surface-200 text-surface-500">{kp}</span>
              ))}
            </div>
          )}
        </div>

        {/* 关键概念卡片 */}
        {conceptBlocks.length > 0 && (
          <div className="mb-6 p-4 bg-amber-50/70 border border-amber-200 rounded-xl">
            <p className="text-xs font-semibold text-amber-700 mb-2">💡 关键概念速览</p>
            <ul className="space-y-1.5">
              {conceptBlocks.map((cb, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-surface-600">
                  <span className="text-amber-400 mt-0.5">✦</span>
                  <span><strong>{cb[1]}</strong>：{cb[2]}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Markdown 正文 */}
        <div className="prose prose-sm max-w-none prose-headings:text-surface-800 prose-h2:text-lg prose-h2:font-bold prose-h2:mt-8 prose-h2:mb-3 prose-h2:pb-2 prose-h2:border-b prose-h2:border-surface-100 prose-h3:text-base prose-h3:font-semibold prose-h3:mt-6 prose-h3:mb-2 prose-p:text-surface-600 prose-p:leading-relaxed prose-li:text-surface-600 prose-code:text-brand-600 prose-code:bg-brand-50 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-pre:bg-surface-800 prose-pre:text-surface-100 prose-table:text-xs prose-th:bg-surface-50 prose-th:font-medium prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-2">
          <LongContent content={enrichedContent} maxLen={3000} />
        </div>
      </div>
    </div>
  );
}

/* ===================================================================
 * Lecture — 讲义：使用 DocRenderer
 * =================================================================== */
function LectureRenderer({ resource }: Props) {
  return <DocRenderer resource={resource} type="lecture" />;
}

/* ===================================================================
 * Reading — 拓展阅读：使用 DocRenderer
 * =================================================================== */
function ReadingRenderer({ resource }: Props) {
  return <DocRenderer resource={resource} type="reading" />;
}

/* ===================================================================
 * Mindmap — 思维导图（Mermaid 实时渲染）
 * =================================================================== */
function MindmapRenderer({ resource }: Props) {
  const mermaidCode = resource.mermaidDef || resource.content || '';
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!mermaidCode || !containerRef.current) return;
    let cancelled = false;
    renderMermaid(containerRef.current, mermaidCode)
      .then((result) => { if (!cancelled) { setSvg(result); setError(null); } })
      .catch((e: any) => { if (!cancelled) setError(e?.message || String(e)); });
    return () => { cancelled = true; };
  }, [mermaidCode]);

  return (
    <div>
      <div className="mb-4 p-3 bg-purple-50/70 border border-purple-100 rounded-xl">
        <p className="text-xs text-purple-700 font-medium">🧠 思维导图</p>
        <p className="text-[10px] text-purple-500 mt-0.5">知识结构可视化，可缩放拖拽查看</p>
      </div>
      <div className="p-4 bg-white rounded-xl border border-gray-100 overflow-auto" style={{ minHeight: 200 }}>
        <div ref={containerRef} className="flex items-center justify-center" />
        {svg && <div dangerouslySetInnerHTML={{ __html: svg }} className="flex items-center justify-center [&>svg]:max-w-full [&>svg]:h-auto" />}
        {error && (
          <details className="mt-3">
            <summary className="text-[10px] text-gray-400 cursor-pointer">渲染失败，查看源码</summary>
            <pre className="text-xs text-gray-500 font-mono whitespace-pre-wrap mt-1 p-2 bg-gray-50 rounded">{mermaidCode}</pre>
          </details>
        )}
      </div>
    </div>
  );
}

/* ===================================================================
 * Quiz — 交互式练习题（支持选择+填空+判分）
 * =================================================================== */
function QuizRenderer({ resource }: Props) {
  const questions = resource.questions || [];
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});

  const handleSelect = (qId: string, val: string) => {
    if (revealed[qId]) return;
    setAnswers((a) => ({ ...a, [qId]: val }));
  };
  const handleReveal = (qId: string) => {
    setRevealed((r) => ({ ...r, [qId]: true }));
  };

  if (questions.length === 0) return <LongContent content={resource.content || ''} />;

  return (
    <div>
      <div className="mb-4 p-3 bg-amber-50/70 border border-amber-100 rounded-xl">
        <p className="text-xs text-amber-700 font-medium">📝 练习题（共 {questions.length} 题）</p>
        <p className="text-[10px] text-amber-500 mt-0.5">点击选项作答，提交后查看解析</p>
      </div>
      <div className="space-y-4">
        {questions.map((q: any, i: number) => {
          const qId = q.question_id || q.id || String(i);
          const selected = answers[qId] || '';
          const show = revealed[qId];
          const isCorrect = show && q.answer ? (selected === q.answer || selected === q.correct) : null;

          return (
            <div key={qId} className={`p-4 border rounded-xl transition-all ${show ? (isCorrect ? 'bg-success-50/50 border-success-200' : 'bg-error-50/50 border-error-200') : 'bg-white border-gray-100'}`}>
              <p className="text-sm font-semibold text-gray-800 mb-3">
                <span className="text-brand-500 mr-2">{i + 1}.</span>{q.stem || q.question}
              </p>

              {/* 选择题 */}
              {q.options && q.options.length > 0 && (
                <div className="space-y-2">
                  {q.options.map((opt: string, oi: number) => {
                    const letter = String.fromCharCode(65 + oi);
                    const isSelected = selected === letter;
                    let cls = 'border-gray-200 hover:border-primary-300 cursor-pointer';
                    if (show && letter === (q.answer || q.correct)) cls = 'border-success-400 bg-success-50';
                    else if (show && isSelected && !isCorrect) cls = 'border-error-400 bg-error-50';
                    else if (isSelected && !show) cls = 'border-primary-400 bg-primary-50';

                    return (
                      <button key={oi} disabled={show} onClick={() => handleSelect(qId, letter)}
                        className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition-all ${cls}`}>
                        <span className="font-semibold mr-2 text-xs">{letter}.</span>{opt}
                        {show && letter === (q.answer || q.correct) && <span className="ml-2 text-success-500 text-xs">✓ 正确</span>}
                        {show && isSelected && !isCorrect && <span className="ml-2 text-error-500 text-xs">✗</span>}
                      </button>
                    );
                  })}
                </div>
              )}

              {/* 判断题 */}
              {q.type === 'truefalse' && (
                <div className="flex gap-3">
                  {['true', 'false'].map((val) => {
                    const label = val === 'true' ? '✓ 正确' : '✗ 错误';
                    const isSelected = selected === val;
                    let cls = 'border-gray-200 hover:border-primary-300 cursor-pointer';
                    if (show && val === String(q.correct)) cls = 'border-success-400 bg-success-50';
                    else if (show && isSelected && !isCorrect) cls = 'border-error-400 bg-error-50';
                    else if (isSelected && !show) cls = 'border-primary-400 bg-primary-50';
                    return (
                      <button key={val} disabled={show} onClick={() => handleSelect(qId, val)}
                        className={`flex-1 px-4 py-3 rounded-lg border font-medium transition-all ${cls}`}>{label}</button>
                    );
                  })}
                </div>
              )}

              {/* 查看解析 */}
              {selected && !show && (
                <button onClick={() => handleReveal(qId)}
                  className="mt-3 px-3 py-1.5 rounded-lg text-xs font-medium text-brand-500 bg-brand-50 hover:bg-brand-100">
                  提交查看解析
                </button>
              )}

              {show && (
                <div className="mt-3 p-3 bg-white/80 rounded-lg text-xs">
                  {isCorrect ? (
                    <p className="text-success-600 font-medium">✓ 回答正确！</p>
                  ) : (
                    <p className="text-error-600 font-medium">✗ 正确答案是 {q.answer || q.correct}</p>
                  )}
                  {(q.explanation || q.misconception_explanation) && (
                    <p className="text-gray-500 mt-1 leading-relaxed">{q.explanation || q.misconception_explanation}</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ===================================================================
 * Case Study / Practice — 实操案例
 * =================================================================== */
function PracticeRenderer({ resource }: Props) {
  return (
    <div>
      <div className="mb-4 p-3 bg-cyan-50/70 border border-cyan-100 rounded-xl">
        <p className="text-xs text-cyan-700 font-medium">💻 实操案例</p>
        <p className="text-[10px] text-cyan-500 mt-0.5">动手实践，将理论知识转化为实际代码能力</p>
      </div>
      <Markdown content={resource.content || ''} />
      {resource.codeBlocks && resource.codeBlocks.length > 0 && (
        <div className="mt-4 space-y-4">
          <p className="text-xs font-semibold text-gray-600">🔧 代码示例</p>
          {resource.codeBlocks.map((block, i) => (
            <div key={i} className="bg-gray-900 text-gray-100 rounded-xl overflow-hidden border border-gray-800">
              {block.language && (
                <div className="px-4 py-1.5 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
                  <span className="text-[10px] text-gray-400 font-mono">{block.language}</span>
                </div>
              )}
              <pre className="text-xs font-mono p-4 overflow-x-auto"><code>{block.code}</code></pre>
              {block.explanation && (
                <div className="px-4 py-2 bg-gray-800/50 border-t border-gray-700">
                  <p className="text-[10px] text-gray-400">{block.explanation}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ===================================================================
 * Video — 视频脚本
 * =================================================================== */
function VideoRenderer({ resource }: Props) {
  return (
    <div>
      <div className="mb-4 p-3 bg-red-50/70 border border-red-100 rounded-xl">
        <p className="text-xs text-red-700 font-medium">🎬 教学视频</p>
        <p className="text-[10px] text-red-500 mt-0.5">视频讲稿或分镜脚本，帮助理解课程内容</p>
      </div>
      {resource.pptOutline && resource.pptOutline.length > 0 ? (
        <div className="space-y-3">
          {resource.pptOutline.map((slide, i) => (
            <div key={i} className="p-4 bg-white border border-gray-100 rounded-xl shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <span className="w-5 h-5 rounded-full bg-red-100 text-red-600 text-[10px] font-bold flex items-center justify-center">
                  {i + 1}
                </span>
                <h4 className="text-sm font-semibold text-gray-800">{slide.title}</h4>
              </div>
              {slide.bullets && slide.bullets.length > 0 && (
                <ul className="space-y-1 ml-7">
                  {slide.bullets.map((b, bi) => (
                    <li key={bi} className="text-xs text-gray-600 list-disc">{b}</li>
                  ))}
                </ul>
              )}
              {slide.notes && (
                <p className="text-[10px] text-gray-400 mt-2 ml-7 italic">💡 {slide.notes}</p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <Markdown content={resource.content || ''} />
      )}
    </div>
  );
}

/* ===================================================================
 * PPT — 幻灯片大纲
 * =================================================================== */
function PptRenderer({ resource }: Props) {
  return (
    <div>
      <div className="mb-4 p-3 bg-orange-50/70 border border-orange-100 rounded-xl">
        <p className="text-xs text-orange-700 font-medium">📊 PPT 大纲</p>
        <p className="text-[10px] text-orange-500 mt-0.5">幻灯片结构总览，方便快速浏览核心内容</p>
      </div>
      {resource.pptOutline && resource.pptOutline.length > 0 ? (
        <div className="space-y-3">
          {resource.pptOutline.map((slide, i) => (
            <div key={i} className="p-4 bg-white border border-gray-100 rounded-xl shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <span className="w-5 h-5 rounded-full bg-orange-100 text-orange-600 text-[10px] font-bold flex items-center justify-center">
                  {i + 1}
                </span>
                <h4 className="text-sm font-semibold text-gray-800">{slide.title}</h4>
              </div>
              {slide.bullets && slide.bullets.length > 0 && (
                <ul className="space-y-1 ml-7">
                  {slide.bullets.map((b, bi) => (
                    <li key={bi} className="text-xs text-gray-600 list-disc">{b}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      ) : (
        <Markdown content={resource.content || ''} />
      )}
    </div>
  );
}
