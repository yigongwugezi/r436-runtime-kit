// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatStore } from '../store/chatStore';
import { getSessions, getSessionMessages } from '../api/chat';
import { PageLoading, PageEmpty } from '../components/common/PageState';
import { MessageCircle, Clock, ChevronRight, Trash2, ArrowLeft } from 'lucide-react';
import { timeAgo } from '../utils/format';
import Markdown from '../utils/markdown';

export default function ConversationHistoryPage() {
  const nav = useNavigate();
  const { sessions, setCurrentSession, removeSession, setSessions } = useChatStore() as any;
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<any[]>([]);
  const [msgsLoading, setMsgsLoading] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const res = await getSessions();
        if (res?.sessions) setSessions(res.sessions);
      } catch { /* ignore */ }
      finally { setLoading(false); }
    })();
  }, []);

  const handleSelect = async (id: string) => {
    setSelectedId(id);
    setCurrentSession(id);
    setMsgsLoading(true);
    try {
      const res = await getSessionMessages(id);
      setMsgs(res?.messages || []);
    } catch { setMsgs([]); }
    finally { setMsgsLoading(false); }
  };

  const handleEnter = (id: string) => {
    setCurrentSession(id);
    nav('/chat');
  };

  if (loading) return <PageLoading text="加载对话记录…" />;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold text-surface-800">对话记录</h2>
          <p className="text-surface-500 mt-1">查看和管理所有历史对话</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* 会话列表 */}
        <div className="bg-white rounded-2xl shadow-soft p-5">
          <h3 className="text-sm font-semibold text-surface-700 mb-3">全部会话</h3>
          <div className="space-y-1.5 max-h-[560px] overflow-y-auto pr-1">
            {sessions.length === 0 ? (
              <p className="text-surface-400 text-sm py-4 text-center">暂无对话记录</p>
            ) : sessions.map((s: any) => (
              <button
                key={s.id}
                onClick={() => handleSelect(s.id)}
                onDoubleClick={() => handleEnter(s.id)}
                className={`w-full text-left px-4 py-3 rounded-xl transition-all flex items-center gap-3 ${
                  selectedId === s.id ? 'bg-primary-50 border border-primary-200' : 'hover:bg-surface-50 border border-transparent'
                }`}
              >
                <div className="w-9 h-9 rounded-lg bg-primary-100 flex items-center justify-center flex-shrink-0">
                  <MessageCircle size={16} className="text-primary-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-surface-700 truncate">{s.title || '新对话'}</p>
                  <p className="text-[10px] text-surface-400 flex items-center gap-1"><Clock size={10} />{timeAgo(s.updatedAt || s.createdAt)}</p>
                </div>
                <ChevronRight size={14} className="text-surface-300 flex-shrink-0" />
              </button>
            ))}
          </div>
        </div>

        {/* 消息预览 */}
        <div className="col-span-2 bg-white rounded-2xl shadow-soft p-5 flex flex-col min-h-[500px]">
          {!selectedId ? (
            <div className="flex-1 flex items-center justify-center text-surface-400">
              <div className="text-center">
                <MessageCircle size={36} className="mx-auto mb-3 text-surface-300" />
                <p className="text-sm">选择一个会话查看消息</p>
                <p className="text-xs mt-1">双击可直接进入对话</p>
              </div>
            </div>
          ) : msgsLoading ? (
            <div className="flex-1 flex items-center justify-center"><PageLoading text="加载消息…" /></div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-4 pb-3 border-b border-surface-100">
                <h3 className="font-semibold text-surface-700">{sessions.find((s: any) => s.id === selectedId)?.title || '对话详情'}</h3>
                <div className="flex items-center gap-2">
                  <button onClick={() => handleEnter(selectedId)} className="px-3 py-1.5 bg-primary-600 text-white rounded-lg text-xs font-medium hover:bg-primary-700">进入对话</button>
                  <button onClick={() => { removeSession(selectedId); setSelectedId(null); setMsgs([]); }} className="px-3 py-1.5 bg-error-50 text-error-600 rounded-lg text-xs font-medium hover:bg-error-100"><Trash2 size={14} /></button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto space-y-3 pr-1">
                {msgs.length === 0 ? (
                  <p className="text-surface-400 text-sm py-4 text-center">暂无消息</p>
                ) : msgs.map((msg: any) => (
                  <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[75%] rounded-xl px-4 py-2.5 ${msg.role === 'user' ? 'bg-primary-600 text-white' : 'bg-surface-100 text-surface-700'}`}>
                      {msg.role === 'user' ? (
                        <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                      ) : (
                        <div className="text-sm prose-custom"><Markdown content={msg.content || '[空消息]'} /></div>
                      )}
                      <p className={`text-[10px] mt-1 ${msg.role === 'user' ? 'text-primary-200' : 'text-surface-400'}`}>{timeAgo(msg.timestamp)}</p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
