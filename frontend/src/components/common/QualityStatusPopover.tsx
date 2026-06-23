import { useState, useRef, useEffect } from 'react';
import { Info, Shield, AlertTriangle, CheckCircle, X } from 'lucide-react';
import type { QualityStatus, ReviewStatus, ReviewIssue } from '../../types/resource';

/* ===================================================================
 * 质检状态含义映射
 * =================================================================== */
export const QUALITY_STATUS_INFO: Record<string, {
  label: string;
  description: string;
  color: string;
  bg: string;
  border: string;
  icon: any;
  details: string;
}> = {
  passed: {
    label: '已通过',
    description: '内容质量通过 AI 审核',
    color: 'text-green-600',
    bg: 'bg-green-50',
    border: 'border-green-200',
    icon: CheckCircle,
    details: '此资源已通过 ReviewAgent 的质量审核，内容准确性和完整性符合标准，可以放心使用。',
  },
  needs_review: {
    label: '需复核',
    description: '内容质量需要人工复核',
    color: 'text-red-600',
    bg: 'bg-red-50',
    border: 'border-red-200',
    icon: AlertTriangle,
    details: '此资源在审核中发现潜在问题，建议在使用前仔细核对内容准确性。可能存在的事实错误或不一致需要人工确认。',
  },
  fallback_passed: {
    label: '兜底通过',
    description: '系统规则生成的兜底内容',
    color: 'text-amber-600',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    icon: Shield,
    details: '此资源由系统规则自动生成，未经过 AI 智能体的深度审核。内容可能与当前课程知识库存在偏差，建议结合课程内容谨慎参考。',
  },
};

/* ===================================================================
 * 审核状态映射
 * =================================================================== */
export const REVIEW_STATUS_INFO: Record<string, {
  label: string;
  color: string;
  bg: string;
  icon: any;
  description: string;
}> = {
  passed: {
    label: '审核通过',
    color: 'text-green-600',
    bg: 'bg-green-50',
    icon: CheckCircle,
    description: '内容已通过审核，无重大问题',
  },
  warning: {
    label: '审核警告',
    color: 'text-amber-600',
    bg: 'bg-amber-50',
    icon: AlertTriangle,
    description: '内容存在一些需要注意的问题',
  },
  blocked: {
    label: '审核未通过',
    color: 'text-red-600',
    bg: 'bg-red-50',
    icon: X,
    description: '内容存在严重问题，需要修复',
  },
};

/* ===================================================================
 * 质检状态说明弹窗
 * =================================================================== */
