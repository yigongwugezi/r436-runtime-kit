import { useState, useRef, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useChatStore } from '../store/chatStore';
import { useStreamChat } from '../hooks/useStreamChat';
import { getSessionMessages, getQuickCommands, getAgents } from '../api/chat';
import type { AgentInfo } from '../api/chat';
import { DEFAULT_QUICK_COMMANDS } from '../utils/constants';
import { timeAgo } from '../utils/format';
import type { ChatMessage, GenerationProgress, QuickCommand } from '../types/chat';
import { Send, Sparkles, Square, Copy, Check, AlertCircle, Bot, User, RefreshCw, ChevronDown, XCircle, History, Brain, Loader2, BrainCircuit, FileText, Video, Menu } from 'lucide-react';
import Markdown from '../utils/markdown';
import ChatHistorySidebar from '../components/chat/ChatHistorySidebar';
import ChatClarification from '../components/chat/ChatClarification';
import PromptTemplates from '../components/chat/PromptTemplates';

const GEN_PIPELINE = [{ key: 'understanding', label: '理解需求' }, { key: 'profiling', label: '生成画像' }, { key: 'planning', label: '规划路径' }, { key: 'generating', label: '生成资源' }, { key: 'saving', label: '保存结果' }];

function HistoryPopover({ sessions, currentSessionId, onSelect, onDelete, onRename, onNew, onClose }: {
  sessions: any[]; currentSessionId: string;
  onSelect: (id: string) => void; onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void; onNew: () => void; onClose: () => void;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const popRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (popRef.current && !popRef.current.contains(e.target as Node)) onClose(); };
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h);
  }, [onClose]);
  useEffect(() => { if (editingId) inputRef.current?.focus(); }, [editingId]);
  const sorted = sessions.slice().sort((a: any, b: any) => (b.updatedAt || 0) - (a.updatedAt || 0));
  return (
    <div ref={popRef} className="absolute left-0 top-14 w-72 bg-white rounded-xl shadow-elevated border border-gray-200 z-50 animate-fade-in overflow-hidden">
      <div className="px-3 py-2 border-b border-gray-100 flex items-center justify-between">
        <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">对话记录</span>
        <button onClick={onNew} className="text-[10px] text-brand-600 hover:text-brand-700 font-medium">+ 新建</button>
      </div>
      <div className="max-h-[320px] overflow-y-auto">
        {sorted.length === 0 ? <p className="text-xs text-gray-400 py-6 text-center">暂无对话</p> : sorted.map((ses: any) => {
          const active = ses.id === currentSessionId; const isEditing = editingId === ses.id;
          return (
            <div key={ses.id} onClick={() => { if (!isEditing) onSelect(ses.id); }}
              onDoubleClick={(e) => { e.stopPropagation(); setEditingId(ses.id); setEditTitle(ses.title || ''); }}
              className={`w-full text-left transition-colors flex items-stretch group cursor-pointer ${active ? 'bg-brand-50' : 'hover:bg-gray-50'}`}
              style={{ borderLeft: active ? '3px solid #3b82f6' : '3px solid transparent' }}>
              <div className="flex-1 min-w-0 px-3 py-2.5">
                {isEditing ? (
                  <input ref={inputRef} value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { onRename(ses.id, editTitle); setEditingId(null); } if (e.key === 'Escape') setEditingId(null); }}
                    onBlur={() => { if (editTitle.trim()) onRename(ses.id, editTitle); setEditingId(null); }}
                    onClick={(e) => e.stopPropagation()}
                    className="w-full text-[11px] px-1.5 py-0.5 bg-white border border-brand-300 rounded outline-none focus:ring-1 focus:ring-brand-400" placeholder="输入名称…" />
                ) : (
                  <>
                    <p className={`text-[12px] truncate ${active ? 'text-gray-800 font-semibold' : 'text-gray-600'}`}>{ses.title || '新对话'}</p>
                    <p className="text-[9px] text-gray-400 mt-0.5">{timeAgo(ses.updatedAt || ses.createdAt)}</p>
                  </>
                )}
              </div>
              <button onClick={(e) => { e.stopPropagation(); onDelete(ses.id); }}
                className="flex-shrink-0 w-7 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity text-gray-300 hover:text-red-500 hover:bg-red-50" title="删除">
                <XCircle className="w-3 h-3" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MessageBubble({ msg, onClarificationSelect }: { msg: ChatMessage; onClarificationSelect?: (prompt: string) => void }) {
  const isUser = msg.role === 'user'; const [copied, setCopied] = useState(false);
  return (
    <div className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''} group`}>
      <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${isUser ? 'bg-primary-600' : 'bg-gradient-to-br from-primary-500 to-accent-500'}`}>{isUser ? <User size={16} className="text-white" /> : <Bot size={16} className="text-white" />}</div>
      <div className={`max-w-2xl ${isUser ? '' : ''}`}>
        <div className={`rounded-2xl px-4 py-3 relative ${isUser ? 'bg-primary-600 text-white' : 'bg-surface-100 text-surface-700'}`}>
          {isUser ? <p className="whitespace-pre-wrap text-sm leading-relaxed">{msg.content}</p> : (
            <div className="text-sm leading-relaxed">
              {msg.content ? <Markdown content={msg.content} /> : msg.streaming ? <span className="text-surface-400">思考中…</span> : null}
              {msg.streaming && msg.content && <span className="inline-block w-1.5 h-4 bg-primary-400 animate-pulse rounded ml-0.5 align-text-bottom" />}
              {msg.error && <div className="mt-2 p-3 bg-error-50 rounded-xl flex items-start gap-2"><AlertCircle className="w-4 h-4 text-error-400 flex-shrink-0 mt-0.5" /><div><p className="text-xs text-error-600 font-medium">生成失败</p><p className="text-xs text-error-400 mt-0.5">{msg.error}</p></div></div>}
              {msg.isClarification && onClarificationSelect && <ChatClarification onSelect={onClarificationSelect} />}
            </div>
          )}
          {!isUser && msg.content && !msg.streaming && (
            <button onClick={() => { navigator.clipboard.writeText(msg.content); setCopied(true); setTimeout(() => setCopied(false), 2000); }} className="absolute -bottom-1 right-2 translate-y-full opacity-0 group-hover:opacity-100 transition-opacity p-1 bg-white rounded-lg hover:bg-surface-50 shadow-soft border border-surface-200">
              {copied ? <Check className="w-3 h-3 text-success-500" /> : <Copy className="w-3 h-3 text-surface-400" />}
            </button>
          )}
        </div>
        <div className={`mt-1 text-xs ${isUser ? 'text-right' : ''} text-surface-400`}>{new Date(msg.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</div>
      </div>
    </div>
  );
}

function AgentPipelineProgress({ progress, onRetry, onNavigate }: { progress: GenerationProgress; onRetry?: () => void; onNavigate?: (path: string) => void }) {
  const [elapsed, setElapsed] = useState(0); const currentIdx = GEN_PIPELINE.findIndex(s => s.key === (progress.agentName || '')); const isError = !!progress.error; const [doneV, setDoneV] = useState(false); const isDone = progress.done && !progress.error;
  useEffect(() => { if (isDone) { const t = setTimeout(() => setDoneV(true), 1500); return () => clearTimeout(t); } setDoneV(false); }, [isDone]);
  useEffect(() => { if (isDone || isError) return; const t = setInterval(() => setElapsed(v => v + 1), 1000); return () => clearInterval(t); }, [isDone, isError]);
  if (isError) return <div className="px-4 py-4 bg-error-50 border border-error-100 rounded-2xl shadow-soft animate-fade-in-up space-y-3 max-w-[82%] ml-12"><div className="flex items-start gap-2.5"><div className="w-6 h-6 rounded-full bg-error-100 flex items-center justify-center"><XCircle className="w-4 h-4 text-error-500" /></div><div className="flex-1"><p className="text-sm font-semibold text-error-700">生成失败</p><p className="text-xs text-error-500 mt-1">{progress.error}</p>{onRetry && <button onClick={onRetry} className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 bg-error-100 hover:bg-error-200 rounded-lg text-xs font-medium text-error-700"><RefreshCw className="w-3.5 h-3.5" />重新生成</button>}</div></div></div>;
  if (isDone) return <div className="px-4 py-4 bg-success-50/60 border border-success-100 rounded-2xl shadow-soft animate-fade-in-up space-y-3 max-w-[82%] ml-12"><div className="flex items-center gap-2.5"><div className="w-6 h-6 rounded-full bg-success-100 flex items-center justify-center"><Check className="w-4 h-4 text-success-600" /></div><span className="text-sm font-semibold text-success-700">生成完成</span></div>{onNavigate && doneV && <div className="flex flex-wrap gap-2 pt-1 animate-fade-in-up"><button onClick={() => onNavigate('/profile')} className="px-3 py-1.5 bg-white border border-success-200 rounded-lg text-xs font-medium text-success-700 hover:bg-success-50">📋 查看画像</button><button onClick={() => onNavigate('/path')} className="px-3 py-1.5 bg-white border border-success-200 rounded-lg text-xs font-medium text-success-700 hover:bg-success-50">🗺️ 查看路径</button><button onClick={() => onNavigate('/resources')} className="px-3 py-1.5 bg-white border border-success-200 rounded-lg text-xs font-medium text-success-700 hover:bg-success-50">📚 查看资源</button></div>}</div>;
  return <div className="px-4 py-4 bg-white border border-surface-200 rounded-2xl shadow-soft animate-fade-in-up space-y-3 max-w-[82%] ml-12"><div className="flex items-center gap-2.5"><div className="w-5 h-5 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" /><span className="text-sm font-semibold text-surface-800">{progress.stage || '多智能体协同处理中'}</span><span className="text-xs text-primary-600 font-medium ml-auto">{progress.progress}%</span></div><div className="flex items-center gap-1">{GEN_PIPELINE.map((step, idx) => { const done = idx < currentIdx; const cur = idx === currentIdx; return <div key={step.key} className="flex items-center gap-1 flex-1 min-w-0"><div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${done ? 'bg-success-100 ring-2 ring-success-200' : cur ? 'bg-primary-100 ring-2 ring-primary-300' : 'bg-surface-50 ring-2 ring-surface-100'}`}>{done ? <Check className="w-3 h-3 text-success-600" /> : cur ? <div className="w-2.5 h-2.5 rounded-full bg-primary-500 animate-pulse" /> : <div className="w-2 h-2 rounded-full bg-surface-300" />}</div>{idx < GEN_PIPELINE.length - 1 && <div className={`flex-1 h-0.5 rounded-full ${done ? 'bg-success-300' : cur ? 'bg-surface-200' : 'bg-surface-100'}`} />}</div>; })}</div><div className="h-1.5 bg-surface-100 rounded-full overflow-hidden"><div className="h-full bg-gradient-to-r from-primary-500 to-accent-500 rounded-full transition-all duration-700 ease-out" style={{ width: `${progress.progress}%` }} /></div></div>;
}

export default function ChatPage() {
  const loc = useLocation(); const nav = useNavigate();
  const initialMessage = (loc.state as any)?.initialMessage;
  const { messages, isStreaming, agentProgress, currentSessionId, setLoading } = useChatStore() as any;
  const { send, abort } = useStreamChat();
  const [input, setInput] = useState(''); const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [messagesLoaded, setMessagesLoaded] = useState(false); const [menuOpen, setMenuOpen] = useState(false); const [historyOpen, setHistoryOpen] = useState(false);
  const [quickCommands, setQuickCommands] = useState<QuickCommand[]>(DEFAULT_QUICK_COMMANDS);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null); const inputRef = useRef<HTMLTextAreaElement>(null); const bottomRef = useRef<HTMLDivElement>(null);

  // Fetch dynamic quick commands and agents on mount
  useEffect(() => {
    getQuickCommands().then(res => { if (res.commands?.length) setQuickCommands(res.commands); }).catch(() => {});
    getAgents().then(res => { if (res.agents?.length) setAgents(res.agents); }).catch(() => {});
  }, []);

  const scrollToBottom = useCallback((smooth = false) => { smooth ? bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) : scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }); }, []);
  useEffect(() => { scrollToBottom(); }, [messages, agentProgress, scrollToBottom]);
  useEffect(() => { const el = scrollRef.current; if (!el) return; const h = () => { setShowScrollBtn(el.scrollHeight - el.scrollTop - el.clientHeight > 100 && messages.length > 0); }; el.addEventListener('scroll', h); return () => el.removeEventListener('scroll', h); });
  useEffect(() => { if (useChatStore.getState().messages.length > 0) { setMessagesLoaded(true); setLoading(false); return; } setMessagesLoaded(false); let cancelled = false; (async () => { setLoading(true); try { const res = await getSessionMessages(currentSessionId); if (!cancelled && res.messages?.length) useChatStore.setState({ messages: res.messages }); } catch {} finally { if (!cancelled) { setMessagesLoaded(true); setLoading(false); } } })(); return () => { cancelled = true; }; }, [currentSessionId]);
  useEffect(() => { if (initialMessage && messages.length === 0 && messagesLoaded) send(initialMessage); }, [initialMessage, messagesLoaded]);

  const handleSend = () => { if (!input.trim() || isStreaming) return; send(input.trim()); setInput(''); inputRef.current?.focus(); };
  const handleKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } };

  return (
    <div className="h-[calc(100vh-160px)] flex flex-col animate-fade-in">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center shadow-lg"><Brain className="w-6 h-6 text-white" /></div>
          <div>
            <div className="flex items-center gap-3">
              <h2 className="font-display text-xl font-bold text-surface-800">智能学习助手</h2>
              <div className="relative">
                <button
                  onClick={() => setMenuOpen(v => !v)}
                  className={`w-7 h-7 rounded-lg flex items-center justify-center transition-all ${menuOpen ? 'bg-primary-100 text-primary-600' : 'text-surface-400 hover:text-surface-600 hover:bg-surface-100'}`}
                  title="对话记录"
                >
                  <Menu size={16} />
                </button>
                {menuOpen && (
                  <HistoryPopover
                    sessions={useChatStore.getState().sessions}
                    currentSessionId={currentSessionId}
                    onSelect={async (id: string) => {
                      setMenuOpen(false);
                      useChatStore.getState().setCurrentSession(id);
                      try {
                        const res = await getSessionMessages(id);
                        if (res?.messages) useChatStore.setState({ messages: res.messages });
                      } catch { /* ignore */ }
                    }}
                    onDelete={(id: string) => useChatStore.getState().removeSession(id)}
                    onRename={(id: string, title: string) => useChatStore.getState().renameSession(id, title)}
                    onNew={() => { useChatStore.getState().newSession(); setMenuOpen(false); }}
                    onClose={() => setMenuOpen(false)}
                  />
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 mt-1"><span className="w-2 h-2 bg-success-500 rounded-full animate-pulse" /><span className="text-sm text-surface-500">在线 · 可通过对话构建学习画像</span></div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setHistoryOpen(true)} className="w-10 h-10 rounded-xl bg-surface-100 text-surface-500 hover:bg-surface-200 hover:text-surface-700 flex items-center justify-center transition-colors" title="历史记录">
            <History size={20} />
          </button>
          <button onClick={() => { useChatStore.getState().newSession(); }} className="flex items-center gap-2 px-4 py-2.5 bg-primary-50 text-primary-600 rounded-xl font-medium hover:bg-primary-100 transition-colors"><Sparkles size={18} />新对话</button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col bg-white rounded-2xl shadow-soft overflow-hidden">
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-4">
            {messages.length === 0 && !isStreaming ? (
              <div className="flex flex-col items-center justify-center h-full text-center px-4">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-100 to-accent-100 flex items-center justify-center mb-4"><Bot className="w-8 h-8 text-primary-600" /></div>
                <h3 className="font-display text-lg font-semibold text-surface-800 mb-2">开始你的学习之旅</h3>
                <p className="text-surface-500 text-sm max-w-sm mb-6">告诉系统你的专业、基础和目标，多智能体将为你定制学习方案</p>
                <div className="flex flex-wrap gap-2">{quickCommands.map(cmd => <button key={cmd.id} onClick={() => { setInput(cmd.prompt); inputRef.current?.focus(); }} className="px-3 py-2 bg-surface-100 border border-surface-200 rounded-xl text-xs text-surface-600 hover:border-primary-300 hover:text-primary-600 transition-all">{cmd.icon} {cmd.label}</button>)}</div>
              </div>
            ) : (
              <>
                {messages.map((msg: ChatMessage) => <MessageBubble key={msg.id} msg={msg} onClarificationSelect={send} />)}
                {agentProgress && <AgentPipelineProgress progress={agentProgress} onRetry={() => { const lastUser = [...messages].reverse().find(m => m.role === 'user'); if (lastUser) send(lastUser.content); }} onNavigate={(p: string) => nav(p)} />}
                {isStreaming && !agentProgress && (
                  <div className="flex items-start gap-3 animate-fade-in"><div className="w-8 h-8 rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center flex-shrink-0"><Bot size={16} className="text-white" /></div><div className="bg-surface-100 rounded-2xl px-4 py-3"><div className="flex items-center gap-2 text-surface-500"><Loader2 size={14} className="animate-spin" />正在思考...</div></div></div>
                )}
              </>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-surface-100 p-4">
            {messages.length > 0 && !isStreaming && <PromptTemplates onSelect={(prompt: string) => { setInput(prompt); inputRef.current?.focus(); }} />}
            <div className="flex items-end gap-3">
              <div className="flex-1 relative">
                <textarea ref={inputRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown} placeholder={isStreaming ? '生成中…' : '输入你的问题，或描述你的学习需求...'} rows={1} disabled={isStreaming} className="w-full px-4 py-3 bg-surface-50 border border-surface-200 rounded-xl text-surface-800 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 resize-none transition-all disabled:opacity-50" style={{ minHeight: '48px', maxHeight: '120px' }} />
              </div>
              {isStreaming ? (
                <button onClick={abort} className="p-3 rounded-xl bg-error-500 text-white hover:bg-error-600 transition-all"><Square size={20} /></button>
              ) : (
                <button onClick={handleSend} disabled={!input.trim()} className={`p-3 rounded-xl transition-all ${input.trim() ? 'bg-gradient-to-r from-primary-600 to-accent-600 text-white hover:shadow-lg' : 'bg-surface-100 text-surface-300 cursor-not-allowed'}`}><Send size={20} /></button>
              )}
            </div>
            <div className="flex items-center gap-4 mt-3 text-xs text-surface-400"><span>按 Enter 发送，Shift + Enter 换行</span></div>
          </div>
        </div>

        <div className="w-72 space-y-4 overflow-y-auto hidden xl:block ml-5">
          <div className="bg-white rounded-2xl p-5 shadow-soft">
            <div className="flex items-center gap-2 mb-4"><Bot size={18} className="text-primary-600" /><h3 className="font-semibold text-surface-800">协同智能体</h3></div>
            <div className="space-y-3">
              {(agents.length > 0 ? agents : [
                { id: 'profile_agent', name: '画像分析', icon: '🧠', description: '分析学习背景，构建多维学习画像', stage: 'profiling' },
                { id: 'knowledge_agent', name: '知识检索', icon: '📚', description: '从课程知识库检索相关知识点', stage: 'profiling' },
                { id: 'diagnosis_agent', name: '诊断分析', icon: '🎯', description: '诊断薄弱环节和知识缺口', stage: 'profiling' },
                { id: 'planner_agent', name: '路径规划', icon: '📊', description: '规划个性化学习阶段', stage: 'planning' },
                { id: 'resource_agent', name: '资源生成', icon: '📝', description: '生成讲义、思维导图等资源', stage: 'generating' },
                { id: 'review_agent', name: '质量审查', icon: '✅', description: '审查资源准确性和完整性', stage: 'generating' },
              ]).map((agent) => (
                <div key={agent.id} className="flex items-center gap-3 p-2 rounded-xl hover:bg-surface-50 transition-colors">
                  <div className="w-9 h-9 rounded-xl bg-primary-50 flex items-center justify-center text-sm">{agent.icon}</div>
                  <div className="flex-1 min-w-0"><p className="text-sm font-medium text-surface-800">{agent.name}</p><p className="text-xs text-surface-400 truncate">{agent.description}</p></div>
                  <span className="w-2 h-2 rounded-full bg-success-500" />
                </div>
              ))}
            </div>
          </div>
          <div className="bg-white rounded-2xl p-5 shadow-soft">
            <div className="flex items-center gap-2 mb-4"><Sparkles size={18} className="text-warning-600" /><h3 className="font-semibold text-surface-800">推荐话题</h3></div>
            <div className="space-y-2">
              {['如何制定学习计划？', '推荐CNN学习路径', '生成深度学习思维导图', 'Python项目实践案例'].map((topic, idx) => (
                <button key={idx} onClick={() => setInput(topic)} className="w-full text-left px-3 py-2 rounded-lg text-sm text-surface-600 hover:bg-primary-50 hover:text-primary-600 transition-colors">{topic}</button>
              ))}
            </div>
          </div>
          <div className="bg-white rounded-2xl p-5 shadow-soft">
            <div className="flex items-center gap-2 mb-4"><FileText size={18} className="text-accent-600" /><h3 className="font-semibold text-surface-800">生成内容</h3></div>
            <div className="space-y-2">
              {[{ icon: BrainCircuit, title: '知识图谱', to: '/resources?type=mindmap' },{ icon: Video, title: '动画演示', to: '/resources?type=video' },{ icon: FileText, title: '课程文档', to: '/resources?type=lecture' }].map((item, idx) => (
                <button key={idx} onClick={() => nav(item.to)} className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-surface-50 transition-colors">
                  <div className="w-8 h-8 rounded-lg bg-accent-50 flex items-center justify-center"><item.icon size={16} className="text-accent-600" /></div>
                  <div className="flex-1 min-w-0 text-left"><p className="text-sm font-medium text-surface-800 truncate">{item.title}</p><p className="text-xs text-surface-400">跳转资源库</p></div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {showScrollBtn && <button onClick={() => scrollToBottom(true)} className="absolute bottom-24 left-1/2 -translate-x-1/2 w-8 h-8 bg-white border border-surface-200 rounded-full flex items-center justify-center shadow-soft hover:shadow-elevated transition-all z-10"><ChevronDown className="w-4 h-4 text-surface-500" /></button>}
      <ChatHistorySidebar open={historyOpen} onClose={() => setHistoryOpen(false)} onJump={() => { setHistoryOpen(false); scrollToBottom(true); }} />
    </div>
  );
}
