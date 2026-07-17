import { useState, useMemo } from 'react';
import { ChevronRight, Clock } from 'lucide-react';

// ══════════════════════════════════════════════════════════════════════
// Types
// ══════════════════════════════════════════════════════════════════════

interface SectionData {
  id: string;
  title: string;
  estimatedMinutes?: number;
  status?: string;
  mastery?: number;
  _adjustment?: string;
}

interface StageData {
  id: string;
  title: string;
  order?: number;
  chapters?: ChapterData[];
  estimatedDays?: number;
  status?: string;
}

interface ChapterData {
  id: string;
  title: string;
  sections: SectionData[];
  status?: string;
}

interface Props {
  stages: StageData[];
  totalDays?: number;
  onSectionClick: (sectionId: string) => void;
}

// ══════════════════════════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════════════════════════

function stageStatus(stage: StageData): 'completed' | 'in_progress' | 'locked' {
  const allSections = stage.chapters?.flatMap(c => c.sections ?? []) ?? [];
  if (allSections.length === 0) return 'locked';
  const allDone = allSections.every(s => s.status === 'mastered' || s.status === 'completed');
  if (allDone) return 'completed';
  const anyActive = allSections.some(s => s.status === 'in_progress');
  if (anyActive) return 'in_progress';
  return 'locked';
}

function stageProgress(stage: StageData): number {
  const allSections = stage.chapters?.flatMap(c => c.sections ?? []) ?? [];
  if (allSections.length === 0) return 0;
  const mastered = allSections.filter(s => s.status === 'mastered' || s.status === 'completed').length;
  return Math.round((mastered / allSections.length) * 100);
}

function totalProgress(stages: StageData[]): { completed: number; total: number; pct: number } {
  const all = stages.flatMap(s => s.chapters?.flatMap(c => c.sections ?? []) ?? []);
  const done = all.filter(s => s.status === 'mastered' || s.status === 'completed').length;
  return { completed: done, total: all.length, pct: all.length > 0 ? Math.round((done / all.length) * 100) : 0 };
}

// ══════════════════════════════════════════════════════════════════════
// Adjustment marker (minimal)
// ══════════════════════════════════════════════════════════════════════

function AdjDot({ adj }: { adj?: string }) {
  if (!adj || adj === 'normal') return null;
  const colors: Record<string, string> = {
    accelerated: 'bg-emerald-400',
    strengthened: 'bg-amber-400',
    mixed: 'bg-orange-400',
    remedial: 'bg-blue-400',
  };
  return <span className={`inline-block w-1.5 h-1.5 rounded-full ${colors[adj] || 'bg-surface-300'} ml-1`} />;
}

// ══════════════════════════════════════════════════════════════════════
// Section row
// ══════════════════════════════════════════════════════════════════════

