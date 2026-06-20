import { useState, useCallback, useEffect, useRef } from 'react';
import { useNavigate, useParams, useLocation, useSearchParams } from 'react-router-dom';
import {
  Search, Filter, BookOpen, Brain, Code, FileText, Lightbulb,
  Play, Presentation, Clock, Star, ChevronRight, BookmarkPlus,
  BookmarkCheck, CheckCircle2, MessageSquare, X, Send, Sparkles,
  HelpCircle, Check, XCircle, RefreshCw, AlertCircle,
} from 'lucide-react';
import { useResources } from '../hooks/useResources';
import { useChatStore } from '../store/chatStore';
import { useProfileStore } from '../store/profileStore';
import { useSubjectStore } from '../store/subjectStore';
import type { Resource } from '../types/resource';
import type { ResourceType } from '../types/chat';
import { RESOURCE_TYPE_LABELS } from '../utils/constants';
import { timeAgo, formatDuration } from '../utils/format';
import Loading from '../components/common/Loading';
import EmptyState from '../components/common/EmptyState';
import Modal from '../components/common/Modal';
import Markdown from '../utils/markdown';
import MermaidDiagram from '../utils/mermaid';
import client from '../api/client';
import { submitFeedback, logStudyEvent } from '../api/feedback';
import SourceBadge, { type DataSource } from '../components/common/SourceBadge';
import { SourceTag, RefreshOverlay, PageError } from '../components/common/PageState';

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
  const colorMap: Record<string, string> = {
    lecture:    'from-blue-400 to-blue-500',
    mindmap:    'from-purple-400 to-purple-500',
    quiz:       'from-amber-400 to-orange-500',
    case_study: 'from-cyan-400 to-teal-500',
    reading:    'from-emerald-400 to-green-500',
    video:      'from-red-400 to-rose-500',
    ppt:        'from-orange-400 to-amber-500',
  };
  const bgMap: Record<string, string> = {
    lecture:    'bg-blue-50',
    mindmap:    'bg-purple-50',
    quiz:       'bg-amber-50',
    case_study: 'bg-cyan-50',
    reading:    'bg-emerald-50',
    video:      'bg-red-50',
    ppt:        'bg-orange-50',
  };

  return (
    <button
      onClick={onClick}
      className="group bg-white border border-gray-100 rounded-2xl text-left hover:shadow-xl hover:-translate-y-1.5 transition-all duration-300 w-full relative overflow-hidden"
    >
      {/* 顶部渐变条 */}
      <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${colorMap[resource.type] || 'from-gray-400 to-gray-500'}`} />

      {/* 装饰光晕 */}
      <div className={`absolute -bottom-8 -right-8 w-20 h-20 ${bgMap[resource.type] || 'bg-gray-50'} rounded-full opacity-60 group-hover:scale-150 transition-transform duration-500`} />

      <div className="relative p-5 pt-4">
        <div className="flex items-start gap-3 mb-3">
          <div className={`w-11 h-11 rounded-xl ${bgMap[resource.type] || 'bg-gray-50'} flex items-center justify-center flex-shrink-0 shadow-sm group-hover:scale-110 group-hover:shadow-md transition-all duration-300`}>
            {iconMap[resource.type]}
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-gray-900 truncate group-hover:text-gray-700 transition-colors">{resource.title}</h3>
            <p className="text-xs text-gray-400 mt-0.5 line-clamp-2 leading-relaxed">{resource.description}</p>
            <div className="mt-1.5">
              <SourceTag source={resource.source} />
            </div>
          </div>
          {/* 学习状态标记 */}
          {resource.studyStatus === 'completed' && (
            <div className="w-6 h-6 rounded-full bg-green-100 flex items-center justify-center flex-shrink-0">
              <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />
            </div>
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
          {/* 质检状态 */}
          {resource.qualityStatus && resource.qualityStatus !== 'passed' && (
            <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${
              resource.qualityStatus === 'fallback_passed'
                ? 'bg-amber-50 text-amber-600 border-amber-200'
                : 'bg-red-50 text-red-600 border-red-200'
            }`}>
              {resource.qualityStatus === 'fallback_passed' ? '兜底' : '需复核'}
            </span>
          )}
          {resource.tags.slice(0, 2).map((tag) => (
            <span key={tag} className="px-2 py-0.5 rounded-md text-[10px] text-gray-400 bg-gray-50">{tag}</span>
          ))}
        </div>

        {/* 所属阶段 + 章节 */}
        {(resource.relatedStageId || resource.relatedChapter) && (
          <div className="flex flex-wrap items-center gap-2 mb-2 text-[10px] text-gray-400">
            {resource.relatedChapter && (
              <span className="inline-flex items-center gap-1">
                📖 {resource.relatedChapter}
              </span>
            )}
            {resource.relatedStageId && (
              <span className="inline-flex items-center gap-1">
                📍 阶段 {resource.relatedStageId.replace(/[^0-9]/g, '')}
              </span>
            )}
          </div>
        )}

        {/* 底部信息 */}
        <div className="flex items-center justify-between text-[10px] text-gray-400 pt-1">
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatDuration(resource.estimatedMinutes)}
          </span>
          <div className="flex items-center gap-2">
            {resource.bookmarked && (
              <span className="flex items-center gap-0.5 text-brand-500">
                <BookmarkCheck className="w-3 h-3" />
              </span>
            )}
            <SourceBadge source={resource.source || 'system_inferred'} size="xs" />
            <span className="flex items-center gap-0.5 text-brand-500 opacity-0 group-hover:opacity-100 transition-opacity">
              查看详情 <ChevronRight className="w-3 h-3" />
            </span>
          </div>
        </div>
      </div>
    </button>
  );
}

