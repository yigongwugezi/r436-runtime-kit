import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, Plus, Copy, Trash2, ChevronRight, BookOpen, GraduationCap } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { getMyClassSubjects, createClassSubject } from '../api/classSubjects';
import type { ClassSubject } from '../types/classSubject';

function TeacherGuard({ children }: { children: React.ReactNode }) {
  const role = useAuthStore(s => s.learner?.role);
  const nav = useNavigate();
  useEffect(() => { if (role && !['admin', 'teacher'].includes(role)) nav('/'); }, [role, nav]);
  if (!role || !['admin', 'teacher'].includes(role)) return null;
  return <>{children}</>;
}

export default function TeacherHome() {
  const nav = useNavigate();
  const [classes, setClasses] = useState<ClassSubject[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [creating, setCreating] = useState(false);
  const [createdClass, setCreatedClass] = useState<ClassSubject | null>(null);

  const loadClasses = async () => {
    try {
      const list = await getMyClassSubjects();
      setClasses(list);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { loadClasses(); }, []);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const cs = await createClassSubject({
        name: newName.trim(),
        description: newDesc.trim() || undefined,
        subject: '',  // Backend auto-sets subject = name
      });
      setCreatedClass(cs);
      setNewName('');
      setNewDesc('');
      await loadClasses();
    } catch {}
    setCreating(false);
  };

  const copyCode = (code: string) => {
    navigator.clipboard.writeText(code).catch(() => {});
  };

  return (
    <TeacherGuard>
      <div className="space-y-6 animate-fade-in">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-display text-2xl font-bold text-surface-800">班级管理</h2>
            <p className="text-surface-500 mt-1">创建和管理你的班级，推送练习，查看学情</p>
          </div>
          <button
            onClick={() => { setShowCreate(!showCreate); setCreatedClass(null); }}
            className="flex items-center gap-2 px-4 py-2.5 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 transition-colors"
          >
            <Plus size={16} /> 创建班级
          </button>
        </div>

        {/* 创建班级表单 */}
        {showCreate && (
          <div className="bg-white rounded-2xl p-6 shadow-soft animate-fade-in">
            <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">创建新班级</h3>
            {createdClass ? (
              <div className="p-6 bg-success-50 rounded-xl border border-success-200 text-center">
                <p className="text-success-700 font-semibold mb-2">班级创建成功！</p>
                <p className="text-sm text-surface-600 mb-3">
                  邀请码：<span className="text-2xl font-mono font-bold text-primary-600 tracking-[0.2em]">{createdClass.invite_code}</span>
                </p>
                <button
                  onClick={() => copyCode(createdClass.invite_code)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 text-white rounded-lg text-sm hover:bg-primary-700 transition-colors"
                >
                  <Copy size={14} /> 复制邀请码
                </button>
                <button
                  onClick={() => { setShowCreate(false); setCreatedClass(null); }}
                  className="ml-3 px-4 py-2 text-sm text-surface-500 hover:text-surface-700"
                >
                  关闭
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-surface-700 mb-1.5">班级名称 *</label>
                  <input
                    value={newName}
                    onChange={e => setNewName(e.target.value)}
                    placeholder="例如：高一数学春季班"
                    maxLength={30}
                    className="w-full px-4 py-2.5 bg-surface-50 border border-surface-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-surface-700 mb-1.5">描述（可选）</label>
                  <textarea
                    value={newDesc}
                    onChange={e => setNewDesc(e.target.value)}
                    placeholder="班级描述…"
                    maxLength={200}
                    rows={2}
                    className="w-full px-4 py-2.5 bg-surface-50 border border-surface-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 transition-all resize-none"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleCreate}
                    disabled={creating || !newName.trim()}
                    className="px-6 py-2.5 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors"
                  >
                    {creating ? '创建中…' : '创建班级'}
                  </button>
                  <button
                    onClick={() => setShowCreate(false)}
                    className="px-4 py-2.5 text-sm text-surface-500 hover:text-surface-700"
                  >
                    取消
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 班级列表 */}
        <div className="bg-white rounded-2xl p-6 shadow-soft">
          <h3 className="font-display text-lg font-semibold text-surface-800 mb-5">
            我的班级 <span className="text-sm font-normal text-surface-400 ml-2">{classes.length} 个班级</span>
          </h3>
          {loading ? (
            <p className="text-surface-400 text-sm py-4 text-center">加载中…</p>
          ) : classes.length === 0 ? (
            <p className="text-surface-400 text-sm py-8 text-center">
              还没有创建班级，点击"创建班级"开始吧
            </p>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {classes.map(cs => (
                <div
                  key={cs.id}
                  className="p-5 bg-surface-50 rounded-xl border border-surface-200 hover:border-primary-300 hover:shadow-soft transition-all cursor-pointer group"
                  onClick={() => nav(`/teacher/classes/${cs.id}`)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2.5">
                      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-400 to-accent-400 flex items-center justify-center">
                        <BookOpen size={18} className="text-white" />
                      </div>
                      <div>
                        <p className="font-semibold text-surface-800">{cs.name}</p>
                        {cs.subject && <p className="text-xs text-surface-400">{cs.subject}</p>}
                      </div>
                    </div>
                    <ChevronRight size={18} className="text-surface-300 group-hover:text-primary-500 transition-colors" />
                  </div>
                  {cs.description && (
                    <p className="text-sm text-surface-500 mb-3 line-clamp-2">{cs.description}</p>
                  )}
                  <div className="flex items-center gap-4 text-xs text-surface-400">
                    <span className="flex items-center gap-1"><Users size={12} /> {cs.student_count} 名学生</span>
                    <span className="flex items-center gap-1">邀请码: <code className="font-mono text-primary-600">{cs.invite_code}</code></span>
                    <span>{new Date(cs.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </TeacherGuard>
  );
}
