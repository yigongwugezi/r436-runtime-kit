// @ts-nocheck
import React, { useState } from 'react';
import {
  User, Bell, Palette, Shield, Database, HelpCircle, ChevronRight, Moon, Sun, Globe, Volume2, Download, Upload, Trash2, GraduationCap,
} from 'lucide-react';
import { getCurrentLearner, logoutLearner } from './LoginPage';
import { useSubjectStore } from '../store/subjectStore';
import { readStorageJson, writeStorageJson, runtimeStorageKeys } from '../utils/storageKeys';
import { safeClearCache, exportAllData, importAllData, getCacheSize, formatBytes } from '../utils/cache';

interface SettingsSection { id: string; label: string; icon: React.ReactNode; description: string; }

const settingsSections: SettingsSection[] = [
  { id: 'account', label: '账户设置', icon: <User size={20} />, description: '管理你的账户信息' },
  { id: 'notifications', label: '通知设置', icon: <Bell size={20} />, description: '配置通知提醒' },
  { id: 'appearance', label: '外观设置', icon: <Palette size={20} />, description: '自定义界面样式' },
  { id: 'privacy', label: '隐私安全', icon: <Shield size={20} />, description: '数据安全与隐私' },
  { id: 'data', label: '数据管理', icon: <Database size={20} />, description: '学习数据管理' },
  { id: 'help', label: '帮助支持', icon: <HelpCircle size={20} />, description: '使用指南与反馈' },
];

