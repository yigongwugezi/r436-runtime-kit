import { useNavigate, useLocation } from 'react-router-dom';
import { Home, MessageSquare, Library, GitFork, User } from 'lucide-react';

const tabs = [
  { path: '/', label: '首页', icon: Home },
  { path: '/chat', label: '对话', icon: MessageSquare },
  { path: '/resources', label: '资源库', icon: Library },
  { path: '/path', label: '学习路径', icon: GitFork },
  { path: '/profile', label: '画像', icon: User },
];

export default function BottomNav() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  return (
    <nav className="bg-white/85 backdrop-blur-xl border-t border-gray-100 sticky bottom-0 z-50 md:hidden safe-area-bottom">
      <div className="flex items-center justify-around h-16 px-2">
        {tabs.map(({ path, label, icon: Icon }) => {
          const active = pathname === path;
          return (
            <button
              key={path}
              onClick={() => navigate(path)}
              className={`flex flex-col items-center gap-0.5 px-2 py-1.5 rounded-xl transition-all duration-200 min-w-[52px] ${
                active ? 'text-brand-600' : 'text-gray-400 hover:text-gray-600'
              }`}
            >
              <div className={`p-1 rounded-lg transition-all ${active ? 'bg-brand-50' : ''}`}>
                <Icon className="w-5 h-5" />
              </div>
              <span className="text-[10px] font-medium">{label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
