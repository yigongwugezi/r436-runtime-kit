import { useState, forwardRef, useImperativeHandle } from 'react';
import { Sparkles, ArrowLeft, ChevronRight, X, Trash2, MessageCircle } from 'lucide-react';

type GenCardStatus = 'generating' | 'ready' | 'error';

interface GenCard {
  id: string;
  type: string;
  title: string;
  content?: string;
  requirements?: string;
  status: GenCardStatus;
  quizData?: {
    questions: any[];
    quizId: string;
    answers: Record<string, string>;
    results: any[];
    totalScore: number | null;
    submitted: boolean;
  };
}

export interface GeneratePanelHandle {
  /** 开始一条生成记录，返回卡片 ID。调用方在生成完成后用 updateRecord 更新状态 */
  beginRecord(type: string, title: string, requirements?: string): string;
  /** 更新一条已有的生成记录 */
  updateRecord(cardId: string, updates: { status: GenCardStatus; content?: string; quizData?: GenCard['quizData'] }): void;
  /** 删除一条生成记录 */
  deleteRecord(cardId: string): void;
}

interface Props {
  sessionId: string;
  activeSectionId: string;
  currentSection: any;
  chapterCtx: any;
  lecture: string;
  generating: boolean;
  genAll: boolean;
  onViewContent: (c: GenCard) => void;
  onGenerateAll: () => void;
  /** 父组件收到 cardId + requirements 后调 API，完成后通过 ref.updateRecord 更新卡片 */
  onGenerateLecture: (cardId: string, requirements?: string) => void;
  onGenerateQuiz: (cardId: string, requirements?: string) => void;
  onGenerateVideo: (cardId: string, requirements?: string) => void;
  onGenerateReading: (cardId: string, requirements?: string) => void;
  onGeneratePractice: (cardId: string, requirements?: string) => void;
  onGenerateMindmap?: (cardId: string, requirements?: string) => void;
}

const TYPES = [
  { type: 'lecture', label: '课程教材', desc: '正式出版级别的教材内容' },
  { type: 'quiz', label: '练习题目', desc: '选择题/判断题/简答题' },
  { type: 'mindmap', label: '思维导图', desc: '知识点结构可视化' },
  { type: 'video', label: '教学视频', desc: '微课视频脚本/动画' },
  { type: 'reading', label: '拓展阅读', desc: '背景知识/进阶材料' },
  { type: 'practice', label: '实操案例', desc: '代码/实验/项目实践' },
] as const;

