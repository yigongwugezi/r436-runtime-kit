// @ts-nocheck
import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Search, BookOpen, Brain, Code, FileText, Lightbulb, Play, Presentation, Clock, Star, ChevronRight, BookmarkPlus, BookmarkCheck, CheckCircle2, X, LayoutGrid, List, ChevronDown, MoreHorizontal, RotateCcw, ListChecks, Download, SlidersHorizontal, MessageSquare, Send, ArrowLeft } from 'lucide-react';
import { useResources } from '../hooks/useResources';
import { useChatStore } from '../store/chatStore';
import { getResourceById, updateStudyStatus, autoAdvanceNode, getResourceKnowledgeGraph, batchUpdateStudyStatus, batchSetBookmark, batchExportResources } from '../api/resources';
import { submitFeedback, logStudyEvent } from '../api/feedback';
import type { Resource, ResourceType } from '../types/resource';
import { RESOURCE_TYPE_LABELS } from '../utils/constants';
import { timeAgo, formatDuration } from '../utils/format';
import { PageLoading, PageEmpty, PageError } from '../components/common/PageState';
import SourceBadge from '../components/common/SourceBadge';
import Markdown from '../utils/markdown';
import MermaidDiagram from '../utils/mermaid';

const icons: Record<string, React.ReactNode> = {
  lecture: <BookOpen className="w-5 h-5 text-blue-500" />, mindmap: <Brain className="w-5 h-5 text-purple-500" />,
  quiz: <FileText className="w-5 h-5 text-amber-500" />, reading: <Lightbulb className="w-5 h-5 text-green-500" />,
  case_study: <Code className="w-5 h-5 text-cyan-500" />, video: <Play className="w-5 h-5 text-red-500" />, ppt: <Presentation className="w-5 h-5 text-orange-500" />
};
const colorMap: Record<string, { bg: string; text: string }> = {
  lecture: { bg: 'bg-blue-50', text: 'text-blue-600' }, mindmap: { bg: 'bg-purple-50', text: 'text-purple-600' },
  quiz: { bg: 'bg-amber-50', text: 'text-amber-600' }, reading: { bg: 'bg-emerald-50', text: 'text-emerald-600' },
  case_study: { bg: 'bg-cyan-50', text: 'text-cyan-600' }, video: { bg: 'bg-red-50', text: 'text-red-600' }, ppt: { bg: 'bg-orange-50', text: 'text-orange-600' }
};
const diffBadge: Record<string, string> = { easy: 'bg-success-100 text-success-700', medium: 'bg-warning-100 text-warning-700', hard: 'bg-error-100 text-error-700' };
const diffLabel: Record<string, string> = { easy: '基础', medium: '进阶', hard: '挑战' };
const TYPES = ['', 'lecture', 'mindmap', 'quiz', 'reading', 'case_study', 'video', 'ppt'];
const SORTS = [{ v: 'default', l: '推荐' }, { v: 'newest', l: '最新' }, { v: 'easiest', l: '最简单' }, { v: 'hardest', l: '最困难' }];

