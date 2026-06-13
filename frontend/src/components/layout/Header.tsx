import { Brain } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';

const navItems = [
  { path: '/', label: '首页' },
  { path: '/chat', label: 'AI 对话' },
  { path: '/resources', label: '资源库' },
  { path: '/path', label: '学习路径' },
  { path: '/profile', label: '学习画像' },
];

export default function Header() {
  const navigate = useNavigate();
  const location = useLocation();

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
            Edu<span className="gradient-text">Agent</span>
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

        {/* CTA */}
        <button
          onClick={() => navigate('/chat')}
          className="px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all shadow-lg shadow-gray-200"
        >
          开始学习
        </button>
      </div>
    </header>
  );
}
