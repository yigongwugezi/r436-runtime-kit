import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSubjectStore } from '../store/subjectStore';
import { getCurrentLearner } from './LoginPage';
import { BookOpen, Plus, ChevronRight, Settings, Trash2 } from 'lucide-react';

export default function Home() {
  const navigate = useNavigate();
  const { subjects, activeSubject, create, setActive, remove } = useSubjectStore();
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState('');
  const learner = getCurrentLearner();

  const handleCreate = () => {
    const name = newName.trim();
    if (!name) return;
    const subject = create(name);
    setNewName('');
    setShowNew(false);
    setActive(subject);
    navigate('/chat');
  };

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-xl font-bold shadow-md">
            {learner?.name?.[0] || '?'}
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">{learner?.name || '学习者'}</h1>
            <p className="text-sm text-gray-400">{subjects.length} 个科目</p>
          </div>
        </div>
        <button className="p-2 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors" title="设置">
          <Settings className="w-5 h-5" />
        </button>
      </div>

      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-700">我的科目</h2>
          <button onClick={() => setShowNew(!showNew)}
            className="flex items-center gap-1.5 text-sm text-brand-500 hover:text-brand-600 font-medium transition-colors">
            <Plus className="w-4 h-4" />
            新建科目
          </button>
        </div>

        {showNew && (
          <div className="mb-4 p-4 bg-gray-50 rounded-xl border border-gray-200">
            <div className="flex items-center gap-3">
              <input value={newName} onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                placeholder="输入科目名称，如「数据结构」"
                className="flex-1 bg-white border border-gray-200 rounded-lg px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent" autoFocus maxLength={30} />
              <button onClick={handleCreate} disabled={!newName.trim()}
                className="px-4 py-2.5 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-30 transition-colors">创建</button>
              <button onClick={() => setShowNew(false)}
                className="px-3 py-2.5 text-sm text-gray-400 hover:text-gray-600 transition-colors">取消</button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {subjects.length === 0 ? (
            <div className="text-center py-16 bg-gray-50 rounded-2xl border border-gray-100">
              <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
                <BookOpen className="w-8 h-8 text-gray-300" />
              </div>
              <h3 className="text-base font-semibold text-gray-700 mb-1">还没有科目</h3>
              <p className="text-sm text-gray-400 mb-6">新建一个科目开始你的学习之旅</p>
              <button onClick={() => setShowNew(true)}
                className="px-5 py-2.5 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800 transition-colors inline-flex items-center gap-2">
                <Plus className="w-4 h-4" />
                新建科目
              </button>
            </div>
          ) : (
            subjects.map((subject) => {
              const isActive = activeSubject?.id === subject.id;
              return (
                <div key={subject.id}
                  onClick={() => { setActive(subject); navigate('/chat'); }}
                  className={'flex items-center justify-between p-4 rounded-xl border cursor-pointer transition-all group ' + (isActive ? 'bg-brand-50 border-brand-200' : 'bg-white border-gray-100 hover:border-gray-200 hover:shadow-sm')}>
                  <div className="flex items-center gap-3">
                    <div className={'w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold ' + (isActive ? 'bg-brand-500 text-white shadow-sm' : 'bg-gray-100 text-gray-600')}>
                      {subject.name[0]}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-gray-800">{subject.name}</p>
                      <p className="text-xs text-gray-400">{new Date(subject.updatedAt).toLocaleDateString('zh-CN')}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {isActive && <span className="px-2 py-0.5 bg-brand-100 text-brand-600 rounded text-[10px] font-semibold">当前</span>}
                    <button onClick={(e) => { e.stopPropagation(); if (confirm(`确定删除科目「${subject.name}」？相关数据将被清除。`)) remove(subject.id); }}
                      className="p-1.5 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 transition-all opacity-0 group-hover:opacity-100">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                    <ChevronRight className="w-4 h-4 text-gray-300" />
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
