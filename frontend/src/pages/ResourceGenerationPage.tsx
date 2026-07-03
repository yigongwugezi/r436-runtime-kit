// @ts-nocheck
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles,
  FileText,
  Video,
  BrainCircuit,
  Code2,
  FileQuestion,
  Presentation,
  BookOpen,
  Loader2,
  CheckCircle2,
  Clock,
  Users,
  ChevronRight,
  Zap,
} from 'lucide-react';
import { generateResource } from '../api/resources';
import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';
import { getCurrentLearner } from '../store/authStore';

const resourceTypes = [
  { id: 'lecture', label: '课程讲义', icon: FileText, color: 'from-blue-500 to-cyan-400', description: '专业知识点讲解' },
  { id: 'video', label: '教学视频', icon: Video, color: 'from-rose-500 to-pink-400', description: '可视化教学讲解' },
  { id: 'mindmap', label: '思维导图', icon: BrainCircuit, color: 'from-violet-500 to-purple-400', description: '知识结构梳理' },
  { id: 'case_study', label: '实操案例', icon: Code2, color: 'from-amber-500 to-orange-400', description: '实践代码示例' },
  { id: 'quiz', label: '练习题库', icon: FileQuestion, color: 'from-emerald-500 to-teal-400', description: '测试评估练习' },
  { id: 'ppt', label: 'PPT大纲', icon: Presentation, color: 'from-cyan-500 to-blue-400', description: '幻灯片结构' },
];