function QuizAnswerer({ questions, resourceId }: { questions: any[]; resourceId: string }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  if (!questions?.length) return null;

  const score = submitted ? { correct: questions.filter(q => answers[q.id] === q.answer).length, total: questions.length } : null;

  return (
    <div className="p-4 bg-amber-50/40 border border-amber-100 rounded-xl space-y-3">
      <h4 className="text-sm font-semibold text-surface-700">随堂练习 ({questions.length} 题)</h4>
      {questions.map((q, qi) => (
        <div key={q.id} className="p-3 rounded-xl border bg-white border-surface-200">
          <p className="text-xs font-medium text-surface-800 mb-2">{qi + 1}. {q.stem}</p>
          {q.type === 'choice' && q.options ? (
            <div className="space-y-1">
              {q.options.map((opt, oi) => {
                const letter = String.fromCharCode(65 + oi); const chosen = answers[q.id] === letter;
                return (
                  <button key={oi} onClick={() => { if (!submitted) setAnswers(prev => ({ ...prev, [q.id]: letter })); }} disabled={submitted}
                    className={`w-full text-left px-3 py-1.5 rounded-lg text-xs transition-all ${submitted && letter === q.answer ? 'bg-success-100 text-success-700' : submitted && chosen && letter !== q.answer ? 'bg-error-100 text-error-600' : chosen ? 'bg-primary-50 text-primary-600 ring-1 ring-primary-200' : 'bg-surface-50 text-surface-600 hover:bg-surface-100'}`}>
                    <span className="font-semibold mr-1.5">{letter}.</span>{opt}{submitted && letter === q.answer && <CheckCircle2 className="w-3 h-3 inline ml-1.5 text-success-500" />}
                  </button>
                );
              })}
            </div>
          ) : (
            <input value={answers[q.id] || ''} onChange={e => { if (!submitted) setAnswers(prev => ({ ...prev, [q.id]: e.target.value })); }} disabled={submitted} placeholder="输入答案…" className="w-full px-3 py-1.5 bg-white border border-surface-200 rounded-lg text-xs outline-none focus:ring-2 focus:ring-primary-200" />
          )}
          {submitted && q.explanation && <p className="text-[10px] text-surface-500 mt-1">📖 {q.explanation}</p>}
        </div>
      ))}
      <div className="flex items-center gap-2">
        {!submitted ? (
          <button onClick={() => setSubmitted(true)} disabled={Object.keys(answers).length < questions.length} className="px-4 py-2 bg-primary-600 text-white rounded-xl text-xs font-semibold hover:bg-primary-700 disabled:opacity-30 transition-colors">提交答案</button>
        ) : (
          <div className="flex items-center gap-2">
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${score?.correct === score?.total ? 'bg-success-100 text-success-600' : 'bg-warning-100 text-warning-600'}`}>{score?.correct}/{score?.total} 正确</span>
            <button onClick={() => { setAnswers({}); setSubmitted(false); }} className="px-3 py-1.5 bg-surface-100 text-surface-600 rounded-lg text-xs font-medium hover:bg-surface-200">重做</button>
          </div>
        )}
        <span className="text-[10px] text-surface-400">已答 {Object.keys(answers).length}/{questions.length}</span>
      </div>
    </div>
  );
}

/* ===================================================================
 * 资源详情视图（页面内嵌）
 * =================================================================== */
function ResourceDetailView({
  resource,
  onBack,
  onBookmark,
  onComplete,
  onRefetch,
}: {
  resource: Resource;
  onBack: () => void;
  onBookmark: (id: string) => void;
  onComplete: (r: Resource) => void;
  onRefetch: () => void;
}) {
  const nav = useNavigate();
  const sessionId = useChatStore(s => s.currentSessionId);
  const [showExplain, setShowExplain] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const [showThanks, setShowThanks] = useState(false);
  const [showKnowledgeGraph, setShowKnowledgeGraph] = useState(false);
  const [kgMermaidDef, setKgMermaidDef] = useState('');
  const [kgLoading, setKgLoading] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState(0);
  const [feedbackCat, setFeedbackCat] = useState('');
  const [feedbackComment, setFeedbackComment] = useState('');

  const c = colorMap[resource.type] || { bg: 'bg-surface-100', text: 'text-surface-500' };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* 返回按钮 */}
      <button
        onClick={onBack}
        className="inline-flex items-center gap-2 px-4 py-2 bg-white rounded-xl shadow-soft text-surface-600 hover:text-surface-800 hover:shadow-elevated transition-all text-sm font-medium"
      >
        <ArrowLeft className="w-4 h-4" />
        返回资源库
      </button>

      {/* 头部卡片 */}
      <div className="bg-white rounded-2xl shadow-soft p-6">
        <div className="flex items-start gap-5">
          <div className={`w-16 h-16 rounded-2xl ${c.bg} flex items-center justify-center flex-shrink-0`}>
            {icons[resource.type]}
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-bold text-surface-800 mb-2">{resource.title}</h1>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <span className={`px-2.5 py-1 rounded-lg text-xs font-medium ${diffBadge[resource.difficulty]}`}>{diffLabel[resource.difficulty]}</span>
              <span className="px-2.5 py-1 rounded-lg text-xs text-surface-500 bg-surface-50">{RESOURCE_TYPE_LABELS[resource.type]}</span>
              <span className="text-xs text-surface-400">· {formatDuration(resource.estimatedMinutes)}</span>
              <span className="text-xs text-surface-400">· {timeAgo(resource.createdAt)}</span>
              <SourceBadge source={resource.source || 'system_inferred'} size="sm" />
              {resource.studyStatus === 'completed' && <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-success-50 text-success-600">✅ 已完成</span>}
            </div>
            <p className="text-sm text-surface-500 leading-relaxed">{resource.description}</p>
          </div>
        </div>
      </div>

      {/* 元信息 */}
      <div className="bg-white rounded-2xl shadow-soft p-5 space-y-3">
        {resource.relatedChapter && (
          <div className="flex items-center gap-2 text-sm text-surface-500">
            <span className="text-surface-400">📖 章节：</span>
            <span className="font-medium text-surface-700">{resource.relatedChapter}</span>
            {resource.relatedStageId && (
              <span className="text-surface-400">· 阶段 {resource.relatedStageId.replace(/[^0-9]/g, '')}</span>
            )}
          </div>
        )}
        {resource.knowledgePoints?.length > 0 && (
          <div className="flex items-start gap-2">
            <span className="text-sm text-surface-400 flex-shrink-0 mt-0.5">🧩 知识点：</span>
            <div className="flex flex-wrap gap-1.5">
              {resource.knowledgePoints.map((kp: string) => (
                <span key={kp} className="px-2 py-0.5 bg-primary-50 text-primary-600 rounded-md text-[10px] font-medium">{kp}</span>
              ))}
            </div>
          </div>
        )}
        {resource.tags?.length > 0 && (
          <div className="flex items-start gap-2">
            <span className="text-sm text-surface-400 flex-shrink-0 mt-0.5">🏷️ 标签：</span>
            <div className="flex flex-wrap gap-1.5">
              {resource.tags.map((t: string) => (
                <span key={t} className="px-2 py-0.5 bg-surface-100 text-surface-500 rounded-md text-[10px] font-medium">{t}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 操作按钮 */}
      <div className="bg-white rounded-2xl shadow-soft p-5">
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => setShowExplain(!showExplain)} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-surface-50 text-surface-500 rounded-lg text-xs font-medium hover:bg-surface-100 transition-colors">🛡️ {showExplain ? '收起解释' : '可信解释'}</button>
          <button onClick={() => onBookmark(resource.id)} className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${resource.bookmarked ? 'bg-primary-50 text-primary-600 border-primary-200' : 'bg-white text-surface-500 border-surface-200 hover:border-primary-300'}`}>
            {resource.bookmarked ? <BookmarkCheck className="w-3.5 h-3.5" /> : <BookmarkPlus className="w-3.5 h-3.5" />}{resource.bookmarked ? '已收藏' : '收藏'}
          </button>
          <button onClick={() => onComplete(resource)} className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${resource.studyStatus === 'completed' ? 'bg-warning-50 text-warning-700 hover:bg-warning-100' : 'bg-success-50 text-success-700 hover:bg-success-100'}`}><CheckCircle2 className="w-3.5 h-3.5" />{resource.studyStatus === 'completed' ? '撤销完成' : '标记完成'}</button>
          <button onClick={async () => {
            if (showKnowledgeGraph) { setShowKnowledgeGraph(false); return; }
            setKgLoading(true);
            try {
              const res = await getResourceKnowledgeGraph(resource.id, { sessionId });
              setKgMermaidDef(res.mermaidDef || '');
              setShowKnowledgeGraph(true);
            } catch { setKgMermaidDef(''); setShowKnowledgeGraph(true); }
            finally { setKgLoading(false); }
          }} className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${showKnowledgeGraph ? 'bg-accent-50 text-accent-700' : 'bg-surface-50 text-surface-500 hover:bg-surface-100'}`}>🧠 {kgLoading ? '加载中…' : showKnowledgeGraph ? '收起图谱' : '知识图谱'}</button>
          <button onClick={() => nav('/chat')} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary-50 text-primary-700 rounded-lg text-xs font-medium hover:bg-primary-100">✏️ 去提问</button>
          <button onClick={() => nav('/analytics')} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-surface-50 text-surface-500 rounded-lg text-xs font-medium hover:bg-surface-100">📊 学习分析</button>
        </div>
      </div>

      {/* 内容区 */}
      {resource.content && (
        <div className="bg-white rounded-2xl shadow-soft p-6">
          <div className="prose-custom">
            {(resource.type === 'lecture' || resource.type === 'reading') && <Markdown content={resource.content} />}
            {resource.type === 'mindmap' && (resource.mermaidDef ? <div className="p-4 bg-white rounded-xl border border-surface-200"><MermaidDiagram definition={resource.mermaidDef} /></div> : <Markdown content={resource.content} />)}
            {resource.type === 'quiz' && resource.questions?.length > 0 ? <QuizAnswerer questions={resource.questions} resourceId={resource.id} /> : resource.type !== 'mindmap' ? <Markdown content={resource.content || '暂无内容'} /> : null}
            {resource.type === 'case_study' && resource.codeBlocks?.length > 0 && <div className="space-y-4 mt-4">{resource.codeBlocks.map((b, i) => <div key={i} className="bg-surface-800 text-surface-100 rounded-xl overflow-hidden"><div className="px-4 py-1.5 bg-surface-700 text-[10px]">{b.language || 'code'}</div><pre className="text-xs p-4 overflow-x-auto"><code>{b.code}</code></pre></div>)}</div>}
            {(resource.type === 'video' || resource.type === 'ppt') && resource.pptOutline?.length > 0 && <div className="space-y-3">{resource.pptOutline.map((s, i) => <div key={i} className="p-4 bg-white border border-surface-200 rounded-xl"><div className="flex items-center gap-2 mb-2"><span className="w-5 h-5 rounded-full bg-primary-100 text-primary-600 text-[10px] font-bold flex items-center justify-center">{i + 1}</span><h4 className="text-sm font-semibold text-surface-800">{s.title}</h4></div>{s.bullets?.length > 0 && <ul className="space-y-1 ml-7">{s.bullets.map((b, bi) => <li key={bi} className="text-xs text-surface-600 list-disc">{b}</li>)}</ul>}</div>)}</div>}
          </div>
        </div>
      )}

      {/* 可信解释面板 */}
      {showExplain && (
        <div className="bg-white rounded-2xl shadow-soft p-5 space-y-3 animate-fade-in">
          <h3 className="text-sm font-semibold text-surface-700">🛡️ 可信解释</h3>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div><span className="text-surface-400">来源类型：</span><span className="font-medium text-surface-700">{(resource as any).sourceType ? ((resource as any).sourceType === 'llm_generated' ? '大模型生成' : (resource as any).sourceType === 'rule_based' ? '规则生成' : (resource as any).sourceType === 'knowledge_base' ? '知识库检索' : (resource as any).sourceType) : resource.source === 'agent_generated' ? '智能体生成' : resource.source === 'system_inferred' ? '系统推断' : resource.source === 'fallback' ? '兜底' : '用户输入'}</span></div>
            <div><span className="text-surface-400">生成方式：</span><span className="font-medium text-surface-700">{(resource as any).generationMode === 'direct_generation' ? '直接生成' : (resource as any).generationMode === 'knowledge_retrieval' ? '知识检索' : (resource as any).generationMode === 'hybrid' ? '混合生成' : (resource as any).generationMode === 'rule_fallback' ? '规则兜底' : '大模型生成'}</span></div>
          </div>
          {(resource as any).reason && <div className="p-3 bg-primary-50 border border-primary-100 rounded-xl"><p className="text-xs font-semibold text-primary-700 mb-1">💡 推荐理由</p><p className="text-[11px] text-primary-600">{(resource as any).reason}</p></div>}
          {(resource as any).fallbackReason && <div className="p-3 bg-warning-50 border border-warning-100 rounded-xl"><p className="text-xs font-semibold text-warning-700 mb-1">⚠️ 兜底说明</p><p className="text-[11px] text-warning-600">{(resource as any).fallbackReason}</p></div>}
          {(resource as any).evidence && (resource as any).evidence.length > 0 && <div><p className="text-xs text-surface-400 mb-1">📋 依据来源</p><ul className="space-y-1">{(resource as any).evidence.map((ev: string, i: number) => <li key={i} className="text-[11px] text-surface-600">• {ev}</li>)}</ul></div>}
          {resource.qualityStatus && <div className="text-xs"><span className="text-surface-400">质检状态：</span><span className={`font-medium ${resource.qualityStatus === 'passed' ? 'text-success-600' : resource.qualityStatus === 'fallback_passed' ? 'text-warning-600' : 'text-error-600'}`}>{resource.qualityStatus === 'passed' ? '已通过 ✓' : resource.qualityStatus === 'fallback_passed' ? '兜底通过 🛡' : '需人工复核 ⚠'}</span></div>}
        </div>
      )}

      {/* 知识图谱面板 */}
      {showKnowledgeGraph && (
        <div className="bg-white rounded-2xl shadow-soft p-5 space-y-3 animate-fade-in">
          <h3 className="text-sm font-semibold text-surface-700 flex items-center gap-2">🧠 知识图谱</h3>
          {kgMermaidDef ? (
            <div className="p-4 bg-white rounded-xl border border-surface-200">
              <MermaidDiagram definition={kgMermaidDef} />
            </div>
          ) : (
            <p className="text-xs text-surface-500">暂无知识图谱数据</p>
          )}
        </div>
      )}

      {/* 反馈区 */}
      {!showFeedback && !showThanks && (
        <button onClick={() => setShowFeedback(true)} className="inline-flex items-center gap-1.5 px-4 py-2 bg-white rounded-xl shadow-soft text-surface-500 text-xs font-medium hover:bg-surface-50 transition-colors"><MessageSquare className="w-3.5 h-3.5" />评价这份资源</button>
      )}
      {showFeedback && (
        <div className="bg-white rounded-2xl shadow-soft p-5 space-y-3 animate-fade-in">
          <h4 className="text-sm font-semibold text-surface-700 flex items-center gap-2"><MessageSquare className="w-4 h-4 text-primary-500" />对这份资源评价</h4>
          <div className="flex flex-wrap gap-1.5">
            {[{ v: 'helpful', l: '👍 有帮助' }, { v: 'too_hard', l: '😓 太难' }, { v: 'too_easy', l: '😅 太简单' }, { v: 'unclear', l: '🤔 不清楚' }, { v: 'other', l: '💬 其他' }].map(cat => (
              <button key={cat.v} onClick={() => setFeedbackCat(feedbackCat === cat.v ? '' : cat.v)} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${feedbackCat === cat.v ? 'bg-primary-600 text-white' : 'bg-white border border-surface-200 text-surface-500 hover:border-primary-300'}`}>{cat.l}</button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            {[1, 2, 3, 4, 5].map(i => <button key={i} onClick={() => setFeedbackRating(i)} className="transition-transform hover:scale-110"><Star className="w-5 h-5" fill={feedbackRating >= i ? '#f59e0b' : 'none'} stroke={feedbackRating >= i ? '#f59e0b' : '#d1d5db'} strokeWidth={1.5} /></button>)}
          </div>
          <textarea value={feedbackComment} onChange={e => setFeedbackComment(e.target.value)} placeholder="更多想法…（选填）" rows={2} className="w-full resize-none bg-white border border-surface-200 rounded-xl px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-primary-200" />
          <div className="flex items-center gap-2">
            <button onClick={async () => {
              try {
                await submitFeedback({ sessionId: useChatStore.getState().currentSessionId, resourceId: resource.id, rating: feedbackRating, category: feedbackCat, comment: feedbackComment || undefined });
                await logStudyEvent({ event: 'feedback', resourceId: resource.id, sessionId: useChatStore.getState().currentSessionId, metadata: { rating: feedbackRating, feedbackType: feedbackCat } });
              } catch { }
              setShowFeedback(false);
              setShowThanks(true);
            }} className="px-4 py-2 bg-primary-600 text-white rounded-xl text-xs font-semibold hover:bg-primary-700 flex items-center gap-1.5"><Send className="w-3 h-3" />提交评价</button>
            <button onClick={() => setShowFeedback(false)} className="px-3 py-2 text-xs text-surface-400 hover:text-surface-600">取消</button>
          </div>
        </div>
      )}

      {showThanks && (
        <div className="bg-white rounded-2xl shadow-soft p-4 border border-success-200">
          <div className="flex items-center gap-2 text-xs text-success-600"><CheckCircle2 className="w-4 h-4" />感谢你的反馈！</div>
        </div>
      )}

      <p className="text-[10px] text-surface-400 text-center pt-2">AI 生成内容仅供参考</p>
    </div>
  );
}

/* ===================================================================
 * 资源库列表视图
 * =================================================================== */
function ResourceListView({
  resources: allResources,
  total,
  loading,
  error,
  onRefetch,
  onToggleBookmark,
  onApplyFilter,
  sessionId,
  activeTaskId,
  activeStageId,
}: {
  resources: Resource[];
  total: number;
  loading: boolean;
  error: string;
  onRefetch: () => void;
  onToggleBookmark: (id: string) => Promise<void>;
  onApplyFilter: (u: any) => void;
  sessionId: string | null;
  activeTaskId?: string;
  activeStageId?: string;
}) {
  const nav = useNavigate();

  const [view, setView] = useState<'grid' | 'list'>('grid');
  const [search, setSearch] = useState('');
  const [activeType, setActiveType] = useState('');
  const [activeDiff, setActiveDiff] = useState('');
  const [activeSort, setActiveSort] = useState('default');
  const [showExtra, setShowExtra] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [activeSource, setActiveSource] = useState('');
  const [activeQuality, setActiveQuality] = useState('');
  const [activeStudyStatus, setActiveStudyStatus] = useState('');
  const [bookmarkedFilter, setBookmarkedFilter] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const updateFilters = useCallback((u: any) => {
    if ('type' in u) setActiveType(u.type || '');
    if ('search' in u) setSearch(u.search || '');
    if ('difficulty' in u) setActiveDiff(u.difficulty || '');
    if ('sortBy' in u) setActiveSort(u.sortBy || 'default');
    if ('studyStatus' in u) setActiveStudyStatus(u.studyStatus || '');
    onApplyFilter(u);
  }, [onApplyFilter]);

  const handleBatch = async (action: string) => {
    const ids = Array.from(selectedIds);
    if (!ids.length) return;
    try {
      if (action === 'complete') await batchUpdateStudyStatus(useChatStore.getState().currentSessionId, ids, 'completed');
      else if (action === 'bookmark') await batchSetBookmark(useChatStore.getState().currentSessionId, ids, true);
      else if (action === 'export') {
        const r = await batchExportResources(useChatStore.getState().currentSessionId, ids);
        const blob = new Blob([r.export], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = 'resources_export.txt'; a.click();
        URL.revokeObjectURL(url);
      }
      setSelectedIds(new Set()); setSelectionMode(false);
      onRefetch();
    } catch (e) {
      setErrorMsg('批量操作失败');
      setTimeout(() => setErrorMsg(''), 3000);
    }
  };

  let filtered = allResources || [];
  if (search) filtered = filtered.filter(r => r.title?.includes(search) || r.description?.includes(search));
  if (activeType) filtered = filtered.filter(r => r.type === activeType);
  if (activeDiff) filtered = filtered.filter(r => r.difficulty === activeDiff);
  if (activeSource) filtered = filtered.filter(r => r.source === activeSource);
  if (activeQuality) filtered = filtered.filter(r => r.qualityStatus === activeQuality);
  if (bookmarkedFilter) filtered = filtered.filter(r => r.bookmarked);
  if (activeSort === 'newest') filtered = [...filtered].sort((a, b) => new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime());
  if (activeSort === 'easiest') filtered = [...filtered].sort((a, b) => (a.estimatedMinutes || 0) - (b.estimatedMinutes || 0));
  if (activeSort === 'hardest') filtered = [...filtered].sort((a, b) => (b.estimatedMinutes || 0) - (a.estimatedMinutes || 0));

  return (
    <div className="space-y-6 animate-fade-in">
      {errorMsg && <div className="fixed top-4 right-4 z-50 px-4 py-2 bg-error-50 border border-error-200 text-error-600 rounded-xl text-xs shadow-soft">{errorMsg}</div>}

      {(activeTaskId || activeStageId) && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-primary-50 border border-primary-100 rounded-xl text-sm">
          <BookOpen size={14} className="text-primary-500" />
          <span className="text-primary-700 font-medium">正在查看子阶段关联资源</span>
          <button onClick={() => nav('/resources')} className="ml-2 px-2.5 py-1 bg-white text-primary-600 rounded-lg text-xs font-medium hover:bg-primary-100 transition-colors">查看全部</button>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div><h2 className="font-display text-2xl font-bold text-surface-800">学习资源库</h2><p className="text-surface-500 mt-1">共 {total} 个学习资源{(search || activeType || activeDiff || bookmarkedFilter || activeSource || activeQuality || activeTaskId || activeStageId) ? '（已筛选）' : ''}</p></div>
        <div className="flex items-center gap-3">
          {(search || activeType || activeDiff || bookmarkedFilter || activeSource || activeQuality || activeStudyStatus) && <button onClick={() => { setSearch(''); setActiveType(''); setActiveDiff(''); setActiveSource(''); setActiveQuality(''); setActiveStudyStatus(''); setBookmarkedFilter(false); setActiveSort('default'); setShowExtra(false); onApplyFilter({ sortBy: 'default', type: undefined, difficulty: undefined, source: undefined, qualityStatus: undefined, studyStatus: undefined }); }} className="text-xs text-surface-500 hover:text-surface-700 px-3 py-1.5 rounded-lg border border-surface-200 hover:bg-surface-50"><RotateCcw className="w-3 h-3 inline mr-1" />清空</button>}
          <button onClick={() => setView('grid')} className={`p-2.5 rounded-lg transition-colors ${view === 'grid' ? 'bg-primary-100 text-primary-600' : 'bg-surface-100 text-surface-500'}`}><LayoutGrid size={18} /></button>
          <button onClick={() => setView('list')} className={`p-2.5 rounded-lg transition-colors ${view === 'list' ? 'bg-primary-100 text-primary-600' : 'bg-surface-100 text-surface-500'}`}><List size={18} /></button>
        </div>
      </div>

      <div className="bg-white rounded-2xl p-5 shadow-soft">
        <div className="flex items-center gap-4">
          <div className="flex-1 relative"><Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-surface-400" /><input value={search} onChange={e => { setSearch(e.target.value); }} placeholder="搜索资源…" className="w-full pl-11 pr-4 py-3 bg-surface-50 border border-surface-200 rounded-xl text-surface-800 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all" /></div>
          <div className="flex items-center gap-1.5">
            {SORTS.map(s => <button key={s.v} onClick={() => updateFilters({ sortBy: s.v === 'default' ? undefined : s.v })} className={`px-2.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${activeSort === s.v ? 'bg-surface-800 text-white' : 'bg-surface-100 text-surface-500 hover:bg-surface-200'}`}>{s.l}</button>)}
          </div>
          <button onClick={() => { setSelectionMode(v => !v); if (selectionMode) setSelectedIds(new Set()); }} className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 ${selectionMode ? 'bg-surface-800 text-white' : 'bg-surface-100 text-surface-500 hover:bg-surface-200'}`}><ListChecks size={14} />{selectionMode ? '取消' : '批量'}</button>
          <button onClick={() => setShowExtra(!showExtra)} className={`p-2.5 rounded-lg transition-colors ${showExtra ? 'bg-primary-100 text-primary-600' : 'bg-surface-100 text-surface-500'}`}><SlidersHorizontal size={18} /></button>
        </div>

        <div className="flex items-center gap-3 mt-5 overflow-x-auto py-1">
          <span className="text-sm text-surface-500 flex-shrink-0">类型:</span>
          {TYPES.map(t => { const isSel = activeType === t || (!activeType && !t); const c = colorMap[t] || { bg: 'bg-surface-100', text: 'text-surface-500' }; return <button key={t || 'all'} onClick={() => updateFilters({ type: t || undefined })} className={`flex-shrink-0 px-3 py-1.5 rounded-full text-sm font-medium transition-all ${isSel && t ? `${c.bg} ${c.text} ring-2 ring-offset-1` : !t && isSel ? 'bg-surface-800 text-white' : 'bg-surface-100 text-surface-500 hover:bg-surface-200'}`}>{t ? RESOURCE_TYPE_LABELS[t as ResourceType] || t : '全部'}</button>; })}
        </div>
        <div className="flex items-center gap-3 mt-3 overflow-x-auto py-1">
          <span className="text-sm text-surface-500 flex-shrink-0">难度:</span>
          {['', 'easy', 'medium', 'hard'].map(d => { const isSel = activeDiff === d || (!activeDiff && !d); return <button key={d || 'all'} onClick={() => updateFilters({ difficulty: d || undefined })} className={`flex-shrink-0 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${isSel && d ? 'bg-surface-800 text-white' : !d && isSel ? 'bg-surface-800 text-white' : 'bg-surface-100 text-surface-500 hover:bg-surface-200'}`}>{d ? diffLabel[d] || d : '全部'}</button>; })}
          <div className="w-px h-5 bg-surface-200 mx-1" />
          <button onClick={() => setBookmarkedFilter(!bookmarkedFilter)} className={`flex-shrink-0 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${bookmarkedFilter ? 'bg-warning-100 text-warning-700 ring-2 ring-offset-1' : 'bg-surface-100 text-surface-500 hover:bg-surface-200'}`}>⭐ 已收藏</button>
        </div>

        {showExtra && (
          <div className="space-y-3 mt-3 pt-3 border-t border-surface-100 pb-1">
            <div className="flex items-center gap-3 overflow-x-auto py-1">
              <span className="text-sm text-surface-500 flex-shrink-0">状态:</span>
              {['', 'new', 'in_progress', 'completed'].map(s => { const isSel = activeStudyStatus === s || (!activeStudyStatus && !s); return <button key={s || 'all'} onClick={() => updateFilters({ studyStatus: s || undefined })} className={`flex-shrink-0 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${isSel ? 'bg-surface-800 text-white' : 'bg-surface-100 text-surface-500 hover:bg-surface-200'}`}>{s === 'new' ? '未开始' : s === 'in_progress' ? '学习中' : s === 'completed' ? '已完成' : '全部'}</button>; })}
            </div>
            <div className="flex items-center gap-3 overflow-x-auto py-1">
              <span className="text-sm text-surface-500 flex-shrink-0">来源:</span>
              {['', 'agent_generated', 'system_inferred', 'fallback', 'user_input'].map(s => <button key={s || 'all'} onClick={() => { setActiveSource(s || ''); onApplyFilter({ source: s || undefined }); }} className={`flex-shrink-0 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${activeSource === s ? 'bg-surface-800 text-white' : !s && !activeSource ? 'bg-surface-800 text-white' : 'bg-surface-100 text-surface-500 hover:bg-surface-200'}`}>{s === 'agent_generated' ? '智能体' : s === 'system_inferred' ? '系统推断' : s === 'fallback' ? '兜底' : s === 'user_input' ? '用户' : '全部'}</button>)}
            </div>
            <div className="flex items-center gap-3 overflow-x-auto py-1">
              <span className="text-sm text-surface-500 flex-shrink-0">质检:</span>
              {['', 'passed', 'needs_review', 'fallback_passed'].map(s => <button key={s || 'all'} onClick={() => { setActiveQuality(s || ''); onApplyFilter({ qualityStatus: s || undefined }); }} className={`flex-shrink-0 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${activeQuality === s ? 'bg-surface-800 text-white' : !s && !activeQuality ? 'bg-surface-800 text-white' : 'bg-surface-100 text-surface-500 hover:bg-surface-200'}`}>{s === 'passed' ? '已通过' : s === 'needs_review' ? '需复核' : s === 'fallback_passed' ? '兜底通过' : '全部'}</button>)}
            </div>
          </div>
        )}

        {selectionMode && selectedIds.size > 0 && (
          <div className="flex items-center gap-2 mt-3 pt-3 border-t border-surface-100">
            <span className="text-xs text-surface-500">已选 {selectedIds.size} 项</span>
            <button onClick={() => { setSelectedIds(new Set(filtered.map(r => r.id))); }} className="px-2.5 py-1 bg-surface-100 rounded-lg text-[11px] font-medium hover:bg-surface-200">全选</button>
            <button onClick={() => handleBatch('complete')} className="px-2.5 py-1 bg-success-50 text-success-700 rounded-lg text-[11px] font-medium hover:bg-success-100">标记完成</button>
            <button onClick={() => handleBatch('bookmark')} className="px-2.5 py-1 bg-primary-50 text-primary-700 rounded-lg text-[11px] font-medium hover:bg-primary-100">批量收藏</button>
            <button onClick={() => handleBatch('export')} className="px-2.5 py-1 bg-warning-50 text-warning-700 rounded-lg text-[11px] font-medium hover:bg-warning-100">导出</button>
            <button onClick={() => setSelectedIds(new Set())} className="px-2.5 py-1 bg-surface-100 text-surface-500 rounded-lg text-[11px] font-medium hover:bg-surface-200">取消</button>
          </div>
        )}
      </div>

      {!sessionId ? <PageEmpty icon={<BookOpen className="w-8 h-8" />} title="请先进入学习会话" description="在对话页开始学习，智能体将自动从知识库生成资源" /> :
        loading && filtered.length === 0 ? <PageLoading text="加载资源中…" /> :
          error && filtered.length === 0 ? <PageError title="资源加载失败" description={error} onRetry={onRefetch} /> :
            filtered.length === 0 ? <div className="text-center py-16 bg-white rounded-2xl shadow-soft"><p className="text-surface-600 font-medium">暂无资源</p><p className="text-sm text-surface-400 mt-1">在对话页发送"帮我生成学习方案"，智能体将自动从课程知识库生成资源</p></div> :
              view === 'grid' ? (
                <div className="grid grid-cols-3 gap-5">
                  {filtered.map(r => { const c = colorMap[r.type] || { bg: 'bg-surface-100', text: 'text-surface-500' }; return (
                    <div key={r.id} onClick={() => selectionMode ? (setSelectedIds(prev => { const n = new Set(prev); n.has(r.id) ? n.delete(r.id) : n.add(r.id); return n; })) : nav(`/resources/${r.id}`)} className={`relative bg-white rounded-2xl shadow-soft hover:shadow-elevated transition-all duration-300 overflow-hidden cursor-pointer ${selectionMode && selectedIds.has(r.id) ? 'ring-2 ring-primary-400 shadow-elevated' : selectionMode ? 'hover:ring-2 hover:ring-surface-300' : 'group'}`}>
                      {selectionMode && <div className="absolute top-3 left-3 z-20">{selectedIds.has(r.id) ? <CheckCircle2 className="w-5 h-5 text-primary-600 drop-shadow-sm" /> : <div className="w-5 h-5 rounded-full border-2 border-surface-300 bg-white/80" />}</div>}
                      <div className="relative h-32 bg-gradient-to-br from-surface-100 to-surface-200 flex items-center justify-center"><div className={`w-16 h-16 rounded-2xl ${c.bg} flex items-center justify-center`}>{icons[r.type]}</div><div className={`absolute top-3 left-3 px-2.5 py-1 rounded-lg ${c.bg} ${c.text} flex items-center gap-1.5 text-xs font-medium`}>{RESOURCE_TYPE_LABELS[r.type]}</div>{r.studyStatus === 'completed' && <CheckCircle2 size={18} className="absolute top-3 right-3 text-success-500" />}</div>
                      <div className="p-5"><h4 className="font-semibold text-surface-800 line-clamp-2 group-hover:text-primary-600 transition-colors mb-2">{r.title}</h4><p className="text-sm text-surface-500 line-clamp-2 mb-3">{r.description}</p>{r.relatedChapter && <p className="text-xs text-surface-400 mb-2 truncate">📖 {r.relatedChapter}</p>}<div className="flex items-center justify-between text-xs text-surface-400"><div className="flex items-center gap-2"><Clock size={12} />{formatDuration(r.estimatedMinutes)}</div><span className={`px-2 py-0.5 rounded ${diffBadge[r.difficulty]}`}>{diffLabel[r.difficulty]}</span></div></div>
                    </div>
                  ); })}
                </div>
              ) : (
                <div className="space-y-3">
                  {filtered.map(r => { const c = colorMap[r.type] || { bg: 'bg-surface-100', text: 'text-surface-500' }; return (
                    <div key={r.id} onClick={() => selectionMode ? (setSelectedIds(prev => { const n = new Set(prev); n.has(r.id) ? n.delete(r.id) : n.add(r.id); return n; })) : nav(`/resources/${r.id}`)} className={`bg-white rounded-xl p-4 shadow-soft hover:shadow-elevated transition-all cursor-pointer flex items-center gap-4 ${selectionMode && selectedIds.has(r.id) ? 'ring-2 ring-primary-400 shadow-elevated' : selectionMode ? 'hover:ring-2 hover:ring-surface-300' : 'group'}`}>
                      {selectionMode && <div className="flex-shrink-0">{selectedIds.has(r.id) ? <CheckCircle2 className="w-5 h-5 text-primary-600" /> : <div className="w-5 h-5 rounded-full border-2 border-surface-300" />}</div>}
                      <div className={`w-12 h-12 rounded-xl ${c.bg} flex items-center justify-center flex-shrink-0`}>{icons[r.type]}</div>
                      <div className="flex-1 min-w-0"><div className="flex items-center gap-2 mb-1"><h4 className="font-semibold text-surface-800 group-hover:text-primary-600 transition-colors truncate">{r.title}</h4><span className={`flex-shrink-0 px-2 py-0.5 rounded text-xs ${diffBadge[r.difficulty]}`}>{diffLabel[r.difficulty]}</span></div><p className="text-sm text-surface-500 truncate">{r.description}</p><div className="flex items-center gap-3 mt-1.5 text-xs text-surface-400"><span className="flex items-center gap-1"><Clock size={12} />{formatDuration(r.estimatedMinutes)}</span>{r.relatedChapter && <span className="truncate">📖 {r.relatedChapter}</span>}<SourceBadge source={r.source || 'system_inferred'} size="xs" /></div></div>
                      <div className="flex items-center gap-2">{r.studyStatus === 'completed' && <CheckCircle2 size={18} className="text-success-500" />}{r.bookmarked && <BookmarkCheck size={18} className="text-primary-500" />}<ChevronRight size={18} className="text-surface-300 group-hover:text-primary-500 transition-colors" /></div>
                    </div>
                  ); })}
                </div>
              )}
    </div>
  );
}

/* ===================================================================
 * ResourceLibrary 主入口
 * =================================================================== */
export default function ResourceLibrary() {
  const nav = useNavigate();
  const params = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();

  // 从 URL 参数读取初始过滤条件
  const initialFilter = useMemo(() => {
    const f: Record<string, string> = {};
    const taskId = searchParams.get('taskId');
    if (taskId) f.taskId = taskId;
    const stageId = searchParams.get('relatedStageId');
    if (stageId) f.relatedStageId = stageId;
    const chapter = searchParams.get('chapter');
    if (chapter) f.chapter = chapter;
    return Object.keys(f).length > 0 ? f : undefined;
  }, [searchParams]);

  const { resources, total, loading, error, applyFilter, toggleBookmark, refetch } = useResources(initialFilter);
  const sessionId = useChatStore(s => s.currentSessionId);

  // 详情视图状态
  const [detailResource, setDetailResource] = useState<Resource | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');

  // 当路由参数变化时获取资源详情
  useEffect(() => {
    if (params.id && sessionId) {
      setDetailLoading(true);
      setDetailError('');
      getResourceById(params.id, { sessionId })
        .then(res => {
          setDetailResource(res.resource);
        })
        .catch(err => {
          setDetailError(err?.response?.data?.message || err?.message || '资源加载失败');
        })
        .finally(() => setDetailLoading(false));
    } else if (!params.id) {
      setDetailResource(null);
      setDetailError('');
    }
  }, [params.id, sessionId]);

  const handleBookmark = async (id: string) => {
    await toggleBookmark(id);
    if (detailResource?.id === id) {
      setDetailResource(prev => prev ? { ...prev, bookmarked: !prev.bookmarked } : null);
    }
    refetch();
  };

  const handleComplete = async (r: Resource) => {
    const ns = r.studyStatus === 'completed' ? 'new' : 'completed';
    const sid = useChatStore.getState().currentSessionId;
    try {
      await updateStudyStatus(r.id, ns, sid);
      // Auto-advance the learning path node when a resource is completed
      if (ns === 'completed' && r.relatedStageId) {
        try {
          await autoAdvanceNode({
            sessionId: sid,
            relatedStageId: r.relatedStageId,
            taskId: r.taskId,
            event: 'resource_complete',
          });
        } catch {
          // Auto-advance is best-effort — don't block the UI
        }
      }
      if (detailResource?.id === r.id) {
        setDetailResource(prev => prev ? { ...prev, studyStatus: ns } : null);
      }
      refetch();
    } catch (e) {
      // silently fail
    }
  };

  const handleBack = () => {
    const query = searchParams.toString();
    nav(`/resources${query ? `?${query}` : ''}`);
  };

  // 详情视图
  if (params.id) {
    if (detailLoading) {
      return <PageLoading text="加载资源详情…" />;
    }
    if (detailError) {
      return <PageError title="资源加载失败" description={detailError} onRetry={() => {
        if (params.id && sessionId) {
          setDetailLoading(true);
          setDetailError('');
          getResourceById(params.id, { sessionId })
            .then(res => setDetailResource(res.resource))
            .catch(err => setDetailError(err?.response?.data?.message || err?.message || '资源加载失败'))
            .finally(() => setDetailLoading(false));
        }
      }} />;
    }
    if (!detailResource) {
      return <PageEmpty icon={<BookOpen className="w-8 h-8" />} title="资源不存在" description="该资源可能已被删除" />;
    }
    return (
      <ResourceDetailView
        resource={detailResource}
        onBack={handleBack}
        onBookmark={handleBookmark}
        onComplete={handleComplete}
        onRefetch={refetch}
      />
    );
  }

  // 列表视图
  return (
    <ResourceListView
      resources={resources}
      total={total}
      loading={loading}
      error={error}
      onRefetch={refetch}
      onToggleBookmark={toggleBookmark}
      onApplyFilter={applyFilter}
      sessionId={sessionId}
      activeTaskId={searchParams.get('taskId') || undefined}
      activeStageId={searchParams.get('relatedStageId') || undefined}
    />
  );
}
