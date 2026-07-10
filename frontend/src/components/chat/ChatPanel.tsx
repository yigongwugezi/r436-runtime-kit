import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatStore, detectOrphanedStreaming } from '../../store/chatStore';
import { useStreamChat } from '../../hooks/useStreamChat';
import { getSessionMessages } from '../../api/chat';
import { DEFAULT_QUICK_COMMANDS } from '../../utils/constants';
import type { ChatMessage, GenerationProgress } from '../../types/chat';
import { timeAgo } from '../../utils/format';
import { runtimeStorageKeys, writeStorageItem } from '../../utils/storageKeys';
import {
  Send, Sparkles, Square, Copy, Check, AlertCircle,
  Bot, RefreshCw, ChevronDown, XCircle, Plus, History,
  CheckCircle2, AlertTriangle, XOctagon,
} from 'lucide-react';
import Markdown from '../../utils/markdown';
import MarkmapDiagram from '../../utils/markmap';
import ChatClarification from './ChatClarification';
import PromptTemplates from './PromptTemplates';

/* ===================================================================
 * §2.5.2 Agent Status Bar
 * =================================================================== */
function AgentStatusBar({ progress }: { progress: GenerationProgress | null }) {
  if (!progress) return null;
  const { stage, agentName, done, error, progress: pct, retry, maxRetries, reason } = progress as any;

  return (
    <div className={`h-8 flex items-center gap-2 px-4 text-xs font-medium flex-shrink-0 ${
      error ? 'bg-red-50 text-red-700'
        : done ? 'bg-green-50 text-green-700'
        : 'bg-[#EEF2FF] text-[#4338CA]'
    }`}>
      {error ? (
        <XOctagon className="w-3.5 h-3.5" />
      ) : done ? (
        <CheckCircle2 className="w-3.5 h-3.5" />
      ) : retry ? (
        <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
      ) : (
        <span className="w-2 h-2 rounded-full bg-current animate-pulse" />
      )}
      <span className="truncate">
        {retry ? `⚠️ ${reason || '重试中'} (${retry}/${maxRetries})`
          : done ? '✅ 执行完成'
          : stage || '处理中…'}
      </span>
      {!done && !error && pct > 0 && (
        <span className="ml-auto tabular-nums">{Math.round(pct)}%</span>
      )}
    </div>
  );
}

/* ===================================================================
 * §2.5.3 Structured Card Renderer
 * =================================================================== */
