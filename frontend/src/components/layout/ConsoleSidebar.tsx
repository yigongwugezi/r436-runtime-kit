import { useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, User, Route, FolderOpen, MessageCircle, Settings, Sparkles, Bot, GraduationCap, History, Edit3, Users, BarChart3 } from 'lucide-react';
import { getCurrentLearner } from '../../store/authStore';

const STUDENT_NAV = [
  { id: 'dashboard', path: '/', label: '学习中心', icon: <LayoutDashboard size={20} /> },
  { id: 'profile', path: '/profile', label: '学习画像', icon: <User size={20} /> },
  { id: 'path', path: '/path', label: '学习路径', icon: <Route size={20} /> },
  { id: 'resources', path: '/resources', label: '资源库', icon: <FolderOpen size={20} /> },
  { id: 'chat', path: '/chat', label: '智能对话', icon: <MessageCircle size={20} /> },
  { id: 'generate', path: '/generate', label: '资源生成', icon: <Sparkles size={20} /> },
  { id: 'practice', path: '/practice', label: '练习中心', icon: <Edit3 size={20} /> },
  { id: 'settings', path: '/settings', label: '系统设置', icon: <Settings size={20} /> },
];

const TEACHER_NAV = [
  { id: 'dashboard', path: '/', label: '学习中心', icon: <LayoutDashboard size={20} /> },
  { id: 'class-home', path: '/teacher', label: '班级管理', icon: <Users size={20} /> },
  { id: 'admin', path: '/admin', label: '后台管理', icon: <Settings size={20} /> },
  { id: 'settings', path: '/settings', label: '系统设置', icon: <Settings size={20} /> },
];

const PARENT_NAV = [
  { id: 'dashboard', path: '/', label: '学习中心', icon: <LayoutDashboard size={20} /> },
  { id: 'analytics', path: '/analytics', label: '学习分析', icon: <BarChart3 size={20} /> },
  { id: 'timeline', path: '/timeline', label: '学习时间线', icon: <History size={20} /> },
  { id: 'profile', path: '/profile', label: '学习画像', icon: <User size={20} /> },
  { id: 'resources', path: '/resources', label: '资源库', icon: <FolderOpen size={20} /> },
  { id: 'path', path: '/path', label: '学习路径', icon: <Route size={20} /> },
  { id: 'settings', path: '/settings', label: '系统设置', icon: <Settings size={20} /> },
];

export default function ConsoleSidebar() {
  const nav = useNavigate();
  const loc = useLocation();
  const user = getCurrentLearner();
  const isTeacher = user?.role === 'teacher' || user?.role === 'admin';
  const isParent = user?.role === 'parent';
  const NAV = isTeacher ? TEACHER_NAV : (isParent ? PARENT_NAV : STUDENT_NAV);
  const roleLabel = isTeacher ? (user?.role === 'admin' ? '管理员' : '教师') : (isParent ? '家长' : '学习平台用户');
  const isActive = (p: string) => loc.pathname === p || (p === '/resources' && loc.pathname.startsWith('/resources')) || (p === '/teacher' && loc.pathname.startsWith('/teacher'));

  return (
    <div className="h-full bg-white dark:bg-surface-800 border-r border-surface-200 dark:border-surface-700 flex flex-col shadow-soft">
      <div className="p-5 border-b border-surface-100 dark:border-surface-700">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center">
            <GraduationCap className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="font-display font-bold text-lg text-surface-800 dark:text-gray-100">EduAgent</h1>
            <p className="text-xs text-surface-400 dark:text-gray-500">个性化学习平台</p>
          </div>
        </div>
      </div>

      <div className="p-4 mx-3 mt-4 bg-gradient-to-r from-primary-50 to-accent-50 dark:from-primary-500/10 dark:to-accent-500/10 rounded-xl">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary-400 to-accent-400 flex items-center justify-center text-white font-semibold">
            {user?.name?.charAt(0) || '?'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-medium text-surface-800 dark:text-gray-200 truncate">{user?.name || '学习者'}</p>
            <p className="text-xs text-surface-500 dark:text-gray-400 truncate">{roleLabel}</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV.map(item => {
          const active = isActive(item.path);
          return (
            <button key={item.id} onClick={() => nav(item.path)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 group ${active ? 'bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400' : 'text-surface-600 dark:text-gray-400 hover:bg-surface-50 dark:hover:bg-surface-700 hover:text-surface-800 dark:hover:text-gray-200'}`}>
              <span className={`transition-transform duration-200 ${active ? 'scale-110' : 'group-hover:scale-105'}`}>{item.icon}</span>
              <span className="font-medium text-sm">{item.label}</span>
              {active && <div className="ml-auto w-1.5 h-1.5 rounded-full bg-primary-500" />}
            </button>
          );
        })}
      </nav>

      <div className="p-4 mx-3 mb-4 bg-surface-50 dark:bg-surface-700 rounded-xl">
        <div className="flex items-center gap-2 mb-3"><Bot size={16} className="text-primary-500 dark:text-primary-400" /><span className="text-sm font-medium text-surface-700 dark:text-gray-300">智能体状态</span></div>
        <div className="flex gap-2">{['🧠', '🎬', '🗂️', '💻', '📝'].map((icon, idx) => <div key={idx} className={`w-8 h-8 rounded-lg bg-white dark:bg-surface-600 flex items-center justify-center text-sm shadow-card ${idx === 0 ? 'ring-2 ring-primary-300' : ''}`}>{icon}</div>)}</div>
        <p className="text-xs text-surface-400 dark:text-gray-500 mt-2">5个智能体在线待命</p>
      </div>
    </div>
  );
}
