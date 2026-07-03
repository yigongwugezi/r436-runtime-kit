import { ClipboardList, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useDailyTasks } from '../../hooks/useDailyTasks';
import { getCurrentLearner } from '../../store/authStore';
import TaskItem from './TaskItem';

const SUBJECT_COLORS = ['primary', 'accent', 'warning', 'success'] as const;

export default function DailyTaskPanel() {
  const nav = useNavigate();
  const isParent = getCurrentLearner()?.role === 'parent';
  const {
    tasks,
    tasksBySubject,
    completedCount,
    totalCount,
    loading,
    error,
    toggleTask,
  } = useDailyTasks();

  // Loading skeleton
  if (loading && tasks.length === 0) {
    return (
      <div className="bg-white rounded-2xl p-6 shadow-soft animate-pulse">
        <div className="h-5 w-32 bg-surface-100 rounded mb-4" />
        <div className="space-y-3">
          <div className="h-12 bg-surface-50 rounded-xl" />
          <div className="h-12 bg-surface-50 rounded-xl" />
          <div className="h-12 bg-surface-50 rounded-xl" />
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-white rounded-2xl p-6 shadow-soft">
        <div className="flex items-center gap-2 mb-3">
          <ClipboardList size={20} className="text-error-500" />
          <h3 className="font-display text-lg font-semibold text-surface-800">
            今日任务
          </h3>
        </div>
        <p className="text-sm text-error-500 py-3">{error}</p>
      </div>
    );
  }

  // Empty state
  if (totalCount === 0) {
    return (
      <div className="bg-white rounded-2xl p-6 shadow-soft">
        <div className="flex items-center gap-2 mb-3">
          <ClipboardList size={20} className="text-primary-500" />
          <h3 className="font-display text-lg font-semibold text-surface-800">
            今日任务
          </h3>
        </div>
        <p className="text-sm text-surface-400 text-center py-6">
          还没有今日任务
          <br />
          <span className="text-xs">
            选择科目并生成学习计划后，每日任务会自动出现
          </span>
        </p>
        <button
          onClick={() => nav('/chat')}
          className="w-full mt-2 flex items-center justify-center gap-2 px-4 py-2.5 bg-primary-50 rounded-xl text-primary-600 text-sm font-medium hover:bg-primary-100 transition-colors"
        >
          去生成学习计划 <ChevronRight size={16} />
        </button>
      </div>
    );
  }

  const progressPct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  return (
    <div className="bg-white rounded-2xl p-6 shadow-soft">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <ClipboardList size={20} className="text-primary-500" />
          <h3 className="font-display text-lg font-semibold text-surface-800">
            今日任务
          </h3>
          {totalCount > 0 && (
            <span className="px-2 py-0.5 bg-primary-100 text-primary-700 rounded-full text-[10px] font-semibold">
              {completedCount}/{totalCount}
            </span>
          )}
        </div>
        {/* Progress ring */}
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-surface-50 flex items-center justify-center">
            <svg className="w-6 h-6" viewBox="0 0 24 24">
              <circle
                cx="12" cy="12" r="10"
                fill="none" stroke="#e2e8f0" strokeWidth="3"
              />
              <circle
                cx="12" cy="12" r="10"
                fill="none" stroke="#3b82f6"
                strokeWidth="3"
                strokeDasharray={`${progressPct * 0.628} 62.8`}
                strokeLinecap="round"
                transform="rotate(-90 12 12)"
              />
            </svg>
          </div>
          <span className="text-xs text-surface-500">{progressPct}%</span>
        </div>
      </div>

      {/* Progress bar */}
      {totalCount > 0 && (
        <div className="h-1.5 bg-surface-100 rounded-full mb-4 overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-primary-500 to-accent-500 rounded-full transition-all duration-500 ease-out"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      )}

      {/* Tasks grouped by subject */}
      <div className="space-y-4 max-h-[360px] overflow-y-auto pr-1">
        {Object.entries(tasksBySubject).map(([subjectId, subjectTasks], idx) => {
          const firstTask = subjectTasks[0];
          const subjectCompleted = subjectTasks.filter((t) => t.completed).length;
          const subjectTotal = subjectTasks.length;
          const color = SUBJECT_COLORS[idx % SUBJECT_COLORS.length];
          return (
            <div key={subjectId}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-surface-600 uppercase tracking-wider">
                  {firstTask?.subjectName || '未命名科目'}
                </span>
                <span className="text-[10px] text-surface-400">
                  {subjectCompleted}/{subjectTotal}
                </span>
              </div>
              <div className="space-y-1">
                {subjectTasks.map((task) => (
                  <TaskItem
                    key={task.id}
                    task={task}
                    onToggle={isParent ? undefined : toggleTask}
                    color={color}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
