import {
  AlertCircle, AlertTriangle, BookOpen, GitFork, Inbox, Loader2,
  RefreshCw, Sparkles, TrendingUp, User, Cpu,
} from 'lucide-react';
import type { ReactNode } from 'react';

/* ===================================================================
 * 状态枚举
 * =================================================================== */
export type PageStateType = 'loading' | 'empty' | 'error' | 'fallback' | 'generated' | 'idle';

/* ===================================================================
 * 页面级 Loading（带刷新时覆盖模式）
 * =================================================================== */
export function PageLoading({
  text = '加载中...',
  overlay = false,
}: {
  text?: string;
  overlay?: boolean;
}) {
  const inner = (
    <div className="flex flex-col items-center justify-center gap-3">
      <div className="relative">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-brand-100 to-brand-200 flex items-center justify-center shadow-lg shadow-brand-100/50">
          <Sparkles className="w-6 h-6 text-brand-500 animate-pulse" />
        </div>
        <div className="absolute -top-1 -right-1">
          <div className="w-5 h-5 rounded-full border-2 border-brand-500 border-t-transparent animate-spin bg-white" />
        </div>
      </div>
      <span className="text-sm font-medium text-gray-500">{text}</span>
      <div className="flex items-center gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-brand-300 animate-bounce"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  );

  if (overlay) {
    return (
      <div className="absolute inset-0 z-10 bg-white/70 backdrop-blur-[1px] flex items-center justify-center rounded-2xl">
        {inner}
      </div>
    );
  }

  return <div className="py-16">{inner}</div>;
}

/* ===================================================================
 * 页面级空状态
 * =================================================================== */
export function PageEmpty({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-6 text-center animate-fade-in-up">
      <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center mb-6 shadow-inner">
        {icon || <Inbox className="w-9 h-9 text-gray-300" />}
      </div>
      <h3 className="text-lg font-bold text-gray-700 mb-2">{title}</h3>
      {description && <p className="text-sm text-gray-400 max-w-sm mb-8 leading-relaxed">{description}</p>}
      {action}
    </div>
  );
}

/* ===================================================================
 * 重试按钮组
 * =================================================================== */
export function RetryActions({
  onRetry,
  onGoChat,
  chatLabel = '去对话页',
}: {
  onRetry: () => void;
  onGoChat?: () => void;
  chatLabel?: string;
}) {
  return (
    <div className="flex items-center gap-3 mt-3">
      <button
        onClick={onRetry}
        className="px-4 py-2 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all inline-flex items-center gap-2"
      >
        <RefreshCw className="w-4 h-4" />
        重试
      </button>
      {onGoChat && (
        <button
          onClick={onGoChat}
          className="px-4 py-2 bg-white border border-gray-200 text-gray-600 rounded-xl text-sm font-semibold hover:bg-gray-50 transition-all"
        >
          {chatLabel}
        </button>
      )}
    </div>
  );
}

/* ===================================================================
 * 数据来源标签
 * =================================================================== */
export function SourceTag({
  source,
}: {
  source: string | undefined | null;
}) {
  if (!source || source === 'none' || source === 'user_input') return null;

  const config: Record<string, { label: string; icon: React.ReactNode; cls: string }> = {
    agent_generated: {
      label: 'AI 生成',
      icon: <Sparkles className="w-3 h-3" />,
      cls: 'bg-purple-50 text-purple-600 border-purple-200',
    },
    system_inferred: {
      label: '系统推断',
      icon: <Cpu className="w-3 h-3" />,
      cls: 'bg-amber-50 text-amber-600 border-amber-200',
    },
    fallback: {
      label: '规则兜底',
      icon: <Cpu className="w-3 h-3" />,
      cls: 'bg-slate-50 text-slate-500 border-slate-200',
    },
  };

  const c = config[source];
  // 未知 source 值时不显示
  if (!c) return null;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[10px] font-medium ${c.cls}`}
      title={
        source === 'system_inferred' ? '基于系统规则的初步推断，尚未经过 AI 深度分析' :
        source === 'fallback' ? '此内容由系统规则兜底生成，可能与实际存在偏差' :
        '由 AI 智能体分析生成'
      }
    >
      {c.icon}
      {c.label}
    </span>
  );
}

/* ===================================================================
 * 错误状态
 * =================================================================== */
export function PageError({
  title = '加载失败',
  description,
  onRetry,
  onGoChat,
}: {
  title?: string;
  description?: string | null;
  onRetry: () => void;
  onGoChat?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-6 text-center animate-fade-in-up">
      <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-red-50 to-red-100 flex items-center justify-center mb-6 shadow-inner">
        <AlertCircle className="w-9 h-9 text-red-400" />
      </div>
      <h3 className="text-lg font-bold text-gray-700 mb-2">{title}</h3>
      {description && (
        <p className="text-sm text-gray-400 max-w-sm mb-8 leading-relaxed">{description}</p>
      )}
      <RetryActions onRetry={onRetry} onGoChat={onGoChat} />
    </div>
  );
}

/* ===================================================================
 * Fallback 提示条（内嵌在已有数据页面）
 * =================================================================== */
export function FallbackBanner({
  message = '当前内容来自系统兜底规则，部分数据可能不准确。建议在 AI 对话中补充信息以获取个性化内容。',
}: {
  message?: string;
}) {
  return (
    <div className="mb-6 p-3 bg-amber-50/80 border border-amber-200 rounded-xl flex items-start gap-2.5">
      <Cpu className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
      <p className="text-xs text-amber-700 leading-relaxed">{message}</p>
    </div>
  );
}

/* ===================================================================
 * 刷新遮罩（用于已有数据时后台刷新）
 * =================================================================== */
export function RefreshOverlay() {
  return (
    <div className="absolute inset-0 z-10 bg-white/60 backdrop-blur-[1px] flex items-center justify-center rounded-2xl">
      <div className="flex items-center gap-2 px-4 py-2 bg-white/90 rounded-xl shadow-sm border border-gray-100">
        <Loader2 className="w-4 h-4 text-brand-500 animate-spin" />
        <span className="text-xs text-gray-500">刷新中...</span>
      </div>
    </div>
  );
}
