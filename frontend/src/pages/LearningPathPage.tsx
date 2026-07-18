// @ts-nocheck
import { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useLearningPath } from '../hooks/useLearningPath';
import { useChatStore } from '../store/chatStore';
import { enableProfileExtraction, listPlanningDrafts, getWorkflowTask } from '../api/learningPath';
import { useProfile } from '../hooks/useProfile';
import PlanningWizard from '../components/learning/PlanningWizard';
import RevisionProposalCard from '../components/learning/RevisionProposalCard';
import { PageLoading, PageError } from '../components/common/PageState';
import { getCurrentLearner } from '../store/authStore';
import { learningTaskRoute } from '../utils/learningTaskRoute';
import {
  ArrowRight, BookOpen, Check, CircleDot, Clock3,
  FileText, FlaskConical, Lightbulb, PenLine, Plus, Sparkles, Target, Zap,
  Loader2, ChevronRight, Lock
} from 'lucide-react';

/* ── 任务类型图标与标签 ──────────────────── */
const KIND_CFG: Record<string, { label: string; icon: React.ReactNode }> = {
  read_doc:   { label: '阅读', icon: <BookOpen className="h-3.5 w-3.5" /> },
  write_code: { label: '推演', icon: <PenLine className="h-3.5 w-3.5" /> },
  do_quiz:    { label: '小测', icon: <FlaskConical className="h-3.5 w-3.5" /> },
  practice:   { label: '专项', icon: <Target className="h-3.5 w-3.5" /> },
  method:     { label: '方法', icon: <Lightbulb className="h-3.5 w-3.5" /> },
  mock:       { label: '模拟', icon: <FileText className="h-3.5 w-3.5" /> },
  review:     { label: '复盘', icon: <Sparkles className="h-3.5 w-3.5" /> },
};
function kindMeta(k: string) { return KIND_CFG[k] || KIND_CFG.read_doc; }

/* ── Chapters/sections 兜底渲染 ──────────── */
function renderChapters(chapters: any[], nav: any) {
  return chapters.map((ch: any, ci: number) => (
    <div key={ch.id || ci} className="space-y-2">
      <h4 className="text-sm font-semibold text-surface-700">{ch.title}</h4>
      {(ch.sections || []).map((sec: any, si: number) => {
        const done = sec.status === 'mastered' || sec.status === 'completed';
        return (
          <div key={sec.id || si} onClick={() => nav(`/lecture/section/${encodeURIComponent(sec.id)}`)}
            className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
              done ? 'border-success-200 bg-success-50/50' : 'border-surface-200 bg-white hover:border-primary-200 hover:shadow-sm'
            }`}>
            <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] ${
              done ? 'bg-success-100 text-success-600' : 'bg-surface-100 text-surface-400'
            }`}>{done ? <Check size={12} /> : <Target size={12} />}</span>
            <span className="flex-1 text-sm text-surface-600 truncate">{sec.title}</span>
            {sec.estimatedMinutes && <span className="text-xs text-surface-300">{sec.estimatedMinutes}′</span>}
          </div>
        );
      })}
    </div>
  ));
}

