import { useMemo, type ReactNode } from 'react';
import {
  Bookmark, Volume2, FileText, PenTool, Mic, Brain,
  Clock, CheckCircle2, Sparkles,
} from 'lucide-react';
import type { ContentType } from './SectionContentRouter';

// ══════════════════════════════════════════════════════════════════════
// Types
// ══════════════════════════════════════════════════════════════════════

interface TaskMeta {
  label: string;
  icon: typeof Bookmark;
  gradient: string;
  defaultContentType: ContentType;
  quickPrompt: string;
}

// ══════════════════════════════════════════════════════════════════════
// Task type → visual config (single source of truth)
// ══════════════════════════════════════════════════════════════════════

const TASK_META: Record<string, TaskMeta> = {
  vocabulary: {
    label: '词汇记忆',
    icon: Bookmark,
    gradient: 'from-violet-500 to-purple-600',
    defaultContentType: 'memory_drill',
    quickPrompt: '用闪卡形式展示本节核心词汇，包含词义、例句和记忆技巧。',
  },
  listening: {
    label: '听力训练',
    icon: Volume2,
    gradient: 'from-blue-500 to-cyan-600',
    defaultContentType: 'lecture',
    quickPrompt: '提供本节相关的听力材料，包含音频脚本和理解题目。',
  },
  reading: {
    label: '阅读理解',
    icon: FileText,
    gradient: 'from-emerald-500 to-teal-600',
    defaultContentType: 'lecture',
    quickPrompt: '提供一篇与本课主题相关的阅读文章，附上理解题。',
  },
  grammar: {
    label: '语法专项',
    icon: PenTool,
    gradient: 'from-amber-500 to-orange-600',
    defaultContentType: 'step_through',
    quickPrompt: '用分步讲解的方式解析本节语法点，配例句和练习。',
  },
  speaking: {
    label: '口语练习',
    icon: Mic,
    gradient: 'from-rose-500 to-pink-600',
    defaultContentType: 'lecture',
    quickPrompt: '提供本节主题的口语练习素材，包含对话模板和发音要点。',
  },
  writing: {
    label: '写作训练',
    icon: PenTool,
    gradient: 'from-orange-500 to-red-500',
    defaultContentType: 'lecture',
    quickPrompt: '围绕本节主题提供写作任务，包含提纲指引和范文。',
  },
  review: {
    label: '复习测验',
    icon: Brain,
    gradient: 'from-cyan-500 to-blue-600',
    defaultContentType: 'lecture',
    quickPrompt: '对本节内容进行综合回顾，生成一组自测题目。',
  },
};

export function getTaskMeta(taskType?: string): TaskMeta | null {
  if (!taskType) return null;
  return TASK_META[taskType] || null;
}

function getMeta(taskType?: string): TaskMeta | null {
  return getTaskMeta(taskType);
}

export function getDefaultContentType(taskType?: string): ContentType {
  return getMeta(taskType)?.defaultContentType || 'lecture';
}

// ══════════════════════════════════════════════════════════════════════
// DailyTaskHeader — shows task type, progress, and quick-AI button
// ══════════════════════════════════════════════════════════════════════

interface DailyHeaderProps {
  taskType?: string;
  sectionTitle?: string;
  estimatedMinutes?: number;
  dayIndex?: number;
  totalDays?: number;
  completedTasks?: number;
  totalTasks?: number;
  onQuickPrompt?: (prompt: string) => void;
}

