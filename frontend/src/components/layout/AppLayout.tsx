import { useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { ToastProvider } from '../common/Toast';
import DebugPanel from '../common/DebugPanel';
import ConsoleSidebar from './ConsoleSidebar';

export default function AppLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <ToastProvider>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex">
        {/* 左侧控制台 */}
        <ConsoleSidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        />

        {/* 右侧主内容 */}
        <div className={`flex-1 flex flex-col min-h-screen transition-all duration-300 ${
          sidebarCollapsed ? 'ml-14' : 'ml-72'
        }`}>
          <MobileTopBar collapsed={sidebarCollapsed} />
          <main className="flex-1 overflow-y-auto">
            <div className="max-w-6xl mx-auto">
              <Outlet />
            </div>
          </main>
        </div>

        <DebugPanel />
      </div>
    </ToastProvider>
  );
}

/** 移动端顶部（不显示 sidebar 时用） */
function MobileTopBar({ collapsed }: { collapsed: boolean }) {
  const { pathname } = useLocation();
  const labels: Record<string, string> = {
    '/': '首页', '/chat': 'AI 对话', '/resources': '资源库',
    '/path': '学习路径', '/profile': '学习画像', '/analytics': '学习分析',
  };

  if (!collapsed) return null;

  return (
    <div className="md:hidden sticky top-0 z-40 bg-white/90 dark:bg-gray-900/90 backdrop-blur-xl border-b border-gray-100 dark:border-gray-800 px-4 py-3">
      <p className="text-sm font-bold text-gray-800 dark:text-gray-200">
        {labels[pathname] || 'r436-runtime-kit'}
      </p>
    </div>
  );
}

