import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Database, GitGraph, BarChart3, Settings, Activity,
  Plus, Edit3, Trash2, Upload, Download, CheckCircle, XCircle, Search, ChevronDown, Filter,
  Tag, ShieldCheck, ShieldX, ShieldAlert, Send, TrendingUp, Target, Users, MessageSquare,
} from 'lucide-react';
import ReactEChartsCore from 'echarts-for-react';
import { useAuthStore } from '../store/authStore';
import * as adminApi from '../api/admin';
import type { AdminQuestion, AdminKP, ConfigItem, GraphData, TagInfo } from '../api/admin';

const TABS = [
  { id: 'questions', label: '题库管理', icon: Database },
  { id: 'knowledge', label: '知识图谱', icon: GitGraph },
  { id: 'stats', label: '数据统计', icon: BarChart3 },
  { id: 'config', label: '系统配置', icon: Settings },
  { id: 'monitor', label: '模型监控', icon: Activity },
] as const;

const QUESTION_TYPES = ['choice', 'fill', 'truefalse', 'shortanswer'];
const TYPE_LABELS: Record<string, string> = { choice: '选择题', fill: '填空题', truefalse: '判断题', shortanswer: '解答题' };
const DIFF_LABELS: Record<string, string> = { easy: '简单', medium: '中等', hard: '困难', challenge: '挑战' };
const STATUS_LABELS: Record<string, string> = { draft: '草稿', published: '已发布', archived: '已归档' };

function AdminGuard({ children }: { children: React.ReactNode }) {
  const role = useAuthStore(s => s.learner?.role);
  const nav = useNavigate();
  useEffect(() => { if (role && !['admin', 'teacher'].includes(role)) nav('/'); }, [role, nav]);
  if (!role || !['admin', 'teacher'].includes(role)) return null;
  return <>{children}</>;
}

