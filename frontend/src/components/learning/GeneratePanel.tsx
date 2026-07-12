import { useState, useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, ArrowLeft, ChevronRight } from 'lucide-react';
import MermaidDiagram from '../../utils/mermaid';
import Markdown from '../../utils/markdown';

interface GenCard { type: string; title: string; id: string; content?: string; loading?: boolean; }

interface Props {
  sessionId: string;
  activeSectionId: string;
  currentSection: any;
  chapterCtx: any;
  path: any;
  lecture: string;
  onViewContent: (content: any) => void;
  onGenerateLecture: () => void;
  onGenerateQuiz: () => void;
  onGenerateVideo: () => void;
  onGenerateReading: () => void;
  onGeneratePractice: () => void;
  onGenerateAll: () => void;
  generating: boolean;
  genAll: boolean;
}

const TYPES = [
  { type: 'lecture', label: '课程讲义', desc: '专业课程讲解文档' },
  { type: 'quiz', label: '练习题目', desc: '选择题/判断题/简答题' },
  { type: 'mindmap', label: '思维导图', desc: '知识点结构可视化' },
  { type: 'video', label: '教学视频', desc: '微课视频脚本/动画' },
  { type: 'reading', label: '拓展阅读', desc: '背景知识/进阶材料' },
  { type: 'practice', label: '实操案例', desc: '代码/实验/项目实践' },
] as const;

