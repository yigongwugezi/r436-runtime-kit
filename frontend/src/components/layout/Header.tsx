import { useState, useRef, useEffect } from 'react';
import { Brain, Sparkles, LogOut, User, Settings, ChevronDown, Edit3 } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { getCurrentLearner, logoutLearner } from '../../pages/LoginPage';
import { useChatStore } from '../../store/chatStore';
import { readStorageJson, writeStorageJson, runtimeStorageKeys } from '../../utils/storageKeys';

const navItems = [
  { path: '/', label: '首页' },
  { path: '/chat', label: 'AI 对话' },
  { path: '/resources', label: '资源库' },
  { path: '/path', label: '学习路径' },
  { path: '/profile', label: '学习画像' },
  { path: '/analytics', label: '学习分析' },
];

export default function Header() {
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editName, setEditName] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);
  const learner = getCurrentLearner();

  // 点击外部关闭菜单
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
        setEditOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleLogout = () => {
    logoutLearner();
    useChatStore.getState().newSession();
    navigate('/login');
  };

  const handleSaveName = () => {
    const name = editName.trim();
    if (!name || !learner) return;
    // 更新 localStorage 中的 learner 名称
    const learners = readStorageJson(runtimeStorageKeys.learners, [] as any[]);
    const updated = learners.map((l: any) =>
      l.id === learner.id ? { ...l, name } : l
    );
    writeStorageJson(runtimeStorageKeys.learners, updated);
    writeStorageJson(runtimeStorageKeys.activeLearner, { ...learner, name });
    setEditOpen(false);
    window.location.reload(); // 刷新以更新所有组件中的名称
  };

  return (
    <header className="bg-white/85 backdrop-blur-xl border-b border-gray-100 sticky top-0 z-50 hidden md:block">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2.5 cursor-pointer hover:opacity-80 transition-opacity"
        >
          <div className="w-9 h-9 bg-gradient-to-br from-brand-500 to-brand-700 rounded-xl flex items-center justify-center shadow-lg shadow-brand-200">
            <Brain className="w-5 h-5 text-white" />
          </div>
          <span className="text-xl font-extrabold text-gray-900 tracking-tight">
            r436<span className="gradient-text">-runtime-kit</span>
          </span>
        </button>

        {/* Nav */}
        <nav className="flex items-center gap-1 bg-gray-50/80 rounded-xl p-1">
          {navItems.map((item) => {
            const active = location.pathname === item.path;
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  active
                    ? 'bg-white text-brand-600 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* User 下拉菜单 */}
        <div className="flex items-center gap-3 relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl hover:bg-gray-50 border border-transparent hover:border-gray-100 transition-all"
          >
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-xs font-bold shadow-sm">
              {learner?.name?.[0] || '?'}
            </div>
            <div className="hidden xl:block text-left">
              <p className="text-xs font-semibold text-gray-800 leading-tight">{learner?.name || '学习者'}</p>
              <p className="text-[9px] text-gray-400">个人中心</p>
            </div>
            <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform duration-200 ${menuOpen ? 'rotate-180' : ''}`} />
          </button>

          {/* 下拉菜单 */}
          {menuOpen && (
            <div className="absolute top-full right-0 mt-2 w-56 bg-white border border-gray-100 rounded-2xl shadow-xl shadow-gray-200/50 py-2 animate-fade-in-up">
              {/* 用户信息 */}
              <div className="px-4 py-3 border-b border-gray-50">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-sm font-bold shadow-sm">
                    {learner?.name?.[0] || '?'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-gray-900 truncate">{learner?.name || '学习者'}</p>
                    <p className="text-[10px] text-gray-400 font-mono truncate">
                      ID: {learner?.id?.slice(0, 12)}...
                    </p>
                  </div>
                </div>
              </div>

              {/* 修改昵称 */}
              {editOpen ? (
                <div className="px-4 py-3 border-b border-gray-50">
                  <div className="flex items-center gap-2">
                    <input
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSaveName()}
                      className="flex-1 text-xs bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-brand-500"
                      placeholder="输入新昵称"
                      autoFocus
                      maxLength={20}
                    />
                    <button
                      onClick={handleSaveName}
                      className="px-3 py-2 bg-brand-500 text-white rounded-lg text-xs font-semibold hover:bg-brand-600 transition-colors"
                    >
                      保存
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => { setEditName(learner?.name || ''); setEditOpen(true); }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  <Edit3 className="w-4 h-4 text-gray-400" />
                  修改昵称
                </button>
              )}

              {/* 查看画像 */}
              <button
                onClick={() => { navigate('/profile'); setMenuOpen(false); }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <User className="w-4 h-4 text-gray-400" />
                学习画像
              </button>

              {/* 分隔线 */}
              <div className="border-t border-gray-50 my-1" />

              {/* 切换用户 */}
              <button
                onClick={() => { setMenuOpen(false); navigate('/login'); }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <Settings className="w-4 h-4 text-gray-400" />
                切换用户
              </button>

              {/* 退出登录 */}
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-500 hover:bg-red-50 transition-colors"
              >
                <LogOut className="w-4 h-4" />
                退出登录
              </button>
            </div>
          )}

          <button
            onClick={() => navigate('/chat')}
            className="px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all shadow-lg shadow-gray-200 inline-flex items-center gap-2"
          >
            <Sparkles className="w-4 h-4" />
            开始学习
          </button>
        </div>
      </div>
    </header>
  );
}
