/**
 * Adaptive action generators — determine what quick actions / generate buttons
 * to show based on mode, task_type, subject category, and course.
 *
 * Single source of truth for all context-aware UI actions.
 * No hardcoded one-size-fits-all buttons.
 */

export interface ActionItem {
  key: string;
  label: string;
  icon: string;
  desc: string;
  /** If set, this calls lecture/generate with this type */
  genType?: string;
  /** If set, this sends a prompt to the tutor */
  tutorPrompt?: string;
}

// ══════════════════════════════════════════════════════════════════════
// Subject category detection (mirrors backend _detect_subject_category)
// ══════════════════════════════════════════════════════════════════════

function detectCategory(course: string): string {
  const t = course.toLowerCase();
  if (/编程|python|java|c语言|c\+\+|数据结构|算法|计算机|代码|程序设计|软件开发|前端|后端|数据库|sql|操作系统|网络|programming|code/.test(t)) return 'programming';
  if (/数学|微积分|线性代数|概率|统计|高等数学|离散|几何|代数|拓扑|数论|物理|力学|电磁|光学|热学|量子|化学|有机|无机|calculus|math|physics|chemistry/.test(t)) return 'math_science';
  if (/历史|古代|近代|现代|世界史|中国史|文明|朝代|文学|哲学|艺术|音乐|美术|诗歌|小说|散文|history|literature|philosophy/.test(t)) return 'humanities';
  if (/英语|日语|韩语|法语|德语|西语|词汇|语法|听力|口语|写作|阅读|翻译|english|japanese|语言/.test(t)) return 'language';
  return 'general';
}

// ══════════════════════════════════════════════════════════════════════
// Daily mode — quick tutor prompts adapt to task_type + course
// ══════════════════════════════════════════════════════════════════════

export function dailyQuickActions(taskType: string, course: string, sectionTitle: string): ActionItem[] {
  const cat = detectCategory(course);
  const isLang = cat === 'language';
  const isProg = cat === 'programming';
  const isMath = cat === 'math_science';

  const base: ActionItem[] = [
    { key: 'explain', label: isLang ? '用中文讲解' : '文字讲解', icon: '📖',
      desc: `详细讲解本节内容`, tutorPrompt: `请详细讲解「${sectionTitle}」的核心内容和要点。` },
  ];

  if (taskType === 'vocabulary') {
    if (isLang) {
      base.push(
        { key: 'sentences', label: '生成例句', icon: '💬', desc: '每个词配一个地道例句', tutorPrompt: `请为「${sectionTitle}」中的每个词汇配一个地道的${course || '目标语言'}例句，帮助理解用法。` },
        { key: 'dictation', label: '听写练习', icon: '🎧', desc: '列出词汇供听写自测', tutorPrompt: `请列出「${sectionTitle}」的词汇（只写${course || '目标语言'}词汇不写释义），供我听写自测。` },
        { key: 'quiz', label: '词汇测验', icon: '📝', desc: '5道词汇选择题', genType: 'quiz' },
      );
    } else if (isProg) {
      base.push(
        { key: 'compare', label: '术语对比', icon: '🔍', desc: '对比相似术语的区别', tutorPrompt: `请对比「${sectionTitle}」中容易混淆的编程术语，说明它们的区别和适用场景。` },
        { key: 'quiz', label: '术语测验', icon: '📝', desc: '术语填空/选择题', genType: 'quiz' },
      );
    } else if (isMath) {
      base.push(
        { key: 'formulas', label: '公式速查', icon: '📐', desc: 'LaTeX公式卡片', tutorPrompt: `请用LaTeX格式列出「${sectionTitle}」的核心公式，每个附一句话直觉解释。` },
        { key: 'quiz', label: '概念测验', icon: '📝', desc: '概念选择题', genType: 'quiz' },
      );
    }
  }

  if (taskType === 'listening') {
    base.push(
      { key: 'script', label: '显示脚本', icon: '📄', desc: '查看完整听力文本', tutorPrompt: `请提供「${sectionTitle}」的完整听力脚本文本。` },
      { key: 'quiz', label: '听力题', icon: '📝', desc: '生成理解选择题', genType: 'quiz' },
    );
  }

  if (taskType === 'reading') {
    base.push(
      { key: 'vocab', label: '生词表', icon: '📋', desc: '提取文章核心词汇', tutorPrompt: `请从「${sectionTitle}」的阅读文章中提取核心词汇，列出词汇、释义和例句。` },
      { key: 'quiz', label: '阅读题', icon: '📝', desc: '生成阅读理解题', genType: 'quiz' },
    );
  }

  if (taskType === 'grammar') {
    base.push(
      { key: 'practice', label: '语法练习', icon: '✏️', desc: '填空/改错练习', genType: 'quiz' },
      { key: 'compare', label: '易混对比', icon: '🔍', desc: '对比容易混淆的规则', tutorPrompt: `请对比「${sectionTitle}」中容易混淆的语法规则，用表格说明区别。` },
    );
  }

  if (taskType === 'speaking') {
    base.push(
      { key: 'dialogue', label: '对话练习', icon: '💬', desc: '生成对话模板', tutorPrompt: `请为「${sectionTitle}」生成一段${isLang ? course : ''}对话模板，10-15轮，标注发音要点。` },
      { key: 'pronounce', label: '发音指导', icon: '🔊', desc: '发音要点和音标', tutorPrompt: `请详细说明「${sectionTitle}」中的发音要点，标注音标和常见错误。` },
    );
  }

  if (taskType === 'writing') {
    base.push(
      { key: 'outline', label: '写作提纲', icon: '📋', desc: '生成详细提纲', tutorPrompt: `请为「${sectionTitle}」生成一份详细的写作提纲（3-5段结构）。` },
      { key: 'sample', label: '参考范文', icon: '📄', desc: '生成一篇范文', genType: 'reading' },
    );
  }

  if (taskType === 'review') {
    base.push(
      { key: 'summary', label: '知识总结', icon: '📋', desc: '总结本节要点', tutorPrompt: `请总结「${sectionTitle}」的核心知识和易错点。` },
      { key: 'quiz', label: '综合测验', icon: '📝', desc: '生成综合测题', genType: 'quiz' },
    );
  }

  // Fallback for unknown task types
  if (base.length === 1) {
    base.push(
      { key: 'diagram', label: '图解结构', icon: '🧠', desc: 'Mermaid知识结构图', tutorPrompt: `请用mermaid flowchart LR绘制「${sectionTitle}」的知识结构图。` },
      { key: 'quiz', label: '小测验', icon: '📝', desc: '5道练习', genType: 'quiz' },
    );
  }

  return base;
}

