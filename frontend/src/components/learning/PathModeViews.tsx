import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BookOpen, Calendar, Clock, Target, Zap, ArrowRight, CheckCircle2,
  Circle, Brain, Volume2, PenTool, Mic, FileText, Bookmark, Layers,
  ChevronRight, Play, Sparkles, Trophy, AlertCircle, Hash, Lightbulb,
  ExternalLink, Star,
} from 'lucide-react';
import type { LearningStage, Chapter, Section } from '../../types/learningPath';

// ══════════════════════════════════════════════════════════════════════
// Types
// ══════════════════════════════════════════════════════════════════════

interface StageLike {
  stage_id?: string;
  id?: string;
  title: string;
  order: number;
  chapters?: ChapterLike[];
  nodes?: any[];
  path_mode?: string;
  plan_mode?: string;
}

interface ChapterLike {
  chapter_id?: string;
  id?: string;
  title: string;
  order: number;
  sections?: SectionLike[];
}

interface SectionLike {
  section_id?: string;
  id?: string;
  title: string;
  goal?: string;
  estimated_minutes?: number;
  content_type?: string;
  task_type?: string;
  knowledge_points?: { name: string; type?: string }[];
  status?: string;
}

interface Props {
  stages: StageLike[];
  path?: any;
  progress: number;
  totalNodes: number;
  masteredNodes: number;
  onNavigateChapter: (chapterId: string) => void;
  onNavigateSection: (sectionId: string) => void;
}

// ══════════════════════════════════════════════════════════════════════
// Task type visual config
// ══════════════════════════════════════════════════════════════════════

