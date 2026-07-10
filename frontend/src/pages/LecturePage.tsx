import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useLearningPath } from '../hooks/useLearningPath';
import { ChevronDown, ChevronRight, Sparkles, MessageCircle, Send, Brain, FileText } from 'lucide-react';
import Markdown from '../utils/markdown';

export default function LecturePage() {
  const { sectionId } = useParams<{ sectionId: string }>();
  const nav = useNavigate();
  const { path, fetchPath } = useLearningPath();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [activeSection, setActiveSection] = useState(sectionId || '');
  const [lecture, setLecture] = useState('');
  const [generating, setGenerating] = useState(false);
  const [chatMsg, setChatMsg] = useState('');

  useEffect(() => { fetchPath(); }, []);
  useEffect(() => { if (sectionId) setActiveSection(sectionId); }, [sectionId]);

  const pathData: any = path || {};
  const chapters = pathData.chapters || pathData.stages || [];

  const toggle = (id: string) => {
    const n = new Set(expanded); n.has(id) ? n.delete(id) : n.add(id); setExpanded(n);
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: `生成图文讲义`, sessionId: `lecture_${activeSection}` }),
      });
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '', content = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try { const evt = JSON.parse(line.slice(6)); if (evt.type === 'messages') content += evt.content || ''; } catch {}
          }
        }
      }
      setLecture(content);
    } catch {}
    setGenerating(false);
  };

  return (
    <div className="flex h-screen -m-6">
      <div className="w-52 border-r border-gray-200 bg-gray-50 overflow-y-auto flex-shrink-0">
        <div className="p-3 border-b border-gray-200">
          <span className="text-xs font-medium text-gray-500">{pathData.courseName || '学习路径'}</span>
        </div>
        {chapters.map((ch: any, ci: number) => {
          const cid = ch.chapter_id || `c${ci}`;
          return (
            <div key={cid}>
              <button onClick={() => toggle(cid)} className="w-full flex items-center gap-1.5 px-3 py-2 text-left text-xs hover:bg-gray-100">
                {expanded.has(cid) ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <FileText size={12} className="text-gray-400" />
                <span className="truncate font-medium text-gray-700">{ch.title}</span>
              </button>
              {expanded.has(cid) && (ch.sections || []).map((sec: any, si: number) => {
                const sid = sec.section_id || `s${ci}_${si}`;
                return (
                  <button key={sid}
                    onClick={() => { setActiveSection(sid); nav(`/lecture/${sid}`); }}
                    className={`w-full text-left pl-8 pr-3 py-1.5 text-xs ${sid === activeSection ? 'bg-blue-50 text-blue-700 border-l-2 border-blue-500' : 'hover:bg-gray-100 text-gray-600'}`}>
                    {sec.title}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>

      <div className="flex-1 flex flex-col min-w-0 border-r border-gray-200">
        <div className="px-4 py-2.5 border-b border-gray-200 flex items-center gap-2">
          <span className="text-sm font-medium truncate flex-1">讲义</span>
          <button onClick={handleGenerate} disabled={generating}
            className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-50">
            <Sparkles size={12} />{generating ? '...' : '生成讲义'}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {lecture ? (
            <div className="prose prose-sm max-w-none"><Markdown content={lecture} /></div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-2">
              <Brain size={36} /><p className="text-sm">点击「生成讲义」创建内容</p>
            </div>
          )}
        </div>
      </div>

      <div className="w-64 bg-gray-50 flex flex-col flex-shrink-0">
        <div className="px-3 py-2.5 border-b border-gray-200">
          <span className="text-xs font-medium text-gray-500 flex items-center gap-1"><MessageCircle size={12} />智能辅导</span>
        </div>
        <div className="flex-1 p-3 text-xs text-gray-400">针对当前章节提问。</div>
        <div className="p-2 border-t border-gray-200">
          <div className="flex gap-1">
            <input type="text" value={chatMsg} onChange={e => setChatMsg(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && setChatMsg('')}
              placeholder="提问..." className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-xs" />
            <button className="px-2 py-1.5 bg-blue-600 text-white rounded text-xs"><Send size={12} /></button>
          </div>
        </div>
      </div>
    </div>
  );
}
