import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, Search, Calendar, TrendingUp, User, Settings, LogOut, RefreshCw } from 'lucide-react';
import { getCurrentLearner, logoutLearner } from '../../pages/LoginPage';
import { useLearningAnalytics } from '../../hooks/useLearningAnalytics';

interface HeaderProps {
  title: string;
  subtitle?: string;
}

export default function Header({ title, subtitle }: HeaderProps) {
  const nav = useNavigate();
  const user = getCurrentLearner();
  const { analytics } = useLearningAnalytics();
  const [q, setQ] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => { if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const streak = analytics?.streak || 0;
  const todayMin = analytics?.todayStudyMinutes || 0;
  const todayStr = todayMin >= 60 ? `${(todayMin / 60).toFixed(1)}h` : `${todayMin}min`;

  const handleSearch = (e: React.KeyboardEvent) => { if (e.key === 'Enter' && q.trim()) { nav(`/resources?search=${encodeURIComponent(q.trim())}`); } };
  return (
    <div className="bg-white border-b border-surface-200 px-6 py-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-surface-800">{title}</h1>
          {subtitle && <p className="text-surface-500 text-sm mt-1">{subtitle}</p>}
        </div>

        <div className="flex items-center gap-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
            <input type="text" value={q} onChange={e => setQ(e.target.value)} onKeyDown={handleSearch} placeholder="搜索学习资源..." className="w-64 pl-10 pr-4 py-2.5 bg-surface-50 border border-surface-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all" />
          </div>

          <div className="flex items-center gap-6 px-4 border-l border-r border-surface-200">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-accent-50 flex items-center justify-center">
                <TrendingUp size={16} className="text-accent-600" />
              </div>
              <div>
                <p className="text-xs text-surface-400">连续学习</p>
                <p className="text-sm font-semibold text-surface-700">{streak}天</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-warning-50 flex items-center justify-center">
                <Calendar size={16} className="text-warning-600" />
              </div>
              <div>
                <p className="text-xs text-surface-400">今日时长</p>
                <p className="text-sm font-semibold text-surface-700">{todayStr}</p>
              </div>
            </div>
          </div>

          <button className="relative w-10 h-10 rounded-xl bg-surface-50 hover:bg-surface-100 flex items-center justify-center transition-colors">
            <Bell size={20} className="text-surface-600" />
            <span className="absolute -top-1 -right-1 w-5 h-5 bg-error-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
              3
            </span>
          </button>

          <div ref={menuRef} className="relative">
            <button onClick={() => setMenuOpen(v => !v)} className="w-10 h-10 rounded-full bg-gradient-to-br from-primary-400 to-accent-400 flex items-center justify-center text-white font-semibold hover:shadow-lg transition-shadow">
              {user?.name?.charAt(0) || '?'}
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-12 w-48 bg-white rounded-xl shadow-elevated border border-surface-200 py-1.5 z-50 animate-fade-in">
                <div className="px-4 py-2 border-b border-surface-100">
                  <p className="text-sm font-semibold text-surface-800 truncate">{user?.name || '学习者'}</p>
                  <p className="text-[10px] text-surface-400">当前账户</p>
                </div>
                <button onClick={() => { nav('/profile'); setMenuOpen(false); }} className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-surface-600 hover:bg-surface-50 transition-colors">
                  <User size={16} />学习画像
                </button>
                <button onClick={() => { nav('/login'); setMenuOpen(false); }} className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-surface-600 hover:bg-surface-50 transition-colors">
                  <RefreshCw size={16} />切换账户
                </button>
                <button onClick={() => { nav('/settings'); setMenuOpen(false); }} className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-surface-600 hover:bg-surface-50 transition-colors">
                  <Settings size={16} />系统设置
                </button>
                <div className="border-t border-surface-100 mt-1 pt-1">
                  <button onClick={() => { logoutLearner(); nav('/login'); setMenuOpen(false); }} className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-error-600 hover:bg-error-50 transition-colors">
                    <LogOut size={16} />退出登录
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
