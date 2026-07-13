import { useMemo } from 'react';
import {
  Zap, Target, Trophy, Clock, CheckCircle2,
  ArrowUp, Layers,
} from 'lucide-react';
import type { LearningStage, Section } from '../../types/learningPath';

// ══════════════════════════════════════════════════════════════════════
// Types
// ══════════════════════════════════════════════════════════════════════

type Priority = 'high' | 'medium' | 'low';

interface SprintInfo {
  index: number;
  stage: LearningStage;
  focus: string;
  reason: string;
  priority: Priority;
  tasksDone: number;
  tasksTotal: number;
  pct: number;
}

// ══════════════════════════════════════════════════════════════════════
// Priority → visual config (single source of truth)
// ══════════════════════════════════════════════════════════════════════

const PRIORITY_STYLE: Record<Priority, { bar: string; badge: string; accent: string }> = {
  high:   { bar: 'from-red-500 to-rose-500',   badge: 'bg-red-100 text-red-600',   accent: 'shadow-red-500/20' },
  medium: { bar: 'from-amber-500 to-orange-500', badge: 'bg-amber-100 text-amber-600', accent: 'shadow-amber-500/20' },
  low:    { bar: 'from-blue-500 to-cyan-500',   badge: 'bg-blue-100 text-blue-600',  accent: 'shadow-blue-500/20' },
};

const PRIORITY_LABEL: Record<Priority, string> = {
  high: '最高优先', medium: '中等优先', low: '一般优先',
};

// ══════════════════════════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════════════════════════

function countMastered(sections: Section[]): number {
  return sections.filter(s => s.status === 'mastered').length;
}

function findCurrentSprint(stages: LearningStage[], currentSectionId?: string): SprintInfo | null {
  for (let i = 0; i < stages.length; i++) {
    const s = stages[i];
    const sections = s.chapters?.flatMap(ch => ch.sections || []) || [];
    if (!sections.some(sec => sec.id === currentSectionId)) continue;

    const done = countMastered(sections);
    const total = sections.length;
    return {
      index: i,
      stage: s,
      focus: (s as any).focus || '',
      reason: (s as any).reason || '',
      priority: (i === 0 ? 'high' : i < 3 ? 'medium' : 'low') as Priority,
      tasksDone: done,
      tasksTotal: total,
      pct: total > 0 ? Math.round((done / total) * 100) : 0,
    };
  }
  return null;
}

// ══════════════════════════════════════════════════════════════════════
// FocusSprintHeader — sprint progress card above lecture content
// ══════════════════════════════════════════════════════════════════════

interface FocusHeaderProps {
  stages: LearningStage[];
  currentSectionId?: string;
  currentSection?: Section;
  totalSprints?: number;
  completedSprints?: number;
}

