import { createContext, useContext, useState, useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { ToastProvider } from '../common/Toast';
import DebugPanel from '../common/DebugPanel';
import ConsoleSidebar from './ConsoleSidebar';
import ChatPanel from '../chat/ChatPanel';
import { Menu, MessageSquare } from 'lucide-react';

interface ChatPanelContextValue {
  open: boolean;
  setOpen: (v: boolean) => void;
  toggle: () => void;
}
const ChatPanelCtx = createContext<ChatPanelContextValue>({
  open: false,
  setOpen: () => {},
  toggle: () => {},
});
export const useChatPanel = () => useContext(ChatPanelCtx);

export default function AppLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [chatPanelOpen, setChatPanelOpen] = useState(false);
  const [panelWidth, setPanelWidth] = useState(400);
  const location = useLocation();
  const isChatPage = location.pathname === '/chat';
  const isHomePage = location.pathname === '/';

  useEffect(() => {
    setMobileDrawerOpen(false);
    if (location.pathname === '/chat' || location.pathname === '/') {
      setChatPanelOpen(false);
    } else {
      setChatPanelOpen(true);
    }
  }, [location.pathname]);

  useEffect(() => {
    if (mobileDrawerOpen) document.body.style.overflow = 'hidden';
    else document.body.style.overflow = '';
    return () => { document.body.style.overflow = ''; };
  }, [mobileDrawerOpen]);

  const chatPanelValue: ChatPanelContextValue = {
    open: chatPanelOpen,
    setOpen: setChatPanelOpen,
    toggle: () => setChatPanelOpen(v => !v),
  };

  return (
    <ChatPanelCtx.Provider value={chatPanelValue}>
    <ToastProvider>
      <div className="min-h-screen flex">
        {/* Sidebar desktop */}
        <div className="hidden md:block">
          <ConsoleSidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(v => !v)} />
        </div>

        {/* Sidebar mobile overlay */}
        {mobileDrawerOpen && <div className="fixed inset-0 z-40 bg-black/30 md:hidden" onClick={() => setMobileDrawerOpen(false)} />}
        <div className={`fixed inset-y-0 left-0 z-50 w-64 transition-transform md:hidden ${mobileDrawerOpen ? 'translate-x-0' : '-translate-x-full'}`}>
          <ConsoleSidebar collapsed={false} onToggle={() => setMobileDrawerOpen(false)} />
        </div>

        {/* Main */}
        <div className={`flex-1 flex flex-col min-h-screen transition-all ${sidebarCollapsed ? 'md:ml-14' : 'md:ml-60'}`}
          style={!isChatPage && !isHomePage && chatPanelOpen ? { marginRight: panelWidth } : undefined}>
          <MobileTopBar onMenuToggle={() => setMobileDrawerOpen(true)} onChatToggle={() => setChatPanelOpen(v => !v)} />
          <main className="flex-1 overflow-y-auto">
            <div className="max-w-5xl mx-auto px-6 py-8">
              <Outlet />
            </div>
          </main>
        </div>

        {/* Floating chat toggle */}
        {!isChatPage && !isHomePage && !chatPanelOpen && (
          <button onClick={() => setChatPanelOpen(true)}
            className="fixed top-4 right-4 z-30 w-9 h-9 rounded-xl bg-white shadow border border-gray-100 flex items-center justify-center text-gray-400 hover:text-accent-600 hover:border-accent-200 transition-all hidden md:flex">
            <MessageSquare className="w-4 h-4" />
          </button>
        )}

        {/* Chat panel */}
        {!isChatPage && !isHomePage && (
          <ChatPanel open={chatPanelOpen} onClose={() => setChatPanelOpen(false)} panelWidth={panelWidth} onWidthChange={setPanelWidth} />
        )}

        <DebugPanel />
      </div>
    </ToastProvider>
    </ChatPanelCtx.Provider>
  );
}

function MobileTopBar({ onMenuToggle, onChatToggle }: { onMenuToggle: () => void; onChatToggle: () => void }) {
  const { pathname } = useLocation();
  const labels: Record<string, string> = {
    '/': '首页', '/chat': 'AI 对话', '/resources': '资源库',
    '/path': '学习路径', '/profile': '学习画像', '/analytics': '学习分析', '/timeline': '时间线',
  };
  return (
    <div className="md:hidden sticky top-0 z-30 bg-white/95 backdrop-blur-sm px-4 py-2.5 flex items-center gap-2">
      <button onClick={onMenuToggle} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-50">
        <Menu className="w-4 h-4" />
      </button>
      <span className="text-sm font-semibold text-gray-800 truncate flex-1">{labels[pathname] || 'EduAgent'}</span>
      <button onClick={onChatToggle} className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-50">
        <MessageSquare className="w-4 h-4" />
      </button>
    </div>
  );
}

