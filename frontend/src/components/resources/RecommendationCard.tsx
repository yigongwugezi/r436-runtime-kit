// @ts-nocheck
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, Brain, Code, FileText, Lightbulb, Play, Presentation, X, ChevronRight } from 'lucide-react';
import type { ProfileRecommendation } from '../../api/profile';
import type { Resource } from '../../types/resource';
import { RESOURCE_TYPE_LABELS } from '../../utils/constants';
import { formatDuration } from '../../utils/format';

const icons: Record<string, React.ReactNode> = {
  lecture: <BookOpen className="w-4 h-4" />,
  mindmap: <Brain className="w-4 h-4" />,
  quiz: <FileText className="w-4 h-4" />,
  reading: <Lightbulb className="w-4 h-4" />,
  case_study: <Code className="w-4 h-4" />,
  practice: <Code className="w-4 h-4" />,
  video: <Play className="w-4 h-4" />,
  ppt: <Presentation className="w-4 h-4" />,
};

const priorityLabel: Record<string, string> = { high: '优先', medium: '推荐', low: '参考' };

const diffLabel: Record<string, string> = { easy: '基础', medium: '进阶', hard: '挑战' };

export interface RecommendationCardProps {
  recommendation: ProfileRecommendation;
  localResource?: Resource;
  onDismiss?: (recommendation: ProfileRecommendation) => void;
}

export default function RecommendationCard({
  recommendation,
  localResource,
  onDismiss,
}: RecommendationCardProps) {
  const nav = useNavigate();

  const resourceType = localResource?.type || inferType(recommendation);
  const difficulty = localResource?.difficulty;
  const estimatedMinutes = localResource?.estimatedMinutes;
  const hasResource = Boolean(recommendation.target_resource_id);
  const icon = icons[resourceType] || icons.reading;
  const typeLabel = RESOURCE_TYPE_LABELS[resourceType as keyof typeof RESOURCE_TYPE_LABELS] || resourceType;

  const handleClick = () => {
    if (recommendation.target_resource_id) {
      nav(`/resources/${recommendation.target_resource_id}`);
    }
  };

  const handleDismiss = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDismiss?.(recommendation);
  };

  return (
    <div
      onClick={handleClick}
      className={`bg-white rounded-xl border border-surface-200 p-4 hover:border-surface-300 hover:shadow-sm transition-all ${hasResource ? 'cursor-pointer group' : 'opacity-60 cursor-default'}`}
    >
      {/* 类型标签行 */}
      <div className="flex items-center justify-between mb-3">
        <span className="inline-flex items-center gap-1.5 text-xs text-surface-500">
          <span className="text-surface-400">{icon}</span>
          {typeLabel}
        </span>
        <span className="text-[10px] text-surface-400">{priorityLabel[recommendation.priority]}</span>
      </div>

      {/* 标题 */}
      <h4 className={`text-sm font-medium text-surface-800 mb-1.5 line-clamp-2 ${hasResource ? 'group-hover:text-primary-600' : ''} transition-colors`}>
        {recommendation.title}
      </h4>

      {/* 推荐理由 */}
      <p className="text-xs text-surface-500 mb-3 leading-relaxed line-clamp-2">
        {recommendation.reason}
      </p>

      {/* 元信息行 */}
      <div className="flex items-center gap-3 text-[11px] text-surface-400 mb-3">
        {difficulty && <span>{diffLabel[difficulty]}</span>}
        {estimatedMinutes != null && estimatedMinutes > 0 && (
          <span>约 {formatDuration(estimatedMinutes)}</span>
        )}
        {recommendation.confidence > 0 && (
          <span>置信 {Math.round(recommendation.confidence * 100)}%</span>
        )}
      </div>

      {/* 操作按钮行 */}
      <div className="flex items-center gap-2">
        {hasResource ? (
          <button
            onClick={(e) => { e.stopPropagation(); handleClick(); }}
            className="flex-1 inline-flex items-center justify-center gap-1 px-3 py-1.5 bg-surface-800 text-white rounded-lg text-xs font-medium hover:bg-surface-900 transition-colors"
          >
            开始学习
            <ChevronRight size={12} />
          </button>
        ) : (
          <span className="flex-1 text-center text-[11px] text-surface-400">暂无关联资源</span>
        )}
        <button
          onClick={handleDismiss}
          title="不感兴趣"
          className="p-1.5 rounded-lg text-surface-300 hover:text-surface-500 hover:bg-surface-100 transition-colors"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}

function inferType(rec: ProfileRecommendation): string {
  const reason = (rec.reason || '').toLowerCase();
  if (reason.includes('练习') || reason.includes('练习')) return 'quiz';
  if (reason.includes('案例') || reason.includes('实操')) return 'case_study';
  if (reason.includes('视频') || reason.includes('动画')) return 'video';
  return 'reading';
}
