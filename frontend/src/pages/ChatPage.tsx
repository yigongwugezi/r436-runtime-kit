import { useState, useRef, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useChatStore } from '../store/chatStore';
import { useStreamChat } from '../hooks/useStreamChat';
import { DEFAULT_QUICK_COMMANDS } from '../utils/constants';
import type { ChatMessage } from '../types/chat';
import { Send, Sparkles, Square } from 'lucide-react';
import Markdown from '../utils/markdown';
import MermaidDiagram from '../utils/mermaid';

/* ===================================================================
 * 子组件
 * =================================================================== */

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'} animate-fade-in-up`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center flex-shrink-0 shadow-md">
          <Sparkles className="w-4 h-4 text-white" />
        </div>
      )}
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-gray-900 text-white rounded-br-md'
            : 'bg-white border border-gray-100 shadow-sm rounded-bl-md'
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{msg.content}</p>
        ) : (
          <div className="text-gray-800">
            <Markdown content={msg.content} />
            {msg.streaming && (
              <span className="inline-block w-1.5 h-4 bg-brand-500 animate-pulse rounded ml-0.5 align-text-bottom" />
            )}
            {msg.error && (
              <p className="text-red-500 text-xs mt-2">⚠️ {msg.error}</p>
            )}
          </div>
        )}
      </div>
      {isUser && (
        <div className="w-8 h-8 rounded-xl bg-gray-200 flex items-center justify-center flex-shrink-0 text-xs font-bold text-gray-600">
          U
        </div>
      )}
    </div>
  );
}

function ProgressIndicator({ stage, progress }: { stage: string; progress: number }) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 bg-white border border-gray-100 rounded-2xl shadow-sm animate-fade-in-up">
      <div className="w-6 h-6 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-700">{stage}</p>
        <div className="mt-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-brand-500 to-brand-600 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
      <span className="text-xs text-gray-400">{progress}%</span>
    </div>
  );
}

function QuickCommands({ onSelect }: { onSelect: (prompt: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2 px-1">
      {DEFAULT_QUICK_COMMANDS.map((cmd) => (
        <button
          key={cmd.id}
          onClick={() => onSelect(cmd.prompt)}
          className="inline-flex items-center gap-1.5 px-3 py-2 bg-white border border-gray-200 rounded-xl text-xs text-gray-600 hover:border-brand-300 hover:text-brand-600 hover:bg-brand-50/50 transition-all"
        >
          <span>{cmd.icon}</span>
          <span>{cmd.label}</span>
        </button>
      ))}
    </div>
  );
}

/* ===================================================================
 * 主页面
 * =================================================================== */

export default function ChatPage() {
  const location = useLocation();
  const initialMessage = (location.state as { initialMessage?: string })?.initialMessage;
  const { messages, isStreaming } = useChatStore();
  const { send, abort } = useStreamChat();
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  // 从 Home 页跳转来的初始消息
  useEffect(() => {
    if (initialMessage) {
      send(initialMessage);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] md:h-[calc(100vh-4rem)]">
      {/* 消息区域 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-brand-100 to-brand-200 flex items-center justify-center mb-6">
              <Sparkles className="w-10 h-10 text-brand-600" />
            </div>
            <h2 className="text-xl font-bold text-gray-800 mb-2">开始你的学习之旅</h2>
            <p className="text-gray-400 text-sm max-w-sm mb-8">
              告诉 EduAgent 你的专业、基础和目标，AI 智能体会为你量身定制学习方案。
            </p>
            <QuickCommands onSelect={(prompt) => { setInput(prompt); inputRef.current?.focus(); }} />
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}

        {isStreaming && (
          <ProgressIndicator stage="AI 正在思考..." progress={50} />
        )}
      </div>

      {/* 输入区域 */}
      <div className="border-t border-gray-100 bg-white px-4 py-3">
        <div className="max-w-4xl mx-auto flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的问题，例如：我想学习机器学习..."
            rows={1}
            className="flex-1 resize-none bg-gray-50 border border-gray-200 rounded-2xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all max-h-32"
          />
          {isStreaming ? (
            <button
              onClick={abort}
              className="w-10 h-10 bg-red-500 text-white rounded-xl flex items-center justify-center hover:bg-red-600 transition-colors flex-shrink-0"
            >
              <Square className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="w-10 h-10 bg-gray-900 text-white rounded-xl flex items-center justify-center hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed transition-all flex-shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          )}
        </div>
        <p className="text-[10px] text-gray-400 text-center mt-2">
          EduAgent 可能生成不准确内容，关键信息请查阅课程教材确认
        </p>
      </div>
    </div>
  );
}
