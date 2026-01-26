import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { monitorApi } from '../api/client';
import { usePageVisible } from './usePageVisible';

export function useMonitorStats(enabled: boolean = true) {
  const isVisible = usePageVisible();
  return useQuery({
    queryKey: ['monitor', 'stats'],
    queryFn: () => monitorApi.getResources(),
    enabled: enabled && isVisible,
    refetchInterval: (enabled && isVisible) ? 1000 : false,
  });
}

export function usePurgeQueue() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (queueName: string) => monitorApi.purgeQueue(queueName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['monitor', 'stats'] });
    },
  });
}

export function usePurgeAllQueues() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => monitorApi.purgeAllQueues(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['monitor', 'stats'] });
    },
  });
}
