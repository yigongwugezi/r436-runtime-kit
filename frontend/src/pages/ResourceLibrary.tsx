import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search, Filter, BookOpen, Brain, Code, FileText, Lightbulb,
  Play, Presentation, Clock, Star, ChevronRight, BookmarkPlus,
  BookmarkCheck, CheckCircle2, MessageSquare, X, Send, Sparkles,
} from 'lucide-react';
import { useResources } from '../hooks/useResources';
import type { Resource } from '../types/resource';
import type { ResourceType } from '../types/chat';
import { RESOURCE_TYPE_LABELS } from '../utils/constants';
import { timeAgo, formatDuration } from '../utils/format';
import Loading from '../components/common/Loading';
import EmptyState from '../components/common/EmptyState';
import Modal from '../components/common/Modal';
import Markdown from '../utils/markdown';
import MermaidDiagram from '../utils/mermaid';
import { submitFeedback, logStudyEvent } from '../api/feedback';

/* ===================================================================
 * 常量定义
 * =================================================================== */
const iconMap: Record<ResourceType, React.ReactNode> = {
  lecture:    <BookOpen className="w-5 h-5 text-blue-500" />,
  mindmap:    <Brain className="w-5 h-5 text-purple-500" />,
  quiz:       <FileText className="w-5 h-5 text-amber-500" />,
  reading:    <Lightbulb className="w-5 h-5 text-green-500" />,
  case_study: <Code className="w-5 h-5 text-cyan-500" />,
  video:      <Play className="w-5 h-5 text-red-500" />,
  ppt:        <Presentation className="w-5 h-5 text-orange-500" />,
};

const difficultyBadge: Record<string, string> = {
  easy:   'bg-green-50 text-green-600 border-green-200',
  medium: 'bg-amber-50 text-amber-600 border-amber-200',
  hard:   'bg-red-50 text-red-600 border-red-200',
};

const difficultyLabel: Record<string, string> = {
  easy: '基础', medium: '进阶', hard: '挑战',
};

const FILTER_TYPES: (ResourceType | undefined)[] = [
  undefined, 'lecture', 'mindmap', 'quiz', 'reading', 'case_study',
];

/* ===================================================================
 * 资源卡片
 * =================================================================== */
