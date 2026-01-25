import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { Cpu, Power, PowerOff, ChevronRight, AlertTriangle } from 'lucide-react';
import type { AgentMetric } from '../../types';
import { cn } from '../../lib/utils';

interface AgentStationCardProps {
  agent: AgentMetric;
  isDisabled?: boolean;
  onToggleDisable?: () => void;
  disablePending?: boolean;
  onPurgePending?: () => void;
  onPurgeCompleted?: () => void;
  onRedrive?: () => void;
}

function PipelineItem({
  label,
  value,
  valueClassName,
  icon = null,
  hint,
}: {
  label: string;
  value: number;
  valueClassName: string;
  icon?: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <div className="flex items-center gap-1 text-xs text-zinc-500">
        {icon}
        <span>{label}</span>
      </div>
      <span className={cn('text-lg font-semibold tabular-nums', valueClassName)}>{value}</span>
      {hint && <span className="text-[10px] text-zinc-600">{hint}</span>}
    </div>
  );
}

export function AgentStationCard({
  agent,
  isDisabled = false,
  onToggleDisable,
  disablePending = false,
  onPurgePending,
  onPurgeCompleted,
  onRedrive,
}: AgentStationCardProps) {
  const pending = agent.queues.pending ?? 0;
  const suspended = agent.queues.suspended ?? 0;
  const completed = agent.queues.completed ?? 0;
  const hasSuspended = suspended > 0;
  const isProcessing = !!agent.is_processing;
  // 状态优先级：Suspended > Processing > Idle
  const statusKind = hasSuspended ? 'suspended' : (isProcessing ? 'processing' : 'idle');

  return (
    <Card
      className={cn(
        'w-max bg-zinc-900/50 backdrop-blur-sm border transition-all overflow-hidden',
        'border-zinc-700/50',
        hasSuspended && 'border-amber-500/40 shadow-sm shadow-amber-500/10',
        statusKind === 'processing' && 'border-blue-500/30 shadow-sm shadow-blue-500/10',
        isDisabled && 'opacity-80'
      )}
    >
      <CardContent className="p-0">
        <div className="flex flex-row items-center h-20 gap-4 px-[40px] min-w-0">
          {/* 左侧：Agent 信息，随名称变宽，带动整卡变宽 */}
          <div className="flex items-center gap-3 min-w-[5.5rem] flex-shrink-0">
            <Cpu
              className={cn(
                'w-5 h-5 flex-shrink-0',
                statusKind === 'processing' && 'text-blue-400',
                statusKind === 'suspended' && 'text-amber-500',
                statusKind === 'idle' && (agent.is_online ? 'text-green-400' : 'text-zinc-500')
              )}
            />
            <div className="flex flex-col shrink-0 overflow-visible">
              <span className="font-semibold text-zinc-100 whitespace-nowrap">{agent.name}</span>
              <div className="flex items-center gap-2">
                <div
                  className={cn(
                    'w-2 h-2 rounded-full flex-shrink-0',
                    statusKind === 'processing' && 'bg-blue-500 animate-pulse',
                    statusKind === 'suspended' && 'bg-amber-500',
                    statusKind === 'idle' && (agent.is_online ? 'bg-green-400' : 'bg-zinc-500')
                  )}
                />
                <span
                  className={cn(
                    'text-xs',
                    statusKind === 'processing' && 'text-blue-400',
                    statusKind === 'suspended' && 'text-amber-500',
                    statusKind === 'idle' && 'text-zinc-500'
                  )}
                >
                  {statusKind === 'processing' && 'Processing...'}
                  {statusKind === 'suspended' && 'Suspended'}
                  {statusKind === 'idle' && 'Idle'}
                </span>
              </div>
            </div>
          </div>

          {/* 中间：队列流水线，可压缩，保留最小宽度 */}
          <div className="flex-1 flex items-center justify-center gap-6 min-w-[180px] shrink">
            <PipelineItem
              label="Pending"
              value={pending}
              valueClassName="text-zinc-300"
            />
            <ChevronRight className="w-4 h-4 text-zinc-600 flex-shrink-0" aria-hidden />
            <PipelineItem
              label="Suspended"
              value={suspended}
              valueClassName={hasSuspended ? 'text-amber-500' : 'text-zinc-600'}
              icon={hasSuspended ? <AlertTriangle className="w-3 h-3 text-amber-500" /> : null}
              hint={!hasSuspended ? '无挂起' : undefined}
            />
            <ChevronRight className="w-4 h-4 text-zinc-600 flex-shrink-0" aria-hidden />
            <PipelineItem
              label="Completed"
              value={completed}
              valueClassName="text-purple-400"
            />
          </div>

          {/* 右侧：操作区，固定不压缩 */}
          <div className="flex items-center justify-end gap-2 flex-shrink-0">
            {onToggleDisable && (
              <Button
                variant="outline"
                size="sm"
                className={cn(
                  'h-8 px-3 text-xs flex-shrink-0',
                  isDisabled
                    ? 'border-emerald-500/50 text-emerald-400 hover:bg-emerald-500/10'
                    : 'border-red-500/50 text-red-400 hover:bg-red-500/10'
                )}
                onClick={onToggleDisable}
                disabled={disablePending}
              >
                {isDisabled ? <Power className="w-3.5 h-3.5 mr-1.5" /> : <PowerOff className="w-3.5 h-3.5 mr-1.5" />}
                {isDisabled ? '启用' : '禁用'}
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
