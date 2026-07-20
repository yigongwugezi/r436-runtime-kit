import { useState, useMemo } from 'react';
import { X, Sparkles, BookOpen, Hash, BarChart3, MessageSquare } from 'lucide-react';

interface Props {
  open: boolean;
  onClose: () => void;
  onGenerate: (config: PracticeConfig) => void;
  availableKnowledgePoints: string[];
  loading?: boolean;
}

export interface PracticeConfig {
  knowledgePoints: string[];
  types: string[];
  count: number;
  difficulty: string;
  extraDesc: string;
}

const QUESTION_TYPES = [
  { key: 'choice', label: '选择题' },
  { key: 'fill', label: '填空题' },
  { key: 'truefalse', label: '判断题' },
  { key: 'shortanswer', label: '简答题' },
];

const COUNTS = [5, 10, 15, 20];

const DIFFICULTIES = [
  { key: 'easy', label: '简单' },
  { key: 'medium', label: '中等' },
  { key: 'hard', label: '困难' },
  { key: 'mixed', label: '混合' },
];

export default function CustomPracticeModal({ open, onClose, onGenerate, availableKnowledgePoints, loading }: Props) {
  const [selectedKPs, setSelectedKPs] = useState<string[]>([]);
  const [selectedTypes, setSelectedTypes] = useState<string[]>(['choice']);
  const [count, setCount] = useState(5);
  const [difficulty, setDifficulty] = useState('medium');
  const [extraDesc, setExtraDesc] = useState('');

  // 去重 + 排序
  const knowledgePoints = useMemo(
    () => [...new Set(availableKnowledgePoints.filter(Boolean))].sort(),
    [availableKnowledgePoints],
  );

  const toggleKP = (kp: string) => {
    setSelectedKPs(prev =>
      prev.includes(kp) ? prev.filter(k => k !== kp) : [...prev, kp],
    );
  };

  const toggleType = (type: string) => {
    setSelectedTypes(prev => {
      if (prev.includes(type)) {
        if (prev.length <= 1) return prev; // 至少保留一个
        return prev.filter(t => t !== type);
      }
      return [...prev, type];
    });
  };

  const handleGenerate = () => {
    onGenerate({
      knowledgePoints: selectedKPs,
      types: selectedTypes,
      count,
      difficulty,
      extraDesc: extraDesc.trim(),
    });
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-fade-in">
      <div className="relative mx-4 w-full max-w-lg rounded-2xl bg-white dark:bg-surface-800 shadow-elevated animate-scale-in">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-surface-200 dark:border-surface-600 px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-50 dark:bg-accent-500/20 text-accent-600 dark:text-accent-300">
              <BookOpen size={18} />
            </div>
            <div>
              <h3 className="text-base font-semibold text-surface-800 dark:text-gray-100">自定义练习</h3>
              <p className="text-xs text-surface-400">自选知识点、题型和难度</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-700 transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[60vh] overflow-y-auto space-y-5 px-6 py-5">
          {/* 知识点 */}
          <section>
            <div className="mb-2.5 flex items-center gap-1.5">
              <BookOpen size={14} className="text-surface-400" />
              <span className="text-xs font-medium text-surface-500">知识点范围（可多选，留空则自动）</span>
            </div>
            {knowledgePoints.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {knowledgePoints.slice(0, 30).map(kp => (
                  <button
                    key={kp}
                    onClick={() => toggleKP(kp)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                      selectedKPs.includes(kp)
                        ? 'bg-accent-500 text-white shadow-sm'
                        : 'bg-surface-100 dark:bg-surface-700 text-surface-600 dark:text-gray-300 hover:bg-surface-200 dark:hover:bg-surface-600'
                    }`}
                  >
                    {kp}
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-surface-400 italic">暂无可用知识点，将根据学习上下文自动出题</p>
            )}
          </section>

          {/* 题型 */}
          <section>
            <div className="mb-2.5 flex items-center gap-1.5">
              <Hash size={14} className="text-surface-400" />
              <span className="text-xs font-medium text-surface-500">题型</span>
            </div>
            <div className="flex gap-1.5">
              {QUESTION_TYPES.map(t => (
                <button
                  key={t.key}
                  onClick={() => toggleType(t.key)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                    selectedTypes.includes(t.key)
                      ? 'bg-accent-500 text-white shadow-sm'
                      : 'bg-surface-100 dark:bg-surface-700 text-surface-600 dark:text-gray-300 hover:bg-surface-200 dark:hover:bg-surface-600'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </section>

          {/* 题目数量 */}
          <section>
            <div className="mb-2.5 flex items-center gap-1.5">
              <BarChart3 size={14} className="text-surface-400" />
              <span className="text-xs font-medium text-surface-500">题目数量</span>
            </div>
            <div className="flex gap-1.5">
              {COUNTS.map(c => (
                <button
                  key={c}
                  onClick={() => setCount(c)}
                  className={`rounded-lg px-4 py-1.5 text-xs font-medium transition-all ${
                    count === c
                      ? 'bg-accent-500 text-white shadow-sm'
                      : 'bg-surface-100 dark:bg-surface-700 text-surface-600 dark:text-gray-300 hover:bg-surface-200 dark:hover:bg-surface-600'
                  }`}
                >
                  {c} 道
                </button>
              ))}
            </div>
          </section>

          {/* 难度 */}
          <section>
            <div className="mb-2.5 flex items-center gap-1.5">
              <BarChart3 size={14} className="text-surface-400" />
              <span className="text-xs font-medium text-surface-500">难度</span>
            </div>
            <div className="flex gap-1.5">
              {DIFFICULTIES.map(d => (
                <button
                  key={d.key}
                  onClick={() => setDifficulty(d.key)}
                  className={`rounded-lg px-4 py-1.5 text-xs font-medium transition-all ${
                    difficulty === d.key
                      ? 'bg-accent-500 text-white shadow-sm'
                      : 'bg-surface-100 dark:bg-surface-700 text-surface-600 dark:text-gray-300 hover:bg-surface-200 dark:hover:bg-surface-600'
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </section>

          {/* 额外描述 */}
          <section>
            <div className="mb-2.5 flex items-center gap-1.5">
              <MessageSquare size={14} className="text-surface-400" />
              <span className="text-xs font-medium text-surface-500">额外描述（可选）</span>
            </div>
            <textarea
              value={extraDesc}
              onChange={e => setExtraDesc(e.target.value)}
              rows={2}
              placeholder="例如：重点出三角函数、不要出选择题..."
              className="w-full resize-none rounded-xl border-2 border-surface-200 dark:border-surface-600 bg-surface-50 dark:bg-surface-800 px-3.5 py-2.5 text-sm text-surface-700 dark:text-gray-200 outline-none placeholder:text-surface-400 focus:border-accent-400 dark:focus:border-accent-500/50 transition-colors"
            />
          </section>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-surface-200 dark:border-surface-600 px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-surface-500 hover:text-surface-700 dark:hover:text-gray-200 transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-primary-500 to-accent-500 px-5 py-2 text-sm font-medium text-white shadow-sm hover:from-primary-600 hover:to-accent-600 disabled:opacity-50 transition-all"
          >
            <Sparkles size={15} />
            {loading ? '生成中…' : '生成练习'}
          </button>
        </div>
      </div>
    </div>
  );
}
