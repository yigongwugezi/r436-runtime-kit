/**
 * VoiceInputButton — 语音输入按钮
 *
 * 点击开始录音，再次点击/自动超时后识别。
 * 识别文本通过 onResult 回调传出。
 */

import { useEffect, useRef } from 'react';
import { Mic, MicOff, Loader2 } from 'lucide-react';
import { useVoiceInput } from '../../hooks/useVoiceInput';

export interface VoiceInputButtonProps {
  onResult?: (text: string) => void;
  disabled?: boolean;
  size?: 'sm' | 'md';
  className?: string;
  maxSeconds?: number;
}

export default function VoiceInputButton({
  onResult,
  disabled = false,
  size = 'md',
  className = '',
  maxSeconds,
}: VoiceInputButtonProps) {
  const { isListening, stateText, interimText, transcribedText, error, start, stop } =
    useVoiceInput({ maxSeconds });

  // 用 ref 存 onResult，避免 effect 的依赖问题
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;

  // 上次已回调的文本，防止重复触发
  const lastTextRef = useRef('');

  useEffect(() => {
    if (transcribedText && transcribedText !== lastTextRef.current) {
      lastTextRef.current = transcribedText;
      console.log('[VoiceInputButton] effect calling onResult with:', transcribedText);
      onResultRef.current?.(transcribedText);
    }
  }, [transcribedText]);

  const handleClick = async () => {
    if (disabled) return;
    if (isListening) {
      await stop();
    } else {
      await start();
    }
  };

  const sizeClass = size === 'sm' ? 'w-7 h-7' : 'w-9 h-9';
  const iconSize = size === 'sm' ? 14 : 17;

  return (
    <div className="relative inline-flex items-center" title={error || stateText || '语音输入'}>
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled}
        className={`${sizeClass} rounded-full flex items-center justify-center transition-all flex-shrink-0 ${
          disabled
            ? 'text-gray-300 cursor-not-allowed bg-gray-100'
            : isListening
              ? 'text-white bg-red-500 hover:bg-red-600 animate-pulse shadow-sm'
              : 'text-gray-400 hover:text-gray-600 hover:bg-gray-200/60'
        } ${className}`}
        title={isListening ? '点击停止录音' : '语音输入'}
      >
        {isListening ? (
          <MicOff size={iconSize} />
        ) : stateText === 'connecting' || stateText === 'processing' ? (
          <Loader2 size={iconSize} className="animate-spin" />
        ) : (
          <Mic size={iconSize} />
        )}
      </button>

      {isListening && (
        <span className="absolute -top-7 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md bg-red-500 px-2 py-0.5 text-[10px] text-white shadow pointer-events-none">
          {stateText}
        </span>
      )}

      {interimText && isListening && (
        <span className="absolute -bottom-7 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md bg-white border border-gray-200 px-2 py-0.5 text-[10px] text-gray-500 shadow max-w-[200px] overflow-hidden text-ellipsis pointer-events-none">
          {interimText}
        </span>
      )}

      {error && !isListening && (
        <span className="absolute -top-7 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md bg-amber-500 px-2 py-0.5 text-[10px] text-white shadow pointer-events-none">
          {error}
        </span>
      )}
    </div>
  );
}
