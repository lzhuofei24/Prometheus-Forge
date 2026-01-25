import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { workflowApi } from '../api/client';
import type { WorkflowStartRequest } from '../types';
import { usePageVisible } from './usePageVisible';

export function useWorkflowState(workflowId: string | null, enabled: boolean = true) {
  const isVisible = usePageVisible();
  return useQuery({
    queryKey: ['workflow', workflowId, 'state'],
    queryFn: () => workflowApi.getState(workflowId!),
    enabled: enabled && !!workflowId && isVisible,
    refetchInterval: (enabled && !!workflowId && isVisible) ? 2000 : false,
  });
}

export function useWorkflowTrace(workflowId: string | null, enabled: boolean = true) {
  const isVisible = usePageVisible();
  return useQuery({
    queryKey: ['workflow', workflowId, 'trace'],
    queryFn: () => workflowApi.getTrace(workflowId!),
    enabled: enabled && !!workflowId && isVisible,
    refetchInterval: (enabled && !!workflowId && isVisible) ? 1000 : false,
  });
}

export function useStartWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: WorkflowStartRequest) => workflowApi.start(request),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['workflow', data.workflow_id] });
      // 使工作流助手页的队列数据立即刷新，便于看到 architect_pending 变化
      queryClient.invalidateQueries({ queryKey: ['monitor', 'stats'] });
    },
  });
}
