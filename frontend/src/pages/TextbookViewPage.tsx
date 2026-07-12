import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, BookOpen, Loader2, ChevronRight, ChevronLeft } from 'lucide-react';
import { useSubjectStore } from '../store/subjectStore';
import { getTextbookTOC } from '../api/textbooks';
import TextbookViewer from '../components/learning/TextbookViewer';
import TextbookTocPanel from '../components/learning/TextbookTocPanel';
import type { TextbookTOC } from '../types/textbook';

/**
 * Standalone textbook browsing page.
 *
 * Route: /textbook/:subjectId
 *
 * Displays the full PDF textbook with a TOC sidebar for navigation.
 * Does NOT require a learning path — works directly from the resource library.
 */
export default function TextbookViewPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const nav = useNavigate();
  const activeSubject = useSubjectStore((s) => s.activeSubject);

  const [toc, setToc] = useState<TextbookTOC | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [currentSectionId, setCurrentSectionId] = useState<string | undefined>();
  const [showToc, setShowToc] = useState(true);

  // Determine the effective subject ID
  const effectiveSubjectId = subjectId || activeSubject?.id || '';

  // Load textbook TOC
  useEffect(() => {
    if (!effectiveSubjectId) {
      setLoading(false);
      setError('未找到科目');
      return;
    }

    setLoading(true);
    setError('');

    getTextbookTOC(effectiveSubjectId)
      .then((data) => {
        if (!data || !data.chapters || data.chapters.length === 0) {
          setError('教材目录为空，请等待教材解析完成');
        } else {
          setToc(data);
          // Start at first section of first chapter
          const firstChapter = data.chapters[0];
          const firstSecStart = firstChapter?.sections?.[0]?.startPage;
          const page = firstSecStart && firstSecStart > 0 ? firstSecStart : (firstChapter?.startPage && firstChapter.startPage > 0 ? firstChapter.startPage : 1);
          setCurrentPage(page);
          setCurrentSectionId(firstChapter?.sections?.[0]?.sectionId);
        }
      })
      .catch((err) => {
        setError(err?.message || '加载教材失败');
      })
      .finally(() => setLoading(false));
  }, [effectiveSubjectId]);

  const handleSectionClick = useCallback(
    (_chapterId: string, sectionId: string, pageStart: number) => {
      const page = pageStart > 0 ? pageStart : 1;
      setCurrentPage(page);
      setCurrentSectionId(sectionId);
    },
    [],
  );

  const textbook = toc?.textbook;
  // Use DB pageCount, but fall back to the max page from TOC if DB value is missing
  const maxTocPage = toc?.chapters?.reduce((max, ch) => {
    const chEnd = ch.endPage ?? 0;
    const secMax = ch.sections?.reduce((m, s) => Math.max(m, s.endPage ?? 0), 0) ?? 0;
    return Math.max(max, chEnd, secMax);
  }, 0) ?? 0;
  const pageCount = textbook?.pageCount || maxTocPage || 1;

  // ── Loading state ──
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-50">
        <div className="text-center">
          <Loader2 size={32} className="text-blue-500 animate-spin mx-auto mb-3" />
          <p className="text-sm text-surface-500">加载教材中…</p>
        </div>
      </div>
    );
  }

  // ── Error / empty state ──
  if (error || !toc) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-50">
        <div className="text-center max-w-sm">
          <BookOpen size={40} className="text-surface-300 mx-auto mb-3" />
          <p className="text-base font-medium text-surface-600 mb-1">
            {error || '教材不可用'}
          </p>
          <p className="text-sm text-surface-400 mb-4">
            {textbook?.status === 'processing' || textbook?.status === 'uploading'
              ? '教材正在解析中，请稍后再试'
              : textbook?.status === 'error'
                ? `教材解析失败：${textbook.parseError || '未知错误'}`
                : '请先为科目上传教材'}
          </p>
          <button
            onClick={() => nav(-1)}
            className="px-4 py-2 bg-surface-100 text-surface-600 rounded-xl text-sm hover:bg-surface-200 transition-colors"
          >
            返回
          </button>
        </div>
      </div>
    );
  }

  // ── Textbook view ──
  return (
    <div className="h-screen flex flex-col bg-surface-50">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 bg-white border-b border-surface-200 flex-shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => nav(-1)}
            className="p-1.5 rounded-lg hover:bg-surface-100 transition-colors"
            title="返回"
          >
            <ArrowLeft size={18} className="text-surface-500" />
          </button>
          <div>
            <h1 className="text-sm font-semibold text-surface-800">
              {textbook?.title || textbook?.filename || '教材浏览'}
            </h1>
            {textbook?.author && (
              <p className="text-xs text-surface-400">{textbook.author}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs text-surface-500">
          <span>{pageCount} 页</span>
          <span className="text-surface-300">|</span>
          <span>{(toc.chapters?.length ?? 0)} 章</span>
          <button
            onClick={() => setShowToc(!showToc)}
            className={`ml-2 p-1.5 rounded-lg transition-colors ${
              showToc ? 'bg-blue-100 text-blue-600' : 'hover:bg-surface-100 text-surface-500'
            }`}
            title={showToc ? '隐藏目录' : '显示目录'}
          >
            {showToc ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>
      </div>

      {/* Main content: PDF viewer + optional TOC sidebar */}
      <div className="flex-1 flex min-h-0">
        {/* PDF viewer — renders all pages with lazy image loading */}
        <div className="flex-1 min-w-0">
          <TextbookViewer
            subjectId={effectiveSubjectId}
            pageStart={1}
            pageEnd={pageCount || 1}
            initialScrollPage={currentPage}
            jumpToPage={currentPage}
          />
        </div>

        {/* TOC sidebar */}
        {showToc && (
          <div className="w-64 lg:w-72 bg-white border-l border-surface-200 flex-shrink-0 overflow-hidden">
            <TextbookTocPanel
              chapters={toc.chapters}
              currentSectionId={currentSectionId}
              currentPageStart={currentPage}
              onSectionClick={handleSectionClick}
            />
          </div>
        )}
      </div>
    </div>
  );
}
