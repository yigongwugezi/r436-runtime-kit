import { useState, useEffect, useRef } from 'react';
import { useSubjectStore } from '../../store/subjectStore';
import { getCurrentLearner, logoutLearner } from '../../pages/LoginPage';
import {
  User, BookOpen, MessageSquare, Activity, Database, Info,
  Check, X, Edit3, Trash2, Download, Upload,
  Brain, ChevronDown, Settings,
} from 'lucide-react';
import Modal from './Modal';

/* ===================================================================
 * 设置分类定义
 * =================================================================== */
const TABS = [
  { id: 'profile',     label: '个人资料', icon: User },
  { id: 'preferences', label: '学习偏好', icon: BookOpen },
  { id: 'chat',        label: '对话设置', icon: MessageSquare },
  { id: 'diagnosis',   label: '诊断设置', icon: Activity },
  { id: 'data',        label: '数据管理', icon: Database },
  { id: 'about',       label: '关于',     icon: Info },
] as const;

/* ===================================================================
 * 子组件
 * =================================================================== */
function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button type="button" onClick={() => onChange(!value)}
      className={`relative w-10 h-5.5 rounded-full transition-all duration-200 flex-shrink-0 ${
        value ? 'bg-brand-500' : 'bg-gray-200'
      }`}>
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

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const selected = options.find(o => o.value === value);
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100 transition-colors min-w-[120px] whitespace-nowrap">
        <span className="flex-1 text-left">{selected?.label || value}</span>
        <ChevronDown className={`w-3 h-3 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-44 bg-white border border-gray-200 rounded-xl shadow-xl py-1 z-50 animate-fade-in-up">
          {options.map(opt => (
            <button key={opt.value} type="button" onClick={() => { onChange(opt.value); setOpen(false); }}
              className={`w-full text-left px-3 py-2 text-sm transition-colors ${
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

function SettingRow({ label, description, children }: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between py-3 px-4 bg-white border border-gray-100 rounded-xl hover:border-gray-200 transition-colors">
      <div className="flex-1 min-w-0 mr-4">
        <p className="text-sm font-medium text-gray-800">{label}</p>
        {description && <p className="text-xs text-gray-400 mt-0.5">{description}</p>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

/* ===================================================================
 * 学习偏好持久化
 * =================================================================== */
const PREFS_KEY = 'eduagent_learning_preferences';

interface LearningPrefs {
  defaultDuration: number;
  difficulty: string;
  learningStyle: string;
  aiStyle: string;
  autoDiagnose: boolean;
  diagnoseDepth: string;
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
  try {
    const data = localStorage.getItem(PREFS_KEY);
    return data ? { ...DEFAULT_PREFS, ...JSON.parse(data) } : DEFAULT_PREFS;
  } catch { return DEFAULT_PREFS; }
}

function savePrefs(prefs: LearningPrefs) {
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch {}
}

/* ===================================================================
 * SettingsModal
 * =================================================================== */
export default function SettingsModal({ open, onClose }: {
  open: boolean;
  onClose: () => void;
}) {
  const learner = getCurrentLearner();
  const { subjects } = useSubjectStore();
  const [tab, setTab] = useState('profile');

  // 个人资料
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState('');

  // 偏好
  const [prefs, setPrefs] = useState<LearningPrefs>(loadPrefs);

  // 数据管理
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearDone, setClearDone] = useState(false);
  const [exportDone, setExportDone] = useState(false);

  // 重置 tab 状态
  useEffect(() => {
    if (open) {
      setTab('profile');
      setEditingName(false);
      setShowClearConfirm(false);
      setClearDone(false);
      setExportDone(false);
      setPrefs(loadPrefs());
    }
  }, [open]);

  const updatePrefs = (updates: Partial<LearningPrefs>) => {
    const next = { ...prefs, ...updates };
    setPrefs(next);
    savePrefs(next);
  };

  const handleSaveName = () => {
    const name = nameInput.trim();
    if (!name || !learner) return;
    const learners = JSON.parse(localStorage.getItem('eduagent_learners') || '[]');
    const updated = learners.map((l: any) =>
      l.id === learner.id ? { ...l, name } : l
    );
    localStorage.setItem('eduagent_learners', JSON.stringify(updated));
    localStorage.setItem('eduagent_active_learner', JSON.stringify({ ...learner, name }));
    setEditingName(false);
    window.location.reload();
  };

  const handleClearData = () => {
    const learners = localStorage.getItem('eduagent_learners');
    const activeLearner = localStorage.getItem('eduagent_active_learner');
    localStorage.clear();
    if (learners) localStorage.setItem('eduagent_learners', learners);
    if (activeLearner) localStorage.setItem('eduagent_active_learner', activeLearner);
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
    a.download = `eduagent_backup_${new Date().toISOString().slice(0, 10)}.json`;
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

  return (
    <Modal open={open} onClose={onClose} xwide>
      {/* 顶部标题 */}
      <div className="flex items-center gap-3 mb-6 pb-5 border-b border-gray-100">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-sm">
          <Settings className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-gray-900">设置</h2>
          <p className="text-sm text-gray-400">管理个人偏好与应用配置</p>
        </div>
      </div>

      {/* ======== 左右布局 ======== */}
      <div className="flex gap-8 min-h-[450px]">
        {/* ===== 左侧导航 ===== */}
        <div className="w-52 flex-shrink-0 space-y-0.5">
          {TABS.map(t => {
            const isActive = tab === t.id;
            return (
              <button key={t.id} type="button" onClick={() => setTab(t.id)}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-left transition-all ${
                  isActive
                    ? 'bg-brand-500/10 text-brand-600 font-medium'
                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700'
                }`}>
                <t.icon className={`w-4.5 h-4.5 ${isActive ? 'text-brand-500' : 'text-gray-400'}`} />
                <span className="text-sm">{t.label}</span>
              </button>
            );
          })}
        </div>

        {/* ===== 右侧内容 ===== */}
        <div className="flex-1 min-w-0 max-h-[70vh] overflow-y-auto pr-2 space-y-5">

          {/* ---- 个人资料 ---- */}
          {tab === 'profile' && (
            <div className="space-y-3">
              <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider">基本信息</p>

              <SettingRow label="用户昵称" description="界面各处的显示名称">
                {editingName ? (
                  <div className="flex items-center gap-1.5">
                    <input value={nameInput} onChange={e => setNameInput(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleSaveName()}
                      className="w-28 text-sm bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-brand-500"
                      autoFocus maxLength={20} />
                    <button onClick={handleSaveName} className="p-1 rounded hover:bg-gray-100 text-brand-500"><Check className="w-3 h-3" /></button>
                    <button onClick={() => setEditingName(false)} className="p-1 rounded hover:bg-gray-100 text-gray-400"><X className="w-3 h-3" /></button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-gray-700">{learner?.name || '未命名'}</span>
                    <button onClick={() => { setNameInput(learner?.name || ''); setEditingName(true); }}
                      className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600">
                      <Edit3 className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </SettingRow>

              <SettingRow label="当前科目" description="已创建的科目数量">
                <span className="text-xs font-semibold text-gray-600">{subjects.length} 个</span>
              </SettingRow>

              <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider pt-2">账户</p>

              <SettingRow label="切换学习者" description="切换到其他账号">
                <button type="button" onClick={() => { logoutLearner(); window.location.href = '/login'; }}
                  className="px-2.5 py-1.5 bg-gray-50 border border-gray-200 rounded-lg text-[10px] font-medium text-gray-600 hover:bg-gray-100 transition-colors">
                  切换
                </button>
              </SettingRow>
            </div>
          )}

          {/* ---- 学习偏好 ---- */}
          {tab === 'preferences' && (
            <div className="space-y-3">
              <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider">学习习惯</p>

              <SettingRow label="单次学习时长" description="推荐的单次学习时间">
                <Select value={String(prefs.defaultDuration)} options={[
                  { value: '15', label: '15 分钟' }, { value: '30', label: '30 分钟' },
                  { value: '45', label: '45 分钟' }, { value: '60', label: '60 分钟' },
                  { value: '90', label: '90 分钟' },
                ]} onChange={v => updatePrefs({ defaultDuration: Number(v) })} />
              </SettingRow>

              <SettingRow label="默认难度" description="生成资源/路径时的难度偏好">
                <Select value={prefs.difficulty} options={[
                  { value: 'beginner', label: '🌱 入门级' },
                  { value: 'intermediate', label: '📗 进阶级' },
                  { value: 'advanced', label: '🔥 挑战级' },
                ]} onChange={v => updatePrefs({ difficulty: v })} />
              </SettingRow>

              <SettingRow label="学习风格" description="推荐的学习资源类型偏好">
                <Select value={prefs.learningStyle} options={[
                  { value: 'visual', label: '👁 视觉型（图表/导图）' },
                  { value: 'reading', label: '📖 阅读型（讲义/文章）' },
                  { value: 'practical', label: '💻 实践型（案例/代码）' },
                  { value: 'mixed', label: '🎯 混合型（自适应）' },
                ]} onChange={v => updatePrefs({ learningStyle: v })} />
              </SettingRow>
            </div>
          )}

          {/* ---- 对话设置 ---- */}
          {tab === 'chat' && (
            <div className="space-y-3">
              <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider">AI 回复偏好</p>

              <SettingRow label="回复详细程度">
                <Select value={prefs.aiStyle} options={[
                  { value: 'concise', label: '⚡ 简洁（直击要点）' },
                  { value: 'balanced', label: '⚖️ 平衡（适中篇幅）' },
                  { value: 'detailed', label: '📚 详细（全面深入）' },
                ]} onChange={v => updatePrefs({ aiStyle: v })} />
              </SettingRow>

              <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider pt-2">多智能体管线</p>
              <div className="grid grid-cols-2 gap-1.5">
                {[
                  { name: 'ProfileAgent', label: '画像分析', desc: '提取学习画像' },
                  { name: 'KnowledgeAgent', label: '知识检索', desc: '检索课程知识库' },
                  { name: 'DiagnosisAgent', label: '诊断分析', desc: '诊断知识短板' },
                  { name: 'PlannerAgent', label: '路径规划', desc: '生成学习路径' },
                  { name: 'ResourceAgent', label: '资源生成', desc: '生成学习资源' },
                  { name: 'ReviewAgent', label: '质量检查', desc: '校验内容质量' },
                ].map(a => (
                  <div key={a.name} className="flex items-center gap-2 px-2.5 py-2 bg-gray-50 rounded-lg border border-gray-100">
                    <div className="w-6 h-6 rounded-lg bg-brand-100 flex items-center justify-center">
                      <Brain className="w-3 h-3 text-brand-500" />
                    </div>
                    <div>
                    <p className="text-xs font-semibold text-gray-700">{a.label}</p>
                    <p className="text-[10px] text-gray-400">{a.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ---- 诊断设置 ---- */}
          {tab === 'diagnosis' && (
            <div className="space-y-3">
              <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider">诊断配置</p>

              <SettingRow label="自动诊断" description="每次对话后自动分析知识短板">
                <Toggle value={prefs.autoDiagnose} onChange={v => updatePrefs({ autoDiagnose: v })} />
              </SettingRow>

              <SettingRow label="诊断深度">
                <Select value={prefs.diagnoseDepth} options={[
                  { value: 'basic', label: '📊 基础（知识点层面）' },
                  { value: 'deep', label: '🔍 深入（概念关联分析）' },
                  { value: 'comprehensive', label: '🧠 全面（含交叉领域）' },
                ]} onChange={v => updatePrefs({ diagnoseDepth: v })} />
              </SettingRow>

              <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider pt-2">学习分析</p>

              <SettingRow label="学习追踪" description="记录学习时长和完成情况">
                <Toggle value={true} onChange={() => {}} />
              </SettingRow>

              <SettingRow label="艾宾浩斯复习提醒" description="基于遗忘曲线的复习计划">
                <Toggle value={true} onChange={() => {}} />
              </SettingRow>
            </div>
          )}

          {/* ---- 数据管理 ---- */}
          {tab === 'data' && (
            <div className="space-y-3">
              <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider">本地数据</p>

              <SettingRow label="导出数据" description="将所有本地数据导出为 JSON">
                <div className="flex items-center gap-2">
                  {exportDone && <span className="text-[9px] text-green-500 font-medium">✓ 已导出</span>}
                  <button type="button" onClick={handleExportData}
                    className="flex items-center gap-1.5 px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors">
                    <Download className="w-3.5 h-3.5" /> 导出
                  </button>
                </div>
              </SettingRow>

              <SettingRow label="导入数据" description="从备份文件恢复">
                <button type="button" onClick={handleImportData}
                    className="flex items-center gap-1.5 px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors">
                    <Upload className="w-3.5 h-3.5" /> 导入
                </button>
              </SettingRow>

              <SettingRow label="清除本地数据" description="保留学习者信息，清除其余缓存">
                {showClearConfirm ? (
                  <div className="flex items-center gap-1.5">
                    <span className="text-[9px] text-red-500 font-medium">确认？</span>
                    <button onClick={handleClearData}
                      className="px-2 py-1 bg-red-500 text-white rounded-lg text-[9px] font-semibold hover:bg-red-600">确认</button>
                    <button onClick={() => setShowClearConfirm(false)}
                      className="px-2 py-1 bg-gray-100 text-gray-600 rounded-lg text-[9px] font-medium">取消</button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    {clearDone && <span className="text-[9px] text-green-500 font-medium">✓ 已清除</span>}
                    <button onClick={() => setShowClearConfirm(true)}
                    className="flex items-center gap-1.5 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm font-medium text-red-600 hover:bg-red-100 transition-colors">
                    <Trash2 className="w-3.5 h-3.5" /> 清除
                    </button>
                  </div>
                )}
              </SettingRow>

              <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider pt-2">存储统计</p>

              <SettingRow label="本地存储用量">
                <span className="text-sm text-gray-500">
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
            </div>
          )}

          {/* ---- 关于 ---- */}
          {tab === 'about' && (
            <div className="space-y-4">
              <div className="bg-gradient-to-br from-brand-500/5 to-brand-700/5 border border-brand-100 rounded-xl p-5 text-center">
                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center mx-auto mb-3 shadow-md">
                  <Brain className="w-7 h-7 text-white" />
                </div>
                <h3 className="text-xl font-extrabold text-gray-900">Edu<span className="text-brand-500">Agent</span></h3>
                <p className="text-xs text-gray-400 mt-1">v0.3.0 · 2026.06</p>
                <p className="text-sm text-gray-500 mt-2 leading-relaxed max-w-sm mx-auto">
                  基于多智能体协作架构的 AI 个性化学习规划平台
                </p>
              </div>

              <div className="grid grid-cols-2 gap-1.5">
                {[
                  ['前端框架', 'React 19 + TypeScript'],
                  ['样式方案', 'Tailwind CSS v4'],
                  ['状态管理', 'Zustand 5'],
                  ['后端框架', 'FastAPI 0.137'],
                  ['数据库', 'SQLAlchemy + SQLite'],
                  ['AI 架构', '多智能体协作'],
                ].map(([label, value]) => (
                  <div key={label as string} className="px-2.5 py-2 bg-gray-50 rounded-lg border border-gray-100">
                    <p className="text-[10px] text-gray-400">{label as string}</p>
                    <p className="text-xs font-semibold text-gray-700 mt-0.5">{value as string}</p>
                  </div>
                ))}
              </div>

              <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider">智能体架构</p>
              <div className="flex flex-wrap gap-1.5">
                {['画像分析', '知识检索', '诊断分析', '路径规划', '资源生成', '质量检查'].map(name => (
                  <span key={name} className="px-2.5 py-1 bg-brand-50 border border-brand-100 rounded-lg text-[10px] text-brand-600 font-medium">{name}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
