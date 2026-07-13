import { useEffect, useRef, useState } from 'react';
import { ExternalLink, FilePlus2, Loader2, RefreshCw, Search, Sparkles, FileText } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Markdown from '../../utils/markdown';
import MermaidDiagram from '../../utils/mermaid';
import {
  generateSectionMindmap,
  generateSectionResource,
  generatedResourceLabels,
  getSectionMindmap,
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
const platformLabels: Record<string, string> = { bilibili: 'B站', youtube: 'YouTube', vimeo: 'Vimeo', icourse163: '中国大学MOOC', xuetangx: '学堂在线', smartedu: '智慧教育平台', imooc: '慕课网', youku: '优酷', iqiyi: '爱奇艺', douyin: '抖音', tencent_video: '腾讯视频' };
const trustLabels: Record<string, string> = { official: '官方来源', educational: '教育来源', general: '普通来源' };
const matchLevelLabels: Record<string, string> = { exact_topic: '精确匹配', chapter_level: '章节匹配', course_level: '课程拓展', expanded_research: '拓展论文' };

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
  const requestSerial = useRef(0);

  useEffect(() => {
    let active = true;
    if (!sessionId || !section?.id) { setGenerated([]); return; }
    getGeneratedSectionResources(section.id, sessionId).then((items) => active && setGenerated(items)).catch(() => active && setGenerated([]));
    return () => { active = false; };
  }, [sessionId, section?.id]);

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
        language: 'zh-CN', resourceTypes: filter === 'all' ? ['video', 'article', 'course', 'document', 'paper'] : [filter],
      });
      if (requestId === requestSerial.current) setRecommendations(result);
    } catch {
      if (requestId === requestSerial.current) setRecommendations({ query: [], resources: [], status: 'failed', warnings: ['外部资源检索失败，请稍后重试。'] });
    } finally { if (requestId === requestSerial.current) setSearching(false); }
  };
  const search = () => searchResources(resourceFilter);

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
    if (!sessionId || !section) return;
    setMindmapLoading(true);
    setNotice('');
    try {
      const result = await generateSectionMindmap(section.id, {
        sessionId, pathId, stageId, sectionTitle: section.title,
        knowledgePoints: section.knowledgePoints,
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
          </div>
        ))}
      </div>
    )}

  </div>;
}
