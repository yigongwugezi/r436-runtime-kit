/**
 * 科大讯飞语音识别 (iFlytek ASR) 服务 — 实时流式版
 *
 * 关键改进：边录边传音频帧，而非录完再一次性发送。
 * 这样才能配合讯飞服务端的 VAD 机制正确识别。
 *
 * 凭据：每用户配置（系统设置 → AI 模型配置 → 语音识别）。
 * HMAC 签名在后端完成（GET /api/learner/me/ai-config/asr-ws-url），
 * apiKey/apiSecret 永不下发前端；本模块只拿到预签名 wss URL 和 appId。
 *
 * 用法：
 *   const asr = new IflytekASR();
 *   await asr.start();          // 连接 + 开始录音（音频实时推送）
 *   const result = await asr.finish();  // 停止录音，等待最终结果
 */

import client from '../api/client';

const DEBUG = true;
function log(...args: unknown[]) {
  if (DEBUG) console.log('[iflytekASR]', ...args);
}

// ── 连接信息（后端预签名） ─────────────────────────────────

interface AsrConnection { url: string; appId: string; }

async function fetchAsrConnection(): Promise<AsrConnection> {
  try {
    const { data } = await client.get('/api/learner/me/ai-config/asr-ws-url');
    return data as AsrConnection;
  } catch (e: any) {
    // 409 AI_CONFIG_MISSING → 引导去系统设置；其余错误保留原信息
    const code = e?.response?.data?.code ?? e?.code;
    if (code === 'AI_CONFIG_MISSING') {
      throw new Error('语音识别未配置，请前往「系统设置 → AI 模型配置」填写讯飞语音听写凭据');
    }
    throw new Error(e?.message || '获取语音服务连接失败');
  }
}

function uint8ToBase64(buf: Uint8Array): string {
  const CHUNK = 0x8000;
  const parts: string[] = [];
  for (let i = 0; i < buf.length; i += CHUNK) {
    parts.push(String.fromCharCode(...buf.subarray(i, i + CHUNK)));
  }
  return btoa(parts.join(''));
}

// ── 结果类型 ─────────────────────────────────────────────

export interface AsrResult { text: string; raw: unknown; }
export type AsrState = 'idle' | 'connecting' | 'recording' | 'processing' | 'done' | 'error';
export interface AsrStateChange { state: AsrState; message?: string; }

// ── 实时录音 + 流式推送 ──────────────────────────────────

type AudioChunkCallback = (int16: Int16Array) => void;

/**
 * 边录边推：ScriptProcessorNode 每拿到一帧 PCM 就回调出去。
 */
class StreamingRecorder {
  private audioCtx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private _sampleRate = 16000;
  private _totalSamples = 0;
  private onChunk: AudioChunkCallback | null = null;

  get sampleRate() { return this._sampleRate; }
  get totalSamples() { return this._totalSamples; }

  async start(onChunk: AudioChunkCallback): Promise<void> {
    this._totalSamples = 0;
    this.onChunk = onChunk;

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: { ideal: 1 },
        sampleRate: { ideal: 16000 },
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    const trackSettings = this.stream.getAudioTracks()[0]?.getSettings();
    log('Mic track settings:', JSON.stringify(trackSettings));

    this.audioCtx = new AudioContext({ sampleRate: 16000 });
    this._sampleRate = this.audioCtx.sampleRate;
    log('AudioContext rate:', this._sampleRate);

    this.source = this.audioCtx.createMediaStreamSource(this.stream);
    this.processor = this.audioCtx.createScriptProcessor(4096, 1, 1);

    this.processor.onaudioprocess = (e: AudioProcessingEvent) => {
      const floatData = e.inputBuffer.getChannelData(0);
      if (floatData.length === 0) return;

      const int16 = new Int16Array(floatData.length);
      for (let i = 0; i < floatData.length; i++) {
        const s = Math.max(-1, Math.min(1, floatData[i]));
        int16[i] = s < 0 ? Math.round(s * 32768) : Math.round(s * 32767);
      }
      this._totalSamples += int16.length;
      this.onChunk?.(int16);
    };

    this.source.connect(this.processor);
    this.processor.connect(this.audioCtx.destination);
  }

