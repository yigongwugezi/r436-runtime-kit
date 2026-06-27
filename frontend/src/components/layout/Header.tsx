import { useState, useRef, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Brain, Sparkles, LogOut, User, Settings, ChevronDown, Edit3 } from 'lucide-react';
import { getCurrentLearner, logoutLearner } from '../../pages/LoginPage';
import { useChatStore } from '../../store/chatStore';
import { readStorageJson, writeStorageJson, runtimeStorageKeys } from '../../utils/storageKeys';

const NAV = [
  { path: '/', label: '首页' },
  { path: '/chat', label: '对话' },
  { path: '/resources', label: '资源库' },
  { path: '/path', label: '学习路径' },
  { path: '/profile', label: '画像' },
  { path: '/analytics', label: '分析' },
  { path: '/timeline', label: '时间线' },
];

export default function Header() {
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [nick, setNick] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const user = getCurrentLearner();

  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) { setOpen(false); setEditing(false); } };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const save = () => {
    const n = nick.trim();
    if (!n || !user) return;
    const list = readStorageJson(runtimeStorageKeys.learners, [] as any[]);
    writeStorageJson(runtimeStorageKeys.learners, list.map((l: any) => l.id === user.id ? { ...l, name: n } : l));
    writeStorageJson(runtimeStorageKeys.activeLearner, { ...user, name: n });
    setEditing(false);
    window.location.reload();
  };

  return (
    <header className="sticky top-0 z-50 hidden md:block bg-white/80 backdrop-blur-md border-b border-gray-100">
      <div className="h-14 flex items-center justify-between px-6 max-w-screen-2xl mx-auto">
        {/* Logo */}
        <button onClick={() => nav('/')} className="flex items-center gap-2.5 shrink-0">
          <div className="w-8 h-8 rounded-xl bg-indigo-600 flex items-center justify-center"><Brain className="w-4.5 h-4.5 text-white" /></div>
          <span className="text-lg font-bold text-gray-900">EduAgent</span>
        </button>

        {/* Nav */}
        <nav className="flex items-center gap-0.5">
          {NAV.map(item => {
            const on = loc.pathname === item.path || (item.path === '/resources' && loc.pathname.startsWith('/resources'));
            return (
              <button key={item.path} onClick={() => nav(item.path)}
                className={`px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${on ? 'bg-gray-100 text-gray-900' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'}`}>
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Actions */}
        <div className="flex items-center gap-3 relative shrink-0" ref={ref}>
          <button onClick={() => nav('/chat')}
            className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm font-semibold hover:bg-gray-800 transition-colors inline-flex items-center gap-2">
            <Sparkles className="w-4 h-4" /> 开始学习
          </button>

          <button onClick={() => setOpen(!open)} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-gray-50 transition-colors">
            <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white text-xs font-bold">{user?.name?.[0] || '?'}</div>
            <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
          </button>

          {open && (
            <div className="absolute top-full right-0 mt-2 w-56 bg-white rounded-xl shadow-lg shadow-gray-200/50 border border-gray-100 py-2 animate-fade-in-up">
              <div className="px-4 py-3 border-b border-gray-50">
                <p className="text-sm font-semibold text-gray-900">{user?.name || '学习者'}</p>
                <p className="text-xs text-gray-400">个人中心</p>
              </div>
              {editing ? (
                <div className="px-4 py-3 border-b border-gray-50 flex gap-2">
                  <input value={nick} onChange={e => setNick(e.target.value)} onKeyDown={e => e.key === 'Enter' && save()}
                    className="flex-1 text-sm bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500" placeholder="新昵称" autoFocus maxLength={20} />
                  <button onClick={save} className="px-3 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700">保存</button>
                </div>
              ) : (
                <button onClick={() => { setNick(user?.name || ''); setEditing(true); }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-600 hover:bg-gray-50"><Edit3 className="w-4 h-4 text-gray-400" /> 修改昵称</button>
              )}
              <button onClick={() => { nav('/profile'); setOpen(false); }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-600 hover:bg-gray-50"><User className="w-4 h-4 text-gray-400" /> 学习画像</button>
              <div className="border-t border-gray-50 my-1" />
              <button onClick={() => { setOpen(false); nav('/login'); }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-600 hover:bg-gray-50"><Settings className="w-4 h-4 text-gray-400" /> 切换用户</button>
              <button onClick={() => { logoutLearner(); useChatStore.getState().newSession(); nav('/login'); }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-500 hover:bg-red-50"><LogOut className="w-4 h-4" /> 退出登录</button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
