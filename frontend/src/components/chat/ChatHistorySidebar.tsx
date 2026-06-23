import { useRef, useEffect } from 'react';
import { useChatStore } from '../../store/chatStore';
import { Clock, X, MessageSquare } from 'lucide-react';

/* ===================================================================
 * 对话历史侧边栏 — ChatPage 右侧
 * 显示当前会话所有消息，点击跳转到对应消息位置
 * =================================================================== */
export default function ChatHistorySidebar({ open, onClose, onJump }: {
  open: boolean;
  onClose: () => void;
  onJump: (index: number) => void;
}) {
  const messages = useChatStore((s) => s.messages);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [open, messages.length]);

  if (!open) return null;

  return (
    <>
      {/* 遮罩 */}
      <div className="fixed inset-0 z-40 bg-black/20 md:hidden" onClick={onClose} />

      {/* 侧边栏 */}
      <div className="fixed right-0 top-0 bottom-0 z-50 w-80 bg-white border-l border-gray-100 shadow-xl flex flex-col animate-slide-in-right">
        {/* 头部 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
            <MessageSquare className="w-4 h-4 text-brand-500" />
            对话历史
            <span className="text-xs text-gray-400 font-normal">({messages.length} 条)</span>
          </h2>
          <button onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 消息列表 */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
          {messages.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-sm text-gray-400">暂无消息</p>
            </div>
          ) : (
            messages.map((msg, idx) => {
              const isLatest = idx === messages.length - 1;
              return (
              <button
                key={msg.id || idx}
                onClick={() => { onJump(idx); onClose(); }}
                className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors group ${
                  isLatest
                    ? 'bg-brand-50/70 ring-1 ring-brand-200'
                    : msg.role === 'user' ? 'hover:bg-gray-50' : 'bg-gray-50/50 hover:bg-gray-100'
                }`}
              >
                <div className="flex items-start gap-2">
                  <span className={`text-[10px] font-bold mt-0.5 flex-shrink-0 w-8 ${
                    msg.role === 'user' ? 'text-gray-600' : 'text-brand-500'
                  }`}>
                    {msg.role === 'user' ? '我' : 'AI'}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-gray-700 line-clamp-2 leading-relaxed">
                      {msg.content || (msg.streaming ? '生成中…' : '(空)')}
                    </p>
                    <p className="text-[9px] text-gray-400 mt-1 flex items-center gap-1">
                      <Clock className="w-2.5 h-2.5" />
                      {new Date(msg.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </div>
                </div>
              </button>
              );
            })
          )}
        </div>

        {/* 底部 */}
        <div className="px-5 py-3 border-t border-gray-100">
          <p className="text-[10px] text-gray-400 text-center">
            点击消息跳转到对应位置
          </p>
        </div>
      </div>
    </>
  );
}
