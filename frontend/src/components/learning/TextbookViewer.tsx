import { useEffect, useRef, useState, useCallback, useLayoutEffect } from 'react';
import { ChevronUp, ChevronDown, ZoomIn, ZoomOut, Loader2 } from 'lucide-react';
import client from '../../api/client';

interface Props {
  subjectId: string;
  pageStart: number;
  pageEnd: number;
  /** Page to scroll to on initial load (defaults to pageStart) */
  initialScrollPage?: number;
  /** When this changes, the viewer scrolls to this page (used for TOC navigation) */
  jumpToPage?: number;
  className?: string;
}

/** Estimated page height at zoom 1.0 for min-height placeholder (A4 ratio). */
const BASE_PAGE_WIDTH = 400;
const PAGE_ASPECT_RATIO = 1.35;

/**
 * Fetches a single PDF page image via Axios (with auth headers).
 * Only starts loading when the placeholder nears the viewport.
 */
function PageImage({ subjectId, pageNum, zoom, onLoad, onError }: {
  subjectId: string;
  pageNum: number;
  zoom: number;
  onLoad: () => void;
  onError: () => void;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [shouldLoad, setShouldLoad] = useState(false);
  const placeholderRef = useRef<HTMLDivElement>(null);

  // Lazy-load: only fetch when within 800px of the viewport
  useEffect(() => {
    const el = placeholderRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShouldLoad(true);
          observer.disconnect();
        }
      },
      { rootMargin: '800px 0px 800px 0px' },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!shouldLoad) return;
    let objectUrl: string | null = null;
    let cancelled = false;

    client
      .get(`/api/textbooks/${encodeURIComponent(subjectId)}/pages/${pageNum}`, {
        params: { zoom },
        responseType: 'blob',
      })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setSrc(objectUrl);
        onLoad();
      })
      .catch(() => {
        if (cancelled) return;
        setFailed(true);
        onError();
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [shouldLoad, subjectId, pageNum, zoom]);

  const ph = Math.round(BASE_PAGE_WIDTH * PAGE_ASPECT_RATIO * zoom);

  return (
    <div ref={placeholderRef} className="relative w-full" style={{ minHeight: `${ph}px` }}>
      {failed ? (
        <div className="absolute inset-0 flex items-center justify-center bg-surface-50">
          <span className="text-xs text-surface-400">加载失败</span>
        </div>
      ) : src ? (
        <img src={src} alt={`Page ${pageNum}`} className="w-full" />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center bg-surface-50">
          <Loader2 size={24} className="text-surface-300 animate-spin" />
        </div>
      )}
    </div>
  );
}

/**
 * PDF textbook page-by-page viewer.
 *
 * - Lazy-loads page images: only fetches when within 800px of the viewport.
 * - Uses CSS min-height placeholders to prevent layout shifts on image load.
 * - Supports zoom, page navigation, and external jump-to-page via TOC.
 */
