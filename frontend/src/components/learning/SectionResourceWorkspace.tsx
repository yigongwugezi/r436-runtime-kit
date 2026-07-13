import { useEffect, useRef, useState } from 'react';
import { ExternalLink, FilePlus2, Loader2, RefreshCw, Search, Sparkles, FileText } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useSubjectStore } from '../../store/subjectStore';
import Markdown from '../../utils/markdown';
import MermaidDiagram from '../../utils/mermaid';
import {
  generateSectionMindmap,
  generateSectionResource,
  generatedResourceLabels,
  getSectionMindmap,
  getGeneratedSectionResources,
  recommendSectionResources,
  submitSectionResourceFeedback,
  submitGeneratedSectionResourceFeedback,
} from '../../api/sectionResources';
import type { ChapterMindmap, GeneratedSectionResource, GeneratedSectionResourceType, SectionRecommendationResult } from '../../types/sectionResources';
import type { Section } from '../../types/learningPath';

interface Props {
  sessionId: string;
  pathId: string;
  stageId: string;
  chapterId: string;
  chapterTitle: string;
  section: Section | undefined;
  lectureContent: string;
  sections: Section[];
  legacyMindmapId?: string;
}

const resourceGroups: Array<{ label: string; types: GeneratedSectionResourceType[] }> = [
  { label: '学习材料', types: ['summary_card', 'concept_comparison', 'worked_example', 'mistake_checklist', 'review_notes'] },
  { label: '结构化可视化', types: ['knowledge_map', 'process_flow', 'concept_diagram', 'execution_trace', 'code_trace'] },
];
const platformLabels: Record<string, string> = { bilibili: 'B站', youtube: 'YouTube', vimeo: 'Vimeo', icourse163: '中国大学MOOC', xuetangx: '学堂在线', smartedu: '智慧教育平台', imooc: '慕课网', youku: '优酷', iqiyi: '爱奇艺', douyin: '抖音', tencent_video: '腾讯视频' };
const trustLabels: Record<string, string> = { official: '官方来源', educational: '教育来源', general: '普通来源' };
const matchLevelLabels: Record<string, string> = { exact_topic: '精确匹配', chapter_level: '章节匹配', course_level: '课程拓展', expanded_research: '拓展论文' };
type GeneratedFeedback = NonNullable<GeneratedSectionResource['feedback']>['feedback'];

function safeExternalUrl(url: string): boolean {
  try { return ['http:', 'https:'].includes(new URL(url).protocol); } catch { return false; }
}