export default function SettingsPage() {
  const learner = getCurrentLearner();
  const { subjects } = useSubjectStore();
  const [selectedSection, setSelectedSection] = useState('appearance');
  const [darkMode, setDarkMode] = useState(false);
  const [notifications, setNotifications] = useState({ email: true, push: true, sound: false, weekly: true });
  const [exportMsg, setExportMsg] = useState('');
  const [clearMsg, setClearMsg] = useState('');

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="font-display text-2xl font-bold text-surface-800">系统设置</h2>
        <p className="text-surface-500 mt-1">个性化你的学习体验</p>
      </div>

      <div className="grid grid-cols-4 gap-6">
        <div className="bg-white rounded-2xl p-2 shadow-soft h-fit">
          <nav className="space-y-1">
            {settingsSections.map(section => {
              const isActive = selectedSection === section.id;
              return (
                <button key={section.id} onClick={() => setSelectedSection(section.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${isActive ? 'bg-primary-50 text-primary-600' : 'text-surface-600 hover:bg-surface-50'}`}>
                  <span className={isActive ? 'text-primary-600' : 'text-surface-400'}>{section.icon}</span>
                  <div className="flex-1 text-left"><p className={`text-sm font-medium ${isActive ? 'text-primary-700' : 'text-surface-700'}`}>{section.label}</p></div>
                  {isActive && <ChevronRight size={16} className="text-primary-400" />}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="col-span-3 bg-white rounded-2xl p-6 shadow-soft">
          {selectedSection === 'appearance' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between pb-4 border-b border-surface-100">
                <div><h3 className="font-display text-lg font-semibold text-surface-800">外观设置</h3><p className="text-sm text-surface-500 mt-1">自定义你的界面风格</p></div>
              </div>
              <div className="flex items-center justify-between p-4 rounded-xl bg-surface-50">
                <div className="flex items-center gap-3">{darkMode ? <Moon size={20} className="text-primary-600" /> : <Sun size={20} className="text-warning-500" />}<div><p className="font-medium text-surface-800">深色模式</p><p className="text-sm text-surface-500">切换深色/浅色主题</p></div></div>
                <button onClick={() => setDarkMode(!darkMode)} className={`w-14 h-8 rounded-full transition-colors ${darkMode ? 'bg-primary-600' : 'bg-surface-200'}`}><div className={`w-6 h-6 rounded-full bg-white shadow-md transition-transform ${darkMode ? 'translate-x-7' : 'translate-x-1'}`} /></button>
              </div>
              <div className="flex items-center justify-between p-4 rounded-xl bg-surface-50">
                <div className="flex items-center gap-3"><Globe size={20} className="text-accent-600" /><div><p className="font-medium text-surface-800">语言设置</p><p className="text-sm text-surface-500">选择界面语言</p></div></div>
                <select className="px-4 py-2 bg-white border border-surface-200 rounded-lg text-surface-700 focus:outline-none focus:ring-2 focus:ring-primary-200"><option>简体中文</option><option>English</option></select>
              </div>
              <div className="p-4 rounded-xl bg-surface-50">
                <div className="flex items-center gap-3 mb-4"><Volume2 size={20} className="text-warning-600" /><div><p className="font-medium text-surface-800">字体大小</p><p className="text-sm text-surface-500">调整界面文字大小</p></div></div>
                <div className="flex items-center gap-4"><span className="text-sm text-surface-500">小</span><input type="range" min="12" max="20" defaultValue="16" className="flex-1 h-2 bg-surface-200 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-primary-600 [&::-webkit-slider-thumb]:rounded-full" /><span className="text-sm text-surface-500">大</span></div>
              </div>
            </div>
          )}

          {selectedSection === 'notifications' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between pb-4 border-b border-surface-100"><div><h3 className="font-display text-lg font-semibold text-surface-800">通知设置</h3><p className="text-sm text-surface-500 mt-1">管理你的通知偏好</p></div></div>
              {Object.entries({ email: { label: '邮件通知', desc: '接收学习提醒邮件' }, push: { label: '推送通知', desc: '浏览器推送提醒' }, sound: { label: '声音提醒', desc: '播放提示音' }, weekly: { label: '周报告', desc: '每周学习总结邮件' } }).map(([key, config]) => (
                <div key={key} className="flex items-center justify-between p-4 rounded-xl bg-surface-50">
                  <div><p className="font-medium text-surface-800">{config.label}</p><p className="text-sm text-surface-500">{config.desc}</p></div>
                  <button onClick={() => setNotifications(prev => ({ ...prev, [key]: !prev[key] }))} className={`w-14 h-8 rounded-full transition-colors ${notifications[key] ? 'bg-primary-600' : 'bg-surface-200'}`}><div className={`w-6 h-6 rounded-full bg-white shadow-md transition-transform ${notifications[key] ? 'translate-x-7' : 'translate-x-1'}`} /></button>
                </div>
              ))}
            </div>
          )}

          {selectedSection === 'account' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between pb-4 border-b border-surface-100"><div><h3 className="font-display text-lg font-semibold text-surface-800">账户设置</h3><p className="text-sm text-surface-500 mt-1">管理你的账户信息</p></div></div>
              <div className="flex items-center gap-6">
                <div className="w-24 h-24 rounded-2xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center text-white text-3xl font-bold">{learner?.name?.charAt(0) || '?'}</div>
                <div><h4 className="text-lg font-semibold text-surface-800">{learner?.name || '未命名'}</h4><p className="text-surface-500">{subjects.length} 个科目 · 上次登录 {learner?.lastLoginAt ? new Date(learner.lastLoginAt).toLocaleDateString('zh-CN') : '—'}</p><button className="mt-2 text-sm text-primary-600 hover:text-primary-700 font-medium" onClick={() => { logoutLearner(); window.location.href = '/login'; }}>切换学习者</button></div>
              </div>
            </div>
          )}

          {selectedSection === 'data' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between pb-4 border-b border-surface-100"><div><h3 className="font-display text-lg font-semibold text-surface-800">数据管理</h3><p className="text-sm text-surface-500 mt-1">管理本地学习数据</p></div></div>
              <div className="space-y-3">
                <div className="flex items-center justify-between p-4 rounded-xl bg-surface-50">
                  <div><p className="font-medium text-surface-800">导出数据</p><p className="text-sm text-surface-500">将所有本地数据导出为 JSON 文件</p></div>
                  <button onClick={() => { const data = exportAllData(); const blob = new Blob([JSON.stringify(data,null,2)],{type:'application/json'}); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `eduagent_backup_${new Date().toISOString().slice(0,10)}.json`; a.click(); URL.revokeObjectURL(url); setExportMsg('已导出'); setTimeout(()=>setExportMsg(''),3000); }} className="flex items-center gap-2 px-4 py-2 bg-primary-50 text-primary-600 rounded-xl text-sm font-medium hover:bg-primary-100 transition-colors"><Download size={16} />{exportMsg||'导出'}</button>
                </div>
                <div className="flex items-center justify-between p-4 rounded-xl bg-surface-50">
                  <div><p className="font-medium text-surface-800">导入数据</p><p className="text-sm text-surface-500">从备份文件恢复数据</p></div>
                  <button onClick={() => { const input = document.createElement('input'); input.type = 'file'; input.accept = '.json'; input.onchange = (e) => { const file = (e.target as HTMLInputElement).files?.[0]; if(!file) return; const reader = new FileReader(); reader.onload = () => { try { importAllData(JSON.parse(reader.result as string)); window.location.reload(); } catch { alert('数据格式错误'); } }; reader.readAsText(file); }; input.click(); }} className="flex items-center gap-2 px-4 py-2 bg-primary-50 text-primary-600 rounded-xl text-sm font-medium hover:bg-primary-100 transition-colors"><Upload size={16} />导入</button>
                </div>
                <div className="flex items-center justify-between p-4 rounded-xl bg-surface-50">
                  <div><p className="font-medium text-surface-800">清除缓存</p><p className="text-sm text-surface-500">保留学习者信息，清除其余数据 · {formatBytes(getCacheSize())}</p></div>
                  <button onClick={() => { safeClearCache(); setClearMsg('已清除'); setTimeout(()=>setClearMsg(''),3000); }} className="flex items-center gap-2 px-4 py-2 bg-error-50 text-error-600 rounded-xl text-sm font-medium hover:bg-error-100 transition-colors"><Trash2 size={16} />{clearMsg||'清除'}</button>
                </div>
              </div>
            </div>
          )}

          {selectedSection === 'help' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between pb-4 border-b border-surface-100"><div><h3 className="font-display text-lg font-semibold text-surface-800">关于 EduAgent</h3><p className="text-sm text-surface-500 mt-1">版本与技术支持</p></div></div>
              <div className="bg-gradient-to-br from-primary-50 to-accent-50 rounded-2xl p-6 text-center">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center mx-auto mb-3 shadow-lg"><GraduationCap size={32} className="text-white" /></div>
                <h3 className="font-display text-xl font-bold text-surface-800">EduAgent</h3>
                <p className="text-surface-500 text-sm mt-1">v0.3.0 · 2026.06</p>
                <p className="text-surface-400 text-sm mt-2 max-w-sm mx-auto">面向课程工作流与模块集成的本地演示套件</p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {[['前端框架','React 19 + TypeScript'],['样式方案','Tailwind CSS'],['状态管理','Zustand'],['后端框架','FastAPI'],['数据库','SQLAlchemy + SQLite'],['AI架构','多智能体协同']].map(([l,v]) => <div key={l} className="p-3 bg-surface-50 rounded-xl"><p className="text-[10px] text-surface-400">{l}</p><p className="text-xs font-semibold text-surface-700 mt-0.5">{v}</p></div>)}
              </div>
            </div>
          )}

          {!['appearance', 'notifications', 'account', 'data', 'help'].includes(selectedSection) && (
            <div className="text-center py-16"><div className="w-16 h-16 mx-auto rounded-2xl bg-surface-100 flex items-center justify-center mb-4"><HelpCircle size={32} className="text-surface-400" /></div><p className="text-surface-600 font-medium">功能开发中</p><p className="text-sm text-surface-400 mt-1">敬请期待</p></div>
          )}
        </div>
      </div>
    </div>
  );
}
