// @ts-nocheck
import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLearningPath } from '../hooks/useLearningPath';
import { useChatStore } from '../store/chatStore';
import { enableProfileExtraction, listPlanningDrafts } from '../api/learningPath';
import DayPlanView from '../components/learning/DayPlanView';
import MasteryBarGroup from '../components/learning/MasteryBarGroup';
import { useProfile } from '../hooks/useProfile';
import PlanningWizard from '../components/learning/PlanningWizard';
import { PageLoading, PageError } from '../components/common/PageState';
import { getCurrentLearner } from '../store/authStore';
import {
  ArrowRight, BookOpen, Check, CircleDot, Clock3,
  FileText, FlaskConical, Lightbulb, PenLine, Plus, Sparkles, Target, Zap,
  Loader2, ChevronRight
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
  const { path, loading, error, fetchPath, generatePath } = useLearningPath();
  const { profileV2 } = useProfile();
  const subject = profileV2?.subject_context || {};
  const [existingDraft, setExistingDraft] = useState<any>(null);
  const [draftLoading, setDraftLoading] = useState(true);
  const [activeStageId, setActiveStageId] = useState<string | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const sessionId = useChatStore((s) => s.currentSessionId);
  const isParent = getCurrentLearner()?.role === 'parent';

  const stages = path?.stages || [];
  const allNodes = stages.flatMap(s => s.nodes || []);
  const totalNodes = allNodes.length;
  const masteredNodes = allNodes.filter(n => n.status === 'mastered' || n.status === 'completed').length;
  const progress = path?.overallProgress ?? (totalNodes > 0 ? Math.round((masteredNodes / totalNodes) * 100) : 0);
  const estimatedDays = path?.estimatedDays ?? 14;
  const hasProfile = stages.length > 0 && stages.some(s =>
    (s.tasks || []).length > 0 || (s.nodes || []).length > 0 || (s.chapters || []).length > 0
  );

  const allTasks = stages.flatMap(s => (s.tasks || []).map(t => ({ ...t, stageTitle: s.title, stageId: s.id })));
  const totalTasks = allTasks.length;
  const doneTasks = allTasks.filter(t => t.status === 'completed' || t.status === 'mastered').length;
  const nextTask = allTasks.find(t => t.status !== 'completed' && t.status !== 'mastered');
  const hasInj = stages.some(s => (s.tasks || []).some((t: any) =>
    t.source === 'remedial' || t._adjustment === 'remedial' || t._adjustment === 'strengthened'
  ));

  // ── Lock + tab + recommendation state ──
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
  const [middleTab, setMiddleTab] = useState<'tasks' | 'recommendations'>('tasks');
  const [recommendedResources, setRecommendedResources] = useState<any[]>([]);
  const [recommendLoading, setRecommendLoading] = useState(false);
  const circumference = 100.53;

  const firstIncompleteIdx = stages.findIndex(s => (s.tasks || []).some(t => t.status !== 'completed' && t.status !== 'mastered'));
  const completedStages = stages.filter(s => (s.tasks || []).length > 0 && (s.tasks || []).every((t: any) => t.status === 'completed' || t.status === 'mastered')).length;

  useEffect(() => {
    if (!sessionId) { setDraftLoading(false); return; }
    (async () => {
      try { const r = await listPlanningDrafts({ sessionId }); if (r.ok && r.draft && r.draft.status !== 'expired') setExistingDraft(r.draft); } catch {}
      setDraftLoading(false);
    })();
  }, [sessionId]);

  // 首次加载自动选中第一个未完成阶段
  useEffect(() => {
    if (!activeStageId && firstIncompleteIdx >= 0) {
      setActiveStageId(stages[firstIncompleteIdx]?.id);
    }
  }, [stages.length]);

  const selectStage = (id: string) => {
    setActiveStageId(id);
    requestAnimationFrame(() => stageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };

  /* ── Hooks that must precede any conditional return ── */
  const fetchRecommendations = useCallback(async () => {
    if (!sessionId || !activeStageId) return;
    setRecommendLoading(true);
    try {
      const r = await fetch('/api/resources/recommendations/for-learning', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId, stageId: activeStageId }),
      }).then(res => res.json());
      setRecommendedResources(r?.data?.recommendations?.resources || []);
    } catch { setRecommendedResources([]); }
    finally { setRecommendLoading(false); }
  }, [sessionId, activeStageId]);

  useEffect(() => {
    if (middleTab === 'recommendations') fetchRecommendations();
  }, [middleTab, fetchRecommendations]);

  /* ── Loading / Empty ── */
  if (loading) return <PageLoading text="加载学习路径中…" />;
  if (error && stages.length === 0) return <PageError title="加载失败" description={error} onRetry={fetchPath} />;

  if (!path || stages.length === 0 || !hasProfile) {
    if (existingDraft && !draftLoading)
      return <PlanningWizard sessionId={useChatStore.getState().dataSessionId || sessionId || ''}
        subjectId={subject.subject_id || ''} subjectName={subject.subject_name || ''}
        profileV2={profileV2} onPathGenerated={(id: string) => { setExistingDraft(null); fetchPath(); }} />;
    if (draftLoading) return <div className="flex-1 flex items-center justify-center"><Loader2 size={24} className="animate-spin text-primary-500" /></div>;
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

  /* ── 有路径：左侧选中 + 中间单阶段 ── */
  const activeStage = stages.find(s => s.id === activeStageId) || stages[firstIncompleteIdx] || stages[0];
  const activeStageIdx = stages.findIndex(s => s.id === activeStage?.id);

  return (
    <div className="flex-1 flex flex-col bg-surface-50 px-4 py-6 sm:px-6 lg:px-8 lg:py-8 min-h-0">
      {/* ── Header ── */}
      <header className="flex-shrink-0 flex flex-col gap-6">
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

        {/* ── 进度概览 ── */}
        <section className="flex-shrink-0 rounded-[20px] border border-surface-200 bg-white/80 backdrop-blur-sm p-5 sm:p-6 shadow-sm">
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
        <div className="flex-1 min-h-0 flex flex-col xl:flex-row gap-8">
          {/* ═══ 左栏：阶段选择器 ═══ */}
          <aside className="space-y-5 xl:flex-[0.9_1_0%] xl:min-w-[200px] min-w-0 min-h-0 overflow-y-auto">
            <section className="rounded-[20px] border border-surface-200 bg-white/80 backdrop-blur-sm p-5 shadow-sm">
              <p className="mb-5 text-xs font-semibold uppercase tracking-[0.24em] text-surface-400">阶段导航</p>
              <div className="space-y-2">
                {stages.map((stage: any, si: number) => {
                  const tasks = stage.tasks || [];
                  const tDone = tasks.filter((t: any) => t.status === 'completed' || t.status === 'mastered').length;
                  const tTotal = tasks.length;
                  const selected = stage.id === activeStage?.id;
                  const allDone = tTotal > 0 && tasks.every((t: any) => t.status === 'completed' || t.status === 'mastered');
                  return (
                    <button key={stage.id || si} type="button" onClick={() => selectStage(stage.id)}
                      className={`group flex w-full items-center gap-3 rounded-2xl border px-3 py-3 text-left transition-all duration-300 ${
                        selected ? 'border-primary-200 bg-primary-50/50 shadow-[inset_3px_0_0_#3478f6]' :
                        allDone ? 'border-transparent bg-transparent opacity-60' :
                        'border-transparent bg-transparent hover:border-surface-200 hover:bg-surface-50'
                      }`}>
                      <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${
                        selected ? 'bg-primary-500 text-white shadow-[0_0_12px_rgba(52,120,246,0.35)]' :
                        allDone ? 'bg-success-100 text-success-600' :
                        'border border-surface-300 text-surface-400'
                      }`}>{allDone ? <Check size={12} /> : si + 1}</span>
                      <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold text-surface-800">{stage.title}</span></span>
                      <span className="text-xs font-semibold text-surface-400">{tDone}/{tTotal}</span>
                    </button>
                  );
                })}
              </div>
            </section>
            {hasInj && (
              <section className="rounded-[20px] border border-warning-200/60 bg-warning-50/50 p-5">
                <div className="mb-3 flex items-center gap-2 text-warning-600"><Sparkles size={16} /><p className="text-xs font-semibold uppercase tracking-[0.18em]">AI 调整提示</p></div>
                <p className="text-sm leading-6 text-surface-600">路径已根据你的学习表现动态优化</p>
              </section>
            )}
          </aside>

          {/* ═══ 中栏：只展示选中的阶段（始终展开） ═══ */}
          <section className="space-y-4 xl:flex-[1.55_1_0%] min-w-0 min-h-0 overflow-y-auto" ref={stageRef}>
            {activeStage && (() => {
              const stage = activeStage;
              const tasks = stage.tasks || [];
              const tTotal = tasks.length;
              const tDone = tasks.filter((t: any) => t.status === 'completed' || t.status === 'mastered').length;
              const pct = tTotal > 0 ? Math.round((tDone / tTotal) * 100) : 0;
              const allDone = tTotal > 0 && tasks.every((t: any) => t.status === 'completed' || t.status === 'mastered');
              const dashOffset = circumference - (circumference * pct) / 100;
              return (<React.Fragment>
                <article className="scroll-mt-8 overflow-hidden rounded-[20px] border bg-white/80 backdrop-blur-sm shadow-sm shrink-0"
                  style={{ borderColor: allDone ? '#31b16f' : '#3478f6', boxShadow: allDone ? 'none' : '0 0 0 1px rgba(52,120,246,0.3), 0 8px 32px rgba(52,120,246,0.08)' }}>
                  {/* 阶段头 —— 纯展示，不可点击 */}
                  <div className="flex w-full items-center gap-4 p-5 text-left sm:p-6">
                    <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                      allDone ? 'bg-success-100 text-success-600' : 'bg-gradient-to-br from-primary-500 to-accent-500 text-white shadow-[0_0_20px_rgba(52,120,246,0.3)]'
                    }`}>{allDone ? <Check size={16} /> : stages.indexOf(stage) + 1}</span>
                    <span className="min-w-0 flex-1">
                      <h2 className="text-base font-semibold leading-tight tracking-[-0.02em] text-surface-800">{stage.title}</h2>
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
                  {/* ── 标签切换 ── */}
                  <div className="flex gap-2 px-5 pt-4 sm:px-6">
                    <button type="button" onClick={() => setMiddleTab('tasks')}
                      className={'text-[11px] font-medium tracking-wide pb-1 border-b-2 ' + (middleTab==='tasks'?'border-primary-400 text-surface-700':'border-transparent text-surface-400 hover:text-surface-500')}
                    >任务</button>
                    <button type="button" onClick={() => setMiddleTab('recommendations')}
                      className={'text-[11px] font-medium tracking-wide pb-1 border-b-2 ' + (middleTab==='recommendations'?'border-primary-400 text-surface-700':'border-transparent text-surface-400 hover:text-surface-500')}
                    >推荐资源</button>
                  </div>
                  {/* 阶段体 —— 始终展开 */}
                  <div className="border-t border-surface-200 px-5 pb-5 pt-5 sm:px-6 sm:pb-6 space-y-4">
                    {middleTab === 'tasks' ? (
                    <>
                    <p className="max-w-2xl text-sm leading-7 text-surface-500">{stage.objective || stage.theme || ''}</p>
                    <div className="space-y-3">
                      {tasks.length > 0 ? tasks.map((task: any, ti: number) => {
                        const done = task.status === 'completed' || task.status === 'mastered';
                        const prog = task.status === 'in_progress';
                        const inj = task.source === 'remedial' || task._adjustment === 'remedial' || task._adjustment === 'strengthened';
                        const kind = task.type || 'read_doc';
                        const meta = kindMeta(kind);
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
                                  done ? 'bg-success-100 text-success-600' : prog ? 'bg-primary-100 text-primary-500 animate-pulse' : 'bg-surface-100 text-surface-400'
                                }`}>{done ? <Check size={18} /> : prog ? <CircleDot size={18} /> : <Target size={18} />}</span>
                                <span className="min-w-0 flex-1">
                                  <span className="flex flex-wrap items-center gap-2">
                                    <h3 className="text-sm font-semibold leading-6 text-surface-800">{task.title}</h3>
                                    {inj && <span className="rounded-full border border-warning-200/50 bg-warning-50 px-2 py-0.5 text-[11px] font-semibold text-warning-600">⚡ AI 注入</span>}
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
                              <button type="button" disabled={done || (activeStageIdx > currentStageIdx || (activeStageIdx === currentStageIdx && ti > currentTaskIdx))}
                                onClick={(e) => { e.stopPropagation(); nav(`/lecture/section/${encodeURIComponent(task.task_id || task.title)}`); }}
                                className={`h-10 shrink-0 rounded-xl px-4 text-xs font-bold transition-all duration-300 ${
                                  done ? 'border border-success-200 bg-success-50 text-success-500' :
                                  prog ? 'bg-gradient-to-r from-primary-500 to-accent-500 text-white shadow-[0_0_20px_rgba(52,120,246,0.3)]' :
                                  'border border-surface-200 bg-white text-surface-600 hover:border-primary-300 hover:bg-primary-50 hover:text-primary-600'
                                }`}>{done ? '✓ 完成' : prog ? '继续 →' : '开始'}</button>
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
                  </>
                ) : (
                  <div className="space-y-4">
                    {recommendLoading ? (
                      <div className="flex items-center justify-center py-10">
                        <Loader2 size={24} className="animate-spin text-surface-300" />
                        <span className="ml-3 text-sm text-surface-400">正在搜索推荐资源...</span>
                      </div>
                    ) : recommendedResources.length === 0 ? (
                      <div className="text-center py-10">
                        <BookOpen size={40} className="mx-auto mb-3 text-surface-300" />
                        <p className="text-sm text-surface-500">暂无推荐资源</p>
                        <button onClick={fetchRecommendations} className="mt-3 text-xs text-primary-500 hover:underline">点击重试</button>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 gap-3">
                        {recommendedResources.map((r: any, i: number) => (
                          <a key={i} href={r.url || '#'} target="_blank" rel="noopener noreferrer"
                            className="flex items-start gap-3 rounded-xl border border-surface-100 p-3 hover:border-primary-200 hover:bg-primary-50/30 transition-all h-[72px] overflow-hidden">
                            <span className="mt-0.5 shrink-0 text-lg">{r.type==='video'?'🎬':r.type==='article'?'📄':r.type==='course'?'🎓':'📖'}</span>
                            <span className="min-w-0 flex-1">
                              <span className="block text-sm font-semibold text-surface-800 truncate">{r.title}</span>
                              <span className="mt-1 block text-xs text-surface-400 line-clamp-2">{r.snippet || r.description || ''}</span>
                            </span>
                          </a>
                        ))}
                      </div>
                    )}
              </div>
            )}
              </div>
                </article>
                </React.Fragment>
              );
            })()}
          </section>

          {/* ═══ 右栏：立即开始 + 学习分析 + 练习 ═══ */}
          <aside className="space-y-5 xl:flex-[0.82_1_0%] xl:min-w-[260px] min-w-0 min-h-0 overflow-y-auto">
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
            {path?.day_plan && (
              <section className="rounded-[20px] border border-surface-200 bg-white/80 backdrop-blur-sm p-5 shadow-sm">
                <DayPlanView dayPlan={path.day_plan} totalDays={estimatedDays} currentDay={1} />
              </section>
            )}
            <section className="rounded-[20px] border border-surface-200 bg-white/80 backdrop-blur-sm p-5 shadow-sm">
              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.24em] text-surface-400">学习分析</p>
              <ul className="space-y-4 text-sm leading-6 text-surface-600">
                <li className="flex gap-3"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-primary-500 shadow-[0_0_12px_rgba(52,120,246,0.45)]" />已完成 {doneTasks}/{totalTasks || totalNodes} 项学习任务</li>
                <li className="flex gap-3"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-warning-400 shadow-[0_0_12px_rgba(251,191,36,0.4)]" />共 {stages.length} 个阶段，{completedStages} 个已完成</li>
                {nextTask?.stageTitle && <li className="flex gap-3"><span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-accent-500 shadow-[0_0_12px_rgba(141,107,255,0.45)]" />当前阶段：{nextTask.stageTitle}</li>}
              </ul>
              {path?.diagnosis?.mastery_levels && (
                <MasteryBarGroup items={path.diagnosis.mastery_levels as any[]} max={5} />
              )}
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
  );
}