export default function AdminDashboard() {
  const [tab, setTab] = useState('questions');

  return (
    <AdminGuard>
      <div className="space-y-6 animate-fade-in">
        <div>
          <h2 className="font-display text-2xl font-bold text-surface-800 dark:text-gray-100">后台管理</h2>
          <p className="text-surface-500 dark:text-gray-400 mt-1">题库 · 知识图谱 · 数据统计 · 系统配置</p>
        </div>

        <div className="flex gap-6">
          {/* Left nav */}
          <div className="w-44 flex-shrink-0">
            <nav className="bg-white dark:bg-surface-700 rounded-2xl p-2 shadow-soft space-y-0.5 sticky top-24">
              {TABS.map(t => (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-left transition-all text-sm ${
                    tab === t.id ? 'bg-brand-500/10 dark:bg-brand-500/20 text-brand-600 dark:text-brand-400 font-medium' : 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-surface-600'
                  }`}>
                  <t.icon size={16} />{t.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Right content */}
          <div className="flex-1 min-w-0 bg-white dark:bg-surface-700 rounded-2xl p-6 shadow-soft">
            {tab === 'questions' && <QuestionsTab />}
            {tab === 'knowledge' && <KnowledgeTab />}
            {tab === 'stats' && <StatsTab />}
            {tab === 'config' && <ConfigTab />}
            {tab === 'monitor' && <MonitorTab />}
          </div>
        </div>
      </div>
    </AdminGuard>
  );
}

/* ===================================================================
 * Tab: Questions
 * =================================================================== */
function QuestionsTab() {
  const [questions, setQuestions] = useState<AdminQuestion[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ subject: '', type: '', difficulty: '', status: 'published', review_status: '', tags: '', search: '' });
  const [editing, setEditing] = useState<AdminQuestion | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [reviewing, setReviewing] = useState<AdminQuestion | null>(null);
  const [showTagManager, setShowTagManager] = useState(false);
  const [allTags, setAllTags] = useState<TagInfo[]>([]);
  const [calibrating, setCalibrating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = { ...filters, page, page_size: 20 };
      const res = await adminApi.listQuestions(params);
      setQuestions(res.questions);
      setTotal(res.pagination.total);
    } catch { /* noop */ }
    setLoading(false);
  }, [filters, page]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => { adminApi.listQuestionTags().then(r => setAllTags(r.tags)).catch(() => {}); }, [questions]);

  const handleImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const text = await file.text();
      try {
        const items = JSON.parse(text);
        const res = await adminApi.batchImport(Array.isArray(items) ? items : [items]);
        alert(`导入成功：${res.imported} 题`);
        load();
      } catch { alert('JSON 格式错误'); }
    };
    input.click();
  };

  const handleExport = async () => {
    const res = await adminApi.exportQuestions(filters.subject);
    const blob = new Blob([JSON.stringify(res.questions, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `questions_${new Date().toISOString().slice(0,10)}.json`; a.click();
    URL.revokeObjectURL(url);
  };

  const handleReview = async (q: AdminQuestion, action: string, comment?: string) => {
    try {
      await adminApi.reviewQuestion(q.id, { action, comment });
      setReviewing(null);
      load();
    } catch (e: any) { alert(e?.message || '操作失败'); }
  };

  const handleCalibrate = async () => {
    setCalibrating(true);
    try {
      const res = await adminApi.calibrateDifficulty();
      alert(`校准完成：已校准 ${res.calibrated} 题，${res.skipped} 题跳过（无数据）`);
      load();
    } catch (e: any) { alert(e?.message || '校准失败'); }
    setCalibrating(false);
  };

  const REVIEW_LABELS: Record<string, { label: string; color: string }> = {
    pending_review: { label: '待审核', color: 'text-yellow-600 bg-yellow-50 dark:bg-yellow-500/10 dark:text-yellow-400' },
    approved: { label: '已通过', color: 'text-green-600 bg-green-50 dark:bg-green-500/10 dark:text-green-400' },
    rejected: { label: '已驳回', color: 'text-red-600 bg-red-50 dark:bg-red-500/10 dark:text-red-400' },
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-display text-lg font-semibold text-gray-800 dark:text-gray-100">题库管理</h3>
        <div className="flex gap-2">
          <button onClick={() => setShowTagManager(true)} className="flex items-center gap-1.5 px-3 py-2 bg-gray-50 dark:bg-surface-600 border border-gray-200 dark:border-gray-500 rounded-lg text-xs font-medium hover:bg-gray-100 dark:hover:bg-surface-500 transition-colors"><Tag size={14} />标签管理</button>
          <button onClick={handleCalibrate} disabled={calibrating} className="flex items-center gap-1.5 px-3 py-2 bg-gray-50 dark:bg-surface-600 border border-gray-200 dark:border-gray-500 rounded-lg text-xs font-medium hover:bg-gray-100 dark:hover:bg-surface-500 transition-colors"><TrendingUp size={14} />{calibrating ? '校准中...' : '难度校准'}</button>
          <button onClick={handleImport} className="flex items-center gap-1.5 px-3 py-2 bg-gray-50 dark:bg-surface-600 border border-gray-200 dark:border-gray-500 rounded-lg text-xs font-medium hover:bg-gray-100 dark:hover:bg-surface-500 transition-colors"><Upload size={14} />批量导入</button>
          <button onClick={handleExport} className="flex items-center gap-1.5 px-3 py-2 bg-gray-50 dark:bg-surface-600 border border-gray-200 dark:border-gray-500 rounded-lg text-xs font-medium hover:bg-gray-100 dark:hover:bg-surface-500 transition-colors"><Download size={14} />导出</button>
          <button onClick={() => setShowCreate(true)} className="flex items-center gap-1.5 px-3 py-2 bg-brand-500 text-white rounded-lg text-xs font-medium hover:bg-brand-600 transition-colors"><Plus size={14} />新建题目</button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <input placeholder="搜索题目内容..." value={filters.search} onChange={e => { setFilters(f => ({ ...f, search: e.target.value })); setPage(1); }}
          className="px-3 py-2 bg-gray-50 dark:bg-surface-600 border border-gray-200 dark:border-gray-500 rounded-lg text-xs w-48" />
        <SelectSm value={filters.subject} onChange={v => { setFilters(f => ({ ...f, subject: v })); setPage(1); }} options={[
          { value: '', label: '全部学科' }, { value: '高中数学', label: '高中数学' }, { value: '高中物理', label: '高中物理' }, { value: '高中英语', label: '高中英语' },
        ]} />
        <SelectSm value={filters.type} onChange={v => { setFilters(f => ({ ...f, type: v })); setPage(1); }} options={[
          { value: '', label: '全部题型' }, ...QUESTION_TYPES.map(t => ({ value: t, label: TYPE_LABELS[t] })),
        ]} />
        <SelectSm value={filters.difficulty} onChange={v => { setFilters(f => ({ ...f, difficulty: v })); setPage(1); }} options={[
          { value: '', label: '全部难度' }, { value: 'easy', label: '简单' }, { value: 'medium', label: '中等' }, { value: 'hard', label: '困难' }, { value: 'challenge', label: '挑战' },
        ]} />
        <SelectSm value={filters.status} onChange={v => { setFilters(f => ({ ...f, status: v })); setPage(1); }} options={[
          { value: '', label: '全部状态' }, { value: 'published', label: '已发布' }, { value: 'draft', label: '草稿' }, { value: 'archived', label: '已归档' },
        ]} />
        <SelectSm value={filters.review_status} onChange={v => { setFilters(f => ({ ...f, review_status: v })); setPage(1); }} options={[
          { value: '', label: '全部审核状态' }, { value: 'pending_review', label: '待审核' }, { value: 'approved', label: '已通过' }, { value: 'rejected', label: '已驳回' },
        ]} />
        <SelectSm value={filters.tags} onChange={v => { setFilters(f => ({ ...f, tags: v })); setPage(1); }} options={[
          { value: '', label: '全部标签' }, ...allTags.map(t => ({ value: t.name, label: `${t.name} (${t.count})` })),
        ]} />
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-600 text-left">
              <th className="pb-2 font-medium text-gray-500 dark:text-gray-400 w-16">题型</th>
              <th className="pb-2 font-medium text-gray-500 dark:text-gray-400">内容</th>
              <th className="pb-2 font-medium text-gray-500 dark:text-gray-400 w-16">难度</th>
              <th className="pb-2 font-medium text-gray-500 dark:text-gray-400 w-16">状态</th>
              <th className="pb-2 font-medium text-gray-500 dark:text-gray-400 w-16">审核</th>
              <th className="pb-2 font-medium text-gray-500 dark:text-gray-400 w-28">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={6} className="py-8 text-center text-gray-400">加载中...</td></tr>}
            {!loading && questions.length === 0 && <tr><td colSpan={6} className="py-8 text-center text-gray-400">暂无题目</td></tr>}
            {questions.map(q => (
              <tr key={q.id} className="border-b border-gray-50 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-surface-600 transition-colors">
                <td className="py-2.5 text-xs text-gray-500">{TYPE_LABELS[q.type] || q.type}</td>
                <td className="py-2.5">
                  <div className="text-gray-700 dark:text-gray-200 truncate max-w-xs">{q.content?.stem as string || '(空)'}</div>
                  <div className="text-xs text-gray-400 mt-0.5">{q.knowledge_point} · {q.subject}</div>
                  {q.calibrated_difficulty != null && (
                    <div className="text-xs text-accent-600 dark:text-accent-400 mt-0.5">校准难度: {Math.round(q.calibrated_difficulty * 100)}%</div>
                  )}
                </td>
                <td className="py-2.5"><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${q.difficulty === 'easy' ? 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400' : q.difficulty === 'hard' ? 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400' : 'bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400'}`}>{DIFF_LABELS[q.difficulty] || q.difficulty}</span></td>
                <td className="py-2.5"><span className={`text-xs ${q.status === 'published' ? 'text-green-600' : q.status === 'draft' ? 'text-yellow-600' : 'text-gray-400'}`}>{STATUS_LABELS[q.status] || q.status}</span></td>
                <td className="py-2.5">
                  {q.review_status ? (
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${REVIEW_LABELS[q.review_status]?.color || 'text-gray-400'}`}>
                      {REVIEW_LABELS[q.review_status]?.label || q.review_status}
                    </span>
                  ) : <span className="text-xs text-gray-400">—</span>}
                </td>
                <td className="py-2.5">
                  <div className="flex gap-1 flex-wrap">
                    {!q.review_status && q.status === 'draft' && (
                      <button onClick={() => handleReview(q, 'submit')} className="p-1 rounded hover:bg-brand-50 dark:hover:bg-brand-500/10 text-gray-400 hover:text-brand-500" title="提交审核"><Send size={13} /></button>
                    )}
                    {q.review_status === 'pending_review' && (
                      <>
                        <button onClick={() => handleReview(q, 'approve')} className="p-1 rounded hover:bg-green-50 dark:hover:bg-green-500/10 text-gray-400 hover:text-green-500" title="通过"><CheckCircle size={13} /></button>
                        <button onClick={() => setReviewing(q)} className="p-1 rounded hover:bg-red-50 dark:hover:bg-red-500/10 text-gray-400 hover:text-red-500" title="驳回"><XCircle size={13} /></button>
                      </>
                    )}
                    {q.review_status === 'rejected' && (
                      <button onClick={() => handleReview(q, 'submit')} className="p-1 rounded hover:bg-brand-50 dark:hover:bg-brand-500/10 text-gray-400 hover:text-brand-500" title="重新提交"><Send size={13} /></button>
                    )}
                    <button onClick={() => setEditing(q)} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-surface-500 text-gray-400 hover:text-gray-600"><Edit3 size={13} /></button>
                    <button onClick={async () => { await adminApi.deleteQuestion(q.id); load(); }} className="p-1 rounded hover:bg-red-50 dark:hover:bg-red-500/10 text-gray-400 hover:text-red-500"><Trash2 size={13} /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > 20 && (
        <div className="flex items-center justify-between text-xs text-gray-500 pt-2">
          <span>共 {total} 题</span>
          <div className="flex gap-1">
            <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page <= 1} className="px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-surface-600 disabled:opacity-30">上一页</button>
            <span className="px-2 py-1">{page} / {Math.ceil(total / 20)}</span>
            <button onClick={() => setPage(p => p + 1)} disabled={page >= Math.ceil(total / 20)} className="px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-surface-600 disabled:opacity-30">下一页</button>
          </div>
        </div>
      )}

      {/* Edit modal */}
      {editing && <QuestionEditModal question={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
      {/* Create modal */}
      {showCreate && <QuestionEditModal onClose={() => setShowCreate(false)} onSaved={() => { setShowCreate(false); load(); }} />}
      {/* Reject modal */}
      {reviewing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setReviewing(null)}>
          <div className="bg-white dark:bg-surface-800 rounded-2xl p-6 shadow-elevated w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <h3 className="font-display text-lg font-semibold mb-4">驳回题目</h3>
            <div><label className="text-xs text-gray-500 mb-1 block">驳回理由（必填）</label>
              <textarea id="reject-comment" rows={3} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm resize-none" placeholder="请说明驳回原因..." /></div>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setReviewing(null)} className="px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-surface-600 rounded-lg">取消</button>
              <button onClick={() => {
                const comment = (document.getElementById('reject-comment') as HTMLTextAreaElement)?.value;
                if (!comment?.trim()) { alert('请填写驳回理由'); return; }
                handleReview(reviewing, 'reject', comment);
              }} className="px-4 py-2 bg-red-500 text-white text-sm rounded-lg hover:bg-red-600">驳回</button>
            </div>
          </div>
        </div>
      )}
      {/* Tag manager modal */}
      {showTagManager && <TagManagerModal tags={allTags} onClose={() => setShowTagManager(false)} onRefresh={() => adminApi.listQuestionTags().then(r => setAllTags(r.tags)).catch(() => {})} questions={questions} onSaved={load} />}
    </div>
  );
}

function QuestionEditModal({ question, onClose, onSaved }: { question?: AdminQuestion; onClose: () => void; onSaved: () => void }) {
  const [stem, setStem] = useState(question?.content?.stem as string || '');
  const [answer, setAnswer] = useState(question?.content?.answer as string || '');
  const [explanation, setExplanation] = useState(question?.content?.explanation as string || '');
  const [subject, setSubject] = useState(question?.subject || '');
  const [kp, setKp] = useState(question?.knowledge_point || '');
  const [type, setType] = useState(question?.type || 'choice');
  const [difficulty, setDifficulty] = useState(question?.difficulty || 'medium');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    const content = { stem, answer, explanation };
    try {
      if (question) {
        await adminApi.updateQuestion(question.id, { subject, knowledge_point: kp, type, difficulty, content });
      } else {
        await adminApi.createQuestion({ subject, knowledge_point: kp, type, difficulty, content });
      }
      onSaved();
    } catch (e: any) { alert(e?.message || '保存失败'); }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="bg-white dark:bg-surface-800 rounded-2xl p-6 shadow-elevated w-full max-w-lg max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h3 className="font-display text-lg font-semibold mb-4">{question ? '编辑题目' : '新建题目'}</h3>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div><label className="text-xs text-gray-500 mb-1 block">学科</label><input value={subject} onChange={e => setSubject(e.target.value)} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" /></div>
            <div><label className="text-xs text-gray-500 mb-1 block">知识点</label><input value={kp} onChange={e => setKp(e.target.value)} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="text-xs text-gray-500 mb-1 block">题型</label>
              <select value={type} onChange={e => setType(e.target.value)} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm">
                {QUESTION_TYPES.map(t => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
              </select>
            </div>
            <div><label className="text-xs text-gray-500 mb-1 block">难度</label>
              <select value={difficulty} onChange={e => setDifficulty(e.target.value)} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm">
                {['easy','medium','hard','challenge'].map(d => <option key={d} value={d}>{DIFF_LABELS[d]}</option>)}
              </select>
            </div>
          </div>
          <div><label className="text-xs text-gray-500 mb-1 block">题目内容</label><textarea value={stem} onChange={e => setStem(e.target.value)} rows={3} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm resize-none" /></div>
          <div><label className="text-xs text-gray-500 mb-1 block">答案</label><input value={answer} onChange={e => setAnswer(e.target.value)} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" /></div>
          <div><label className="text-xs text-gray-500 mb-1 block">解析</label><textarea value={explanation} onChange={e => setExplanation(e.target.value)} rows={2} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm resize-none" /></div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-surface-600 rounded-lg">取消</button>
          <button onClick={save} disabled={saving} className="px-4 py-2 bg-brand-500 text-white text-sm rounded-lg hover:bg-brand-600 disabled:opacity-50">{saving ? '保存中...' : '保存'}</button>
        </div>
      </div>
    </div>
  );
}

/* ===================================================================
 * Tab: Knowledge Graph
 * =================================================================== */
function KnowledgeTab() {
  const [kps, setKps] = useState<AdminKP[]>([]);
  const [subject, setSubject] = useState('高中数学');
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [selected, setSelected] = useState<AdminKP | null>(null);
  const [editing, setEditing] = useState<AdminKP | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    try {
      const [listRes, graphRes] = await Promise.all([
        adminApi.listKPs({ subject }),
        adminApi.getGraph(subject),
      ]);
      setKps(listRes.knowledge_points);
      setGraph(graphRes);
    } catch { /* noop */ }
  }, [subject]);

  useEffect(() => { load(); }, [load]);

  const handleValidate = async () => {
    const res = await adminApi.validateGraph(subject);
    alert(res.message);
  };

  // Build echarts graph option
  const chapters = [...new Set((graph?.nodes || []).map(n => n.chapter).filter(Boolean) as string[])];
  const diffColors: Record<string, string> = { easy: '#22c55e', medium: '#6366f1', hard: '#f97316', challenge: '#ef4444' };

  const graphOption = graph ? {
    tooltip: {
      trigger: 'item' as const,
      formatter: (params: any) => {
        if (params.dataType === 'node') {
          return `<b>${params.name}</b><br/>难度: ${params.data.difficulty}<br/>重要度: ${'★'.repeat(params.data.importance)}<br/>章节: ${params.data.chapter || '未分类'}`;
        }
        return `${params.data.source} → ${params.data.target}`;
      },
    },
    legend: chapters.length > 0 ? { data: chapters, top: 10, textStyle: { fontSize: 11 } } : undefined,
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      force: { repulsion: 300, edgeLength: [100, 200], gravity: 0.1 },
      data: graph.nodes.map(n => ({
        id: n.id,
        name: n.name,
        difficulty: n.difficulty,
        importance: n.importance,
        chapter: n.chapter || '未分类',
        symbolSize: 8 + n.importance * 2.5,
        itemStyle: { color: diffColors[n.difficulty] || '#6366f1' },
        category: n.chapter || '未分类',
        label: { show: true, position: 'right' as const, fontSize: 10, color: '#666' },
      })),
      edges: graph.edges.map(e => ({
        source: e.source,
        target: e.target,
        lineStyle: { color: '#cbd5e1', width: 1.5, curveness: 0.2 },
        symbol: ['none', 'triangle'],
        symbolSize: [0, 8],
      })),
      categories: chapters.map(c => ({ name: c })),
      emphasis: { focus: 'adjacency' as const, lineStyle: { width: 3 } },
      label: { show: true, position: 'right' as const, fontSize: 10, color: '#374151' },
    }],
    animationDuration: 1500,
    animationEasingUpdate: 'quinticInOut' as const,
  } : null;

  const onGraphEvents = {
    click: (params: any) => {
      if (params.dataType === 'node') {
        const kp = kps.find(k => k.id === params.data.id);
        if (kp) setSelected(kp);
      }
    },
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-display text-lg font-semibold text-gray-800 dark:text-gray-100">知识图谱</h3>
        <div className="flex gap-2">
          <SelectSm value={subject} onChange={setSubject} options={[
            { value: '高中数学', label: '高中数学' }, { value: '高中物理', label: '高中物理' }, { value: '高中英语', label: '高中英语' },
          ]} />
          <button onClick={handleValidate} className="px-3 py-2 bg-gray-50 dark:bg-surface-600 border border-gray-200 dark:border-gray-500 rounded-lg text-xs font-medium hover:bg-gray-100 transition-colors">校验DAG</button>
          <button onClick={() => setShowCreate(true)} className="flex items-center gap-1 px-3 py-2 bg-brand-500 text-white rounded-lg text-xs font-medium hover:bg-brand-600 transition-colors"><Plus size={14} />新增知识点</button>
        </div>
      </div>

      <div className="flex gap-6">
        {/* Left: Graph visualization */}
        <div className="flex-1 min-w-0 border border-gray-100 dark:border-gray-600 rounded-xl overflow-hidden bg-gray-50 dark:bg-surface-800" style={{ minHeight: 420 }}>
          {graphOption ? (
            <ReactEChartsCore option={graphOption} style={{ height: 420 }} onEvents={onGraphEvents} notMerge={true} />
          ) : (
            <div className="flex items-center justify-center h-[420px] text-gray-400 text-sm">加载图谱数据中...</div>
          )}
          {graph && (
            <div className="flex gap-4 px-4 py-2 bg-white dark:bg-surface-700 border-t border-gray-100 dark:border-gray-600 text-xs text-gray-500">
              <span>节点: {graph.nodes.length}</span>
              <span>边: {graph.edges.length}</span>
              <span className="flex items-center gap-3 ml-auto">
                {Object.entries(diffColors).map(([d, c]) => (
                  <span key={d} className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full inline-block" style={{ backgroundColor: c }} />{DIFF_LABELS[d]}</span>
                ))}
              </span>
            </div>
          )}
        </div>

        {/* Right: Node list + detail */}
        <div className="w-72 flex-shrink-0 flex flex-col gap-4">
          {/* Node list */}
          <div className="border border-gray-100 dark:border-gray-600 rounded-xl overflow-hidden">
            <div className="px-3 py-2 bg-gray-50 dark:bg-surface-600 border-b border-gray-100 dark:border-gray-500 text-xs font-medium text-gray-500">知识点列表</div>
            <div className="max-h-64 overflow-y-auto">
              {kps.map(kp => (
                <button key={kp.id} onClick={() => setSelected(kp)}
                  className={`w-full text-left px-3 py-2 text-xs transition-colors border-b border-gray-50 dark:border-gray-700 last:border-0 ${selected?.id === kp.id ? 'bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-surface-600'}`}>
                  <div className="font-medium truncate">{kp.name}</div>
                  <div className="text-gray-400 mt-0.5">{kp.chapter || kp.subject} · 重要度 {'★'.repeat(kp.importance)}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Detail panel */}
          <div className="border border-gray-100 dark:border-gray-600 rounded-xl p-4 flex-1 min-h-32">
            {selected ? (
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h4 className="font-semibold text-sm text-gray-800 dark:text-gray-100">{selected.name}</h4>
                    <p className="text-xs text-gray-500 mt-1">{selected.description || '暂无描述'}</p>
                  </div>
                  <div className="flex gap-1">
                    <button onClick={() => setEditing(selected)} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-surface-600 text-gray-400"><Edit3 size={14} /></button>
                    <button onClick={async () => { await adminApi.deleteKP(selected.id); setSelected(null); load(); }} className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 text-gray-400 hover:text-red-500"><Trash2 size={14} /></button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="bg-gray-50 dark:bg-surface-600 rounded-lg p-2"><span className="text-gray-400">难度</span><div className="font-medium text-gray-700 dark:text-gray-200">{DIFF_LABELS[selected.difficulty] || selected.difficulty}</div></div>
                  <div className="bg-gray-50 dark:bg-surface-600 rounded-lg p-2"><span className="text-gray-400">重要度</span><div className="font-medium text-gray-700 dark:text-gray-200">{'★'.repeat(selected.importance)}{'☆'.repeat(Math.max(0, 10 - selected.importance))}</div></div>
                </div>
                <div>
                  <p className="text-xs text-gray-500 mb-1">前置依赖 ({(selected.prerequisites || []).length} 个)</p>
                  <div className="flex flex-wrap gap-1">
                    {(selected.prerequisites || []).map(pid => {
                      const pre = kps.find(k => k.id === pid);
                      return <span key={pid} className="px-2 py-0.5 bg-gray-100 dark:bg-surface-600 rounded text-xs text-gray-600 dark:text-gray-300">{pre?.name || pid.slice(0, 12)}</span>;
                    })}
                    {(!selected.prerequisites || selected.prerequisites.length === 0) && <span className="text-xs text-gray-400">无（根节点）</span>}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-gray-500 mb-1">后置依赖</p>
                  <div className="flex flex-wrap gap-1">
                    {(() => {
                      const children = kps.filter(k => (k.prerequisites || []).includes(selected.id));
                      if (children.length === 0) return <span className="text-xs text-gray-400">无（叶子节点）</span>;
                      return children.map(c => <span key={c.id} className="px-2 py-0.5 bg-brand-50 dark:bg-brand-500/10 rounded text-xs text-brand-600 dark:text-brand-400">{c.name}</span>);
                    })()}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-gray-400 text-xs text-center">
                <GitGraph size={24} className="mb-2 opacity-30" />
                <p>点击图谱节点或左侧列表</p><p>查看知识点详情</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setEditing(null)}>
          <div className="bg-white dark:bg-surface-800 rounded-2xl p-6 shadow-elevated w-full max-w-md" onClick={e => e.stopPropagation()}>
            <h3 className="font-display text-lg font-semibold mb-4">编辑知识点</h3>
            <div className="space-y-3">
              <div><label className="text-xs text-gray-500 mb-1 block">名称</label><input value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" /></div>
              <div><label className="text-xs text-gray-500 mb-1 block">描述</label><textarea value={editing.description || ''} onChange={e => setEditing({ ...editing, description: e.target.value })} rows={2} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="text-xs text-gray-500 mb-1 block">难度</label>
                  <select value={editing.difficulty} onChange={e => setEditing({ ...editing, difficulty: e.target.value })} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm">
                    {['easy','medium','hard','challenge'].map(d => <option key={d} value={d}>{DIFF_LABELS[d]}</option>)}
                  </select>
                </div>
                <div><label className="text-xs text-gray-500 mb-1 block">重要度 (1-10)</label><input type="number" min={1} max={10} value={editing.importance} onChange={e => setEditing({ ...editing, importance: parseInt(e.target.value) || 5 })} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" /></div>
              </div>
              <div><label className="text-xs text-gray-500 mb-1 block">章节</label><input value={editing.chapter || ''} onChange={e => setEditing({ ...editing, chapter: e.target.value })} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" /></div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setEditing(null)} className="px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-surface-600 rounded-lg">取消</button>
              <button onClick={async () => { await adminApi.updateKP(editing.id, { name: editing.name, description: editing.description, difficulty: editing.difficulty, importance: editing.importance, chapter: editing.chapter }); setEditing(null); load(); }} className="px-4 py-2 bg-brand-500 text-white text-sm rounded-lg hover:bg-brand-600">保存</button>
            </div>
          </div>
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setShowCreate(false)}>
          <CreateKPModal subject={subject} onClose={() => setShowCreate(false)} onSaved={() => { setShowCreate(false); load(); }} />
        </div>
      )}
    </div>
  );
}

function CreateKPModal({ subject, onClose, onSaved }: { subject: string; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState('');
  const [chapter, setChapter] = useState('');
  const [difficulty, setDifficulty] = useState('medium');
  const [importance, setImportance] = useState(5);
  const [desc, setDesc] = useState('');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!name.trim()) return;
    setSaving(true);
    await adminApi.createKP({ subject, name: name.trim(), chapter: chapter.trim(), difficulty, importance, description: desc.trim() });
    setSaving(false);
    onSaved();
  };

  return (
    <div className="bg-white dark:bg-surface-800 rounded-2xl p-6 shadow-elevated w-full max-w-md" onClick={e => e.stopPropagation()}>
      <h3 className="font-display text-lg font-semibold mb-4">新增知识点</h3>
      <div className="space-y-3">
        <div><label className="text-xs text-gray-500 mb-1 block">名称 *</label><input value={name} onChange={e => setName(e.target.value)} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" autoFocus /></div>
        <div><label className="text-xs text-gray-500 mb-1 block">章节</label><input value={chapter} onChange={e => setChapter(e.target.value)} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><label className="text-xs text-gray-500 mb-1 block">难度</label>
            <select value={difficulty} onChange={e => setDifficulty(e.target.value)} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm">
              {['easy','medium','hard','challenge'].map(d => <option key={d} value={d}>{DIFF_LABELS[d]}</option>)}
            </select>
          </div>
          <div><label className="text-xs text-gray-500 mb-1 block">重要度</label><input type="number" min={1} max={10} value={importance} onChange={e => setImportance(parseInt(e.target.value) || 5)} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" /></div>
        </div>
        <div><label className="text-xs text-gray-500 mb-1 block">描述</label><textarea value={desc} onChange={e => setDesc(e.target.value)} rows={2} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" /></div>
      </div>
      <div className="flex justify-end gap-2 mt-5">
        <button onClick={onClose} className="px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-surface-600 rounded-lg">取消</button>
        <button onClick={save} disabled={saving || !name.trim()} className="px-4 py-2 bg-brand-500 text-white text-sm rounded-lg hover:bg-brand-600 disabled:opacity-50">创建</button>
      </div>
    </div>
  );
}

/* ===================================================================
 * Tab: Stats
 * =================================================================== */
function StatsTab() {
  const [overview, setOverview] = useState({ total_learners: 0, active_today: 0, total_sessions: 0, total_messages: 0 });
  const [users, setUsers] = useState<Array<Record<string, unknown>>>([]);
  const [trend, setTrend] = useState<Array<{ date: string; count: number }>>([]);

  useEffect(() => {
    adminApi.getStatsOverview().then(setOverview).catch(() => {});
    adminApi.getStatsUsers({ sort_by: 'updated_at', page: 1, page_size: 20 }).then(r => setUsers(r.users)).catch(() => {});
    adminApi.getStatsDaily(30).then(r => setTrend(r.trend)).catch(() => {});
  }, []);

  const maxCount = Math.max(1, ...trend.map(t => t.count));

  return (
    <div className="space-y-6">
      <h3 className="font-display text-lg font-semibold text-gray-800 dark:text-gray-100">数据统计</h3>

      {/* Overview cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: '总用户', value: overview.total_learners, color: 'bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400' },
          { label: '今日活跃', value: overview.active_today, color: 'bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400' },
          { label: '总会话', value: overview.total_sessions, color: 'bg-accent-50 dark:bg-accent-500/10 text-accent-600 dark:text-accent-400' },
          { label: '总消息', value: overview.total_messages, color: 'bg-warning-50 dark:bg-warning-500/10 text-warning-600 dark:text-warning-400' },
        ].map(card => (
          <div key={card.label} className={`rounded-2xl p-4 ${card.color}`}>
            <div className="text-xs opacity-70">{card.label}</div>
            <div className="text-2xl font-bold mt-1">{card.value.toLocaleString()}</div>
          </div>
        ))}
      </div>

      {/* Trend sparkline */}
      <div>
        <p className="text-xs font-medium text-gray-500 mb-3">近30天消息趋势</p>
        <div className="h-32 flex items-end gap-0.5">
          {trend.map((t, i) => (
            <div key={i} className="flex-1 bg-brand-400 dark:bg-brand-500 rounded-t-sm hover:bg-brand-500 transition-colors"
              style={{ height: `${Math.max(4, (t.count / maxCount) * 100)}%` }}
              title={`${t.date}: ${t.count} 条`} />
          ))}
        </div>
      </div>

      {/* User table */}
      <div>
        <p className="text-xs font-medium text-gray-500 mb-2">用户活跃排行</p>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-600 text-left">
              <th className="pb-2 font-medium text-gray-400 w-8">#</th>
              <th className="pb-2 font-medium text-gray-400">昵称</th>
              <th className="pb-2 font-medium text-gray-400">角色</th>
              <th className="pb-2 font-medium text-gray-400">年级</th>
              <th className="pb-2 font-medium text-gray-400">会话数</th>
              <th className="pb-2 font-medium text-gray-400">消息数</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u, i) => (
              <tr key={u.id as string} className="border-b border-gray-50 dark:border-gray-700">
                <td className="py-2 text-gray-400">{i + 1}</td>
                <td className="py-2 text-gray-700 dark:text-gray-200">{u.nickname as string}</td>
                <td className="py-2 text-xs text-gray-500">{u.role as string}</td>
                <td className="py-2 text-xs text-gray-500">{(u.grade as string) || '—'}</td>
                <td className="py-2 text-xs">{u.session_count as number}</td>
                <td className="py-2 text-xs">{u.message_count as number}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ===================================================================
 * Tab: Config
 * =================================================================== */
function ConfigTab() {
  const [configs, setConfigs] = useState<Record<string, ConfigItem[]>>({});
  const [editing, setEditing] = useState<ConfigItem | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const load = async () => {
    const res = await adminApi.listConfig();
    setConfigs(res.configs);
  };
  useEffect(() => { load(); }, []);

  const handleDelete = async (key: string) => {
    if (!confirm(`确定删除配置项 "${key}"？`)) return;
    try {
      await adminApi.deleteConfig(key);
      load();
    } catch (e: any) { alert(e?.message || '删除失败'); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="font-display text-lg font-semibold text-gray-800 dark:text-gray-100">系统配置</h3>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-1.5 px-3 py-2 bg-brand-500 text-white rounded-lg text-xs font-medium hover:bg-brand-600 transition-colors"><Plus size={14} />新增配置</button>
      </div>

      {Object.entries(configs).map(([cat, items]) => (
        <div key={cat}>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">{cat}</p>
          <div className="space-y-2">
            {items.map(cfg => (
              <div key={cfg.key} className="flex items-center justify-between py-2.5 px-4 bg-gray-50 dark:bg-surface-600 rounded-xl">
                <div>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-200">{cfg.key}</p>
                  <p className="text-xs text-gray-400">{cfg.description}</p>
                </div>
                <div className="flex items-center gap-2">
                  <code className="text-xs bg-white dark:bg-surface-700 px-2 py-1 rounded font-mono text-gray-600 dark:text-gray-300 max-w-48 truncate">{cfg.value}</code>
                  <button onClick={() => setEditing(cfg)} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-surface-500 text-gray-400"><Edit3 size={13} /></button>
                  <button onClick={() => handleDelete(cfg.key)} className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 text-gray-400 hover:text-red-500"><Trash2 size={13} /></button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {Object.keys(configs).length === 0 && (
        <div className="text-center py-12 text-gray-400 text-sm">暂无配置项</div>
      )}

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setEditing(null)}>
          <div className="bg-white dark:bg-surface-800 rounded-2xl p-6 shadow-elevated w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <h3 className="font-display text-lg font-semibold mb-4">编辑配置</h3>
            <div className="space-y-3">
              <div><label className="text-xs text-gray-500 mb-1 block">键</label><input value={editing.key} disabled className="w-full px-3 py-2 bg-gray-100 dark:bg-surface-700 border rounded-lg text-sm text-gray-400" /></div>
              <div><label className="text-xs text-gray-500 mb-1 block">新值</label><input value={editing.value} onChange={e => setEditing({ ...editing, value: e.target.value })} className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" autoFocus /></div>
              <p className="text-xs text-warning-500">⚠ 部分配置需要重启服务后生效</p>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setEditing(null)} className="px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-surface-600 rounded-lg">取消</button>
              <button onClick={async () => { await adminApi.updateConfig(editing.key, { value: editing.value }); setEditing(null); load(); }} className="px-4 py-2 bg-brand-500 text-white text-sm rounded-lg hover:bg-brand-600">保存</button>
            </div>
          </div>
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setShowCreate(false)}>
          <div className="bg-white dark:bg-surface-800 rounded-2xl p-6 shadow-elevated w-full max-w-sm" onClick={e => e.stopPropagation()}>
            <h3 className="font-display text-lg font-semibold mb-4">新增配置</h3>
            <div className="space-y-3">
              <div><label className="text-xs text-gray-500 mb-1 block">键 *</label><input id="new-config-key" className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" autoFocus /></div>
              <div><label className="text-xs text-gray-500 mb-1 block">值 *</label><input id="new-config-value" className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" /></div>
              <div><label className="text-xs text-gray-500 mb-1 block">描述</label><input id="new-config-desc" className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm" /></div>
              <div><label className="text-xs text-gray-500 mb-1 block">分类</label>
                <select id="new-config-cat" className="w-full px-3 py-2 bg-gray-50 dark:bg-surface-700 border rounded-lg text-sm">
                  {['general','llm','agent','feature'].map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-surface-600 rounded-lg">取消</button>
              <button onClick={async () => {
                const key = (document.getElementById('new-config-key') as HTMLInputElement)?.value?.trim();
                const value = (document.getElementById('new-config-value') as HTMLInputElement)?.value?.trim();
                const desc = (document.getElementById('new-config-desc') as HTMLInputElement)?.value?.trim();
                const cat = (document.getElementById('new-config-cat') as HTMLSelectElement)?.value;
                if (!key || !value) { alert('键和值为必填'); return; }
                try {
                  await adminApi.updateConfig(key, { value, description: desc, category: cat });
                  setShowCreate(false);
                  load();
                } catch (e: any) { alert(e?.message || '创建失败'); }
              }} className="px-4 py-2 bg-brand-500 text-white text-sm rounded-lg hover:bg-brand-600">创建</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ===================================================================
 * Tab: Monitor — full monitoring dashboard
 * =================================================================== */
function MonitorTab() {
  const [overview, setOverview] = useState<adminApi.MonitorOverview | null>(null);
  const [diagnostic, setDiagnostic] = useState<adminApi.DiagnosticAccuracy | null>(null);
  const [quality, setQuality] = useState<adminApi.QuestionQuality | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      adminApi.getMonitorOverview(),
      adminApi.getDiagnosticAccuracy(),
      adminApi.getQuestionQuality(),
    ]).then(([o, d, q]) => {
      setOverview(o);
      setDiagnostic(d);
      setQuality(q);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="flex items-center justify-center py-20 text-gray-400">加载中...</div>;
  }

  const accuracyTrendOption = {
    tooltip: { trigger: 'axis' as const },
    grid: { top: 20, right: 20, bottom: 30, left: 45 },
    xAxis: { type: 'category' as const, data: overview?.accuracy_trend?.map(t => t.date) || [], axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' as const, min: 0, max: 100, name: '准确率 %', axisLabel: { fontSize: 10 } },
    series: [{
      type: 'line', data: overview?.accuracy_trend?.map(t => t.accuracy) || [],
      smooth: true, areaStyle: { opacity: 0.15, color: '#6366f1' },
      itemStyle: { color: '#6366f1' }, lineStyle: { width: 2 },
    }],
  };

  const dailyCountOption = {
    tooltip: { trigger: 'axis' as const },
    grid: { top: 20, right: 20, bottom: 30, left: 45 },
    xAxis: { type: 'category' as const, data: overview?.daily_answer_count?.map(t => t.date) || [], axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' as const, name: '答题数', axisLabel: { fontSize: 10 } },
    series: [{
      type: 'bar', data: overview?.daily_answer_count?.map(t => t.count) || [],
      itemStyle: { color: '#3b82f6', borderRadius: [4, 4, 0, 0] },
    }],
  };

  const scoreDistOption = {
    tooltip: { trigger: 'item' as const },
    series: [{
      type: 'pie', radius: ['40%', '70%'],
      data: quality?.score_distribution?.map(d => ({ name: d.range, value: d.count })) || [],
      label: { formatter: '{b}: {d}%', fontSize: 10 },
      emphasis: { label: { fontSize: 14, fontWeight: 'bold' } },
    }],
  };

  const calibrationOption = {
    tooltip: { trigger: 'axis' as const },
    grid: { top: 20, right: 20, bottom: 30, left: 45 },
    legend: { data: ['预期', '实际'], top: 0, textStyle: { fontSize: 10 } },
    xAxis: { type: 'category' as const, data: quality?.difficulty_calibration?.map(d => d.label) || [], axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' as const, min: 0, max: 100, name: '得分', axisLabel: { fontSize: 10 } },
    series: [
      { name: '预期', type: 'bar', data: quality?.difficulty_calibration?.map(d => d.expected) || [], itemStyle: { color: '#cbd5e1' } },
      { name: '实际', type: 'bar', data: quality?.difficulty_calibration?.map(d => d.actual) || [], itemStyle: { color: '#6366f1' } },
    ],
  };

  const typeDistOption = {
    tooltip: { trigger: 'item' as const },
    series: [{
      type: 'pie', radius: '65%',
      data: quality?.type_distribution?.map(d => ({ name: TYPE_LABELS[d.type] || d.type, value: d.count })) || [],
      label: { formatter: '{b}\n{d}%', fontSize: 10 },
    }],
  };

  const subjectOption = {
    tooltip: { trigger: 'item' as const },
    series: [{
      type: 'pie', radius: '65%',
      data: overview?.subject_breakdown?.map(s => ({ name: s.subject, value: s.count })) || [],
      label: { formatter: '{b}: {d}%', fontSize: 10 },
    }],
  };

  return (
    <div className="space-y-6">
      <h3 className="font-display text-lg font-semibold text-gray-800 dark:text-gray-100">模型效果监控</h3>

      {/* Overview cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: '总答题数', value: overview?.total_answered || 0, icon: MessageSquare, color: 'bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400' },
          { label: '活跃学生', value: overview?.active_students || 0, icon: Users, color: 'bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400' },
          { label: '整体正确率', value: `${overview?.overall_accuracy || 0}%`, icon: Target, color: 'bg-accent-50 dark:bg-accent-500/10 text-accent-600 dark:text-accent-400' },
          { label: '今日生成', value: overview?.questions_generated_today || 0, icon: TrendingUp, color: 'bg-warning-50 dark:bg-warning-500/10 text-warning-600 dark:text-warning-400' },
        ].map(card => (
          <div key={card.label} className={`rounded-2xl p-4 ${card.color}`}>
            <div className="flex items-center gap-2 text-xs opacity-70"><card.icon size={14} />{card.label}</div>
            <div className="text-2xl font-bold mt-1">{typeof card.value === 'number' ? card.value.toLocaleString() : card.value}</div>
          </div>
        ))}
      </div>

      {/* Charts row 1: accuracy trend + daily volume */}
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white dark:bg-surface-700 rounded-2xl p-4 shadow-soft">
          <p className="text-xs font-medium text-gray-500 mb-2">近30天准确率趋势</p>
          <ReactEChartsCore option={accuracyTrendOption} style={{ height: 240 }} />
        </div>
        <div className="bg-white dark:bg-surface-700 rounded-2xl p-4 shadow-soft">
          <p className="text-xs font-medium text-gray-500 mb-2">近30天每日答题量</p>
          <ReactEChartsCore option={dailyCountOption} style={{ height: 240 }} />
        </div>
      </div>

      {/* Charts row 2: score distribution + calibration + type + subject */}
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white dark:bg-surface-700 rounded-2xl p-4 shadow-soft">
          <p className="text-xs font-medium text-gray-500 mb-2">题目质量分数分布</p>
          <ReactEChartsCore option={scoreDistOption} style={{ height: 220 }} />
        </div>
        <div className="bg-white dark:bg-surface-700 rounded-2xl p-4 shadow-soft">
          <p className="text-xs font-medium text-gray-500 mb-2">难度校准对比 (预期 vs 实际得分)</p>
          <ReactEChartsCore option={calibrationOption} style={{ height: 220 }} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white dark:bg-surface-700 rounded-2xl p-4 shadow-soft">
          <p className="text-xs font-medium text-gray-500 mb-2">题型分布</p>
          <ReactEChartsCore option={typeDistOption} style={{ height: 220 }} />
        </div>
        <div className="bg-white dark:bg-surface-700 rounded-2xl p-4 shadow-soft">
          <p className="text-xs font-medium text-gray-500 mb-2">学科分布</p>
          <ReactEChartsCore option={subjectOption} style={{ height: 220 }} />
        </div>
      </div>

      {/* Diagnostic accuracy details */}
      {diagnostic && diagnostic.total_diagnoses > 0 && (
        <div className="bg-white dark:bg-surface-700 rounded-2xl p-4 shadow-soft">
          <p className="text-xs font-medium text-gray-500 mb-3">诊断准确率分布 (共 {diagnostic.total_diagnoses} 次诊断)</p>
          <div className="flex items-end gap-4 h-20">
            {diagnostic.accuracy_distribution.map(d => {
              const maxCount = Math.max(...diagnostic.accuracy_distribution.map(x => x.count), 1);
              const pct = Math.round((d.count / maxCount) * 100);
              return (
                <div key={d.range} className="flex-1 flex flex-col items-center gap-1">
                  <span className="text-xs font-medium text-gray-600 dark:text-gray-300">{d.count}</span>
                  <div className="w-full bg-brand-400 rounded-t-sm hover:bg-brand-500 transition-colors" style={{ height: `${Math.max(4, pct)}%` }} />
                  <span className="text-xs text-gray-400">{d.range}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Weak questions table */}
      {quality && quality.top_weak_questions.length > 0 && (
        <div>
          <p className="text-xs font-medium text-gray-500 mb-2">易错题排行 (Top 10)</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-600 text-left">
                <th className="pb-2 font-medium text-gray-400 w-8">#</th>
                <th className="pb-2 font-medium text-gray-400">题目内容</th>
                <th className="pb-2 font-medium text-gray-400 w-16">均分</th>
                <th className="pb-2 font-medium text-gray-400 w-16">作答数</th>
              </tr>
            </thead>
            <tbody>
              {quality.top_weak_questions.map((q, i) => (
                <tr key={q.question_id} className="border-b border-gray-50 dark:border-gray-700">
                  <td className="py-2 text-gray-400 text-xs">{i + 1}</td>
                  <td className="py-2 text-gray-700 dark:text-gray-200 text-xs truncate max-w-xs">{q.stem}</td>
                  <td className="py-2">
                    <span className={`text-xs font-medium ${q.avg_score >= 60 ? 'text-green-600' : q.avg_score >= 40 ? 'text-yellow-600' : 'text-red-600'}`}>
                      {q.avg_score}
                    </span>
                  </td>
                  <td className="py-2 text-xs text-gray-500">{q.attempt_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty state */}
      {(!overview || overview.total_answered === 0) && !loading && (
        <div className="flex flex-col items-center justify-center py-12 text-center border border-dashed border-gray-200 dark:border-gray-600 rounded-2xl">
          <Activity size={36} className="text-gray-300 dark:text-gray-600 mb-3" />
          <p className="text-sm text-gray-500 mb-1">暂无监控数据</p>
          <p className="text-xs text-gray-400">学生开始答题后，监控数据将自动汇聚展示</p>
        </div>
      )}
    </div>
  );
}

/* ===================================================================
 * Shared: Tag Manager Modal
 * =================================================================== */
function TagManagerModal({ tags, onClose, onRefresh, questions, onSaved }: { tags: TagInfo[]; onClose: () => void; onRefresh: () => void; questions: AdminQuestion[]; onSaved: () => void }) {
  const [renaming, setRenaming] = useState<string | null>(null);
  const [newName, setNewName] = useState('');

  const handleRename = async (oldName: string) => {
    if (!newName.trim() || newName === oldName) { setRenaming(null); return; }
    // Rename tag: update all questions that have this tag
    const affected = questions.filter(q => (q.tags || []).includes(oldName));
    for (const q of affected) {
      const updatedTags = (q.tags || []).map(t => t === oldName ? newName.trim() : t);
      await adminApi.updateQuestion(q.id, { tags: updatedTags });
    }
    setRenaming(null);
    onSaved();
  };

  const handleDelete = async (tagName: string) => {
    if (!confirm(`确定删除标签 "${tagName}"？将从所有题目中移除此标签。`)) return;
    const affected = questions.filter(q => (q.tags || []).includes(tagName));
    for (const q of affected) {
      const updatedTags = (q.tags || []).filter(t => t !== tagName);
      await adminApi.updateQuestion(q.id, { tags: updatedTags });
    }
    onSaved();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="bg-white dark:bg-surface-800 rounded-2xl p-6 shadow-elevated w-full max-w-md max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h3 className="font-display text-lg font-semibold mb-4">标签管理</h3>
        {tags.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-8">暂无标签</p>
        ) : (
          <div className="space-y-2">
            {tags.map(tag => (
              <div key={tag.name} className="flex items-center justify-between py-2.5 px-4 bg-gray-50 dark:bg-surface-600 rounded-xl">
                <div className="flex-1 min-w-0">
                  {renaming === tag.name ? (
                    <input value={newName} onChange={e => setNewName(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') handleRename(tag.name); if (e.key === 'Escape') setRenaming(null); }}
                      className="w-full px-2 py-1 bg-white dark:bg-surface-700 border rounded text-sm" autoFocus />
                  ) : (
                    <>
                      <p className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate">{tag.name}</p>
                      <p className="text-xs text-gray-400">{tag.count} 题 · {tag.subjects?.join(', ') || '全部学科'}</p>
                    </>
                  )}
                </div>
                <div className="flex gap-1 ml-2">
                  {renaming === tag.name ? (
                    <>
                      <button onClick={() => handleRename(tag.name)} className="p-1 rounded hover:bg-green-50 text-gray-400 hover:text-green-500"><CheckCircle size={13} /></button>
                      <button onClick={() => setRenaming(null)} className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500"><XCircle size={13} /></button>
                    </>
                  ) : (
                    <>
                      <button onClick={() => { setRenaming(tag.name); setNewName(tag.name); }} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-surface-500 text-gray-400"><Edit3 size={13} /></button>
                      <button onClick={() => handleDelete(tag.name)} className="p-1 rounded hover:bg-red-50 dark:hover:bg-red-500/10 text-gray-400 hover:text-red-500"><Trash2 size={13} /></button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="flex justify-end mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-surface-600 rounded-lg">关闭</button>
        </div>
      </div>
    </div>
  );
}

/* ===================================================================
 * Shared: small select
 * =================================================================== */
function SelectSm({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      className="px-2.5 py-2 bg-gray-50 dark:bg-surface-600 border border-gray-200 dark:border-gray-500 rounded-lg text-xs text-gray-600 dark:text-gray-300">
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}
