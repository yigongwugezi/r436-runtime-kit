import { useEffect, useState } from 'react';
import { ExternalLink, FilePlus2, Loader2, RefreshCw, Search, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Markdown from '../../utils/markdown';
import MermaidDiagram from '../../utils/mermaid';
import {
  generateChapterMindmap,
  generateSectionResource,
  generatedResourceLabels,
  getChapterMindmap,
  getGeneratedSectionResources,
  recommendSectionResources,
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

const resourceTypes: GeneratedSectionResourceType[] = ['summary_card', 'concept_comparison', 'worked_example', 'mistake_checklist', 'review_notes'];

function safeExternalUrl(url: string): boolean {
  try { return ['http:', 'https:'].includes(new URL(url).protocol); } catch { return false; }
}

export default function SectionResourceWorkspace(props: Props) {
  const nav = useNavigate();
  const { sessionId, pathId, stageId, chapterId, chapterTitle, section, lectureContent, sections, legacyMindmapId } = props;
  const [recommendations, setRecommendations] = useState<SectionRecommendationResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [resourceFilter, setResourceFilter] = useState<'all' | 'video' | 'article' | 'course' | 'paper' | 'document'>('all');
  const [generated, setGenerated] = useState<GeneratedSectionResource[]>([]);
  const [generating, setGenerating] = useState<GeneratedSectionResourceType | null>(null);
  const [preview, setPreview] = useState<GeneratedSectionResource | null>(null);
  const [mindmap, setMindmap] = useState<ChapterMindmap | null>(null);
  const [mindmapLoading, setMindmapLoading] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let active = true;
    if (!sessionId || !section?.id) { setGenerated([]); return; }
    getGeneratedSectionResources(section.id, sessionId).then((items) => active && setGenerated(items)).catch(() => active && setGenerated([]));
    return () => { active = false; };
  }, [sessionId, section?.id]);

  useEffect(() => {
    let active = true;
    if (!sessionId || !chapterId) { setMindmap(null); return; }
    getChapterMindmap(chapterId, sessionId).then((item) => active && setMindmap(item)).catch(() => active && setMindmap(null));
    return () => { active = false; };
  }, [sessionId, chapterId]);

  const search = async () => {
    if (!sessionId || !section) return;
    setSearching(true);
    setNotice('');
    try {
      setRecommendations(await recommendSectionResources(section.id, {
        sessionId, sectionTitle: section.title, knowledgePoints: section.knowledgePoints,
        language: 'zh-CN', resourceTypes: resourceFilter === 'all' ? ['video', 'article', 'course', 'document'] : [resourceFilter],
      }));
    } catch {
      setRecommendations({ query: [], resources: [], status: 'failed', warnings: ['外部资源检索失败，请稍后重试。'] });
    } finally { setSearching(false); }
  };

  const generate = async (resourceType: GeneratedSectionResourceType) => {
    if (!sessionId || !section) return;
    setGenerating(resourceType);
    setNotice('');
    try {
      const result = await generateSectionResource(section.id, {
        sessionId, resourceType, pathId, stageId, chapterId, sectionTitle: section.title,
        knowledgePoints: section.knowledgePoints, lectureContent, regenerate: generated.some((item) => item.resourceType === resourceType),
      });
      setGenerated((items) => [result.resource, ...items.filter((item) => item.id !== result.resource.id)]);
      setPreview(result.resource);
    } catch { setNotice('资源生成失败，请稍后重试。'); } finally { setGenerating(null); }
  };

  const generateMindmap = async () => {
    if (!sessionId || !chapterId) return;
    setMindmapLoading(true);
    setNotice('');
    try {
      const result = await generateChapterMindmap(chapterId, {
        sessionId, pathId, stageId, chapterTitle,
        sections: sections.map((item) => ({ title: item.title, knowledgePoints: item.knowledgePoints })),
        regenerate: Boolean(mindmap),
      });
      setMindmap(result.mindmap);
    } catch { setNotice('思维导图生成失败，请稍后重试。'); } finally { setMindmapLoading(false); }
  };

  return <div className="p-4 space-y-4">
    {notice && <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{notice}</p>}
    <section className="rounded-xl border border-amber-100 bg-amber-50/40 p-3 space-y-2">
      <p className="text-[10px] font-medium text-surface-400 uppercase tracking-wide">外部资源推荐</p>
      <button onClick={search} disabled={searching || !section} className="w-full inline-flex justify-center items-center gap-1.5 rounded-lg bg-amber-500 px-3 py-2 text-xs font-medium text-white disabled:opacity-50">
        {searching ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}{searching ? '搜索中…' : recommendations ? '重新搜索' : '搜索相关资源'}
      </button>
      {recommendations?.warnings.map((warning, index) => <p key={index} className="text-xs text-amber-700">{warning}</p>)}
      {recommendations && <select value={resourceFilter} onChange={(event) => setResourceFilter(event.target.value as typeof resourceFilter)} className="w-full rounded-lg border border-amber-100 bg-white px-2 py-1.5 text-[11px] text-surface-600">
        <option value="all">全部类型</option><option value="video">视频</option><option value="article">文章</option><option value="course">课程</option><option value="paper">论文</option><option value="document">文档</option>
      </select>}
      <div className="space-y-2">
        {recommendations?.resources.filter((resource) => resourceFilter === 'all' || resource.resource_type === resourceFilter).map((resource) => <div key={resource.url} className="rounded-lg bg-white p-2.5 border border-amber-100">
          <p className="text-xs font-semibold text-surface-700 line-clamp-2">{resource.title}</p>
          <p className="mt-1 text-[10px] text-surface-400">{resource.resource_type} · {resource.source} · {resource.trust_level}</p>
          <p className="mt-1 text-[11px] text-surface-500 line-clamp-3">{resource.snippet}</p>
          <p className="mt-1 text-[10px] text-amber-700">{resource.reason}</p>
          {safeExternalUrl(resource.url) && <a href={resource.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-blue-600 hover:text-blue-700">打开原文 <ExternalLink size={11} /></a>}
        </div>)}
      </div>
    </section>

    <section className="rounded-xl border border-blue-100 bg-blue-50/40 p-3 space-y-2">
      <p className="text-[10px] font-medium text-surface-400 uppercase tracking-wide">生成学习资源</p>
      <div className="grid grid-cols-1 gap-1.5">
        {resourceTypes.map((type) => <button key={type} onClick={() => generate(type)} disabled={Boolean(generating) || !section} className="inline-flex items-center gap-1.5 rounded-lg bg-white px-2.5 py-2 text-left text-[11px] font-medium text-blue-700 border border-blue-100 hover:bg-blue-100 disabled:opacity-50">
          {generating === type ? <Loader2 size={12} className="animate-spin" /> : <FilePlus2 size={12} />}{generatedResourceLabels[type]}
        </button>)}
      </div>
      {preview && <div className="rounded-lg bg-white border border-blue-100 p-2.5"><p className="mb-1 text-[11px] font-semibold text-surface-700">已保存到资源库：{preview.title}</p><div className="max-h-40 overflow-auto text-xs"><Markdown content={preview.content} /></div><button onClick={() => nav(`/resources/${preview.id}`)} className="mt-2 text-[11px] font-medium text-blue-600">打开完整内容</button></div>}
    </section>

    <section className="rounded-xl border border-violet-100 bg-violet-50/40 p-3 space-y-2">
      <p className="text-[10px] font-medium text-surface-400 uppercase tracking-wide">章节思维导图</p>
      <button onClick={generateMindmap} disabled={mindmapLoading || !chapterId} className="w-full inline-flex justify-center items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-xs font-medium text-white disabled:opacity-50">
        {mindmapLoading ? <Loader2 size={13} className="animate-spin" /> : mindmap ? <RefreshCw size={13} /> : <Sparkles size={13} />}{mindmap ? '重新生成思维导图' : '生成章节思维导图'}
      </button>
      {mindmap ? <div className="rounded-lg bg-white border border-violet-100 p-2 overflow-auto"><MermaidDiagram definition={mindmap.mermaidDef} /><button onClick={() => nav(`/resources/${mindmap.id}`)} className="mt-2 text-[11px] font-medium text-violet-600">已保存到资源库，打开完整导图</button></div> : legacyMindmapId ? <button onClick={() => nav(`/resources/${legacyMindmapId}`)} className="text-xs font-medium text-violet-600">查看已有章节思维导图</button> : <p className="text-xs text-surface-400">暂未生成</p>}
    </section>
  </div>;
}
