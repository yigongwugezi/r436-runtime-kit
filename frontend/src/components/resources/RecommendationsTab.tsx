// @ts-nocheck
import React, { useCallback, useEffect, useState } from 'react';
import { ExternalLink, FileText, Loader2, RefreshCw, Search, User, ArrowRight, BookOpen, Brain, Code, Lightbulb, Play } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { recommendV2, type RecommendCategory, type RecommendGroup, type WebSearchResultItem, type GeneratedResourceItem } from '../../api/resources';
import { useProfile } from '../../hooks/useProfile';
import { useChatStore } from '../../store/chatStore';
import { useSubjectStore } from '../../store/subjectStore';
import { PageLoading, PageEmpty } from '../common/PageState';

// ── 常量 ──────────────────────────────────────────────────────────────

const CATEGORY_TABS: { id: string; label: string; icon: React.ReactNode }[] = [
  { id: 'recommended', label: '智能推荐', icon: <User className="w-3.5 h-3.5" /> },
  { id: 'web_results', label: '联网资源', icon: <Search className="w-3.5 h-3.5" /> },
  { id: 'ai_generated', label: 'AI 生成', icon: <Brain className="w-3.5 h-3.5" /> },
];

const TYPE_ICONS: Record<string, React.ReactNode> = {
  article: <FileText className="w-3.5 h-3.5" />,
  video: <Play className="w-3.5 h-3.5" />,
  course: <BookOpen className="w-3.5 h-3.5" />,
  document: <FileText className="w-3.5 h-3.5" />,
  paper: <FileText className="w-3.5 h-3.5" />,
  lecture: <BookOpen className="w-3.5 h-3.5" />,
  mindmap: <Brain className="w-3.5 h-3.5" />,
  quiz: <FileText className="w-3.5 h-3.5" />,
  reading: <Lightbulb className="w-3.5 h-3.5" />,
  practice: <Code className="w-3.5 h-3.5" />,
};

const WEB_TYPE_LABELS: Record<string, string> = {
  article: '文章', video: '视频', course: '课程', document: '文档', paper: '论文',
};

const GEN_TYPE_LABELS: Record<string, string> = {
  lecture: '学习文档', mindmap: '思维导图', quiz: '练习题库', reading: '拓展阅读', practice: '实操案例',
};

// ──画像摘要卡片（复用）─────────────────────────────────────────────

