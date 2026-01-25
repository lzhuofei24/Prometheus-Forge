import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '../ui/card';
import { Badge } from '../ui/badge';
import { cn } from '../../lib/utils';
import {
  Sparkles,
  FileText,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Loader2,
} from 'lucide-react';
import type { AuditLogEntry } from '../../types';
import { EventSource } from '../../types';

interface NeuralTraceProps {
  logs: AuditLogEntry[];
}

export default function NeuralTrace({ logs }: NeuralTraceProps) {
  const { t } = useTranslation();
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current && logs.length > 0) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const toggleExpand = (id: string) => {
    const newSet = new Set(expandedIds);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setExpandedIds(newSet);
  };

  const getEventIcon = (log: AuditLogEntry) => {
    if (log.source === EventSource.AGENT_WRITER) {
      if (log.event_type.includes('WRITING') || log.event_type.includes('STARTED')) {
        return <Loader2 className="w-5 h-5 text-indigo-400 animate-spin" />;
      }
      return <FileText className="w-5 h-5 text-indigo-400" />;
    }
    if (log.source === EventSource.AGENT_CRITIC) {
      const score = log.details?.score || log.details?.critique_score;
      if (score !== undefined) {
        if (score >= 80) {
          return <CheckCircle2 className="w-5 h-5 text-green-400" />;
        }
        if (score < 75) {
          return <AlertTriangle className="w-5 h-5 text-red-400" />;
        }
      }
      return <CheckCircle2 className="w-5 h-5 text-yellow-400" />;
    }
    if (log.source === EventSource.DISPATCHER) {
      return <Sparkles className="w-5 h-5 text-zinc-400" />;
    }
    return <FileText className="w-5 h-5 text-zinc-400" />;
  };

  const getSummary = (log: AuditLogEntry): string => {
    if (log.source === EventSource.AGENT_WRITER && log.details?.content) {
      const content = log.details.content;
      const wordCount = typeof content === 'string' ? content.length : 0;
      return t('writer.trace.generated_words', { count: wordCount });
    }
    if (log.source === EventSource.AGENT_CRITIC) {
      const score = log.details?.score || log.details?.critique_score;
      if (score !== undefined) {
        const advice = log.details?.advice || log.details?.comments || '';
        return t('writer.trace.score', { score }) + (advice ? '，' + advice.substring(0, 20) + '...' : '');
      }
    }
    return log.event_type.replace(/_/g, ' ').toLowerCase();
  };

  if (logs.length === 0) {
    return (
      <div className="relative p-8 text-center text-zinc-500">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-indigo-600 rounded-full blur-3xl opacity-10 pointer-events-none"></div>
        <div className="relative">
          <Sparkles className="w-16 h-16 mx-auto mb-4 text-zinc-700" />
          <p className="text-sm text-zinc-400 leading-relaxed">{t('writer.trace.waiting_log')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative p-6" ref={scrollRef}>
      <div className="absolute left-10 top-6 bottom-6 w-0.5 bg-white/5"></div>
      <div className="space-y-6 relative">
        {logs.map((log, index) => {
          const logId = `${log.timestamp}-${index}`;
          const isExpanded = expandedIds.has(logId);
          const score = log.details?.score || log.details?.critique_score;
          const isWriter = log.source === EventSource.AGENT_WRITER;
          const isCritic = log.source === EventSource.AGENT_CRITIC;

          return (
            <div key={logId} className="relative pl-14">
              <div className="absolute left-0 top-3 w-5 h-5 rounded-full bg-zinc-900 border-2 border-white/10 flex items-center justify-center">
                <div className="w-2.5 h-2.5 rounded-full bg-indigo-500"></div>
              </div>
              <Card className={cn(
                'bg-zinc-900/30 hover:bg-zinc-900/50 transition-colors',
                isWriter && 'border-l-4 border-l-indigo-500/50',
                isCritic && score !== undefined && (score >= 80 ? 'border-l-4 border-l-green-500/50' : score < 75 ? 'border-l-4 border-l-red-500/50' : 'border-l-4 border-l-yellow-500/50')
              )}>
                <CardContent className="p-6">
                  <div className="flex items-start gap-4">
                    <div className="mt-1">{getEventIcon(log)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className="text-sm font-semibold text-zinc-200 leading-relaxed tracking-widest">
                            {log.source.replace('agent_', '').replace('_', ' ').toUpperCase()}
                          </span>
                          {score !== undefined && (
                            <Badge
                              variant={score >= 80 ? 'success' : score < 75 ? 'error' : 'warning'}
                              className="text-xs font-bold"
                            >
                              {score}/100
                            </Badge>
                          )}
                        </div>
                        <button
                          onClick={() => toggleExpand(logId)}
                          className="text-zinc-500 hover:text-zinc-300 transition-colors"
                        >
                          {isExpanded ? (
                            <ChevronDown className="w-4 h-4" />
                          ) : (
                            <ChevronRight className="w-4 h-4" />
                          )}
                        </button>
                      </div>
                      <div className="text-xs text-zinc-500 mb-3 font-mono leading-relaxed">
                        {new Date(log.timestamp).toLocaleTimeString()}
                      </div>
                      <div className="text-sm text-zinc-400 mb-2 leading-relaxed">
                        {getSummary(log)}
                      </div>
                      {isExpanded && (
                        <div className="mt-4 pt-4 border-t border-white/5">
                          <pre className="text-xs text-zinc-500 overflow-auto font-mono leading-relaxed">
                            {JSON.stringify(log.details, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          );
        })}
      </div>
    </div>
  );
}
