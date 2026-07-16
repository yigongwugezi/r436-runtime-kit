import { useMemo, useState } from 'react';
import { Calendar, Clock, ChevronDown, ChevronRight, Zap, CheckCircle2, AlertCircle, BookOpen } from 'lucide-react';
import type { Section, LearningStage } from '../../types/learningPath';

// ══════════════════════════════════════════════════════════════════════
// Distribute sections across days based on estimated_minutes
// ══════════════════════════════════════════════════════════════════════

interface DayBlock {
  day: number;
  sections: { stageTitle: string; section: Section }[];
  totalMinutes: number;
}

function distributeToDays(
  stages: LearningStage[],
  dailyMinutes: number = 60,
): DayBlock[] {
  const allSections: { stageTitle: string; section: Section }[] = [];
  for (const s of stages) {
    for (const ch of s.chapters || []) {
      for (const sec of ch.sections || []) {
        const kps = (sec as any).knowledgePoints || (sec as any).knowledge_points || [];
        // Skip mastered KPs sections (already known)
        if ((sec as any)._adjustment === 'accelerated') continue;
        allSections.push({ stageTitle: s.title || '', section: sec });
      }
    }
  }

  const days: DayBlock[] = [];
  let currentDay: DayBlock = { day: 1, sections: [], totalMinutes: 0 };

  for (const item of allSections) {
    const minutes = (item.section as any).estimated_minutes || (item.section as any).estimatedMinutes || 45;

    if (currentDay.totalMinutes + minutes > dailyMinutes && currentDay.sections.length > 0) {
      days.push(currentDay);
      currentDay = { day: days.length + 1, sections: [], totalMinutes: 0 };
    }
    currentDay.sections.push(item);
    currentDay.totalMinutes += minutes;
  }
  if (currentDay.sections.length > 0) days.push(currentDay);
  return days;
}

// ══════════════════════════════════════════════════════════════════════
// Adjustment badge
// ══════════════════════════════════════════════════════════════════════