function StructuredCard({ card }: { card: any }) {
  const nav = useNavigate();
  const ct = card?.card_type;

  if (ct === 'diagnosis_result') {
    const d = card.data || {};
    return (
      <div className="p-3 bg-white border border-gray-100 rounded-xl shadow-sm space-y-1.5">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-700">
          <StethoscopeIcon /> 诊断结果
        </div>
        <p className="text-2xs text-gray-500">{card.summary}</p>
        {d.high_count > 0 && <span className="inline-block px-1.5 py-0.5 rounded bg-red-50 text-red-600 text-2xs font-medium">{d.high_count} 个高优先级</span>}
        {d.needs_more_evidence && <span className="inline-block px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 text-2xs ml-1">需要更多证据</span>}
        <button onClick={() => nav('/diagnosis')} className="text-2xs text-brand-600 hover:underline mt-0.5 block">查看完整诊断 →</button>
      </div>
    );
  }

  if (ct === 'learning_path_preview') {
    const d = card.data || {};
    return (
      <div className="p-3 bg-white border border-gray-100 rounded-xl shadow-sm space-y-1.5">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-700">
          <RouteIcon /> 学习路径
        </div>
        <p className="text-2xs text-gray-500">{card.summary}</p>
        <p className="text-2xs text-gray-400">{d.estimated_days}天 · {d.stages?.length || 0}个阶段 · {d.review_count || 0}个复习提醒</p>
        {d.risk_flags?.length > 0 && <span className="inline-block px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 text-2xs">⚠️ {d.risk_flags.join(', ')}</span>}
        <button onClick={() => nav('/path')} className="text-2xs text-brand-600 hover:underline mt-0.5 block">查看完整路径 →</button>
      </div>
    );
  }

  if (ct === 'resources_ready') {
    const d = card.data || {};
    return (
      <div className="p-3 bg-white border border-gray-100 rounded-xl shadow-sm space-y-1.5">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-700">
          <ResourceIcon /> 资源就绪
        </div>
        <p className="text-2xs text-gray-500">{card.summary}</p>
        <div className="flex flex-wrap gap-1">
          {Object.entries(d.by_type || {}).map(([t, c]) => (
            <span key={t} className="px-1.5 py-0.5 rounded bg-gray-50 text-gray-500 text-2xs">{t}×{c as number}</span>
          ))}
        </div>
        {(d.by_quality?.warning > 0 || d.by_quality?.blocked > 0) && (
          <span className="inline-block px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 text-2xs">⚠️ {d.by_quality.warning || 0}警告 {d.by_quality.blocked || 0}阻断</span>
        )}
        <button onClick={() => nav('/resources')} className="text-2xs text-brand-600 hover:underline mt-0.5 block">查看全部资源 →</button>
      </div>
    );
  }

  if (ct === 'review_result') {
    const d = card.data || {};
    return (
      <div className="p-3 bg-white border border-gray-100 rounded-xl shadow-sm space-y-1.5">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-700">
          <ShieldIcon /> 质量审查
        </div>
        <div className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium ${
          d.quality_status === 'passed' ? 'bg-green-50 text-green-600'
            : d.quality_status === 'warning' ? 'bg-amber-50 text-amber-600'
            : 'bg-red-50 text-red-600'
        }`}>
          {d.quality_status === 'passed' ? '✅ passed' : d.quality_status === 'warning' ? '⚠️ warning' : '🚫 blocked'}
        </div>
        <p className="text-2xs text-gray-400">通过{d.passed} · 警告{d.warning} · 阻断{d.blocked}</p>
      </div>
    );
  }

  if (ct === 'grading_result') {
    const d = card.data || {};
    return (
      <div className="p-3 bg-white border border-gray-100 rounded-xl shadow-sm space-y-1.5">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-700">
          <CheckCircle2 className="w-3.5 h-3.5" /> 批改结果
        </div>
        <p className="text-sm font-bold">{d.total_score}/100</p>
        {d.error_type && d.error_type !== 'null' && (
          <span className="inline-block px-1.5 py-0.5 rounded bg-red-50 text-red-600 text-2xs">{d.error_label || d.error_type}</span>
        )}
      </div>
    );
  }

  return null;
}

/* ── Mini icons for cards ── */
function StethoscopeIcon() { return <svg className="w-3.5 h-3.5 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>; }
function RouteIcon() { return <svg className="w-3.5 h-3.5 text-blue-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="3 11 22 2 13 21 11 13 3 11"/></svg>; }
function ResourceIcon() { return <svg className="w-3.5 h-3.5 text-green-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>; }
function ShieldIcon() { return <svg className="w-3.5 h-3.5 text-purple-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>; }

/* ===================================================================
 * §2.5.6 Confirm preview UI
 * =================================================================== */
function PreviewConfirm({ previewData, onConfirm, onAdjust, onCancel }: {
  previewData: any;
  onConfirm: () => void;
  onAdjust: (msg: string) => void;
  onCancel: () => void;
}) {
  const [adjustMsg, setAdjustMsg] = useState('');
  const [showAdjust, setShowAdjust] = useState(false);

  const planner = previewData?.planner?.data || {};
  return (
    <div className="p-3 bg-white border border-brand-200 rounded-xl shadow-sm space-y-3">
      <div className="flex items-center gap-2 text-xs font-semibold text-gray-800">
        <RouteIcon /> 学习路径预览
      </div>
      <p className="text-2xs text-gray-500">{planner.estimated_days}天 · {planner.stages?.length || 0}个阶段 · {planner.review_count || 0}个复习提醒</p>
      {planner.risk_flags?.length > 0 && (
        <p className="text-2xs text-amber-600">⚠️ {planner.risk_flags.join(', ')}</p>
      )}
      {!showAdjust ? (
        <div className="flex gap-2">
          <button onClick={onConfirm} className="flex-1 py-2 rounded-lg bg-brand-500 text-white text-xs font-medium hover:bg-brand-600 transition-colors">✅ 确认方案</button>
          <button onClick={() => setShowAdjust(true)} className="flex-1 py-2 rounded-lg border border-gray-200 text-gray-600 text-xs font-medium hover:bg-gray-50 transition-colors">✏️ 调整</button>
          <button onClick={onCancel} className="px-3 py-2 rounded-lg border border-gray-200 text-gray-400 text-xs hover:text-red-500 hover:border-red-200 transition-colors">❌</button>
        </div>
      ) : (
        <div className="space-y-2">
          <textarea value={adjustMsg} onChange={e => setAdjustMsg(e.target.value)}
            placeholder="请描述你想要的调整…" rows={2}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-xs resize-none focus:ring-2 focus:ring-brand-500 outline-none"
          />
          <div className="flex gap-2">
            <button onClick={() => onAdjust(adjustMsg)} className="flex-1 py-1.5 rounded-lg bg-brand-500 text-white text-xs font-medium hover:bg-brand-600 disabled:opacity-30" disabled={!adjustMsg.trim()}>确认调整</button>
            <button onClick={() => setShowAdjust(false)} className="px-3 py-1.5 rounded-lg border border-gray-200 text-gray-500 text-xs hover:bg-gray-50">返回</button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ===================================================================
 * Quick Commands
 * =================================================================== */
function QuickCommands({ onSelect }: { onSelect: (prompt: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {DEFAULT_QUICK_COMMANDS.map((cmd) => (
        <button key={cmd.id} onClick={() => onSelect(cmd.prompt)}
          className="inline-flex items-center gap-1 px-2 py-1.5 bg-white border border-gray-200 rounded-lg text-[10px] text-gray-600 hover:border-brand-300 hover:text-brand-600 hover:bg-brand-50/50 transition-all"
        >
          <span className="text-xs">{cmd.icon}</span>
          <span>{cmd.label}</span>
        </button>
      ))}
    </div>
  );
}

/* ===================================================================
 * Message bubble
 * =================================================================== */
function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';
  const [copied, setCopied] = useState(false);

  return (
    <div className={`flex gap-2 ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in-up group`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center flex-shrink-0 shadow-sm">
          <Sparkles className="w-3.5 h-3.5 text-white" />
        </div>
      )}
      <div className={`flex flex-col gap-0.5 ${isUser ? 'items-end' : 'items-start'} max-w-[85%]`}>
        <div className={`rounded-2xl px-3 py-2 text-xs leading-relaxed ${
          isUser ? 'bg-gray-900 text-white rounded-br-md' : 'bg-white border border-gray-100 shadow-sm rounded-bl-md'
        }`}>
          {isUser ? <p className="whitespace-pre-wrap">{msg.content}</p> : (
            <div className="text-gray-800 [&_p]:mb-1 [&_ul]:pl-3 [&_ol]:pl-3 [&_li]:mb-0.5 [&_h1]:text-sm [&_h2]:text-sm [&_h3]:text-xs [&_pre]:text-[10px] [&_code]:text-[10px]">
              {msg.content ? <Markdown content={msg.content} /> : msg.streaming ? <span className="text-gray-400 italic">思考中…</span> : null}
              {msg.streaming && msg.content && <span className="inline-block w-1 h-3 bg-brand-500 animate-pulse rounded ml-0.5 align-text-bottom" />}
            </div>
          )}
          {!isUser && msg.content && !msg.streaming && (
            <button onClick={() => { navigator.clipboard.writeText(msg.content); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
              className="absolute -bottom-0.5 right-1.5 translate-y-full opacity-0 group-hover:opacity-100 transition-opacity p-0.5 bg-white border border-gray-200 rounded-md hover:bg-gray-50 shadow-sm">
              {copied ? <Check className="w-2.5 h-2.5 text-green-500" /> : <Copy className="w-2.5 h-2.5 text-gray-400" />}
            </button>
          )}
        </div>
        {/* §2.5.3 Structured cards rendered below AI message */}
        {(msg as any).cards?.length > 0 && (
          <div className="space-y-2 mt-1 w-full">
            {(msg as any).cards.map((card: any, i: number) => (
              <StructuredCard key={i} card={card} />
            ))}
          </div>
        )}
        <span className="text-[9px] text-gray-300 px-1 flex items-center gap-1">
          {timeAgo(msg.timestamp)}
          {!isUser && !msg.streaming && msg.content && !msg.error && <span className="w-1 h-1 rounded-full bg-green-300" />}
          {!isUser && msg.streaming && <span className="w-1 h-1 rounded-full bg-brand-400 animate-pulse" />}
        </span>
      </div>
    </div>
  );
}

/* ===================================================================
 * ChatPanel — §2.5 Right chat area, always visible on desktop
 * =================================================================== */
export default function ChatPanel({ embedded = false, open, onClose, panelWidth, onWidthChange }: {
  embedded?: boolean;
  open?: boolean;
  onClose?: () => void;
  panelWidth?: number;
  onWidthChange?: (w: number) => void;
}) {
  const navigate = useNavigate();
  const { messages, isStreaming, agentProgress, currentSessionId } = useChatStore() as {
    messages: ChatMessage[];
    isStreaming: boolean;
    agentProgress: GenerationProgress | null;
    currentSessionId: string;
  };
  const { send, abort } = useStreamChat();
  const [input, setInput] = useState('');
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [previewState, setPreviewState] = useState<any>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);

  const scrollToBottom = useCallback((force = false) => {
    if (force) userScrolledUpRef.current = false;
    if (force || !userScrolledUpRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, []);

  useEffect(() => { if (!userScrolledUpRef.current) scrollToBottom(); }, [messages, agentProgress, scrollToBottom]);

  useEffect(() => {
    const el = scrollRef.current; if (!el) return;
    const handler = () => {
      const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (dist <= 60) userScrolledUpRef.current = false;
      else userScrolledUpRef.current = true;
      setShowScrollBtn(dist > 80 && messages.length > 0);
    };
    el.addEventListener('scroll', handler, { passive: true });
    return () => el.removeEventListener('scroll', handler);
  });

  // Recovery
  useEffect(() => {
    const orphanId = detectOrphanedStreaming();
    if (!orphanId) return;
    writeStorageItem(runtimeStorageKeys.pendingGeneration, '');
    useChatStore.getState().setAgentProgress(null);
  }, []);

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    setPreviewState(null);
    send(input.trim());
    setInput('');
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleRetry = () => {
    const lastUser = [...messages].reverse().find(m => m.role === 'user');
    if (lastUser) send(lastUser.content);
  };

  const handleConfirm = async () => {
    if (!previewState?.session_id) return;
    setPreviewState(null);
    try {
      const { streamRequest } = await import('../../api/client');
      const reader = await streamRequest('/api/chat/confirm', { sessionId: previewState.session_id, action: 'confirm' }, new AbortController().signal);
      useChatStore.getState().setStreaming(true);
      const decoder = new TextDecoder(); let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n'); buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const evt = JSON.parse(line.slice(6));
              if (evt.type === 'agent_progress') {
                useChatStore.getState().setAgentProgress({ stage: `${evt.agent_name}: ${evt.label}`, progress: evt.status === 'completed' ? 100 : 50, agentName: evt.node, done: false });
              } else if (evt.type === 'final_reply') {
                useChatStore.getState().addMessage({ id: `ai_${Date.now()}`, role: 'assistant', content: evt.content || '', timestamp: Date.now(), streaming: false });
              } else if (evt.type === 'done') {
                useChatStore.getState().setStreaming(false);
                useChatStore.getState().setAgentProgress(null);
              }
            } catch { /* non-JSON line */ }
          }
        }
      }
    } catch { useChatStore.getState().setStreaming(false); }
  };

  const handleAdjust = async (msg: string) => {
    if (!previewState?.session_id) return;
    setPreviewState(null);
    try {
      const { streamRequest } = await import('../../api/client');
      const reader = await streamRequest('/api/chat/confirm', { sessionId: previewState.session_id, action: 'adjust', message: msg }, new AbortController().signal);
      useChatStore.getState().setStreaming(true);
      const decoder = new TextDecoder(); let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n'); buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const evt = JSON.parse(line.slice(6));
              if (evt.type === 'agent_progress') {
                useChatStore.getState().setAgentProgress({ stage: `${evt.agent_name}: ${evt.label}`, progress: 50, agentName: evt.node, done: false });
              } else if (evt.type === 'final_reply') {
                useChatStore.getState().addMessage({ id: `ai_${Date.now()}`, role: 'assistant', content: evt.content || '', timestamp: Date.now(), streaming: false });
              } else if (evt.type === 'done') {
                useChatStore.getState().setStreaming(false);
                useChatStore.getState().setAgentProgress(null);
              }
            } catch { /* skip */ }
          }
        }
      }
    } catch { useChatStore.getState().setStreaming(false); }
  };

  const handleCancelPreview = () => setPreviewState(null);

  // Detect preview events from stream (set by useStreamChat)
  useEffect(() => {
    const unsub = useChatStore.subscribe((state, prev) => {
      if ((state as any)._previewState && !(prev as any)._previewState) {
        setPreviewState((state as any)._previewState);
      }
    });
    return unsub;
  }, []);

  const content = (
    <div className={`h-full bg-[#FAFBFC] border-l border-[#E2E8F0] flex flex-col ${embedded ? '' : 'fixed inset-y-0 right-0 z-40 shadow-2xl'}`}
      style={!embedded ? { width: panelWidth || 400 } : undefined}>
      {/* §2.5.1 Header */}
      <div className="h-14 flex items-center justify-between px-4 border-b border-[#E2E8F0] flex-shrink-0 bg-white">
        <span className="text-base font-semibold text-[#1A1A2E]">EduAgent 学习助手</span>
        {!embedded && onClose && (
          <button onClick={onClose} className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
            <XCircle className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* §2.5.2 Agent Status Bar */}
      <AgentStatusBar progress={agentProgress} />

      {/* §2.5.3 Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-full text-center px-2">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-brand-100 to-brand-200 flex items-center justify-center mb-4 shadow-sm">
              <Bot className="w-7 h-7 text-brand-600" />
            </div>
            <h3 className="text-sm font-bold text-gray-800 mb-1">开始对话</h3>
            <p className="text-[11px] text-gray-400 mb-4">告诉我你想学什么，9 个 AI 智能体为你服务</p>
            <QuickCommands onSelect={(prompt) => { setInput(prompt); inputRef.current?.focus(); }} />
          </div>
        )}

        {messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}

        {/* Preview confirm */}
        {previewState && (
          <PreviewConfirm previewData={previewState} onConfirm={handleConfirm} onAdjust={handleAdjust} onCancel={handleCancelPreview} />
        )}

        {isStreaming && !agentProgress && (
          <div className="px-3 py-2 bg-white border border-gray-100 rounded-xl flex items-center gap-2">
            <div className="w-4 h-4 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
            <span className="text-xs text-gray-500">正在分析你的需求…</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {showScrollBtn && (
        <button onClick={() => scrollToBottom(true)} className="absolute bottom-20 left-1/2 -translate-x-1/2 w-7 h-7 bg-white border border-gray-200 rounded-full flex items-center justify-center shadow-md">
          <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
        </button>
      )}

      {/* §2.5.4 Context bar + §2.5.5 Quick commands */}
      {/* §2.5.6 Input */}
      <div className="border-t border-[#E2E8F0] bg-white px-3 py-3 flex-shrink-0">
        {messages.length > 0 && !isStreaming && (
          <PromptTemplates onSelect={(prompt) => { setInput(prompt); inputRef.current?.focus(); }} />
        )}
        <div className="flex items-end gap-2">
          <button className="w-5 h-5 text-[#94A3B8] hover:text-brand-600 flex-shrink-0 mb-1.5">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
          </button>
          <textarea ref={inputRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown}
            data-chat-input
            placeholder={isStreaming ? '正在生成中…' : '输入问题，或选中文档内容进行提问…'}
            rows={1} disabled={isStreaming}
            className="flex-1 resize-none bg-white border border-[#E2E8F0] rounded-[10px] px-3 py-2 text-sm outline-none focus:ring-[3px] focus:ring-brand-500/10 focus:border-brand-500 disabled:opacity-50 transition-all max-h-[120px]"
          />
          {isStreaming ? (
            <button onClick={abort} className="w-10 h-10 rounded-full bg-red-500 text-white flex items-center justify-center hover:bg-red-600 flex-shrink-0"><Square className="w-4 h-4" /></button>
          ) : (
            <button onClick={handleSend} disabled={!input.trim()}
              className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-all bg-[#CBD5E1] text-white enabled:bg-[#6366F1] enabled:hover:bg-[#4F46E5] enabled:active:bg-[#4338CA] disabled:cursor-not-allowed">
              <Send className="w-4 h-4" />
            </button>
          )}
        </div>
        <p className="mt-1.5 text-[9px] text-[#94A3B8] text-right">系统可能生成不准确内容，请查阅教材确认</p>
      </div>
    </div>
  );

  if (embedded) return content;
  return <>{open && content}</>;
}
