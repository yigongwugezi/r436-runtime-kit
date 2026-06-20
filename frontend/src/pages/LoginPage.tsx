import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Brain, Sparkles, User, ArrowRight, Check, Trash2, Plus } from 'lucide-react';

/* ===================================================================
 * 多学习者管理
 * =================================================================== */

const LEARNERS_KEY = 'eduagent_learners';
const ACTIVE_KEY = 'eduagent_active_learner';

interface Learner {
  id: string;
  name: string;
  createdAt: number;
  lastLoginAt: number;
}

function loadLearners(): Learner[] {
  try {
    return JSON.parse(localStorage.getItem(LEARNERS_KEY) || '[]');
  } catch { return []; }
}

function saveLearners(learners: Learner[]) {
  try { localStorage.setItem(LEARNERS_KEY, JSON.stringify(learners)); } catch { /* noop */ }
}

function loadActiveLearner(): Learner | null {
  try {
    const data = localStorage.getItem(ACTIVE_KEY);
    return data ? JSON.parse(data) : null;
  } catch { return null; }
}

function saveActiveLearner(learner: Learner) {
  try { localStorage.setItem(ACTIVE_KEY, JSON.stringify(learner)); } catch { /* noop */ }
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

export function getCurrentLearner(): Learner | null {
  return loadActiveLearner();
}

export function logoutLearner() {
  try { localStorage.removeItem(ACTIVE_KEY); } catch { /* noop */ }
}

/* ===================================================================
 * 登录页面
 * =================================================================== */
export default function LoginPage() {
  const navigate = useNavigate();
  const [learners, setLearners] = useState<Learner[]>(loadLearners);
  const [showCreate, setShowCreate] = useState(learners.length === 0);
  const [newName, setNewName] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');

  const switchLearner = (learner: Learner) => {
    learner.lastLoginAt = Date.now();
    saveActiveLearner(learner);

    // 更新列表中的时间
    const list = loadLearners().map(l =>
      l.id === learner.id ? { ...l, lastLoginAt: learner.lastLoginAt } : l
    );
    saveLearners(list);

    navigate('/');
  };

  const createLearner = () => {
    const name = newName.trim();
    if (!name) return;

    const learner: Learner = {
      id: generateId(),
      name,
      createdAt: Date.now(),
      lastLoginAt: Date.now(),
    };

    const list = loadLearners();
    list.push(learner);
    saveLearners(list);
    saveActiveLearner(learner);

    setLearners(list);
    setNewName('');
    setShowCreate(false);
    navigate('/');
  };

  const deleteLearner = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const list = loadLearners().filter(l => l.id !== id);
    saveLearners(list);
    setLearners(list);

    // 如果删除的是当前用户，清除活跃状态
    const active = loadActiveLearner();
    if (active?.id === id) {
      logoutLearner();
    }
  };

  const renameLearner = (id: string) => {
    const name = editName.trim();
    if (!name) return;

    const list = loadLearners().map(l =>
      l.id === id ? { ...l, name } : l
    );
    saveLearners(list);
    setLearners(list);

    // 如果重命名的是当前用户，同步更新
    const active = loadActiveLearner();
    if (active?.id === id) {
      saveActiveLearner({ ...active, name });
    }

    setEditingId(null);
  };

  const activeLearner = loadActiveLearner();

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-brand-50/30 flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-10">
          <div className="w-16 h-16 rounded-3xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center mx-auto mb-4 shadow-xl shadow-brand-200/50 animate-float">
            <Brain className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-extrabold text-gray-900">r436<span className="gradient-text">-runtime-kit</span></h1>
          <p className="text-sm text-gray-400 mt-1">课程工作流演示系统</p>
        </div>

        {/* 当前已登录 */}
        {activeLearner && !showCreate && (
          <div className="mb-6 p-4 bg-gradient-to-br from-brand-50 to-white border border-brand-100 rounded-2xl">
            <p className="text-[10px] text-brand-500 font-semibold uppercase tracking-wider mb-2">当前学习者</p>
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-lg font-bold shadow-md">
                {activeLearner.name[0]}
              </div>
              <div className="flex-1">
                <p className="text-base font-bold text-gray-900">{activeLearner.name}</p>
                <p className="text-xs text-gray-400">
                  ID: <span className="font-mono text-[10px]">{activeLearner.id.slice(0, 12)}...</span>
                </p>
              </div>
              <button
                onClick={() => navigate('/')}
                className="px-4 py-2 bg-brand-500 text-white rounded-xl text-sm font-semibold hover:bg-brand-600 transition-all shadow-md shadow-brand-200 inline-flex items-center gap-1.5"
              >
                进入 <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* 学习者列表 / 创建表单 */}
        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          {/* 标题 */}
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-gray-800">
              {showCreate ? '创建学习者' : '切换学习者'}
            </h2>
            {!showCreate && (
              <button
                onClick={() => setShowCreate(true)}
                className="text-xs text-brand-500 hover:text-brand-600 font-medium inline-flex items-center gap-1 transition-colors"
              >
                <Plus className="w-3 h-3" />
                新建
              </button>
            )}
          </div>

          {/* 创建表单 */}
          {showCreate ? (
            <div className="space-y-3">
              <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl">
                <div className="w-10 h-10 rounded-xl bg-brand-100 flex items-center justify-center flex-shrink-0">
                  <User className="w-5 h-5 text-brand-500" />
                </div>
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && createLearner()}
                  placeholder="输入你的名字或昵称…"
                  className="flex-1 bg-transparent border-none outline-none text-sm text-gray-700 placeholder-gray-300"
                  autoFocus
                  maxLength={20}
                />
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={createLearner}
                  disabled={!newName.trim()}
                  className="flex-1 px-4 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 disabled:opacity-30 transition-all inline-flex items-center justify-center gap-2"
                >
                  <Sparkles className="w-4 h-4" />
                  创建并开始
                </button>
                {learners.length > 0 && (
                  <button
                    onClick={() => { setShowCreate(false); setNewName(''); }}
                    className="px-4 py-2.5 text-sm text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    取消
                  </button>
                )}
              </div>
            </div>
          ) : (
            /* 学习者列表 */
            <div className="space-y-2">
              {learners.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-sm text-gray-400 mb-4">还没有学习者，创建一个吧</p>
                  <button
                    onClick={() => setShowCreate(true)}
                    className="px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all inline-flex items-center gap-2"
                  >
                    <Plus className="w-4 h-4" />
                    创建学习者
                  </button>
                </div>
              ) : (
                learners
                  .sort((a, b) => b.lastLoginAt - a.lastLoginAt)
                  .map((learner) => {
                    const isActive = activeLearner?.id === learner.id;
                    const isEditing = editingId === learner.id;

                    return (
                      <div
                        key={learner.id}
                        onClick={() => !isEditing && switchLearner(learner)}
                        className={`flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-all group ${
                          isActive
                            ? 'bg-brand-50 border border-brand-100'
                            : 'bg-gray-50 border border-transparent hover:bg-gray-100 hover:border-gray-200'
                        }`}
                      >
                        <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-white text-sm font-bold flex-shrink-0 ${
                          isActive
                            ? 'bg-gradient-to-br from-brand-500 to-brand-700 shadow-md'
                            : 'bg-gradient-to-br from-gray-400 to-gray-500'
                        }`}>
                          {learner.name[0]}
                        </div>

                        {isEditing ? (
                          <div className="flex-1 flex items-center gap-2">
                            <input
                              value={editName}
                              onChange={(e) => setEditName(e.target.value)}
                              onKeyDown={(e) => e.key === 'Enter' && renameLearner(learner.id)}
                              className="flex-1 text-sm bg-white border border-gray-200 rounded-lg px-2 py-1 outline-none focus:ring-2 focus:ring-brand-500"
                              autoFocus
                              maxLength={20}
                              onClick={(e) => e.stopPropagation()}
                            />
                            <button
                              onClick={(e) => { e.stopPropagation(); renameLearner(learner.id); }}
                              className="p-1.5 rounded-lg hover:bg-brand-50 text-brand-500"
                            >
                              <Check className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-semibold text-gray-800">{learner.name}</p>
                              {isActive && (
                                <span className="px-1.5 py-0.5 bg-brand-100 text-brand-600 rounded text-[9px] font-semibold">
                                  当前
                                </span>
                              )}
                            </div>
                            <p className="text-[10px] text-gray-400">
                              上次登录：{new Date(learner.lastLoginAt).toLocaleDateString('zh-CN')}
                            </p>
                          </div>
                        )}

                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          {!isEditing && (
                            <button
                              onClick={(e) => { e.stopPropagation(); setEditingId(learner.id); setEditName(learner.name); }}
                              className="p-1.5 rounded-lg hover:bg-gray-200 text-gray-400"
                              title="重命名"
                            >
                              <User className="w-3 h-3" />
                            </button>
                          )}
                          <button
                            onClick={(e) => deleteLearner(learner.id, e)}
                            className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-500"
                            title="删除"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    );
                  })
              )}
            </div>
          )}
        </div>

        {/* 底部说明 */}
        <p className="text-center text-[10px] text-gray-400 mt-6">
          学习数据保存在本地 · 切换学习者自动切换 session
        </p>
      </div>
    </div>
  );
}
