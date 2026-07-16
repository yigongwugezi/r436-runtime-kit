import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { imageAttachmentKey, useChatStore, detectOrphanedStreaming } from '../store/chatStore';
import { useStreamChat } from '../hooks/useStreamChat';
import { useNotificationPoller } from '../hooks/useNotificationPoller';
import { getSessionMessages, getQuickCommands, recoverGeneration, uploadMultimodalImage, saveMultimodalResource, prepareKnowledgeCandidates } from '../api/chat';
import { DEFAULT_QUICK_COMMANDS } from '../utils/constants';
import { timeAgo } from '../utils/format';
import { runtimeStorageKeys, writeStorageItem } from '../utils/storageKeys';
import type { ChatAttachment, ChatMessage, GenerationProgress, ProgressStep, QuickCommand } from '../types/chat';
import { Send, Sparkles, Square, Copy, Check, AlertCircle, Bot, RefreshCw, XCircle, Loader2, BrainCircuit, ImagePlus, Trash2, MessageCircle, Globe } from 'lucide-react';
import { getCurrentLearner } from '../store/authStore';
import Markdown from '../utils/markdown';
import MarkmapDiagram from '../utils/markmap';
import ChatHistorySidebar from '../components/chat/ChatHistorySidebar';
import ChatClarification from '../components/chat/ChatClarification';
import PromptTemplates from '../components/chat/PromptTemplates';
import AgentExecutionDetails from '../components/chat/AgentExecutionDetails';
import ModePicker, { parseModePickTag, stripModePickTag } from '../components/chat/ModePicker';

/** Agent 通用阶段映射 —— 后端 agent_id → 中文标签 */
const AGENT_LABELS: Record<string, string> = {
  profile_agent: '生成画像',
  knowledge_agent: '检索知识',
  diagnosis_agent: '诊断分析',
  question_agent: '生成试题',
  planner_agent: '规划路径',
  resource_agent: '生成资源',
  review_agent: '检查质量',
  grading_agent: '批改作答',
};
const EMPTY_PIPELINE: ProgressStep[] = [];
const IMAGE_REFERENCE_RE = /(这张图|这张图片|上面这张图|刚才那张图|图中|图片里|这道题|这页笔记|题图|错题图|继续讲第\s*[0-9一二两三四五六七八九十]+\s*题)/;

const attachmentUrl = (item: ChatAttachment | null | undefined) =>
  item?.preview_url || item?.image_url || item?.url || (item?.file_id ? `/api/multimodal/file/${item.file_id}` : '');

function MathText({ children }: { children: unknown }) {
  return <Markdown content={String(children || '')} />;
}

const INTERNAL_TEXT_RE = /See extracted_questions|per-question answers|extracted_questions|raw_structured_result|source_evidence/i;

const isUseful = (value: unknown) => {
  const text = String(value ?? '').trim();
  return Boolean(text) && !/^(null|undefined|\.{1,}|…+)$/i.test(text) && !INTERNAL_TEXT_RE.test(text);
};

const safeText = (value: unknown) => (isUseful(value) ? String(value).trim() : '');

const questionText = (item: any) =>
  safeText(item?.question_text || item?.stem || item?.question || item?.text || item?.content || item?.title);

function QuestionDetail({ item, idx }: { item: any; idx: number }) {
  const no = item?.index || item?.question_index || idx + 1;
  const text = questionText(item);
  const options = Array.isArray(item?.options) ? item.options.filter(isUseful) : [];
  const points = Array.isArray(item?.knowledge_points || item?.possible_knowledge_points)
    ? (item.knowledge_points || item.possible_knowledge_points).filter(isUseful)
    : [];
  return (
    <li>
      <div className="font-medium text-surface-700">第 {no} 题</div>
      <div><MathText>{text || `第 ${no} 题题干识别不完整`}</MathText></div>
      {options.length > 0 && <div>选项：<MathText>{options.join('；')}</MathText></div>}
      {isUseful(item?.answer || item?.correct_answer) && <div>答案：<MathText>{item.answer || item.correct_answer}</MathText></div>}
      {points.length > 0 && <div>知识点：{points.join('、')}</div>}
      {item?.needs_manual_review && <div className="text-amber-700">这一题有识别不确定项</div>}
    </li>
  );
}

function humanizeReviewField(value: unknown) {
  const text = String(value || '');
  const cardMatch = text.match(/^cards\[(\d+)\]\.(front|back|answer)$/);
  if (cardMatch) {
    const idx = Number(cardMatch[1]) + 1;
    return `第${idx}张卡片${cardMatch[2] === 'front' ? '问题' : '答案'}可能缺失或不完整`;
  }
  const labels: Record<string, string> = {
    question_text: '题干',
    answer: '答案',
    formula_text: '公式',
    detected_text: '识别文本',
    options: '选项',
    source_evidence: '证据来源',
  };
  return labels[text] || text;
}

function ImageAttachmentPreview({ item }: { item: ChatAttachment }) {
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  const url = attachmentUrl(item);
  if (!url) return null;
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="mt-2 block text-left">
        {failed ? (
          <span className="block rounded-xl border border-white/30 bg-white/10 px-3 py-2 text-xs">
            图片预览加载失败，点击查看原始文件
          </span>
        ) : (
          <span className="inline-flex flex-col gap-1">
            {item.reused_from_last && <span className="text-[11px] opacity-80">引用当前图片</span>}
            <img
              src={url}
              onError={() => setFailed(true)}
              className="max-h-44 w-40 rounded-xl border border-white/30 object-cover"
              loading="lazy"
            />
          </span>
        )}
      </button>
      {open && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-6" onClick={() => setOpen(false)}>
          <div className="relative max-h-full max-w-5xl" onClick={(e) => e.stopPropagation()}>
            <button className="absolute -right-3 -top-3 rounded-full bg-white p-1 text-surface-600 shadow" onClick={() => setOpen(false)}>
              <XCircle size={22} />
            </button>
            {failed ? (
              <a href={url} target="_blank" rel="noreferrer" className="rounded-xl bg-white px-4 py-3 text-sm text-primary-600">
                打开原始文件
              </a>
            ) : (
              <img src={url} className="max-h-[82vh] max-w-[88vw] rounded-2xl bg-white object-contain" />
            )}
          </div>
        </div>
      )}
    </>
  );
}

