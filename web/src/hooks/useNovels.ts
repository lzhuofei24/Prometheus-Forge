import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { novelsApi, chaptersApi, type CreateNovelRequest, type CreateChapterRequest, type SaveChapterRequest } from '../api/services';

/** 写作/阅读助手数据 hooks：小说列表、目录、正文、大纲均来自 novels/chapters API（数据库），无文件或本地源。 */
export function useNovels() {
  return useQuery({
    queryKey: ['novels'],
    queryFn: () => novelsApi.list(),
    retry: 1,
    retryDelay: 1000,
    staleTime: 30000,
    gcTime: 300000,
  });
}

export function useNovel(novelId: string | null) {
  return useQuery({
    queryKey: ['novels', novelId],
    queryFn: () => novelsApi.get(novelId!),
    enabled: !!novelId,
  });
}

export function useChapters(novelId: string | null) {
  return useQuery({
    queryKey: ['novels', novelId, 'chapters'],
    queryFn: () => chaptersApi.list(novelId!),
    enabled: !!novelId,
    retry: 1,
    retryDelay: 1000,
    staleTime: 30000,
    gcTime: 300000,
  });
}

export function useChapterContent(novelId: string | null, chapterIndex: number | null) {
  return useQuery({
    queryKey: ['novels', novelId, 'chapters', chapterIndex],
    queryFn: () => chaptersApi.get(novelId!, chapterIndex!),
    enabled: !!novelId && chapterIndex !== null,
    staleTime: 60000,
    gcTime: 300000,
    retry: (failureCount, error: any) => {
      if (error?.response?.status === 404) {
        return false;
      }
      return failureCount < 2;
    },
  });
}

export function useCreateNovel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateNovelRequest) => novelsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['novels'] });
    },
  });
}

export function useCreateChapter() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateChapterRequest) => chaptersApi.create(data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['novels', variables.novel_id, 'chapters'] });
    },
  });
}

export function useSaveChapter() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ novelId, chapterIndex, data }: { novelId: string; chapterIndex: number; data: SaveChapterRequest }) =>
      chaptersApi.save(novelId, chapterIndex, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['novels', variables.novelId, 'chapters', variables.chapterIndex] });
      queryClient.invalidateQueries({ queryKey: ['novels', variables.novelId, 'chapters'] });
    },
  });
}

export function useDeleteChapter() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ novelId, chapterIndex }: { novelId: string; chapterIndex: number }) =>
      chaptersApi.delete(novelId, chapterIndex),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['novels', variables.novelId, 'chapters'] });
    },
  });
}
