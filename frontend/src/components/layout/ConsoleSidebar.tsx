import { useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, User, Route, FolderOpen, MessageCircle, Settings, Sparkles, Bot, GraduationCap, History } from 'lucide-react';
import { getCurrentLearner } from '../../pages/LoginPage';

const NAV = [
  { id: 'dashboard', path: '/', label: '学习中心', icon: <LayoutDashboard size={20} /> },
  { id: 'profile', path: '/profile', label: '学习画像', icon: <User size={20} /> },
  { id: 'path', path: '/path', label: '学习路径', icon: <Route size={20} /> },
  { id: 'resources', path: '/resources', label: '资源库', icon: <FolderOpen size={20} /> },
  { id: 'chat', path: '/chat', label: '智能对话', icon: <MessageCircle size={20} /> },
  { id: 'generate', path: '/generate', label: '资源生成', icon: <Sparkles size={20} /> },
  { id: 'settings', path: '/settings', label: '系统设置', icon: <Settings size={20} /> },
];

export default function ConsoleSidebar() {
  const nav = useNavigate();
  const loc = useLocation();
  const user = getCurrentLearner();
  const isActive = (p: string) => loc.pathname === p || (p === '/resources' && loc.pathname.startsWith('/resources'));

  return (
    <div className="h-full bg-white border-r border-surface-200 flex flex-col shadow-soft">
      <div className="p-5 border-b border-surface-100">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center">
            <GraduationCap className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="font-display font-bold text-lg text-surface-800">EduAgent</h1>
            <p className="text-xs text-surface-400">个性化学习平台</p>
          </div>
        </div>
      </div>

      <div className="p-4 mx-3 mt-4 bg-gradient-to-r from-primary-50 to-accent-50 rounded-xl">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary-400 to-accent-400 flex items-center justify-center text-white font-semibold">
            {user?.name?.charAt(0) || '?'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-medium text-surface-800 truncate">{user?.name || '学习者'}</p>
            <p className="text-xs text-surface-500 truncate">学习平台用户</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV.map(item => {
          const active = isActive(item.path);
          return (
            <button key={item.id} onClick={() => nav(item.path)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 group ${active ? 'bg-primary-50 text-primary-600' : 'text-surface-600 hover:bg-surface-50 hover:text-surface-800'}`}>
              <span className={`transition-transform duration-200 ${active ? 'scale-110' : 'group-hover:scale-105'}`}>{item.icon}</span>
              <span className="font-medium text-sm">{item.label}</span>
              {active && <div className="ml-auto w-1.5 h-1.5 rounded-full bg-primary-500" />}
            </button>
          );
        })}
      </nav>

      <div className="p-4 mx-3 mb-4 bg-surface-50 rounded-xl">
        <div className="flex items-center gap-2 mb-3"><Bot size={16} className="text-primary-500" /><span className="text-sm font-medium text-surface-700">智能体状态</span></div>
        <div className="flex gap-2">{['🧠', '🎬', '🗂️', '💻', '📝'].map((icon, idx) => <div key={idx} className={`w-8 h-8 rounded-lg bg-white flex items-center justify-center text-sm shadow-card ${idx === 0 ? 'ring-2 ring-primary-300' : ''}`}>{icon}</div>)}</div>
        <p className="text-xs text-surface-400 mt-2">5个智能体在线待命</p>
      </div>
    </div>
  );
}
