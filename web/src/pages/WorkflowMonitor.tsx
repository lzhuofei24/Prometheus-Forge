import { useMonitorStats, usePurgeQueue } from '../hooks/useMonitor';
import { DispatchTerminal } from '../components/monitor/DispatchTerminal';
import { ControllerLogicPanel } from '../components/monitor/ControllerLogicPanel';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { monitorApi } from '../api/client';
import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { cn } from '../lib/utils';
import type { AgentMetric } from '../types';
import { RefreshCw, Rocket, AlertCircle, Save, RotateCcw, Plus } from 'lucide-react';
import {
  ReactFlow,
  Controls,
  MarkerType,
  useNodesState,
  useEdgesState,
  addEdge,
  ConnectionMode,
  type Edge,
  type OnConnect,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { AgentNode, StartNode, DecisionNode, type AgentFlowNode, type StartFlowNode, type DecisionFlowNode } from '../components/monitor/flow';
import { EditElementDialog, type EditData } from '../components/monitor/flow/EditElementDialog';

const FLOW_LAYOUT_KEY_PREFIX = 'novel-agent-flow-layout';

/** 工作流唯一标识，与后端 workflows 注册表一致 */
export const WORKFLOW_ID_GENERATE_CHAPTER = 'generate_chapter';
export const WORKFLOW_ID_OUTLINE_ONLY = 'outline_only';

/** 工作流列表（可用 API /workflow/types 覆盖） */
export const WORKFLOW_OPTIONS: { id: string; name: string }[] = [
  { id: WORKFLOW_ID_GENERATE_CHAPTER, name: '生成新章节' },
  { id: WORKFLOW_ID_OUTLINE_ONLY, name: '仅生成大纲' },
];

const getFlowLayoutKey = (workflowId: string) =>
  `${FLOW_LAYOUT_KEY_PREFIX}-${workflowId}`;

const AGENT_ORDER = ['architect', 'writer', 'censor', 'critic', 'media', 'knowledge'];

/** 连线样式 */
const NORMAL_STYLE = { stroke: '#71717a', strokeWidth: 2, strokeDasharray: '0' };
const NORMAL_MARKER = { type: MarkerType.ArrowClosed as const, color: '#71717a' };
const SUCCESS_STYLE = { stroke: '#10b981', strokeWidth: 2, strokeDasharray: '0' };
const SUCCESS_MARKER = { type: MarkerType.ArrowClosed as const, color: '#10b981' };
const REVISE_STYLE = { stroke: '#f59e0b', strokeWidth: 2, strokeDasharray: '5,5' };
const REVISE_MARKER = { type: MarkerType.ArrowClosed as const, color: '#f59e0b' };
const LABEL_STYLE = { fill: '#a1a1aa', fontWeight: 500 };
const LABEL_BG = { fill: '#18181b', fillOpacity: 0.8 };

/** 编辑对话框用的颜色映射 (default | success | warning) */
const STYLES = {
  default: { stroke: '#71717a', color: '#71717a' },
  success: { stroke: '#10b981', color: '#10b981' },
  warning: { stroke: '#f59e0b', color: '#f59e0b' },
} as const;

/** 用户拖拽新建连线时的默认样式 */
const DEFAULT_EDGE_STYLE = { stroke: '#71717a', strokeWidth: 2 };
const DEFAULT_EDGE_MARKER = { type: MarkerType.ArrowClosed as const, color: '#71717a' };

/** 默认位置（Reset 或首次且无存档时使用） */
const DEFAULT_POSITIONS: Record<string, { x: number; y: number }> = {
  start: { x: 0, y: 0 },
  architect: { x: -200, y: 100 },
  writer: { x: -200, y: 250 },
  censor: { x: -200, y: 400 },
  'decision-pass': { x: -25, y: 550 },
  critic: { x: -200, y: 650 },
  'decision-score': { x: -25, y: 800 },
  media: { x: -450, y: 950 },
  knowledge: { x: 50, y: 950 },
};

/** 生成新章节：完整流程连线 */
const DEFAULT_EDGES_TEMPLATE: Edge[] = [
  { id: 'e-start-arch', source: 'start', target: 'architect', sourceHandle: 'bottom', targetHandle: 'top', type: 'default', animated: true, style: NORMAL_STYLE, markerEnd: NORMAL_MARKER },
  { id: 'e-arch-writer', source: 'architect', target: 'writer', sourceHandle: 'bottom', targetHandle: 'top', type: 'default', animated: true, style: NORMAL_STYLE, markerEnd: NORMAL_MARKER },
  { id: 'e-writer-censor', source: 'writer', target: 'censor', sourceHandle: 'bottom', targetHandle: 'top', type: 'default', animated: true, style: NORMAL_STYLE, markerEnd: NORMAL_MARKER },
  { id: 'e-censor-pass', source: 'censor', target: 'decision-pass', sourceHandle: 'bottom', targetHandle: 'top', type: 'default', animated: true, style: NORMAL_STYLE, markerEnd: NORMAL_MARKER },
  { id: 'e-pass-critic', source: 'decision-pass', target: 'critic', sourceHandle: 'bottom', targetHandle: 'top', type: 'default', animated: true, style: SUCCESS_STYLE, markerEnd: SUCCESS_MARKER, label: 'Yes', labelStyle: LABEL_STYLE, labelBgStyle: LABEL_BG, labelBgPadding: [6, 4], labelBgBorderRadius: 4 },
  { id: 'e-critic-score', source: 'critic', target: 'decision-score', sourceHandle: 'bottom', targetHandle: 'top', type: 'default', animated: true, style: NORMAL_STYLE, markerEnd: NORMAL_MARKER },
  { id: 'e-score-writer', source: 'decision-score', target: 'writer', sourceHandle: 'right', targetHandle: 'right', type: 'default', animated: true, style: REVISE_STYLE, markerEnd: REVISE_MARKER, label: 'Revise (<75)', labelStyle: { ...LABEL_STYLE, fill: '#f59e0b' }, labelBgStyle: LABEL_BG, labelBgPadding: [6, 4], labelBgBorderRadius: 4 },
  { id: 'e-score-media', source: 'decision-score', target: 'media', sourceHandle: 'left', targetHandle: 'left', type: 'default', animated: true, style: SUCCESS_STYLE, markerEnd: SUCCESS_MARKER, label: 'Generate Media', labelStyle: LABEL_STYLE, labelBgStyle: LABEL_BG, labelBgPadding: [6, 4], labelBgBorderRadius: 4 },
  { id: 'e-score-knowledge', source: 'decision-score', target: 'knowledge', sourceHandle: 'bottom', targetHandle: 'top', type: 'default', animated: true, style: SUCCESS_STYLE, markerEnd: SUCCESS_MARKER, label: 'Archive', labelStyle: LABEL_STYLE, labelBgStyle: LABEL_BG, labelBgPadding: [6, 4], labelBgBorderRadius: 4 },
];

/** 仅生成大纲：开始 -> 生成大纲 -> 结束 */
const OUTLINE_ONLY_EDGES: Edge[] = [
  { id: 'e-start-arch-outline', source: 'start', target: 'architect', sourceHandle: 'bottom', targetHandle: 'top', type: 'default', animated: true, style: NORMAL_STYLE, markerEnd: NORMAL_MARKER },
];

const WORKFLOW_EDGES: Record<string, Edge[]> = {
  [WORKFLOW_ID_GENERATE_CHAPTER]: DEFAULT_EDGES_TEMPLATE,
  [WORKFLOW_ID_OUTLINE_ONLY]: OUTLINE_ONLY_EDGES,
};

type WorkflowNode = AgentFlowNode | StartFlowNode | DecisionFlowNode;
const nodeTypes = { agent: AgentNode, start: StartNode, decision: DecisionNode };

/** 完整图结构存档 */
interface SavedGraph {
  agentPositions: Record<string, { x: number; y: number }>;
  decisionNodes: DecisionFlowNode[];
  edges: Edge[];
}

const getSavedGraph = (workflowId: string): SavedGraph | null => {
  try {
    const raw = localStorage.getItem(getFlowLayoutKey(workflowId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object' || !('agentPositions' in parsed) || !('decisionNodes' in parsed) || !('edges' in parsed)) {
      return null;
    }
    return parsed as SavedGraph;
  } catch {
    return null;
  }
};

export default function WorkflowMonitor() {
  const { data: stats, isLoading } = useMonitorStats();
  const purgeQueueMutation = usePurgeQueue();
  const queryClient = useQueryClient();
  const [logs, setLogs] = useState<Array<{ time: string; type: string; message: string }>>([]);
  const [layoutMessage, setLayoutMessage] = useState<{ text: string; type: 'success' | 'info' } | null>(null);

  const [currentWorkflowId, setCurrentWorkflowId] = useState<string>(WORKFLOW_ID_GENERATE_CHAPTER);
  const [savedGraph, setSavedGraph] = useState<SavedGraph | null>(() =>
    getSavedGraph(WORKFLOW_ID_GENERATE_CHAPTER)
  );

  const [editingItem, setEditingItem] = useState<EditData | null>(null);

  const queueLengths = stats?.stats?.queues || {};
  const workersList = stats?.stats?.workers?.list || [];
  const agentTasks = stats?.stats?.agent_tasks || {};
  const agentDisabled = stats?.stats?.agent_disabled || {};
  const agentProcessing = stats?.stats?.agent_processing || {};
  const controllerWorker = workersList.find((w: unknown) => (w as { name?: string }).name === 'Controller');
  const controllerActive =
    (stats?.stats?.controller as { online?: boolean } | undefined)?.online === true ||
    (controllerWorker as { status?: string } | undefined)?.status === 'online';

  const agents: Record<string, AgentMetric> = {};
  AGENT_ORDER.forEach((agentKey) => {
    const worker = workersList.find((w: unknown) => (w as { name?: string }).name?.toLowerCase() === agentKey);
    const task = agentTasks[agentKey];
    agents[agentKey] = {
      name: agentKey.charAt(0).toUpperCase() + agentKey.slice(1),
      is_online: (worker as { status?: string } | undefined)?.status === 'online',
      queues: {
        pending: (queueLengths as Record<string, number>)[`${agentKey}_pending`] || 0,
        completed: (queueLengths as Record<string, number>)[`${agentKey}_completed`] || 0,
        suspended: (queueLengths as Record<string, number>)[`${agentKey}_suspended`] ?? 0,
      },
      current_task_id: task?.task_name,
      status: task ? 'busy' : 'idle',
      is_processing: !!agentProcessing[agentKey],
    };
  });

  const startControllerMutation = useMutation({
    mutationFn: () => monitorApi.startController(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['monitor', 'stats'] });
      addLog('system', 'Controller started');
    },
  });

  const addLog = (type: string, message: string) => {
    const time = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev.slice(-49), { time, type, message }]);
  };

  useEffect(() => {
    if (stats) {
      Object.entries(agents).forEach(([key, agent]) => {
        if (agent.queues.completed > 0) {
          addLog('route', `📥 Picked up from ${key}_completed`);
        }
      });
    }
  }, [stats]);

  const handlePurgePending = (agentKey: string) => {
    purgeQueueMutation.mutate(`${agentKey}_pending`, {
      onSuccess: () => addLog('action', `Purged ${agentKey}_pending queue`),
    });
  };

  const handlePurgeCompleted = (agentKey: string) => {
    purgeQueueMutation.mutate(`${agentKey}_completed`, {
      onSuccess: () => addLog('action', `Purged ${agentKey}_completed queue`),
    });
  };

  const handleRedrive = (agentKey: string) => {
    addLog('action', `Re-driving ${agentKey}_completed queue`);
  };

  const agentDisplayName = (key: string) =>
    key.charAt(0).toUpperCase() + key.slice(1);

  const disableAgentMutation = useMutation({
    mutationFn: (name: string) => monitorApi.disableAgent(name),
    onSuccess: (_data, name) => {
      queryClient.invalidateQueries({ queryKey: ['monitor', 'stats'] });
      addLog('action', `${agentDisplayName(name)} 已禁用`);
    },
  });
  const enableAgentMutation = useMutation({
    mutationFn: (name: string) => monitorApi.enableAgent(name),
    onSuccess: (data, name) => {
      queryClient.invalidateQueries({ queryKey: ['monitor', 'stats'] });
      const redriven = (data as { redriven?: number }).redriven ?? 0;
      const msg = redriven > 0
        ? `${agentDisplayName(name)} 已启用，已将 ${redriven} 条挂起任务弹回 Pending`
        : `${agentDisplayName(name)} 已启用`;
      addLog('action', msg);
    },
  });
  const toggleDisablePending = disableAgentMutation.isPending || enableAgentMutation.isPending;

  /**
   * 混合节点：Agent/Start 来自 API+代码（位置用存档），Decision 来自存档或默认两个
   */
  const computedNodes = useMemo<WorkflowNode[]>(() => {
    const getPos = (key: string) => savedGraph?.agentPositions?.[key] ?? DEFAULT_POSITIONS[key];

    const startNode: StartFlowNode = {
      id: 'start',
      type: 'start',
      position: getPos('start') ?? { x: 0, y: 0 },
      data: {},
      deletable: false,
    };
    const agentNodes: AgentFlowNode[] = AGENT_ORDER.map((key) => ({
      id: key,
      type: 'agent',
      position: getPos(key) ?? { x: -200, y: 0 },
      deletable: false,
      data: {
        agent: agents[key],
        isDisabled: !!(agentDisabled as Record<string, boolean>)[key],
        onToggleDisable: () =>
          (agentDisabled as Record<string, boolean>)[key]
            ? enableAgentMutation.mutate(key)
            : disableAgentMutation.mutate(key),
        disablePending: toggleDisablePending,
        onPurgePending: () => handlePurgePending(key),
        onPurgeCompleted: () => handlePurgeCompleted(key),
        onRedrive: () => handleRedrive(key),
      },
    }));
    const decisionNodes: DecisionFlowNode[] =
      currentWorkflowId === WORKFLOW_ID_OUTLINE_ONLY
        ? []
        : savedGraph?.decisionNodes?.length
          ? savedGraph.decisionNodes
          : [
              { id: 'decision-pass', type: 'decision', position: DEFAULT_POSITIONS['decision-pass'] ?? { x: -25, y: 550 }, data: { label: 'Pass?' } },
              { id: 'decision-score', type: 'decision', position: DEFAULT_POSITIONS['decision-score'] ?? { x: -25, y: 800 }, data: { label: 'Score > 75?' } },
            ];
    return [startNode, ...agentNodes, ...decisionNodes];
  }, [agents, agentDisabled, toggleDisablePending, enableAgentMutation, disableAgentMutation, savedGraph, currentWorkflowId]);

  const [nodes, setNodes, onNodesChange] = useNodesState<WorkflowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState(DEFAULT_EDGES_TEMPLATE);
  const lastSyncSigRef = useRef<string | null>(null);

  // 切换工作流时加载该工作流的存档并更新连线
  useEffect(() => {
    const saved = getSavedGraph(currentWorkflowId);
    setSavedGraph(saved);
    setEdges(saved?.edges ?? WORKFLOW_EDGES[currentWorkflowId] ?? DEFAULT_EDGES_TEMPLATE);
  }, [currentWorkflowId, setEdges]);

  const dataSig = JSON.stringify({ agents, agentDisabled, toggleDisablePending, savedGraph: !!savedGraph, currentWorkflowId });
  useEffect(() => {
    if (lastSyncSigRef.current === dataSig) return;
    lastSyncSigRef.current = dataSig;
    setNodes((prev) => {
      const next = computedNodes.map((fresh) => {
        const p = prev.find((x) => x.id === fresh.id);
        const savedPos = savedGraph?.agentPositions?.[fresh.id];
        return { ...fresh, position: p?.position ?? savedPos ?? fresh.position };
      });
      return next;
    });
  }, [dataSig, computedNodes, setNodes, savedGraph]);


  const onConnect: OnConnect = useCallback(
    (params) => {
      setEdges((eds) =>
        addEdge(
          {
            ...params,
            type: 'default',
            animated: true,
            style: DEFAULT_EDGE_STYLE,
            markerEnd: DEFAULT_EDGE_MARKER,
          },
          eds
        )
      );
    },
    [setEdges]
  );

  const addDecisionNode = useCallback(() => {
    const id = `decision-${Date.now()}`;
    const newNode: DecisionFlowNode = {
      id,
      type: 'decision',
      position: { x: 50, y: 100 },
      data: { label: 'New Logic' },
    };
    setNodes((nds) => [...nds, newNode]);
    addLog('action', 'Added new decision node');
  }, [setNodes]);

  const onSave = useCallback(() => {
    const agentPositions: Record<string, { x: number; y: number }> = {};
    const decisionNodes: DecisionFlowNode[] = [];
    nodes.forEach((node) => {
      if (node.type === 'agent' || node.type === 'start') {
        agentPositions[node.id] = { x: node.position.x, y: node.position.y };
      } else if (node.type === 'decision') {
        decisionNodes.push(node as DecisionFlowNode);
      }
    });
    const graphToSave: SavedGraph = { agentPositions, decisionNodes, edges };
    try {
      localStorage.setItem(getFlowLayoutKey(currentWorkflowId), JSON.stringify(graphToSave));
      setSavedGraph(graphToSave);
      setLayoutMessage({ text: '布局与连线已保存', type: 'success' });
      setTimeout(() => setLayoutMessage(null), 2000);
    } catch {
      setLayoutMessage({ text: '保存失败', type: 'info' });
      setTimeout(() => setLayoutMessage(null), 2000);
    }
  }, [nodes, edges, currentWorkflowId]);

  const onReset = useCallback(() => {
    localStorage.removeItem(getFlowLayoutKey(currentWorkflowId));
    const defaultEdges = WORKFLOW_EDGES[currentWorkflowId] ?? DEFAULT_EDGES_TEMPLATE;
    setSavedGraph(null);
    setEdges(defaultEdges);
    const defaultIds =
      currentWorkflowId === WORKFLOW_ID_OUTLINE_ONLY
        ? new Set(['start', ...AGENT_ORDER])
        : new Set(['start', ...AGENT_ORDER, 'decision-pass', 'decision-score']);
    setNodes((prev) =>
      prev
        .filter((n) => defaultIds.has(n.id))
        .map((n) => ({ ...n, position: DEFAULT_POSITIONS[n.id] ?? n.position }))
    );
    setLayoutMessage({ text: '已恢复当前工作流默认布局', type: 'info' });
    setTimeout(() => setLayoutMessage(null), 2000);
  }, [setEdges, setNodes, currentWorkflowId]);

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    if (node.type === 'decision') {
      setEditingItem({
        id: node.id,
        type: 'node',
        label: (node.data?.label as string) ?? '',
      });
    }
  }, []);

  const onEdgeClick = useCallback((_event: React.MouseEvent, edge: Edge) => {
    let currentColor: 'default' | 'success' | 'warning' = 'default';
    const stroke = (edge.style as { stroke?: string } | undefined)?.stroke;
    if (stroke === STYLES.success.stroke) currentColor = 'success';
    else if (stroke === STYLES.warning.stroke) currentColor = 'warning';
    const currentPattern = (edge.style as { strokeDasharray?: string } | undefined)?.strokeDasharray
      ? 'dashed'
      : 'solid';
    setEditingItem({
      id: edge.id,
      type: 'edge',
      label: (edge.label as string) ?? '',
      edgeColor: currentColor,
      edgePattern: currentPattern,
      animated: edge.animated ?? true,
    });
  }, []);

  const handleSaveElement = useCallback(
    (data: EditData) => {
      if (data.type === 'node') {
        setNodes((nds) =>
          nds.map((node) => {
            if (node.id === data.id && node.type === 'decision') {
              return { ...node, data: { ...node.data, label: data.label } } as WorkflowNode;
            }
            return node;
          })
        );
      } else if (data.type === 'edge') {
        const styleConfig = STYLES[data.edgeColor ?? 'default'];
        setEdges((eds) =>
          eds.map((edge) => {
            if (edge.id !== data.id) return edge;
            return {
              ...edge,
              label: data.label,
              animated: data.animated ?? true,
              style: {
                ...(edge.style as object),
                stroke: styleConfig.stroke,
                strokeWidth: 2,
                strokeDasharray: data.edgePattern === 'dashed' ? '5,5' : '0',
              },
              markerEnd: { type: MarkerType.ArrowClosed, color: styleConfig.color },
              labelStyle: data.label ? LABEL_STYLE : undefined,
              labelBgStyle: data.label ? LABEL_BG : undefined,
              labelBgPadding: data.label ? ([6, 4] as [number, number]) : undefined,
              labelBgBorderRadius: 4,
            };
          })
        );
      }
    },
    [setNodes, setEdges]
  );

  const handleDeleteElement = useCallback(
    (data: EditData) => {
      if (data.type === 'edge') {
        setEdges((eds) => eds.filter((e) => e.id !== data.id));
      }
      setEditingItem(null);
    },
    [setEdges]
  );

  if (isLoading) {
    return (
      <div className="h-[calc(100vh-64px)] w-full flex items-center justify-center bg-gradient-to-br from-zinc-950 via-indigo-950/20 to-zinc-950">
        <RefreshCw className="w-8 h-8 animate-spin text-zinc-400" />
      </div>
    );
  }

  return (
    <div
      className={cn(
        'h-[calc(100vh-64px)] w-full flex overflow-hidden',
        'bg-gradient-to-br from-zinc-950 via-indigo-950/20 to-zinc-950'
      )}
    >
      <div className="w-[78%] flex flex-col min-w-0 pr-3 pl-6 py-4">
        <div className="flex items-center gap-3 mb-4 flex-shrink-0">
          <h1 className="text-xl font-bold text-zinc-100">工作流助手</h1>
          {controllerActive ? (
            <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/50 gap-1">
              <Rocket className="w-3 h-3" />
              Central Cortex Online
            </Badge>
          ) : (
            <>
              <Badge variant="default" className="bg-red-500/20 text-red-400 border-red-500/50 gap-1">
                <AlertCircle className="w-3 h-3" />
                Offline
              </Badge>
              <Button
                size="sm"
                onClick={() => startControllerMutation.mutate()}
                disabled={startControllerMutation.isPending}
                className="h-7"
              >
                {startControllerMutation.isPending ? '启动中…' : 'Start'}
              </Button>
            </>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={addDecisionNode}
            className="h-8 border-dashed border-zinc-600 hover:border-zinc-400"
          >
            <Plus className="w-4 h-4 mr-1" />
            Add Logic
          </Button>
          <div className="flex-1" />
          <Button
            variant="outline"
            size="sm"
            onClick={onSave}
            className="h-8"
          >
            <Save className="w-4 h-4 mr-1" />
            Save
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onReset}
            className="h-8 text-muted-foreground"
          >
            <RotateCcw className="w-4 h-4 mr-1" />
            Reset
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['monitor', 'stats'] })}
            className="ml-auto h-8"
          >
            <RefreshCw className="w-4 h-4 mr-1" />
            Refresh
          </Button>
          {layoutMessage && (
            <span
              className={cn(
                'text-sm',
                layoutMessage.type === 'success' ? 'text-emerald-400' : 'text-zinc-400'
              )}
            >
              {layoutMessage.text}
            </span>
          )}
        </div>

        <div className="workflow-monitor-flow flex-1 min-h-0 h-full rounded-lg overflow-hidden border border-zinc-700/50 bg-zinc-900/30">
          <ReactFlow<WorkflowNode, Edge>
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            connectionMode={ConnectionMode.Loose}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.2, minZoom: 0.5, maxZoom: 1.5 }}
            minZoom={0.5}
            maxZoom={1.5}
            colorMode="dark"
            proOptions={{ hideAttribution: true }}
            snapToGrid
            snapGrid={[20, 20]}
            deleteKeyCode={['Backspace', 'Delete']}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
          >
            <Controls />
          </ReactFlow>
        </div>
      </div>

      <div className="flex min-h-0 w-[22%] min-w-[250px] flex-col border-l border-zinc-800 bg-zinc-950">
        <div className="flex min-h-0 flex-[0.3] flex-col border-b border-zinc-800">
          <DispatchTerminal logs={logs} className="h-full flex-1 border-none" sidebar />
        </div>
        <div className="flex min-h-0 flex-[0.7] flex-col">
          <ControllerLogicPanel
            nodes={nodes}
            edges={edges}
            setEdges={setEdges}
            currentWorkflowId={currentWorkflowId}
            workflowOptions={WORKFLOW_OPTIONS}
            onWorkflowChange={setCurrentWorkflowId}
          />
        </div>
      </div>

      <EditElementDialog
        isOpen={!!editingItem}
        onClose={() => setEditingItem(null)}
        data={editingItem}
        onSave={handleSaveElement}
        onDelete={handleDeleteElement}
      />
    </div>
  );
}