const TASK_TYPE_CONFIG: Record<string, { icon: typeof BookOpen; label: string; color: string; bg: string }> = {
  vocabulary: { icon: Bookmark, label: '词汇', color: 'text-violet-600', bg: 'bg-violet-50 border-violet-200' },
  listening:   { icon: Volume2, label: '听力', color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200' },
  reading:     { icon: FileText, label: '阅读', color: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200' },
  grammar:     { icon: PenTool, label: '语法', color: 'text-amber-600', bg: 'bg-amber-50 border-amber-200' },
  speaking:    { icon: Mic, label: '口语', color: 'text-rose-600', bg: 'bg-rose-50 border-rose-200' },
  writing:     { icon: PenTool, label: '写作', color: 'text-orange-600', bg: 'bg-orange-50 border-orange-200' },
  review:      { icon: Brain, label: '复习', color: 'text-cyan-600', bg: 'bg-cyan-50 border-cyan-200' },
};

const CONTENT_TYPE_CONFIG: Record<string, { icon: typeof BookOpen; label: string }> = {
  lecture:      { icon: FileText, label: '讲义' },
  memory_drill: { icon: Brain, label: '闪卡' },
  step_through: { icon: Layers, label: '分步' },
};

function TaskTypeBadge({ type }: { type: string }) {
  const cfg = TASK_TYPE_CONFIG[type];
  if (!cfg) return null;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg border text-[10px] font-medium ${cfg.bg} ${cfg.color}`}>
      <Icon size={10} />{cfg.label}
    </span>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Shared: header + progress bar
// ══════════════════════════════════════════════════════════════════════

function PathHeader({ path, progress, totalNodes, masteredNodes, stages }: Pick<Props, 'path' | 'progress' | 'totalNodes' | 'masteredNodes' | 'stages'>) {
  const totalDays = stages.reduce((sum, s) => {
    const chapters = s.chapters || [];
    return sum + chapters.reduce((cs, ch) =>
      cs + (ch.sections || []).reduce((ss, sec) => ss + (sec.estimated_minutes || 30), 0), 0);
  }, 0);
  const totalHours = Math.round(totalDays / 60);

  return (
    <div className="bg-white rounded-2xl p-6 shadow-soft mb-6">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="font-display text-xl font-bold text-surface-900">
            {path?.title || path?.courseName || '学习路径'}
          </h3>
          <p className="text-surface-500 text-sm mt-1">
            {path?.description || '个性化学习规划'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-2 bg-surface-50 rounded-xl">
            <Clock size={16} className="text-surface-400" />
            <span className="text-sm font-medium text-surface-600">约 {totalHours}h</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 bg-primary-50 rounded-xl">
            <Target size={16} className="text-primary-500" />
            <span className="text-sm font-bold text-primary-700">{progress}%</span>
          </div>
        </div>
      </div>
      <div className="h-2.5 bg-surface-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-blue-500 via-violet-500 to-emerald-500 rounded-full transition-all duration-1000"
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="flex items-center justify-between mt-2 text-xs text-surface-400">
        <span>已完成 {masteredNodes} 项</span>
        <span>共 {totalNodes} 项 · {stages.length} 个阶段</span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// 📅 DailyPathView — weekly calendar with daily task cards
// ══════════════════════════════════════════════════════════════════════

function DailyPathView({ stages, onNavigateSection, path, progress, totalNodes, masteredNodes }: Props) {
  // Flatten all days from all weeks
  const allDays = useMemo(() => {
    const days: { weekTitle: string; weekIdx: number; day: ChapterLike }[] = [];
    stages.forEach((stage, wi) => {
      (stage.chapters || []).forEach(ch => {
        days.push({ weekTitle: stage.title, weekIdx: wi, day: ch });
      });
    });
    return days;
  }, [stages]);

  // Group by week for the calendar grid
  const weeks = useMemo(() => {
    const map: Record<number, { title: string; days: ChapterLike[] }> = {};
    stages.forEach((stage, wi) => {
      map[wi] = { title: stage.title, days: stage.chapters || [] };
    });
    return Object.values(map);
  }, [stages]);

  const totalTasks = allDays.reduce((s, d) => s + (d.day.sections?.length || 0), 0);
  const completedTasks = allDays.reduce((s, d) =>
    s + (d.day.sections || []).filter(sec => sec.status === 'mastered' || sec.status === 'completed').length, 0);

  return (
    <div className="space-y-6">
      <PathHeader path={path} progress={progress} totalNodes={totalNodes} masteredNodes={masteredNodes} stages={stages} />

      {/* Weekly progress summary */}
      <div className="grid grid-cols-3 gap-4">
        {weeks.map((week, wi) => {
          const weekTasks = week.days.reduce((s, d) => s + (d.sections?.length || 0), 0);
          const weekDone = week.days.reduce((s, d) =>
            s + (d.sections || []).filter(sec => sec.status === 'mastered' || sec.status === 'completed').length, 0);
          const pct = weekTasks > 0 ? Math.round((weekDone / weekTasks) * 100) : 0;
          return (
            <div key={wi}
              className={`rounded-2xl p-5 border-2 transition-all cursor-default
                ${wi === 0 ? 'border-blue-200 bg-blue-50/30 shadow-blue-100/30 shadow-md' :
                  pct === 100 ? 'border-emerald-200 bg-emerald-50/30' :
                  'border-surface-200 bg-white shadow-soft'}`}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold text-surface-500 uppercase tracking-wider">
                  {week.title}
                </span>
                {wi === 0 && (
                  <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-600 text-[10px] font-bold">当前</span>
                )}
              </div>
              <div className="text-3xl font-bold text-surface-900 font-display mb-1">{pct}%</div>
              <div className="flex items-center gap-2 text-xs text-surface-500">
                <CheckCircle2 size={12} className="text-emerald-500" />
                {weekDone}/{weekTasks} 完成
              </div>
              <div className="mt-3 h-1.5 bg-surface-200 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-blue-500 to-emerald-500 rounded-full transition-all duration-700"
                  style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Daily task calendar */}
      <div className="bg-white rounded-2xl shadow-soft overflow-hidden">
        <div className="bg-gradient-to-r from-violet-500 to-blue-500 px-6 py-4">
          <div className="flex items-center gap-3">
            <Calendar size={20} className="text-white/80" />
            <div>
              <h3 className="text-lg font-bold text-white font-display">每日任务</h3>
              <p className="text-white/70 text-xs mt-0.5">{totalTasks} 项任务 · {completedTasks} 已完成</p>
            </div>
          </div>
        </div>

        <div className="divide-y divide-surface-100">
          {allDays.map(({ weekTitle, day }, di) => {
            const sections = day.sections || [];
            const dayDone = sections.filter(s => s.status === 'mastered' || s.status === 'completed').length;
            const dayPct = sections.length > 0 ? Math.round((dayDone / sections.length) * 100) : 0;
            const isToday = di === 0;

            return (
              <div key={day.id || day.chapter_id || di}
                className={`group transition-colors ${isToday ? 'bg-blue-50/30' : 'hover:bg-surface-50'}`}>
                {/* Day header */}
                <div className="flex items-center gap-4 px-6 py-3 border-b border-surface-100">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0
                    ${isToday ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/30' :
                      dayPct === 100 ? 'bg-emerald-100 text-emerald-600' : 'bg-surface-100 text-surface-500'}`}>
                    <span className="text-sm font-bold">{di + 1}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-bold text-surface-800">{day.title}</p>
                      {isToday && (
                        <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-600 text-[10px] font-bold">今天</span>
                      )}
                    </div>
                    <p className="text-[10px] text-surface-400">{weekTitle}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="hidden sm:flex items-center gap-1.5">
                      <div className="w-16 h-1.5 bg-surface-200 rounded-full overflow-hidden">
                        <div className="h-full bg-emerald-400 rounded-full transition-all" style={{ width: `${dayPct}%` }} />
                      </div>
                      <span className="text-[10px] font-medium text-surface-500">{dayPct}%</span>
                    </div>
                    <span className="text-[10px] text-surface-400">{sections.length} 项</span>
                  </div>
                </div>

                {/* Day tasks */}
                <div className="px-6 pb-3 pt-2 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  {sections.map((sec, si) => {
                    const taskType = (sec as any).task_type || sec.content_type || 'lecture';
                    const ctCfg = TASK_TYPE_CONFIG[taskType] || CONTENT_TYPE_CONFIG[taskType];
                    const isDone = sec.status === 'mastered' || sec.status === 'completed';
                    const Icon = ctCfg?.icon || BookOpen;
                    return (
                      <div key={sec.id || sec.section_id || si}
                        onClick={() => onNavigateSection(sec.id || sec.section_id || '')}
                        className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all
                          ${isDone
                            ? 'bg-emerald-50/50 border-emerald-200 hover:border-emerald-300'
                            : isToday
                              ? 'bg-white border-blue-200 hover:border-blue-400 hover:shadow-md shadow-sm'
                              : 'bg-white border-surface-200 hover:border-surface-300 hover:shadow-sm'}`}>
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5
                          ${isDone ? 'bg-emerald-100 text-emerald-500' :
                            TASK_TYPE_CONFIG[taskType]?.bg || 'bg-surface-100 text-surface-500'}`}>
                          {isDone ? <CheckCircle2 size={15} /> : <Icon size={15} className={TASK_TYPE_CONFIG[taskType]?.color} />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-0.5">
                            <p className="text-xs font-semibold text-surface-800 truncate">{sec.title}</p>
                            {taskType && !isDone && <TaskTypeBadge type={taskType} />}
                          </div>
                          <p className="text-[10px] text-surface-400 line-clamp-1">{sec.goal}</p>
                          <div className="flex items-center gap-2 mt-1.5 text-[10px] text-surface-400">
                            <span className="flex items-center gap-1"><Clock size={9} />{sec.estimated_minutes || 30}min</span>
                          </div>
                        </div>
                        <ChevronRight size={14} className="text-surface-300 flex-shrink-0 mt-1 group-hover:text-surface-500" />
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// 🎯 FocusPathView — sprint priority cards with progress tracking
// ══════════════════════════════════════════════════════════════════════

function FocusPathView({ stages, onNavigateSection, path, progress, totalNodes, masteredNodes }: Props) {
  const sprints = useMemo(() => {
    return stages.map((s, i) => {
      const sections = (s.chapters || []).flatMap(ch => ch.sections || []);
      const tasksDone = sections.filter(sec => sec.status === 'mastered' || sec.status === 'completed').length;
      const tasksTotal = sections.length;
      const pct = tasksTotal > 0 ? Math.round((tasksDone / tasksTotal) * 100) : 0;
      const focus = (s as any).focus || '';
      const reason = (s as any).reason || '';
      const priority: 'high' | 'medium' | 'low' = i === 0 ? 'high' : i < 3 ? 'medium' : 'low';
      return { stage: s, index: i, tasksDone, tasksTotal, pct, focus, reason, priority, sections };
    });
  }, [stages]);

  const totalDone = sprints.reduce((s, sp) => s + sp.tasksDone, 0);
  const totalAll = sprints.reduce((s, sp) => s + sp.tasksTotal, 0);

  const priorityColors = {
    high:   { ring: 'ring-red-400', bg: 'bg-red-50', bar: 'from-red-500 to-rose-500', badge: 'bg-red-100 text-red-600' },
    medium: { ring: 'ring-amber-400', bg: 'bg-amber-50', bar: 'from-amber-500 to-orange-500', badge: 'bg-amber-100 text-amber-600' },
    low:    { ring: 'ring-blue-400', bg: 'bg-blue-50', bar: 'from-blue-500 to-cyan-500', badge: 'bg-blue-100 text-blue-600' },
  };

  return (
    <div className="space-y-6">
      <PathHeader path={path} progress={progress} totalNodes={totalNodes} masteredNodes={masteredNodes} stages={stages} />

      {/* Sprint summary bar */}
      <div className="bg-white rounded-2xl shadow-soft p-5">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-lg shadow-amber-500/20">
            <Zap size={24} className="text-white" />
          </div>
          <div className="flex-1">
            <h3 className="font-display text-lg font-bold text-surface-900">精进突破计划</h3>
            <p className="text-sm text-surface-500 mt-0.5">
              按优先级逐个攻克薄弱点 · {sprints.length} 个冲刺阶段
            </p>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold text-surface-900 font-display">
              {totalAll > 0 ? Math.round((totalDone / totalAll) * 100) : 0}%
            </div>
            <p className="text-xs text-surface-400">{totalDone}/{totalAll} 完成</p>
          </div>
        </div>
      </div>

      {/* Sprint cards */}
      <div className="space-y-4">
        {sprints.map((sp) => {
          const pc = priorityColors[sp.priority];
          const isActive = sp.index === 0 && sp.pct < 100;
          return (
            <div key={sp.stage.id || sp.stage.stage_id || sp.index}
              className={`bg-white rounded-2xl shadow-soft overflow-hidden transition-all
                ${isActive ? 'ring-2 ring-amber-400 shadow-lg shadow-amber-100/50' : 'hover:shadow-elevated'}`}>
              {/* Card header */}
              <div className="bg-gradient-to-r from-surface-50 to-white px-6 py-4 flex items-start gap-4">
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0
                  ${sp.pct === 100
                    ? 'bg-emerald-100 text-emerald-600'
                    : isActive
                      ? 'bg-amber-100 text-amber-600 ring-2 ring-amber-300'
                      : 'bg-surface-100 text-surface-400'}`}>
                  {sp.pct === 100
                    ? <Trophy size={22} />
                    : <span className="text-lg font-bold">{sp.index + 1}</span>}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="text-base font-bold text-surface-900 font-display">{sp.stage.title}</h4>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${pc.badge}`}>
                      {{ high: '最高优先', medium: '中等优先', low: '一般优先' }[sp.priority]}
                    </span>
                    {isActive && (
                      <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-bold animate-pulse">
                        进行中
                      </span>
                    )}
                  </div>
                  {sp.focus && (
                    <p className="text-sm text-surface-600 flex items-center gap-1.5">
                      <Target size={13} className="text-amber-500 flex-shrink-0" />
                      <span className="font-medium">{sp.focus}</span>
                      {sp.reason && <span className="text-surface-400">— {sp.reason}</span>}
                    </p>
                  )}
                </div>
                <div className="text-right flex-shrink-0">
                  <div className="text-2xl font-bold text-surface-900">{sp.pct}%</div>
                  <p className="text-[10px] text-surface-400">{sp.tasksDone}/{sp.tasksTotal} 项</p>
                </div>
              </div>

              {/* Progress bar */}
              <div className="px-6 pb-1">
                <div className="h-2 bg-surface-100 rounded-full overflow-hidden">
                  <div className={`h-full bg-gradient-to-r ${pc.bar} rounded-full transition-all duration-700`}
                    style={{ width: `${sp.pct}%` }} />
                </div>
              </div>

              {/* Task list */}
              {sp.sections.length > 0 && (
                <div className="px-6 pb-4 pt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {sp.sections.map((sec, si) => {
                    const isDone = sec.status === 'mastered' || sec.status === 'completed';
                    return (
                      <div key={sec.id || sec.section_id || si}
                        onClick={() => onNavigateSection(sec.id || sec.section_id || '')}
                        className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all
                          ${isDone
                            ? 'bg-emerald-50/50 border-emerald-200'
                            : 'bg-surface-50 border-surface-200 hover:border-surface-400 hover:shadow-sm'}`}>
                        <div className={`w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0
                          ${isDone ? 'bg-emerald-100 text-emerald-500' : 'bg-surface-200 text-surface-400'}`}>
                          {isDone ? <CheckCircle2 size={13} /> : <Circle size={12} />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs font-medium truncate ${isDone ? 'text-surface-500 line-through' : 'text-surface-700'}`}>
                            {sec.title}
                          </p>
                        </div>
                        <span className="text-[10px] text-surface-400 flex-shrink-0">
                          {sec.estimated_minutes || 30}min
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// 📐 TextbookPathView — enhanced chapter tree (existing + polish)
// ══════════════════════════════════════════════════════════════════════

function TextbookPathView({ stages, onNavigateChapter, onNavigateSection, path, progress, totalNodes, masteredNodes }: Props) {
  const [expandedStage, setExpandedStage] = useState<string | null>(null);

  const totalChapters = stages.reduce((s, st) => s + (st.chapters?.length || 0), 0);
  const totalSections = stages.reduce((s, st) =>
    s + (st.chapters || []).reduce((cs, ch) => cs + (ch.sections?.length || 0), 0), 0);

  return (
    <div className="space-y-6">
      <PathHeader path={path} progress={progress} totalNodes={totalNodes} masteredNodes={masteredNodes} stages={stages} />

      {/* Summary line */}
      <div className="flex items-center gap-4 text-sm text-surface-500">
        <span className="flex items-center gap-1.5"><Layers size={14} />{stages.length} 阶段</span>
        <span className="text-surface-300">|</span>
        <span className="flex items-center gap-1.5"><BookOpen size={14} />{totalChapters} 章</span>
        <span className="text-surface-300">|</span>
        <span className="flex items-center gap-1.5"><Hash size={14} />{totalSections} 节</span>
      </div>

      {/* Stage accordion */}
      <div className="space-y-4">
        {stages.map((stage, si) => {
          const chapters = stage.chapters || [];
          const isExpanded = expandedStage === (stage.id || stage.stage_id || '');
          const stageDone = chapters.reduce((s, ch) =>
            s + (ch.sections || []).filter(sec => sec.status === 'mastered' || sec.status === 'completed').length, 0);
          const stageTotal = chapters.reduce((s, ch) => s + (ch.sections?.length || 0), 0);
          const stagePct = stageTotal > 0 ? Math.round((stageDone / stageTotal) * 100) : 0;

          return (
            <div key={stage.id || stage.stage_id || si}
              className={`bg-white rounded-2xl shadow-soft overflow-hidden transition-all
                ${isExpanded ? 'ring-2 ring-blue-200 shadow-lg' : ''}`}>
              {/* Stage header — clickable */}
              <button
                onClick={() => setExpandedStage(isExpanded ? null : (stage.id || stage.stage_id || ''))}
                className="w-full flex items-center gap-4 px-6 py-5 hover:bg-surface-50/50 transition-colors text-left">
                <div className={`w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0
                  ${stagePct === 100
                    ? 'bg-emerald-100 text-emerald-600'
                    : si === 0
                      ? 'bg-blue-100 text-blue-600'
                      : 'bg-surface-100 text-surface-500'}`}>
                  {stagePct === 100
                    ? <Trophy size={20} />
                    : <span className="text-sm font-bold">{si + 1}</span>}
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="text-base font-bold text-surface-900 font-display">{stage.title}</h4>
                  <div className="flex items-center gap-3 mt-1 text-xs text-surface-400">
                    <span>{chapters.length} 章 · {stageTotal} 节</span>
                    {stageDone > 0 && (
                      <span className="text-emerald-500">{stageDone} 已完成</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="hidden sm:block w-24 h-2 bg-surface-100 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-blue-400 to-emerald-400 rounded-full transition-all"
                      style={{ width: `${stagePct}%` }} />
                  </div>
                  <span className="text-sm font-bold text-surface-600">{stagePct}%</span>
                  <ChevronRight size={18} className={`text-surface-300 transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>
              </button>

              {/* Expanded: chapters list */}
              {isExpanded && (
                <div className="border-t border-surface-100 px-6 pb-5 pt-3 space-y-2 animate-fade-in">
                  {chapters.map((ch, ci) => {
                    const sections = ch.sections || [];
                    const chDone = sections.filter(s => s.status === 'mastered' || s.status === 'completed').length;
                    return (
                      <div key={ch.id || ch.chapter_id || ci}
                        className="flex items-center gap-4 p-3.5 rounded-xl border border-surface-200 bg-surface-50
                          hover:border-blue-300 hover:shadow-sm transition-all cursor-pointer group"
                        onClick={() => onNavigateChapter(ch.id || ch.chapter_id || '')}>
                        <div className="w-8 h-8 rounded-lg bg-primary-100 text-primary-600 flex items-center justify-center flex-shrink-0 font-bold text-xs">
                          {ci + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-surface-800 group-hover:text-primary-600 transition-colors truncate">
                            {ch.title}
                          </p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-[10px] text-surface-400">{sections.length} 节</span>
                            {chDone > 0 && (
                              <span className="text-[10px] text-emerald-500 font-medium">{chDone} 完成</span>
                            )}
                          </div>
                        </div>
                        {/* Section preview chips */}
                        <div className="hidden md:flex items-center gap-1 flex-shrink-0 max-w-[300px] overflow-hidden">
                          {sections.slice(0, 4).map((sec, si) => {
                            const ct = sec.content_type || 'lecture';
                            const cfg = CONTENT_TYPE_CONFIG[ct] || { icon: FileText, label: '' };
                            const Icon = cfg.icon;
                            return (
                              <span key={si}
                                className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-surface-100 text-[9px] text-surface-500 flex-shrink-0">
                                <Icon size={9} />{sec.title.slice(0, 6)}
                              </span>
                            );
                          })}
                          {sections.length > 4 && (
                            <span className="text-[9px] text-surface-400">+{sections.length - 4}</span>
                          )}
                        </div>
                        <ExternalLink size={14} className="text-surface-300 group-hover:text-primary-400 transition-colors flex-shrink-0" />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Path Mode Router
// ══════════════════════════════════════════════════════════════════════

export default function PathModeRouter(props: Props) {
  const { stages } = props;

  // Detect mode
  const pathMode = useMemo(() => {
    // Check if stages have path_mode or plan_mode markers
    for (const s of stages) {
      if ((s as any).path_mode === 'daily') return 'daily';
      if ((s as any).plan_mode === 'focus') return 'focus';
    }
    // Check first stage's chapters for task_type markers (daily mode indicator)
    const firstChapter = stages[0]?.chapters?.[0];
    if (firstChapter) {
      const firstSection = firstChapter.sections?.[0];
      if ((firstSection as any)?.task_type) return 'daily';
    }
    // Check for focus mode markers
    if (stages.length > 0 && (stages[0] as any).focus) return 'focus';
    return 'textbook';
  }, [stages]);

  switch (pathMode) {
    case 'daily':
      return <DailyPathView {...props} />;
    case 'focus':
      return <FocusPathView {...props} />;
    case 'textbook':
    default:
      return <TextbookPathView {...props} />;
  }
}
