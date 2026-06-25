import { useState } from 'react';
import {
  Clock, BookOpen, Brain, Code, FileText, Lightbulb,
  Play, Presentation, BookmarkCheck, CheckCircle2, ChevronRight,
  CheckSquare, Square, ChevronDown, ChevronUp, Shield,
} from 'lucide-react';
import type { Resource } from '../../types/resource';
import type { ResourceType } from '../../types/resource';
import { RESOURCE_TYPE_LABELS } from '../../utils/constants';
import { formatDuration } from '../../utils/format';
import { HighlightText, matchesQuery } from '../../utils/highlight';
import SourceBadge from '../common/SourceBadge';
import { SourceTag } from '../common/PageState';

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

interface Props {
  resource: Resource;
  onClick: () => void;
  searchQuery?: string;
  selected?: boolean;
  onToggleSelect?: () => void;
  selectionMode?: boolean;
}

export default function ResourceCard({ resource, onClick, searchQuery, selected, onToggleSelect, selectionMode }: Props) {
  const [showAllKps, setShowAllKps] = useState(false);
  const hasManyKps = resource.knowledgePoints.length > 3;
  const colorMap: Record<string, string> = {
    lecture: 'from-blue-400 to-blue-500', mindmap: 'from-purple-400 to-purple-500',
    quiz: 'from-amber-400 to-orange-500', case_study: 'from-cyan-400 to-teal-500',
    reading: 'from-emerald-400 to-green-500', video: 'from-red-400 to-rose-500',
    ppt: 'from-orange-400 to-amber-500',
  };
  const bgMap: Record<string, string> = {
    lecture: 'bg-blue-50', mindmap: 'bg-purple-50', quiz: 'bg-amber-50',
    case_study: 'bg-cyan-50', reading: 'bg-emerald-50', video: 'bg-red-50', ppt: 'bg-orange-50',
  };

  return (
    <button
      onClick={onClick}
      className={`group bg-white border rounded-2xl text-left transition-all duration-300 w-full relative overflow-hidden ${
        selected ? 'border-brand-400 ring-2 ring-brand-200 shadow-md' : 'border-gray-100 hover:shadow-xl hover:-translate-y-1.5'
      }`}
    >
      <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${colorMap[resource.type] || 'from-gray-400 to-gray-500'}`} />
      <div className={`absolute -bottom-8 -right-8 w-20 h-20 ${bgMap[resource.type] || 'bg-gray-50'} rounded-full opacity-60 group-hover:scale-150 transition-transform duration-500`} />

      <div className="relative p-5 pt-4">
        <div className="flex items-start gap-3 mb-3">
          <div className={`w-11 h-11 rounded-xl ${bgMap[resource.type] || 'bg-gray-50'} flex items-center justify-center flex-shrink-0 shadow-sm group-hover:scale-110 group-hover:shadow-md transition-all duration-300`}>
            {iconMap[resource.type]}
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-gray-900 truncate group-hover:text-gray-700 transition-colors">
              <HighlightText text={resource.title} query={searchQuery} />
            </h3>
            <p className="text-xs text-gray-400 mt-0.5 line-clamp-2 leading-relaxed">
              <HighlightText text={resource.description} query={searchQuery} />
            </p>
            <div className="mt-1.5"><SourceTag source={resource.source} /></div>
          </div>
          {resource.studyStatus === 'completed' && (
            <div className="w-6 h-6 rounded-full bg-green-100 flex items-center justify-center flex-shrink-0">
              <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${difficultyBadge[resource.difficulty]}`}>
            {difficultyLabel[resource.difficulty]}
          </span>
          <span className="px-2 py-0.5 rounded-md text-[10px] text-gray-500 bg-gray-50 border border-gray-100">
            {RESOURCE_TYPE_LABELS[resource.type]}
          </span>
          {resource.qualityStatus && resource.qualityStatus !== 'passed' && (
            <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${
              resource.qualityStatus === 'fallback_passed' ? 'bg-amber-50 text-amber-600 border-amber-200' : 'bg-red-50 text-red-600 border-red-200'
            }`}>
              {resource.qualityStatus === 'fallback_passed' ? '兜底' : '需复核'}
            </span>
          )}
          {resource.tags.slice(0, 2).map((tag) => (
            <span key={tag} className={`px-2 py-0.5 rounded-md text-[10px] ${searchQuery && matchesQuery(tag, searchQuery) ? 'bg-amber-100 text-amber-700 font-medium' : 'text-gray-400 bg-gray-50'}`}>
              <HighlightText text={tag} query={searchQuery} />
            </span>
          ))}
          {(showAllKps ? resource.knowledgePoints : resource.knowledgePoints.slice(0, 3)).map((kp) => (
            <span key={kp} className={`px-2 py-0.5 rounded-md text-[10px] ${
              searchQuery && matchesQuery(kp, searchQuery) ? 'bg-amber-100 text-amber-700 font-medium border border-amber-200' : 'bg-brand-50 text-brand-600 border border-brand-100'
            }`}>
              <HighlightText text={kp} query={searchQuery} />
            </span>
          ))}
          {hasManyKps && (
            <button
              onClick={(e) => { e.stopPropagation(); setShowAllKps(!showAllKps); }}
              className="px-2 py-0.5 rounded-md text-[10px] font-medium text-gray-400 bg-gray-50 border border-gray-100 hover:bg-gray-100 hover:text-gray-600 transition-colors inline-flex items-center gap-0.5"
            >
              {showAllKps ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              {showAllKps ? '收起' : `+${resource.knowledgePoints.length - 3}`}
            </button>
          )}
        </div>

        {(resource.relatedStageId || resource.relatedChapter) && (
          <div className="flex flex-wrap items-center gap-2 mb-2 text-[10px] text-gray-400">
            {resource.relatedChapter && <span className="inline-flex items-center gap-1">📖 <HighlightText text={resource.relatedChapter} query={searchQuery} /></span>}
            {resource.relatedStageId && <span className="inline-flex items-center gap-1">📍 阶段 {resource.relatedStageId.replace(/[^0-9]/g, '')}</span>}
          </div>
        )}

        {/* ── 可信解释区 ── */}
        <div className="mb-2 space-y-1">
          {/* 来源类型 + 生成方式 */}
          {(resource.sourceType || resource.generationMode) && (
            <div className="flex flex-wrap items-center gap-1.5">
              {resource.sourceType && (
                <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-medium bg-gray-50 text-gray-500 border border-gray-100"
                  title="来源类型">
                  🏷️ {resource.sourceType === 'llm_generated' ? '大模型生成' :
                         resource.sourceType === 'rule_based' ? '规则生成' :
                         resource.sourceType === 'knowledge_base' ? '知识库检索' :
                         resource.sourceType === 'user_input' ? '用户输入' :
                         resource.sourceType}
                </span>
              )}
              {resource.generationMode && (
                <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-medium bg-gray-50 text-gray-500 border border-gray-100"
                  title="生成方式">
                  ⚙️ {resource.generationMode === 'direct_generation' ? '直接生成' :
                        resource.generationMode === 'knowledge_retrieval' ? '知识检索' :
                        resource.generationMode === 'hybrid' ? '混合生成' :
                        resource.generationMode === 'rule_fallback' ? '规则兜底' :
                        resource.generationMode}
                </span>
              )}
            </div>
          )}
          {/* 推荐理由 */}
          {resource.reason && (
            <p className="text-[10px] text-gray-500 leading-relaxed line-clamp-2">
              💡 <span className="font-medium text-gray-600">推荐理由：</span>{resource.reason}
            </p>
          )}
          {/* 兜底原因 */}
          {resource.fallbackReason && (
            <p className="text-[10px] text-amber-600 leading-relaxed line-clamp-2">
              ⚠️ <span className="font-medium">兜底说明：</span>{resource.fallbackReason}
            </p>
          )}
        </div>

        <div className="flex items-center justify-between text-[10px] text-gray-400 pt-1">
          <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{formatDuration(resource.estimatedMinutes)}</span>
          <div className="flex items-center gap-2">
            {/* fallback 温和标识 */}
            {resource.source === 'system_inferred' && (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] bg-slate-50 text-slate-400 border border-slate-100" title="此资源由系统规则生成">
                <Shield className="w-2.5 h-2.5" />
                兜底
              </span>
            )}
            {resource.bookmarked && <span className="flex items-center gap-0.5 text-brand-500"><BookmarkCheck className="w-3 h-3" /></span>}
            <SourceBadge source={resource.source || 'system_inferred'} size="xs" />
            <span className="flex items-center gap-0.5 text-brand-500 opacity-0 group-hover:opacity-100 transition-opacity">查看详情 <ChevronRight className="w-3 h-3" /></span>
          </div>
        </div>
      </div>

      {selectionMode && (
        <button onClick={(e) => { e.stopPropagation(); onToggleSelect?.(); }}
          className={`absolute top-3 left-3 w-6 h-6 rounded-md border-2 flex items-center justify-center transition-all z-10 ${selected ? 'bg-brand-500 border-brand-500 text-white' : 'bg-white/90 border-gray-300 hover:border-brand-400'}`}>
          {selected ? <CheckSquare className="w-4 h-4" /> : <Square className="w-3.5 h-3.5" />}
        </button>
      )}
    </button>
  );
}
