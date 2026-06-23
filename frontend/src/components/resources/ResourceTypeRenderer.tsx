import { useState } from 'react';
import Markdown from '../../utils/markdown';
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
 * Lecture — 讲义：标题、重点、讲解、例子、总结
 * =================================================================== */
function LectureRenderer({ resource }: Props) {
  return (
    <div>
      <div className="mb-4 p-3 bg-blue-50/70 border border-blue-100 rounded-xl">
        <p className="text-xs text-blue-700 font-medium">📖 课程讲义</p>
        <p className="text-[10px] text-blue-500 mt-0.5">系统根据你的学习画像和课程知识库生成的个性化讲义</p>
      </div>
      <LongContent content={resource.content || ''} />
    </div>
  );
}

/* ===================================================================
 * Reading — 拓展阅读
 * =================================================================== */
function ReadingRenderer({ resource }: Props) {
  return (
    <div>
      <div className="mb-4 p-3 bg-emerald-50/70 border border-emerald-100 rounded-xl">
        <p className="text-xs text-emerald-700 font-medium">📚 拓展阅读</p>
        <p className="text-[10px] text-emerald-500 mt-0.5">以下内容属于扩展知识，理解核心概念后可选择性阅读</p>
      </div>
      <LongContent content={resource.content || ''} />
    </div>
  );
}

/* ===================================================================
 * Mindmap — 思维导图
 * =================================================================== */
function MindmapRenderer({ resource }: Props) {
  return (
    <div>
      <div className="mb-4 p-3 bg-purple-50/70 border border-purple-100 rounded-xl">
        <p className="text-xs text-purple-700 font-medium">🧠 思维导图</p>
        <p className="text-[10px] text-purple-500 mt-0.5">知识结构可视化，帮助你快速建立整体框架</p>
      </div>
      {resource.mermaidDef ? (
        <div className="p-4 bg-white rounded-xl border border-gray-100 overflow-x-auto">
          <pre className="text-xs text-gray-500 font-mono whitespace-pre-wrap">{resource.mermaidDef}</pre>
          <p className="text-[10px] text-gray-400 mt-2">💡 思维导图需要 Mermaid 支持渲染</p>
        </div>
      ) : (
        <Markdown content={resource.content || ''} />
      )}
    </div>
  );
}

/* ===================================================================
 * Quiz — 练习题（配合 QuizAnswerer）
 * =================================================================== */
function QuizRenderer({ resource }: Props) {
  if (resource.questions && resource.questions.length > 0) {
    return (
      <div>
        <div className="mb-4 p-3 bg-amber-50/70 border border-amber-100 rounded-xl">
          <p className="text-xs text-amber-700 font-medium">📝 练习题</p>
          <p className="text-[10px] text-amber-500 mt-0.5">完成以下题目检验掌握程度，提交后可查看解析</p>
        </div>
        <div className="space-y-4">
          {resource.questions.map((q, i) => (
            <div key={q.id || i} className="p-4 bg-white border border-gray-100 rounded-xl">
              <p className="text-xs font-semibold text-gray-800 mb-2">
                {i + 1}. {q.stem}
              </p>
              {q.options && q.options.length > 0 && (
                <div className="space-y-1.5 ml-2">
                  {q.options.map((opt, oi) => (
                    <div key={oi} className="flex items-center gap-2 text-xs text-gray-600">
                      <span className="w-5 h-5 rounded-full bg-gray-50 border border-gray-200 flex items-center justify-center text-[10px] font-medium text-gray-400">
                        {String.fromCharCode(65 + oi)}
                      </span>
                      {opt}
                    </div>
                  ))}
                </div>
              )}
              {q.answer && (
                <details className="mt-2">
                  <summary className="text-[10px] text-brand-500 cursor-pointer hover:text-brand-600">查看答案</summary>
                  <p className="text-xs text-green-600 mt-1">答案：{q.answer}</p>
                  {q.explanation && <p className="text-[10px] text-gray-500 mt-1">{q.explanation}</p>}
                </details>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }
  return <LongContent content={resource.content || ''} />;
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
