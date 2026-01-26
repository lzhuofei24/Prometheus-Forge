import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import {
  approvalsApi,
  WORKFLOW_TYPE_LABELS,
  type PendingItem,
  type PendingDetail,
} from '../api/client';
import { useConcepts } from '../hooks/useConcepts';
import { Check, X, FileText, ListTodo, Database } from 'lucide-react';
import { cn } from '../lib/utils';

const ALL_WORKFLOWS = '__all__';
const ALL_TYPES = '__all__';

export default function ApprovalAssistant() {
  const { getConceptLabel } = useConcepts();
  const queryClient = useQueryClient();
  const [selectedWorkflowType, setSelectedWorkflowType] = useState<string | null>(ALL_TYPES);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(ALL_WORKFLOWS);
  const [selectedPendingId, setSelectedPendingId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'body' | 'outline'>('body');
  const runLabel = getConceptLabel('run');

  const { data: workflowTypes = [] } = useQuery({
    queryKey: ['approvals', 'workflow-types'],
    queryFn: () => approvalsApi.listWorkflowTypesWithPending('pending'),
    refetchInterval: 10000,
  });

  const { data: workflows = [] } = useQuery({
    queryKey: ['approvals', 'workflows', selectedWorkflowType],
    queryFn: () =>
      approvalsApi.listWorkflowsWithPending(
        'pending',
        selectedWorkflowType === ALL_TYPES ? undefined : selectedWorkflowType ?? undefined
      ),
    refetchInterval: 10000,
  });

  const { data: list = [], isLoading } = useQuery({
    queryKey: ['approvals', 'pending', selectedWorkflowType, selectedWorkflowId],
    queryFn: () =>
      approvalsApi.listPending(
        'pending',
        selectedWorkflowId === ALL_WORKFLOWS ? undefined : selectedWorkflowId ?? undefined,
        selectedWorkflowType === ALL_TYPES ? undefined : selectedWorkflowType ?? undefined
      ),
    refetchInterval: 10000,
  });

  const { data: detail } = useQuery({
    queryKey: ['approvals', 'detail', selectedPendingId],
    queryFn: () => approvalsApi.getDetail(selectedPendingId!),
    enabled: !!selectedPendingId,
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, novelId }: { id: string; novelId: string }) => approvalsApi.approve(id),
    onSuccess: (_, { novelId }) => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      queryClient.invalidateQueries({ queryKey: ['novels', novelId, 'chapters'] });
      setSelectedPendingId(null);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) => approvalsApi.reject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      setSelectedPendingId(null);
    },
  });

  const selectedItem = list.find((x) => x.id === selectedPendingId);

  return (
    <div className="h-full flex flex-col bg-zinc-950 text-zinc-100">
      <div className="flex-none px-6 py-4 border-b border-white/10">
        <h1 className="text-xl font-semibold">审批助手</h1>
        <p className="text-sm text-zinc-400 mt-0.5">
          左侧第一层选启动形式、第二层选{runLabel}、第三层选审批请求；右侧对比待写入与原有内容，支持正文/大纲切换。
        </p>
      </div>

      <div className="flex-1 flex min-h-0">
        {/* 左侧三层侧边栏 */}
        <div className="w-80 flex-shrink-0 flex flex-col border-r border-white/10 bg-zinc-900/50">
          {/* 第一层：启动形式 */}
          <div className="flex-none border-b border-white/10 px-3 py-2">
            <div className="text-xs font-medium text-zinc-400 uppercase tracking-wider">启动形式</div>
            <ScrollArea className="h-20 mt-1">
              <div className="space-y-0.5">
                <button
                  type="button"
                  onClick={() => {
                    setSelectedWorkflowType(ALL_TYPES);
                    setSelectedWorkflowId(ALL_WORKFLOWS);
                    setSelectedPendingId(null);
                  }}
                  className={cn(
                    'w-full text-left rounded px-2 py-1.5 text-sm',
                    selectedWorkflowType === ALL_TYPES
                      ? 'bg-indigo-600/80 text-white'
                      : 'text-zinc-300 hover:bg-white/5'
                  )}
                >
                  全部
                </button>
                {workflowTypes.map((wt) => (
                  <button
                    key={wt.workflow_type || '_empty'}
                    type="button"
                    onClick={() => {
                      setSelectedWorkflowType(wt.workflow_type);
                      setSelectedWorkflowId(ALL_WORKFLOWS);
                      setSelectedPendingId(null);
                    }}
                    className={cn(
                      'w-full text-left rounded px-2 py-1.5 text-sm flex items-center justify-between',
                      selectedWorkflowType === wt.workflow_type
                        ? 'bg-indigo-600/80 text-white'
                        : 'text-zinc-300 hover:bg-white/5'
                    )}
                  >
                    <span className="truncate text-xs">
                      {WORKFLOW_TYPE_LABELS[wt.workflow_type] ?? (wt.workflow_type || '未区分')}
                    </span>
                    <Badge variant="secondary" className="ml-1 h-5 text-[10px]">
                      {wt.count}
                    </Badge>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </div>
          {/* 第二层：运行 */}
          <div className="flex-none border-b border-white/10 px-3 py-2">
            <div className="text-xs font-medium text-zinc-400 uppercase tracking-wider">{runLabel}</div>
            <ScrollArea className="h-20 mt-1">
              <div className="space-y-0.5">
                <button
                  type="button"
                  onClick={() => {
                    setSelectedWorkflowId(ALL_WORKFLOWS);
                    setSelectedPendingId(null);
                  }}
                  className={cn(
                    'w-full text-left rounded px-2 py-1.5 text-sm',
                    selectedWorkflowId === ALL_WORKFLOWS
                      ? 'bg-indigo-600/80 text-white'
                      : 'text-zinc-300 hover:bg-white/5'
                  )}
                >
                  全部
                </button>
                {workflows.map((w) => (
                  <button
                    key={w.workflow_id}
                    type="button"
                    onClick={() => {
                      setSelectedWorkflowId(w.workflow_id);
                      setSelectedPendingId(null);
                    }}
                    className={cn(
                      'w-full text-left rounded px-2 py-1.5 text-sm flex items-center justify-between',
                      selectedWorkflowId === w.workflow_id
                        ? 'bg-indigo-600/80 text-white'
                        : 'text-zinc-300 hover:bg-white/5'
                    )}
                  >
                    <span className="truncate font-mono text-xs">{w.workflow_id}</span>
                    <Badge variant="secondary" className="ml-1 h-5 text-[10px]">
                      {w.count}
                    </Badge>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </div>
          {/* 第三层：审批请求 */}
          <div className="flex-1 min-h-0 flex flex-col">
            <div className="flex-none px-3 py-2 border-b border-white/10 text-xs font-medium text-zinc-400 uppercase tracking-wider">
              审批请求
            </div>
            <ScrollArea className="flex-1">
              {isLoading ? (
                <div className="p-4 text-zinc-500 text-sm text-center">加载中…</div>
              ) : list.length === 0 ? (
                <div className="p-4 text-zinc-500 text-sm text-center">该{runLabel}下暂无待审批项</div>
              ) : (
                <ul className="p-2 space-y-1">
                  {list.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedPendingId(item.id)}
                        className={cn(
                          'w-full text-left rounded px-3 py-2 text-sm border transition-colors',
                          selectedPendingId === item.id
                            ? 'bg-indigo-500/20 border-indigo-500/50 text-white'
                            : 'border-transparent hover:bg-white/5 text-zinc-300'
                        )}
                      >
                        <div className="font-medium truncate">
                          《{item.novel_title}》 第{item.chapter_index}章
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <Badge variant={item.write_type === 'outline' ? 'secondary' : 'default'} className="text-[10px]">
                            {item.write_type === 'outline' ? '大纲' : '正文'}
                          </Badge>
                          {item.source_agent && (
                            <span className="text-xs text-zinc-500">来源: {item.source_agent}</span>
                          )}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </ScrollArea>
          </div>
        </div>

        {/* 右侧对比区域 */}
        <div className="flex-1 min-w-0 flex flex-col">
          {!detail && !selectedPendingId && (
            <div className="flex-1 flex items-center justify-center text-zinc-500">
              请从左侧选择一条审批请求
            </div>
          )}
          {selectedPendingId && !detail && (
            <div className="flex-1 flex items-center justify-center text-zinc-500">加载中…</div>
          )}
          {detail && selectedItem && (
            <>
              <div className="flex-none flex items-center justify-between gap-4 px-6 py-3 border-b border-white/10 bg-zinc-900/30 flex-wrap">
                <div className="flex items-center gap-4 flex-wrap">
                  <span className="font-medium">
                    《{detail.novel_title}》 第{detail.chapter_index}章
                  </span>
                  <div className="flex rounded-lg border border-white/10 overflow-hidden">
                    <button
                      type="button"
                      onClick={() => setViewMode('body')}
                      className={cn(
                        'px-3 py-1.5 text-sm',
                        viewMode === 'body' ? 'bg-indigo-600 text-white' : 'bg-zinc-800/80 text-zinc-400 hover:text-zinc-200'
                      )}
                    >
                      正文
                    </button>
                    <button
                      type="button"
                      onClick={() => setViewMode('outline')}
                      className={cn(
                        'px-3 py-1.5 text-sm',
                        viewMode === 'outline' ? 'bg-indigo-600 text-white' : 'bg-zinc-800/80 text-zinc-400 hover:text-zinc-200'
                      )}
                    >
                      大纲
                    </button>
                  </div>
                  <span className="text-sm text-zinc-400">
                    来源: {detail.source_agent ?? '—'}
                  </span>
                  <span className="text-xs text-zinc-500 flex items-center gap-1">
                    <Database className="h-3.5 w-3.5" />
                    存储: novels(id={detail.novel_id}) → chapters(index={detail.chapter_index}) → chapter_drafts.{viewMode === 'outline' ? 'summary' : 'content'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    className="bg-green-600 hover:bg-green-700"
                    onClick={() => approveMutation.mutate({ id: detail.id, novelId: detail.novel_id })}
                    disabled={approveMutation.isPending || rejectMutation.isPending}
                  >
                    <Check className="h-4 w-4 mr-1" />
                    通过
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => rejectMutation.mutate(detail.id)}
                    disabled={approveMutation.isPending || rejectMutation.isPending}
                  >
                    <X className="h-4 w-4 mr-1" />
                    拒绝
                  </Button>
                </div>
              </div>

              <div className="flex-1 grid grid-cols-2 gap-4 p-6 min-h-0 overflow-auto">
                <div className="flex flex-col min-h-0">
                  <div className="flex-none flex items-center gap-2 text-sm font-medium text-zinc-300 mb-2">
                    <FileText className="h-4 w-4" />
                    待写入内容
                  </div>
                  <div className="flex-1 rounded-lg border border-emerald-500/30 bg-zinc-900/50 p-4 overflow-auto">
                    <pre className="whitespace-pre-wrap text-sm text-zinc-200 font-sans">
                      {viewMode === 'outline'
                        ? (typeof detail.payload?.summary === 'string' ? detail.payload.summary : (detail.payload?.summary ? JSON.stringify(detail.payload.summary, null, 2) : '')) || '（空白）'
                        : (detail.payload?.content ?? '') || '（空白）'}
                    </pre>
                  </div>
                </div>
                <div className="flex flex-col min-h-0">
                  <div className="flex-none flex items-center gap-2 text-sm font-medium text-zinc-300 mb-2">
                    <ListTodo className="h-4 w-4" />
                    原有内容（数据库中）
                  </div>
                  <div className="flex-1 rounded-lg border border-amber-500/30 bg-amber-950/20 p-4 overflow-auto">
                    <pre className="whitespace-pre-wrap text-sm text-zinc-200 font-sans">
                      {viewMode === 'outline'
                        ? (detail.existing_summary ?? '') || '（空白）'
                        : (detail.existing_content ?? '') || '（空白）'}
                    </pre>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
