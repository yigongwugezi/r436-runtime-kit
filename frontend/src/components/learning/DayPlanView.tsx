import { useState } from 'react';
import {
  Calendar, Clock, ChevronDown, ChevronRight,
  BookOpen, RefreshCw, PenTool, Activity, Target,
  CheckCircle2, Zap, AlertCircle, Sparkles,
} from 'lucide-react';

// ══════════════════════════════════════════════════════════════════════
// Types matching backend day_plan response
// ══════════════════════════════════════════════════════════════════════

export interface DayPlanItem {
  id?: string;
  type: 'new' | 'review' | 'practice' | 'diagnosis' | 'project';
  title: string;
  minutes: number;
  source_section_id?: string;
  source_stage?: string;
  description?: string;
  adjustment?: string | null;
  weak_kps?: string[];
  status?: 'pending' | 'completed';
}

export interface DayBlock {
  day: number;
  total_minutes: number;
  items: DayPlanItem[];
}

export interface DayPlan {
  days: DayBlock[];
  version: number;
  generated_at?: number;
  _adjusted_days?: number[];
}

// ══════════════════════════════════════════════════════════════════════
// Item type → visual config
// ══════════════════════════════════════════════════════════════════════

const ITEM_CONFIG: Record<string, { label: string; icon: typeof BookOpen; color: string; bg: string }> = {
  new:       { label: '新课',        icon: BookOpen,   color: 'text-blue-600',   bg: 'bg-blue-50 border-blue-200' },
  review:    { label: '复习',        icon: RefreshCw,  color: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200' },
  practice:  { label: '练习',        icon: PenTool,     color: 'text-amber-600',  bg: 'bg-amber-50 border-amber-200' },
  diagnosis: { label: '诊断',        icon: Activity,    color: 'text-purple-600', bg: 'bg-purple-50 border-purple-200' },
  project:   { label: '项目',        icon: Target,      color: 'text-rose-600',   bg: 'bg-rose-50 border-rose-200' },
};

function getItemMeta(type: string) {
  return ITEM_CONFIG[type] || ITEM_CONFIG.new;
}

// ══════════════════════════════════════════════════════════════════════
// Adjustment badge
// ══════════════════════════════════════════════════════════════════════

function AdjBadge({ adj }: { adj?: string | null }) {
  if (!adj || adj === 'normal') return null;
  const cfg: Record<string, { label: string; icon: typeof Zap; cls: string }> = {
    accelerated:  { label: '已掌握·加速',  icon: CheckCircle2, cls: 'text-emerald-600 bg-emerald-50 border-emerald-200' },
    strengthened: { label: '薄弱·强化',  icon: Zap,          cls: 'text-amber-600 bg-amber-50 border-amber-200' },
    mixed:        { label: '部分薄弱',    icon: AlertCircle,  cls: 'text-orange-600 bg-orange-50 border-orange-200' },
    remedial:     { label: '前置补救',    icon: BookOpen,     cls: 'text-blue-600 bg-blue-50 border-blue-200' },
  };
  const c = cfg[adj];
  if (!c) return null;
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-medium border ${c.cls}`}>
      <Icon size={10} />
      {c.label}
    </span>
  );
}

// ══════════════════════════════════════════════════════════════════════
// DayItem — a single learnable unit
// ══════════════════════════════════════════════════════════════════════

function DayItem({ item, onClick }: { item: DayPlanItem; onClick?: (id: string) => void }) {
  const meta = getItemMeta(item.type);
  const Icon = meta.icon;
  const completed = item.status === 'completed';
  const hasAdj = !!item.adjustment && item.adjustment !== 'normal';

  return (
    <div
      onClick={() => onClick?.(item.source_section_id || item.id || '')}
      className={`flex items-start gap-3 p-3 rounded-xl border transition-all cursor-pointer
        ${completed ? 'bg-surface-50 border-surface-200 opacity-70' : 'bg-white border-surface-100 hover:border-primary-200 hover:shadow-sm'}
        ${item.type === 'diagnosis' ? 'bg-gradient-to-r from-purple-50 to-white border-purple-200' : ''}`}
    >
      {/* Type icon */}
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${meta.bg.split(' ')[0]}`}>
        <Icon size={15} className={meta.color} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`text-[10px] font-bold uppercase tracking-wider ${meta.color}`}>{meta.label}</span>
          {hasAdj && <AdjBadge adj={item.adjustment} />}
          {completed && <CheckCircle2 size={12} className="text-emerald-400" />}
        </div>
        <p className={`text-sm font-medium mt-0.5 ${completed ? 'text-surface-400 line-through' : 'text-surface-800'}`}>
          {item.title}
        </p>
        {item.description && (
          <p className="text-[11px] text-surface-400 mt-0.5 line-clamp-2">{item.description}</p>
        )}
        {item.weak_kps && item.weak_kps.length > 0 && (
          <p className="text-[10px] text-amber-600 mt-1">
            <AlertCircle size={10} className="inline mr-0.5" />
            关注：{item.weak_kps.join('、')}
          </p>
        )}
        <div className="flex items-center gap-2 mt-1.5">
          <span className="flex items-center gap-1 text-[10px] text-surface-400">
            <Clock size={10} />
            {item.minutes} 分钟
          </span>
          {item.source_stage && (
            <span className="text-[10px] text-surface-300">· {item.source_stage}</span>
          )}
        </div>
      </div>

      {/* Time indicator */}
      <div className="flex-shrink-0 pt-1">
        <div className="w-10 h-6 rounded-lg bg-surface-50 flex items-center justify-center">
          <span className="text-[10px] font-medium text-surface-500">{item.minutes}′</span>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// DayCard — one day's worth of items
