import { useState } from 'react';
import { Sparkles, NotebookPen, Route, BookOpen, Stethoscope, TrendingUp, ChevronDown, ChevronUp } from 'lucide-react';

/* ===================================================================
 * Clarification 动作定义
 * =================================================================== */
const CLARIFICATION_ACTIONS = [
  {
    id: 'profile',
    label: '生成学习画像',
    icon: NotebookPen,
    prompt: '我想开始学习，帮我构建学习画像',
    description: '分析你的背景、基础和目标',
    color: 'from-violet-500 to-purple-600',
    bg: 'bg-violet-50 hover:bg-violet-100',
    textColor: 'text-violet-700',
    borderColor: 'border-violet-200',
    ringColor: 'ring-violet-300',
  },
  {
    id: 'plan',
    label: '规划学习路径',
    icon: Route,
    prompt: '帮我规划一个学习路径',
    description: '制定个性化分阶段学习计划',
    color: 'from-blue-500 to-cyan-600',
    bg: 'bg-blue-50 hover:bg-blue-100',
    textColor: 'text-blue-700',
    borderColor: 'border-blue-200',
    ringColor: 'ring-blue-300',
  },
  {
    id: 'resource',
    label: '推荐学习资源',
    icon: BookOpen,
    prompt: '帮我推荐学习资源',
    description: '获取讲义、练习、思维导图',
    color: 'from-emerald-500 to-green-600',
    bg: 'bg-emerald-50 hover:bg-emerald-100',
    textColor: 'text-emerald-700',
    borderColor: 'border-emerald-200',
    ringColor: 'ring-emerald-300',
  },
  {
    id: 'diagnosis',
    label: '诊断薄弱点',
    icon: Stethoscope,
    prompt: '帮我诊断薄弱点',
    description: '找出你的知识漏洞和短板',
    color: 'from-amber-500 to-orange-600',
    bg: 'bg-amber-50 hover:bg-amber-100',
    textColor: 'text-amber-700',
    borderColor: 'border-amber-200',
    ringColor: 'ring-amber-300',
  },
  {
    id: 'feedback',
    label: '反馈学习进度',
    icon: TrendingUp,
    prompt: '反馈我的学习进度',
    description: '告诉我你学了什么，效果如何',
    color: 'from-rose-500 to-pink-600',
    bg: 'bg-rose-50 hover:bg-rose-100',
    textColor: 'text-rose-700',
    borderColor: 'border-rose-200',
    ringColor: 'ring-rose-300',
  },
] as const;

/* ===================================================================
 * Props
 * =================================================================== */
interface ChatClarificationProps {
  /** 用户选择某个方向后调用，传入对应 prompt */
  onSelect: (prompt: string) => void;
}

/* ===================================================================
 * ChatClarification 组件
 * 低置信度 unknown intent 时展示的友好引导面板
 * =================================================================== */
export default function ChatClarification({ onSelect }: ChatClarificationProps) {
  const [showDebug, setShowDebug] = useState(false);

  return (
    <div className="mt-3 space-y-3 animate-fade-in-up" data-testid="chat-clarification">
      {/* 引导提示 */}
      <div className="flex items-start gap-2.5 px-1">
        <div className="w-6 h-6 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0 mt-0.5">
          <Sparkles className="w-3.5 h-3.5 text-amber-600" />
        </div>
        <p className="text-sm text-amber-800 leading-relaxed">
          我还不太确定你想让我做什么，请选择一个方向：
        </p>
      </div>

      {/* 快捷操作按钮 — 大卡片网格 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {CLARIFICATION_ACTIONS.map((action) => {
          const Icon = action.icon;
          return (
            <button
              key={action.id}
              onClick={() => onSelect(action.prompt)}
              className={`
                group relative flex items-start gap-3 p-3.5 rounded-xl border
                ${action.bg} ${action.borderColor}
                transition-all duration-200
                hover:shadow-md hover:-translate-y-0.5
                focus:outline-none focus:ring-2 ${action.ringColor} focus:ring-offset-1
                text-left
              `}
              title={action.description}
            >
              {/* 图标 */}
              <div className={`
                w-9 h-9 rounded-lg bg-gradient-to-br ${action.color}
                flex items-center justify-center flex-shrink-0
                shadow-sm
              `}>
                <Icon className="w-4.5 h-4.5 text-white" />
              </div>

              {/* 文字 */}
              <div className="flex-1 min-w-0">
                <span className={`text-sm font-semibold ${action.textColor} block`}>
                  {action.label}
                </span>
                <span className="text-[11px] text-gray-500 mt-0.5 block leading-relaxed">
                  {action.description}
                </span>
              </div>

              {/* 箭头指示 */}
              <div className={`
                absolute right-2.5 top-1/2 -translate-y-1/2
                opacity-0 group-hover:opacity-100 transition-opacity
                ${action.textColor}
              `}>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </button>
          );
        })}
      </div>

      {/* 开发调试信息（可折叠） */}
      <div className="pt-1">
        <button
          onClick={() => setShowDebug(!showDebug)}
          className="flex items-center gap-1 text-[10px] text-gray-300 hover:text-gray-500 transition-colors px-1"
        >
          {showDebug ? (
            <ChevronUp className="w-3 h-3" />
          ) : (
            <ChevronDown className="w-3 h-3" />
          )}
          开发信息
        </button>
        {showDebug && (
          <div className="mt-1.5 p-2.5 bg-gray-50 border border-gray-100 rounded-lg">
            <p className="text-[10px] text-gray-400 font-mono leading-relaxed">
              意图识别结果未知（置信度低于阈值），系统自动展示澄清引导面板。
              <br />
              该面板仅当前端收到 <code className="text-brand-500">isClarification</code> 标记时触发。
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
