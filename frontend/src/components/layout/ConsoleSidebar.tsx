import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useChatStore } from '../../store/chatStore';
import { useSubjectStore } from '../../store/subjectStore';
import { getCurrentLearner, logoutLearner } from '../../pages/LoginPage';
import SettingsModal from '../common/SettingsModal';
import {
  Brain, MessageSquare, Library, GitFork, User, Home,
  TrendingUp, Clock, LogOut, Settings, Plus, Trash2, ChevronLeft, ChevronRight
} from 'lucide-react';

const NAV = [
  { path: '/resources', label: '资源库', icon: Library },
  { path: '/path', label: '学习路径', icon: GitFork },
  { path: '/profile', label: '学习画像', icon: User },
  { path: '/analytics', label: '学习分析', icon: TrendingUp },
  { path: '/timeline', label: '时间线', icon: Clock },
];

export default function ConsoleSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const nav = useNavigate();
  const loc = useLocation();
  const sessions = useChatStore(s => s.sessions);
  const setSession = useChatStore(s => s.setCurrentSession);
  const { activeSubject, subjects } = useSubjectStore();
  const user = getCurrentLearner();
  const [settingsOpen, setSettingsOpen] = useState(false);

  const isActive = (p: string) => p === '/resources' ? loc.pathname.startsWith('/resources') : loc.pathname === p;

  /* ---------- Collapsed ---------- */
  if (collapsed) {
    return (
      <aside className="fixed left-0 top-0 bottom-0 z-50 w-14 bg-[#11111b] flex flex-col items-center py-4 gap-1">
        <button onClick={onToggle} className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center mb-2">
          <Brain className="w-5 h-5 text-white" />
        </button>
        <DotBtn icon={Home} active={loc.pathname === '/'} onClick={() => nav('/')} />
        {activeSubject && NAV.map(n => <DotBtn key={n.path} icon={n.icon} active={isActive(n.path)} onClick={() => nav(n.path)} />)}
        <div className="flex-1" />
        <button onClick={onToggle} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-600 hover:text-gray-400"><ChevronRight className="w-4 h-4" /></button>
      </aside>
    );
  }

  /* ---------- Expanded ---------- */
  return (
    <>
    <aside className="fixed left-0 top-0 bottom-0 z-50 w-60 bg-[#11111b] flex flex-col text-sm">
      {/* Logo */}
      <div className="flex items-center justify-between px-4 h-14 shrink-0">
        <button onClick={() => nav('/')} className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-indigo-600 flex items-center justify-center"><Brain className="w-4.5 h-4.5 text-white" /></div>
          <span className="text-base font-bold text-white">EduAgent</span>
        </button>
        <button onClick={onToggle} className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-600 hover:text-gray-400 hover:bg-white/5"><ChevronLeft className="w-4 h-4" /></button>
      </div>

      <div className="mx-3 h-px bg-white/5" />

      {/* User */}
      <div className="px-3 py-3 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center text-white text-sm font-bold shrink-0">{(user?.name || '?')[0]}</div>
          <p className="font-medium text-white truncate">{user?.name || '未登录'}</p>
        </div>
      </div>

      {/* Subject */}
      <div className="px-3 pb-3 shrink-0">
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-white/5">
          <span className="text-xs text-gray-400 truncate">{activeSubject?.name || '选择科目'}</span>
          <span className="text-[10px] text-gray-500 bg-white/10 px-2 py-0.5 rounded-full">{subjects.length}</span>
        </div>
      </div>

      <div className="mx-3 h-px bg-white/5" />

      {/* Nav */}
      {activeSubject && (
      <nav className="px-2 py-3 space-y-0.5 shrink-0">
        <button onClick={() => { useChatStore.getState().newSession(); nav('/chat'); }}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg font-medium text-indigo-400 hover:bg-indigo-500/10 transition-colors">
          <Plus className="w-4.5 h-4.5" /> 新建对话
        </button>
        <SectionLabel>内容</SectionLabel>
        {NAV.slice(0, 2).map(n => <NavRow key={n.path} {...n} active={isActive(n.path)} onClick={() => nav(n.path)} />)}
        <SectionLabel>工具</SectionLabel>
        {NAV.slice(2).map(n => <NavRow key={n.path} {...n} active={isActive(n.path)} onClick={() => nav(n.path)} />)}
      </nav>
      )}

      <div className="mx-3 h-px bg-white/5" />

      {/* Sessions */}
      {activeSubject && (
      <div className="flex-1 overflow-y-auto px-2 py-3 min-h-0">
        <p className="px-3 mb-2 text-[10px] font-semibold text-gray-500 uppercase tracking-wider">对话记录</p>
        {sessions.length === 0 ? (
          <p className="text-xs text-gray-600 text-center py-4">暂无对话</p>
        ) : (
          <div className="space-y-0.5">
            {sessions.map(s => {
              const on = s.id === useChatStore.getState().currentSessionId;
              return (
                <div key={s.id} className="group relative">
                  <button onClick={() => { setSession(s.id); nav('/chat'); }}
                    className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${on ? 'bg-white/10 text-white font-medium' : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'}`}>
                    <p className="truncate">{s.title || '新对话'}</p>
                  </button>
                  <button onClick={e => { e.stopPropagation(); if (confirm('删除？')) useChatStore.getState().removeSession(s.id); }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
      )}

      {!activeSubject && <div className="flex-1" />}

      {/* Footer */}
      <div className="px-4 py-3 border-t border-white/5 flex items-center justify-between shrink-0">
        <button onClick={() => setSettingsOpen(true)} className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors"><Settings className="w-4 h-4" /> 设置</button>
        <button onClick={() => { logoutLearner(); nav('/login'); }} className="flex items-center gap-2 text-xs text-gray-500 hover:text-red-400 transition-colors"><LogOut className="w-4 h-4" /> 退出</button>
      </div>
    </aside>
    <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </>
  );
}

/* ── Sub-components ── */

function SectionLabel({ children }: { children: string }) {
  return <div className="pt-2 pb-1"><p className="px-3 text-[10px] font-semibold text-gray-500 uppercase tracking-wider">{children}</p></div>;
}

function NavRow({ path, label, icon: Icon, active, onClick }: { path: string; label: string; icon: any; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors ${active ? 'bg-indigo-500/15 text-indigo-300 font-semibold' : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'}`}>
      <Icon className="w-4.5 h-4.5" /> {label}
    </button>
  );
}

function DotBtn({ icon: Icon, active, onClick }: { icon: any; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`w-9 h-9 rounded-xl flex items-center justify-center transition-colors ${active ? 'bg-indigo-500/20 text-indigo-300' : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'}`}>
      <Icon className="w-5 h-5" />
    </button>
  );
}
