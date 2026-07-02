import { useState, useEffect, useRef, useCallback } from 'react';
import {
  User, BookOpen, MessageSquare, Activity, Database, Palette, Info,
  Check, X, Edit3, Trash2, Download, Upload,
  Brain, ChevronDown, Moon, Sun, GraduationCap,
} from 'lucide-react';

const ROLE_LABEL: Record<string, string> = {
  student: '🎓 学生',
  parent: '👨‍👩‍👧 家长',
  teacher: '📚 教师',
  admin: '⚙️ 管理员',
};
import { getCurrentLearner, useAuthStore } from '../store/authStore';
import { useSubjectStore } from '../store/subjectStore';
import { readStorageJson, writeStorageJson, runtimeStorageKeys } from '../utils/storageKeys';
import { safeClearCache, exportAllData, importAllData, getCacheSize, formatBytes } from '../utils/cache';

/* ===================================================================
 * 导航分区定义
 * =================================================================== */
const NAV_SECTIONS = [
  { id: 'account',     label: '账户设置', icon: User },
  { id: 'preferences', label: '学习偏好', icon: BookOpen },
  { id: 'chat',        label: '对话设置', icon: MessageSquare },
  { id: 'diagnosis',   label: '诊断设置', icon: Activity },
  { id: 'data',        label: '数据管理', icon: Database },
  { id: 'appearance',  label: '外观设置', icon: Palette },
  { id: 'about',       label: '关于',     icon: Info },
] as const;

/* ===================================================================
 * 通用子组件
 * =================================================================== */