export default function LearningPathPage() {
  const nav = useNavigate();
  const location = useLocation();
  const { path, loading, error, fetchPath, generatePath, applyPathFromWorkflow } = useLearningPath();
  const { profileV2 } = useProfile();
  const subject = profileV2?.subject_context || {};
  const [existingDraft, setExistingDraft] = useState<any>(null);
  const [draftLoading, setDraftLoading] = useState(true);
  const [pathGenerating, setPathGenerating] = useState(false);
  const [generatingStatus, setGeneratingStatus] = useState<string>('');

  const [generatingTaskId] = useState<string>(() => {
    const tid = sessionStorage.getItem('_pending_gen_task_id') || '';
    return tid;
  });
  const [generatingSessionId] = useState<string>(() => {
    const sid = sessionStorage.getItem('_pending_gen_session_id') || '';
    if (sid) sessionStorage.removeItem('_pending_gen_session_id');
    return sid;
  });
  const [activeStageId, setActiveStageId] = useState<string | null>(null);
  const [middleTab, setMiddleTab] = useState<'tasks' | 'recommendations'>('tasks');
  const [recommendLoading, setRecommendLoading] = useState(false);
  const [recommendedResources, setRecommendedResources] = useState<any[]>([]);
  const [expandedStages, setExpandedStages] = useState<Set<string>>(new Set());
  const [activeDay, setActiveDay] = useState<number | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const sessionId = useChatStore((s) => s.currentSessionId);
  const isParent = getCurrentLearner()?.role === 'parent';

  const stages = path?.stages || [];
  const dayPlan = (path as any)?.day_plan || null;
  const allNodes = stages.flatMap(s => s.nodes || []);
  const totalNodes = allNodes.length;
  const masteredNodes = allNodes.filter(n => n.status === 'mastered' || n.status === 'completed').length;
  const progress = path?.overallProgress ?? (totalNodes > 0 ? Math.round((masteredNodes / totalNodes) * 100) : 0);
  const estimatedDays = path?.estimatedDays ?? 14;
  const hasProfile = stages.length > 0 && stages.some(s =>
    (s.tasks || []).length > 0 || (s.nodes || []).length > 0 || (s.chapters || []).length > 0 || (s.sections || []).length > 0
  );

  const allTasks = stages.flatMap(s => (s.tasks || []).map(t => ({ ...t, stageTitle: s.title, stageId: s.id })));
  const totalTasks = allTasks.length;
  const doneTasks = allTasks.filter(t => t.status === 'completed' || t.status === 'mastered').length;
  const nextTask = allTasks.find(t => t.status !== 'completed' && t.status !== 'mastered');
  const hasInj = stages.some(s => (s.tasks || []).some((t: any) =>
    t.source === 'remedial' || t._adjustment === 'remedial' || t._adjustment === 'strengthened'
  ));
  const circumference = 100.53;

  const { currentStageIdx, currentTaskIdx } = useMemo(() => {
    for (let si = 0; si < stages.length; si++) {
      const tasks = stages[si].tasks || [];
      for (let ti = 0; ti < tasks.length; ti++) {
        if (tasks[ti].status !== 'completed' && tasks[ti].status !== 'mastered')
          return { currentStageIdx: si, currentTaskIdx: ti };
      }
    }
    return { currentStageIdx: stages.length, currentTaskIdx: -1 };
  }, [stages]);

  const firstIncompleteIdx = stages.findIndex(s => (s.tasks || []).some(t => t.status !== 'completed' && t.status !== 'mastered'));
  const completedStages = stages.filter(s => (s.tasks || []).length > 0 && (s.tasks || []).every((t: any) => t.status === 'completed' || t.status === 'mastered')).length;

  useEffect(() => {
    if (!sessionId) { setDraftLoading(false); return; }
    (async () => {
      try { const r = await listPlanningDrafts({ sessionId }); if (r.ok && r.draft && r.draft.status !== 'expired') setExistingDraft(r.draft); } catch {}
      setDraftLoading(false);
    })();
  }, [sessionId]);

  useEffect(() => {
    if (!activeStageId && firstIncompleteIdx >= 0) {
      setActiveStageId(stages[firstIncompleteIdx]?.id);
    }
  }, [stages.length]);

  useEffect(() => { if (path && path.stages?.length && hasProfile) { setPathGenerating(false); setGeneratingStatus(''); } }, [path, hasProfile]);

  useEffect(() => {
    if (!generatingTaskId) return;
    setPathGenerating(true);
    setGeneratingStatus('正在创建学习路径…');
    let cancelled = false;
    const poll = async () => {
      try {
        const task: any = await getWorkflowTask(generatingTaskId);
        if (cancelled) return;
        if (task && task.task_id) {
          setGeneratingStatus(task.current_stage || task.status || '生成中…');
          if (task.status === 'completed') {
            sessionStorage.removeItem('_pending_gen_task_id');
            sessionStorage.removeItem('_pending_gen_session_id');
            const rawPath = task.result?.data?.path;
            if (rawPath && rawPath.stages?.length) {
              applyPathFromWorkflow(rawPath);
            } else {
              fetchPath(true, generatingSessionId || undefined);
            }
            return;
          }
          if (task.status === 'failed' || task.status === 'cancelled' || task.status === 'expired') {
            sessionStorage.removeItem('_pending_gen_task_id');
            sessionStorage.removeItem('_pending_gen_session_id');
            setPathGenerating(false);
            setGeneratingStatus('');
            return;
          }
          setTimeout(() => { if (!cancelled) poll(); }, 2000);
        }
      } catch {
        if (!cancelled) setTimeout(() => poll(), 3000);
      }
    };
    poll();
    return () => { cancelled = true; };
  }, [generatingTaskId]);

  const selectStage = (id: string) => {
    setActiveStageId(id);
    setActiveDay(null);
    setMiddleTab('tasks');
    setRecommendedResources([]);
    setExpandedStages(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
    requestAnimationFrame(() => stageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };
  const selectDay = (stageId: string, dayNum: number) => {
    setActiveStageId(stageId);
    setActiveDay(dayNum);
    setMiddleTab('tasks');
    requestAnimationFrame(() => stageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };

  const fetchRecommendations = useCallback(async () => {
    if (!sessionId || !activeStageId) { console.warn('[rec] skip: no session/stage', {sessionId, activeStageId}); return; }
    console.log('[rec] fetching for', {sessionId, stageId: activeStageId});
    setRecommendLoading(true);
    try {
      const res = await fetch('/api/resources/recommendations/for-learning', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId, stageId: activeStageId }),
      });
      const r = await res.json();
      console.log('[rec] response:', r);
      const resources = r?.data?.recommendations?.resources || r?.recommendations?.resources || [];
      console.log('[rec] parsed resources:', resources.length, resources);
      setRecommendedResources(resources);
    } catch (e) { console.error('[rec] fetch error:', e); setRecommendedResources([]); }
    finally { setRecommendLoading(false); }
  }, [sessionId, activeStageId]);

  useEffect(() => {
    if (middleTab === 'recommendations') fetchRecommendations();
  }, [middleTab, fetchRecommendations]);

  if (loading) return <PageLoading text="加载学习路径中…" />;
  if (error && stages.length === 0) return <PageError title="加载失败" description={error} onRetry={fetchPath} />;

  if (!path || stages.length === 0 || !hasProfile) {
    if (existingDraft && !draftLoading)
      return <PlanningWizard sessionId={useChatStore.getState().dataSessionId || sessionId || ''}
        subjectId={subject.subject_id || ''} subjectName={subject.subject_name || ''}
        profileV2={profileV2} onPathGenerated={(id: string) => { setExistingDraft(null); fetchPath(); }} />;
    if (draftLoading || pathGenerating) return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4">
        <Loader2 size={32} className="animate-spin text-primary-500" />
        <p className="text-sm text-surface-500">{generatingStatus || '正在准备…'}</p>
      </div>
    );
    return (
      <div className="flex-1 flex items-center justify-center bg-surface-50">
        <div className="relative text-center max-w-sm px-6">
          <div className="w-16 h-16 mx-auto mb-6 rounded-[20px] bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center shadow-lg">
            <Target size={32} className="text-white" />
          </div>
          <h2 className="text-2xl font-bold text-surface-800 mb-3">开始你的学习路径</h2>
          <p className="text-surface-400 mb-8 leading-relaxed text-sm">
            先通过对话了解你的学习目标、基础和时间安排，AI 将为你量身定制专属学习计划。
          </p>
          <button onClick={() => { useChatStore.getState().setChatMode('planning');
            const sid = useChatStore.getState().currentSessionId; nav('/chat', { state: { chatMode: 'planning' } });
            if (sid) enableProfileExtraction(sid).catch(() => {}); }}
            className="inline-flex items-center gap-2 px-8 py-3 bg-primary-500 text-white rounded-[14px] text-sm font-medium hover:bg-primary-600 transition-all shadow-md">
            <Zap size={18} />开始规划学习路径
          </button>
        </div>
      </div>
    );
  }

  const activeStage = stages.find(s => s.id === activeStageId) || stages[firstIncompleteIdx] || stages[0];
  const activeStageIdx = stages.findIndex(s => s.id === activeStage?.id);
  const openTask = (task: any, stage: any) => nav(learningTaskRoute(task.type || 'read_doc', {
    sessionId, subjectId: subject.subject_id, pathId: path?.id, stageId: stage.id,
    taskId: task.task_id || task.id, sectionId: task.section_id || task.task_id,
  }));

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-surface-50 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <div className="mx-auto w-full max-w-[1440px] flex flex-col gap-8">
        {/* ── Header ── */}
        <header className="flex flex-col gap-6">
          <div className="flex items-center justify-between gap-4">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-surface-400">学习路径</p>
            {!isParent && (
              <button onClick={() => nav('/chat', { state: { initialMessage: '调整一下我的学习路径' } })}
                className="rounded-full border border-surface-200 bg-white px-4 py-2 text-xs font-semibold text-surface-600 hover:border-primary-300 hover:bg-primary-50 transition-colors">
                调整路径
              </button>
            )}
          </div>
          <section className="max-w-3xl">
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.24em] text-primary-500">个性化学习计划</p>
            <h1 className="text-[32px] font-bold leading-[1.05] tracking-[-0.045em] text-surface-800 sm:text-[36px]">{path?.title || '学习路径'}</h1>
            <p className="mt-4 text-sm leading-7 text-surface-400">{path?.description || 'AI 根据你的学习表现持续优化这条路径'}</p>
          </section>
        </header>

        {path?.id && sessionId && subject.subject_id && <RevisionProposalCard sessionId={sessionId} subjectId={subject.subject_id} pathId={path.id} />}

        {/* ── 进度概览 ── */}
        <section className="rounded-[20px] border border-surface-200 bg-white/80 backdrop-blur-sm p-5 sm:p-6 shadow-sm">
          <div className="grid gap-6 xl:grid-cols-[1fr_300px] xl:items-center">
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4 lg:gap-0">
              <div className="lg:border-r lg:border-surface-200 lg:pr-6">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-surface-400">总进度</p>
                <strong className="mt-2 block text-[32px] leading-none tracking-[-0.04em] text-primary-500">{progress}%</strong>
              </div>
              <div className="lg:border-r lg:border-surface-200 lg:px-6">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-surface-400">已完成</p>
                <strong className="mt-2 block text-xl leading-tight tracking-[-0.03em] text-success-500">{doneTasks}/{totalTasks || totalNodes} 项</strong>
              </div>
              <div className="lg:border-r lg:border-surface-200 lg:px-6">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-surface-400">预计剩余</p>
                <strong className="mt-2 block text-xl leading-tight tracking-[-0.03em] text-surface-800">{estimatedDays} 天</strong>
              </div>
              <div className="lg:pl-6">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-surface-400">阶段进度</p>
                <strong className="mt-2 block text-xl leading-tight tracking-[-0.03em] text-accent-500">{completedStages}/{stages.length} 完成</strong>
              </div>
            </div>
            <div className="rounded-2xl border border-surface-200 bg-surface-50/50 p-4">
              <div className="mb-3 flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-surface-400">路径阶段</p>
                <p className="text-xs font-semibold text-surface-800">{progress}%</p>
              </div>
              <div className="flex gap-2">
                {stages.map((_, i) => (
                  <span key={i}
                    className={`h-2.5 flex-1 rounded-full transition-all duration-500 ${
                      i / Math.max(stages.length - 1, 1) < progress / 100
                        ? 'bg-gradient-to-r from-primary-500 to-accent-500'
                        : 'bg-surface-200'
                    }`} />
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ── 左侧导航 + 中间单阶段 + 右侧面板 ── */}
        <div className="grid gap-8 xl:h-[calc(100vh-16rem)] xl:min-h-0 xl:grid-cols-[minmax(200px,0.9fr)_minmax(0,1.55fr)_minmax(260px,0.82fr)] xl:items-stretch">
          
          {/* ═══ 左栏：阶段+天 手风琴 ═══ */}
          <aside className="min-w-0 space-y-5 max-h-[calc(100vh-16rem)] overflow-y-auto overscroll-contain">
            <section className="rounded-[20px] border border-surface-200 bg-white/80 backdrop-blur-sm p-5 shadow-sm">
              <p className="mb-5 text-xs font-semibold uppercase tracking-[0.24em] text-surface-400">学习日程</p>
              <div className="space-y-1 pr-1">
                {stages.map((stage: any, si: number) => {
                  const tasks = stage.tasks || [];
                  const days = stage.days || [];
                  const tDone = tasks.filter((t: any) => t.status === 'completed' || t.status === 'mastered').length;
                  const tTotal = tasks.length;
                  const selected = stage.id === activeStage?.id;
                  const allDone = tTotal > 0 && tasks.every((t: any) => t.status === 'completed' || t.status === 'mastered');
                  const isExpanded = expandedStages.has(stage.id);
                  const hasAdj = stage._adjustment && stage._adjustment !== 'normal';
                  const isLocked = si > currentStageIdx;
                  return (
                    <div key={stage.id || si}>
                      <button type="button" disabled={isLocked} onClick={() => selectStage(stage.id)}
                        className={`group flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left transition-all ${
                          selected ? 'bg-primary-50/50' :
                          allDone ? 'opacity-50' :
                          isLocked ? 'opacity-40 cursor-not-allowed' : 'hover:bg-surface-50'
                        }`}>
                        <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[10px] font-bold ${
                          selected ? 'bg-primary-500 text-white' :
                          allDone ? 'bg-success-100 text-success-500' :
                          isLocked ? 'bg-surface-100 text-surface-300' : 'bg-surface-100 text-surface-500'
                        }`}>{isLocked ? <Lock size={10} /> : allDone ? <Check size={10} /> : si + 1}</span>
                        <span className="min-w-0 flex-1 text-[12px] font-semibold text-surface-700 truncate">{stage.title}</span>
                        {hasAdj && <span className="shrink-0 rounded-full bg-warning-100 px-1.5 py-px text-[9px] font-bold text-warning-600">⚡</span>}
                        <ChevronRight size={12} className={`shrink-0 text-surface-300 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                      </button>
                      {isExpanded && days.length > 0 && (
                        <div className="ml-5 mt-0.5 space-y-0.5 border-l border-surface-200 pl-3">
                          {days.map((d: any, di: number) => {
                            const dtasks = d.tasks || [];
                            const dDone = dtasks.filter((t: any) => t.status === 'completed' || t.status === 'mastered').length;
                            const dTotal = dtasks.length;
                            const isToday = si === currentStageIdx && di === 0;
                            const isActiveDay = activeDay === d.day && stage.id === activeStage?.id;
                            const isDayLocked = si > currentStageIdx || (si === currentStageIdx && di > 0);
                            return (
                              <button key={di} type="button" disabled={isDayLocked} onClick={() => selectDay(stage.id, d.day)}
                                className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] transition-all ${
                                  isActiveDay ? 'bg-primary-100/50 text-primary-700' :
                                  isDayLocked ? 'text-surface-300 cursor-not-allowed' : 'text-surface-500 hover:bg-surface-50'
                                }`}>
                                <span className="shrink-0">{isDayLocked ? '🔒' : isToday ? '📌' : '📅'}</span>
                                <span className="flex-1 truncate font-medium">第{d.day}天{isToday ? ' · 今天' : ''}</span>
                                <span className="shrink-0 text-[10px] text-surface-400">{dDone}/{dTotal}</span>
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
            {hasInj && (
              <section className="rounded-[20px] border border-warning-200/60 bg-warning-50/50 p-4 mt-3">
                <div className="flex items-center gap-2 text-warning-600 mb-2"><Sparkles size={14} /><p className="text-[11px] font-semibold uppercase tracking-[0.18em]">动态调整日志</p></div>
                <div className="space-y-2 text-xs text-surface-600">
                  {stages.filter((s: any) => s._adjustment && s._adjustment !== 'normal').slice(0, 5).map((s: any, ai: number) => (
                    <p key={ai} className="flex items-start gap-1.5">
                      <span className="mt-0.5 shrink-0 text-[10px]">{s._adjustment === 'accelerated' ? '⏩' : s._adjustment === 'strengthened' ? '🔧' : s._adjustment === 'remedial' ? '🩹' : '⚡'}</span>
                      <span className="leading-relaxed">{s._adjustment_reason || `${s.title} 已自动调整`}</span>
                    </p>
                  ))}
                  {dayPlan?._adjusted_days?.length > 0 && (
                    <p className="text-[11px] text-warning-500 mt-1">📅 已调整第 {dayPlan._adjusted_days.join('、')} 天</p>
                  )}
                </div>
              </section>
            )}
          </aside>

          {/* ═══ 中栏 ═══ */}
          <section className="min-w-0 flex flex-col xl:h-full xl:min-h-0" ref={stageRef}>
            {activeStage && (() => {
              const stage = activeStage;
              const allStageTasks = stage.tasks || [];
              const days = stage.days || [];
              const tasks = activeDay && days.length > 0
                ? (days.find((d: any) => d.day === activeDay)?.tasks || allStageTasks)
                : allStageTasks;
              const tTotal = tasks.length;
              const tDone = tasks.filter((t: any) => t.status === 'completed' || t.status === 'mastered').length;
              const pct = tTotal > 0 ? Math.round((tDone / tTotal) * 100) : 0;
              const allDone = tTotal > 0 && tasks.every((t: any) => t.status === 'completed' || t.status === 'mastered');
              const dashOffset = circumference - (circumference * pct) / 100;
              return (
                <article className="flex flex-col xl:h-full xl:min-h-0 overflow-hidden rounded-[20px] border bg-white/80 backdrop-blur-sm shadow-sm"
                  style={{ borderColor: allDone ? '#31b16f' : '#3478f6', boxShadow: allDone ? 'none' : '0 0 0 1px rgba(52,120,246,0.3), 0 8px 32px rgba(52,120,246,0.08)' }}>
                  
                  {/* ── 阶段头：固定在顶部 ── */}
                  <div className="shrink-0 flex w-full items-center gap-4 p-5 text-left sm:p-6">
                    <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                      allDone ? 'bg-success-100 text-success-600' : 'bg-gradient-to-br from-primary-500 to-accent-500 text-white shadow-[0_0_20px_rgba(52,120,246,0.3)]'
                    }`}>{allDone ? <Check size={16} /> : stages.indexOf(stage) + 1}</span>
                    <span className="min-w-0 flex-1">
                      <h2 className="text-base font-semibold leading-tight tracking-[-0.02em] text-surface-800">{stage.title}{activeDay ? ` · 第${activeDay}天` : ''}</h2>
                      <p className="mt-1 text-xs leading-5 text-surface-400">{stage.theme || stage.objective || ''}</p>
                    </span>
                    <span className="hidden items-center gap-3 sm:flex">
                      {tTotal > 0 && (
                        <span className="relative flex h-10 w-10 items-center justify-center">
                          <svg className="h-10 w-10 -rotate-90" viewBox="0 0 40 40">
                            <circle cx="20" cy="20" r="16" fill="none" stroke="#e9ecf0" strokeWidth="3" />
                            <circle cx="20" cy="20" r="16" fill="none" stroke={allDone ? '#31b16f' : '#3478f6'} strokeLinecap="round" strokeWidth="3" strokeDasharray={circumference} strokeDashoffset={dashOffset} className="transition-all duration-500" />
                          </svg>
                          <span className="absolute text-[10px] font-bold text-surface-700">{pct}%</span>
                        </span>
                      )}
                      <span className="w-10 text-right text-xs font-semibold text-surface-400">{tDone}/{tTotal}</span>
                    </span>
                  </div>

                  {/* ── 小标签切换：任务 / 推荐资源 ── */}
                  <div className="shrink-0 flex gap-1 mx-5 sm:mx-6 bg-surface-100 rounded-md p-0.5 w-fit">
                    <button type="button" onClick={() => setMiddleTab('tasks')}
                      className={`rounded px-2.5 py-1 text-[10px] font-semibold transition-all ${
                        middleTab === 'tasks' ? 'bg-white text-surface-800 shadow-sm' : 'text-surface-400 hover:text-surface-600'
                      }`}>任务</button>
                    <button type="button" onClick={() => setMiddleTab('recommendations')}
                      className={`rounded px-2.5 py-1 text-[10px] font-semibold transition-all ${
                        middleTab === 'recommendations' ? 'bg-white text-surface-800 shadow-sm' : 'text-surface-400 hover:text-surface-600'
                      }`}>推荐资源</button>
                  </div>

                  {/* ── 内容区：可滚动 ── */}
                  <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-5 pb-5 pt-4 sm:px-6 sm:pb-6">
                    {middleTab === 'tasks' ? (
                      <div className="space-y-4">
                        <p className="max-w-2xl text-sm leading-7 text-surface-500">{stage.objective || stage.theme || ''}</p>
                        <div className="space-y-3">
                          {tasks.length > 0 ? tasks.map((task: any, ti: number) => {
                            const done = task.status === 'completed' || task.status === 'mastered';
                            const prog = task.status === 'in_progress';
                            const inj = task.source === 'remedial' || task._adjustment === 'remedial' || task._adjustment === 'strengthened';
                            const kind = task.type || 'read_doc';
                            const meta = kindMeta(kind);
                            const isLocked = activeStageIdx > currentStageIdx || (activeStageIdx === currentStageIdx && ti > currentTaskIdx);
                            return (
                              <article key={task.task_id || ti}
                                className={`rounded-2xl border p-4 transition-all duration-300 ${
                                  done ? 'bg-surface-50/50 border-surface-200' :
                                  prog ? 'bg-primary-50/30 border-primary-200' :
                                  inj ? 'bg-warning-50/30 border-warning-200' :
                                  'bg-white border-surface-200 hover:border-primary-200 hover:shadow-sm'
                                }`}>
                                <div className="flex flex-col gap-4 md:flex-row md:items-center">
                                  <div className="flex min-w-0 flex-1 gap-4">
                                    <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${
                                      done ? 'bg-success-100 text-success-600' : 
                                      prog ? 'bg-primary-100 text-primary-500 animate-pulse' : 
                                      isLocked ? 'bg-surface-100 text-surface-300' : 'bg-surface-100 text-surface-400'
                                    }`}>{done ? <Check size={18} /> : prog ? <CircleDot size={18} /> : isLocked ? <Lock size={18} /> : <Target size={18} />}</span>
                                    <span className="min-w-0 flex-1">
                                      <span className="flex flex-wrap items-center gap-2">
                                        <h3 className="text-sm font-semibold leading-6 text-surface-800">{task.title}</h3>
                                        {inj && <span className="rounded-full border border-warning-200/50 bg-warning-50 px-2 py-0.5 text-[11px] font-semibold text-warning-600">⚡ AI 注入</span>}
                                        {isLocked && !done && !prog && <span className="rounded-full border border-surface-200 bg-surface-100 px-2 py-0.5 text-[11px] font-semibold text-surface-400">🔒 未解锁</span>}
                                      </span>
                                      {task.goal && <p className="mt-1 text-xs leading-6 text-surface-400">{task.goal}</p>}
                                      <span className="mt-3 flex flex-wrap items-center gap-2">
                                        <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
                                          inj ? 'border-warning-200/40 bg-warning-50/50 text-warning-600' :
                                          `border-surface-200 bg-surface-50 text-surface-500`
                                        }`}>
                                          {meta.icon} {meta.label}
                                        </span>
                                        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-surface-400"><Clock3 size={13} />{task.estimated_minutes}分钟</span>
                                        {inj && task._adjustment_reason && <span className="text-[11px] text-warning-500">⚡ {task._adjustment_reason}</span>}
                                      </span>
                                    </span>
                                  </div>
                                  <button type="button" 
                                    disabled={done || isLocked}
                                    onClick={(e) => { e.stopPropagation(); openTask(task, stage); }}
                                    className={`h-10 shrink-0 rounded-xl px-4 text-xs font-bold transition-all duration-300 ${
                                      done ? 'border border-success-200 bg-success-50 text-success-500 cursor-default' :
                                      isLocked ? 'border border-surface-200 bg-surface-50 text-surface-300 cursor-not-allowed' :
                                      prog ? 'bg-gradient-to-r from-primary-500 to-accent-500 text-white shadow-[0_0_20px_rgba(52,120,246,0.3)]' :
                                      'border border-surface-200 bg-white text-surface-600 hover:border-primary-300 hover:bg-primary-50 hover:text-primary-600'
                                    }`}>
                                    {done ? '✓ 完成' : isLocked ? '🔒 锁定' : prog ? '继续 →' : '开始'}
                                  </button>
                                </div>
                              </article>
                            );
                          }) : (stage.chapters || []).length > 0 ? renderChapters(stage.chapters, nav) : (stage.nodes || []).slice(0, 5).map((node: any, ni: number) => (
                            <div key={node.id || ni} onClick={() => nav(`/lecture/section/${encodeURIComponent(node.id)}`)}
                              className="flex items-center gap-3 p-3.5 rounded-xl border border-surface-200 hover:border-primary-200 hover:shadow-sm transition-all cursor-pointer bg-white">
                              <Target size={16} className="text-surface-400 flex-shrink-0" />
                              <span className="flex-1 text-sm text-surface-600 truncate">{node.topic}</span>
                              <span className="text-xs text-surface-300">{node.estimated_minutes || ''}′</span>
                            </div>
                          ))}
                          {allDone && tTotal > 0 && <div className="text-center py-3 text-sm text-success-500 font-medium">🎉 本阶段已全部完成</div>}
                        </div>
                      </div>
                    ) : (
                      <>
                        {recommendLoading ? (
                          <div className="flex items-center justify-center py-16"><Loader2 size={24} className="animate-spin text-primary-400" /></div>
                        ) : recommendedResources.length > 0 ? (
                          <div className="space-y-3">
                            {recommendedResources.map((res: any, ri: number) => {
                              const rtype = res.type || res.resource_type || '';
                              const icon = rtype === 'video' ? '🎬' : rtype === 'quiz' ? '✏️' : rtype === 'mindmap' ? '🧠' : rtype === 'practice' || rtype === 'lab' ? '💻' : '📖';
                              return (
                                <a key={ri} href={res.url || res.link || '#'} target="_blank" rel="noopener noreferrer"
                                  className="flex items-start gap-4 rounded-xl border border-surface-200 bg-white p-4 hover:border-primary-200 hover:shadow-sm transition-all h-[192px] overflow-hidden">
                                  <span className="mt-0.5 text-2xl shrink-0">{icon}</span>
                                  <span className="min-w-0 flex-1">
                                    <span className="block text-base font-semibold text-surface-800 truncate">{res.title || res.name || '推荐资源'}</span>
                                    {(res.snippet || res.description) && <span className="mt-1.5 block text-sm text-surface-400 line-clamp-4">{res.snippet || res.description}</span>}
                                    <span className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-surface-400">
                                      <span className="uppercase tracking-wide">{rtype || 'resource'}</span>
                                      {res.duration && <span> · {res.duration}min</span>}
                                    </span>
                                  </span>
                                </a>
                              );
                            })}
                          </div>
                        ) : (
                          <div className="text-center py-16">
                            <p className="text-sm text-surface-400">暂无推荐资源</p>
                            <button type="button" onClick={fetchRecommendations}
                              className="mt-3 text-xs font-semibold text-primary-500 hover:text-primary-600">重新加载</button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </article>
              );
            })()}
          </section>

          {/* ═══ 右栏：完全静止，卡片静态排列 ═══ */}
          <aside className="min-w-0 space-y-5">
            {nextTask && (
              <section className="overflow-hidden rounded-[20px] border border-surface-200 bg-white/80 backdrop-blur-sm shadow-sm">
                <div className="h-20 bg-gradient-to-r from-primary-500 to-accent-500" />
                <div className="p-5">
                  <p className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-surface-400">立即开始</p>
                  <h2 className="text-sm font-bold leading-6 text-surface-800">{nextTask.title}</h2>
                  <p className="mt-2 text-xs leading-6 text-surface-400">{nextTask.goal || '优先处理最新学习任务'}</p>
                  <p className="mt-3 text-xs font-semibold text-surface-400"><span className="text-primary-500">{kindMeta(nextTask.type || 'read_doc').label}</span> · {nextTask.estimated_minutes}分钟</p>
                  <button type="button" onClick={() => nav(`/lecture/section/${encodeURIComponent(nextTask.task_id || nextTask.title)}`)}
                    className="mt-5 flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary-500 to-accent-500 text-sm font-bold text-white shadow-[0_0_24px_rgba(52,120,246,0.3)] hover:shadow-[0_0_32px_rgba(167,139,250,0.3)] transition-all">
                    开始学习 <ArrowRight size={16} />
                  </button>
                </div>
              </section>
            )}
            <section className="rounded-[20px] border border-surface-200 bg-white/80 backdrop-blur-sm p-5 shadow-sm">
              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.24em] text-surface-400">学习分析</p>
              <ul className="space-y-4 text-sm leading-6 text-surface-600">
                <li className="flex gap-3"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-primary-500 shadow-[0_0_12px_rgba(52,120,246,0.45)]" />已完成 {doneTasks}/{totalTasks || totalNodes} 项学习任务</li>
                <li className="flex gap-3"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-warning-400 shadow-[0_0_12px_rgba(251,191,36,0.4)]" />共 {stages.length} 个阶段，{completedStages} 个已完成</li>
                {nextTask?.stageTitle && <li className="flex gap-3"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-accent-500 shadow-[0_0_12px_rgba(141,107,255,0.45)]" />当前阶段：{nextTask.stageTitle}</li>}
              </ul>
            </section>
            <section className="rounded-[20px] border border-surface-200 bg-white/80 backdrop-blur-sm p-5 shadow-sm">
              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.24em] text-surface-400">练习</p>
              <button type="button" onClick={() => nav('/practice')}
                className="flex w-full items-center gap-3 rounded-2xl border border-transparent p-3 text-left transition-all duration-300 hover:border-surface-200 hover:bg-surface-50">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-500 border border-primary-100"><FileText size={16} /></span>
                <span className="min-w-0 flex-1"><strong className="block truncate text-sm font-semibold text-surface-800">前往练习中心</strong><span className="mt-0.5 block text-xs text-surface-400">做题巩固知识点</span></span>
                <ChevronRight size={16} className="text-surface-300" />
              </button>
              <button type="button" onClick={() => nav('/practice?prompt=出题')}
                className="mt-4 flex h-11 w-full items-center justify-center gap-2 rounded-xl border border-dashed border-primary-300/50 bg-primary-50/30 text-sm font-bold text-primary-500 transition-all duration-300 hover:border-primary-400/70 hover:bg-primary-50/60 hover:text-primary-600">
                <Plus size={16} />生成题集
              </button>
            </section>
          </aside>
        </div>
      </div>
    </div>
  );
}