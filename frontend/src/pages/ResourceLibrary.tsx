import { useState } from 'react';
import { Search, Filter, BookOpen, Brain, Code, FileText, Lightbulb, Play, Presentation, Clock, Star, ChevronRight } from 'lucide-react';
import { useResources } from '../hooks/useResources';
import type { Resource } from '../types/resource';
import type { ResourceType } from '../types/chat';
import { RESOURCE_TYPE_LABELS } from '../utils/constants';
import { timeAgo, formatDuration } from '../utils/format';
import Loading from '../components/common/Loading';
import EmptyState from '../components/common/EmptyState';
import Modal from '../components/common/Modal';

const iconMap: Record<ResourceType, React.ReactNode> = {
  lecture: <BookOpen className="w-5 h-5 text-blue-500" />,
  mindmap: <Brain className="w-5 h-5 text-purple-500" />,
  quiz: <FileText className="w-5 h-5 text-amber-500" />,
  reading: <Lightbulb className="w-5 h-5 text-green-500" />,
  case_study: <Code className="w-5 h-5 text-cyan-500" />,
  video: <Play className="w-5 h-5 text-red-500" />,
  ppt: <Presentation className="w-5 h-5 text-orange-500" />,
};

const difficultyBadge: Record<string, string> = {
  easy: 'bg-green-50 text-green-600 border-green-200',
  medium: 'bg-amber-50 text-amber-600 border-amber-200',
  hard: 'bg-red-50 text-red-600 border-red-200',
};

const difficultyLabel: Record<string, string> = { easy: '基础', medium: '进阶', hard: '挑战' };

/* ===================================================================
 * 子组件
 * =================================================================== */

function ResourceCard({ resource, onClick }: { resource: Resource; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="group bg-white border border-gray-100 rounded-2xl p-5 text-left hover:shadow-lg hover:-translate-y-1 transition-all duration-300 w-full"
    >
      <div className="flex items-start gap-3 mb-3">
        <div className="w-10 h-10 rounded-xl bg-gray-50 flex items-center justify-center flex-shrink-0">
          {iconMap[resource.type]}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-gray-900 truncate">{resource.title}</h3>
          <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{resource.description}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${difficultyBadge[resource.difficulty]}`}>
          {difficultyLabel[resource.difficulty]}
        </span>
        <span className="px-2 py-0.5 rounded-md text-[10px] text-gray-500 bg-gray-50 border border-gray-100">
          {RESOURCE_TYPE_LABELS[resource.type]}
        </span>
        {resource.tags.slice(0, 3).map((tag) => (
          <span key={tag} className="px-2 py-0.5 rounded-md text-[10px] text-gray-400 bg-gray-50">
            {tag}
          </span>
        ))}
      </div>

      <div className="flex items-center justify-between text-[10px] text-gray-400">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{formatDuration(resource.estimatedMinutes)}</span>
        </div>
        <div className="flex items-center gap-1 text-brand-500 group-hover:translate-x-0.5 transition-transform">
          <span>查看详情</span>
          <ChevronRight className="w-3 h-3" />
        </div>
      </div>
    </button>
  );
}

/* ===================================================================
 * 筛选栏
 * =================================================================== */

function FilterBar({ onFilter }: { onFilter: (type: ResourceType | undefined) => void }) {
  const [active, setActive] = useState<ResourceType | undefined>();
  const types: (ResourceType | undefined)[] = [undefined, 'lecture', 'mindmap', 'quiz', 'reading', 'case_study'];

  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-2">
      <Filter className="w-4 h-4 text-gray-400 flex-shrink-0" />
      {types.map((t) => (
        <button
          key={t || 'all'}
          onClick={() => { setActive(t); onFilter(t); }}
          className={`px-3 py-1.5 rounded-xl text-xs font-medium whitespace-nowrap transition-all ${
            active === t
              ? 'bg-gray-900 text-white'
              : 'bg-white border border-gray-200 text-gray-500 hover:border-gray-300'
          }`}
        >
          {t ? RESOURCE_TYPE_LABELS[t] : '全部'}
        </button>
      ))}
    </div>
  );
}

/* ===================================================================
 * 主页面
 * =================================================================== */

export default function ResourceLibrary() {
  const { resources, total, loading, applyFilter } = useResources();
  const [selected, setSelected] = useState<Resource | null>(null);
  const [search, setSearch] = useState('');

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 md:py-8">
      {/* 头部 */}
      <div className="mb-6">
        <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-1">资源库</h1>
        <p className="text-sm text-gray-500">共 {total} 个学习资源，由 AI 智能体为你个性化生成</p>
      </div>

      {/* 搜索 + 筛选 */}
      <div className="space-y-4 mb-6">
        <div className="relative max-w-md">
          <Search className="w-4 h-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); applyFilter({ search: e.target.value }); }}
            placeholder="搜索资源..."
            className="w-full h-10 pl-10 pr-4 bg-white border border-gray-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <FilterBar onFilter={(type) => applyFilter({ type })} />
      </div>

      {/* 列表 */}
      {loading ? (
        <Loading text="加载资源中..." />
      ) : !resources || resources.length === 0 ? (
        <EmptyState
          icon={<BookOpen className="w-8 h-8" />}
          title="暂无资源"
          description="开始对话后，AI 智能体将为你生成个性化学习资源"
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {resources.map((r) => (
            <ResourceCard key={r.id} resource={r} onClick={() => setSelected(r)} />
          ))}
        </div>
      )}

      {/* 资源详情弹窗 */}
      <Modal open={!!selected} onClose={() => setSelected(null)} title={selected?.title} wide>
        {selected && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${difficultyBadge[selected.difficulty]}`}>
                {difficultyLabel[selected.difficulty]}
              </span>
              <span className="px-2.5 py-1 rounded-lg text-xs text-gray-500 bg-gray-50">
                {RESOURCE_TYPE_LABELS[selected.type]}
              </span>
              <span className="text-xs text-gray-400">· {formatDuration(selected.estimatedMinutes)}</span>
              <span className="text-xs text-gray-400">· {timeAgo(selected.createdAt)}</span>
            </div>
            <p className="text-sm text-gray-500">{selected.description}</p>
            <div className="flex flex-wrap gap-1.5">
              {selected.knowledgePoints.map((kp) => (
                <span key={kp} className="px-2 py-0.5 bg-brand-50 text-brand-600 rounded-md text-[10px] font-medium">
                  {kp}
                </span>
              ))}
            </div>
            <div className="prose-custom text-sm text-gray-800 leading-relaxed p-4 bg-gray-50 rounded-xl max-h-[50vh] overflow-y-auto">
              <div dangerouslySetInnerHTML={{ __html: selected.content }} />
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