  stop(): number {
    // 返回总采样数用于日志
    const total = this._totalSamples;
    if (this.processor) { this.processor.disconnect(); this.processor = null; }
    if (this.source) { this.source.disconnect(); this.source = null; }
    if (this.stream) { this.stream.getTracks().forEach(t => t.stop()); this.stream = null; }
    if (this.audioCtx) { this.audioCtx.close().catch(() => {}); this.audioCtx = null; }
    this.onChunk = null;
    return total;
  }

  abort(): void {
    this._totalSamples = 0;
    if (this.processor) { this.processor.disconnect(); this.processor = null; }
    if (this.source) { this.source.disconnect(); this.source = null; }
    if (this.stream) { this.stream.getTracks().forEach(t => t.stop()); this.stream = null; }
    if (this.audioCtx) { this.audioCtx.close().catch(() => {}); this.audioCtx = null; }
    this.onChunk = null;
  }
}

// ── 主识别类 ─────────────────────────────────────────────

export class IflytekASR {
  private ws: WebSocket | null = null;
  private recorder = new StreamingRecorder();
  private _state: AsrState = 'idle';
  private resultResolve: ((r: AsrResult) => void) | null = null;
  private resultReject: ((e: Error) => void) | null = null;
  private sampleRate = 16000;
  private formatStr = 'audio/L16;rate=16000';
  private finalText = '';
  private audioSent = false;
  private readyToSendAudio = false;

  onStateChange: ((change: AsrStateChange) => void) | null = null;
  onInterimResult: ((text: string) => void) | null = null;

  get state() { return this._state; }

  private setState(state: AsrState, message?: string) {
    log('State →', state, message || '');
    this._state = state;
    this.onStateChange?.({ state, message });
  }

  // ── 音频帧回调（边录边发）──────────────────────────────

  private onAudioChunk = (int16: Int16Array) => {
    // 必须等参数帧（status=0）发出后才能发音频帧
    if (!this.readyToSendAudio) return;
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    const raw = new Uint8Array(int16.buffer);
    try {
      this.ws.send(JSON.stringify({
        data: {
          status: 1,
          format: this.formatStr,
          encoding: 'raw',
          audio: uint8ToBase64(raw),
        },
      }));
      this.audioSent = true;
    } catch {
      // ws 可能刚好关闭
    }
  };

  // ── 公开方法 ───────────────────────────────────────────

  async start(): Promise<void> {
    if (this._state !== 'idle') return;
    this.setState('connecting', '正在连接…');
    this.finalText = '';
    this.audioSent = false;

    try {
      // 1. 从后端获取预签名连接（凭据缺失时抛出引导文案）
      const conn = await fetchAsrConnection();
      log('Connecting to iFlytek IAT (pre-signed by backend)');
      this.ws = new WebSocket(conn.url);

      await new Promise<void>((resolve, reject) => {
        if (!this.ws) return reject(new Error('ws null'));
        let settled = false;

        this.ws.onopen = () => {
          if (settled) return; settled = true;
          log('✅ WebSocket connected');
          resolve();
        };
        this.ws.onerror = () => {
          if (settled) return; settled = true;
          log('❌ WebSocket error during connect');
          reject(new Error('连接讯飞服务失败'));
        };
        this.ws.onclose = (ev) => {
          if (settled) return; settled = true;
          log('❌ WebSocket closed before open, code=', ev.code);
          reject(new Error(`连接关闭 (${ev.code})`));
        };
        setTimeout(() => { if (!settled) { settled = true; reject(new Error('连接超时')); } }, 10000);
      });

      // 2. 设置消息接收（在发第一帧之前）
      this.setupMessageHandler();

      // 3. 开始录音（会触发 onAudioChunk，但在发参数帧前还不能发音频）
      //    所以先用一个 flag 控制
      await this.recorder.start(this.onAudioChunk);

      // 4. 发送参数帧
      this.sampleRate = this.recorder.sampleRate;
      this.formatStr = `audio/L16;rate=${this.sampleRate}`;
      log('Format:', this.formatStr);

      this.ws.send(JSON.stringify({
        common: { app_id: conn.appId },
        business: {
          language: 'zh_cn',
          domain: 'iat',
          accent: 'mandarin',
          vad_eos: 3000,
          ptt: 0,
        },
        data: {
          status: 0,
          format: this.formatStr,
          encoding: 'raw',
          audio: '',
        },
      }));
      log('→ Sent first frame (params)');

      this.readyToSendAudio = true;
      this.setState('recording');
    } catch (e: any) {
      this.readyToSendAudio = false;
      log('start() failed:', e.message);
      this.recorder.abort();
      this.cleanupWs();
      this.setState('error', e.message || '启动失败');
      throw e;
    }
  }

