export type LogType = 'INFO' | 'WARN' | 'ERROR' | 'ACTION' | 'NETWORK';

export interface LogEntry {
  timestamp: string;
  type: LogType;
  category: string;
  message: string;
  data?: any;
}

class Logger {
  private logs: LogEntry[] = [];
  private maxLogs = 10000;

  log(type: LogType, category: string, message: string, data?: any): void {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      type,
      category,
      message,
      data: data ? JSON.parse(JSON.stringify(data)) : undefined,
    };

    this.logs.push(entry);

    if (this.logs.length > this.maxLogs) {
      this.logs.shift();
    }

    const consoleMethod =
      type === 'ERROR' ? 'error' : type === 'WARN' ? 'warn' : 'log';

    console.groupCollapsed(
      `[${entry.timestamp}] ${type} | ${category} | ${message}`
    );
    if (data) {
      console[consoleMethod](data);
    }
    console.groupEnd();
  }

  info(category: string, message: string, data?: any): void {
    this.log('INFO', category, message, data);
  }

  warn(category: string, message: string, data?: any): void {
    this.log('WARN', category, message, data);
  }

  error(category: string, message: string, data?: any): void {
    this.log('ERROR', category, message, data);
  }

  action(category: string, message: string, data?: any): void {
    this.log('ACTION', category, message, data);
  }

  network(category: string, message: string, data?: any): void {
    this.log('NETWORK', category, message, data);
  }

  async exportLogs(): Promise<string> {
    const exportData = {
      exportedAt: new Date().toISOString(),
      totalLogs: this.logs.length,
      logs: this.logs,
    };

    const jsonString = JSON.stringify(exportData, null, 2);

    try {
      await navigator.clipboard.writeText(jsonString);
      return jsonString;
    } catch (error) {
      console.error('Failed to copy to clipboard:', error);
      return jsonString;
    }
  }

  clear(): void {
    this.logs = [];
    this.info('Logger', 'Logs cleared');
  }

  getLogs(): LogEntry[] {
    return [...this.logs];
  }

  getLogCount(): number {
    return this.logs.length;
  }
}

export const logger = new Logger();

if (typeof window !== 'undefined') {
  (window as any).__LOGGER__ = logger;
}
