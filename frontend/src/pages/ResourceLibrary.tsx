import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Search, Filter, BookOpen, Brain, Code, FileText, Lightbulb,
  Play, Presentation, Clock, Star, ChevronRight, BookmarkPlus,
  BookmarkCheck, CheckCircle2, MessageSquare, X, Send, Sparkles,
  HelpCircle, Check, XCircle, RefreshCw, AlertCircle, AlertTriangle, RotateCcw,
  SlidersHorizontal, BookmarkX, Layers, TrendingUp,
  Download, ListChecks, Square, CheckSquare, ChevronUp, ChevronDown,
  Shield,
} from 'lucide-react';
import { useResources } from '../hooks/useResources';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import { useChatPanel } from '../components/layout/AppLayout';
import type { Resource, ResourceFilter, SortBy } from '../types/resource';
import type { ResourceType, DataSource } from '../types/resource';
import { RESOURCE_TYPE_LABELS } from '../utils/constants';
import { timeAgo, formatDuration } from '../utils/format';
import { HighlightText, matchesQuery } from '../utils/highlight';
import { PageLoading, PageEmpty, RefreshOverlay, PageError, SourceTag } from '../components/common/PageState';
import Modal from '../components/common/Modal';
import Markdown from '../utils/markdown';
import MermaidDiagram from '../utils/mermaid';
import { submitFeedback, logStudyEvent } from '../api/feedback';
import * as resourcesApi from '../api/resources';
import { updateStudyStatus, autoAdvanceNode } from '../api/resources';
import SourceBadge from '../components/common/SourceBadge';

import ExpandableText from '../components/common/ExpandableText';
import QualityStatusPopover, {
  ReviewStatusBadge,
} from '../components/common/QualityStatusPopover';

/* ===================================================================
 * 长内容折叠组件
 * =================================================================== */
function LongContent({ content, children }: { content: string; children: React.ReactNode }) {
  const [expanded, setExpanded] = useState(content.length <= 1500);
  const isLong = content.length > 1500;

  if (!isLong) return <div className="p-5 bg-gray-50/80 rounded-xl border border-gray-100 prose-custom">{children}</div>;

  return (
    <div>
      <div className={`relative ${expanded ? '' : 'max-h-[500px] overflow-hidden'}`}>
        <div className={`p-5 bg-gray-50/80 rounded-xl border border-gray-100 prose-custom transition-opacity ${expanded ? '' : 'opacity-40 pointer-events-none'}`}>
          {children}
        </div>
        {!expanded && (
          <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-b from-transparent to-gray-50 rounded-b-xl" />
        )}
      </div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-2 w-full flex items-center justify-center gap-1.5 px-4 py-2 bg-gray-50 border border-gray-200 rounded-xl text-xs text-gray-500 hover:text-brand-600 hover:border-brand-200 transition-all"
      >
        {expanded ? (
          <><ChevronUp className="w-3.5 h-3.5" /> 收起内容</>
        ) : (
          <><ChevronDown className="w-3.5 h-3.5" /> 展开全文（共约 {Math.ceil(content.length / 100) * 100} 字）</>
        )}
      </button>
    </div>
  );
}

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
  undefined, 'lecture', 'mindmap', 'quiz', 'reading', 'case_study', 'video', 'ppt',
];

const QUALITY_STATUS_OPTIONS = [
  { value: undefined, label: '不限' },
  { value: 'passed', label: '已通过' },
  { value: 'needs_review', label: '需复核' },
  { value: 'fallback_passed', label: '兜底通过' },
] as const;

const STUDY_STATUS_OPTIONS = [
  { value: undefined, label: '不限' },
  { value: 'new', label: '未开始' },
  { value: 'in_progress', label: '学习中' },
  { value: 'completed', label: '已完成' },
] as const;

const BOOKMARKED_OPTIONS = [
  { value: undefined, label: '不限' },
  { value: 'true', label: '已收藏' },
  { value: 'false', label: '未收藏' },
] as const;

const SORT_OPTIONS: { value: SortBy; label: string; icon: string }[] = [
  { value: 'default',  label: '推荐排序',   icon: '⭐' },
  { value: 'newest',   label: '最新生成',   icon: '🕐' },
  { value: 'shortest', label: '时间短优先', icon: '⏱' },
  { value: 'easiest',  label: '难度低→高', icon: '📗' },
  { value: 'hardest',  label: '难度高→低', icon: '📕' },
  { value: 'status',   label: '未完成优先', icon: '📌' },
  { value: 'stage',    label: '阶段优先',   icon: '📍' },
];

import ResourceCard from '../components/resources/ResourceCard';

