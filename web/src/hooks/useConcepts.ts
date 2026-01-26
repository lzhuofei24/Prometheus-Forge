import { useQuery, useQueryClient } from '@tanstack/react-query';
import { helpApi, type SystemConcept } from '../api/client';

const CONCEPTS_QUERY_KEY = ['help', 'concepts'] as const;

/** 获取系统概念列表，用于帮助页与全站术语展示 */
export function useConcepts(scope?: string) {
  const queryClient = useQueryClient();
  const { data: concepts = [], isLoading, isError, refetch } = useQuery({
    queryKey: [...CONCEPTS_QUERY_KEY, scope ?? 'all'],
    queryFn: () => helpApi.getConcepts(scope),
  });

  const map = new Map<string, SystemConcept>();
  for (const c of concepts) {
    map.set(c.key, c);
  }

  /** 按 key 取展示用 label，若无则退回 key */
  const getConceptLabel = (key: string): string => map.get(key)?.label ?? key;

  /** 按 key 取完整概念 */
  const getConcept = (key: string): SystemConcept | undefined => map.get(key);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: CONCEPTS_QUERY_KEY });

  return {
    concepts,
    getConceptLabel,
    getConcept,
    map,
    isLoading,
    isError,
    refetch,
    invalidate,
  };
}
