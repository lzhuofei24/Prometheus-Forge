import { memo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { Play } from 'lucide-react';
import { cn } from '../../../lib/utils';

export interface StartNodeData extends Record<string, unknown> {
  label?: string;
}

export type StartFlowNode = Node<StartNodeData, 'start'>;

function StartNodeComponent({ selected }: NodeProps<StartFlowNode>) {
  return (
    <div className="relative">
      <div
        className={cn(
          'rounded-full px-6 py-3 min-w-[160px] flex items-center justify-center gap-2',
          'bg-gradient-to-r from-emerald-500 to-emerald-700',
          'shadow-lg shadow-emerald-500/25 border border-emerald-400/30',
          selected && 'ring-2 ring-emerald-400'
        )}
      >
        <Play className="w-5 h-5 text-white fill-white" />
        <span className="text-sm font-semibold text-white">Start Workflow</span>
      </div>
      {/* 只给一个底部输出，便于向下连线 */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom"
        className="w-3 h-3 bg-emerald-400 border-2 border-emerald-950"
      />
    </div>
  );
}

export const StartNode = memo(StartNodeComponent);
