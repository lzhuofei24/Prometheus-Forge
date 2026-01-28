/**
 * Index Inspector：RAG 索引可视化调试
 * - 向量透视：索引管理（添加/删除/更新）、语义搜索、按序分页列表
 * - 图谱探索：力导向图、节点着色、边标签、点击节点详情
 * 索引的添加/删除/更新由 knowledge worker 执行，日志在其终端输出。
 */
import { useState, useMemo, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ForceGraph2D from 'react-force-graph-2d';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { Button } from '../components/ui/button';
import { ScrollArea } from '../components/ui/scroll-area';
import { retrievalApi, inspectorApi, type InspectorVectorChunk, type InspectorGraphNode, type InspectorGraphLink, type InspectorGraphEdgeProperties, type IndexedNovel } from '../api/client';
import { useNovels, useChapters } from '../hooks/useNovels';
import { Loader2, Search, ChevronDown, ChevronUp, Database, Network, Plus, Trash2, RefreshCw, RotateCcw } from 'lucide-react';
import { cn } from '../lib/utils';

const COLLAPSE_LEN = 180;

function ChunkRow({ chunk, index }: { chunk: InspectorVectorChunk; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const text = chunk.text || '';
  const needCollapse = text.length > COLLAPSE_LEN;
  const displayText = needCollapse && !expanded ? text.slice(0, COLLAPSE_LEN) + '…' : text;
  const meta = chunk.metadata as Record<string, unknown> | undefined;
  const ch = meta?.chapter_num != null ? String(meta.chapter_num) : '-';
  const idx = meta?.chunk_index != null ? String(meta.chunk_index) : '-';
  const distance = chunk.distance;
  const score = distance != null ? 1 / (1 + distance) : null;
  const pct = score != null ? Math.min(100, Math.round(score * 100)) : null;

  return (
    <div className="rounded-lg border border-zinc-700/80 bg-zinc-800/50 overflow-hidden">
      <div className="px-4 py-2 flex items-center justify-between gap-3 flex-wrap border-b border-zinc-700/50">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs font-medium text-zinc-400"># {index + 1}</span>
          <span className="text-xs text-zinc-500">
            章节 {ch} · 块 {idx}
          </span>
          {pct != null && (
            <div className="flex items-center gap-2">
              <div className="w-20 h-1.5 rounded-full bg-zinc-700 overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all',
                    pct >= 70 ? 'bg-emerald-500' : pct >= 40 ? 'bg-amber-500' : 'bg-zinc-500'
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="text-xs text-zinc-400">相似度 {pct}%</span>
            </div>
          )}
        </div>
      </div>
      <div className="px-4 py-2">
        <p className="text-sm text-zinc-200 whitespace-pre-wrap break-words">{displayText}</p>
        {needCollapse && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="mt-1 text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-0.5"
          >
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {expanded ? '收起' : '展开'}
          </button>
        )}
      </div>
    </div>
  );
}

function VectorInspectorView({
  selectedNovelId,
  onNovelChange,
  indexed,
  novels,
}: {
  selectedNovelId: string | null;
  onNovelChange: (id: string | null) => void;
  indexed: IndexedNovel[];
  novels: { id: string; title: string }[];
}) {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const isSearch = !!submittedQuery.trim();
  const { data: chapters = [] } = useChapters(selectedNovelId);
  const { data: chunks = [], isLoading } = useQuery({
    queryKey: ['inspector', 'vector', selectedNovelId, isSearch ? submittedQuery : '', isSearch ? 'search' : 'list', isSearch ? undefined : offset],
    queryFn: () =>
      inspectorApi.getVectorChunks({
        novel_id: selectedNovelId!,
        q: isSearch ? submittedQuery.trim() : undefined,
        top_k: isSearch ? 30 : undefined,
        limit: isSearch ? undefined : limit,
        offset: isSearch ? undefined : offset,
      }),
    enabled: !!selectedNovelId,
  });

  const indexedById = useMemo(() => {
    const m = new Map<string, IndexedNovel>();
    indexed.forEach((r) => {
      const id = r.novel_id || novels.find((n) => n.title === r.novel_title)?.id;
      if (id) m.set(id, { ...r, novel_id: id });
    });
    return m;
  }, [indexed, novels]);

  const indexedChapters = selectedNovelId ? (indexedById.get(selectedNovelId)?.chapters ?? []) : [];
  const hasChapters = indexedChapters.length > 0;

  const addIndexMutation = useMutation({
    mutationFn: ({ novel_id, chapter_index }: { novel_id: string; chapter_index: number }) =>
      retrievalApi.addIndex(novel_id, chapter_index),
    onSuccess: (_, { novel_id }) => {
      queryClient.invalidateQueries({ queryKey: ['retrieval', 'indexed'] });
      queryClient.invalidateQueries({ queryKey: ['inspector', 'vector', novel_id] });
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ['retrieval', 'indexed'] }), 5000);
      // 任务入队后由 worker 执行，约 10–15s 后自动刷新向量列表
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ['inspector', 'vector', novel_id] }), 12000);
    },
  });

  const deleteIndexMutation = useMutation({
    mutationFn: ({ novel_id, chapter_index }: { novel_id: string; chapter_index: number }) =>
      retrievalApi.deleteIndex(novel_id, chapter_index),
    onSuccess: (_, { novel_id }) => {
      queryClient.invalidateQueries({ queryKey: ['retrieval', 'indexed'] });
      queryClient.invalidateQueries({ queryKey: ['inspector', 'vector', novel_id] });
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ['retrieval', 'indexed'] }), 5000);
    },
  });

  const handleUpdateIndex = (novelId: string, chapterIndex: number) => {
    deleteIndexMutation.mutate(
      { novel_id: novelId, chapter_index: chapterIndex },
      {
        onSuccess: () => {
          addIndexMutation.mutate({ novel_id: novelId, chapter_index: chapterIndex });
        },
      }
    );
  };

  return (
    <div className="h-full flex flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center gap-3 flex-shrink-0">
        <div className="flex items-center gap-2">
          <label className="text-sm text-zinc-400">小说</label>
          <select
            value={selectedNovelId ?? ''}
            onChange={(e) => {
              onNovelChange(e.target.value || null);
              setOffset(0);
            }}
            className="rounded-md border border-zinc-600 bg-zinc-800/80 text-zinc-200 px-3 py-1.5 text-sm min-w-[180px]"
          >
            <option value="">选择小说</option>
            {novels.map((n) => (
              <option key={n.id} value={n.id}>
                {n.title}
                {indexedById.get(n.id)?.chapters?.length != null ? `（已索引 ${indexedById.get(n.id)!.chapters.length} 章）` : ''}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1 flex items-center gap-2 min-w-[260px]">
          <Search className="w-4 h-4 text-zinc-500 shrink-0" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入查询词做语义检索（留空则按章节顺序展示最新切片）"
            className="flex-1 rounded-md border border-zinc-600 bg-zinc-800/80 text-zinc-200 px-3 py-2 text-sm placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <Button
            size="sm"
            className="bg-indigo-600 hover:bg-indigo-700"
            disabled={!selectedNovelId || isLoading}
            onClick={() => {
              setSubmittedQuery(query.trim());
              setOffset(0);
            }}
          >
            {query.trim() ? '检索' : '刷新'}
          </Button>
        </div>
      </div>

      {!selectedNovelId && (
        <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm">
          请先选择一本小说；可在下方索引管理中为该书添加/删除/更新向量索引（由 knowledge worker 执行）。
        </div>
      )}

      {selectedNovelId && (
        <>
          <div className="flex-shrink-0 rounded-lg border border-zinc-700 bg-zinc-800/50 p-3">
            <div className="text-sm font-medium text-zinc-300 mb-2">索引管理（由 knowledge worker 执行，日志见其终端）</div>
            <div className="flex flex-wrap gap-2 items-center">
              <span className="text-xs text-zinc-500">已索引章节：</span>
              {indexedChapters.length === 0 ? (
                <span className="text-xs text-zinc-500">暂无</span>
              ) : (
                indexedChapters.map((ch) => (
                  <span key={ch} className="inline-flex items-center gap-1 rounded bg-zinc-700/80 px-2 py-1 text-xs">
                    第{ch}章
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-5 w-5 p-0 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                      disabled={deleteIndexMutation.isPending}
                      onClick={() => deleteIndexMutation.mutate({ novel_id: selectedNovelId!, chapter_index: ch })}
                    >
                      <Trash2 className="w-3 h-3" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-5 w-5 p-0 text-amber-400 hover:text-amber-300"
                      disabled={addIndexMutation.isPending || deleteIndexMutation.isPending}
                      onClick={() => handleUpdateIndex(selectedNovelId!, ch)}
                      title="重建本章索引"
                    >
                      <RefreshCw className="w-3 h-3" />
                    </Button>
                  </span>
                ))
              )}
              <span className="text-xs text-zinc-500 ml-2">添加索引：</span>
              {(chapters || [])
                .filter((c) => !indexedChapters.includes(c.index))
                .map((c) => (
                  <Button
                    key={c.index}
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs border-zinc-600"
                    disabled={addIndexMutation.isPending}
                    onClick={() => addIndexMutation.mutate({ novel_id: selectedNovelId!, chapter_index: c.index })}
                  >
                    <Plus className="w-3 h-3 mr-1" />
                    第{c.index}章
                  </Button>
                ))}
              {(chapters || []).filter((c) => !indexedChapters.includes(c.index)).length === 0 && indexedChapters.length > 0 && (
                <span className="text-xs text-zinc-500">已全部索引</span>
              )}
            </div>
            {(addIndexMutation.isSuccess || deleteIndexMutation.isSuccess) && (
              <p className="text-xs text-emerald-400 mt-1">已提交 knowledge 执行，请稍后刷新列表</p>
            )}
          </div>

          {!hasChapters ? (
            <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm">
              该书暂无已索引章节，请在上方「添加索引」中选择章节并添加；任务由 knowledge worker 执行。
            </div>
          ) : (
            <>
              {isLoading ? (
                <div className="flex-1 flex items-center justify-center gap-2 text-zinc-400">
                  <Loader2 className="w-5 h-5 animate-spin" /> 加载中…
                </div>
              ) : (
                <ScrollArea className="flex-1 min-h-0">
                  <div className="space-y-3 pr-2">
                    {chunks.length === 0 ? (
                      <div className="py-8 text-center text-zinc-500 text-sm">
                        {isSearch ? '未命中与查询相似的切片' : '暂无切片数据'}
                      </div>
                    ) : (
                      chunks.map((c, i) => <ChunkRow key={c.id ?? i} chunk={c} index={i} />)
                    )}
                  </div>
                </ScrollArea>
              )}
              {!isSearch && chunks.length === limit && (
                <div className="flex justify-center pt-2">
                  <Button variant="outline" size="sm" className="border-zinc-600" onClick={() => setOffset((o) => o + limit)}>
                    加载更多
                  </Button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

const NODE_COLORS: Record<string, string> = {
  person: '#60a5fa',
  place: '#34d399',
  item: '#fbbf24',
  default: '#a78bfa',
};

const LINK_COLORS = ['#818cf8', '#22d3ee', '#34d399', '#fbbf24', '#f472b6', '#a78bfa', '#38bdf8', '#4ade80'];

function graphNodeColor(node: InspectorGraphNode): string {
  const t = (node.type ?? '').toLowerCase();
  if (t.includes('人') || t.includes('person')) return NODE_COLORS.person;
  if (t.includes('地') || t.includes('place') || t.includes('location')) return NODE_COLORS.place;
  if (t.includes('物') || t.includes('item') || t.includes('道具')) return NODE_COLORS.item;
  if (t.includes('concept')) return '#c084fc';
  return NODE_COLORS.default;
}

function linkColorByRelation(relation: string | null | undefined): string {
  if (!relation) return LINK_COLORS[0];
  let h = 0;
  for (let i = 0; i < relation.length; i++) h = (h * 31 + relation.charCodeAt(i)) >>> 0;
  return LINK_COLORS[h % LINK_COLORS.length];
}

function edgePropsSummary(p: InspectorGraphEdgeProperties): string {
  const parts: string[] = [];
  if (p.chapter != null) parts.push(`章节${p.chapter}`);
  if (p.location) parts.push(p.location);
  if (p.state) parts.push(p.state);
  if (p.quote) parts.push(`「${p.quote.length > 20 ? p.quote.slice(0, 20) + '…' : p.quote}」`);
  if (p.context) parts.push(p.context.length > 24 ? p.context.slice(0, 24) + '…' : p.context);
  return parts.join(' · ') || '';
}

type GraphNodeWithDegree = InspectorGraphNode & { __degree?: number; __level?: number };
type GraphLinkWithMeta = { source: string; target: string; relation?: string | null; properties?: InspectorGraphEdgeProperties | null };

type ContextMenu =
  | { type: 'node'; node: InspectorGraphNode; x: number; y: number }
  | { type: 'link'; link: InspectorGraphLink; x: number; y: number }
  | null;

function GraphExplorerView({
  selectedNovelId,
  onNovelChange,
  indexed: _indexed,
  novels,
}: {
  selectedNovelId: string | null;
  onNovelChange: (id: string | null) => void;
  indexed: IndexedNovel[];
  novels: { id: string; title: string }[];
}) {
  void _indexed;
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<InspectorGraphNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNodeWithDegree | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenu>(null);
  const { data: graph, isLoading } = useQuery({
    queryKey: ['inspector', 'graph', selectedNovelId],
    queryFn: () => inspectorApi.getGraph(selectedNovelId!),
    enabled: !!selectedNovelId,
  });

  const chapters = useMemo(() => {
    const s = new Set<number>();
    (graph?.links || []).forEach((l) => {
      const ch = (l.properties?.chapter ?? 0);
      s.add(ch);
    });
    return Array.from(s).sort((a, b) => a - b);
  }, [graph?.links]);

  const maxChapter = chapters.length ? Math.max(...chapters) : 0;
  const [selectedChapter, setSelectedChapter] = useState<number>(0);
  const hasSyncedChapter = useRef(false);
  const prevNovelId = useRef<string | null>(null);
  
  useEffect(() => {
    if (selectedNovelId !== prevNovelId.current) {
      prevNovelId.current = selectedNovelId;
      hasSyncedChapter.current = false;
      setSelectedChapter(0);
      setFocusNodeId(null);
      setSelectedNode(null);
    }
  }, [selectedNovelId]);
  
  useEffect(() => {
    if (chapters.length > 0 && maxChapter >= 0) {
      if (!hasSyncedChapter.current) {
        hasSyncedChapter.current = true;
        setSelectedChapter(maxChapter);
      } else {
        setSelectedChapter((prev) => Math.min(prev, maxChapter));
      }
    } else {
      hasSyncedChapter.current = false;
      setSelectedChapter(0);
    }
  }, [chapters.length, maxChapter]);

  const { gData, neighborIds } = useMemo(() => {
    if (!graph?.nodes?.length) return { gData: { nodes: [], links: [] }, neighborIds: new Set<string>() };
    const allLinks = (graph.links || []).map((l) => ({
      source: l.source,
      target: l.target,
      relation: l.relation ?? '',
      ...(l.properties ? { properties: l.properties } : {}),
    })) as GraphLinkWithMeta[];
    
    // 章节过滤：只显示当前选中章节的数据
    const hasChapterInfo = allLinks.some((l) => l.properties?.chapter != null);
    let filteredLinks = allLinks;
    if (hasChapterInfo) {
      filteredLinks = allLinks.filter((l) => (l.properties?.chapter ?? 0) === selectedChapter);
      // 如果过滤后没有边，且 selectedChapter 为 0，可能是没有章节信息，显示所有
      if (filteredLinks.length === 0 && selectedChapter === 0) {
        filteredLinks = allLinks;
      }
    }
    
    // 2-Hop 子图构建
    let nodes: GraphNodeWithDegree[] = [];
    let links: GraphLinkWithMeta[] = [];
    let neighborIds: Set<string>;
    const nodeLevelMap = new Map<string, number>();
    
    if (focusNodeId) {
      // Focus Mode: 构建 2-Hop 子图
      const centerNode = graph.nodes.find((n) => n.id === focusNodeId);
      if (!centerNode) {
        return { gData: { nodes: [], links: [] }, neighborIds: new Set<string>() };
      }
      
      // Level 0: 中心节点
      const level0 = new Set<string>([focusNodeId]);
      nodeLevelMap.set(focusNodeId, 0);
      
      // Level 1: 直接邻居
      const level1 = new Set<string>();
      filteredLinks.forEach((l) => {
        if (l.source === focusNodeId) {
          level1.add(String(l.target));
          nodeLevelMap.set(String(l.target), 1);
        } else if (l.target === focusNodeId) {
          level1.add(String(l.source));
          nodeLevelMap.set(String(l.source), 1);
        }
      });
      
      // Level 2: 间接邻居（与 Level 1 相连，且不在 Level 0 或 Level 1）
      const level2 = new Set<string>();
      filteredLinks.forEach((l) => {
        const src = String(l.source);
        const tgt = String(l.target);
        if (level1.has(src) && !level0.has(tgt) && !level1.has(tgt)) {
          level2.add(tgt);
          if (!nodeLevelMap.has(tgt)) nodeLevelMap.set(tgt, 2);
        } else if (level1.has(tgt) && !level0.has(src) && !level1.has(src)) {
          level2.add(src);
          if (!nodeLevelMap.has(src)) nodeLevelMap.set(src, 2);
        }
      });
      
      // 收集所有节点
      const allNodeIds = new Set([...level0, ...level1, ...level2]);
      nodes = graph.nodes
        .filter((n) => allNodeIds.has(n.id))
        .map((n) => ({
          ...n,
          __level: nodeLevelMap.get(n.id) ?? 0,
          __degree: 0,
        }));
      
      // 仅保留在子图中的边
      links = filteredLinks.filter((l) => {
        const src = String(l.source);
        const tgt = String(l.target);
        return allNodeIds.has(src) && allNodeIds.has(tgt);
      });
      
      // 计算度数
      const degree = new Map<string, number>();
      nodes.forEach((n) => degree.set(n.id, 0));
      links.forEach((l) => {
        degree.set(String(l.source), (degree.get(String(l.source)) ?? 0) + 1);
        degree.set(String(l.target), (degree.get(String(l.target)) ?? 0) + 1);
      });
      nodes = nodes.map((n) => ({
        ...n,
        __degree: Math.max(1, degree.get(n.id) ?? 1),
      }));
      
      // 邻居集合（用于聚焦高亮）
      neighborIds = new Set([...level1]);
    } else {
      // Global Mode: 显示所有数据
      const nodeIds = new Set<string>();
      filteredLinks.forEach((l) => {
        nodeIds.add(String(l.source));
        nodeIds.add(String(l.target));
      });
      
      let filteredNodes = graph.nodes.filter((n) => nodeIds.has(n.id));
      if (filteredNodes.length === 0 && graph.nodes.length > 0) {
        filteredNodes = graph.nodes;
        nodeIds.clear();
        filteredNodes.forEach((n) => nodeIds.add(n.id));
      }
      
      const degree = new Map<string, number>();
      filteredNodes.forEach((n) => degree.set(n.id, 0));
      filteredLinks.forEach((l) => {
        degree.set(String(l.source), (degree.get(String(l.source)) ?? 0) + 1);
        degree.set(String(l.target), (degree.get(String(l.target)) ?? 0) + 1);
      });
      nodes = filteredNodes.map((n) => ({
        ...n,
        __level: undefined,
        __degree: Math.max(1, degree.get(n.id) ?? 1),
      }));
      links = filteredLinks.map((l) => ({ ...l }));
      neighborIds = new Set<string>();
    }
    
    return { gData: { nodes, links }, neighborIds };
  }, [graph, selectedChapter, focusNodeId]);

  const incoming = useMemo(() => {
    if (!selectedNode || !graph?.links) return [];
    const links = graph.links.filter((l) => l.target === selectedNode.id);
    // 只显示当前章节的边
    const hasChapterInfo = links.some((l) => l.properties?.chapter != null);
    if (hasChapterInfo) {
      return links.filter((l) => (l.properties?.chapter ?? 0) === selectedChapter);
    }
    return links;
  }, [selectedNode, graph?.links, selectedChapter]);
  const outgoing = useMemo(() => {
    if (!selectedNode || !graph?.links) return [];
    const links = graph.links.filter((l) => l.source === selectedNode.id);
    // 只显示当前章节的边
    const hasChapterInfo = links.some((l) => l.properties?.chapter != null);
    if (hasChapterInfo) {
      return links.filter((l) => (l.properties?.chapter ?? 0) === selectedChapter);
    }
    return links;
  }, [selectedNode, graph?.links, selectedChapter]);

  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [size, setSize] = useState({ w: 640, h: 400 });
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0]?.contentRect ?? { width: 640, height: 400 };
      setSize({ w: Math.max(1, width), h: Math.max(1, height) });
    });
    ro.observe(el);
    setSize({ w: el.clientWidth || 640, h: el.clientHeight || 400 });
    return () => ro.disconnect();
  }, [selectedNovelId, isLoading]);

  useEffect(() => {
    if (!fgRef.current || !gData.nodes.length) return;
    const t = setTimeout(() => {
      try {
        const fg = fgRef.current;
        
        if (focusNodeId) {
          // Focus Mode: 同心圆布局
          // 移除默认的 center 力，手动控制中心节点
          const centerForce = fg.d3Force('center');
          if (centerForce) {
            centerForce.x(0).y(0);
          }
          
          // 配置 charge 力
          const chargeForce = fg.d3Force('charge');
          if (chargeForce && typeof chargeForce.strength === 'function') {
            chargeForce.strength((node: any) => {
              const level = (node as GraphNodeWithDegree).__level ?? 0;
              if (level === 0) return 0; // 中心节点不受排斥
              return -300; // Level 1 和 2 的排斥力
            });
          }
          
          // 配置 link 距离
          const linkForce = fg.d3Force('link');
          if (linkForce && typeof linkForce.distance === 'function') {
            linkForce.distance(100);
          }
          
          // 锁定中心节点到 (0, 0)
          gData.nodes.forEach((node: any) => {
            if ((node as GraphNodeWithDegree).__level === 0) {
              node.fx = 0;
              node.fy = 0;
            } else {
              node.fx = undefined;
              node.fy = undefined;
            }
          });
          
          // 为 Level 1 和 Level 2 添加径向力（使用自定义力函数）
          // 移除旧的径向力
          fg.d3Force('radial1', null);
          fg.d3Force('radial2', null);
          
          // Level 1: 内环 (半径 150)
          fg.d3Force('radial1', (alpha: number) => {
            const nodes = gData.nodes as any[];
            nodes.forEach((node: any) => {
              if ((node as GraphNodeWithDegree).__level === 1) {
                const dx = node.x ?? 0;
                const dy = node.y ?? 0;
                const r = Math.sqrt(dx * dx + dy * dy);
                const targetR = 150;
                if (r > 0.01) {
                  const k = (targetR - r) * alpha * 0.8;
                  node.vx = (node.vx ?? 0) + (dx / r) * k;
                  node.vy = (node.vy ?? 0) + (dy / r) * k;
                }
              }
            });
          });
          
          // Level 2: 外环 (半径 280)
          fg.d3Force('radial2', (alpha: number) => {
            const nodes = gData.nodes as any[];
            nodes.forEach((node: any) => {
              if ((node as GraphNodeWithDegree).__level === 2) {
                const dx = node.x ?? 0;
                const dy = node.y ?? 0;
                const r = Math.sqrt(dx * dx + dy * dy);
                const targetR = 280;
                if (r > 0.01) {
                  const k = (targetR - r) * alpha * 0.6;
                  node.vx = (node.vx ?? 0) + (dx / r) * k;
                  node.vy = (node.vy ?? 0) + (dy / r) * k;
                }
              }
            });
          });
          
          fg.d3ReheatSimulation?.();
          
          // 自动适配视图：等待布局稳定后自动缩放适配
          setTimeout(() => {
            try {
              if (fg.zoomToFit) {
                fg.zoomToFit(400, 20);
              }
            } catch (e) {
              console.warn('自动适配视图失败', e);
            }
          }, 800);
        } else {
          // Global Mode: 标准力导向布局
          // 释放所有固定位置
          gData.nodes.forEach((node: any) => {
            node.fx = undefined;
            node.fy = undefined;
          });
          
          // 移除径向力
          fg.d3Force('radial1', null);
          fg.d3Force('radial2', null);
          
          const chargeForce = fg.d3Force('charge');
          if (chargeForce && typeof chargeForce.strength === 'function') {
            chargeForce.strength(-400);
          }
          
          const linkForce = fg.d3Force('link');
          if (linkForce && typeof linkForce.distance === 'function') {
            linkForce.distance((link: any) => {
              const sourceDegree = (link.source as GraphNodeWithDegree)?.__degree ?? 1;
              const targetDegree = (link.target as GraphNodeWithDegree)?.__degree ?? 1;
              return 80 + Math.max(sourceDegree, targetDegree) * 15;
            });
          }
          
          fg.d3ReheatSimulation?.();
        }
      } catch (e) {
        console.warn('配置力参数失败', e);
      }
    }, 150);
    return () => clearTimeout(t);
  }, [gData.nodes.length, selectedChapter, focusNodeId, gData.nodes]);

  const handleDeleteNode = (node: InspectorGraphNode) => {
    setContextMenu(null);
    setSelectedNode((n) => (n?.id === node.id ? null : n));
    console.warn('删除节点尚未接入后端 API', node.id);
  };
  const handleDeleteLink = (link: InspectorGraphLink) => {
    setContextMenu(null);
    console.warn('删除连线尚未接入后端 API', link);
  };
  const handleEditRelation = (link: InspectorGraphLink) => {
    setContextMenu(null);
    const name = window.prompt('修改关系名称', link.relation ?? '');
    if (name != null) console.warn('修改关系名尚未接入后端 API', { link, name });
  };
  const handleMergeNodes = (node: InspectorGraphNode) => {
    setContextMenu(null);
    const targetId = window.prompt('输入要合并到的目标节点 id', '');
    if (targetId) console.warn('合并节点尚未接入后端 API', { from: node.id, to: targetId });
  };

  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close();
    const t = setTimeout(() => document.addEventListener('click', close, { once: true }), 0);
    document.addEventListener('keydown', onKey);
    return () => {
      clearTimeout(t);
      document.removeEventListener('keydown', onKey);
    };
  }, [contextMenu]);

  const nodeVal = (n: GraphNodeWithDegree) => {
    const level = n.__level;
    if (level === 0) return 12; // Center: 最大
    if (level === 1) return 8;  // Level 1: 中等
    if (level === 2) return 4;  // Level 2: 较小
    // Global Mode: 根据度数
    const degree = n.__degree ?? 1;
    return 6 + Math.sqrt(degree) * 2;
  };
  const nodeCanvasObjectMode = () => 'replace' as const;
  const nodeCanvasObject = (node: GraphNodeWithDegree & { x?: number; y?: number }, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const level = node.__level;
    const r = Math.sqrt(Math.max(0, nodeVal(node))) * 3.2;
    const isCenter = level === 0;
    const isLevel1 = level === 1;
    const isLevel2 = level === 2;
    const showLabel = globalScale > 0.7 || hoveredNode?.id === node.id;
    const label = (node.label || node.id) as string;
    
    ctx.save();
    
    // Level 2 节点降低透明度
    if (isLevel2) {
      ctx.globalAlpha = 0.75;
    }
    
    // 绘制节点
    ctx.beginPath();
    ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI, false);
    ctx.fillStyle = graphNodeColor(node);
    ctx.fill();
    
    // 描边样式
    if (isCenter) {
      // Center 节点：金色高亮描边 + 光晕
      ctx.strokeStyle = '#fbbf24';
      ctx.lineWidth = 3 / globalScale;
      ctx.stroke();
      // 外圈光晕
      ctx.beginPath();
      ctx.arc(node.x ?? 0, node.y ?? 0, r + 4, 0, 2 * Math.PI, false);
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.4)';
      ctx.lineWidth = 2 / globalScale;
      ctx.stroke();
    } else if (isLevel1) {
      ctx.strokeStyle = 'rgba(255,255,255,0.5)';
      ctx.lineWidth = 2 / globalScale;
      ctx.stroke();
    } else {
      ctx.strokeStyle = 'rgba(255,255,255,0.3)';
      ctx.lineWidth = 1 / globalScale;
      ctx.stroke();
    }
    
    // 绘制标签
    if (showLabel && label) {
      const fontSize = Math.max(10, Math.min(14, r * 0.4));
      ctx.font = `${fontSize}px system-ui, sans-serif`;
      ctx.fillStyle = 'rgba(255,255,255,0.95)';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, node.x ?? 0, node.y ?? 0);
    }
    
    ctx.restore();
  };

  const linkCanvasObjectMode = () => 'after' as const;
  const linkCanvasObject = (
    link: GraphLinkWithMeta & { source?: { x?: number; y?: number }; target?: { x?: number; y?: number } },
    ctx: CanvasRenderingContext2D,
    globalScale: number
  ) => {
    const rel = link.relation ?? '';
    if (!rel || globalScale < 0.5) return;
    const src = link.source as unknown as { x?: number; y?: number };
    const tgt = link.target as unknown as { x?: number; y?: number };
    if (src?.x == null || tgt?.x == null) return;
    const mx = ((src.x ?? 0) + (tgt.x ?? 0)) / 2;
    const my = ((src.y ?? 0) + (tgt.y ?? 0)) / 2;
    ctx.save();
    ctx.font = `${Math.max(9, 11 / globalScale)}px system-ui, sans-serif`;
    const tw = ctx.measureText(rel).width;
    const pad = 4;
    ctx.fillStyle = 'rgba(24,24,27,0.85)';
    ctx.fillRect(mx - tw / 2 - pad, my - 8, tw + pad * 2, 16);
    ctx.fillStyle = '#e4e4e7';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(rel, mx, my);
    ctx.restore();
  };

  return (
    <div className="h-full flex flex-col gap-4 p-4">
      <div className="flex items-center gap-3 flex-shrink-0">
        <label className="text-sm text-zinc-400">小说</label>
        <select
          value={selectedNovelId ?? ''}
          onChange={(e) => {
            onNovelChange(e.target.value || null);
            setSelectedNode(null);
            setContextMenu(null);
            setFocusNodeId(null);
          }}
          className="rounded-md border border-zinc-600 bg-zinc-800/80 text-zinc-200 px-3 py-1.5 text-sm min-w-[200px]"
        >
          <option value="">选择小说（按 id 加载图谱）</option>
          {novels.map((n) => (
            <option key={n.id} value={n.id}>
              {n.title}
            </option>
          ))}
        </select>
        {focusNodeId && (
          <Button
            size="sm"
            variant="outline"
            className="border-zinc-600 text-zinc-300 hover:bg-zinc-700"
            onClick={() => {
              setFocusNodeId(null);
              setSelectedNode(null);
            }}
          >
            <RotateCcw className="w-4 h-4 mr-1.5" />
            恢复全局视图
          </Button>
        )}
      </div>

      <div className="flex-1 min-h-0 flex gap-4">
        <div className="flex-1 min-h-0 flex flex-col gap-2">
          <div
            ref={containerRef}
            className="flex-1 min-h-[320px] rounded-lg border border-zinc-700 bg-zinc-900/80 relative overflow-hidden"
          >
            {!selectedNovelId && (
              <div className="absolute inset-0 flex items-center justify-center text-zinc-500 text-sm">
                选择小说后加载知识图谱
              </div>
            )}
            {selectedNovelId && isLoading && (
              <div className="absolute inset-0 flex items-center justify-center gap-2 text-zinc-400 bg-zinc-900/90">
                <Loader2 className="w-5 h-5 animate-spin" /> 加载中…
              </div>
            )}
            {selectedNovelId && !isLoading && gData.nodes.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center text-zinc-500 text-sm">
                该小说暂无图谱数据
              </div>
            )}
            {selectedNovelId && !isLoading && gData.nodes.length > 0 && (
              <ForceGraph2D
                ref={fgRef}
                graphData={gData}
                nodeId="id"
                nodeVal={nodeVal}
                nodeCanvasObjectMode={nodeCanvasObjectMode}
                nodeCanvasObject={nodeCanvasObject}
                nodeLabel={(n: InspectorGraphNode) => n.label || n.id}
                nodeColor={(n: InspectorGraphNode) => graphNodeColor(n)}
                linkLabel={(l: { relation?: string }) => (l as { relation?: string }).relation || ''}
                linkColor={(l: GraphLinkWithMeta) => linkColorByRelation(l.relation)}
                linkWidth={(l: any) => {
                  const sourceLevel = (l.source as GraphNodeWithDegree)?.__level;
                  const targetLevel = (l.target as GraphNodeWithDegree)?.__level;
                  if (sourceLevel != null || targetLevel != null) {
                    const minLevel = Math.min(sourceLevel ?? 99, targetLevel ?? 99);
                    if (minLevel === 0) return 2.5; // Center 到 Level 1
                    if (minLevel === 1) return 2.0; // Level 1 之间或到 Level 2
                    return 1.5; // Level 2 之间
                  }
                  return 1.8; // Global Mode
                }}
                linkCurvature={focusNodeId ? 0 : 0.12}
                linkDirectionalArrowLength={6}
                linkDirectionalArrowRelPos={1}
                linkDirectionalArrowColor={(l: GraphLinkWithMeta) => linkColorByRelation(l.relation)}
                linkCanvasObjectMode={linkCanvasObjectMode}
                linkCanvasObject={linkCanvasObject}
                linkDirectionalParticles={0}
                backgroundColor="rgba(24,24,27,0)"
                d3AlphaDecay={0.02}
                d3VelocityDecay={0.4}
                cooldownTicks={200}
                onNodeClick={(n, ev) => {
                  if (ev) {
                    ev.preventDefault();
                    ev.stopPropagation();
                  }
                  const node = n as GraphNodeWithDegree;
                  const originalNode = graph?.nodes?.find((gn) => gn.id === node.id);
                  if (originalNode) {
                    setSelectedNode(originalNode);
                  } else {
                    setSelectedNode({
                      id: node.id,
                      label: node.label ?? null,
                      type: node.type ?? null,
                      status: node.status ?? null,
                      description: node.description ?? null,
                    });
                  }
                  // 设置聚焦节点（触发 2-Hop 布局）
                  setFocusNodeId(node.id);
                }}
                onNodeHover={(n) => setHoveredNode(n as GraphNodeWithDegree | null)}
                onNodeRightClick={(n, ev) => {
                  ev.preventDefault();
                  setContextMenu({ type: 'node', node: n as InspectorGraphNode, x: ev.clientX, y: ev.clientY });
                }}
                onLinkRightClick={(l, ev) => {
                  ev.preventDefault();
                  const link = l as unknown as InspectorGraphLink;
                  setContextMenu({ type: 'link', link: { source: String(link.source?.id ?? link.source), target: String(link.target?.id ?? link.target), relation: (link as { relation?: string }).relation, properties: (link as { properties?: InspectorGraphEdgeProperties }).properties }, x: ev.clientX, y: ev.clientY });
                }}
                onBackgroundClick={(ev) => {
                  ev?.stopPropagation?.();
                  ev?.preventDefault?.();
                  setContextMenu(null);
                }}
                onBackgroundRightClick={() => setContextMenu(null)}
                width={size.w}
                height={size.h}
              />
            )}
          </div>
          {selectedNovelId && !isLoading && gData.nodes.length > 0 && chapters.length > 0 && (
            <div className="flex-shrink-0 px-2 pb-1 flex items-center gap-3">
              <span className="text-xs text-zinc-500 whitespace-nowrap">时间轴（按章过滤）</span>
              <input
                type="range"
                min={0}
                max={maxChapter}
                step={1}
                value={selectedChapter}
                onChange={(e) => setSelectedChapter(Number(e.target.value))}
                className="flex-1 h-2 rounded-full appearance-none bg-zinc-700 accent-indigo-500"
              />
              <span className="text-xs text-zinc-400 tabular-nums">第 {selectedChapter} 章</span>
            </div>
          )}
        </div>

        {contextMenu && (
          <div
            className="fixed z-50 min-w-[160px] rounded-lg border border-zinc-600 bg-zinc-800 shadow-xl py-1"
            style={{ left: contextMenu.x, top: contextMenu.y }}
            role="menu"
            onClick={(e) => e.stopPropagation()}
          >
            {contextMenu.type === 'node' && (
              <>
                <button
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
                  onClick={() => handleDeleteNode(contextMenu.node)}
                >
                  删除节点
                </button>
                <button
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
                  onClick={() => handleMergeNodes(contextMenu.node)}
                >
                  合并节点
                </button>
              </>
            )}
            {contextMenu.type === 'link' && (
              <>
                <button
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
                  onClick={() => handleDeleteLink(contextMenu.link)}
                >
                  删除连线
                </button>
                <button
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
                  onClick={() => handleEditRelation(contextMenu.link)}
                >
                  修改关系名称
                </button>
              </>
            )}
          </div>
        )}

        <div className="w-80 flex-shrink-0 rounded-lg border border-zinc-700 bg-zinc-800/80 p-4 flex flex-col gap-3 overflow-auto">
          <div className="font-medium text-zinc-200">实体详情</div>
          {selectedNode ? (
            <>
              <div className="text-sm">
                <div className="text-zinc-400">ID</div>
                <div className="text-zinc-200 break-all">{selectedNode.id}</div>
              </div>
              {selectedNode.label && (
                <div className="text-sm">
                  <div className="text-zinc-400">标签</div>
                  <div className="text-zinc-200">{selectedNode.label}</div>
                </div>
              )}
              {selectedNode.type && (
                <div className="text-sm">
                  <div className="text-zinc-400">类型</div>
                  <div className="text-zinc-200">{selectedNode.type}</div>
                </div>
              )}
              {(selectedNode.status != null && selectedNode.status !== '') && (
                <div className="text-sm">
                  <div className="text-zinc-400">状态</div>
                  <div className="text-zinc-200">{selectedNode.status}</div>
                </div>
              )}
              {(selectedNode.description != null && selectedNode.description !== '') && (
                <div className="text-sm">
                  <div className="text-zinc-400">描述</div>
                  <div className="text-zinc-200 text-xs leading-relaxed">{selectedNode.description}</div>
                </div>
              )}
              <div className="text-sm">
                <div className="text-zinc-400">入边 ({incoming.length})</div>
                <ul className="mt-1 space-y-2 text-zinc-300 text-xs">
                  {(incoming as InspectorGraphLink[]).slice(0, 10).map((l, i) => (
                    <li key={i} className="border-l border-zinc-600 pl-2">
                      <div>{l.source} ―{l.relation || '?'}→ {l.target}</div>
                      {(l.properties && edgePropsSummary(l.properties)) ? (
                        <div className="text-zinc-500 mt-0.5">{edgePropsSummary(l.properties)}</div>
                      ) : null}
                    </li>
                  ))}
                  {incoming.length > 10 && <li className="text-zinc-500">… 等 {incoming.length - 10} 条</li>}
                </ul>
              </div>
              <div className="text-sm">
                <div className="text-zinc-400">出边 ({outgoing.length})</div>
                <ul className="mt-1 space-y-2 text-zinc-300 text-xs">
                  {(outgoing as InspectorGraphLink[]).slice(0, 10).map((l, i) => (
                    <li key={i} className="border-l border-zinc-600 pl-2">
                      <div>{l.source} ―{l.relation || '?'}→ {l.target}</div>
                      {(l.properties && edgePropsSummary(l.properties)) ? (
                        <div className="text-zinc-500 mt-0.5">{edgePropsSummary(l.properties)}</div>
                      ) : null}
                    </li>
                  ))}
                  {outgoing.length > 10 && <li className="text-zinc-500">… 等 {outgoing.length - 10} 条</li>}
                </ul>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm">
              点击图谱中的节点查看详情
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function IndexInspector() {
  const [tab, setTab] = useState<'vector' | 'graph'>('vector');
  const [vectorNovelId, setVectorNovelId] = useState<string | null>(null);
  const [graphNovelId, setGraphNovelId] = useState<string | null>(null);

  const { data: novels = [] } = useNovels();
  const { data: indexed = [] } = useQuery({
    queryKey: ['retrieval', 'indexed'],
    queryFn: () => retrievalApi.listIndexed(),
    staleTime: 15000,
  });

  return (
    <div className="h-full flex flex-col bg-zinc-950 text-zinc-100">
      <div className="flex-none px-6 py-4 border-b border-white/10">
        <h1 className="text-xl font-semibold">索引洞察 (Index Inspector)</h1>
        <p className="text-sm text-zinc-400 mt-0.5">
          向量索引透视与知识图谱可视化，用于调试 RAG 与 Graph 状态。
        </p>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as 'vector' | 'graph')} className="flex-1 flex flex-col min-h-0">
        <TabsList className="flex-none mx-6 mt-4 w-fit bg-zinc-800/80 border border-zinc-700">
          <TabsTrigger value="vector" className="data-[state=active]:bg-indigo-600/80 data-[state=active]:text-white text-zinc-300">
            <Database className="w-4 h-4 mr-2" />
            向量透视
          </TabsTrigger>
          <TabsTrigger value="graph" className="data-[state=active]:bg-indigo-600/80 data-[state=active]:text-white text-zinc-300">
            <Network className="w-4 h-4 mr-2" />
            图谱探索
          </TabsTrigger>
        </TabsList>

        <TabsContent value="vector" className="flex-1 min-h-0 mt-0">
          <VectorInspectorView
            selectedNovelId={vectorNovelId}
            onNovelChange={setVectorNovelId}
            indexed={indexed}
            novels={novels}
          />
        </TabsContent>
        <TabsContent value="graph" className="flex-1 min-h-0 mt-0">
          <GraphExplorerView
            selectedNovelId={graphNovelId}
            onNovelChange={setGraphNovelId}
            indexed={indexed}
            novels={novels}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
