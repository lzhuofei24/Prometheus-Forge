import { useState, useMemo } from 'react';
import { type Node, type Edge, MarkerType } from '@xyflow/react';
import { Plus, Trash2, ArrowRight } from 'lucide-react';
import { Button } from '../ui/button';
import { cn } from '../../lib/utils';

/** 与 WorkflowMonitor 中 STYLES 保持一致的连线样式映射 */
const EDGE_STYLE_MAP = {
  default: { stroke: '#71717a', color: '#71717a', strokeDasharray: '0' as const },
  success: { stroke: '#10b981', color: '#10b981', strokeDasharray: '0' as const },
  revise: { stroke: '#f59e0b', color: '#f59e0b', strokeDasharray: '5,5' as const },
} as const;

type EdgeStyleKey = keyof typeof EDGE_STYLE_MAP;

const LABEL_STYLE = { fill: '#a1a1aa', fontWeight: 500 };
const LABEL_BG = { fill: '#18181b', fillOpacity: 0.8 };

function getEdgeStyleKey(edge: Edge): EdgeStyleKey {
  const s = edge.style as { stroke?: string; strokeDasharray?: string } | undefined;
  if (!s?.stroke) return 'default';
  if (s.stroke === EDGE_STYLE_MAP.success.stroke) return 'success';
  if (s.stroke === EDGE_STYLE_MAP.revise.stroke) return 'revise';
  return 'default';
}

function getNodeDisplayName(node: Node): string {
  const d = node.data as Record<string, unknown> | undefined;
  if (d?.agent && typeof d.agent === 'object' && 'name' in d.agent) {
    return String((d.agent as { name?: string }).name ?? node.id);
  }
  if (typeof d?.label === 'string') return d.label;
  if (node.id === 'start') return 'Start';
  return node.id;
}

export interface ControllerLogicPanelProps {
  nodes: Node[];
  edges: Edge[];
  setEdges: (edges: Edge[] | ((eds: Edge[]) => Edge[])) => void;
  onEdgeClick?: (edgeId: string) => void;
}