export function FocusSprintHeader({
  stages,
  currentSectionId,
  totalSprints,
  completedSprints = 0,
}: FocusHeaderProps) {
  const sprint = findCurrentSprint(stages, currentSectionId);
  const total = totalSprints ?? stages.length;

  // Fallback: no section match → show overview
  if (!sprint) {
    return (
      <div className="bg-white rounded-2xl shadow-soft p-5 mb-5 animate-fade-in">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center flex-shrink-0 shadow-lg shadow-amber-500/20">
            <Zap size={22} className="text-white" />
          </div>
          <div>
            <h3 className="text-base font-bold text-surface-900 font-display">精进突破模式</h3>
            <p className="text-sm text-surface-500 mt-0.5">
              已完成 {completedSprints}/{total} 个冲刺阶段
            </p>
          </div>
        </div>
      </div>
    );
  }

  const { index, focus, reason, priority, tasksDone, tasksTotal, pct } = sprint;
  const ps = PRIORITY_STYLE[priority];
  const isActive = index === 0 && pct < 100;
  const isDone = pct === 100;

  return (
    <div className="bg-white rounded-2xl shadow-soft p-5 mb-5 animate-fade-in">
      <div className="flex items-start gap-4">
        {/* Icon */}
        <div className={`w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0 shadow-lg ${ps.accent}
          ${isDone
            ? 'bg-gradient-to-br from-emerald-400 to-emerald-500'
            : 'bg-gradient-to-br from-amber-500 to-orange-500'}`}
        >
          {isDone
            ? <Trophy size={22} className="text-white" />
            : <Zap size={22} className="text-white" />}
        </div>

        <div className="flex-1 min-w-0">
          {/* Badges row */}
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg bg-surface-100 text-[10px] font-bold text-surface-500">
              冲刺 {index + 1}/{total}
            </span>
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${ps.badge}`}>
              {PRIORITY_LABEL[priority]}
            </span>
            {isActive && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-bold animate-pulse">
                进行中
              </span>
            )}
            {isDone && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-bold">
                <CheckCircle2 size={9} />已攻克
              </span>
            )}
          </div>

          {/* Focus area */}
          {focus && (
            <h3 className="text-base font-bold text-surface-900 font-display flex items-center gap-1.5">
              <Target size={14} className="text-amber-500 flex-shrink-0" />
              攻克：{focus}
            </h3>
          )}
          {reason && (
            <p className="text-xs text-surface-500 mt-1">{reason}</p>
          )}
        </div>

        {/* Percentage + count */}
        <div className="text-right flex-shrink-0 pt-1">
          <p className="text-2xl font-bold text-surface-800 font-display">{pct}%</p>
          <p className="text-xs text-surface-400 mt-0.5">{tasksDone}/{tasksTotal} 项</p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mt-4 space-y-1.5">
        <div className="h-2 bg-surface-100 rounded-full overflow-hidden">
          <div
            className={`h-full bg-gradient-to-r ${ps.bar} rounded-full transition-all duration-700`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-[10px] text-surface-400">
          <span className="flex items-center gap-1">
            <Clock size={10} />{sprint.stage.estimatedDays || '?'} 天
          </span>
          {isDone
            ? <span className="flex items-center gap-1 text-emerald-500 font-medium"><CheckCircle2 size={10} />已攻克</span>
            : <span>{100 - pct}% 剩余</span>}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// SprintNav — right-panel sprint jump-list
// ══════════════════════════════════════════════════════════════════════

interface SprintNavProps {
  stages: LearningStage[];
  currentSectionId?: string;
  onNavigate: (sectionId: string) => void;
}

export function SprintNav({ stages, currentSectionId, onNavigate }: SprintNavProps) {
  const sprints = useMemo(() => {
    return stages.map((s, i) => {
      const sections = s.chapters?.flatMap(ch => ch.sections || []) || [];
      return {
        index: i,
        title: s.title,
        firstSectionId: sections[0]?.id || '',
        total: sections.length,
        done: countMastered(sections),
        focus: (s as any).focus || '',
      };
    });
  }, [stages]);

  const currentIdx = sprints.findIndex(sp =>
    stages[sp.index]?.chapters
      ?.flatMap(ch => ch.sections || [])
      .some(sec => sec.id === currentSectionId),
  );

  if (sprints.length <= 1) return null;

  return (
    <div className="border-t border-surface-100 pt-3 mt-3">
      <p className="text-[10px] font-semibold text-surface-400 uppercase tracking-wider px-1 mb-2">
        冲刺导航
      </p>
      <div className="space-y-1">
        {sprints.map((sp) => {
          const isCurrent = sp.index === currentIdx;
          const isDone = sp.done === sp.total && sp.total > 0;
          return (
            <button
              key={sp.index}
              onClick={() => sp.firstSectionId && onNavigate(sp.firstSectionId)}
              className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-left transition-all duration-150 active:scale-[0.98]
                ${isCurrent
                  ? 'bg-amber-50 border border-amber-200 shadow-sm'
                  : isDone
                    ? 'bg-emerald-50/50 border border-emerald-100 hover:border-emerald-200'
                    : 'hover:bg-surface-50 border border-transparent'}`}
            >
              {/* Index / check */}
              <div className={`w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0 text-[10px] font-bold
                ${isDone ? 'bg-emerald-100 text-emerald-600' :
                  isCurrent ? 'bg-amber-200 text-amber-700' :
                  'bg-surface-100 text-surface-400'}`}>
                {isDone ? <CheckCircle2 size={12} /> : sp.index + 1}
              </div>

              {/* Title + focus */}
              <div className="flex-1 min-w-0 text-left">
                <p className={`text-xs font-medium truncate ${isCurrent ? 'text-amber-800' : 'text-surface-600'}`}>
                  {sp.title}
                </p>
                {sp.focus && (
                  <p className="text-[10px] text-surface-400 truncate">{sp.focus}</p>
                )}
              </div>

              {/* Count */}
              <span className="text-[10px] text-surface-400 flex-shrink-0 tabular-nums">
                {sp.done}/{sp.total}
              </span>

              {isCurrent && <ArrowUp size={12} className="text-amber-500 flex-shrink-0" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}
