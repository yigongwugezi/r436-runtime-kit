import { useState, useCallback, useMemo } from 'react';
import {
  BookOpen, Brain, ChevronLeft, ChevronRight, Lightbulb,
  CheckCircle2, RefreshCw, Sparkles, ArrowRight, RotateCcw,
  Zap, Target, Hash, Check, X, Volume2, Eye, EyeOff,
} from 'lucide-react';
import Markdown, { splitSections } from '../../utils/markdown';

// ══════════════════════════════════════════════════════════════════════
// Types
// ══════════════════════════════════════════════════════════════════════

export type ContentType = 'lecture' | 'memory_drill' | 'step_through' | 'practice';

export interface SectionContent {
  contentType: ContentType;
  title: string;
  goal: string;
  content: string;
  knowledgePoints: { name: string; type?: string }[];
  // memory_drill specific
  drillItems?: DrillCard[];
  // step_through specific
  steps?: StepItem[];
}

export interface DrillCard {
  front: string;
  back: string;
  hint?: string;
}

export interface StepItem {
  title: string;
  explanation: string;
  keyPoint?: string;
}

interface Props {
  content: SectionContent;
  onComplete?: () => void;
}

// ══════════════════════════════════════════════════════════════════════
// Shared sub-components
// ══════════════════════════════════════════════════════════════════════

