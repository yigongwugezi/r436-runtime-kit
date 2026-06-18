import { useState, useEffect } from 'react';
import { useChatStore } from '../../store/chatStore';
import { useProfileStore } from '../../store/profileStore';
import { useSubjectStore } from '../../store/subjectStore';
import { Bug, ChevronDown, ChevronUp, X, Activity } from 'lucide-react';

/* ===================================================================
 * 接口调试面板
 * 显示：
 *   - 当前 sessionId
 *   - 当前请求的 API 路径（实时追踪 fetch）
 *   - dataVersion
 *   - 数据来源（db/agent/mock/none）
 * =================================================================== */

// 拦截 fetch 记录 API 调用
let apiCalls: { method: string; url: string; time: number }[] = [];
const originalFetch = window.fetch;
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  // 只记录后端 API 调用
  if (url.includes('localhost:8001') || url.includes('/api/')) {
    apiCalls.unshift({ method: init?.method || 'GET', url: url.split('localhost:8001')[1] || url, time: Date.now() });
    if (apiCalls.length > 20) apiCalls.pop();
  }
  return originalFetch(input, init);
};

export default function DebugPanel() {
  const [open, setOpen] = useState(false);
  const [, forceUpdate] = useState(0);

  // 每秒刷新
  useEffect(() => {
    const timer = setInterval(() => forceUpdate(n => n + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const calls = apiCalls.slice(0, 8);
  const learner = (() => {
    try {
      const data = localStorage.getItem('eduagent_active_learner');
      return data ? JSON.parse(data) : null;
    } catch { return null; }
  })();

  return (
    <>
      {/* 浮动开关 - 明显化 */}
      <button
        onClick={() => setOpen(!open)}
        className={`fixed bottom-20 right-4 z-[60] w-10 h-10 rounded-2xl flex items-center justify-center shadow-lg transition-all duration-200 ${
          open
            ? 'bg-brand-600 text-white shadow-brand-200'
            : 'bg-gray-900 text-white hover:bg-gray-800 shadow-gray-200'
        }`}
        title="调试面板"
      >
        {open ? <X className="w-4 h-4" /> : <Bug className="w-4 h-4" />}
      </button>

      {/* 面板 */}
      {open && (
        <div className="fixed bottom-[7.5rem] right-4 z-[60] w-80 max-h-[70vh] overflow-y-auto bg-gray-900/95 backdrop-blur-xl border border-gray-700 rounded-2xl shadow-2xl animate-fade-in-up">
          {/* 头部 */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700/50">
            <span className="text-xs font-bold text-gray-300 flex items-center gap-1.5">
              <Bug className="w-3.5 h-3.5 text-green-400" />
              Debug
              <span className="text-[9px] text-gray-500 font-normal ml-1">实时</span>
            </span>
            <span className="text-[9px] text-gray-500">{new Date().toLocaleTimeString()}</span>
          </div>

          <div className="p-4 space-y-3">
            {/* 学习者 */}
            <DebugRow label="Learner" value={learner?.name || '未登录'} />
            <DebugRow label="Session ID" value={useChatStore.getState().currentSessionId} mono />
            <DebugRow label="Data Version" value={String(useChatStore.getState().dataVersion)} />
            <DebugRow label="Streaming" value={String(useChatStore.getState().isStreaming)} />
            <DebugRow label="Messages" value={`${useChatStore.getState().messages.length} 条`} />

            {/* 数据来源 */}
            <div className="border-t border-gray-700/50 pt-3 space-y-2">
              <p className="text-[9px] text-gray-500 uppercase tracking-wider font-semibold">数据来源</p>
              {(() => {
                const sid = useSubjectStore.getState().activeSubject?.id;
                const p = sid ? useProfileStore.getState().profiles[sid] : null;
                return (
                  <>
                    <DebugSource label="Profile" source={p ? 'agent_generated' : 'none'} />
                    <DebugSource label="Resources" source={p?.dimensions?.length ? 'agent_generated' : 'none'} />
                  </>
                );
              })()}
            </div>

            {/* 最近 API 调用 */}
            {calls.length > 0 && (
              <div className="border-t border-gray-700/50 pt-3 space-y-1.5">
                <p className="text-[9px] text-gray-500 uppercase tracking-wider font-semibold">最近 API</p>
                {calls.map((call, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className={`text-[8px] font-mono font-bold px-1 py-0.5 rounded ${
                      call.method === 'POST' ? 'text-green-400 bg-green-500/10' :
                      call.method === 'GET' ? 'text-blue-400 bg-blue-500/10' :
                      'text-gray-400 bg-gray-500/10'
                    }`}>{call.method}</span>
                    <span className="text-[9px] text-gray-400 font-mono truncate flex-1">{call.url}</span>
                  </div>
                ))}
              </div>
            )}

            {/* 操作 */}
            <div className="border-t border-gray-700/50 pt-3 space-y-2">
              <p className="text-[9px] text-gray-500 uppercase tracking-wider font-semibold">操作</p>
              <button
                onClick={() => {
                  localStorage.clear();
                  window.location.reload();
                }}
                className="w-full text-left px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg text-[10px] text-red-400 hover:bg-red-500/20 transition-colors"
              >
                🗑 清除所有本地数据并刷新
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function DebugRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] text-gray-500">{label}</span>
      <span className={`text-[10px] text-gray-300 max-w-[180px] truncate text-right ${mono ? 'font-mono' : ''}`}>
        {value}
      </span>
    </div>
  );
}

function DebugSource({ label, source }: { label: string; source: 'agent_generated' | 'system_inferred' | 'none' }) {
  const colorMap = {
    agent_generated: 'text-purple-400 bg-purple-500/10 border-purple-500/30',
    system_inferred: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
    none: 'text-gray-500 bg-gray-500/10 border-gray-500/30',
  };
  const labelMap = { agent_generated: 'Agent', system_inferred: 'Inferred', none: 'None' };

  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] text-gray-500">{label}</span>
      <span className={`text-[9px] font-mono font-semibold px-2 py-0.5 rounded border ${colorMap[source]}`}>
        {labelMap[source]}
      </span>
    </div>
  );
}
