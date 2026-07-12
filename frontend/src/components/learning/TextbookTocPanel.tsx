import { useState, useMemo } from 'react';
import { ChevronDown, ChevronRight, BookOpen, FileText } from 'lucide-react';
import type { TextbookChapter, TextbookSection } from '../../types/textbook';

interface Props {
  chapters: TextbookChapter[];
  currentSectionId?: string;
  currentPageStart?: number;
  onSectionClick: (chapterId: string, sectionId: string, pageStart: number) => void;
}

/**
 * Textbook table of contents panel — renders the chapter/section tree
 * from the textbook's chapters_json structure.

 * Used in the LecturePage right sidebar as a "教材目录" tab.
 */
export default function TextbookTocPanel({
  chapters,
  currentSectionId,
  currentPageStart,
  onSectionClick,
}: Props) {
  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(() => {
    // Auto-expand the chapter containing the current section
    if (currentSectionId && chapters.length > 0) {
      const parent = chapters.find((ch) =>
        ch.sections.some((sec) => sec.sectionId === currentSectionId),
      );
      if (parent) return new Set([parent.chapterId]);
    }
    // Default: expand first chapter
    return chapters.length > 0 ? new Set([chapters[0].chapterId]) : new Set();
  });

  const toggleChapter = (chapterId: string) => {
    setExpandedChapters((prev) => {
      const next = new Set(prev);
      if (next.has(chapterId)) next.delete(chapterId);
      else next.add(chapterId);
      return next;
    });
  };

  if (!chapters || chapters.length === 0) {
    return (
      <div className="p-4 text-center text-xs text-surface-400">
        <BookOpen size={24} className="mx-auto mb-2 text-surface-300" />
        <p>教材目录加载中…</p>
        <p className="mt-1 text-[10px]">教材解析完成后即可查看目录</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-2 border-b border-surface-100 flex-shrink-0">
        <div className="flex items-center gap-1.5">
          <BookOpen size={12} className="text-blue-500" />
          <span className="text-[10px] font-semibold text-surface-600 uppercase tracking-wide">
            教材目录
          </span>
          <span className="text-[10px] text-surface-400">
            ({chapters.length} 章)
          </span>
        </div>
      </div>

      {/* Chapter list */}
      <div className="flex-1 overflow-y-auto">
        {chapters.map((ch) => {
          const isExpanded = expandedChapters.has(ch.chapterId);
          const sectionCount = ch.sections?.length ?? 0;
          const hasCurrentSection = ch.sections.some(
            (sec) => sec.sectionId === currentSectionId,
          );

          return (
            <div key={ch.chapterId}>
              {/* Chapter header */}
              <button
                onClick={() => toggleChapter(ch.chapterId)}
                className={`w-full flex items-center gap-1.5 px-3 py-2 text-left transition-colors hover:bg-surface-50 ${
                  hasCurrentSection ? 'bg-blue-50/50' : ''
                }`}
              >
                <span className="flex-shrink-0 text-surface-400">
                  {isExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                </span>
                <span
                  className={`text-[11px] font-medium truncate flex-1 ${
                    hasCurrentSection ? 'text-blue-700' : 'text-surface-700'
                  }`}
                >
                  {ch.title}
                </span>
                <span className="text-[10px] text-surface-400 flex-shrink-0">
                  {ch.startPage > 0 && ch.endPage > 0 && ch.startPage !== ch.endPage
                    ? `${ch.startPage}-${ch.endPage}页`
                    : ch.startPage > 0
                      ? `${ch.startPage}页起`
                      : ''}
                </span>
              </button>

              {/* Section list (expandable) */}
              {isExpanded && (
                <div className="border-l-2 border-surface-100 ml-4">
                  {ch.sections.map((sec) => {
                    const isCurrent = sec.sectionId === currentSectionId;
                    return (
                      <button
                        key={sec.sectionId}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSectionClick(ch.chapterId, sec.sectionId, sec.startPage);
                        }}
                        className={`w-full flex items-center gap-1.5 pl-4 pr-2 py-1.5 text-left transition-colors hover:bg-surface-50 ${
                          isCurrent
                            ? 'bg-blue-100/60 border-r-2 border-blue-500'
                            : ''
                        }`}
                      >
                        <FileText
                          size={10}
                          className={`flex-shrink-0 ${
                            isCurrent ? 'text-blue-500' : 'text-surface-400'
                          }`}
                        />
                        <span
                          className={`text-[10px] truncate flex-1 ${
                            isCurrent
                              ? 'text-blue-700 font-medium'
                              : 'text-surface-600'
                          }`}
                        >
                          {sec.title}
                        </span>
                        <span className="text-[9px] text-surface-400 flex-shrink-0">
                          {sec.startPage > 0 ? `第${sec.startPage}页` : ''}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
