import axios, { AxiosError } from 'axios';
import { logger } from '../utils/logger';
import type {
  WorkflowStartRequest,
  WorkflowStartResponse,
  WorkflowState,
  WorkflowTrace,
  WorkflowTaskItem,
  MonitorStats,
  PromptTemplate,
  PromptUpdatePayload,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

apiClient.interceptors.request.use(
  (config) => {
    const method = config.method?.toUpperCase() || 'UNKNOWN';
    const url = config.url || '';
    const fullUrl = `${config.baseURL}${url}`;
    const payload = config.data || config.params;

    (config as any).requestTime = Date.now();

    logger.network(
      'API Request',
      `Request: ${method} ${fullUrl}`,
      {
        method,
        url: fullUrl,
        headers: config.headers,
        payload,
        requestTime: (config as any).requestTime,
      }
    );

    console.log(`[API Request] ${method} ${url}`, payload);
    return config;
  },
  (error) => {
    logger.error('API Request Error', 'Request failed before sending', {
      error: error.message,
      stack: error.stack,
    });
    console.error('[API Request Error]', error);
    return Promise.reject(error);
  }
);

apiClient.interceptors.response.use(
  (response) => {
    const method = response.config.method?.toUpperCase() || 'UNKNOWN';
    const url = response.config.url || '';
    const fullUrl = `${response.config.baseURL}${url}`;
    const status = response.status;
    const requestTime = (response.config as any).requestTime || Date.now();
    const latency = Date.now() - requestTime;

    logger.network(
      'API Response',
      `Response: ${status} ${method} ${fullUrl}`,
      {
        method,
        url: fullUrl,
        status,
        statusText: response.statusText,
        data: response.data,
        headers: response.headers,
        requestTime,
        latency,
      }
    );

    console.log(`[API Response] ${method} ${url}`, response.data);
    return response;
  },
  (error: AxiosError) => {
    const method = error.config?.method?.toUpperCase() || 'UNKNOWN';
    const url = error.config?.url || '';
    const fullUrl = error.config ? `${error.config.baseURL}${url}` : url;
    const status = error.response?.status;
    const message = error.response?.data
      ? (error.response.data as any)?.detail || (error.response.data as any)?.message || '请求失败'
      : error.message || '网络错误';

    logger.error(
      'API Error',
      `API Error: ${status || 'NO_STATUS'} ${method} ${fullUrl}`,
      {
        method,
        url: fullUrl,
        status,
        statusText: error.response?.statusText,
        message,
        responseData: error.response?.data,
        requestData: error.config?.data,
        requestParams: error.config?.params,
      }
    );

    console.error(`[API Error] ${method} ${url}`, {
      status,
      message,
    });

    if (error.response?.status === 500) {
      console.error('[Server Error]', error.response.data);
    } else if (error.response?.status === 422) {
      console.error('[Validation Error]', error.response.data);
    }

    alert(`错误: ${message}`);
    return Promise.reject(error);
  }
);

export const workflowApi = {
  start: async (request: WorkflowStartRequest): Promise<WorkflowStartResponse> => {
    const response = await apiClient.post<WorkflowStartResponse>(
      '/workflow/start',
      request
    );
    return response.data;
  },

  getTypes: async (): Promise<{ id: string; name: string }[]> => {
    const response = await apiClient.get<{ id: string; name: string }[]>('/workflow/types');
    return response.data;
  },

  getState: async (workflowId: string): Promise<WorkflowState> => {
    const response = await apiClient.get<WorkflowState>(
      `/workflow/${workflowId}/state`
    );
    return response.data;
  },

  getTrace: async (workflowId: string): Promise<WorkflowTrace> => {
    const response = await apiClient.get<WorkflowTrace>(
      `/workflow/${workflowId}/trace`
    );
    return response.data;
  },

  getTasks: async (workflowType: string): Promise<WorkflowTaskItem[]> => {
    const response = await apiClient.get<WorkflowTaskItem[]>('/workflow/tasks', {
      params: { workflow_type: workflowType },
    });
    return response.data;
  },

  /** 一次请求拉取多种类型的任务，返回 { workflow_type: WorkflowTaskItem[] } */
  getTasksBatch: async (
    workflowTypes: string[]
  ): Promise<Record<string, WorkflowTaskItem[]>> => {
    if (workflowTypes.length === 0) return {};
    const response = await apiClient.get<Record<string, WorkflowTaskItem[]>>(
      '/workflow/tasks/batch',
      { params: { workflow_types: workflowTypes.join(',') } }
    );
    return response.data || {};
  },
  getHistory: async (workflowId: string, limit = 50): Promise<{ checkpoint_id: string; metadata?: Record<string, unknown>; values?: Record<string, unknown> }[]> => {
    const response = await apiClient.get(`/workflow/${workflowId}/history`, { params: { limit } });
    return response.data;
  },
  resume: async (workflowId: string, userFeedback: string): Promise<{ workflow_id: string; status: string }> => {
    const response = await apiClient.post<{ workflow_id: string; status: string }>(
      `/workflow/${workflowId}/resume`,
      { user_feedback: userFeedback }
    );
    return response.data;
  },
};

/** /monitor/resources 会拉取 Celery inspect，耗时可能超过默认 30s，单独延长超时 */
const MONITOR_RESOURCES_TIMEOUT_MS = 60000;

export const monitorApi = {
  getResources: async (): Promise<MonitorStats> => {
    const response = await apiClient.get<MonitorStats>('/monitor/resources', {
      timeout: MONITOR_RESOURCES_TIMEOUT_MS,
    });
    return response.data;
  },
  purgeQueue: async (queueName: string): Promise<{ success: boolean; purged: number; queue: string }> => {
    const response = await apiClient.post<{ success: boolean; purged: number; queue: string }>(
      `/monitor/queues/${queueName}/purge`
    );
    return response.data;
  },
  purgeAllQueues: async (): Promise<{ success: boolean; total_purged: number; queues: Record<string, number> }> => {
    const response = await apiClient.post<{ success: boolean; total_purged: number; queues: Record<string, number> }>(
      '/monitor/queues/purge-all'
    );
    return response.data;
  },
  startController: async (): Promise<{ status: string }> => {
    const response = await apiClient.post<{ status: string }>('/monitor/controller/start');
    return response.data;
  },
  disableAgent: async (agentName: string): Promise<{ success: boolean; agent: string; status: string }> => {
    const response = await apiClient.post<{ success: boolean; agent: string; status: string }>(
      `/monitor/agents/${agentName}/disable`
    );
    return response.data;
  },
  enableAgent: async (agentName: string): Promise<{ success: boolean; agent: string; status: string; redriven?: number }> => {
    const response = await apiClient.post<{ success: boolean; agent: string; status: string; redriven?: number }>(
      `/monitor/agents/${agentName}/enable`
    );
    return response.data;
  },
};

export const healthApi = {
  check: async (): Promise<{ status: string; service: string }> => {
    const response = await apiClient.get<{ status: string; service: string }>('/health');
    return response.data;
  },
};

export interface PromptExpectedKeysResponse {
  keys: string[];
}

const DEFAULT_WORKFLOW = '';

export const promptApi = {
  getAll: async (workflowType?: string): Promise<PromptTemplate[]> => {
    const params = workflowType !== undefined && workflowType !== null ? { workflow_type: workflowType } : {};
    const response = await apiClient.get<PromptTemplate[]>('/api/prompts', { params });
    return response.data;
  },
  getExpectedKeys: async (): Promise<PromptExpectedKeysResponse> => {
    const response = await apiClient.get<PromptExpectedKeysResponse>('/api/prompts/expected-keys');
    return response.data;
  },
  getByKey: async (key: string, workflowType: string = DEFAULT_WORKFLOW): Promise<PromptTemplate> => {
    if (workflowType === DEFAULT_WORKFLOW) {
      const response = await apiClient.get<PromptTemplate>(`/api/prompts/${encodeURIComponent(key)}`);
      return response.data;
    }
    const response = await apiClient.get<PromptTemplate>(`/api/prompts/by-key/${encodeURIComponent(key)}`, {
      params: { workflow_type: workflowType },
    });
    return response.data;
  },
  update: async (key: string, data: PromptUpdatePayload, workflowType: string = DEFAULT_WORKFLOW): Promise<PromptTemplate> => {
    if (workflowType === DEFAULT_WORKFLOW) {
      const response = await apiClient.put<PromptTemplate>(`/api/prompts/${encodeURIComponent(key)}`, data);
      return response.data;
    }
    const response = await apiClient.put<PromptTemplate>(
      `/api/prompts/by-key/${encodeURIComponent(key)}`,
      data,
      { params: { workflow_type: workflowType } }
    );
    return response.data;
  },
  create: async (data: {
    key: string;
    workflow_type?: string;
    content?: string;
    description?: string | null;
  }): Promise<PromptTemplate> => {
    const response = await apiClient.post<PromptTemplate>('/api/prompts', {
      key: data.key,
      workflow_type: data.workflow_type ?? DEFAULT_WORKFLOW,
      content: data.content ?? '',
      description: data.description ?? null,
      is_active: true,
    });
    return response.data;
  },
};

export interface PendingItem {
  id: string;
  write_type: string;
  novel_id: string;
  novel_title: string;
  chapter_index: number;
  workflow_id: string | null;
  source_agent: string | null;
  status: string;
  created_at: string | null;
  payload_preview: string;
  existing_has_summary: boolean;
  existing_has_content: boolean;
  existing_summary_preview: string | null;
  existing_content_preview: string | null;
}

export interface PendingDetail {
  id: string;
  write_type: string;
  novel_id: string;
  novel_title: string;
  chapter_index: number;
  workflow_id: string | null;
  source_agent: string | null;
  status: string;
  created_at: string | null;
  payload: { content?: string; summary?: string; critique_data?: unknown };
  existing_summary: string | null;
  existing_content: string | null;
  existing_critique_data: unknown;
}

export interface WorkflowWithCount {
  workflow_id: string;
  count: number;
}

export interface WorkflowTypeWithCount {
  workflow_type: string;
  count: number;
}

/** 启动形式 id -> 展示名（与后端 workflows 注册一致） */
export const WORKFLOW_TYPE_LABELS: Record<string, string> = {
  generate_chapter: '生成新章节',
  outline_only: '仅生成大纲',
  content_only: '仅生成正文',
  approval_only: '仅进行审批',
  media_only: '仅生成媒体',
};

export const approvalsApi = {
  listWorkflowTypesWithPending: async (status?: string): Promise<WorkflowTypeWithCount[]> => {
    const params = status ? { status } : {};
    const response = await apiClient.get<WorkflowTypeWithCount[]>('/approvals/workflow-types', { params });
    return response.data;
  },
  listWorkflowsWithPending: async (status?: string, workflowType?: string | null): Promise<WorkflowWithCount[]> => {
    const params: Record<string, string> = {};
    if (status) params.status = status;
    if (workflowType != null && workflowType !== '') params.workflow_type = workflowType;
    const response = await apiClient.get<WorkflowWithCount[]>('/approvals/workflows', { params });
    return response.data;
  },
  listPending: async (
    status?: string,
    workflowId?: string | null,
    workflowType?: string | null
  ): Promise<PendingItem[]> => {
    const params: Record<string, string> = {};
    if (status) params.status = status;
    if (workflowId != null && workflowId !== '') params.workflow_id = workflowId;
    if (workflowType != null && workflowType !== '') params.workflow_type = workflowType;
    const response = await apiClient.get<PendingItem[]>('/approvals/pending', { params });
    return response.data;
  },
  getDetail: async (pendingId: string): Promise<PendingDetail> => {
    const response = await apiClient.get<PendingDetail>(`/approvals/pending/${pendingId}`);
    return response.data;
  },
  approve: async (pendingId: string): Promise<{ success: boolean; draft_id?: string }> => {
    const response = await apiClient.post<{ success: boolean; draft_id?: string }>(
      `/approvals/pending/${pendingId}/approve`
    );
    return response.data;
  },
  reject: async (pendingId: string): Promise<{ success: boolean }> => {
    const response = await apiClient.post<{ success: boolean }>(
      `/approvals/pending/${pendingId}/reject`
    );
    return response.data;
  },
};

export interface SystemConcept {
  id: string;
  key: string;
  label: string;
  description: string | null;
  scope: string | null;
  sort_order: number;
}

export const helpApi = {
  getConcepts: async (scope?: string): Promise<SystemConcept[]> => {
    const params = scope ? { scope } : {};
    const response = await apiClient.get<SystemConcept[]>('/api/help/concepts', { params });
    return response.data;
  },
  getConcept: async (key: string): Promise<SystemConcept> => {
    const response = await apiClient.get<SystemConcept>(`/api/help/concepts/${encodeURIComponent(key)}`);
    return response.data;
  },
  updateConcept: async (
    key: string,
    body: { label: string; description?: string | null; scope?: string | null; sort_order?: number }
  ): Promise<SystemConcept> => {
    const response = await apiClient.put<SystemConcept>(`/api/help/concepts/${encodeURIComponent(key)}`, body);
    return response.data;
  },
};

/** 检索（向量/RAG）API：仅手动调用，不进入工作流 */
export interface RetrievalSearchItem {
  text: string;
  novel_name: string;
  chapter_num: number | null;
  distance: number;
  metadata?: Record<string, unknown>;
}

export interface IndexedNovel {
  novel_id: string;
  novel_title: string;
  chapters: number[];
}

export const retrievalApi = {
  search: async (params: {
    q: string;
    novel_id?: string | null;
    top_k?: number;
  }): Promise<RetrievalSearchItem[]> => {
    const { q, novel_id, top_k = 10 } = params;
    const p: Record<string, string | number> = { q, top_k };
    if (novel_id != null && novel_id !== '') p.novel_id = novel_id;
    const response = await apiClient.get<RetrievalSearchItem[]>('/retrieval/search', { params: p });
    return response.data;
  },
  listIndexed: async (): Promise<IndexedNovel[]> => {
    const response = await apiClient.get<IndexedNovel[]>('/retrieval/indexed');
    return response.data;
  },
  addIndex: async (novel_id: string, chapter_index: number): Promise<{ success: boolean; novel_title: string; chapter_index: number }> => {
    const response = await apiClient.post<{ success: boolean; novel_title: string; chapter_index: number }>(
      '/retrieval/index',
      { novel_id, chapter_index }
    );
    return response.data;
  },
  deleteIndex: async (novel_id: string, chapter_index?: number | null): Promise<{ success: boolean; novel_title: string; chapter_index?: number | null }> => {
    const params: Record<string, string | number> = { novel_id };
    if (chapter_index != null) params.chapter_index = chapter_index;
    const response = await apiClient.delete<{ success: boolean; novel_title: string; chapter_index?: number | null }>(
      '/retrieval/index',
      { params }
    );
    return response.data;
  },
};

/** Index Inspector：向量透视 + 图谱导出，与后端 /inspector 保持一致 */
export interface InspectorVectorChunk {
  text: string;
  metadata?: Record<string, unknown> | null;
  distance: number | null;
  novel_name: string;
  id?: string | null;
}

export interface InspectorGraphNode {
  id: string;
  label?: string | null;
  type?: string | null;
  status?: string | null;
  description?: string | null;
}

export interface InspectorGraphEdgeProperties {
  chapter?: number | null;
  location?: string | null;
  state?: string | null;
  quote?: string | null;
  context?: string | null;
}

export interface InspectorGraphLink {
  source: string;
  target: string;
  relation?: string | null;
  properties?: InspectorGraphEdgeProperties | null;
}

export type InspectorGraphLinkWithProps = InspectorGraphLink;

export interface InspectorGraphExport {
  nodes: InspectorGraphNode[];
  links: InspectorGraphLink[];
}

export const inspectorApi = {
  getVectorChunks: async (params: {
    novel_id: string;
    q?: string | null;
    top_k?: number;
    limit?: number;
    offset?: number;
  }): Promise<InspectorVectorChunk[]> => {
    const p: Record<string, string | number> = { novel_id: params.novel_id };
    if (params.q != null && params.q !== '') p.q = params.q;
    if (params.top_k != null) p.top_k = params.top_k;
    if (params.limit != null) p.limit = params.limit;
    if (params.offset != null) p.offset = params.offset;
    const response = await apiClient.get<InspectorVectorChunk[]>('/inspector/vector/chunks', { params: p });
    return response.data;
  },
  getGraph: async (novel_id: string): Promise<InspectorGraphExport> => {
    const response = await apiClient.get<InspectorGraphExport>('/inspector/graph', {
      params: { novel_id },
    });
    return response.data;
  },
};