function ProfileSummaryCard() {
  const nav = useNavigate();
  const { profileV2, loading } = useProfile();

  if (loading || !profileV2) {
    return (
      <div className="bg-white rounded-xl border border-surface-200 p-5 animate-pulse">
        <div className="h-4 bg-surface-100 rounded w-20 mb-4" />
        <div className="grid grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-14 bg-surface-50 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  const ctx = profileV2.subject_context || {};
  const background = ctx.background || '—';
  const contentPrefs = (ctx.content_preferences || []).slice(0, 2);
  const resourcePrefs = (ctx.resource_preferences || []).slice(0, 2);
  const weakPoints = (profileV2.knowledge_mastery || [])
    .filter((k) => k.status === 'weak')
    .map((k) => k.label)
    .slice(0, 3);
  const prefs = contentPrefs.length > 0 ? contentPrefs.join('、') : resourcePrefs.length > 0 ? resourcePrefs.join('、') : '—';
  const lastUpdated = profileV2.updated_at
    ? (() => { try { return new Date(profileV2.updated_at).toLocaleString('zh-CN'); } catch { return profileV2.updated_at; } })()
    : '—';

  return (
    <div className="bg-white rounded-xl border border-surface-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <User className="w-3.5 h-3.5 text-surface-400" />
          <span className="text-xs font-medium text-surface-600">学习画像</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-surface-400">{lastUpdated}</span>
          <button onClick={() => nav('/profile')} className="inline-flex items-center gap-0.5 text-[11px] text-surface-500 hover:text-surface-700">
            详情 <ArrowRight size={10} />
          </button>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-3 text-xs">
        <div><span className="text-surface-400">专业背景</span><p className="mt-0.5 text-surface-700 truncate">{background}</p></div>
        <div><span className="text-surface-400">内容偏好</span><p className="mt-0.5 text-surface-700 truncate">{prefs}</p></div>
        <div><span className="text-surface-400">薄弱环节</span><p className="mt-0.5 text-surface-700 truncate">{weakPoints.length > 0 ? `${weakPoints.length} 项` : '—'}</p></div>
        <div><span className="text-surface-400">画像完整度</span><p className="mt-0.5 text-surface-700">{Math.round((profileV2.profile_completeness || 0) * 100)}%</p></div>
      </div>
    </div>
  );
}

// ── 子组件：联网资源卡片 ──────────────────────────────────────────

function WebResultCard({ item }: { item: WebSearchResultItem }) {
  const host = (() => { try { return new URL(item.url).hostname.replace(/^www\./, ''); } catch { return ''; } })();
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block bg-white rounded-xl border border-surface-200 p-4 hover:border-primary-200 hover:shadow-sm transition-all group h-full"
    >
      <div className="flex flex-col h-full">
        {/* 类型标记行 */}
        <div className="flex items-center justify-between mb-2">
          <span className="inline-flex items-center gap-1.5 text-[11px] text-surface-500">
            <span className="text-surface-400">{TYPE_ICONS[item.resource_type] || <FileText className="w-3.5 h-3.5" />}</span>
            {WEB_TYPE_LABELS[item.resource_type] || item.resource_type}
          </span>
          <span className="text-[10px] text-primary-600 truncate max-w-[140px]">{host}</span>
        </div>

        {/* 标题 */}
        <h4 className="text-sm font-medium text-surface-800 line-clamp-2 group-hover:text-primary-600 transition-colors mb-2">
          {item.title}
        </h4>

        {/* 描述 — 资源内容概要 */}
        {item.snippet && (
          <p className="text-xs text-surface-500 line-clamp-3 leading-relaxed flex-1">{item.snippet}</p>
        )}
        {!item.snippet && (
          <p className="text-xs text-surface-400 line-clamp-3 leading-relaxed flex-1 italic">暂无内容摘要</p>
        )}

        {/* 底部 */}
        <div className="flex items-center justify-between mt-3 pt-2 border-t border-surface-100">
          <span className="text-[10px] text-surface-400">外部链接</span>
          <span className="inline-flex items-center gap-1 text-[11px] text-primary-600 font-medium">
            打开 <ExternalLink size={11} />
          </span>
        </div>
      </div>
    </a>
  );
}

// ── 子组件：生成资源卡片 ──────────────────────────────────────────

function GeneratedCard({ item }: { item: GeneratedResourceItem }) {
  const nav = useNavigate();
  const diffLabel: Record<string, string> = { easy: '基础', medium: '进阶', hard: '挑战' };
  const diffBadge: Record<string, string> = { easy: 'bg-success-100 text-success-700', medium: 'bg-warning-100 text-warning-700', hard: 'bg-error-100 text-error-700' };
  // Extract readable description from content if backend description is too generic
  const description = (() => {
    if (item.description && !item.description.startsWith('围绕') && item.description.length > 8) return item.description;
    if (item.content) {
      const clean = item.content.replace(/^#\s+.*$/m, '').replace(/[#*`\n|]/g, ' ').replace(/\s+/g, ' ').trim();
      return clean.slice(0, 140) + (clean.length > 140 ? '…' : '');
    }
    return item.description || GEN_TYPE_LABELS[item.type] || item.type;
  })();
  const estimatedMinutes = item.estimated_minutes || item.estimatedMinutes;

  return (
    <div
      onClick={() => item.id && nav(`/resources/${item.id}`)}
      className="bg-white rounded-xl border border-surface-200 p-4 hover:border-primary-200 hover:shadow-sm transition-all cursor-pointer group h-full"
    >
      <div className="flex flex-col h-full">
        {/* 类型标记行 */}
        <div className="flex items-center justify-between mb-2">
          <span className="inline-flex items-center gap-1.5 text-[11px] text-surface-500">
            <span className="text-primary-500">{TYPE_ICONS[item.type] || <FileText className="w-3.5 h-3.5" />}</span>
            {GEN_TYPE_LABELS[item.type] || item.type}
          </span>
          {item.difficulty && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${diffBadge[item.difficulty] || 'bg-surface-100 text-surface-500'}`}>
              {diffLabel[item.difficulty] || item.difficulty}
            </span>
          )}
        </div>

        {/* 标题 */}
        <h4 className="text-sm font-medium text-surface-800 line-clamp-2 group-hover:text-primary-600 transition-colors mb-2">
          {item.title}
        </h4>

        {/* 描述 — 从内容提取的概要 */}
        {description && (
          <p className="text-xs text-surface-500 line-clamp-3 leading-relaxed flex-1">{description}</p>
        )}
        {!description && (
          <p className="text-xs text-surface-400 line-clamp-3 leading-relaxed flex-1 italic">查看资源内容</p>
        )}

        {/* 底部元信息 */}
        <div className="flex items-center justify-between mt-3 pt-2 border-t border-surface-100">
          <div className="flex items-center gap-3 text-[10px] text-surface-400">
            {estimatedMinutes != null && estimatedMinutes > 0 && <span>约 {estimatedMinutes} 分钟</span>}
            <span>AI 生成</span>
          </div>
          <span className="inline-flex items-center gap-1 text-[11px] text-primary-600 font-medium">
            {item.id ? '查看详情' : '预览'} <ArrowRight size={11} />
          </span>
        </div>
      </div>
    </div>
  );
}

// ── 子组件：DB 推荐资源卡片（全面，与生成卡片一致）────────────────

function RecommendationCardItem({ rec }: { rec: any }) {
  const nav = useNavigate();
  const hasResource = Boolean(rec.target_resource_id);
  const priorityLabel: Record<string, string> = { high: '优先', medium: '推荐', low: '参考' };
  const priorityBadge: Record<string, string> = { high: 'bg-primary-100 text-primary-700', medium: 'bg-surface-100 text-surface-600', low: 'bg-surface-50 text-surface-400' };

  return (
    <div
      onClick={() => hasResource && nav(`/resources/${rec.target_resource_id}`)}
      className={`bg-white rounded-xl border border-surface-200 p-4 ${
        hasResource ? 'cursor-pointer group hover:border-primary-200 hover:shadow-sm' : 'opacity-60 cursor-default'
      } transition-all h-full`}
    >
      <div className="flex flex-col h-full">
        {/* 优先级 + 来源 */}
        <div className="flex items-center justify-between mb-2">
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${priorityBadge[rec.priority] || 'bg-surface-100 text-surface-500'}`}>
            {priorityLabel[rec.priority] || '推荐'}
          </span>
          <span className="text-[10px] text-surface-400">{rec.source || 'db'}</span>
        </div>

        {/* 标题 */}
        <h4 className={`text-sm font-medium text-surface-800 line-clamp-2 mb-2 ${hasResource ? 'group-hover:text-primary-600' : ''} transition-colors`}>
          {rec.title}
        </h4>

        {/* 推荐理由 + 内容概要 */}
        {rec.reason && (
          <p className="text-xs text-surface-500 line-clamp-3 leading-relaxed flex-1">{rec.reason}</p>
        )}
        {!rec.reason && (
          <p className="text-xs text-surface-400 line-clamp-3 leading-relaxed flex-1 italic">继续学习该资源以巩固知识</p>
        )}

        {/* 置信度 */}
        <div className="flex items-center justify-between mt-3 pt-2 border-t border-surface-100">
          {rec.confidence != null && (
            <span className="text-[10px] text-surface-400">置信 {Math.round(rec.confidence * 100)}%</span>
          )}
          {hasResource ? (
            <span className="inline-flex items-center gap-1 text-[11px] text-surface-700 font-medium ml-auto">
              开始学习 <ArrowRight size={11} />
            </span>
          ) : (
            <span className="text-[10px] text-surface-400 ml-auto">暂无关联资源</span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── 缓存：避免每次切 Tab 都重新请求 ──────────────────────────────
const cache = new Map<string, { categories: RecommendCategory[]; expiresAt: number }>();
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 分钟

// ── 主组件 ──────────────────────────────────────────────────────────

export interface RecommendationsTabProps {
  sessionId?: string | null;
  subjectId?: string;
}

export default function RecommendationsTab({ sessionId: propSessionId, subjectId: propSubjectId }: RecommendationsTabProps) {
  const storeSessionId = useChatStore((s) => s.currentSessionId);
  const storeSubjectId = useSubjectStore((s) => s.activeSubject?.id || '');
  const sessionId = propSessionId ?? storeSessionId;
  const subjectId = propSubjectId ?? storeSubjectId;
  const cacheKey = `${sessionId}:${subjectId}`;

  const [categories, setCategories] = useState<RecommendCategory[]>(() => {
    const cached = cache.get(cacheKey);
    if (cached && cached.expiresAt > Date.now()) return cached.categories;
    return [];
  });
  const [activeCategory, setActiveCategory] = useState<string>('recommended');
  const [fetched, setFetched] = useState(() => {
    const cached = cache.get(cacheKey);
    return !!(cached && cached.expiresAt > Date.now());
  });
  const [loading, setLoading] = useState(!fetched);
  const [error, setError] = useState<string | null>(null);

  const fetchRecommendations = useCallback(async (force = false) => {
    if (!sessionId) { setLoading(false); setError('请先进入学习会话'); return; }
    // Check cache again (may have been populated since mount)
    if (!force) {
      const cached = cache.get(cacheKey);
      if (cached && cached.expiresAt > Date.now()) {
        setCategories(cached.categories);
        setFetched(true);
        setLoading(false);
        const firstNonEmpty = cached.categories.find((c) => {
          if (c.items && c.items.length > 0) return true;
          if (c.groups && c.groups.some((g) => g.items.length > 0)) return true;
          return false;
        });
        if (firstNonEmpty) setActiveCategory(firstNonEmpty.id);
        return;
      }
    }
    setLoading(true);
    setError(null);
    try {
      const data = await recommendV2({ sessionId, subjectId });
      const cats = data.categories || [];
      cache.set(cacheKey, { categories: cats, expiresAt: Date.now() + CACHE_TTL_MS });
      setCategories(cats);
      setFetched(true);
      const firstNonEmpty = cats.find((c) => {
        if (c.items && c.items.length > 0) return true;
        if (c.groups && c.groups.some((g) => g.items.length > 0)) return true;
        return false;
      });
      if (firstNonEmpty) setActiveCategory(firstNonEmpty.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : '推荐加载失败');
      setCategories([]);
    } finally {
      setLoading(false);
    }
  }, [sessionId, subjectId, cacheKey]);

  useEffect(() => { if (!fetched) fetchRecommendations(); }, [fetched, fetchRecommendations]);

  if (!sessionId) {
    return <PageEmpty icon={<User className="w-8 h-8" />} title="请先进入学习会话" description="选择一个学习会话以获取个性化推荐" />;
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <ProfileSummaryCard />
        <div className="flex flex-col items-center justify-center py-16 text-surface-400">
          <Loader2 className="w-8 h-8 animate-spin mb-3" />
          <p className="text-sm">正在联网搜索并生成学习资源…</p>
          <p className="text-xs mt-1 text-surface-300">同时查找外部资料和生成针对性内容</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <ProfileSummaryCard />
        <div className="flex flex-col items-center justify-center py-16 text-surface-400">
          <p className="text-sm text-error-600 mb-3">{error}</p>
          <button onClick={() => fetchRecommendations(true)} disabled={loading} className="inline-flex items-center gap-1.5 px-3 py-2 bg-primary-600 text-white text-sm rounded-xl hover:bg-primary-700 transition-colors">
            <RefreshCw size={14} />重试
          </button>
        </div>
      </div>
    );
  }

  const hasAnyContent = categories.some((c) => {
    if (c.items && c.items.length > 0) return true;
    if (c.groups && c.groups.some((g) => g.items.length > 0)) return true;
    return false;
  });

  if (!hasAnyContent) {
    return (
      <div className="space-y-4">
        <ProfileSummaryCard />
        <PageEmpty
          icon={<RefreshCw className="w-8 h-8" />}
          title="暂无推荐"
          description="完成更多学习和诊断后，系统将基于画像为你推荐学习资源"
        />
      </div>
    );
  }

  const activeCat = categories.find((c) => c.id === activeCategory);
  const badgeCount = (cat: RecommendCategory): number => {
    if (cat.items) return cat.items.length;
    if (cat.groups) return cat.groups.reduce((s, g) => s + g.items.length, 0);
    return 0;
  };

  return (
    <div className="space-y-4 animate-fade-in">
      <ProfileSummaryCard />

      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-surface-800">智能推荐</h2>
        <button
          onClick={() => fetchRecommendations(true)}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-surface-500 hover:text-surface-700 hover:bg-surface-50 rounded-lg transition-colors"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {/* 分类 Tab */}
      <div className="flex gap-1 bg-surface-100 rounded-xl p-1">
        {categories.map((cat) => {
          const isActive = cat.id === activeCategory;
          const count = badgeCount(cat);
          return (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id)}
              disabled={count === 0}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg transition-all ${
                isActive
                  ? 'bg-white text-surface-800 shadow-sm'
                  : 'text-surface-400 hover:text-surface-600 disabled:opacity-40 disabled:cursor-not-allowed'
              }`}
            >
              {CATEGORY_TABS.find((t) => t.id === cat.id)?.icon}
              {cat.label}
              {count > 0 && <span className="text-[10px] text-surface-400 ml-0.5">({count})</span>}
            </button>
          );
        })}
      </div>

      {/* 分类内容 */}
      {activeCat && (
        <div className="space-y-4">
          {activeCat.description && (
            <p className="text-xs text-surface-400">{activeCat.description}</p>
          )}

          {/* 智能推荐：flat list */}
          {activeCat.id === 'recommended' && activeCat.items && (
            <div className="grid grid-cols-2 gap-3">
              {activeCat.items.map((rec, i) => (
                <RecommendationCardItem key={i} rec={rec} />
              ))}
            </div>
          )}

          {/* 联网资源 / AI 生成：分组展示 */}
          {(activeCat.id === 'web_results' || activeCat.id === 'ai_generated') && activeCat.groups && (
            <div className="space-y-6">
              {activeCat.groups.map((group, gi) => (
                <section key={`${activeCat.id}-${gi}`}>
                  <h4 className="text-xs font-medium text-surface-500 mb-3 flex items-center gap-1.5">
                    {TYPE_ICONS[group.type]}
                    {group.label}
                    <span className="text-surface-300 ml-0.5">({group.items.length})</span>
                  </h4>
                  <div className="grid grid-cols-2 gap-3">
                    {group.items.map((item, ii) => (
                      activeCat.id === 'web_results'
                        ? <WebResultCard key={ii} item={item as WebSearchResultItem} />
                        : <GeneratedCard key={ii} item={item as GeneratedResourceItem} />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}

          {/* 空的分类 */}
          {activeCat.items?.length === 0 && (!activeCat.groups || activeCat.groups.every((g) => g.items.length === 0)) && (
            <div className="flex flex-col items-center justify-center py-12 text-surface-400">
              <p className="text-sm">暂无结果</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