export function ControllerLogicPanel({
  nodes,
  edges,
  setEdges,
  onEdgeClick,
}: ControllerLogicPanelProps) {
  const [showAddForm, setShowAddForm] = useState(false);
  const [addSource, setAddSource] = useState('');
  const [addTarget, setAddTarget] = useState('');

  const nodeOptions = useMemo(
    () => nodes.map((n) => ({ id: n.id, name: getNodeDisplayName(n) })),
    [nodes]
  );

  const updateEdgeLabel = (edgeId: string, label: string) => {
    setEdges((eds) =>
      eds.map((e) => {
        if (e.id !== edgeId) return e;
        return {
          ...e,
          label: label || undefined,
          labelStyle: label ? LABEL_STYLE : undefined,
          labelBgStyle: label ? LABEL_BG : undefined,
          labelBgPadding: label ? ([6, 4] as [number, number]) : undefined,
          labelBgBorderRadius: 4,
        };
      })
    );
  };

  const updateEdgeStyle = (edgeId: string, key: EdgeStyleKey) => {
    const styleConfig = EDGE_STYLE_MAP[key];
    setEdges((eds) =>
      eds.map((e) => {
        if (e.id !== edgeId) return e;
        return {
          ...e,
          style: {
            ...(e.style as object),
            stroke: styleConfig.stroke,
            strokeWidth: 2,
            strokeDasharray: styleConfig.strokeDasharray,
          },
          markerEnd: { type: MarkerType.ArrowClosed, color: styleConfig.color },
          labelStyle:
            (e.label as string) && key === 'revise'
              ? { ...LABEL_STYLE, fill: styleConfig.color }
              : (e.label as string)
                ? LABEL_STYLE
                : undefined,
        };
      })
    );
  };

  const removeEdge = (edgeId: string) => {
    setEdges((eds) => eds.filter((e) => e.id !== edgeId));
  };

  const handleAddRule = () => {
    if (!addSource || !addTarget || addSource === addTarget) return;
    const id = `e-${addSource}-${addTarget}-${Date.now()}`;
    const cfg = EDGE_STYLE_MAP.default;
    const newEdge: Edge = {
      id,
      source: addSource,
      target: addTarget,
      sourceHandle: 'bottom',
      targetHandle: 'top',
      type: 'default',
      animated: true,
      style: { stroke: cfg.stroke, strokeWidth: 2, strokeDasharray: cfg.strokeDasharray },
      markerEnd: { type: MarkerType.ArrowClosed, color: cfg.color },
    };
    setEdges((eds) => [...eds, newEdge]);
    setAddSource('');
    setAddTarget('');
    setShowAddForm(false);
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-zinc-900">
      <div className="flex flex-shrink-0 items-center justify-between gap-2 border-b border-zinc-800 px-3 py-2">
        <span className="text-xs font-semibold text-zinc-200">Routing Logic</span>
        <Button
          variant="outline"
          size="sm"
          className="h-7 border-dashed border-zinc-600 px-2 text-zinc-400 hover:border-zinc-500 hover:text-zinc-300"
          onClick={() => setShowAddForm((v) => !v)}
        >
          <Plus className="mr-1 h-3.5 w-3.5" />
          Add Rule
        </Button>
      </div>

      {showAddForm && (
        <div className="flex flex-shrink-0 flex-col gap-2 border-b border-zinc-800 bg-zinc-950/80 p-3">
          <div className="grid grid-cols-[1fr,auto,1fr] items-center gap-2 text-xs">
            <select
              value={addSource}
              onChange={(e) => setAddSource(e.target.value)}
              className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-zinc-200 outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">Source</option>
              {nodeOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
            <ArrowRight className="h-4 w-4 text-zinc-500" />
            <select
              value={addTarget}
              onChange={(e) => setAddTarget(e.target.value)}
              className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-zinc-200 outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">Target</option>
              {nodeOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </div>
          <Button
            size="sm"
            className="h-7 w-full text-xs"
            onClick={handleAddRule}
            disabled={!addSource || !addTarget || addSource === addTarget}
          >
            Confirm Add
          </Button>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto">
        <ul className="space-y-1 p-2">
          {edges.map((edge) => {
            const src = nodes.find((n) => n.id === edge.source);
            const tgt = nodes.find((n) => n.id === edge.target);
            const srcName = src ? getNodeDisplayName(src) : edge.source;
            const tgtName = tgt ? getNodeDisplayName(tgt) : edge.target;
            const styleKey = getEdgeStyleKey(edge);
            const label = (edge.label as string) ?? '';

            return (
              <li
                key={edge.id}
                className={cn(
                  'rounded border border-zinc-700/60 bg-zinc-950/60 p-2',
                  onEdgeClick && 'cursor-pointer hover:border-zinc-600'
                )}
                onClick={() => onEdgeClick?.(edge.id)}
              >
                <div className="mb-1.5 flex items-center justify-between gap-1 text-xs text-zinc-400">
                  <span className="truncate font-medium text-zinc-300">{srcName}</span>
                  <ArrowRight className="h-3.5 w-3.5 flex-shrink-0 text-zinc-500" />
                  <span className="truncate font-medium text-zinc-300">{tgtName}</span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeEdge(edge.id);
                    }}
                    className="flex-shrink-0 rounded p-0.5 text-zinc-500 hover:bg-red-500/20 hover:text-red-400"
                    title="Delete"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    type="text"
                    value={label}
                    onChange={(e) => updateEdgeLabel(edge.id, e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    placeholder="Condition"
                    className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-[11px] text-zinc-200 placeholder:text-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                  <select
                    value={styleKey}
                    onChange={(e) => updateEdgeStyle(edge.id, e.target.value as EdgeStyleKey)}
                    onClick={(e) => e.stopPropagation()}
                    className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-[11px] text-zinc-200 focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="default">Default</option>
                    <option value="success">Success</option>
                    <option value="revise">Revise</option>
                  </select>
                </div>
              </li>
            );
          })}
          {edges.length === 0 && (
            <li className="py-6 text-center text-xs text-zinc-500">No routing rules. Add one or draw on the graph.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
