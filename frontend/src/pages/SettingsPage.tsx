import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSubjectStore } from '../store/subjectStore';
import { getCurrentLearner, logoutLearner } from './LoginPage';
import { readStorageItem, readStorageJson, writeStorageJson, runtimeStorageKeys } from '../utils/storageKeys';
import {
  Settings, User, BookOpen, MessageSquare, Activity, Database, Info,
  ChevronRight, Check, X, Edit3, Save, Trash2, Download, Upload,
  RefreshCw, AlertTriangle, Sparkles, Brain, Clock, Target,
  ChevronDown, Sun, Moon, Globe,
} from 'lucide-react';

/* ===================================================================
 * 设置分类定义
 * =================================================================== */
interface SettingCategory {
  id: string;
  label: string;
  icon: any;
  description: string;
}

const CATEGORIES: SettingCategory[] = [
  { id: 'profile',    label: '个人资料', icon: User,         description: '昵称、头像等基本信息' },
  { id: 'preferences', label: '学习偏好', icon: BookOpen,     description: '学习时长、难度、风格偏好' },
  { id: 'chat',       label: '对话设置', icon: MessageSquare, description: 'AI 回复风格、详细程度' },
  { id: 'diagnosis',  label: '诊断设置', icon: Activity,      description: '诊断深度、分析频率' },
  { id: 'data',       label: '数据管理', icon: Database,      description: '缓存清理、数据导入导出' },
  { id: 'about',      label: '关于',     icon: Info,          description: '版本信息与技术栈' },
];

/* ===================================================================
 * 设置项包装组件
 * =================================================================== */
function SettingSection({ title, description, children }: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-8">
      <div className="mb-4">
        <h3 className="text-base font-semibold text-gray-900">{title}</h3>
        {description && <p className="text-xs text-gray-400 mt-0.5">{description}</p>}
      </div>
      <div className="space-y-3">
        {children}
      </div>
    </div>
  );
}

function SettingRow({ label, description, children }: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between py-3 px-4 bg-white border border-gray-100 rounded-xl hover:border-gray-200 transition-colors">
      <div className="flex-1 min-w-0 mr-4">
        <p className="text-sm font-medium text-gray-800">{label}</p>
        {description && <p className="text-[11px] text-gray-400 mt-0.5">{description}</p>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={`relative w-10 h-5.5 rounded-full transition-all duration-200 ${
        value ? 'bg-brand-500' : 'bg-gray-200'
      }`}
    >
      <div className={`absolute top-0.5 w-4.5 h-4.5 bg-white rounded-full shadow-sm transition-all duration-200 ${
        value ? 'left-[20px]' : 'left-0.5'
      }`} />
    </button>
  );
}

