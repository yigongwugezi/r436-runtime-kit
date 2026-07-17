/** Filter chips for knowledge graph — by status and chapter. */
import { X } from 'lucide-react';

export type KGNodeStatusFilter = 'not_started' | 'in_progress' | 'mastered' | 'needs_review';

const STATUS_OPTIONS: Array<{ value: KGNodeStatusFilter; label: string }> = [
  { value: 'not_started', label: '未学习' },
  { value: 'in_progress', label: '进行中' },
  { value: 'mastered', label: '已掌握' },
  { value: 'needs_review', label: '需复习' },
];

interface KGFilterProps {
  selectedStatuses: KGNodeStatusFilter[];
  onStatusChange: (statuses: KGNodeStatusFilter[]) => void;
  chapters: string[];
  selectedChapter: string;
  onChapterChange: (chapter: string) => void;
}

export default function KGFilter({
  selectedStatuses,
  onStatusChange,
  chapters,
  selectedChapter,
  onChapterChange,
}: KGFilterProps) {
  const toggleStatus = (status: KGNodeStatusFilter) => {
    if (selectedStatuses.includes(status)) {
      onStatusChange(selectedStatuses.filter((s) => s !== status));
    } else {
      onStatusChange([...selectedStatuses, status]);
    }
  };

  return (
    <div className="flex items-center gap-3 flex-wrap">
      {/* Chapter selector */}
      {chapters.length > 0 && (
        <select
          value={selectedChapter}
          onChange={(e) => onChapterChange(e.target.value)}
          className="px-3 py-1.5 rounded-xl border border-surface-200 bg-white text-xs font-medium text-surface-600 outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all cursor-pointer"
        >
          <option value="">全部章节</option>
          {chapters.map((ch) => (
            <option key={ch} value={ch}>{ch}</option>
          ))}
        </select>
      )}

      {/* Status chips */}
      <div className="flex items-center gap-1.5">
        {STATUS_OPTIONS.map((opt) => {
          const active = selectedStatuses.includes(opt.value);
          return (
            <button
              key={opt.value}
              onClick={() => toggleStatus(opt.value)}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all ${
                active
                  ? 'bg-primary-50 text-primary-700 ring-1 ring-primary-300'
                  : 'bg-surface-100 text-surface-500 hover:bg-surface-200'
              }`}
            >
              {opt.label}
              {active && <X size={10} className="inline ml-1 -mr-0.5 align-text-top" />}
            </button>
          );
        })}
      </div>

      {/* Clear filters */}
      {(selectedChapter || selectedStatuses.length > 0) && (
        <button
          onClick={() => {
            onStatusChange([]);
            onChapterChange('');
          }}
          className="text-[11px] text-primary-600 hover:text-primary-700 font-medium"
        >
          清除筛选
        </button>
      )}
    </div>
  );
}
