import { Info, ChevronDown, ChevronUp, ShieldAlert } from 'lucide-react';
import type { ProfileDimension } from '../../types/profile';
import { DIMENSION_COLORS } from '../../utils/constants';
import ExpandableText from '../common/ExpandableText';

const SOURCE_LABELS: Record<string, { label: string; color: string }> = {
  user_input:          { label: '用户提供',   color: 'bg-blue-50 text-blue-600 border-blue-200' },
  inferred:            { label: '系统推断',   color: 'bg-purple-50 text-purple-600 border-purple-200' },
  llm_generated:       { label: 'LLM 生成',  color: 'bg-green-50 text-green-600 border-green-200' },
  rule_based_fallback: { label: '规则兜底',   color: 'bg-amber-50 text-amber-600 border-amber-200' },
  diagnosis:           { label: '诊断分析',   color: 'bg-rose-50 text-rose-600 border-rose-200' },
  feedback:            { label: '用户反馈',   color: 'bg-cyan-50 text-cyan-600 border-cyan-200' },
};

interface Props {
  dim: ProfileDimension;
  index: number;
}

export default function ProfileDimensionCard({ dim, index }: Props) {
  const color = DIMENSION_COLORS[index % DIMENSION_COLORS.length];
  const sourceInfo = SOURCE_LABELS[dim.source];

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-4 hover:shadow-md transition-all duration-200">
      <div className="flex items-start justify-between mb-3 gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
          <h4 className="text-sm font-semibold text-gray-800 truncate">{dim.label}</h4>
        </div>
        {sourceInfo && (
          <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border whitespace-nowrap ${sourceInfo.color}`}>
            {sourceInfo.label}
          </span>
        )}
      </div>

      <div className="flex items-center gap-3 mb-3">
        <div className="flex-1 h-2.5 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all duration-700" style={{ width: `${dim.score}%`, backgroundColor: color }} />
        </div>
        <span className="text-lg font-bold tabular-nums" style={{ color }}>{dim.score}</span>
      </div>

      {dim.value && (
        <p className="text-xs text-gray-700 leading-relaxed mb-2">{dim.value}</p>
      )}

      {(dim.explanation || dim.description) && (
        <ExpandableText
          text={dim.explanation || dim.description || ''}
          maxLines={3}
          className="text-[11px] text-gray-500 leading-relaxed mb-2"
        />
      )}

      {dim.evidence && (
        <div className="mb-2 p-3 bg-gray-50 border border-gray-100 rounded-lg">
          <div className="flex items-center gap-1 mb-1.5">
            <Info className="w-3 h-3 text-gray-400" />
            <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">支撑证据</span>
          </div>
          <ExpandableText
            text={dim.evidence}
            maxLines={4}
            className="text-[11px] text-gray-500 leading-relaxed"
          />
        </div>
      )}

      <div className="flex items-center gap-1.5 text-[10px] text-gray-400">
        <div className="flex-1 h-1 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${dim.confidence * 100}%`, backgroundColor: color }} />
        </div>
        {dim.confidence < 0.5 ? (
          <span className="tabular-nums text-amber-500 flex items-center gap-0.5" title="需要更多学习数据确认（置信度较低）">
            <ShieldAlert className="w-2.5 h-2.5" />
            需更多数据
          </span>
        ) : dim.confidence < 0.75 ? (
          <span className="tabular-nums text-gray-400">{(dim.confidence * 100).toFixed(0)}%</span>
        ) : (
          <span className="tabular-nums text-green-500">{(dim.confidence * 100).toFixed(0)}%</span>
        )}
      </div>
      {dim.confidence < 0.5 && dim.source !== 'user_input' && (
        <div className="mt-2 p-2 bg-amber-50/60 border border-dashed border-amber-200 rounded-lg">
          <p className="text-[10px] text-amber-600 leading-relaxed flex items-start gap-1">
            <ShieldAlert className="w-2.5 h-2.5 flex-shrink-0 mt-0.5" />
            此维度基于有限数据推断（置信度 {(dim.confidence * 100).toFixed(0)}%），继续学习后可获得更精准的画像。
          </p>
        </div>
      )}
    </div>
  );
}
