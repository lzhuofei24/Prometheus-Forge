import { useNavigate } from 'react-router-dom';
import {
  PenLine,
  BookOpen,
  GitBranch,
  BarChart3,
  Zap,
  RefreshCw,
  Activity,
  Database,
} from 'lucide-react';

const FEATURES = [
  { icon: Zap, title: '多智能体流水线', desc: 'Architect → Writer → Censor → Critic，Controller 驱动下一步。' },
  { icon: RefreshCw, title: '自动反馈环', desc: 'Critic 评分 &lt; 75 触发修订，默认最多 3 次。' },
  { icon: Activity, title: '端到端可观测', desc: '审计日志 + 工作流拓扑与实时追踪。' },
  { icon: Database, title: '向量与上下文', desc: 'ChromaDB + 近期章节与大纲，支撑长线一致性。' },
] as const;

const QUICK_LINKS = [
  { path: '/writer', label: '写作', icon: PenLine },
  { path: '/reader', label: '阅读', icon: BookOpen },
  { path: '/workflow', label: '工作流助手', icon: GitBranch },
  { path: '/resources', label: '资源', icon: BarChart3 },
] as const;

export default function Home() {
  const navigate = useNavigate();

  return (
    <div className="h-full w-full overflow-auto bg-gradient-to-br from-zinc-950 via-indigo-950/15 to-zinc-950 relative">
      <div
        className="absolute inset-0 bg-[linear-gradient(to_right,#8080800a_1px,transparent_1px),linear-gradient(to_bottom,#8080800a_1px,transparent_1px)] bg-[size:28px_28px]"
        aria-hidden
      />
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[720px] h-[720px] bg-indigo-600 rounded-full blur-3xl opacity-[0.12] pointer-events-none"
        aria-hidden
      />
      <div
        className="absolute top-1/4 right-1/4 w-[480px] h-[480px] bg-violet-600 rounded-full blur-3xl opacity-10 pointer-events-none"
        aria-hidden
      />

      <div className="relative z-0 w-full min-h-full flex justify-center px-4 sm:px-6 py-12 sm:py-16 box-border">
        <div className="w-full max-w-3xl flex flex-col items-center">
        {/* Hero — 不修改背景与标题风格 */}
        <header className="text-center mb-14 w-full flex flex-col items-center">
          <h1 className="text-5xl sm:text-6xl font-bold mb-3 bg-gradient-to-r from-indigo-400 via-violet-400 to-fuchsia-400 bg-clip-text text-transparent leading-tight tracking-tight">
            Prometheus Forge
          </h1>
          <p className="text-lg sm:text-xl text-indigo-200/90 font-medium mb-1">
            Igniting Creative Intelligence Through Event-Driven Orchestration
          </p>
          <p className="text-base text-zinc-400 mb-6">普罗米修斯工坊 / 火种工坊</p>
          <p className="text-zinc-400 max-w-2xl text-center text-sm sm:text-base leading-relaxed">
            事件驱动的多智能体小说创作系统，具备全链路可观测、向量检索上下文与自动质量反馈环。
          </p>
        </header>

        {/* 导航：极简文本链 */}
        <nav className="flex flex-wrap items-center justify-center gap-x-6 gap-y-1 mb-20 text-zinc-500" aria-label="快捷导航">
          {QUICK_LINKS.map(({ path, label, icon: Icon }) => (
            <button
              key={path}
              type="button"
              onClick={() => navigate(path)}
              className="group inline-flex items-center gap-2 text-sm hover:text-indigo-400 transition-colors"
            >
              <Icon className="w-3.5 h-3.5 opacity-70 group-hover:opacity-100" />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        {/* 能力：单列列表，居中 */}
        <section className="w-full flex flex-col items-center space-y-6" aria-label="核心能力">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div
              key={title}
              className="flex flex-col items-center text-center max-w-md w-full py-3 border-b border-zinc-800/60 last:border-0"
            >
              <div className="flex-shrink-0 w-8 h-8 rounded flex items-center justify-center bg-zinc-800/50 text-zinc-400 mb-2">
                <Icon className="w-4 h-4" />
              </div>
              <div className="text-zinc-200 font-medium text-sm mb-0.5">{title}</div>
              <div className="text-zinc-500 text-xs leading-relaxed">{desc}</div>
            </div>
          ))}
        </section>
        </div>
      </div>
    </div>
  );
}
