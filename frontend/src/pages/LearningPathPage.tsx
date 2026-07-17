// @ts-nocheck
import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatPanel } from '../components/layout/AppLayout';
import { useLearningPath } from '../hooks/useLearningPath';
import { PlayCircle, BookOpen, Code2, FileCheck, Lock, CheckCircle2, Circle, Loader2, ChevronRight, Zap, Target, ArrowLeft, FileText, Brain, Calendar, ExternalLink, Clock, ClipboardList, Plus, AlertCircle, LayoutGrid } from 'lucide-react';
import { listExamSets, generateExamSet } from '../api/assessment';
import { validateCourse, enableProfileExtraction, planningChat, listPlanningDrafts, type PlanningDraft } from '../api/learningPath';
import { useProfile } from '../hooks/useProfile';
import { useChatStore } from '../store/chatStore';
import DayPlanView from '../components/learning/DayPlanView';
import StageTimeline from '../components/learning/StageTimeline';
import type { ExamSet } from '../types/assessment';
import PlanningWizard from '../components/learning/PlanningWizard';
import { PageLoading, PageEmpty, PageError } from '../components/common/PageState';
import { getCurrentLearner } from '../store/authStore';
import PathModeRouter from '../components/learning/PathModeViews';

// ── 画像收集进度卡片 ──