const GeneratePanel = forwardRef<GeneratePanelHandle, Props>(function GeneratePanel(props, ref) {
  const storageKey = `gen_cards_${props.activeSectionId}`;

  const [cards, setCards] = useState<GenCard[]>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || '[]');
      // 迁移旧数据：把 loading 转为 status，保留 quizData
      return saved.map((c: any) => ({
        ...c,
        status: (c.quizData?.questions || c.content) ? 'ready' : (c.loading ? 'generating' : 'ready'),
      } as GenCard));
    } catch { return []; }
  });

  const [subTab, setSubTab] = useState('');
  const [reqDialog, setReqDialog] = useState<{ type: string; label: string } | null>(null);
  const [requirements, setRequirements] = useState('');

  const persist = (next: GenCard[]) => {
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* noop */ }
  };

  const deleteCard = (cardId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setCards(prev => { const next = prev.filter(c => c.id !== cardId); persist(next); return next; });
  };

  const clearCardsByType = (type: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setCards(prev => { const next = prev.filter(c => c.type !== type); persist(next); return next; });
  };

  // ── 暴露给父组件的记录接口 ──
  useImperativeHandle(ref, () => ({
    beginRecord(type: string, title: string, requirements?: string): string {
      const id = Date.now().toString();
      const card: GenCard = { id, type, title, requirements, status: 'generating' };
      setCards(prev => { const next = [...prev, card]; persist(next); return next; });
      return id;
    },
    updateRecord(cardId: string, updates: { status: GenCardStatus; content?: string; quizData?: GenCard['quizData'] }) {
      setCards(prev => {
        const next = prev.map(c => c.id === cardId ? { ...c, ...updates } : c);
        persist(next);
        return next;
      });
    },
    deleteRecord(cardId: string) {
      setCards(prev => {
        const next = prev.filter(c => c.id !== cardId);
        persist(next);
        return next;
      });
    },
  }), []);

  // ── 打开需求确认对话框 ──
  const openReqDialog = (type: string, label: string) => {
    setReqDialog({ type, label });
    setRequirements('');
  };

  // ── 确认生成：创建记录 → 通知父组件调 API ──
  const confirmGenerate = () => {
    if (!reqDialog) return;
    const { type, label } = reqDialog;
    const cardTitle = requirements ? `${label}（${requirements.slice(0, 20)}${requirements.length > 20 ? '…' : ''}）` : label;
    const card: GenCard = { id: Date.now().toString(), type, title: cardTitle, requirements: requirements || undefined, status: 'generating' };
    setCards(prev => { const next = [...prev, card]; persist(next); return next; });
    setReqDialog(null);
    const req = requirements.trim() || undefined;
    setRequirements('');
    switch (type) {
      case 'lecture': props.onGenerateLecture(card.id, req); break;
      case 'quiz': props.onGenerateQuiz(card.id, req); break;
      case 'mindmap': props.onGenerateMindmap?.(card.id, req); break;
      case 'video': props.onGenerateVideo(card.id, req); break;
      case 'reading': props.onGenerateReading(card.id, req); break;
      case 'practice': props.onGeneratePractice(card.id, req); break;
    }
  };

  const filteredCards = cards.filter(c => !subTab || c.type === subTab);

  // ══════════════════════════════════════════════════════════
  // 二级视图：按类型查看记录
  // ══════════════════════════════════════════════════════════
  if (subTab) {
    const ti = TYPES.find(t => t.type === subTab);
    return (
      <div className="flex flex-col flex-1 min-h-0">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-surface-100 flex-shrink-0">
          <button onClick={() => setSubTab('')} className="flex items-center gap-1 text-xs text-surface-500 hover:text-surface-700"><ArrowLeft size={14} />返回</button>
          <span className="text-xs font-semibold text-surface-700">{ti?.label}</span>
          <span className="text-[10px] text-surface-400 ml-auto">{filteredCards.length} 条</span>
          {filteredCards.length > 0 && (
            <button onClick={(e) => clearCardsByType(subTab, e)} title="清空此类记录"
              className="w-5 h-5 rounded hover:bg-red-50 flex items-center justify-center text-surface-300 hover:text-red-500 transition-colors">
              <Trash2 size={12} />
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {reqDialog && reqDialog.type === subTab && (
            <div className="p-4 rounded-xl bg-white border-2 border-primary-300 shadow-sm space-y-3 animate-fade-in-up">
              <div className="flex items-center gap-2">
                <MessageCircle size={14} className="text-primary-500" />
                <p className="text-xs font-semibold text-surface-700">生成「{reqDialog.label}」</p>
              </div>
              <p className="text-[11px] text-surface-500 leading-relaxed">
                系统将基于当前小节「<span className="font-medium text-surface-700">{props.currentSection?.title || '—'}</span>」的内容
                为你生成{reqDialog.label}。你可以提出特殊要求来定制生成结果。
              </p>
              <textarea value={requirements} onChange={e => setRequirements(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); confirmGenerate(); }
                }}
                placeholder={"例如：多放几道例题、难度高一点、重点讲微积分、用更通俗的语言…"}
                rows={3} autoFocus
                className="w-full px-3 py-2 bg-surface-50 border border-surface-200 rounded-lg text-xs focus:outline-none focus:border-primary-400 resize-none" />
              <div className="flex gap-2">
                <button onClick={confirmGenerate}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 bg-accent-500 text-white rounded-lg text-xs font-semibold hover:bg-accent-600 transition-colors"
                  style={{ backgroundColor: '#14b8a6' }}>
                  <Sparkles size={12} />{requirements.trim() ? '按需求生成' : '直接生成'}
                </button>
                <button onClick={() => setReqDialog(null)}
                  className="px-3 py-2 bg-surface-100 text-surface-600 rounded-lg text-xs hover:bg-surface-200 transition-colors">取消</button>
              </div>
            </div>
          )}

          {filteredCards.length === 0 && (
            <p className="text-xs text-surface-400 text-center py-8">暂无记录，点击下方按钮生成</p>
          )}

          {filteredCards.map(c => (
            <div key={c.id}
              onClick={() => {
                if (c.status === 'ready') props.onViewContent(c);
                else if (c.status === 'error') openReqDialog(c.type, TYPES.find(t => t.type === c.type)?.label || c.title);
              }}
              className={`relative group p-3 rounded-xl border transition-colors cursor-pointer
                ${c.status === 'generating' ? 'bg-surface-50 border-surface-100' :
                  c.status === 'error' ? 'bg-red-50 border-red-200 hover:border-red-400' :
                  'bg-surface-50 border-surface-200 hover:border-surface-400'}`}>
              <button onClick={(e) => deleteCard(c.id, e)}
                className="absolute top-2 right-2 w-5 h-5 rounded opacity-0 group-hover:opacity-100 hover:bg-red-100 flex items-center justify-center text-surface-300 hover:text-red-500 transition-all"
                title="删除记录">
                <X size={11} />
              </button>
              <span className="text-xs font-medium text-surface-700 pr-4">{c.title}</span>
              {c.status === 'generating' ? (
                <p className="text-[10px] text-surface-400 mt-0.5 flex items-center gap-1">
                  <div className="w-2.5 h-2.5 border-2 border-surface-300 border-t-surface-400 rounded-full animate-spin" />生成中…
                </p>
              ) : c.status === 'error' ? (
                <p className="text-[10px] text-red-500 mt-0.5">生成失败 · 点击重试</p>
              ) : (
                <p className="text-[10px] text-surface-400 mt-0.5">已完成 · 点击查看</p>
              )}
            </div>
          ))}

          <button onClick={() => openReqDialog(subTab, ti?.label || subTab)}
            disabled={props.generating || props.genAll || cards.some(c => c.type === subTab && c.status === 'generating')}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-surface-100 text-surface-600 text-xs font-medium hover:bg-surface-200 disabled:opacity-30">
            <Sparkles size={12} />生成新的{ti?.label || ''}
          </button>
        </div>
      </div>
    );
  }

  // ══════════════════════════════════════════════════════════
  // 主视图：资源类型列表
  // ══════════════════════════════════════════════════════════
  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-3">
      <button onClick={props.onGenerateAll} disabled={props.genAll}
        className="w-full flex items-center justify-center gap-2 px-3 py-3 rounded-xl bg-surface-800 text-white text-xs font-semibold hover:bg-surface-900 disabled:opacity-40 transition-colors">
        <Sparkles size={14} />{props.genAll ? '协同生成中…' : '一键生成全部资源'}
      </button>
      <p className="text-[10px] text-surface-400 text-center -mt-2">多智能体协同：画像 → 诊断 → 生成</p>
      <div className="border-t border-surface-100 pt-3">
        <p className="text-[10px] font-medium text-surface-400 uppercase tracking-wide mb-2">生成记录</p>
        <div className="space-y-1">
          {TYPES.map(({ type, label, desc }) => {
            const count = cards.filter(c => c.type === type).length;
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
});

export default GeneratePanel;