export default function SectionResourceWorkspace(props: Props) {
  const nav = useNavigate();
  const { sessionId, pathId, stageId, chapterId, chapterTitle, section, lectureContent, sections, legacyMindmapId } = props;
  const subjectId = useSubjectStore((state) => state.activeSubject?.id ?? state.activeClassSubject?.subject);
  const [recommendations, setRecommendations] = useState<SectionRecommendationResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [resourceFilter, setResourceFilter] = useState<'all' | 'video' | 'article' | 'course' | 'paper' | 'document'>('all');
  const [generated, setGenerated] = useState<GeneratedSectionResource[]>([]);
  const [generating, setGenerating] = useState<GeneratedSectionResourceType | null>(null);
  const [selectedType, setSelectedType] = useState<GeneratedSectionResourceType>('knowledge_map');
  const [generatedFeedback, setGeneratedFeedback] = useState<GeneratedFeedback>('helpful');
  const [preview, setPreview] = useState<GeneratedSectionResource | null>(null);
  const [mindmap, setMindmap] = useState<ChapterMindmap | null>(null);
  const [mindmapLoading, setMindmapLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const requestSerial = useRef(0);

  useEffect(() => {
    let active = true;
    if (!sessionId || !section?.id) { setGenerated([]); return; }
    getGeneratedSectionResources(section.id, sessionId, subjectId).then((items) => active && setGenerated(items)).catch(() => active && setGenerated([]));
    return () => { active = false; };
  }, [sessionId, section?.id, subjectId]);

  useEffect(() => {
    let active = true;
    if (!sessionId || !section?.id) { setMindmap(null); return; }
    getSectionMindmap(section.id, sessionId).then((item) => active && setMindmap(item)).catch(() => active && setMindmap(null));
    return () => { active = false; };
  }, [sessionId, section?.id]);

  const searchResources = async (filter = resourceFilter) => {
    if (!sessionId || !section) return;
    const requestId = ++requestSerial.current;
    setSearching(true);
    setNotice('');
    try {
      const result = await recommendSectionResources(section.id, {
        sessionId, sectionTitle: section.title, knowledgePoints: section.knowledgePoints,
        subjectId,
        language: 'zh-CN', resourceTypes: filter === 'all' ? ['video', 'article', 'course', 'document', 'paper'] : [filter],
      });
      if (requestId === requestSerial.current) setRecommendations(result);
    } catch {
      if (requestId === requestSerial.current) setRecommendations({ query: [], resources: [], status: 'failed', warnings: ['外部资源检索失败，请稍后重试。'] });
    } finally { if (requestId === requestSerial.current) setSearching(false); }
  };
  const search = () => searchResources(resourceFilter);

  const giveFeedback = async (resource: any, feedback: 'helpful' | 'not_relevant' | 'too_hard' | 'too_easy') => {
    if (!sessionId || !section || !subjectId) return;
    setNotice('');
    try {
      await submitSectionResourceFeedback(section.id, { sessionId, subjectId, url: resource.url, resourceType: resource.resource_type, feedback });
      setRecommendations((current) => current ? { ...current, resources: current.resources.map((item) => item.url === resource.url ? { ...item, feedback } : item) } : current);
    } catch { setNotice('反馈保存失败，请稍后重试。'); }
  };

  const generate = async (resourceType: GeneratedSectionResourceType, feedback: GeneratedFeedback | '' = '') => {
    if (!sessionId || !section) return;
    setGenerating(resourceType);
    setNotice('');
    try {
      const result = await generateSectionResource(section.id, {
        sessionId, resourceType, pathId, stageId, chapterId, sectionTitle: section.title,
        subjectId, knowledgePoints: section.knowledgePoints, lectureContent, feedback,
        regenerate: generated.some((item) => item.resourceType === resourceType),
      });
      const previous = generated.find((item) => item.resourceType === resourceType);
      const next: GeneratedSectionResource = {
        ...result.resource,
        feedback: feedback ? { ...previous?.feedback, feedback } : result.resource.feedback,
      };
      setGenerated((items) => [next, ...items.filter((item) => item.id !== next.id)]);
      setPreview(next);
    } catch { setNotice('资源生成失败，请稍后重试。'); } finally { setGenerating(null); }
  };

  const regenerateFromFeedback = async () => {
    if (!preview || !sessionId || !section) return;
    try {
      const savedFeedback = { ...preview.feedback, feedback: generatedFeedback };
      await submitGeneratedSectionResourceFeedback(section.id, preview.resourceType, {
        sessionId,
        subjectId,
        feedback: generatedFeedback,
        rating: savedFeedback.rating,
        comment: savedFeedback.comment,
      });
      setGenerated((items) => items.map((item) => item.id === preview.id ? { ...item, feedback: savedFeedback } : item));
      setPreview((item) => item ? { ...item, feedback: savedFeedback } : item);
      if (generatedFeedback === 'helpful') {
        setNotice('已记录，这将用于优化后续同类资源推荐。');
        return;
      }
      await generate(preview.resourceType, generatedFeedback);
    } catch { setNotice('反馈保存或重新生成失败，请稍后重试。'); }
  };

  const openGeneratedDetail = (resource: GeneratedSectionResource) => {
    if (!section) return;
    const returnTo = `/lecture/section/${encodeURIComponent(section.id)}?panel=resources`;
    const query = new URLSearchParams({
      source: 'lecture', activePanel: 'related_resources', returnTo, sessionId,
      subjectId: subjectId || '', pathId, stageId, chapterId, sectionId: section.id,
    });
    nav(`/resources/${encodeURIComponent(resource.id)}?${query.toString()}`);
  };

  const generateMindmap = async () => {
    if (!sessionId || !section) return;
    setMindmapLoading(true);
    setNotice('');
    try {
      const result = await generateSectionMindmap(section.id, {
        sessionId, pathId, stageId, sectionTitle: section.title,
        subjectId, knowledgePoints: section.knowledgePoints,
        regenerate: Boolean(mindmap),
      });
      setMindmap(result.mindmap);
    } catch { setNotice('思维导图生成失败，请稍后重试。'); } finally { setMindmapLoading(false); }
  };

  return <div className="p-4 space-y-4">
    {notice && <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{notice}</p>}

    {/* ── 一键推送 ── */}
    <button onClick={search} disabled={searching || !section}
      className="w-full flex items-center justify-center gap-2 px-3 py-3 rounded-xl bg-surface-800 text-white text-xs font-semibold hover:bg-surface-900 disabled:opacity-40 transition-colors">
      <Search size={14} />{searching ? '搜索中…' : recommendations ? '重新推送' : '一键推送'}
    </button>
    <p className="text-[10px] text-surface-400 text-center -mt-3 mb-1">基于画像 + 知识点智能匹配</p>

    {/* ── 分类推送 ── */}
    <div className="grid grid-cols-2 gap-1.5">
      {[
        { key: 'all', label: '全部' },
        { key: 'video', label: '教学视频' },
        { key: 'article', label: '文章' },
        { key: 'course', label: '课程' },
        { key: 'document', label: '文档' },
        { key: 'paper', label: '学术论文' },
      ].map(({ key, label }) => (
        <button key={label}
          onClick={() => {
            const filter = key as typeof resourceFilter;
            setResourceFilter(filter);
            void searchResources(filter);
          }}
          disabled={searching || !section}
          className="flex items-center justify-center gap-1 px-2.5 py-2 rounded-lg bg-surface-50 text-surface-600 text-[10px] font-medium hover:bg-surface-100 disabled:opacity-30 transition-colors">
          {label}
        </button>
      ))}
    </div>

    {/* ── 推送结果 ── */}
    {recommendations && (
      <div className="space-y-1.5">
        {!recommendations.resources.length && <p className="rounded-lg bg-surface-50 px-3 py-2 text-[11px] text-surface-500">{recommendations.status === 'search_unavailable' ? '外部搜索暂不可用，请稍后重试。' : recommendations.status === 'expanded_no_results' ? '已扩大搜索范围，仍未找到高相关公开资源。' : recommendations.status === 'no_high_relevance' ? '暂无高相关公开资源，可调整知识点后重试。' : '未找到与当前小节匹配的公开资源。'}</p>}
        {recommendations.resources.filter(r => resourceFilter === 'all' || r.resource_type === resourceFilter).map(r => (
          <div key={r.url} className="rounded-lg bg-surface-50 p-2.5">
            <p className="text-xs font-medium text-surface-700 line-clamp-2">{r.title}</p>
            <p className="mt-0.5 text-[10px] text-surface-400">{r.platform ? platformLabels[r.platform] || r.platform : r.resource_type} · {r.source} · {trustLabels[r.trust_level] || r.trust_level}</p>
            {r.match_level && <p className="mt-0.5 text-[10px] text-surface-400">{matchLevelLabels[r.match_level] || r.match_level}</p>}
            <p className="mt-1 text-[11px] text-surface-500 line-clamp-2">{r.snippet}</p>
            <p className="mt-1 text-[10px] text-surface-500 line-clamp-2">推荐理由：{r.reason}</p>
            {safeExternalUrl(r.url) && <a href={r.url} target="_blank" rel="noopener noreferrer"
              className="mt-1.5 inline-flex items-center gap-1 text-[10px] font-medium text-surface-500 hover:text-surface-700">
              {r.resource_type === 'video' ? '打开视频' : '打开原文'} <ExternalLink size={10} /></a>}
            <div className="mt-2 flex flex-wrap gap-1"><span className="mr-1 text-[10px] text-surface-400">这条推荐：</span>{[['helpful', '有帮助'], ['not_relevant', '不相关'], ['too_hard', '太难'], ['too_easy', '太简单']].map(([value, label]) => <button key={value} onClick={() => giveFeedback(r, value as 'helpful' | 'not_relevant' | 'too_hard' | 'too_easy')} className={`rounded px-1.5 py-0.5 text-[10px] ${r.feedback === value ? 'bg-blue-100 text-blue-700' : 'bg-white text-surface-500 hover:bg-surface-100'}`}>{label}</button>)}</div>
          </div>
        ))}
      </div>
    )}

    <div className="border-t border-surface-100 pt-4 space-y-2">
      <div className="flex items-center gap-2">
        <Sparkles size={14} className="text-primary-600" />
        <p className="text-xs font-semibold text-surface-700">生成本节学习资源</p>
      </div>
      <p className="text-[10px] text-surface-400">本地模板生成，保存到当前会话的资源库。</p>
      <div className="flex gap-2">
        <select value={selectedType} onChange={(event) => setSelectedType(event.target.value as GeneratedSectionResourceType)}
          className="min-w-0 flex-1 rounded-lg border border-surface-200 bg-white px-2 py-2 text-xs text-surface-600">
          {resourceGroups.map((group) => <optgroup key={group.label} label={group.label}>
            {group.types.map((type) => <option key={type} value={type}>{generatedResourceLabels[type]}</option>)}
          </optgroup>)}
        </select>
        <button onClick={() => generate(selectedType)} disabled={Boolean(generating) || !section}
          className="inline-flex items-center gap-1 rounded-lg bg-primary-600 px-3 py-2 text-xs font-medium text-white hover:bg-primary-700 disabled:opacity-40">
          {generating === selectedType ? <Loader2 size={13} className="animate-spin" /> : <FilePlus2 size={13} />}
          生成
        </button>
      </div>

      {generated.length > 0 && <div className="space-y-1.5 pt-1">
        {generated.map((item) => <button key={item.id} onClick={() => { setPreview(item); setGeneratedFeedback(item.feedback?.feedback || 'helpful'); }}
          className={`w-full rounded-lg border px-2.5 py-2 text-left text-xs transition-colors ${preview?.id === item.id ? 'border-primary-200 bg-primary-50 text-primary-700' : 'border-surface-100 bg-surface-50 text-surface-600 hover:bg-surface-100'}`}>
          <span className="font-medium">{item.title}</span>
          {item.quality && <span className="ml-1.5 text-[10px] text-surface-400">质检：{item.quality === 'passed' ? '通过' : item.quality === 'repaired' ? '已修复' : item.quality === 'fallback' ? '本地兜底' : '失败'}</span>}
        </button>)}
      </div>}

      {preview && <div className="space-y-2 rounded-xl border border-surface-200 bg-white p-3">
        <div className="flex items-center justify-between gap-2"><p className="text-xs font-semibold text-surface-700">{preview.title}</p><button onClick={() => openGeneratedDetail(preview)} className="text-[10px] text-primary-600 hover:text-primary-700">打开详情</button></div>
        {preview.mermaidDef && <div className="rounded-lg border border-surface-100 bg-white p-2"><MermaidDiagram definition={preview.mermaidDef} /></div>}
        <div className="prose prose-sm max-w-none text-xs"><Markdown content={preview.content} /></div>
        <div className="flex gap-2 border-t border-surface-100 pt-2">
          <select value={generatedFeedback} onChange={(event) => setGeneratedFeedback(event.target.value as typeof generatedFeedback)} className="min-w-0 flex-1 rounded-lg border border-surface-200 px-2 py-1.5 text-[10px]">
            <option value="helpful">有帮助</option><option value="not_relevant">不相关</option><option value="too_hard">太难</option><option value="too_easy">太简单</option><option value="other">其他</option>
          </select>
          {generatedFeedback === 'helpful' ? <button onClick={regenerateFromFeedback} className="rounded-lg bg-success-50 px-2 py-1.5 text-[10px] text-success-700">记录有帮助</button> : <button onClick={regenerateFromFeedback} disabled={Boolean(generating)} className="inline-flex items-center gap-1 rounded-lg bg-surface-800 px-2 py-1.5 text-[10px] text-white hover:bg-surface-900 disabled:opacity-40"><RefreshCw size={11} />按反馈重新生成</button>}
        </div>
        {generatedFeedback === 'helpful' && <p className="text-[10px] text-success-600">有帮助不需要重新生成；保存后会用于优化后续同类推荐。</p>}
        {preview.workflowTrace && preview.workflowTrace.length > 0 && <details className="rounded-lg bg-surface-50 p-2 text-[10px] text-surface-500"><summary className="cursor-pointer font-medium text-surface-600">查看协同执行记录</summary><ol className="mt-1 space-y-1 pl-4">{preview.workflowTrace.map((step, index) => <li key={`${step.agent}-${index}`}>{step.agent}：{step.summary}</li>)}</ol></details>}
      </div>}
    </div>

  </div>;
}
