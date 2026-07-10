import { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useLearningPath } from '../hooks/useLearningPath';
import { useChatStore } from '../store/chatStore';
import { ChevronRight, Sparkles, MessageCircle, Send, Brain, BookOpen, ArrowLeft, ArrowRight, Target, Lightbulb, Layers, Clock, GraduationCap, Hash, CheckCircle2 } from 'lucide-react';
import Markdown, { splitSections } from '../utils/markdown';
import type { Chapter, Section, ContentStatus } from '../types/learningPath';

const sectionStatusStyle: Record<ContentStatus, { dot: string; bar: string }> = {
  not_started:  { dot: 'bg-surface-300 ring-surface-100', bar: 'bg-surface-300' },
  in_progress:  { dot: 'bg-blue-400 ring-blue-100',      bar: 'bg-blue-400' },
  mastered:     { dot: 'bg-emerald-400 ring-emerald-100', bar: 'bg-emerald-400' },
  needs_review: { dot: 'bg-amber-400 ring-amber-100',     bar: 'bg-amber-400' },
  blocked:      { dot: 'bg-red-400 ring-red-100',         bar: 'bg-red-400' },
};

export default function LecturePage() {
  const { chapterId, sectionId } = useParams<{ chapterId?: string; sectionId?: string }>();
  const nav = useNavigate();
  const { path, updateKnowledgePoint } = useLearningPath();
  const sessionId = useChatStore((s) => s.dataSessionId);

  // 找到当前章节和所属阶段
  const chapterCtx = useMemo(() => {
    for (const stage of (path?.stages ?? [])) {
      for (const ch of (stage.chapters ?? [])) {
        if (ch.id === (chapterId || sectionId)) return { chapter: ch, stage };
      }
    }
    return null;
  }, [path, chapterId, sectionId]);

  const sections = chapterCtx?.chapter.sections ?? [];
  const [activeSectionId, setActiveSectionId] = useState(sectionId || sections[0]?.id || '');
  const [lecture, setLecture] = useState('');
  const [lectureLoaded, setLectureLoaded] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [chatMsg, setChatMsg] = useState('');
  const [chatReply, setChatReply] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [rightTab, setRightTab] = useState<'tutor' | 'resources' | 'quiz'>('tutor');
  const [generatedSectionIds, setGeneratedSectionIds] = useState<Set<string>>(new Set());

  const sectionToc = useMemo(() => lecture ? splitSections(lecture) : [], [lecture]);

  useEffect(() => { if (!activeSectionId && sections.length > 0) setActiveSectionId(sections[0].id); }, [sections, activeSectionId]);

  const currentSection = sections.find((s: Section) => s.id === activeSectionId);
  const currentIdx = sections.findIndex((s: Section) => s.id === activeSectionId);
  const prevSection = currentIdx > 0 ? sections[currentIdx - 1] : null;
  const nextSection = currentIdx < sections.length - 1 ? sections[currentIdx + 1] : null;

  // 加载已有讲义
  const [loadedSectionIds, setLoadedSectionIds] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!activeSectionId) return;
    // 已经加载过的小节不重复请求，直接保留讲义内容
    if (loadedSectionIds.has(activeSectionId)) return;
    setLectureLoaded(false);
    const url = `/api/sections/${encodeURIComponent(activeSectionId)}/lecture?sessionId=${encodeURIComponent(sessionId || '')}`;
    fetch(url)
      .then(r => r.json())
      .then(d => {
        setLoadedSectionIds(prev => new Set(prev).add(activeSectionId));
        console.log(`[讲义加载] section=${activeSectionId} hasContent=${!!d?.data?.lecture?.content}`);
        if (d?.data?.lecture?.content) {
          setLecture(d.data.lecture.content);
          setGeneratedSectionIds(prev => new Set(prev).add(activeSectionId));
        }
      })
      .catch(() => setLoadedSectionIds(prev => new Set(prev).add(activeSectionId)))
      .finally(() => setLectureLoaded(true));
  }, [activeSectionId, sessionId]);

  const totalKps = chapterCtx?.chapter.sections?.reduce((s, sec) => s + (sec.knowledgePoints?.length ?? 0), 0) ?? 0;
  const masteredKps = chapterCtx?.chapter.sections?.reduce((s, sec) => s + (sec.knowledgePoints?.filter(k => k.status === 'mastered').length ?? 0), 0) ?? 0;
  const totalMin = chapterCtx?.chapter.sections?.reduce((s, sec) => s + (sec.estimatedMinutes ?? 45), 0) ?? 0;

  const handleGenerate = useCallback(async () => {
    if (!currentSection || !sessionId) return;
    setGenerating(true);
    try {
      const res = await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/lecture/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId,
          sectionTitle: currentSection.title,
          sectionGoal: currentSection.goal || '',
          chapterId: chapterCtx?.chapter.id || '',
          stageId: chapterCtx?.stage.id || '',
          pathId: path?.id || '',
          courseId: path?.courseName || '',
          knowledgePoints: currentSection.knowledgePoints || [],
        }),
      });
      const data = await res.json();
      if (data?.data?.lecture?.content) {
        setLecture(data.data.lecture.content);
        setGeneratedSectionIds(prev => new Set(prev).add(activeSectionId));
      }
    } catch {} finally { setGenerating(false); }
  }, [currentSection, activeSectionId, sessionId, chapterCtx, path]);

  const [videoGenerating, setVideoGenerating] = useState(false);
  const [videoResult, setVideoResult] = useState<any>(null);

  const sendChat = useCallback(async (question: string) => {
    if (!question.trim() || !sessionId || !currentSection) return;
    setChatMsg(''); setChatLoading(true); setChatReply('');
    try {
      const res = await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/tutor/ask`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionId, question,
          sectionTitle: currentSection.title,
          sectionGoal: currentSection.goal || '',
          knowledgePoints: currentSection.knowledgePoints || [],
          lectureExcerpt: lecture.slice(0, 1000),
        }),
      });
      const data = await res.json();
      if (data?.data?.reply) setChatReply(data.data.reply);
      else if (data?.status === 'error') setChatReply(`出错了：${data.message}`);
    } catch {} finally { setChatLoading(false); }
  }, [sessionId, currentSection, activeSectionId, lecture]);

  const handleGenerateVideo = useCallback(async () => {
    if (!sessionId || !currentSection) return;
    setVideoGenerating(true); setVideoResult(null);
    try {
      const res = await fetch(`/api/sections/${encodeURIComponent(activeSectionId)}/tutor/video`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId, sectionTitle: currentSection.title }),
      });
      const data = await res.json();
      setVideoResult(data?.data?.video || { status: 'failed' });
    } catch {} finally { setVideoGenerating(false); }
  }, [sessionId, currentSection, activeSectionId]);

  const handleSendChat = useCallback(async () => {
    await sendChat(chatMsg);
  }, [chatMsg, sendChat]);

  const loadingLecture = !lectureLoaded;

  const [showRightPanel, setShowRightPanel] = useState(true);

  return (
    <div className="flex h-screen -m-6">
      {/* ══ 左：章节 + 小节 ══ */}
      <div className="w-44 lg:w-52 xl:w-56 bg-white border-r border-surface-200 flex flex-col flex-shrink-0">
        <div className="p-4 bg-gradient-to-b from-surface-50 to-white border-b border-surface-100">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-lg bg-blue-100 flex items-center justify-center"><Hash size={13} className="text-blue-600" /></div>
            <p className="text-xs font-bold text-surface-800 leading-snug flex-1">{chapterCtx?.chapter.title || '讲义'}</p>
          </div>
          <div className="flex items-center gap-3 text-[10px] text-surface-400">
            <span className="flex items-center gap-1"><Layers size={10} />{sections.length} 小节</span>
            <span className="flex items-center gap-1"><GraduationCap size={10} />{totalKps} 知识点</span>
            <span className="flex items-center gap-1"><Clock size={10} />{Math.round(totalMin / 60)}h</span>
          </div>
          {totalKps > 0 && (
            <div className="flex items-center gap-2 mt-2">
              <div className="flex-1 h-1.5 bg-surface-100 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-blue-400 to-emerald-400 rounded-full transition-all duration-500" style={{ width: `${Math.round((masteredKps / totalKps) * 100)}%` }} />
              </div>
              <span className="text-[10px] font-medium text-surface-500">{Math.round((masteredKps / totalKps) * 100)}%</span>
            </div>
          )}
        </div>
        <div className="flex-1 overflow-y-auto">
          {sections.map((sec: Section, si: number) => {
            const isActive = sec.id === activeSectionId;
            const st = sectionStatusStyle[(sec.status as ContentStatus) || 'not_started'];
            const hasLecture = (sec.lectureIds?.length ?? 0) > 0 || generatedSectionIds.has(sec.id);
            const kpCount = sec.knowledgePoints?.length ?? 0;
            return (
              <button key={sec.id} onClick={() => setActiveSectionId(sec.id)}
                className={`w-full text-left px-4 py-3 transition-all group relative ${isActive ? 'bg-blue-50' : 'hover:bg-surface-50'}`}>
                <div className={`absolute left-0 top-2 bottom-2 w-0.5 rounded-r-full transition-all ${isActive ? 'bg-blue-500' : 'bg-transparent group-hover:bg-surface-200'}`} />
                <div className="flex items-center gap-2.5">
                  <div className={`w-2.5 h-2.5 rounded-full ring-2 flex-shrink-0 ${st.dot} ${isActive ? 'scale-110' : ''} transition-transform`} />
                  <span className={`text-[10px] font-bold w-4 text-right flex-shrink-0 ${isActive ? 'text-blue-500' : 'text-surface-400'}`}>{si + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className={`text-xs truncate transition-colors ${isActive ? 'text-blue-700 font-semibold' : 'text-surface-700 group-hover:text-surface-800'}`}>{sec.title}</p>
                    <div className="flex items-center gap-2 mt-0.5 text-[10px] text-surface-400">
                      {hasLecture && <span className="text-blue-400 flex items-center gap-0.5"><BookOpen size={9} />讲义</span>}
                      <span>{kpCount} 知识点</span>
                    </div>
                  </div>
                  {hasLecture && isActive && <CheckCircle2 size={13} className="text-emerald-400 flex-shrink-0" />}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ══ 中：讲义 ══ */}
      <div className="flex-1 flex flex-col min-w-0 bg-surface-50/50">
        <div className="bg-white border-b border-surface-200">
          <div className="h-1 bg-gradient-to-r from-blue-500 via-violet-500 to-amber-500" />
          <div className="px-5 py-3.5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 text-[10px] text-surface-400 mb-2">
                  <button onClick={() => nav('/path')} className="flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-surface-100 hover:text-blue-600 transition-colors">学习路径</button>
                  <ChevronRight size={10} />
                  <span className="text-surface-500 truncate max-w-[200px]">{chapterCtx?.chapter.title}</span>
                </div>
                <h2 className="text-lg font-bold text-surface-900">{currentSection?.title || '选择小节'}</h2>
                {currentSection?.goal && (
                  <p className="text-xs text-surface-400 mt-1.5 flex items-center gap-1.5"><Target size={11} className="text-amber-500 flex-shrink-0" />{currentSection.goal}</p>
                )}
                {(currentSection?.knowledgePoints?.length ?? 0) > 0 && (
                  <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                    {currentSection!.knowledgePoints.map((kp: any) => {
                      const kpSt = sectionStatusStyle[(kp.status as ContentStatus) || 'not_started'];
                      return (
                        <span key={kp.id} onClick={() => updateKnowledgePoint(kp.id, { status: kp.status === 'mastered' ? 'not_started' : 'mastered' })}
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] cursor-pointer hover:opacity-80 transition-opacity ${kp.status === 'mastered' ? 'bg-emerald-50 text-emerald-600' : 'bg-surface-100 text-surface-500'}`}>
                          <div className={`w-1.5 h-1.5 rounded-full ${kp.status === 'mastered' ? 'bg-emerald-400' : kpSt.dot}`} />
                          {kp.name}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <button onClick={() => setShowRightPanel(!showRightPanel)}
                  className={`w-8 h-8 rounded-lg border transition-colors flex items-center justify-center ${showRightPanel ? 'bg-violet-50 border-violet-200 text-violet-500' : 'bg-white border-surface-200 text-surface-400 hover:bg-surface-50'}`}
                  title={showRightPanel ? '折叠功能面板' : '展开功能面板'}>
                  <MessageCircle size={14} />
                </button>
                {currentSection && (
                  <button onClick={handleGenerate} disabled={generating || loadingLecture}
                    className="flex items-center gap-1.5 px-4 py-2.5 bg-gradient-to-r from-blue-600 to-violet-600 text-white rounded-xl text-sm font-semibold hover:from-blue-700 hover:to-violet-700 disabled:opacity-50 transition-all shadow-md shadow-blue-200">
                    <Sparkles size={14} />{generating ? 'AI 正在生成…' : lecture ? '重新生成' : '生成讲义'}
                  </button>
                )}
              </div>
            </div>
            {sections.length > 1 && (
              <div className="flex items-center gap-3 mt-3 pt-3 border-t border-surface-100">
                <button onClick={() => { if (prevSection) setActiveSectionId(prevSection.id); }} disabled={!prevSection}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl transition-all disabled:opacity-25 enabled:hover:bg-surface-100 enabled:hover:text-blue-600 text-surface-500">
                  <ArrowLeft size={13} /><span className="hidden sm:inline">上一节</span>
                </button>
                <div className="flex-1 flex items-center justify-center gap-1">
                  {sections.map((_, i) => (
                    <div key={i} className={`w-1.5 h-1.5 rounded-full transition-all ${i === currentIdx ? 'bg-blue-500 scale-125' : i < currentIdx ? 'bg-emerald-400' : 'bg-surface-200'}`} />
                  ))}
                </div>
                <button onClick={() => { if (nextSection) setActiveSectionId(nextSection.id); }} disabled={!nextSection}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl transition-all disabled:opacity-25 enabled:hover:bg-surface-100 enabled:hover:text-blue-600 text-surface-500">
                  <span className="hidden sm:inline">下一节</span><ArrowRight size={13} />
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {lecture ? (
            <div className="flex gap-0">
              <div className="flex-1 min-w-0 px-5 py-4 space-y-5">
                {sectionToc.map((sec) => (
                  <section key={sec.id} id={sec.id} className="bg-white rounded-2xl p-6 shadow-soft border border-surface-100">
                    <Markdown content={sec.content} />
                  </section>
                ))}
              </div>
              {sectionToc.length > 1 && (
                <div className="w-40 flex-shrink-0 hidden xl:block pr-2 pt-4">
                  <div className="sticky top-4">
                    <p className="text-[10px] font-bold text-surface-400 uppercase tracking-wider mb-2">页面目录</p>
                    <nav className="space-y-0.5">
                      {sectionToc.map((sec) => (
                        <a key={sec.id} href={`#${sec.id}`}
                          className="block text-[11px] text-surface-500 hover:text-blue-600 py-1.5 px-2 rounded-lg hover:bg-blue-50 transition-all truncate">{sec.title}</a>
                      ))}
                    </nav>
                  </div>
                </div>
              )}
            </div>
          ) : loadingLecture ? (
            <div className="flex items-center justify-center h-full">
              <div className="w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-5">
              <div className="relative">
                <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-blue-100 via-violet-100 to-amber-100 flex items-center justify-center shadow-lg shadow-blue-100">
                  <Brain size={40} className="text-blue-500" />
                </div>
                <div className="absolute -bottom-1 -right-1 w-8 h-8 rounded-full bg-white shadow-md flex items-center justify-center">
                  <Sparkles size={14} className="text-amber-500" />
                </div>
              </div>
              <div className="text-center">
                <p className="text-base font-semibold text-surface-700">准备开始学习</p>
                <p className="text-sm text-surface-400 mt-1 max-w-xs">点击「生成讲义」，AI 将根据本节知识点创建专属学习材料</p>
              </div>
              <button onClick={handleGenerate} disabled={generating || loadingLecture}
                className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-blue-600 to-violet-600 text-white rounded-xl text-sm font-semibold hover:from-blue-700 hover:to-violet-700 disabled:opacity-50 transition-all shadow-md shadow-blue-200">
                <Sparkles size={15} />{generating ? '生成中…' : '开始生成讲义'}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ══ 右：功能面板 ══ */}
      {showRightPanel && (
      <div className="w-64 lg:w-72 xl:w-80 bg-white border-l border-surface-200 flex flex-col flex-shrink-0 overflow-hidden relative">
        {/* 折叠按钮 */}
        <button onClick={() => setShowRightPanel(false)}
          className="absolute top-2 right-2 z-10 w-6 h-6 rounded-md hover:bg-surface-100 flex items-center justify-center text-surface-400 hover:text-surface-600 transition-colors"
          title="折叠功能面板">
          <ChevronRight size={14} />
        </button>
        {/* 顶部标签 */}
        <div className="flex border-b border-surface-200 flex-shrink-0">
          {([
            { key: 'tutor' as const, label: '智能辅导', icon: <MessageCircle size={12} />, color: 'violet' },
            { key: 'resources' as const, label: '相关资源', icon: <Lightbulb size={12} />, color: 'amber' },
            { key: 'quiz' as const, label: '知识点', icon: <Target size={12} />, color: 'emerald' },
          ]).map(tab => (
            <button key={tab.key} onClick={() => setRightTab(tab.key)}
              className={`flex-1 flex items-center justify-center gap-1 py-2.5 text-[10px] font-medium transition-all border-b-2 ${rightTab === tab.key ? `border-${tab.color}-500 text-${tab.color}-700 bg-${tab.color}-50` : 'border-transparent text-surface-400 hover:text-surface-600'}`}>
              {tab.icon}{tab.label}
            </button>
          ))}
        </div>

        {/* 面板内容 */}
        <div className="flex-1 flex flex-col min-h-0 overflow-y-auto">
          {rightTab === 'tutor' && (
            <div className="flex flex-col flex-1 min-h-0">
              {/* 快捷操作 */}
              {!chatReply && !chatLoading && currentSection && (
                <div className="px-3 py-2 space-y-1 flex-shrink-0">
                  <p className="text-[10px] font-medium text-surface-400 uppercase tracking-wide mb-2 px-1">AI 助手</p>
                  <div className="space-y-2">
                    <button onClick={() => sendChat(`请详细解释「${currentSection.knowledgePoints?.[0]?.name || '核心概念'}」的含义、原理和应用场景。`)}
                      className="w-full p-3 rounded-xl bg-gradient-to-br from-violet-50 to-blue-50 border border-violet-100 hover:border-violet-200 hover:shadow-sm transition-all text-left group">
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-7 h-7 rounded-lg bg-violet-100 flex items-center justify-center group-hover:scale-110 transition-transform"><Brain size={13} className="text-violet-600" /></div>
                        <span className="text-xs font-semibold text-surface-700">概念讲解</span>
                      </div>
                      <p className="text-[10px] text-surface-400 leading-relaxed">解释"{currentSection.knowledgePoints?.[0]?.name || '核心概念'}"的含义、原理和应用</p>
                    </button>
                    <button onClick={() => sendChat('请用图解（Mermaid）和文字结合的方式，说明本节的核心知识结构和概念关系。')}
                      className="w-full p-3 rounded-xl bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-100 hover:border-amber-200 hover:shadow-sm transition-all text-left group">
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-7 h-7 rounded-lg bg-amber-100 flex items-center justify-center group-hover:scale-110 transition-transform"><Lightbulb size={13} className="text-amber-600" /></div>
                        <span className="text-xs font-semibold text-surface-700">图解结构</span>
                      </div>
                      <p className="text-[10px] text-surface-400 leading-relaxed">用知识结构图和文字梳理本节概念关系</p>
                    </button>
                    <button onClick={() => sendChat(`请根据本节「${currentSection.title}」的内容，出一道中等难度的练习题并给出详细解析。`)}
                      className="w-full p-3 rounded-xl bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-100 hover:border-emerald-200 hover:shadow-sm transition-all text-left group">
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center group-hover:scale-110 transition-transform"><Target size={13} className="text-emerald-600" /></div>
                        <span className="text-xs font-semibold text-surface-700">随堂练习</span>
                      </div>
                      <p className="text-[10px] text-surface-400 leading-relaxed">根据本节内容生成练习题并给出详细解析</p>
                    </button>
                    <button onClick={handleGenerateVideo} disabled={videoGenerating}
                      className="w-full p-3 rounded-xl bg-gradient-to-br from-rose-50 to-pink-50 border border-rose-100 hover:border-rose-200 hover:shadow-sm transition-all text-left group disabled:opacity-60">
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-7 h-7 rounded-lg bg-rose-100 flex items-center justify-center group-hover:scale-110 transition-transform"><Sparkles size={13} className="text-rose-600" /></div>
                        <span className="text-xs font-semibold text-surface-700">讲解视频</span>
                      </div>
                      <p className="text-[10px] text-surface-400 leading-relaxed">{videoGenerating ? '正在生成微课视频脚本…' : videoResult ? '已生成脚本，点击查看' : '生成本节微课讲解视频'}</p>
                    </button>
                  </div>
                </div>
              )}
              {/* 视频结果 */}
              {videoResult && (
                <div className="px-3 py-2 flex-shrink-0">
                  <div className="p-3 rounded-xl bg-rose-50 border border-rose-100">
                    <p className="text-[10px] font-semibold text-rose-600 mb-1">🎬 讲解视频</p>
                    <p className="text-xs text-surface-600 leading-relaxed whitespace-pre-wrap line-clamp-6">{videoResult.script || '脚本生成中...'}</p>
                    {videoResult.status === 'script_ready_provider_not_configured' && (
                      <p className="text-[10px] text-rose-400 mt-1">视频模型尚未配置，已生成脚本草稿</p>
                    )}
                  </div>
                </div>
              )}
              <div className="flex-1 overflow-y-auto px-3 min-h-0">
                {chatReply ? (
                  <div className="text-xs surface-600 leading-relaxed">
                    <Markdown content={chatReply} />
                  </div>
                ) : !chatLoading && (
                  <p className="text-[11px] text-surface-400 px-1">点击快捷提问或输入问题，AI 结合讲义和知识点为你解答</p>
                )}
                {chatLoading && (
                  <div className="flex items-center gap-2 text-xs text-violet-500 px-1"><div className="w-3 h-3 border-2 border-violet-400 border-t-transparent rounded-full animate-spin" />AI 正在分析…</div>
                )}
              </div>
              <div className="p-3 border-t border-surface-100 flex-shrink-0">
                <div className="flex gap-1.5">
                  <input value={chatMsg} onChange={e => setChatMsg(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') handleSendChat(); }} placeholder="输入问题…"
                    className="flex-1 px-3 py-2 bg-surface-50 border border-surface-200 rounded-lg text-xs focus:outline-none focus:border-violet-300 focus:ring-2 focus:ring-violet-100 transition-all" />
                  <button onClick={handleSendChat} disabled={chatLoading} className="px-3 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 disabled:opacity-50 transition-colors shadow-sm"><Send size={13} /></button>
                </div>
              </div>
            </div>
          )}

          {rightTab === 'resources' && (
            <div className="p-4 space-y-3">
              <div className="p-3 rounded-xl bg-surface-50 border border-surface-100">
                <p className="text-[10px] font-medium text-surface-400 uppercase tracking-wide mb-2">思维导图</p>
                {chapterCtx?.chapter.mindmapId ? (
                  <a onClick={() => nav(`/resources/${chapterCtx.chapter.mindmapId}`)}
                    className="flex items-center gap-2 text-sm font-medium text-amber-700 hover:text-amber-800 cursor-pointer"><Brain size={16} />查看章节思维导图</a>
                ) : (
                  <p className="text-xs text-surface-400">暂未生成，在路径页章节详情中生成</p>
                )}
              </div>
              <div className="p-3 rounded-xl bg-surface-50 border border-surface-100">
                <p className="text-[10px] font-medium text-surface-400 uppercase tracking-wide mb-2">讲义状态</p>
                {lecture ? (
                  <p className="text-xs text-emerald-600 flex items-center gap-1.5"><CheckCircle2 size={13} />已生成</p>
                ) : (
                  <p className="text-xs text-surface-400">选择小节后点击「生成讲义」</p>
                )}
              </div>
              <div className="p-3 rounded-xl bg-surface-50 border border-surface-100">
                <p className="text-[10px] font-medium text-surface-400 uppercase tracking-wide mb-2">章节统计</p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="text-center p-2 bg-white rounded-lg"><p className="font-bold text-surface-700">{sections.length}</p><p className="text-[10px] text-surface-400">小节</p></div>
                  <div className="text-center p-2 bg-white rounded-lg"><p className="font-bold text-surface-700">{totalKps}</p><p className="text-[10px] text-surface-400">知识点</p></div>
                  <div className="text-center p-2 bg-white rounded-lg"><p className="font-bold text-surface-700">{masteredKps}</p><p className="text-[10px] text-surface-400">已掌握</p></div>
                  <div className="text-center p-2 bg-white rounded-lg"><p className="font-bold text-surface-700">{Math.round(totalMin / 60)}h</p><p className="text-[10px] text-surface-400">总时长</p></div>
                </div>
              </div>
            </div>
          )}

          {rightTab === 'quiz' && (
            <div className="p-4">
              {currentSection ? (
                <>
                  <p className="text-[10px] font-medium text-surface-400 uppercase tracking-wide mb-3">
                    {currentSection.title} · {currentSection.knowledgePoints?.length ?? 0} 个知识点
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {(currentSection.knowledgePoints ?? []).map((kp: any, i: number) => {
                      const isMastered = kp.status === 'mastered';
                      return (
                        <button key={i} onClick={() => updateKnowledgePoint(kp.id, { status: isMastered ? 'not_started' : 'mastered' })}
                          className={`px-2.5 py-1 rounded-full text-[10px] font-medium transition-all cursor-pointer ${isMastered ? 'bg-emerald-100 text-emerald-600 line-through' : 'bg-surface-100 text-surface-500 hover:bg-surface-200 hover:text-surface-700'}`}>
                          {kp.name}
                        </button>
                      );
                    })}
                  </div>
                  {masteredKps === totalKps && totalKps > 0 && (
                    <div className="mt-4 p-3 bg-emerald-50 rounded-xl text-center">
                      <CheckCircle2 size={18} className="text-emerald-500 mx-auto mb-1" />
                      <p className="text-xs font-semibold text-emerald-700">全部掌握！</p>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-xs text-surface-400">选择小节后查看知识点</p>
              )}
            </div>
          )}
        </div>
      </div>
      )}
      {/* 右侧栏折叠按钮 */}
      {!showRightPanel && (
        <button onClick={() => setShowRightPanel(true)}
          className="absolute right-4 top-4 z-10 w-8 h-8 rounded-lg bg-white border border-surface-200 shadow-sm flex items-center justify-center hover:bg-surface-50 transition-colors"
          title="展开功能面板">
          <MessageCircle size={14} className="text-surface-400" />
        </button>
      )}
    </div>
  );
}
