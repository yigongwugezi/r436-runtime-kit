import { useState } from 'react';
import { Sparkles, ChevronDown, ChevronUp, Zap } from 'lucide-react';

/* ===================================================================
 * 快捷输入模板
 * 输入框上方可折叠的面板，点击模板填入输入框
 * =================================================================== */
const TEMPLATES = [
  {
    group: '学习规划',
    items: [
      { icon: '🎯', label: '构建学习画像', prompt: '我想开始学习，帮我构建学习画像' },
      { icon: '🗺️', label: '规划学习路径', prompt: '帮我规划一个两周的机器学习学习路径' },
      { icon: '📊', label: '诊断知识短板', prompt: '帮我诊断一下在人工智能方面的知识短板' },
    ],
  },
  {
    group: '学习资源',
    items: [
      { icon: '📝', label: '生成练习题', prompt: '根据我的画像生成一套神经网络基础练习题' },
      { icon: '🧠', label: '生成思维导图', prompt: '帮我生成人工智能导论的知识思维导图' },
      { icon: '💻', label: '实操案例', prompt: '给我一个Python实现神经网络的实操案例' },
    ],
  },
  {
    group: '进度与反馈',
    items: [
      { icon: '📈', label: '反馈学习进度', prompt: '反馈我的学习进度' },
      { icon: '❓', label: '解释知识点', prompt: '帮我解释一下反向传播算法' },
      { icon: '📋', label: '推荐学习资源', prompt: '帮我推荐学习资源' },
    ],
  },
];

interface Props {
  onSelect: (prompt: string) => void;
}

export default function PromptTemplates({ onSelect }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-600 transition-colors px-1"
      >
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        <Zap className="w-3 h-3" />
        快捷输入模板
      </button>

      {open && (
        <div className="mt-2 p-3 bg-gray-50 border border-gray-100 rounded-xl space-y-2 animate-fade-in-up">
          {TEMPLATES.map((group) => (
            <div key={group.group}>
              <p className="text-[10px] font-semibold text-gray-400 mb-1.5">{group.group}</p>
              <div className="flex flex-wrap gap-1.5">
                {group.items.map((item) => (
                  <button
                    key={item.label}
                    onClick={() => { onSelect(item.prompt); setOpen(false); }}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-medium bg-white border border-gray-200 text-gray-500 hover:border-brand-300 hover:text-brand-600 hover:bg-brand-50/50 transition-all"
                  >
                    <span>{item.icon}</span>
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