export default function QualityStatusPopover({
  qualityStatus,
  reviewStatus,
  reviewIssues,
  reviewSuggestions,
}: {
  qualityStatus?: QualityStatus;
  reviewStatus?: ReviewStatus;
  reviewIssues?: ReviewIssue[];
  reviewSuggestions?: string[];
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  if (!qualityStatus && !reviewStatus) return null;

  const qcInfo = qualityStatus ? QUALITY_STATUS_INFO[qualityStatus] : null;

  return (
    <div ref={ref} className="relative inline-block">
      {/* 触发按钮 — 显示当前状态 */}
      <button
        onClick={() => setOpen(!open)}
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium border cursor-pointer transition-all hover:opacity-80 ${
          qcInfo ? `${qcInfo.bg} ${qcInfo.color} ${qcInfo.border}` : 'bg-gray-50 text-gray-500 border-gray-200'
        }`}
        title="点击查看质量说明"
        aria-label="查看质量状态说明"
      >
        {qcInfo && <qcInfo.icon className="w-3 h-3" />}
        {qcInfo?.label || qualityStatus || '未知'}
      </button>

      {/* 弹出面板 */}
      {open && (
        <div className="absolute z-50 mt-2 w-80 bg-white border border-gray-200 rounded-2xl shadow-xl animate-fade-in-up p-4 right-0">
          {/* 关闭按钮 */}
          <button
            onClick={() => setOpen(false)}
            className="absolute top-2 right-2 p-1 rounded-lg hover:bg-gray-100 text-gray-400"
            title="关闭"
          >
            <X className="w-3.5 h-3.5" />
          </button>

          {/* 质检状态说明 */}
          {qcInfo && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <qcInfo.icon className={`w-4 h-4 ${qcInfo.color}`} />
                <span className={`text-sm font-semibold ${qcInfo.color}`}>{qcInfo.label}</span>
              </div>
              <p className="text-xs text-gray-600 leading-relaxed">{qcInfo.details}</p>
            </div>
          )}

          {/* 审核状态 */}
          {reviewStatus && (
            <div className={`mt-3 pt-3 ${qcInfo ? 'border-t border-gray-100' : ''}`}>
              <div className="flex items-center gap-2 mb-2">
                <Shield className="w-3.5 h-3.5 text-gray-400" />
                <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">审核状态</span>
              </div>
              <ReviewStatusBadge status={reviewStatus} />
              {REVIEW_STATUS_INFO[reviewStatus] && (
                <p className="text-[11px] text-gray-500 mt-1">{REVIEW_STATUS_INFO[reviewStatus].description}</p>
              )}
            </div>
          )}

          {/* 审核问题列表 */}
          {reviewIssues && reviewIssues.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-100 space-y-2">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-3.5 h-3.5 text-gray-400" />
                <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                  发现问题（{reviewIssues.length}）
                </span>
              </div>
              <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
                {reviewIssues.map((issue, i) => (
                  <div
                    key={i}
                    className={`p-2 rounded-lg border text-[11px] ${
                      issue.severity === 'error' ? 'bg-red-50 border-red-100' :
                      issue.severity === 'warning' ? 'bg-amber-50 border-amber-100' :
                      'bg-blue-50 border-blue-100'
                    }`}
                  >
                    <div className="flex items-start gap-1.5">
                      <span className={`flex-shrink-0 mt-0.5 ${
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

          {/* 审核建议 */}
          {reviewSuggestions && reviewSuggestions.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <div className="flex items-center gap-2 mb-1.5">
                <Info className="w-3.5 h-3.5 text-gray-400" />
                <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">改进建议</span>
              </div>
              <ul className="space-y-1">
                {reviewSuggestions.map((suggestion, i) => (
                  <li key={i} className="text-[11px] text-gray-600 flex items-start gap-1.5">
                    <span className="text-brand-400 mt-0.5">•</span>
                    {suggestion}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 底部提示 */}
          <p className="text-[9px] text-gray-300 mt-3 pt-2 border-t border-gray-50">
            由 ReviewAgent 自动审核生成
          </p>
        </div>
      )}
    </div>
  );
}

/* ===================================================================
 * 审核状态标签（纯展示用）
 * =================================================================== */
export function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  const info = REVIEW_STATUS_INFO[status];
  if (!info) return null;
  const Icon = info.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium border ${info.bg} ${info.color}`}>
      <Icon className="w-3 h-3" />
      {info.label}
    </span>
  );
}

/* ===================================================================
 * Fallback 提示横幅
 * =================================================================== */
export function FallbackNotice({
  message = '此内容由系统规则生成，尚未经过 AI 智能体的深度分析和校验。内容可能与实际课程存在偏差，建议结合课程知识库参考使用。',
  subtle = false,
}: {
  message?: string;
  subtle?: boolean;
}) {
  if (subtle) {
    return (
      <div className="flex items-start gap-1.5 p-2 bg-slate-50/60 border border-slate-100 rounded-lg">
        <Shield className="w-3 h-3 text-slate-400 flex-shrink-0 mt-0.5" />
        <p className="text-[10px] text-slate-500 leading-relaxed">{message}</p>
      </div>
    );
  }

  return (
    <div className="p-3 bg-slate-50/80 border border-slate-200 rounded-xl flex items-start gap-2.5">
      <Shield className="w-4 h-4 text-slate-500 flex-shrink-0 mt-0.5" />
      <div>
        <p className="text-xs font-medium text-slate-700 mb-0.5">🛡️ 系统兜底内容</p>
        <p className="text-[10px] text-slate-500 leading-relaxed">{message}</p>
      </div>
    </div>
  );
}

/* ===================================================================
 * 低置信度提示横幅
 * =================================================================== */
export function LowConfidenceNotice({
  confidence,
  label = '画像维度',
}: {
  confidence: number;
  label?: string;
}) {
  if (confidence >= 0.5) return null;

  return (
    <div className="flex items-start gap-1.5 p-2 bg-amber-50/60 border border-dashed border-amber-200 rounded-lg">
      <Info className="w-3 h-3 text-amber-400 flex-shrink-0 mt-0.5" />
      <p className="text-[10px] text-amber-600 leading-relaxed">
        此{label}基于有限数据（置信度 {Math.round(confidence * 100)}%），
        随着更多学习行为的积累，画像精度将逐步提升。
      </p>
    </div>
  );
}