function Select({ value, options, onChange }: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = options.find(o => o.value === value);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-xs font-medium text-gray-700 hover:bg-gray-100 transition-colors min-w-[100px]">
        <span className="flex-1 text-left">{selected?.label || value}</span>
        <ChevronDown className={`w-3 h-3 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-40 bg-white border border-gray-200 rounded-xl shadow-xl py-1 z-50 animate-fade-in-up">
          {options.map(opt => (
            <button key={opt.value} onClick={() => { onChange(opt.value); setOpen(false); }}
              className={`w-full text-left px-3 py-2 text-xs transition-colors ${
                opt.value === value ? 'text-brand-600 bg-brand-50 font-medium' : 'text-gray-600 hover:bg-gray-50'
              }`}>
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ===================================================================
 * 学习偏好设置存储
 * =================================================================== */
interface LearningPrefs {
  defaultDuration: number;       // 分钟
  difficulty: 'beginner' | 'intermediate' | 'advanced';
  learningStyle: 'visual' | 'reading' | 'practical' | 'mixed';
  aiStyle: 'detailed' | 'concise' | 'balanced';
  autoDiagnose: boolean;
  diagnoseDepth: 'basic' | 'deep' | 'comprehensive';
}

const DEFAULT_PREFS: LearningPrefs = {
  defaultDuration: 30,
  difficulty: 'intermediate',
  learningStyle: 'mixed',
  aiStyle: 'balanced',
  autoDiagnose: true,
  diagnoseDepth: 'deep',
};

function loadPrefs(): LearningPrefs {
  return { ...DEFAULT_PREFS, ...readStorageJson(runtimeStorageKeys.learningPrefs, {}) };
}

function savePrefs(prefs: LearningPrefs) {
  writeStorageJson(runtimeStorageKeys.learningPrefs, prefs);
}

/* ===================================================================
 * 主页面
 * =================================================================== */
export default function SettingsPage() {
  const navigate = useNavigate();
  const learner = getCurrentLearner();
  const { subjects } = useSubjectStore();
  const [activeCategory, setActiveCategory] = useState('profile');

  // 个人资料
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState('');

  // 学习偏好
  const [prefs, setPrefs] = useState<LearningPrefs>(loadPrefs);

  // 数据管理
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearDone, setClearDone] = useState(false);
  const [exportDone, setExportDone] = useState(false);

  const updatePrefs = (updates: Partial<LearningPrefs>) => {
    const next = { ...prefs, ...updates };
    setPrefs(next);
    savePrefs(next);
  };

  const handleSaveName = () => {
    const name = nameInput.trim();
    if (!name || !learner) return;
    const learners = readStorageJson(runtimeStorageKeys.learners, [] as any[]);
    const updated = learners.map((l: any) =>
      l.id === learner.id ? { ...l, name } : l
    );
    writeStorageJson(runtimeStorageKeys.learners, updated);
    writeStorageJson(runtimeStorageKeys.activeLearner, { ...learner, name });
    setEditingName(false);
    window.location.reload();
  };

  const handleClearData = () => {
    // 保留学习者信息，清除其他
    const learners = readStorageItem(runtimeStorageKeys.learners);
    const activeLearner = readStorageItem(runtimeStorageKeys.activeLearner);
    const prefs = readStorageItem(runtimeStorageKeys.learningPrefs);
    localStorage.clear();
    if (learners) localStorage.setItem(runtimeStorageKeys.learners.primary, learners);
    if (activeLearner) localStorage.setItem(runtimeStorageKeys.activeLearner.primary, activeLearner);
    if (prefs) localStorage.setItem(runtimeStorageKeys.learningPrefs.primary, prefs);
    setShowClearConfirm(false);
    setClearDone(true);
    setTimeout(() => setClearDone(false), 3000);
  };

  const handleExportData = () => {
    const data: Record<string, any> = {};
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key) {
        try { data[key] = JSON.parse(localStorage.getItem(key) || ''); }
        catch { data[key] = localStorage.getItem(key); }
      }
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `r436_runtime_backup_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setExportDone(true);
    setTimeout(() => setExportDone(false), 3000);
  };

  const handleImportData = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const data = JSON.parse(reader.result as string);
          Object.entries(data).forEach(([key, value]) => {
            localStorage.setItem(key, JSON.stringify(value));
          });
          window.location.reload();
        } catch { alert('数据格式错误，导入失败'); }
      };
      reader.readAsText(file);
    };
    input.click();
  };

  const activeCategoryData = CATEGORIES.find(c => c.id === activeCategory)!;

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 md:py-8">
      {/* ========== 页面标题 ========== */}
      <div className="mb-6">
        <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-1">设置</h1>
        <p className="text-sm text-gray-400">管理你的个人偏好与应用配置</p>
      </div>

      {/* ========== 主体布局 ========== */}
      <div className="flex gap-6">
        {/* ===== 左侧分类导航 ===== */}
        <div className="w-52 flex-shrink-0 space-y-1">
          {CATEGORIES.map(cat => {
            const isActive = cat.id === activeCategory;
            return (
              <button key={cat.id} onClick={() => setActiveCategory(cat.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-all ${
                  isActive
                    ? 'bg-brand-500/10 text-brand-600 font-semibold'
                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                }`}>
                <cat.icon className={`w-4.5 h-4.5 ${isActive ? 'text-brand-500' : 'text-gray-400'}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm">{cat.label}</p>
                  <p className={`text-[10px] ${isActive ? 'text-brand-400' : 'text-gray-400'} truncate`}>
                    {cat.description}
                  </p>
                </div>
                {isActive && <div className="w-1 h-5 rounded-full bg-brand-500" />}
              </button>
            );
          })}
        </div>

        {/* ===== 右侧内容区 ===== */}
        <div className="flex-1 min-w-0">
          {/* 分类标题 */}
          <div className="mb-6 pb-4 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-brand-50 flex items-center justify-center">
                <activeCategoryData.icon className="w-5 h-5 text-brand-500" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-gray-900">{activeCategoryData.label}</h2>
                <p className="text-xs text-gray-400">{activeCategoryData.description}</p>
              </div>
            </div>
          </div>

          {/* ==============================
               个人资料
              ============================== */}
          {activeCategory === 'profile' && (
            <div>
              <SettingSection title="基本信息" description="管理你的个人身份信息">
                <SettingRow label="用户昵称" description="将显示在界面各处的名称">
                  {editingName ? (
                    <div className="flex items-center gap-2">
                      <input value={nameInput} onChange={(e) => setNameInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSaveName()}
                        className="w-32 text-xs bg-gray-50 border border-gray-200 rounded-lg px-3 py-1.5 outline-none focus:ring-2 focus:ring-brand-500"
                        autoFocus maxLength={20} />
                      <button onClick={handleSaveName} className="p-1 rounded-lg hover:bg-gray-100 text-brand-500"><Check className="w-3.5 h-3.5" /></button>
                      <button onClick={() => setEditingName(false)} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400"><X className="w-3.5 h-3.5" /></button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-700">{learner?.name || '未命名'}</span>
                      <button onClick={() => { setNameInput(learner?.name || ''); setEditingName(true); }}
                        className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors">
                        <Edit3 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </SettingRow>

                <SettingRow label="用户头像" description="自动生成的首字母头像">
                  <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-sm font-bold shadow-sm">
                    {learner?.name?.[0] || '?'}
                  </div>
                </SettingRow>

                <SettingRow label="当前科目" description="已创建的科目数量">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-gray-700">{subjects.length} 个科目</span>
                    <button onClick={() => navigate('/')}
                      className="text-[10px] text-brand-500 hover:text-brand-600 font-medium transition-colors">
                      管理
                    </button>
                  </div>
                </SettingRow>
              </SettingSection>

              <SettingSection title="账户操作">
                <SettingRow label="切换学习者" description="切换到其他学习者账号">
                  <button onClick={() => { logoutLearner(); window.location.href = '/login'; }}
                    className="px-3 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-xs font-medium text-gray-600 hover:bg-gray-100 transition-colors">
                    切换
                  </button>
                </SettingRow>
              </SettingSection>
            </div>
          )}

          {/* ==============================
               学习偏好
              ============================== */}
          {activeCategory === 'preferences' && (
            <div>
              <SettingSection title="学习习惯" description="定制你的默认学习参数">
                <SettingRow label="单次学习时长" description="推荐的单次学习时间">
                  <Select value={String(prefs.defaultDuration)} options={[
                    { value: '15', label: '15 分钟' },
                    { value: '30', label: '30 分钟' },
                    { value: '45', label: '45 分钟' },
                    { value: '60', label: '60 分钟' },
                    { value: '90', label: '90 分钟' },
                  ]} onChange={(v) => updatePrefs({ defaultDuration: Number(v) })} />
                </SettingRow>

                <SettingRow label="默认难度" description="生成资源和路径时的难度偏好">
                  <Select value={prefs.difficulty} options={[
                    { value: 'beginner', label: '🌱 入门级' },
                    { value: 'intermediate', label: '📗 进阶级' },
                    { value: 'advanced', label: '🔥 挑战级' },
                  ]} onChange={(v) => updatePrefs({ difficulty: v as any })} />
                </SettingRow>

                <SettingRow label="学习风格" description="推荐的学习资源类型偏好">
                  <Select value={prefs.learningStyle} options={[
                    { value: 'visual', label: '👁 视觉型（图表/导图）' },
                    { value: 'reading', label: '📖 阅读型（讲义/文章）' },
                    { value: 'practical', label: '💻 实践型（案例/代码）' },
                    { value: 'mixed', label: '🎯 混合型（自适应）' },
                  ]} onChange={(v) => updatePrefs({ learningStyle: v as any })} />
                </SettingRow>
              </SettingSection>
            </div>
          )}

          {/* ==============================
               对话设置
              ============================== */}
          {activeCategory === 'chat' && (
            <div>
              <SettingSection title="AI 回复偏好" description="控制模块输出的对话风格">
                <SettingRow label="回复详细程度" description="AI 回答的篇幅和深度">
                  <Select value={prefs.aiStyle} options={[
                    { value: 'concise', label: '⚡ 简洁（直击要点）' },
                    { value: 'balanced', label: '⚖️ 平衡（适中篇幅）' },
                    { value: 'detailed', label: '📚 详细（全面深入）' },
                  ]} onChange={(v) => updatePrefs({ aiStyle: v as any })} />
                </SettingRow>

                <SettingRow label="快捷指令" description="对话页面的快捷指令按钮">
                  <div className="text-xs text-gray-400">6 个默认指令</div>
                </SettingRow>

                <SettingRow label="历史记录保留" description="对话历史在本地保留">
                  <div className="text-xs text-gray-400">永久保存</div>
                </SettingRow>
              </SettingSection>

              <SettingSection title="模块管线" description="对话时的工作流协作流程">
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { name: 'ProfileAgent', label: '画像分析', desc: '提取学习画像' },
                    { name: 'KnowledgeAgent', label: '知识检索', desc: '检索课程知识库' },
                    { name: 'DiagnosisAgent', label: '诊断分析', desc: '诊断知识短板' },
                    { name: 'PlannerAgent', label: '路径规划', desc: '生成学习路径' },
                    { name: 'ResourceAgent', label: '资源生成', desc: '生成学习资源' },
                    { name: 'ReviewAgent', label: '质量检查', desc: '校验内容质量' },
                  ].map(agent => (
                    <div key={agent.name} className="flex items-center gap-3 px-3 py-2.5 bg-gray-50 rounded-xl border border-gray-100">
                      <div className="w-7 h-7 rounded-lg bg-brand-100 flex items-center justify-center">
                        <Brain className="w-3.5 h-3.5 text-brand-500" />
                      </div>
                      <div>
                        <p className="text-xs font-semibold text-gray-700">{agent.label}</p>
                        <p className="text-[9px] text-gray-400">{agent.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </SettingSection>
            </div>
          )}

          {/* ==============================
               诊断设置
              ============================== */}
          {activeCategory === 'diagnosis' && (
            <div>
              <SettingSection title="诊断配置" description="控制知识诊断的行为">
                <SettingRow label="自动诊断" description="每次对话后自动分析知识短板">
                  <Toggle value={prefs.autoDiagnose} onChange={(v) => updatePrefs({ autoDiagnose: v })} />
                </SettingRow>

                <SettingRow label="诊断深度" description="知识诊断的分析粒度">
                  <Select value={prefs.diagnoseDepth} options={[
                    { value: 'basic', label: '📊 基础（知识点层面）' },
                    { value: 'deep', label: '🔍 深入（概念关联分析）' },
                    { value: 'comprehensive', label: '🧠 全面（含交叉领域）' },
                  ]} onChange={(v) => updatePrefs({ diagnoseDepth: v as any })} />
                </SettingRow>

                <SettingRow label="诊断维度数" description="画像分析的维度数量">
                  <div className="text-xs text-gray-400">10 个核心维度</div>
                </SettingRow>
              </SettingSection>

              <SettingSection title="学习分析" description="学习数据的统计与分析">
                <SettingRow label="学习追踪" description="记录学习时长和完成情况">
                  <Toggle value={true} onChange={() => {}} />
                </SettingRow>

                <SettingRow label="艾宾浩斯复习提醒" description="基于遗忘曲线的复习计划">
                  <Toggle value={true} onChange={() => {}} />
                </SettingRow>
              </SettingSection>
            </div>
          )}

          {/* ==============================
               数据管理
              ============================== */}
          {activeCategory === 'data' && (
            <div>
              <SettingSection title="本地数据" description="管理浏览器中存储的学习数据">
                <SettingRow label="导出数据" description="将所有本地数据导出为 JSON 文件">
                  <div className="flex items-center gap-2">
                    {exportDone && <span className="text-[10px] text-green-500 font-medium">✓ 已导出</span>}
                    <button onClick={handleExportData}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors">
                      <Download className="w-3.5 h-3.5" />
                      导出
                    </button>
                  </div>
                </SettingRow>

                <SettingRow label="导入数据" description="从备份文件恢复数据">
                  <button onClick={handleImportData}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors">
                    <Upload className="w-3.5 h-3.5" />
                    导入
                  </button>
                </SettingRow>

                <SettingRow label="清除本地数据" description="清除所有本地缓存（保留学习者信息）">
                  {showClearConfirm ? (
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-red-500 font-medium">确认清除？</span>
                      <button onClick={handleClearData}
                        className="px-2.5 py-1.5 bg-red-500 text-white rounded-lg text-[10px] font-semibold hover:bg-red-600 transition-colors">
                        确认
                      </button>
                      <button onClick={() => setShowClearConfirm(false)}
                        className="px-2.5 py-1.5 bg-gray-100 text-gray-600 rounded-lg text-[10px] font-medium hover:bg-gray-200 transition-colors">
                        取消
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      {clearDone && <span className="text-[10px] text-green-500 font-medium">✓ 已清除</span>}
                      <button onClick={() => setShowClearConfirm(true)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg text-xs font-medium text-red-600 hover:bg-red-100 transition-colors">
                        <Trash2 className="w-3.5 h-3.5" />
                        清除
                      </button>
                    </div>
                  )}
                </SettingRow>
              </SettingSection>

              <SettingSection title="存储统计">
                <SettingRow label="本地存储用量" description="localStorage 占用的数据量">
                  <span className="text-xs text-gray-500">
                    {(() => {
                      let size = 0;
                      for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        if (key) size += localStorage.getItem(key)?.length || 0;
                      }
                      return size < 1024 ? `${size} B` : `${(size / 1024).toFixed(1)} KB`;
                    })()}
                  </span>
                </SettingRow>

                <SettingRow label="科目数量" description="已创建的学习科目">
                  <span className="text-xs font-semibold text-gray-600">{subjects.length}</span>
                </SettingRow>
              </SettingSection>
            </div>
          )}

          {/* ==============================
               关于
              ============================== */}
          {activeCategory === 'about' && (
            <div>
              <SettingSection title="r436-runtime-kit" description="面向课程工作流的本地演示套件">
                <div className="bg-gradient-to-br from-brand-500/5 to-brand-700/5 border border-brand-100 rounded-2xl p-6 text-center mb-6">
                  <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center mx-auto mb-3 shadow-lg shadow-brand-200">
                    <Brain className="w-8 h-8 text-white" />
                  </div>
                  <h3 className="text-xl font-extrabold text-gray-900">
                    r436<span className="text-brand-500">-runtime-kit</span>
                  </h3>
                  <p className="text-xs text-gray-400 mt-1">v0.3.0 · 2026.06</p>
                  <p className="text-xs text-gray-500 mt-3 max-w-md mx-auto leading-relaxed">
                    面向课程工作流与模块集成的本地演示套件。
                  </p>
                </div>
              </SettingSection>

              <SettingSection title="技术栈">
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: '前端框架', value: 'React 19 + TypeScript' },
                    { label: '样式方案', value: 'Tailwind CSS v4' },
                    { label: '状态管理', value: 'Zustand 5' },
                    { label: '路由方案', value: 'React Router 7' },
                    { label: '构建工具', value: 'Vite 8' },
                    { label: '后端框架', value: 'FastAPI 0.137' },
                    { label: '数据库', value: 'SQLAlchemy + SQLite' },
                    { label: 'AI 模型', value: 'workflow modules' },
                  ].map(item => (
                    <div key={item.label} className="px-3 py-2.5 bg-gray-50 rounded-xl border border-gray-100">
                      <p className="text-[10px] text-gray-400">{item.label}</p>
                      <p className="text-xs font-semibold text-gray-700 mt-0.5">{item.value}</p>
                    </div>
                  ))}
                </div>
              </SettingSection>

              <SettingSection title="模块架构">
                <div className="flex flex-wrap gap-2">
                  {[
                    'ProfileAgent · 画像分析',
                    'KnowledgeAgent · 知识检索',
                    'DiagnosisAgent · 诊断分析',
                    'PlannerAgent · 路径规划',
                    'ResourceAgent · 资源生成',
                    'ReviewAgent · 质量检查',
                  ].map(agent => (
                    <div key={agent} className="px-3 py-1.5 bg-brand-50 border border-brand-100 rounded-lg">
                      <span className="text-[10px] text-brand-600 font-medium">{agent}</span>
                    </div>
                  ))}
                </div>
              </SettingSection>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
