// @ts-nocheck
import { useEffect, useState } from 'react';
import { Brain, ClipboardCheck, Edit3, RefreshCw, Save, Sparkles, Target } from 'lucide-react';
import { useChatPanel } from '../components/layout/AppLayout';
import { useProfile } from '../hooks/useProfile';
import { useChatStore } from '../store/chatStore';
import { assessInterest, updateProfileContext, updateProfileSelfReport } from '../api/profile';
import { PageError, PageLoading } from '../components/common/PageState';

const confidenceLabel = { low: '低', medium: '中', high: '高' };
const statusLabel = { unassessed: '未评估', tentative: '待验证', basic: '基础', developing: '发展中', proficient: '熟练', advanced: '高阶', learning: '学习中', partial: '部分掌握', mastered: '已掌握', weak: '薄弱', assessed: '已评估' };

function Evidence({ items = [] }) {
  if (!items.length) return <p className="text-xs text-surface-400">证据不足，等待补充。</p>;
  return <p className="text-xs text-surface-500">依据：{items.map((item) => item.detail).filter(Boolean).join('；')}</p>;
}

export default function ProfilePage() {
  const chat = useChatPanel();
  const sessionId = useChatStore((state) => state.dataSessionId);
  const { profileV2, loading, error, fetchProfile } = useProfile();
  const [editing, setEditing] = useState(false);
  const [context, setContext] = useState({});
  const [interest, setInterest] = useState(50);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState([3, 3, 3]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (profileV2?.subject_context) setContext(profileV2.subject_context);
    const current = profileV2?.general_states?.find((item) => item.key === 'interest');
    if (current?.self_report != null) setInterest(current.self_report);
  }, [profileV2]);

  if (loading && !profileV2) return <PageLoading text="加载学习画像…" />;
  if (error && !profileV2) return <PageError title="画像加载失败" description={error} onRetry={fetchProfile} />;
  if (!profileV2) return <div className="rounded-2xl bg-white p-10 text-center shadow-sm"><Brain className="mx-auto mb-3 text-surface-300" size={42} /><h2 className="text-xl font-bold">尚未构建学习画像</h2><p className="mt-2 text-sm text-surface-500">在对话中告诉 AI 你的课程、目标和时间安排。</p><button onClick={() => chat.setOpen(true)} className="mt-5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white">开始对话</button></div>;

  const subject = profileV2.subject_context || {};
  const interestState = profileV2.general_states?.find((item) => item.key === 'interest');
  const saveContext = async () => { setSaving(true); try { await updateProfileContext(sessionId, { ...context, daily_minutes: Number(context.daily_minutes) || null, prior_experience: String(context.prior_experience || '').split(/[，,]/).map((x) => x.trim()).filter(Boolean), content_preferences: String(context.content_preferences || '').split(/[，,]/).map((x) => x.trim()).filter(Boolean) }); await fetchProfile(); setEditing(false); } finally { setSaving(false); } };
  const saveInterest = async () => { setSaving(true); try { await updateProfileSelfReport(sessionId, { interest }); await fetchProfile(); } finally { setSaving(false); } };
  const startAssessment = async () => { const result = await assessInterest(sessionId); setQuestions(result.questions || []); };
  const submitAssessment = async () => { setSaving(true); try { await assessInterest(sessionId, answers); await fetchProfile(); setQuestions([]); } finally { setSaving(false); } };

  return <div className="space-y-6 pb-8">
    <header className="rounded-2xl bg-gradient-to-r from-blue-600 to-violet-600 p-6 text-white">
      <p className="text-sm text-blue-100">当前学习概览</p><h2 className="mt-1 text-2xl font-bold">{subject.subject_name || '当前课程待确认'}</h2>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-4"><span>目标：{subject.learning_goal || '待补充'}</span><span>每日：{subject.daily_minutes ? `${subject.daily_minutes} 分钟` : '待补充'}</span><span>阶段：{subject.deadline || '待补充'}</span><span>信息完整度：{Math.round((profileV2.profile_completeness || 0) * 100)}%</span></div>
    </header>

    <section className="rounded-2xl bg-white p-5 shadow-sm"><div className="mb-4 flex items-center justify-between"><h3 className="font-semibold">学习情境与偏好</h3><button onClick={() => setEditing(!editing)} className="inline-flex items-center gap-1 text-sm text-blue-600"><Edit3 size={14} />{editing ? '取消' : '编辑'}</button></div>
      {editing ? <div className="grid gap-3 md:grid-cols-2">
        {[["learning_goal", "学习目标"], ["deadline", "截止时间"], ["daily_minutes", "每日可用分钟"], ["background", "专业背景"], ["prior_experience", "已有经验（逗号分隔）"], ["content_preferences", "内容偏好（逗号分隔）"]].map(([key, label]) => <label key={key} className="text-sm text-surface-600">{label}<input value={Array.isArray(context[key]) ? context[key].join('、') : context[key] || ''} onChange={(event) => setContext({ ...context, [key]: event.target.value })} className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2" /></label>)}
        <button disabled={saving} onClick={saveContext} className="inline-flex w-fit items-center gap-1 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white"><Save size={14} />保存情境</button>
      </div> : <div className="grid gap-3 text-sm md:grid-cols-3">{[["学习目标", subject.learning_goal], ["时间安排", subject.daily_minutes ? `${subject.daily_minutes} 分钟/天` : '待补充'], ["专业背景", subject.background], ["已有经验", (subject.prior_experience || []).join('、')], ["内容偏好", (subject.content_preferences || []).join('、')], ["资源偏好", (subject.resource_preferences || []).join('、')]].map(([label, value]) => <div key={label} className="rounded-xl bg-surface-50 p-3"><p className="text-xs text-surface-400">{label}</p><p className="mt-1 text-surface-700">{value || '待补充'}</p></div>)}</div>}
    </section>

    <section className="rounded-2xl bg-white p-5 shadow-sm"><h3 className="mb-4 font-semibold">当前学习状态</h3><div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">{profileV2.general_states.map((state) => <div key={state.key} className="rounded-xl border border-surface-100 p-3"><p className="font-medium text-surface-700">{state.label}</p><p className="mt-2 text-sm">用户自评：{state.self_report == null ? '未评估' : `${state.self_report}/100`}</p><p className="text-xs text-surface-500">系统观察：{state.system_estimate == null ? '证据不足' : `${state.level} (${state.system_estimate})`}</p><p className="mt-1 text-xs text-surface-400">置信度：{confidenceLabel[state.confidence]}</p><Evidence items={state.evidence} /></div>)}</div>
      <div className="mt-5 rounded-xl bg-blue-50 p-4"><div className="flex flex-wrap items-center gap-3"><span className="text-sm font-medium">当前兴趣自评：{interest}</span><input type="range" min="0" max="100" value={interest} onChange={(event) => setInterest(Number(event.target.value))} className="w-44" /><button disabled={saving} onClick={saveInterest} className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm text-white">保存自评</button><button onClick={startAssessment} className="inline-flex items-center gap-1 text-sm text-blue-700"><Sparkles size={14} />AI 辅助校准</button></div>
        {questions.length > 0 && <div className="mt-4 space-y-3">{questions.map((question, index) => <label key={question} className="block text-sm text-surface-700">{question}<input type="range" min="1" max="5" value={answers[index]} onChange={(event) => setAnswers(answers.map((value, i) => i === index ? Number(event.target.value) : value))} className="ml-3 w-36" />{answers[index]}</label>)}<button disabled={saving} onClick={submitAssessment} className="rounded-lg bg-violet-600 px-3 py-1.5 text-sm text-white">提交校准</button></div>}
      </div>
    </section>

    <section className="rounded-2xl bg-white p-5 shadow-sm"><h3 className="mb-4 font-semibold">当前学科能力</h3><div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">{profileV2.subject_dimensions.map((dimension) => <div key={dimension.key} className="rounded-xl border border-surface-100 p-4"><div className="flex items-center justify-between"><p className="font-medium">{dimension.label}</p><span className="text-xs text-surface-500">{statusLabel[dimension.status]}</span></div><p className="mt-2 text-sm text-surface-500">置信度：{confidenceLabel[dimension.confidence]} · 证据 {dimension.evidence.length} 条</p><Evidence items={dimension.evidence} /><p className="mt-2 text-xs text-blue-600">下一步：{dimension.recommended_action}</p></div>)}</div></section>

    <section className="rounded-2xl bg-white p-5 shadow-sm"><h3 className="mb-4 font-semibold">知识点掌握与证据</h3>{profileV2.knowledge_mastery.length ? <div className="space-y-3">{profileV2.knowledge_mastery.map((point) => <div key={point.knowledge_id} className="rounded-xl bg-amber-50 p-3"><div className="flex justify-between"><p className="font-medium">{point.label}</p><span className="text-sm">{statusLabel[point.status]}</span></div><Evidence items={point.evidence} /></div>)}</div> : <p className="text-sm text-surface-400">尚无可验证的知识点证据，完成诊断题或练习后会在此更新。</p>}<p className="mt-4 text-xs text-surface-400">证据来源：对话 {profileV2.evidence_summary.conversation} · 诊断 {profileV2.evidence_summary.diagnostic} · 练习 {profileV2.evidence_summary.practice} · 行为 {profileV2.evidence_summary.behavior}</p></section>
  </div>;
}
