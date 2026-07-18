import { memo } from 'react';

// ══════════════════════════════════════════════════════════════════════
// MasteryBar — 单个知识点掌握度进度条
// 使用系统 surface / success / warning / danger 色阶
// ══════════════════════════════════════════════════════════════════════

interface MasteryItem {
  name?: string;
  topic?: string;
  score?: number;
  level?: string;
}

function masteryColor(score: number): string {
  if (score >= 80) return 'bg-success-500';
  if (score >= 50) return 'bg-warning-400';
  return 'bg-danger-400';
}

function masteryLabel(score: number): string {
  if (score >= 80) return '熟练';
  if (score >= 50) return '掌握中';
  return '需加强';
}

const MasteryBar = memo(function MasteryBar({
  name,
  score = 50,
}: {
  name: string;
  score: number;
}) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="w-16 shrink-0 truncate text-[11px] font-medium text-surface-600"
        title={name}
      >
        {name}
      </span>
      <span className="flex-1 h-1.5 rounded-full bg-surface-100 overflow-hidden">
        <span
          className={`block h-full rounded-full transition-all duration-500 ${masteryColor(score)}`}
          style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
        />
      </span>
      <span className="w-10 shrink-0 text-right text-[10px] font-semibold text-surface-400">
        {masteryLabel(score)}
      </span>
    </div>
  );
});

export default memo(function MasteryBarGroup({
  items,
  max = 5,
}: {
  items: MasteryItem[] | null | undefined;
  max?: number;
}) {
  if (!items || items.length === 0) return null;

  const list = items.slice(0, max).map((m) => ({
    name: m.name || m.topic || '未知',
    score: typeof m.score === 'number' ? m.score : 50,
  }));

  return (
    <div className="mt-4 pt-4 border-t border-surface-100">
      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-surface-400">
        知识掌握度
      </p>
      <div className="space-y-2">
        {list.map((item, i) => (
          <MasteryBar key={i} name={item.name} score={item.score} />
        ))}
      </div>
    </div>
  );
});