function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button type="button" onClick={() => onChange(!value)}
      className={`relative w-10 h-5.5 rounded-full transition-all duration-200 flex-shrink-0 ${
        value ? 'bg-brand-500' : 'bg-gray-200 dark:bg-gray-600'
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
        className="flex items-center gap-1.5 px-3 py-2 bg-gray-50 dark:bg-surface-700 border border-gray-200 dark:border-gray-600 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-surface-600 transition-colors min-w-[130px] whitespace-nowrap">
        <span className="flex-1 text-left">{selected?.label || value}</span>
        <ChevronDown className={`w-3 h-3 text-gray-400 dark:text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-48 bg-white dark:bg-surface-700 border border-gray-200 dark:border-gray-600 rounded-xl shadow-elevated py-1 z-50 animate-fade-in-up">
          {options.map(opt => (
            <button key={opt.value} type="button" onClick={() => { onChange(opt.value); setOpen(false); }}
              className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                opt.value === value ? 'text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-500/10 font-medium' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-surface-600'
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
    <div className="flex items-center justify-between py-3.5 px-4 bg-white dark:bg-surface-700 border border-gray-100 dark:border-gray-600 rounded-xl hover:border-gray-200 dark:hover:border-gray-500 transition-colors">
      <div className="flex-1 min-w-0 mr-4">
        <p className="text-sm font-medium text-gray-800 dark:text-gray-100">{label}</p>
        {description && <p className="text-xs text-gray-400 dark:text-gray-400 mt-0.5">{description}</p>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

/* ===================================================================
 * 学习偏好类型与持久化
 * =================================================================== */
interface LearningPrefs {
  defaultDuration: number;
  difficulty: string;
  learningStyle: string;
  aiStyle: string;
  autoDiagnose: boolean;
  diagnoseDepth: string;
  learningTracking: boolean;
  ebbinghausReminder: boolean;
}

const DEFAULT_PREFS: LearningPrefs = {
  defaultDuration: 30,
  difficulty: 'intermediate',
  learningStyle: 'mixed',
  aiStyle: 'balanced',
  autoDiagnose: true,
  diagnoseDepth: 'deep',
  learningTracking: true,
  ebbinghausReminder: true,
};

function loadPrefs(): LearningPrefs {
  try {
    return { ...DEFAULT_PREFS, ...readStorageJson<Partial<LearningPrefs>>(runtimeStorageKeys.learningPrefs, {}) };
  } catch { return DEFAULT_PREFS; }
}

function savePrefs(prefs: LearningPrefs) {
  writeStorageJson(runtimeStorageKeys.learningPrefs, prefs);
}

/* ===================================================================
 * 深色模式工具
 * =================================================================== */
function loadTheme(): 'light' | 'dark' {
  try {
    const stored = localStorage.getItem(runtimeStorageKeys.theme.primary);
    if (stored === 'dark' || stored === 'light') return stored;
  } catch { /* noop */ }
  return 'light';
}

function applyTheme(theme: 'light' | 'dark') {
  const root = document.documentElement;
  if (theme === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }
  try {
    localStorage.setItem(runtimeStorageKeys.theme.primary, theme);
  } catch { /* noop */ }
}

/* ===================================================================
 * 字体大小工具（连续平滑缩放）
 * =================================================================== */
function loadFontSize(): number {
  try {
    const stored = parseFloat(localStorage.getItem(runtimeStorageKeys.fontSize.primary) || '');
    if (stored >= 12 && stored <= 22) return stored;
  } catch { /* noop */ }
  return 16;
}

function applyFontSize(size: number) {
  const scale = size / 16;
  document.documentElement.style.setProperty('--font-size-scale', String(scale));
  try {
    localStorage.setItem(runtimeStorageKeys.fontSize.primary, String(size));
  } catch { /* noop */ }
}

/* ===================================================================
 * SettingsPage
 * =================================================================== */
export default function SettingsPage() {
  const learner = getCurrentLearner();
  const { subjects } = useSubjectStore();

  // ── 选中分区 ──
  const [section, setSection] = useState('account');

  // ── 账户 ──
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState('');

  // ── 偏好（持久化） ──
  const [prefs, setPrefs] = useState<LearningPrefs>(loadPrefs);

  // ── 外观 ──
  const [darkMode, setDarkMode] = useState(() => loadTheme() === 'dark');
  const [fontSize, setFontSize] = useState(loadFontSize);

  // ── 数据管理 ──
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearDone, setClearDone] = useState(false);
  const [exportDone, setExportDone] = useState(false);
  const [cacheSize, setCacheSize] = useState(getCacheSize);

  // ── 初始化：应用已保存的外观设置 ──
  useEffect(() => {
    applyTheme(darkMode ? 'dark' : 'light');
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const updatePrefs = useCallback((updates: Partial<LearningPrefs>) => {
    const next = { ...prefs, ...updates };
    setPrefs(next);
    savePrefs(next);
  }, [prefs]);

  const handleSaveName = async () => {
    const name = nameInput.trim();
    if (!name || !learner) return;
    try {
      await useAuthStore.getState().updateProfile({ nickname: name });
      setEditingName(false);
    } catch {
      // Keep editing mode so user can retry
    }
  };

  const handleClearData = () => {
    safeClearCache();
    setShowClearConfirm(false);
    setClearDone(true);
    setCacheSize(0);
    setTimeout(() => setClearDone(false), 3000);
  };

  const handleExportData = () => {
    const data = exportAllData();
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
          importAllData(data);
          window.location.reload();
        } catch { alert('数据格式错误，导入失败'); }
      };
      reader.readAsText(file);
    };
    input.click();
  };

  const toggleDarkMode = () => {
    const next = !darkMode;
    setDarkMode(next);
    applyTheme(next ? 'dark' : 'light');
  };

  const handleFontSizeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const size = parseInt(e.target.value, 10);
    setFontSize(size);
    applyFontSize(size);
  };

  /* ===================================================================
   * 管道智能体列表
   * =================================================================== */
  const AGENTS = [
    { name: 'ProfileAgent', label: '画像分析', desc: '提取多维学习画像' },
    { name: 'KnowledgeAgent', label: '知识检索', desc: '检索课程知识库' },
    { name: 'DiagnosisAgent', label: '诊断分析', desc: '诊断知识短板' },
    { name: 'PlannerAgent', label: '路径规划', desc: '生成个性化路径' },
    { name: 'ResourceAgent', label: '资源生成', desc: '生成讲义/练习/导图' },
    { name: 'ReviewAgent', label: '质量检查', desc: '校验内容质量' },
  ];

  /* ===================================================================
   * 技术栈
   * =================================================================== */
  const TECH_STACK = [
    ['前端框架', 'React 19 + TypeScript'],
    ['样式方案', 'Tailwind CSS v4'],
    ['状态管理', 'Zustand 5'],
    ['后端框架', 'FastAPI 0.137'],
    ['数据库', 'SQLAlchemy + SQLite'],
    ['AI 架构', '多智能体协同编排'],
  ];

  /* ===================================================================
   * 渲染分区内容
   * =================================================================== */
  const renderSection = () => {
    switch (section) {
      /* ---- 账户设置 ---- */
      case 'account':
        return (
          <div className="space-y-4">
            <SectionHeader icon={User} title="账户设置" desc="管理个人信息与账户" />
            <div className="flex items-center gap-5 p-5 bg-white dark:bg-surface-700 border border-gray-100 dark:border-gray-600 rounded-2xl">
              <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-brand-500 to-accent-500 flex items-center justify-center text-white text-3xl font-bold shadow-md flex-shrink-0">
                {learner?.name?.charAt(0) || '?'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  {editingName ? (
                    <div className="flex items-center gap-1.5">
                      <input value={nameInput} onChange={e => setNameInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleSaveName()}
                        className="w-36 text-base bg-gray-50 dark:bg-surface-600 border border-gray-200 dark:border-gray-500 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-brand-500 dark:text-white"
                        autoFocus maxLength={20} />
                      <button onClick={handleSaveName} className="p-1.5 rounded-lg hover:bg-green-50 dark:hover:bg-green-500/10 text-green-600 transition-colors"><Check className="w-4 h-4" /></button>
                      <button onClick={() => setEditingName(false)} className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 text-gray-400 transition-colors"><X className="w-4 h-4" /></button>
                    </div>
                  ) : (
                    <>
                      <h3 className="text-xl font-bold text-gray-800 dark:text-gray-100">{learner?.name || '未命名'}</h3>
                      <button onClick={() => { setNameInput(learner?.name || ''); setEditingName(true); }}
                        className="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-surface-600 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
                        <Edit3 className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {subjects.length} 个科目 · 上次登录 {learner?.lastLoginAt ? new Date(learner.lastLoginAt).toLocaleDateString('zh-CN') : '—'}
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  {ROLE_LABEL[learner?.role || 'student']} · {learner?.grade || '未设置年级'} · {learner?.target_exam || '无目标考试'}
                </p>
              </div>
            </div>

            <SettingRow label="当前角色" description="你的账户角色">
              <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                {ROLE_LABEL[learner?.role || 'student']}
              </span>
            </SettingRow>

            <SettingRow label="年级" description={learner?.grade || '未设置'}>
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {learner?.grade || '—'}
              </span>
            </SettingRow>

            <SettingRow label="目标考试" description={learner?.target_exam || '未设置'}>
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {learner?.target_exam || '—'}
              </span>
            </SettingRow>

            {learner?.student_no && (
              <SettingRow label="学号" description="学生账号">
                <span className="text-sm font-mono text-gray-600 dark:text-gray-400">{learner.student_no}</span>
              </SettingRow>
            )}

            <SettingRow label="当前科目" description="已创建的科目数量">
              <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">{subjects.length} 个</span>
            </SettingRow>

            <SettingRow label="切换学习者" description="退出当前账号以切换身份">
              <button type="button" onClick={() => { useAuthStore.getState().logout(); window.location.href = '/login'; }}
                className="px-3 py-1.5 bg-gray-50 dark:bg-surface-600 border border-gray-200 dark:border-gray-500 rounded-lg text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-surface-500 transition-colors">
                切换账号
              </button>
            </SettingRow>
          </div>
        );

      /* ---- 学习偏好 ---- */
      case 'preferences':
        return (
          <div className="space-y-4">
            <SectionHeader icon={BookOpen} title="学习偏好" desc="个性化你的学习体验" />
            <p className="text-xs text-gray-400 dark:text-gray-500 font-semibold uppercase tracking-wider px-1">学习习惯</p>

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
        );

      /* ---- 对话设置 ---- */
      case 'chat':
        return (
          <div className="space-y-4">
            <SectionHeader icon={MessageSquare} title="对话设置" desc="配置 AI 回复和智能体行为" />
            <p className="text-xs text-gray-400 dark:text-gray-500 font-semibold uppercase tracking-wider px-1">AI 回复偏好</p>

            <SettingRow label="回复详细程度" description="控制 AI 回复的篇幅和深度">
              <Select value={prefs.aiStyle} options={[
                { value: 'concise', label: '⚡ 简洁（直击要点）' },
                { value: 'balanced', label: '⚖️ 平衡（适中篇幅）' },
                { value: 'detailed', label: '📚 详细（全面深入）' },
              ]} onChange={v => updatePrefs({ aiStyle: v })} />
            </SettingRow>

            <p className="text-xs text-gray-400 dark:text-gray-500 font-semibold uppercase tracking-wider px-1 pt-2">智能体管线</p>
            <div className="grid grid-cols-2 gap-2">
              {AGENTS.map(a => (
                <div key={a.name} className="flex items-center gap-2.5 px-3 py-2.5 bg-white dark:bg-surface-700 rounded-xl border border-gray-100 dark:border-gray-600">
                  <div className="w-7 h-7 rounded-lg bg-brand-100 dark:bg-brand-500/20 flex items-center justify-center flex-shrink-0">
                    <Brain className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">{a.label}</p>
                    <p className="text-[10px] text-gray-400 dark:text-gray-500">{a.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );

      /* ---- 诊断设置 ---- */
      case 'diagnosis':
        return (
          <div className="space-y-4">
            <SectionHeader icon={Activity} title="诊断设置" desc="配置学习诊断与分析参数" />
            <p className="text-xs text-gray-400 dark:text-gray-500 font-semibold uppercase tracking-wider px-1">诊断配置</p>

            <SettingRow label="自动诊断" description="每次对话后自动分析知识短板">
              <Toggle value={prefs.autoDiagnose} onChange={v => updatePrefs({ autoDiagnose: v })} />
            </SettingRow>

            <SettingRow label="诊断深度" description="控制知识分析的粒度">
              <Select value={prefs.diagnoseDepth} options={[
                { value: 'basic', label: '📊 基础（知识点层面）' },
                { value: 'deep', label: '🔍 深入（概念关联分析）' },
                { value: 'comprehensive', label: '🧠 全面（含交叉领域）' },
              ]} onChange={v => updatePrefs({ diagnoseDepth: v })} />
            </SettingRow>

            <p className="text-xs text-gray-400 dark:text-gray-500 font-semibold uppercase tracking-wider px-1 pt-2">学习分析</p>

            <SettingRow label="学习追踪" description="记录学习时长和完成情况">
              <Toggle value={prefs.learningTracking} onChange={v => updatePrefs({ learningTracking: v })} />
            </SettingRow>

            <SettingRow label="艾宾浩斯复习提醒" description="基于遗忘曲线安排复习计划">
              <Toggle value={prefs.ebbinghausReminder} onChange={v => updatePrefs({ ebbinghausReminder: v })} />
            </SettingRow>
          </div>
        );

      /* ---- 数据管理 ---- */
      case 'data':
        return (
          <div className="space-y-4">
            <SectionHeader icon={Database} title="数据管理" desc="管理本地学习数据与备份" />
            <p className="text-xs text-gray-400 dark:text-gray-500 font-semibold uppercase tracking-wider px-1">本地数据</p>

            <SettingRow label="导出数据" description="将所有本地数据导出为 JSON 备份文件">
              <div className="flex items-center gap-2">
                {exportDone && <span className="text-xs text-green-500 font-medium">✓ 已导出</span>}
                <button type="button" onClick={handleExportData}
                  className="flex items-center gap-1.5 px-3 py-2 bg-white dark:bg-surface-600 border border-gray-200 dark:border-gray-500 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-surface-500 transition-colors">
                  <Download className="w-3.5 h-3.5" /> 导出
                </button>
              </div>
            </SettingRow>

            <SettingRow label="导入数据" description="从备份文件恢复数据">
              <button type="button" onClick={handleImportData}
                className="flex items-center gap-1.5 px-3 py-2 bg-white dark:bg-surface-600 border border-gray-200 dark:border-gray-500 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-surface-500 transition-colors">
                <Upload className="w-3.5 h-3.5" /> 导入
              </button>
            </SettingRow>

            <SettingRow label="清除本地数据" description="保留学习者信息，清除其余缓存">
              {showClearConfirm ? (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-red-500 font-medium">确认清除？</span>
                  <button onClick={handleClearData}
                    className="px-2.5 py-1.5 bg-red-500 text-white rounded-lg text-xs font-semibold hover:bg-red-600 transition-colors">确认</button>
                  <button onClick={() => setShowClearConfirm(false)}
                    className="px-2.5 py-1.5 bg-gray-100 dark:bg-gray-600 text-gray-600 dark:text-gray-300 rounded-lg text-xs font-medium hover:bg-gray-200 dark:hover:bg-gray-500 transition-colors">取消</button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  {clearDone && <span className="text-xs text-green-500 font-medium">✓ 已清除</span>}
                  <button onClick={() => setShowClearConfirm(true)}
                    className="flex items-center gap-1.5 px-3 py-2 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 rounded-lg text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors">
                    <Trash2 className="w-3.5 h-3.5" /> 清除
                  </button>
                </div>
              )}
            </SettingRow>

            <p className="text-xs text-gray-400 dark:text-gray-500 font-semibold uppercase tracking-wider px-1 pt-2">存储统计</p>
            <SettingRow label="本地存储用量">
              <span className="text-sm font-semibold text-gray-600 dark:text-gray-300">
                {formatBytes(cacheSize)}
              </span>
            </SettingRow>
          </div>
        );

      /* ---- 外观设置 ---- */
      case 'appearance':
        return (
          <div className="space-y-4">
            <SectionHeader icon={Palette} title="外观设置" desc="自定义界面风格与显示效果" />
            <p className="text-xs text-gray-400 dark:text-gray-500 font-semibold uppercase tracking-wider px-1">主题</p>

            <SettingRow label="深色模式" description="切换深色/浅色主题">
              <div className="flex items-center gap-2">
                {darkMode ? <Moon className="w-4 h-4 text-brand-500" /> : <Sun className="w-4 h-4 text-warning-500" />}
                <Toggle value={darkMode} onChange={toggleDarkMode} />
              </div>
            </SettingRow>

            <p className="text-xs text-gray-400 dark:text-gray-500 font-semibold uppercase tracking-wider px-1 pt-2">显示</p>

            <div className="py-4 px-5 bg-white dark:bg-surface-700 border border-gray-100 dark:border-gray-600 rounded-xl">
              <div className="flex items-center gap-3 mb-4">
                <span className="text-xs text-gray-400 dark:text-gray-500">A</span>
                <div className="flex-1">
                  <p className="text-sm font-medium text-gray-800 dark:text-gray-100">字体大小</p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">调整界面文字大小 · <span className="font-semibold text-brand-500">{fontSize.toFixed(0)}px</span></p>
                </div>
                <span className="text-xl text-gray-400 dark:text-gray-500">A</span>
              </div>
              <input type="range" min="12" max="22" step="0.5" value={fontSize} onChange={handleFontSizeChange}
                className="w-full h-1.5 bg-gradient-to-r from-gray-200 via-brand-400 to-gray-600 dark:from-gray-600 dark:via-brand-500 dark:to-gray-200 rounded-full appearance-none cursor-pointer
                  [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5
                  [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-brand-500
                  [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-thumb]:cursor-pointer
                  [&::-webkit-slider-thumb]:hover:scale-110 [&::-webkit-slider-thumb]:transition-transform" />
              <div className="flex justify-between mt-2">
                <span className="text-[10px] text-gray-400">12px</span>
                <span className="text-[10px] text-gray-400">16px</span>
                <span className="text-[10px] text-gray-400">22px</span>
              </div>
            </div>
          </div>
        );

      /* ---- 关于 ---- */
      case 'about':
        return (
          <div className="space-y-4">
            <SectionHeader icon={Info} title="关于 EduAgent" desc="版本信息与技术栈" />

            <div className="bg-gradient-to-br from-brand-500/5 to-accent-500/5 dark:from-brand-500/10 dark:to-accent-500/10 border border-brand-100 dark:border-brand-500/20 rounded-2xl p-6 text-center">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500 to-accent-500 flex items-center justify-center mx-auto mb-3 shadow-lg">
                <GraduationCap className="w-8 h-8 text-white" />
              </div>
              <h3 className="text-2xl font-extrabold text-gray-800 dark:text-gray-100">EduAgent</h3>
              <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">v0.3.0 · 2026.06</p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 leading-relaxed max-w-md mx-auto">
                面向课程工作流与模块集成的本地演示套件
              </p>
            </div>

            <p className="text-xs text-gray-400 dark:text-gray-500 font-semibold uppercase tracking-wider px-1 pt-2">技术栈</p>
            <div className="grid grid-cols-2 gap-2">
              {TECH_STACK.map(([label, value]) => (
                <div key={label} className="px-3 py-2.5 bg-white dark:bg-surface-700 rounded-xl border border-gray-100 dark:border-gray-600">
                  <p className="text-[10px] text-gray-400 dark:text-gray-500">{label}</p>
                  <p className="text-xs font-semibold text-gray-700 dark:text-gray-200 mt-0.5">{value}</p>
                </div>
              ))}
            </div>

            <p className="text-xs text-gray-400 dark:text-gray-500 font-semibold uppercase tracking-wider px-1 pt-2">智能体架构</p>
            <div className="flex flex-wrap gap-1.5">
              {AGENTS.map(a => (
                <span key={a.label} className="px-2.5 py-1 bg-brand-50 dark:bg-brand-500/10 border border-brand-100 dark:border-brand-500/20 rounded-lg text-xs text-brand-600 dark:text-brand-400 font-medium">
                  {a.label}
                </span>
              ))}
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="font-display text-2xl font-bold text-surface-800 dark:text-gray-100">系统设置</h2>
        <p className="text-surface-500 dark:text-gray-400 mt-1">个性化你的学习体验</p>
      </div>

      {/* ======== 左右布局 ======== */}
      <div className="flex gap-6">
        {/* ===== 左侧导航 ===== */}
        <div className="w-48 flex-shrink-0">
          <nav className="bg-white dark:bg-surface-700 rounded-2xl p-2 shadow-soft space-y-0.5 sticky top-24">
            {NAV_SECTIONS.map(s => {
              const isActive = section === s.id;
              return (
                <button key={s.id} type="button" onClick={() => setSection(s.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-left transition-all ${
                    isActive
                      ? 'bg-brand-500/10 dark:bg-brand-500/20 text-brand-600 dark:text-brand-400 font-medium'
                      : 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-surface-600 hover:text-gray-700 dark:hover:text-gray-200'
                  }`}>
                  <s.icon className={`w-4.5 h-4.5 ${isActive ? 'text-brand-500 dark:text-brand-400' : 'text-gray-400 dark:text-gray-500'}`} />
                  <span className="text-sm">{s.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* ===== 右侧内容 ===== */}
        <div className="flex-1 min-w-0 bg-white dark:bg-surface-700 rounded-2xl p-6 shadow-soft">
          {renderSection()}
        </div>
      </div>
    </div>
  );
}

/* ===================================================================
 * 分区标题组件
 * =================================================================== */
function SectionHeader({ icon: Icon, title, desc }: {
  icon: React.ElementType;
  title: string;
  desc: string;
}) {
  return (
    <div className="flex items-center justify-between pb-4 border-b border-gray-100 dark:border-gray-600">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-brand-50 dark:bg-brand-500/10 flex items-center justify-center">
          <Icon size={18} className="text-brand-600 dark:text-brand-400" />
        </div>
        <div>
          <h3 className="font-display text-lg font-semibold text-gray-800 dark:text-gray-100">{title}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{desc}</p>
        </div>
      </div>
    </div>
  );
}
