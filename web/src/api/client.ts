import axios, { AxiosError } from 'axios';
import { logger } from '../utils/logger';
import type {
  WorkflowStartRequest,
  WorkflowStartResponse,
  WorkflowState,
  WorkflowTrace,
  MonitorStats,
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
