/**
 * useVoiceInput — 语音输入 React Hook
 *
 * 封装科大讯飞语音识别的完整流程。
 * 识别完成后 transcribedText 更新，父组件通过 useEffect 监听即可。
 *
 * 用法：
 *   const { isListening, transcribedText, start, stop } = useVoiceInput({ maxSeconds: 30 });
 *   useEffect(() => { if (transcribedText) setInput(transcribedText); }, [transcribedText]);
 */

import { useCallback, useRef, useState } from 'react';
import { IflytekASR, type AsrState } from '../services/iflytekASR';

const MAX_RECORD_SECONDS = 30;

export interface UseVoiceInputOptions {
  maxSeconds?: number;
}

export interface UseVoiceInputReturn {
  isListening: boolean;
  stateText: string;
  interimText: string;
  /** 最终识别文本，完成后更新 */
  transcribedText: string;
  error: string | null;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  cancel: () => void;
}

export function useVoiceInput(options: UseVoiceInputOptions = {}): UseVoiceInputReturn {
  const { maxSeconds = MAX_RECORD_SECONDS } = options;

  const [isListening, setIsListening] = useState(false);
  const [stateText, setStateText] = useState('');
  const [interimText, setInterimText] = useState('');
  const [transcribedText, setTranscribedText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const asrRef = useRef<IflytekASR | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
  }, []);

  const cleanup = useCallback(() => {
    clearTimer();
    asrRef.current = null;
  }, [clearTimer]);

  const handleStateChange = useCallback(({ state, message }: { state: AsrState; message?: string }) => {
    switch (state) {
      case 'connecting': setStateText('正在连接…'); setError(null); break;
      case 'recording': setIsListening(true); setStateText('正在聆听…'); break;
      case 'processing': setIsListening(false); setStateText('正在识别…'); clearTimer(); break;
      case 'done': setIsListening(false); setStateText('识别完成'); setError(null); break;
      case 'error': setIsListening(false); setStateText(''); setError(message || '语音识别失败'); cleanup(); break;
      default: setStateText(''); setIsListening(false); break;
    }
  }, [clearTimer, cleanup]);

  const handleInterim = useCallback((text: string) => {
    setInterimText(text);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setInterimText('');
    setTranscribedText('');

    const asr = new IflytekASR();
    asr.onStateChange = handleStateChange;
    asr.onInterimResult = handleInterim;
    asrRef.current = asr;

    try {
      await asr.start();
      timerRef.current = setTimeout(async () => {
        if (asrRef.current?.state === 'recording') {
          try { await asrRef.current.finish(); } catch { /* handled */ }
        }
      }, maxSeconds * 1000);
    } catch {
      cleanup();
    }
  }, [handleStateChange, handleInterim, maxSeconds, cleanup]);

  const stop = useCallback(async () => {
    clearTimer();
    const asr = asrRef.current;
    if (!asr) return;

    try {
      const result = await asr.finish();
      console.log('[useVoiceInput] result.text:', JSON.stringify(result.text));
      if (result.text) {
        setTranscribedText(result.text);
      }
    } catch {
      // handled in stateChange
    } finally {
      setTimeout(() => {
        setInterimText('');
        setStateText('');
        setIsListening(false);
      }, 1200);
      cleanup();
    }
  }, [clearTimer, cleanup]);

  const cancel = useCallback(() => {
    clearTimer();
    asrRef.current?.abort();
    setIsListening(false);
    setStateText('');
    setInterimText('');
    setError(null);
    cleanup();
  }, [clearTimer, cleanup]);

  return { isListening, stateText, interimText, transcribedText, error, start, stop, cancel };
}
