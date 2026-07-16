// @ts-nocheck
import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { RefreshCw, ArrowRight, User, ChevronDown } from 'lucide-react';
import { getProfileRecommendations, type ProfileRecommendation } from '../../api/profile';
import { useProfile } from '../../hooks/useProfile';
import { useChatStore } from '../../store/chatStore';
import { useSubjectStore } from '../../store/subjectStore';
import type { Resource } from '../../types/resource';
import RecommendationCard from './RecommendationCard';
import { PageLoading, PageEmpty, PageError } from '../common/PageState';

// ── 分组定义（纯文本，无颜色图标）─────────────────────────────────────
interface RecommendationGroup {
  key: string;
  label: string;
  items: ProfileRecommendation[];
}

const GROUP_ORDER = ['weakness', 'preference', 'progress', 'difficulty', 'other'];

const GROUP_LABELS: Record<string, string> = {
  weakness: '薄弱补强',
  preference: '偏好匹配',
  progress: '进度推进',
  difficulty: '难度匹配',
  other: '其他推荐',
};

function classifyRecommendation(rec: ProfileRecommendation): string {
  const title = (rec.title || '').toLowerCase();
  const reason = (rec.reason || '').toLowerCase();
  const rtype = rec.recommendation_type || '';
  const source = rec.source || '';

  if (source === 'profile') {
    if (reason.includes('薄弱') || reason.includes('补强') || title.includes('补强')) return 'weakness';
    if (reason.includes('偏好') || reason.includes('适合')) return 'preference';
    if (reason.includes('难度')) return 'difficulty';
    return 'preference';
  }

  if (rtype === 'low_accuracy_topic' || rtype === 'frequent_weak_topic') return 'weakness';
  if (rtype === 'incomplete_practice') return 'progress';
  if (rtype === 'stage_incomplete' || rtype === 'incomplete_resource') return 'progress';
  return 'other';
}

