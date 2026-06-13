import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Brain, Sparkles, ArrowRight, MessageSquare,
  Users, TrendingUp, Zap, Star,
  CheckCircle2, Bot, Cpu, Target, GitFork, BookOpen,
  Menu, X, ChevronRight, Shield,
} from 'lucide-react';

/* ===================================================================
 * 数据定义
 * =================================================================== */

const stats = [
  { icon: Users, value: '10,000+', label: '服务学生', color: 'from-blue-500 to-cyan-500' },
  { icon: TrendingUp, value: '90%', label: '效率提升', color: 'from-green-500 to-emerald-500' },
  { icon: Star, value: '4.8', label: '用户评分', color: 'from-amber-400 to-orange-500' },
  { icon: Zap, value: '24/7', label: '全天候在线', color: 'from-purple-500 to-pink-500' },
];

const features = [
  {
    icon: Cpu,
    title: '多智能体协同架构',
    description: '10 个专业 Agent 分工协作，每个智能体专注单一任务，协同完成复杂的学习服务流程。',
    points: ['画像分析 Agent', '学习诊断 Agent', '路径规划 Agent', '资源生成 Agent', '质量检查 Agent'],
    gradient: 'from-indigo-500 to-blue-600',
    bgLight: 'bg-indigo-50',
    textColor: 'text-indigo-600',
  },
  {
    icon: Target,
    title: '10 维度精准画像',
    description: '从专业背景到学习节奏，全方位深度理解每位学习者的独特需求与偏好，实现真正的因材施教。',
    points: ['专业背景', '知识基础', '学习目标', '认知风格', '编程能力', '学习节奏'],
    gradient: 'from-violet-500 to-purple-600',
    bgLight: 'bg-violet-50',
    textColor: 'text-violet-600',
  },
  {
    icon: GitFork,
    title: '动态学习路径规划',
    description: '基于知识图谱和 DAG 依赖关系，自动规划最优学习顺序，根据学习进度实时动态调整。',
    points: ['知识图谱构建', 'DAG 拓扑排序', '艾宾浩斯复习', '自适应难度', '考前冲刺模式'],
    gradient: 'from-cyan-500 to-teal-600',
    bgLight: 'bg-cyan-50',
    textColor: 'text-cyan-600',
  },
  {
    icon: BookOpen,
    title: '5 种多模态资源',
    description: '根据学习需求自动生成讲义、思维导图、练习题、拓展阅读、实操案例等多种学习材料。',
    points: ['个性化讲义', '思维导图', '练习题', '拓展阅读', '实操案例', '教学视频'],
    gradient: 'from-emerald-500 to-green-600',
    bgLight: 'bg-emerald-50',
    textColor: 'text-emerald-600',
  },
];

const steps = [
  {
    step: '01',
    icon: MessageSquare,
    title: '对话描述需求',
    description: '像和朋友聊天一样，告诉 AI 你的专业、基础和目标。',
    detail: '无需填表，无需测试。系统通过自然语言对话自动提取你的 10 维度学习画像，精准理解你的需求。',
  },
  {
    step: '02',
    icon: Brain,
    title: '多智能体协同分析',
    description: '10 个智能体同时工作，深度诊断知识短板并生成个性化学习方案。',
    detail: '画像分析、知识诊断、路径规划、资源生成同步进行，数十秒内完成全部分析和规划。',
  },
  {
    step: '03',
    icon: BookOpen,
    title: '个性化高效学习',
    description: '按规划路径开始学习，获得持续更新的专属学习资源。',
    detail: '5 种多模态资源实时生成，学习进度动态追踪，根据掌握情况自动调整后续学习计划。',
  },
];

const agentList = [
  { name: '画像分析', role: '提取学习画像', active: true },
  { name: '诊断分析', role: '识别知识短板', active: true },
  { name: '路径规划', role: '规划学习路线', active: true },
  { name: '讲义生成', role: '生成课程讲义', active: false },
  { name: '题库生成', role: '生成练习题', active: false },
  { name: '思维导图', role: '生成知识导图', active: false },
  { name: '案例生成', role: '生成实操案例', active: false },
  { name: '质量检查', role: '校验内容质量', active: false },
];

