import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

console.log('[Main] Starting application...');

// 确保 root 元素存在
const rootElement = document.getElementById('root');
if (!rootElement) {
  document.body.innerHTML = '<div style="padding: 20px; color: red; font-size: 16px;">错误: 找不到 root 元素 (#root)</div>';
  throw new Error('Root element not found');
}

// 初始化应用
async function initApp() {
  try {
    console.log('[Main] Loading i18n...');
    // 加载 i18n
    try {
      await import('./lib/i18n');
      console.log('[Main] i18n loaded');
    } catch (error) {
      console.error('[Main] Failed to load i18n:', error);
    }

    // 加载 logger
    let logger: any = null;
    try {
      const loggerModule = await import('./utils/logger');
      logger = loggerModule.logger;
      console.log('[Main] Logger loaded');
    } catch (error) {
      console.error('[Main] Failed to load logger:', error);
      // 创建一个简单的 logger 替代
      logger = {
        error: (...args: any[]) => console.error('[Logger]', ...args),
        info: (...args: any[]) => console.log('[Logger]', ...args),
        warn: (...args: any[]) => console.warn('[Logger]', ...args),
      };
    }

    // 设置全局错误处理
    window.onerror = (message, source, lineno, colno, error) => {
      const errorInfo = {
        message: String(message),
        source,
        lineno,
        colno,
        error: error ? {
          name: error.name,
          message: error.message,
          stack: error.stack,
        } : undefined,
      };
      
      console.error('[Global Error]', errorInfo);
      if (logger) {
        logger.error('Global Error', `Unhandled error: ${message}`, errorInfo);
      }
      return false;
    };

    window.onunhandledrejection = (event) => {
      const errorInfo = {
        reason: event.reason,
        promise: event.promise,
      };
      
      console.error('[Unhandled Promise Rejection]', errorInfo);
      if (logger) {
        logger.error('Unhandled Promise Rejection', `Promise rejected: ${event.reason}`, errorInfo);
      }
    };

    console.log('[Main] Loading App component...');
    const { default: App } = await import('./App.tsx');
    
    console.log('[Main] Rendering App...');
    createRoot(rootElement).render(
      <StrictMode>
        <App />
      </StrictMode>,
    );
    
    console.log('[Main] Application rendered successfully');
    
    if (logger) {
      logger.info('App', 'Application started', {
        userAgent: navigator.userAgent,
        url: window.location.href,
        timestamp: new Date().toISOString(),
      });
    }
  } catch (error) {
    console.error('[Main] Failed to initialize app:', error);
    rootElement.innerHTML = `
      <div style="padding: 20px; color: red; font-family: monospace;">
        <h1 style="font-size: 24px; margin-bottom: 10px;">应用启动失败</h1>
        <p style="font-size: 16px; margin-bottom: 10px;">${error instanceof Error ? error.message : String(error)}</p>
        <pre style="background: #f0f0f0; padding: 10px; margin-top: 10px; overflow: auto; font-size: 12px;">
${error instanceof Error ? error.stack : String(error)}
        </pre>
        <button onclick="window.location.reload()" style="margin-top: 10px; padding: 8px 16px; background: #007bff; color: white; border: none; cursor: pointer;">
          刷新页面
        </button>
      </div>
    `;
  }
}

// 启动应用
initApp().catch((error) => {
  console.error('[Main] Unhandled error in initApp:', error);
  if (rootElement) {
    rootElement.innerHTML = `
      <div style="padding: 20px; color: red;">
        <h1>严重错误</h1>
        <p>${String(error)}</p>
      </div>
    `;
  }
});
