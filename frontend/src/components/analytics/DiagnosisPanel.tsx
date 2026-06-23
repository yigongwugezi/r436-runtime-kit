import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertCircle, AlertTriangle, Info, BookOpen, MessageSquare,
  ChevronDown, ChevronUp, Target, ArrowRight, ExternalLink,
  Sparkles, Cpu, Shield,
} from 'lucide-react';
import ExpandableText from '../common/ExpandableText';

/* ===================================================================
 * 诊断数据类型
 * =================================================================== */
export interface DiagnosisResult {
  /** 薄弱知识点列表 */
  weakTopics: DiagnosisWeakTopic[];
  /** 综合诊断描述 */
  summary?: string;
  /** 诊断置信度 (0-1) */
  confidence?: number;
  /** 诊断数据来源 */
  source?: 'agent_generated' | 'system_inferred' | 'user_input';
  /** 推荐资源 ID 列表 */
  recommendedResourceIds?: string[];
  /** 推荐学习阶段 ID */
  recommendedStageId?: string;
  /** 建议的学习路径阶段 */
  recommendedStageTitle?: string;
}

export interface DiagnosisWeakTopic {
  topic: string;
  /** 优先级: high / medium / low */
  priority: 'high' | 'medium' | 'low';
  /** 推荐原因 */
  reason?: string;
  /** 支撑证据 */
  evidence?: string;
  /** 置信度 (0-1) */
  confidence?: number;
  /** 掌握度 (0-100) */
  mastery?: number;
  /** 错误次数 */
  wrongCount?: number;
  /** 总题数 */
  totalCount?: number;
  /** 推荐资源 ID 列表 */
  recommendedResourceIds?: string[];
  /** 推荐学习阶段 ID */
  recommendedStageId?: string;
}

/* ===================================================================
 * 优先级配置
 * =================================================================== */
const PRIORITY_CONFIG: Record<string, {
  label: string; color: string; bg: string; border: string; icon: any;
}> = {
  high: {
    label: '高优先',
    color: 'text-red-600',
    bg: 'bg-red-50',
    border: 'border-red-200',
    icon: AlertCircle,
  },
  medium: {
    label: '中优先',
    color: 'text-amber-600',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    icon: AlertTriangle,
  },
  low: {
    label: '低优先',
    color: 'text-blue-600',
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    icon: Info,
  },
};

/* ===================================================================
 * 薄弱知识点卡片
 * =================================================================== */
