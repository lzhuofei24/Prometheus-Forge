import { useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Terminal } from 'lucide-react';
import { cn } from '../../lib/utils';

export interface DispatchLogLine {
  time: string;
  type: string;
  message: string;
}

interface DispatchTerminalProps {
  logs: DispatchLogLine[];
  className?: string;
  /** 侧边栏模式：更窄、更高、背景加深、字号缩小，保持黑客风 */
  sidebar?: boolean;
}

const ROUTE_NEXT: Record<string, string> = {
  architect_completed: 'WRITER_PENDING',
  writer_completed: 'CENSOR_PENDING',
  censor_completed: 'CRITIC_PENDING',
  critic_completed: 'MEDIA_PENDING', // or KNOWLEDGE_PENDING; use one representative
  media_completed: 'END',
  knowledge_completed: 'END',
};

function formatForTerminal(log: DispatchLogLine): string {
  const t = log.time;
  let msg = log.message;
  const m = msg.match(/Picked up from (\w+)_completed/i);
  if (log.type === 'route' && m) {
    const src = `${m[1].toUpperCase()}_COMPLETED`;
    const next = ROUTE_NEXT[`${m[1].toLowerCase()}_completed`] ?? 'END';
    msg = `🔀 ${src} => ${next}`;
  }
  if (!msg.startsWith('🔀 ') && !/=>/.test(msg)) msg = msg;
  return `[${t}] ${msg}`;
}

export function DispatchTerminal({ logs, className, sidebar }: DispatchTerminalProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs.length]);

  return (
    <Card
      className={cn(
        'flex-1 min-h-0 flex flex-col bg-zinc-950 border border-emerald-500/30 overflow-hidden',
        sidebar && '!bg-zinc-950/95 border-zinc-800/80 rounded-none',
        className
      )}
    >
      <CardHeader className={cn('py-2 px-3 border-b border-emerald-500/20', sidebar && 'py-1.5 px-2 border-zinc-800')}>
        <div className="flex items-center gap-2">
          <Terminal className={cn('text-emerald-400', sidebar ? 'w-3.5 h-3.5' : 'w-4 h-4')} />
          <CardTitle className={cn('font-mono font-medium text-emerald-400', sidebar ? 'text-[11px]' : 'text-sm')}>
            Dispatch Terminal
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 p-0">
        <div
          ref={scrollRef}
          className={cn(
            'h-full overflow-y-auto overflow-x-hidden font-mono text-emerald-400 leading-relaxed',
            sidebar ? 'bg-black/95 text-[11px] p-2' : 'bg-black/90 text-xs p-3'
          )}
        >
          {logs.length === 0 ? (
            <span className="text-emerald-400/50">
              No dispatches yet. Format: [HH:mm:ss] 🔀 SOURCE_COMPLETED =&gt; TARGET_PENDING
            </span>
          ) : (
            logs.map((log, idx) => (
              <div key={idx} className="whitespace-pre-wrap break-all">
                {formatForTerminal(log)}
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