function ResourceCard({ resource, onClick }: { resource: Resource; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="group bg-white border border-gray-100 rounded-2xl p-5 text-left hover:shadow-lg hover:-translate-y-1 transition-all duration-300 w-full relative overflow-hidden"
    >
      {/* 顶部彩色条 */}
      <div className={`absolute top-0 left-0 right-0 h-1 ${
        resource.type === 'lecture' ? 'bg-blue-400' :
        resource.type === 'mindmap' ? 'bg-purple-400' :
        resource.type === 'quiz' ? 'bg-amber-400' :
        resource.type === 'case_study' ? 'bg-cyan-400' :
        'bg-green-400'
      }`} />

      <div className="flex items-start gap-3 mb-3 mt-1">
        <div className="w-10 h-10 rounded-xl bg-gray-50 flex items-center justify-center flex-shrink-0">
          {iconMap[resource.type]}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-gray-900 truncate">{resource.title}</h3>
          <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{resource.description}</p>
        </div>
        {/* 学习状态标记 */}
        {resource.studyStatus === 'completed' && (
          <CheckCircle2 className="w-5 h-5 text-green-500 flex-shrink-0" />
        )}
      </div>

      {/* 标签 */}
      <div className="flex flex-wrap items-center gap-1.5 mb-3">
        <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${difficultyBadge[resource.difficulty]}`}>
          {difficultyLabel[resource.difficulty]}
        </span>
        <span className="px-2 py-0.5 rounded-md text-[10px] text-gray-500 bg-gray-50 border border-gray-100">
          {RESOURCE_TYPE_LABELS[resource.type]}
        </span>
        {resource.tags.slice(0, 2).map((tag) => (
          <span key={tag} className="px-2 py-0.5 rounded-md text-[10px] text-gray-400 bg-gray-50">{tag}</span>
        ))}
      </div>

      {/* 底部信息 */}
      <div className="flex items-center justify-between text-[10px] text-gray-400">
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" />{formatDuration(resource.estimatedMinutes)}
        </span>
        <div className="flex items-center gap-2">
          {resource.bookmarked && <BookmarkCheck className="w-3 h-3 text-brand-500" />}
          <span className="flex items-center gap-1 text-brand-500 group-hover:translate-x-0.5 transition-transform">
            查看详情 <ChevronRight className="w-3 h-3" />
          </span>
        </div>
      </div>
    </button>
  );
}

/* ===================================================================
 * 筛选栏
 * =================================================================== */
function FilterBar({
  active, onFilter, onSelectDifficulty, activeDifficulty,
}: {
  active: ResourceType | undefined;
  onFilter: (type: ResourceType | undefined) => void;
  onSelectDifficulty: (level: string | undefined) => void;
  activeDifficulty: string | undefined;
}) {
  return (
    <div className="space-y-2">
      {/* 类型筛选 */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        <Filter className="w-4 h-4 text-gray-400 flex-shrink-0" />
        {FILTER_TYPES.map((t) => (
          <button
            key={t || 'all'}
            onClick={() => onFilter(t)}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium whitespace-nowrap transition-all ${
              active === t
                ? 'bg-gray-900 text-white shadow-sm'
                : 'bg-white border border-gray-200 text-gray-500 hover:border-gray-300 hover:bg-gray-50'
            }`}
          >
            {t ? RESOURCE_TYPE_LABELS[t] : '全部'}
          </button>
        ))}
      </div>

      {/* 难度筛选 */}
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] text-gray-400 flex-shrink-0">难度：</span>
        {[undefined, 'easy', 'medium', 'hard'].map((level) => (
          <button
            key={level || 'all-diff'}
            onClick={() => onSelectDifficulty(level)}
            className={`px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all ${
              activeDifficulty === level
                ? 'bg-gray-800 text-white'
                : 'bg-gray-50 text-gray-500 hover:bg-gray-100'
            }`}
          >
            {level ? difficultyLabel[level] : '不限'}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ===================================================================
 * 反馈表单
 * =================================================================== */
function FeedbackForm({
  resourceId, onSubmit, onCancel,
}: {
  resourceId: string;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  const [rating, setRating] = useState(0);
  const [hoverRating, setHoverRating] = useState(0);
  const [difficultyMatch, setDifficultyMatch] = useState<string>('');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (rating === 0) return;
    setSubmitting(true);
    try {
      await submitFeedback({ resourceId, rating, difficultyMatch: difficultyMatch as any, comment: comment || undefined });
      onSubmit();
    } catch { /* ignore */ }
    finally { setSubmitting(false); }
  };

  return (
    <div className="p-4 bg-gray-50 rounded-xl space-y-3">
      <h4 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
        <MessageSquare className="w-4 h-4 text-brand-500" />
        对这份资源评价
      </h4>

      {/* 星级评分 */}
      <div>
        <p className="text-xs text-gray-500 mb-1.5">综合评分</p>
        <div className="flex items-center gap-1">
          {[1, 2, 3, 4, 5].map((i) => (
            <button
              key={i}
              onClick={() => setRating(i)}
              onMouseEnter={() => setHoverRating(i)}
              onMouseLeave={() => setHoverRating(0)}
              className="transition-transform hover:scale-110"
            >
              <Star
                className="w-6 h-6"
                fill={(hoverRating || rating) >= i ? '#f59e0b' : 'none'}
                stroke={(hoverRating || rating) >= i ? '#f59e0b' : '#d1d5db'}
                strokeWidth={1.5}
              />
            </button>
          ))}
        </div>
      </div>

      {/* 难度匹配 */}
      <div>
        <p className="text-xs text-gray-500 mb-1.5">难度匹配</p>
        <div className="flex gap-1.5">
          {[
            { value: 'too_easy', label: '太简单' },
            { value: 'just_right', label: '刚刚好' },
            { value: 'too_hard', label: '太难了' },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => setDifficultyMatch(opt.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                difficultyMatch === opt.value
                  ? 'bg-brand-500 text-white'
                  : 'bg-white border border-gray-200 text-gray-500 hover:border-brand-300'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* 评论 */}
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="更多想法…（选填）"
        rows={2}
        className="w-full resize-none bg-white border border-gray-200 rounded-xl px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-brand-500"
      />

      <div className="flex items-center gap-2">
        <button
          onClick={handleSubmit}
          disabled={rating === 0 || submitting}
          className="flex items-center gap-1.5 px-4 py-2 bg-gray-900 text-white rounded-xl text-xs font-semibold hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
        >
          <Send className="w-3 h-3" />
          {submitting ? '提交中…' : '提交评价'}
        </button>
        <button onClick={onCancel} className="px-3 py-2 text-xs text-gray-400 hover:text-gray-600 transition-colors">
          取消
        </button>
      </div>
    </div>
  );
}

/* ===================================================================
 * 主页面
 * =================================================================== */
export default function ResourceLibrary() {
  const navigate = useNavigate();
  const { resources, total, loading, applyFilter, toggleBookmark } = useResources();
  const [selected, setSelected] = useState<Resource | null>(null);
  const [search, setSearch] = useState('');
  const [activeType, setActiveType] = useState<ResourceType | undefined>();
  const [activeDifficulty, setActiveDifficulty] = useState<string | undefined>();
  const [showFeedback, setShowFeedback] = useState(false);
  const [showThanks, setShowThanks] = useState(false);

  // 收藏切换
  const handleBookmark = useCallback(async (id: string) => {
    await toggleBookmark(id);
    if (selected?.id === id) {
      setSelected((prev) => prev ? { ...prev, bookmarked: !prev.bookmarked } : null);
    }
  }, [toggleBookmark, selected?.id]);

  // 完成学习
  const handleComplete = useCallback(async (resource: Resource) => {
    await logStudyEvent({
      event: 'resource_complete',
      resourceId: resource.id,
      metadata: { type: resource.type },
    });
    setSelected((prev) => prev ? { ...prev, studyStatus: 'completed' } : null);
  }, []);

  // 打开资源详情
  const openDetail = useCallback(async (resource: Resource) => {
    setSelected(resource);
    setShowFeedback(false);
    setShowThanks(false);
    // 上报查看事件
    await logStudyEvent({
      event: 'resource_view',
      resourceId: resource.id,
      metadata: { type: resource.type },
    });
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 md:py-8">
      {/* ========== 头部 ========== */}
      <div className="mb-6">
        <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-1">资源库</h1>
        <p className="text-sm text-gray-500">
          共 <span className="font-semibold text-gray-700">{total}</span> 个学习资源，由多智能体协同为你个性化生成
        </p>
      </div>

      {/* ========== 搜索 + 筛选 ========== */}
      <div className="space-y-3 mb-6">
        <div className="relative max-w-md">
          <Search className="w-4 h-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              applyFilter({ search: e.target.value });
            }}
            placeholder="搜索资源标题、知识点…"
            className="w-full h-10 pl-10 pr-4 bg-white border border-gray-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
        </div>
        <FilterBar
          active={activeType}
          onFilter={(type) => { setActiveType(type); applyFilter({ type }); }}
          onSelectDifficulty={(d) => { setActiveDifficulty(d); applyFilter({ difficulty: d }); }}
          activeDifficulty={activeDifficulty}
        />
      </div>

      {/* ========== 列表 ========== */}
      {loading ? (
        <Loading text="加载资源中…" />
      ) : !resources || resources.length === 0 ? (
        <EmptyState
          icon={<BookOpen className="w-8 h-8" />}
          title={search || activeType || activeDifficulty ? '没有匹配的资源' : '暂无资源'}
          description={
            search || activeType || activeDifficulty
              ? '尝试调整筛选条件或搜索关键词'
              : '在 AI 对话中描述学习需求，多智能体将为你生成个性化学习资源'
          }
          action={
            !search && !activeType && !activeDifficulty ? (
              <button
                onClick={() => navigate('/chat')}
                className="mt-3 px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all inline-flex items-center gap-2"
              >
                <Sparkles className="w-4 h-4" />
                去对话页生成资源
              </button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {resources.map((r) => (
            <ResourceCard key={r.id} resource={r} onClick={() => openDetail(r)} />
          ))}
        </div>
      )}

      {/* ========== 资源详情弹窗 ========== */}
      <Modal open={!!selected} onClose={() => setSelected(null)} title={selected?.title} wide>
        {selected && (
          <div className="space-y-4">
            {/* 元信息 */}
            <div className="flex flex-wrap items-center gap-2">
              <span className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${difficultyBadge[selected.difficulty]}`}>
                {difficultyLabel[selected.difficulty]}
              </span>
              <span className="px-2.5 py-1 rounded-lg text-xs text-gray-500 bg-gray-50 border border-gray-100">
                {RESOURCE_TYPE_LABELS[selected.type]}
              </span>
              <span className="text-xs text-gray-400">· {formatDuration(selected.estimatedMinutes)}</span>
              <span className="text-xs text-gray-400">· {timeAgo(selected.createdAt)}</span>
              {selected.studyStatus === 'completed' && (
                <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-green-50 text-green-600 border border-green-200">
                  ✅ 已完成
                </span>
              )}
            </div>

            {/* 描述 */}
            <p className="text-sm text-gray-500">{selected.description}</p>

            {/* 知识点标签 */}
            <div className="flex flex-wrap gap-1.5">
              {selected.knowledgePoints.map((kp) => (
                <span key={kp} className="px-2 py-0.5 bg-brand-50 text-brand-600 rounded-md text-[10px] font-medium">
                  {kp}
                </span>
              ))}
            </div>

            {/* 操作按钮组 */}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {/* 收藏 */}
              <button
                onClick={() => handleBookmark(selected.id)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                  selected.bookmarked
                    ? 'bg-brand-50 text-brand-600 border-brand-200'
                    : 'bg-white text-gray-500 border-gray-200 hover:border-brand-300'
                }`}
              >
                {selected.bookmarked ? <BookmarkCheck className="w-3.5 h-3.5" /> : <BookmarkPlus className="w-3.5 h-3.5" />}
                {selected.bookmarked ? '已收藏' : '收藏'}
              </button>

              {/* 完成学习 */}
              {selected.studyStatus !== 'completed' && (
                <button
                  onClick={() => handleComplete(selected)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-green-50 text-green-600 border border-green-200 hover:bg-green-100 transition-all"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  标记完成
                </button>
              )}

              {/* 反馈 */}
              {!showFeedback && !showThanks && (
                <button
                  onClick={() => setShowFeedback(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-50 text-gray-500 border border-gray-100 hover:bg-gray-100 transition-all"
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  评价资源
                </button>
              )}
            </div>

            {/* 反馈表单 */}
            {showFeedback && (
              <FeedbackForm
                resourceId={selected.id}
                onSubmit={() => { setShowFeedback(false); setShowThanks(true); }}
                onCancel={() => setShowFeedback(false)}
              />
            )}

            {/* 感谢提示 */}
            {showThanks && (
              <div className="p-3 bg-green-50 border border-green-100 rounded-xl flex items-center gap-2 text-xs text-green-600">
                <CheckCircle2 className="w-4 h-4" />
                感谢你的反馈！系统将根据评价优化后续资源推荐
              </div>
            )}

            {/* 资源内容 */}
            <div className="prose-custom text-sm text-gray-800 leading-relaxed p-5 bg-gray-50/80 rounded-xl max-h-[55vh] overflow-y-auto border border-gray-100">
              {/* Markdown 渲染 */}
              <Markdown content={selected.content} />
              {/* Mermaid 图表 */}
              {selected.mermaidDef && (
                <div className="mt-4 p-3 bg-white rounded-xl border border-gray-100">
                  <p className="text-xs text-gray-400 mb-2">知识图谱</p>
                  <MermaidDiagram definition={selected.mermaidDef} />
                </div>
              )}
              {/* 代码块 */}
              {selected.codeBlocks && selected.codeBlocks.length > 0 && (
                <div className="mt-4 space-y-3">
                  <p className="text-xs text-gray-400">代码示例</p>
                  {selected.codeBlocks.map((block, i) => (
                    <div key={i} className="bg-gray-900 text-gray-100 rounded-xl p-4 overflow-x-auto">
                      <pre className="text-xs font-mono"><code>{block.code}</code></pre>
                      {block.explanation && (
                        <p className="text-[10px] text-gray-400 mt-2">{block.explanation}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {/* 题目 */}
              {selected.questions && selected.questions.length > 0 && (
                <div className="mt-4 space-y-4">
                  <p className="text-xs text-gray-400 font-medium">练习题 ({selected.questions.length} 题)</p>
                  {selected.questions.map((q, i) => (
                    <div key={q.id} className="p-3 bg-white border border-gray-100 rounded-xl">
                      <p className="text-xs font-medium text-gray-800">
                        {i + 1}. {q.stem}
                      </p>
                      {q.options && (
                        <div className="mt-2 space-y-1">
                          {q.options.map((opt, oi) => (
                            <div key={oi} className="text-xs text-gray-600 pl-3">
                              {String.fromCharCode(65 + oi)}. {opt}
                            </div>
                          ))}
                        </div>
                      )}
                      <details className="mt-2">
                        <summary className="text-[10px] text-brand-500 cursor-pointer hover:underline">查看答案</summary>
                        <p className="text-[10px] text-green-600 mt-1">答案：{q.answer}</p>
                        <p className="text-[10px] text-gray-400 mt-0.5">{q.explanation}</p>
                      </details>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 底部提示 */}
            <p className="text-[10px] text-gray-400 text-center pt-2">
              AI 生成内容仅供参考 · 如需深入学习请查阅课程教材
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
}