function SectionHeader({ title, goal, icon: Icon, kps }: {
  title: string; goal: string; icon: typeof BookOpen; kps: { name: string }[];
}) {
  return (
    <div className="bg-white rounded-2xl shadow-soft p-6 mb-6">
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-violet-500 flex items-center justify-center flex-shrink-0 shadow-lg shadow-blue-500/20">
          <Icon size={22} className="text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-xl font-bold text-surface-900 font-display">{title}</h2>
          <p className="text-sm text-surface-500 mt-1.5 flex items-center gap-1.5">
            <Target size={13} className="text-amber-500 flex-shrink-0" />{goal}
          </p>
          {kps.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {kps.map((kp, i) => (
                <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-surface-100 text-[10px] font-medium text-surface-500">
                  <Hash size={9} />{kp.name}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CompletionFooter({ onComplete }: { onComplete?: () => void }) {
  const [done, setDone] = useState(false);
  if (done) {
    return (
      <div className="mt-8 bg-emerald-50 border border-emerald-200 rounded-2xl p-6 text-center animate-fade-in">
        <div className="w-14 h-14 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-3">
          <CheckCircle2 size={28} className="text-emerald-600" />
        </div>
        <h3 className="text-lg font-bold text-emerald-800 font-display">本节已完成</h3>
        <p className="text-sm text-emerald-600 mt-1">可以继续下一节或做个小测巩固</p>
      </div>
    );
  }
  return (
    <div className="mt-8 flex justify-center">
      <button
        onClick={() => { setDone(true); onComplete?.(); }}
        className="inline-flex items-center gap-2.5 px-8 py-3.5 bg-gradient-to-r from-blue-500 to-violet-500 text-white rounded-2xl font-semibold text-sm shadow-lg shadow-blue-500/25 hover:shadow-xl hover:shadow-blue-500/30 hover:scale-[1.02] active:scale-[0.98] transition-all duration-200"
      >
        <CheckCircle2 size={18} />
        标记完成
      </button>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// MemoryDrillView — flashcard flip UI
// ══════════════════════════════════════════════════════════════════════

function MemoryDrillView({ content, onComplete }: Props) {
  const items = content.drillItems || parseDrillFromMarkdown(content.content);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [known, setKnown] = useState<Set<number>>(new Set());
  const [unknown, setUnknown] = useState<Set<number>>(new Set());
  const [finished, setFinished] = useState(false);

  const card = items[index];
  const total = items.length;
  const reviewed = known.size + unknown.size;
  const progress = total > 0 ? (reviewed / total) * 100 : 0;

  const advance = useCallback((knew: boolean) => {
    const nextKnown = new Set(known);
    const nextUnknown = new Set(unknown);
    if (knew) nextKnown.add(index); else nextUnknown.add(index);
    setKnown(nextKnown);
    setUnknown(nextUnknown);

    if (reviewed + 1 >= total) {
      setFinished(true);
      return;
    }
    setFlipped(false);
    // Find next unreviewed
    let next = (index + 1) % total;
    while (nextKnown.has(next) || nextUnknown.has(next)) {
      next = (next + 1) % total;
      if (next === index) break;
    }
    setIndex(next);
  }, [index, known, unknown, reviewed, total]);

  const restart = () => {
    setIndex(0); setFlipped(false); setKnown(new Set()); setUnknown(new Set()); setFinished(false);
  };

  if (items.length === 0) {
    return (
      <div className="bg-white rounded-2xl shadow-soft p-10 text-center">
        <Brain size={40} className="text-surface-300 mx-auto mb-3" />
        <p className="text-surface-500 text-sm">暂无记忆卡片内容</p>
      </div>
    );
  }

  if (finished) {
    const pct = total > 0 ? Math.round((known.size / total) * 100) : 0;
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="bg-white rounded-2xl shadow-soft p-8 text-center">
          <div className="w-20 h-20 rounded-full bg-gradient-to-br from-emerald-400 to-emerald-500 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-emerald-500/20">
            <Sparkles size={34} className="text-white" />
          </div>
          <h3 className="text-2xl font-bold text-surface-900 font-display">复习完成！</h3>
          <p className="text-surface-500 mt-2">
            已掌握 <span className="font-bold text-emerald-600">{known.size}</span> / {total} 张卡片（{pct}%）
          </p>
          {unknown.size > 0 && (
            <div className="mt-6 p-5 bg-amber-50 border border-amber-200 rounded-2xl text-left">
              <p className="text-xs font-semibold text-amber-700 mb-3 flex items-center gap-1.5">
                <RefreshCw size={12} />需要复习的卡片
              </p>
              <div className="space-y-2">
                {Array.from(unknown).map(i => (
                  <div key={i} className="flex items-start gap-2.5 text-sm">
                    <span className="text-amber-500 mt-0.5">•</span>
                    <div>
                      <p className="font-medium text-surface-800">{items[i].front}</p>
                      <p className="text-xs text-surface-500 mt-0.5">{items[i].back}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="flex items-center justify-center gap-3 mt-6">
            <button onClick={restart}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-surface-100 text-surface-600 rounded-xl text-sm font-medium hover:bg-surface-200 transition-colors">
              <RotateCcw size={15} />重新复习
            </button>
            <CompletionFooter onComplete={onComplete} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeader title={content.title} goal={content.goal} icon={Brain} kps={content.knowledgePoints} />

      {/* Progress bar */}
      <div className="bg-white rounded-2xl shadow-soft p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-surface-500">记忆进度</span>
          <span className="text-xs font-bold text-surface-700">{reviewed}/{total}</span>
        </div>
        <div className="h-2 bg-surface-100 rounded-full overflow-hidden">
          <div className="h-full bg-gradient-to-r from-violet-400 to-blue-500 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }} />
        </div>
        <div className="flex justify-between mt-2 text-[10px] text-surface-400">
          <span>✅ {known.size} 已掌握</span>
          <span>🔄 {unknown.size} 待复习</span>
        </div>
      </div>

      {/* Flashcard */}
      <div className="perspective-1000">
        <div
          onClick={() => setFlipped(!flipped)}
          className={`relative w-full min-h-[240px] rounded-2xl cursor-pointer transition-all duration-500 shadow-soft hover:shadow-elevated
            ${flipped
              ? 'bg-gradient-to-br from-violet-50 to-blue-50 border-2 border-violet-200 shadow-violet-100/50'
              : 'bg-white border-2 border-surface-200 hover:border-blue-300'}`}
          style={{ transformStyle: 'preserve-3d' }}
        >
          {/* Card number badge */}
          <div className="absolute top-4 left-4 px-2.5 py-1 rounded-lg bg-surface-100 text-[10px] font-bold text-surface-400">
            {index + 1} / {total}
          </div>

          {/* Content */}
          <div className="flex flex-col items-center justify-center min-h-[240px] p-10 pt-12 text-center">
            {!flipped ? (
              <>
                <p className="text-sm font-medium text-surface-400 mb-4 flex items-center gap-1.5">
                  <Eye size={14} />点击翻转查看答案
                </p>
                <p className="text-2xl font-bold text-surface-900 font-display leading-relaxed">
                  {card.front}
                </p>
                {card.hint && (
                  <p className="mt-3 text-xs text-surface-400 italic flex items-center gap-1">
                    <Lightbulb size={11} />{card.hint}
                  </p>
                )}
              </>
            ) : (
              <>
                <p className="text-sm font-medium text-violet-500 mb-4 flex items-center gap-1.5">
                  <EyeOff size={14} />答案
                </p>
                <p className="text-xl font-bold text-violet-800 font-display leading-relaxed">
                  {card.back}
                </p>
                <p className="mt-4 text-xs text-surface-400">点击翻转回问题</p>
              </>
            )}
          </div>

          {/* Flip indicator */}
          <div className="absolute bottom-3 right-4 text-[10px] text-surface-300 flex items-center gap-1">
            <RefreshCw size={10} />{flipped ? '点击回正' : '点击翻转'}
          </div>
        </div>
      </div>

      {/* Know / Don't Know buttons */}
      {flipped && (
        <div className="flex gap-4 animate-fade-in">
          <button onClick={() => advance(false)}
            className="flex-1 flex items-center justify-center gap-2.5 py-4 rounded-2xl bg-amber-50 border-2 border-amber-200 text-amber-700 font-semibold text-sm hover:bg-amber-100 hover:border-amber-300 active:scale-[0.98] transition-all duration-150">
            <X size={18} />还不熟练
          </button>
          <button onClick={() => advance(true)}
            className="flex-1 flex items-center justify-center gap-2.5 py-4 rounded-2xl bg-emerald-50 border-2 border-emerald-200 text-emerald-700 font-semibold text-sm hover:bg-emerald-100 hover:border-emerald-300 active:scale-[0.98] transition-all duration-150">
            <Check size={18} />已经掌握
          </button>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// StepThroughView — step-by-step derivation walkthrough
// ══════════════════════════════════════════════════════════════════════

function StepThroughView({ content, onComplete }: Props) {
  const steps: StepItem[] = content.steps || parseStepsFromMarkdown(content.content);
  const [currentStep, setCurrentStep] = useState(0);
  const [revealed, setRevealed] = useState<Set<number>>(new Set([0]));
  const total = steps.length;

  const goNext = () => {
    if (currentStep < total - 1) {
      const next = currentStep + 1;
      setCurrentStep(next);
      setRevealed(prev => new Set(prev).add(next));
    }
  };
  const goPrev = () => { if (currentStep > 0) setCurrentStep(currentStep - 1); };

  if (steps.length === 0) {
    return (
      <div className="bg-white rounded-2xl shadow-soft p-10 text-center">
        <Zap size={40} className="text-surface-300 mx-auto mb-3" />
        <p className="text-surface-500 text-sm">暂无分步讲解内容</p>
      </div>
    );
  }

  const step = steps[currentStep];

  return (
    <div className="space-y-6">
      <SectionHeader title={content.title} goal={content.goal} icon={Zap} kps={content.knowledgePoints} />

      {/* Step progress dots */}
      <div className="bg-white rounded-2xl shadow-soft p-4">
        <div className="flex items-center gap-2 justify-center">
          {steps.map((s, i) => (
            <button
              key={i}
              onClick={() => revealed.has(i) && setCurrentStep(i)}
              disabled={!revealed.has(i)}
              className={`w-8 h-8 rounded-xl flex items-center justify-center text-[10px] font-bold transition-all duration-300
                ${i === currentStep ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/30 scale-110' :
                  revealed.has(i) ? 'bg-blue-100 text-blue-600 hover:bg-blue-200 cursor-pointer' :
                  'bg-surface-100 text-surface-300 cursor-not-allowed'}`}
            >
              {i + 1}
            </button>
          ))}
        </div>
        <p className="text-center text-[10px] text-surface-400 mt-3">
          第 {currentStep + 1} 步 / 共 {total} 步
          {revealed.size < total && <span className="text-surface-300 ml-1">（逐步解锁）</span>}
        </p>
      </div>

      {/* Step card */}
      <div className="bg-white rounded-2xl shadow-soft overflow-hidden animate-fade-in">
        {/* Step header */}
        <div className="bg-gradient-to-r from-blue-500 to-violet-500 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-white/20 flex items-center justify-center text-white font-bold text-sm">
              {currentStep + 1}
            </div>
            <div>
              <h3 className="text-lg font-bold text-white font-display">{step.title}</h3>
            </div>
          </div>
        </div>

        {/* Step body */}
        <div className="p-6">
          <div className="prose prose-sm max-w-none">
            <Markdown content={step.explanation} />
          </div>

          {step.keyPoint && (
            <div className="mt-5 p-4 bg-amber-50 border border-amber-200 rounded-2xl flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                <Lightbulb size={15} className="text-amber-600" />
              </div>
              <div>
                <p className="text-xs font-semibold text-amber-700 mb-0.5">关键点</p>
                <p className="text-sm text-amber-800">{step.keyPoint}</p>
              </div>
            </div>
          )}
        </div>

        {/* Step navigation */}
        <div className="px-6 pb-5 flex items-center justify-between">
          <button onClick={goPrev} disabled={currentStep === 0}
            className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-medium transition-all
              disabled:opacity-30 disabled:cursor-not-allowed
              text-surface-500 hover:bg-surface-100 active:scale-[0.98]">
            <ChevronLeft size={16} />上一步
          </button>

          {currentStep < total - 1 ? (
            <button onClick={goNext}
              className="inline-flex items-center gap-2 px-6 py-2.5 bg-blue-500 text-white rounded-xl text-sm font-semibold
                hover:bg-blue-600 active:scale-[0.98] shadow-lg shadow-blue-500/20 transition-all duration-150">
              下一步<ArrowRight size={16} />
            </button>
          ) : (
            <CompletionFooter onComplete={onComplete} />
          )}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Default Markdown Lecture View (existing behavior, enhanced)
// ══════════════════════════════════════════════════════════════════════

function MarkdownLectureView({ content, onComplete }: Props) {
  const sections = useMemo(() => splitSections(content.content), [content.content]);

  return (
    <div className="space-y-6">
      <SectionHeader title={content.title} goal={content.goal} icon={BookOpen} kps={content.knowledgePoints} />

      {sections.length > 0 ? (
        sections.map((sec, i) => (
          <div key={i} className="bg-white rounded-2xl shadow-soft p-6 animate-fade-in">
            <div className="prose prose-sm max-w-none prose-headings:font-display prose-h2:text-lg prose-h3:text-base prose-code:bg-surface-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:text-sm prose-pre:bg-surface-900 prose-pre:text-surface-100">
              <Markdown content={sec.content} />
            </div>
          </div>
        ))
      ) : (
        <div className="bg-white rounded-2xl shadow-soft p-10 text-center">
          <BookOpen size={40} className="text-surface-300 mx-auto mb-3" />
          <p className="text-surface-500 text-sm">点击上方「生成讲义」按钮生成本节内容</p>
        </div>
      )}

      {sections.length > 0 && <CompletionFooter onComplete={onComplete} />}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Helpers: extract structured data from Markdown when not provided
// ══════════════════════════════════════════════════════════════════════

function parseDrillFromMarkdown(md: string): DrillCard[] {
  const items: DrillCard[] = [];
  // Pattern: **word** — meaning / **front** — back
  const lines = md.split('\n');
  for (const line of lines) {
    const match = line.match(/^\s*\*\*(.+?)\*\*\s*[—\-–]\s*(.+)$/);
    if (match) {
      items.push({ front: match[1].trim(), back: match[2].trim() });
      continue;
    }
    // Pattern: - word: meaning
    const match2 = line.match(/^\s*[-•]\s*(.+?)\s*[:：]\s*(.+)$/);
    if (match2 && match2[1].length < 50) {
      items.push({ front: match2[1].trim(), back: match2[2].trim() });
    }
  }
  return items;
}

function parseStepsFromMarkdown(md: string): StepItem[] {
  const items: StepItem[] = [];
  // Pattern: ### Step N: Title or ## 第N步
  const stepRegex = /^#{2,3}\s*(?:Step\s*\d+[：:]\s*|第[一二三四五六七八九十\d]+步[：:\s]*)(.+)$/gm;
  const matches = [...md.matchAll(stepRegex)];
  if (matches.length === 0) {
    // Fallback: split by ## headings
    const sections = splitSections(md);
    return sections.map(s => ({
      title: s.title || '',
      explanation: s.content,
      keyPoint: extractKeyPoint(s.content),
    }));
  }
  for (let i = 0; i < matches.length; i++) {
    const start = matches[i].index! + matches[i][0].length;
    const end = i < matches.length - 1 ? matches[i + 1].index! : md.length;
    const body = md.slice(start, end).trim();
    items.push({
      title: matches[i][1].trim(),
      explanation: body,
      keyPoint: extractKeyPoint(body),
    });
  }
  return items;
}

function extractKeyPoint(text: string): string | undefined {
  const match = text.match(/(?:关键点|要点|重点|核心)[：:]\s*(.+?)(?:\n|$)/);
  return match ? match[1].trim() : undefined;
}

// ══════════════════════════════════════════════════════════════════════
// Content Type Router
// ══════════════════════════════════════════════════════════════════════

export default function SectionContentRouter({ content, onComplete }: Props) {
  const ct = content.contentType;

  switch (ct) {
    case 'memory_drill':
      return <MemoryDrillView content={content} onComplete={onComplete} />;
    case 'step_through':
      return <StepThroughView content={content} onComplete={onComplete} />;
    case 'lecture':
    default:
      return <MarkdownLectureView content={content} onComplete={onComplete} />;
  }
}

export { MarkdownLectureView, MemoryDrillView, StepThroughView };
