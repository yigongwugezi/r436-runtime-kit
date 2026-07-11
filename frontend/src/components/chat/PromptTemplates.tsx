import { useState, useMemo } from 'react';
import { ChevronDown, ChevronUp, Zap } from 'lucide-react';
import { useSubjectStore } from '../../store/subjectStore';

/* ===================================================================
 * 快捷输入模板 — 动态适配当前科目
 * =================================================================== */

interface Props {
  onSelect: (prompt: string) => void;
}

export default function PromptTemplates({ onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const activeSubject = useSubjectStore((s) => s.activeSubject);
  const activeClassSubject = useSubjectStore((s) => s.activeClassSubject);
  const courseName = activeSubject?.name || activeClassSubject?.name || '';

  const templates = useMemo(() => {
    const course = courseName || '这门课';
    return [
      {
        group: '学习规划',
        items: [
          { icon: '🎯', label: '了解我的基础', prompt: courseName ? `我想学${course}，帮我了解一下我的基础` : '我想开始学习，帮我了解一下我的基础' },
          { icon: '🗺️', label: '规划学习路径', prompt: courseName ? `帮我规划${course}的学习路径` : '帮我规划学习路径' },
          { icon: '📊', label: '诊断薄弱点', prompt: courseName ? `帮我诊断一下在${course}方面的薄弱点` : '帮我诊断一下我的薄弱点' },
        ],
      },
      {
        group: '学习资源',
        items: [
          { icon: '📝', label: '生成练习题', prompt: courseName ? `根据我的学习情况，出几道${course}的练习题` : '根据我的学习情况，出几道练习题' },
          { icon: '🧠', label: '生成思维导图', prompt: courseName ? `帮我生成${course}的知识思维导图` : '帮我生成知识思维导图' },
          { icon: '📖', label: '讲解知识点', prompt: courseName ? `帮我详细讲解${course}的一个知识点` : '帮我详细讲解一个知识点' },
        ],
      },
      {
        group: '进度与反馈',
        items: [
          { icon: '📈', label: '查看学习进度', prompt: '帮我看看最近的学习进度怎么样' },
          { icon: '❓', label: '我不理解某个概念', prompt: '我有一个概念不太理解，帮我讲一下' },
          { icon: '📋', label: '推荐学习资源', prompt: '根据我的学习情况推荐一些资源' },
        ],
      },
      {
        group: '规划模式',
        items: [
          { icon: '', label: '教材式（数理）', prompt: courseName ? `帮我按章节系统学${courseName}` : '帮我按章节系统学' },
          { icon: '', label: '日课式（语言）', prompt: courseName ? `帮我规划${courseName}的每日学习计划` : '帮我规划每日学习计划' },
          { icon: '', label: '精进式（补短）', prompt: courseName ? `帮我专攻${courseName}的薄弱点` : '帮我专项突破薄弱点' },
        ],
      },
    ];
  }, [courseName]);

  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-600 transition-colors px-1"
      >
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        <Zap className="w-3 h-3" />
        推荐话题
      </button>

      {open && (
        <div className="mt-2 p-3 bg-gray-50 border border-gray-100 rounded-xl space-y-2 animate-fade-in-up">
          {templates.map((group) => (
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
