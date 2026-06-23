import { useState, useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { ToastProvider } from '../common/Toast';
import DebugPanel from '../common/DebugPanel';
import ConsoleSidebar from './ConsoleSidebar';
import { Menu, X } from 'lucide-react';

export default function AppLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const location = useLocation();

  // 路由变化时关闭移动端抽屉
  useEffect(() => {
    setMobileDrawerOpen(false);
  }, [location.pathname]);

  // 移动端抽屉打开时禁止 body 滚动
  useEffect(() => {
    if (mobileDrawerOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [mobileDrawerOpen]);

  return (
    <ToastProvider>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex">
        {/* 桌面端侧边栏 - 大屏显示 */}
        <div className="hidden md:block">
          <ConsoleSidebar
            collapsed={sidebarCollapsed}
            onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
          />
        </div>

        {/* 移动端抽屉遮罩 */}
        {mobileDrawerOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/40 md:hidden"
            onClick={() => setMobileDrawerOpen(false)}
          />
        )}

        {/* 移动端抽屉侧栏 */}
        <div className={`fixed inset-y-0 left-0 z-50 w-72 transform transition-transform duration-300 ease-in-out md:hidden ${
          mobileDrawerOpen ? 'translate-x-0' : '-translate-x-full'
        }`}>
          <ConsoleSidebar
            collapsed={false}
            onToggle={() => setMobileDrawerOpen(false)}
          />
        </div>

        {/* 右侧主内容 */}
        <div className={`flex-1 flex flex-col min-h-screen transition-all duration-300 ${
          sidebarCollapsed ? 'md:ml-14' : 'md:ml-72'
        }`}>
          {/* 移动端顶部栏 */}
          <MobileTopBar onMenuToggle={() => setMobileDrawerOpen(true)} />
          <main className="flex-1 overflow-y-auto">
            <div className="max-w-6xl mx-auto px-2 sm:px-4">
              <Outlet />
            </div>
          </main>
        </div>

        <DebugPanel />
      </div>
    </ToastProvider>
  );
}

/** 移动端顶部栏 */
function MobileTopBar({ onMenuToggle }: { onMenuToggle: () => void }) {
  const { pathname } = useLocation();
  const labels: Record<string, string> = {
    '/': '首页', '/chat': 'AI 对话', '/resources': '资源库',
    '/path': '学习路径', '/profile': '学习画像', '/analytics': '学习分析', '/timeline': '时间线',
  };

  return (
    <div className="md:hidden sticky top-0 z-30 bg-white/95 backdrop-blur-xl border-b border-gray-100 px-3 py-2.5 flex items-center gap-3">
      <button
        onClick={onMenuToggle}
        className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-600 hover:bg-gray-100 transition-colors"
        title="打开菜单"
        aria-label="打开导航菜单"
      >
        <Menu className="w-5 h-5" />
      </button>
      <p className="text-sm font-bold text-gray-800 truncate flex-1">
        {labels[pathname] || 'r436-runtime-kit'}
      </p>
    </div>
  );
}

