import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { helpApi, type SystemConcept } from '../api/client';
import { Button } from '../components/ui/button';
import { Card, CardHeader, CardTitle } from '../components/ui/card';
import { ScrollArea } from '../components/ui/scroll-area';
import { HelpCircle, Pencil, X, Check } from 'lucide-react';
import { cn } from '../lib/utils';

export default function Help() {
  const queryClient = useQueryClient();
  const { data: concepts = [], isLoading } = useQuery({
    queryKey: ['help', 'concepts'],
    queryFn: () => helpApi.getConcepts(),
  });
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState('');
  const [editDesc, setEditDesc] = useState('');

  const updateMutation = useMutation({
    mutationFn: ({ key, label, description }: { key: string; label: string; description: string | null }) =>
      helpApi.updateConcept(key, { label, description }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['help', 'concepts'] });
      setEditingKey(null);
    },
  });

  const startEdit = (c: SystemConcept) => {
    setEditingKey(c.key);
    setEditLabel(c.label);
    setEditDesc(c.description ?? '');
  };

  const cancelEdit = () => {
    setEditingKey(null);
  };

  const saveEdit = () => {
    if (!editingKey) return;
    updateMutation.mutate({
      key: editingKey,
      label: editLabel.trim() || editingKey,
      description: editDesc.trim() || null,
    });
  };

  return (
    <div className="h-full flex flex-col bg-zinc-950 text-zinc-100">
      <div className="flex-none px-6 py-4 border-b border-white/10">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <HelpCircle className="w-5 h-5 text-indigo-400" />
          帮助 · 系统概念
        </h1>
        <p className="text-sm text-zinc-400 mt-1">
          此处展示并支持编辑系统内的核心概念名称与说明，用于全站术语统一（如「流程类型」「运行」等）。修改后将影响写作、审批助手、监控等页面的用词。
        </p>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-6 space-y-4 max-w-3xl">
          {isLoading ? (
            <div className="text-zinc-500 py-8 text-center">加载中…</div>
          ) : concepts.length === 0 ? (
            <div className="text-zinc-500 py-8 text-center">暂无概念数据，请确认后端已执行迁移脚本或访问过帮助接口以初始化种子数据。</div>
          ) : (
            concepts.map((c) => (
              <Card key={c.key} className={cn('bg-zinc-900/80 border-zinc-700 text-zinc-100')}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <code className="text-xs text-zinc-500 font-mono">{c.key}</code>
                      {editingKey === c.key ? (
                        <div className="mt-2 space-y-2">
                          <input
                            value={editLabel}
                            onChange={(e) => setEditLabel(e.target.value)}
                            className="w-full rounded border border-zinc-600 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100"
                            placeholder="展示名称"
                          />
                          <textarea
                            value={editDesc}
                            onChange={(e) => setEditDesc(e.target.value)}
                            rows={3}
                            className="w-full rounded border border-zinc-600 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100 resize-y"
                            placeholder="说明（可选）"
                          />
                          <div className="flex gap-2">
                            <Button size="sm" onClick={saveEdit} disabled={updateMutation.isPending}>
                              <Check className="w-3.5 h-3.5 mr-1" /> 保存
                            </Button>
                            <Button size="sm" variant="ghost" onClick={cancelEdit}>
                              <X className="w-3.5 h-3.5 mr-1" /> 取消
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <CardTitle className="text-base mt-1">{c.label}</CardTitle>
                          {c.description ? (
                            <p className="text-sm text-zinc-400 mt-1 whitespace-pre-wrap">{c.description}</p>
                          ) : null}
                          {c.scope ? (
                            <span className="inline-block mt-2 text-xs text-zinc-500">分类: {c.scope}</span>
                          ) : null}
                        </>
                      )}
                    </div>
                    {editingKey !== c.key && (
                      <Button variant="ghost" size="sm" className="text-zinc-400 hover:text-zinc-200" onClick={() => startEdit(c)}>
                        <Pencil className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                </CardHeader>
              </Card>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
