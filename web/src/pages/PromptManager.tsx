import { useState, useEffect, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { ScrollArea } from '../components/ui/scroll-area';
import { Badge } from '../components/ui/badge';
import { promptApi } from '../api/client';
import type { PromptUpdatePayload, PromptTemplate } from '../types';
import { Save, FileText, Loader2, Check, Plus } from 'lucide-react';
import { cn } from '../lib/utils';

type ListItem = PromptTemplate | { key: string; placeholder: true };

function isPlaceholder(item: ListItem): item is { key: string; placeholder: true } {
  return 'placeholder' in item && item.placeholder === true;
}

export default function PromptManager() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<{ description: string; content: string }>({ description: '', content: '' });

  const { data: list = [], isLoading: listLoading } = useQuery({
    queryKey: ['prompts'],
    queryFn: () => promptApi.getAll(),
    staleTime: 30000,
  });

  const { data: expectedKeysRes } = useQuery({
    queryKey: ['prompts', 'expected-keys'],
    queryFn: () => promptApi.getExpectedKeys(),
    staleTime: 60000,
  });

  const expectedKeys = expectedKeysRes?.keys ?? [];
  const dbByKey = useMemo(() => {
    const m: Record<string, PromptTemplate> = {};
    list.forEach((p) => { m[p.key] = p; });
    return m;
  }, [list]);

  const mergedList = useMemo((): ListItem[] => {
    const out: ListItem[] = [];
    const seen = new Set<string>();
    for (const k of expectedKeys) {
      seen.add(k);
      out.push(dbByKey[k] ?? { key: k, placeholder: true });
    }
    list.forEach((p) => {
      if (!seen.has(p.key)) {
        seen.add(p.key);
        out.push(p);
      }
    });
    return out.sort((a, b) => a.key.localeCompare(b.key));
  }, [list, expectedKeys, dbByKey]);

  const selectedPlaceholder = selectedKey && mergedList.some((m) => m.key === selectedKey && isPlaceholder(m));
  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['prompts', selectedKey],
    queryFn: () => promptApi.getByKey(selectedKey!),
    enabled: !!selectedKey && !selectedPlaceholder,
  });

  useEffect(() => {
    if (detail) {
      setEditForm({
        description: detail.description ?? '',
        content: detail.content ?? '',
      });
    }
  }, [detail]);

  const updateMutation = useMutation({
    mutationFn: (payload: PromptUpdatePayload) =>
      promptApi.update(selectedKey!, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] });
      queryClient.invalidateQueries({ queryKey: ['prompts', selectedKey] });
      setToast(t('prompts.saved', '已保存'));
      window.setTimeout(() => setToast(null), 2000);
    },
  });

  const createMutation = useMutation({
    mutationFn: (key: string) => promptApi.create({ key, content: '', description: null }),
    onSuccess: (_, key) => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] });
      queryClient.invalidateQueries({ queryKey: ['prompts', key] });
      setSelectedKey(key);
      setToast(t('prompts.created', '已创建，可编辑内容后保存'));
      window.setTimeout(() => setToast(null), 2000);
    },
  });

  const handleSave = () => {
    if (!selectedKey) return;
    updateMutation.mutate({
      description: editForm.description || null,
      content: editForm.content,
    });
  };

  const loading = listLoading;

  return (
    <div className="h-full flex flex-col bg-zinc-50 dark:bg-zinc-900">
      <div className="flex-none px-4 py-3 border-b border-zinc-200 dark:border-zinc-800">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
          {t('prompts.title', '提示词助手')}
        </h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-0.5">
          {t('prompts.subtitle', '查看与编辑数据库中的提示词模板')}
        </p>
        <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-2">
          {t('prompts.db_first_hint', '所有 AI 请求均优先从本库按 key 读取；未配置时回退到 config/prompts/*.yaml。')}
          {' '}
          {t('prompts.merged_hint', '下方列表已合并「系统预期 key」与「库中已有」；标「未配置」的 key 当前使用 YAML 回退，可点选后创建到库。')}
        </p>
      </div>

      <div className="flex-1 flex min-h-0 overflow-x-auto overflow-y-hidden">
        <div className="flex-1 grid grid-cols-[320px_1fr] gap-0 min-h-0 min-w-[640px]">
          <div className="border-r border-zinc-200 dark:border-zinc-800 flex flex-col min-h-0">
          <ScrollArea className="flex-1 py-2">
            <div className="px-3 space-y-1">
              {(loading || (mergedList.length === 0 && expectedKeys.length === 0)) && (
                <div className="flex items-center gap-2 py-4 text-zinc-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>{t('prompts.loading', '加载中…')}</span>
                </div>
              )}
              {!loading && mergedList.length === 0 && expectedKeys.length > 0 && (
                <p className="py-4 text-sm text-zinc-500">{t('prompts.empty', '暂无提示词模板')}</p>
              )}
              {!loading && mergedList.length > 0 &&
                mergedList.map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    onClick={() => setSelectedKey(p.key)}
                    className={cn(
                      'w-full text-left rounded-lg px-3 py-2.5 border transition-colors',
                      selectedKey === p.key
                        ? 'bg-indigo-50 dark:bg-indigo-950/40 border-indigo-200 dark:border-indigo-800 text-indigo-900 dark:text-indigo-100'
                        : 'bg-white dark:bg-zinc-900/50 border-transparent hover:bg-zinc-100 dark:hover:bg-zinc-800/50 text-zinc-900 dark:text-zinc-100'
                    )}
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <FileText className="w-4 h-4 text-zinc-500 flex-shrink-0" />
                      <span className="font-medium truncate">{p.key}</span>
                      {isPlaceholder(p) ? (
                        <Badge variant="warning" className="text-xs">
                          {t('prompts.not_configured', '未配置')}
                        </Badge>
                      ) : !('is_active' in p) ? null : !p.is_active ? (
                        <Badge variant="default" className="text-xs">
                          {t('prompts.inactive', '停用')}
                        </Badge>
                      ) : null}
                    </div>
                    {!isPlaceholder(p) && 'description' in p && p.description && (
                      <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 truncate">
                        {p.description}
                      </p>
                    )}
                  </button>
                ))}
            </div>
          </ScrollArea>
        </div>

        <div className="flex flex-col min-h-0 min-w-0 overflow-hidden pl-4">
          <div className="flex-none py-2 mb-2 border-b border-zinc-100 dark:border-zinc-800">
            <h2 className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
              {t('prompts.edit_panel_title', '编辑区')}
            </h2>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
              {t('prompts.edit_panel_hint', '在右侧编辑所选提示词的描述与内容')}
            </p>
          </div>
          {!selectedKey && (
            <div className="flex-1 flex items-center justify-center text-zinc-500 dark:text-zinc-400">
              {t('prompts.select_hint', '从左侧选择一条提示词，在此编辑')}
            </div>
          )}
          {selectedKey && selectedPlaceholder && (
            <div className="flex-1 flex flex-col min-h-0 p-4">
              <Card className="flex-1 flex flex-col min-h-0">
                <CardHeader className="flex-none py-4">
                  <CardTitle className="text-lg font-mono">{selectedKey}</CardTitle>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
                    {t('prompts.fallback_hint', '该 key 未在库中配置，当前使用 config/prompts 下对应 YAML 回退。')}
                  </p>
                </CardHeader>
                <CardContent>
                  <Button
                    size="sm"
                    onClick={() => createMutation.mutate(selectedKey)}
                    disabled={createMutation.isPending}
                  >
                    {createMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                    <span className="ml-2">{t('prompts.create_in_db', '创建到数据库')}</span>
                  </Button>
                  {toast && (
                    <span className="ml-3 text-sm text-emerald-600 dark:text-emerald-400">{toast}</span>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
          {selectedKey && !selectedPlaceholder && (
            <div className="flex-1 flex flex-col min-h-0 p-4">
              {detailLoading && (
                <div className="flex items-center gap-2 text-zinc-500 py-8">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>{t('prompts.loading', '加载中…')}</span>
                </div>
              )}
              {!detailLoading && detail && (
                <Card className="flex-1 flex flex-col min-h-0 flex overflow-hidden">
                  <CardHeader className="flex-none py-4">
                    <div className="flex items-center justify-between gap-4">
                      <CardTitle className="text-lg font-mono">{detail.key}</CardTitle>
                      {toast && (
                        <span className="flex items-center gap-1 text-sm text-emerald-600 dark:text-emerald-400">
                          <Check className="w-4 h-4" />
                          {toast}
                        </span>
                      )}
                      <Button
                        size="sm"
                        onClick={handleSave}
                        disabled={updateMutation.isPending}
                      >
                        {updateMutation.isPending ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Save className="w-4 h-4" />
                        )}
                        <span className="ml-2">{t('prompts.save', '保存')}</span>
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="flex-1 flex flex-col gap-4 min-h-0 overflow-hidden">
                    <div>
                      <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                        {t('prompts.description', '描述')}
                      </label>
                      <input
                        value={editForm.description}
                        onChange={(e) =>
                          setEditForm((f) => ({ ...f, description: e.target.value }))
                        }
                        className="w-full rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-900 px-3 py-2 text-zinc-900 dark:text-zinc-100 text-sm outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
                        placeholder={t('prompts.description_placeholder', '功能说明（选填）')}
                      />
                    </div>
                    <div className="flex-1 flex flex-col min-h-0">
                      <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1">
                        {t('prompts.content', '内容')}
                      </label>
                      <textarea
                        value={editForm.content}
                        onChange={(e) =>
                          setEditForm((f) => ({ ...f, content: e.target.value }))
                        }
                        className="flex-1 min-h-[200px] w-full rounded-md border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-900 px-3 py-2 font-mono text-sm text-zinc-900 dark:text-zinc-100 leading-relaxed resize-y outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
                        placeholder={t('prompts.content_placeholder', '提示词内容，支持换行')}
                        spellCheck={false}
                      />
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </div>
        </div>
      </div>
    </div>
  );
}
