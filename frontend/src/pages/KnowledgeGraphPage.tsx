/** Knowledge Graph Page — full-page interactive force-directed graph of knowledge points. */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Network, Loader2, AlertCircle, LayoutGrid, ArrowLeftRight, Circle } from 'lucide-react';
import { KGGraph, KGNodeCard, KGDetailPanel, KGSearch, KGFilter } from '../components/kg';
import type { LayoutType } from '../components/kg';
import type { KGNodeStatusFilter } from '../components/kg';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import { getKnowledgeGraph, getNodeDetail } from '../api/knowledgeGraph';
import type { KnowledgeGraphData, KGNode, KGNodeDetail } from '../types/knowledgeGraph';

const LAYOUT_OPTIONS: Array<{ value: LayoutType; label: string; icon: React.ReactNode }> = [
  { value: 'force', label: '力导向', icon: <Network size={14} /> },
  { value: 'dagre', label: '层级', icon: <ArrowLeftRight size={14} /> },
  { value: 'circular', label: '环形', icon: <Circle size={14} /> },
];

export default function KnowledgeGraphPage() {
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionId = useChatStore((s) => s.currentSessionId);
  const activeSubject = useSubjectStore((s) => s.activeSubject);
  const initialNodeId = searchParams.get('nodeId');

  // ── Data ──
  const [graphData, setGraphData] = useState<KnowledgeGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── Interaction state ──
  const [layoutType, setLayoutType] = useState<LayoutType>('force');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStatuses, setSelectedStatuses] = useState<KGNodeStatusFilter[]>([]);
  const [selectedChapter, setSelectedChapter] = useState('');
  const [selectedNode, setSelectedNode] = useState<KGNode | null>(null);
  const [selectedNodeDetail, setSelectedNodeDetail] = useState<KGNodeDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showDetailPanel, setShowDetailPanel] = useState(false);

  // ── Fetch graph data ──
  const fetchGraph = useCallback(async (chapter?: string) => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const params: { sessionId: string; subjectId?: string; chapter?: string } = { sessionId };
      if (activeSubject) params.subjectId = activeSubject;
      if (chapter) params.chapter = chapter;
      const data = await getKnowledgeGraph(params);
      setGraphData(data);
    } catch (err) {
      setError('加载知识图谱失败，请稍后重试');
      console.error('[KG] Failed to load graph:', err);
    } finally {
      setLoading(false);
    }
  }, [sessionId, activeSubject]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  // ── Initial nodeId handling ──
  useEffect(() => {
    if (initialNodeId && graphData) {
      const node = graphData.nodes.find((n) => n.id === initialNodeId);
      if (node) {
        setSelectedNode(node);
        handleExpandDetail(node.id);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialNodeId, graphData]);

  // ── Chapter change → refetch ──
  const handleChapterChange = useCallback((chapter: string) => {
    setSelectedChapter(chapter);
    setSelectedNode(null);
    setSelectedNodeDetail(null);
    setShowDetailPanel(false);
    fetchGraph(chapter || undefined);
  }, [fetchGraph]);

  // ── Filtered nodes (for graph display) ──
  const filteredNodes = useMemo(() => {
    if (!graphData) return [];
    let nodes = graphData.nodes;
    if (selectedStatuses.length > 0) {
      nodes = nodes.filter((n) => selectedStatuses.includes(n.status));
    }
    return nodes;
  }, [graphData, selectedStatuses]);

  const filteredNodeIds = useMemo(() => new Set(filteredNodes.map((n) => n.id)), [filteredNodes]);

  const filteredEdges = useMemo(() => {
    if (!graphData) return [];
    return graphData.edges.filter(
      (e) => filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target),
    );
  }, [graphData, filteredNodeIds]);

  // ── Search ──
  const handleSearch = useCallback((term: string) => {
    setSearchTerm(term);
    if (!term) {
      setSelectedNode(null);
    }
  }, []);

  // ── Node click (floating card) ──
  const handleNodeClick = useCallback((node: KGNode | null) => {
    setSelectedNode(node);
    if (!node) {
      setShowDetailPanel(false);
    }
  }, []);

  // ── Expand detail ──
  const handleExpandDetail = useCallback(async (nodeId: string) => {
    if (!sessionId) return;
    setShowDetailPanel(true);
    setDetailLoading(true);
    try {
      const params: { sessionId: string; subjectId?: string } = { sessionId };
      if (activeSubject) params.subjectId = activeSubject;
      const detail = await getNodeDetail(nodeId, params);
      setSelectedNodeDetail(detail);
    } catch (err) {
      console.error('[KG] Failed to load node detail:', err);
    } finally {
      setDetailLoading(false);
    }
  }, [sessionId, activeSubject]);

  // ── Click "去学习" ──
  const handleLearn = useCallback((nodeId: string) => {
    nav(`/resources?taskId=${encodeURIComponent(nodeId)}`);
  }, [nav]);

  // ── Close detail panel ──
  const handleCloseDetail = useCallback(() => {
    setShowDetailPanel(false);
    setSelectedNodeDetail(null);
  }, []);

  // ── Render states ──
  if (!sessionId) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px] text-surface-500">
        <p className="text-sm">请先开始一个学习会话</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={28} className="animate-spin text-primary-500" />
          <p className="text-sm text-surface-500">加载知识图谱...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <AlertCircle size={28} className="text-error-500" />
          <p className="text-sm text-surface-600">{error}</p>
          <button
            onClick={() => fetchGraph()}
            className="px-4 py-2 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 transition-colors"
          >
            重新加载
          </button>
        </div>
      </div>
    );
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <Network size={36} className="text-surface-300" />
          <p className="text-sm text-surface-500">暂无知识图谱数据</p>
          <p className="text-xs text-surface-400">完成学习路径生成后即可查看</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* ── Header bar ── */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-surface-200 bg-white">
        <div className="flex items-center justify-between flex-wrap gap-3">
          {/* Left: title + search */}
          <div className="flex items-center gap-4 flex-1 min-w-0">
            <h1 className="text-lg font-display font-semibold text-surface-800 whitespace-nowrap">
              知识图谱
            </h1>
            <KGSearch value={searchTerm} onChange={handleSearch} />
          </div>

          {/* Right: layout switcher + filter */}
          <div className="flex items-center gap-3">
            {/* Layout switcher */}
            <div className="flex items-center gap-0.5 bg-surface-100 rounded-xl p-0.5">
              {LAYOUT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setLayoutType(opt.value)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    layoutType === opt.value
                      ? 'bg-white text-primary-700 shadow-sm'
                      : 'text-surface-500 hover:text-surface-700'
                  }`}
                >
                  {opt.icon}
                  {opt.label}
                </button>
              ))}
            </div>

            {/* Filter */}
            <KGFilter
              selectedStatuses={selectedStatuses}
              onStatusChange={setSelectedStatuses}
              chapters={graphData.meta.chapters}
              selectedChapter={selectedChapter}
              onChapterChange={handleChapterChange}
            />
          </div>
        </div>

        {/* Stats bar */}
        <div className="flex items-center gap-4 mt-2 text-[11px] text-surface-400">
          <span>{filteredNodes.length} 个知识点</span>
          <span>{filteredEdges.length} 条关系</span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-success-500 inline-block" />
            已掌握 {graphData.meta.masteredCount}
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-primary-500 inline-block" />
            进行中 {graphData.nodes.filter((n) => n.status === 'in_progress').length}
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-surface-300 inline-block" />
            未学习 {graphData.nodes.filter((n) => n.status === 'not_started').length}
          </span>
        </div>
      </div>

      {/* ── Graph area ── */}
      <div className="flex-1 flex overflow-hidden relative">
        <div className="flex-1 relative">
          <KGGraph
            nodes={filteredNodes}
            edges={filteredEdges}
            layoutType={layoutType}
            selectedNodeId={selectedNode?.id || null}
            onNodeClick={handleNodeClick}
            searchTerm={searchTerm}
            filterStatus={selectedStatuses}
            filterChapter={selectedChapter}
          />

          {/* Floating node card */}
          {selectedNode && !showDetailPanel && (
            <div className="absolute left-6 bottom-6" style={{ pointerEvents: 'none' }}>
              <KGNodeCard
                node={selectedNode}
                onClose={() => setSelectedNode(null)}
                onLearn={handleLearn}
                onExpand={handleExpandDetail}
              />
            </div>
          )}
        </div>

        {/* Right detail panel */}
        {showDetailPanel && (
          <KGDetailPanel
            detail={selectedNodeDetail}
            loading={detailLoading}
            onClose={handleCloseDetail}
          />
        )}
      </div>
    </div>
  );
}