const reviews = [
  {
    name: '张同学',
    role: '大二学生 · 计算机学院',
    text: '我基础比较薄弱，传统课程跟不上。EduAgent 帮我精准定位了知识短板，从最基础的线性代数开始补起，两周就掌握了机器学习入门。',
    stars: 5,
  },
  {
    name: '李同学',
    role: '大三学生 · 电子信息学院',
    text: '准备考研复习时用了 EduAgent，它自动生成的知识导图帮我理清了整个学科体系，练习题也很有针对性。效率比盲目刷题高太多了。',
    stars: 5,
  },
  {
    name: '王老师',
    role: '讲师 · 人工智能学院',
    text: '作为教学辅助工具非常出色。可以根据每个学生的不同水平自动调整教学内容和难度，真正实现了因材施教。已经推荐给整个教研室使用。',
    stars: 4,
  },
];

const navItems = [
  { label: '功能', href: '#features' },
  { label: '流程', href: '#how-it-works' },
  { label: '架构', href: '#architecture' },
  { label: '评价', href: '#testimonials' },
];

/* ===================================================================
 * 子组件
 * =================================================================== */

function StatCard({ icon: Icon, value, label, color }: typeof stats[0]) {
  return (
    <div className="group bg-white border border-gray-100 rounded-2xl p-6 text-center shadow-sm hover:shadow-lg hover:-translate-y-1 transition-all duration-300">
      <div className={`w-12 h-12 rounded-2xl bg-gradient-to-br ${color} flex items-center justify-center mx-auto mb-4 shadow-lg`}>
        <Icon className="w-6 h-6 text-white" />
      </div>
      <p className="text-3xl font-extrabold text-gray-900 mb-1">{value}</p>
      <p className="text-sm text-gray-500">{label}</p>
    </div>
  );
}

function FeatureCard({ icon: Icon, title, description, points, bgLight, textColor }: typeof features[0]) {
  return (
    <div className="group bg-white border border-gray-100 rounded-2xl p-8 hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
      <div className={`w-14 h-14 rounded-2xl ${bgLight} flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300`}>
        <Icon className={`w-7 h-7 ${textColor}`} />
      </div>
      <h3 className="text-xl font-bold text-gray-900 mb-3">{title}</h3>
      <p className="text-gray-500 leading-relaxed mb-6">{description}</p>
      <div className="flex flex-wrap gap-2">
        {points.map((point: string) => (
          <span key={point} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-50 border border-gray-100 rounded-lg text-xs font-medium text-gray-600">
            <CheckCircle2 className="w-3.5 h-3.5 text-green-400 flex-shrink-0" />
            {point}
          </span>
        ))}
      </div>
    </div>
  );
}

function StepCard({ step, icon: Icon, title, description, detail }: typeof steps[0] & { index: number }) {
  return (
    <div className="text-center px-4">
      <div className="w-24 h-24 bg-gray-900 rounded-3xl flex items-center justify-center mx-auto mb-6 shadow-xl">
        <Icon className="w-12 h-12 text-white" />
      </div>
      <div className="inline-block text-xs font-bold text-indigo-500 bg-indigo-50 px-3 py-1 rounded-full mb-3">
        STEP {step}
      </div>
      <h3 className="text-xl font-bold text-gray-900 mb-2">{title}</h3>
      <p className="text-gray-500 text-sm mb-2">{description}</p>
      <p className="text-gray-400 text-xs leading-relaxed max-w-xs mx-auto">{detail}</p>
    </div>
  );
}

function AgentCard({ name, role, active }: typeof agentList[0]) {
  return (
    <div className="group bg-white border border-gray-100 rounded-2xl p-5 text-center hover:border-gray-200 hover:shadow-lg hover:-translate-y-1 transition-all duration-300">
      <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center mx-auto mb-3 shadow-lg group-hover:scale-110 transition-transform duration-300">
        <Bot className="w-6 h-6 text-white" />
      </div>
      <p className="text-sm font-semibold text-gray-900 mb-1">{name}</p>
      <p className="text-xs text-gray-400 mb-3">{role}</p>
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${active ? 'bg-green-50 text-green-600' : 'bg-gray-100 text-gray-400'}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-green-400 animate-pulse' : 'bg-gray-300'}`} />
        {active ? '运行中' : '待命'}
      </span>
    </div>
  );
}

function ReviewCard({ name, role, text, stars }: typeof reviews[0]) {
  return (
    <div className="bg-white border border-gray-100 rounded-2xl p-8 hover:shadow-lg hover:-translate-y-1 transition-all duration-300">
      <div className="flex items-center gap-1 mb-6">
        {Array.from({ length: 5 }).map((_, i) => (
          <Star key={i} className={`w-5 h-5 ${i < stars ? 'text-amber-400 fill-amber-400' : 'text-gray-200'}`} />
        ))}
      </div>
      <blockquote className="text-gray-600 text-sm leading-relaxed mb-8">"{text}"</blockquote>
      <div className="flex items-center gap-4 pt-6 border-t border-gray-100">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center text-white font-bold text-sm shadow-lg">
          {name[0]}
        </div>
        <div>
          <p className="font-semibold text-gray-900 text-sm">{name}</p>
          <p className="text-xs text-gray-400">{role}</p>
        </div>
      </div>
    </div>
  );
}