function AdjustmentBadge({ adj }: { adj?: string }) {
  if (!adj || adj === 'normal') return null;
  const cfg: Record<string, { label: string; icon: typeof Zap; color: string }> = {
    accelerated: { label: '已掌握·加速', icon: CheckCircle2, color: 'text-emerald-600 bg-emerald-50' },
    strengthened: { label: '薄弱·强化', icon: Zap, color: 'text-amber-600 bg-amber-50' },
    mixed: { label: '部分薄弱', icon: AlertCircle, color: 'text-orange-600 bg-orange-50' },
    remedial: { label: '前置补救', icon: BookOpen, color: 'text-blue-600 bg-blue-50' },
  };
  const c = cfg[adj];
  if (!c) return null;
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${c.color}`}>
      <Icon size={10} />
      {c.label}
    </span>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Main: DayDistributionView
// ══════════════════════════════════════════════════════════════════════

interface Props {
  stages: LearningStage[];
  estimatedMinutesTotal?: number;
  dailyMinutes?: number;
  onSectionClick?: (sectionId: string) => void;
}

export default function DayDistributionView({
  stages,
  estimatedMinutesTotal,
  dailyMinutes = 60,
  onSectionClick,
}: Props) {
  const days = useMemo(() => distributeToDays(stages, dailyMinutes), [stages, dailyMinutes]);
  const [expandedDays, setExpandedDays] = useState<Set<number>>(() => new Set([1]));

  const toggleDay = (day: number) => {
    setExpandedDays(prev => {
      const next = new Set(prev);
      if (next.has(day)) next.delete(day);
      else next.add(day);
      return next;
    });
  };

  const adjustments = useMemo(() => {
    const found = new Set<string>();
    for (const s of stages) {
      for (const ch of s.chapters || []) {
        for (const sec of ch.sections || []) {
          const adj = (sec as any)._adjustment;
          if (adj && adj !== 'normal') found.add(adj);
        }
      }
    }
    return found;
  }, [stages]);

  if (!stages.length) return null;

  return (
    <div className="animate-fade-in space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Calendar size={18} className="text-primary-500" />
          <h3 className="font-display text-lg font-semibold text-surface-800">
            日视图
            <span className="ml-2 text-sm font-normal text-surface-400">
              {days.length}天 · 每{dailyMinutes}分钟/天
            </span>
          </h3>
        </div>
        {estimatedMinutesTotal && (
          <span className="text-xs text-surface-400">
            总计 {estimatedMinutesTotal} 分钟
          </span>
        )}
      </div>

      {/* Adjustment legend */}
      {adjustments.size > 0 && (
        <div className="flex flex-wrap gap-2 px-3 py-2 bg-surface-50 rounded-xl border border-surface-200">
          <span className="text-[10px] font-medium text-surface-400 uppercase tracking-wider">调整标记：</span>
          {Array.from(adjustments).map(a => (
            <AdjustmentBadge key={a} adj={a} />
          ))}
        </div>
      )}

      {/* Day cards */}
      <div className="space-y-3">
        {days.map((day) => {
          const isExpanded = expandedDays.has(day.day);
          const sectionsWithAdj = day.sections.filter(s => (s.section as any)._adjustment);

          return (
            <div
              key={day.day}
              className="bg-white rounded-2xl border border-surface-200 overflow-hidden transition-all hover:shadow-soft"
            >
              <button
                onClick={() => toggleDay(day.day)}
                className="w-full flex items-center justify-between px-5 py-4 hover:bg-surface-50 transition-colors text-left"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-primary-100 text-primary-600 flex items-center justify-center font-bold text-sm">
                    {day.day}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-surface-800">第 {day.day} 天</p>
                    <p className="text-xs text-surface-400">
                      {day.sections.length} 个小节 · {day.totalMinutes} 分钟
                      {sectionsWithAdj.length > 0 && (
                        <span className="ml-2 text-amber-500">（{sectionsWithAdj.length} 项已调整）</span>
                      )}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {isExpanded ? <ChevronDown size={16} className="text-surface-400" /> : <ChevronRight size={16} className="text-surface-400" />}
                </div>
              </button>

              {isExpanded && (
                <div className="px-5 pb-4 space-y-2 animate-fade-in">
                  {day.sections.map((item, i) => {
                    const sec = item.section;
                    const secTitle = (sec as any).title || '';
                    const minutes = (sec as any).estimated_minutes || (sec as any).estimatedMinutes || 45;
                    const adjustment = (sec as any)._adjustment;
                    const reason = (sec as any)._adjustment_reason;
                    const weakKps = (sec as any)._weak_kps;
                    const gp = (sec as any).goal || '';

                    return (
                      <div
                        key={(sec as any).section_id || i}
                        onClick={() => onSectionClick?.((sec as any).section_id)}
                        className={`flex items-start gap-3 p-3 rounded-xl border transition-all cursor-pointer
                          ${adjustment === 'strengthened' ? 'border-amber-200 bg-amber-50/30' :
                            adjustment === 'accelerated' ? 'border-emerald-200 bg-emerald-50/30' :
                            adjustment === 'remedial' ? 'border-blue-200 bg-blue-50/30' :
                            'border-surface-100 hover:border-surface-200 hover:bg-surface-50'}`}
                      >
                        <div className="flex-shrink-0 w-6 h-6 rounded-lg bg-surface-100 text-surface-500 flex items-center justify-center text-[10px] font-bold">
                          {i + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="text-sm font-medium text-surface-800 truncate">{secTitle}</p>
                            <AdjustmentBadge adj={adjustment} />
                          </div>
                          {gp && <p className="text-xs text-surface-400 mt-0.5 line-clamp-1">{gp}</p>}
                          {reason && (
                            <p className="text-[10px] text-surface-500 mt-1 italic">{reason}</p>
                          )}
                          {weakKps && weakKps.length > 0 && (
                            <p className="text-[10px] text-amber-600 mt-1">
                              关注：{weakKps.join('、')}
                            </p>
                          )}
                          <div className="flex items-center gap-2 mt-1.5">
                            <span className="flex items-center gap-1 text-[10px] text-surface-400">
                              <Clock size={10} />
                              {minutes} 分钟
                            </span>
                            <span className="text-[10px] text-surface-300">·</span>
                            <span className="text-[10px] text-surface-400 truncate">{item.stageTitle}</span>
                          </div>
                        </div>
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
