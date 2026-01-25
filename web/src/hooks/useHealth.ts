import { useQuery } from '@tanstack/react-query';
import { healthApi } from '../api/client';

export function useHealthCheck() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => healthApi.check(),
    refetchInterval: 5000,
    retry: 1,
    retryDelay: 1000,
  });
}