/* ===================================================================
 * 主页面
 * =================================================================== */

export default function Home() {
  const [input, setInput] = useState('');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();

  const handleStart = () => {
    navigate('/chat', { state: { initialMessage: input.trim() || undefined } });
  };

  return (
    <div className="min-h-screen bg-white">

      {/* ================================================================ */}
      {/* 移动端导航栏                                                     */}
      {/* ================================================================ */}
      <header className="sticky top-0 z-50 bg-white/95 backdrop-blur border-b border-gray-100 md:hidden">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <button className="flex items-center gap-2.5" onClick={() => navigate('/')}>
            <div className="w-9 h-9 bg-gradient-to-br from-gray-800 to-gray-900 rounded-xl flex items-center justify-center shadow-lg">
              <Brain className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-extrabold text-gray-900">
              Edu<span className="text-indigo-600">Agent</span>
            </span>
          </button>

          <button
            className="p-2 rounded-lg hover:bg-gray-50"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? <X className="w-6 h-6 text-gray-700" /> : <Menu className="w-6 h-6 text-gray-700" />}
          </button>
        </div>

        {mobileMenuOpen && (
          <div className="border-t border-gray-100 bg-white px-6 py-4 space-y-2">
            {navItems.map((item) => (
              <a key={item.href} href={item.href} className="block py-3 text-sm font-medium text-gray-600"
                onClick={() => setMobileMenuOpen(false)}>
                {item.label}
              </a>
            ))}
            <button onClick={() => { navigate('/chat'); setMobileMenuOpen(false); }}
              className="w-full py-3 bg-gray-900 text-white rounded-xl text-sm font-semibold mt-2">
              开始使用
            </button>
          </div>
        )}
      </header>

      {/* ================================================================ */}
      {/* Hero 区域                                                        */}
      {/* ================================================================ */}
      <section className="bg-gradient-to-b from-gray-50 to-white">
        <div className="max-w-7xl mx-auto px-6 py-20 md:py-28">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-10 lg:gap-16 items-center">
            {/* 左侧文字 */}
            <div className="space-y-8 max-w-2xl">
              <div className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-full text-sm font-medium text-gray-600 shadow-sm">
                <Sparkles className="w-4 h-4 text-indigo-500" />
                <span>10 个 AI 智能体协同工作</span>
                <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
              </div>

              <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold text-gray-900 leading-tight">
                用 AI 多智能体
                <br />
                <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">
                  重新定义学习
                </span>
              </h1>

              <p className="text-lg text-gray-500 max-w-xl leading-relaxed">
                EduAgent 通过 10 个专业智能体协同工作，深入理解你的知识结构与学习偏好，
                自动生成个性化学习路径和 5 种多模态资源，让每一次学习都精准高效。
              </p>

              <div className="flex items-center gap-3 max-w-lg">
                <div className="flex-1 relative">
                  <MessageSquare className="w-5 h-5 text-gray-400 absolute left-4 top-1/2 -translate-y-1/2" />
                  <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleStart()}
                    placeholder="输入你想学的课程，例如：人工智能导论..."
                    className="w-full h-14 pl-12 pr-4 bg-white border border-gray-200 rounded-2xl text-sm outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent shadow-sm transition-all"
                  />
                </div>
                <button
                  onClick={handleStart}
                  className="h-14 px-8 bg-gray-900 text-white rounded-2xl font-semibold hover:bg-gray-800 flex items-center gap-2 transition-all shadow-xl shadow-gray-200 flex-shrink-0"
                >
                  开始学习
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>

              <div className="flex items-center gap-6 text-sm text-gray-400">
                <div className="flex -space-x-2">
                  {['S1', 'S2', 'S3', 'S4'].map((s, i) => (
                    <div key={i} className="w-9 h-9 rounded-full border-2 border-white bg-gradient-to-br from-indigo-100 to-violet-100 flex items-center justify-center text-[10px] font-bold text-indigo-600 shadow-sm">
                      {s}
                    </div>
                  ))}
                </div>
                <div className="flex items-center gap-1">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <Star key={i} className="w-4 h-4 text-amber-400 fill-amber-400" />
                  ))}
                  <span className="font-bold text-gray-900 ml-1">4.8</span>
                </div>
                <span>· 10,000+ 学生</span>
              </div>
            </div>

            {/* 右侧智能体面板 */}
            <div className="hidden md:block">
              <div className="bg-white border border-gray-100 rounded-3xl shadow-xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-sm font-semibold text-gray-700">智能体运行状态</span>
                  <span className="text-xs text-green-600 font-medium bg-green-50 px-2.5 py-1 rounded-full">
                    系统运行中
                  </span>
                </div>
                <div className="space-y-3">
                  {agentList.slice(0, 6).map((agent, i) => (
                    <div key={i} className="flex items-center gap-3 p-3 rounded-2xl bg-gray-50 hover:bg-gray-100 transition-colors">
                      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gray-700 to-gray-900 flex items-center justify-center shadow-lg">
                        <Bot className="w-5 h-5 text-white" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">{agent.name}</p>
                        <p className="text-xs text-gray-400">{agent.role}</p>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <div className={`w-2 h-2 rounded-full ${agent.active ? 'bg-green-400 animate-pulse' : 'bg-gray-300'}`} />
                        <span className="text-[10px] text-gray-400">{agent.active ? '活跃' : '待命'}</span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="text-center text-xs text-gray-400 pt-3 mt-3 border-t border-gray-100">
                  + 2 个智能体待命 · 随时响应学习需求
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ================================================================ */}
      {/* 数据统计                                                         */}
      {/* ================================================================ */}
      <section className="bg-white">
        <div className="max-w-6xl mx-auto px-6 pb-20 md:pb-28">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-6">
            {stats.map((stat) => (
              <StatCard key={stat.label} {...stat} />
            ))}
          </div>
        </div>
      </section>

      {/* ================================================================ */}
      {/* 核心功能                                                         */}
      {/* ================================================================ */}
      <section id="features" className="bg-gray-50">
        <div className="max-w-7xl mx-auto px-6 py-20 md:py-28">
          <div className="text-center mb-16">
            <span className="inline-block text-xs font-bold text-indigo-500 uppercase tracking-[0.2em] bg-indigo-50 px-4 py-1.5 rounded-full mb-4">
              Features
            </span>
            <h2 className="text-3xl md:text-4xl font-extrabold text-gray-900 mb-4">
              为什么选择 EduAgent？
            </h2>
            <p className="text-lg text-gray-500 max-w-2xl mx-auto">
              传统学习平台内容固定、千人一面。EduAgent 用多智能体协同技术，为每个人生成专属学习方案。
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {features.map((feature) => (
              <FeatureCard key={feature.title} {...feature} />
            ))}
          </div>
        </div>
      </section>

      {/* ================================================================ */}
      {/* 工作流程                                                         */}
      {/* ================================================================ */}
      <section id="how-it-works" className="bg-white">
        <div className="max-w-7xl mx-auto px-6 py-24 md:py-32">
          <div className="text-center mb-20">
            <span className="inline-block text-xs font-bold text-indigo-500 uppercase tracking-[0.2em] bg-indigo-50 px-4 py-1.5 rounded-full mb-4">
              How It Works
            </span>
            <h2 className="text-4xl md:text-5xl font-extrabold text-gray-900 mb-4">
              三步开始学习
            </h2>
            <p className="text-xl text-gray-500">
              不需要填表，不需要测试，像聊天一样开始你的学习之旅
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-10 max-w-6xl mx-auto">
            {steps.map((step, i) => (
              <StepCard key={step.step} {...step} index={i} />
            ))}
          </div>
        </div>
      </section>

      {/* ================================================================ */}
      {/* 智能体架构                                                       */}
      {/* ================================================================ */}
      <section id="architecture" className="bg-gray-50">
        <div className="max-w-7xl mx-auto px-6 py-20 md:py-28">
          <div className="text-center mb-16">
            <span className="inline-block text-xs font-bold text-indigo-500 uppercase tracking-[0.2em] bg-indigo-50 px-4 py-1.5 rounded-full mb-4">
              Architecture
            </span>
            <h2 className="text-3xl md:text-4xl font-extrabold text-gray-900 mb-4">
              10 个智能体协同工作
            </h2>
            <p className="text-lg text-gray-500 max-w-2xl mx-auto">
              每个智能体专注单一职责，通过编排协调器串联成完整的学习服务流程
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto mb-16">
            {agentList.map((agent) => (
              <AgentCard key={agent.name} {...agent} />
            ))}
          </div>

          {/* 流程示意 */}
          <div className="bg-white border border-gray-200 rounded-3xl p-6 max-w-4xl mx-auto overflow-x-auto">
            <div className="flex items-center justify-center gap-2 text-sm min-w-[600px]">
              {['用户对话', '画像分析', '学习诊断', '路径规划', '资源生成'].map((label, i) => (
                <span key={label} className="flex items-center gap-2">
                  <span className="px-4 py-2 bg-gray-50 border border-gray-200 rounded-xl font-medium text-gray-700 shadow-sm whitespace-nowrap">
                    {label}
                  </span>
                  {i < 4 && <ChevronRight className="w-4 h-4 text-gray-300 flex-shrink-0" />}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ================================================================ */}
      {/* 用户评价                                                         */}
      {/* ================================================================ */}
      <section id="testimonials" className="bg-white">
        <div className="max-w-7xl mx-auto px-6 py-20 md:py-28">
          <div className="text-center mb-16">
            <span className="inline-block text-xs font-bold text-indigo-500 uppercase tracking-[0.2em] bg-indigo-50 px-4 py-1.5 rounded-full mb-4">
              Testimonials
            </span>
            <h2 className="text-3xl md:text-4xl font-extrabold text-gray-900 mb-4">
              来自用户的声音
            </h2>
            <p className="text-lg text-gray-500">听听他们怎么说</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {reviews.map((review) => (
              <ReviewCard key={review.name} {...review} />
            ))}
          </div>
        </div>
      </section>

      {/* ================================================================ */}
      {/* CTA                                                              */}
      {/* ================================================================ */}
      <section className="bg-gray-50">
        <div className="max-w-4xl mx-auto px-6 py-20 md:py-28">
          <div className="bg-gray-900 rounded-3xl p-12 md:p-20 text-center">
            <Shield className="w-12 h-12 text-indigo-400 mx-auto mb-6" />
            <h2 className="text-3xl md:text-4xl font-extrabold text-white mb-4">
              准备好开始了吗？
            </h2>
            <p className="text-gray-400 text-lg max-w-2xl mx-auto mb-10">
              加入 10,000+ 名学生，用 AI 多智能体开启高效学习新模式
            </p>
            <div className="flex flex-col md:flex-row items-center justify-center gap-4">
              <button
                onClick={() => navigate('/chat')}
                className="px-10 py-4 bg-white text-gray-900 rounded-2xl font-bold text-lg hover:bg-gray-100 transition-all shadow-2xl inline-flex items-center gap-2"
              >
                免费开始使用
                <ArrowRight className="w-5 h-5" />
              </button>
              <button
                onClick={() => navigate('/resources')}
                className="px-10 py-4 border border-gray-600 text-white rounded-2xl font-bold text-lg hover:bg-white/10 transition-all inline-flex items-center gap-2"
              >
                浏览资源库
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ================================================================ */}
      {/* 页脚                                                             */}
      {/* ================================================================ */}
      <footer className="bg-white border-t border-gray-100">
        <div className="max-w-7xl mx-auto px-6 py-12">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-8">
            <div className="col-span-2">
              <div className="flex items-center gap-2.5 mb-4">
                <div className="w-9 h-9 bg-gradient-to-br from-gray-800 to-gray-900 rounded-xl flex items-center justify-center shadow-lg">
                  <Brain className="w-5 h-5 text-white" />
                </div>
                <span className="text-xl font-extrabold text-gray-900">EduAgent</span>
              </div>
              <p className="text-sm text-gray-400 max-w-xs leading-relaxed">
                基于大模型的多智能体个性化学习资源生成与自适应学习系统。让 AI 为每个人量身定制学习方案。
              </p>
            </div>
            {[
              { title: '产品', items: ['功能介绍', '使用流程', '常见问题', '更新日志'] },
              { title: '资源', items: ['知识库', '案例库', '文档中心', 'API 文档'] },
              { title: '关于', items: ['关于我们', '联系方式', '用户协议', '隐私政策'] },
            ].map((col) => (
              <div key={col.title}>
                <h4 className="font-semibold text-gray-900 mb-4">{col.title}</h4>
                <ul className="space-y-3">
                  {col.items.map((item) => (
                    <li key={item}>
                      <a href="#" className="text-sm text-gray-400 hover:text-gray-600 transition-colors">
                        {item}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="border-t border-gray-200 mt-12 pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
            <p className="text-sm text-gray-400">© 2026 EduAgent. All rights reserved.</p>
            <p className="text-sm text-gray-400">第十五届中国软件杯大赛 A3 赛题参赛作品</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