export default function TextbookViewer({ subjectId, pageStart, pageEnd, initialScrollPage, jumpToPage, className = '' }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const pageElements = useRef<Map<number, HTMLElement>>(new Map());
  const [zoom, setZoom] = useState(1.5);
  const [loadedPages, setLoadedPages] = useState<Set<number>>(new Set());
  const [errorPages, setErrorPages] = useState<Set<number>>(new Set());
  const [currentPage, setCurrentPage] = useState(pageStart);
  const pendingJumpRef = useRef<number | null>(null);

  const pageCount = Math.max(1, pageEnd - pageStart + 1);
  const pages = Array.from({ length: pageCount }, (_, i) => pageStart + i);

  // ── IntersectionObserver: track which page is currently visible ─────
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && entry.intersectionRatio >= 0.4) {
            const pageNum = Number(entry.target.getAttribute('data-page'));
            if (!isNaN(pageNum)) setCurrentPage(pageNum);
          }
        }
      },
      { root: containerRef.current, threshold: 0.4 },
    );

    const current = pageRefs.current;
    current.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [pages, loadedPages]);

  // ── Initial scroll ──────────────────────────────────────────────────
  const scrollTarget = initialScrollPage ?? pageStart;
  useEffect(() => {
    // Use a small delay so the DOM layout is settled
    const timer = setTimeout(() => {
      const el = pageRefs.current.get(scrollTarget);
      if (el) {
        el.scrollIntoView({ behavior: 'instant', block: 'start' });
      }
    }, 150);
    return () => clearTimeout(timer);
  }, [scrollTarget, subjectId]);

  // ── TOC jump-to-page ────────────────────────────────────────────────
  const jumpTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (jumpToPage == null || jumpToPage < 1) return;

    const target = jumpToPage;
    let retries = 0;
    const maxRetries = 15;

    const tryScroll = () => {
      // Look up the page element
      const refEl = pageRefs.current.get(target);
      const queryEl = containerRef.current?.querySelector(`[data-page="${target}"]`) as HTMLElement | null;
      const el: HTMLElement | null = refEl ?? queryEl ?? null;

      if (el && containerRef.current) {
        const containerTop = containerRef.current.getBoundingClientRect().top;
        const elTop = el.getBoundingClientRect().top;
        const scrollOffset = elTop - containerTop + containerRef.current.scrollTop;
        containerRef.current.scrollTo({ top: scrollOffset - 8, behavior: 'smooth' });
        setCurrentPage(target);
      } else if (retries < maxRetries) {
        retries++;
        jumpTimerRef.current = setTimeout(tryScroll, 150);
      }
    };

    jumpTimerRef.current = setTimeout(tryScroll, 80);

    return () => {
      if (jumpTimerRef.current) clearTimeout(jumpTimerRef.current);
    };
  }, [jumpToPage]);

  const doScrollToPage = useCallback((page: number) => {
    const el = pageRefs.current.get(page);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setCurrentPage(page);
    }
  }, []);

  const handlePrevPage = () => {
    if (currentPage > pageStart) doScrollToPage(currentPage - 1);
  };
  const handleNextPage = () => {
    if (currentPage < pageEnd) doScrollToPage(currentPage + 1);
  };

  // ── Render ──────────────────────────────────────────────────────────
  const ph = Math.round(BASE_PAGE_WIDTH * PAGE_ASPECT_RATIO * zoom);

  return (
    <div className={`flex flex-col h-full ${className}`}>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-surface-50 border-b border-surface-200 flex-shrink-0">
        <div className="flex items-center gap-2 text-xs text-surface-500">
          <span>第 {currentPage} / {pageEnd} 页</span>
          <span className="text-surface-300">|</span>
          <span>{pageStart}-{pageEnd}（共 {pageCount} 页）</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))} disabled={zoom <= 0.5}
            className="p-1.5 rounded hover:bg-surface-200 disabled:opacity-30 transition-colors" title="缩小">
            <ZoomOut size={14} className="text-surface-500" />
          </button>
          <span className="text-[10px] text-surface-400 w-10 text-center">{Math.round(zoom * 100)}%</span>
          <button onClick={() => setZoom((z) => Math.min(4, z + 0.25))} disabled={zoom >= 4}
            className="p-1.5 rounded hover:bg-surface-200 disabled:opacity-30 transition-colors" title="放大">
            <ZoomIn size={14} className="text-surface-500" />
          </button>
          <span className="text-surface-300 mx-1">|</span>
          <button onClick={handlePrevPage} disabled={currentPage <= pageStart}
            className="p-1.5 rounded hover:bg-surface-200 disabled:opacity-30 transition-colors" title="上一页">
            <ChevronUp size={14} className="text-surface-500" />
          </button>
          <button onClick={handleNextPage} disabled={currentPage >= pageEnd}
            className="p-1.5 rounded hover:bg-surface-200 disabled:opacity-30 transition-colors" title="下一页">
            <ChevronDown size={14} className="text-surface-500" />
          </button>
        </div>
      </div>

      {/* Page container — each page card uses min-height as a stable placeholder */}
      <div ref={containerRef} className="flex-1 overflow-y-auto bg-surface-100">
        <div className="flex flex-col items-center py-4 gap-3">
          {pages.map((pageNum) => (
            <div
              key={`${subjectId}-p${pageNum}`}
              ref={(el) => {
                if (el) pageRefs.current.set(pageNum, el);
              }}
              data-page={pageNum}
              className="relative bg-white rounded-lg shadow-md overflow-hidden"
              style={{ width: `${zoom * BASE_PAGE_WIDTH}px`, minHeight: `${ph}px` }}
            >
              <div className="absolute top-2 right-2 z-10 px-2 py-0.5 rounded-full bg-black/40 text-white text-[10px] font-medium">
                {pageNum}
              </div>

              <PageImage
                subjectId={subjectId}
                pageNum={pageNum}
                zoom={zoom}
                onLoad={() => setLoadedPages((prev) => new Set(prev).add(pageNum))}
                onError={() => setErrorPages((prev) => new Set(prev).add(pageNum))}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
