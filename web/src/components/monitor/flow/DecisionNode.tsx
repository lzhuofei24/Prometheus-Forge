import { memo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { cn } from '../../../lib/utils';

export interface DecisionNodeData extends Record<string, unknown> {
  label?: string;
}

export type DecisionFlowNode = Node<DecisionNodeData, 'decision'>;

/** Handle 样式：可见、便于连线；z-50 确保浮在节点上方 */
const HANDLE_STYLE = 'w-2.5 h-2.5 bg-amber-200 border border-amber-900 z-50';

function DecisionNodeComponent({ data, selected }: NodeProps<DecisionFlowNode>) {
  const label = (data?.label as string) ?? 'Condition?';
  return (
    <div className="relative group">
      {/* 菱形容器 */}
      <div
        className={cn(
          'w-24 h-24 rotate-45 flex items-center justify-center',
          'bg-zinc-900 border-2 transition-all shadow-md',
          selected ? 'border-amber-500 shadow-amber-500/20' : 'border-zinc-700 hover:border-zinc-500'
        )}
      >
        {/* 内容反向旋转，保持水平 */}
        <div className="-rotate-45 text-center px-1">
          <span className="text-xs font-bold text-zinc-100 block leading-tight">{label}</span>
        </div>
      </div>

      {/* Handles - 上下左右四个方向 */}
      <Handle type="target" position={Position.Top} id="top" className={`${HANDLE_STYLE} -top-1`} />
      <Handle type="source" position={Position.Right} id="right" className={`${HANDLE_STYLE} -right-1`} />
      <Handle type="source" position={Position.Bottom} id="bottom" className={`${HANDLE_STYLE} -bottom-1`} />
      <Handle type="source" position={Position.Left} id="left" className={`${HANDLE_STYLE} -left-1`} />
    </div>
  );
}

export const DecisionNode = memo(DecisionNodeComponent);
