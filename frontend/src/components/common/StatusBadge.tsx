import type { ReactNode } from 'react';

/* ===================================================================
 * 统一 Badge 组件
 * 支持 source / quality / difficulty / event_type / priority
 * =================================================================== */

type BadgeVariant = 'blue' | 'green' | 'amber' | 'red' | 'purple' | 'cyan' | 'rose' | 'slate' | 'brand' | 'emerald' | 'indigo';

const VARIANT_STYLES: Record<BadgeVariant, string> = {
  blue:    'bg-blue-50 text-blue-600 border-blue-200',
  green:   'bg-green-50 text-green-600 border-green-200',
  amber:   'bg-amber-50 text-amber-600 border-amber-200',
  red:     'bg-red-50 text-red-600 border-red-200',
  purple:  'bg-purple-50 text-purple-600 border-purple-200',
  cyan:    'bg-cyan-50 text-cyan-600 border-cyan-200',
  rose:    'bg-rose-50 text-rose-600 border-rose-200',
  slate:   'bg-slate-50 text-slate-600 border-slate-200',
  brand:   'bg-brand-50 text-brand-600 border-brand-200',
  emerald: 'bg-emerald-50 text-emerald-600 border-emerald-200',
  indigo:  'bg-indigo-50 text-indigo-600 border-indigo-200',
};

const DIFFICULTY_MAP: Record<string, { label: string; variant: BadgeVariant }> = {
  easy:   { label: '基础',   variant: 'green' },
  medium: { label: '进阶',   variant: 'amber' },
  hard:   { label: '挑战',   variant: 'red' },
};

const QUALITY_MAP: Record<string, { label: string; variant: BadgeVariant }> = {
  passed:          { label: '已通过',   variant: 'green' },
  needs_review:    { label: '需复核',   variant: 'red' },
  fallback_passed: { label: '兜底通过', variant: 'amber' },
  warning:         { label: '警告',     variant: 'amber' },
  ok:              { label: '正常',     variant: 'green' },
};

const PRIORITY_MAP: Record<string, { label: string; variant: BadgeVariant }> = {
  high:   { label: '高优', variant: 'red' },
  medium: { label: '中等', variant: 'amber' },
  low:    { label: '普通', variant: 'slate' },
};

interface StatusBadgeProps {
  label?: string;
  variant?: BadgeVariant;
  icon?: ReactNode;
  size?: 'xs' | 'sm';
  /** 快捷设置：按类型自动选择样式 */
  type?: 'difficulty' | 'quality' | 'priority';
  typeValue?: string;
}

/** 统一状态标签 */
export default function StatusBadge({
  label,
  variant = 'slate',
  icon,
  size = 'xs',
  type,
  typeValue,
}: StatusBadgeProps) {
  // 根据类型自动推断样式
  if (type && typeValue) {
    const map = type === 'difficulty' ? DIFFICULTY_MAP
      : type === 'quality' ? QUALITY_MAP
      : PRIORITY_MAP;
    const cfg = map[typeValue];
    if (cfg) {
      label = cfg.label;
      variant = cfg.variant;
    }
  }

  if (!label) return null;

  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border font-medium whitespace-nowrap ${
        size === 'xs' ? 'text-[9px]' : 'text-[10px]'
      } ${VARIANT_STYLES[variant] || VARIANT_STYLES.slate}`}
    >
      {icon}
      {label}
    </span>
  );
}

/* ===================================================================
 * 快捷导出：常用 badge 变体
 * =================================================================== */
export function DifficultyBadge({ level, size }: { level: string; size?: 'xs' | 'sm' }) {
  return <StatusBadge type="difficulty" typeValue={level} size={size} />;
}

export function QualityBadge({ status, size }: { status: string; size?: 'xs' | 'sm' }) {
  return <StatusBadge type="quality" typeValue={status} size={size} />;
}

export function PriorityBadge({ priority, size }: { priority: string; size?: 'xs' | 'sm' }) {
  return <StatusBadge type="priority" typeValue={priority} size={size} />;
}