export default function GeneratePanel(props: Props) {
  const nav = useNavigate();
  const storageKey = `gen_cards_${props.activeSectionId}`;
  const [cards, setCards] = useState<GenCard[]>(() => {
    try { return JSON.parse(localStorage.getItem(storageKey) || '[]'); } catch { return []; }
  });
  const [subTab, setSubTab] = useState('');
  const [mindmapLoading, setMindmapLoading] = useState(false);
  const [genMindmap, setGenMindmap] = useState<any>(null);
  const [namePrompt, setNamePrompt] = useState<{type:string;label:string}|null>(null);
  const [customName, setCustomName] = useState('');

  const updateCard = (type: string, title: string, updates: Partial<GenCard>) => setCards(prev => {
    const next = prev.map(c => c.type === type && c.title === title && c.loading ? { ...c, ...updates, loading: false } : c);
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch {}
    return next;
  });

  const addCard = (c: GenCard) => setCards(prev => {
    const next = [...prev, c];
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch {}
    return next;
  });

  const startGenerate = (type: string, label: string, name: string) => {
    setNamePrompt(null);
    const title = name || label || '';
    const cardId = Date.now().toString();
    addCard({ type, title, id: cardId, loading: true });
    const h = handlers[type];
    if (h) (h as any)(title, cardId);
  };

  const handlers: Record<string, (title: string, cardId: string) => void> = {
    lecture: (title, cardId) => { props.onGenerateLecture(); updateCard('lecture', title, { content: props.lecture || '已生成', id: props.activeSectionId }); },
    quiz: (title, cardId) => { props.onGenerateQuiz(); updateCard('quiz', title, { content: '已生成', id: props.activeSectionId }); },
    mindmap: async (title, cardId) => {
      if (!props.chapterCtx?.chapter.id || !props.sessionId) return;
      try {
        const { generateChapterMindmap } = await import('../../api/sectionResources');
        const r = await generateChapterMindmap(props.chapterCtx.chapter.id, { sessionId: props.sessionId, regenerate: false, knowledgePoints: props.currentSection?.knowledgePoints || [] });
        const mm = (r as any)?.mindmap || (r as any);
        setGenMindmap(mm);
        updateCard('mindmap', title, { content: mm?.mermaidDef || '已生成', id: props.chapterCtx.chapter.id });
      } catch {}
    },
    video: (title, cardId) => { props.onGenerateVideo(); updateCard('video', title, { content: '已生成', id: props.activeSectionId }); },
    reading: (title, cardId) => { props.onGenerateReading(); updateCard('reading', title, { content: '已生成', id: props.activeSectionId }); },
    practice: (title, cardId) => { props.onGeneratePractice(); updateCard('practice', title, { content: '已生成', id: props.activeSectionId }); },
  };

  // Persist genAll cards when generation completes
  const prevGenAll = useRef(props.genAll);
  useEffect(() => {
    if (prevGenAll.current && !props.genAll) {
      const genCards: GenCard[] = [
        { type: 'lecture', title: props.currentSection?.title || '讲义', id: props.activeSectionId, content: props.lecture, loading: false },
        { type: 'quiz', title: '练习题', id: props.activeSectionId, loading: false },
        { type: 'mindmap', title: '思维导图', id: props.chapterCtx?.chapter.id || '', loading: false },
        { type: 'video', title: '教学视频', id: props.activeSectionId, loading: false },
        { type: 'reading', title: '拓展阅读', id: props.activeSectionId, loading: false },
        { type: 'practice', title: '实操案例', id: props.activeSectionId, loading: false },
      ];
      try { localStorage.setItem(storageKey, JSON.stringify(genCards)); } catch {}
      setCards(genCards);
    }
    prevGenAll.current = props.genAll;
  }, [props.genAll]);

  const allCards = props.genAll ? [
    { type: 'lecture', title: props.currentSection?.title || '讲义', id: props.activeSectionId, content: props.lecture, loading: false } as GenCard,
    { type: 'quiz', title: '练习题', id: props.activeSectionId, loading: false } as GenCard,
    { type: 'mindmap', title: '思维导图', id: props.chapterCtx?.chapter.id || '', loading: false } as GenCard,
    { type: 'video', title: '教学视频', id: props.activeSectionId, loading: false } as GenCard,
    { type: 'reading', title: '拓展阅读', id: props.activeSectionId, loading: false } as GenCard,
    { type: 'practice', title: '实操案例', id: props.activeSectionId, loading: false } as GenCard,
  ] : cards;

  if (subTab) {
    const typeCards = allCards.filter(c => c.type === subTab);
    const tabInfo = TYPES.find(t => t.type === subTab);
    return (
      <div className="flex flex-col flex-1 min-h-0">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-surface-100 flex-shrink-0">
          <button onClick={() => setSubTab('')} className="flex items-center gap-1 text-xs text-surface-500 hover:text-surface-700"><ArrowLeft size={14} />返回</button>
          <span className="text-xs font-semibold text-surface-700">{tabInfo?.label}</span>
          <span className="text-[10px] text-surface-400 ml-auto">{typeCards.length} 个</span>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {/* Name prompt */}
          {namePrompt && namePrompt.type === subTab && (
            <div className="p-3 rounded-xl bg-surface-50 border border-surface-200 space-y-2">
              <p className="text-[10px] text-surface-500">为「{namePrompt.label}」命名</p>
              <input value={customName} onChange={e => setCustomName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') startGenerate(namePrompt.type, namePrompt.label, customName || namePrompt.label); }}
                placeholder={tabInfo?.label || '输入名称'} autoFocus
                className="w-full px-3 py-2 bg-white border border-surface-200 rounded-lg text-xs focus:outline-none focus:border-surface-400" />
              <div className="flex gap-2">
                <button onClick={() => startGenerate(namePrompt.type, namePrompt.label, customName || namePrompt.label || '')}
                  className="flex-1 px-3 py-2 bg-surface-800 text-white rounded-lg text-xs font-medium">确定</button>
                <button onClick={() => setNamePrompt(null)}
                  className="px-3 py-2 bg-surface-100 text-surface-600 rounded-lg text-xs">取消</button>
              </div>
            </div>
          )}
          {typeCards.map((c, i) => (
            <div key={i} onClick={() => {
              if (c.loading) return;
              if (!c.content && c.type !== 'mindmap') return;
              props.onViewContent(c);
            }}
              className="p-3 rounded-xl bg-surface-50 border border-surface-200 hover:border-surface-400 cursor-pointer">
              <span className="text-xs font-medium text-surface-700">{c.title}</span>
              {c.loading ? (
                <p className="text-[10px] text-surface-400 mt-0.5 flex items-center gap-1"><div className="w-2.5 h-2.5 border-2 border-surface-300 border-t-surface-400 rounded-full animate-spin" />生成中…</p>
              ) : (
                <p className="text-[10px] text-surface-400 mt-0.5">已完成 · 点击查看</p>
              )}
            </div>
          ))}
          <button onClick={() => { setNamePrompt({ type: subTab, label: tabInfo?.label || subTab }); setCustomName(''); }}
            disabled={props.generating || props.genAll}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-surface-100 text-surface-600 text-xs font-medium hover:bg-surface-200 disabled:opacity-30">
            <Sparkles size={12} />{tabInfo?.label ? `生成新的${tabInfo.label}` : '生成'}
          </button>
          {subTab === 'mindmap' && genMindmap?.mermaidDef && (
            <div className="rounded-xl bg-surface-50 border border-surface-200 p-2 overflow-auto"><MermaidDiagram definition={genMindmap.mermaidDef} /></div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-3">
      <button onClick={props.onGenerateAll} disabled={props.genAll}
        className="w-full flex items-center justify-center gap-2 px-3 py-3 rounded-xl bg-surface-800 text-white text-xs font-semibold hover:bg-surface-900 disabled:opacity-40 transition-colors">
        <Sparkles size={14} />{props.genAll ? '协同生成中…' : '一键生成全部资源'}
      </button>
      <p className="text-[10px] text-surface-400 text-center -mt-2">多智能体协同：画像 → 诊断 → 生成</p>
      <div className="border-t border-surface-100 pt-3">
        <p className="text-[10px] font-medium text-surface-400 uppercase tracking-wide mb-2">按类型生成</p>
        <div className="space-y-1">
          {TYPES.map(({ type, label, desc }) => {
            const count = allCards.filter(c => c.type === type).length;
            return (
              <button key={type} onClick={() => setSubTab(type)}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg bg-surface-50 hover:bg-surface-100 transition-colors text-left">
                <span className="text-xs font-medium text-surface-700 flex-1">{label}</span>
                <span className="text-[10px] text-surface-400 hidden sm:inline">{desc}</span>
                {count > 0 && <span className="px-1.5 py-0.5 rounded-full bg-surface-200 text-[10px] font-medium text-surface-600">{count}</span>}
                <ChevronRight size={14} className="text-surface-300" />
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
