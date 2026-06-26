import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatStore } from '../../store/chatStore';
import { useStreamChat } from '../../hooks/useStreamChat';
import { getSessionMessages } from '../../api/chat';
import { DEFAULT_QUICK_COMMANDS } from '../../utils/constants';
import type { ChatMessage, GenerationProgress } from '../../types/chat';
import { timeAgo } from '../../utils/format';
import {
  Send, Sparkles, Square, Copy, Check, AlertCircle,
  Bot, User, RefreshCw, ChevronDown, XCircle, PanelRightClose, PanelRightOpen,
} from 'lucide-react';
import Markdown from '../../utils/markdown';
import ChatClarification from './ChatClarification';
import PromptTemplates from './PromptTemplates';

/* ===================================================================
 * 生成流程管线定义
 * =================================================================== */
const GEN_PIPELINE: { key: string; label: string }[] = [
  { key: 'understanding', label: '理解需求' },
  { key: 'profiling',     label: '生成画像' },
  { key: 'planning',      label: '规划路径' },
  { key: 'generating',    label: '生成资源' },
  { key: 'saving',        label: '保存结果' },
];

/* ===================================================================
 * 消息气泡
 * =================================================================== */
function MessageBubble({ msg, onClarificationSelect }: { msg: ChatMessage; onClarificationSelect?: (prompt: string) => void }) {
  const isUser = msg.role === 'user';
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className={`flex gap-2 ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in-up group`}>
      {!isUser ? (
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center flex-shrink-0 shadow-sm">
          <Sparkles className="w-3.5 h-3.5 text-white" />
        </div>
      ) : null}

      <div className={`flex flex-col gap-0.5 ${isUser ? 'items-end' : 'items-start'} max-w-[88%]`}>
        <div
          className={`rounded-2xl px-3 py-2 text-xs leading-relaxed ${
            isUser
              ? 'bg-gray-900 text-white rounded-br-md'
              : 'bg-white border border-gray-100 shadow-sm rounded-bl-md'
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{msg.content}</p>
          ) : (
            <div className="text-gray-800 [&_p]:mb-1 [&_ul]:pl-3 [&_ol]:pl-3 [&_li]:mb-0.5 [&_h1]:text-sm [&_h2]:text-sm [&_h3]:text-xs [&_pre]:text-[10px] [&_code]:text-[10px]">
              {msg.content ? (
                <Markdown content={msg.content} />
              ) : msg.streaming ? (
                <span className="text-gray-400 italic">思考中…</span>
              ) : null}
              {msg.streaming && msg.content && (
                <span className="inline-block w-1 h-3 bg-brand-500 animate-pulse rounded ml-0.5 align-text-bottom" />
              )}
              {msg.error && (
                <div className="mt-1.5 p-2 bg-red-50 border border-red-100 rounded-lg flex items-start gap-1.5">
                  <AlertCircle className="w-3 h-3 text-red-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-[10px] text-red-600 font-medium">生成失败</p>
                    <p className="text-[10px] text-red-400 mt-0.5">{msg.error}</p>
                  </div>
                </div>
              )}
              {msg.isClarification && onClarificationSelect && (
                <ChatClarification onSelect={onClarificationSelect} />
              )}
            </div>
          )}

          {!isUser && msg.content && !msg.streaming && (
            <button
              onClick={handleCopy}
              className="absolute -bottom-0.5 right-1.5 translate-y-full opacity-0 group-hover:opacity-100 transition-opacity p-0.5 bg-white border border-gray-200 rounded-md hover:bg-gray-50 shadow-sm"
              title="复制"
            >
              {copied ? <Check className="w-2.5 h-2.5 text-green-500" /> : <Copy className="w-2.5 h-2.5 text-gray-400" />}
            </button>
          )}
        </div>

        <span className="text-[9px] text-gray-300 px-1 flex items-center gap-1">
          {timeAgo(msg.timestamp)}
          {!isUser && !msg.streaming && msg.content && !msg.error && !msg.isClarification && (
            <span className="w-1 h-1 rounded-full bg-green-300" />
          )}
          {!isUser && msg.streaming && (
            <span className="w-1 h-1 rounded-full bg-brand-400 animate-pulse" />
          )}
          {msg.error && (
            <span className="w-1 h-1 rounded-full bg-red-400" />
          )}
        </span>
      </div>
    </div>
  );
}

/* ===================================================================
 * 生成进度管线
 * =================================================================== */
function AgentPipelineProgress({
  progress,
  onRetry,
  onNavigate,
}: {
  progress: GenerationProgress;
  onRetry?: () => void;
  onNavigate?: (path: string) => void;
}) {
  const [elapsed, setElapsed] = useState(0);
  const currentKey = progress.agentName || '';
  const currentIdx = GEN_PIPELINE.findIndex((s) => s.key === currentKey);
  const isError = !!progress.error;
  const [doneVisible, setDoneVisible] = useState(false);
  const isDone = progress.done && !progress.error;

  // 完成时延迟 1.5 秒再显示跳转按钮，避免闪烁
  useEffect(() => {
    if (isDone) {
      const t = setTimeout(() => setDoneVisible(true), 1500);
      return () => clearTimeout(t);
    }
    setDoneVisible(false);
  }, [isDone]);

  useEffect(() => {
    if (isDone || isError) return;
    const t = setInterval(() => setElapsed((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, [isDone, isError]);

  const longWait = elapsed >= 15;

  if (isError) {
    return (
      <div className="px-3 py-3 bg-red-50 border border-red-100 rounded-xl space-y-2">
        <div className="flex items-start gap-2">
          <div className="w-5 h-5 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
            <XCircle className="w-3 h-3 text-red-500" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-red-700">生成失败</p>
            <p className="text-[10px] text-red-500 mt-0.5">{progress.error || '后端处理出错，请稍后重试'}</p>
            {onRetry && (
              <button onClick={onRetry} className="mt-2 inline-flex items-center gap-1 px-2.5 py-1 bg-red-100 hover:bg-red-200 rounded-lg text-[10px] font-medium text-red-700 transition-colors">
                <RefreshCw className="w-3 h-3" />重新生成
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (isDone) {
    return (
      <div className="px-3 py-3 bg-green-50/60 border border-green-100 rounded-xl space-y-2">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-full bg-green-100 flex items-center justify-center flex-shrink-0">
            <Check className="w-3 h-3 text-green-600" />
          </div>
          <span className="text-xs font-semibold text-green-700">生成完成</span>
          {!doneVisible && <span className="text-[10px] text-green-500 animate-pulse">处理中…</span>}
        </div>
        {onNavigate && doneVisible && (
          <div className="flex flex-wrap gap-1.5 animate-fade-in-up">
            <button onClick={() => onNavigate('/profile')} className="inline-flex items-center gap-1 px-2 py-1 bg-white border border-green-200 rounded-lg text-[10px] font-medium text-green-700 hover:bg-green-50 transition-colors">📋 画像</button>
            <button onClick={() => onNavigate('/path')} className="inline-flex items-center gap-1 px-2 py-1 bg-white border border-green-200 rounded-lg text-[10px] font-medium text-green-700 hover:bg-green-50 transition-colors">🗺️ 路径</button>
            <button onClick={() => onNavigate('/resources')} className="inline-flex items-center gap-1 px-2 py-1 bg-white border border-green-200 rounded-lg text-[10px] font-medium text-green-700 hover:bg-green-50 transition-colors">📚 资源</button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="px-3 py-3 bg-white border border-gray-100 rounded-xl space-y-2">
      <div className="flex items-center gap-2">
        <div className="w-4 h-4 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
        <span className="text-xs font-semibold text-gray-800">{progress.stage || '正在处理中…'}</span>
        <span className="text-[10px] text-brand-500 font-medium ml-auto">{progress.progress}%</span>
      </div>

      <div className="flex items-center gap-0.5">
        {GEN_PIPELINE.map((step, idx) => {
          const isCompleted = idx < currentIdx;
          const isCurrent = idx === currentIdx;
          const isPending = idx > currentIdx;
          return (
            <div key={step.key} className="flex items-center gap-0.5 flex-1 min-w-0">
              <div className={`w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0 ${isCompleted ? 'bg-green-100' : isCurrent ? 'bg-brand-100' : 'bg-gray-50'}`}>
                {isCompleted ? <Check className="w-2 h-2 text-green-600" /> : isCurrent ? <div className="w-2 h-2 rounded-full bg-brand-500 animate-pulse" /> : <div className="w-1.5 h-1.5 rounded-full bg-gray-300" />}
              </div>
              {idx < GEN_PIPELINE.length - 1 && (
                <div className={`flex-1 h-0.5 rounded-full ${isCompleted ? 'bg-green-300' : isCurrent ? 'bg-gray-200' : 'bg-gray-100'}`} />
              )}
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between">
        {GEN_PIPELINE.map((step, idx) => {
          const isCurrent = idx === currentIdx;
          const isCompleted = idx < currentIdx;
          return (
            <span key={step.key} className={`text-[8px] ${isCurrent ? 'text-brand-600 font-semibold' : isCompleted ? 'text-green-500' : 'text-gray-300'}`}>{step.label}</span>
          );
        })}
      </div>

      <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
        <div className="h-full bg-gradient-to-r from-brand-500 to-brand-600 rounded-full transition-all duration-700 ease-out" style={{ width: `${progress.progress}%` }} />
      </div>

      {longWait && (
        <div className="flex items-center gap-1.5 p-1.5 bg-amber-50 border border-amber-100 rounded-lg">
          <span className="text-amber-500 text-[10px]">⏳</span>
          <p className="text-[9px] text-amber-600">已持续 {elapsed} 秒，多智能体协同请耐心等待…</p>
        </div>
      )}
    </div>
  );
}

/* ===================================================================
 * 快捷指令
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
 * 等待指示器
 * =================================================================== */
function StreamingWaitIndicator() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setElapsed((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="px-3 py-2 bg-white border border-gray-100 rounded-xl">
      <div className="flex items-center gap-2">
        <div className="w-4 h-4 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
        <span className="text-xs text-gray-500">AI 正在分析你的需求…</span>
        {elapsed >= 8 && <p className="text-[9px] text-amber-500">已等待 {elapsed} 秒</p>}
      </div>
    </div>
  );
}

/* ===================================================================
 * ChatPanel — 内嵌于布局右侧的持久化对话面板
 * =================================================================== */
type AgentProgressInfo = GenerationProgress | null;

const MIN_PANEL_WIDTH = 320;
const MAX_PANEL_WIDTH = 640;

export default function ChatPanel({ open, onClose, panelWidth = 420, onWidthChange }: {
  open: boolean;
  onClose: () => void;
  panelWidth?: number;
  onWidthChange?: (w: number) => void;
}) {
  const navigate = useNavigate();
  const { messages, isStreaming, agentProgress, currentSessionId, sessions, setCurrentSession, newSession } = useChatStore() as {
    messages: ChatMessage[];
    isStreaming: boolean;
    agentProgress: AgentProgressInfo;
    currentSessionId: string;
    sessions: any[];
    setCurrentSession: (id: string) => void;
    newSession: () => void;
  };
  const { send, abort } = useStreamChat();
  const [input, setInput] = useState('');
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);

  // 拖拽调整宽度
  useEffect(() => {
    if (!dragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      if (!onWidthChange) return;
      const newWidth = Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, window.innerWidth - e.clientX));
      onWidthChange(newWidth);
    };
    const handleMouseUp = () => setDragging(false);
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [dragging, onWidthChange]);

  // 阻止拖拽时选中文字
  useEffect(() => {
    if (dragging) {
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'col-resize';
    } else {
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    }
  }, [dragging]);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, agentProgress, scrollToBottom]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const handler = () => {
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      setShowScrollBtn(!atBottom && messages.length > 0);
    };
    el.addEventListener('scroll', handler);
    return () => el.removeEventListener('scroll', handler);
  });

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    send(input.trim());
    setInput('');
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleRetry = () => {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
    if (lastUser) send(lastUser.content);
  };

  const handleNavigate = (path: string) => {
    navigate(path);
    onClose();
  };

  const hasError = messages.some((m) => m.error);

  return (
    <>
      {/* 遮罩 - 移动端 */}
      {open && (
        <div className="fixed inset-0 z-40 bg-black/30 md:hidden" onClick={onClose} />
      )}

      {/* 面板 — fixed 固定，不随页面滚动 */}
      <div
        className={`fixed inset-y-0 right-0 z-40 w-full bg-gray-50 border-l border-gray-200 flex flex-col transition-transform duration-300 ease-in-out ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
        style={{ width: panelWidth }}
      >
        {/* 拖拽调整宽度的把手 */}
        <div
          ref={dragRef}
          onMouseDown={() => setDragging(true)}
          className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-brand-400/30 active:bg-brand-400/50 transition-colors z-10 hidden md:block"
          title="拖拽调整宽度"
        />

        {/* 面板头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white flex-shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-sm flex-shrink-0">
              <Bot className="w-3.5 h-3.5 text-white" />
            </div>

            {/* 当前会话标题 / 历史记录切换 */}
            <div className="relative">
              <button
                onClick={() => setHistoryOpen(!historyOpen)}
                className="flex items-center gap-1 text-sm font-semibold text-gray-800 hover:text-brand-600 transition-colors"
              >
                <span className="truncate max-w-[120px]">
                  {sessions.find(s => s.id === currentSessionId)?.title || 'AI 对话'}
                </span>
                <svg className={`w-3 h-3 text-gray-400 transition-transform ${historyOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
              </button>

              {/* 历史会话下拉 */}
              {historyOpen && (
                <div className="absolute top-full left-0 mt-1 w-56 bg-white border border-gray-200 rounded-xl shadow-xl z-50 max-h-60 overflow-y-auto py-1">
                  {sessions.length === 0 ? (
                    <p className="px-3 py-2 text-xs text-gray-400">暂无历史对话</p>
                  ) : (
                    sessions.map((ses) => {
                      const active = ses.id === currentSessionId;
                      return (
                        <button
                          key={ses.id}
                          onClick={() => { setCurrentSession(ses.id); setHistoryOpen(false); }}
                          className={`w-full text-left px-3 py-2 text-xs transition-colors ${active ? 'bg-brand-50 text-brand-700 font-semibold' : 'text-gray-600 hover:bg-gray-50'}`}
                        >
                          <span className="truncate block">{ses.title || '新对话'}</span>
                          <span className="text-[9px] text-gray-400">{new Date(ses.updatedAt || ses.createdAt).toLocaleDateString('zh-CN')}</span>
                        </button>
                      );
                    })
                  )}
                  <div className="border-t border-gray-100 mt-1 pt-1">
                    <button
                      onClick={() => { newSession(); setHistoryOpen(false); }}
                      className="w-full text-left px-3 py-2 text-xs text-brand-600 hover:bg-brand-50 font-medium"
                    >
                      + 新建对话
                    </button>
                  </div>
                </div>
              )}
            </div>

            {isStreaming && (
              <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-pulse flex-shrink-0" title="生成中" />
            )}
          </div>
          <button onClick={onClose}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all flex-shrink-0"
            title="关闭对话面板" aria-label="关闭对话面板">
            <PanelRightClose className="w-4 h-4" />
          </button>
        </div>

        {/* 错误横幅 */}
        {hasError && (
          <div className="flex items-center justify-between px-3 py-1.5 bg-red-50 border-b border-red-100 flex-shrink-0">
            <span className="text-[10px] text-red-600 flex items-center gap-1">
              <AlertCircle className="w-3 h-3" />最近一次生成出现问题
            </span>
            <button onClick={handleRetry} className="flex items-center gap-1 px-2 py-0.5 bg-red-100 hover:bg-red-200 rounded-lg text-[10px] text-red-600 font-medium transition-colors">
              <RefreshCw className="w-2.5 h-2.5" />重试
            </button>
          </div>
        )}

        {/* 消息区域 */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-4 space-y-3 scroll-smooth">
          {/* 空状态 */}
          {messages.length === 0 && !isStreaming && (
            <div className="flex flex-col items-center justify-center h-full text-center px-2">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-brand-100 to-brand-200 flex items-center justify-center mb-4 shadow-sm">
                <Bot className="w-7 h-7 text-brand-600" />
              </div>
              <h3 className="text-sm font-bold text-gray-800 mb-1">开始对话</h3>
              <p className="text-[11px] text-gray-400 mb-4">告诉系统你的专业、基础和目标</p>
              <QuickCommands onSelect={(prompt) => { setInput(prompt); inputRef.current?.focus(); }} />
            </div>
          )}

          {messages.map((msg, idx) => (
            <MessageBubble key={msg.id} msg={msg} onClarificationSelect={send} />
          ))}

          {agentProgress && (
            <AgentPipelineProgress progress={agentProgress} onRetry={handleRetry} onNavigate={handleNavigate} />
          )}

          {isStreaming && !agentProgress && <StreamingWaitIndicator />}

          <div ref={bottomRef} />
        </div>

        {/* 滚到底部按钮 */}
        {showScrollBtn && (
          <button onClick={() => scrollToBottom()}
            className="absolute bottom-20 left-1/2 -translate-x-1/2 w-7 h-7 bg-white border border-gray-200 rounded-full flex items-center justify-center shadow-md hover:shadow-lg transition-all z-10"
            title="滚动到底部">
            <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
          </button>
        )}

        {/* 输入区域 */}
        <div className="border-t border-gray-200 bg-white px-3 py-2.5 flex-shrink-0">
          {messages.length > 0 && !isStreaming && (
            <PromptTemplates onSelect={(prompt) => { setInput(prompt); inputRef.current?.focus(); }} />
          )}
          <div className="flex items-end gap-1.5 mt-1">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isStreaming ? '正在生成中…' : '输入你的问题…'}
              rows={1}
              disabled={isStreaming}
              className="flex-1 resize-none bg-gray-50 border border-gray-200 rounded-xl px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed transition-all max-h-24"
            />
            {isStreaming ? (
              <button onClick={abort}
                className="w-8 h-8 bg-red-500 text-white rounded-lg flex items-center justify-center hover:bg-red-600 transition-all flex-shrink-0 shadow-sm"
                title="停止生成">
                <Square className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button onClick={handleSend} disabled={!input.trim()}
                className="w-8 h-8 bg-gray-900 text-white rounded-lg flex items-center justify-center hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed transition-all flex-shrink-0 shadow-sm"
                title="发送">
                <Send className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <div className="mt-1 text-[9px] text-gray-400 text-right">系统可能生成不准确内容，请查阅教材确认</div>
        </div>
      </div>
    </>
  );
}