// ── 画像摘要卡片 ───────────────────────────────────────────────────────
function ProfileSummaryCard() {
  const nav = useNavigate();
  const { profileV2, loading } = useProfile();

  if (loading || !profileV2) {
    return (
      <div className="bg-white rounded-xl border border-surface-200 p-5 animate-pulse">
        <div className="h-4 bg-surface-100 rounded w-20 mb-4" />
        <div className="grid grid-cols-4 gap-3">
          {[1, 2, 3, 4].map(i => (
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
    .filter(k => k.status === 'weak')
    .map(k => k.label)
    .slice(0, 3);

  const lastUpdated = profileV2.updated_at
    ? (() => { try { return new Date(profileV2.updated_at).toLocaleString('zh-CN'); } catch { return profileV2.updated_at; } })()
    : '—';

  const prefs = contentPrefs.length > 0 ? contentPrefs.join('、') : resourcePrefs.length > 0 ? resourcePrefs.join('、') : '—';

  return (
    <div className="bg-white rounded-xl border border-surface-200 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <User className="w-3.5 h-3.5 text-surface-400" />
          <span className="text-xs font-medium text-surface-600">学习画像</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-surface-400">{lastUpdated}</span>
          <button
            onClick={() => nav('/profile')}
            className="inline-flex items-center gap-0.5 text-[11px] text-surface-500 hover:text-surface-700"
          >
            详情 <ArrowRight size={10} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3 text-xs">
        <div>
          <span className="text-surface-400">专业背景</span>
          <p className="mt-0.5 text-surface-700 truncate">{background}</p>
        </div>
        <div>
          <span className="text-surface-400">内容偏好</span>
          <p className="mt-0.5 text-surface-700 truncate">{prefs}</p>
        </div>
        <div>
          <span className="text-surface-400">薄弱环节</span>
          <p className="mt-0.5 text-surface-700 truncate">
            {weakPoints.length > 0 ? `${weakPoints.length} 项` : '—'}
          </p>
        </div>
        <div>
          <span className="text-surface-400">画像完整度</span>
          <p className="mt-0.5 text-surface-700">
            {Math.round((profileV2.profile_completeness || 0) * 100)}%
          </p>
        </div>
      </div>
    </div>
  );
}

// ── 主组件 ────────────────────────────────────────────────────────────
export interface RecommendationsTabProps {
  localResources: Resource[];
}

export default function RecommendationsTab({ localResources }: RecommendationsTabProps) {
  const nav = useNavigate();
  const sessionId = useChatStore((s) => s.dataSessionId);
  const { profileV2 } = useProfile();

  const [recommendations, setRecommendations] = useState<ProfileRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dismissedIds, setDismissedIds] = useState<Set<number>>(new Set());
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const resourceMap = useMemo(() => {
    const map = new Map<string, Resource>();
    for (const r of localResources) {
      if (r.id) map.set(r.id, r);
    }
    return map;
  }, [localResources]);

  const fetchRecommendations = useCallback(async () => {
    if (!sessionId) { setLoading(false); setError('请先进入学习会话'); return; }
    setLoading(true);
    setError(null);
    try {
      const data = await getProfileRecommendations(sessionId);
      setRecommendations(data.recommendations || []);
      setDismissedIds(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : '推荐加载失败');
      setRecommendations([]);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { fetchRecommendations(); }, [fetchRecommendations]);

  const groups = useMemo(() => {
    const visible = recommendations.filter((_, i) => !dismissedIds.has(i));
    const grouped = new Map<string, ProfileRecommendation[]>();
    for (const rec of visible) {
      const g = classifyRecommendation(rec);
      if (!grouped.has(g)) grouped.set(g, []);
      grouped.get(g)!.push(rec);
    }
    const result: RecommendationGroup[] = [];
    for (const key of GROUP_ORDER) {
      const items = grouped.get(key);
      if (items && items.length > 0) {
        result.push({ key, label: GROUP_LABELS[key] || key, items });
      }
    }
    return result;
  }, [recommendations, dismissedIds]);

  const handleDismiss = useCallback((rec: ProfileRecommendation) => {
    const idx = recommendations.indexOf(rec);
    if (idx >= 0) {
      setDismissedIds(prev => { const next = new Set(prev); next.add(idx); return next; });
    }
  }, [recommendations]);

  const toggleGroup = (key: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  // ── 无画像 ──
  if (!loading && !error && !profileV2) {
    return (
      <PageEmpty
        icon={<User className="w-8 h-8" />}
        title="尚未构建学习画像"
        description="在对话中告诉 AI 你的课程、目标和偏好，系统将基于画像为你精准推荐学习资源"
      />
    );
  }

  // ── 加载中 ──
  if (loading) {
    return (
      <div className="space-y-4">
        <ProfileSummaryCard />
        <PageLoading text="正在生成推荐…" />
      </div>
    );
  }

  // ── 加载失败 ──
  if (error) {
    return (
      <div className="space-y-4">
        <ProfileSummaryCard />
        <PageError title="推荐加载失败" description={error} onRetry={fetchRecommendations} />
      </div>
    );
  }

  // ── 无推荐 ──
  if (groups.length === 0) {
    return (
      <div className="space-y-4">
        <ProfileSummaryCard />
        <PageEmpty
          icon={<RefreshCw className="w-8 h-8" />}
          title="暂无推荐"
          description="完成更多学习和诊断后，AI 将基于画像为你生成个性化的学习资源推荐"
        />
      </div>
    );
  }

  // ── 正常态 ──
  return (
    <div className="space-y-4 animate-fade-in">
      <ProfileSummaryCard />

      {/* 顶栏 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-surface-800">智能推荐</h2>
          <p className="text-xs text-surface-400 mt-0.5">
            共 {recommendations.length} 条，基于你的学习画像匹配
          </p>
        </div>
        <button
          onClick={fetchRecommendations}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-surface-500 hover:text-surface-700 hover:bg-surface-50 rounded-lg transition-colors"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {/* 分组列表 */}
      {groups.map(group => {
        const collapsed = collapsedGroups.has(group.key);
        return (
          <section key={group.key}>
            <button
              onClick={() => toggleGroup(group.key)}
              className="w-full flex items-center gap-2 mb-3 text-left"
            >
              <span className="text-xs font-medium text-surface-500">
                {group.label}
                <span className="ml-1.5 text-surface-300">{group.items.length}</span>
              </span>
              <span className="flex-1 h-px bg-surface-100" />
              <ChevronDown
                size={14}
                className={`text-surface-300 transition-transform ${collapsed ? '' : 'rotate-180'}`}
              />
            </button>

            {!collapsed && (
              <div className="grid grid-cols-3 gap-3">
                {group.items.map((rec, i) => (
                  <RecommendationCard
                    key={`${group.key}-${i}`}
                    recommendation={rec}
                    localResource={rec.target_resource_id ? resourceMap.get(rec.target_resource_id) : undefined}
                    onDismiss={handleDismiss}
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
