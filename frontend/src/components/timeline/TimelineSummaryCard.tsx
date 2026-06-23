import { BookOpen, FileText, Code, Clock, History } from 'lucide-react';
import type { TimelineEvent } from '../../types/timeline';
import { timeAgo } from '../../utils/format';

/* ===================================================================
 * TimelineSummaryCard — 右侧统计概览卡片
 * 展示当前筛选后学习记录的汇总数据
 * =================================================================== */
interface TimelineSummaryCardProps {
  events: TimelineEvent[];
  total: number;
}

export default function TimelineSummaryCard({ events, total }: TimelineSummaryCardProps) {
  // 统计
  const resourceViewCount = events.filter((e) => e.event === 'resource_view').length;
  const resourceCompleteCount = events.filter((e) => e.event === 'resource_complete').length;
  const quizCount = events.filter((e) => e.event === 'quiz_result').length;
  const practiceCount = events.filter((e) => e.event === 'practice_result').length;
  const feedbackCount = events.filter((e) => e.event === 'feedback').length;
  const stageCompleteCount = events.filter((e) => e.event === 'stage_complete' || e.event === 'node_progress').length;

  // 最近学习时间
  const timestamps = events.map((e) => e.timestamp).filter(Boolean);
  const lastTime = timestamps.length > 0 ? Math.max(...timestamps) : null;

  const items = [
    { icon: History, label: '总事件数', value: `${total}`, color: 'text-brand-500 bg-brand-50' },
    { icon: BookOpen, label: '查看资源', value: `${resourceViewCount}`, color: 'text-blue-500 bg-blue-50' },
    { icon: BookOpen, label: '完成资源', value: `${resourceCompleteCount}`, color: 'text-green-500 bg-green-50' },
    { icon: FileText, label: '测验', value: `${quizCount}`, color: 'text-amber-500 bg-amber-50' },
    { icon: Code, label: '实践', value: `${practiceCount}`, color: 'text-cyan-500 bg-cyan-50' },
    { icon: Clock, label: '反馈', value: `${feedbackCount}`, color: 'text-purple-500 bg-purple-50' },
  ];

  return (
    <div className="bg-white border border-gray-100 rounded-2xl p-5 shadow-sm">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
        学习概览
      </h3>

      {/* 统计网格 */}
      <div className="grid grid-cols-2 gap-2.5">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.label} className={`${item.color} rounded-xl p-3 flex flex-col items-center gap-1`}>
              <Icon className="w-4 h-4" />
              <span className="text-lg font-extrabold">{item.value}</span>
              <span className="text-[10px] opacity-75 whitespace-nowrap">{item.label}</span>
            </div>
          );
        })}
      </div>

      {/* 阶段完成 */}
      {stageCompleteCount > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-50 flex items-center justify-between text-xs">
          <span className="text-gray-500">阶段完成</span>
          <span className="font-bold text-rose-500">{stageCompleteCount}</span>
        </div>
      )}

      {/* 最近学习时间 */}
      {lastTime && (
        <div className="mt-2 pt-2 border-t border-gray-50 flex items-center justify-between text-[10px]">
          <span className="text-gray-400">最近学习</span>
          <span className="text-gray-500 font-medium">{timeAgo(lastTime)}</span>
        </div>
      )}
    </div>
  );
}
