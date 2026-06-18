import { Clock, Cpu, Sparkles, User } from 'lucide-react';
import type { ReactNode } from 'react';

export type DataSource = 'user_input' | 'agent_generated' | 'system_inferred';

const SOURCE_CONFIG: Record<DataSource, {
  label: string;
  icon: ReactNode;
  className: string;
}> = {
  user_input: {
    label: '用户提供',
    icon: <User className="w-2.5 h-2.5" />,
    className: 'bg-blue-50 text-blue-600 border-blue-200',
  },
  agent_generated: {
    label: '智能体生成',
    icon: <Sparkles className="w-2.5 h-2.5" />,
    className: 'bg-purple-50 text-purple-600 border-purple-200',
  },
  system_inferred: {
    label: '系统推断',
    icon: <Cpu className="w-2.5 h-2.5" />,
    className: 'bg-amber-50 text-amber-600 border-amber-200',
  },
};

export default function SourceBadge({
  source,
  size = 'sm',
}: {
  source: DataSource;
  size?: 'sm' | 'xs';
}) {
  const cfg = SOURCE_CONFIG[source] || SOURCE_CONFIG.system_inferred;
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border font-medium whitespace-nowrap ${
        size === 'xs' ? 'text-[9px]' : 'text-[10px]'
      } ${cfg.className}`}
      title={`数据来源：${cfg.label}`}
    >
      {cfg.icon}
      {cfg.label}
    </span>
  );
}

export function UpdateTimeRow({
  label,
  timestamp,
  source,
}: {
  label: string;
  timestamp: number;
  source?: DataSource;
}) {
  return (
    <div className="flex items-center gap-2 text-[10px] text-gray-400 mt-1">
      <Clock className="w-3 h-3" />
      <span>{label}：{timeAgoShort(timestamp)}</span>
      {source && <SourceBadge source={source} size="xs" />}
    </div>
  );
}

function timeAgoShort(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 60000) return '刚刚';
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}分钟前`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}小时前`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}天前`;
  return new Date(ts).toLocaleDateString('zh-CN');
}
