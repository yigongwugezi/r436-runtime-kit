/** Floating card for node detail — pops up near the selected node. */
import { useEffect, useRef } from 'react';
import { BookOpen, CheckCircle2, Clock, X } from 'lucide-react';
import type { KGNode } from '../../types/knowledgeGraph';

interface KGNodeCardProps {
  node: KGNode;
  onClose: () => void;
  onLearn: (nodeId: string) => void;
  onExpand: (nodeId: string) => void;
}

const STATUS_LABELS: Record<string, string> = {
  not_started: '未学习',
  in_progress: '进行中',
  mastered: '已掌握',
  needs_review: '需复习',
};

const DIFFICULTY_LABELS: Record<string, string> = {
  easy: '简单',
  medium: '中等',
  hard: '困难',
  challenge: '挑战',
};

export default function KGNodeCard({ node, onClose, onLearn, onExpand }: KGNodeCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const masteryColor =
    node.mastery >= 80 ? 'bg-success-500' : node.mastery >= 40 ? 'bg-primary-500' : 'bg-surface-300';

  return (
    <div
      ref={cardRef}
      className="absolute z-50 bg-white rounded-xl shadow-elevated border border-surface-200 w-72 overflow-hidden animate-fade-in"
      style={{ pointerEvents: 'auto' }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-start justify-between px-4 pt-3 pb-1">
        <h4 className="text-sm font-semibold text-surface-800 leading-tight pr-2">
          {node.label}
        </h4>
        <button
          onClick={onClose}
          className="p-0.5 rounded-md hover:bg-surface-100 text-surface-400 hover:text-surface-600 transition-colors flex-shrink-0"
        >
          <X size={14} />
        </button>
      </div>

      {/* Mastery bar */}
      <div className="px-4 py-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-surface-500">掌握度</span>
          <span className="text-xs font-medium text-surface-600 tabular-nums">{node.mastery}%</span>
        </div>
        <div className="mt-1 w-full h-1.5 bg-surface-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${masteryColor}`}
            style={{ width: `${node.mastery}%` }}
          />
        </div>
      </div>

      {/* Tags */}
      <div className="px-4 pb-2 flex flex-wrap gap-1.5">
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-surface-100 text-surface-600 text-[10px] font-medium">
          {STATUS_LABELS[node.status] || node.status}
        </span>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-surface-100 text-surface-600 text-[10px] font-medium">
          {DIFFICULTY_LABELS[node.difficulty] || node.difficulty}
        </span>
        {node.category && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-accent-50 text-accent-700 text-[10px] font-medium">
            {node.category}
          </span>
        )}
      </div>

      {/* Stats row */}
      <div className="px-4 pb-2 flex items-center gap-3 text-[11px] text-surface-400">
        {node.resourceCount > 0 && (
          <span className="flex items-center gap-1">
            <BookOpen size={12} />
            {node.completedCount}/{node.resourceCount} 资源
          </span>
        )}
        <span className="flex items-center gap-1">
          <Clock size={12} />
          重要性 {'★'.repeat(node.importance) || '-'}
        </span>
      </div>

      {/* Actions */}
      <div className="px-4 pb-3 flex gap-2">
        <button
          onClick={() => onLearn(node.id)}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 bg-primary-600 text-white rounded-lg text-xs font-medium hover:bg-primary-700 transition-colors"
        >
          <BookOpen size={13} />
          去学习
        </button>
        <button
          onClick={() => onExpand(node.id)}
          className="flex items-center justify-center gap-1.5 px-3 py-1.5 bg-surface-100 text-surface-600 rounded-lg text-xs font-medium hover:bg-surface-200 transition-colors"
        >
          展开详情
        </button>
      </div>
    </div>
  );
}
