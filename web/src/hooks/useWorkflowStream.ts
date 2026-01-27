import { useEffect, useRef, useState } from 'react';

const WS_BASE = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000')
  .replace(/^http/, 'ws');

export type WorkflowStreamEvent = {
  workflow_id: string;
  kind: string;
  node?: string;
  data?: Record<string, unknown>;
};

export function useWorkflowStream(workflowId: string | null) {
  const [lastEvent, setLastEvent] = useState<WorkflowStreamEvent | null>(null);
  const [status, setStatus] = useState<'idle' | 'connecting' | 'connected' | 'closed' | 'error'>('idle');
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!workflowId) {
      setStatus('idle');
      setLastEvent(null);
      return;
    }
    const url = `${WS_BASE}/ws/workflow?workflow_id=${encodeURIComponent(workflowId)}`;
    setStatus('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setStatus('connected');
    ws.onclose = () => setStatus('closed');
    ws.onerror = () => setStatus('error');
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        setLastEvent(msg);
      } catch {
        // ignore
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [workflowId]);

  return { lastEvent, status };
}
