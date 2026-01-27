import { useQuery } from '@tanstack/react-query';
import { novelsApi } from '../../api/services';
import { useMemo } from 'react';

export interface GraphRAGViewerProps {
  novelId: string | null;
  className?: string;
  onNodeClick?: (node: { id: string; label?: string }) => void;
}

export function GraphRAGViewer({ novelId, className = '', onNodeClick }: GraphRAGViewerProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['novel-graph', novelId],
    queryFn: () => novelsApi.getGraph(novelId!),
    enabled: !!novelId,
  });

  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    return { nodes: data.nodes || [], edges: data.edges || [] };
  }, [data]);

  if (!novelId) {
    return (
      <div className={`rounded border border-zinc-700 bg-zinc-900/50 p-4 text-zinc-500 ${className}`}>
        请先选择小说
      </div>
    );
  }
  if (isLoading) {
    return (
      <div className={`rounded border border-zinc-700 bg-zinc-900/50 p-4 text-zinc-500 ${className}`}>
        加载图谱中…
      </div>
    );
  }
  if (nodes.length === 0 && edges.length === 0) {
    return (
      <div className={`rounded border border-zinc-700 bg-zinc-900/50 p-4 text-zinc-500 ${className}`}>
        暂无关系图谱数据，完成章节并运行知识节点后会生成
      </div>
    );
  }

  return (
    <div className={`rounded border border-zinc-700 bg-zinc-900/50 overflow-hidden ${className}`}>
      <div className="px-3 py-2 border-b border-zinc-700 text-xs font-medium text-zinc-400">
        人物/实体关系图谱（GraphRAG）
      </div>
      <div className="p-3 max-h-80 overflow-auto">
        <ul className="space-y-1 text-sm">
          {edges.slice(0, 50).map((e, i) => (
            <li key={i} className="text-zinc-300">
              <span
                className="cursor-pointer hover:text-indigo-400"
                onClick={() => onNodeClick?.({ id: e.source, label: e.source })}
                role="button"
                tabIndex={0}
              >
                {e.source}
              </span>
              <span className="text-zinc-500 mx-1">—{e.relation || '关系'}—</span>
              <span
                className="cursor-pointer hover:text-indigo-400"
                onClick={() => onNodeClick?.({ id: e.target, label: e.target })}
                role="button"
                tabIndex={0}
              >
                {e.target}
              </span>
            </li>
          ))}
        </ul>
        {edges.length > 50 && (
          <p className="text-zinc-500 text-xs mt-2">仅展示前 50 条，共 {edges.length} 条关系</p>
        )}
      </div>
    </div>
  );
}