// ══════════════════════════════════════════════════════════════════════
// Focus mode — sprint actions
// ══════════════════════════════════════════════════════════════════════

export function focusQuickActions(course: string, sectionTitle: string): ActionItem[] {
  return [
    { key: 'diagnose', label: '薄弱点诊断', icon: '🔍', desc: '分析具体哪里不会', tutorPrompt: `请针对「${sectionTitle}」出一组诊断题（3-5题），帮我定位具体的薄弱点在哪里。` },
    { key: 'practice', label: '针对性练习', icon: '🎯', desc: '专门攻这个薄弱点', genType: 'quiz' },
    { key: 'explain', label: '概念讲解', icon: '📖', desc: '讲解核心要点', tutorPrompt: `请讲解「${sectionTitle}」的核心要点和常见误区。` },
  ];
}

// ══════════════════════════════════════════════════════════════════════
// Textbook mode — generate panel actions adapt to subject
// ══════════════════════════════════════════════════════════════════════

export function textbookGenerateActions(course: string): ActionItem[] {
  const cat = detectCategory(course);
  const actions: ActionItem[] = [
    { key: 'lecture', label: '生成教材', icon: '📖', desc: '正式出版级别的教材内容' },
  ];

  if (cat === 'math_science') {
    actions.push(
      { key: 'exercises', label: '生成习题集', icon: '📐', desc: '基础+进阶+思考题', genType: 'quiz' },
      { key: 'mindmap', label: '生成公式导图', icon: '🧠', desc: '定理和公式关系图', genType: 'mindmap' },
    );
  } else if (cat === 'programming') {
    actions.push(
      { key: 'practice', label: '生成编程练习', icon: '💻', desc: '完整编程题+测试用例' },
      { key: 'mindmap', label: '生成算法导图', icon: '🧠', desc: '算法关系结构图', genType: 'mindmap' },
    );
  } else if (cat === 'humanities') {
    actions.push(
      { key: 'timeline', label: '生成时间线', icon: '📅', desc: '历史事件时间线' },
      { key: 'reading', label: '生成延伸阅读', icon: '📚', desc: '原典/研究著作推荐' },
    );
  } else if (cat === 'language') {
    actions.push(
      { key: 'vocab', label: '生成词汇表', icon: '📋', desc: '核心词汇+例句+辨析', genType: 'quiz' },
      { key: 'exercises', label: '生成练习', icon: '📝', desc: '互译+情景写作题', genType: 'quiz' },
    );
  } else {
    actions.push(
      { key: 'quiz', label: '生成练习', icon: '📝', desc: '课后练习题', genType: 'quiz' },
      { key: 'mindmap', label: '生成思维导图', icon: '🧠', desc: '知识结构可视化', genType: 'mindmap' },
    );
  }

  return actions;
}
