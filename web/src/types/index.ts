export const EventType = {
  WORKFLOW_STARTED: 'workflow_started',
  TASK_DISPATCHED: 'task_dispatched',
  TASK_STARTED: 'task_started',
  TASK_COMPLETED: 'task_completed',
  TASK_FAILED: 'task_failed',
  OUTLINE_GENERATED: 'outline_generated',
  CONTENT_WRITTEN: 'content_written',
  CRITIQUE_COMPLETED: 'critique_completed',
  REVISION_REQUESTED: 'revision_requested',
  MEDIA_GENERATED: 'media_generated',
} as const;

export type EventType = typeof EventType[keyof typeof EventType];

export const EventSource = {
  DISPATCHER: 'dispatcher',
  AGENT_WRITER: 'agent_writer',
  AGENT_CRITIC: 'agent_critic',
  AGENT_ARCHITECT: 'agent_architect',
  AGENT_MEDIA: 'agent_media',
  SYSTEM: 'system',
} as const;

export type EventSource = typeof EventSource[keyof typeof EventSource];

export interface AuditLogEntry {
  timestamp: string;
  workflow_id: string;
  source: string;
  event_type: string;
  details: Record<string, any>;
  task_id?: string;
  error?: string;
}

export interface WorkflowState {
  workflow_id: string;
  novel_name: string;
  chapter_num: number;
  status: string;
  outline?: string;
  draft_content?: string;
  critique_score?: number;
  critique_comments?: string;
  revision_count: number;
  created_at?: string;
}

export interface WorkflowTrace {
  workflow_id: string;
  logs: AuditLogEntry[];
}

export interface WorkflowStartRequest {
  novel_name: string;
  chapter_num: number;
}

export interface WorkflowStartResponse {
  workflow_id: string;
  status: string;
  task_id?: string;
  /** 发送任务后立刻读到的 architect_pending 队列长度，便于确认入队情况 */
  architect_pending_after_send?: number;
}

// 重新导出 monitor.ts 中的所有类型
export type {
  AgentMetric,
  AgentQueueStats,
  ControllerStats,
} from './monitor';

// 注意：monitor.ts 中也有 MonitorStats，但这里的定义不同，用于 API 响应
// 如果需要使用 monitor.ts 中的 MonitorStats，请直接从 './monitor' 导入
export interface MonitorStats {
  stats: {
    queues?: {
      text_queue?: number;
      media_queue?: number;
      rag_queue?: number;
    };
    [key: string]: any;
  };
}

export interface ChapterNode {
  id: number;
  title: string;
  status: 'draft' | 'writing' | 'critiquing' | 'finished' | 'failed';
}

export interface Novel {
  id: string;
  title: string;
  genre?: string;
  summary?: string;
  created_at: string;
}

export interface Chapter {
  id: string;
  novel_id: string;
  index: number;
  title?: string;
  status: string;
  created_at: string;
}
