import { memo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { AgentStationCard } from '../AgentStationCard';
import type { AgentMetric } from '../../../types';

export interface AgentNodeData extends Record<string, unknown> {
  agent: AgentMetric;
  isDisabled?: boolean;
  onToggleDisable?: () => void;
  disablePending?: boolean;
  onPurgePending?: () => void;
  onPurgeCompleted?: () => void;
  onRedrive?: () => void;
}

export type AgentFlowNode = Node<AgentNodeData, 'agent'>;

/** Handle 通用样式：大一点，易于点击，带深色边框；z-50 确保浮在卡片上方 */
const HANDLE_STYLE = 'w-3 h-3 bg-zinc-400 border-2 border-zinc-900 transition-colors hover:bg-emerald-400 z-50';

function AgentNodeComponent({ data, selected }: NodeProps<AgentFlowNode>) {
  return (
    <div
      className={`relative rounded-xl transition-all ${
        selected ? 'ring-2 ring-indigo-500 shadow-lg shadow-indigo-500/20' : ''
      }`}
    >
      {/* 上方输入 (Input) */}
      <Handle type="target" position={Position.Top} id="top" className={HANDLE_STYLE} />

      {/* 右侧输出 (Output - 常用) */}
      <Handle type="source" position={Position.Right} id="right" className={HANDLE_STYLE} />

      {/* 底部输出 (Output - 常用) */}
      <Handle type="source" position={Position.Bottom} id="bottom" className={HANDLE_STYLE} />

      {/* 左侧输入 (Input - 用于回环) */}
      <Handle type="target" position={Position.Left} id="left" className={HANDLE_STYLE} />

      {/* 核心卡片 */}
      <AgentStationCard
        agent={data.agent}
        isDisabled={data.isDisabled}
        onToggleDisable={data.onToggleDisable}
        disablePending={data.disablePending}
        onPurgePending={data.onPurgePending}
        onPurgeCompleted={data.onPurgeCompleted}
        onRedrive={data.onRedrive}
      />
    </div>
  );
}

export const AgentNode = memo(AgentNodeComponent);
