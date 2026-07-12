import { useEffect, useState } from 'react';
import { ExternalLink, FilePlus2, Loader2, RefreshCw, Search, Sparkles, FileText } from 'lucide-react';
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
        { key: 'document', label: '课程讲义' },
        { key: 'video', label: '教学视频' },
        { key: 'article', label: '练习题库' },
        { key: 'course', label: '实操案例' },
        { key: 'paper', label: '学术论文' },
        { key: 'document', label: '拓展阅读' },
        { key: 'video', label: '动画演示' },
      ].map(({ key, label }) => (
        <button key={label}
          onClick={async () => {
            setResourceFilter(key as any);
            if (!sessionId || !section) return;
            setSearching(true);
            try {
              setRecommendations(await recommendSectionResources(section.id, {
                sessionId, sectionTitle: section.title, knowledgePoints: section.knowledgePoints,
                language: 'zh-CN',
                resourceTypes: key === 'all' ? ['video','article','course','document','paper'] : [key],
              }));
            } catch { setRecommendations({ query: [], resources: [], status: 'failed', warnings: ['检索失败'] }); }
            finally { setSearching(false); }
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
        {recommendations.resources.filter(r => resourceFilter === 'all' || r.resource_type === resourceFilter).map(r => (
          <div key={r.url} className="rounded-lg bg-surface-50 p-2.5">
            <p className="text-xs font-medium text-surface-700 line-clamp-2">{r.title}</p>
            <p className="mt-0.5 text-[10px] text-surface-400">{r.resource_type} · {r.source}</p>
            <p className="mt-1 text-[11px] text-surface-500 line-clamp-2">{r.snippet}</p>
            {safeExternalUrl(r.url) && <a href={r.url} target="_blank" rel="noopener noreferrer"
              className="mt-1.5 inline-flex items-center gap-1 text-[10px] font-medium text-surface-500 hover:text-surface-700">
              打开 <ExternalLink size={10} /></a>}
          </div>
        ))}
      </div>
    )}

  </div>;
}