export function DailyTaskHeader({
  taskType,
  sectionTitle,
  estimatedMinutes,
  dayIndex,
  totalDays,
  completedTasks = 0,
  totalTasks = 0,
  onQuickPrompt,
}: DailyHeaderProps) {
  const meta = getMeta(taskType);
  if (!meta) return null;

  const Icon = meta.icon;
  const pct = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  return (
    <div className="bg-white rounded-2xl shadow-soft p-5 mb-5 animate-fade-in">
      <div className="flex items-start gap-4">
        {/* Icon — matches SectionHeader style */}
        <div
          className={`w-12 h-12 rounded-2xl bg-gradient-to-br ${meta.gradient} flex items-center justify-center flex-shrink-0 shadow-lg shadow-${meta.gradient.split('-')[1]}-500/20`}
        >
          <Icon size={22} className="text-white" />
        </div>

        <div className="flex-1 min-w-0">
          {/* Task type badge + day counter */}
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg bg-surface-100 text-[10px] font-bold text-surface-500">
              {meta.label}
            </span>
            {dayIndex != null && totalDays != null && (
              <span className="text-xs text-surface-400 font-medium">
                Day {dayIndex}/{totalDays}
              </span>
            )}
            {estimatedMinutes != null && (
              <span className="flex items-center gap-1 text-xs text-surface-400">
                <Clock size={11} /> ~{estimatedMinutes}min
              </span>
            )}
          </div>

          {sectionTitle && (
            <h3 className="text-base font-bold text-surface-900 font-display">{sectionTitle}</h3>
          )}

          {/* Quick AI prompt — clean secondary button */}
          {onQuickPrompt && (
            <button
              onClick={() => onQuickPrompt(meta.quickPrompt)}
              className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl
                bg-surface-50 border border-surface-200 text-xs font-medium text-surface-500
                hover:text-surface-700 hover:border-surface-300 hover:bg-white
                active:scale-[0.98] transition-all duration-150"
            >
              <Sparkles size={12} className="text-surface-400" />
              AI 准备{meta.label}素材
            </button>
          )}
        </div>

        {/* Mini progress circle */}
        {totalTasks > 0 && (
          <div className="text-right flex-shrink-0 pt-1">
            <p className="text-2xl font-bold text-surface-800 font-display">{pct}%</p>
            <p className="flex items-center justify-end gap-1 text-xs text-surface-400 mt-0.5">
              <CheckCircle2 size={11} className="text-emerald-500" />
              {completedTasks}/{totalTasks}
            </p>
          </div>
        )}
      </div>

      {/* Progress bar */}
      {totalTasks > 0 && (
        <div className="mt-4 h-2 bg-surface-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-blue-400 to-emerald-400 rounded-full transition-all duration-700"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════
// DailyQuickActions — right-panel task-specific shortcuts
// ══════════════════════════════════════════════════════════════════════

interface DailyQuickActionsProps {
  taskType?: string;
  onAction: (actionType: string, prompt: string) => void;
}

export function DailyQuickActions({ taskType, onAction }: DailyQuickActionsProps) {
  const meta = getMeta(taskType);

  const actions: { key: string; label: string; icon: ReactNode; prompt: string }[] = useMemo(() => {
    const common = [
      { key: 'explain', label: '文字讲解', icon: <FileText size={13} />, prompt: '详细讲解本节核心内容和要点。' },
      { key: 'diagram', label: '图解结构', icon: <Sparkles size={13} />, prompt: '用结构化图解梳理本节知识体系。' },
      { key: 'quiz', label: '小测验', icon: <Brain size={13} />, prompt: '根据本节内容生成一组练习题目。' },
    ];
    if (meta) {
      return [
        { key: meta.defaultContentType, label: meta.label, icon: <meta.icon size={13} />, prompt: meta.quickPrompt },
        ...common,
      ];
    }
    return common;
  }, [meta]);

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold text-surface-400 uppercase tracking-wider px-1">
        {meta ? `${meta.label} · 快捷操作` : '快捷操作'}
      </p>
      {actions.map((a) => (
        <button
          key={a.key}
          onClick={() => onAction(a.key, a.prompt)}
          className="w-full flex items-center gap-2.5 p-2.5 rounded-xl bg-surface-50
            hover:bg-white hover:border-surface-200 active:scale-[0.98]
            transition-all duration-150 text-left border border-transparent"
        >
          <span className="text-surface-400 flex-shrink-0">{a.icon}</span>
          <span className="text-xs font-medium text-surface-600">{a.label}</span>
        </button>
      ))}
    </div>
  );
}