function ProfileInfoPanel({ sessionId }: { sessionId: string }) {
  const [facts, setFacts] = useState<Record<string, string>>({});
  const [richFacts, setRichFacts] = useState<Record<string, any>>({});
  const [expandedDim, setExpandedDim] = useState<string | null>(null);
  const nav = useNavigate();

  useEffect(() => {
    if (!sessionId) return;
    fetch(`/api/conversation-facts?sessionId=${sessionId}`).then(r => r.json()).then(d => {
      if (d.facts) setFacts(d.facts);
      if (d.rich_facts) setRichFacts(d.rich_facts);
    }).catch(() => {});
  }, [sessionId]);

  const DIMS = [
    { key: 'background', label: '专业/年级', hint: '聊聊你的专业背景' },
    { key: 'target_course', label: '目标课程', hint: '想学什么课程' },
    { key: 'knowledge_base', label: '已有基础', hint: '说说你已有的基础' },
    { key: 'weak_points', label: '薄弱点', hint: '聊聊哪里容易卡住' },
    { key: 'learning_goal', label: '学习目标', hint: '你的目标是什么' },
    { key: 'time_budget', label: '时间安排', hint: '每天能学多久' },
    { key: 'preference', label: '学习偏好', hint: '喜欢什么学习方式' },
  ];

  const filled = DIMS.filter(d => {
    const v = facts[d.key] || '';
    return v && v !== '未提及' && v !== '待补充' && v !== '未知' && v !== '';
  }).length;
  const total = DIMS.length;
  const pct = Math.round((filled / total) * 100);

  const goChat = (prompt: string) => {
    nav('/chat', { state: { initialMessage: prompt, chatMode: 'planning' } });
  };

  const levelLabel = (lvl: string) => {
    const map: Record<string, string> = { none: '未掌握', beginner: '入门', intermediate: '中等', advanced: '精通' };
    return map[lvl] || lvl;
  };
  const levelColor = (lvl: string) => {
    const map: Record<string, string> = { none: 'text-red-500', beginner: 'text-amber-500', intermediate: 'text-primary-500', advanced: 'text-green-500' };
    return map[lvl] || 'text-surface-400';
  };
  const evidenceIcon = (ev: string) => {
    if (!ev) return '';
    if (ev.includes('诊断') || ev.includes('探测')) return '🔍';
    if (ev.includes('行为')) return '👀';
    return '💬';
  };

  return (
    <div className="bg-white rounded-2xl p-5 shadow-soft border border-surface-100">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-display text-sm font-semibold text-surface-700 flex items-center gap-2">
          <span>📋</span> 画像收集进度
        </h3>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${pct >= 80 ? 'bg-success-50 text-success-600' : pct >= 40 ? 'bg-primary-50 text-primary-600' : 'bg-surface-100 text-surface-500'}`}>
          {filled}/{total} 项
        </span>
      </div>

      <div className="relative h-2 bg-surface-100 rounded-full mb-4 overflow-hidden">
        <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary-400 to-accent-500 rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
      </div>

      <div className="space-y-2">
        {DIMS.map(d => {
          const v = facts[d.key] || '';
          const has = v && v !== '未提及' && v !== '待补充' && v !== '未知' && v !== '';
          const rich = richFacts[d.key] || {};
          const topics: any[] = rich.topics || [];
          const isExpanded = expandedDim === d.key;
          return (
            <div key={d.key}>
              <div
                className={`rounded-xl p-3 border transition-all cursor-pointer ${has ? 'bg-success-50/40 border-success-100' : 'bg-surface-50 border-surface-100'} ${isExpanded ? 'rounded-b-none border-b-0' : ''}`}
                onClick={() => setExpandedDim(isExpanded ? null : d.key)}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 mb-1">
                      <span>{has ? '✅' : '⬜'}</span>
                      <span className={`text-xs font-semibold ${has ? 'text-surface-700' : 'text-surface-400'}`}>{d.label}</span>
                      {topics.length > 0 && <span className="text-[10px] text-surface-400">({topics.length})</span>}
                    </div>
                    {has ? (
                      <p className="text-xs text-surface-600 ml-6 leading-relaxed truncate">{v}</p>
                    ) : (
                      <button
                        onClick={(e) => { e.stopPropagation(); goChat(d.hint); }}
                        className="ml-6 text-xs text-primary-500 hover:text-primary-700 hover:underline transition-colors"
                      >💬 {d.hint}</button>
                    )}
                  </div>
                  {topics.length > 0 && (
                    <span className="text-[10px] text-surface-400 flex-shrink-0">{isExpanded ? '▲' : '▼'}</span>
                  )}
                </div>
              </div>
              {isExpanded && topics.length > 0 && (
                <div className="rounded-b-xl border border-t-0 border-surface-200 bg-surface-50/80 p-3 space-y-2">
                  {topics.map((t: any, i: number) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className={`font-medium ${levelColor(t.level)}`}>●</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-surface-700">{t.topic}</span>
                          <span className={`text-[10px] font-medium ${levelColor(t.level)}`}>{levelLabel(t.level)}</span>
                          {t.confidence >= 0.7 && <span className="text-[10px] text-green-500">高置信</span>}
                        </div>
                        {t.detail && <p className="text-surface-500 mt-0.5">{t.detail}</p>}
                        {t.evidence && (
                          <p className="text-[10px] text-surface-400 mt-0.5">
                            {evidenceIcon(t.evidence)} {t.evidence}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const statusStyle: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  mastered: { bg: 'bg-success-50', border: 'border-success-200', text: 'text-success-700', icon: 'text-success-500' },
  completed: { bg: 'bg-success-50', border: 'border-success-200', text: 'text-success-700', icon: 'text-success-500' },
  in_progress: { bg: 'bg-primary-50', border: 'border-primary-300', text: 'text-primary-700', icon: 'text-primary-500' },
  available: { bg: 'bg-surface-50', border: 'border-surface-200', text: 'text-surface-700', icon: 'text-surface-400' },
  locked: { bg: 'bg-surface-100', border: 'border-surface-200', text: 'text-surface-400', icon: 'text-surface-300' },
};
const _def = { bg: 'bg-surface-50', border: 'border-surface-200', text: 'text-surface-700', icon: 'text-surface-400' };

const nodeBorder: Record<string, string> = {
  mastered: 'bg-success-50 border-success-200',
  in_progress: 'bg-primary-50 border-primary-200',
  available: 'bg-surface-50 border-surface-200',
  locked: 'bg-surface-100 border-surface-200',
};

function truncateTitle(title: string, maxLen: number = 6): string {
  if (!title) return '';
  return title.length > maxLen ? title.slice(0, maxLen) + '…' : title;
}

const nodeStatusIcon = (status: string, size: number = 16) => {
  if (status === 'mastered' || status === 'completed') return <CheckCircle2 size={size} />;
  if (status === 'in_progress') return <Loader2 size={size} className="animate-spin" />;
  return <Circle size={size - 2} />;
};

const nodeStatusColor = (status: string) => {
  if (status === 'mastered' || status === 'completed') return 'bg-success-100 text-success-600';
  if (status === 'in_progress') return 'bg-primary-100 text-primary-600';
  if (status === 'locked') return 'bg-surface-100 text-surface-400';
  return 'bg-surface-50 text-surface-400';
};

// ====== 布局常量 ======
const GRAPH_MIN_Y = 150;
const GRAPH_MAX_Y = 200;
const AXIS_TOP = 320;
const AXIS_PAD = 48;
const NODE_BOX_HEIGHT = 56;

export default function LearningPathPage() {
  const nav = useNavigate();
  const chat = useChatPanel();
  const { path, loading, error, fetchPath, generatePath, generationWorkflow } = useLearningPath();
  const { profileV2 } = useProfile();
  const subject = profileV2?.subject_context || {};
  // Settings
  const [planMode, setPlanMode] = useState('textbook'); // textbook / daily / focus // systematic / sprint / gap_fill
  const [granularity, setGranularity] = useState('standard'); // coarse / standard / fine
  const [weekends, setWeekends] = useState(true);
  const [dynamicAdjust, setDynamicAdjust] = useState(true);
  const [reviewEnabled, setReviewEnabled] = useState(true);
  const [textbookAligned, setTextbookAligned] = useState(true);
  const [initTotalDays, setInitTotalDays] = useState(30);
  const [showAdvanced, setShowAdvanced] = useState(false);
  // Course + info
  const [courseName, setCourseName] = useState(subject.subject_name || '');
  const [courseSuggestions, setCourseSuggestions] = useState([]);
  const [courseValid, setCourseValid] = useState(!!subject.subject_name);
  const [courseId, setCourseId] = useState('');
  const [initGoal, setInitGoal] = useState(subject.learning_goal || '');
  const [initTime, setInitTime] = useState(subject.daily_minutes ? subject.daily_minutes + '分钟/天' : '');
  const [initBase, setInitBase] = useState((subject.prior_experience || []).join('、'));
  const [initGenerating, setInitGenerating] = useState(false);
  const [initError, setInitError] = useState('');
  // Planning chat state
  const [planChatMessages, setPlanChatMessages] = useState<{ role: string; text: string }[]>([
    { role: 'assistant', text: '你好！我是你的学习路径规划助手。' },
    { role: 'assistant', text: '在生成路径前，我需要简单了解三件事：\n1️⃣ 你的学习目标是什么？\n2️⃣ 每天能投入多少时间？\n3️⃣ 目前的基础怎么样？' },
    { role: 'assistant', text: '不用一次说完，我们慢慢聊～先告诉我，你想通过这门课达到什么目标？' },
  ]);
  const [planChatInput, setPlanChatInput] = useState('');
  const [planChatFacts, setPlanChatFacts] = useState<Record<string, string>>({});
  const [planChatReady, setPlanChatReady] = useState(false);
  const [planChatBusy, setPlanChatBusy] = useState(false);
  // Draft state (returning from chat)
  const [existingDraft, setExistingDraft] = useState<any>(null);
  const [draftLoading, setDraftLoading] = useState(true);
  // View mode: 'graph' | 'day'
  const [viewMode, setViewMode] = useState<'timeline' | 'day'>('timeline');

  const stages = path?.stages || [];
  const allNodes = stages.flatMap(s => s.nodes || []);
  const totalNodes = allNodes.length;
  const masteredNodes = allNodes.filter(n => n.status === 'mastered' || n.status === 'completed').length;
  const progress = path?.overallProgress ?? (totalNodes > 0 ? Math.round((masteredNodes / totalNodes) * 100) : 0);
  const estimatedDays = path?.estimatedDays || 14;
  const isParent = getCurrentLearner()?.role === 'parent';
  const maxNodesInStage = Math.max(...stages.map(s => s.nodes?.length || 0), 1);

  // ====== 核心算法 ======
  const { stageLayouts, totalDays, dayToPixelX } = useMemo(() => {
    const fallbackDays = Math.ceil(estimatedDays / Math.max(stages.length, 1));
    const totalDays = estimatedDays;
    const weights = stages.map(s => s.estimatedDays || fallbackDays);
    const totalWeight = weights.reduce((a, b) => a + b, 0) || 1;
    let cursor = 0;
    const stageData = stages.map((s, i) => {
      const stageDays = i === stages.length - 1
        ? totalDays - cursor
        : Math.max(1, Math.round(totalDays * weights[i] / totalWeight));
      cursor += stageDays;
      return {
        stage: s,
        index: i,
        days: stageDays,
        endDay: cursor,
        startDay: cursor - stageDays + 1,
        nodeCount: s.nodes?.length || 1,
      };
    });
    const layouts = stageData.map((data, i) => {
      const { startDay, endDay, nodeCount } = data;
      const xRatio = totalDays > 1 ? (startDay - 1) / (totalDays - 1) : 0.5;
      const wave = Math.sin((i / Math.max(stages.length - 1, 1)) * Math.PI * 1.2);
      const cy = GRAPH_MIN_Y + (GRAPH_MAX_Y - GRAPH_MIN_Y) * ((1 - wave) / 2);
      const scale = 0.85 + (nodeCount / maxNodesInStage) * 0.3;
      return { ...data, xRatio, cy, scale };
    });
    const dayToPixelX = (day, graphWidth) => {
      if (totalDays <= 1) return AXIS_PAD + graphWidth * 0.5;
      const ratio = (day - 1) / (totalDays - 1);
      return AXIS_PAD + ratio * (graphWidth - AXIS_PAD * 2);
    };
    return { stageLayouts: layouts, totalDays, dayToPixelX };
  }, [stages, estimatedDays, maxNodesInStage]);

  const formatDuration = (minutes: number) => {
    if (!minutes || minutes <= 0) return '0分钟';
    if (minutes < 60) return `${minutes}分钟`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}h${m}m` : `${h}h`;
  };

  // ====== 容器宽度 ======
  const graphRef = React.useRef<HTMLDivElement>(null);
  const [graphW, setGraphW] = useState(800);

  useEffect(() => {
    const el = graphRef.current;
    if (!el) return;
    const getWidth = () => {
      if (el.offsetWidth > 0) setGraphW(el.offsetWidth);
    };
    getWidth();
    const observer = new ResizeObserver(getWidth);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const ratioToLeftPct = useCallback((ratio: number) => {
    if (graphW <= 0) return '50%';
    const px = AXIS_PAD + ratio * (graphW - AXIS_PAD * 2);
    return `${(px / graphW) * 100}%`;
  }, [graphW]);

  const sessionId = useChatStore((s) => s.currentSessionId);

  // Check for existing planning draft (returning from chat)
  useEffect(() => {
    if (!sessionId) { setDraftLoading(false); return; }
    (async () => {
      try {
        const res = await listPlanningDrafts({ sessionId });
        if (res.ok && res.draft && res.draft.status !== 'expired') {
          setExistingDraft(res.draft);
        }
      } catch {}
      setDraftLoading(false);
    })();
  }, [sessionId]);

  const inProgressStage = stages.find(s => s.nodes?.some(n => n.status === 'in_progress'));
  const [activeStageId, setActiveStageId] = useState<string | null>(null);
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);
  const [examSets, setExamSets] = useState<ExamSet[]>([]);
  const [genExamSet, setGenExamSet] = useState(false);

  const activeStage = stages.find(s => s.id === activeStageId);
  const activeNode = activeStage?.nodes?.find(n => n.id === activeNodeId);

  const handleStageClick = useCallback((stageId: string) => {
    setActiveStageId(stageId);
    setActiveNodeId(null);
  }, []);

  const handleBackToGraph = useCallback(() => {
    setActiveStageId(null);
    setActiveNodeId(null);
  }, []);

  const handleNodeClick = useCallback((nodeId: string) => {
    nav(`/lecture/section/${encodeURIComponent(nodeId)}`);
  }, [nav]);

  // ── Exam sets ──
  useEffect(() => {
    if (sessionId && path?.id) {
      listExamSets({ sessionId }).then((d: any) => {
        setExamSets(d?.examSets || []);
      }).catch(() => {});
    }
  }, [sessionId, path?.id]);

  const handleGenerateExamSet = async (scopeType: 'chapter' | 'stage' | 'path') => {
    setGenExamSet(true);
    try {
      const kps = stages.flatMap(s => (s.nodes || []).map(n => n.topic));
      const scopeId = scopeType === 'path' ? path?.id :
        scopeType === 'stage' ? inProgressStage?.id : '';
      const chTitle = scopeType === 'path' ? path?.courseName || path?.title :
        scopeType === 'stage' ? inProgressStage?.title : stages[0]?.title;
      const res: any = await generateExamSet({
        sessionId: sessionId || '',
        title: `${chTitle || '综合'} · ${scopeType === 'chapter' ? '章节' : scopeType === 'stage' ? '阶段' : '综合'}题集`,
        scopeType,
        scopeId: scopeId || '',
        pathId: path?.id || '',
        stageId: scopeType === 'stage' ? inProgressStage?.id : '',
        chapterId: scopeType === 'chapter' ? stages[0]?.id : '',
        knowledgePoints: kps.slice(0, 15),
        difficulty: 'medium',
      });
      const data = res?.data || res;
      if (data?.examSet) {
        setExamSets(prev => [data.examSet, ...prev]);
      }
    } catch (e: any) {
      alert('题集生成失败: ' + (e?.message || '请重试'));
    }
    setGenExamSet(false);
  };

  const ss = (k: string) => statusStyle[k] || _def;
  const nb = (k: string) => nodeBorder[k] || 'bg-surface-50 border-surface-200';

  const validationRequestRef = useRef(0);
  useEffect(() => {
    const normalized = courseName.trim();
    if (!normalized) { setCourseValid(false); setCourseSuggestions([]); return; }
    const request = ++validationRequestRef.current;
    const timer = window.setTimeout(async () => {
      try {
        const res: any = await validateCourse(normalized);
        if (request !== validationRequestRef.current) return;
        setCourseValid(!!res.valid);
        setCourseSuggestions([]);
        if (res.valid && res.normalizedCourseName && res.normalizedCourseName !== courseName) setCourseName(res.normalizedCourseName);
      } catch { if (request === validationRequestRef.current) setCourseValid(false); }
    }, 400);
    return () => window.clearTimeout(timer);
  }, [courseName]);

  const handleValidateCourse = (name: string) => { setCourseName(name); setCourseId(''); };





  if (loading) return <PageLoading text="加载学习路径中…" />;
  if (error && stages.length === 0) return <PageError title="学习路径加载失败" description={error} onRetry={fetchPath} />;

  if (!path || stages.length === 0) {
    // Show draft confirmation if returning from chat with collected info
    if (existingDraft && !draftLoading) {
      return <PlanningWizard
        sessionId={useChatStore.getState().dataSessionId || sessionId || ''}
        subjectId={subject.subject_id || ''}
        subjectName={subject.subject_name || courseName || ''}
        profileV2={profileV2}
        planMode={planMode}
        pathMode={planMode === 'daily' ? 'daily' : 'textbook'}
        totalDays={initTotalDays}
        weekends={weekends}
        dynamicAdjust={dynamicAdjust}
        reviewEnabled={reviewEnabled}
        onPathGenerated={(pathId: string) => { setExistingDraft(null); fetchPath(); }}
      />;
    }
    if (draftLoading) {
      return <div className="flex-1 flex items-center justify-center"><Loader2 size={24} className="animate-spin text-primary-500" /></div>;
    }
    return (
      <div className="w-full max-w-5xl mx-auto flex-1 animate-fade-in py-8">
        <div className="text-center space-y-2 mb-6">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-primary-50 mb-2">
            <Target size={24} className="text-primary-500" />
          </div>
          <h2 className="font-display text-2xl font-bold text-surface-800">创建学习路径</h2>
          <p className="text-surface-500 text-sm">设定偏好，对话收集信息后生成专属学习计划</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* ── 左栏：表单 ── */}
          <div className="lg:col-span-3 space-y-5">

            <div className="bg-white rounded-2xl p-5 shadow-soft border border-surface-100">
              <label className="text-xs font-medium text-surface-400 uppercase tracking-wide mb-2 block">目标课程</label>
              <input
                value={courseName}
                onChange={e => handleValidateCourse(e.target.value)}
                onBlur={e => handleValidateCourse(e.target.value)}
                placeholder="输入课程名称，系统自动识别"
                className={`w-full px-4 py-3 rounded-xl border text-surface-800 placeholder-surface-400 focus:outline-none focus:ring-2 transition-all text-lg font-medium ${courseName && courseValid ? 'border-green-300 focus:ring-green-400 bg-green-50/30' : courseName && !courseValid ? 'border-amber-300 focus:ring-amber-400' : 'border-surface-200 focus:ring-primary-400'}`}
              />
              {courseName && courseValid && <p className="mt-1.5 text-xs text-green-600 flex items-center gap-1"><CheckCircle2 size={12} />已识别课程</p>}
              {courseSuggestions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <span className="text-xs text-surface-400 mt-0.5">推荐：</span>
                  {courseSuggestions.map((s: string) => (
                    <button key={s} onClick={() => handleValidateCourse(s)} className="text-xs px-2.5 py-1 bg-surface-100 hover:bg-primary-100 hover:text-primary-700 text-surface-600 rounded-full border border-surface-200 transition-all">{s}</button>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-white rounded-2xl p-5 shadow-soft border border-surface-100 space-y-5">
              <div>
                <label className="text-xs font-medium text-surface-400 uppercase tracking-wide mb-3 block">规划模式</label>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    ['textbook', '教材式', '按章节系统推进', BookOpen],
                    ['daily', '日课式', '每日定量学习任务', Calendar],
                    ['focus', '精进式', '聚焦薄弱点突破', Zap],
                  ].map(([v, label, desc, Icon]) => (
                    <button key={v}
                      onClick={() => setPlanMode(v)}
                      className={`p-4 rounded-xl border-2 text-left transition-all ${planMode === v ? 'border-primary-400 bg-primary-50/50 shadow-sm' : 'border-surface-100 hover:border-surface-200 hover:bg-surface-50'}`}
                    >
                      <Icon size={20} className={planMode === v ? 'text-primary-500' : 'text-surface-400'} />
                      <div className="text-sm font-semibold text-surface-800 mt-2">{label}</div>
                      <div className="text-[11px] text-surface-400 mt-1 leading-relaxed">{desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-medium text-surface-400 mb-1.5 block">总天数</label>
                  <input type="number" min={1} max={365} value={initTotalDays}
                    onChange={e => setInitTotalDays(Math.max(1, Math.min(365, Number(e.target.value) || 30)))}
                    className="w-full px-4 py-2.5 rounded-xl border border-surface-200 text-surface-800 focus:outline-none focus:ring-2 focus:ring-primary-400"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-surface-400 mb-1.5 block">周末安排</label>
                  <div className="flex gap-2">
                    {[[true, '坚持学习'], [false, '休息']].map(([v, label]) => (
                      <button key={label} onClick={() => setWeekends(v as boolean)}
                        className={`flex-1 py-2.5 rounded-xl border text-sm transition-all ${weekends === v ? 'border-primary-400 bg-primary-50 text-primary-700 font-medium' : 'border-surface-200 text-surface-500'}`}
                      >{label}</button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-surface-50 border border-surface-100 cursor-pointer hover:bg-surface-100 transition-colors">
                  <input type="checkbox" checked={dynamicAdjust} onChange={e => setDynamicAdjust(e.target.checked)} className="sr-only" />
                  <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-colors ${dynamicAdjust ? 'bg-primary-500 border-primary-500' : 'border-surface-300'}`}>
                    {dynamicAdjust && <CheckCircle2 size={12} className="text-white" />}
                  </div>
                  <span className="text-sm text-surface-700">动态调整</span>
                </label>
                <label className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-surface-50 border border-surface-100 cursor-pointer hover:bg-surface-100 transition-colors">
                  <input type="checkbox" checked={reviewEnabled} onChange={e => setReviewEnabled(e.target.checked)} className="sr-only" />
                  <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-colors ${reviewEnabled ? 'bg-primary-500 border-primary-500' : 'border-surface-300'}`}>
                    {reviewEnabled && <CheckCircle2 size={12} className="text-white" />}
                  </div>
                  <span className="text-sm text-surface-700">含复习阶段</span>
                </label>
              </div>

              <button onClick={() => setShowAdvanced(!showAdvanced)}
                className="w-full text-left text-xs text-surface-400 hover:text-surface-600 flex items-center gap-1 transition-colors"
              >
                <span className="w-3 text-center">{showAdvanced ? '-' : '+'}</span> 高级设置
              </button>
              {showAdvanced && (
                <div className="space-y-4 pt-1">
                  <div>
                    <label className="text-xs font-medium text-surface-400 mb-1.5 block">路径粒度</label>
                    <div className="flex gap-2">
                      {[['coarse', '按周'], ['standard', '标准'], ['fine', '按天']].map(([v, label]) => (
                        <button key={v} onClick={() => setGranularity(v)}
                          className={`flex-1 py-2 rounded-lg border text-xs transition-all ${granularity === v ? 'border-primary-400 bg-primary-50 text-primary-700 font-medium' : 'border-surface-200 text-surface-500'}`}
                        >{label}</button>
                      ))}
                    </div>
                  </div>
                  <label className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-surface-50 border border-surface-100 cursor-pointer hover:bg-surface-100 transition-colors">
                    <input type="checkbox" checked={textbookAligned} onChange={e => setTextbookAligned(e.target.checked)} className="sr-only" />
                    <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-colors ${textbookAligned ? 'bg-primary-500 border-primary-500' : 'border-surface-300'}`}>
                      {textbookAligned && <CheckCircle2 size={12} className="text-white" />}
                    </div>
                    <span className="text-sm text-surface-700">关联教材章节</span>
                  </label>
                </div>
              )}
            </div>

            {initError && (
              <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600 flex items-center gap-2">
                <AlertCircle size={16} /> {initError}
              </div>
            )}

            <div className="flex gap-3">
              <button onClick={async () => {
            const sid = useChatStore.getState().dataSessionId || sessionId || '';
            try { await enableProfileExtraction(sid); } catch {}
            const msg = [
              '帮我制定学习计划',
              courseName && '课程：' + courseName,
              '规划模式：' + (planMode === 'textbook' ? '教材式按章节系统学习' : planMode === 'daily' ? '日课式每日定量任务' : '精进式针对薄弱点突破'),
              '总天数：' + initTotalDays + '天',
              weekends ? '周末也学' : '周末休息',
              dynamicAdjust && '需要动态调整',
              !reviewEnabled && '不需要复习阶段',
            ].filter(Boolean).join('，') + '。请先问我几个问题了解我的具体情况吧。';
            useChatStore.getState().newSession();
            nav('/chat', { state: { initialMessage: msg, chatMode: 'planning' } });
          }}
            className="flex-1 py-3 border-2 border-primary-200 text-primary-700 rounded-xl font-medium hover:bg-primary-50 transition-colors text-sm"
          >
            去对话收集信息
          </button>
          <button onClick={() => {
            generatePath({
              subjectId: subject.subject_id || '',
              planMode: planMode === 'focus' ? 'focus' : '',
              pathMode: planMode === 'daily' ? 'daily' : 'textbook',
              totalDays: initTotalDays,
              weekends: weekends,
              dynamicAdjust: dynamicAdjust,
              reviewEnabled: reviewEnabled,
              userMessage: [courseName && '学习' + courseName, '规划模式：' + planMode, '总天数：' + initTotalDays + '天'].filter(Boolean).join('。'),
            }).then(path => { if (!path) setInitError('生成失败'); }).catch(e => setInitError(e?.message || '生成失败'));
          }}
            disabled={generationWorkflow?.status === 'running'}
            className="flex-1 py-3 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors text-sm flex items-center justify-center gap-2"
          >
            {generationWorkflow?.status === 'running' ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />} {generationWorkflow?.status === 'running' ? '正在生成路径' : '直接生成路径'}
          </button>
        </div>
      </div>

      {/* ── 右栏：画像进度 ── */}
      <div className="lg:col-span-2 space-y-5">
        <ProfileInfoPanel sessionId={useChatStore.getState().dataSessionId || sessionId || ''} />
      </div>
    </div>
  </div>
  );
}
  const isDetailView = !!activeStageId;

  // ── Daily/Focus modes → use PathModeRouter. Textbook → keep original UI ──
  const isDailyOrFocus = stages.some((s: any) =>
    (s as any).path_mode === 'daily' || (s as any).plan_mode === 'focus'
  );
  if (isDailyOrFocus) {
    return (
      <div className="animate-fade-in flex-1 flex flex-col">
        <div className="flex items-center justify-between mb-5 flex-shrink-0">
          <div>
            <h2 className="font-display text-2xl font-bold text-surface-800">学习路径</h2>
            <p className="text-surface-500 mt-1">
              {(() => {
                for (const s of stages) {
                  if ((s as any).path_mode === 'daily') return '每日任务式学习计划';
                  if ((s as any).plan_mode === 'focus') return '精进突破冲刺计划';
                }
                return '结构化进阶学习路线';
              })()}
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-4 py-2 bg-surface-50 rounded-xl">
              <Target size={18} className="text-primary-500" />
              <span className="text-sm font-medium text-surface-600">进度: {progress}%</span>
            </div>
            {!isParent && (
              <button onClick={() => chat.setOpen(true)} className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors">
                <Zap size={18} />完善路径
              </button>
            )}
          </div>
        </div>
        <PathModeRouter
          stages={stages as any}
          path={path}
          progress={progress}
          totalNodes={totalNodes}
          masteredNodes={masteredNodes}
          onNavigateChapter={(chId) => { if (chId) nav(`/lecture/${encodeURIComponent(chId)}`); }}
          onNavigateSection={(secId) => { if (secId) nav(`/lecture/section/${encodeURIComponent(secId)}`); }}
        />
      </div>
    );
  }

  return (
    <div className="animate-fade-in flex-1 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-5 flex-shrink-0">
        <div>
          <h2 className="font-display text-2xl font-bold text-surface-800">学习路径</h2>
          <p className="text-surface-500 mt-1">基于你的学习画像智能规划的进阶路线</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-4 py-2 bg-surface-50 rounded-xl">
            <Target size={18} className="text-primary-500" />
            <span className="text-sm font-medium text-surface-600">进度: {progress}%</span>
          </div>
          {!isParent && (
          <button onClick={() => nav('/chat', { state: { initialMessage: '调整一下我的学习路径' } })} className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors">
            <Zap size={18} />修改路径
          </button>
          )}
        </div>
      </div>

      {/* Overview card */}
      <div className="bg-white rounded-2xl p-5 shadow-soft mb-4 flex-shrink-0">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="font-display text-lg font-semibold text-surface-800">{path.title}</h3>
            <p className="text-surface-500 text-sm mt-0.5">{path.description || '个性化学习路径规划'}</p>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 bg-accent-50 rounded-lg">
            <Calendar size={14} className="text-accent-500" />
            <span className="text-sm text-accent-700 font-medium">预计 {totalDays} 天</span>
          </div>
        </div>
        <div className="relative h-2.5 bg-surface-100 rounded-full overflow-hidden">
          <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary-500 to-accent-500 rounded-full transition-all duration-1000" style={{ width: `${progress}%` }} />
        </div>
        <div className="flex items-center justify-between mt-2 text-sm">
          <span className="text-surface-500">已完成 {masteredNodes} 个知识点</span>
          <span className="text-surface-500">共 {totalNodes} 个知识点 · {stages.length} 个阶段</span>
        </div>
      </div>

      {/* ── Exam Sets section ── */}
      {!isParent && (
        <div className="bg-white rounded-2xl p-5 shadow-soft mb-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display text-sm font-semibold text-surface-700 flex items-center gap-2">
              <ClipboardList size={16} className="text-accent-500" />题集
            </h3>
            <div className="flex items-center gap-1.5">
              <button onClick={() => handleGenerateExamSet('chapter')} disabled={genExamSet}
                className="flex items-center gap-1 px-2.5 py-1.5 bg-accent-500 text-white rounded-lg text-xs hover:bg-accent-600 disabled:opacity-50 transition-colors"
                style={{ backgroundColor: '#14b8a6' }}>
                <Plus size={12} />{genExamSet ? '...' : '章节题集'}
              </button>
              <button onClick={() => handleGenerateExamSet('stage')} disabled={genExamSet}
                className="flex items-center gap-1 px-2.5 py-1.5 bg-accent-500 text-white rounded-lg text-xs hover:bg-accent-600 disabled:opacity-50 transition-colors"
                style={{ backgroundColor: '#14b8a6' }}>
                <Plus size={12} />{genExamSet ? '...' : '阶段题集'}
              </button>
              <button onClick={() => handleGenerateExamSet('path')} disabled={genExamSet}
                className="flex items-center gap-1 px-2.5 py-1.5 bg-primary-500 text-white rounded-lg text-xs hover:bg-primary-600 disabled:opacity-50 transition-colors">
                <Plus size={12} />{genExamSet ? '...' : '综合题集'}
              </button>
            </div>
          </div>
          {examSets.length === 0 ? (
            <p className="text-xs text-surface-400">暂无题集，点击上方按钮生成</p>
          ) : (
            <div className="space-y-2">
              {examSets.map(es => (
                <div key={es.id}
                  className="flex items-center gap-3 p-3 rounded-xl border border-surface-200 hover:border-accent-300 hover:shadow-soft transition-all cursor-pointer"
                  onClick={() => nav(`/practice?examSetId=${es.id}`)}>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${es.status === 'completed' ? 'bg-success-100 text-success-600' : es.status === 'in_progress' ? 'bg-primary-100 text-primary-600' : 'bg-surface-100 text-surface-400'}`}>
                    <ClipboardList size={14} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-surface-700 truncate">{es.title}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[10px] text-surface-400">{es.questionCount} 题 · {es.estimatedMinutes}分钟</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                        es.scopeType === 'path' ? 'bg-primary-50 text-primary-600' :
                        es.scopeType === 'stage' ? 'bg-accent-50 text-accent-600' : 'bg-surface-100 text-surface-500'
                      }`}>
                        {es.scopeType === 'chapter' ? '章节' : es.scopeType === 'stage' ? '阶段' : '综合'}
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                        es.status === 'completed' ? 'bg-success-50 text-success-600' :
                        es.status === 'in_progress' ? 'bg-primary-50 text-primary-600' : 'bg-surface-100 text-surface-500'
                      }`}>
                        {es.status === 'completed' ? '已完成' : es.status === 'in_progress' ? '进行中' : '未开始'}
                      </span>
                    </div>
                  </div>
                  <ChevronRight size={14} className="text-surface-300 flex-shrink-0" />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {!isParent && (
        <div className="bg-white rounded-2xl p-4 shadow-soft mb-4">
          <details className="group" open={path.adjustments && path.adjustments.length > 0}>
            <summary className="flex items-center gap-2 cursor-pointer list-none">
              <Brain size={16} className="text-amber-500" />
              <span className="text-sm font-semibold text-surface-700">学习路径调整记录</span>
              {path.adjustments && path.adjustments.length > 0 && (
                <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded-full text-[10px] font-medium">{path.adjustments.length}</span>
              )}
              <span className="ml-auto text-surface-400 group-open:rotate-180 transition-transform">▾</span>
            </summary>
            <div className="mt-2 space-y-2 max-h-48 overflow-y-auto">
              {!path.adjustments || path.adjustments.length === 0 ? (
                <p className="text-xs text-surface-400">暂无调整记录。学习路径会根据你的答题表现自动调整。</p>
              ) : (
                path.adjustments.map((adj, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <span className="mt-0.5 flex-shrink-0">
                      {adj.type === 'accelerate' ? '⚡' : adj.type === 'remedial' ? '⚠️' : adj.type === 'insert' ? '➕' : adj.type === 'split' ? '✂️' : adj.type === 'sprint' ? '🎯' : '📌'}
                    </span>
                    <span className="text-surface-600">{typeof adj === 'string' ? adj : adj.description}</span>
                  </div>
                ))
              )}
            </div>
          </details>
        </div>
      )}

      {/* ── View mode tab bar ── */}
      {!isDetailView && (
        <div className="flex items-center gap-1 mb-4">
          <button
            onClick={() => setViewMode('timeline')}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
              viewMode === 'timeline'
                ? 'bg-primary-100 text-primary-700 shadow-sm'
                : 'text-surface-500 hover:text-surface-700 hover:bg-surface-50'
            }`}
          >
            阶段
          </button>
          <button
            onClick={() => setViewMode('day')}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
              viewMode === 'day'
                ? 'bg-primary-100 text-primary-700 shadow-sm'
                : 'text-surface-500 hover:text-surface-700 hover:bg-surface-50'
            }`}
          >
            <Calendar size={16} className="inline mr-1.5" />
            日视图
          </button>
        </div>
      )}

      {viewMode === 'day' && !isDetailView ? (
        /* ── 日视图（全宽） ── */
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <DayPlanView
            dayPlan={(path as any)?.day_plan ?? null}
            adjustedDays={(path as any)?.day_plan?._adjusted_days}
            onItemClick={(sectionId) => {
              if (sectionId) nav(`/lecture/section/${encodeURIComponent(sectionId)}`);
            }}
          />
        </div>
      ) : (
      /* Main content - 两栏，撑满剩余高度 */
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-1 min-h-0">
        {/* 左侧：学习阶段 */}
        <div className="lg:col-span-2 bg-white rounded-2xl p-6 shadow-soft flex flex-col">
          {isDetailView ? (
            <div className="animate-fade-in flex-1 overflow-auto">
              <button onClick={handleBackToGraph} className="flex items-center gap-1.5 text-sm text-surface-500 hover:text-primary-600 transition-colors mb-4">
                <ArrowLeft size={16} />
                <span>返回学习节点</span>
              </button>

              <div className="mb-4">
                <h3 className="font-display text-lg font-semibold text-surface-800 mb-1">{activeStage?.title}</h3>
                <div className="flex items-center gap-3 text-sm text-surface-500">
                  {activeStage?.objective && <span>{activeStage.objective}</span>}
                  {activeStage?.estimatedDays && (
                    <span className="flex items-center gap-1 text-xs text-surface-400">
                      <Calendar size={12} />预计 {activeStage.estimatedDays} 天
                    </span>
                  )}
                </div>
              </div>

              {/* -- 章节列表（新格式） -- */}
              { activeStage?.chapters?.length > 0 && (
                <div className="grid grid-cols-1 gap-3 mb-4">
                  {activeStage.chapters.map((ch: any, ci: number) => {
                    const secCount = ch.sections?.length ?? 0;
                    const totalKps = ch.sections?.reduce((s: number, sec: any) => s + (sec.knowledgePoints?.length ?? 0), 0) ?? 0;
                    return (
                      <div key={ch.id}
                        onClick={() => { if (ch.id) nav(`/lecture/${encodeURIComponent(ch.id)}`); }}
                        className="flex items-center gap-4 p-5 rounded-xl cursor-pointer transition-all border border-surface-200 bg-surface-50 hover:border-primary-300 hover:shadow-elevated group">
                        <div className="w-11 h-11 rounded-xl bg-primary-100 text-primary-600 flex items-center justify-center flex-shrink-0 font-bold text-base">{ci + 1}</div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-semibold text-surface-800 truncate group-hover:text-primary-600 transition-colors">{ch.title}</p>
                          </div>
                          <div className="flex items-center gap-2 mt-1 text-xs text-surface-400">
                            <span className="flex items-center gap-0.5"><BookOpen size={12} />{secCount} 小节</span>
                            <span>{totalKps} 知识点</span>
                            {ch.mindmapId && <span className="text-accent-500">思维导图</span>}
                          </div>
                        </div>
                        <ExternalLink size={16} className="text-surface-300 group-hover:text-primary-400 transition-colors" />
                      </div>
                    );
                  })}
                </div>
              )}

              {/* -- 知识点列表（仅旧格式兜底） -- */}
              { (!activeStage?.chapters || activeStage.chapters.length === 0) && (
                <div className="grid grid-cols-1 gap-3">
                  {activeStage?.nodes?.map((node: any, ni: number) => {
                  const nc = nb(node.status || 'available');
                  const nStatus = node.status || 'available';
                  const resourceCount = node.resources?.length || 0;
                  const essentialCount = node.resources?.filter((r: any) => r.essential)?.length || 0;
                  return (
                    <div
                      key={node.id}
                      onClick={() => handleNodeClick(node.id)}
                      className={`flex items-center gap-4 p-5 rounded-xl cursor-pointer transition-all border ${nc} hover:shadow-elevated hover:border-primary-300 group`}
                    >
                      <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${nodeStatusColor(nStatus)}`}>
                        {nodeStatusIcon(nStatus, 20)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-surface-400 font-medium w-5 text-right">{ni + 1}</span>
                          <p className="text-sm font-semibold text-surface-800 truncate group-hover:text-primary-600 transition-colors">{node.topic}</p>
                          {node.isKeyPoint && (
                            <span className="text-[10px] px-1.5 py-0.5 bg-warning-100 text-warning-700 rounded-full font-medium flex-shrink-0">重点</span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 mt-1.5 text-xs text-surface-400">
                          {resourceCount > 0 ? (
                            <>
                              <span className="flex items-center gap-1"><BookOpen size={10} />{resourceCount} 个资源</span>
                              {essentialCount > 0 && <span className="text-error-500">{essentialCount} 个必学</span>}
                            </>
                          ) : (
                            <span className="text-surface-300 italic">暂无资源</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <div className="w-14 h-1.5 bg-surface-100 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${(node.mastery || 0) >= 80 ? 'bg-success-500' : (node.mastery || 0) >= 40 ? 'bg-primary-500' : 'bg-surface-300'}`} style={{ width: `${node.mastery || 0}%` }} />
                        </div>
                        <span className="text-xs font-medium text-surface-500 w-7 text-right tabular-nums">{node.mastery || 0}%</span>
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            nav(`/resources?taskId=${encodeURIComponent(node.id)}`);
                          }}
                          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] text-surface-500 hover:bg-surface-100 hover:text-primary-600"
                        >
                          关联资源<ExternalLink size={12} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
              )}
            </div>
          ) : (
            <div className="flex-1 flex flex-col min-h-0">
              <h3 className="font-display text-lg font-semibold text-surface-800 mb-3 flex-shrink-0">学习节点 · 时间规划</h3>
              <div className="relative flex-1" ref={graphRef}>
                <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ zIndex: 0 }}>
                  {stageLayouts.map((layout, i) => {
                    if (i >= stageLayouts.length - 1) return null;
                    const sx = dayToPixelX(layout.startDay, graphW);
                    const sy = layout.cy;
                    const nextLayout = stageLayouts[i + 1];
                    const tx = dayToPixelX(nextLayout.startDay, graphW);
                    const ty = nextLayout.cy;
                    const locked = nextLayout.stage.nodes?.every(n => n.status === 'locked');
                    const midX = (sx + tx) / 2;
                    const d = `M${sx},${sy} C${midX},${sy} ${midX},${ty} ${tx},${ty}`;
                    return <path key={`conn-${layout.stage.id}`} d={d} fill="none" stroke={locked ? '#e2e8f0' : '#93c5fd'} strokeWidth="2.5" strokeDasharray="5,5" />;
                  })}

                  {stageLayouts.map((layout) => {
                    const cx = dayToPixelX(layout.startDay, graphW);
                    return (
                      <line key={`drop-${layout.stage.id}`} x1={cx} y1={layout.cy + NODE_BOX_HEIGHT / 2 + 40} x2={cx} y2={AXIS_TOP} stroke="#cbd5e1" strokeWidth="1.5" strokeDasharray="4,4" opacity="0.7" />
                    );
                  })}

                  {(() => {
                    const axStart = dayToPixelX(1, graphW);
                    const axEnd = dayToPixelX(totalDays, graphW);
                    const stageStartDays = new Set(stageLayouts.map(l => l.startDay));
                    const stageEndDays = new Set(stageLayouts.map(l => l.endDay));
                    const showAllLabels = totalDays <= 20;

                    return (
                      <>
                        <line x1={axStart} y1={AXIS_TOP} x2={axEnd} y2={AXIS_TOP} stroke="#cbd5e1" strokeWidth="2" />
                        <circle cx={axStart} cy={AXIS_TOP} r="4" fill="#64748b" />
                        <text x={axStart - 8} y={AXIS_TOP + 18} textAnchor="end" fill="#64748b" fontSize="11" fontWeight={600}>开始</text>
                        <polygon points={`${axEnd},${AXIS_TOP} ${axEnd - 10},${AXIS_TOP - 5} ${axEnd - 10},${AXIS_TOP + 5}`} fill="#cbd5e1" />
                        <text x={axEnd + 8} y={AXIS_TOP + 18} textAnchor="start" fill="#64748b" fontSize="11" fontWeight={600}>完成</text>

                        {Array.from({ length: totalDays }, (_, idx) => {
                          const day = idx + 1;
                          const dx = dayToPixelX(day, graphW);
                          const isStageStart = stageStartDays.has(day);
                          const isStageEnd = stageEndDays.has(day);
                          const isImportant = isStageStart || isStageEnd;

                          return (
                            <g key={`tick-${day}`}>
                              <line x1={dx} y1={AXIS_TOP - (isImportant ? 8 : 5)} x2={dx} y2={AXIS_TOP + (isImportant ? 8 : 5)} stroke={isStageStart ? '#3b82f6' : isStageEnd ? '#94a3b8' : '#e2e8f0'} strokeWidth={isImportant ? 2 : 1} />
                              {isStageStart && (
                                <>
                                  <circle cx={dx} cy={AXIS_TOP} r="5" fill="#3b82f6" stroke="#fff" strokeWidth="2" />
                                  <text x={dx} y={AXIS_TOP + 22} textAnchor="middle" fill="#3b82f6" fontSize="10" fontWeight={700}>D{day}</text>
                                </>
                              )}
                              {isStageEnd && !isStageStart && (
                                <>
                                  <circle cx={dx} cy={AXIS_TOP} r="3.5" fill="#94a3b8" stroke="#fff" strokeWidth="1.5" />
                                  <text x={dx} y={AXIS_TOP + 18} textAnchor="middle" fill="#94a3b8" fontSize="9">D{day}</text>
                                </>
                              )}
                              {!isImportant && showAllLabels && day % 3 === 0 && (
                                <text x={dx} y={AXIS_TOP + 15} textAnchor="middle" fill="#cbd5e1" fontSize="9">{day}</text>
                              )}
                            </g>
                          );
                        })}

                        {stageLayouts.map((layout, i) => {
                          if (layout.startDay === layout.endDay) return null;
                          const sx = dayToPixelX(layout.startDay, graphW);
                          const ex = dayToPixelX(layout.endDay, graphW);
                          const midX = (sx + ex) / 2;
                          return (
                            <g key={`range-${i}`}>
                              <rect x={sx} y={AXIS_TOP - 35} width={ex - sx} height="20" rx="4" fill="#f1f5f9" opacity="0.8" />
                              <text x={midX} y={AXIS_TOP - 21} textAnchor="middle" fill="#64748b" fontSize="10" fontWeight={500}>{truncateTitle(layout.stage.title, 8)}</text>
                            </g>
                          );
                        })}
                      </>
                    );
                  })()}

                  {(() => {
                    const axStart = dayToPixelX(1, graphW);
                    let progressEndDay = 0;
                    let isInProgress = false;
                    for (let i = 0; i < stageLayouts.length; i++) {
                      const layout = stageLayouts[i];
                      const nodes = layout.stage.nodes || [];
                      const allDone = nodes.every(n => n.status === 'mastered' || n.status === 'completed');
                      const hasActive = nodes.some(n => n.status === 'in_progress');
                      if (allDone) { progressEndDay = layout.endDay; }
                      else if (hasActive) { progressEndDay = layout.startDay; isInProgress = true; break; }
                      else { break; }
                    }
                    if (progressEndDay === 0) return null;
                    const endX = dayToPixelX(progressEndDay, graphW);
                    return <line x1={axStart} y1={AXIS_TOP} x2={endX} y2={AXIS_TOP} stroke={isInProgress ? '#3b82f6' : '#22c55e'} strokeWidth="3" strokeLinecap="round" opacity="0.8" />;
                  })()}
                </svg>

                {/* HTML层：学习节点 */}
                {stageLayouts.map((layout) => {
                  const { stage, startDay, endDay, xRatio, cy, scale } = layout;
                  const hasActive = stage.nodes?.some(n => n.status === 'in_progress');
                  const allMastered = stage.nodes?.every(n => n.status === 'mastered' || n.status === 'completed');
                  const allLocked = stage.nodes?.every(n => n.status === 'locked');
                  const stageDuration = stage.nodes?.reduce((sum: number, n: any) => sum + (n.duration || 0), 0) || 0;
                  const stageStatus = allMastered ? 'mastered' : hasActive ? 'in_progress' : allLocked ? 'locked' : 'available';
                  const _s = ss(stageStatus);
                  const iconSize = Math.round(24 * scale);
                  const boxSize = Math.round(NODE_BOX_HEIGHT * scale);
                  return (
                    <div key={stage.id} className="absolute transform -translate-x-1/2 -translate-y-1/2" style={{ left: ratioToLeftPct(xRatio), top: cy, zIndex: 10 }}>
                      <button onClick={() => handleStageClick(stage.id)} disabled={allLocked} className={`relative flex flex-col items-center transition-all ${allLocked ? 'cursor-not-allowed' : 'cursor-pointer group'}`}>
                        <div className={`rounded-2xl ${_s.bg} border-2 ${_s.border} flex items-center justify-center transition-all group-hover:scale-110 group-hover:shadow-md`} style={{ width: boxSize, height: boxSize }}>
                          {allMastered && <CheckCircle2 size={iconSize} className={_s.icon} />}
                          {hasActive && !allMastered && <Loader2 size={iconSize} className={`${_s.icon} animate-spin`} />}
                          {!hasActive && !allMastered && !allLocked && <Circle size={iconSize} className={_s.icon} />}
                          {allLocked && <Lock size={iconSize} className={_s.icon} />}
                        </div>
                        <div className="mt-1.5 px-2.5 py-1 rounded-lg text-center bg-white shadow-sm border border-surface-100 relative group/title max-w-[90px] hover:max-w-[280px] transition-all duration-300 hover:z-20 overflow-hidden">
                          <p className={`text-[11px] font-semibold whitespace-nowrap ${allLocked ? 'text-surface-400' : 'text-surface-700'}`}>
                            {stage.title}
                          </p>
                          {/* 右侧渐变虚化遮罩 - hover时消失 */}
                          <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-white via-white/70 to-transparent pointer-events-none rounded-r-lg group-hover/title:opacity-0 transition-opacity duration-200" />
                        </div>
                        <div className="flex items-center gap-1 mt-0.5">
                          <Calendar size={9} className="text-surface-400" />
                          <span className={`text-[9px] font-medium ${allLocked ? 'text-surface-300' : 'text-surface-500'}`}>{startDay === endDay ? `第${startDay}天` : `第${startDay}-${endDay}天`}</span>
                        </div>
                        <div className="flex items-center gap-1 mt-0.5">
                          <Clock size={9} className="text-surface-400" />
                          <span className={`text-[9px] font-medium ${allLocked ? 'text-surface-300' : 'text-surface-500'}`}>{formatDuration(stageDuration)}</span>
                        </div>
                        {hasActive && <div className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-primary-500 rounded-full flex items-center justify-center shadow-sm"><span className="text-[10px] text-white font-bold">{layout.index + 1}</span></div>}
                      </button>
                    </div>
                  );
                })}

                <div className="absolute" style={{ left: `${(AXIS_PAD / graphW) * 100}%`, top: AXIS_TOP + 30, zIndex: 5 }}>
                  <span className="text-[10px] text-surface-400">{stages.filter(s => s.nodes?.every(n => n.status === 'mastered' || n.status === 'completed')).length}/{stages.length} 阶段完成 · 共 {totalDays} 天</span>
                </div>
              </div>

              <div className="flex items-center gap-6 pt-3 border-t border-surface-100 flex-shrink-0">
                <div className="flex items-center gap-2"><CheckCircle2 size={14} className="text-success-500" /><span className="text-xs text-surface-600">已掌握</span></div>
                <div className="flex items-center gap-2"><Loader2 size={14} className="text-primary-500" /><span className="text-xs text-surface-600">进行中</span></div>
                <div className="flex items-center gap-2"><Circle size={14} className="text-surface-400" /><span className="text-xs text-surface-600">待解锁</span></div>
                <div className="flex items-center gap-2"><Lock size={14} className="text-surface-300" /><span className="text-xs text-surface-600">未解锁</span></div>
              </div>
            </div>
          )}
        </div>

        {/* 右侧：概览卡片 */}
        <div className="bg-white rounded-2xl p-6 shadow-soft flex flex-col justify-center">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">学习概览</h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-surface-500">总体进度</span>
              <span className="text-sm font-semibold text-primary-600">{progress}%</span>
            </div>
            <div className="relative h-2 bg-surface-100 rounded-full overflow-hidden">
              <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary-500 to-accent-500 rounded-full" style={{ width: `${progress}%` }} />
            </div>
            <div className="grid grid-cols-2 gap-3 mt-4">
              <div className="bg-surface-50 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-surface-800">{stages.length}</p>
                <p className="text-xs text-surface-400 mt-1">学习阶段</p>
              </div>
              <div className="bg-surface-50 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-surface-800">{totalNodes}</p>
                <p className="text-xs text-surface-400 mt-1">知识点</p>
              </div>
              <div className="bg-success-50 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-success-600">{masteredNodes}</p>
                <p className="text-xs text-success-500 mt-1">已掌握</p>
              </div>
              <div className="bg-primary-50 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-primary-600">{totalDays}</p>
                <p className="text-xs text-primary-500 mt-1">预计天数</p>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-surface-100">
              <div className="flex items-center justify-between">
                <span className="text-sm text-surface-500 flex items-center gap-1.5">
                  <Clock size={14} className="text-primary-400" />
                  今日学习时长
                </span>
                <span className="text-lg font-bold text-primary-600">{formatDuration(path?.todayDuration || 0)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      )}
    </div>
  );
}
