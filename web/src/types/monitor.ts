export interface AgentQueueStats {
  pending: number;
  completed: number;
  suspended?: number;
}

export interface AgentMetric {
  name: string;
  is_online: boolean;
  queues: AgentQueueStats;
  current_task_id?: string;
  status?: 'idle' | 'busy';
  /** 是否正在执行任务（Redis agent:{name}:processing 存在） */
  is_processing?: boolean;
}

export interface ControllerStats {
  is_active: boolean;
  uptime?: number;
  total_routed?: number;
}

export interface MonitorStats {
  agents: Record<string, AgentMetric>;
  controller: ControllerStats;
  queue_lengths: Record<string, number>;
}
