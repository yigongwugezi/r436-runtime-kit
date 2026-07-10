import { useChatStore } from '../../store/chatStore';
import type { AgentStep } from '../../types/chat';
import { CheckCircle2, Loader2, XCircle, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';

const AGENT_ICONS: Record<string, string> = {
  intent_router: '🧭', conversation: '💬', profile: '👤', knowledge: '📚',
  diagnosis: '🩺', planner: '🗺️', resource: '📦', question: '📝',
  review: '🛡️', grading: '📊', reply: '💬',
};

function StepRow({ step, isLast }: { step: AgentStep; isLast: boolean }) {
  const statusIcon = step.status === 'completed'
    ? <CheckCircle2 className="w-4 h-4 text-green-500" />
    : step.status === 'failed'
    ? <XCircle className="w-4 h-4 text-red-500" />
    : step.status === 'retrying'
    ? <AlertTriangle className="w-4 h-4 text-amber-500" />
    : <Loader2 className="w-4 h-4 text-brand-500 animate-spin" />;

  return (
    <div className="flex items-start gap-3">
      {/* Timeline */}
      <div className="flex flex-col items-center flex-shrink-0 pt-0.5">
        <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${
          step.status === 'completed' ? 'bg-green-50' :
          step.status === 'failed' ? 'bg-red-50' :
          step.status === 'retrying' ? 'bg-amber-50' :
          'bg-brand-50'
        }`}>
          {statusIcon}
        </div>
        {!isLast && <div className={`w-0.5 flex-1 min-h-[20px] mt-1 ${
          step.status === 'completed' ? 'bg-green-200' : 'bg-surface-200'
        }`} />}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold text-surface-800 dark:text-gray-200">
            {AGENT_ICONS[step.node] || '•'} {step.agent_name}
          </span>
          <span className="text-xs text-surface-500">{step.label}</span>
          {step.duration_ms != null && step.status === 'completed' && (
            <span className="text-2xs text-surface-400 ml-auto">{(step.duration_ms / 1000).toFixed(1)}s</span>
          )}
        </div>
        {step.summary && (
          <p className="text-xs text-surface-500 dark:text-surface-400 mt-0.5">{step.summary}</p>
        )}
        {step.status === 'retrying' && (
          <p className="text-2xs text-amber-600 mt-0.5">
            ⚠️ {step.reason || '重试中'} ({step.retry}/{step.max_retries})
          </p>
        )}
        {step.status === 'failed' && (
          <p className="text-2xs text-red-500 mt-0.5">{step.summary || '执行失败'}</p>
        )}
      </div>
    </div>
  );
}

export default function PipelineProgressPanel() {
  const agentSteps = useChatStore((s) => s.agentSteps);
  const agentProgress = useChatStore((s) => s.agentProgress);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const [collapsed, setCollapsed] = useState(false);

  if (agentSteps.length === 0 && !isStreaming) return null;

  const completedCount = agentSteps.filter(s => s.status === 'completed').length;
  const totalCount = agentSteps.length;
  const hasError = agentSteps.some(s => s.status === 'failed');
  const allDone = !isStreaming && agentSteps.length > 0;

  // §3.3 Collapsed summary bar when all done
  if (allDone && collapsed) {
    return (
      <div className="mx-0 mb-4">
        <button onClick={() => setCollapsed(false)}
          className="w-full flex items-center gap-3 px-4 py-2.5 bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-500/20 rounded-xl text-sm transition-colors hover:bg-green-100 dark:hover:bg-green-500/20">
          <CheckCircle2 className="w-4 h-4 text-green-600" />
          <span className="font-medium text-green-700 dark:text-green-400">
            ✅ 全部 {totalCount} 个智能体协同完成
          </span>
          <span className="text-xs text-green-500 ml-auto">展开 <ChevronDown className="w-3 h-3 inline" /></span>
        </button>
      </div>
    );
  }

  // §3.2 Full progress panel
  return (
    <div className="mx-0 mb-4 bg-white dark:bg-surface-800 border border-surface-200 dark:border-surface-700 rounded-2xl shadow-soft overflow-hidden animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-surface-100 dark:border-surface-700">
        <div className="flex items-center gap-2">
          <div className={`w-2.5 h-2.5 rounded-full ${allDone ? 'bg-green-500' : hasError ? 'bg-red-500' : 'bg-brand-500 animate-pulse'}`} />
          <span className="text-sm font-semibold text-surface-800 dark:text-gray-200">
            {allDone ? '执行完成' : hasError ? '执行异常' : '智能体协同工作中'}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-surface-500">{completedCount}/{totalCount}</span>
          {allDone && (
            <button onClick={() => setCollapsed(true)}
              className="flex items-center gap-1 text-xs text-surface-400 hover:text-surface-600 transition-colors">
              收起 <ChevronUp className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Step list */}
      <div className="px-5 py-3 space-y-0">
        {agentSteps.map((step, i) => (
          <StepRow key={`${step.node}-${i}`} step={step} isLast={i === agentSteps.length - 1 && !allDone} />
        ))}
        {isStreaming && agentSteps.length === 0 && (
          <div className="flex items-center gap-3 py-4">
            <Loader2 className="w-5 h-5 text-brand-500 animate-spin" />
            <span className="text-sm text-surface-500">ConversationAgent 正在分析你的需求…</span>
          </div>
        )}
      </div>

      {/* §3.3 Summary cards after completion */}
      {allDone && agentSteps.filter(s => s.card?.card_type).length > 0 && (
        <div className="px-5 py-3 border-t border-surface-100 dark:border-surface-700 bg-surface-50 dark:bg-surface-800/50">
          <div className="flex flex-wrap gap-2">
            {agentSteps.filter(s => s.card?.card_type).map((step, i) => (
              <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white dark:bg-surface-700 border border-surface-200 dark:border-surface-600 text-2xs text-surface-600 dark:text-surface-300">
                {AGENT_ICONS[step.node] || '•'} {step.card!.summary}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
