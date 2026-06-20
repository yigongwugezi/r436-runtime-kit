import { useState, useRef, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useChatStore } from '../../store/chatStore';
import { useSubjectStore } from '../../store/subjectStore';
import { getCurrentLearner, logoutLearner } from '../../pages/LoginPage';
import SettingsModal from '../common/SettingsModal';
import { readStorageJson, writeStorageJson, runtimeStorageKeys } from '../../utils/storageKeys';
import {
  Brain, MessageSquare, Library, GitFork, User, Home, TrendingUp,
  LogOut, ChevronLeft, ChevronRight, Edit3, Check, X,
  Settings, Gift, HelpCircle, GraduationCap, Share2, Plus, Trash2,
} from 'lucide-react';

/* ===================================================================
 * 导航按钮
 * =================================================================== */
function NavBtn({ path, label, icon: Icon, active, navigate }: { path: string; label: string; icon: any; active: boolean; navigate: any }) {
  return (
    <button onClick={() => navigate(path)}
      className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-medium transition-all ${
        active ? 'bg-brand-500/15 text-brand-400' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
      }`}
    >
      <Icon className="w-4.5 h-4.5 flex-shrink-0" />
      {label}
      {active && <div className="ml-auto w-1 h-4 rounded-full bg-brand-500" />}
    </button>
  );
}

/* ===================================================================
 * ConsoleSidebar
 * =================================================================== */
export default function ConsoleSidebar({ collapsed, onToggle }: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const messages = useChatStore((s) => s.messages);
  const sessions = useChatStore((s) => s.sessions);
  const setCurrentSession = useChatStore((s) => s.setCurrentSession);
  const newSession = useChatStore((s) => s.newSession);
  const { activeSubject, subjects, setActive } = useSubjectStore();
  const learner = getCurrentLearner();
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState('');
  const [profileOpen, setProfileOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
        setMoreOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSaveName = () => {
    const name = nameInput.trim();
    if (!name || !learner) return;
    const learners = readStorageJson(runtimeStorageKeys.learners, [] as any[]);
    const updated = learners.map((l: any) =>
      l.id === learner.id ? { ...l, name } : l
    );
    writeStorageJson(runtimeStorageKeys.learners, updated);
    writeStorageJson(runtimeStorageKeys.activeLearner, { ...learner, name });
    setEditingName(false);
    window.location.reload();
  };

  if (collapsed) {
    return (
      <div className="fixed left-0 top-0 bottom-0 z-50 w-14 bg-gray-900 border-r border-gray-800 flex flex-col items-center py-4 gap-2">
        <button onClick={onToggle} className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-lg mb-4">
          <Brain className="w-5 h-5 text-white" />
        </button>
        <button onClick={() => navigate('/')}
          className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${location.pathname === '/' ? 'bg-brand-500/20 text-brand-400' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}>
          <Home className="w-4.5 h-4.5" />
        </button>
        <div className="w-8 border-t border-gray-800/30 my-1" />
        <button onClick={() => { useChatStore.getState().newSession(); navigate('/chat'); }}
          className="w-9 h-9 rounded-xl flex items-center justify-center text-green-400 hover:text-green-300 hover:bg-gray-800" title="新建对话">
          <Plus className="w-4.5 h-4.5" />
        </button>
        <div className="w-8 border-t border-gray-800/30 my-1" />
        <button onClick={() => navigate('/resources')}
          className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${location.pathname === '/resources' ? 'bg-brand-500/20 text-brand-400' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}>
          <Library className="w-4.5 h-4.5" />
        </button>
        <button onClick={() => navigate('/path')}
          className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${location.pathname === '/path' ? 'bg-brand-500/20 text-brand-400' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}>
          <GitFork className="w-4.5 h-4.5" />
        </button>
        <button onClick={() => navigate('/chat')}
          className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${location.pathname === '/chat' ? 'bg-brand-500/20 text-brand-400' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}>
          <MessageSquare className="w-4.5 h-4.5" />
        </button>
        <button onClick={() => navigate('/profile')}
          className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${location.pathname === '/profile' ? 'bg-brand-500/20 text-brand-400' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}>
          <User className="w-4.5 h-4.5" />
        </button>
        <button onClick={() => navigate('/analytics')}
          className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${location.pathname === '/analytics' ? 'bg-brand-500/20 text-brand-400' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}>
          <TrendingUp className="w-4.5 h-4.5" />
        </button>
        <div className="w-8 border-t border-gray-800/30 my-1" />
        <button onClick={() => setSettingsOpen(true)}
          className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all text-gray-500 hover:text-gray-300 hover:bg-gray-800`}>
          <Settings className="w-4.5 h-4.5" />
        </button>
        <div className="flex-1" />
        <button onClick={onToggle} className="w-9 h-9 rounded-xl flex items-center justify-center text-gray-500 hover:text-gray-300 hover:bg-gray-800">
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <>
    <div className="fixed left-0 top-0 bottom-0 z-50 w-72 bg-gray-900 border-r border-gray-800 flex flex-col">
      {/* ===== Logo + 折叠 ===== */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
        <button onClick={() => navigate('/')} className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-lg">
            <Brain className="w-4.5 h-4.5 text-white" />
          </div>
          <span className="text-base font-extrabold text-white tracking-tight">
            r436<span className="text-brand-400">-runtime-kit</span>
          </span>
        </button>
        <button onClick={onToggle}
          className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-600 hover:text-gray-300 hover:bg-gray-800 transition-all">
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* ===== 用户信息 ===== */}
      <div className="px-4 py-3 border-b border-gray-800/50">
        {editingName ? (
          <div className="flex items-center gap-2">
            <input
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSaveName()}
              className="flex-1 text-sm bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-200 outline-none focus:ring-2 focus:ring-brand-500 placeholder-gray-500"
              placeholder="输入新昵称"
              autoFocus
              maxLength={20}
            />
            <button onClick={handleSaveName} className="p-1.5 rounded-lg hover:bg-gray-700 text-brand-400">
              <Check className="w-3.5 h-3.5" />
            </button>
            <button onClick={() => setEditingName(false)} className="p-1.5 rounded-lg hover:bg-gray-700 text-gray-500">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-sm font-bold flex-shrink-0 shadow-sm">
              {learner?.name?.[0] || '?'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-gray-200 truncate">{learner?.name || '未登录'}</p>
              <div className="flex items-center gap-1.5">
                <p className="text-[10px] text-gray-600">学习者</p>
                <button onClick={() => { setNameInput(learner?.name || ''); setEditingName(true); }}
                  className="text-gray-600 hover:text-gray-300 transition-colors">
                  <Edit3 className="w-3 h-3" />
                </button>
              </div>
            </div>
            <button onClick={() => { logoutLearner(); useChatStore.getState().newSession(); window.location.href = '/login'; }}
              className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-600 hover:text-red-400 transition-all">
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* ===== 当前科目 ===== */}
      <div className="px-4 py-3 border-b border-gray-800/50">
        <button onClick={() => navigate('/')}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl bg-gray-800/50 hover:bg-gray-800 transition-all mb-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-sm">
            <Home className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1 text-left">
            <p className="text-sm font-semibold text-gray-200">个人中心</p>
            <p className="text-[10px] text-gray-500">科目管理 · 账户设置</p>
          </div>
        </button>
        <div className="flex items-center gap-2 px-1">
          <div className="w-2 h-2 rounded-full bg-brand-500" />
          <span className="text-sm font-semibold text-gray-200 truncate">{activeSubject?.name || '选择科目'}</span>
          <span className="ml-auto text-[10px] text-gray-600 bg-gray-800/30 px-2 py-0.5 rounded-full">{subjects.length} 科</span>
        </div>
      </div>

      {/* ===== 导航 */}
      <div className="px-3 py-3 space-y-0.5 border-b border-gray-800/30">
        <button onClick={() => { useChatStore.getState().newSession(); navigate('/chat'); }}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-gray-200 hover:text-white hover:bg-gray-800/50 transition-all border border-dashed border-gray-700/50 mb-2">
          <div className="w-4.5 h-4.5 flex items-center justify-center"><Plus className="w-4 h-4" /></div>
          新建对话
        </button>

        <p className="text-[9px] text-gray-600 uppercase tracking-wider font-semibold px-3 mb-1">资源</p>
        <NavBtn path="/resources" label="资源库" icon={Library} active={location.pathname === '/resources'} navigate={navigate} />
        <NavBtn path="/path" label="学习路径" icon={GitFork} active={location.pathname === '/path'} navigate={navigate} />

        <div className="border-t border-gray-800/40 my-2" />
        <p className="text-[9px] text-gray-600 uppercase tracking-wider font-semibold px-3 mb-1">工具台</p>
        <NavBtn path="/chat" label="对话" icon={MessageSquare} active={location.pathname === '/chat'} navigate={navigate} />
        <NavBtn path="/profile" label="画像" icon={User} active={location.pathname === '/profile'} navigate={navigate} />
        <NavBtn path="/analytics" label="分析" icon={TrendingUp} active={location.pathname === '/analytics'} navigate={navigate} />
      </div>

      {/* ===== 对话记录（按会话） ===== */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        <p className="text-[10px] text-gray-600 uppercase tracking-wider font-semibold px-1 mb-2 flex items-center gap-1.5">
          <MessageSquare className="w-3 h-3" />
          对话记录
        </p>

        {sessions.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-[11px] text-gray-700">暂无对话</p>
            <p className="text-[9px] text-gray-700 mt-1">去对话页开始学习</p>
          </div>
        ) : (
          <div className="space-y-0.5">
            {sessions.map((ses) => {
              const active = ses.id === useChatStore.getState().currentSessionId;
              return (
                <div key={ses.id} className="group relative">
                  <button
                    onClick={() => {
                      setCurrentSession(ses.id);
                      navigate('/chat');
                    }}
                    className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${
                      active ? 'bg-gray-800/50' : 'hover:bg-gray-800/50'
                    }`}
                  >
                    <p className={`text-[11px] leading-relaxed truncate ${
                      active ? 'text-gray-200' : 'text-gray-400'
                    }`}>
                      {ses.title || '新对话'}
                    </p>
                    <p className="text-[9px] text-gray-700 mt-0.5">
                      {new Date(ses.updatedAt || ses.createdAt).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); if (confirm('确定删除此对话？')) useChatStore.getState().removeSession(ses.id); }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md text-gray-600 hover:text-red-400 hover:bg-gray-800 opacity-0 group-hover:opacity-100 transition-all"
                    title="删除对话"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ===== 底部图标栏（紧凑） ===== */}
      <div className="flex items-center justify-between px-3 py-2 border-t border-gray-800">
        <div className="flex items-center gap-1">
          <IconBtn icon={Gift} title="购买" />
          <button onClick={() => setSettingsOpen(true)}
            className="w-7 h-7 rounded-lg bg-gray-800/50 flex items-center justify-center text-gray-500 hover:text-gray-200 hover:bg-gray-700 transition-all" title="设置">
            <Settings className="w-3.5 h-3.5" />
          </button>
          <IconBtn icon={GraduationCap} title="新手教学" />
          <IconBtn icon={HelpCircle} title="问题与帮助" />
        </div>

        {/* 个人中心 - 圆形 + 弹出菜单 */}
        <div className="relative" ref={profileRef}>
          <button onClick={() => setProfileOpen(!profileOpen)}
            className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-xs font-bold shadow-sm hover:shadow-md hover:scale-105 transition-all" title="个人中心">
            {learner?.name?.[0] || '?'}
          </button>

          {profileOpen && (
            <div className="absolute bottom-full right-0 mb-2 w-48 bg-gray-800 border border-gray-700 rounded-xl py-1.5 shadow-xl animate-fade-in-up">
              <div className="px-4 py-2 border-b border-gray-700/50">
                <p className="text-xs font-semibold text-gray-200">{learner?.name || '用户'}</p>
                <p className="text-[9px] text-gray-500">个人中心</p>
              </div>
              <MenuItem icon={User} label="完善资料" onClick={() => { navigate('/profile'); setProfileOpen(false); }} />
              <MenuItem icon={Gift} label="套餐购买" />
              <MenuItem icon={Settings} label="设置" onClick={() => { setSettingsOpen(true); setProfileOpen(false); }} />
              <MenuItem icon={Share2} label="邀请好友" />
              <MenuItem icon={LogOut} label="切换账号" onClick={() => { logoutLearner(); useChatStore.getState().newSession(); window.location.href = '/login'; }} />

              <div className="border-t border-gray-700/50 mt-1 pt-1">
                <div className="relative">
                  <button onClick={() => setMoreOpen(!moreOpen)}
                    className="w-full flex items-center gap-2.5 px-4 py-2 text-xs text-gray-400 hover:text-gray-200 hover:bg-gray-700/50 transition-colors">
                    <span>更多</span>
                    <ChevronRight className={`w-3 h-3 ml-auto transition-transform ${moreOpen ? 'rotate-90' : ''}`} />
                  </button>
                  {moreOpen && (
                    <div className="pl-6 pb-1 space-y-0.5">
                      <button onClick={() => setProfileOpen(false)} className="w-full text-left px-4 py-1.5 text-xs text-gray-500 hover:text-gray-300 hover:bg-gray-700/50 rounded-lg transition-colors">反馈</button>
                      <button onClick={() => setProfileOpen(false)} className="w-full text-left px-4 py-1.5 text-xs text-gray-500 hover:text-gray-300 hover:bg-gray-700/50 rounded-lg transition-colors">问题与帮助</button>
                    </div>
                  )}
                </div>
              </div>

              <div className="border-t border-gray-700/50 mt-1 pt-1">
                <MenuItem icon={LogOut} label="登出账户" onClick={() => { logoutLearner(); useChatStore.getState().newSession(); window.location.href = '/login'; }} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>

    <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </>
  );
}

function IconBtn({ icon: Icon, title }: { icon: any; title: string }) {
  return (
    <button className="w-7 h-7 rounded-lg bg-gray-800/50 flex items-center justify-center text-gray-500 hover:text-gray-200 hover:bg-gray-700 transition-all" title={title}>
      <Icon className="w-3.5 h-3.5" />
    </button>
  );
}

function MenuItem({ icon: Icon, label, onClick }: { icon: any; label: string; onClick?: () => void }) {
  return (
    <button onClick={onClick}
      className="w-full flex items-center gap-2.5 px-4 py-2 text-xs text-gray-400 hover:text-gray-200 hover:bg-gray-700/50 transition-colors">
      <Icon className="w-3.5 h-3.5" />
      {label}
    </button>
  );
}
