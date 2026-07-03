import { CheckCircle2, Circle, Loader2 } from 'lucide-react';
import { useState } from 'react';
import type { DailyTask } from '../../types/dailyTask';

interface TaskItemProps {
  task: DailyTask;
  onToggle?: ((task: DailyTask) => Promise<void>) | undefined;
  /** Optional accent color for the checkbox */
  color?: string;
}

const COLOR_MAP: Record<string, string> = {
  primary: 'text-primary-500 group-hover:text-primary-600',
  accent: 'text-accent-500 group-hover:text-accent-600',
  warning: 'text-warning-500 group-hover:text-warning-600',
  success: 'text-success-500 group-hover:text-success-600',
};

export default function TaskItem({ task, onToggle, color = 'primary' }: TaskItemProps) {
  const [pending, setPending] = useState(false);

  const handleClick = async () => {
    if (!onToggle || pending) return;
    setPending(true);
    try {
      await onToggle(task);
    } finally {
      setPending(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={pending || !onToggle}
      className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all
        ${task.completed ? 'bg-surface-50 opacity-60' : 'bg-white hover:bg-surface-50'}
        ${pending ? 'cursor-wait' : (!onToggle ? 'cursor-default' : 'cursor-pointer')}
        group`}
    >
      <div className="flex-shrink-0">
        {pending ? (
          <Loader2 size={20} className="animate-spin text-surface-400" />
        ) : task.completed ? (
          <CheckCircle2 size={20} className="text-success-500" />
        ) : (
          <Circle
            size={20}
            className={COLOR_MAP[color] || 'text-primary-400 group-hover:opacity-80'}
          />
        )}
      </div>
      <div className="flex-1 text-left min-w-0">
        <p
          className={`text-sm font-medium truncate ${
            task.completed ? 'text-surface-400 line-through' : 'text-surface-800'
          }`}
        >
          {task.title}
        </p>
        <p className="text-[11px] text-surface-400 mt-0.5">
          {task.subjectName}
          {task.courseName ? ` · ${task.courseName}` : ''}
        </p>
      </div>
    </button>
  );
}
