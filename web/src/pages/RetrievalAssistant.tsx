/** 检索助手：管理所有小说的向量索引。可筛选/删除/添加任一小说任一章节的索引。 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { retrievalApi, type IndexedNovel } from '../api/client';
import { useNovels, useChapters } from '../hooks/useNovels';
import { Button } from '../components/ui/button';
import { ScrollArea } from '../components/ui/scroll-area';
import { Loader2, Plus, Trash2, BookOpen } from 'lucide-react';
import { cn } from '../lib/utils';

export default function RetrievalAssistant() {
  const queryClient = useQueryClient();
  const [selectedNovelId, setSelectedNovelId] = useState<string | null>(null);
  const [addingNovelId, setAddingNovelId] = useState<string | null>(null);
  const [addingChapterIndex, setAddingChapterIndex] = useState<number | null>(null);

  const { data: novels = [] } = useNovels();
  const { data: chapters = [] } = useChapters(selectedNovelId);
  const { data: indexed = [], isLoading: indexedLoading } = useQuery({
    queryKey: ['retrieval', 'indexed'],
    queryFn: () => retrievalApi.listIndexed(),
    staleTime: 15000,
  });

  const addIndexMutation = useMutation({
    mutationFn: ({ novel_id, chapter_index }: { novel_id: string; chapter_index: number }) =>
      retrievalApi.addIndex(novel_id, chapter_index),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['retrieval'] });
      setAddingNovelId(null);
      setAddingChapterIndex(null);
    },
  });

  const deleteIndexMutation = useMutation({
    mutationFn: ({ novel_id, chapter_index }: { novel_id: string; chapter_index?: number }) =>
      retrievalApi.deleteIndex(novel_id, chapter_index),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['retrieval'] });
    },
  });

  const indexedByNovelId = new Map<string, IndexedNovel>();
  for (const row of indexed) {
    if (row.novel_id) indexedByNovelId.set(row.novel_id, row);
    else {
      const byTitle = novels.find((n) => n.title === row.novel_title);
      if (byTitle) indexedByNovelId.set(byTitle.id, { ...row, novel_id: byTitle.id });
    }
  }

  return (
    <div className="h-full flex flex-col bg-zinc-950 text-zinc-100">
      <div className="flex-none px-6 py-4 border-b border-white/10">
        <h1 className="text-xl font-semibold">检索助手</h1>
        <p className="text-sm text-zinc-400 mt-0.5">
          管理所有小说的向量索引。筛选小说后，可对任一章执行「添加索引」或「删除索引」；索引用于写作中的向量检索。
        </p>
      </div>

      <div className="flex-1 flex min-h-0">
        <div className="w-72 flex-shrink-0 flex flex-col border-r border-white/10 bg-zinc-900/50">
          <div className="flex-none px-3 py-2 border-b border-white/10 text-xs font-medium text-zinc-400 uppercase tracking-wider">
            已索引小说
          </div>
          <ScrollArea className="flex-1">
            <div className="p-2 space-y-0.5">
              <button
                type="button"
                onClick={() => setSelectedNovelId(null)}
                className={cn(
                  'w-full text-left rounded px-3 py-2 text-sm',
                  selectedNovelId === null ? 'bg-indigo-600/80 text-white' : 'text-zinc-300 hover:bg-white/5'
                )}
              >
                全部
              </button>
              {indexedLoading ? (
                <div className="p-4 flex items-center gap-2 text-zinc-500 text-sm">
                  <Loader2 className="w-4 h-4 animate-spin" /> 加载中…
                </div>
              ) : indexed.length === 0 ? (
                <div className="p-4 text-zinc-500 text-sm">暂无已索引小说</div>
              ) : (
                indexed.map((row) => {
                    const id = row.novel_id || novels.find((n) => n.title === row.novel_title)?.id;
                    const title = row.novel_title;
                    if (!id && !title) return null;
                    return (
                      <button
                        key={id ?? title}
                        type="button"
                        onClick={() => setSelectedNovelId(id || null)}
                        className={cn(
                          'w-full text-left rounded px-3 py-2 text-sm flex items-center justify-between',
                          selectedNovelId === id ? 'bg-indigo-600/80 text-white' : 'text-zinc-300 hover:bg-white/5'
                        )}
                      >
                        <span className="truncate flex-1">{title || id}</span>
                        <span className="text-xs text-zinc-500 shrink-0 ml-1">{row.chapters.length} 章</span>
                      </button>
                    );
                  })
              )}
            </div>
          </ScrollArea>
        </div>

        <div className="flex-1 min-w-0 flex flex-col p-6">
          {!selectedNovelId ? (
            <div className="flex-1 flex items-center justify-center text-zinc-500">
              左侧选择一本小说，或使用下方「按小说添加索引」为某章建索引。
            </div>
          ) : (
            <>
              <div className="flex-none flex items-center justify-between gap-4 mb-4">
                <h2 className="text-lg font-medium text-zinc-100">
                  《{novels.find((n) => n.id === selectedNovelId)?.title ?? '…'}》已索引章节
                </h2>
              </div>
              <ScrollArea className="flex-1 min-h-0">
                <div className="space-y-2">
                  {(() => {
                    const row = indexedByNovelId.get(selectedNovelId) ?? indexed.find(
                      (i) => i.novel_id === selectedNovelId || i.novel_title === novels.find((n) => n.id === selectedNovelId)?.title
                    );
                    const chs = row?.chapters ?? [];
                    if (chs.length === 0) {
                      return (
                        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-zinc-500 text-sm">
                          该书暂无已索引章节。请从下方「添加索引」中选择章节并添加。
                        </div>
                      );
                    }
                    return chs.map((ch) => (
                      <div
                        key={ch}
                        className="rounded-lg border border-zinc-700/80 bg-zinc-800/50 px-4 py-2 flex items-center justify-between"
                      >
                        <span className="text-zinc-200">第 {ch} 章</span>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                          disabled={deleteIndexMutation.isPending}
                          onClick={() =>
                            deleteIndexMutation.mutate({
                              novel_id: selectedNovelId,
                              chapter_index: ch,
                            })
                          }
                        >
                          <Trash2 className="w-4 h-4 mr-1" />
                          删除索引
                        </Button>
                      </div>
                    ));
                  })()}
                </div>
              </ScrollArea>

              <div className="flex-none mt-6 pt-4 border-t border-white/10">
                <h3 className="text-sm font-medium text-zinc-300 mb-2">添加索引</h3>
                <p className="text-xs text-zinc-500 mb-3">选择要建立向量索引的章节，该章须已有正文。建索引后可被「写作 → 检索」使用。</p>
                <div className="flex flex-wrap gap-2">
                  {(chapters || []).map((c) => {
                    const row = indexedByNovelId.get(selectedNovelId);
                    const isIndexed = row?.chapters.includes(c.index);
                    const isAdding =
                      addingNovelId === selectedNovelId && addingChapterIndex === c.index && addIndexMutation.isPending;
                    return (
                      <Button
                        key={c.index}
                        size="sm"
                        variant="outline"
                        className={cn(
                          'border-zinc-600',
                          isIndexed ? 'text-zinc-500 cursor-default' : 'text-zinc-300 hover:bg-zinc-800'
                        )}
                        disabled={isIndexed || addIndexMutation.isPending}
                        onClick={() => {
                          if (isIndexed) return;
                          setAddingNovelId(selectedNovelId);
                          setAddingChapterIndex(c.index);
                          addIndexMutation.mutate({ novel_id: selectedNovelId!, chapter_index: c.index });
                        }}
                      >
                        {isAdding ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
                        ) : (
                          <Plus className="w-3.5 h-3.5 mr-1" />
                        )}
                        第{c.index}章
                        {isIndexed ? '（已索引）' : ''}
                      </Button>
                    );
                  })}
                </div>
              </div>
            </>
          )}

          {!selectedNovelId && (
            <div className="flex-none mt-6 pt-4 border-t border-white/10">
              <h3 className="text-sm font-medium text-zinc-300 mb-2">按小说添加索引</h3>
              <p className="text-xs text-zinc-500 mb-3">选择小说后再在右侧为具体章节添加索引。</p>
              <div className="flex flex-wrap gap-2">
                {novels.map((n) => (
                  <Button
                    key={n.id}
                    size="sm"
                    variant="outline"
                    className="border-zinc-600 text-zinc-300 hover:bg-zinc-800"
                    onClick={() => setSelectedNovelId(n.id)}
                  >
                    <BookOpen className="w-3.5 h-3.5 mr-1" />
                    {n.title}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
