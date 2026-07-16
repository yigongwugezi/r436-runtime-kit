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
  lecture: '课程讲义', mindmap: '思维导图', quiz: '练习题库', reading: '拓展阅读', practice: '实操案例',
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
      className="block bg-white rounded-xl border border-surface-200 p-4 hover:border-primary-200 hover:shadow-sm transition-all group"
    >
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-surface-100 flex items-center justify-center flex-shrink-0">
          {TYPE_ICONS[item.resource_type] || <FileText className="w-4 h-4 text-surface-500" />}
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-surface-800 line-clamp-2 group-hover:text-primary-600 transition-colors">
            {item.title}
          </h4>
          {item.snippet && (
            <p className="text-xs text-surface-500 mt-1 line-clamp-2 leading-relaxed">{item.snippet}</p>
          )}
          <div className="flex items-center gap-2 mt-2">
            <span className="text-[11px] text-primary-600 truncate max-w-[180px]">{host}</span>
            <span className="text-[10px] text-surface-300">·</span>
            <span className="text-[10px] text-surface-400">{WEB_TYPE_LABELS[item.resource_type] || item.resource_type}</span>
            {item.source && (
              <>
                <span className="text-[10px] text-surface-300">·</span>
                <span className="text-[10px] text-surface-400 truncate max-w-[100px]">{item.source}</span>
              </>
            )}
          </div>
        </div>
        <ExternalLink size={14} className="text-surface-300 flex-shrink-0 mt-1" />
      </div>
    </a>
  );
}

// ── 子组件：生成资源卡片 ──────────────────────────────────────────

function GeneratedCard({ item }: { item: GeneratedResourceItem }) {
  const nav = useNavigate();
  const diffLabel: Record<string, string> = { easy: '基础', medium: '进阶', hard: '挑战' };
  const diffBadge: Record<string, string> = { easy: 'bg-success-100 text-success-700', medium: 'bg-warning-100 text-warning-700', hard: 'bg-error-100 text-error-700' };

  return (
    <div
      onClick={() => item.id && nav(`/resources/${item.id}`)}
      className="bg-white rounded-xl border border-surface-200 p-4 hover:border-primary-200 hover:shadow-sm transition-all cursor-pointer group"
    >
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-primary-50 flex items-center justify-center flex-shrink-0">
          {TYPE_ICONS[item.type] || <FileText className="w-4 h-4 text-primary-600" />}
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-surface-800 truncate group-hover:text-primary-600 transition-colors">
            {item.title}
          </h4>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[11px] text-surface-400">{GEN_TYPE_LABELS[item.type] || item.type}</span>
            {item.difficulty && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded ${diffBadge[item.difficulty] || 'bg-surface-100 text-surface-500'}`}>
                {diffLabel[item.difficulty] || item.difficulty}
              </span>
            )}
          </div>
        </div>
        <ArrowRight size={14} className="text-surface-300 flex-shrink-0" />
      </div>
    </div>
  );
}

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

  const [categories, setCategories] = useState<RecommendCategory[]>([]);
  const [activeCategory, setActiveCategory] = useState<string>('recommended');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRecommendations = useCallback(async () => {
    if (!sessionId) { setLoading(false); setError('请先进入学习会话'); return; }
    setLoading(true);
    setError(null);
    try {
      const data = await recommendV2({ sessionId, subjectId });
      setCategories(data.categories || []);
      // Auto-switch to first non-empty category
      const firstNonEmpty = (data.categories || []).find((c) => {
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
  }, [sessionId, subjectId]);

  useEffect(() => { fetchRecommendations(); }, [fetchRecommendations]);

  // ── 无会话 ──
  if (!sessionId) {
    return <PageEmpty icon={<User className="w-8 h-8" />} title="请先进入学习会话" description="选择一个学习会话以获取个性化推荐" />;
  }

  // ── 加载中 ──
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

  // ── 加载失败 ──
  if (error) {
    return (
      <div className="space-y-4">
        <ProfileSummaryCard />
        <div className="flex flex-col items-center justify-center py-16 text-surface-400">
          <p className="text-sm text-error-600 mb-3">{error}</p>
          <button onClick={fetchRecommendations} className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 text-white text-sm rounded-xl hover:bg-primary-700 transition-colors">
            <RefreshCw size={14} />重试
          </button>
        </div>
      </div>
    );
  }

  // ── 无推荐 ──
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

  // ── 正常渲染 ──
  const activeCat = categories.find((c) => c.id === activeCategory);
  const badgeCount = (cat: RecommendCategory): number => {
    if (cat.items) return cat.items.length;
    if (cat.groups) return cat.groups.reduce((s, g) => s + g.items.length, 0);
    return 0;
  };

  return (
    <div className="space-y-4 animate-fade-in">
      <ProfileSummaryCard />

      {/* 顶栏 + 刷新 */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-surface-800">智能推荐</h2>
        <button
          onClick={fetchRecommendations}
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
            <div className="grid grid-cols-3 gap-3">
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

// ── 智能推荐卡片（内联，简化为纯展示）──────────────────────────────

function RecommendationCardItem({ rec }: { rec: any }) {
  const nav = useNavigate();
  const hasResource = Boolean(rec.target_resource_id);
  const priorityLabel: Record<string, string> = { high: '优先', medium: '推荐', low: '参考' };

  return (
    <div
      onClick={() => hasResource && nav(`/resources/${rec.target_resource_id}`)}
      className={`bg-white rounded-xl border border-surface-200 p-4 ${
        hasResource ? 'cursor-pointer group hover:border-surface-300 hover:shadow-sm' : 'opacity-60 cursor-default'
      } transition-all`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] text-surface-400">{priorityLabel[rec.priority] || '推荐'}</span>
        <span className="text-[10px] text-surface-300">{rec.source || 'db'}</span>
      </div>
      <h4 className={`text-sm font-medium text-surface-800 mb-1.5 line-clamp-2 ${hasResource ? 'group-hover:text-primary-600' : ''} transition-colors`}>
        {rec.title}
      </h4>
      {rec.reason && (
        <p className="text-xs text-surface-500 leading-relaxed line-clamp-2">{rec.reason}</p>
      )}
      {rec.confidence != null && (
        <p className="text-[10px] text-surface-400 mt-2">置信 {Math.round(rec.confidence * 100)}%</p>
      )}
    </div>
  );
}
