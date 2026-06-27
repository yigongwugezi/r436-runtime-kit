import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Brain, User, Check, Trash2, Plus } from 'lucide-react';
import { readStorageJson, writeStorageJson, runtimeStorageKeys } from '../utils/storageKeys';
import { useSubjectStore } from '../store/subjectStore';
import { useChatStore } from '../store/chatStore';
import { useProfileStore } from '../store/profileStore';

interface Learner { id: string; name: string; createdAt: number; lastLoginAt: number; }

function loadLearners(): Learner[] { return readStorageJson(runtimeStorageKeys.learners, []); }
function saveLearners(v: Learner[]) { writeStorageJson(runtimeStorageKeys.learners, v); }
function loadActive(): Learner | null { return readStorageJson(runtimeStorageKeys.activeLearner, null); }
function saveActive(v: Learner) { writeStorageJson(runtimeStorageKeys.activeLearner, v); }
function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }

export function getCurrentLearner(): Learner | null { return loadActive(); }

export function logoutLearner() {
  try { localStorage.removeItem(runtimeStorageKeys.activeLearner.primary); } catch {}
  useSubjectStore.getState().load();
  useChatStore.getState().reloadSession();
  useProfileStore.getState().clearAll();
}

export default function LoginPage() {
  const nav = useNavigate();
  const [list, setList] = useState<Learner[]>(loadLearners);
  const [creating, setCreating] = useState(list.length === 0);
  const [name, setName] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const active = loadActive();

  const login = (l: Learner) => {
    l.lastLoginAt = Date.now();
    saveActive(l);
    saveLearners(loadLearners().map(x => x.id === l.id ? { ...x, lastLoginAt: l.lastLoginAt } : x));
    useSubjectStore.getState().load();
    useChatStore.getState().reloadSession();
    useProfileStore.getState().clearAll();
    nav('/');
  };

  const create = () => {
    const n = name.trim(); if (!n) return;
    const l: Learner = { id: uid(), name: n, createdAt: Date.now(), lastLoginAt: Date.now() };
    const ls = loadLearners(); ls.push(l); saveLearners(ls); saveActive(l);
    setList(ls); setName(''); setCreating(false);
    useSubjectStore.getState().load(); useChatStore.getState().reloadSession(); useProfileStore.getState().clearAll();
    nav('/');
  };

  const del = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const ls = loadLearners().filter(x => x.id !== id); saveLearners(ls); setList(ls);
    if (loadActive()?.id === id) logoutLearner();
  };

  const rename = (id: string) => {
    const n = editName.trim(); if (!n) return;
    const ls = loadLearners().map(x => x.id === id ? { ...x, name: n } : x); saveLearners(ls); setList(ls);
    const a = loadActive(); if (a?.id === id) saveActive({ ...a, name: n });
    setEditingId(null);
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-[#f7f7f8]">
      <div className="w-full max-w-md">
        {/* Brand */}
        <div className="text-center mb-10">
          <div className="w-16 h-16 rounded-2xl bg-indigo-600 flex items-center justify-center mx-auto mb-5 shadow-lg shadow-indigo-200">
            <Brain className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">EduAgent</h1>
          <p className="text-sm text-gray-400 mt-2">AI 驱动的个性化学习平台</p>
        </div>

        {/* Active user */}
        {active && !creating && (
          <div className="mb-6 p-4 bg-white rounded-2xl shadow-sm border border-gray-100 flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-indigo-600 flex items-center justify-center text-white text-lg font-bold shadow-sm">{active.name[0]}</div>
            <div className="flex-1 min-w-0"><p className="text-base font-bold text-gray-900 truncate">{active.name}</p><p className="text-xs text-gray-400">欢迎回来</p></div>
            <button onClick={() => nav('/')} className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors">进入</button>
          </div>
        )}

        {/* Card */}
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          {creating ? (
            <div className="space-y-4">
              <h2 className="text-lg font-bold text-gray-900">创建学习者</h2>
              <input value={name} onChange={e => setName(e.target.value)} onKeyDown={e => e.key === 'Enter' && create()}
                placeholder="输入你的名字" autoFocus maxLength={20}
                className="w-full px-4 py-3 text-sm bg-gray-50 border border-gray-200 rounded-xl outline-none focus:bg-white focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50 transition-all" />
              <div className="flex gap-3">
                <button onClick={create} disabled={!name.trim()} className="flex-1 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-40 transition-colors">创建并开始</button>
                {list.length > 0 && <button onClick={() => { setCreating(false); setName(''); }} className="px-4 py-2.5 text-sm text-gray-400 hover:text-gray-600 transition-colors">取消</button>}
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-bold text-gray-900">选择学习者</h2>
                <button onClick={() => setCreating(true)} className="text-sm font-semibold text-indigo-600 hover:text-indigo-700">新建</button>
              </div>
              <div className="space-y-1">
                {list.length === 0 ? (
                  <div className="text-center py-12">
                    <p className="text-sm text-gray-400 mb-4">还没有学习者</p>
                    <button onClick={() => setCreating(true)} className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700">创建学习者</button>
                  </div>
                ) : (
                  list.sort((a, b) => b.lastLoginAt - a.lastLoginAt).map(l => {
                    const isActive = active?.id === l.id;
                    const isEditing = editingId === l.id;
                    return (
                      <div key={l.id} onClick={() => !isEditing && login(l)}
                        className={`flex items-center gap-3 px-4 py-3 rounded-xl cursor-pointer transition-colors group ${isActive ? 'bg-indigo-50' : 'hover:bg-gray-50'}`}>
                        <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-white text-sm font-bold shrink-0 ${isActive ? 'bg-indigo-600' : 'bg-gray-300'}`}>{l.name[0]}</div>
                        {isEditing ? (
                          <div className="flex-1 flex items-center gap-2">
                            <input value={editName} onChange={e => setEditName(e.target.value)} onKeyDown={e => e.key === 'Enter' && rename(l.id)}
                              className="flex-1 text-sm bg-white border border-gray-200 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500" autoFocus maxLength={20} onClick={e => e.stopPropagation()} />
                            <button onClick={e => { e.stopPropagation(); rename(l.id); }} className="p-1.5 rounded-lg text-indigo-600 hover:bg-indigo-50"><Check className="w-4 h-4" /></button>
                          </div>
                        ) : (
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2"><span className="text-sm font-semibold text-gray-900">{l.name}</span>{isActive && <span className="px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full text-[10px] font-semibold">当前</span>}</div>
                            <p className="text-xs text-gray-400">上次登录 {new Date(l.lastLoginAt).toLocaleDateString('zh-CN')}</p>
                          </div>
                        )}
                        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          {!isEditing && <button onClick={e => { e.stopPropagation(); setEditingId(l.id); setEditName(l.name); }} className="p-1.5 rounded-lg hover:bg-gray-200 text-gray-400" title="重命名"><User className="w-3.5 h-3.5" /></button>}
                          <button onClick={e => del(l.id, e)} className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-500" title="删除"><Trash2 className="w-3.5 h-3.5" /></button>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </>
          )}
        </div>

        <p className="text-center text-[11px] text-gray-300 mt-6">学习数据保存在本地浏览器</p>
      </div>
    </div>
  );
}
