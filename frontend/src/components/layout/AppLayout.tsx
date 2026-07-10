import { Outlet, useLocation } from 'react-router-dom';
import { ToastProvider } from '../common/Toast';
import ConsoleSidebar from './ConsoleSidebar';
import ChatPanel from '../chat/ChatPanel';
import PipelineProgressPanel from '../chat/PipelineProgressPanel';
import { useChatStore } from '../../store/chatStore';

const PAGE_INFO: Record<string, { title: string; subtitle: string }> = {
  '/': { title: '学习主页', subtitle: '' },
  '/diagnosis': { title: '学习诊断', subtitle: '薄弱点分析与证据链' },
  '/path': { title: '学习路径', subtitle: '个性化学习规划与复习调度' },
  '/resources': { title: '资源库', subtitle: '多智能体生成的个性化资源' },
  '/report': { title: '学习报告', subtitle: '质量审查与学习评估' },
  '/profile': { title: '学习画像', subtitle: '9维动态学习特征' },
  '/practice': { title: '练习中心', subtitle: '答题练习与错题回顾' },
  '/settings': { title: '系统设置', subtitle: '' },
};

export default function AppLayout() {
  const loc = useLocation();
  const info = PAGE_INFO[loc.pathname] || { title: 'EduAgent', subtitle: '' };
  const agentSteps = useChatStore((s) => s.agentSteps);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const showProgress = agentSteps.length > 0 || isStreaming;

  return (
    <ToastProvider>
      <div className="h-screen flex overflow-hidden bg-surface-50 dark:bg-surface-900">
        {/* §2.4 Left Sidebar — 240px lg, 64px icons on tablet */}
        <aside className="w-[64px] lg:w-60 flex-shrink-0 h-full transition-all duration-200">
          <ConsoleSidebar />
        </aside>

        {/* §2.6 Center Content Area */}
        <main className="flex-1 flex flex-col min-w-0 h-full overflow-hidden bg-white dark:bg-surface-900">
          {/* §2.6.2 Toolbar */}
          <div className="h-12 flex items-center px-4 lg:px-5 border-b border-surface-200 dark:border-surface-700 bg-white dark:bg-surface-800 flex-shrink-0">
            <nav className="text-xs text-surface-500 dark:text-surface-400 truncate">
              <span className="hover:text-brand-600 cursor-pointer">EduAgent</span>
              {info.title && info.title !== 'EduAgent' && (
                <>
                  <span className="mx-1.5 text-surface-300 dark:text-surface-600">{'>'}</span>
                  <span className="text-surface-800 dark:text-gray-200 font-medium">{info.title}</span>
                </>
              )}
            </nav>
            {info.subtitle && (
              <span className="ml-2 text-2xs text-surface-400 dark:text-surface-500 hidden sm:inline truncate">{info.subtitle}</span>
            )}
            <div className="flex-1" />
            <div className="hidden sm:flex items-center gap-0.5">
              <button className="w-8 h-8 rounded-lg flex items-center justify-center text-surface-400 hover:text-brand-600 hover:bg-brand-50 dark:hover:bg-brand-500/10 transition-colors" title="书签">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
              </button>
            </div>
          </div>

          {/* Content — scrollable with page padding */}
          <div className="flex-1 overflow-y-auto p-4 lg:p-6">
            {/* §3.2 Pipeline progress — visible across all pages during agent execution */}
            {showProgress && <PipelineProgressPanel />}
            <Outlet />
          </div>
        </main>

        {/* §2.5 Right Chat Area — 400px lg, hidden on mobile/tablet */}
        <aside className="w-[400px] flex-shrink-0 h-full hidden xl:block border-l border-surface-200 dark:border-surface-700">
          <ChatPanel embedded />
        </aside>
      </div>
    </ToastProvider>
  );
}
