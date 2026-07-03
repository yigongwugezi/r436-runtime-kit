import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useParams, useNavigate } from 'react-router-dom';
import {
  BookOpen, Users, BarChart3, ChevronLeft, Plus, Trash2, Send,
  Loader2, CheckCircle, GraduationCap,
} from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import {
  getClassSubject, getClassMembers, removeClassMember,
  getPushHistory, pushExercises, getClassStats,
} from '../api/classSubjects';
import * as adminApi from '../api/admin';
import type { ClassSubject, ClassMember, ClassPush, ClassStats } from '../types/classSubject';
import type { AdminQuestion } from '../api/admin';

const TABS = [
  { id: 'exercises', label: '练习管理', icon: BookOpen },
  { id: 'students', label: '学生管理', icon: Users },
  { id: 'stats', label: '学情统计', icon: BarChart3 },
] as const;

function TeacherGuard({ children }: { children: React.ReactNode }) {
  const role = useAuthStore(s => s.learner?.role);
  const nav = useNavigate();
  useEffect(() => { if (role && !['admin', 'teacher'].includes(role)) nav('/'); }, [role, nav]);
  if (!role || !['admin', 'teacher'].includes(role)) return null;
  return <>{children}</>;
}

export default function TeacherClassDetail() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const [tab, setTab] = useState<string>('exercises');
  const [cs, setCs] = useState<ClassSubject | null>(null);
  const [loading, setLoading] = useState(true);

  // Exercise management state
  const [pushes, setPushes] = useState<ClassPush[]>([]);
  const [showPushModal, setShowPushModal] = useState(false);
  const [bankQuestions, setBankQuestions] = useState<AdminQuestion[]>([]);
  const [selectedQids, setSelectedQids] = useState<Set<string>>(new Set());
  const [pushTitle, setPushTitle] = useState('');
  const [pushDesc, setPushDesc] = useState('');
  const [pushing, setPushing] = useState(false);

  // Inline question creation state
  const [showCreateQ, setShowCreateQ] = useState(false);
  const [newQStem, setNewQStem] = useState('');
  const [newQAnswer, setNewQAnswer] = useState('');
  const [newQExpl, setNewQExpl] = useState('');
  const [newQType, setNewQType] = useState('choice');
  const [newQDiff, setNewQDiff] = useState('medium');
  const [newQKp, setNewQKp] = useState('');
  const [creatingQ, setCreatingQ] = useState(false);

  // Student management state
  const [members, setMembers] = useState<ClassMember[]>([]);
  const [membersTotal, setMembersTotal] = useState(0);

  // Stats state
  const [stats, setStats] = useState<ClassStats | null>(null);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      getClassSubject(id).then(setCs).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (!id) return;
    if (tab === 'exercises') {
      getPushHistory(id).then(setPushes).catch(() => {});
    } else if (tab === 'students') {
      getClassMembers(id).then(d => { setMembers(d.members); setMembersTotal(d.total); }).catch(() => {});
    } else if (tab === 'stats') {
      getClassStats(id).then(setStats).catch(() => {});
    }
  }, [tab, id]);

  const loadBankQuestions = async () => {
    try {
      const params: any = { status: 'published', limit: 200 };
      if (cs?.subject) params.subject = cs.subject;
      const res: any = await adminApi.listQuestions(params);
      setBankQuestions(res?.questions || []);
    } catch {}
  };

  const handleCreateQuestion = async () => {
    if (!newQStem.trim() || !newQAnswer.trim()) return;
    setCreatingQ(true);
    try {
      await adminApi.createQuestion({
        subject: cs?.subject || '',
        knowledge_point: newQKp.trim(),
        type: newQType,
        difficulty: newQDiff,
        content: { stem: newQStem.trim(), answer: newQAnswer.trim(), explanation: newQExpl.trim() },
      });
      setShowCreateQ(false);
      setNewQStem(''); setNewQAnswer(''); setNewQExpl(''); setNewQKp('');
      await loadBankQuestions();
    } catch (e: any) { alert(e?.message || '创建失败'); }
    setCreatingQ(false);
  };

  const handlePush = async () => {
    if (!id || !pushTitle.trim() || selectedQids.size === 0) return;
    setPushing(true);
    try {
      await pushExercises(id, {
        title: pushTitle.trim(),
        description: pushDesc.trim() || undefined,
        questionIds: Array.from(selectedQids),
      });
      setShowPushModal(false);
      setPushTitle('');
      setPushDesc('');
      setSelectedQids(new Set());
      const updated = await getPushHistory(id);
      setPushes(updated);
    } catch {}
    setPushing(false);
  };

  const handleRemoveMember = async (studentId: string, name: string) => {
    if (!id || !confirm(`确定要将 ${name} 移出班级？`)) return;
    try {
      await removeClassMember(id, studentId);
      setMembers(prev => prev.filter(m => m.student_id !== studentId));
      setMembersTotal(prev => prev - 1);
    } catch {}
  };

  if (loading) {
    return (
      <div className="p-6 animate-fade-in">
        <Loader2 className="w-6 h-6 animate-spin text-surface-400 mx-auto mt-20" />
      </div>
    );
  }

  if (!cs) {
    return (
      <div className="p-6 animate-fade-in">
        <p className="text-surface-400 text-center mt-20">班级不存在</p>
      </div>
    );
  }

  return (
    <TeacherGuard>
      <div className="space-y-6 animate-fade-in">
        {/* Header */}
        <div className="flex items-center gap-4">
          <button onClick={() => nav('/teacher')} className="p-2 rounded-lg hover:bg-surface-100 transition-colors">
            <ChevronLeft size={20} className="text-surface-500" />
          </button>
          <div>
            <h2 className="font-display text-2xl font-bold text-surface-800">{cs.name}</h2>
            <p className="text-surface-500 text-sm mt-0.5">
              {cs.subject && <span>{cs.subject} · </span>}
              邀请码: <code className="font-mono text-primary-600">{cs.invite_code}</code> · {cs.student_count} 名学生
            </p>
          </div>
        </div>

        <div className="flex gap-6">
          {/* Left nav */}
          <div className="w-40 flex-shrink-0">
            <nav className="bg-white rounded-2xl p-2 shadow-soft space-y-0.5 sticky top-24">
              {TABS.map(t => (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-left transition-all text-sm ${
                    tab === t.id ? 'bg-brand-500/10 text-brand-600 font-medium' : 'text-gray-500 hover:bg-gray-50'
                  }`}>
                  <t.icon size={16} />{t.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Right content */}
          <div className="flex-1 min-w-0">
            {/* ── Tab: Exercises ── */}
            {tab === 'exercises' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-display text-lg font-semibold text-surface-800">推送记录</h3>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => nav(`/admin?subject=${encodeURIComponent(cs?.subject || '')}`)}
                      className="flex items-center gap-1.5 px-4 py-2 bg-surface-100 border border-surface-200 text-surface-700 rounded-xl text-sm font-medium hover:bg-surface-200 transition-colors"
                    >
                      管理题库
                    </button>
                    <button
                      onClick={() => { setShowPushModal(true); loadBankQuestions(); setSelectedQids(new Set()); setPushTitle(''); setPushDesc(''); }}
                      className="flex items-center gap-1.5 px-4 py-2 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 transition-colors"
                    >
                      <Send size={14} /> 推送练习
                    </button>
                  </div>
                </div>
                {pushes.length === 0 ? (
                  <p className="text-surface-400 text-sm py-8 text-center">还没有推送过练习</p>
                ) : (
                  <div className="space-y-3">
                    {pushes.map(p => (
                      <div key={p.id} className="p-4 bg-white rounded-xl border border-surface-200 shadow-soft">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="font-medium text-surface-700">{p.title}</p>
                            {p.description && <p className="text-xs text-surface-400 mt-0.5">{p.description}</p>}
                          </div>
                          <span className="text-xs text-surface-400">{new Date(p.created_at).toLocaleDateString()}</span>
                        </div>
                        <div className="flex items-center gap-4 mt-2 text-xs text-surface-500">
                          <span>{p.question_count} 题</span>
                          <span>{p.answered_count} 人作答</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Tab: Students ── */}
            {tab === 'students' && (
              <div className="space-y-4">
                <h3 className="font-display text-lg font-semibold text-surface-800">
                  班级成员 <span className="text-sm font-normal text-surface-400 ml-1">({membersTotal}人)</span>
                </h3>
                {members.length === 0 ? (
                  <p className="text-surface-400 text-sm py-8 text-center">暂无学生加入</p>
                ) : (
                  <div className="space-y-2">
                    {members.map(m => (
                      <div key={m.student_id} className="flex items-center justify-between p-4 bg-white rounded-xl border border-surface-200 shadow-soft">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary-400 to-accent-400 flex items-center justify-center text-white font-semibold text-sm">
                            {m.student_name.charAt(0)}
                          </div>
                          <div>
                            <p className="font-medium text-surface-700 text-sm">{m.student_name}</p>
                            <p className="text-xs text-surface-400">
                              {[m.grade, m.school].filter(Boolean).join(' · ') || '未设置'}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-surface-400">{new Date(m.joined_at).toLocaleDateString()} 加入</span>
                          <button
                            onClick={() => handleRemoveMember(m.student_id, m.student_name)}
                            className="p-1.5 rounded-lg text-surface-300 hover:text-error-500 hover:bg-error-50 transition-colors"
                            title="移除"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── Tab: Stats ── */}
            {tab === 'stats' && (
              <div className="space-y-4">
                <h3 className="font-display text-lg font-semibold text-surface-800">学情统计</h3>
                {!stats ? (
                  <p className="text-surface-400 text-sm py-8 text-center">加载中…</p>
                ) : (
                  <>
                    {/* Overview cards */}
                    <div className="grid grid-cols-4 gap-4">
                      <StatCard label="班级人数" value={stats.totalStudents} unit="人" color="primary" />
                      <StatCard label="推送次数" value={stats.totalPushes} unit="次" color="accent" />
                      <StatCard label="题目总数" value={stats.totalQuestions} unit="题" color="warning" />
                      <StatCard label="平均得分" value={stats.avgScore ?? '-'} unit={stats.avgScore != null ? '分' : ''} color="success" />
                    </div>
                    <div className="bg-white rounded-2xl p-6 shadow-soft">
                      <p className="text-sm text-surface-500">
                        累计作答 <span className="font-semibold text-surface-700">{stats.totalAnswered}</span> 次
                        {stats.avgScore != null && (
                          <span className="ml-2">
                            · 平均正确率 <span className="font-semibold text-surface-700">{stats.avgScore}%</span>
                          </span>
                        )}
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Push Modal */}
        {showPushModal && createPortal(
          <div className="fixed inset-0 z-[100] flex items-center justify-center">
            <div className="absolute inset-0 bg-black/40" onClick={() => setShowPushModal(false)} />
            <div className="relative bg-white rounded-2xl shadow-elevated p-6 w-full max-w-3xl max-h-[80vh] overflow-y-auto animate-fade-in">
              <h3 className="font-display text-lg font-semibold text-surface-800 mb-4">推送练习</h3>

              <div className="space-y-4 mb-6">
                <input
                  value={pushTitle}
                  onChange={e => setPushTitle(e.target.value)}
                  placeholder="推送标题（例如：第一周练习）*"
                  maxLength={50}
                  className="w-full px-4 py-2.5 bg-surface-50 border border-surface-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary-200"
                />
                <input
                  value={pushDesc}
                  onChange={e => setPushDesc(e.target.value)}
                  placeholder="描述（可选）"
                  maxLength={200}
                  className="w-full px-4 py-2.5 bg-surface-50 border border-surface-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-primary-200"
                />
              </div>

              {/* 快速创建题目 */}
              <div className="mb-4">
                <button
                  onClick={() => setShowCreateQ(!showCreateQ)}
                  className="text-sm text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1"
                >
                  <Plus size={14} /> 快速创建题目（学科自动设为「{cs?.subject || '未设置'}」）
                </button>
                {showCreateQ && (
                  <div className="mt-3 p-4 bg-primary-50/50 rounded-xl border border-primary-200 space-y-3 animate-fade-in">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-surface-500 mb-1 block">题型</label>
                        <select value={newQType} onChange={e => setNewQType(e.target.value)}
                          className="w-full px-3 py-2 bg-white border border-surface-200 rounded-lg text-sm">
                          <option value="choice">选择题</option>
                          <option value="fill">填空题</option>
                          <option value="truefalse">判断题</option>
                          <option value="shortanswer">解答题</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-surface-500 mb-1 block">难度</label>
                        <select value={newQDiff} onChange={e => setNewQDiff(e.target.value)}
                          className="w-full px-3 py-2 bg-white border border-surface-200 rounded-lg text-sm">
                          <option value="easy">简单</option>
                          <option value="medium">中等</option>
                          <option value="hard">困难</option>
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="text-xs text-surface-500 mb-1 block">知识点</label>
                      <input value={newQKp} onChange={e => setNewQKp(e.target.value)} placeholder="例如：二次函数"
                        className="w-full px-3 py-2 bg-white border border-surface-200 rounded-lg text-sm" />
                    </div>
                    <div>
                      <label className="text-xs text-surface-500 mb-1 block">题目内容 *</label>
                      <textarea value={newQStem} onChange={e => setNewQStem(e.target.value)} rows={2} placeholder="题干的完整内容"
                        className="w-full px-3 py-2 bg-white border border-surface-200 rounded-lg text-sm resize-none" />
                    </div>
                    <div>
                      <label className="text-xs text-surface-500 mb-1 block">答案 *</label>
                      <input value={newQAnswer} onChange={e => setNewQAnswer(e.target.value)} placeholder="正确答案"
                        className="w-full px-3 py-2 bg-white border border-surface-200 rounded-lg text-sm" />
                    </div>
                    <div>
                      <label className="text-xs text-surface-500 mb-1 block">解析（可选）</label>
                      <textarea value={newQExpl} onChange={e => setNewQExpl(e.target.value)} rows={1} placeholder="答案解析"
                        className="w-full px-3 py-2 bg-white border border-surface-200 rounded-lg text-sm resize-none" />
                    </div>
                    <div className="flex gap-2">
                      <button onClick={handleCreateQuestion} disabled={creatingQ || !newQStem.trim() || !newQAnswer.trim()}
                        className="px-4 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50">
                        {creatingQ ? '创建中…' : '创建并加入题库'}
                      </button>
                      <button onClick={() => setShowCreateQ(false)}
                        className="px-3 py-2 text-sm text-surface-500 hover:text-surface-700">取消</button>
                    </div>
                  </div>
                )}
              </div>

              <p className="text-sm text-surface-500 mb-3">
                选择题库中的题目进行推送 · 已选 <span className="font-semibold text-primary-600">{selectedQids.size}</span> 题
                {cs?.subject && <span className="ml-2 text-surface-400">· 学科筛选: {cs.subject}</span>}
              </p>

              <div className="space-y-2 max-h-64 overflow-y-auto mb-6">
                {bankQuestions.length === 0 ? (
                  <p className="text-surface-400 text-sm py-4 text-center">暂无可推送的题目，请先在后台管理中发布题目</p>
                ) : (
                  bankQuestions.map(q => {
                    const stem = typeof q.content === 'object' && q.content ? (q.content as any).stem || '' : '';
                    const isSelected = selectedQids.has(q.id);
                    return (
                      <label
                        key={q.id}
                        className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                          isSelected ? 'border-primary-400 bg-primary-50' : 'border-surface-200 hover:border-surface-300'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => {
                            setSelectedQids(prev => {
                              const next = new Set(prev);
                              isSelected ? next.delete(q.id) : next.add(q.id);
                              return next;
                            });
                          }}
                          className="w-4 h-4 rounded accent-primary-600"
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-surface-700 truncate">{stem || '(无题干)'}</p>
                          <span className="text-[10px] text-surface-400">{q.knowledge_point || q.subject}</span>
                        </div>
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-surface-100 text-surface-500">{q.type}</span>
                      </label>
                    );
                  })
                )}
              </div>

              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => setShowPushModal(false)}
                  className="px-4 py-2 text-sm text-surface-500 hover:text-surface-700"
                >
                  取消
                </button>
                <button
                  onClick={handlePush}
                  disabled={pushing || !pushTitle.trim() || selectedQids.size === 0}
                  className="px-6 py-2 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors"
                >
                  {pushing ? '推送中…' : `确认推送 (${selectedQids.size}题)`}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
      </div>
    </TeacherGuard>
  );
}

function StatCard({ label, value, unit, color }: { label: string; value: string | number; unit: string; color: string }) {
  const bgMap: Record<string, string> = {
    primary: 'bg-primary-50 ring-1 ring-primary-100',
    accent: 'bg-accent-50 ring-1 ring-accent-100',
    warning: 'bg-warning-50 ring-1 ring-warning-100',
    success: 'bg-success-50 ring-1 ring-success-100',
  };
  const textMap: Record<string, string> = {
    primary: 'text-primary-600',
    accent: 'text-accent-600',
    warning: 'text-warning-600',
    success: 'text-success-600',
  };
  return (
    <div className={`rounded-2xl p-5 ${bgMap[color] || bgMap.primary} shadow-soft`}>
      <p className="text-sm text-surface-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${textMap[color] || textMap.primary}`}>
        {value}{unit && <span className="text-sm font-normal ml-1">{unit}</span>}
      </p>
    </div>
  );
}
