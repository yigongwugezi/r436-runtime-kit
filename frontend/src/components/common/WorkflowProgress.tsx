import { useEffect, useState } from 'react';
import { Check, ChevronDown, ChevronUp, Circle, Loader2, RotateCcw, Square } from 'lucide-react';
import type { WorkflowState } from '../../api/workflows';

interface Props {
  state: WorkflowState;
  onCancel?: () => void;
  onRetry?: () => void;
}

const terminal = new Set(['completed', 'cancelled', 'failed', 'expired']);

export default function WorkflowProgress({ state, onCancel, onRetry }: Props) {
  const [expanded, setExpanded] = useState(state.status !== 'completed');
  const [liveSeconds, setLiveSeconds] = useState(0);
  useEffect(() => {
    if (terminal.has(state.status)) return;
    const timer = window.setInterval(() => setLiveSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [state.status]);
  const stages = state.events.filter((event) => event.event !== 'content_delta' && event.event !== 'preview_updated' && !event.event.startsWith('workflow_'))
    .reduce<WorkflowState['events']>((items, event) => {
      const index = items.findIndex((item) => item.stage_id === event.stage_id);
      if (index < 0) return [...items, event];
      const next = [...items]; next[index] = event; return next;
    }, []);
  const latest = state.events[state.events.length - 1];
  const elapsed = terminal.has(state.status) ? (latest?.elapsed_ms || state.elapsedMs) : Math.max(state.elapsedMs, latest?.elapsed_ms || 0) + liveSeconds * 1000;
  const count = latest?.total_units ? ` · 已完成 ${latest.completed_units || 0} / ${latest.total_units}` : '';

  return <section className="rounded-xl border border-blue-100 bg-blue-50/60 p-3 text-xs text-surface-700" aria-live="polite">
    <div className="flex items-center gap-2">
      {state.status === 'running' || state.status === 'queued' ? <Loader2 size={14} className="animate-spin text-blue-600" /> : state.status === 'completed' ? <Check size={14} className="text-emerald-600" /> : <Square size={13} className="text-amber-600" />}
      <button className="flex-1 text-left font-medium" onClick={() => setExpanded((value) => !value)}>
        {state.status === 'cancelled' ? '任务已取消（预览未保存）' : state.status === 'failed' ? '任务失败' : latest?.label || '准备任务'}
        <span className="ml-2 font-normal text-surface-400">已用时 {Math.ceil(elapsed / 1000)} 秒{count}</span>
      </button>
      {onCancel && !terminal.has(state.status) && <button onClick={onCancel} className="rounded px-2 py-1 text-red-600 hover:bg-red-50">取消</button>}
      {onRetry && ['failed', 'cancelled', 'expired'].includes(state.status) && <button onClick={onRetry} className="flex items-center gap-1 rounded px-2 py-1 text-blue-600 hover:bg-white"><RotateCcw size={12} />重试</button>}
      <button onClick={() => setExpanded((value) => !value)} aria-label={expanded ? '折叠进度' : '展开进度'}>{expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</button>
    </div>
    {expanded && <div className="mt-3 space-y-2">
      {stages.map((stage) => <div key={stage.stage_id} className="flex items-start gap-2">
        {stage.status === 'completed' ? <Check size={13} className="mt-0.5 text-emerald-600" /> : stage.status === 'running' ? <Loader2 size={13} className="mt-0.5 animate-spin text-blue-600" /> : <Circle size={13} className="mt-0.5 text-surface-300" />}
        <span>{stage.label}{stage.used_fallback ? '（已安全使用备用方案）' : ''}</span>
      </div>)}
      {state.preview && <div className="max-h-36 overflow-auto rounded-lg bg-white p-2 text-[11px] text-surface-500"><p className="mb-1 font-medium text-surface-600">生成预览（完成校验前不会保存）</p><pre className="whitespace-pre-wrap font-sans">{state.preview}</pre></div>}
    </div>}
  </section>;
}