function WeakTopicCard({
  topic,
  priority,
  reason,
  evidence,
  confidence,
  mastery,
  wrongCount,
  totalCount,
  recommendedResourceIds,
  recommendedStageId,
}: DiagnosisWeakTopic) {
  const navigate = useNavigate();
  const [showEvidence, setShowEvidence] = useState(false);
  const cfg = PRIORITY_CONFIG[priority] || PRIORITY_CONFIG.low;
  const Icon = cfg.icon;
  const hasResources = recommendedResourceIds && recommendedResourceIds.length > 0;
  const hasStage = !!recommendedStageId;
  const isLowConfidence = confidence != null && confidence < 0.5;

  return (
    <div className={`${cfg.bg} ${cfg.border} border rounded-xl p-3.5 space-y-2.5`}>
      {/* 第一行：知识点名 + 优先级 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Icon className={`w-4 h-4 flex-shrink-0 ${cfg.color}`} />
          <span className={`text-sm font-semibold ${cfg.color} truncate`}>{topic}</span>
        </div>
        <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border whitespace-nowrap ${cfg.color} ${cfg.bg} ${cfg.border}`}>
          {cfg.label}
        </span>
      </div>

      {/* 第二行：掌握度 + 置信度 */}
      <div className="flex items-center gap-3 flex-wrap">
        {mastery != null && (
          <div className="flex items-center gap-1.5">
            <Target className="w-3 h-3 text-gray-400" />
            <div className="flex items-center gap-1">
              <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    mastery >= 80 ? 'bg-green-400' : mastery >= 50 ? 'bg-amber-400' : 'bg-red-400'
                  }`}
                  style={{ width: `${mastery}%` }}
                />
              </div>
              <span className={`text-[10px] font-medium ${
                mastery >= 80 ? 'text-green-600' : mastery >= 50 ? 'text-amber-600' : 'text-red-600'
              }`}>
                {mastery}%
              </span>
            </div>
          </div>
        )}
        {wrongCount != null && totalCount != null && (
          <span className="text-[10px] text-gray-400">
            错 {wrongCount}/{totalCount}
          </span>
        )}
        {confidence != null && (
          <span
            className={`text-[10px] font-medium ${
              confidence >= 0.7 ? 'text-green-500' : confidence >= 0.4 ? 'text-amber-500' : 'text-red-400'
            }`}
            title={`置信度：${Math.round(confidence * 100)}%`}
          >
            {confidence >= 0.7 ? '✓ 高可信' : confidence >= 0.4 ? '~ 中等可信' : '? 低可信'}
          </span>
        )}
      </div>

      {/* 低置信度提示 */}
      {isLowConfidence && (
        <div className="flex items-start gap-1.5 p-2 bg-white/60 rounded-lg border border-dashed border-gray-200">
          <Info className="w-3 h-3 text-amber-400 flex-shrink-0 mt-0.5" />
          <p className="text-[10px] text-amber-600 leading-relaxed">
            此诊断结果基于有限数据（置信度 {Math.round((confidence || 0) * 100)}%），随着更多学习数据的积累，诊断准确性将逐步提升。
          </p>
        </div>
      )}

      {/* 推荐原因 */}
      {reason && (
        <ExpandableText
          text={reason}
          maxLines={2}
          className="text-xs text-gray-600 leading-relaxed"
        />
      )}

      {/* 支撑证据（可展开） */}
      {evidence && (
        <div>
          <button
            onClick={() => setShowEvidence(!showEvidence)}
            className="inline-flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-600 font-medium transition-colors"
          >
            <Shield className="w-3 h-3" />
            支撑证据
            {showEvidence ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
          {showEvidence && (
            <div className="mt-1.5 p-2.5 bg-white/80 rounded-lg border border-gray-100">
              <ExpandableText
                text={evidence}
                maxLines={5}
                className="text-[11px] text-gray-500 leading-relaxed"
              />
            </div>
          )}
        </div>
      )}

      {/* 跳转按钮 */}
      <div className="flex items-center gap-2 pt-0.5">
        {hasResources && (
          <button
            onClick={() => {
              const ids = recommendedResourceIds!.join(',');
              navigate(`/resources?resourceIds=${encodeURIComponent(ids)}`);
            }}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-medium bg-white border border-gray-200 text-gray-500 hover:border-brand-300 hover:text-brand-600 transition-all"
            title="查看推荐的相关资源"
          >
            <BookOpen className="w-3 h-3" />
            推荐资源 ({recommendedResourceIds!.length})
          </button>
        )}
        {hasStage && (
          <button
            onClick={() => navigate(`/path?stage=${encodeURIComponent(recommendedStageId!)}`)}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-medium bg-white border border-gray-200 text-gray-500 hover:border-brand-300 hover:text-brand-600 transition-all"
            title="跳转到推荐的学习阶段"
          >
            <ArrowRight className="w-3 h-3" />
            查看阶段
          </button>
        )}
        <button
          onClick={() => navigate(`/chat?prompt=${encodeURIComponent(`帮我讲解一下${topic}，我这个地方掌握得不太好`)}`)}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-medium bg-white border border-gray-200 text-gray-500 hover:border-brand-300 hover:text-brand-600 transition-all"
          title="去对话页提问"
        >
          <MessageSquare className="w-3 h-3" />
          去提问
        </button>
      </div>
    </div>
  );
}

/* ===================================================================
 * 空状态 — 暂无诊断结果
 * =================================================================== */
export function DiagnosisEmptyState({
  onStartDiagnosis,
}: {
  onStartDiagnosis?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center mb-4 shadow-inner">
        <AlertCircle className="w-7 h-7 text-gray-300" />
      </div>
      <h3 className="text-base font-semibold text-gray-700 mb-1">暂无诊断结果</h3>
      <p className="text-xs text-gray-400 max-w-xs mb-5 leading-relaxed">
        完成更多学习任务后，系统将自动分析你的知识短板并提供针对性建议
      </p>
      {onStartDiagnosis && (
        <button
          onClick={onStartDiagnosis}
          className="px-4 py-2 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-all inline-flex items-center gap-2"
        >
          <Sparkles className="w-4 h-4" />
          去对话页开始学习
        </button>
      )}
    </div>
  );
}

/* ===================================================================
 * 主诊断面板
 * =================================================================== */
interface DiagnosisPanelProps {
  /** 诊断结果数据 */
  diagnosis?: DiagnosisResult | null;
  /** 是否正在加载 */
  loading?: boolean;
  /** 点击"开始诊断"的回调 */
  onStartDiagnosis?: () => void;
  /** 自定义空状态提示 */
  emptyTitle?: string;
  emptyDescription?: string;
}

export default function DiagnosisPanel({
  diagnosis,
  loading,
  onStartDiagnosis,
  emptyTitle = '暂无诊断结果',
  emptyDescription = '完成更多学习任务后，系统将自动分析你的知识短板并提供针对性建议',
}: DiagnosisPanelProps) {
  const navigate = useNavigate();

  // —— Loading ——
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
          <p className="text-xs text-gray-400">正在分析学习数据…</p>
        </div>
      </div>
    );
  }

  // —— Empty ——
  if (!diagnosis || !diagnosis.weakTopics || diagnosis.weakTopics.length === 0) {
    return (
      <DiagnosisEmptyState
        onStartDiagnosis={onStartDiagnosis}
      />
    );
  }

  const isLowConfidence = diagnosis.confidence != null && diagnosis.confidence < 0.5;
  const isFallback = diagnosis.source === 'system_inferred';

  return (
    <div className="space-y-4">
      {/* 诊断摘要 */}
      {diagnosis.summary && (
        <div className="p-3.5 bg-gradient-to-r from-brand-50 to-blue-50 border border-brand-100 rounded-xl">
          <div className="flex items-start gap-2.5">
            <div className="w-7 h-7 rounded-xl bg-brand-100 flex items-center justify-center flex-shrink-0">
              <Target className="w-3.5 h-3.5 text-brand-600" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-gray-800 mb-1">诊断结论</p>
              <p className="text-xs text-gray-600 leading-relaxed">{diagnosis.summary}</p>
            </div>
          </div>
        </div>
      )}

      {/* 低置信度提示 */}
      {isLowConfidence && (
        <div className="p-3 bg-amber-50/80 border border-amber-200 rounded-xl flex items-start gap-2.5">
          <Info className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-xs font-medium text-amber-700 mb-0.5">诊断数据有限</p>
            <p className="text-[10px] text-amber-600 leading-relaxed">
              当前诊断基于有限的学习事件（置信度 {Math.round((diagnosis.confidence || 0) * 100)}%），
              完成更多学习任务可获得更精准的诊断分析。
            </p>
          </div>
        </div>
      )}

      {/* fallback 提示 */}
      {isFallback && (
        <div className="p-3 bg-slate-50/80 border border-slate-200 rounded-xl flex items-start gap-2.5">
          <Cpu className="w-4 h-4 text-slate-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-xs font-medium text-slate-700 mb-0.5">系统推测</p>
            <p className="text-[10px] text-slate-500 leading-relaxed">
              此为系统基于有限规则的初步推测，尚未经过 AI 智能体的深度分析。
              建议在对话中补充更多学习信息以获取个性化诊断。
            </p>
          </div>
        </div>
      )}

      {/* 通用推荐跳转（整个面板级别） */}
      {diagnosis.recommendedResourceIds && diagnosis.recommendedResourceIds.length > 0 && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              const ids = diagnosis.recommendedResourceIds!.join(',');
              navigate(`/resources?resourceIds=${encodeURIComponent(ids)}`);
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-medium bg-brand-50 text-brand-600 border border-brand-200 hover:bg-brand-100 transition-all"
            title="查看推荐的针对性资源"
          >
            <BookOpen className="w-3.5 h-3.5" />
            查看推荐资源 ({diagnosis.recommendedResourceIds.length})
            <ExternalLink className="w-3 h-3" />
          </button>
          {diagnosis.recommendedStageId && (
            <button
              onClick={() => navigate(`/path?stage=${encodeURIComponent(diagnosis.recommendedStageId!)}`)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-medium bg-brand-50 text-brand-600 border border-brand-200 hover:bg-brand-100 transition-all"
              title="跳转到推荐的学习阶段"
            >
              <ArrowRight className="w-3.5 h-3.5" />
              推荐阶段{diagnosis.recommendedStageTitle ? `：${diagnosis.recommendedStageTitle}` : ''}
              <ExternalLink className="w-3 h-3" />
            </button>
          )}
        </div>
      )}

      {/* 薄弱知识点列表 */}
      <div className="space-y-2.5">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-gray-400" />
          <span className="text-xs font-semibold text-gray-600">
            薄弱知识点（{diagnosis.weakTopics.length}）
          </span>
          <span className="text-[10px] text-gray-400">
            按优先级排列
          </span>
        </div>
        {diagnosis.weakTopics.map((topic, i) => (
          <WeakTopicCard key={`${topic.topic}-${i}`} {...topic} />
        ))}
      </div>
    </div>
  );
}

export { WeakTopicCard };
