/** Expandable detail panel for a knowledge node — shows resources, sections, prerequisites. */
import { BookOpen, ChevronRight, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { KGNodeDetail } from '../../types/knowledgeGraph';

interface KGDetailPanelProps {
  detail: KGNodeDetail | null;
  loading: boolean;
  onClose: () => void;
}

const DIFFICULTY_LABELS: Record<string, string> = {
  easy: '简单',
  medium: '中等',
  hard: '困难',
  challenge: '挑战',
};

const STATUS_LABELS: Record<string, string> = {
  not_started: '未学习',
  in_progress: '进行中',
  mastered: '已掌握',
  needs_review: '需复习',
};

export default function KGDetailPanel({ detail, loading, onClose }: KGDetailPanelProps) {
  const nav = useNavigate();

  if (loading) {
    return (
      <div className="w-80 border-l border-surface-200 bg-white h-full flex items-center justify-center">
        <div className="animate-spin w-5 h-5 border-2 border-primary-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!detail) return null;

  const masteryColor =
    detail.mastery >= 80
      ? 'bg-success-500'
      : detail.mastery >= 40
        ? 'bg-primary-500'
        : 'bg-surface-300';

  return (
    <div className="w-80 border-l border-surface-200 bg-white h-full overflow-y-auto flex-shrink-0">
      {/* Header */}
      <div className="sticky top-0 bg-white border-b border-surface-100 px-5 py-4 flex items-start justify-between z-10">
        <div className="min-w-0 flex-1 pr-2">
          <h3 className="text-sm font-semibold text-surface-800 truncate">{detail.label}</h3>
          {detail.description && (
            <p className="text-xs text-surface-500 mt-1 leading-relaxed line-clamp-3">
              {detail.description}
            </p>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-md hover:bg-surface-100 text-surface-400 transition-colors flex-shrink-0"
        >
          <X size={16} />
        </button>
      </div>

      <div className="px-5 py-4 space-y-5">
        {/* Mastery */}
        <Section title="掌握进度">
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <span className="text-xs text-surface-500">完成度</span>
            <span className="text-xs font-medium text-surface-600 tabular-nums">{detail.mastery}%</span>
          </div>
          <div className="w-full h-2 bg-surface-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${masteryColor}`}
              style={{ width: `${detail.mastery}%` }}
            />
          </div>
          <div className="flex items-center gap-2 mt-2 text-[11px] text-surface-500">
            <span className="px-2 py-0.5 rounded bg-surface-100">{STATUS_LABELS[detail.status] || detail.status}</span>
            <span className="px-2 py-0.5 rounded bg-surface-100">{DIFFICULTY_LABELS[detail.difficulty] || detail.difficulty}</span>
            <span>重要性 {'★'.repeat(detail.importance)}</span>
          </div>
        </Section>

        {/* Linked Sections */}
        {detail.linkedSections.length > 0 && (
          <Section title="关联章节">
            <ul className="space-y-1.5">
              {detail.linkedSections.map((sec) => (
                <li key={sec.id}>
                  <button
                    onClick={() => nav(`/lecture/section/${sec.id}`)}
                    className="w-full text-left flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-surface-50 transition-colors group"
                  >
                    <BookOpen size={14} className="text-surface-400 flex-shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs text-surface-700 truncate group-hover:text-primary-600 transition-colors">
                        {sec.title}
                      </p>
                      <p className="text-[10px] text-surface-400 truncate">{sec.chapterTitle}</p>
                    </div>
                    <ChevronRight size={12} className="text-surface-300 flex-shrink-0" />
                  </button>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Linked Resources */}
        {detail.resources.length > 0 && (
          <Section title={`关联资源 (${detail.resources.length})`}>
            <ul className="space-y-1.5">
              {detail.resources.slice(0, 8).map((r) => (
                <li key={r.id}>
                  <button
                    onClick={() => nav(`/resources?id=${r.id}`)}
                    className="w-full text-left flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-surface-50 transition-colors group"
                  >
                    <div className="w-1.5 h-1.5 rounded-full flex-shrink-0 mt-0.5" style={{
                      backgroundColor: r.studyStatus === 'completed' ? '#22c55e' : '#94a3b8',
                    }} />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs text-surface-700 truncate group-hover:text-primary-600 transition-colors">
                        {r.title}
                      </p>
                      <p className="text-[10px] text-surface-400">{r.type}</p>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Prerequisites */}
        {detail.prerequisites.length > 0 && (
          <Section title="前置知识">
            <div className="flex flex-wrap gap-1.5">
              {detail.prerequisites.map((p) => (
                <button
                  key={p.id}
                  onClick={() => nav(`/kg?nodeId=${p.id}`)}
                  className="px-2.5 py-1 rounded-lg bg-surface-100 text-surface-600 text-[11px] font-medium hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  {p.label}
                </button>
              ))}
            </div>
          </Section>
        )}

        {/* Dependents */}
        {detail.dependents.length > 0 && (
          <Section title="后续知识">
            <div className="flex flex-wrap gap-1.5">
              {detail.dependents.map((d) => (
                <button
                  key={d.id}
                  onClick={() => nav(`/kg?nodeId=${d.id}`)}
                  className="px-2.5 py-1 rounded-lg bg-accent-50 text-accent-700 text-[11px] font-medium hover:bg-accent-100 transition-colors"
                >
                  {d.label}
                </button>
              ))}
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}

// ── Section wrapper ──

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-[11px] font-semibold text-surface-400 uppercase tracking-wider mb-2">{title}</h4>
      {children}
    </div>
  );
}
