import * as React from 'react';
import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import { Button } from '../components/ui/button';
import { DollarSign, Database, Activity, Eye, Filter, X } from 'lucide-react';
import { monitorApi } from '../api/client';
import { useQuery } from '@tanstack/react-query';

interface RequestLog {
  timestamp: string;
  endpoint: string;
  method: string;
  latency: number;
  status: number;
  cost: number;
  request?: any;
  response?: any;
  rawTimestamp: number;
}

interface FilterState {
  status: string;
  method: string;
  search: string;
}

const INPUT_PRICE_PER_1K = 0.0001;
const OUTPUT_PRICE_PER_1K = 0.0003;

function calculateCost(promptTokens: number, completionTokens: number): number {
  return (promptTokens / 1000) * INPUT_PRICE_PER_1K + (completionTokens / 1000) * OUTPUT_PRICE_PER_1K;
}

export default function ResourceMonitor() {
  const { t } = useTranslation();
  const [selectedLog, setSelectedLog] = useState<RequestLog | null>(null);
  const [logs, setLogs] = useState<RequestLog[]>([]);
  const [filters, setFilters] = useState<FilterState>({
    status: 'all',
    method: 'all',
    search: '',
  });

  const { data: monitorStats } = useQuery({
    queryKey: ['monitor', 'resources'],
    queryFn: () => monitorApi.getResources(),
    refetchInterval: 5000,
  });

  React.useEffect(() => {
    const updateLogs = () => {
      if (typeof window !== 'undefined' && (window as any).__LOGGER__) {
        const loggerInstance = (window as any).__LOGGER__;
        const allLogs = loggerInstance.logs || [];
        const networkLogs = allLogs
          .filter((log: any) => log.type === 'NETWORK' && log.category === 'API Response')
          .map((log: any) => {
            const rawTimestamp = new Date(log.timestamp).getTime();
            const latency = log.data?.latency || 0;
            return {
              timestamp: new Date(log.timestamp).toLocaleString(),
              endpoint: log.data?.url?.replace(/^https?:\/\/[^/]+/, '') || '',
              method: log.data?.method || 'GET',
              latency: latency > 0 ? latency : 0,
              status: log.data?.status || 200,
              cost: 0,
              request: log.data,
              response: log.data,
              rawTimestamp,
            };
          })
          .slice(-100)
          .reverse();
        setLogs(networkLogs);
      }
    };

    updateLogs();
    const interval = setInterval(updateLogs, 2000);
    return () => clearInterval(interval);
  }, []);

  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      if (filters.status !== 'all') {
        if (filters.status === '200' && log.status !== 200) {
          return false;
        }
        if (filters.status === '400' && (log.status < 400 || log.status >= 500)) {
          return false;
        }
        if (filters.status === '500' && log.status < 500) {
          return false;
        }
      }
      if (filters.method !== 'all' && filters.method !== log.method) {
        return false;
      }
      if (filters.search && !log.endpoint.toLowerCase().includes(filters.search.toLowerCase())) {
        return false;
      }
      return true;
    });
  }, [logs, filters]);

  const llmStats = useMemo(() => {
    if (!monitorStats?.stats) return { totalTokens: 0, totalCost: 0, totalCalls: 0, totalPromptTokens: 0, totalCompletionTokens: 0 };
    
    let totalPromptTokens = 0;
    let totalCompletionTokens = 0;
    let totalCalls = 0;

    Object.entries(monitorStats.stats).forEach(([key, workflowStats]: [string, any]) => {
      if (key === 'queues') return;
      
      if (workflowStats.prompt_tokens) {
        totalPromptTokens += parseInt(String(workflowStats.prompt_tokens)) || 0;
      }
      if (workflowStats.completion_tokens) {
        totalCompletionTokens += parseInt(String(workflowStats.completion_tokens)) || 0;
      }
      if (workflowStats.api_calls) {
        totalCalls += parseInt(String(workflowStats.api_calls)) || 0;
      }
    });

    const totalTokens = totalPromptTokens + totalCompletionTokens;
    const totalCost = calculateCost(totalPromptTokens, totalCompletionTokens);

    return { totalTokens, totalCost, totalCalls, totalPromptTokens, totalCompletionTokens };
  }, [monitorStats]);

  const totalCalls = filteredLogs.length;

  return (
    <div className="h-full w-full overflow-auto bg-zinc-50 dark:bg-zinc-900 pt-8">
      <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-10 py-12 space-y-12">
        <div>
          <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-100 mb-4 leading-tight">{t('resources.title')}</h1>
          <p className="text-zinc-600 dark:text-zinc-400 leading-relaxed">{t('resources.subtitle')}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <Card className="bg-white/50 dark:bg-zinc-900/30">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-zinc-600 dark:text-zinc-400 flex items-center gap-3 leading-relaxed">
                <Database className="w-5 h-5" />
                {t('resources.cards.llm_token_usage')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-zinc-900 dark:text-zinc-100 leading-tight mb-3">
                {llmStats.totalTokens.toLocaleString()}
              </div>
              <div className="text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
                {t('resources.list.input')}: {llmStats.totalPromptTokens.toLocaleString()} / {t('resources.list.output')}: {llmStats.totalCompletionTokens.toLocaleString()}
              </div>
            </CardContent>
          </Card>

          <Card className="bg-white/50 dark:bg-zinc-900/30">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-zinc-600 dark:text-zinc-400 flex items-center gap-3 leading-relaxed">
                <DollarSign className="w-5 h-5" />
                LLM Estimated Cost
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-zinc-900 dark:text-zinc-100 leading-tight mb-3">
                ${llmStats.totalCost.toFixed(4)}
              </div>
              <div className="text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
                LLM API 调用成本
              </div>
            </CardContent>
          </Card>

          <Card className="bg-white/50 dark:bg-zinc-900/30">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-zinc-600 dark:text-zinc-400 flex items-center gap-3 leading-relaxed">
                <Activity className="w-5 h-5" />
                {t('resources.cards.api_calls')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-zinc-900 dark:text-zinc-100 leading-tight mb-3">
                {totalCalls}
              </div>
              <div className="text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
                {t('resources.cards.api_calls_filtered')}
              </div>
            </CardContent>
          </Card>
        </div>

        <Card className="bg-white/50 dark:bg-zinc-900/30">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 leading-tight mb-4">
                {t('resources.list.api_request_logs')}
              </CardTitle>
              <div className="flex items-center gap-2">
                {(filters.status !== 'all' || filters.method !== 'all' || filters.search) && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setFilters({ status: 'all', method: 'all', search: '' })}
                    className="text-xs"
                  >
                    <X className="w-3 h-3 mr-1" />
                    {t('resources.list.clear_filter')}
                  </Button>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="mb-6 flex flex-wrap gap-4 items-center">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-zinc-500" />
                <span className="text-sm text-zinc-600 dark:text-zinc-400">{t('resources.list.filter')}:</span>
              </div>
              
              <select
                value={filters.status}
                onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                className="px-3 py-1.5 text-sm bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-md text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="all">{t('resources.list.all_status')}</option>
                <option value="200">200 OK</option>
                <option value="400">4xx 错误</option>
                <option value="500">5xx 错误</option>
              </select>

              <select
                value={filters.method}
                onChange={(e) => setFilters({ ...filters, method: e.target.value })}
                className="px-3 py-1.5 text-sm bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-md text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="all">{t('resources.list.all_methods')}</option>
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
                <option value="DELETE">DELETE</option>
              </select>

              <input
                type="text"
                placeholder={t('resources.list.search_endpoint')}
                value={filters.search}
                onChange={(e) => setFilters({ ...filters, search: e.target.value })}
                className="px-3 py-1.5 text-sm bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-md text-zinc-900 dark:text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 min-w-[200px]"
              />
            </div>

            <ScrollArea className="h-[500px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="tracking-widest uppercase">{t('resources.list.timestamp')}</TableHead>
                    <TableHead className="tracking-widest uppercase">{t('resources.list.endpoint')}</TableHead>
                    <TableHead className="tracking-widest uppercase">{t('resources.list.method')}</TableHead>
                    <TableHead className="tracking-widest uppercase">{t('resources.list.latency')}</TableHead>
                    <TableHead className="tracking-widest uppercase">{t('common.status')}</TableHead>
                    <TableHead className="tracking-widest uppercase">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredLogs.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center text-zinc-500 py-12 leading-relaxed">
                        {logs.length === 0 ? t('resources.list.no_logs') : t('resources.list.no_matching_logs')}
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredLogs.map((log, idx) => (
                      <TableRow
                        key={idx}
                        className="cursor-pointer hover:bg-zinc-100/50 dark:hover:bg-white/5"
                        onClick={() => setSelectedLog(log)}
                      >
                        <TableCell className="font-mono text-xs leading-relaxed">{log.timestamp}</TableCell>
                        <TableCell className="font-mono text-xs max-w-xs truncate leading-relaxed">
                          {log.endpoint}
                        </TableCell>
                        <TableCell>
                          <Badge variant={log.method === 'GET' ? 'default' : 'warning'}>
                            {log.method}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono leading-relaxed">{log.latency.toFixed(0)}ms</TableCell>
                        <TableCell>
                          <Badge
                            variant={log.status >= 400 ? 'error' : log.status >= 200 && log.status < 300 ? 'success' : 'default'}
                          >
                            {log.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Eye className="w-4 h-4 text-zinc-400" />
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </ScrollArea>
          </CardContent>
        </Card>

        {selectedLog && (
          <Card className="bg-white/50 dark:bg-zinc-900/30">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 leading-tight mb-4">
                  {t('resources.list.request_details')}
                </CardTitle>
                <button
                  onClick={() => setSelectedLog(null)}
                  className="text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
                >
                  ×
                </button>
              </div>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[400px]">
                <div className="space-y-6">
                  <div>
                    <h3 className="text-sm font-semibold mb-4 text-zinc-700 dark:text-zinc-300 leading-relaxed">{t('resources.list.request')}</h3>
                    <pre className="p-6 bg-zinc-100/50 dark:bg-zinc-900/50 rounded-lg text-xs overflow-auto leading-relaxed">
                      {JSON.stringify(selectedLog.request, null, 2)}
                    </pre>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold mb-4 text-zinc-700 dark:text-zinc-300 leading-relaxed">{t('resources.list.response')}</h3>
                    <pre className="p-6 bg-zinc-100/50 dark:bg-zinc-900/50 rounded-lg text-xs overflow-auto leading-relaxed">
                      {JSON.stringify(selectedLog.response, null, 2)}
                    </pre>
                  </div>
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
