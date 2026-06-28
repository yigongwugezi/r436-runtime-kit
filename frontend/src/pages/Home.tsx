import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSubjectStore } from '../store/subjectStore';
import { getCurrentLearner } from './LoginPage';
import { BookOpen, Plus, Trash2 } from 'lucide-react';

export default function Home() {
  const nav = useNavigate();
  const { subjects, activeSubject, create, setActive, remove } = useSubjectStore();
  const [show, setShow] = useState(false);
  const [name, setName] = useState('');
  const user = getCurrentLearner();

  const submit = () => {
    const n = name.trim(); if (!n) return;
    const s = create(n); setName(''); setShow(false); setActive(s); nav('/chat');
  };

  return (
    <div className="max-w-2xl">
      {/* User */}
      <div className="flex items-center gap-4 mb-8">
        <div className="w-14 h-14 rounded-2xl bg-indigo-600 flex items-center justify-center text-white text-xl font-bold shadow-sm shadow-indigo-200">
          {user?.name?.[0] || '?'}
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{user?.name || '学习者'}</h1>
          <p className="text-sm text-gray-400 mt-0.5">{subjects.length} 个科目</p>
        </div>
      </div>

      {/* Subjects */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">我的科目</h2>
        <button onClick={() => setShow(!show)} className="text-sm font-semibold text-indigo-600 hover:text-indigo-700">+ 新建科目</button>
      </div>

      {show && (
        <div className="flex items-center gap-3 mb-4">
          <input value={name} onChange={e => setName(e.target.value)} onKeyDown={e => e.key === 'Enter' && submit()}
            placeholder="输入科目名称，如「数据结构」" autoFocus maxLength={30}
            className="flex-1 px-4 py-3 text-sm bg-gray-50 border border-gray-200 rounded-xl outline-none focus:bg-white focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50 transition-all" />
          <button onClick={submit} disabled={!name.trim()} className="px-5 py-3 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-40 transition-colors whitespace-nowrap">创建</button>
          <button onClick={() => setShow(false)} className="px-3 py-3 text-sm text-gray-400 hover:text-gray-600 transition-colors whitespace-nowrap">取消</button>
        </div>
      )}

      {subjects.length === 0 ? (
        <div className="text-center py-16">
          <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-5"><BookOpen className="w-8 h-8 text-gray-300" /></div>
          <h3 className="text-lg font-semibold text-gray-700 mb-2">还没有科目</h3>
          <p className="text-sm text-gray-400 mb-6">新建一个科目，开始你的 AI 学习之旅</p>
          <button onClick={() => setShow(true)} className="px-6 py-3 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 inline-flex items-center gap-2"><Plus className="w-4 h-4" /> 新建科目</button>
        </div>
      ) : (
        <div className="space-y-2">
          {subjects.map(s => {
            const on = activeSubject?.id === s.id;
            return (
              <div key={s.id} onClick={() => { setActive(s); nav('/chat'); }}
                className={`flex items-center justify-between px-5 py-4 rounded-2xl cursor-pointer transition-all group ${on ? 'bg-indigo-50 ring-1 ring-indigo-200' : 'bg-white hover:bg-gray-50 border border-gray-100'}`}>
                <div className="flex items-center gap-4 min-w-0">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-base font-bold shrink-0 ${on ? 'bg-indigo-600 text-white shadow-sm' : 'bg-gray-100 text-gray-400'}`}>{s.name[0]}</div>
                  <div className="min-w-0"><p className="text-sm font-semibold text-gray-900 truncate">{s.name}</p><p className="text-xs text-gray-400 mt-0.5">{new Date(s.updatedAt).toLocaleDateString('zh-CN')}</p></div>
                </div>
                <div className="flex items-center gap-3">
                  {on && <span className="px-2.5 py-1 bg-indigo-100 text-indigo-700 rounded-full text-[11px] font-semibold">当前</span>}
                  <button onClick={e => { e.stopPropagation(); if (confirm(`删除「${s.name}」？`)) remove(s.id); }}
                    className="p-2 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all"><Trash2 className="w-4 h-4" /></button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
