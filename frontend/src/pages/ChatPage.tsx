import { useState, useRef, useEffect, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { useChatStore } from '../store/chatStore';
import { useStreamChat } from '../hooks/useStreamChat';
import { getSessionMessages } from '../api/chat';
import { DEFAULT_QUICK_COMMANDS } from '../utils/constants';
import type { ChatMessage, GenerationProgress } from '../types/chat';
import { timeAgo } from '../utils/format';
import {
  Send, Sparkles, Square, Copy, Check, AlertCircle,
  Bot, User, RefreshCw, ChevronDown, XCircle,
} from 'lucide-react';
import Markdown from '../utils/markdown';

/* ===================================================================
 * 多智能体管线定义
 * =================================================================== */
const AGENT_PIPELINE: { agentName: string; label: string; description: string }[] = [
  { agentName: 'ProfileAgent',   label: '画像分析',   description: '正在提取学习画像…' },
  { agentName: 'KnowledgeAgent', label: '知识检索',   description: '正在检索课程知识库…' },
  { agentName: 'DiagnosisAgent', label: '诊断分析',   description: '正在诊断知识短板…' },
  { agentName: 'PlannerAgent',   label: '路径规划',   description: '正在生成学习路径…' },
  { agentName: 'ResourceAgent',  label: '资源生成',   description: '正在生成学习资源…' },
  { agentName: 'ReviewAgent',    label: '质量检查',   description: '正在校验内容质量…' },
];

/* ===================================================================
 * 消息气泡 — 优化版
 * =================================================================== */
function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in-up group`}>
      {/* 头像 */}
      {!isUser ? (
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center flex-shrink-0 shadow-md shadow-brand-200">
          <Sparkles className="w-4.5 h-4.5 text-white" />
        </div>
      ) : (
        <div className="w-9 h-9 rounded-xl bg-gray-700 flex items-center justify-center flex-shrink-0 text-xs font-bold text-white order-10">
          <User className="w-4 h-4" />
        </div>
      )}

      <div className={`flex flex-col gap-1 ${isUser ? 'items-end' : 'items-start'} max-w-[82%]`}>
        {/* 气泡 */}
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed relative ${
            isUser
              ? 'bg-gray-900 text-white rounded-br-md'
              : 'bg-white border border-gray-100 shadow-sm rounded-bl-md'
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{msg.content}</p>
          ) : (
            <div className="text-gray-800">
              {msg.content ? (
                <Markdown content={msg.content} />
              ) : msg.streaming ? (
                <span className="text-gray-400 italic">思考中…</span>
              ) : null}
              {/* 流式光标 */}
              {msg.streaming && msg.content && (
                <span className="inline-block w-1.5 h-4 bg-brand-500 animate-pulse rounded ml-0.5 align-text-bottom" />
              )}
              {/* 错误信息 */}
              {msg.error && (
                <div className="mt-2 p-2.5 bg-red-50 border border-red-100 rounded-xl flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs text-red-600 font-medium">生成失败</p>
                    <p className="text-xs text-red-400 mt-0.5">{msg.error}</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 复制按钮 (AI消息 hover 时显示) */}
          {!isUser && msg.content && !msg.streaming && (
            <button
              onClick={handleCopy}
              className="absolute -bottom-1 right-2 translate-y-full opacity-0 group-hover:opacity-100 transition-opacity p-1 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 shadow-sm"
              title="复制"
            >
              {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3 text-gray-400" />}
            </button>
          )}
        </div>

        {/* 时间戳 */}
        <span className="text-[10px] text-gray-300 px-1">
          {timeAgo(msg.timestamp)}
        </span>
      </div>

      {/* 头像占位 (user 的反侧) */}
      {isUser ? (
        <div className="w-9 h-9 flex-shrink-0 order-0" />
      ) : (
        <div className="w-9 h-9 flex-shrink-0" />
      )}
    </div>
  );
}

/* ===================================================================
 * 多智能体进度管线 — 赛级展示
 * =================================================================== */
function AgentPipelineProgress({ progress }: { progress: GenerationProgress }) {
  const currentIdx = AGENT_PIPELINE.findIndex((a) => a.agentName === progress.agentName);
  const pct = progress.progress;

  return (
    <div className="px-4 py-4 bg-white border border-gray-100 rounded-2xl shadow-sm animate-fade-in-up space-y-3 max-w-[82%] ml-12">
      {/* 标题 */}
      <div className="flex items-center gap-2.5">
        <div className="w-5 h-5 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
        <span className="text-sm font-semibold text-gray-800">
          {progress.stage || '多智能体正在协同工作'}
        </span>
        <span className="text-xs text-brand-500 font-medium ml-auto">{pct}%</span>
      </div>

      {/* 管线步骤 */}
      <div className="flex items-center gap-1">
        {AGENT_PIPELINE.map((agent, idx) => {
          const isCompleted = idx < currentIdx;
          const isCurrent = idx === currentIdx;
          const isPending = idx > currentIdx;

          return (
            <div key={agent.agentName} className="flex items-center gap-1 flex-1 min-w-0">
              {/* 步骤圆点 */}
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-300 ${
                  isCompleted
                    ? 'bg-green-100 ring-2 ring-green-200'
                    : isCurrent
                      ? 'bg-brand-100 ring-2 ring-brand-300'
                      : 'bg-gray-50 ring-2 ring-gray-100'
                }`}
                title={agent.description}
              >
                {isCompleted ? (
                  <Check className="w-3 h-3 text-green-600" />
                ) : isCurrent ? (
                  <div className="w-2.5 h-2.5 rounded-full bg-brand-500 animate-pulse" />
                ) : (
                  <div className="w-2 h-2 rounded-full bg-gray-300" />
                )}
              </div>
              {/* 连接线 */}
              {idx < AGENT_PIPELINE.length - 1 && (
                <div
                  className={`flex-1 h-0.5 rounded-full transition-colors duration-300 ${
                    isCompleted ? 'bg-green-300' : isCurrent ? 'bg-gray-200' : 'bg-gray-100'
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* 标签 */}
      <div className="flex items-center justify-between">
        {AGENT_PIPELINE.map((agent, idx) => {
          const isCurrent = idx === currentIdx;
          const isCompleted = idx < currentIdx;
          return (
            <span
              key={agent.agentName}
              className={`text-[9px] transition-colors duration-300 ${
                isCurrent ? 'text-brand-600 font-semibold' : isCompleted ? 'text-green-500' : 'text-gray-300'
              }`}
            >
              {agent.label}
            </span>
          );
        })}
      </div>

      {/* 进度条 */}
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-brand-500 to-brand-600 rounded-full transition-all duration-700 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/* ===================================================================
 * 快捷指令
 * =================================================================== */
function QuickCommands({ onSelect }: { onSelect: (prompt: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2 px-1">
      {DEFAULT_QUICK_COMMANDS.map((cmd) => (
        <button
          key={cmd.id}
          onClick={() => onSelect(cmd.prompt)}
          className="inline-flex items-center gap-1.5 px-3 py-2 bg-white border border-gray-200 rounded-xl text-xs text-gray-600 hover:border-brand-300 hover:text-brand-600 hover:bg-brand-50/50 transition-all hover:-translate-y-0.5"
        >
          <span className="text-sm">{cmd.icon}</span>
          <span>{cmd.label}</span>
        </button>
      ))}
    </div>
  );
}

/* ===================================================================
 * 主页面 — 优化版
 * =================================================================== */

type AgentProgressInfo = GenerationProgress | null;

export default function ChatPage() {
  const location = useLocation();
  const initialMessage = (location.state as { initialMessage?: string })?.initialMessage;
  const { messages, isStreaming, agentProgress } = useChatStore() as {
    messages: ChatMessage[];
    isStreaming: boolean;
    agentProgress: AgentProgressInfo;
  };
  const { send, abort } = useStreamChat();
  const [input, setInput] = useState('');
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  const scrollToBottom = useCallback((smooth = false) => {
    if (smooth) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    } else {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, agentProgress, scrollToBottom]);

  // 检测是否在底部，控制"滚到底部"按钮
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const handler = () => {
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
      setShowScrollBtn(!atBottom && messages.length > 0);
    };
    el.addEventListener('scroll', handler);
    return () => el.removeEventListener('scroll', handler);
  }, [messages]);

  // 挂载时从后端恢复已有消息（页面刷新后保留对话）
  useEffect(() => {
    let cancelled = false;
    async function restore() {
      setLoading(true);
      try {
        const res = await getSessionMessages(currentSessionId);
        if (cancelled) return;
        if (res.messages && res.messages.length > 0) {
          useChatStore.setState((s) => {
            // 避免重复加载（流式消息可能已在此 session 中）
            if (s.messages.length > 0) return {};
            return { messages: res.messages };
          });
        }
      } catch {
        // 新 session 或网络错误，静默处理
      } finally {
        if (!cancelled) {
          setMessagesLoaded(true);
          setLoading(false);
        }
      }
    }
    restore();
    return () => { cancelled = true; };
  }, [currentSessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  // 从 Home 页跳转来的初始消息（仅在无历史消息时触发）
  useEffect(() => {
    if (initialMessage && messages.length === 0 && messagesLoaded) {
      send(initialMessage);
    }
  }, [initialMessage, messagesLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

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
    // 去掉错误消息后重试最后一次用户输入
    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
    if (lastUser) send(lastUser.content);
  };

  const hasError = messages.some((m) => m.error);

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] md:h-[calc(100vh-4rem)]">
      {/* 错误横幅 */}
      {hasError && (
        <div className="flex items-center justify-between px-4 py-2 bg-red-50 border-b border-red-100">
          <div className="flex items-center gap-2 text-xs text-red-600">
            <AlertCircle className="w-3.5 h-3.5" />
            <span>最近一次生成出现问题</span>
          </div>
          <button
            onClick={handleRetry}
            className="flex items-center gap-1 px-2.5 py-1 bg-red-100 hover:bg-red-200 rounded-lg text-xs text-red-600 font-medium transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            重试
          </button>
        </div>
      )}

      {/* 消息区域 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-5 scroll-smooth">
        {/* 空状态 */}
        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-brand-100 to-brand-200 flex items-center justify-center mb-6 shadow-lg shadow-brand-100">
              <Bot className="w-10 h-10 text-brand-600" />
            </div>
            <h2 className="text-xl font-bold text-gray-800 mb-2">开始你的学习之旅</h2>
            <p className="text-gray-400 text-sm max-w-sm mb-8">
              告诉 EduAgent 你的专业、基础和目标<br />AI 智能体会为你量身定制学习方案
            </p>
            <QuickCommands onSelect={(prompt) => { setInput(prompt); inputRef.current?.focus(); }} />
          </div>
        )}

        {messages.length === 0 && !messagesLoaded && (
          <div className="flex items-center justify-center h-full">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
              <p className="text-sm text-gray-400">恢复对话记录…</p>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}

        {/* 多智能体进度管线 */}
        {isStreaming && agentProgress && (
          <AgentPipelineProgress progress={agentProgress} />
        )}

        {/* 简单 loading (无 agentProgress 时的兜底) */}
        {isStreaming && !agentProgress && (
          <div className="px-4 py-3 bg-white border border-gray-100 rounded-2xl shadow-sm animate-pulse max-w-[82%] ml-12">
            <div className="flex items-center gap-2.5">
              <div className="w-5 h-5 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
              <span className="text-sm text-gray-500">AI 正在分析你的需求…</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* 滚到底部按钮 */}
      {showScrollBtn && (
        <button
          onClick={() => scrollToBottom(true)}
          className="absolute bottom-24 left-1/2 -translate-x-1/2 w-8 h-8 bg-white border border-gray-200 rounded-full flex items-center justify-center shadow-md hover:shadow-lg transition-all z-10"
        >
          <ChevronDown className="w-4 h-4 text-gray-500" />
        </button>
      )}

      {/* 输入区域 */}
      <div className="border-t border-gray-100 bg-white px-4 py-3">
        <div className="max-w-4xl mx-auto flex items-end gap-2">
          {/* 输入框 */}
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isStreaming ? '正在生成中…' : '输入你的问题，例如：我想学习机器学习…'
            }
            rows={1}
            disabled={isStreaming}
            className="flex-1 resize-none bg-gray-50 border border-gray-200 rounded-2xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed transition-all max-h-32"
          />

          {/* 发送/停止 按钮 */}
          {isStreaming ? (
            <button
              onClick={abort}
              className="w-10 h-10 bg-red-500 text-white rounded-xl flex items-center justify-center hover:bg-red-600 transition-all flex-shrink-0 shadow-sm shadow-red-200"
              title="停止生成"
            >
              <Square className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="w-10 h-10 bg-gray-900 text-white rounded-xl flex items-center justify-center hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed transition-all flex-shrink-0 shadow-sm"
              title="发送"
            >
              <Send className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* 字数统计 + 免责声明 */}
        <div className="max-w-4xl mx-auto flex items-center justify-between mt-2 text-[10px] text-gray-400">
          <span>
            {input.length > 0 && `${input.length} / 4000`}
          </span>
          <span>
            EduAgent 可能生成不准确内容，关键信息请查阅课程教材确认
          </span>
        </div>
      </div>
    </div>
  );
}
