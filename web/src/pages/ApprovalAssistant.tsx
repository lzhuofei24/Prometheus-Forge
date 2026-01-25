import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import { approvalsApi, type PendingItem, type PendingDetail } from '../api/client';
import { Check, X, ChevronDown, ChevronUp, FileText, ListTodo } from 'lucide-react';

export default function ApprovalAssistant() {
  const queryClient = useQueryClient();
  const [detailId, setDetailId] = useState<string | null>(null);

  const { data: list = [], isLoading } = useQuery({
    queryKey: ['approvals', 'pending'],
    queryFn: () => approvalsApi.listPending('pending'),
    refetchInterval: 10000,
  });

  const { data: detail } = useQuery({
    queryKey: ['approvals', 'detail', detailId],
    queryFn: () => approvalsApi.getDetail(detailId!),
    enabled: !!detailId,
  });

  const approveMutation = useMutation({
    mutationFn: (id: string) => approvalsApi.approve(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      setDetailId(null);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) => approvalsApi.reject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      setDetailId(null);
    },
  });

  const toggleDetail = (id: string) => {
    setDetailId((cur) => (cur === id ? null : id));
  };

  return (
    <div className="h-full flex flex-col p-4 bg-zinc-50 dark:bg-zinc-900">
      <div className="flex-none mb-4">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">审批助手</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-0.5">
          展示所有待审批的写入内容、即将写入的数据库位置，以及该位置是否已有内容；通过后写入数据库，拒绝则丢弃。
        </p>
      </div>

      <ScrollArea className="flex-1 pr-4">
        {isLoading ? (
          <div className="text-zinc-500 py-8 text-center">加载中…</div>
        ) : list.length === 0 ? (
          <div className="text-zinc-500 py-8 text-center">暂无待审批项</div>
        ) : (
          <ul className="space-y-3">
            {list.map((item) => (
              <PendingCard
                key={item.id}
                item={item}
                detail={detailId === item.id ? detail : undefined}
                onToggleDetail={() => toggleDetail(item.id)}
                onApprove={() => approveMutation.mutate(item.id)}
                onReject={() => rejectMutation.mutate(item.id)}
                approving={approveMutation.isPending && approveMutation.variables === item.id}
                rejecting={rejectMutation.isPending && rejectMutation.variables === item.id}
              />
            ))}
          </ul>
        )}
      </ScrollArea>
    </div>
  );
}

function PendingCard({
  item,
  detail,
  onToggleDetail,
  onApprove,
  onReject,
  approving,
  rejecting,
}: {
  item: PendingItem;
  detail?: PendingDetail | null;
  onToggleDetail: () => void;
  onApprove: () => void;
  onReject: () => void;
  approving: boolean;
  rejecting: boolean;
}) {
  const isOutline = item.write_type === 'outline';
  const targetDesc = `数据库位置： novels → chapters(novel_id=${item.novel_id}, index=${item.chapter_index}) → chapter_drafts.${isOutline ? 'summary' : 'content'}`;

  return (
    <Card className="border-zinc-200 dark:border-zinc-700">
      <CardHeader className="py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <CardTitle className="text-base font-medium">
              《{item.novel_title}》 第 {item.chapter_index} 章
            </CardTitle>
            <Badge variant={isOutline ? 'secondary' : 'default'}>
              {isOutline ? '大纲' : '正文'}
            </Badge>
            {item.source_agent && (
              <span className="text-xs text-zinc-500">来源: {item.source_agent}</span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <Button size="sm" variant="outline" onClick={onToggleDetail}>
              {detail ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
            <Button
              size="sm"
              className="bg-green-600 hover:bg-green-700"
              onClick={onApprove}
              disabled={approving || rejecting}
            >
              <Check className="h-4 w-4 mr-1" />
              通过
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={onReject}
              disabled={approving || rejecting}
            >
              <X className="h-4 w-4 mr-1" />
              拒绝
            </Button>
          </div>
        </div>
        <p className="text-xs text-zinc-500 mt-1">{targetDesc}</p>
      </CardHeader>
      <CardContent className="pt-0 space-y-2">
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="flex items-center gap-2">
            {item.existing_has_summary ? (
              <Badge variant="outline" className="text-amber-600">已有大纲</Badge>
            ) : (
              <Badge variant="outline" className="text-zinc-400">无现有大纲</Badge>
            )}
            {item.existing_has_content ? (
              <Badge variant="outline" className="text-amber-600">已有正文</Badge>
            ) : (
              <Badge variant="outline" className="text-zinc-400">无现有正文</Badge>
            )}
          </div>
        </div>
        <div className="rounded bg-zinc-100 dark:bg-zinc-800 p-2 text-sm text-zinc-700 dark:text-zinc-300 max-h-24 overflow-y-auto">
          <span className="text-zinc-500">待写入预览：</span>
          {item.payload_preview ? (
            <span>{item.payload_preview.slice(0, 300)}{item.payload_preview.length > 300 ? '…' : ''}</span>
          ) : (
            <span className="italic">（空）</span>
          )}
        </div>

        {detail && (
          <div className="border-t border-zinc-200 dark:border-zinc-700 pt-3 mt-3 space-y-3">
            <Section title="待写入完整内容" icon={<FileText className="h-4 w-4" />}>
              {detail.write_type === 'outline' ? (
                <pre className="whitespace-pre-wrap text-sm bg-zinc-100 dark:bg-zinc-800 p-3 rounded max-h-48 overflow-y-auto">
                  {detail.payload?.summary ?? ''}
                </pre>
              ) : (
                <>
                  {detail.payload?.content && (
                    <pre className="whitespace-pre-wrap text-sm bg-zinc-100 dark:bg-zinc-800 p-3 rounded max-h-48 overflow-y-auto">
                      {detail.payload.content}
                    </pre>
                  )}
                  {detail.payload?.critique_data && (
                    <div className="mt-2 text-xs text-zinc-500">
                      审稿数据已包含在此草稿中
                    </div>
                  )}
                </>
              )}
            </Section>
            <Section title="数据库中该位置现有内容" icon={<ListTodo className="h-4 w-4" />}>
              {detail.write_type === 'outline' ? (
                <pre className="whitespace-pre-wrap text-sm bg-amber-50 dark:bg-amber-950/30 p-3 rounded max-h-32 overflow-y-auto">
                  {detail.existing_summary ?? '（无）'}
                </pre>
              ) : (
                <pre className="whitespace-pre-wrap text-sm bg-amber-50 dark:bg-amber-950/30 p-3 rounded max-h-32 overflow-y-auto">
                  {detail.existing_content ?? '（无）'}
                </pre>
              )}
            </Section>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
        {icon}
        {title}
      </div>
      {children}
    </div>
  );
}
