import { useState, useEffect, useRef } from 'react';
import {
  PlayCircle,
  CheckCircle,
  XCircle,
  Clock,
  FileText,
  MessageSquare,
  Settings,
  Image,
  AlertCircle,
} from 'lucide-react';
import type { AuditLogEntry } from '../../types';
import { EventType, EventSource } from '../../types';
import { useConcepts } from '../../hooks/useConcepts';

interface TraceTimelineProps {
  logs: AuditLogEntry[];
}

const getEventIcon = (eventType: string) => {
  switch (eventType) {
    case EventType.WORKFLOW_STARTED:
      return <PlayCircle className="w-5 h-5" />;
    case EventType.TASK_STARTED:
      return <Clock className="w-5 h-5" />;
    case EventType.TASK_COMPLETED:
      return <CheckCircle className="w-5 h-5" />;
    case EventType.TASK_FAILED:
      return <XCircle className="w-5 h-5" />;
    case EventType.OUTLINE_GENERATED:
      return <FileText className="w-5 h-5" />;
    case EventType.CONTENT_WRITTEN:
      return <FileText className="w-5 h-5" />;
    case EventType.CRITIQUE_COMPLETED:
      return <MessageSquare className="w-5 h-5" />;
    case EventType.TASK_DISPATCHED:
      return <Settings className="w-5 h-5" />;
    case EventType.MEDIA_GENERATED:
      return <Image className="w-5 h-5" />;
    default:
      return <AlertCircle className="w-5 h-5" />;
  }
};

const getSourceColor = (source: string) => {
  switch (source) {
    case EventSource.DISPATCHER:
      return 'bg-blue-500 text-white';
    case EventSource.AGENT_WRITER:
      return 'bg-green-500 text-white';
    case EventSource.AGENT_CRITIC:
      return 'bg-yellow-500 text-white';
    case EventSource.AGENT_ARCHITECT:
      return 'bg-purple-500 text-white';
    case EventSource.AGENT_MEDIA:
      return 'bg-pink-500 text-white';
    case EventSource.SYSTEM:
      return 'bg-gray-500 text-white';
    default:
      return 'bg-gray-400 text-white';
  }
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  [EventType.TASK_DISPATCHED]: '任务派发',
  [EventType.TASK_STARTED]: '任务开始',
  [EventType.TASK_COMPLETED]: '任务完成',
  [EventType.TASK_FAILED]: '任务失败',
  [EventType.OUTLINE_GENERATED]: '大纲生成',
  [EventType.CONTENT_WRITTEN]: '内容撰写',
  [EventType.CRITIQUE_COMPLETED]: '审稿完成',
  [EventType.REVISION_REQUESTED]: '重写请求',
  [EventType.MEDIA_GENERATED]: '媒体生成',
};

const getSourceLabel = (source: string): string => {
  const labels: Record<string, string> = {
    [EventSource.DISPATCHER]: '调度器',
    [EventSource.AGENT_WRITER]: '写作',
    [EventSource.AGENT_CRITIC]: '审稿助手',
    [EventSource.AGENT_ARCHITECT]: '架构助手',
    [EventSource.AGENT_MEDIA]: '媒体助手',
    [EventSource.SYSTEM]: '系统',
  };
  return labels[source] || source;
};

export default function TraceTimeline({ logs }: TraceTimelineProps) {
  const { getConceptLabel } = useConcepts();
  const runStartLabel = getConceptLabel('run') + '启动';
  const getEventTypeLabel = (eventType: string): string =>
    eventType === EventType.WORKFLOW_STARTED ? runStartLabel : (EVENT_TYPE_LABELS[eventType] ?? eventType);

  const [expandedLog, setExpandedLog] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevLogsLengthRef = useRef(0);

  useEffect(() => {
    if (logs.length > prevLogsLengthRef.current && containerRef.current) {
      const container = containerRef.current;
      container.scrollTop = container.scrollHeight;
    }
    prevLogsLengthRef.current = logs.length;
  }, [logs.length]);

  if (logs.length === 0) {
    return (
      <div className="text-center text-gray-500 py-8">
        暂无追踪日志
      </div>
    );
  }

  return (
    <div ref={containerRef} className="space-y-4 overflow-y-auto" style={{ maxHeight: '100%' }}>
      {logs.map((log, index) => {
        const isExpanded = expandedLog === index;
        const icon = getEventIcon(log.event_type);
        const sourceColor = getSourceColor(log.source);

        return (
          <div
            key={index}
            className={`relative pl-8 pb-4 border-l-2 ${
              log.error ? 'border-red-300' : 'border-blue-300'
            } animate-in fade-in slide-in-from-left-4 duration-300`}
          >
            <div className="absolute -left-3 top-0">
              <div className={`rounded-full p-1.5 ${sourceColor} shadow-md`}>
                {icon}
              </div>
            </div>

            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 hover:shadow-md transition-shadow">
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-gray-900">
                      {getEventTypeLabel(log.event_type)}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${sourceColor}`}>
                      {getSourceLabel(log.source)}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500">
                    {new Date(log.timestamp).toLocaleString('zh-CN', {
                      year: 'numeric',
                      month: '2-digit',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </div>
                </div>
              </div>

              {log.error && (
                <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700">
                  <strong>错误:</strong> {log.error}
                </div>
              )}

              {log.event_type === EventType.CRITIQUE_COMPLETED && log.details.score !== undefined && (
                <div className="mt-2 p-2 bg-yellow-50 border border-yellow-200 rounded">
                  <div className="text-sm">
                    <strong>评分:</strong>{' '}
                    <span className={`font-bold ${
                      log.details.score >= 75 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {log.details.score}/100
                    </span>
                  </div>
                  {log.details.advice && (
                    <div className="text-xs text-gray-600 mt-1">
                      {log.details.advice}
                    </div>
                  )}
                </div>
              )}

              {log.details && Object.keys(log.details).length > 0 && (
                <button
                  onClick={() => setExpandedLog(isExpanded ? null : index)}
                  className="mt-2 text-xs text-blue-600 hover:text-blue-800"
                >
                  {isExpanded ? '收起详情' : '展开详情'}
                </button>
              )}

              {isExpanded && log.details && (
                <div className="mt-2 p-3 bg-gray-50 rounded border border-gray-200">
                  <pre className="text-xs overflow-x-auto">
                    {JSON.stringify(log.details, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