export default function ResourceGenerationPage() {
  const nav = useNavigate();
  const isParent = getCurrentLearner()?.role === 'parent';

  if (isParent) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="h-[calc(100vh-300px)] flex items-center justify-center">
          <div className="text-center max-w-md">
            <div className="w-16 h-16 rounded-2xl bg-surface-100 dark:bg-surface-700 flex items-center justify-center mx-auto mb-4">
              <Sparkles className="w-8 h-8 text-surface-400" />
            </div>
            <h3 className="font-display text-lg font-semibold text-surface-800 dark:text-gray-100 mb-2">只读模式</h3>
            <p className="text-surface-500 dark:text-gray-400 text-sm">家长账户无法生成资源。<br/>请前往资源库查看已生成的资源。</p>
          </div>
        </div>
      </div>
    );
  }
  const sessionId = useChatStore(s => s.currentSessionId);
  const subjectId = useSubjectStore(s => s.activeSubject?.id);
  const [selectedTypes, setSelectedTypes] = useState<string[]>(['lecture', 'mindmap', 'quiz']);
  const [prompt, setPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [genError, setGenError] = useState('');

  const toggleType = (id: string) => {
    setSelectedTypes(prev =>
      prev.includes(id) ? prev.filter(t => t !== id) : [...prev, id]
    );
  };

  const handleGenerate = async () => {
    if (selectedTypes.length === 0 || !prompt.trim()) return;
    setIsGenerating(true);
    setGenError('');
    try {
      // 对每种选中的类型依次生成
      for (const type of selectedTypes) {
        await generateResource({
          sessionId,
          subjectId,
          type,
          topic: prompt.trim(),
          difficulty: 'medium',
        });
      }
      // 生成完成后跳转到资源库
      nav('/resources');
    } catch (e: any) {
      setGenError(e?.message || '生成失败，请重试');
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold text-surface-800">智能资源生成</h2>
          <p className="text-surface-500 mt-1">多智能体协同为你生成个性化学习资源</p>
        </div>
        <div className="flex items-center gap-2 px-4 py-2 bg-accent-50 rounded-xl">
          <Users size={18} className="text-accent-600" />
          <span className="text-sm font-medium text-accent-700">多智能体协同</span>
        </div>
      </div>

      {/* Agent Status Bar */}
      <div className="bg-white rounded-2xl p-5 shadow-soft">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-surface-700">智能体团队</h3>
          <span className="text-xs text-surface-400">{isGenerating ? '生成中...' : '就绪'}</span>
        </div>
        <div className="flex items-center gap-4 overflow-x-auto pb-2">
          {([
            { name: '画像分析', emoji: '🧠', color: '#6366f1' },
            { name: '知识诊断', emoji: '🔍', color: '#14b8a6' },
            { name: '路径规划', emoji: '🗺️', color: '#f59e0b' },
            { name: '资源生成', emoji: '✨', color: '#ec4899' },
            { name: '质量审核', emoji: '✅', color: '#22c55e' },
          ]).map((a) => (
            <div key={a.name} className={`flex-shrink-0 flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${isGenerating ? 'bg-primary-50' : 'bg-surface-50'}`}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center text-lg" style={{ backgroundColor: a.color + '20' }}>
                {a.emoji}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-surface-800">{a.name}</p>
                <p className="text-xs text-surface-400">就绪</p>
              </div>
              <CheckCircle2 size={16} className="text-success-500" />
            </div>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-3 gap-6">
        {/* Left - Generation Form */}
        <div className="col-span-2 space-y-6">
          {/* Prompt Input */}
          <div className="bg-white rounded-2xl p-6 shadow-soft">
            <label className="block text-sm font-medium text-surface-700 mb-3">
              描述你的学习需求
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="例如：我需要学习CNN卷积神经网络的核心原理，包括卷积层、池化层的工作机制..."
              className="w-full h-32 px-4 py-3 bg-surface-50 border border-surface-200 rounded-xl text-surface-800 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-primary-200 focus:border-primary-400 resize-none transition-all"
            />
            <div className="flex items-center justify-between mt-3">
              <span className="text-xs text-surface-400">支持Markdown格式输入</span>
              <span className="text-xs text-surface-400">{prompt.length}/500</span>
            </div>
          </div>

          {/* Resource Type Selection */}
          <div className="bg-white rounded-2xl p-6 shadow-soft">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-surface-700">选择资源类型</h3>
              <span className="text-xs text-primary-600">已选择 {selectedTypes.length}/5 种</span>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {resourceTypes.map((type) => {
                const isSelected = selectedTypes.includes(type.id);
                const Icon = type.icon;
                return (
                  <button
                    key={type.id}
                    onClick={() => toggleType(type.id)}
                    disabled={!isSelected && selectedTypes.length >= 5}
                    className={`relative p-4 rounded-xl border-2 transition-all text-left ${
                      isSelected
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-surface-200 bg-surface-50 hover:border-surface-300'
                    } ${!isSelected && selectedTypes.length >= 5 ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${type.color} flex items-center justify-center mb-3`}>
                      <Icon size={20} className="text-white" />
                    </div>
                    <p className="text-sm font-medium text-surface-800">{type.label}</p>
                    <p className="text-xs text-surface-500 mt-1">{type.description}</p>
                    {isSelected && (
                      <div className="absolute top-2 right-2">
                        <CheckCircle2 size={18} className="text-primary-500" />
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Generate Button */}
          <button
            onClick={handleGenerate}
            disabled={selectedTypes.length === 0 || !prompt.trim() || isGenerating}
            className={`w-full flex items-center justify-center gap-3 px-6 py-4 rounded-xl font-semibold text-lg transition-all ${
              selectedTypes.length > 0 && prompt.trim() && !isGenerating
                ? 'bg-gradient-to-r from-primary-600 to-accent-600 text-white hover:shadow-lg'
                : 'bg-surface-100 text-surface-400 cursor-not-allowed'
            }`}
          >
            {isGenerating ? (
              <>
                <Loader2 size={22} className="animate-spin" />
                生成中...
              </>
            ) : (
              <>
                <Sparkles size={22} />
                开始生成 {selectedTypes.length > 0 && `(${selectedTypes.length}种资源)`}
              </>
            )}
          </button>
        </div>

        {/* Right - Generation Queue */}
        <div className="space-y-6">
          {/* Progress */}
          {isGenerating && (
            <div className="bg-primary-50 rounded-2xl p-6 border border-primary-100">
              <div className="flex items-center gap-2 mb-4">
                <Zap size={18} className="text-primary-600" />
                <span className="font-semibold text-primary-800">生成进度</span>
              </div>
              <div className="space-y-3">
                {selectedTypes.map(typeId => {
                  const type = resourceTypes.find(t => t.id === typeId);
                  if (!type) return null;
                  return (
                    <div key={typeId} className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${type.color} flex items-center justify-center`}>
                        <type.icon size={16} className="text-white" />
                      </div>
                      <div className="flex-1">
                        <p className="text-sm font-medium text-surface-700">{type.label}</p>
                        <div className="mt-1 h-1.5 bg-primary-100 rounded-full overflow-hidden">
                          <div className="h-full bg-primary-500 rounded-full animate-pulse" style={{ width: '60%' }} />
                        </div>
                      </div>
                      <Loader2 size={16} className="text-primary-500 animate-spin" />
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 生成状态 */}
          {isGenerating && (
            <div className="bg-primary-50 rounded-2xl p-6 border border-primary-100">
              <div className="flex items-center gap-2 mb-3">
                <Loader2 size={18} className="text-primary-500 animate-spin" />
                <span className="font-semibold text-primary-700">正在生成...</span>
              </div>
              <div className="space-y-2">
                {selectedTypes.map(type => {
                  const t = resourceTypes.find(rt => rt.id === type);
                  return (
                    <div key={type} className="flex items-center gap-2 text-sm text-primary-600">
                      <Loader2 size={12} className="animate-spin" />
                      <span>{t?.label || type}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {genError && (
            <div className="bg-error-50 rounded-2xl p-4 border border-error-200">
              <p className="text-sm text-error-600">{genError}</p>
            </div>
          )}

          {/* Quick Templates */}
          <div className="bg-surface-50 rounded-2xl p-5">
            <h4 className="text-sm font-medium text-surface-700 mb-3">快捷模板</h4>
            <div className="space-y-2">
              {['CNN原理学习', 'Transformer架构', 'Python项目实战'].map((template, idx) => (
                <button
                  key={idx}
                  onClick={() => setPrompt(template + '相关知识点和代码示例')}
                  className="w-full flex items-center justify-between px-4 py-2.5 bg-white rounded-lg text-sm text-surface-600 hover:bg-primary-50 hover:text-primary-600 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <BookOpen size={14} />
                    {template}
                  </div>
                  <ChevronRight size={14} />
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
