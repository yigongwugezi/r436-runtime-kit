import { useState } from 'react';
import { useStreamChat } from '../../hooks/useStreamChat';

interface Props {
  options: string[];
  course: string;
  defaultMode: string;
}

const MODE_DESC: Record<string, string> = {
  '教材式': '按章节系统学，适合数理类',
  '日课式': '每天打卡任务，适合语言类',
  '精进式': '专攻薄弱点，适合查漏补缺',
};

export default function ModePicker({ options, course, defaultMode }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const { send, isStreaming } = useStreamChat();

  const handlePick = (opt: string) => {
    if (selected || isStreaming) return;
    setSelected(opt);
    const prompt = opt === '教材式'
      ? `帮我按章节系统学${course}`
      : opt === '日课式'
        ? `帮我规划${course}的每日学习计划`
        : `帮我专攻${course}的薄弱点`;
    send(prompt);
  };

  if (selected || isStreaming) {
    return (
      <div className="my-3 p-4 bg-emerald-50 rounded-2xl border border-emerald-200 animate-fade-in">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-full bg-emerald-200 flex items-center justify-center">
            <svg className="w-3 h-3 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
          </div>
          <p className="text-xs text-emerald-700 font-medium">
            {selected ? `已选择「${selected}」模式，正在生成…` : '正在生成学习路径…'}
          </p>
        </div>
        <p className="text-[10px] text-emerald-500 mt-1.5 ml-7">生成完成后可在学习路径页面查看结果</p>
      </div>
    );
  }

  return (
    <div className="my-3 p-4 bg-white rounded-2xl border-2 border-surface-200 animate-fade-in">
      <p className="text-xs font-semibold text-surface-600 mb-3">
        选择学习模式
      </p>
      <div className="flex flex-wrap gap-2.5">
        {options.map(opt => {
          const isDefault = opt === defaultMode;
          return (
            <button
              key={opt}
              onClick={() => handlePick(opt)}
              className={`px-4 py-2.5 rounded-xl text-sm font-medium transition-all active:scale-[0.97]
                ${isDefault
                  ? 'bg-blue-500 text-white shadow-lg shadow-blue-200 hover:bg-blue-600'
                  : 'bg-surface-50 text-surface-600 hover:bg-surface-100 hover:text-surface-800 border border-surface-200'}`}
            >
              {opt}
              {isDefault && <span className="ml-1.5 text-[10px] opacity-70">推荐</span>}
            </button>
          );
        })}
      </div>
      <div className="mt-3 space-y-1">
        {options.map(opt => (
          <p key={opt} className="text-[10px] text-surface-400">
            <span className="font-medium text-surface-500">{opt}</span> — {MODE_DESC[opt] || ''}
          </p>
        ))}
      </div>
    </div>
  );
}

/** Parse [[mode-pick:...]] tag from message text */
export function parseModePickTag(text: string): { options: string[]; course: string; defaultMode: string } | null {
  const match = text.match(/\[\[mode-pick:(.+?)\]\]/);
  if (!match) return null;
  const inner = match[1];
  const parts = inner.split('|');
  let options: string[] = [];
  let course = '';
  let defaultMode = '教材式';
  for (const part of parts) {
    if (part.startsWith('course:')) {
      course = part.slice(7);
    } else if (part.startsWith('default:')) {
      defaultMode = part.slice(8);
    } else {
      options = part.split(',').filter(Boolean);
    }
  }
  if (options.length === 0) return null;
  return { options, course, defaultMode };
}

/** Strip [[mode-pick:...]] tag from text for clean rendering */
export function stripModePickTag(text: string): string {
  return text.replace(/\[\[mode-pick:.+?\]\]/g, '').trim();
}