/* ===================================================================
 * 筛选栏
 * =================================================================== */
function FilterBar({
  active, onFilter, onSelectDifficulty, activeDifficulty, dataSource, onSelectSource,
}: {
  active: ResourceType | undefined;
  onFilter: (type: ResourceType | undefined) => void;
  onSelectDifficulty: (level: string | undefined) => void;
  activeDifficulty: string | undefined;
  dataSource?: DataSource | undefined;
  onSelectSource: (s: DataSource | undefined) => void;
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

      {/* 难度 + 数据来源 */}
      <div className="flex items-center gap-4 flex-wrap">
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
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-gray-400 flex-shrink-0">来源：</span>
          {([undefined, 'agent_generated', 'system_inferred', 'fallback', 'user_input'] as (DataSource | undefined)[]).map((s) => (
            <button
              key={s || 'all-src'}
              onClick={() => onSelectSource(s)}
              className={`px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all ${
                dataSource === s
                  ? 'bg-gray-800 text-white'
                  : 'bg-gray-50 text-gray-500 hover:bg-gray-100'
              }`}
            >
              {s ? (s === 'agent_generated' ? '智能体生成' : s === 'system_inferred' ? '系统推断' : s === 'fallback' ? '兜底' : '用户输入') : '不限'}
            </button>
          ))}
        </div>
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
      // 同时上报学习事件，使学习分析页能看到反馈行为
      await logStudyEvent({
        event: 'feedback',
        resourceId,
        sessionId: useChatStore.getState().currentSessionId,
        metadata: { rating, difficultyMatch, hasComment: !!comment },
      });
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
 * 做题交互组件
 * =================================================================== */
function QuizAnswerer({ questions, resourceId }: {
  questions: NonNullable<Resource['questions']>;
  resourceId: string;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const [score, setScore] = useState<{ correct: number; total: number } | null>(null);

  const handleChoose = (questionId: string, choice: string) => {
    if (submitted) return;
    setAnswers((prev) => ({ ...prev, [questionId]: choice }));
  };

  const handleSubmit = async () => {
    const correct = questions.filter((q) => answers[q.id] === q.answer).length;
    const wrong = questions.length - correct;
    setScore({ correct, total: questions.length });
    setSubmitted(true);
    // 上报做题事件（quiz_result 使学习分析页能计算正确率和薄弱知识点）
    await logStudyEvent({
      event: 'quiz_result',
      resourceId,
      sessionId: useChatStore.getState().currentSessionId,
      metadata: {
        correct,
        wrong,
        total: questions.length,
        accuracy: Math.round((correct / questions.length) * 100),
        topic: questions[0]?.knowledgePoint || '通用',
        knowledgePoint: questions[0]?.knowledgePoint || '通用',
      },
    });
  };

  const handleReset = () => {
    setAnswers({});
    setSubmitted(false);
    setScore(null);
  };

  if (questions.length === 0) return null;

  return (
    <div className="p-4 bg-amber-50/40 border border-amber-100 rounded-xl space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <HelpCircle className="w-4 h-4 text-amber-500" />
          随堂练习 ({questions.length} 题)
        </h4>
        {submitted && score && (
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
            score.correct === score.total ? 'bg-green-100 text-green-600' : 'bg-amber-100 text-amber-600'
          }`}>
            {score.correct}/{score.total} 正确
          </span>
        )}
      </div>

      {questions.map((q, qi) => {
        const chosen = answers[q.id];
        const isCorrect = submitted && chosen === q.answer;
        const isWrong = submitted && chosen && chosen !== q.answer;

        return (
          <div key={q.id} className={`p-3 rounded-xl border transition-all ${
            isCorrect ? 'bg-green-50 border-green-200' : isWrong ? 'bg-red-50 border-red-200' : 'bg-white border-gray-100'
          }`}>
            <p className="text-xs font-medium text-gray-800 mb-2">{qi + 1}. {q.stem}</p>
            {q.type === 'choice' && q.options ? (
              <div className="space-y-1">
                {q.options.map((opt, oi) => {
                  const letter = String.fromCharCode(65 + oi);
                  const selected = chosen === letter;
                  return (
                    <button
                      key={oi}
                      onClick={() => handleChoose(q.id, letter)}
                      disabled={submitted}
                      className={`w-full text-left px-3 py-1.5 rounded-lg text-xs transition-all ${
                        submitted && letter === q.answer
                          ? 'bg-green-100 text-green-700 font-medium'
                          : submitted && selected && letter !== q.answer
                            ? 'bg-red-100 text-red-600'
                            : selected
                              ? 'bg-brand-50 text-brand-600 ring-1 ring-brand-200'
                              : 'bg-gray-50 text-gray-600 hover:bg-gray-100'
                      }`}
                    >
                      <span className="font-semibold mr-1.5">{letter}.</span>
                      {opt}
                      {submitted && letter === q.answer && <Check className="w-3 h-3 inline ml-1.5 text-green-500" />}
                      {isWrong && selected && <XCircle className="w-3 h-3 inline ml-1.5 text-red-400" />}
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="space-y-1">
                <input
                  type="text"
                  value={chosen || ''}
                  onChange={(e) => handleChoose(q.id, e.target.value)}
                  disabled={submitted}
                  placeholder="输入你的答案…"
                  className="w-full px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-xs outline-none focus:ring-2 focus:ring-brand-500 disabled:bg-gray-50"
                />
                {submitted && (
                  <p className="text-[10px] text-gray-500">
                    正确答案：{q.answer}
                    {q.explanation && ` · ${q.explanation}`}
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}

      <div className="flex items-center gap-2 pt-1">
        {!submitted ? (
          <button
            onClick={handleSubmit}
            disabled={Object.keys(answers).length < questions.length}
            className="px-4 py-2 bg-amber-500 text-white rounded-xl text-xs font-semibold hover:bg-amber-600 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          >
            提交答案
          </button>
        ) : (
          <button
            onClick={handleReset}
            className="px-4 py-2 bg-gray-100 text-gray-600 rounded-xl text-xs font-semibold hover:bg-gray-200 transition-all"
          >
            重新作答
          </button>
        )}
        <span className="text-[10px] text-gray-400">
          已答 {Object.keys(answers).length}/{questions.length}
        </span>
      </div>
    </div>
  );
}

/* ===================================================================
 * 主页面
 * =================================================================== */
export default function ResourceLibrary() {
  const navigate = useNavigate();
  const params = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const { resources, total, loading, error, applyFilter, toggleBookmark, updateResource, refetch } = useResources();
  const dataVersion = useChatStore((state) => state.dataVersion);
  const subjectId = useSubjectStore((s) => s.activeSubject?.id);
  const profile = useProfileStore((s) => subjectId ? s.profiles[subjectId] ?? null : null);
  const hasCourse = profile?.dimensions?.some(d => d.key === 'knowledge_base');
  const [selected, setSelected] = useState<Resource | null>(null);
  const [search, setSearch] = useState('');
  const [activeType, setActiveType] = useState<ResourceType | undefined>();
  const [activeDifficulty, setActiveDifficulty] = useState<string | undefined>();
  const [activeSource, setActiveSource] = useState<DataSource | undefined>();
  const [activeStageId, setActiveStageId] = useState<string | undefined>();
  const [showFeedback, setShowFeedback] = useState(false);
  const [showThanks, setShowThanks] = useState(false);
  const [prevResourceIds, setPrevResourceIds] = useState<string>('');
  const stageFilterApplied = useRef(false);

  // 从 URL query ?stage=xxx 读取阶段筛选
  useEffect(() => {
    const stageFromUrl = searchParams.get('stage');
    const stageFromStorage = sessionStorage.getItem('eduagent_filter_stage');
    const stageId = stageFromUrl || stageFromStorage;
    if (stageId && !stageFilterApplied.current) {
      stageFilterApplied.current = true;
      setActiveStageId(stageId);
      applyFilter({ search: stageId }); // 用 stageId 作为搜索词传递给后端
      sessionStorage.removeItem('eduagent_filter_stage');
    }
  }, [searchParams, applyFilter]);

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
      sessionId: useChatStore.getState().currentSessionId,
      metadata: { type: resource.type, subjectId, title: resource.title },
    });
    // 持久化到后端
    try {
      await client.patch(`/resources/${resource.id}/study-status`, { studyStatus: 'completed' });
    } catch { /* 静默失败，本地状态优先 */ }
    // 同步更新前端列表
    updateResource(resource.id, { studyStatus: 'completed' });
    setSelected((prev) => prev ? { ...prev, studyStatus: 'completed' } : null);
  }, [subjectId]);

  // 打开资源详情
  const openDetail = useCallback(async (resource: Resource) => {
    setSelected(resource);
    setShowFeedback(false);
    setShowThanks(false);
    // 上报查看事件
    await logStudyEvent({
      event: 'resource_view',
      resourceId: resource.id,
      sessionId: useChatStore.getState().currentSessionId,
      metadata: { type: resource.type, subjectId, title: resource.title },
    });
  }, [subjectId]);

  // 当资源列表加载完成且 URL 有 :id 参数时自动打开详情
  useEffect(() => {
    if (!params.id || loading || resources.length === 0) return;
    const ids = resources.map(r => r.id).join(',');
    if (ids === prevResourceIds) return;
    setPrevResourceIds(ids);
    const found = resources.find(r => r.id === params.id);
    if (found) openDetail(found);
  }, [params.id, resources, loading, openDetail, prevResourceIds]);


  return (
    <div className="max-w-7xl mx-auto px-4 py-6 md:py-8">
      {/* ========== 头部 ========== */}
      <div className="mb-6">
        <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-1">资源库</h1>
        <p className="text-sm text-gray-500">
          共 <span className="font-semibold text-gray-700">{total}</span> 个学习资源，由当前工作流按课程上下文整理
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
          dataSource={activeSource}
          onSelectSource={(s) => { setActiveSource(s); applyFilter({ source: s }); }}
        />
      </div>

      {/* ========== 列表 ========== */}
      {loading && resources.length === 0 ? (
        <Loading text="加载资源中…" />
      ) : error && resources.length === 0 ? (
        <PageError
          title="资源加载失败"
          description={error}
          onRetry={refetch}
          onGoChat={() => navigate('/chat')}
        />
      ) : !resources || resources.length === 0 ? (
        <div className="relative">
          {loading && <RefreshOverlay />}
          <EmptyState
            icon={<BookOpen className="w-8 h-8" />}
            title={search || activeType || activeDifficulty ? '没有匹配的资源' : '暂无资源'}
            description={
              search || activeType || activeDifficulty
                ? '尝试调整筛选条件或搜索关键词'
                : hasCourse
                  ? '当前课程暂无资源，在对话中说"生成学习资源"来获得课程材料'
                  : '在对话中描述你的学习需求，系统会为你整理课程资源'
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
        </div>
      ) : (
        <div className="relative">
          {loading && <RefreshOverlay />}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {resources.map((r) => (
              <ResourceCard key={r.id} resource={r} onClick={() => openDetail(r)} />
            ))}
          </div>
        </div>
      )}

      {/* ========== 资源详情弹窗 ========== */}
      <Modal open={!!selected} onClose={() => setSelected(null)} title={selected?.title} wide>
        {selected && (
          <div className="space-y-4">
            {/* 元信息 — 类型 / 难度 / 来源 / 质检 / 时长 */}
            <div className="flex flex-wrap items-center gap-2">
              <span className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${difficultyBadge[selected.difficulty]}`}>
                {difficultyLabel[selected.difficulty]}
              </span>
              <span className="px-2.5 py-1 rounded-lg text-xs text-gray-500 bg-gray-50 border border-gray-100">
                {RESOURCE_TYPE_LABELS[selected.type]}
              </span>
              <span className="text-xs text-gray-400">· {formatDuration(selected.estimatedMinutes)}</span>
              <span className="text-xs text-gray-400">· {timeAgo(selected.createdAt)}</span>
              <SourceBadge source={selected.source || 'system_inferred'} size="sm" />
              {selected.qualityStatus && selected.qualityStatus !== 'passed' && (
                <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${
                  selected.qualityStatus === 'fallback_passed'
                    ? 'bg-amber-50 text-amber-600 border-amber-200'
                    : 'bg-red-50 text-red-600 border-red-200'
                }`}>
                  {selected.qualityStatus === 'fallback_passed' ? '🛡️ 兜底内容' : '⚠️ 需复核'}
                </span>
              )}
              {selected.studyStatus === 'completed' && (
                <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-green-50 text-green-600 border border-green-200">
                  ✅ 已完成
                </span>
              )}
            </div>

            {/* 描述 */}
            <p className="text-sm text-gray-500">{selected.description}</p>

            {/* 关联信息卡片 — 阶段 / 章节 / 知识点 / 来源 */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-4 bg-gray-50/80 border border-gray-100 rounded-xl">
              {/* 所属阶段 */}
              {selected.relatedStageId && (
                <div className="flex items-start gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-brand-100 flex items-center justify-center flex-shrink-0">
                    <span className="text-xs font-bold text-brand-600">
                      {selected.relatedStageId.replace(/[^0-9]/g, '') || '?'}
                    </span>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-400 font-medium">所属学习阶段</p>
                    <p className="text-xs font-semibold text-gray-700">
                      {selected.relatedChapter ? `第${selected.relatedStageId.replace(/[^0-9]/g, '') || ''}阶段` : selected.relatedStageId}
                    </p>
                  </div>
                </div>
              )}
              {/* 关联章节 */}
              {selected.relatedChapter && (
                <div className="flex items-start gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center flex-shrink-0">
                    <span className="text-xs font-bold text-emerald-600">章</span>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-400 font-medium">关联章节</p>
                    <p className="text-xs font-semibold text-gray-700">{selected.relatedChapter}</p>
                  </div>
                </div>
              )}
              {/* 知识点 */}
              {(selected.relatedKnowledgePoints?.length ?? 0) > 0 && (
                <div className="flex items-start gap-2.5 sm:col-span-2">
                  <div className="w-7 h-7 rounded-lg bg-purple-100 flex items-center justify-center flex-shrink-0">
                    <span className="text-xs font-bold text-purple-600">知</span>
                  </div>
                  <div className="flex-1">
                    <p className="text-[10px] text-gray-400 font-medium">关联知识点</p>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {selected.relatedKnowledgePoints?.map((kp) => (
                        <span key={kp} className="px-2 py-0.5 bg-purple-50 text-purple-600 rounded-md text-[10px] font-medium border border-purple-100">
                          {kp}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              )}
              {/* 质检状态 */}
              {selected.qualityStatus && (
                <div className="flex items-start gap-2.5">
                  <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${
                    selected.qualityStatus === 'passed' ? 'bg-green-100' :
                    selected.qualityStatus === 'fallback_passed' ? 'bg-amber-100' : 'bg-red-100'
                  }`}>
                    <span className={`text-xs font-bold ${
                      selected.qualityStatus === 'passed' ? 'text-green-600' :
                      selected.qualityStatus === 'fallback_passed' ? 'text-amber-600' : 'text-red-600'
                    }`}>
                      {selected.qualityStatus === 'passed' ? '✓' :
                       selected.qualityStatus === 'fallback_passed' ? '🛡' : '⚠'}
                    </span>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-400 font-medium">质检状态</p>
                    <p className={`text-xs font-semibold ${
                      selected.qualityStatus === 'passed' ? 'text-green-600' :
                      selected.qualityStatus === 'fallback_passed' ? 'text-amber-600' : 'text-red-600'
                    }`}>
                      {selected.qualityStatus === 'passed' ? '已通过' :
                       selected.qualityStatus === 'fallback_passed' ? '兜底通过' : '需人工复核'}
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* 来源说明 / fallback 标签 */}
            {selected.source === 'system_inferred' && (
              <div className="p-3 bg-amber-50/80 border border-amber-200 rounded-xl">
                <p className="text-xs text-amber-700 font-medium mb-0.5">🛡️ 兜底资源</p>
                <p className="text-[10px] text-amber-500">
                  此资源由系统规则生成，内容与当前课程信息的匹配度可能有限。
                  建议在对话中补充详细信息以获取更准确的课程资源。
                </p>
              </div>
            )}
            {selected.source === 'agent_generated' && (
              <div className="p-3 bg-green-50/70 border border-green-100 rounded-xl">
                <p className="text-xs text-green-600 font-medium mb-0.5">💡 推荐理由</p>
                <p className="text-[10px] text-green-500">
                  此资源基于当前课程阶段「{selected.relatedChapter || selected.relatedStageId || '当前课程'}」
                  和知识短板整理，与学习路径直接关联。
                </p>
              </div>
            )}

            {/* 知识点标签 */}
            <div className="flex flex-wrap gap-1.5">
              {selected.knowledgePoints.map((kp) => (
                <span key={kp} className="px-2 py-0.5 bg-brand-50 text-brand-600 rounded-md text-[10px] font-medium">
                  {kp}
                </span>
              ))}</div>

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

            {/* 资源内容 — 按类型差异化展示 */}
            <div className="prose-custom text-sm text-gray-800 leading-relaxed p-5 bg-gray-50/80 rounded-xl border border-gray-100">
              {/* ===== 课程讲义 / 拓展阅读 : Markdown 正文 ===== */}
              {(selected.type === 'lecture' || selected.type === 'reading') && (
                <div>
                  {selected.type === 'reading' && (
                    <div className="mb-4 p-3 bg-emerald-50/70 border border-emerald-100 rounded-xl">
                      <p className="text-xs text-emerald-700 font-medium mb-0.5">📖 拓展阅读</p>
                      <p className="text-[10px] text-emerald-500">以下为与本课程相关的拓展阅读材料，帮助你加深理解</p>
                    </div>
                  )}
                  {selected.type === 'lecture' && (
                    <div className="mb-4 p-3 bg-blue-50/70 border border-blue-100 rounded-xl">
                      <p className="text-xs text-blue-700 font-medium mb-0.5">📚 课程讲义</p>
                      <p className="text-[10px] text-blue-500">以下为针对当前阶段定制的课程讲义内容</p>
                    </div>
                  )}
                  <Markdown content={selected.content} />
                </div>
              )}

              {/* ===== 思维导图 : Mermaid 或结构化层级 ===== */}
              {selected.type === 'mindmap' && (
                <div>
                  <div className="mb-4 p-3 bg-purple-50/70 border border-purple-100 rounded-xl">
                    <p className="text-xs text-purple-700 font-medium mb-0.5">🧠 知识图谱 / 思维导图</p>
                    <p className="text-[10px] text-purple-500">可视化呈现本阶段知识结构和知识点之间的关系</p>
                  </div>
                  {selected.mermaidDef ? (
                    <div className="p-4 bg-white rounded-xl border border-gray-100">
                      <MermaidDiagram definition={selected.mermaidDef} />
                    </div>
                  ) : (
                    <Markdown content={selected.content} />
                  )}
                </div>
              )}

              {/* ===== 练习题 : 交互式做题 ===== */}
              {selected.type === 'quiz' && (
                <div>
                  <div className="mb-4 p-3 bg-amber-50/70 border border-amber-100 rounded-xl">
                    <p className="text-xs text-amber-700 font-medium mb-0.5">📝 随堂练习</p>
                    <p className="text-[10px] text-amber-500">完成以下题目检验学习效果，系统将记录正确率</p>
                  </div>
                  {selected.questions && selected.questions.length > 0 ? (
                    <QuizAnswerer questions={selected.questions} resourceId={selected.id} />
                  ) : (
                    <Markdown content={selected.content} />
                  )}
                </div>
              )}

              {/* ===== 实操案例 : 代码块 + 步骤说明 ===== */}
              {selected.type === 'case_study' && (
                <div>
                  <div className="mb-4 p-3 bg-cyan-50/70 border border-cyan-100 rounded-xl">
                    <p className="text-xs text-cyan-700 font-medium mb-0.5">💻 实操案例</p>
                    <p className="text-[10px] text-cyan-500">动手实践加深理解，包含代码示例和操作步骤</p>
                  </div>
                  {/* Markdown 正文（含步骤说明） */}
                  <Markdown content={selected.content} />
                  {/* 代码块 */}
                  {selected.codeBlocks && selected.codeBlocks.length > 0 && (
                    <div className="mt-4 space-y-4">
                      <p className="text-xs font-semibold text-gray-600">🔧 代码示例</p>
                      {selected.codeBlocks.map((block, i) => (
                        <div key={i} className="bg-gray-900 text-gray-100 rounded-xl overflow-hidden border border-gray-800">
                          {block.language && (
                            <div className="px-4 py-1.5 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
                              <span className="text-[10px] text-gray-400 font-mono">{block.language}</span>
                            </div>
                          )}
                          <pre className="text-xs font-mono p-4 overflow-x-auto"><code>{block.code}</code></pre>
                          {block.explanation && (
                            <div className="px-4 py-2 bg-gray-800/50 border-t border-gray-700">
                              <p className="text-[10px] text-gray-400">{block.explanation}</p>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* ===== 视频脚本 : 分镜/讲稿结构 ===== */}
              {selected.type === 'video' && (
                <div>
                  <div className="mb-4 p-3 bg-red-50/70 border border-red-100 rounded-xl">
                    <p className="text-xs text-red-700 font-medium mb-0.5">🎬 教学视频</p>
                    <p className="text-[10px] text-red-500">以下为本阶段配套教学视频的讲稿/分镜脚本</p>
                  </div>
                  {/* 优先展示 pptOutline 作为分镜结构 */}
                  {selected.pptOutline && selected.pptOutline.length > 0 ? (
                    <div className="space-y-3">
                      {selected.pptOutline.map((slide, i) => (
                        <div key={i} className="p-4 bg-white border border-gray-100 rounded-xl shadow-sm">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="w-5 h-5 rounded-full bg-red-100 text-red-600 text-[10px] font-bold flex items-center justify-center flex-shrink-0">
                              {i + 1}
                            </span>
                            <h4 className="text-sm font-semibold text-gray-800">{slide.title}</h4>
                          </div>
                          {slide.bullets.length > 0 && (
                            <ul className="space-y-1 ml-7">
                              {slide.bullets.map((b, bi) => (
                                <li key={bi} className="text-xs text-gray-600 list-disc">{b}</li>
                              ))}
                            </ul>
                          )}
                          {slide.notes && (
                            <p className="text-[10px] text-gray-400 mt-2 ml-7 italic">💡 {slide.notes}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <Markdown content={selected.content} />
                  )}
                </div>
              )}

              {/* ===== PPT 大纲 ===== */}
              {selected.type === 'ppt' && (
                <div>
                  <div className="mb-4 p-3 bg-orange-50/70 border border-orange-100 rounded-xl">
                    <p className="text-xs text-orange-700 font-medium mb-0.5">📊 PPT 大纲</p>
                    <p className="text-[10px] text-orange-500">本阶段课程配套演示文稿大纲</p>
                  </div>
                  {selected.pptOutline && selected.pptOutline.length > 0 ? (
                    <div className="space-y-3">
                      {selected.pptOutline.map((slide, i) => (
                        <div key={i} className="p-4 bg-white border border-gray-100 rounded-xl shadow-sm">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="w-5 h-5 rounded-full bg-orange-100 text-orange-600 text-[10px] font-bold flex items-center justify-center flex-shrink-0">
                              {i + 1}
                            </span>
                            <h4 className="text-sm font-semibold text-gray-800">{slide.title}</h4>
                          </div>
                          {slide.bullets.length > 0 && (
                            <ul className="space-y-1 ml-7">
                              {slide.bullets.map((b, bi) => (
                                <li key={bi} className="text-xs text-gray-600 list-disc">{b}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <Markdown content={selected.content} />
                  )}
                </div>
              )}

              {/* ===== 兜底 : 通用 Markdown ===== */}
              {!['lecture', 'mindmap', 'quiz', 'case_study', 'reading', 'video', 'ppt'].includes(selected.type) && (
                <Markdown content={selected.content} />
              )}
            </div>

            {/* 可折叠的题目展示（非 quiz 类型但带题目） */}
            {selected.type !== 'quiz' && selected.questions && selected.questions.length > 0 && (
              <details className="group">
                <summary className="text-xs font-semibold text-brand-500 cursor-pointer hover:text-brand-600 transition-colors p-2">
                  查看随堂练习 ({selected.questions.length} 题)
                </summary>
                <div className="mt-2">
                  <QuizAnswerer questions={selected.questions} resourceId={selected.id} />
                </div>
              </details>
            )}

            {/* 底部提示 */}
            <p className="text-[10px] text-gray-400 text-center pt-2">
              AI 生成内容仅供参考 · 如需深入学习请查阅课程教材
            </p>
          </div>
        )}
      </Modal>

      {/* ========== 底部说明 ========== */}
      <div className="text-center py-6 mt-6 border-t border-gray-50">
        <div className="flex items-center justify-center gap-3 mb-2">
          <SourceBadge source="agent_generated" size="xs" />
          <SourceBadge source="system_inferred" size="xs" />
        </div>
        <p className="text-xs text-gray-400">
          {dataVersion > 0 ? '已同步最新对话数据' : '等待新对话生成资源'} · 支持按来源筛选真实数据
        </p>
      </div>
    </div>
  );
}
