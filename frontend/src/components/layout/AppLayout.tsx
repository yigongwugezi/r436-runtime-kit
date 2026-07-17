import { createContext, useContext, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { MessageSquare } from 'lucide-react';
import { ToastProvider } from '../common/Toast';
import ConsoleSidebar from './ConsoleSidebar';
import Header from './Header';
import ChatPanel from '../chat/ChatPanel';

const ChatPanelCtx = createContext<{ open: boolean; setOpen: (v: boolean) => void; toggle: () => void }>({ open: false, setOpen: () => {}, toggle: () => {} });
export const useChatPanel = () => useContext(ChatPanelCtx);

const PAGE_TITLES: Record<string, { title: string; subtitle: string }> = {
  '/': { title: '学习中心', subtitle: '你的个性化学习仪表盘' },
  '/chat': { title: '智能对话', subtitle: '与AI助手对话交流' },
  '/resources': { title: '资源库', subtitle: '个性化推荐的学习资源' },
  '/path': { title: '学习路径', subtitle: '智能规划的学习进阶路线' },
  '/kg': { title: '知识图谱', subtitle: '交互式知识点关系图谱' },
  '/profile': { title: '学习画像', subtitle: 'AI对话构建的个性化学习特征' },
  '/analytics': { title: '学习分析', subtitle: '学习行为数据分析' },
  '/timeline': { title: '学习时间线', subtitle: '学习行为记录' },
  '/generate': { title: '资源生成', subtitle: '多智能体协同生成学习资源' },
  '/practice': { title: '练习中心', subtitle: '答题练习与错题回顾' },
  '/settings': { title: '系统设置', subtitle: '个性化你的学习体验' },
  '/teacher': { title: '班级管理', subtitle: '管理你的班级和学生' },
};

const HIDE_CHAT_PANEL = new Set(['/chat', '/settings', '/login']);

export default function AppLayout() {
  const loc = useLocation();
  const info = PAGE_TITLES[loc.pathname]
    || (loc.pathname.startsWith('/teacher/classes/') ? { title: '班级详情', subtitle: '练习 · 学生 · 统计' } : null)
    || (loc.pathname.startsWith('/resources/') ? { title: '资源详情', subtitle: '个性化推荐的学习资源' } : null)
    || { title: 'EduAgent', subtitle: '' };
  const [chatOpen, setChatOpen] = useState(false);
  const [panelWidth, setPanelWidth] = useState(420);
  const showChat = !HIDE_CHAT_PANEL.has(loc.pathname);

  return (
    <ChatPanelCtx.Provider value={{ open: chatOpen, setOpen: setChatOpen, toggle: () => setChatOpen(v => !v) }}>
    <ToastProvider>
      <div className="min-h-screen bg-surface-50 dark:bg-surface-900 flex">
        <aside className="w-64 fixed left-0 top-0 bottom-0 z-40">
          <ConsoleSidebar />
        </aside>
        <div className="flex-1 ml-64 flex flex-col min-h-screen">
          <Header title={info.title} subtitle={info.subtitle} />
          <main className="p-6 flex-1 flex flex-col"><Outlet /></main>
        </div>
      </div>
      {showChat && !chatOpen && (
        <button
          onClick={() => setChatOpen(true)}
          className="fixed bottom-6 right-6 z-50 w-11 h-11 rounded-xl flex items-center justify-center bg-white dark:bg-surface-700 text-surface-600 dark:text-gray-300 hover:bg-primary-50 dark:hover:bg-primary-500/10 hover:text-primary-600 dark:hover:text-primary-400 shadow-soft transition-all"
          title="AI 对话"
        >
          <MessageSquare size={22} />
        </button>
      )}
      {showChat && <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} panelWidth={panelWidth} onWidthChange={setPanelWidth} />}
    </ToastProvider>
    </ChatPanelCtx.Provider>
  );
}