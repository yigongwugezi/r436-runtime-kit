import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, User, Stethoscope, Route, FileText, Settings, Sparkles, Upload, GraduationCap } from 'lucide-react';
import { getCurrentLearner } from '../../store/authStore';
import client from '../../api/client';

interface NavBadges {
  profile_filled: number;
  profile_total: number;
  diagnosis_weak_count: number;
  diagnosis_high_count: number;
  path_has_new: boolean;
  path_has_adjustment: boolean;
  review_warning_count: number;
  review_blocked_count: number;
}

export default function ConsoleSidebar() {
  const nav = useNavigate();
  const loc = useLocation();
  const user = getCurrentLearner();
  const [badges, setBadges] = useState<NavBadges | null>(null);

  // §2.4.2 fetch nav badges on mount
  useEffect(() => {
    const fetchBadges = async () => {
      try {
        const sid = loc.pathname.includes('session') ? new URLSearchParams(loc.search).get('sessionId') : '';
        const { data } = await client.get('/api/nav-state', { params: { sessionId: sid || undefined } });
        if (data?.badges) setBadges(data.badges);
      } catch { /* nav badges are best-effort */ }
    };
    fetchBadges();
    const interval = setInterval(fetchBadges, 15000); // poll every 15s
    return () => clearInterval(interval);
  }, [loc.pathname, loc.search]);

  const profilePct = badges ? Math.round((badges.profile_filled / badges.profile_total) * 100) : 0;

  // §2.4.2 ring color
  const ringColor = profilePct <= 20 ? '#475569'
    : profilePct <= 60 ? '#06B6D4'
    : profilePct <= 90 ? '#6366F1'
    : '#F59E0B';
  const circumference = 2 * Math.PI * 26; // r=26
  const dashLength = profilePct > 0 ? (profilePct / 100) * circumference : circumference * 0.05;
  const isDashed = profilePct <= 20;

  const isActive = (p: string) => loc.pathname === p || (p === '/resources' && loc.pathname.startsWith('/resources'));

  const navItems = [
    { id: 'home', path: '/', label: '学习主页', icon: <LayoutDashboard size={18} /> },
    {
      id: 'diagnosis', path: '/diagnosis', label: '学习诊断', icon: <Stethoscope size={18} />,
      badge: badges ? (badges.diagnosis_high_count > 0 ? { text: `${badges.diagnosis_high_count}`, color: 'bg-red-500' } : badges.diagnosis_weak_count > 0 ? { text: `${badges.diagnosis_weak_count}`, color: 'bg-amber-500' } : null) : null,
    },
    {
      id: 'path', path: '/path', label: '学习路径', icon: <Route size={18} />,
      badge: badges?.path_has_adjustment ? { text: '', color: 'bg-amber-400 w-2 h-2' } : badges?.path_has_new ? { text: '', color: 'bg-red-500 w-2 h-2' } : null,
    },
    {
      id: 'report', path: '/report', label: '学习报告', icon: <FileText size={18} />,
      badge: badges ? (badges.review_blocked_count > 0 ? { text: `${badges.review_blocked_count}`, color: 'bg-red-500' } : badges.review_warning_count > 0 ? { text: `${badges.review_warning_count}`, color: 'bg-amber-500' } : null) : null,
    },
    { id: 'profile', path: '/profile', label: '我的画像', icon: <User size={18} /> },
    { id: 'settings', path: '/settings', label: '系统设置', icon: <Settings size={18} /> },
  ];

  return (
    <div className="h-full bg-[#0F0F1A] text-[#E2E8F0] flex flex-col border-r border-white/5">
      {/* §2.4.1 Logo — icon only on tablet, full on desktop */}
      <div className="h-16 flex items-center justify-center lg:justify-start lg:px-5 border-b border-white/5">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-accent-500 flex items-center justify-center lg:mr-2.5">
          <GraduationCap className="w-4 h-4 text-white" />
        </div>
        <span className="hidden lg:inline text-[17px] font-bold text-[#F1F5F9] tracking-wide">EduAgent</span>
      </div>

      {/* §2.4.2 User area — icon only on tablet */}
      <div className="h-16 lg:h-20 flex items-center justify-center lg:justify-start gap-0 lg:gap-3 px-2 lg:px-4 hover:bg-white/[0.03] cursor-pointer transition-colors" onClick={() => nav('/profile')}>
        <div className="relative flex-shrink-0">
          <div className="w-9 h-9 lg:w-12 lg:h-12 rounded-full bg-[#1E293B] flex items-center justify-center text-sm lg:text-lg font-semibold text-white">
            {user?.name?.charAt(0) || '?'}
          </div>
          <svg className="absolute inset-0 w-9 h-9 lg:w-12 lg:h-12 -rotate-90" viewBox="0 0 56 56">
            <circle cx="28" cy="28" r="26" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="3" />
            <circle cx="28" cy="28" r="26" fill="none" stroke={ringColor} strokeWidth="3"
              strokeLinecap="round"
              strokeDasharray={`${dashLength} ${circumference - dashLength}`}
              style={{ transition: 'stroke-dasharray 500ms ease, stroke 300ms ease' }}
              strokeDashoffset={isDashed ? 5 : 0}
            />
          </svg>
        </div>
        <div className="hidden lg:block">
          <p className="text-sm font-medium">{user?.name || '学习者'}</p>
          <p className="text-[11px] text-[#94A3B8]">{badges ? `${badges.profile_filled}/${badges.profile_total}维 · ${profilePct}%` : '加载中…'}</p>
        </div>
      </div>

      {/* §2.4.3 Navigation — icons only on tablet */}
      <nav className="flex-1 px-1.5 lg:px-2 py-2 space-y-0.5 overflow-y-auto">
        {navItems.map(item => {
          const active = isActive(item.path);
          return (
            <button key={item.id} onClick={() => nav(item.path)}
              title={item.label}
              className={`w-full flex items-center gap-2.5 h-11 px-2 lg:px-3 rounded-lg text-sm transition-all duration-150 ${
                active
                  ? 'bg-brand-500/15 text-brand-400 border-l-[3px] border-brand-500'
                  : 'text-[#94A3B8] hover:bg-white/[0.04] border-l-[3px] border-transparent'
              }`}
            >
              <span className="flex-shrink-0">{item.icon}</span>
              <span className="hidden lg:inline font-normal truncate">{item.label}</span>
              {item.badge && (
                <span className={`ml-auto flex-shrink-0 hidden lg:flex ${item.badge.color} ${item.badge.text ? 'min-w-[18px] h-[18px] rounded-full items-center justify-center text-[10px] text-white font-medium px-1' : 'rounded-full'}`}>
                  {item.badge.text}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* §2.4.4 Quick actions — icon only on tablet */}
      <div className="px-2 lg:px-4 py-3 space-y-2">
        <button onClick={() => { document.querySelector<HTMLTextAreaElement>('[data-chat-input]')?.focus(); }}
          title="开始新学习"
          className="w-full h-10 rounded-lg text-[13px] font-medium bg-brand-500/12 text-brand-300 hover:bg-brand-500/20 active:bg-brand-500/28 transition-colors flex items-center justify-center lg:justify-start lg:px-3"
        >
          <span className="lg:hidden">✨</span>
          <span className="hidden lg:inline">✨ 开始新学习</span>
        </button>
        <button title="上传资料"
          className="w-full h-10 rounded-lg text-[13px] border border-dashed border-brand-500/40 text-[#94A3B8] hover:border-brand-500 hover:text-brand-300 hover:bg-brand-500/5 transition-colors flex items-center justify-center lg:justify-start lg:px-3"
        >
          <span className="lg:hidden">📎</span>
          <span className="hidden lg:inline">📎 上传资料</span>
        </button>
      </div>

      {/* §2.4.5 Footer */}
      <div className="py-3 text-center">
        <button onClick={() => nav('/settings')} className="w-5 h-5 text-[#64748B] hover:text-[#E2E8F0] transition-colors mx-auto block">
          <Settings size={16} />
        </button>
        <p className="hidden lg:block text-[10px] text-[#475569] mt-1">v4.0</p>
      </div>
    </div>
  );
}
