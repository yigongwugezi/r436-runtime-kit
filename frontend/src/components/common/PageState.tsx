import { AlertCircle, AlertTriangle, Inbox, RefreshCw, Sparkles, Cpu } from 'lucide-react';
import type { ReactNode } from 'react';

export type PageStateType = 'loading' | 'empty' | 'error' | 'fallback' | 'generated' | 'idle';

export function PageLoading({ text = '加载中...', overlay }: { text?: string; overlay?: boolean }) {
  const inner = (
    <div className="flex flex-col items-center gap-3 py-16">
      <div className="w-8 h-8 rounded-full border-3 border-accent-200 border-t-accent-600 animate-spin" />
      <span className="text-sm text-gray-400">{text}</span>
    </div>
  );
  if (overlay) return <div className="absolute inset-0 z-10 bg-white/70 flex items-center justify-center">{inner}</div>;
  return inner;
}

export function PageEmpty({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center py-20 text-center">
      <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mb-5">
        {icon || <Inbox className="w-8 h-8 text-gray-300" />}
      </div>
      <h3 className="text-lg font-semibold text-gray-700 mb-2">{title}</h3>
      {description && <p className="text-sm text-gray-400 max-w-sm mb-6">{description}</p>}
      {action}
    </div>
  );
}

export function RetryActions({ onRetry, onGoChat, chatLabel = '去对话页' }: { onRetry: () => void; onGoChat?: () => void; chatLabel?: string }) {
  return (
    <div className="flex items-center gap-3">
      <button onClick={onRetry} className="px-5 py-2.5 bg-accent-600 text-white rounded-xl text-sm font-semibold hover:bg-accent-700 transition-colors inline-flex items-center gap-2">
        <RefreshCw className="w-4 h-4" /> 重试
      </button>
      {onGoChat && <button onClick={onGoChat} className="px-5 py-2.5 bg-gray-100 text-gray-600 rounded-xl text-sm font-semibold hover:bg-gray-200 transition-colors">{chatLabel}</button>}
    </div>
  );
}

export function SourceTag({ source }: { source: string | undefined | null }) {
  if (!source || source === 'none' || source === 'user_input') return null;
  const config: Record<string, { label: string; icon: React.ReactNode; cls: string }> = {
    agent_generated: { label: 'AI 生成', icon: <Sparkles className="w-3 h-3" />, cls: 'bg-purple-50 text-purple-600' },
    system_inferred: { label: '系统推断', icon: <Cpu className="w-3 h-3" />, cls: 'bg-amber-50 text-amber-600' },
    fallback: { label: '规则兜底', icon: <Cpu className="w-3 h-3" />, cls: 'bg-slate-50 text-slate-500' },
  };
  const c = config[source];
  if (!c) return null;
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${c.cls}`}>{c.icon}{c.label}</span>;
}

export function PageError({ title, description, onRetry, onGoChat }: { title?: string; description?: string | null; onRetry: () => void; onGoChat?: () => void }) {
  return (
    <div className="flex flex-col items-center py-20 text-center">
      <div className="w-16 h-16 rounded-2xl bg-red-50 flex items-center justify-center mb-5">
        <AlertCircle className="w-8 h-8 text-red-400" />
      </div>
      <h3 className="text-lg font-semibold text-gray-700 mb-2">{title || '加载失败'}</h3>
      {description && <p className="text-sm text-gray-400 max-w-sm mb-6">{description}</p>}
      <RetryActions onRetry={onRetry} onGoChat={onGoChat} />
    </div>
  );
}

export function FallbackBanner({ message = '内容来自系统兜底规则。' }: { message?: string }) {
  return <div className="mb-4 p-3 bg-amber-50 rounded-xl flex items-start gap-2"><AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-px" /><p className="text-xs text-amber-700">{message}</p></div>;
}

export function RefreshOverlay() {
  return <div className="absolute inset-0 z-10 bg-white/60 flex items-center justify-center"><div className="flex items-center gap-2 px-4 py-2 bg-white rounded-lg shadow-sm border border-gray-100"><div className="w-4 h-4 rounded-full border-2 border-accent-200 border-t-accent-600 animate-spin" /><span className="text-xs text-gray-400">刷新中...</span></div></div>;
}
