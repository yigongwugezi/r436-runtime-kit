// @ts-nocheck
import { useEffect, useState } from 'react';
import { Brain, ClipboardCheck, Edit3, RefreshCw, Save, Sparkles, Target } from 'lucide-react';
import { useChatPanel } from '../components/layout/AppLayout';
import { useProfile } from '../hooks/useProfile';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import { assessInterest, syncProfileFromConversation, updateProfileContext, updateProfileSelfReport, updateProfileFact } from '../api/profile';
import { PageError, PageLoading } from '../components/common/PageState';

const confidenceLabel = { low: '低', medium: '中', high: '高' };
const statusLabel = { unassessed: '未评估', tentative: '待验证', basic: '基础', developing: '发展中', proficient: '熟练', advanced: '高阶', learning: '学习中', partial: '部分掌握', mastered: '已掌握', familiar: '较熟悉', weak: '薄弱', unknown: '未评估', assessed: '已评估' };
const preferenceLabel = { example_first: '先看例题', practice_after_explanation: '理解讲解后练习', definition_first: '先讲定义', visual_explanation: '图解', step_by_step: '分步讲解', concise_explanation: '简洁讲解' };
const sourceLabel = { user_self_report: '用户自评', conversation_explicit: '对话中明确表达', system_observation: '系统观察', assessment: '测评结果', manual_edit: '用户手动确认' };
const contextLabel = { learning_goal: '学习目标', deadline: '学习周期', daily_minutes: '每日可用时间', background: '专业背景', prior_experience: '已有经验', content_preferences: '内容偏好', resource_preferences: '资源偏好' };

function preferenceText(values = []) {
  return values.map((value) => preferenceLabel[value] || value).join('、');
}

function Evidence({ items = [] }) {
  if (!items.length) return <p className="text-xs text-surface-400">证据不足，等待补充。</p>;
  return <details className="mt-2 text-xs text-surface-500"><summary className="cursor-pointer text-blue-600">查看依据</summary>{items.map((item, index) => <div key={index} className="mt-2 rounded bg-surface-50 p-2"><p>当前值：{String(item.value ?? '—')}</p><p>来源：{sourceLabel[item.source_type || item.source] || '系统记录'} · 置信度：{confidenceLabel[item.confidence] || '低'}</p><p>摘要：{item.evidence_summary || item.detail || '证据不足'}</p><p>更新：{item.updated_at ? new Date(item.updated_at).toLocaleString('zh-CN') : '—'}</p></div>)}</details>;
}