function SectionRow({ section, onClick }: { section: SectionData; onClick: (id: string) => void }) {
  const isDone = section.status === 'mastered' || section.status === 'completed';
  const isActive = section.status === 'in_progress';
  const minutes = section.estimatedMinutes || 45;

  return (
    <button
      onClick={() => onClick(section.id)}
      className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all text-left
        ${isDone ? 'text-surface-400' : isActive ? 'text-surface-800 bg-primary-50/50' : 'text-surface-600 hover:bg-surface-50'}`}
    >
      {/* Status indicator */}
      <span className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-medium
        ${isDone ? 'bg-emerald-100 text-emerald-500' :
          isActive ? 'bg-primary-100 text-primary-600 ring-2 ring-primary-200' :
          'bg-surface-100 text-surface-300'}`}
      >
        {isDone ? '✓' : isActive ? '◉' : '○'}
      </span>

      {/* Title */}
      <span className={`flex-1 min-w-0 text-sm ${isDone ? 'line-through' : ''} truncate`}>
        {section.title}
      </span>

      {/* Adjustment dot */}
      <AdjDot adj={section._adjustment} />

      {/* Minutes */}
      <span className="text-[11px] text-surface-300 flex-shrink-0 w-10 text-right tabular-nums">
        {minutes}′
      </span>

      {/* Active indicator */}
      {isActive && (
        <span className="text-[10px] text-primary-500 font-medium flex-shrink-0">学习中</span>
      )}
    </button>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Stage card (collapsible)
// ══════════════════════════════════════════════════════════════════════

function StageCard({ stage, defaultOpen, onSectionClick }: {
  stage: StageData;
  defaultOpen: boolean;
  onSectionClick: (id: string) => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const status = stageStatus(stage);
  const progress = stageProgress(stage);
  const sections = stage.chapters?.flatMap(c => c.sections ?? []) ?? [];
  const activeIndex = sections.findIndex(s => s.status === 'in_progress');
  const completedCount = sections.filter(s => s.status === 'mastered' || s.status === 'completed').length;

  const statusLabel = status === 'completed' ? '已完成' : status === 'in_progress' ? '进行中' : '';
  const isLocked = status === 'locked';

  return (
    <div className={`rounded-2xl border overflow-hidden transition-all
      ${isLocked ? 'border-surface-100 opacity-50' : 'border-surface-200 hover:shadow-soft'}`}
    >
      {/* Header — clickable */}
      <button
        onClick={() => !isLocked && setOpen(!open)}
        disabled={isLocked}
        className={`w-full flex items-center gap-3 px-5 py-4 text-left transition-colors
          ${isLocked ? 'cursor-default' : 'hover:bg-surface-50'}`}
      >
        {/* Stage number */}
        <div className={`w-9 h-9 rounded-xl flex items-center justify-center text-sm font-bold flex-shrink-0
          ${status === 'completed' ? 'bg-emerald-100 text-emerald-600' :
            status === 'in_progress' ? 'bg-primary-100 text-primary-600' :
            'bg-surface-100 text-surface-400'}`}
        >
          {status === 'completed' ? '✓' : (stage.order ?? 0) + 1}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`text-sm font-semibold ${isLocked ? 'text-surface-400' : 'text-surface-800'}`}>
              {stage.title}
            </span>
            {statusLabel && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium
                ${status === 'completed' ? 'bg-emerald-50 text-emerald-600' :
                  'bg-primary-50 text-primary-600'}`}
              >
                {statusLabel}
              </span>
            )}
          </div>

          {/* Thin progress bar */}
          {!isLocked && (
            <div className="mt-1.5 flex items-center gap-2">
              <div className="flex-1 h-1 bg-surface-100 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all duration-500
                  ${status === 'completed' ? 'bg-emerald-400' : 'bg-primary-400'}`}
                  style={{ width: `${progress}%` }}
                />
              </div>
              <span className="text-[10px] text-surface-400 tabular-nums">{progress}%</span>
            </div>
          )}

          {isLocked && (
            <p className="text-[11px] text-surface-400 mt-0.5">需要先完成前面的阶段</p>
          )}
        </div>

        {!isLocked && (
          <ChevronRight size={14} className={`text-surface-300 transition-transform ${open ? 'rotate-90' : ''}`} />
        )}
      </button>

      {/* Section list — expandable */}
      {open && !isLocked && (
        <div className="border-t border-surface-100 pb-2 pt-1 animate-fade-in">
          {sections.map((sec, i) => (
            <SectionRow key={sec.id} section={sec} onClick={onSectionClick} />
          ))}
          {activeIndex >= 0 && (
            <p className="text-[10px] text-surface-400 px-4 pt-1.5">
              第 {activeIndex + 1}/{sections.length} 小节
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Progress ring (SVG)
// ══════════════════════════════════════════════════════════════════════

function ProgressRing({ pct, size = 48 }: { pct: number; size?: number }) {
  const stroke = 3;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  return (
    <svg width={size} height={size} className="flex-shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#3b82f6" strokeWidth={stroke}
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        className="transition-all duration-700"
      />
      <text x={size / 2} y={size / 2} textAnchor="middle" dominantBaseline="central"
        fontSize={size * 0.28} fontWeight={600} fill="#475569" className="tabular-nums">
        {pct}%
      </text>
    </svg>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Main: StageTimeline
// ══════════════════════════════════════════════════════════════════════

export default function StageTimeline({ stages, totalDays = 14, onSectionClick }: Props) {
  const prog = useMemo(() => totalProgress(stages), [stages]);
  const stageCount = stages.length;
  const activeStageIdx = stages.findIndex(s => stageStatus(s) === 'in_progress');

  if (!stages.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-surface-300">
        <div className="w-12 h-12 rounded-2xl bg-surface-50 flex items-center justify-center mb-3">
          <Clock size={22} />
        </div>
        <p className="text-sm font-medium">暂无学习路径</p>
        <p className="text-xs mt-1">先生成路径后，这里会展示具体学习进度</p>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Top summary bar */}
      <div className="flex items-center gap-4 px-5 py-4 bg-white rounded-2xl border border-surface-100">
        <ProgressRing pct={prog.pct} size={52} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-display text-sm font-semibold text-surface-800">学习进度</h3>
            <span className="text-xs text-surface-400">
              {activeStageIdx >= 0 ? `第 ${activeStageIdx + 1} / ${stageCount} 阶段` : `${stageCount} 阶段`}
            </span>
          </div>
          <p className="text-xs text-surface-400 mt-0.5">
            {prog.completed} / {prog.total} 知识点 · 预计 {totalDays} 天
            {prog.completed > 0 && ` · 已完成 ${Math.round(prog.pct)}%`}
          </p>
        </div>
      </div>

      {/* Stage cards */}
      {stages.map((stage, i) => (
        <StageCard
          key={stage.id}
          stage={stage}
          defaultOpen={stageStatus(stage) === 'in_progress' || i === activeStageIdx}
          onSectionClick={onSectionClick}
        />
      ))}

      {/* Footer */}
      {stageCount > 0 && (
        <div className="text-center">
          <span className="text-[10px] text-surface-300">
            {prog.completed} / {prog.total} 知识点完成 · 预计剩余 {Math.round(totalDays * (1 - prog.pct / 100))} 天
          </span>
        </div>
      )}
    </div>
  );
}
