import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface Props {
  text: string;
  /** 超过此行数时折叠，默认 3 */
  maxLines?: number;
  /** 类名 */
  className?: string;
}

/**
 * 可展开/收起的长文本组件
 *
 * 用法：
 * <ExpandableText text={longText} maxLines={3} className="text-xs text-gray-500" />
 */
export default function ExpandableText({ text, maxLines = 3, className = '' }: Props) {
  const [expanded, setExpanded] = useState(false);
  const lineCount = text.split('\n').length;
  const isLong = lineCount > maxLines || text.length > 200;

  // 较短文本直接显示
  if (!isLong) {
    return <p className={className}>{text}</p>;
  }

  return (
    <div>
      <p
        className={`${className} ${!expanded ? `line-clamp-${maxLines}` : ''}`}
        style={!expanded ? { display: '-webkit-box', WebkitLineClamp: maxLines, WebkitBoxOrient: 'vertical', overflow: 'hidden' } : undefined}
      >
        {text}
      </p>
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-1 inline-flex items-center gap-1 text-[10px] text-brand-500 hover:text-brand-600 font-medium transition-colors"
      >
        {expanded ? (
          <>
            <ChevronUp className="w-3 h-3" />
            收起
          </>
        ) : (
          <>
            <ChevronDown className="w-3 h-3" />
            展开全文（{lineCount} 行）
          </>
        )}
      </button>
    </div>
  );
}