export default function ProfilePage() {
  const chat = useChatPanel();
  const sessionId = useChatStore((state) => state.dataSessionId);
  const subjectId = useSubjectStore((state) => state.activeSubject?.id ?? state.activeClassSubject?.subject);
  const { profileV2, loading, error, fetchProfile } = useProfile();
  const [editing, setEditing] = useState(false);
  const [context, setContext] = useState({});
  const [interest, setInterest] = useState<number | null>(null);
  const [editingInterest, setEditingInterest] = useState(false);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState([3, 3, 3]);
  const [saving, setSaving] = useState(false);
  const [syncPreview, setSyncPreview] = useState(null);
  const [syncError, setSyncError] = useState('');
  const [factBusy, setFactBusy] = useState('');

  useEffect(() => {
    if (profileV2?.subject_context) setContext(profileV2.subject_context);
    const current = profileV2?.general_states?.find((item) => item.key === 'interest');
    setInterest(current?.self_report ?? null);
    setEditingInterest(false);
  }, [profileV2]);

  if (loading && !profileV2) return <PageLoading text="加载学习画像…" />;
  if (error && !profileV2) return <PageError title="画像加载失败" description={error} onRetry={fetchProfile} />;
  if (!profileV2) return <div className="rounded-2xl bg-white p-10 text-center shadow-sm"><Brain className="mx-auto mb-3 text-surface-300" size={42} /><h2 className="text-xl font-bold">尚未构建学习画像</h2><p className="mt-2 text-sm text-surface-500">在对话中告诉 AI 你的课程、目标和时间安排。</p><button onClick={() => chat.setOpen(true)} className="mt-5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white">开始对话</button></div>;

  const subject = profileV2.subject_context || {};
  const interestState = profileV2.general_states?.find((item) => item.key === 'interest');
  const saveContext = async () => { setSaving(true); try { await updateProfileContext(sessionId, { ...context, daily_minutes: Number(context.daily_minutes) || null, prior_experience: String(context.prior_experience || '').split(/[，,]/).map((x) => x.trim()).filter(Boolean), content_preferences: String(context.content_preferences || '').split(/[，,]/).map((x) => x.trim()).filter(Boolean) }); await fetchProfile(); setEditing(false); } finally { setSaving(false); } };
  const saveInterest = async () => { if (interest == null) return; setSaving(true); try { await updateProfileSelfReport(sessionId, { interest }); await fetchProfile(); } finally { setSaving(false); } };
  const startInterestSelfReport = () => { setInterest(interestState?.self_report ?? 50); setEditingInterest(true); };
  const startAssessment = async () => { const result = await assessInterest(sessionId); setQuestions(result.questions || []); };
  const submitAssessment = async () => { setSaving(true); try { await assessInterest(sessionId, answers); await fetchProfile(); setQuestions([]); } finally { setSaving(false); } };
  const syncFromConversation = async (preview = true) => { if (!subjectId || !sessionId) return; setSaving(true); setSyncError(''); try { const result = await syncProfileFromConversation(subjectId, sessionId, preview); setSyncPreview(result.preview); if (!preview) await fetchProfile(); } catch (error) { setSyncError(error instanceof Error ? error.message : '同步失败，请稍后重试。'); } finally { setSaving(false); } };
  const factEvidence = (key) => profileV2?.fact_records?.[key] ? [{ ...profileV2.fact_records[key], detail: profileV2.fact_records[key].evidence_summary }] : [];
  const controlFact = async (key, action) => { if (!sessionId) return; setFactBusy(key); try { await updateProfileFact(sessionId, key, action); await fetchProfile(); } finally { setFactBusy(''); } };
  const editFact = async (key, current) => { const value = window.prompt('修改画像事实', String(current ?? '')); if (value?.trim()) { setFactBusy(key); try { await updateProfileFact(sessionId, key, 'edit', value.trim()); await fetchProfile(); } finally { setFactBusy(''); } } };

  return <div className="space-y-6 pb-8">
    <header className="rounded-2xl bg-gradient-to-r from-blue-600 to-violet-600 p-6 text-white">
      <p className="text-sm text-blue-100">当前学习概览</p><h2 className="mt-1 text-2xl font-bold">{subject.subject_name || '当前课程待确认'}</h2>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-4"><span>目标：{subject.learning_goal || '待补充'}</span><span>每日：{subject.daily_minutes ? `${subject.daily_minutes} 分钟` : '待补充'}</span><span>学习周期：{subject.deadline || '待补充'}</span><span>学习情境完整度：{Math.round((profileV2.profile_completeness || 0) * 100)}%</span></div><p className="mt-3 text-xs text-blue-100">该指标表示基础学习信息的完整程度，不代表所有能力与知识点均已完成测评。</p>
    </header>

    <section className="rounded-2xl bg-white p-5 shadow-sm"><div className="mb-4 flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">学习情境与偏好</h3><div className="flex gap-3"><button disabled={saving || !subjectId || !sessionId} onClick={() => syncFromConversation(true)} className="inline-flex items-center gap-1 text-sm text-violet-600"><RefreshCw size={14} />从当前对话同步画像</button><button onClick={() => setEditing(!editing)} className="inline-flex items-center gap-1 text-sm text-blue-600"><Edit3 size={14} />{editing ? '取消' : '编辑'}</button></div></div>
      {syncError && <p className="mb-3 text-sm text-red-600">{syncError}</p>}{syncPreview && <div className="mb-4 rounded-xl border border-violet-100 bg-violet-50 p-4 text-sm"><p className="font-medium">对话同步预览</p>{['added', 'updates', 'conflicts', 'ignored'].map((kind) => <div key={kind} className="mt-2"><p className="text-surface-600">{{ added: '将新增', updates: '将更新', conflicts: '存在冲突', ignored: '将忽略' }[kind]}：{(syncPreview[kind] || []).length ? (syncPreview[kind] || []).map((item) => `${item.field}：${item.value ?? item.candidate ?? item.current}`).join('；') : '无'}</p></div>)}{!syncPreview.has_changes ? <p className="mt-3 text-surface-500">当前对话没有发现新的画像信息。</p> : <button disabled={saving} onClick={() => syncFromConversation(false)} className="mt-3 rounded-lg bg-violet-600 px-3 py-1.5 text-white">确认应用</button>}</div>}
      {editing ? <div className="grid gap-3 md:grid-cols-2">
        {[["learning_goal", "学习目标"], ["deadline", "学习周期"], ["daily_minutes", "每日可用分钟"], ["background", "专业背景"], ["prior_experience", "已有经验（逗号分隔）"], ["content_preferences", "内容偏好（逗号分隔）"]].map(([key, label]) => <label key={key} className="text-sm text-surface-600">{label}<input value={Array.isArray(context[key]) ? (key === "content_preferences" ? preferenceText(context[key]) : context[key].join('、')) : context[key] || ''} onChange={(event) => setContext({ ...context, [key]: event.target.value })} className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2" /></label>)}
        <button disabled={saving} onClick={saveContext} className="inline-flex w-fit items-center gap-1 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white"><Save size={14} />保存情境</button>
      </div> : <div className="grid gap-3 text-sm md:grid-cols-3">{[["学习目标", subject.learning_goal, "learning_goal"], ["时间安排", subject.daily_minutes ? `每天${subject.daily_minutes}分钟` : '待补充', "daily_minutes"], ["专业背景", subject.background, "background"], ["已有经验", (subject.prior_experience || []).join('、'), "prior_experience"], ["内容偏好", preferenceText(subject.content_preferences || []), "content_preferences"], ["资源偏好", preferenceText(subject.resource_preferences || []), "resource_preferences"]].map(([label, value, key]) => <div key={label} className="rounded-xl bg-surface-50 p-3"><p className="text-xs text-surface-400">{label}</p><p className="mt-1 text-surface-700">{value || '待补充'}</p><Evidence items={factEvidence(key)} /></div>)}</div>}
    </section>

    {Object.keys(profileV2.fact_records || {}).length > 0 && <section className="rounded-2xl bg-white p-5 shadow-sm"><h3 className="mb-4 font-semibold">可控画像事实</h3><div className="space-y-2">{Object.entries(profileV2.fact_records).filter(([, fact]) => fact.status !== 'deleted').map(([key, fact]) => <div key={key} className="flex flex-wrap items-center gap-2 rounded-xl border border-surface-100 p-3 text-sm"><span className="font-medium text-surface-700">{contextLabel[key] || '学习偏好'}</span><span className="text-surface-500">{fact.fact_type === 'inferred' || fact.source_type === 'system_observation' ? '系统推断' : '我明确说过'}</span><span className="text-surface-400">{fact.is_disabled_for_personalization ? '已停止个性化' : fact.scope === 'session' ? '仅当前会话' : '参与当前学科'}</span><div className="ml-auto flex gap-1"><button disabled={factBusy === key} onClick={() => editFact(key, fact.value)} className="rounded border px-2 py-1 text-xs text-blue-600">修改</button><button disabled={factBusy === key} onClick={() => controlFact(key, fact.is_disabled_for_personalization ? 'enable' : 'disable')} className="rounded border px-2 py-1 text-xs text-violet-600">{fact.is_disabled_for_personalization ? '恢复个性化' : '停用个性化'}</button><button disabled={factBusy === key} onClick={() => controlFact(key, 'delete')} className="rounded border px-2 py-1 text-xs text-red-600">删除</button></div></div>)}</div></section>}

    <section className="rounded-2xl bg-white p-5 shadow-sm"><h3 className="mb-4 font-semibold">当前学习状态</h3><div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">{profileV2.general_states.map((state) => <div key={state.key} className="rounded-xl border border-surface-100 p-3"><p className="font-medium text-surface-700">{state.label}</p><p className="mt-2 text-sm">用户自评：{state.self_report == null ? '未评估' : `${state.self_report}/100`}</p><p className="text-xs text-surface-500">系统观察：{state.system_estimate == null ? '证据不足' : `${state.level} (${state.system_estimate})`}</p><p className="mt-1 text-xs text-surface-400">置信度：{confidenceLabel[state.confidence]}</p><Evidence items={state.evidence} /></div>)}</div>
      <div className="mt-5 rounded-xl bg-blue-50 p-4"><div className="flex flex-wrap items-center gap-3"><span className="text-sm font-medium">当前兴趣自评：{interest == null ? '尚未自评' : interest}</span>{editingInterest && interest != null && <><input type="range" min="0" max="100" value={interest} onChange={(event) => setInterest(Number(event.target.value))} className="w-44" /><button disabled={saving} onClick={saveInterest} className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm text-white">保存自评</button></>} {!editingInterest && <button onClick={startInterestSelfReport} className="rounded-lg border border-blue-200 px-3 py-1.5 text-sm text-blue-700">{interest == null ? '开始自评' : '修改自评'}</button>}<button onClick={startAssessment} className="inline-flex items-center gap-1 text-sm text-blue-700"><Sparkles size={14} />AI 辅助校准</button></div>
        {questions.length > 0 && <div className="mt-4 space-y-3">{questions.map((question, index) => <label key={question} className="block text-sm text-surface-700">{question}<input type="range" min="1" max="5" value={answers[index]} onChange={(event) => setAnswers(answers.map((value, i) => i === index ? Number(event.target.value) : value))} className="ml-3 w-36" />{answers[index]}</label>)}<button disabled={saving} onClick={submitAssessment} className="rounded-lg bg-violet-600 px-3 py-1.5 text-sm text-white">提交校准</button></div>}
      </div>
    </section>

    <section className="rounded-2xl bg-white p-5 shadow-sm"><h3 className="mb-4 font-semibold">当前学科能力</h3><div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">{profileV2.subject_dimensions.map((dimension) => <div key={dimension.key} className="rounded-xl border border-surface-100 p-4"><div className="flex items-center justify-between"><p className="font-medium">{dimension.label}</p><span className="text-xs text-surface-500">{statusLabel[dimension.status]}</span></div><p className="mt-2 text-sm text-surface-500">置信度：{confidenceLabel[dimension.confidence]} · 证据 {dimension.evidence.length} 条</p><Evidence items={dimension.evidence} /><p className="mt-2 text-xs text-blue-600">下一步：{dimension.recommended_action}</p></div>)}</div></section>

    <section className="rounded-2xl bg-white p-5 shadow-sm"><h3 className="mb-4 font-semibold">知识点掌握与证据</h3>{profileV2.knowledge_mastery.length ? <div className="space-y-3">{profileV2.knowledge_mastery.map((point) => <div key={point.knowledge_id} className="rounded-xl bg-amber-50 p-3"><div className="flex justify-between"><p className="font-medium">{point.label}</p><span className="text-sm">{statusLabel[point.status]}</span></div><Evidence items={point.evidence} /></div>)}</div> : <p className="text-sm text-surface-400">尚无可验证的知识点证据，完成诊断题或练习后会在此更新。</p>}<p className="mt-4 text-xs text-surface-400">证据来源：对话 {profileV2.evidence_summary.conversation} · 诊断 {profileV2.evidence_summary.diagnostic} · 练习 {profileV2.evidence_summary.practice} · 行为 {profileV2.evidence_summary.behavior}</p></section>
  </div>;
}