function HistoryPopover({ sessions, currentSessionId, onSelect, onDelete, onRename, onNew, onClose }: {
  sessions: any[]; currentSessionId: string;
  onSelect: (id: string) => void; onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void; onNew: () => void; onClose: () => void;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const popRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (popRef.current && !popRef.current.contains(e.target as Node)) onClose(); };
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h);
  }, [onClose]);
  useEffect(() => { if (editingId) inputRef.current?.focus(); }, [editingId]);
  const sorted = sessions.slice().sort((a: any, b: any) => (b.updatedAt || 0) - (a.updatedAt || 0));
  return (
    <div ref={popRef} className="absolute left-0 top-14 w-72 bg-white rounded-xl shadow-elevated border border-gray-200 z-50 animate-fade-in overflow-hidden">
      <div className="px-3 py-2 border-b border-gray-100 flex items-center justify-between">
        <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">对话记录</span>
        <button onClick={onNew} className="text-[10px] text-brand-600 hover:text-brand-700 font-medium">+ 新建</button>
      </div>
      <div className="max-h-[320px] overflow-y-auto">
        {sorted.length === 0 ? <p className="text-xs text-gray-400 py-6 text-center">暂无对话</p> : sorted.map((ses: any) => {
          const active = ses.id === currentSessionId; const isEditing = editingId === ses.id;
          return (
            <div key={ses.id} onClick={() => { if (!isEditing) onSelect(ses.id); }}
              onDoubleClick={(e) => { e.stopPropagation(); setEditingId(ses.id); setEditTitle(ses.title || ''); }}
              className={`w-full text-left transition-colors flex items-stretch group cursor-pointer ${active ? 'bg-brand-50' : 'hover:bg-gray-50'}`}
              style={{ borderLeft: active ? '3px solid #3b82f6' : '3px solid transparent' }}>
              <div className="flex-1 min-w-0 px-3 py-2.5">
                {isEditing ? (
                  <input ref={inputRef} value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { onRename(ses.id, editTitle); setEditingId(null); } if (e.key === 'Escape') setEditingId(null); }}
                    onBlur={() => { if (editTitle.trim()) onRename(ses.id, editTitle); setEditingId(null); }}
                    onClick={(e) => e.stopPropagation()}
                    className="w-full text-[11px] px-1.5 py-0.5 bg-white border border-brand-300 rounded outline-none focus:ring-1 focus:ring-brand-400" placeholder="输入名称…" />
                ) : (
                  <>
                    <p className={`text-[12px] truncate ${active ? 'text-gray-800 font-semibold' : 'text-gray-600'}`}>{ses.title || '新对话'}</p>
                    <p className="text-[9px] text-gray-400 mt-0.5">{timeAgo(ses.updatedAt || ses.createdAt)}</p>
                  </>
                )}
              </div>
              <button onClick={(e) => { e.stopPropagation(); onDelete(ses.id); }}
                className="flex-shrink-0 w-7 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity text-gray-300 hover:text-red-500 hover:bg-red-50" title="删除">
                <XCircle className="w-3 h-3" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MultimodalResultView({ result }: { result: ChatMessage['multimodalResult'] }) {
  const data = result?.result || {};
  const publicContent = safeText(result?.content);
  const publicContentUrl = safeText(result?.content_url);
  const trace = result?.trace || result?.workflow_trace || {};
  const sessionId = useChatStore((s) => s.currentSessionId);
  const [saveState, setSaveState] = useState('');
  const [candidateState, setCandidateState] = useState('');
  const vision = data.vision_result || data.understanding || (data.detected_text || data.summary ? data : null);
  const explanation = data.explanation || (data.explanation_steps ? data : null);
  const wrong = data.wrong_question_analysis || (data.mistake_reason ? data : null);
  const note = data.note_summary || (data.key_points ? data : null);
  const mindmap = data.mindmap || data;
  const diagram = mindmap?.markdown || mindmap?.mermaid || data.markdown || data.mermaid;
  const rawFlashcards = data.flashcards || data.cards || [];
  const flashcards = Array.isArray(rawFlashcards)
    ? rawFlashcards.filter((card: any) => isUseful(card?.front) && isUseful(card?.back) && card.front !== card.back)
    : [];
  const path = data.recommended_path || [];
  const variants = data.optional_variants || data.variants || [];
  const candidates = data.knowledge_candidates || [];
  const warnings = result?.warnings || [];
  const extractedQuestions = Array.isArray(data.extracted_questions)
    ? data.extracted_questions
    : Array.isArray(vision?.extracted_questions)
      ? vision.extracted_questions
      : [];
  const needsReview = data.needs_manual_review || result?.status === 'needs_manual_review';
  const isExplanationTask = result?.task_type === 'explain_image_question' || result?.task_type === 'solve_image_question';
  const isMindmapTask = result?.task_type === 'image_to_mindmap';
  const isResourceBundleTask = result?.task_type === 'image_to_resource_bundle';
  const reviewReasons = Array.isArray(data.review_reasons) ? data.review_reasons.filter(Boolean) : [];
  const uncertainQuestionIndices = Array.isArray(data.uncertain_question_indices) ? data.uncertain_question_indices.filter(Boolean) : [];
  const uncertainFields = Array.isArray(data.uncertain_fields) ? data.uncertain_fields.filter(Boolean) : [];
  const uncertainSpans = Array.isArray(data.uncertain_spans) ? data.uncertain_spans.filter(Boolean) : [];
  const [reviewDismissed, setReviewDismissed] = useState(false);
  const imageSourceLabel = (() => {
    const source = String(trace.image_context_source || data.image_context_source || '');
    if (source === 'current_attachment') return '当前上传图片';
    if (source === 'last_uploaded_image') return '当前选中图片';
    if (source === 'last_vision_result') return '已缓存图片识别结果';
    return '图片识别结果';
  })();

  const saveResource = async () => {
    setSaveState('保存中...');
    try {
      const res = await saveMultimodalResource({ sessionId, task_type: result?.task_type, result: data });
      setSaveState(res.saved ? '已保存为学习资源，待确认' : '保存失败');
    } catch {
      setSaveState('保存失败');
    }
  };

  const prepareCandidates = async () => {
    setCandidateState('生成中...');
    try {
      const res = await prepareKnowledgeCandidates({ result: data, knowledge_candidates: candidates });
      setCandidateState(`已生成 ${res.candidates?.length || 0} 条知识候选，待确认`);
    } catch {
      setCandidateState('生成失败');
    }
  };

  const list = (items: any[]) => items.filter(Boolean).map((item, idx) => <li key={idx}><MathText>{String(item)}</MathText></li>);
  const ReviewNotice = () => {
    if (reviewDismissed || (!needsReview && warnings.length === 0)) return null;
    const body = (
      <div className="space-y-1">
        {reviewReasons.map((item: string, idx: number) => <div key={`reason-${idx}`}>{item}</div>)}
        {uncertainQuestionIndices.length > 0 && <div>涉及题号：{uncertainQuestionIndices.join('、')}</div>}
        {uncertainFields.length > 0 && <div>涉及字段：{uncertainFields.map(humanizeReviewField).join('、')}</div>}
        {uncertainSpans.length > 0 && <div>可疑片段：{uncertainSpans.join('、')}</div>}
        {warnings.map((item, idx) => <div key={`warning-${idx}`}>{String(item).replace(/cards\[(\d+)\]\.back/g, (_m, n) => `第${Number(n) + 1}张卡片答案`)}</div>)}
        <div className="pt-1 text-amber-700">
          {data.can_continue === false ? '建议重新上传更清晰图片后再继续。' : '这些地方可能识别不完整，但不影响继续学习。'}
        </div>
        <div className="flex gap-2 pt-1">
          <button onClick={() => setReviewDismissed(true)} className="rounded-lg bg-white px-2 py-1 text-amber-700 border border-amber-200">我知道了</button>
          {data.can_continue !== false && <button onClick={() => setReviewDismissed(true)} className="rounded-lg bg-amber-100 px-2 py-1 text-amber-800">继续使用当前识别结果</button>}
        </div>
      </div>
    );
    if (data.can_continue !== false) {
      return (
        <details className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          <summary className="cursor-pointer font-semibold">以下内容可能需要你确认</summary>
          <div className="mt-2">{body}</div>
        </details>
      );
    }
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
        <div className="mb-1 font-semibold">以下内容需要你确认</div>
        {body}
      </div>
    );
  };

  if (isExplanationTask) {
    return (
      <div className="mt-3 space-y-2">
        <details className="rounded-xl border border-surface-200 bg-white/70 p-3 text-xs text-surface-600">
          <summary className="cursor-pointer font-medium text-surface-700">查看识别详情</summary>
          <div className="mt-2 space-y-1">
            {isUseful(vision?.summary) && <div>摘要：{vision.summary}</div>}
            {isUseful(vision?.question_text) && <div className="whitespace-pre-wrap">题目：{vision.question_text}</div>}
            {isUseful(vision?.detected_text) && <div className="whitespace-pre-wrap">识别文本：{vision.detected_text}</div>}
            {extractedQuestions.length > 0 && (
              <ol className="list-decimal pl-4 space-y-1">
                {extractedQuestions.map((item: any, idx: number) => <QuestionDetail key={idx} item={item} idx={idx} />)}
              </ol>
            )}
          </div>
        </details>
        <ReviewNotice />
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-3">
      {isResourceBundleTask && (
        <div className="rounded-xl border border-primary-100 bg-primary-50 p-3 text-xs text-primary-800">
          我已把这张图片整理成一份学习资源包。你可以先查看内容，也可以保存到资源库；其中提取出的知识点会作为“待确认知识候选”，不会直接写入正式知识库。
        </div>
      )}
      {!isMindmapTask && vision && (
        <div className="rounded-xl border border-surface-200 bg-white p-3 text-xs text-surface-600 space-y-1">
          <div className="font-semibold text-surface-700">图片理解</div>
          {isUseful(vision.image_type) && vision.image_type !== 'unknown' && <div>类型：{vision.image_type}</div>}
          {isUseful(vision.subject) && <div>学科：{vision.subject}</div>}
          {isUseful(vision.summary) && <div>摘要：{vision.summary}</div>}
          {isUseful(vision.question_text) && <div>题目：{vision.question_text}</div>}
          {isUseful(vision.detected_text) && <div className="whitespace-pre-wrap">识别文本：{vision.detected_text}</div>}
          {Array.isArray(vision.possible_knowledge_points) && vision.possible_knowledge_points.length > 0 && (
            <div>知识点：{vision.possible_knowledge_points.join('、')}</div>
          )}
          {typeof vision.confidence === 'number' && <div>置信度：{Math.round(vision.confidence * 100)}%</div>}
        </div>
      )}
      {explanation && (
        <div className="rounded-xl border border-surface-200 bg-white p-3 text-xs text-surface-600 space-y-2">
          <div className="font-semibold text-surface-700">题目讲解</div>
          {explanation.question_text && <div className="whitespace-pre-wrap">题目：{explanation.question_text}</div>}
          {Array.isArray(explanation.knowledge_points) && <div>知识点：{explanation.knowledge_points.join('、')}</div>}
          {Array.isArray(explanation.explanation_steps) && <ol className="list-decimal pl-4 space-y-1">{list(explanation.explanation_steps)}</ol>}
          {explanation.answer && <div>答案：{explanation.answer}</div>}
          {Array.isArray(explanation.common_mistakes) && explanation.common_mistakes.length > 0 && <div>常见错误：{explanation.common_mistakes.join('、')}</div>}
        </div>
      )}
      {wrong && (
        <div className="rounded-xl border border-surface-200 bg-white p-3 text-xs text-surface-600 space-y-1">
          <div className="font-semibold text-surface-700">错题分析</div>
          {wrong.mistake_type && <div>错误类型：{wrong.mistake_type}</div>}
          {wrong.mistake_reason && <div>错因：{wrong.mistake_reason}</div>}
          {Array.isArray(wrong.weak_knowledge_points) && <div>薄弱点：{wrong.weak_knowledge_points.join('、')}</div>}
          {Array.isArray(wrong.remediation_plan) && <ul className="list-disc pl-4">{list(wrong.remediation_plan)}</ul>}
          {Array.isArray(wrong.similar_practice_suggestions) && wrong.similar_practice_suggestions.length > 0 && <div>练习建议：{wrong.similar_practice_suggestions.join('、')}</div>}
        </div>
      )}
      {note && (
        <div className="rounded-xl border border-surface-200 bg-white p-3 text-xs text-surface-600 space-y-1">
          <div className="font-semibold text-surface-700">笔记总结</div>
          {note.title && <div className="font-medium">{note.title}</div>}
          {note.summary && <div>{note.summary}</div>}
          {Array.isArray(note.key_points) && note.key_points.length > 0 && <ul className="list-disc pl-4">{list(note.key_points)}</ul>}
          {Array.isArray(note.formulas) && note.formulas.length > 0 && <div>公式：{note.formulas.join('、')}</div>}
          {Array.isArray(note.definitions) && note.definitions.length > 0 && <div>定义：{note.definitions.join('、')}</div>}
          {Array.isArray(note.pitfalls) && note.pitfalls.length > 0 && <div>易错点：{note.pitfalls.join('、')}</div>}
          {Array.isArray(note.next_actions) && note.next_actions.length > 0 && <div>下一步：{note.next_actions.join('、')}</div>}
        </div>
      )}
      {diagram && (
        <div className="rounded-xl border border-surface-200 bg-white p-3 overflow-x-auto">
          {isMindmapTask && (
            <div className="mb-2 text-xs text-surface-500">
              基于图片：{imageSourceLabel}
              {trace.selected_image_attachment_id ? ` · ${String(trace.selected_image_attachment_id).slice(-24)}` : ''}
            </div>
          )}
          <MarkmapDiagram definition={diagram} />
          <details className="mt-2 text-xs text-surface-500">
            <summary>查看 Markdown</summary>
            <pre className="mt-2 whitespace-pre-wrap">{diagram}</pre>
          </details>
        </div>
      )}
      {Array.isArray(flashcards) && flashcards.length > 0 && (
        <div className="grid gap-2">
          {flashcards.slice(0, 6).map((card: any, idx: number) => (
            <details key={idx} className="rounded-xl border border-surface-200 bg-white p-3 text-xs">
              <summary className="cursor-pointer list-none">
                <div className="font-semibold text-surface-700"><MathText>{card.front || `第 ${idx + 1} 张卡片`}</MathText></div>
                <div className="mt-1 text-surface-400">{card.knowledge_point || '知识点待确认'} · {card.difficulty || 'medium'} · {card.card_type || 'review'}</div>
              </summary>
              <div className="mt-2 rounded-lg bg-surface-50 p-2 text-surface-600"><MathText>{card.back || '答案待补充'}</MathText></div>
            </details>
          ))}
          {flashcards.length > 6 && (
            <details className="rounded-xl border border-surface-200 bg-white p-3 text-xs">
              <summary className="cursor-pointer text-surface-600">还有 {flashcards.length - 6} 张卡片，点击展开</summary>
              <div className="mt-2 grid gap-2">
                {flashcards.slice(6).map((card: any, idx: number) => (
                  <div key={idx} className="rounded-lg bg-surface-50 p-2">
                    <div className="font-medium text-surface-700"><MathText>{card.front}</MathText></div>
                    <div className="mt-1 text-surface-500"><MathText>{card.back}</MathText></div>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
      {Array.isArray(path) && path.length > 0 && (
        <div className="rounded-xl border border-surface-200 bg-white p-3 text-xs text-surface-600 space-y-2">
          <div className="font-semibold text-surface-700">学习计划</div>
          {path.map((stage: any, idx: number) => (
            <div key={idx} className="border-l-2 border-primary-200 pl-3">
              <div className="font-medium text-surface-700">{stage.stage_title}</div>
              {stage.objective && <div>{stage.objective}</div>}
              {Array.isArray(stage.knowledge_points) && <div>知识点：{stage.knowledge_points.join('、')}</div>}
              {stage.estimated_minutes && <div>{stage.estimated_minutes} 分钟</div>}
            </div>
          ))}
        </div>
      )}
      {Array.isArray(variants) && variants.length > 0 && (
        <div className="rounded-xl border border-surface-200 bg-white p-3 text-xs text-surface-600 space-y-2">
          <div className="font-semibold text-surface-700">变式题</div>
          {variants.map((item: any, idx: number) => (
            <details key={idx} className="rounded-lg bg-surface-50 p-2">
              <summary className="cursor-pointer font-medium">{item.question}</summary>
              <div className="mt-2">答案：{item.answer}</div>
              <div className="mt-1">{item.explanation}</div>
            </details>
          ))}
        </div>
      )}
      {Array.isArray(data.image_urls) && data.image_urls.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {data.image_urls.map((url: string) => <img key={url} src={url} className="max-h-48 rounded-xl border border-surface-200" />)}
        </div>
      )}
      {data.script && (
        <div className="rounded-xl border border-surface-200 bg-white p-3 text-xs whitespace-pre-wrap">{data.script}</div>
      )}
      {publicContent && !diagram && publicContent !== data.script && (
        <div className="rounded-xl border border-surface-200 bg-white p-3 text-xs whitespace-pre-wrap"><MathText>{publicContent}</MathText></div>
      )}
      {publicContentUrl && (
        <a href={publicContentUrl} target="_blank" rel="noreferrer" className="inline-flex rounded-lg border border-primary-200 bg-white px-3 py-2 text-xs font-medium text-primary-700 hover:bg-primary-50">打开生成内容</a>
      )}
      {(data.resource_save_candidate || candidates.length > 0) && (
        <div className="rounded-xl border border-surface-200 bg-white p-3 text-xs text-surface-600 space-y-2">
          <div className="font-semibold text-surface-700">资源与知识候选</div>
          {data.resource_save_candidate && <button onClick={saveResource} className="px-3 py-1.5 rounded-lg bg-primary-600 text-white">保存为学习资源</button>}
          {candidates.length > 0 && <button onClick={prepareCandidates} className="ml-2 px-3 py-1.5 rounded-lg border border-surface-200">生成知识候选</button>}
          {saveState && <div>{saveState}</div>}
          {candidateState && <div>{candidateState}</div>}
          {candidates.length > 0 && <div>知识候选：{candidates.map((item: any) => item.knowledge_point).filter(Boolean).join('、')}（待确认）</div>}
        </div>
      )}
      <ReviewNotice />
    </div>
  );
}

const MessageBubble = memo(function MessageBubble({ msg, onClarificationSelect }: { msg: ChatMessage; onClarificationSelect?: (prompt: string) => void }) {
  const isUser = msg.role === 'user'; const [copied, setCopied] = useState(false);
  const [thinkingExpanded, setThinkingExpanded] = useState(true);
  const hasThinking = !isUser && msg.reasoningContent && msg.reasoningContent.trim().length > 0;
  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex gap-3 max-w-[85%] ${isUser ? 'flex-row-reverse' : ''}`}>
        {!isUser && (
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center flex-shrink-0 mt-0.5">
            <Sparkles size={13} className="text-white" />
          </div>
        )}
        <div className={`min-w-0 group ${isUser ? 'flex flex-col items-end' : ''}`}>
          {/* ── DeepSeek-style thinking section ── */}
          {hasThinking && (
            <div className="mb-2">
              <button
                onClick={() => setThinkingExpanded(!thinkingExpanded)}
                className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-700 transition-colors mb-1"
              >
                <svg className={`w-3 h-3 transition-transform ${thinkingExpanded ? 'rotate-90' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
                <span>{msg.streaming ? '正在思考...' : '思考过程'}</span>
                {msg.streaming && <Loader2 size={10} className="animate-spin" />}
              </button>
              {thinkingExpanded && (
                <div className="border-l-2 border-gray-300 pl-3 py-1 text-xs text-gray-500 leading-relaxed whitespace-pre-wrap">
                  {msg.reasoningContent}
                  {msg.streaming && <span className="inline-block w-1.5 h-3 bg-gray-400 animate-pulse rounded ml-0.5 align-text-bottom" />}
                </div>
              )}
            </div>
          )}
          {/* ── Main content bubble ── */}
          <div className={`text-sm leading-relaxed ${
            isUser
              ? 'bg-[#2f2f2f] text-white px-4 py-2.5 rounded-3xl'
              : 'text-gray-700 px-0.5'
          }`}>
            {isUser ? (
              <div>
                <p className="whitespace-pre-wrap">{msg.content}</p>
                {msg.attachments?.map((item: ChatAttachment) => <ImageAttachmentPreview key={item.file_id || attachmentUrl(item)} item={item} />)}
              </div>
            ) : (
              <div className="prose prose-sm max-w-none [&_p]:mb-2 [&_p:last-child]:mb-0 [&_ul]:pl-4 [&_ol]:pl-4 [&_li]:mb-1 [&_pre]:text-xs [&_code]:text-xs [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm [&_table]:text-xs [&_th]:border [&_th]:border-gray-300 [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-gray-300 [&_td]:px-2 [&_td]:py-1">
                {(() => {
                  const content = msg.content || '';
                  const modePick = parseModePickTag(content);
                  const cleanContent = stripModePickTag(content);
                  return (
                    <>
                      {cleanContent ? <Markdown content={cleanContent} /> : msg.streaming ? <span className="text-gray-400 italic">...</span> : null}
                      {modePick && !msg.streaming && (
                        <ModePicker options={modePick.options} course={modePick.course} defaultMode={modePick.defaultMode} />
                      )}
                    </>
                  );
                })()}
                {msg.multimodalResult && <MultimodalResultView result={msg.multimodalResult} />}
                {msg.streaming && msg.content && (
                  <span className="inline-block w-1.5 h-4 bg-gray-400 animate-pulse rounded ml-0.5 align-text-bottom" />
                )}
                {msg.error && (
                  <div className="mt-2 p-3 bg-red-50 border border-red-100 rounded-xl flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                    <div><p className="text-xs text-red-600 font-medium">生成失败</p><p className="text-xs text-red-400 mt-0.5">{msg.error}</p></div>
                  </div>
                )}
                {msg.isClarification && onClarificationSelect && <ChatClarification onSelect={onClarificationSelect} />}
              </div>
            )}
          </div>
          {/* ── 推荐操作按钮 ── */}
          {!isUser && !msg.streaming && msg.suggestedActions && msg.suggestedActions.length > 0 && onClarificationSelect && (
            <div className="mt-3 flex flex-col gap-1.5">
              {msg.suggestedActions.map((action, idx: number) => (
                <button
                  key={idx}
                  onClick={() => onClarificationSelect(action.prompt)}
                  className="px-3 py-1.5 rounded-full text-xs font-medium border border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50 hover:text-gray-800 transition-all"
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}
          {!isUser && msg.content && !msg.streaming && (
            <button
              onClick={() => { navigator.clipboard.writeText(msg.content); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
              className="inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded-md text-[10px] text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            >
              {copied ? <><Check className="w-3 h-3" />已复制</> : <><Copy className="w-3 h-3" />复制</>}
            </button>
          )}
        </div>
      </div>
    </div>
  );
});

function AgentPipelineProgress({ progress, onRetry, onNavigate }: { progress: GenerationProgress; onRetry?: () => void; onNavigate?: (path: string) => void }) {
  const [elapsed, setElapsed] = useState(0); const isError = !!progress.error; const [doneV, setDoneV] = useState(false); const isDone = progress.done && !progress.error;
  // 使用动态进度条 —— 根据实际运行的 Agent 构建，不再硬编码 5 阶段
  const pipeline = useChatStore((s) => s.progressPipelineSteps.length > 0 ? s.progressPipelineSteps : EMPTY_PIPELINE);
  const currentIdx = pipeline.findIndex(s => s.key === (progress.agentName || ''));
  useEffect(() => { if (isDone) { const t = setTimeout(() => setDoneV(true), 1500); return () => clearTimeout(t); } setDoneV(false); }, [isDone]);
  useEffect(() => { if (isDone || isError) return; const t = setInterval(() => setElapsed(v => v + 1), 1000); return () => clearInterval(t); }, [isDone, isError]);
  if (isError) return <div className="px-4 py-4 bg-error-50 border border-error-100 rounded-2xl shadow-soft animate-fade-in-up space-y-3 max-w-[82%] ml-12"><div className="flex items-start gap-2.5"><div className="w-6 h-6 rounded-full bg-error-100 flex items-center justify-center"><XCircle className="w-4 h-4 text-error-500" /></div><div className="flex-1"><p className="text-sm font-semibold text-error-700">生成失败</p><p className="text-xs text-error-500 mt-1">{progress.error}</p>{onRetry && <button onClick={onRetry} className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 bg-error-100 hover:bg-error-200 rounded-lg text-xs font-medium text-error-700"><RefreshCw className="w-3.5 h-3.5" />重新生成</button>}</div></div></div>;
  if (isDone) { return <div className="flex items-center gap-2.5 px-4 py-2 text-sm text-success-700"><Check className="w-4 h-4 text-success-500" /><span>生成完成</span></div>; }
  // 无 pipeline 步骤时显示简单 spinner
  if (pipeline.length === 0) return <div className="px-4 py-4 bg-white border border-surface-200 rounded-2xl shadow-soft animate-fade-in-up max-w-[82%] ml-12"><div className="flex items-center gap-2.5"><div className="w-5 h-5 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" /><span className="text-sm font-semibold text-surface-800">{progress.stage || '正在处理...'}</span><span className="text-xs text-primary-600 font-medium ml-auto tabular-nums">{Math.round(progress.progress)}%</span></div><div className="h-1.5 bg-surface-100 rounded-full overflow-hidden mt-3"><div className="h-full bg-gradient-to-r from-primary-500 to-accent-500 rounded-full transition-all duration-700 ease-out" style={{ width: `${Math.round(progress.progress)}%` }} /></div></div>;
  return <div className="px-4 py-4 bg-white border border-surface-200 rounded-2xl shadow-soft animate-fade-in-up space-y-3 max-w-[82%] ml-12"><div className="flex items-center gap-2.5"><div className="w-5 h-5 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" /><span className="text-sm font-semibold text-surface-800">{progress.stage || '多智能体协同处理中'}</span><span className="text-xs text-primary-600 font-medium ml-auto tabular-nums">{Math.round(progress.progress)}%</span></div><div className="flex items-center gap-1">{pipeline.map((step, idx) => { const done = idx < currentIdx; const cur = idx === currentIdx; return <div key={step.key} className="flex items-center gap-1 flex-1 min-w-0"><div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${done ? 'bg-success-100 ring-2 ring-success-200' : cur ? 'bg-primary-100 ring-2 ring-primary-300' : 'bg-surface-50 ring-2 ring-surface-100'}`}>{done ? <Check className="w-3 h-3 text-success-600" /> : cur ? <div className="w-2.5 h-2.5 rounded-full bg-primary-500 animate-pulse" /> : <div className="w-2 h-2 rounded-full bg-surface-300" />}</div>{idx < pipeline.length - 1 && <div className={`flex-1 h-0.5 rounded-full ${done ? 'bg-success-300' : cur ? 'bg-surface-200' : 'bg-surface-100'}`} />}</div>; })}</div><div className="h-1.5 bg-surface-100 rounded-full overflow-hidden"><div className="h-full bg-gradient-to-r from-primary-500 to-accent-500 rounded-full transition-all duration-700 ease-out" style={{ width: `${Math.round(progress.progress)}%` }} /></div></div>;
}

const ModeToggleBar = memo(function ModeToggleBar() {
  const chatMode = useChatStore((s) => s.chatMode);
  return (
    <div className="flex-shrink-0 px-4 pt-2 pb-1 w-full min-w-0">
      <div className="max-w-[48rem] mx-auto flex items-center gap-1.5 rounded-xl bg-surface-100 p-1 w-fit">
        <button
          onClick={() => useChatStore.getState().setChatMode('free')}
          className={`rounded-lg px-4 py-1.5 text-xs font-medium transition-colors ${
            chatMode === 'free' ? 'bg-white text-surface-800 shadow-sm' : 'text-surface-500 hover:text-surface-700'
          }`}
        >自由学习</button>
        <button
          onClick={() => useChatStore.getState().setChatMode('planning')}
          className={`rounded-lg px-4 py-1.5 text-xs font-medium transition-colors ${
            chatMode === 'planning' ? 'bg-white text-surface-800 shadow-sm' : 'text-surface-500 hover:text-surface-700'
          }`}
        >规划学习</button>
      </div>
    </div>
  );
});

export default function ChatPage() {
  const loc = useLocation(); const nav = useNavigate();
  const isParent = getCurrentLearner()?.role === 'parent';

  if (isParent) {
    return (
      <div className="h-[calc(100vh-160px)] flex items-center justify-center animate-fade-in">
        <div className="text-center max-w-md">
          <div className="w-16 h-16 rounded-2xl bg-surface-100 dark:bg-surface-700 flex items-center justify-center mx-auto mb-4">
            <MessageCircle className="w-8 h-8 text-surface-400" />
          </div>
          <h3 className="font-display text-lg font-semibold text-surface-800 dark:text-gray-100 mb-2">只读模式</h3>
          <p className="text-surface-500 dark:text-gray-400 text-sm">家长账户无法使用智能对话功能。<br/>请前往学习分析、画像或资源库查看孩子的学习数据。</p>
        </div>
      </div>
    );
  }
  const initialMessage = (loc.state as any)?.initialMessage;
  const initialChatMode = (loc.state as any)?.chatMode;
  const {
    messages,
    isStreaming,
    agentProgress,
    lastDebugInfo,
    currentSessionId,
    setLoading,
    lastImageAttachment,
    imageAttachmentHistory,
    selectedImageAttachmentId,
    selectImageAttachment,
    searchEnabled,
    deepThinkEnabled,
    chatMode,
  } = useChatStore() as any;
  const { send, abort } = useStreamChat();
  const setSearchEnabled = (v: boolean) => useChatStore.getState().setSearchEnabled(v);
  const setDeepThinkEnabled = (v: boolean) => useChatStore.getState().setDeepThinkEnabled(v);
  // Closed-loop assessment notifications — poll every 30s, pause during streaming
  useNotificationPoller(currentSessionId || '', !isStreaming);
  const [messagesLoaded, setMessagesLoaded] = useState(false); const [menuOpen, setMenuOpen] = useState(false); const [historyOpen, setHistoryOpen] = useState(false);
  const [selectedImage, setSelectedImage] = useState<{ file: File; preview: string } | null>(null);
  const [imageContextDisabled, setImageContextDisabled] = useState(false);
  const [imagePickerOpen, setImagePickerOpen] = useState(false);
  const [quickCommands, setQuickCommands] = useState<QuickCommand[]>(DEFAULT_QUICK_COMMANDS);
  const scrollRef = useRef<HTMLDivElement>(null); const inputRef = useRef<HTMLTextAreaElement>(null); const bottomRef = useRef<HTMLDivElement>(null); const fileRef = useRef<HTMLInputElement>(null);
  const userScrolledUpRef = useRef(false);

  // Fetch dynamic quick commands and agents on mount
  useEffect(() => {
    getQuickCommands().then(res => { if (res.commands?.length) setQuickCommands(res.commands); }).catch(() => {});
  }, []);
  useEffect(() => () => { if (selectedImage) URL.revokeObjectURL(selectedImage.preview); }, [selectedImage]);
  const selectedReferenceAttachment = (imageAttachmentHistory || []).find((item: ChatAttachment) => imageAttachmentKey(item) === selectedImageAttachmentId) || lastImageAttachment;
  const referencesLastImage = !selectedImage && Boolean(selectedReferenceAttachment) && IMAGE_REFERENCE_RE.test(inputRef.current?.value || '');
  const willUseLastImage = referencesLastImage && !imageContextDisabled;
  useEffect(() => {
    if (!referencesLastImage) setImageContextDisabled(false);
    if (!referencesLastImage) setImagePickerOpen(false);
  }, [referencesLastImage]);

  const scrollToBottom = useCallback((force = false) => {
    if (force) userScrolledUpRef.current = false;
    if (force || !userScrolledUpRef.current) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, []);
  // Auto-scroll only when user hasn't explicitly scrolled up
  useEffect(() => {
    if (!userScrolledUpRef.current) scrollToBottom();
  }, [messages, agentProgress, scrollToBottom]);
  // Track user scroll intent
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const h = () => {
      const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (distFromBottom <= 80) {
        userScrolledUpRef.current = false;
      } else {
        userScrolledUpRef.current = true;
      }
    };
    el.addEventListener('scroll', h, { passive: true });
    return () => el.removeEventListener('scroll', h);
  });
  useEffect(() => { if (useChatStore.getState().messages.length > 0) { setMessagesLoaded(true); setLoading(false); return; } setMessagesLoaded(false); let cancelled = false; (async () => { setLoading(true); try { const res = await getSessionMessages(currentSessionId); if (!cancelled && res.messages?.length) useChatStore.setState({ messages: res.messages }); } catch {} finally { if (!cancelled) { setMessagesLoaded(true); setLoading(false); } } })(); return () => { cancelled = true; }; }, [currentSessionId]);
  useEffect(() => { if (initialMessage && messages.length === 0 && messagesLoaded) send(initialMessage); }, [initialMessage, messagesLoaded]);
  useEffect(() => { if (initialChatMode) useChatStore.getState().setChatMode(initialChatMode); }, [initialChatMode]);

  // Recovery: check for orphaned streaming messages on mount (Bug 3 fix)
  useEffect(() => {
    if (!messagesLoaded) return;
    const orphanSessionId = detectOrphanedStreaming();
    if (!orphanSessionId) return;

    // Clear marker immediately to prevent re-recovery from parallel tabs
    writeStorageItem(runtimeStorageKeys.pendingGeneration, '');

    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;

    const applyRecovery = (reply: { content: string } | null | undefined) => {
      if (cancelled) return;
      const store = useChatStore.getState();
      store.setAgentProgress(null);
      const msgs = [...store.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === 'assistant' && last.streaming) {
        if (reply?.content) {
          msgs[msgs.length - 1] = { ...last, content: reply.content, streaming: false, error: undefined };
        } else {
          msgs[msgs.length - 1] = { ...last, streaming: false, error: undefined };
        }
        useChatStore.setState({ messages: msgs });
      }
    };

    const poll = () => {
      if (cancelled) return;
      recoverGeneration(orphanSessionId).then(res => {
        if (cancelled) return;
        if (res?.reply?.content) {
          // Got the completed reply
          applyRecovery(res.reply);
        } else if (res?.generating) {
          // Still generating — restore progress bar and poll faster
          if (res.currentProgress) {
            useChatStore.getState().setAgentProgress(res.currentProgress);
          }
          pollTimer = setTimeout(poll, 1000);
        } else {
          // Generation ended with no reply
          applyRecovery(null);
        }
      }).catch(() => {
        if (cancelled) return;
        pollTimer = setTimeout(poll, 2000);
      });
    };

    // Start recovery polling
    poll();

    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
      // Clean up progress if component unmounts during recovery
      if (cancelled) useChatStore.getState().setAgentProgress(null);
    };
  }, [messagesLoaded]);

  const handleImageChange = (file: File | undefined) => {
    if (!file || !/^image\/(png|jpe?g|webp)$/.test(file.type)) return;
    if (selectedImage) URL.revokeObjectURL(selectedImage.preview);
    setSelectedImage({ file, preview: URL.createObjectURL(file) });
    setImageContextDisabled(false);
  };
  const handleSend = async () => {
    const text = (inputRef.current?.value || '').trim();
    if ((!text && !selectedImage) || isStreaming) return;
    const finalText = text || '识别这张图片';
    const attachments = selectedImage ? [await uploadMultimodalImage(selectedImage.file, currentSessionId)] : [];
    send(finalText, attachments, { ignoreImageContext: referencesLastImage && imageContextDisabled });
    if (inputRef.current) inputRef.current.value = '';
    setImageContextDisabled(false);
    if (selectedImage) URL.revokeObjectURL(selectedImage.preview);
    setSelectedImage(null);
    if (fileRef.current) fileRef.current.value = '';
    inputRef.current?.focus();
  };
  const handleKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } };

  return (
    <div className="h-[calc(100vh-160px)] flex flex-col bg-white">
      {/* ── ChatGPT-style top bar ── */}
      <div className="flex items-center justify-between px-4 py-2 flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="relative">
            <button
              onClick={() => setMenuOpen(v => !v)}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors"
              title="对话记录"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <line x1="9" y1="3" x2="9" y2="21" />
              </svg>
            </button>
            {menuOpen && (
              <HistoryPopover
                sessions={useChatStore.getState().sessions}
                currentSessionId={currentSessionId}
                onSelect={async (id: string) => {
                  setMenuOpen(false);
                  useChatStore.getState().setCurrentSession(id);
                  try {
                    const res = await getSessionMessages(id);
                    if (res?.messages) useChatStore.setState({ messages: res.messages });
                  } catch { /* ignore */ }
                }}
                onDelete={(id: string) => useChatStore.getState().removeSession(id)}
                onRename={(id: string, title: string) => useChatStore.getState().renameSession(id, title)}
                onNew={() => { useChatStore.getState().newSession(); setMenuOpen(false); }}
                onClose={() => setMenuOpen(false)}
              />
            )}
          </div>
          <span className="text-sm font-semibold text-gray-700">智能学习助手</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setHistoryOpen(true)}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            title="当前对话记录"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </button>
          <button
            onClick={() => { useChatStore.getState().newSession(); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors"
          >
            <Square size={12} className="rotate-45" />新对话
          </button>
        </div>
      </div>

      <ModeToggleBar />

      {/* ── Messages area ── */}
      <div className="flex-1 overflow-hidden flex flex-col w-full min-w-0">
        <div ref={scrollRef} className="flex-1 overflow-y-scroll w-full min-w-0" style={{ overflowAnchor: 'auto' }}>
          <div className="max-w-[48rem] mx-auto w-full px-4 py-4 space-y-6">
            {(() => {
              const filtered = messages.filter((m: ChatMessage) => !m.mode || m.mode === chatMode);
              return <>
              {filtered.length === 0 && !isStreaming ? (
              chatMode === 'planning' ? (
                <div className="flex flex-col items-center justify-center min-h-[55vh] text-center px-4">
                  <div className="w-14 h-14 rounded-2xl bg-accent-50 flex items-center justify-center mb-5">
                    <Sparkles size={24} className="text-accent-500" />
                  </div>
                  <h2 className="text-xl font-semibold text-surface-800 mb-2">规划学习模式</h2>
                  <p className="text-surface-500 text-sm mb-6 max-w-md leading-relaxed">
                    我会逐步了解你的背景和目标，收集足够信息后帮你生成个性化学习路径。
                  </p>
                  <div className="flex flex-wrap justify-center gap-2 max-w-md">
                    {[
                      { label: '我想制定学习计划', key: 'plan' },
                      { label: '帮我规划数据结构', key: 'plan' },
                      { label: '我要学微积分', key: 'plan' },
                      { label: '两个月搞定英语四级', key: 'plan' },
                    ].map((cmd, i) => (
                      <button key={i}
                        onClick={() => { if (inputRef.current) inputRef.current.value = cmd.label; inputRef.current?.focus(); }}
                        className="px-4 py-2.5 bg-primary-50 border border-primary-200 rounded-xl text-sm text-primary-700 hover:bg-primary-100 transition-all"
                      >{cmd.label}</button>
                    ))}
                  </div>
                </div>
              ) : (
              /* ── Empty state: default free mode ── */
              <div className="flex flex-col items-center justify-center min-h-[55vh] text-center">
                <div className="w-16 h-16 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center mb-6 shadow-lg shadow-emerald-200">
                  <Sparkles className="w-8 h-8 text-white" />
                </div>
                <h2 className="text-2xl font-semibold text-gray-800 mb-2">今天有什么可以帮你的？</h2>
                <p className="text-gray-400 text-sm mb-8">随时问我任何学习问题</p>
                <div className="flex flex-wrap justify-center gap-2 max-w-md">
                  {quickCommands.slice(0, 4).map(cmd => (
                    <button
                      key={cmd.id}
                      onClick={() => { if (inputRef.current) inputRef.current.value = cmd.label; inputRef.current?.focus(); }}
                      className="px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-600 hover:border-gray-300 hover:bg-gray-50 transition-all"
                    >
                      {cmd.label}
                    </button>
                  ))}
                </div>
              </div>
              )
            ) : (
              <>
                {filtered.map((msg: ChatMessage) => <MessageBubble key={msg.id} msg={msg} onClarificationSelect={send} />)}
                {agentProgress && (
                  <div className="max-w-[85%] ml-10">
                    <AgentPipelineProgress
                      progress={agentProgress}
                      onRetry={() => { const lastUser = [...messages].reverse().find(m => m.role === 'user'); if (lastUser) send(lastUser.content); }}
                      onNavigate={(p: string) => nav(p)}
                    />
                  </div>
                )}
                {!isStreaming && <AgentExecutionDetails info={lastDebugInfo} />}
                {isStreaming && !agentProgress && (() => {
                  const lastMsg = messages[messages.length - 1];
                  const hasContent = lastMsg?.role === 'assistant' && (lastMsg.content || lastMsg.reasoningContent);
                  if (hasContent) return null;
                  return (
                    <div className="flex items-start gap-3">
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center flex-shrink-0">
                        <Sparkles size={13} className="text-white" />
                      </div>
                      <div className="flex items-center gap-2 text-gray-400 text-sm py-1">
                        <Loader2 size={14} className="animate-spin" />思考中...
                      </div>
                    </div>
                  );
                })()}
              </>
            )}
          </>
        })()}
        <div ref={bottomRef} />
          </div>
        </div>

        {/* ── Input area: exact ChatGPT + DeepSeek layout ── */}
        <div className="flex-shrink-0 px-4 pb-4 pt-1 w-full min-w-0">
          <div className="max-w-[48rem] mx-auto">
            {/* DeepSeek-style mode toggles — centered above input */}
            <div className="flex items-center justify-center gap-2 mb-3">
              <button
                onClick={() => setSearchEnabled(!searchEnabled)}
                disabled={isStreaming}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                  searchEnabled
                    ? 'bg-blue-50 border-blue-200 text-blue-600'
                    : 'bg-white border-gray-200 text-gray-400 hover:text-gray-500 hover:border-gray-300'
                } disabled:opacity-50`}
              >
                <Globe size={13} />
                联网搜索
              </button>
              <button
                onClick={() => setDeepThinkEnabled(!deepThinkEnabled)}
                disabled={isStreaming}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                  deepThinkEnabled
                    ? 'bg-purple-50 border-purple-200 text-purple-600'
                    : 'bg-white border-gray-200 text-gray-400 hover:text-gray-500 hover:border-gray-300'
                } disabled:opacity-50`}
              >
                <BrainCircuit size={13} />
                深度思考
              </button>
            </div>

            {/* Image preview */}
            {selectedImage && (
              <div className="mb-2 flex items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 p-2 max-w-lg mx-auto">
                <img src={selectedImage.preview} className="h-10 w-10 rounded-lg object-cover" alt="preview" />
                <div className="min-w-0 flex-1 text-xs text-gray-500 truncate">{selectedImage.file.name}</div>
                <button
                  onClick={() => { URL.revokeObjectURL(selectedImage.preview); setSelectedImage(null); if (fileRef.current) fileRef.current.value = ''; }}
                  className="p-1 rounded-lg text-gray-400 hover:bg-white hover:text-red-500 transition-colors"
                >
                  <XCircle size={14} />
                </button>
              </div>
            )}

            {/* Image reference banner */}
            {referencesLastImage && (
              <div className={`relative mb-2 flex items-center gap-2 rounded-xl border-2 p-2 text-xs max-w-lg mx-auto ${willUseLastImage ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-amber-200 bg-amber-50 text-amber-700'}`}>
                <span>{willUseLastImage ? '📎 引用图片中' : '已取消引用'}</span>
                {willUseLastImage ? (
                  <button onClick={() => setImageContextDisabled(true)} className="ml-auto px-2 py-0.5 rounded-md bg-white text-red-600 border border-red-100 text-[11px]">取消</button>
                ) : (
                  <button onClick={() => setImageContextDisabled(false)} className="ml-auto px-2 py-0.5 rounded-md bg-white text-blue-600 border border-blue-100 text-[11px]">恢复</button>
                )}
              </div>
            )}

            {/* Prompt templates */}
            {messages.length > 0 && !isStreaming && (
              <div className="mb-2">
                <PromptTemplates onSelect={(prompt: string) => { if (inputRef.current) inputRef.current.value = prompt; inputRef.current?.focus(); }} />
              </div>
            )}

            {/* ChatGPT-style pill input */}
            <div className="flex items-center gap-2 bg-[#f4f4f4] rounded-full border border-gray-200 px-3 py-2 shadow-sm focus-within:border-gray-300 focus-within:shadow-md focus-within:bg-white transition-all">
              <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => handleImageChange(e.target.files?.[0])} />
              <button
                onClick={() => fileRef.current?.click()}
                disabled={isStreaming}
                className="p-1.5 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-200/60 disabled:opacity-50 transition-colors flex-shrink-0"
                title="上传图片"
              >
                <ImagePlus size={18} />
              </button>
              <textarea
                ref={inputRef}
                defaultValue=""
                key={currentSessionId}  // 切换会话时重置
                onKeyDown={handleKeyDown}
                placeholder="输入消息..."
                rows={1}
                disabled={isStreaming}
                className="flex-1 resize-none bg-transparent text-sm text-gray-800 placeholder:text-gray-400 outline-none py-1 disabled:opacity-50"
                style={{ minHeight: '24px', maxHeight: '160px' }}
              />
              {isStreaming ? (
                <button onClick={abort} className="p-1.5 rounded-full bg-gray-800 text-white hover:bg-gray-700 transition-all flex-shrink-0">
                  <Square size={14} />
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  disabled={!selectedImage && !(inputRef.current?.value || '').trim()}
                  className={`p-1.5 rounded-full transition-all flex-shrink-0 ${
                    (inputRef.current?.value || "").trim() || selectedImage
                      ? 'bg-gray-800 text-white hover:bg-gray-700'
                      : 'bg-gray-300 text-gray-400 cursor-not-allowed'
                  }`}
                >
                  <Send size={14} />
                </button>
              )}
            </div>
            <p className="mt-2.5 text-center text-[10px] text-gray-300">
              内容由AI生成，请查阅教材确认
            </p>
          </div>
        </div>
      </div>

      <ChatHistorySidebar
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onJump={() => { setHistoryOpen(false); scrollToBottom(true); }}
      />
    </div>
  );
}