// ══════════════════════════════════════════════════════════════════════

function DayCard({
  day,
  totalMinutes,
  items,
  isExpanded,
  isAdjusted,
  onToggle,
  onItemClick,
}: {
  day: number;
  totalMinutes: number;
  items: DayPlanItem[];
  isExpanded: boolean;
  isAdjusted?: boolean;
  onToggle: () => void;
  onItemClick?: (id: string) => void;
}) {
  const completedCount = items.filter(i => i.status === 'completed').length;
  const pct = items.length > 0 ? Math.round((completedCount / items.length) * 100) : 0;
  const typeIcons = [...new Set(items.map(i => i.type))].map(t => getItemMeta(t).icon);

  return (
    <div className={`bg-white rounded-2xl border transition-all overflow-hidden
      ${isAdjusted ? 'border-amber-300 shadow-md' : 'border-surface-200 hover:shadow-soft'}`}
    >
      {/* Day header — always visible */}
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-surface-50 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm
            ${isAdjusted ? 'bg-amber-100 text-amber-600' : 'bg-primary-100 text-primary-600'}`}
          >
            {day}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-surface-800">第 {day} 天</p>
              {isAdjusted && (
                <span className="text-[10px] px-1.5 py-0.5 bg-amber-100 text-amber-600 rounded-full font-medium">
                  已调整
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <div className="flex items-center gap-1">
                {typeIcons.slice(0, 3).map((Icon, i) => (
                  <Icon key={i} size={11} className="text-surface-400" />
                ))}
              </div>
              <span className="text-xs text-surface-400">
                {items.length} 项 · {totalMinutes} 分钟
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {completedCount > 0 && (
            <div className="flex items-center gap-1">
              <div className="w-14 h-1.5 bg-surface-100 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-400 rounded-full transition-all" style={{ width: `${pct}%` }} />
              </div>
              <span className="text-[10px] text-surface-400 font-medium">{pct}%</span>
            </div>
          )}
          {isExpanded ? <ChevronDown size={16} className="text-surface-400" /> : <ChevronRight size={16} className="text-surface-400" />}
        </div>
      </button>

      {/* Items — only when expanded */}
      {isExpanded && (
        <div className="px-5 pb-5 space-y-2.5 border-t border-surface-100 pt-3">
          {items.map((item, i) => (
            <DayItem key={item.id || i} item={item} onClick={onItemClick} />
          ))}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// Main: DayPlanView
// ══════════════════════════════════════════════════════════════════════

interface Props {
  dayPlan: DayPlan | null;
  onItemClick?: (sectionId: string) => void;
  onRefresh?: () => void;
  /** 已调整的天数列表（动态规划标记） */
  adjustedDays?: number[];
}

export default function DayPlanView({ dayPlan, onItemClick, onRefresh, adjustedDays }: Props) {
  const [expandedDays, setExpandedDays] = useState<Set<number>>(() => new Set([1]));
  const [filterType, setFilterType] = useState<string | null>(null);

  if (!dayPlan || !dayPlan.days || dayPlan.days.length === 0) {
    return (
      <div className="text-center py-12 text-surface-400">
        <Calendar size={32} className="mx-auto mb-3 opacity-40" />
        <p className="text-sm">暂无学习计划</p>
        <p className="text-xs mt-1">先生成学习路径后，日视图会自动出现</p>
      </div>
    );
  }

  const days = dayPlan.days;
  const allTypes = [...new Set(days.flatMap(d => d.items.map(i => i.type)))];

  // 过滤后的天数
  const filteredDays = filterType
    ? days.filter(d => d.items.some(i => i.type === filterType))
    : days;

  const toggleDay = (d: number) => {
    setExpandedDays(prev => {
      const next = new Set(prev);
      if (next.has(d)) next.delete(d); else next.add(d);
      return next;
    });
  };

  const totalDays = days.length;
  const totalItems = days.reduce((s, d) => s + d.items.length, 0);
  const totalMinutes = days.reduce((s, d) => s + d.total_minutes, 0);
  const completedItems = days.reduce((s, d) => s + d.items.filter(i => i.status === 'completed').length, 0);

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Calendar size={18} className="text-primary-500" />
          <h3 className="font-display text-lg font-semibold text-surface-800">
            日视图
            <span className="ml-2 text-sm font-normal text-surface-400">
              {totalDays} 天 · {totalItems} 项 · ~{totalMinutes} 分钟
            </span>
          </h3>
        </div>
        <div className="flex items-center gap-2">
          {completedItems > 0 && (
            <span className="text-xs text-surface-400">
              {completedItems}/{totalItems} 已完成
            </span>
          )}
          {onRefresh && (
            <button onClick={onRefresh} className="p-2 rounded-lg hover:bg-surface-100 transition-colors">
              <RefreshCw size={14} className="text-surface-400" />
            </button>
          )}
        </div>
      </div>

      {/* Type filter tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
        <button
          onClick={() => setFilterType(null)}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap
            ${!filterType ? 'bg-surface-800 text-white' : 'bg-surface-100 text-surface-500 hover:bg-surface-200'}`}
        >
          全部
        </button>
        {allTypes.map(t => {
          const meta = getItemMeta(t);
          return (
            <button
              key={t}
              onClick={() => setFilterType(filterType === t ? null : t)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap flex items-center gap-1.5
                ${filterType === t ? `${meta.bg.split(' ')[0]} ${meta.color}` : 'bg-surface-100 text-surface-500 hover:bg-surface-200'}`}
            >
              <meta.icon size={12} />
              {meta.label}
            </button>
          );
        })}
      </div>

      {/* Adjustment summary */}
      {adjustedDays && adjustedDays.length > 0 && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-amber-50 border border-amber-200 rounded-xl">
          <Zap size={14} className="text-amber-500 flex-shrink-0" />
          <span className="text-xs text-amber-700">
            动态规划已调整第 {adjustedDays.join('、')} 天的内容
          </span>
        </div>
      )}

      {/* Day cards */}
      <div className="space-y-3">
        {filteredDays.map((day) => {
          const adjusted = adjustedDays?.includes(day.day);
          const isExpanded = expandedDays.has(day.day);
          return (
            <DayCard
              key={day.day}
              day={day.day}
              totalMinutes={day.total_minutes}
              items={day.items}
              isExpanded={isExpanded}
              isAdjusted={adjusted}
              onToggle={() => toggleDay(day.day)}
              onItemClick={onItemClick}
            />
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 bg-surface-50 rounded-xl border border-surface-200">
        <span className="text-[10px] font-medium text-surface-400 uppercase tracking-wider">图例</span>
        {Object.entries(ITEM_CONFIG).map(([key, cfg]) => {
          const Icon = cfg.icon;
          return (
            <span key={key} className="flex items-center gap-1 text-[10px] text-surface-500">
              <Icon size={11} className={cfg.color} />
              {cfg.label}
            </span>
          );
        })}
        <span className="text-surface-200">|</span>
        <span className="flex items-center gap-1 text-[10px] text-amber-600">
          <Zap size={11} />
          动态调整标记
        </span>
      </div>
    </div>
  );
}
