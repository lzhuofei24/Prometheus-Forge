import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { workflowApi } from '../api/client';
import type { WorkflowStartRequest } from '../types';
import { usePageVisible } from './usePageVisible';

export const WORKFLOW_ID_GENERATE_CHAPTER = 'generate_chapter';
export const WORKFLOW_ID_OUTLINE_ONLY = 'outline_only';
export const WORKFLOW_ID_CONTENT_ONLY = 'content_only';
export const WORKFLOW_ID_APPROVAL_ONLY = 'approval_only';
export const WORKFLOW_ID_MEDIA_ONLY = 'media_only';

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

export function useWorkflowTasks(workflowType: string, enabled = true) {
  const isVisible = usePageVisible();
  return useQuery({
    queryKey: ['workflow', 'tasks', workflowType],
    queryFn: () => workflowApi.getTasks(workflowType),
    enabled: enabled && !!workflowType && isVisible,
    refetchInterval: isVisible ? 4000 : false,
  });
}

export function useStartWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: WorkflowStartRequest) => workflowApi.start(request),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['workflow', data.workflow_id] });
      const wt = variables.workflow_type || WORKFLOW_ID_GENERATE_CHAPTER;
      queryClient.invalidateQueries({ queryKey: ['workflow', 'tasks', wt] });
      queryClient.invalidateQueries({ queryKey: ['monitor', 'stats'] });
    },
  });
}