  async finish(): Promise<AsrResult> {
    if (this._state !== 'recording') {
      throw new Error('当前不在录音状态');
    }
    this.setState('processing', '正在识别…');

    // 停止录音
    const totalSamples = this.recorder.stop();
    const duration = totalSamples / this.sampleRate;
    log(`Recording done: ${totalSamples} samples, ${duration.toFixed(2)}s, audioSent=${this.audioSent}`);

    if (!this.audioSent) {
      this.cleanupWs();
      this.setState('error', '未检测到声音，请检查麦克风权限');
      throw new Error('未检测到声音');
    }

    // 等待结果的 Promise
    const resultPromise = new Promise<AsrResult>((resolve, reject) => {
      this.resultResolve = resolve;
      this.resultReject = reject;
    });

    // 发送结束帧
    try {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({
          data: {
            status: 2,
            format: this.formatStr,
            encoding: 'raw',
            audio: '',
          },
        }));
        log('→ Sent end frame (status=2)');
      }
    } catch (e: any) {
      log('Failed to send end frame:', e.message);
    }

    // 等待结果
    const timeout = new Promise<AsrResult>((_, reject) =>
      setTimeout(() => reject(new Error('识别超时，请重试')), 30000),
    );

    try {
      const result = await Promise.race([resultPromise, timeout]);
      log('✅ Recognition done, text:', result.text);
      this.setState('done');
      this.cleanupWs();
      return result;
    } catch (e: any) {
      log('❌ Recognition failed:', e.message);
      this.cleanupWs();
      this.setState('error', e.message || '识别失败');
      throw e;
    }
  }

  abort(): void {
    log('abort()');
    this.recorder.abort();
    this.cleanupWs();
    this.setState('idle');
    this.resultReject?.(new Error('用户取消'));
  }

  // ── WebSocket 消息处理 ─────────────────────────────────

  private setupMessageHandler(): void {
    if (!this.ws) return;
    this.finalText = '';

    this.ws.onmessage = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(ev.data as string);
        log('← Server:', JSON.stringify(msg).slice(0, 600));

        const code = msg?.code;
        if (code !== 0) {
          const errMsg = msg?.message || `服务错误 code=${code}`;
          log('❌ Server error:', errMsg);
          this.resultReject?.(new Error(errMsg));
          this.cleanupWs();
          return;
        }

        // 解析识别文本
        const wsArr = msg?.data?.result?.ws;
        if (wsArr && Array.isArray(wsArr)) {
          let segText = '';
          for (const seg of wsArr) {
            for (const w of seg.cw || []) {
              segText += w.w || '';
            }
          }
          if (segText) {
            this.finalText = segText;
            this.onInterimResult?.(segText);
          }
        }

        // status===2 → 最终结果
        if (msg?.data?.status === 2) {
          if (!this.finalText) {
            log('⚠️ Final result with empty text');
          }
          this.resultResolve?.({ text: this.finalText, raw: msg });
        }
      } catch {
        // 忽略
      }
    };

    this.ws.onerror = () => {
      log('❌ WebSocket error event');
      this.resultReject?.(new Error('通信错误'));
      this.cleanupWs();
    };

    this.ws.onclose = (ev) => {
      log(`WebSocket closed: code=${ev.code} reason="${ev.reason}" wasClean=${ev.wasClean}`);
      if (this._state === 'processing' && !this.resultResolve) {
        // resultResolve 已被调用则忽略
      }
      if (this._state === 'processing' && this.resultResolve) {
        // 还没收到最终结果就断了
        this.resultReject?.(new Error('连接意外断开'));
      }
      this.ws = null;
    };
  }

  private cleanupWs(): void {
    if (this.ws) {
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws.onclose = null;
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close();
      }
      this.ws = null;
    }
  }
}