import ResourceFilters from '../components/resources/ResourceFilters';

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
  const [feedbackCategory, setFeedbackCategory] = useState<string>('');
  const [difficultyMatch, setDifficultyMatch] = useState<string>('');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const FEEDBACK_CATEGORIES = [
    { value: 'helpful',    label: '有帮助', emoji: '👍' },
    { value: 'too_hard',   label: '太难',   emoji: '😓' },
    { value: 'too_easy',   label: '太简单',  emoji: '😅' },
    { value: 'unclear',    label: '内容不清楚', emoji: '🤔' },
    { value: 'irrelevant', label: '不相关',  emoji: '👎' },
    { value: 'other',      label: '其他',   emoji: '💬' },
  ];

  const handleSubmit = async () => {
    if (rating === 0 && !feedbackCategory) return;
    setSubmitting(true);
    try {
      await submitFeedback({ sessionId: useChatStore.getState().currentSessionId, resourceId, rating, difficultyMatch: difficultyMatch as any, category: feedbackCategory, comment: comment || undefined });
      await logStudyEvent({
        event: 'feedback',
        resourceId,
        sessionId: useChatStore.getState().currentSessionId,
        metadata: { rating, difficultyMatch, feedbackType: feedbackCategory, hasComment: !!comment, content: comment || '' },
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

      {/* 反馈分类 */}
      <div>
        <p className="text-xs text-gray-500 mb-1.5">你觉得这份资源怎么样？</p>
        <div className="flex flex-wrap gap-1.5">
          {FEEDBACK_CATEGORIES.map((cat) => (
            <button
              key={cat.value}
              onClick={() => setFeedbackCategory(feedbackCategory === cat.value ? '' : cat.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all inline-flex items-center gap-1 ${
                feedbackCategory === cat.value
                  ? 'bg-brand-500 text-white shadow-sm'
                  : 'bg-white border border-gray-200 text-gray-500 hover:border-brand-300'
              }`}
            >
              {cat.emoji} {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* 星级评分 */}
      <div>
        <p className="text-xs text-gray-500 mb-1.5">综合评分（选填）</p>
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
        <p className="text-xs text-gray-500 mb-1.5">难度匹配（选填）</p>
        <div className="flex gap-1.5">
          {[
            { value: 'too_easy', label: '太简单' },
            { value: 'just_right', label: '刚刚好' },
            { value: 'too_hard', label: '太难了' },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => setDifficultyMatch(difficultyMatch === opt.value ? '' : opt.value)}
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
          disabled={(!rating && !feedbackCategory) || submitting}
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
    // 上报做题事件
    await logStudyEvent({
      event: 'quiz_result',
      resourceId,
      sessionId: useChatStore.getState().currentSessionId,
      metadata: {
        correct, wrong, total: questions.length,
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

  // 计算每题解析
  const questionResults = questions.map((q) => {
    const chosen = answers[q.id];
    const isCorrect = chosen === q.answer;
    const isWrong = chosen && chosen !== q.answer;
    return { q, chosen, isCorrect, isWrong };
  });

  return (
    <div className="p-4 bg-amber-50/40 border border-amber-100 rounded-xl space-y-3">
      {/* 标题 + 得分 */}
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

      {/* 题目列表 */}
      {questionResults.map(({ q, chosen, isCorrect, isWrong }, qi) => (
        <div key={q.id} className={`p-3 rounded-xl border transition-all ${
          isCorrect ? 'bg-green-50 border-green-200' : isWrong ? 'bg-red-50 border-red-200' : 'bg-white border-gray-100'
        }`}>
          <p className="text-xs font-medium text-gray-800 mb-2">{qi + 1}. {q.stem}</p>

          {/* 选择题选项 */}
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
              {/* 选择题的答案解析（提交后展示） */}
              {submitted && q.explanation && (
                <div className="mt-2 px-3 py-2 bg-blue-50/60 border border-blue-100 rounded-lg">
                  <p className="text-[10px] font-semibold text-blue-600 mb-0.5">📖 解析</p>
                  <ExpandableText text={q.explanation} maxLines={3} className="text-[10px] text-gray-600 leading-relaxed" />
                </div>
              )}
            </div>
          ) : (
            /* 填空题 */
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
                <div className="space-y-1">
                  <p className="text-[10px] text-gray-500">
                    正确答案：<span className="font-semibold text-green-600">{q.answer}</span>
                  </p>
                  {q.explanation && (
                    <ExpandableText text={q.explanation} maxLines={3} className="text-[10px] text-gray-500 leading-relaxed" />
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      ))}

      {/* 提交后的整体解析 */}
      {submitted && (
        <div className="p-3 bg-white border border-gray-200 rounded-xl space-y-2">
          <p className="text-[10px] font-semibold text-gray-600 flex items-center gap-1">
            <HelpCircle className="w-3 h-3 text-brand-500" />
            答题总结
          </p>
          <p className="text-[10px] text-gray-500">
            共 {questions.length} 题，正确 {score?.correct || 0} 题，正确率 {score ? Math.round((score.correct / score.total) * 100) : 0}%
          </p>
          {questions[0]?.knowledgePoint && (
            <p className="text-[10px] text-gray-400">
              知识点：{questions[0].knowledgePoint}
            </p>
          )}
        </div>
      )}

      {/* 操作按钮 */}
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

/* ── 可信解释字段标签映射 ── */
function sourceTypeLabel(type: string): string {
  const map: Record<string, string> = {
    llm_generated: '大模型生成',
    rule_based: '规则生成',
    knowledge_base: '知识库检索',
    user_input: '用户输入',
  };
  return map[type] || type;
}

function generationModeLabel(mode: string): string {
  const map: Record<string, string> = {
    direct_generation: '直接生成',
    knowledge_retrieval: '知识检索',
    hybrid: '混合生成',
    rule_fallback: '规则兜底',
  };
  return map[mode] || mode;
}

/* ===================================================================
 * 主页面
 * =================================================================== */
export default function ResourceLibrary() {
  const navigate = useNavigate();
  const chatPanel = useChatPanel();
  const params = useParams<{ id: string }>();

  // ── 从 URL 读取所有筛选参数 ──
  const urlParams = new URLSearchParams(window.location.search);
  const stageFilter = urlParams.get('relatedStageId') || '';
  const taskIdFilter = urlParams.get('taskId') || '';
  const searchFilter = urlParams.get('search') || '';
  const resourceIdsFilter = urlParams.get('resourceIds') || '';
  const typeFilter = urlParams.get('type') || '';
  const difficultyFilter = urlParams.get('difficulty') || '';
  const sourceFilter = urlParams.get('source') || '';
  const chapterFilter = urlParams.get('chapter') || '';
  const qualityFilter = urlParams.get('qualityStatus') || '';
  const studyStatusFilter = urlParams.get('studyStatus') || '';
  const bookmarkedFilter = urlParams.get('bookmarked') || '';
  const sortFilter = urlParams.get('sortBy') || '';

  // 构建初始筛选对象
  const initialFilter: ResourceFilter | undefined = (taskIdFilter || stageFilter || searchFilter || resourceIdsFilter
    || typeFilter || difficultyFilter || sourceFilter || chapterFilter || qualityFilter || studyStatusFilter || bookmarkedFilter || sortFilter)
    ? Object.fromEntries(
        Object.entries({
          taskId: taskIdFilter || undefined,
          relatedStageId: stageFilter || undefined,
          search: searchFilter ? decodeURIComponent(searchFilter) : undefined,
          resourceIds: resourceIdsFilter || undefined,
          type: (typeFilter as ResourceType) || undefined,
          difficulty: difficultyFilter || undefined,
          source: sourceFilter || undefined,
          chapter: chapterFilter || undefined,
          qualityStatus: qualityFilter || undefined,
          studyStatus: studyStatusFilter || undefined,
          bookmarked: bookmarkedFilter || undefined,
          sortBy: (sortFilter as SortBy) || undefined,
        }).filter(([_, v]) => v !== undefined)
      ) as ResourceFilter
    : undefined;

  const { resources, total, completedCount, incompleteCount, completionRate, loading, error, applyFilter, toggleBookmark, updateResource, refetch } = useResources(initialFilter);
  const sessionId = useChatStore((state) => state.currentSessionId);
  const dataVersion = useChatStore((state) => state.dataVersion);
  const subjectId = useSubjectStore((s) => s.activeSubject?.id);

  const [selected, setSelected] = useState<Resource | null>(null);
  const [search, setSearch] = useState(searchFilter ? decodeURIComponent(searchFilter) : '');
  const [activeType, setActiveType] = useState<ResourceType | undefined>(typeFilter ? (typeFilter as ResourceType) : undefined);
  const [activeDifficulty, setActiveDifficulty] = useState<string | undefined>(difficultyFilter || undefined);
  const [activeSource, setActiveSource] = useState<DataSource | undefined>(sourceFilter as DataSource | undefined);
  const [activeStageId, setActiveStageId] = useState<string | undefined>(stageFilter || undefined);
  const [activeChapter, setActiveChapter] = useState<string | undefined>(chapterFilter || undefined);
  const [activeQuality, setActiveQuality] = useState<string | undefined>(qualityFilter || undefined);
  const [activeStudyStatus, setActiveStudyStatus] = useState<string | undefined>(studyStatusFilter || undefined);
  const [activeBookmarked, setActiveBookmarked] = useState<string | undefined>(bookmarkedFilter || undefined);
  const [activeSort, setActiveSort] = useState<SortBy>((sortFilter as SortBy) || 'default');
  const [showFilters, setShowFilters] = useState(
    !!(chapterFilter || qualityFilter || studyStatusFilter || bookmarkedFilter)
  );
  const [showFeedback, setShowFeedback] = useState(false);
  const [showThanks, setShowThanks] = useState(false);
  const [practiceNotes, setPracticeNotes] = useState('');
  // ── 批量操作状态 ──
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchConfirm, setBatchConfirm] = useState<{
    action: 'complete' | 'bookmark' | 'unbookmark' | 'export';
    open: boolean;
  }>({ action: 'complete', open: false });
  const [batchExportText, setBatchExportText] = useState<string | null>(null);
  const [batchProcessing, setBatchProcessing] = useState(false);

  const [prevResourceIds, setPrevResourceIds] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // 从 resources 中提取唯一的章节列表
  const availableChapters = React.useMemo(() => {
    const chapters = new Set<string>();
    resources.forEach(r => {
      if (r.relatedChapter) chapters.add(r.relatedChapter);
    });
    return Array.from(chapters).sort();
  }, [resources]);

  // 是否有任何活动筛选（非默认排序不算"筛选"，但仍展示标签）
  const hasActiveFilters = !!(activeType || activeDifficulty || activeSource ||
    activeChapter || activeQuality || activeStudyStatus || activeBookmarked ||
    activeStageId || search);
  const hasActiveSort = activeSort !== 'default';

  // ── URL 参数同步（筛选变化时更新 URL） ──
  const syncUrlParams = useCallback((filters: {
    type?: string; difficulty?: string; source?: string; search?: string;
    chapter?: string; qualityStatus?: string; studyStatus?: string; bookmarked?: string;
    relatedStageId?: string; taskId?: string; resourceIds?: string; sortBy?: string;
  }) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    const searchStr = params.toString();
    const newPath = searchStr ? `/resources?${searchStr}` : '/resources';
    navigate(newPath, { replace: true });
  }, [navigate]);

  // ── 统一筛选：更新所有状态 + 调用 API + 同步 URL ──
  const updateFilters = useCallback((updates: Partial<{
    type: ResourceType | undefined;
    difficulty: string | undefined;
    source: DataSource | undefined;
    search: string;
    chapter: string | undefined;
    qualityStatus: string | undefined;
    studyStatus: string | undefined;
    bookmarked: string | undefined;
    relatedStageId: string | undefined;
    taskId: string | undefined;
    resourceIds: string | undefined;
    sortBy: SortBy | undefined;
  }>) => {
    // 更新本地状态
    if ('type' in updates) setActiveType(updates.type);
    if ('difficulty' in updates) setActiveDifficulty(updates.difficulty);
    if ('source' in updates) setActiveSource(updates.source);
    if ('search' in updates) setSearch(updates.search ?? '');
    if ('chapter' in updates) setActiveChapter(updates.chapter);
    if ('qualityStatus' in updates) setActiveQuality(updates.qualityStatus);
    if ('studyStatus' in updates) setActiveStudyStatus(updates.studyStatus);
    if ('bookmarked' in updates) setActiveBookmarked(updates.bookmarked);
    if ('relatedStageId' in updates) setActiveStageId(updates.relatedStageId);
    if ('sortBy' in updates) setActiveSort(updates.sortBy ?? 'default');

    // 调用 API
    applyFilter(updates as Partial<ResourceFilter>);

    // 同步 URL
    const currentFilters = {
      type: ('type' in updates ? updates.type : activeType) || '',
      difficulty: ('difficulty' in updates ? updates.difficulty : activeDifficulty) || '',
      source: ('source' in updates ? updates.source : activeSource) || '',
      search: ('search' in updates ? (updates.search ?? '') : search) || '',
      chapter: ('chapter' in updates ? updates.chapter : activeChapter) || '',
      qualityStatus: ('qualityStatus' in updates ? updates.qualityStatus : activeQuality) || '',
      studyStatus: ('studyStatus' in updates ? updates.studyStatus : activeStudyStatus) || '',
      bookmarked: ('bookmarked' in updates ? updates.bookmarked : activeBookmarked) || '',
      relatedStageId: ('relatedStageId' in updates ? updates.relatedStageId : activeStageId) || '',
      sortBy: ('sortBy' in updates ? updates.sortBy : activeSort) || '',
      taskId: taskIdFilter || '',
      resourceIds: resourceIdsFilter || '',
    };
    syncUrlParams(currentFilters);
  }, [activeType, activeDifficulty, activeSource, search, activeChapter,
      activeQuality, activeStudyStatus, activeBookmarked, activeStageId, activeSort,
      taskIdFilter, resourceIdsFilter, applyFilter, syncUrlParams]);

  // ── 清空所有筛选 ──
  // ── 选择工具 ──
  const toggleSelect = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelectedIds(new Set(resources.map(r => r.id)));
  }, [resources]);

  const deselectAll = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const allSelected = resources.length > 0 && selectedIds.size === resources.length;

  // ── 批量操作处理 ──
  const executeBatchAction = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    setBatchProcessing(true);
    const sessionId = useChatStore.getState().currentSessionId;
    try {
      const { action } = batchConfirm;
      if (action === 'complete') {
        await resourcesApi.batchUpdateStudyStatus(sessionId, ids, 'completed');
        setSelectedIds(new Set());
        setSelectionMode(false);
      } else if (action === 'bookmark') {
        await resourcesApi.batchSetBookmark(sessionId, ids, true);
        setSelectedIds(new Set());
      } else if (action === 'unbookmark') {
        await resourcesApi.batchSetBookmark(sessionId, ids, false);
        setSelectedIds(new Set());
      } else if (action === 'export') {
        const result = await resourcesApi.batchExportResources(sessionId, ids);
        setBatchExportText(result.export);
      }
      refetch();
    } catch (e) {
      setErrorMsg('批量操作失败：' + (e instanceof Error ? e.message : '请检查后端服务'));
      setTimeout(() => setErrorMsg(null), 5000);
    } finally {
      setBatchProcessing(false);
      setBatchConfirm(prev => ({ ...prev, open: false }));
    }
  }, [selectedIds, batchConfirm, refetch]);

  const clearAllFilters = useCallback(() => {
    setActiveType(undefined);
    setActiveDifficulty(undefined);
    setActiveSource(undefined);
    setActiveChapter(undefined);
    setActiveQuality(undefined);
    setActiveStudyStatus(undefined);
    setActiveBookmarked(undefined);
    setActiveStageId(undefined);
    setActiveSort('default');
    setSearch('');
    setShowFilters(false);
    setSelectionMode(false);
    setSelectedIds(new Set());
    applyFilter({ sortBy: 'default' });
    navigate('/resources', { replace: true });
  }, [applyFilter, navigate]);

  // ── 搜索防抖同步 URL ──
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      syncUrlParams({
        type: activeType || '',
        difficulty: activeDifficulty || '',
        source: activeSource || '',
        search,
        chapter: activeChapter || '',
        qualityStatus: activeQuality || '',
        studyStatus: activeStudyStatus || '',
        bookmarked: activeBookmarked || '',
        relatedStageId: activeStageId || '',
        sortBy: activeSort || '',
        taskId: taskIdFilter || '',
        resourceIds: resourceIdsFilter || '',
      });
    }, 500);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [search, activeType, activeDifficulty, activeSource, activeChapter,
      activeQuality, activeStudyStatus, activeBookmarked, activeStageId, activeSort,
      taskIdFilter, resourceIdsFilter, syncUrlParams]);

  // 阶段筛选在 useResources(initialFilter) 中已处理，这里仅同步 UI 状态
  useEffect(() => {
    if (stageFilter) setActiveStageId(stageFilter);
  }, [stageFilter]);
  // 无阶段筛选时清除 UI 状态
  useEffect(() => {
    if (!stageFilter) setActiveStageId(undefined);
  }, [stageFilter]);

  // 收藏切换
  const handleBookmark = useCallback(async (id: string) => {
    await toggleBookmark(id);
    if (selected?.id === id) {
      setSelected((prev) => prev ? { ...prev, bookmarked: !prev.bookmarked } : null);
    }
  }, [toggleBookmark, selected?.id]);

  // 切换完成/未完成（可撤销）
  const handleComplete = useCallback(async (resource: Resource) => {
    const wasCompleted = resource.studyStatus === 'completed';
    const newStatus = wasCompleted ? 'new' : 'completed';

    // 先持久化 study_status 到后端
    try {
      await updateStudyStatus(resource.id, newStatus, useChatStore.getState().currentSessionId);
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : '状态保存失败');
      setTimeout(() => setErrorMsg(null), 5000);
    }

    if (newStatus === 'completed') {
      await logStudyEvent({
        event: 'resource_complete',
        resourceId: resource.id,
        sessionId: useChatStore.getState().currentSessionId,
        metadata: { type: resource.type, subjectId, title: resource.title, relatedStageId: resource.relatedStageId },
      });
      // 自动推进学习路径节点状态
      if (resource.relatedStageId) {
        try {
          await autoAdvanceNode({
            sessionId: useChatStore.getState().currentSessionId,
            relatedStageId: resource.relatedStageId || '',
            taskId: resource.taskId,
            event: 'resource_complete',
          });
        } catch (e) {
          setErrorMsg('学习路径推进失败：' + (e instanceof Error ? e.message : ''));
          setTimeout(() => setErrorMsg(null), 5000);
        }
      }
      // 实操案例额外上报
      if (resource.type === 'case_study') {
        await logStudyEvent({
          event: 'practice_result',
          resourceId: resource.id,
          sessionId: useChatStore.getState().currentSessionId,
          metadata: { type: resource.type, subjectId, title: resource.title, completionNotes: practiceNotes || '' },
        });
      }
    }
    // 同步更新前端列表
    updateResource(resource.id, { studyStatus: newStatus });
    setSelected((prev) => prev ? { ...prev, studyStatus: newStatus } : null);
  }, [subjectId]);

  // 打开资源详情
  const openDetail = useCallback(async (resource: Resource) => {
    // 保存当前滚动位置
    try { sessionStorage.setItem('resourceListScrollY', String(window.scrollY)); } catch { /* noop */ }
    setSelected(resource);
    setShowFeedback(false);
    setShowThanks(false);
    // 上报查看事件
    await logStudyEvent({
      event: 'resource_view',
      resourceId: resource.id,
      sessionId: useChatStore.getState().currentSessionId,
      metadata: { type: resource.type, subjectId, title: resource.title, relatedStageId: resource.relatedStageId },
    });
    // 自动推进学习路径节点状态
    if (resource.relatedStageId) {
      try {
        await autoAdvanceNode({
          sessionId: useChatStore.getState().currentSessionId,
          relatedStageId: resource.relatedStageId || '',
          taskId: resource.taskId,
          event: 'resource_view',
        });
      } catch (e) {
        setErrorMsg('学习路径推进失败：' + (e instanceof Error ? e.message : ''));
        setTimeout(() => setErrorMsg(null), 5000);
      }
    }
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

  // 从详情返回时恢复滚动位置
  useEffect(() => {
    if (!params.id && !loading) {
      try {
        const saved = sessionStorage.getItem('resourceListScrollY');
        if (saved) {
          const scrollY = parseInt(saved, 10);
          if (!isNaN(scrollY)) {
            requestAnimationFrame(() => window.scrollTo(0, scrollY));
          }
          sessionStorage.removeItem('resourceListScrollY');
        }
      } catch { /* noop */ }
    }
  }, [params.id, loading]);


  return (
    <div className="max-w-7xl mx-auto px-4 py-6 md:py-8">
      {/* ========== 错误提示 ========== */}
      {errorMsg && (
        <div className="fixed top-4 right-4 z-50 px-4 py-2 bg-red-50 border border-red-200 text-red-600 rounded-xl text-xs shadow-lg animate-slide-down">
          {errorMsg}
        </div>
      )}
      {/* ========== 头部 ========== */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-1">资源库</h1>
            <p className="text-sm text-gray-500">
              共 <span className="font-semibold text-gray-700">{total}</span> 个学习资源
              {hasActiveFilters && <span className="text-gray-400">（已筛选）</span>}
            </p>
          </div>
          {hasActiveFilters && (
            <button
              onClick={clearAllFilters}
              className="text-xs text-red-500 hover:text-red-600 flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-50 border border-red-100 hover:bg-red-100 transition-all"
            >
              <RotateCcw className="w-3 h-3" />
              清空筛选
            </button>
          )}
        </div>

        {/* 完成统计条形图 */}
        {total > 0 && (
          <div className="flex items-center gap-4 mt-3 p-3 bg-gray-50/80 border border-gray-100 rounded-xl">
            <div className="flex items-center gap-2 text-xs">
              <CheckCircle2 className="w-4 h-4 text-green-500" />
              <span className="text-green-700 font-semibold">{completedCount}</span>
              <span className="text-gray-400">已完成</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <div className="w-4 h-4 rounded-full border-2 border-gray-300" />
              <span className="text-gray-500 font-semibold">{incompleteCount}</span>
              <span className="text-gray-400">未完成</span>
            </div>
            <div className="flex-1 max-w-xs">
              <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${completionRate}%`,
                    background: completionRate >= 80
                      ? 'linear-gradient(90deg, #22c55e, #16a34a)'
                      : completionRate >= 40
                        ? 'linear-gradient(90deg, #f59e0b, #d97706)'
                        : 'linear-gradient(90deg, #6366f1, #4f46e5)',
                  }}
                />
              </div>
            </div>
            <span className="text-xs font-semibold text-gray-600">{completionRate}%</span>
          </div>
        )}
        {/* 当前活动筛选标签 — 可单独删除 */}
        {hasActiveFilters && (
          <div className="flex flex-wrap items-center gap-1.5 mt-2">
            {activeType && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-blue-50 text-blue-600 border border-blue-100 group">
                {RESOURCE_TYPE_LABELS[activeType]}
                <button onClick={() => updateFilters({ type: undefined })} className="w-3.5 h-3.5 rounded-full hover:bg-blue-200 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity" title="移除类型筛选"><X className="w-2.5 h-2.5" /></button>
              </span>
            )}
            {activeDifficulty && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-amber-50 text-amber-600 border border-amber-100 group">
                {difficultyLabel[activeDifficulty]}
                <button onClick={() => updateFilters({ difficulty: undefined })} className="w-3.5 h-3.5 rounded-full hover:bg-amber-200 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity" title="移除难度筛选"><X className="w-2.5 h-2.5" /></button>
              </span>
            )}
            {activeSource && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-purple-50 text-purple-600 border border-purple-100 group">
                {activeSource === 'agent_generated' ? '智能体生成' : activeSource === 'system_inferred' ? '系统推断' : activeSource === 'fallback' ? '兜底' : activeSource}
                <button onClick={() => updateFilters({ source: undefined })} className="w-3.5 h-3.5 rounded-full hover:bg-purple-200 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity" title="移除来源筛选"><X className="w-2.5 h-2.5" /></button>
              </span>
            )}
            {activeChapter && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-emerald-50 text-emerald-600 border border-emerald-100 group">
                📖 {activeChapter}
                <button onClick={() => updateFilters({ chapter: undefined })} className="w-3.5 h-3.5 rounded-full hover:bg-emerald-200 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity" title="移除章节筛选"><X className="w-2.5 h-2.5" /></button>
              </span>
            )}
            {activeQuality && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-rose-50 text-rose-600 border border-rose-100 group">
                质检：{activeQuality === 'passed' ? '已通过' : activeQuality === 'needs_review' ? '需复核' : '兜底通过'}
                <button onClick={() => updateFilters({ qualityStatus: undefined })} className="w-3.5 h-3.5 rounded-full hover:bg-rose-200 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity" title="移除质检筛选"><X className="w-2.5 h-2.5" /></button>
              </span>
            )}
            {activeStudyStatus && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-cyan-50 text-cyan-600 border border-cyan-100 group">
                {activeStudyStatus === 'new' ? '未开始' : activeStudyStatus === 'in_progress' ? '学习中' : '已完成'}
                <button onClick={() => updateFilters({ studyStatus: undefined })} className="w-3.5 h-3.5 rounded-full hover:bg-cyan-200 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity" title="移除状态筛选"><X className="w-2.5 h-2.5" /></button>
              </span>
            )}
            {activeBookmarked && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-brand-50 text-brand-600 border border-brand-100 group">
                {activeBookmarked === 'true' ? '⭐ 已收藏' : '未收藏'}
                <button onClick={() => updateFilters({ bookmarked: undefined })} className="w-3.5 h-3.5 rounded-full hover:bg-brand-200 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity" title="移除收藏筛选"><X className="w-2.5 h-2.5" /></button>
              </span>
            )}
            {activeStageId && (
              <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-gray-100 text-gray-600 border border-gray-200">
                📍 阶段 {activeStageId.replace(/[^0-9]/g, '')}
              </span>
            )}
            {search && (
              <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-gray-100 text-gray-600 border border-gray-200">
                🔍 "{search}"
              </span>
            )}
            {hasActiveSort && (
              <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-brand-50 text-brand-600 border border-brand-100">
                {SORT_OPTIONS.find(o => o.value === activeSort)?.icon} {SORT_OPTIONS.find(o => o.value === activeSort)?.label}
              </span>
            )}
          </div>
        )}
      </div>

      {/* ========== 搜索 + 筛选 ========== */}
      <div className="space-y-3 mb-6">
        <div className="relative max-w-md">
          <Search className="w-4 h-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            value={search}
            onChange={(e) => {
              const val = e.target.value;
              setSearch(val);
              applyFilter({ search: val });
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                setSearch('');
                applyFilter({ search: '' });
              }
            }}
            placeholder="搜索标题、知识点、章节…"
            className="w-full h-10 pl-10 pr-9 bg-white border border-gray-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all"
          />
          {/* 清空按钮 */}
          {search && (
            <button
              onClick={() => {
                setSearch('');
                applyFilter({ search: '' });
              }}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 w-5 h-5 rounded-full bg-gray-200 hover:bg-gray-300 flex items-center justify-center transition-colors"
              title="清空搜索"
            >
              <X className="w-3 h-3 text-gray-500" />
            </button>
          )}
        </div>

        {/* ========== 排序 + 批量操作入口 ========== */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
          <span className="text-[10px] text-gray-400 flex-shrink-0 mr-0.5">排序：</span>
          {SORT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => updateFilters({ sortBy: opt.value === 'default' ? undefined : opt.value })}
              className={`px-2.5 py-1 rounded-lg text-[10px] font-medium whitespace-nowrap transition-all ${
                activeSort === opt.value
                  ? 'bg-brand-500 text-white shadow-sm'
                  : 'bg-white border border-gray-200 text-gray-500 hover:border-gray-300 hover:bg-gray-50'
              }`}
            >
              {opt.icon} {opt.label}
            </button>
          ))}
          <div className="w-px h-5 bg-gray-200 mx-1.5 flex-shrink-0" />
          <button
            onClick={() => { setSelectionMode(v => !v); if (selectionMode) setSelectedIds(new Set()); }}
            className={`px-2.5 py-1 rounded-lg text-[10px] font-medium whitespace-nowrap transition-all flex items-center gap-1 ${
              selectionMode
                ? 'bg-brand-500 text-white shadow-sm'
                : 'bg-white border border-gray-200 text-gray-500 hover:border-gray-300 hover:bg-gray-50'
            }`}
          >
            <ListChecks className="w-3 h-3" />
            {selectionMode ? '退出选择' : '批量操作'}
          </button>
        </div>

        <ResourceFilters
          active={activeType}
          onFilter={(type) => updateFilters({ type: type || undefined })}
          onSelectDifficulty={(d) => updateFilters({ difficulty: d || undefined })}
          activeDifficulty={activeDifficulty}
          dataSource={activeSource}
          onSelectSource={(s) => updateFilters({ source: s || undefined })}
          activeQuality={activeQuality}
          onSelectQuality={(q) => updateFilters({ qualityStatus: q || undefined })}
          activeStudyStatus={activeStudyStatus}
          onSelectStudyStatus={(s) => updateFilters({ studyStatus: s || undefined })}
          activeBookmarked={activeBookmarked}
          onSelectBookmarked={(b) => updateFilters({ bookmarked: b || undefined })}
          availableChapters={availableChapters}
          activeChapter={activeChapter}
          onSelectChapter={(c) => updateFilters({ chapter: c || undefined })}
          showFilters={showFilters}
          onToggleFilters={() => setShowFilters(v => !v)}
          hasActiveFilters={hasActiveFilters}
          onClearAll={clearAllFilters}
        />
      </div>

      {/* ========== 列表 ========== */}
      {!sessionId ? (
        // 没有当前 session
        <PageEmpty
          icon={<MessageSquare className="w-8 h-8" />}
          title="请先进入学习会话"
          description="请在对话页开始学习，系统将为你生成个性化学习资源。"
          action={
            <button
              onClick={() => chatPanel.setOpen(true)}
              className="mt-3 px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all inline-flex items-center gap-2"
            >
              <Sparkles className="w-4 h-4" />
              去对话页
            </button>
          }
        />
      ) : loading && resources.length === 0 ? (
        <PageLoading text="加载资源中…" />
      ) : error && resources.length === 0 ? (
        <PageError
          title="资源加载失败"
          description={`${error}，请稍后重试。`}
          onRetry={refetch}
          onGoChat={() => chatPanel.setOpen(true)}
        />
      ) : !resources || resources.length === 0 ? (
        <div className="relative">
          {loading && <RefreshOverlay />}
          {hasActiveFilters || search ? (
            // 有筛选条件但没有匹配结果
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mb-4">
                <Search className="w-7 h-7 text-gray-300" />
              </div>
              <h3 className="text-base font-semibold text-gray-700 mb-1">
                {search ? `未搜到"${search}"` : '没有匹配的资源'}
              </h3>
              <p className="text-sm text-gray-400 mb-1">
                {search
                  ? '尝试不同的关键词，搜索范围包括标题、知识点、章节名'
                  : `当前筛选条件下未找到任何资源，共 ${total} 个资源被筛除`}
              </p>
              <p className="text-xs text-gray-300 mb-5 max-w-sm">
                试试调整资源类型、难度、章节或关键词等条件
              </p>
              <button
                onClick={clearAllFilters}
                className="px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all inline-flex items-center gap-2"
              >
                <RotateCcw className="w-4 h-4" />
                清空所有筛选条件
              </button>
            </div>
          ) : (
            // 当前 session 下没有资源
            <PageEmpty
              icon={<BookOpen className="w-8 h-8" />}
              title="当前会话暂无资源"
              description="当前学习会话暂无资源，请先生成学习路径和学习资源。"
              action={
                <button
                  onClick={() => chatPanel.setOpen(true)}
                  className="mt-3 px-5 py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all inline-flex items-center gap-2"
                >
                  <Sparkles className="w-4 h-4" />
                  去对话页生成资源
                </button>
              }
            />
          )}
        </div>
      ) : (
        <div className="relative">
          {loading && <RefreshOverlay />}

          {/* 没有选择科目但当前 session 有资源的提示 */}
          {!subjectId && (
            <div className="mb-4 px-4 py-3 bg-blue-50 border border-blue-100 rounded-xl text-sm text-blue-600 flex items-center gap-2">
              <MessageSquare className="w-4 h-4 flex-shrink-0" />
              <span>当前显示本学习会话下的全部资源，可选择科目进一步筛选。</span>
            </div>
          )}

          {/* 选择模式顶部操作栏 */}
          {selectionMode && (
            <div className="flex items-center justify-between mb-3 px-1">
              <div className="flex items-center gap-2">
                <button
                  onClick={allSelected ? deselectAll : selectAll}
                  className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 transition-colors"
                >
                  {allSelected ? (
                    <CheckSquare className="w-4 h-4 text-brand-500" />
                  ) : (
                    <Square className="w-4 h-4" />
                  )}
                  {allSelected ? '取消全选' : '全选'}
                </button>
                <span className="text-xs text-gray-400">
                  已选 <span className="font-semibold text-gray-600">{selectedIds.size}</span> / {resources.length}
                </span>
              </div>
              <button
                onClick={deselectAll}
                className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
              >
                清除选择
              </button>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {resources.map((r) => (
              <ResourceCard
                key={r.id}
                resource={r}
                onClick={() => selectionMode ? toggleSelect(r.id) : openDetail(r)}
                searchQuery={search}
                selectionMode={selectionMode}
                selected={selectedIds.has(r.id)}
                onToggleSelect={() => toggleSelect(r.id)}
              />
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
              {/* 质检状态 — 可点击查看说明 */}
              {selected.qualityStatus && (
                <QualityStatusPopover
                  qualityStatus={selected.qualityStatus}
                  reviewStatus={(selected as any).reviewStatus}
                  reviewIssues={(selected as any).reviewIssues}
                  reviewSuggestions={(selected as any).reviewSuggestions}
                />
              )}
              {/* 审核状态标签 */}
              {(selected as any).reviewStatus && !selected.qualityStatus && (
                <ReviewStatusBadge status={(selected as any).reviewStatus} />
              )}
              {selected.studyStatus === 'completed' && (
                <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-green-50 text-green-600 border border-green-200">
                  ✅ 已完成
                  {selected.completedAt && ` ${timeAgo(selected.completedAt)}完成`}
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
                    <p className="text-xs font-semibold text-gray-700">
                      <HighlightText text={selected.relatedChapter} query={search} />
                    </p>
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
              {/* 质检状态 — 点击查看详细说明 */}
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
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className={`text-xs font-semibold ${
                        selected.qualityStatus === 'passed' ? 'text-green-600' :
                        selected.qualityStatus === 'fallback_passed' ? 'text-amber-600' : 'text-red-600'
                      }`}>
                        {selected.qualityStatus === 'passed' ? '已通过' :
                         selected.qualityStatus === 'fallback_passed' ? '兜底通过' : '需人工复核'}
                      </span>
                      <QualityStatusPopover
                        qualityStatus={selected.qualityStatus}
                        reviewStatus={(selected as any).reviewStatus}
                        reviewIssues={(selected as any).reviewIssues}
                        reviewSuggestions={(selected as any).reviewSuggestions}
                      />
                    </div>
                  </div>
                </div>
              )}
              {/* 审核问题列表 */}
              {(selected as any).reviewIssues && (selected as any).reviewIssues.length > 0 && (
                <div className="sm:col-span-2">
                  <div className="flex items-center gap-2 mb-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                    <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                      审核问题（{(selected as any).reviewIssues.length}）
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    {(selected as any).reviewIssues.map((issue: any, i: number) => (
                      <div
                        key={i}
                        className={`p-2 rounded-lg border text-[11px] ${
                          issue.severity === 'error' ? 'bg-red-50 border-red-100' :
                          issue.severity === 'warning' ? 'bg-amber-50 border-amber-100' :
                          'bg-blue-50 border-blue-100'
                        }`}
                      >
                        <div className="flex items-start gap-1.5">
                          <span className={`flex-shrink-0 ${
                            issue.severity === 'error' ? 'text-red-500' :
                            issue.severity === 'warning' ? 'text-amber-500' : 'text-blue-500'
                          }`}>
                            {issue.severity === 'error' ? '✗' : issue.severity === 'warning' ? '!' : 'i'}
                          </span>
                          <div className="flex-1 min-w-0">
                            <p className="text-gray-700">{issue.issue}</p>
                            {issue.location && (
                              <p className="text-[10px] text-gray-400 mt-0.5">位置：{issue.location}</p>
                            )}
                            {issue.suggestion && (
                              <p className="text-[10px] text-gray-500 mt-0.5">建议：{issue.suggestion}</p>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* ═══════════════════════════════════════════════════
             *  可信解释面板
             *  ═══════════════════════════════════════════════════ */}
            <div className="border border-gray-100 rounded-xl overflow-hidden">
              {/* 标题栏 */}
              <div className="px-4 py-2.5 bg-gray-50/80 border-b border-gray-100 flex items-center gap-2">
                <Shield className="w-4 h-4 text-gray-500" />
                <span className="text-xs font-semibold text-gray-600">可信解释</span>
                <span className="text-[10px] text-gray-400 ml-auto">
                  帮助你判断此资源的可信度与适用性
                </span>
              </div>
              <div className="p-4 space-y-3">
                {/* 1. 推荐理由 */}
                {(selected as any).reason ? (
                  <div className="p-3 bg-blue-50/70 border border-blue-100 rounded-xl">
                    <p className="text-xs font-semibold text-blue-700 mb-1">💡 推荐理由</p>
                    <p className="text-[11px] text-blue-600 leading-relaxed">{(selected as any).reason}</p>
                  </div>
                ) : selected.source === 'agent_generated' && (
                  <div className="p-3 bg-blue-50/70 border border-blue-100 rounded-xl">
                    <p className="text-xs font-semibold text-blue-700 mb-1">💡 推荐理由</p>
                    <p className="text-[11px] text-blue-600 leading-relaxed">
                      此资源基于当前{selected.relatedChapter ? `「${selected.relatedChapter}」` : ''}阶段
                      {selected.relatedStageId ? `（${selected.relatedStageId}）` : ''}
                      的学习目标和知识短板生成。
                    </p>
                  </div>
                )}

                {/* 2. 来源与生成方式 */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex items-start gap-2">
                    <div className="w-6 h-6 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
                      <span className="text-[10px] font-bold text-gray-500">源</span>
                    </div>
                    <div>
                      <p className="text-[10px] text-gray-400 font-medium">来源类型</p>
                      <p className="text-xs font-semibold text-gray-700 mt-0.5">
                        {(selected as any).sourceType
                          ? sourceTypeLabel((selected as any).sourceType)
                          : (selected.source === 'agent_generated' ? '智能体生成' :
                             selected.source === 'system_inferred' ? '系统推断' :
                             selected.source === 'fallback' ? '兜底' :
                             selected.source === 'user_input' ? '用户输入' : '未知')}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start gap-2">
                    <div className="w-6 h-6 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
                      <span className="text-[10px] font-bold text-gray-500">式</span>
                    </div>
                    <div>
                      <p className="text-[10px] text-gray-400 font-medium">生成方式</p>
                      <p className="text-xs font-semibold text-gray-700 mt-0.5">
                        {(selected as any).generationMode
                          ? generationModeLabel((selected as any).generationMode)
                          : (selected.source === 'system_inferred' || selected.source === 'fallback' ? '规则兜底' : '大模型生成')}
                      </p>
                    </div>
                  </div>
                </div>

                {/* 3. 兜底原因（仅 fallback 类资源显示） */}
                {(selected as any).fallbackReason && (
                  <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-xl">
                    <div className="flex items-center gap-1.5 mb-1">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                      <span className="text-xs font-semibold text-amber-700">兜底说明</span>
                    </div>
                    <p className="text-[11px] text-amber-600 leading-relaxed">{(selected as any).fallbackReason}</p>
                  </div>
                )}

                {/* 4. 证据/依据 */}
                {(selected as any).evidence && Array.isArray((selected as any).evidence) && (selected as any).evidence.length > 0 && (
                  <div>
                    <p className="text-[10px] text-gray-400 font-medium mb-1.5">📋 依据来源</p>
                    <ul className="space-y-1">
                      {(selected as any).evidence.map((ev: string, i: number) => (
                        <li key={i} className="flex items-start gap-1.5 text-[11px] text-gray-600">
                          <span className="text-gray-300 mt-0.5">•</span>
                          <span>{ev}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 5. 质量状态 */}
                {selected.qualityStatus && (
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="text-gray-400">质检状态：</span>
                    <span className={`font-semibold ${
                      selected.qualityStatus === 'passed' ? 'text-green-600' :
                      selected.qualityStatus === 'fallback_passed' ? 'text-amber-600' : 'text-red-600'
                    }`}>
                      {selected.qualityStatus === 'passed' ? '已通过 ✓' :
                       selected.qualityStatus === 'fallback_passed' ? '兜底通过 🛡' : '需人工复核 ⚠'}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* 知识点标签 */}
            <div className="flex flex-wrap gap-1.5">
              {selected.knowledgePoints.map((kp) => (
                <span key={kp} className={`px-2 py-0.5 rounded-md text-[10px] font-medium ${
                  search && matchesQuery(kp, search)
                    ? 'bg-amber-100 text-amber-700 border border-amber-200'
                    : 'bg-brand-50 text-brand-600'
                }`}>
                  <HighlightText text={kp} query={search} />
                </span>
              ))}</div>

            {/* 实操完成说明 */}
            {selected.type === 'case_study' && selected.studyStatus !== 'completed' && (
              <textarea
                value={practiceNotes}
                onChange={(e) => setPracticeNotes(e.target.value)}
                placeholder="完成说明（选填）：描述你完成了什么…"
                rows={2}
                className="w-full resize-none bg-white border border-gray-200 rounded-xl px-3 py-2 text-[11px] outline-none focus:ring-2 focus:ring-brand-500"
              />
            )}

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

              {/* 完成学习/撤销完成 */}
              <button
                onClick={() => handleComplete(selected)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                  selected.studyStatus === 'completed'
                    ? 'bg-amber-50 text-amber-600 border-amber-200 hover:bg-amber-100'
                    : 'bg-green-50 text-green-600 border-green-200 hover:bg-green-100'
                }`}
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                {selected.studyStatus === 'completed' ? '撤销完成' : '标记完成'}
              </button>

              {/* 查看学习分析 */}
              <button
                onClick={() => { setSelected(null); navigate('/analytics'); }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-500 border border-gray-200 hover:border-brand-300 hover:text-brand-600 bg-white transition-all"
              >
                <TrendingUp className="w-3.5 h-3.5" />
                查看学习分析
              </button>

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
            <div className="text-sm text-gray-800 leading-relaxed">
              {/* ===== 课程讲义 / 拓展阅读 : Markdown 正文 ===== */}
              {(selected.type === 'lecture' || selected.type === 'reading') && (
                <LongContent content={selected.content}>
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
                </LongContent>
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
                              <div className="flex items-center gap-2">
                                <span className="w-5 h-5 rounded-full bg-cyan-700 text-cyan-200 text-[9px] font-bold flex items-center justify-center flex-shrink-0">
                                  {i + 1}
                                </span>
                                <span className="text-[10px] text-gray-400 font-mono">{block.language}</span>
                              </div>
                            </div>
                          )}
                          <pre className="text-xs font-mono p-4 overflow-x-auto"><code>{block.code}</code></pre>
                          {block.explanation && (
                            <div className="px-4 py-2 bg-gray-800/50 border-t border-gray-700">
                              <ExpandableText
                                text={block.explanation}
                                maxLines={3}
                                className="text-[10px] text-gray-400 leading-relaxed"
                              />
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

      {/* ========== 浮动批量操作栏 ========== */}
      {selectionMode && selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 mx-auto max-w-2xl w-[calc(100%-3rem)]">
          <div className="bg-gray-900/95 backdrop-blur-lg border border-gray-700 rounded-2xl shadow-2xl px-4 py-3 flex items-center justify-between gap-2 animate-fade-in-up">
            <span className="text-xs text-gray-300 flex-shrink-0">
              已选 <span className="font-bold text-white">{selectedIds.size}</span> 项
            </span>
            <div className="flex items-center gap-1.5 flex-wrap justify-end">
              <button
                onClick={() => setBatchConfirm({ action: 'complete', open: true })}
                disabled={batchProcessing}
                className="px-3 py-1.5 rounded-lg text-[10px] font-medium bg-green-500 text-white hover:bg-green-600 disabled:opacity-40 transition-all flex items-center gap-1"
              >
                <CheckCircle2 className="w-3 h-3" />
                标记完成
              </button>
              <button
                onClick={() => setBatchConfirm({ action: 'bookmark', open: true })}
                disabled={batchProcessing}
                className="px-3 py-1.5 rounded-lg text-[10px] font-medium bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-40 transition-all flex items-center gap-1"
              >
                <BookmarkCheck className="w-3 h-3" />
                收藏
              </button>
              <button
                onClick={() => setBatchConfirm({ action: 'unbookmark', open: true })}
                disabled={batchProcessing}
                className="px-3 py-1.5 rounded-lg text-[10px] font-medium bg-gray-600 text-white hover:bg-gray-500 disabled:opacity-40 transition-all flex items-center gap-1"
              >
                <BookmarkX className="w-3 h-3" />
                取消收藏
              </button>
              <button
                onClick={() => setBatchConfirm({ action: 'export', open: true })}
                disabled={batchProcessing}
                className="px-3 py-1.5 rounded-lg text-[10px] font-medium bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-40 transition-all flex items-center gap-1"
              >
                <Download className="w-3 h-3" />
                导出
              </button>
              <button
                onClick={deselectAll}
                disabled={batchProcessing}
                className="px-3 py-1.5 rounded-lg text-[10px] font-medium bg-gray-700 text-gray-300 hover:bg-gray-600 disabled:opacity-40 transition-all"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========== 批量操作确认弹窗 ========== */}
      <Modal open={batchConfirm.open} onClose={() => setBatchConfirm(prev => ({ ...prev, open: false }))} title="确认批量操作">
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            {batchConfirm.action === 'complete' && `确定将选中的 ${selectedIds.size} 个资源标记为「已完成」？`}
            {batchConfirm.action === 'bookmark' && `确定将选中的 ${selectedIds.size} 个资源加入「收藏」？`}
            {batchConfirm.action === 'unbookmark' && `确定将选中的 ${selectedIds.size} 个资源取消「收藏」？`}
            {batchConfirm.action === 'export' && `确定导出选中的 ${selectedIds.size} 个资源标题清单？`}
          </p>
          <div className="flex items-center gap-2 justify-end">
            <button
              onClick={() => setBatchConfirm(prev => ({ ...prev, open: false }))}
              disabled={batchProcessing}
              className="px-4 py-2 rounded-xl text-xs font-medium bg-white border border-gray-200 text-gray-500 hover:bg-gray-50 transition-all"
            >
              取消
            </button>
            <button
              onClick={executeBatchAction}
              disabled={batchProcessing}
              className="px-4 py-2 rounded-xl text-xs font-medium bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-40 transition-all flex items-center gap-1.5"
            >
              {batchProcessing ? (
                <>处理中…</>
              ) : (
                <>确认{batchConfirm.action === 'export' ? '导出' : '执行'}</>
              )}
            </button>
          </div>
        </div>
      </Modal>

      {/* ========== 导出结果弹窗 ========== */}
      <Modal open={!!batchExportText} onClose={() => setBatchExportText(null)} title="资源导出清单" wide>
        {batchExportText && (
          <div className="space-y-4">
            <pre className="text-xs text-gray-700 bg-gray-50 rounded-xl p-4 border border-gray-100 max-h-80 overflow-y-auto whitespace-pre-wrap font-mono leading-relaxed">
              {batchExportText}
            </pre>
            <div className="flex items-center gap-2 justify-end">
              <button
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(batchExportText);
                    setErrorMsg('已复制到剪贴板');
                    setTimeout(() => setErrorMsg(null), 2000);
                  } catch { /* ignore */ }
                }}
                className="px-4 py-2 rounded-xl text-xs font-medium bg-white border border-gray-200 text-gray-500 hover:bg-gray-50 transition-all"
              >
                复制到剪贴板
              </button>
              <button
                onClick={() => setBatchExportText(null)}
                className="px-4 py-2 rounded-xl text-xs font-medium bg-gray-900 text-white hover:bg-gray-800 transition-all"
              >
                关闭
              </button>
            </div>
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
